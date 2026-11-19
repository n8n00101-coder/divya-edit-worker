"""e3test.py — E3 rig for agent_loop resume (persistence + resume).

Drives the loop with a SCRIPTED FAKE BRAIN (no model, no network)
and an in-memory step record standing in for the job record's
steps[] — the same list the Worker persists via agentsteps.

Cases (the E3 acceptance gate):
  (a) kill simulation — a 4-step task runs with started-checkpoints
      on; the "runner" dies after step 2 (the brain raises, exactly
      like a process dying between steps); a FRESH loop resumes from
      the record and completes the task; steps 1-2 handlers executed
      exactly ONCE across both runs, numbering continues at 3.
  (b) in-flight step — the record shows a mutating step as started
      but never finished: resume shows the brain an explicit UNKNOWN
      history entry, REFUSES a mutating call until a read-only
      verification step completes (the blind re-run never executes),
      then lets the verified redo run exactly once.
  (c) terminal jobs are not resumed — by state (done) and by a
      terminal step marker in an otherwise "running" record.
  (d) resume with zero steps behaves like a fresh run.
  (e) a FAILED completed step is preserved as FAILED history on
      resume (not retried by the loop itself, not hidden).
  (f) parse: a started marker that DID complete folds into its
      completion — no UNKNOWN, no duplicate history.

Run: python3 e3test.py   (exit 1 on any failure)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _v in ("WORKER_URL", "RUNNER_KEY", "JOB"):
    os.environ.pop(_v, None)

import agent_loop

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


class RunnerDied(Exception):
    """Simulates the runner process dying mid-job."""


class FakeBrain:
    """A scripted brain (e1test pattern): pops the next scripted
    action per call, records every history it was shown, and raises
    RunnerDied when the script says DIE — a process kill between
    steps, after the previous step was recorded."""

    DIE = object()

    def __init__(self, script):
        self.script = list(script)
        self.histories = []
        self.calls = 0

    def __call__(self, goal, history, tools, observation=None):
        self.calls += 1
        self.histories.append([dict(h) for h in history])
        if self.script:
            a = self.script.pop(0)
            if a is FakeBrain.DIE:
                raise RunnerDied("killed between steps")
            return a
        return {"action": "fail", "reason": "script exhausted"}


def no_stop():
    return False


def counted_tool(name, counts, mutating=False, needs_allow=False):
    def run(args):
        counts[name] = counts.get(name, 0) + 1
        return True, f"{name} result"
    return {"name": name, "desc": name, "run": run,
            "mutating": mutating, "needs_allow": needs_allow}


def completions(entries):
    return [e for e in entries if e.get("phase") != "started"]

# ------------------------------------------------------------ (a) kill+resume
counts = {}
tools = [counted_tool(n, counts) for n in ("s1", "s2", "s3", "s4")]
entries = []
brain1 = FakeBrain([
    {"action": "tool", "tool": "s1", "args": {}},
    {"action": "tool", "tool": "s2", "args": {}},
    FakeBrain.DIE,
])
try:
    agent_loop.run_loop("do four steps", tools, brain=brain1,
                        record=entries.append, stop=no_stop,
                        record_started=True)
    died = False
except RunnerDied:
    died = True
check("(a) the first runner died mid-job", died)
check("(a) steps 1-2 each ran once before the kill",
      counts == {"s1": 1, "s2": 1}, f"{counts}")
check("(a) the record holds started+completion pairs for steps 1-2",
      [(e["n"], e["tool"], e.get("phase")) for e in entries] ==
      [(1, "s1", "started"), (1, "s1", None),
       (2, "s2", "started"), (2, "s2", None)], f"{entries}")

job = {"state": "running", "provider": "agent",
       "task": "do four steps", "steps": entries}
check("(a) the dead job reads as resumable", agent_loop.is_resumable(job))
brain2 = FakeBrain([
    {"action": "tool", "tool": "s3", "args": {}},
    {"action": "tool", "tool": "s4", "args": {}},
    {"action": "done", "answer": "all four steps done"},
])
status, out = agent_loop.resume_trigger(job, tools, brain=brain2,
                                        record=entries.append, stop=no_stop)
check("(a) the resumed loop completes the task",
      status == "done" and out == "all four steps done", f"{status} {out}")
check("(a) EVERY step handler executed exactly once across both runs",
      counts == {"s1": 1, "s2": 1, "s3": 1, "s4": 1}, f"{counts}")
check("(a) step numbering continued from the record (3, 4, done=5)",
      [(e["n"], e["tool"]) for e in completions(entries)] ==
      [(1, "s1"), (2, "s2"), (3, "s3"), (4, "s4"), (5, "done")],
      f"{completions(entries)}")
check("(a) the resumed brain was shown steps 1-2 as history",
      len(brain2.histories[0]) == 2
      and brain2.histories[0][0]["result"] == "ok: s1 result"
      and brain2.histories[0][1]["result"] == "ok: s2 result",
      f"{brain2.histories[0] if brain2.histories else None}")

# ------------------------------------------------------- (b) in-flight step
counts = {}
reader = counted_tool("reader", counts)
submit = counted_tool("submit", counts, mutating=True)
other = counted_tool("other_mut", counts, mutating=True)
tools_b = [reader, submit, other]
entries_b = [
    {"n": 1, "tool": "reader", "arg": "", "ok": True,
     "result": "form visible", "at": 100},
    {"n": 2, "tool": "submit", "arg": "{}", "ok": False,
     "result": "", "phase": "started", "at": 200},
]
job_b = {"state": "running", "provider": "agent",
         "task": "submit the form", "steps": entries_b}
hist_b = agent_loop.build_resume_history(entries_b)
check("(b) resume history states the in-flight step as UNKNOWN",
      len(hist_b) == 2 and hist_b[1]["action"] == "submit"
      and hist_b[1]["result"].startswith("UNKNOWN:")
      and "never recorded" in hist_b[1]["result"], f"{hist_b}")
brain_b = FakeBrain([
    {"action": "tool", "tool": "other_mut", "args": {}},   # blind mutating retry
    {"action": "tool", "tool": "reader", "args": {}},      # read-only verify
    {"action": "tool", "tool": "submit", "args": {}},      # verified redo
    {"action": "done", "answer": "verified, then submitted once"},
])
status, out = agent_loop.resume_loop(job_b, tools_b, brain=brain_b,
                                     record=entries_b.append, stop=no_stop)
check("(b) the resumed task completes after verification",
      status == "done", f"{status} {out}")
refusals = [e for e in entries_b
            if e["tool"] == "other_mut" and e["ok"] is False
            and "REFUSED (resume safety)" in e["result"]]
check("(b) the blind mutating call was REFUSED before any verification",
      len(refusals) == 1, f"{entries_b}")
check("(b) the refused handler NEVER executed",
      counts.get("other_mut", 0) == 0, f"{counts}")
check("(b) the refusal was fed back to the brain as FAILED history",
      any("REFUSED (resume safety)" in h.get("result", "")
          for h in brain_b.histories[1]), f"{brain_b.histories}")
check("(b) verify step ran, then the redo ran exactly once",
      counts.get("reader") == 1 and counts.get("submit") == 1, f"{counts}")
order_b = [e["tool"] for e in completions(entries_b)]
check("(b) record order: refusal -> verify -> redo",
      order_b.index("other_mut") < order_b.index("reader", 2)
      and order_b.index("reader", 2) < order_b.index("submit", 2),
      f"{order_b}")

# ------------------------------------------------------------ (c) terminal
brain_c = FakeBrain([{"action": "done", "answer": "should never run"}])
job_done = {"state": "done", "provider": "agent", "task": "t",
            "steps": [{"n": 1, "tool": "echo", "arg": "", "ok": True,
                       "result": "hi", "at": 1}]}
status, out = agent_loop.resume_loop(job_done, [], brain=brain_c,
                                     record=lambda e: None, stop=no_stop)
check("(c) a done job is not resumed",
      status == "terminal" and brain_c.calls == 0, f"{status}")
check("(c) the trigger declines a terminal job",
      agent_loop.resume_trigger(job_done, [], brain=brain_c) is None
      and not agent_loop.is_resumable(job_done))
job_marked = {"state": "running", "provider": "agent", "task": "t",
              "steps": [{"n": 1, "tool": "echo", "arg": "", "ok": True,
                         "result": "hi", "at": 1},
                        {"n": 2, "tool": "done", "arg": "", "ok": True,
                         "result": "hi", "at": 2}]}
status, out = agent_loop.resume_loop(job_marked, [], brain=brain_c,
                                     record=lambda e: None, stop=no_stop)
check("(c) a terminal step marker also blocks resume",
      status == "terminal" and brain_c.calls == 0, f"{status}")

# ------------------------------------------------------------ (d) zero steps
counts_d = {}
echo_d = counted_tool("echo", counts_d)
entries_d = []
job_fresh = {"state": "running", "provider": "agent",
             "task": "fresh task", "steps": []}
brain_d = FakeBrain([
    {"action": "tool", "tool": "echo", "args": {}},
    {"action": "done", "answer": "fresh done"},
])
status, out = agent_loop.resume_loop(job_fresh, [echo_d], brain=brain_d,
                                     record=entries_d.append, stop=no_stop)
check("(d) zero-step resume behaves like a fresh run",
      status == "done" and out == "fresh done"
      and counts_d == {"echo": 1}, f"{status} {counts_d}")
check("(d) numbering starts at 1 on a zero-step record",
      [(e["n"], e["tool"]) for e in completions(entries_d)] ==
      [(1, "echo"), (2, "done")], f"{entries_d}")
check("(d) zero steps is a fresh run, not a 'resume' for the trigger",
      not agent_loop.is_resumable(job_fresh)
      and agent_loop.resume_trigger(job_fresh, [echo_d]) is None)

# ------------------------------------------------- (e) FAILED step preserved
counts_e = {}
flaky_e = counted_tool("flaky", counts_e)
next_e = counted_tool("next", counts_e)
entries_e = [
    {"n": 1, "tool": "flaky", "arg": "", "ok": False,
     "result": "boom: transient failure", "at": 100},
]
job_e = {"state": "running", "provider": "agent",
         "task": "flaky then next", "steps": entries_e}
brain_e = FakeBrain([
    {"action": "tool", "tool": "next", "args": {}},
    {"action": "done", "answer": "moved on with the failure known"},
])
status, out = agent_loop.resume_loop(job_e, [flaky_e, next_e], brain=brain_e,
                                     record=entries_e.append, stop=no_stop)
check("(e) resume completes with the failure in history",
      status == "done", f"{status} {out}")
check("(e) the brain was shown the FAILED result, not a cleaned record",
      brain_e.histories[0] and
      brain_e.histories[0][0]["result"] == "FAILED: boom: transient failure",
      f"{brain_e.histories}")
check("(e) the loop itself never re-ran the failed step",
      counts_e == {"next": 1}, f"{counts_e}")

# ------------------------------------------------------- (f) parse folding
parsed = agent_loop.parse_recorded_steps([
    {"n": 1, "tool": "x", "arg": "", "ok": False, "result": "",
     "phase": "started", "at": 1},
    {"n": 1, "tool": "x", "arg": "", "ok": True, "result": "x done", "at": 2},
    {"n": 2, "tool": "y", "arg": "", "ok": False, "result": "",
     "phase": "started", "at": 3},
])
check("(f) a completed started-step folds into its completion",
      len(parsed["completed"]) == 1 and parsed["history"][0]["result"] == "ok: x done",
      f"{parsed}")
check("(f) only the truly unfinished step is inflight",
      len(parsed["inflight"]) == 1
      and parsed["inflight"][0]["tool"] == "y"
      and parsed["history"][1]["result"].startswith("UNKNOWN:"),
      f"{parsed}")
check("(f) last_n counts every recorded step",
      parsed["last_n"] == 2, f"{parsed['last_n']}")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
sys.exit(1 if FAIL else 0)
