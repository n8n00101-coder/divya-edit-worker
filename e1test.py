"""e1test.py — E1 rig for agent_loop.py (the general agent loop).

Drives the loop with a SCRIPTED FAKE BRAIN (no model, no network):
the brain is a queue of action dicts, and each call records the
history it was shown, so the rig can prove what the loop fed back.

Cases (the E1 acceptance gate):
  (a) a multi-step task completes in order and stops at done;
  (b) MAX_STEPS cap is enforced — an endless brain fails honestly;
  (c) a FAILING tool result is fed back to the brain and the loop
      recovers (retry succeeds) instead of dying;
  (d) a stop flag halts the loop at the next checkpoint;
  (e) an unknown tool is fed back as a failure, not a crash;
  (f) an unreachable brain (None) fails honestly;
  (g) an empty done answer is rejected (browse honesty rule), a real
      answer is then accepted;
  (h) a tool that RAISES becomes a FAILED step fed back to the brain;
  (i) defaults are safe with no Worker env: worker_brain -> None,
      job_state tool -> honest failure, worker_record/worker_stop
      never raise.

Run: python3 e1test.py   (exit 1 on any failure)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The rig must never talk to a real Worker: strip the channel env so
# the default plumbing is inert, and every loop run below injects its
# own brain/record/stop anyway.
for _v in ("WORKER_URL", "RUNNER_KEY", "JOB"):
    os.environ.pop(_v, None)

import agent_loop

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


class FakeBrain:
    """A scripted brain: pops the next scripted action per call and
    remembers every history it was shown."""

    def __init__(self, script):
        self.script = list(script)
        self.histories = []

    def __call__(self, goal, history, tools, observation=None):
        self.histories.append([dict(h) for h in history])
        if self.script:
            return self.script.pop(0)
        return {"action": "fail", "reason": "script exhausted"}


def recorder():
    entries = []
    return entries, entries.append


def no_stop():
    return False


ECHO = {"name": "echo", "desc": "echo", "run": lambda a: (True, str(a.get("text") or ""))}
NOOP = {"name": "noop", "desc": "noop", "run": lambda a: (True, "ok")}

# ------------------------------------------------------------ (a) in order
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "echo", "args": {"text": "one"}},
    {"action": "tool", "tool": "echo", "args": {"text": "two"}},
    {"action": "done", "answer": "did one and two"},
])
status, out = agent_loop.run_loop("say one then two", [ECHO], brain=brain,
                                  record=record, stop=no_stop)
check("(a) multi-step task completes with done", status == "done", status)
check("(a) done answer is the brain's answer", out == "did one and two", out)
tool_entries = [e for e in entries if e["tool"] == "echo"]
check("(a) steps recorded in order (one, two)",
      [e["result"] for e in tool_entries] == ["one", "two"], f"{entries}")
check("(a) step numbers are 1, 2", [e["n"] for e in tool_entries] == [1, 2])
check("(a) terminal done entry recorded",
      entries[-1]["tool"] == "done" and entries[-1]["ok"] is True)
check("(a) brain saw prior results before deciding",
      len(brain.histories) == 3 and brain.histories[2][-1]["result"] == "ok: two")

# ------------------------------------------------------------ (b) step cap
entries, record = recorder()
brain = FakeBrain([{"action": "tool", "tool": "noop", "args": {}}] * 50)
status, out = agent_loop.run_loop("never ends", [NOOP], brain=brain,
                                  record=record, stop=no_stop, max_steps=5)
check("(b) endless brain hits the step cap and fails", status == "failed", status)
check("(b) failure is the honest step-limit message", "Step limit" in out, out)
check("(b) exactly max_steps tools executed",
      len([e for e in entries if e["tool"] == "noop"]) == 5, f"{len(entries)}")
check("(b) default budget is browse's MAX_STEPS=40", agent_loop.MAX_STEPS == 40)

# ------------------------------------------------- (c) failure fed back
calls = {"n": 0}


def flaky(args):
    calls["n"] += 1
    if calls["n"] == 1:
        return False, "boom: transient failure"
    return True, "recovered"


FLAKY = {"name": "flaky", "desc": "fails once", "run": flaky}
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "flaky", "args": {}},
    {"action": "tool", "tool": "flaky", "args": {}},
    {"action": "done", "answer": "recovered on retry"},
])
status, out = agent_loop.run_loop("flaky task", [FLAKY], brain=brain,
                                  record=record, stop=no_stop)
check("(c) loop recovers after a tool failure", status == "done", status)
check("(c) the FAILED result was fed back to the brain",
      len(brain.histories) >= 2
      and brain.histories[1][-1]["result"].startswith("FAILED:")
      and "boom" in brain.histories[1][-1]["result"],
      f"{brain.histories}")
check("(c) both attempts recorded (fail then ok)",
      [e["ok"] for e in entries if e["tool"] == "flaky"] == [False, True],
      f"{entries}")

# ------------------------------------------------------------ (d) stop flag
entries, record = recorder()
polls = {"n": 0}


def stop_after_two():
    polls["n"] += 1
    return polls["n"] > 2  # two checkpoints pass, the third stops


brain = FakeBrain([{"action": "tool", "tool": "noop", "args": {}}] * 10)
status, out = agent_loop.run_loop("stoppable", [NOOP], brain=brain,
                                  record=record, stop=stop_after_two)
check("(d) stop flag halts the loop", status == "stopped", status)
check("(d) exactly 2 steps ran before the halt",
      len([e for e in entries if e["tool"] == "noop"]) == 2, f"{entries}")
check("(d) the halt itself is recorded",
      entries[-1]["tool"] == "stopped")

# ------------------------------------------------------- (e) unknown tool
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "nope", "args": {}},
    {"action": "done", "answer": "gave up on the unknown tool"},
])
status, out = agent_loop.run_loop("bad tool", [ECHO], brain=brain,
                                  record=record, stop=no_stop)
check("(e) unknown tool does not crash the loop", status == "done", status)
check("(e) unknown tool recorded as a FAILED step",
      entries[0]["tool"] == "nope" and entries[0]["ok"] is False
      and "unknown tool" in entries[0]["result"], f"{entries}")
check("(e) brain was told the tool is unknown",
      "unknown tool" in brain.histories[1][-1]["result"])

# ---------------------------------------------------- (f) brain unreachable
entries, record = recorder()
status, out = agent_loop.run_loop("no brain", [ECHO],
                                  brain=lambda g, h, t, o=None: None,
                                  record=record, stop=no_stop)
check("(f) unreachable brain fails honestly",
      status == "failed" and "agentstep unreachable" in out, out)

# ------------------------------------------------- (g) empty done rejected
entries, record = recorder()
brain = FakeBrain([
    {"action": "done", "answer": ""},
    {"action": "done", "answer": "the real answer"},
])
status, out = agent_loop.run_loop("answer honestly", [ECHO], brain=brain,
                                  record=record, stop=no_stop)
check("(g) empty done is rejected, real answer accepted",
      status == "done" and out == "the real answer", f"{status} {out}")
check("(g) the rejection was fed back to the brain",
      any("rejected: empty answer" in h["result"]
          for h in brain.histories[1]))

# ------------------------------------------------------- (h) raising tool
def raiser(args):
    raise RuntimeError("kaboom")


RAISER = {"name": "raiser", "desc": "raises", "run": raiser}
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "raiser", "args": {}},
    {"action": "fail", "reason": "tool is broken"},
])
status, out = agent_loop.run_loop("raising tool", [RAISER], brain=brain,
                                  record=record, stop=no_stop)
check("(h) a raising tool becomes a FAILED step, loop survives to fail",
      status == "failed" and out == "tool is broken", f"{status} {out}")
check("(h) the exception was recorded + fed back",
      entries[0]["ok"] is False and "kaboom" in entries[0]["result"]
      and "kaboom" in brain.histories[1][-1]["result"], f"{entries}")

# ------------------------------------------------------- (i) safe defaults
check("(i) worker_brain with no Worker env returns None",
      agent_loop.worker_brain("g", [], agent_loop.default_tools()) is None)
ok, res = agent_loop.default_tools()[2]["run"]({})
check("(i) job_state tool fails honestly with no Worker env",
      ok is False and "unreachable" in res, res)
try:
    agent_loop.worker_record({"n": 1, "tool": "noop", "ok": True, "result": ""})
    agent_loop.worker_stop()
    safe = True
except Exception:
    safe = False
check("(i) worker_record / worker_stop never raise with no env", safe)
check("(i) default tool set is noop + echo + job_state",
      [t["name"] for t in agent_loop.default_tools()] == ["noop", "echo", "job_state"])
ok, res = agent_loop.default_tools()[1]["run"]({"text": "hello"})
check("(i) echo stub works", ok is True and res == "hello")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
