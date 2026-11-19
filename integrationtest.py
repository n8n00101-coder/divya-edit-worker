"""Integration rig (runner half): agent_runner.py against a stub
Worker over REAL HTTP.

The Worker half of the integration (creation handler, token gate,
dispatch, status, stop, result/refund) is proven in
integrationtest.mjs against the real divya.js. This half proves the
runner claim end to end: agent_runner.py runs as a subprocess with
the same env agent.yml gives it, talking to a stub Worker that
implements the REAL runner channel — GET setup/runner/job, POST
setup/runner/progress, POST setup/runner/result, POST
setup/runner/agentstep (scripted brain), POST setup/runner/agentsteps
(step recording) — over one shared in-memory job record.

Scenarios:
  A (done):       a parity-style mini task (seeded orders.csv →
                  compute_csv → filter_csv → file_write summary →
                  verify_file_contains + verify_csv_subset) ends
                  DONE by evidence auto-close; cleaned.csv is exact;
                  the terminal state + answer land on the record.
  B (unverified): the brain writes a wrong fact and twice claims
                  done against declared evidence it never met — the
                  run ends UNVERIFIED on the record, no answer.
  C (resume):     the record already holds a completed compute step
                  from a "dead" runner; the new runner resumes —
                  the completed step is NOT re-executed (the brain
                  is never asked for it again) and the job finishes.

Run with a python that has httpx + playwright installed (setup.py
imports playwright at module level):
  /tmp/agentrig-venv/bin/python integrationtest.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER_KEY = "test-runner"

STATE = {"record": None, "brain": [], "brain_bodies": [], "results": []}

FAILS = []


def check(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


class StubWorker(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self):
        return self.headers.get("x-runner-key") == RUNNER_KEY

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        if not self._auth():
            return self._json({"error": "no"}, 403)
        if self.path.startswith("/api/setup/runner/job"):
            return self._json({"ok": True, "job": STATE["record"]})
        return self._json({"error": "nf"}, 404)

    def do_POST(self):
        if not self._auth():
            return self._json({"error": "no"}, 403)
        rec = STATE["record"]
        body = self._body()
        route = self.path.split("?")[0]
        if route == "/api/setup/runner/agentsteps":
            rec.setdefault("steps", []).append(body.get("step") or {})
            return self._json({"ok": True, "steps": len(rec["steps"])})
        if route == "/api/setup/runner/agentstep":
            STATE["brain_bodies"].append(body)
            if not STATE["brain"]:
                return self._json({"ok": False, "error": "brain"})
            return self._json({"ok": True, "action": STATE["brain"].pop(0)})
        if route == "/api/setup/runner/progress":
            rec["state"] = body.get("state") or rec.get("state")
            rec["step"] = body.get("step") or rec.get("step")
            if body.get("note"):
                rec["note"] = body["note"]
            return self._json({"ok": True})
        if route == "/api/setup/runner/result":
            status = str(body.get("status") or "failed")
            if status not in ("done", "failed", "stopped", "unverified"):
                status = "failed"
            rec["state"] = status
            if body.get("answer"):
                rec["answer"] = body["answer"]
            if body.get("error"):
                rec["note"] = body["error"]
            STATE["results"].append(body)
            return self._json({"ok": True})
        return self._json({"error": "nf"}, 404)


ORDERS = "id,item,amount,status\n1,pen,100,completed\n2,book,200,completed\n3,bag,300,pending\n"
CLEANED = "id,item,amount,status\n1,pen,100,completed\n2,book,200,completed\n"

EVIDENCE_A = [
    {"tool": "verify_file_contains",
     "args": {"path": "summary.txt",
              "contains": ["completed orders: 2", "revenue: 300"]}},
    {"tool": "verify_csv_subset",
     "args": {"source": "orders.csv", "output": "cleaned.csv",
              "filter": {"column": "status", "equals": "completed"}}},
]


def tool(name, args):
    return {"action": "tool", "tool": name, "args": args}


def run_runner(port, job_id, data_dir):
    env = dict(os.environ)
    # This VM exports an egress-proxy env (http_proxy & friends, with
    # IPv6 no_proxy entries this httpx build cannot parse); the stub
    # Worker is on loopback, so the runner subprocess must connect
    # directly — drop every proxy var. (GitHub Actions, where the
    # real runner runs, has no such proxy env.)
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
              "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY"):
        env.pop(k, None)
    env.update({
        "WORKER_URL": f"http://127.0.0.1:{port}",
        "RUNNER_KEY": RUNNER_KEY,
        "JOB": job_id,
        "PROVIDER": "agent",
        "DATA_DIR": data_dir,
        "PYTHONUNBUFFERED": "1",
    })
    p = subprocess.run([sys.executable, os.path.join(HERE, "agent_runner.py")],
                       env=env, cwd=HERE, capture_output=True, text=True,
                       timeout=300)
    return p


def fresh_record(job_id, **kw):
    rec = {"job": job_id, "user": "919876543210", "provider": "agent",
           "flow": "agent", "state": "queued", "step": "starting",
           "note": "", "steps": []}
    rec.update(kw)
    STATE["record"] = rec
    STATE["brain"] = []
    STATE["brain_bodies"] = []
    STATE["results"] = []
    return rec


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubWorker)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="agentrig-")

    # ---------------- A: full task, DONE by evidence auto-close ----
    rec = fresh_record(
        "agentjobA",
        task="From orders.csv: write summary.txt with the completed "
             "order count and revenue, and cleaned.csv with only the "
             "completed orders.",
        files={"orders.csv": ORDERS}, evidence=EVIDENCE_A)
    STATE["brain"] = [
        tool("compute_csv", {"path": "orders.csv", "spec": {
            "filter": {"column": "status", "equals": "completed"},
            "sum": "amount", "count": True}}),
        tool("filter_csv", {"source": "orders.csv", "dest": "cleaned.csv",
                            "filter": {"column": "status",
                                       "equals": "completed"}}),
        tool("file_write", {"path": "summary.txt",
                            "content": "completed orders: 2\nrevenue: 300\n"}),
        tool("verify_file_contains", {"path": "summary.txt", "contains":
                                      ["completed orders: 2",
                                       "revenue: 300"]}),
        tool("verify_csv_subset", {"source": "orders.csv",
                                   "output": "cleaned.csv",
                                   "filter": {"column": "status",
                                              "equals": "completed"}}),
    ]
    p = run_runner(port, "agentjobA", tmp)
    ws = os.path.join(tmp, "agent", "agentjobA")
    check(p.returncode == 0, f"A: runner exits 0 (got {p.returncode}: {p.stderr[-300:]})")
    check(rec["state"] == "done", f"A: record ends done (got {rec['state']!r})")
    check(bool(rec.get("answer")), "A: answer recorded on the job record")
    check(os.path.isfile(os.path.join(ws, "cleaned.csv")), "A: cleaned.csv exists in the job workspace")
    with open(os.path.join(ws, "cleaned.csv")) as f:
        check(f.read() == CLEANED, "A: cleaned.csv is EXACT (header + completed rows verbatim)")
    with open(os.path.join(ws, "summary.txt")) as f:
        check(f.read() == "completed orders: 2\nrevenue: 300\n", "A: summary.txt carries the computed facts")
    completed = [s for s in rec["steps"] if s.get("phase") != "started"]
    check(len(completed) >= 5 and all(s.get("ok") for s in completed[-5:]),
          "A: every loop step recorded OK on the record")
    check(len(STATE["brain"]) == 0 and len(STATE["brain_bodies"]) == 5,
          "A: evidence auto-closed the run — no 6th brain call after the last verify")

    # ---------------- B: done claimed without evidence → UNVERIFIED -
    rec = fresh_record(
        "agentjobB",
        task="Write summary.txt stating the revenue from orders.csv.",
        files={"orders.csv": ORDERS},
        evidence=[{"tool": "verify_file_contains",
                   "args": {"path": "summary.txt",
                            "contains": ["revenue: 999"]}}])
    STATE["brain"] = [
        tool("file_write", {"path": "summary.txt",
                            "content": "revenue: 300\n"}),
        tool("verify_file_contains", {"path": "summary.txt",
                                      "contains": ["revenue: 999"]}),
        {"action": "done", "answer": "revenue is 999"},
        {"action": "done", "answer": "revenue is 999"},
    ]
    p = run_runner(port, "agentjobB", tmp)
    check(p.returncode == 0, f"B: runner exits 0 (got {p.returncode})")
    check(rec["state"] == "unverified",
          f"B: record ends UNVERIFIED, not done (got {rec['state']!r})")
    check(not rec.get("answer"), "B: no answer recorded for an unverified job")
    check(STATE["results"] and STATE["results"][-1].get("status") == "unverified",
          "B: the result post itself carried status unverified")

    # ---------------- C: resume from a dead runner's record --------
    rec = fresh_record(
        "agentjobC",
        task="From orders.csv: write summary.txt with the completed "
             "order count and revenue, and cleaned.csv with only the "
             "completed orders.",
        files={"orders.csv": ORDERS}, evidence=EVIDENCE_A,
        state="running",
        steps=[{"n": 1, "tool": "compute_csv",
                "arg": "{\"path\": \"orders.csv\"}", "ok": True,
                "result": "ok: {\"rows\": 2, \"sum\": 300}", "at": 1}])
    STATE["brain"] = [
        tool("filter_csv", {"source": "orders.csv", "dest": "cleaned.csv",
                            "filter": {"column": "status",
                                       "equals": "completed"}}),
        tool("file_write", {"path": "summary.txt",
                            "content": "completed orders: 2\nrevenue: 300\n"}),
        tool("verify_file_contains", {"path": "summary.txt", "contains":
                                      ["completed orders: 2",
                                       "revenue: 300"]}),
        tool("verify_csv_subset", {"source": "orders.csv",
                                   "output": "cleaned.csv",
                                   "filter": {"column": "status",
                                              "equals": "completed"}}),
    ]
    p = run_runner(port, "agentjobC", tmp)
    ws = os.path.join(tmp, "agent", "agentjobC")
    check(p.returncode == 0, f"C: runner exits 0 (got {p.returncode})")
    check(rec["state"] == "done", f"C: resumed job ends done (got {rec['state']!r})")
    check(len(STATE["brain_bodies"]) == 4,
          f"C: exactly 4 brain calls — the recorded compute step was NOT re-run (got {len(STATE['brain_bodies'])})")
    hist = (STATE["brain_bodies"][0].get("history") or []) if STATE["brain_bodies"] else []
    check(any("compute_csv" in str(h.get("action") or "") for h in hist),
          "C: the resumed brain's history opens with the recorded compute step")
    with open(os.path.join(ws, "cleaned.csv")) as f:
        check(f.read() == CLEANED, "C: cleaned.csv exact after resume")

    server.shutdown()
    print()
    if FAILS:
        print(f"INTEGRATIONTEST.PY: {len(FAILS)} FAILURES")
        return 1
    print("INTEGRATIONTEST.PY: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
