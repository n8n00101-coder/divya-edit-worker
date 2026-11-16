#!/usr/bin/env python3
"""v103 account-creation harness: the AWAITING_USER ask/resume plumbing
+ flow_kaggle against a scripted fake Kaggle, with a fake Worker
(httpx stubbed) and a fake clock.

Proves:
  - an OTP ask posts a structured awaiting block via progress();
  - the user's chat-delivered code resumes the runner and is entered;
  - a wrong OTP is re-asked ONCE (attempt 2), then the provider fails
    labelled (otp-rejected:phone) — no third ask, no exception;
  - an ask that never gets an answer times out labelled;
  - attempt > 2 is refused by the plumbing itself;
  - a missing identity field (name/phone) is ASKED in chat and the
    user's own value is used — never invented;
  - a captcha routes to the Take-Control gate (kind=captcha ask) and
    flow_kaggle contains no solver call; an incomplete gate fails
    labelled wall captcha:take-control-incomplete;
  - the happy path: register -> email code -> phone code -> API token
    download -> sealed pair -> self-test passes -> result done with
    extra.created.
"""
import os, sys, types, json, time

os.environ.setdefault("WORKER_URL", "https://worker.invalid")
os.environ.setdefault("RUNNER_KEY", "test-runner-key")
os.environ.setdefault("JOB", "acctjob0001")
os.environ.setdefault("PROVIDER", "kaggle")
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

# ---------------- fake clock ----------------
class Clock:
    def __init__(self): self.t = 1_700_000_000.0
    def time(self): self.t += 5; return self.t
    def sleep(self, s):
        try: self.t += min(float(s or 0), 30)
        except Exception: pass
CLOCK = Clock()
time.time, time.sleep = CLOCK.time, CLOCK.sleep

# ---------------- fake Worker (httpx stub) ----------------
PROGRESS, KEYS_POSTED, RESULTS = [], [], []
JOBREC = {}
SIM = {"otp_email": "482916", "otp_phone": "730215",
       "name": "Test User", "phone": "+919876543210", "answer": True}
_polls = {"n": 0, "delivered_for": None}

class Resp:
    def __init__(self, code=200, data=None):
        self.status_code = code; self._d = data or {}
    def json(self): return self._d

def fake_get(url, **kw):
    if "/api/setup/runner/job" in url:
        _polls["n"] += 1
        for p in reversed(PROGRESS):
            if p.get("awaiting"):
                JOBREC["awaiting"] = p["awaiting"]; break
        aw = JOBREC.get("awaiting")
        if aw and _polls["delivered_for"] != aw["id"]:
            JOBREC.pop("userInput", None)
        if SIM["answer"] and aw and "userInput" not in JOBREC and _polls["n"] >= 2:
            if aw["kind"] == "otp":
                val = SIM["otp_phone"] if "phone" in aw["prompt"].lower() else SIM["otp_email"]
            elif aw["kind"] == "field":
                val = SIM.get(aw.get("field") or "", "")
            else:
                val = ""
            if val:
                JOBREC["userInput"] = {"value": val, "askId": aw["id"], "at": 0}
                _polls["delivered_for"] = aw["id"]
        return Resp(200, {"job": dict(JOBREC)})
    if "kaggle.com/api/v1" in url:
        return Resp(200 if kw.get("auth") == ("testuser", "a" * 32) else 401)
    return Resp(404)

def fake_post(url, **kw):
    data = kw.get("json") or {}
    if "/runner/progress" in url: PROGRESS.append(data)
    elif "/runner/key" in url: KEYS_POSTED.append(data)
    elif "/runner/result" in url: RESULTS.append(data)
    return Resp(200, {"ok": True})

setup.httpx.get, setup.httpx.post = fake_get, fake_post

def reset(jobrec_extra=None):
    PROGRESS.clear(); KEYS_POSTED.clear(); RESULTS.clear()
    _polls["n"] = 0; _polls["delivered_for"] = None
    JOBREC.clear()
    JOBREC.update({"job": os.environ["JOB"], "provider": "kaggle",
                   "email": "user@example.com", "pass": "Chain-Pass-123",
                   "userName": "Test User", "userPhone": "+919876543210",
                   "state": "running"})
    if jobrec_extra: JOBREC.update(jobrec_extra)
    SIM["answer"] = True

