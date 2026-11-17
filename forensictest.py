"""v112 tests: total-failure forensic fixes on the runner side.

1. wait_for_auth_form clicks a Log in / Sign up entry CTA when the
   provider's url is a landing page (SambaNova / NVIDIA / AI21 burned
   the whole 60s+30s wait on the root page and failed
   "form kanipinchaledu" without ever opening the form).
2. door_blocked_fail: a job the Worker marked doorBlocked (an earlier
   provider in the chain already burned a full sign-in pause) fails
   Google-door flows in seconds with the class reason — no second
   15-minute pause. Proven through flow_google end to end.
3. creation_identity: when the job record carries userName/userPhone
   (the Worker now resolves them from the account records), NO chat
   ask fires; when they are truly absent, the ask fallback still
   works and consumes the reply.
4. run_provider prints every flow result (status + reason) — today's
   23/23 failure was undiagnosable from Actions logs because flows
   returned their reasons as data and nothing printed them.
5. Static: the post-submit _submit_error fail is preceded by a
   _verify_signed_in rescue probe in flow_email_signup.

No live browser, no network. Run: python3 forensictest.py
"""

import contextlib
import io
import os
import re
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

os.environ.setdefault("WORKER_URL", "http://127.0.0.1:9")
os.environ.setdefault("RUNNER_KEY", "test-runner-key")
os.environ.setdefault("JOB", "forensictestjob")
os.environ.setdefault("PROVIDER", "chain")

_pw = types.ModuleType("playwright")
_pw_api = types.ModuleType("playwright.sync_api")
_pw_api.sync_playwright = lambda: None
_pw.sync_api = _pw_api
sys.modules.setdefault("playwright", _pw)
sys.modules.setdefault("playwright.sync_api", _pw_api)

import setup  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def _quiet():
    saved = {"progress": setup.progress, "get_job": setup.get_job}
    setup.progress = lambda *a, **k: None
    setup.get_job = lambda: {"state": "running"}
    return saved


def _restore(saved):
    setup.progress, setup.get_job = saved["progress"], saved["get_job"]


# ------------------------------------------------------------ fake page
class FakeLocator:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel
        self.first = self

    def nth(self, i):
        return self

    def count(self):
        return 1 if self.page.vis(self.sel) else 0

    def is_visible(self):
        return self.page.vis(self.sel)

    def click(self, timeout=None):
        self.page.clicked(self.sel)


class LandingPage:
    """A product root page: no auth form, only a Log in CTA. Clicking
    the CTA renders the email form (the SambaNova/NVIDIA shape)."""

    def __init__(self):
        self.url = "https://cloud.example.ai/"
        self.cta_clicked = False

    def vis(self, sel):
        if "Log in" in sel or "Sign in" in sel or "Sign up" in sel:
            return not self.cta_clicked
        if "email" in sel:
            return self.cta_clicked
        return False

    def clicked(self, sel):
        if "Log in" in sel or "Sign in" in sel or "Sign up" in sel:
            self.cta_clicked = True

    def goto(self, url, **kw):
        self.url = url

    def wait_for_timeout(self, ms):
        time.sleep(0.05)

    def inner_text(self, sel):
        return "Welcome"

    def content(self):
        return "<html>Welcome</html>"

    def title(self):
        return "Example AI"

    def locator(self, sel):
        return FakeLocator(self, sel)


# ------------------------------------------------------- 1. CTA in form wait
def test_form_wait_clicks_cta():
    saved = _quiet()
    real_cursor = setup._cursor_to
    setup._cursor_to = lambda *a, **k: None
    try:
        page = LandingPage()
        ctrls = setup.wait_for_auth_form(page, {"name": "Example"}, timeout_s=17)
    finally:
        setup._cursor_to = real_cursor
        _restore(saved)
    check(page.cta_clicked, "wait_for_auth_form clicked the Log in CTA on a landing page")
    check(bool(ctrls and ctrls.get("email")), "auth form found after the CTA click")


