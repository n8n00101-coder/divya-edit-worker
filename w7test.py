"""W7 rig: tc_post_frame page-liveness (setup.py).

The frame poster used to screenshot whatever page object it was
handed; when that page died mid-run every later call threw
"Target page closed" and the log filled with `tc frame failed`
lines while the live view froze. W7: liveness check + re-acquire
from the same context (healing _CUR["page"]), one skip line per
dead page, silence after.

Run: /tmp/testvenv/bin/python w7test.py  (needs httpx + playwright
importable; no browser is launched — pages are fakes.)
"""
import io, os, sys
from contextlib import redirect_stdout

os.environ.setdefault("WORKER_URL", "https://worker.invalid")
os.environ.setdefault("RUNNER_KEY", "testkey")
os.environ.setdefault("JOB", "w7testjob")
os.environ.setdefault("PROVIDER", "browse")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setup as S

PASS = [0]
FAIL = [0]


def check(name, cond, detail=""):
    if cond:
        PASS[0] += 1
        print(f"  ok  {name}")
    else:
        FAIL[0] += 1
        print(f"FAIL  {name}  {detail}")


class FakePage:
    def __init__(self, ctx, url="https://x/", closed=False, shot=b"img",
                 die_at_shot=False):
        self.context = ctx
        self.url = url
        self._closed = closed
        self._shot = shot
        self._die = die_at_shot

    def is_closed(self):
        return self._closed

    def screenshot(self, type=None, quality=None):
        if self._die or self._closed:
            raise Exception("Target page, context or browser has been closed")
        return self._shot


class FakeCtx:
    def __init__(self, pages=(), dead=False):
        self._pages = list(pages)
        self._dead = dead

    @property
    def pages(self):
        if self._dead:
            raise Exception("context has been closed")
        return self._pages

    def new_page(self):
        if self._dead:
            raise Exception("context has been closed")
        p = FakePage(self, url="https://new/")
        self._pages.append(p)
        return p


POSTS = []


def fake_post(url, params=None, json=None, headers=None, timeout=None):
    POSTS.append({"url": url, "json": json})
    class R:  # minimal response stand-in
        status_code = 200
    return R()


def run_frame(page, **kw):
    """One tc_post_frame call with throttle/hash state reset and
    stdout captured. Returns (posts_made, stdout_text)."""
    POSTS.clear()
    S._TC_FRAME_LAST.update({"at": 0.0, "hash": ""})
    buf = io.StringIO()
    orig = S.httpx.post
    S.httpx.post = fake_post
    try:
        with redirect_stdout(buf):
            S.tc_post_frame(page, **kw)
    finally:
        S.httpx.post = orig
    return len(POSTS), buf.getvalue()


# 1 — live page: frame posts, nothing logged.
ctx = FakeCtx()
p = FakePage(ctx, url="https://live/", shot=b"one")
ctx._pages.append(p)
n, out = run_frame(p)
check("live page posts one frame, silent", n == 1 and out == "", f"n={n} out={out!r}")

# 2 — closed page, live sibling: frame comes from the SIBLING,
# _CUR healed, no failure line.
ctx = FakeCtx()
dead = FakePage(ctx, url="https://dead/", closed=True)
sib = FakePage(ctx, url="https://sibling/", shot=b"two")
ctx._pages.extend([dead, sib])
S._CUR["page"] = dead
n, out = run_frame(dead)
check("closed page re-acquires sibling",
      n == 1 and POSTS[0]["json"]["url"] == "https://sibling/", f"n={n} posts={POSTS}")
check("_CUR healed to the sibling", S._CUR["page"] is sib)
check("no 'tc frame failed' on re-acquire", "tc frame failed" not in out, out)

# 3 — closed page, no siblings: a fresh page is opened and used.
ctx = FakeCtx()
dead = FakePage(ctx, closed=True)
ctx._pages.append(dead)
n, out = run_frame(dead)
check("closed page with empty context opens a fresh page",
      n == 1 and POSTS[0]["json"]["url"] == "https://new/", f"n={n} posts={POSTS}")

# 4 — dead context: exactly one skip line across repeated calls,
# zero failure lines, zero posts.
ctx = FakeCtx(dead=True)
dead = FakePage(ctx, closed=True)
S._TC_DEAD_SEEN["page_id"] = None
n1, out1 = run_frame(dead)
n2, out2 = run_frame(dead)
check("dead context posts nothing", n1 == 0 and n2 == 0, f"n1={n1} n2={n2}")
check("dead context: one skip line total",
      out1.count("tc frame skipped") == 1 and out2 == "", f"out1={out1!r} out2={out2!r}")
check("dead context: no failure lines",
      "tc frame failed" not in out1 + out2, out1 + out2)

# 5 — page dies AT the screenshot (open at check): one re-acquire
# + retry lands the sibling's frame.
ctx = FakeCtx()
dying = FakePage(ctx, url="https://dying/", die_at_shot=True)
sib = FakePage(ctx, url="https://sib2/", shot=b"five")
ctx._pages.extend([dying, sib])
n, out = run_frame(dying)
check("screenshot-death retries on the sibling",
      n == 1 and POSTS[0]["json"]["url"] == "https://sib2/", f"n={n} posts={POSTS}")
check("screenshot-death: no failure line", "tc frame failed" not in out, out)

print(f"\nw7test: {PASS[0]} passed, {FAIL[0]} failed")
sys.exit(1 if FAIL[0] else 0)
