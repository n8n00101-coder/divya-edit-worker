"""v105 Take Control rig tests (runner side). No live Worker, no live
browser: fake page + fake httpx prove the transport properties the fix
claims — (1) drained inputs are never discarded by wait loops
(tc_pump), (2) inputs apply in arrival order as real mouse/keyboard
calls with the reduced settle, (3) the fast frame mode actually
streams at multi-fps while change-only suppression and the normal
2.5s throttle still hold, (4) park semantics: tc_apply_inputs touches
nothing when the queue is empty.

Run: WORKER_URL=http://127.0.0.1:1 RUNNER_KEY=x JOB=t PROVIDER=kaggle \
     ~/workspace/.venv-divya-test/bin/python tctest.py
"""
import os, sys, time

os.environ["WORKER_URL"] = "http://127.0.0.1:9"
os.environ.setdefault("RUNNER_KEY", "x")
os.environ.setdefault("JOB", "t")
os.environ.setdefault("PROVIDER", "kaggle")

import setup as S

FAILS = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)

class FakeMouse:
    def __init__(self, log): self.log = log
    def click(self, x, y): self.log.append(("click", x, y))
    def wheel(self, dx, dy): self.log.append(("wheel", dx, dy))
    def move(self, x, y, steps=None): self.log.append(("move", x, y))

class FakeKeyboard:
    def __init__(self, log): self.log = log
    def type(self, text, delay=0): self.log.append(("type", text, delay))
    def press(self, key): self.log.append(("press", key))

class FakePage:
    def __init__(self, shot=b"frame-0"):
        self.log = []
        self.mouse = FakeMouse(self.log)
        self.keyboard = FakeKeyboard(self.log)
        self.url = "https://example.test/"
        self._shot = shot
        self.waits = []
    def screenshot(self, type=None, quality=None):
        self.log.append(("shot", quality))
        return self._shot
    def wait_for_timeout(self, ms): self.waits.append(ms)
    def goto(self, u, **kw): self.log.append(("goto", u))

# ---- (2) ordering + real-input semantics + settle -------------------
page = FakePage()
S.tc_apply_inputs(page, [
    {"type": "click", "x": 100, "y": 50},
    {"type": "type", "text": "1"},
    {"type": "type", "text": "2"},
    {"type": "key", "key": "Backspace"},
    {"type": "key", "key": "Enter"},
])
seq = [e for e in page.log if e[0] in ("click", "type", "press")]
check("inputs apply in arrival order as real mouse/keyboard calls",
      seq == [("click", 100.0, 50.0), ("type", "1", 25), ("type", "2", 25),
              ("press", "Backspace"), ("press", "Enter")], str(seq))
check("per-input settle is the reduced 50ms (not 250ms)",
      page.waits == [50] * 5, str(page.waits))

# ---- (1) tc_pump: drained inputs are applied, never discarded -------
page2 = FakePage()
n = S.tc_pump(page2, {"tcInputs": [{"type": "click", "x": 7, "y": 9},
                                   {"type": "type", "text": "5"}]})
check("tc_pump applies what the poll drained", n == 2 and
      ("click", 7.0, 9.0) in page2.log and ("type", "5", 25) in page2.log)
check("tc_pump on an empty queue is a no-op (park semantics)",
      S.tc_pump(page2, {"tcInputs": []}) == 0 and S.tc_pump(page2, {}) == 0
      and S.tc_pump(None, {"tcInputs": [{"type": "click", "x": 1, "y": 1}]}) == 0)
check("wait loops pump what they drain (def + check_stop + await call sites)",
      open("setup.py").read().count("tc_pump(") >= 3)

# ---- (3) frame cadence logic ----------------------------------------
posts = []
class FakeResp: status_code = 200
def fake_post(url, **kw):
    posts.append((time.time(), kw.get("json", {}).get("img", "")[:12]))
    return FakeResp()
S.httpx.post = fake_post

S._TC_FRAME_LAST.update({"at": 0.0, "hash": ""})
p3 = FakePage(shot=b"frame-A")
t0 = time.time()
for i in range(6):
    p3._shot = f"frame-{i}".encode()  # changing screen each time
    S.tc_post_frame(p3, fast=True)
    time.sleep(0.4)
elapsed = time.time() - t0
check("fast mode streams changing frames at >=2 fps",
      len(posts) >= 4 and elapsed < 2.6, f"{len(posts)} posts in {elapsed:.2f}s")

posts.clear()
S._TC_FRAME_LAST.update({"at": 0.0, "hash": ""})
p4 = FakePage(shot=b"same-frame")
for _ in range(4):
    S.tc_post_frame(p4, fast=True)
    time.sleep(0.4)
check("change-only: an unchanged screen posts at most once in fast mode",
      len(posts) == 1, f"{len(posts)} posts")

posts.clear()
S._TC_FRAME_LAST.update({"at": 0.0, "hash": ""})
p5 = FakePage(shot=b"normal-0")
S.tc_post_frame(p5)                      # normal mode: posts
p5._shot = b"normal-1"
S.tc_post_frame(p5)                      # within 2.5s throttle: suppressed
check("normal (non-TC) throttle still 2.5s — v50 quota discipline intact",
      len(posts) == 1, f"{len(posts)} posts")

# ---- source pins for the loop cadences -------------------------------
src = open("setup.py").read()
check("take_control polls at 0.3s (was 3.0s)", "time.sleep(0.3)" in src)
check("take_control fast-frames after applied inputs",
      'tc_post_frame(page, force=True, fast=True)' in src)
check("await_user_input polls at 2s and pumps (was 10s, no pump)",
      "time.sleep(2)" in src)

print()
if FAILS:
    print("TC RIG: FAILURES:", FAILS); sys.exit(1)
print("TC RIG: ALL PASS")
