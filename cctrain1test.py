"""cctrain1test.py — CCTRAIN Session 1 rig: get_history tool for long-job context.

Drives the loop with a SCRIPTED FAKE BRAIN (no model, no network):
the brain is a queue of action dicts, and each call records the
history it was shown, so the rig can prove what the loop fed back.

Cases (the TOP GAP implementation: context handling across long jobs):
  (a) get_history returns the full step history when the brain calls it
  (b) get_history respects limit and offset args for pagination
  (c) get_history works on a resumed job (seed_history is not in the record)
  (d) get_history returns helpful message when no steps recorded
  (e) get_history is read-only (never mutating, never needs Allow)
  (f) the brain can use get_history to recover context beyond HISTORY_WINDOW

Run: python3 cctrain1test.py   (exit 1 on any failure)
"""

import os
import sys
from unittest.mock import patch

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


def recorder(job_steps=None):
    """Create a recorder that appends to the given list (or a new one)."""
    entries = job_steps if job_steps is not None else []
    return entries, entries.append


def no_stop():
    return False


def full_registry():
    """The default tool set from agent_loop.default_tools() — includes
    get_history now."""
    return agent_loop.default_tools()


def run_with_job(job, brain, goal, tools=None, **kw):
    """Run the loop with fetch_job_state patched to return the given job."""
    tools = tools or full_registry()
    mock_job = dict(job)
    mock_job.setdefault("state", "running")
    mock_job.setdefault("steps", [])
    # Ensure the recorder uses the job's steps list
    if "record" in kw:
        # The test's record function already appends to the right list
        pass
    with patch.object(agent_loop, "fetch_job_state", return_value=mock_job):
        return agent_loop.run_loop(goal, tools, brain=brain, **kw)


# ------------------------------------------------------------ (a) basic get_history
job = {"steps": []}
entries, record = recorder(job["steps"])
brain = FakeBrain([
    {"action": "tool", "tool": "echo", "args": {"text": "step one"}},
    {"action": "tool", "tool": "echo", "args": {"text": "step two"}},
    {"action": "tool", "tool": "get_history", "args": {}},
    {"action": "done", "answer": "history retrieved"},
])
status, out = run_with_job(job, brain, "run two steps then get history",
                           record=record, stop=no_stop)
check("(a) loop completes with done", status == "done", status)
check("(a) get_history was called", any(e.get("tool") == "get_history" for e in entries))
hist_step = next(e for e in entries if e.get("tool") == "get_history")
check("(a) get_history step recorded OK", hist_step.get("ok") is True, hist_step.get("result"))
check("(a) history result contains both prior steps",
      "step one" in hist_step.get("result", "") and "step two" in hist_step.get("result", ""),
      hist_step.get("result"))

# ------------------------------------------------------------ (b) limit and offset
job = {"steps": []}
entries, record = recorder(job["steps"])
brain = FakeBrain([
    {"action": "tool", "tool": "echo", "args": {"text": "first"}},
    {"action": "tool", "tool": "echo", "args": {"text": "second"}},
    {"action": "tool", "tool": "echo", "args": {"text": "third"}},
    {"action": "tool", "tool": "get_history", "args": {"limit": 2}},
    {"action": "tool", "tool": "get_history", "args": {"limit": 1, "offset": 1}},
    {"action": "done", "answer": "paginated history retrieved"},
])
status, out = run_with_job(job, brain, "three steps then paginated history",
                           record=record, stop=no_stop)
check("(b) loop completes with done", status == "done", status)
hist_steps = [e for e in entries if e.get("tool") == "get_history"]
check("(b) two get_history calls recorded", len(hist_steps) == 2)
# First call: limit=2 -> most recent 2 (third, second)
check("(b) limit=2 returns most recent 2 steps",
      "third" in hist_steps[0].get("result", "") and "second" in hist_steps[0].get("result", "") and "first" not in hist_steps[0].get("result", ""),
      hist_steps[0].get("result"))
# Second call: limit=1, offset=1 -> skip most recent (get_history call itself), return third
check("(b) limit=1 offset=1 skips the prior get_history call, returns third",
      "third" in hist_steps[1].get("result", "") and "second" not in hist_steps[1].get("result", "") and "first" not in hist_steps[1].get("result", ""),
      hist_steps[1].get("result"))

