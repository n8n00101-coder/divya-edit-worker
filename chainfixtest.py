#!/usr/bin/env python3
"""v104 chain-robustness runner harness (in the acctcreatetest style:
env + playwright stubbed, httpx monkeypatched, no network).

Proves the runner halves of the fixes from the 2026-11-16 live run:
  Fix 5 — _verify_wall recognises verification-WALL pages (incl.
          Cohere's title-only "Confirm Email" page) and does NOT fire
          on ordinary pages with a Confirm button.
  Fix 3 — job_alive() reads the job record's state; push_profile()
          makes NO post when the job is dead (zombie guard), and
          posts when it is live.
  Fix 4 — report_link_rejected() posts to setup/runner/linkbad.
  Fix 1 — check_stop() raises PauseExpired past a non-email pause's
          budget, never raises for an email pause, and still returns
          True on stop / False on resume.
  Fix 6 — submit_provider_result() emits the terminal progress event
          BEFORE report_result (the dying-gasp ordering).
"""
import os, sys, types

os.environ.setdefault("WORKER_URL", "https://worker.invalid")
os.environ.setdefault("RUNNER_KEY", "test-runner-key")
os.environ.setdefault("JOB", "chainjob0001")
os.environ.setdefault("PROVIDER", "groq")
os.environ.setdefault("BROWSER_MODE", "ephemeral")

sys.modules["playwright"] = types.ModuleType("playwright")
sys.modules["playwright.sync_api"] = types.ModuleType("playwright.sync_api")
sys.modules["playwright.sync_api"].sync_playwright = lambda: None

import setup  # noqa: E402

FAILS = []


def check(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


# ---------------------------------------------------------------- Fix 5
class FakePage:
    def __init__(self, title="", body="", url="https://example.com/signup"):
        self._title, self._body, self.url = title, body, url

    def inner_text(self, sel, timeout=None):
        return self._body

    def title(self):
        return self._title


check(setup._verify_wall(FakePage(title="Confirm Email | Cohere", body="")) is True,
      "F5-1 Cohere's title-only 'Confirm Email' page is a verification wall")
check(setup._verify_wall(FakePage(body="Please check your inbox to continue")) is True,
      "F5-2 'check your inbox' body is a verification wall")
check(setup._verify_wall(FakePage(body="We sent you a confirmation email with a link")) is True,
      "F5-3 'sent you a confirmation email' body is a verification wall")
check(setup._verify_wall(FakePage(title="Dashboard", body="Welcome back — create a new API key")) is False,
      "F5-4 an ordinary dashboard is NOT a wall")
check(setup._verify_wall(FakePage(title="Checkout", body="Please confirm your order before paying")) is False,
      "F5-5 a bare 'confirm' (order) is NOT a wall — no false positive")

# ---------------------------------------------------------------- Fix 3
class FakeResp:
    def __init__(self, state):
        self.status_code = 200
        self._state = state

    def json(self):
        return {"job": {"state": self._state}}


posts = []


class FakePostResp:
    status_code = 200


def fake_post(url, **kw):
    posts.append((url, kw))
    return FakePostResp()


setup.httpx.post = fake_post
setup.PROFILE_MODE = True
setup.PROFILE_STATE = {"cookies": [], "origins": []}

setup.httpx.get = lambda url, **kw: FakeResp("failed")
check(setup.job_alive() is False, "F3-1 a failed job record reads as NOT alive")
posts.clear()
setup.push_profile()
check(len(posts) == 0, "F3-2 push_profile makes NO post for a dead job (zombie guard)")

setup.httpx.get = lambda url, **kw: FakeResp("running")
check(setup.job_alive() is True, "F3-3 a running job record reads as alive")
posts.clear()
setup.push_profile()
check(len(posts) == 1 and "runner/profile" in posts[0][0], "F3-4 push_profile posts for a live job")

# ---------------------------------------------------------------- Fix 4
posts.clear()
setup.report_link_rejected("link")
check(len(posts) == 1 and posts[0][0].endswith("/api/setup/runner/linkbad")
      and posts[0][1].get("params", {}).get("job") == "chainjob0001"
      and posts[0][1].get("json", {}).get("kind") == "link",
      "F4-1 report_link_rejected posts {kind:link} to setup/runner/linkbad for this job")

# ---------------------------------------------------------------- Fix 1
import time as _time


class FakeTime:
    @staticmethod
    def time():
        return _time.time()

    @staticmethod
    def sleep(s):
        pass


setup.time = FakeTime
setup.httpx.post = lambda url, **kw: FakePostResp()  # heartbeat sink

setup.LAST_PROGRESS = {"reason": "signin", "step": "google-signin"}
setup.get_job = lambda: {"state": "paused"}
_saved_budgets = dict(setup.PAUSE_SKIP_S)
setup.PAUSE_SKIP_S = {"signin": -1}  # budget already expired
try:
    setup.check_stop()
    check(False, "F1-1 check_stop raises PauseExpired past the signin budget")
except setup.PauseExpired as pe:
    check(pe.kind == "signin", "F1-1 check_stop raises PauseExpired past the signin budget")
setup.PAUSE_SKIP_S = _saved_budgets

setup.LAST_PROGRESS = {"reason": "email", "step": "verify-email"}
_seq = iter([{"state": "paused"}, {"state": "paused"}, {"state": "running"}])
setup.get_job = lambda: next(_seq)
check(setup.check_stop() is False, "F1-2 an EMAIL pause never raises — resume returns False")

setup.get_job = lambda: {"state": "stopped"}
check(setup.check_stop() is True, "F1-3 a stopped job still returns True")

# ---------------------------------------------------------------- Fix 6
order = []
setup.progress = lambda *a, **kw: order.append("progress:" + str(a[0]))
setup.report_result = lambda *a, **kw: order.append("report")
res = setup.submit_provider_result("groq", "Groq", {"status": "failed", "error": "boom reason", "key": None})
check(order == ["progress:failed", "report"], "F6-1 terminal progress is posted BEFORE report_result")
check(res["status"] == "failed", "F6-2 the result passes through unchanged")

print()
if FAILS:
    print(f"{len(FAILS)} FAILURES")
    sys.exit(1)
print("ALL PASS")