# ---------------- ask plumbing ----------------
reset()
res = setup.await_user_input(None, "otp", "Kaggle phone code vachindhi — chat lo code cheppu.", attempt=1)
asks = [p for p in PROGRESS if p.get("awaiting")]
check(res.get("value") == SIM["otp_phone"], "ask: delivered code resumes the runner")
check(asks and asks[0]["awaiting"]["kind"] == "otp" and asks[0]["awaiting"]["provider"] == "kaggle"
      and asks[0]["awaiting"]["attempts"] == 1 and asks[0]["state"] == "paused",
      "ask: progress carries the structured awaiting block (kind/provider/attempts)")
check(any(p.get("state") == "running" and not p.get("awaiting") for p in PROGRESS),
      "ask: a running progress follows delivery")

reset(); SIM["answer"] = False
res = setup.await_user_input(None, "otp", "code?", ttl_s=60)
check(res.get("timeout") is True, "ask: unanswered ask times out (labelled by the caller)")

try:
    setup.await_user_input(None, "otp", "code?", attempt=3)
    check(False, "ask: attempt 3 refused")
except ValueError:
    check(True, "ask: attempt 3 refused (re-ask-once is structural)")

# ---------------- fake Kaggle page ----------------
class FakeEl:
    def __init__(self, page, key): self.page, self.key, self.value = page, key, ""
    def count(self): return 1
    def is_visible(self): return True
    def fill(self, v, timeout=None): self.value = v; self.page.values[self.key] = v
    def click(self, timeout=None): self.page.handle_click(self.key)
    def input_value(self): return self.value
    def locator(self, sel): return FakeLocator(self.page, [])
    def bounding_box(self): return None

class NullEl:
    def count(self): return 0
    def is_visible(self): return False
    def fill(self, v, timeout=None): raise RuntimeError("no element")
    def click(self, timeout=None): raise RuntimeError("no element")
    def input_value(self): return ""
    def locator(self, sel): return FakeLocator(None, [])
    def bounding_box(self): return None
NULL = NullEl()

class FakeLocator:
    def __init__(self, page, els): self.page, self.els = page, els
    def count(self): return len(self.els)
    @property
    def first(self): return self.els[0] if self.els else NULL
    def nth(self, i): return self.els[i] if i < len(self.els) else NULL

class DL:
    def __init__(self, page): self.page = page
    def __enter__(self): return self
    def __exit__(self, *a): return False
    @property
    def value(self):
        class D:
            def save_as(self, path):
                with open(path, "w") as f:
                    json.dump({"username": "testuser", "key": "a" * 32}, f)
        return D()

AV = {"[data-testid='avatar']": ["avatar"]}
class FakePage:
    def __init__(self, states, on_click):
        self.states, self.on_click = states, on_click
        self.state, self.url, self.values, self.els = None, "about:blank", {}, {}
        self.frames = []
    def load(self, state):
        self.state = state; self.url = self.states[state].get("url", self.url)
    def locator(self, sel):
        keys = (self.states[self.state]["els"] if self.state else {}).get(sel, [])
        return FakeLocator(self, [self._el(k) for k in keys])
    def _el(self, key):
        if key not in self.els: self.els[key] = FakeEl(self, key)
        return self.els[key]
    def inner_text(self, sel): return self.states[self.state]["text"]
    def content(self): return self.states[self.state]["text"]
    def title(self): return "Kaggle"
    def wait_for_timeout(self, ms): pass
    def handle_click(self, key): self.on_click(self, key)
    def expect_download(self, timeout=None): return DL(self)

REG_ELS = {"input[type='email']": ["email"], "input[type='password']": ["pw1", "pw2"],
           "input[name*='username' i]": ["uname"], "input[name*='name' i]": ["fname"],
           "button[type='submit']": ["submit"]}
