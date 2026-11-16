"""v84 tests: voicecompute — Kaggle GPU + GitHub Actions voice batch
providers, hybrid split and failover (no real accounts, no network).

1. Kernel script: job lines embedded JSON-safe (quotes/unicode),
   --first-index passed, engine run NOT check=True (gate-failed lines
   still ship), out.zip built from the out/ contents.
2. Kaggle happy path: push body shape (slug, GPU on, internet on),
   status poll running->complete, output zip (out.zip inside the
   kernels/output zip) parsed to GLOBAL line indices + qc.
3. Kaggle quota on push (403) -> KaggleLimitError -> the SAME lines
   fail over to Actions; on_switch fires exactly once with the limit
   line; every line lands.
4. Kaggle kernel error with a quota failureMessage -> limit failover.
   Kaggle stuck running past the timeout -> timeout failover.
   Kaggle output without batch.qc.json -> no_qc failover (distrusted).
5. Hybrid split: Kaggle takes the head share, Actions the tail; the
   Actions workflow's file-relative mp3 numbers are remapped to
   global indices by order; merged result is complete.
6. Gate-failed line under an OK run (qc present, one mp3 missing):
   reported gate_failed, NOT failed over (the engine already
   re-rolled it; another provider would run the same gates).
7. Actions-only (no Kaggle connected) = today's default route.
   Actions run cancelled -> its lines fail over to Kaggle.
8. Worker/app wiring (static, v81test style): the Worker has the
   kaggle KEYPROV entry + keys/kaggle route + KEYLIST row + the /job
   runner-channel KAGGLE injection; the app has the PNAMES label and
   the Kaggle connect card.

Run: python3 kaggletest.py
"""

import base64
import io
import json
import sys
import zipfile
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import voicecompute as vc

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def batch_zip(indices, qc=True, prefix=""):
    entries = {f"{prefix}{i:03d}.mp3": f"MP3-{i}".encode() for i in indices}
    if qc:
        entries[f"{prefix}batch.qc.json"] = json.dumps(
            {"lines": [{"index": i, "out": f"{i:03d}.mp3"} for i in indices]}).encode()
    return make_zip(entries)


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


# ------------------------------------------------------------ fake Kaggle

class FakeKaggle:
    """mode: ok | quota_push | quota_run | stuck | no_qc"""

    def __init__(self, mode="ok", first_index=1, count=3):
        self.mode = mode
        self.first_index = first_index
        self.count = count
        self.pushes = []
        self.status_calls = 0

    def handler(self, request):
        url = str(request.url)
        if url.endswith("/kernels/push"):
            body = json.loads(request.content)
            self.pushes.append(body)
            if self.mode == "quota_push":
                return httpx.Response(403, json={"message": "Quota exceeded for GPU"})
            return httpx.Response(200, json={"ref": "u1/julie-voice-batch", "versionNumber": 1})
        if "/kernels/status" in url:
            self.status_calls += 1
            if self.mode == "stuck":
                return httpx.Response(200, json={"status": "running"})
            if self.mode == "quota_run":
                return httpx.Response(200, json={"status": "error",
                                                 "failureMessage": "GPU quota exceeded for this week"})
            if self.status_calls < 2:
                return httpx.Response(200, json={"status": "running"})
            return httpx.Response(200, json={"status": "complete"})
        if "/kernels/output" in url:
            idx = list(range(self.first_index, self.first_index + self.count))
            inner = batch_zip(idx, qc=self.mode != "no_qc", prefix="out/")
            outer = make_zip({"out.zip": inner, "julie-voice-batch.log": b"log"})
            return httpx.Response(200, content=outer)
        return httpx.Response(404, json={"message": "nope"})

    def client(self):
        return vc.KaggleClient("u1", "k" * 20,
                               http=httpx.Client(transport=httpx.MockTransport(self.handler)))


# ------------------------------------------------------------ fake GitHub

