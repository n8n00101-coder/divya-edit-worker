"""e56test.py — E5+E6 rig for the Julie agent engine.

Drives agent_loop with SCRIPTED FAKE BRAINS (no model, no network)
and an in-memory step record standing in for the job record's
steps[] — the same list the Worker persists via agentsteps.

Cases (the E5+E6 acceptance gate):
  (a) E5 stop mid-tool: a stop landing while a cancel-declaring
      tool runs signals its cancel hook and halts the loop —
      zero further brain/tool calls after the halt, the chain
      marks itself halted-stopped with the reason recorded.
  (b) E5 status-from-real-state: build_job_status output matches
      a hand-built record EXACTLY (counts, current goal, last
      result); an empty record yields the plain no-data status.
  (c) E6 instruction loading: the core / repo / job layers load
      in order and reach the brain's system context (captured by
      the scripted brain); the manifest lands on the job dict;
      an E1-signature brain is called exactly as before.
  (d) E6 done gate: a done claim with missing evidence is fed
      back as a FAILED verification step naming the gap; the
      brain produces the missing step; the second done passes.
  (e) E6 done gate: a done claim that never produces evidence
      ends the run UNVERIFIED after 2 failed verifications, with
      the gap recorded on the record.
  (f) E6 chain wiring: a chain goal's declared evidence gates
      its done claim; an unverified goal halts the chain and the
      next goal never starts.

Run: python3 e56test.py   (exit 1 on any failure)
"""

import hashlib
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _v in ("WORKER_URL", "RUNNER_KEY", "JOB"):
    os.environ.pop(_v, None)

import agent_loop
import engine_instructions
import tools_registry

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


class ScriptBrain:
    """A scripted brain (e1test pattern): pops the next scripted
    action per call and records every history it was shown."""

    def __init__(self, script):
        self.script = list(script)
        self.histories = []
        self.calls = 0

    def __call__(self, goal, history, tools, observation=None):
        self.calls += 1
        self.histories.append([dict(h) for h in history])
        if self.script:
            return self.script.pop(0)
        return {"action": "fail", "reason": "script exhausted"}


class InstrBrain(ScriptBrain):
    """A brain on the E6 contract: accepts the loop's operating
    instructions and captures them per call."""

    def __init__(self, script):
        super().__init__(script)
        self.instructions_seen = []

    def __call__(self, goal, history, tools, observation=None,
                 instructions=None):
        self.instructions_seen.append(instructions)
        return super().__call__(goal, history, tools, observation)


def no_stop():
    return False


def counted_tool(name, counts, result=None):
    def run(args):
        counts[name] = counts.get(name, 0) + 1
        return True, result if result is not None else f"{name} result"
    return {"name": name, "desc": name, "run": run}


# ------------------------------------------- (a) stop mid-tool + chain
class SlowTool:
    """A cooperative tool: blocks until its cancel hook fires."""

    def __init__(self):
        self.started = threading.Event()
        self._cancel = threading.Event()
        self.runs = 0
        self.cancels = 0

    def run(self, args):
        self.runs += 1
        self.started.set()
        self._cancel.wait(10)
        return True, "slow tool wound down"

    def cancel(self):
        self.cancels += 1
        self._cancel.set()


slow = SlowTool()
reg = tools_registry.Registry()
reg.register("slow", "Blocks until cancelled. Rig tool.", {},
             slow.run, cancel=slow.cancel)
reg.register("other", "Instant tool. Rig tool.", {},
             lambda a: (True, "other result"))
tools_a = reg.as_tools()
check("(a) the registry carries the cancel hook into as_tools()",
      callable({t["name"]: t for t in tools_a}["slow"].get("cancel"))
      and "cancel" not in {t["name"]: t for t in tools_a}["other"],
      f"{tools_a}")

entries_a = []
job_a = {"state": "running", "provider": "agent", "task": "chain job",
         "steps": entries_a,
         "chain": agent_loop.make_chain(["slow goal", "later goal"])}


class ChainBrainA:
    def __init__(self):
        self.seen = []

    def __call__(self, goal, history, tools, observation=None):
        self.seen.append(goal)
        if goal == "slow goal":
            return {"action": "tool", "tool": "slow", "args": {}}
        return {"action": "done", "answer": "must never be reached"}


brain_a = ChainBrainA()
status, out = agent_loop.run_chain(
    job_a, tools_a, brain=brain_a, record=entries_a.append,
    stop=lambda: slow.started.is_set())
check("(a) a stop landing mid-tool halts the chain run as stopped",
      status == "stopped", f"{status} {out}")
check("(a) the tool's cancel hook was signalled exactly once",
      slow.cancels == 1, f"cancels={slow.cancels}")
check("(a) zero further brain calls after the halt (1 total)",
      len(brain_a.seen) == 1 and brain_a.seen[0] == "slow goal",
      f"{brain_a.seen}")
check("(a) the tool ran exactly once; the later goal never started",
      slow.runs == 1, f"runs={slow.runs}")