OTP_ELS = {"input[name*='otp' i]": ["otp"], "button:has-text('Verify')": ["verify"]}
STATES = {
    "register": {"url": "https://www.kaggle.com/account/login", "text": "Create your account — register with your email", "els": dict(REG_ELS)},
    "emailcode": {"text": "We sent a verification code to your email — enter the code", "els": dict(OTP_ELS)},
    "aftersignup": {"text": "Welcome to Kaggle", "els": dict(AV)},
    "phone": {"text": "Verify your phone — add a phone number", "els": {**AV, "input[type='tel']": ["phone"], "button:has-text('Send code')": ["sendcode"]}},
    "phonecode": {"text": "Enter the code we sent to your phone", "els": {**AV, "input[name*='otp' i]": ["otp2"], "button:has-text('Verify')": ["verify2"]}},
    "settings": {"text": "Your account settings", "els": {**AV, "button:has-text('API')": ["apitab"]}},
    "api": {"text": "API — create a token for programmatic access", "els": {**AV, "button:has-text('Create New Token')": ["tokenbtn"]}},
    "captcha": {"text": "Create your account", "els": {**REG_ELS, "iframe[src*='recaptcha']": ["capframe"]}},
    "exists": {"text": "An account with this email already exists — sign in", "els": {"input[type='email']": ["email"], "input[type='password']": ["pw1"], "button[type='submit']": ["submit"]}},
}

def make_clicks(phone_code):
    def on_click(page, key):
        st = page.state
        if key == "submit" and st in ("register", "captcha"): page.load("emailcode")
        elif key == "verify" and st == "emailcode":
            if page.values.get("otp") == SIM["otp_email"]: page.load("aftersignup")
        elif key == "sendcode" and st == "phone": page.load("phonecode")
        elif key == "verify2" and st == "phonecode":
            if page.values.get("otp2") == phone_code:
                page.values["_phone_done"] = True; page.load("settings")
        elif key == "apitab": page.load("api")
    return on_click

def fake_goto_factory(page):
    def fake_goto(p, url, cfg=None):
        p.url = url
        if "kaggle.com/settings" in url:
            p.load("settings" if p.values.get("_phone_done") else "phone")
        else:
            p.load("register")
        return True
    return fake_goto

TC_CALLS = []
setup.take_control = lambda page, job, cfg, reason="captcha": TC_CALLS.append(reason) or True
setup.maybe_captcha = lambda page: True
setup.pause_for_email_verify = lambda page, job, cfg: False

# ---------------- happy path ----------------
reset()
page = FakePage(STATES, make_clicks(SIM["otp_phone"]))
setup.goto = fake_goto_factory(page)
job = {"job": os.environ["JOB"], "provider": "kaggle", "email": JOBREC["email"],
       "pass": JOBREC["pass"], "userName": "Test User", "userPhone": "+919876543210"}
res = setup.flow_kaggle(page, job, dict(setup.FLOWS["kaggle"]))
check(res["status"] == "done", f"happy: flow completes (got {res['status']}: {res.get('error')})")
payload = json.loads(res["key"] or "{}")
check(payload.get("user") == "testuser" and payload.get("key") == "a" * 32,
      "happy: kaggle.json pair captured (username + 32-hex key)")
check(res["extra"].get("created") is True, "happy: result marked created")
check(page.values.get("otp2") == SIM["otp_phone"], "happy: the chat-delivered phone code was entered")
check(page.values.get("fname") == "Test User" and page.values.get("phone") == "+919876543210",
      "happy: identity came from the user's own profile values")
otp_asks = [p["awaiting"] for p in PROGRESS if p.get("awaiting", {}).get("kind") == "otp"]
check(len(otp_asks) == 2, "happy: exactly two OTP asks (email + phone)")
out = setup.submit_provider_result("kaggle", "Kaggle (GPU compute)", res)
check(out["status"] == "done" and KEYS_POSTED and json.loads(KEYS_POSTED[-1]["key"]) == payload,
      "happy: pair sealed via the runner key channel after the self-test passed")
check(setup.test_key("kaggle", res["key"]) is True, "self-test: sealed pair passes the Kaggle API test")
check(setup.test_key("kaggle", json.dumps({"user": "testuser", "key": "b" * 32})) is False,
      "self-test: a wrong pair is rejected")
check(setup.test_key("kaggle", "not-json") is False, "self-test: a non-pair key is rejected")

