"""videogen tests: the Kaggle Wan 2.2 render route (no real accounts,
no network) + the Worker/runner wiring (static).

1. Kernel script: prompt embedded JSON-safe (quotes/unicode), render
   contract strings present (videogen_out.mp4 + render_info.json),
   model id pinned to Wan-AI/Wan2.2-TI2V-5B-Diffusers.
2. Happy path: push body shape (slug, script kernel, GPU on, internet
   on, private), status poll running->complete, output zip parsed to
   mp4 bytes + render_info dict.
3. Push rejected with a quota message -> reason "limit".
   Push 401 -> reason "error" (credentials). Kernel error with a
   quota failureMessage -> "limit". Stuck running -> "timeout".
4. Output zip without videogen_out.mp4 -> "error"; without
   render_info.json -> "error" (a run is only trusted with its info
   record, same discipline as voicecompute's batch.qc rule).
5. run_videogen: empty prompt refused; no provider -> honest error;
   VideogenError surfaces as {ok: False, reason}.
6. Wiring (static): runner.py has the videogen dispatch + job fn and
   reads j["KAGGLE"]; the Worker has startVideogen + the videogen
   route token-gated at TOK.COST.video_create.

Run: python3 videogentest.py
"""

import io
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import videogen as vg

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


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeResp:
    def __init__(self, status_code=200, json_body=None, content=b""):
        self.status_code = status_code
        self._json = json_body
        self.content = content

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeKaggleHTTP:
    """httpx-shaped stub: request(method, url, **kw)."""

    def __init__(self, statuses=("complete",), push_status=200,
                 push_body=None, output=None, fail_msg=""):
        self.statuses = list(statuses)
        self.push_status = push_status
        self.push_body = push_body if push_body is not None else {"ref": "u/julie-videogen"}
        self.output = output if output is not None else make_zip({
            "videogen_out.mp4": b"MP4BYTES",
            "render_info.json": json.dumps(
                {"model": vg.MODEL_ID, "render_s": 600.0}).encode(),
        })
        self.fail_msg = fail_msg
        self.pushes = []

    def request(self, method, url, **kw):
        if url.endswith("/kernels/push"):
            self.pushes.append(kw.get("json") or {})
            return FakeResp(self.push_status, json_body=self.push_body)
        if url.endswith("/kernels/status"):
            if self.statuses:
                self._last = self.statuses.pop(0)
            st = getattr(self, "_last", "complete")
            return FakeResp(200, json_body={"status": st,
                                            "failureMessage": self.fail_msg})
        if url.endswith("/kernels/output"):
            return FakeResp(200, content=self.output)
        return FakeResp(404)


def client(http):
    return vg.KaggleVideogenClient("someuser", "somekey", http=http)


# 1. kernel script ---------------------------------------------------
src = vg.build_kernel_script({**vg.DEFAULT_CFG,
                              "prompt": 'a "quoted" cat — ünïcode 🐱'})
check("Wan-AI/Wan2.2-TI2V-5B-Diffusers" in src, "kernel pins the TI2V-5B diffusers model")
check("videogen_out.mp4" in src and "render_info.json" in src,
      "kernel writes the output contract files")
import ast as _ast
_m = src.split("CFG = json.loads(", 1)[1]
_literal, _ = _m, None
# the embedded argument is a python repr of the JSON text — eval it back
_end = _literal.index(")\n")
_cfg_back = json.loads(_ast.literal_eval(_literal[:_end]))
check(_cfg_back["prompt"] == 'a "quoted" cat — ünïcode 🐱',
      "prompt round-trips through the kernel source (JSON-safe embedding)")
try:
    compile(src, "kernel", "exec")
    check(True, "kernel source compiles")
except SyntaxError:
    check(False, "kernel source compiles")

# 2. happy path --------------------------------------------------------
http = FakeKaggleHTTP(statuses=("running", "complete"))
clk = Clock()
mp4, info = client(http).run_render(
    {**vg.DEFAULT_CFG, "prompt": "a cat"}, timeout_s=600, poll_s=10,
    sleep=clk.sleep, now=clk.now)
check(mp4 == b"MP4BYTES", "happy path returns the mp4 bytes")
check(info and info.get("render_s") == 600.0, "happy path returns render_info")
body = http.pushes[0]
check(body.get("kernelType") == "script" and body.get("enableGpu") is True
      and body.get("enableInternet") is True and body.get("isPrivate") is True,
      "push body: script kernel, GPU on, internet on, private")
