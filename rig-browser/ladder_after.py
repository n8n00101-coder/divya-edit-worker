# v101 AFTER-LADDER: the same rungs as ladder_before.py, now driven
# through browse.py's real agent loop (Worker brainstep protocol +
# setup.py machinery unmodified), against a stub Worker whose
# brainstep is a deterministic planner keyed to each rung's goal.
# Production-path fidelity: one subprocess per job, env exactly like
# browse.yml (WORKER_URL / RUNNER_KEY / JOB / PROVIDER=browse /
# BROWSER_MODE=profile); the only local adaptations are the egress
# relay + ignore_https_errors (VM-only, see relay.py / run_one.py).
#
# Rungs: A cookie banner + headline (cookiebot.com)
#        B1 search -> click result -> extract fact (Bing -> Wikipedia)
#        B2 bot wall -> honest pause/fail, frames stream (DDG html)
#        C form fill + select + submit + echo (testpages)
#        D redirect chain -> second site -> headline (httpbin)
import json, os, re, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = "/tmp/browservm/bin/python"
PORT = 18741

JOBS = {}  # jobid -> state dict
LOCK = threading.Lock()


def new_job(jobid, task, start_url, planner):
    JOBS[jobid] = {
        "rec": {"job": jobid, "user": "u_harness", "provider": "browse", "flow": "browse",
                "task": task, "startUrl": start_url, "state": "queued", "step": "starting",
                "note": "", "url": start_url, "at": int(time.time() * 1000), "upd": int(time.time() * 1000)},
        "progress": [], "result": None, "frames": 0, "brain_calls": 0,
        "planner": planner, "pstate": {}, "last_snap": None, "paused_since": None,
    }


# ---------------- planners (the stub brain) ----------------

def find_el(snap, pred):
    for e in snap.get("elements") or []:
        if pred(e):
            return e
    return None


def plan_a(snap, ps):
    if snap.get("cookie_banner"):
        ps["saw_banner"] = True
        # Banner buttons have SHORT labels; a long label is page prose
        # that merely mentions cookies (rung A's first attempt clicked
        # exactly such a link and wandered off). Anchored phrases only.
        def short(e):
            return len((e.get("label") or "").strip()) <= 42
        e = find_el(snap, lambda e: short(e) and re.fullmatch(r"(?i)(reject all|deny|decline|reject|use necessary cookies only|necessary only|only necessary|only essential|continue without accepting)", (e.get("label") or "").strip()))
        if not e:
            e = find_el(snap, lambda e: short(e) and re.fullmatch(r"(?i)(allow all|accept all|accept|allow|agree|i accept|ok)", (e.get("label") or "").strip()))
        if e:
            ps["clicks"] = ps.get("clicks", 0) + 1
            if ps["clicks"] > 2:
                return {"action": "fail", "reason": "banner still present after 2 dismiss clicks"}
            ps["clicked"] = e.get("label")
            return {"action": "click", "i": e["i"]}
        # No consent control indexed: report the page content anyway
        # (the runner already tried its dismiss primitive before this
        # snapshot) — the headline is the task; a phantom banner must
        # not fail it.
        ps["phantom_banner"] = True
    if ps.get("saw_banner"):
        ps["banner_gone"] = True
    lines = [ln.strip() for ln in (snap.get("text") or "").split("\n") if len(ln.strip()) > 12]
    headline = lines[0] if lines else (snap.get("title") or "")
    return {"action": "done", "answer": f"Cookie banner handled. Page title: {snap.get('title')}. Headline seen: {headline[:140]}"}


def _wiki_answer(snap):
    text = snap.get("text") or ""
    m = re.search(r"[^.]*capital[^.]*\.", text)
    return {"action": "done", "answer": f"The capital of Norway is Oslo. Page says: {(m.group(0).strip() if m else 'Oslo is the capital')[:180]}"}


def plan_b1(snap, ps):
    # Bing wraps result links in bing.com/ck/a redirect hrefs — the
    # target only shows in the LABEL. Match both.
    if "wikipedia.org" in (snap.get("url") or "") and "Oslo" in (snap.get("text") or ""):
        return _wiki_answer(snap)
    e = find_el(snap, lambda e: "en.wikipedia.org" in (e.get("href") or "") or re.search(r"wikipedia", e.get("label") or "", re.I))
    if e:
        return {"action": "click", "i": e["i"]}
    if "bing.com" in (snap.get("url") or ""):
        return {"action": "wait", "ms": 1500}
    return {"action": "fail", "reason": "Wikipedia result not present in the page snapshot"}