class FakeGitHub:
    """The voice-batch.yml route. mode: ok | cancelled | no_qc.
    Serves subset-relative mp3 numbers, like the real workflow."""

    def __init__(self, mode="ok"):
        self.mode = mode
        self.dispatched = False
        self.put_files = {}
        self.deleted = []
        self.last_run_id = 100

    def handler(self, request):
        url = str(request.url)
        path = request.url.path
        if request.method == "PUT" and "/contents/" in path:
            body = json.loads(request.content)
            name = path.rsplit("/", 1)[-1]
            self.put_files[name] = base64.b64decode(body["content"]).decode()
            return httpx.Response(201, json={"content": {"sha": "sha-" + name}})
        if request.method == "DELETE" and "/contents/" in path:
            self.deleted.append(path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={"content": None})
        if request.method == "POST" and path.endswith("/dispatches"):
            self.dispatched = True
            self.inputs = json.loads(request.content)["inputs"]
            return httpx.Response(204)
        if request.method == "GET" and path.endswith("/runs"):
            if not self.dispatched:
                return httpx.Response(200, json={"workflow_runs": [{"id": self.last_run_id, "status": "completed", "conclusion": "success"}]})
            conc = "cancelled" if self.mode == "cancelled" else "success"
            return httpx.Response(200, json={"workflow_runs": [
                {"id": self.last_run_id + 1, "status": "completed", "conclusion": conc},
                {"id": self.last_run_id, "status": "completed", "conclusion": "success"}]})
        if request.method == "GET" and "/artifacts" in path and path.endswith("/artifacts"):
            return httpx.Response(200, json={"artifacts": [{"id": 55, "name": "julie-voice-batch-all"}]})
        if request.method == "GET" and path.endswith("/zip"):
            name = next(iter(self.put_files))
            n = len([l for l in self.put_files[name].splitlines() if l.strip()])
            blob = batch_zip(list(range(1, n + 1)), qc=self.mode != "no_qc")
            return httpx.Response(200, content=blob)
        return httpx.Response(404, json={"message": "nope " + path})

    def client(self, tag="testjob"):
        return vc.ActionsClient("ghp_test", http=httpx.Client(
            transport=httpx.MockTransport(self.handler)), job_tag=tag)


LINES = ["First line.", "Second \"quoted\" line.", "Third — తెలుగు mix.", "Fourth line.", "Fifth line."]


# ------------------------------------------------------------ 1. kernel script

def test_kernel_script():
    src = vc.build_kernel_script(LINES, "te", 41)
    check("First line." in src and "తెలుగు" in src, "kernel embeds the job lines (unicode intact)")
    import ast as _ast
    lit = src.split("json.loads(", 1)[1].split(")", 1)[0]
    check(json.loads(_ast.literal_eval(lit)) == LINES,
          "kernel embeds quoted lines safely (JSON round-trips exactly)")
    check('"--first-index", str(FIRST_INDEX)' in src and "FIRST_INDEX = 41" in src,
          "kernel passes the global first index to the engine")
    check("zip -r" in src and "out.zip" in src, "kernel builds out.zip")
    check('subprocess.run([sys.executable, "engine.py", "--batch"' in src
          and 'check=True' not in src.split('"engine.py"')[1].split(")")[0],
          "engine batch run is not check=True (gate-failed lines still ship)")


# ------------------------------------------------------------ 2. kaggle happy path

def test_kaggle_happy():
    fk = FakeKaggle("ok", first_index=1, count=3)
    done, qc = fk.client().run_batch([(1, "a"), (2, "b"), (3, "c")], "en",
                                     timeout_s=600, poll_s=5, sleep=lambda s: None)
    check(sorted(done) == [1, 2, 3], "kaggle happy: all lines returned")
    check(done[2] == b"MP3-2", "kaggle happy: mp3 bytes mapped to the global index")
    check(qc is not None and len(qc.get("lines", [])) == 3, "kaggle happy: qc parsed")
    body = fk.pushes[0]
    check(body["slug"] == "u1/julie-voice-batch" and body["enableGpu"] is True
          and body["enableInternet"] is True and body["isPrivate"] is True,
          "kaggle push body: slug + GPU + internet + private")
    check("a" in body["text"] and "--first-index" in body["text"],
          "kaggle push body carries the lines + first-index contract")


# ------------------------------------------------------------ 3-4. kaggle failures -> failover

def _failover_case(mode, reason_word, switch_word):
    fk = FakeKaggle(mode, first_index=1, count=3)
    gh = FakeGitHub("ok")
    clock = Clock()
    switches, statuses = [], []
    out = vc.run_voice_batch(LINES[:3], "en", kaggle=fk.client(), actions=gh.client(),
                             on_status=statuses.append, on_switch=switches.append,
                             kaggle_share=1.0,  # everything starts on Kaggle
                             kaggle_timeout=60, actions_timeout=600,
                             poll_s=20, sleep=clock.sleep, now=clock.now)
    check(sorted(out["done"]) == [1, 2, 3], f"{mode}: all lines done after failover")
    check(len(switches) == 1 and switch_word in switches[0],
          f"{mode}: exactly one switch line ({switch_word})")
    check(out["switches"] and out["switches"][0]["from"] == "kaggle"
          and out["switches"][0]["reason"] == reason_word,
          f"{mode}: switch recorded with reason {reason_word}")
    check("kaggle" in out["errors"], f"{mode}: kaggle error recorded honestly")


def test_failovers():
    _failover_case("quota_push", "limit", "limit")
    _failover_case("quota_run", "limit", "limit")
    _failover_case("stuck", "timeout", "continue")
    _failover_case("no_qc", "no_qc", "continue")