check("(a) the interrupted step is recorded as a stopped failure",
      any(e.get("tool") == "slow" and e.get("ok") is False
          and "STOPPED mid-step" in str(e.get("result") or "")
          for e in entries_a), f"{entries_a}")
check("(a) the halt itself is recorded as a stopped entry",
      any(e.get("tool") == "stopped" for e in entries_a), f"{entries_a}")
st_a = agent_loop.chain_state(job_a)
check("(a) the chain is marked halted-stopped with the reason",
      st_a is not None and st_a["status"] == "halted"
      and "stopped" in st_a["haltReason"] and "goal 1" in st_a["haltReason"],
      f"{st_a}")

# --------------------------------------------- (b) status from record
job_b = {
    "state": "running", "provider": "agent", "task": "status job",
    "steps": [
        {"n": 1, "tool": "reader", "arg": "", "ok": True,
         "result": "form visible", "at": 1000},
        {"n": 2, "tool": "writer", "arg": "", "ok": False,
         "result": "boom", "at": 2000},
        {"n": 3, "tool": "writer", "arg": "", "ok": True,
         "result": "saved file report.txt", "at": 3000},
        {"n": 4, "tool": "reader", "arg": "", "ok": False,
         "result": "", "phase": "started", "at": 4000},
    ],
    "chain": {"goals": [{"goal": "first goal"}, {"goal": "second goal"},
                        {"goal": "third goal"}],
              "index": 1, "status": "running", "haltReason": "",
              "goalStartN": 0, "handoffs": ["handoff one"],
              "lastAnswer": "answer one"},
}
expected_b = {
    "has_data": True,
    "state": "running",
    "terminal": None,
    "goal": "second goal",
    "steps": {"recorded": 4, "completed": 3, "ok": 2, "failed": 1,
              "inflight": 1},
    "last_step": {"n": 3, "tool": "writer", "ok": True,
                  "result": "saved file report.txt", "at": 3000},
    "chain": {"status": "running", "index": 1, "total": 3,
              "completed": 1, "halt_reason": ""},
    "first_at": 1000,
    "last_at": 4000,
}
got_b = agent_loop.build_job_status(job_b)
check("(b) status matches the hand-built record EXACTLY",
      got_b == expected_b, f"{got_b}")
text_b = agent_loop.format_job_status(job_b)
check("(b) formatted status carries the record's facts, no percentages",
      "second goal" in text_b and "2 ok, 1 failed" in text_b
      and "saved file report.txt" in text_b and "%" not in text_b,
      text_b)
check("(b) an empty record is a plain no-data status",
      agent_loop.build_job_status({}) == {"has_data": False}
      and agent_loop.build_job_status(None) == {"has_data": False}
      and agent_loop.format_job_status({})
      == "No job data recorded yet — there is nothing to report.")

# --------------------------------------- (c) instruction layers load
JOB_INSTR = "JOB-LAYER-MARKER: always log the receipt id."
entries_c = []
job_c = {"state": "running", "provider": "agent", "task": "layered job",
         "instructions": JOB_INSTR, "steps": entries_c}
counts_c = {}
echo_c = counted_tool("echo", counts_c)
brain_c = InstrBrain([
    {"action": "tool", "tool": "echo", "args": {}},
    {"action": "done", "answer": "layered done"},
])
status, out = agent_loop.run_agent_job(job_c, [echo_c], brain=brain_c,
                                       record=entries_c.append,
                                       stop=no_stop)
check("(c) the job completes", status == "done" and out == "layered done",
      f"{status} {out}")
seen_c = brain_c.instructions_seen
check("(c) instructions reached the brain on EVERY call",
      len(seen_c) == 2 and all(isinstance(s, str) and s for s in seen_c),
      f"{len(seen_c)}")
text_c = seen_c[0] if seen_c else ""
i_core = text_c.find("[ENGINE INSTRUCTIONS — core]")
i_repo = text_c.find("[ENGINE INSTRUCTIONS — repo: CLAUDE.md]")
i_job = text_c.find("[ENGINE INSTRUCTIONS — job]")
check("(c) layers load in core -> repo -> job order",
      -1 < i_core < i_repo < i_job, f"{i_core} {i_repo} {i_job}")
check("(c) each layer's content is present (core method, repo file, job text)",
      "Never claim done without evidence" in text_c
      and "worker laws" in text_c and JOB_INSTR in text_c)
man_c = job_c.get("instructionsLoaded") or []
check("(c) the manifest is stamped on the job dict, layers in order",
      [m["layer"] for m in man_c] == ["core", "repo", "job"]
      and all(m["loaded"] for m in man_c)
      and all(len(m["sha256"]) == 64 for m in man_c), f"{man_c}")
check("(c) the job layer's manifest hash is the job text's sha256",
      man_c and man_c[2]["sha256"]
      == hashlib.sha256(JOB_INSTR.encode("utf-8")).hexdigest())
_, man_missing = engine_instructions.load_instructions(
    job=None, repo_root="/nonexistent-dir-e56")
check("(c) a missing repo file is recorded in the manifest, not silent",
      man_missing[1]["layer"] == "repo" and man_missing[1]["loaded"] is False
      and [m["layer"] for m in man_missing] == ["core", "repo"],
      f"{man_missing}")