def plan_b2(snap, ps):
    # If DDG serves its bot-block page, the RUNNER must intercept the
    # wall before this planner is ever called (ps["brain_called"]
    # records whether that held). If DDG serves results, work them:
    # its result hrefs carry the target in the uddg parameter.
    ps["brain_called"] = True
    if "wikipedia.org" in (snap.get("url") or "") and "Oslo" in (snap.get("text") or ""):
        return _wiki_answer(snap)
    e = find_el(snap, lambda e: "en.wikipedia.org" in (e.get("href") or "") or "en.wikipedia.org" in re.sub(r"%2F", "/", (e.get("href") or ""), flags=re.I))
    if e:
        return {"action": "click", "i": e["i"]}
    return {"action": "wait", "ms": 1500}


def plan_c(snap, ps):
    text = snap.get("text") or ""
    if "/submit" in (snap.get("url") or "") and ps.get("submitted"):
        lines = [ln.strip() for ln in text.split("\n") if re.search(r"username|dropdown|comments", ln, re.I) and len(ln.strip()) > 3]
        return {"action": "done", "answer": "Results page shows: " + " | ".join(lines)[:400]}
    if "_valueusername" in text or "form-results" in (snap.get("url") or "") or "Inputted Values" in text:
        lines = [ln.strip() for ln in text.split("\n") if "_value" in ln]
        return {"action": "done", "answer": "Results page shows: " + " | ".join(lines)[:400]}
    if not ps.get("user"):
        e = find_el(snap, lambda e: (e.get("name") or "") == "username")
        if e:
            ps["user"] = True
            return {"action": "type", "i": e["i"], "text": "julie_test", "submit": False}
    if not ps.get("comments"):
        e = find_el(snap, lambda e: (e.get("name") or "") == "comments" and e.get("tag") == "textarea")
        if e:
            ps["comments"] = True
            return {"action": "type", "i": e["i"], "text": "Testing Julie browse", "submit": False}
    if not ps.get("dd"):
        e = find_el(snap, lambda e: e.get("tag") == "select" and (e.get("name") or "") == "dropdown")
        if e:
            ps["dd"] = True
            return {"action": "select", "i": e["i"], "value": "Drop Down Item 5"}
    if not ps.get("submitted"):
        e = find_el(snap, lambda e: (e.get("type") or "") == "submit")
        if e:
            ps["submitted"] = True
            return {"action": "click", "i": e["i"]}
    return {"action": "wait", "ms": 1200}


def plan_d(snap, ps):
    url = snap.get("url") or ""
    if "example.com" in url:
        lines = [ln.strip() for ln in (snap.get("text") or "").split("\n") if len(ln.strip()) > 8]
        return {"action": "done", "answer": f"Redirect chain completed (landed first on {ps.get('landed') or 'httpbin'}). Example Domain headline: {(lines[0] if lines else snap.get('title') or '')[:120]}"}
    if "httpbin.org" in url:
        ps["landed"] = url
        return {"action": "goto", "url": "https://example.com"}
    return {"action": "wait", "ms": 1200}


