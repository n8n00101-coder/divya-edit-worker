"""e2test.py — E2 rig for tools_registry.py (the tools layer).

Drives agent_loop.run_loop with tools taken from a Registry and a
SCRIPTED FAKE BRAIN (no model). "Real tool" proofs run against local
fixtures only — no live external calls:

  - job_state runs for real: a local stub Worker (http.server on an
    ephemeral port) answers GET /api/setup/runner/job, so the tool's
    real httpx read path executes end to end.
  - browser_* tools run for real: browse.py / setup.py are imported
    (with a stub `playwright` module — the browser stack is not
    installed on this VM; it lives in the Actions runner) and their
    actual primitives (snapshot / do_click / do_type) execute
    against a FakePage implementing the small Playwright surface
    those functions touch.

Cases (the E2 acceptance gate):
  (0) registry contract: entries carry name/desc/schema/handler/
      mutating/needs_allow; brain_list() is names+descs only;
      browser tools registered with the right classifications.
  (a) a scripted multi-tool task completes using TWO different real
      read-only registry tools (job_state + browser_read).
  (b) the Allow gate: a mutating tool without Allow is REFUSED (the
      handler never runs) and the refusal is fed back to the brain
      as a FAILED step; with Allow (callable and set forms) the same
      tools execute for real.
  (c) an unknown tool name is rejected exactly as in E1.
  (d) a tool whose handler RAISES becomes a FAILED step and the
      loop recovers.
  (e) schema validation: bad args (missing required / wrong type)
      fail the step BEFORE the handler runs.

Run: python3 e2test.py   (exit 1 on any failure)
"""

import json
import os
import re
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Hermetic rig: this VM exports egress-proxy env vars that make
# httpx mangle even 127.0.0.1 URLs. The real runner (GitHub Actions)
# has none of them, and the rig must only ever talk to its local
# stub — clear them before anything imports httpx.
for _v in ("http_proxy", "https_proxy", "all_proxy",
           "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
           "no_proxy", "NO_PROXY"):
    os.environ.pop(_v, None)

# ---------------------------------------------------------- stub Worker
CANNED_JOB = {"state": "running", "provider": "agent", "step": "rig-step",
              "note": "e2 rig job", "steps": []}


class StubHandler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/setup/runner/job"):
            self._json({"ok": True, "job": CANNED_JOB})
        else:
            self._json({}, 404)

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        if n:
            self.rfile.read(n)
        self._json({"ok": True})

    def log_message(self, *a):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
PORT = server.server_address[1]

# The runner channel env, pointed at the stub. setup.py reads
# WORKER_URL at import time (browse registration imports it lazily),
# so this must be set before register_browser_tools runs.
os.environ["WORKER_URL"] = f"http://127.0.0.1:{PORT}"
os.environ["RUNNER_KEY"] = "e2-rig-key"
os.environ["JOB"] = "e2-rig-job"
os.environ["PROVIDER"] = "browse"

# browse.py / setup.py import playwright at module level; the real
# stack is not on this VM. A stub module lets the REAL browse/setup
# code import and run against FakePage below.
_pw = types.ModuleType("playwright")
_sa = types.ModuleType("playwright.sync_api")
_sa.sync_playwright = lambda *a, **k: None
_pw.sync_api = _sa
sys.modules.setdefault("playwright", _pw)
sys.modules.setdefault("playwright.sync_api", _sa)

import agent_loop
import tools_registry

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


class FakeBrain:
    """A scripted brain (e1test pattern): pops the next action per
    call and remembers every (history, tools) it was shown."""

    def __init__(self, script):
        self.script = list(script)
        self.histories = []
        self.offered = []

    def __call__(self, goal, history, tools, observation=None):
        self.histories.append([dict(h) for h in history])
        self.offered.append([(t["name"], t.get("desc", "")) for t in tools])
        if self.script:
            return self.script.pop(0)
        return {"action": "fail", "reason": "script exhausted"}


def recorder():
    entries = []
    return entries, entries.append


def no_stop():
    return False


# ------------------------------------------------------------- FakePage
def fixture_snapshot(page):
    return {
        "url": page.url,
        "title": "Fixture Form",
        "text": "Fixture page text: a name field and a Go button.",
        "elements": [
            {"i": 0, "tag": "input", "type": "text", "label": "Name",
             "href": "", "name": "name"},
            {"i": 1, "tag": "button", "type": "submit", "label": "Go",
             "href": "", "name": ""},
        ],
        "cookie_banner": False,
    }


class FakeEl:
    def __init__(self, page, i):
        self.page = page
        self.i = i

    def scroll_into_view_if_needed(self, timeout=None):
        self.page.calls.append(("scroll_into_view", self.i))

    def click(self, timeout=None):
        self.page.calls.append(("click", self.i))

    def fill(self, text, timeout=None):
        self.page.calls.append(("fill", self.i, text))

    def evaluate(self, js):
        return "input"  # tagName for do_type's dropdown check

    def bounding_box(self):
        return {"x": 1, "y": 2, "width": 10, "height": 10}

    def select_option(self, **kw):
        self.page.calls.append(("select_option", self.i, kw))
        return []