check(body.get("slug") == "someuser/julie-videogen", "push body slug is user/julie-videogen")
check("somekey" not in json.dumps(body), "push body never carries the API key")

# 3. failure mapping ---------------------------------------------------
http = FakeKaggleHTTP(push_status=403, push_body={"message": "Maximum batch GPU session count reached"})
try:
    client(http).push_kernel({**vg.DEFAULT_CFG, "prompt": "x"})
    check(False, "quota push raises")
except vg.VideogenError as e:
    check(e.reason == "limit", "quota push -> limit")

http = FakeKaggleHTTP(push_status=401, push_body={"message": "unauthorized"})
try:
    client(http).push_kernel({**vg.DEFAULT_CFG, "prompt": "x"})
    check(False, "401 push raises")
except vg.VideogenError as e:
    check(e.reason == "error", "401 push -> error (credentials)")

http = FakeKaggleHTTP(statuses=("error",), fail_msg="GPU quota exceeded for this week")
clk = Clock()
try:
    client(http).run_render({**vg.DEFAULT_CFG, "prompt": "x"},
                            timeout_s=600, poll_s=10, sleep=clk.sleep, now=clk.now)
    check(False, "kernel error raises")
except vg.VideogenError as e:
    check(e.reason == "limit", "kernel error with quota message -> limit")

http = FakeKaggleHTTP(statuses=("running",))
clk = Clock()
try:
    client(http).run_render({**vg.DEFAULT_CFG, "prompt": "x"},
                            timeout_s=100, poll_s=10, sleep=clk.sleep, now=clk.now)
    check(False, "stuck kernel raises")
except vg.VideogenError as e:
    check(e.reason == "timeout", "stuck kernel -> timeout")

# 4. output trust ------------------------------------------------------
http = FakeKaggleHTTP(output=make_zip({"render_info.json": b"{}"}))
try:
    client(http).run_render({**vg.DEFAULT_CFG, "prompt": "x"})
    check(False, "missing mp4 raises")
except vg.VideogenError as e:
    check(e.reason == "error", "output without mp4 -> error")

http = FakeKaggleHTTP(output=make_zip({"videogen_out.mp4": b"MP4"}))
try:
    client(http).run_render({**vg.DEFAULT_CFG, "prompt": "x"})
    check(False, "missing info raises")
except vg.VideogenError as e:
    check(e.reason == "error", "output without render_info.json -> error (untrusted)")

# 5. run_videogen entry --------------------------------------------------
r = vg.run_videogen("   ", kaggle=client(FakeKaggleHTTP()))
check(r["ok"] is False and r["reason"] == "error", "empty prompt refused")
r = vg.run_videogen("a cat", kaggle=None)
check(r["ok"] is False and "no Kaggle" in r["detail"], "no provider -> honest error")
clk = Clock()
r = vg.run_videogen("a cat", kaggle=client(FakeKaggleHTTP()),
                    sleep=clk.sleep, now=clk.now)
check(r["ok"] is True and r["mp4"] == b"MP4BYTES" and r["info"]["render_s"] == 600.0,
      "run_videogen happy path")

# 6. wiring (static) -----------------------------------------------------
runner_src = (HERE / "runner.py").read_text()
check('j.get("mode") == "videogen"' in runner_src, "runner dispatches mode=videogen")
check("async def videogen_job(" in runner_src, "runner has videogen_job")
check('j.get("KAGGLE")' in runner_src, "runner reads the KAGGLE creds hand-off")
worker_src = (HERE / "cfworker" / "divya.js").read_text()
check("async function startVideogen(" in worker_src, "Worker has startVideogen")
check('p === "videogen" && req.method === "POST"' in worker_src, "Worker has the videogen route")
check('mode: "videogen"' in worker_src, "Worker job record carries mode videogen")
route_at = worker_src.index('p === "videogen"')
check("TOK.COST.video_create" in worker_src[route_at:route_at + 2500],
      "videogen route is token-gated at TOK.COST.video_create")

print()
if FAILS:
    print(f"{len(FAILS)} FAILURES")
    sys.exit(1)
print("ALL PASS")
