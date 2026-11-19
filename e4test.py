"""e4test.py — E4 rig for agent_loop chain continuation.

Drives run_chain with a SCRIPTED FAKE BRAIN keyed by goal text (no
model, no network) and an in-memory step record standing in for the
job record's steps[] — the same list the Worker persists via
agentsteps, chain markers included.

Cases (the E4 acceptance gate):
  (a) 3-goal chain runs end-to-end in order; each goal's brain is
      seeded with the handoff summary of the previous goal(s) —
      built from recorded steps + final answer, not a transcript.
  (b) goal 2 fails -> chain halts, goal 3 never starts, the chain
      state records the failure reason; re-running the chain does
      NOT retry (terminal), the brain is never called again.
  (c) stop during goal 2 -> chain halts as stopped, goal 3 never
      starts, the reason is recorded.
  (d) chain cap enforced: with max_goals=2 a 4-goal chain runs
      exactly 2 goals and halts with the cap reason recorded.
  (e) kill mid-goal-2 (brain raises, like a process dying between
      steps) + resume from the record -> chain completes; goal 1
      and the finished goal-2 step executed exactly ONCE across
      both runs; the resumed goal-2 brain sees goal 1's handoff
      AND goal 2's own recorded step as history.
  (f) goal descriptor fields work: a goal's tool subset is what
      its brain is offered, and a goal-level Allow lets a
      needs_allow tool run while the chain-wide default refuses it.

Run: python3 e4test.py   (exit 1 on any failure)
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


class ChainBrain:
    """A scripted brain keyed by goal text: each goal has its own
    action script. Records (goal, history, offered tool names) for
    every call so tests can prove order, handoffs and subsets."""

    DIE = object()

    def __init__(self, scripts):
        self.scripts = {g: list(a) for g, a in scripts.items()}
        self.seen = []

    def __call__(self, goal, history, tools, observation=None):
        self.seen.append((goal, [dict(h) for h in history],
                          [t["name"] for t in tools]))
        s = self.scripts.get(goal)
        if s:
            a = s.pop(0)
            if a is ChainBrain.DIE:
                raise RunnerDied("killed between steps")
            return a
        return {"action": "fail", "reason": f"no script for goal {goal!r}"}

    def goals_seen(self):
        out = []
        for g, _, _ in self.seen:
            if not out or out[-1] != g:
                out.append(g)
        return out

    def first_history(self, goal):
        for g, h, _ in self.seen:
            if g == goal:
                return h
        return None


def no_stop():
    return False


def counted_tool(name, counts, mutating=False, needs_allow=False):
    def run(args):
        counts[name] = counts.get(name, 0) + 1
        return True, f"{name} result"
    return {"name": name, "desc": name, "run": run,
            "mutating": mutating, "needs_allow": needs_allow}


def chain_job(entries, goals):
    return {"state": "running", "provider": "agent",
            "task": "chain job", "steps": entries,
            "chain": agent_loop.make_chain(goals)}


# ------------------------------------------------- (a) 3 goals end-to-end
counts = {}
tools = [counted_tool(n, counts) for n in ("t1", "t2", "t3")]
entries = []
job = chain_job(entries, ["first goal", "second goal", "third goal"])
brain = ChainBrain({
    "first goal": [{"action": "tool", "tool": "t1", "args": {}},
                   {"action": "done", "answer": "answer one"}],
    "second goal": [{"action": "tool", "tool": "t2", "args": {}},
                    {"action": "done", "answer": "answer two"}],
    "third goal": [{"action": "tool", "tool": "t3", "args": {}},
                   {"action": "done", "answer": "answer three"}],
})
status, out = agent_loop.run_chain(job, tools, brain=brain,
                                   record=entries.append, stop=no_stop)
check("(a) the chain completes with the last goal's answer",
      status == "done" and out == "answer three", f"{status} {out}")
check("(a) goals ran in order, each exactly its own run",
      brain.goals_seen() == ["first goal", "second goal", "third goal"],
      f"{brain.goals_seen()}")
check("(a) every tool executed exactly once",
      counts == {"t1": 1, "t2": 1, "t3": 1}, f"{counts}")
h2 = brain.first_history("second goal")
check("(a) goal 2's brain was seeded with goal 1's handoff",
      h2 is not None and len(h2) == 1 and h2[0]["action"] == "handoff"
      and "Completed goal: first goal" in h2[0]["result"]
      and "t1" in h2[0]["result"] and "t1 result" in h2[0]["result"]
      and "Final answer: answer one" in h2[0]["result"], f"{h2}")
h3 = brain.first_history("third goal")
check("(a) goal 3's brain was seeded with BOTH previous handoffs",
      h3 is not None and len(h3) == 2
      and "Final answer: answer one" in h3[0]["result"]
      and "Final answer: answer two" in h3[1]["result"], f"{h3}")
st = agent_loop.chain_state(job)
check("(a) chain state on the record reads done, index 3, 3 handoffs",
      st is not None and st["status"] == "done" and st["index"] == 3
      and len(st["handoffs"]) == 3 and st["lastAnswer"] == "answer three",
      f"{st}")
check("(a) chain markers were recorded into steps[]",
      any(e.get("phase") == "chain" for e in entries), f"{entries[:2]}")
check("(a) chain markers never pollute step parsing",
      agent_loop.parse_recorded_steps(entries)["last_n"] == 6,
      f"{agent_loop.parse_recorded_steps(entries)}")

# ----------------------------------------------------- (b) goal 2 fails
counts = {}
tools = [counted_tool(n, counts) for n in ("t1", "t2", "t3")]
entries = []
job = chain_job(entries, ["first goal", "second goal", "third goal"])
brain = ChainBrain({
    "first goal": [{"action": "tool", "tool": "t1", "args": {}},
                   {"action": "done", "answer": "answer one"}],
    "second goal": [{"action": "fail", "reason": "goal two broke"}],
    "third goal": [{"action": "done", "answer": "must never run"}],
})
status, out = agent_loop.run_chain(job, tools, brain=brain,
                                   record=entries.append, stop=no_stop)
check("(b) the chain reports the goal's failure",
      status == "failed" and "goal two broke" in out, f"{status} {out}")
check("(b) goal 3 never started",
      brain.goals_seen() == ["first goal", "second goal"]
      and counts.get("t3", 0) == 0, f"{brain.goals_seen()} {counts}")
st = agent_loop.chain_state(job)
check("(b) chain state records the halt + reason",
      st is not None and st["status"] == "halted" and st["index"] == 1
      and "goal 2" in st["haltReason"] and "goal two broke" in st["haltReason"],
      f"{st}")
calls_before = len(brain.seen)
status2, out2 = agent_loop.run_chain(job, tools, brain=brain,
                                     record=entries.append, stop=no_stop)
check("(b) a halted chain is terminal — no auto-retry on re-run",
      status2 == "terminal" and len(brain.seen) == calls_before,
      f"{status2} calls {calls_before}->{len(brain.seen)}")

# ---------------------------------------------------- (c) stop in goal 2
counts = {}
flag = {"stop": False}


def arm_stop(args):
    counts["arm"] = counts.get("arm", 0) + 1
    flag["stop"] = True
    return True, "stop armed"


tools = [counted_tool("t1", counts),
         {"name": "arm", "desc": "arm", "run": arm_stop},
         counted_tool("t3", counts)]
entries = []
job = chain_job(entries, ["first goal", "second goal", "third goal"])
brain = ChainBrain({
    "first goal": [{"action": "tool", "tool": "t1", "args": {}},
                   {"action": "done", "answer": "answer one"}],
    "second goal": [{"action": "tool", "tool": "arm", "args": {}},
                    {"action": "done", "answer": "must never be reached"}],
    "third goal": [{"action": "done", "answer": "must never run"}],
})
status, out = agent_loop.run_chain(job, tools, brain=brain,
                                   record=entries.append,
                                   stop=lambda: flag["stop"])
check("(c) the chain halts as stopped",
      status == "stopped", f"{status} {out}")
check("(c) goal 3 never started, goal 2's step ran once",
      brain.goals_seen() == ["first goal", "second goal"]
      and counts == {"t1": 1, "arm": 1}, f"{brain.goals_seen()} {counts}")
st = agent_loop.chain_state(job)
check("(c) chain state records the stop halt + reason",
      st is not None and st["status"] == "halted"
      and "stopped" in st["haltReason"] and "goal 2" in st["haltReason"],
      f"{st}")

# ------------------------------------------------------------ (d) cap
counts = {}
tools = [counted_tool("only", counts)]
entries = []
goals = [f"goal {i}" for i in range(1, 5)]
job = chain_job(entries, goals)
brain = ChainBrain({g: [{"action": "done", "answer": f"done {g}"}]
                    for g in goals})
status, out = agent_loop.run_chain(job, tools, brain=brain,
                                   record=entries.append, stop=no_stop,
                                   max_goals=2)
check("(d) the cap halts the chain as a failure with the reason",
      status == "failed" and "cap" in out, f"{status} {out}")
check("(d) exactly 2 goals ran; goals 3-4 never started",
      brain.goals_seen() == ["goal 1", "goal 2"], f"{brain.goals_seen()}")
st = agent_loop.chain_state(job)
check("(d) chain state records the cap halt at index 2",
      st is not None and st["status"] == "halted" and st["index"] == 2
      and "cap" in st["haltReason"], f"{st}")

# ------------------------------------------- (e) kill mid-goal-2 + resume
counts = {}
tools = [counted_tool(n, counts) for n in ("a", "b", "c", "d")]
entries = []
goals = ["first goal", "second goal", "third goal"]
job = chain_job(entries, goals)
brain1 = ChainBrain({
    "first goal": [{"action": "tool", "tool": "a", "args": {}},
                   {"action": "done", "answer": "one done"}],
    "second goal": [{"action": "tool", "tool": "b", "args": {}},
                    ChainBrain.DIE],
    "third goal": [{"action": "done", "answer": "unreached"}],
})
try:
    agent_loop.run_chain(job, tools, brain=brain1,
                         record=entries.append, stop=no_stop)
    died = False
except RunnerDied:
    died = True
check("(e) the first runner died mid-goal-2", died)
check("(e) before the kill: goal 1 + goal 2's first step ran once each",
      counts == {"a": 1, "b": 1}, f"{counts}")
st = agent_loop.chain_state(job)
check("(e) the record preserves the chain position (index 1, running)",
      st is not None and st["index"] == 1 and st["status"] == "running"
      and len(st["handoffs"]) == 1, f"{st}")

job2 = chain_job(entries, goals)  # fresh record view over the same steps
brain2 = ChainBrain({
    "second goal": [{"action": "tool", "tool": "c", "args": {}},
                    {"action": "done", "answer": "two done"}],
    "third goal": [{"action": "tool", "tool": "d", "args": {}},
                   {"action": "done", "answer": "three done"}],
})
status, out = agent_loop.run_chain(job2, tools, brain=brain2,
                                   record=entries.append, stop=no_stop)
check("(e) the resumed chain completes end-to-end",
      status == "done" and out == "three done", f"{status} {out}")
check("(e) NO completed step was re-executed across the resume",
      counts == {"a": 1, "b": 1, "c": 1, "d": 1}, f"{counts}")
check("(e) goal 1 was never re-run on resume",
      brain2.goals_seen() == ["second goal", "third goal"],
      f"{brain2.goals_seen()}")
h = brain2.first_history("second goal")
check("(e) resumed goal 2 sees goal 1's handoff AND its own recorded step",
      h is not None and len(h) == 2 and h[0]["action"] == "handoff"
      and "Final answer: one done" in h[0]["result"]
      and h[1]["action"] == "b" and h[1]["result"] == "ok: b result",
      f"{h}")
st = agent_loop.chain_state(job2)
check("(e) final chain state: done, index 3, 3 handoffs",
      st is not None and st["status"] == "done" and st["index"] == 3
      and len(st["handoffs"]) == 3, f"{st}")

# --------------------------------------- (f) goal tool subset + Allow
counts = {}
tools = [counted_tool("reader", counts),
         counted_tool("writer", counts, mutating=True, needs_allow=True),
         counted_tool("other", counts)]
entries = []
job = chain_job(entries, [
    {"goal": "open goal"},
    {"goal": "narrow goal", "tools": ["reader", "writer"],
     "allow": ["writer"]},
])
brain = ChainBrain({
    "open goal": [{"action": "tool", "tool": "writer", "args": {}},
                  {"action": "done", "answer": "open done"}],
    "narrow goal": [{"action": "tool", "tool": "writer", "args": {}},
                    {"action": "done", "answer": "narrow done"}],
})
status, out = agent_loop.run_chain(job, tools, brain=brain,
                                   record=entries.append, stop=no_stop)
check("(f) the chain completes", status == "done" and out == "narrow done",
      f"{status} {out}")
open_hist = [h for g, h, _ in brain.seen if g == "open goal"]
check("(f) without a goal Allow the needs_allow call was REFUSED, not run",
      counts.get("writer", 0) == 1
      and any("REFUSED" in h2.get("result", "")
              for h in open_hist for h2 in h), f"{counts} {open_hist}")
offered = {g: t for g, _, t in brain.seen}
check("(f) the narrow goal's brain was offered ONLY its subset",
      offered.get("narrow goal") == ["reader", "writer"]
      and offered.get("open goal") == ["reader", "writer", "other"],
      f"{offered}")
check("(f) with the goal Allow the writer ran exactly once",
      counts.get("writer") == 1, f"{counts}")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
sys.exit(1 if FAIL else 0)