# ------------------------------------------------------------ 5. hybrid split

def test_hybrid():
    kr, ar = vc.split_ranges(209, 0.6)
    check(len(kr) == 125 and kr[0] == 1 and ar[0] == 126 and ar[-1] == 209,
          "split 209 @0.6: kaggle 1-125, actions 126-209 (contiguous)")
    check(list(vc.split_ranges(1)[0]) == [1] and list(vc.split_ranges(0)[0]) == [],
          "split edge cases: n=1 all-kaggle, n=0 empty")
    lines = [f"Line {i}" for i in range(1, 11)]
    fk = FakeKaggle("ok", first_index=1, count=6)   # kaggle share 0.6 of 10 = 6
    gh = FakeGitHub("ok")
    out = vc.run_voice_batch(lines, "en", kaggle=fk.client(), actions=gh.client(),
                             sleep=lambda s: None)
    check(sorted(out["done"]) == list(range(1, 11)), "hybrid: merged result complete 1-10")
    check(out["done"][8] == b"MP3-2", "hybrid: actions subset #2 remapped to global line 8")
    check(not out["switches"] and not out["gate_failed"], "hybrid: no switches, no gate failures")
    name = next(iter(gh.put_files))
    check(gh.put_files[name].splitlines() == lines[6:], "hybrid: actions got exactly its tail lines")
    check(gh.deleted == [name], "hybrid: actions lines file cleaned up after the run")


# ------------------------------------------------------------ 6. gate failure is not failover

def test_gate_failed_line():
    fk = FakeKaggle("ok", first_index=1, count=2)  # line 3 never passes the gates
    out = vc.run_voice_batch(LINES[:3], "en", kaggle=fk.client(), sleep=lambda s: None)
    check(sorted(out["done"]) == [1, 2], "gate-fail: passing lines delivered")
    check(out["gate_failed"].get(3) == "gates", "gate-fail: line 3 reported as gate failure")
    check(not out["switches"] and not out["errors"], "gate-fail: no provider switch for a gate failure")


# ------------------------------------------------------------ 7. actions-only + actions failure

def test_actions_paths():
    gh = FakeGitHub("ok")
    out = vc.run_voice_batch(LINES[:3], "en", actions=gh.client(), sleep=lambda s: None)
    check(sorted(out["done"]) == [1, 2, 3] and not out["switches"],
          "actions-only: today's default route works, no switch")
    gh2 = FakeGitHub("cancelled")
    fk = FakeKaggle("ok", first_index=1, count=5)
    switches = []
    out = vc.run_voice_batch(LINES, "en", kaggle=fk.client(), actions=gh2.client(),
                             on_switch=switches.append, kaggle_share=0.0,
                             sleep=lambda s: None)
    check(sorted(out["done"]) == [1, 2, 3, 4, 5] and len(switches) == 1
          and out["switches"][0]["from"] == "actions",
          "actions cancelled: its lines fail over to Kaggle, one switch line")
    try:
        vc.run_voice_batch(LINES, "en")
        check(False, "no provider at all raises")
    except ValueError:
        check(True, "no provider at all raises")


# ------------------------------------------------------------ 8. worker/app wiring (static)

def test_wiring():
    w = (HERE / "cfworker" / "divya.js").read_text(encoding="utf-8")
    a = (HERE / "app" / "app.js").read_text(encoding="utf-8")
    h = (HERE / "app" / "index.html").read_text(encoding="utf-8")
    r = (HERE / "runner.py").read_text(encoding="utf-8")
    check('kaggle: { name: "Kaggle"' in w, "worker: KEYPROV has the kaggle entry")
    check('p === "keys/kaggle"' in w, "worker: keys/kaggle route exists")
    check('["kaggle", "Kaggle (GPU compute)"]' in w, "worker: setup keys list has the kaggle row")
    check("openKey(env, jrec.to, \"kaggle\")" in w and "KAGGLE: kaggleCreds" in w,
          "worker: /job hands the sealed kaggle creds to the runner channel only")
    check('startVoiceBatch' in w and 'p === "voicebatch"' in w,
          "worker: voicebatch job creation route exists")
    check('kaggle: "Kaggle (GPU)"' in a, "app: PNAMES labels kaggle")
    check('id="kaggleUser"' in h and 'id="kaggleKey"' in h and 'id="kaggleBtn"' in h,
          "app: kaggle connect card fields exist")
    check('j.get("mode") == "voicebatch"' in r and "voicecompute" in r,
          "runner: voicebatch mode wired to voicecompute")


def main():
    test_kernel_script()
    test_kaggle_happy()
    test_failovers()
    test_hybrid()
    test_gate_failed_line()
    test_actions_paths()
    test_wiring()
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURES")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