# ------------------------------------------------------------ (c) works on resumed job (seed_history not in record)
job = {"steps": []}
entries, record = recorder(job["steps"])
# Simulate a seed history from a previous run (not recorded as steps)
seed = [
    {"action": "tool", "arg": "{\"text\": \"seed step\"}", "result": "ok: seeded"},
]
brain = FakeBrain([
    {"action": "tool", "tool": "echo", "args": {"text": "new step"}},
    {"action": "tool", "tool": "get_history", "args": {}},
    {"action": "tool", "tool": "job_state", "args": {}},
    {"action": "done", "answer": "history from resume"},
])
status, out = run_with_job(job, brain, "resume with seed then get history",
                           record=record, stop=no_stop,
                           seed_history=seed, step_offset=1)
check("(c) resumed loop completes with done", status == "done", status)
hist_step = next(e for e in entries if e.get("tool") == "get_history")
check("(c) get_history shows only recorded steps (not seed_history)",
      "new step" in hist_step.get("result", "") and "seed step" not in hist_step.get("result", ""),
      hist_step.get("result"))
# The recorder appended to job["steps"] which is the same list mock_job["steps"]
# points to (shallow copy), so job_state should see 2 recorded steps
check("(c) recorded step count is 2 (seed offset 1 + new step + get_history = 2 steps)",
      any("recorded steps=2" in str(e.get("result") or "") for e in entries if e.get("tool") == "job_state"))

# ------------------------------------------------------------ (d) no steps recorded yet
job = {"steps": []}
entries, record = recorder(job["steps"])
brain = FakeBrain([
    {"action": "tool", "tool": "get_history", "args": {}},
    {"action": "done", "answer": "empty history"},
])
status, out = run_with_job(job, brain, "get history on fresh job",
                           record=record, stop=no_stop)
check("(d) loop completes with done", status == "done", status)
hist_step = next(e for e in entries if e.get("tool") == "get_history")
check("(d) get_history returns helpful empty message",
      "no steps recorded" in hist_step.get("result", "") or "total=0" in hist_step.get("result", ""),
      hist_step.get("result"))

# ------------------------------------------------------------ (e) read-only tool (not mutating, no Allow needed)
reg = full_registry()
hist_tool = next(t for t in reg if t["name"] == "get_history")
check("(e) get_history is read-only (mutating=False)", hist_tool.get("mutating") is False)
check("(e) get_history needs no Allow (needs_allow=False)", hist_tool.get("needs_allow") is False)
check("(e) get_history is not a stub", hist_tool.get("stub") is False)
check("(e) get_history has correct desc", "limit" in hist_tool.get("desc", "") and "offset" in hist_tool.get("desc", ""))

# ------------------------------------------------------------ (f) context recovery beyond HISTORY_WINDOW
# Simulate a long job with > HISTORY_WINDOW steps
job = {"steps": []}
entries, record = recorder(job["steps"])
HISTORY_WINDOW = agent_loop.HISTORY_WINDOW
# Create a script that does many steps, then calls get_history
script = []
for i in range(HISTORY_WINDOW + 3):
    script.append({"action": "tool", "tool": "echo", "args": {"text": f"step {i}"}})
script.append({"action": "tool", "tool": "get_history", "args": {}})
script.append({"action": "done", "answer": "recovered full context"})

brain = FakeBrain(script)
status, out = run_with_job(job, brain, "long job then recover context",
                           record=record, stop=no_stop,
                           max_steps=HISTORY_WINDOW + 10)
check("(f) long job completes with done", status == "done", status)
hist_step = next(e for e in entries if e.get("tool") == "get_history")
# The brain's history is NOT limited by the loop for fake brains;
# the loop passes full history. worker_brain truncates to HISTORY_WINDOW.
# The key test: get_history tool returns ALL steps beyond the window.
check("(f) get_history returns all steps beyond the window",
      all(f"step {i}" in hist_step.get("result", "") for i in range(HISTORY_WINDOW + 3)),
      hist_step.get("result")[:500])

print()
if FAIL:
    print(f"CCTRAIN1TEST.PY: {len(FAIL)} FAILURES")
    sys.exit(1)
print(f"CCTRAIN1TEST.PY: ALL {len(PASS)} TESTS PASS")
sys.exit(0)