# ---------------- wrong OTP: one re-ask, then labelled fail ----------------
reset()
page = FakePage(STATES, make_clicks("999999"))  # the page only accepts 999999
SIM["otp_phone"] = "111111"                     # the user keeps sending a wrong code
setup.goto = fake_goto_factory(page)
res = setup.flow_kaggle(page, dict(job), dict(setup.FLOWS["kaggle"]))
phone_asks = [p["awaiting"] for p in PROGRESS
              if p.get("awaiting", {}).get("kind") == "otp" and "phone" in p["awaiting"]["prompt"].lower()]
check(res["status"] == "failed" and res["extra"].get("wall") == "otp-rejected:phone",
      f"wrong OTP: labelled fail otp-rejected:phone (got {res.get('error')})")
check([a["attempts"] for a in phone_asks] == [1, 2], "wrong OTP: asked once + re-asked once, never a third time")
SIM["otp_phone"] = "730215"

# ---------------- captcha: gate, never a solver ----------------
import inspect
check("solve_" not in inspect.getsource(setup.flow_kaggle),
      "captcha: flow_kaggle contains no solver call")
reset(); TC_CALLS.clear()
setup.take_control = lambda page, job, cfg, reason="captcha": TC_CALLS.append(reason) or False
page = FakePage(STATES, make_clicks(SIM["otp_phone"]))
page.on_click = lambda p, key: None  # the submit lands ON the captcha; it stays up
def goto_cap(p, url, cfg=None):
    p.url = url; p.load("captcha"); return True
setup.goto = goto_cap
res = setup.flow_kaggle(page, dict(job), dict(setup.FLOWS["kaggle"]))
cap_asks = [p["awaiting"] for p in PROGRESS if p.get("awaiting", {}).get("kind") == "captcha"]
check(len(cap_asks) == 1 and TC_CALLS == ["captcha"], "captcha: one kind=captcha ask + Take-Control gate used")
check(res["status"] == "failed" and res["extra"].get("wall") == "captcha:take-control-incomplete",
      "captcha: incomplete gate fails labelled, never solved silently")
setup.take_control = lambda page, job, cfg, reason="captcha": TC_CALLS.append(reason) or True

# ---------------- missing identity: asked, never invented ----------------
reset(jobrec_extra={"userName": "", "userPhone": ""})
page = FakePage(STATES, make_clicks(SIM["otp_phone"]))
setup.goto = fake_goto_factory(page)
job2 = {"job": os.environ["JOB"], "provider": "kaggle", "email": JOBREC["email"],
        "pass": JOBREC["pass"], "userName": "", "userPhone": ""}
# the register submit lands on "exists": the fork signs in with the
# chain credentials and continues to the token — no duplicate account.
orig_clicks = page.on_click
def clicks_exists(p, key):
    if key == "submit" and p.state == "register": p.load("exists")
    elif key == "submit" and p.state == "exists": p.load("aftersignup")
    else: orig_clicks(p, key)
page.on_click = clicks_exists
res = setup.flow_kaggle(page, job2, dict(setup.FLOWS["kaggle"]))
field_asks = [p["awaiting"] for p in PROGRESS if p.get("awaiting", {}).get("kind") == "field"]
seen_fields = list(dict.fromkeys(a.get("field") for a in field_asks))  # heartbeats re-post the same ask id
check(seen_fields == ["name", "phone"],
      "identity: missing name + phone asked in chat (kind=field)")
check(page.values.get("fname") == SIM["name"] and page.values.get("phone") == SIM["phone"],
      "identity: the user's own answers were entered — nothing invented")
check(res["status"] == "done" and any(p.get("step") == "login" for p in PROGRESS),
      "identity: existing-account fork signs in and still reaches the token (no duplicate)")

reset(jobrec_extra={"userName": "", "userPhone": ""}); SIM["answer"] = False
res = setup.flow_kaggle(page, dict(job2), dict(setup.FLOWS["kaggle"]))
check(res["status"] == "failed" and res["extra"].get("wall") == "identity-missing:name",
      "identity: unanswered identity ask fails labelled identity-missing:name")

print()
if FAILS:
    print(f"acctcreatetest: {len(FAILS)} FAIL"); sys.exit(1)
print("acctcreatetest: ALL PASS")