# ---------------- stub Worker ----------------

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _job(self):
        q = parse_qs(urlparse(self.path).query)
        return (q.get("job") or [""])[0]

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        jid = self._job()
        with LOCK:
            J = JOBS.get(jid)
            if p == "/api/setup/runner/job":
                if not J:
                    return self._send({"error": "missing"}, 404)
                # B2: simulate the user pressing Stop ~20s into the wall pause
                if J["rec"]["state"] == "paused" and J["paused_since"] and time.time() - J["paused_since"] > 20:
                    J["rec"]["state"] = "stopped"
                return self._send({"ok": True, "job": {**J["rec"], "tcInputs": []}})
            if p == "/api/setup/runner/profile":
                return self._send({"ok": True, "profile": None})
        return self._send({"error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        jid = self._job()
        ln = int(self.headers.get("content-length") or 0)
        try:
            body = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            body = {}
        with LOCK:
            J = JOBS.get(jid)
            if not J:
                return self._send({"error": "missing"}, 404)
            if p == "/api/setup/runner/progress":
                J["progress"].append(body)
                if body.get("state"):
                    J["rec"]["state"] = body["state"]
                    if body["state"] == "paused" and not J["paused_since"]:
                        J["paused_since"] = time.time()
                if body.get("step"):
                    J["rec"]["step"] = body["step"]
                if body.get("note"):
                    J["rec"]["note"] = body["note"]
                if body.get("url"):
                    J["rec"]["url"] = body["url"]
                return self._send({"ok": True})
            if p == "/api/setup/runner/tcframe":
                J["frames"] += 1
                return self._send({"ok": True})
            if p == "/api/setup/runner/result":
                J["result"] = body
                J["rec"]["state"] = body.get("status") or J["rec"]["state"]
                return self._send({"ok": True})
            if p == "/api/setup/runner/profile":
                return self._send({"ok": True, "stored": True})
            if p == "/api/setup/runner/brainstep":
                J["brain_calls"] += 1
                J["last_snap"] = body.get("snapshot") or {}
                try:
                    action = J["planner"](body.get("snapshot") or {}, J["pstate"])
                except Exception as e:
                    action = {"action": "fail", "reason": f"planner error: {e}"}
                return self._send({"ok": True, "action": action})
        return self._send({"error": "not found"}, 404)


# ---------------- rungs ----------------

def plan_b1w(snap, ps):
    # Search-and-click-through on Wikipedia's own search (Bing serves
    # an empty results shell to this egress — see the B1 evidence).
    if "/wiki/Norway" in (snap.get("url") or "") and "Oslo" in (snap.get("text") or ""):
        return _wiki_answer(snap)
    e = find_el(snap, lambda e: (e.get("href") or "").rstrip("/").endswith("/wiki/Norway"))
    if e:
        return {"action": "click", "i": e["i"]}
    return {"action": "wait", "ms": 1500}


RUNGS = [
    ("B1W", "ladderB1W", "Search Wikipedia for 'capital of Norway', open the Norway article, and tell me the capital",
     "https://en.wikipedia.org/w/index.php?search=capital+of+Norway", plan_b1w, 300),
    ("A", "ladderA", "Open cookiebot.com, dismiss the cookie banner, and tell me the page headline",
     "https://cookiebot.com", plan_a, 300),
    ("B1", "ladderB1", "Search Bing for 'capital of Norway', open the Wikipedia result, and tell me the capital",
     "https://www.bing.com/search?q=capital+of+Norway", plan_b1, 300),
    ("B2", "ladderB2", "Search DuckDuckGo for 'capital of Norway' and open the Wikipedia result",
     "https://html.duckduckgo.com/html/?q=capital+of+Norway", plan_b2, 300),
    ("C", "ladderC", "Fill the test form: username julie_test, a comment, choose 'Drop Down Item 5' in the dropdown, and submit; then tell me what the results page shows",
     "https://testpages.eviltester.com/styled/basic-html-form-test.html", plan_c, 300),
    ("D", "ladderD", "Open the redirect link, follow it to the end, then go to example.com and tell me the headline",
     "https://httpbin.org/redirect/3", plan_d, 300),
]


def run_rung(rung):
    name, jobid, task, start_url, planner, timeout = rung
    new_job(jobid, task, start_url, planner)
    env = dict(os.environ)
    env.update({"WORKER_URL": f"http://127.0.0.1:{PORT}", "RUNNER_KEY": "rk-test", "JOB": jobid,
                "PROVIDER": "browse", "BROWSER_MODE": "profile", "no_proxy": "127.0.0.1,localhost",
                "PYTHONPATH": ROOT + ":" + HERE})
    t0 = time.time()
    try:
        pr = subprocess.run([PY, os.path.join(HERE, "run_one.py")], env=env,
                            capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        out, code = pr.stdout + "\n" + pr.stderr, pr.returncode
    except subprocess.TimeoutExpired as e:
        out, code = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
    J = JOBS[jobid]
    try:
        os.makedirs(os.path.join(HERE, "after"), exist_ok=True)
        with open(os.path.join(HERE, "after", f"snap_{name}.json"), "w") as f:
            json.dump(J["last_snap"] or {}, f, indent=1, default=str)
    except Exception:
        pass
    res = {"rung": name, "secs": round(time.time() - t0, 1), "exit": code,
           "result": J["result"], "frames": J["frames"], "brain_calls": J["brain_calls"],
           "progress_states": [p.get("state") for p in J["progress"]],
           "pstate": {k: v for k, v in J["pstate"].items() if k != "brain_called"},
           "brain_called_on_wall": bool(J["pstate"].get("brain_called")),
           "last_url": (J["last_snap"] or {}).get("url", ""),
           "log_tail": out.strip().split("\n")[-6:]}
    print(f"--- rung {name}: {json.dumps(res, default=str)[:900]}", flush=True)
    return res


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    results = []
    for rung in RUNGS:
        if only and rung[0] not in only:
            continue
        results.append(run_rung(rung))
    os.makedirs(os.path.join(HERE, "after"), exist_ok=True)
    with open(os.path.join(HERE, "after", "results.json"), "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("WROTE after/results.json")


if __name__ == "__main__":
    main()