entries_c2 = []
brain_c2 = ScriptBrain([{"action": "done", "answer": "plain done"}])
status, out = agent_loop.run_loop("plain job", [echo_c], brain=brain_c2,
                                  record=entries_c2.append, stop=no_stop,
                                  instructions="EXPLICIT TEXT")
check("(c) an E1-signature brain is called exactly as before (no kwarg crash)",
      status == "done" and out == "plain done", f"{status} {out}")

# --------------------------------- (d) done gate: fail, complete, pass
counts_d = {}
fetch_d = counted_tool("fetch", counts_d, result="fetched the page")
save_d = counted_tool("save", counts_d, result="saved artifact report.txt")
entries_d = []
brain_d = ScriptBrain([
    {"action": "tool", "tool": "fetch", "args": {}},
    {"action": "done", "answer": "all done"},               # gate: no save yet
    {"action": "tool", "tool": "save", "args": {}},
    {"action": "done", "answer": "saved and done"},
])
status, out = agent_loop.run_loop(
    "fetch then save", [fetch_d, save_d], brain=brain_d,
    record=entries_d.append, stop=no_stop,
    evidence=[{"tool": "save", "contains": "report.txt"}])
check("(d) after producing the missing evidence, done is accepted",
      status == "done" and out == "saved and done", f"{status} {out}")
check("(d) each tool ran exactly once",
      counts_d == {"fetch": 1, "save": 1}, f"{counts_d}")
ver_d = [e for e in entries_d if e.get("tool") == "verify"]
check("(d) the rejected claim was recorded as a FAILED verification step",
      len(ver_d) == 1 and ver_d[0]["ok"] is False
      and "missing evidence" in ver_d[0]["result"]
      and "save" in ver_d[0]["result"], f"{entries_d}")
check("(d) the gap was fed back to the brain as FAILED history",
      any(h.get("action") == "verify"
          and h.get("result", "").startswith("FAILED:")
          and "save" in h.get("result", "")
          for h in brain_d.histories[2]), f"{brain_d.histories}")

# ------------------------------------- (e) done gate: never -> UNVERIFIED
counts_e = {}
save_e = counted_tool("save", counts_e)
entries_e = []
brain_e = ScriptBrain([
    {"action": "done", "answer": "done, trust me"},
    {"action": "done", "answer": "really done"},
    {"action": "done", "answer": "must never be asked"},
])
status, out = agent_loop.run_loop(
    "save the thing", [save_e], brain=brain_e,
    record=entries_e.append, stop=no_stop, evidence=["save"])
check("(e) the run ends UNVERIFIED after 2 failed verifications",
      status == "unverified" and "UNVERIFIED" in out and "save" in out,
      f"{status} {out}")
check("(e) the brain was asked exactly twice — no third claim is heard",
      brain_e.calls == 2, f"{brain_e.calls}")
check("(e) the evidence tool never ran (the claim was never backed)",
      counts_e == {}, f"{counts_e}")
ver_e = [e for e in entries_e if e.get("tool") == "verify"]
unv_e = [e for e in entries_e if e.get("tool") == "unverified"]
check("(e) the record shows 2 verification failures + the unverified end",
      len(ver_e) == 2 and len(unv_e) == 1 and unv_e[0]["ok"] is False
      and "save" in unv_e[0]["result"], f"{entries_e}")
job_e = {"state": "running", "provider": "agent", "task": "save the thing",
         "steps": entries_e}
check("(e) the record reads terminal-unverified (not resumable, not done)",
      agent_loop.job_terminal(job_e) == "unverified"
      and not agent_loop.is_resumable(job_e))

# ------------------------------------- (f) chain goal evidence wiring
counts_f = {}
save_f = counted_tool("save", counts_f)
entries_f = []
job_f = {"state": "running", "provider": "agent", "task": "chain job",
         "steps": entries_f,
         "chain": agent_loop.make_chain([
             {"goal": "gated goal", "evidence": ["save"]},
             {"goal": "later goal"},
         ])}


class ChainBrainF:
    def __init__(self):
        self.seen = []

    def __call__(self, goal, history, tools, observation=None):
        self.seen.append(goal)
        return {"action": "done", "answer": f"claimed {goal}"}


brain_f = ChainBrainF()
status, out = agent_loop.run_chain(job_f, [save_f], brain=brain_f,
                                   record=entries_f.append, stop=no_stop)
check("(f) a goal whose done claim lacks evidence ends the chain UNVERIFIED",
      status == "unverified", f"{status} {out}")
check("(f) the later goal never started",
      brain_f.seen == ["gated goal", "gated goal"], f"{brain_f.seen}")
st_f = agent_loop.chain_state(job_f)
check("(f) the chain records the unverified halt + reason",
      st_f is not None and st_f["status"] == "halted"
      and "unverified" in st_f["haltReason"] and "goal 1" in st_f["haltReason"],
      f"{st_f}")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
sys.exit(1 if FAIL else 0)