class FakeLocator:
    def __init__(self, page, i):
        self.page = page
        self.i = i

    def count(self):
        return 1 if self.i in self.page.known else 0

    @property
    def first(self):
        return FakeEl(self.page, self.i)


class FakeMouse:
    def wheel(self, x, y):
        pass

    def move(self, x, y):
        pass


class FakeKeyboard:
    def type(self, text, delay=None):
        pass

    def press(self, key):
        pass


class FakePage:
    """The small Playwright surface browse.snapshot / do_click /
    do_type actually touch. evaluate() dispatches on the JS text:
    the snapshot script -> the fixture snapshot; the consent probe
    -> False; dom_stamp -> a stable stamp."""

    def __init__(self):
        self.url = "https://fixture.test/form"
        self.calls = []
        self.known = {0, 1}
        self.stamp = "https://fixture.test/form|100"
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()
        self.frames = []

    def evaluate(self, js):
        s = str(js)
        if "onetrust" in s:
            return False
        if "querySelectorAll" in s:
            return fixture_snapshot(self)
        if "location.href" in s:
            return self.stamp
        return ""

    def locator(self, sel):
        m = re.search(r'data-julie-idx="(\d+)"', str(sel))
        return FakeLocator(self, int(m.group(1)) if m else -1)

    def wait_for_timeout(self, ms):
        self.calls.append(("wait", ms))

    def go_back(self, **kw):
        self.calls.append(("back",))

    def goto(self, url, **kw):
        self.calls.append(("goto", url))
        self.url = url


def browser_registry(page):
    reg = tools_registry.default_registry()
    tools_registry.register_browser_tools(reg, page)
    return reg


# ------------------------------------------------------- (0) contract
reg = tools_registry.default_registry()
check("(0) default registry holds E1's tools",
      reg.names() == ["noop", "echo", "job_state"], str(reg.names()))
ok = True
for name in reg.names():
    e = reg.get(name)
    ok = ok and bool(e["desc"]) and isinstance(e["schema"], dict) \
        and callable(e["handler"]) and e["mutating"] is False \
        and e["needs_allow"] is False
check("(0) every entry carries desc/schema/handler + read-only flags", ok)
check("(0) stub flags honest (noop/echo stub, job_state real)",
      reg.get("noop")["stub"] and reg.get("echo")["stub"]
      and not reg.get("job_state")["stub"])
check("(0) unknown tool is not in the registry", reg.get("teleport") is None
      and "teleport" not in reg)
bl = reg.brain_list()
check("(0) brain_list is names+descs only, in order",
      bl == [{"name": e["name"], "desc": e["desc"]}
             for e in (reg.get(n) for n in reg.names())], str(bl))

page = FakePage()
breg = browser_registry(page)
cls = {n: (breg.get(n)["mutating"], breg.get(n)["needs_allow"])
       for n in breg.names() if n.startswith("browser_")}
check("(0) browser tools registered",
      set(cls) == {"browser_read", "browser_open", "browser_click",
                   "browser_type", "browser_select", "browser_scroll",
                   "browser_back", "browser_wait"}, str(sorted(cls)))
check("(0) browser_read read-only; open/click/type/select mutating+Allow",
      cls["browser_read"] == (False, False)
      and cls["browser_open"] == (True, True)
      and cls["browser_click"] == (True, True)
      and cls["browser_type"] == (True, True)
      and cls["browser_select"] == (True, True), str(cls))
check("(0) scroll/back mutating without Allow; wait read-only",
      cls["browser_scroll"] == (True, False)
      and cls["browser_back"] == (True, False)
      and cls["browser_wait"] == (False, False), str(cls))
check("(0) browser tools carry arg schemas",
      breg.get("browser_type")["schema"]["text"]["required"] is True
      and breg.get("browser_click")["schema"]["i"]["type"] == "number")

# ------------------------------------------- (a) two real read-only tools
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "job_state", "args": {}},
    {"action": "tool", "tool": "browser_read", "args": {}},
    {"action": "done", "answer": "job running; page title Fixture Form"},
])
status, out = agent_loop.run_loop("inspect job and page", breg.as_tools(),
                                  brain=brain, record=record, stop=no_stop)
check("(a) multi-tool task completes at done", status == "done", status)
seq = [(e["tool"], e["ok"]) for e in entries]
check("(a) steps recorded in order, both ok",
      seq[:2] == [("job_state", True), ("browser_read", True)], str(seq))
check("(a) job_state result is the real stub-Worker record",
      "state=running" in entries[0]["result"]
      and "step=rig-step" in entries[0]["result"], entries[0]["result"])