# ------------------------------------------------------- 2. door fast-fail
def test_door_blocked_flow_google():
    saved = _quiet()
    try:
        page = LandingPage()
        res = setup.flow_google(page, {"doorBlocked": True, "email": "u@example.com"}, setup.FLOWS["gemini"])
    finally:
        _restore(saved)
    check(res["status"] == "failed", "doorBlocked flow_google fails without pausing")
    check("Google sign-in door" in str(res.get("error") or ""), "door fail names the class reason")
    check((res.get("extra") or {}).get("no_retry") is True, "door fail is no_retry")
    check(setup.door_blocked_fail({"doorBlocked": True}, "X") is not None, "door_blocked_fail fires on a marked job")
    check(setup.door_blocked_fail({}, "X") is None, "door_blocked_fail silent on an unmarked job")


# ------------------------------------------------------- 3. creation identity
def test_creation_identity():
    saved = _quiet()
    asks = []
    real_aui = setup.await_user_input
    setup.await_user_input = lambda *a, **k: asks.append(a) or {"value": ""}
    try:
        ident = setup.creation_identity(None, {"email": "u@example.com", "userName": "Peru Test", "userPhone": "919999999999"})
        check(ident.get("name") == "Peru Test" and ident.get("phone") == "919999999999", "identity taken from the job record")
        check(not asks, "NO chat ask when the record carries name+phone")
        vals = iter([{"value": "Chat Name"}, {"value": "+91 99999 99999"}])
        setup.await_user_input = lambda *a, **k: next(vals)
        ident2 = setup.creation_identity(None, {"email": "u@example.com"})
        check(ident2.get("name") == "Chat Name" and ident2.get("phone") == "+919999999999", "chat ask remains the fallback and its reply is consumed")
    finally:
        setup.await_user_input = real_aui
        _restore(saved)


# ------------------------------------------------------- 4. result prints
def test_run_provider_prints():
    saved = _quiet()
    real = {"open_context": setup.open_context, "close_context": setup.close_context, "run_flow": setup.run_flow}
    setup.open_context = lambda browser: types.SimpleNamespace(new_page=lambda: LandingPage())
    setup.close_context = lambda ctx: None
    setup.run_flow = lambda page, job, cfg: setup._fail("boom reason for the log")
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            res = setup.run_provider(None, {"provider": "testprov"}, {"name": "TestProv", "url": "https://example.com/signup"}, "testprov")
    finally:
        setup.open_context, setup.close_context, setup.run_flow = real["open_context"], real["close_context"], real["run_flow"]
        _restore(saved)
    out = buf.getvalue()
    check(res["status"] == "failed", "run_provider returns the failure")
    check("flow result testprov attempt 1" in out and "boom reason for the log" in out, "flow result (status + reason) printed to the run log")


# ------------------------------------------------------- 5. rescue shape
def test_submit_rescue_shape():
    src = (HERE / "setup.py").read_text()
    a = src.find("def flow_email_signup")
    b = src.find("def flow_google", a)
    span = src[a:b]
    # The SHARED post-submit site (after all mode branches) is the last
    # _submit_error in the flow — it must probe for a landed session
    # before failing. (The earlier site is the pre-password email-step
    # check, where failing fast on a visible error is correct.)
    i = span.rfind("err = _submit_error(page)")
    seg = span[i:i + 800] if i >= 0 else ""
    check(i >= 0 and "_verify_signed_in" in seg and seg.find("_verify_signed_in") < seg.find("return _fail"), "post-submit error path probes for a landed session before failing")


if __name__ == "__main__":
    test_form_wait_clicks_cta()
    test_door_blocked_flow_google()
    test_creation_identity()
    test_run_provider_prints()
    test_submit_rescue_shape()
    print("\n==== FORENSIC RUNNER RIG ====")
    print("failures:", len(FAILS))
    sys.exit(1 if FAILS else 0)