check("(a) browser_read result is the real snapshot content",
      "Fixture Form" in entries[1]["result"]
      and "Name" in entries[1]["result"], entries[1]["result"][:120])
check("(a) brain was offered exactly the registry's list",
      brain.offered[0] == [(d["name"], d["desc"]) for d in breg.brain_list()])

# ------------------------------------------------------- (b) Allow gate
page2 = FakePage()
breg2 = browser_registry(page2)
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "browser_click", "args": {"i": 1}},
    {"action": "done", "answer": "click was refused, stopping here"},
])
status, out = agent_loop.run_loop("click Go", breg2.as_tools(), brain=brain,
                                  record=record, stop=no_stop)
ref = [e for e in entries if e["tool"] == "browser_click"]
check("(b) un-Allowed mutating call recorded as FAILED step",
      len(ref) == 1 and ref[0]["ok"] is False
      and "REFUSED" in ref[0]["result"], str(entries))
check("(b) refusal fed back to the brain as FAILED history",
      any("FAILED" in h.get("result", "") and "REFUSED" in h["result"]
          for h in brain.histories[1]), str(brain.histories))
check("(b) handler NEVER executed without Allow",
      ("click", 1) not in page2.calls, str(page2.calls))

entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "browser_click", "args": {"i": 1}},
    {"action": "tool", "tool": "browser_type",
     "args": {"i": 0, "text": "Ajju"}},
    {"action": "done", "answer": "clicked Go and typed the name"},
])
status, out = agent_loop.run_loop(
    "click Go, type name", breg2.as_tools(), brain=brain, record=record,
    stop=no_stop, allow=lambda name, args: name.startswith("browser_"))
seq = [(e["tool"], e["ok"]) for e in entries]
check("(b) with Allow (callable) the same tools execute for real",
      status == "done" and seq[:2] == [("browser_click", True),
                                       ("browser_type", True)], str(seq))
check("(b) real primitives ran: click + fill recorded on the page",
      ("click", 1) in page2.calls and ("fill", 0, "Ajju") in page2.calls,
      str(page2.calls))

entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "browser_click", "args": {"i": 1}},
    {"action": "done", "answer": "clicked"},
])
status, out = agent_loop.run_loop("click Go", breg2.as_tools(), brain=brain,
                                  record=record, stop=no_stop,
                                  allow={"browser_click"})
check("(b) Allow as a name set also works",
      status == "done" and entries[0]["ok"] is True, str(entries))

# ------------------------------------------------------- (c) unknown tool
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "teleport", "args": {}},
    {"action": "tool", "tool": "echo", "args": {"text": "hi"}},
    {"action": "done", "answer": "recovered"},
])
status, out = agent_loop.run_loop("teleport please", breg.as_tools(),
                                  brain=brain, record=record, stop=no_stop)
check("(c) unknown tool rejected as FAILED step, loop recovers",
      status == "done" and entries[0]["ok"] is False
      and "unknown tool" in entries[0]["result"], str(entries))
check("(c) the rejection was fed back to the brain",
      any("unknown tool" in h.get("result", "") for h in brain.histories[1]))

# ------------------------------------------------------- (d) raising tool
reg4 = tools_registry.default_registry()


def _boom(args):
    raise RuntimeError("kaboom in handler")


reg4.register("boom", "Always raises. Rig tool.", {}, _boom)
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "boom", "args": {}},
    {"action": "tool", "tool": "echo", "args": {"text": "recovered"}},
    {"action": "done", "answer": "survived the boom"},
])
status, out = agent_loop.run_loop("boom then recover", reg4.as_tools(),
                                  brain=brain, record=record, stop=no_stop)
check("(d) raising handler becomes a FAILED step, loop recovers",
      status == "done" and entries[0]["ok"] is False
      and "kaboom in handler" in entries[0]["result"], str(entries))
check("(d) the failure was fed back to the brain",
      any("FAILED" in h.get("result", "") for h in brain.histories[1]))

# ------------------------------------------------------- (e) schema gate
page5 = FakePage()
breg5 = browser_registry(page5)
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "browser_type", "args": {"i": 0}},
    {"action": "tool", "tool": "browser_click", "args": {"i": "zero"}},
    {"action": "done", "answer": "both arg sets were bad"},
])
status, out = agent_loop.run_loop("bad args", breg5.as_tools(), brain=brain,
                                  record=record, stop=no_stop, allow=True)
check("(e) missing required arg fails the step with the reason",
      entries[0]["ok"] is False and "bad args" in entries[0]["result"]
      and "text" in entries[0]["result"], str(entries))
check("(e) wrong-typed arg fails the step with the reason",
      entries[1]["ok"] is False and "bad args" in entries[1]["result"]
      and "'i'" in entries[1]["result"], str(entries))
check("(e) handlers never ran on bad args",
      not any(c[0] in ("fill", "click") for c in page5.calls),
      str(page5.calls))

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
sys.exit(1 if FAIL else 0)
