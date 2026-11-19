"""Julie agent engine (E1): the GENERAL agent loop.

Until now Julie had exactly ONE real agent loop — browse.py's
browser loop (page snapshot -> Worker brainstep -> one JSON action ->
execute -> observe -> replan). Everything else is a scripted pipeline
or a per-provider driver. This module is that loop, generalized:
browse's pattern lifted out of the browser so ANY job type can run as

    goal -> ask the brain for ONE step -> execute it via a tool ->
    record the step + result on the job record -> observe -> repeat

until the brain declares done (with an answer built only from results
it was actually shown), the brain fails the task honestly, the user
stops the job, or the step budget runs out. A tool that FAILS is not
fatal: the failure is fed back to the brain as history and the brain
replans — exactly the browse discipline.

Shape (mirrors browse.py): the runner is the HANDS, the Worker is the
BRAIN. The default brain is POST /api/setup/runner/agentstep — the
general sibling of brainstep, on the same runner-key channel, running
through the job owner's normal chat chain (chatWithFallback), so keys
never leave the Worker and NO model/provider routing lives here
(providers.py / channel.py are untouched by design). The default step
recorder is POST /api/setup/runner/agentsteps, which appends each step
to the job record's steps[] array (the setupjob:<id> record — the same
record shape browse/setup jobs already use), so a later phase (E3) can
resume a job from its record instead of restarting it.

The loop itself is dependency-injected (brain / record / stop are
callables) so rigs can drive it with a scripted fake brain — see
e1test.py. INTEGRATION (the engine program's final phase) wired it
into production dispatch for AGENT jobs only: POST /api/agent
creates a setupjob record with provider "agent", agent.yml runs
agent_runner.py, and that runner claims the job and executes it
through run_agent_job / resume_trigger below. browse.py, setup.py
and the video pipelines keep their current behaviour — no existing
flow routes through this loop.

E3 (persistence + resume) builds on the steps[] record: a runner is
ephemeral, the record is not. With record_started on, the loop writes
a {"phase": "started"} entry BEFORE a tool handler runs and the usual
completion entry after it, so the record distinguishes three states
per step: completed (a result exists), never started, and STARTED
BUT UNFINISHED — a step whose runner died mid-flight, whose effect is
therefore UNKNOWN. resume_loop() rebuilds the brain's history from
the record (completed steps, FAILED ones included, become history
exactly as the original brain saw them; an unfinished step becomes
an explicit UNKNOWN history entry), continues step numbering from
the record, and never replays a completed step itself. For an
unfinished MUTATING step the loop additionally enforces verify-first
mechanically: mutating calls are refused until a read-only tool has
completed, so the brain must look before it redoes. See e3test.py.

E4 (chain continuation) generalizes the hand-off the setup chain
hard-codes between provider jobs: a job record may carry a CHAIN of
goals (job["chain"]); when one goal's loop finishes DONE, run_chain
starts the next goal itself — no human re-asking — seeding the new
goal's brain with a compact handoff built from the finished goal's
recorded steps (what was done + its final answer), never the raw
transcript. A FAILED or STOPPED goal HALTS the chain with the reason
recorded on the chain state; later goals never start, and there is
no auto-retry. A chain runs at most MAX_CHAIN_GOALS goals. Chain
state is mirrored into steps[] as {"phase": "chain"} markers through
the same recorder, so a fresh runner reconstructs the chain from the
record alone and resumes the CURRENT goal under E3's rules (chain
position preserved). Agent jobs only — the existing setup chain in
divya.js and every production flow are untouched. See e4test.py.

E5 (stop + status mechanics) hardens the two promises the loop
already made informally. STOP: the stop flag the runner already
polls (the job record's state, via worker_stop — the same read
setup.get_job / browse use) is now also polled WHILE a tool runs,
for tools that declare cooperative cancellation (a "cancel"
callable on the tool dict, carried through tools_registry): when a
stop lands mid-tool the loop signals the tool's cancel hook, waits
a short grace for it to wind down, records the interrupted step,
and halts — no further brain calls, no further steps, and a chain
(E4) marks itself halted-stopped from the returned status. Tools
without a cancel hook keep the E1 behaviour exactly: synchronous
execution, stop honoured at the checkpoint before the next step.
STATUS: build_job_status() / format_job_status() answer "what is
this job doing, how far has it got, what remains" from the job
RECORD alone — step counts from steps[], chain position from the
chain state, the last recorded result — with no model call and no
invented percentages; a record without data says so plainly.

E6 (instruction loading + done-evidence gate) gives the loop the
two Claude Code habits it lacked. INSTRUCTIONS: at job start the
loop loads its operating instructions through engine_instructions
(core working method -> repo CLAUDE.md -> job-attached text) and
hands them to the brain as its system context on every agentstep
call (worker_brain sends them as the payload's instructions
field); the manifest of what loaded is stamped on the job dict as
instructionsLoaded. DONE-EVIDENCE GATE: when a goal declares
evidence requirements (run_loop's evidence arg, a chain goal's
"evidence", or job["evidence"]), a done claim is VERIFIED against
the recorded steps before it is accepted — every declared check
must have a recorded OK result. A claim that fails is fed back to
the brain as a FAILED verification step naming the exact gap;
after MAX_DONE_VERIFY_FAILURES failed verifications the run ends
UNVERIFIED — an honest terminal state, not done and not a silent
fail — with the gap recorded on the record. With no declared
requirements, done behaves exactly as E1 specified. See e56test.py.

E7 (deterministic compute + verify) closes the hole parity test
v1 exposed: the E6 gate proved a declared artifact EXISTED, not
that its contents were RIGHT, and the model computed the facts
itself — wrongly. A requirement may now be verify-style:
{"tool": "verify_file_contains", "args": {...}} — the gate then
passes only when a recorded OK step from that exact tool, with
args matching the requirement's args, exists AFTER the last
recorded OK write to the artifact the args name (their "path"):
verifying an earlier version of the file, or a FAILED verify,
never satisfies it. Plain tool / tool+contains requirements keep
their E6 meaning unchanged. The verify tools themselves live in
compute_tools.py (with compute_csv, the exact-arithmetic fact
computer). See e7test.py.

E8 (evidence auto-close) closes the third failure parity test v2
exposed: Julie's own verify PASSED and the brain still did not
declare done — it wandered into the step limit and the finished
job was scored a failure. When evidence requirements are declared,
they ARE the goal's definition of done, so the loop now checks
them after EVERY completed step: the moment every requirement is
satisfied by the recorded steps, the loop ends the run as DONE
itself — a terminal record entry stating "evidence complete —
auto-closed" plus a summary of the final step (the brain gave no
answer; it never declared done) — without another brain call.
The brain can still declare done earlier (the E6 gate path is
unchanged), and with no evidence declared the loop behaves
exactly as E1 specified. run_chain treats an auto-closed DONE
like any DONE: the handoff is built from the recorded steps and
the chain continues. See e8test.py.

Tool contract: a tool is a dict {"name": str, "desc": str,
"run": callable}. Since E2 the canonical source of tool dicts is
tools_registry.py (a Registry's as_tools()): entries there also
carry "schema" (args are validated before the handler runs),
"mutating" and "needs_allow". A tool marked needs_allow (a
mutating / external action) runs ONLY when the loop's caller passes
an Allow for it — otherwise the call is REFUSED as a FAILED step fed
back to the brain; it is never executed silently. run(args: dict)
may return:
  - (ok: bool, result: str) tuple,
  - {"ok": bool, "result": str} dict,
  - a plain str (ok=True),
  - None (ok=True, empty result),
or raise — an exception becomes a FAILED step whose message is fed
back to the brain, never a dead loop.

Honesty rules (Ajju's standing orders, same as browse.py):
- done is accepted ONLY with a non-empty answer; an empty done is
  rejected back to the brain, never reported as success.
- When the budget is exhausted the loop returns an honest failure —
  there is no fake "done".
- Step results are recorded on the job record as they happen, so the
  status anyone reads is the real state of the job.
"""
import inspect
import json
import os
import threading
import time

import httpx

import engine_instructions

MAX_STEPS = 40        # same step budget as browse.py
HISTORY_WINDOW = 8    # brainstep/agentstep both see the last 8 steps
RESULT_CAP = 600      # chars of one tool result recorded / fed back
CANCEL_GRACE_S = 3    # E5: after signalling a tool's cancel hook, how
                      # long the loop waits for it to wind down before
                      # halting anyway (its late result is discarded)
MAX_DONE_VERIFY_FAILURES = 2   # E6: failed done-verifications tolerated
                               # before the run ends UNVERIFIED


# ---------------------------------------------------------------- plumbing
# Defaults talk to the Worker over the same env + runner-key channel
# setup.py uses (WORKER_URL / RUNNER_KEY / JOB). All best-effort in the
# setup.py discipline: a lost post is logged, never fatal; a failed
# read is "no signal", never a crash.

def _worker():
    return os.environ.get("WORKER_URL", "").rstrip("/")


def _headers():
    return {"x-runner-key": os.environ.get("RUNNER_KEY", "")}


def _job_id():
    return os.environ.get("JOB", "")


def worker_brain(goal, history, tools, observation=None, instructions=None):
    """Default brain: ask the Worker for the next action via
    /api/setup/runner/agentstep (agentstep is brainstep's general
    sibling). Returns the action dict, or None when the brain is
    unreachable / answered nothing usable — the loop then fails
    honestly, exactly like browse.brain_step. E6: the loop's loaded
    operating instructions ride along as the payload's
    "instructions" field — the brain's system context for the
    call."""
    worker = _worker()
    if not worker or not _job_id():
        return None
    offered = []
    for t in tools:
        o = {"name": t["name"], "desc": t.get("desc", "")}
        if isinstance(t.get("schema"), dict) and t["schema"]:
            o["schema"] = t["schema"]
        offered.append(o)
    payload = {
        "goal": goal,
        "history": history[-HISTORY_WINDOW:],
        "tools": offered,
    }
    if observation:
        payload["observation"] = observation
    if instructions:
        payload["instructions"] = instructions
    for attempt in range(2):
        try:
            r = httpx.post(f"{worker}/api/setup/runner/agentstep",
                           params={"job": _job_id()}, json=payload,
                           headers=_headers(), timeout=90)
            if r.status_code == 200:
                a = (r.json() or {}).get("action")
                if isinstance(a, dict) and a.get("action"):
                    return a
                print(f"agentstep: unusable reply (attempt {attempt + 1})", flush=True)
            else:
                print(f"agentstep HTTP {r.status_code} (attempt {attempt + 1})", flush=True)
        except Exception as e:
            print(f"agentstep failed (attempt {attempt + 1}):", e, flush=True)
        time.sleep(3)
    return None


def worker_record(entry):
    """Default step recorder: POST the step to
    /api/setup/runner/agentsteps — the Worker appends it to the job
    record's steps[] (capped there). Best-effort, like setup.progress:
    a failed post is logged and the loop continues."""
    worker = _worker()
    if not worker or not _job_id():
        return
    try:
        httpx.post(f"{worker}/api/setup/runner/agentsteps",
                   params={"job": _job_id()}, json={"step": entry},
                   headers=_headers(), timeout=20)
    except Exception as e:
        print("agentsteps record failed:", e, flush=True)


def worker_stop():
    """Default stop check: poll the job record through the runner job
    endpoint (the same GET setup.get_job uses) and report True when
    the user/app flipped the job to "stopped". Any fetch failure reads
    as not-stopped (browse discipline — a Worker blip must not kill a
    healthy run; the step budget bounds the loop)."""
    worker = _worker()
    if not worker or not _job_id():
        return False
    try:
        r = httpx.get(f"{worker}/api/setup/runner/job",
                      params={"job": _job_id()}, headers=_headers(), timeout=20)
        if r.status_code == 200:
            return (r.json().get("job") or {}).get("state") == "stopped"
    except Exception:
        pass
    return False


def fetch_job_state():
    """Read this job's own record via the runner channel. Returns the
    job dict, or None when unreachable. Read-only."""
    worker = _worker()
    if not worker or not _job_id():
        return None
    try:
        r = httpx.get(f"{worker}/api/setup/runner/job",
                      params={"job": _job_id()}, headers=_headers(), timeout=20)
        if r.status_code == 200:
            return r.json().get("job") or {}
    except Exception:
        pass
    return None


# ------------------------------------------------------------------- tools

def _tool_noop(args):
    return True, "noop — nothing done (stub tool)"


def _tool_echo(args):
    return True, str(args.get("text") or "")


PLAN_STEP_CAP = 8        # E10: max steps in one set_plan declaration
PLAN_TITLE_CAP = 40      # E10: max chars per plan step title
PLAN_STATUSES = ("pending", "in_progress", "done")


def _plan_from_result(result):
    """Parse the plan JSON a set_plan step recorded in its result
    (\"plan: [{...}]\"), or None. The record IS the persistence: a
    plan survives a dead runner because its set_plan step survives
    in steps[] / seed history."""
    text = str(result or "")
    if text.startswith("ok: "):
        text = text[4:]
    if not text.startswith("plan: "):
        return None
    try:
        plan = json.loads(text[len("plan: "):])
    except Exception:
        return None
    return plan if isinstance(plan, list) and plan else None


def _apply_set_plan(args, job):
    """E10 set_plan handler (registered by
    tools_registry.register_plan_tool, bound to one job record):
    the brain declares or replaces the job's plan — an ordered
    list of {title, status}.
    The normalized plan is stored on the job record dict (when the
    caller passed one) and returned as compact JSON in the step
    result, so the recorded step itself carries the plan across a
    kill+resume. Caps keep that JSON inside RESULT_CAP."""
    steps_in = args.get("steps")
    if not isinstance(steps_in, list) or not steps_in:
        return False, ("refused: set_plan needs a non-empty 'steps' "
                       "list of {title, status} items")
    if len(steps_in) > PLAN_STEP_CAP:
        return False, (f"refused: plan has {len(steps_in)} steps — "
                       f"the cap is {PLAN_STEP_CAP}; declare the "
                       f"current phase only")
    plan = []
    for item in steps_in:
        if isinstance(item, str):
            title, status = item, "pending"
        elif isinstance(item, dict):
            title = str(item.get("title") or "")
            status = str(item.get("status") or "pending")
        else:
            return False, ("refused: each plan step must be a string "
                           "or a {title, status} object")
        title = title.strip()[:PLAN_TITLE_CAP]
        if not title:
            return False, "refused: a plan step has an empty title"
        if status not in PLAN_STATUSES:
            return False, (f"refused: status {status!r} — one of "
                           f"{', '.join(PLAN_STATUSES)}")
        plan.append({"title": title, "status": status})
    if isinstance(job, dict):
        job["plan"] = plan
    return True, "plan: " + json.dumps(plan, ensure_ascii=False)


def _tool_job_state(args):
    """REAL read-only tool: this job's own record, read through the
    existing runner job endpoint (the same read setup.get_job does).
    Reports state/step/note/plan only — no writes, nothing sealed."""
    job = fetch_job_state()
    if job is None:
        return False, "job record unreachable via the runner channel"
    bits = [f"state={job.get('state') or '?'}",
            f"provider={job.get('provider') or '?'}"]
    if job.get("step"):
        bits.append(f"step={job['step']}")
    if job.get("note"):
        bits.append(f"note={str(job['note'])[:160]}")
    nsteps = len(job.get("steps") or [])
    bits.append(f"recorded steps={nsteps}")
    # E10: plan from the record — the plan field when present, else
    # reconstructed from the last recorded set_plan step.
    plan = job.get("plan")
    if not (isinstance(plan, (list, tuple)) and plan):
        plan = None
        for st in job.get("steps") or []:
            if (isinstance(st, dict) and st.get("tool") == "set_plan"
                    and st.get("ok")):
                plan = _plan_from_result(st.get("result")) or plan
    if isinstance(plan, (list, tuple)) and plan:
        def _fmt(p):
            if isinstance(p, dict):
                return f"[{p.get('status') or 'pending'}] {p.get('title') or ''}"
            return str(p)
        plan_lines = "\n".join(f"  - {_fmt(p)[:120]}" for p in plan[:10])
        bits.append(f"plan:\n{plan_lines}")
    return True, "; ".join(bits)


def default_tools():
    """The minimal E1 tool set: two stubs (noop/echo — they exist so
    rigs and smoke runs can exercise the loop with zero side effects)
    plus one real read-only tool (job_state). Real tool families
    (browser actions, file ops, render primitives) register in E2."""
    return [
        {"name": "noop", "desc": "Do nothing and report ok. Stub for smoke tests.",
         "run": _tool_noop},
        {"name": "echo", "desc": "Return the given text unchanged. Args: {text}. Stub.",
         "run": _tool_echo},
        {"name": "job_state", "desc": "Read this job's own record (state, current step, note, recorded step count, plan). Read-only, no side effects.",
         "run": _tool_job_state},
    ]


# -------------------------------------------------------------------- loop

def _arg_summary(action):
    args = action.get("args")
    if isinstance(args, dict):
        return json.dumps(args, ensure_ascii=False)[:200]
    return str(action.get("arg") or "")[:200]


def _normalize(res):
    """Normalize a tool handler's return to (ok, result_str)."""
    if isinstance(res, tuple) and len(res) == 2:
        return bool(res[0]), str(res[1] or "")
    if isinstance(res, dict):
        return bool(res.get("ok", True)), str(res.get("result") or "")
    if res is None:
        return True, ""
    return True, str(res)


def _allowed(allow, name, args):
    """The E2 Allow gate's decision for one needs_allow tool call.
    allow may be: True (everything allowed), a callable
    allow(name, args) -> bool (the job's Allow check), or a container
    of allowed tool names. Anything else — None included — means NOT
    allowed: an un-Allowed mutating call is refused by default, never
    run on silence. A broken Allow check also reads as not allowed."""
    if allow is True:
        return True
    if callable(allow):
        try:
            return bool(allow(name, args))
        except Exception:
            return False
    if isinstance(allow, (set, frozenset, list, tuple)):
        return name in allow
    return False


def _takes_instructions(fn):
    """True when a brain callable accepts the loop's E6 operating
    instructions (an "instructions" parameter, or **kwargs to carry
    it). Brains written against the E1 contract — (goal, history,
    tools, observation) — return False and are called exactly as
    before; worker_brain accepts the parameter and forwards the
    instructions as the agentstep payload's system context."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    if "instructions" in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD
               for p in params.values())


def _call_handler(tool, args):
    """Run one tool handler synchronously and normalize its outcome
    (a raise becomes a FAILED result, never a dead loop — the E1
    contract)."""
    try:
        return _normalize(tool["run"](args))
    except Exception as e:
        return False, f"{tool['name']} error: {str(e)[:RESULT_CAP]}"


def _call_handler_cancellable(tool, args, stop):
    """E5: run a cancel-declaring tool's handler on a daemon thread
    while polling the stop flag. Returns ("ok", ok, result) when
    the handler finishes on its own, or ("stopped", False, "") when
    a stop lands mid-run: the tool's cancel hook is then called
    (best-effort — signalling IS the cooperative contract) and the
    loop waits CANCEL_GRACE_S for the handler to wind down before
    halting regardless; a handler that ignores its hook may finish
    in the background, but its late result is discarded and never
    recorded as this step's result."""
    box = {}

    def _target():
        box["out"] = _call_handler(tool, args)

    th = threading.Thread(target=_target, daemon=True)
    th.start()
    while th.is_alive():
        th.join(0.05)
        if not th.is_alive():
            break
        try:
            stopped = bool(stop())
        except Exception:
            stopped = False   # a broken stop poll is "no signal"
        if stopped:
            try:
                tool["cancel"]()
            except Exception:
                pass
            th.join(CANCEL_GRACE_S)
            return "stopped", False, ""
    return "ok", box["out"][0], box["out"][1]


# ------------------------------------------------------- E6 done gate

def _norm_requirement(r):
    """Normalize one declared evidence requirement to
    {"tool": str, "contains": str, "args": ...}: a bare string
    names a tool that must have a recorded OK result; a dict may
    name "tool" and/or "contains" (a substring the OK result must
    contain — how a required artifact / check is declared). E7: a
    dict carrying "args" is a VERIFY-style requirement — its
    value rides along untouched (None when the key is absent) and
    _verify_gap interprets it."""
    if isinstance(r, str):
        return {"tool": r, "contains": "", "args": None}
    if isinstance(r, dict):
        return {"tool": str(r.get("tool") or ""),
                "contains": str(r.get("contains")
                                or r.get("result_contains") or ""),
                "args": (r.get("args") if "args" in r else None)}
    return {"tool": "", "contains": "", "args": None}


def _args_match(want, got):
    """Subset match for a verify-style requirement: every key/value
    the requirement declares must equal the recorded step's args
    (the step may carry more). Values compare with ==, so lists
    and dicts match structurally. A step whose args were never
    recorded (None — e.g. a seed-history entry) never matches."""
    if not isinstance(got, dict):
        return False
    return all(got.get(k) == v for k, v in want.items())


def _verify_gap(req, events):
    """E7: check one verify-style requirement against the recorded
    OK events (dicts {"tool", "args", "mutating", "seq"} in run
    order). Returns None when satisfied, else the gap description.

    Satisfied = an OK event from the requirement's tool whose args
    match the requirement's args AND whose seq is AFTER the last
    OK mutating event that wrote the artifact the args name
    (args["path"]) — so a verify of an earlier version of the
    file, or a FAILED verify (never an OK event), cannot pass the
    gate. When no write to the artifact is on record, any matching
    OK verify satisfies it (verifying a pre-existing file)."""
    want_args = req["args"]
    artifact = want_args.get("path")
    last_write = None
    if isinstance(artifact, str) and artifact:
        for ev in (events or []):
            ev_args = ev.get("args") or {}
            if ev.get("mutating") and ev_args.get("path") == artifact:
                if last_write is None or ev["seq"] > last_write:
                    last_write = ev["seq"]
    for ev in (events or []):
        if ev.get("tool") != req["tool"]:
            continue
        if not _args_match(want_args, ev.get("args")):
            continue
        if last_write is not None and ev["seq"] <= last_write:
            continue
        return None
    where = (f" after the last write to {artifact!r}"
             if last_write is not None else "")
    return (f"missing evidence: no recorded OK {req['tool']!r} step "
            f"with args {want_args!r}{where}")


def _evidence_gaps(requirements, ok_steps, events=None, job=None):
    """The done-evidence gate's check: for every declared
    requirement, is there a recorded OK step satisfying it?
    ok_steps is a list of (tool, result) pairs — the goal's seed
    history OK entries plus every OK step this run executed.
    events (E7) is the parallel list of OK event dicts carrying
    each step's args + mutating flag + sequence number, which
    verify-style requirements (a dict with "args") are checked
    against; plain requirements keep the E6 check on ok_steps.

    E10: Verify-after-edit gate — when evidence requirements are
    declared, the gate also checks that any mutating file operation
    (edit_file, file_write, file_append) on a file that EXISTED
    before the job's first write to it is followed by a verification
    step for that file (a file_read re-read, a verify_* tool naming
    it, or an OK run_command after the edit). A file the job itself
    created is not gated — creating outputs is the normal case the
    E7/E8 declared-evidence checks already cover.

    Returns the list of gap descriptions (empty = gate passes)."""
    gaps = []
    for r in (requirements or []):
        req = _norm_requirement(r)
        if req["args"] is not None:
            # E7 verify-style: the named tool must have verified,
            # with exactly these args, after the artifact's last
            # write. Content existence (E6) is not enough.
            if not isinstance(req["args"], dict):
                gaps.append("a verify-style evidence requirement "
                            "was declared with non-object args and "
                            "cannot be satisfied")
                continue
            if not req["tool"]:
                gaps.append("a verify-style evidence requirement "
                            "was declared without a tool name and "
                            "cannot be satisfied")
                continue
            gap = _verify_gap(req, events)
            if gap:
                gaps.append(gap)
            continue
        if not req["tool"] and not req["contains"]:
            gaps.append("an empty evidence requirement was declared "
                        "and cannot be satisfied")
            continue
        hit = any((not req["tool"] or t == req["tool"])
                  and (not req["contains"] or req["contains"] in res)
                  for t, res in ok_steps)
        if not hit:
            want = []
            if req["tool"]:
                want.append(f"a recorded OK result from tool {req['tool']!r}")
            if req["contains"]:
                want.append(f"a recorded OK result containing {req['contains']!r}")
            gaps.append("missing evidence: no " + " and ".join(want))

    # E10: Verify-after-edit gate (divya-fixed semantics).
    # Only edits of a PRE-EXISTING file are gated. Pre-existence is
    # decided, per file, by (in order):
    #   1. the workspace layer's record flag
    #      "_e10_file_existed_before_<path>" on the job dict — set by
    #      file_write/file_append at write time, when the registry
    #      was built with the same job record (the production path);
    #   2. inference from the run's own events: the file's first
    #      mutating op was edit_file (an edit can only land on an
    #      existing file), or an OK file_read / a compute/verify step
    #      naming the file precedes its first write — the file was
    #      provably there before the job touched it.
    # Seed-history events carry args=None, so they prove nothing —
    # a resumed run re-verifies in-run (the E7 convention).
    if requirements and events:
        mutating_file_tools = {"edit_file", "file_write", "file_append"}
        first_mut = {}   # path -> (seq, tool) of its first mutating op
        last_mut = {}    # path -> seq of its last mutating op
        proof = {}       # path -> earliest seq proving pre-existence
        for ev in events:
            tool = str(ev.get("tool") or "")
            args = ev.get("args") or {}
            path = args.get("path")
            if isinstance(path, str) and path:
                if tool in mutating_file_tools:
                    if path not in first_mut:
                        first_mut[path] = (ev.get("seq", 0), tool)
                    last_mut[path] = ev.get("seq", 0)
                elif tool == "file_read":
                    proof.setdefault(path, ev.get("seq", 0))
            src = args.get("source")
            if (isinstance(src, str) and src
                    and tool not in mutating_file_tools):
                proof.setdefault(src, ev.get("seq", 0))

        def _is_verify_for(ev, path, after_seq):
            if ev.get("seq", 0) <= after_seq:
                return False
            tool = str(ev.get("tool") or "")
            if tool == "run_command":
                # A command check has no path arg: an OK run after
                # the last edit is the verification (the brief's
                # "run the check after the change").
                return True
            if tool == "file_read" or tool.startswith("verify_"):
                eargs = ev.get("args") or {}
                return (eargs.get("path") == path
                        or eargs.get("output") == path)
            return False

        for path, mut_seq in last_mut.items():
            fseq, ftool = first_mut[path]
            flag = (job.get("_e10_file_existed_before_" + path)
                    if isinstance(job, dict) else None)
            if isinstance(flag, bool):
                existed = flag
            else:
                existed = (ftool == "edit_file"
                           or (path in proof and proof[path] < fseq))
            if not existed:
                continue
            if not any(_is_verify_for(ev, path, mut_seq)
                       for ev in events):
                gaps.append(
                    f"verify-after-edit: file {path!r} was modified by a "
                    f"mutating tool but no subsequent verification "
                    f"(file_read, a verify_* tool, or run_command) was "
                    f"recorded for it"
                )

    return gaps


def run_loop(goal, tools, brain=None, record=None, stop=None,
             max_steps=MAX_STEPS, deadline_s=None, observation=None,
             allow=None, seed_history=None, step_offset=0,
             verify_first_for=None, record_started=False,
             job=None, instructions=None, load_instructions=True,
             evidence=None):
    """Run the general agent loop.

    goal:        the task text (job-type agnostic).
    tools:       list of tool dicts (see module docstring).
    brain:       callable(goal, history, tools, observation) -> action
                 dict | None. Default: worker_brain (agentstep).
    record:      callable(entry) — persists one step entry. Default:
                 worker_record (job record steps[] via the Worker).
    stop:        callable() -> bool — checked at every step boundary
                 (the checkpoint between steps). Default: worker_stop.
    max_steps:   brain-decision budget (default MAX_STEPS=40, browse's).
                 Counts TOTAL steps including step_offset, so resuming
                 a job does not mint a fresh budget per runner.
    deadline_s:  optional wall-clock budget; None = no deadline.
    observation: optional extra context handed to the brain each step
                 (e.g. a page snapshot for browser-flavoured jobs).
    allow:       the E2 Allow grant for needs_allow tools — True, a
                 callable(name, args) -> bool, or a container of
                 allowed tool names. Default None = no Allow: a
                 needs_allow call is refused as a FAILED step (the
                 handler never runs) and the brain replans.
    seed_history: E3 — history entries rebuilt from a previous run's
                 job record (see build_resume_history); the brain
                 starts from exactly what the record proves happened.
    step_offset: E3 — step number the record already reached; new
                 entries continue from there, never reusing a number.
    verify_first_for: E3 — name of a step a previous runner started
                 but never finished (effect UNKNOWN). While set, any
                 mutating / needs_allow call is REFUSED as a FAILED
                 step until a read-only tool completes — the loop's
                 mechanical verify-before-redo guard.
    record_started: E3 — when True, a {"phase": "started"} entry is
                 recorded BEFORE each tool handler runs, so a runner
                 dying mid-step leaves the started-but-unfinished
                 marker resume reads. Default False keeps the E1/E2
                 record shape for callers that do not resume.
    job:         E6 — the job record dict this run serves, when the
                 caller has it: the source of the job instruction
                 layer and of job["evidence"], and the dict the
                 loaded-instructions manifest is stamped onto as
                 job["instructionsLoaded"].
    instructions: E6 — explicit operating-instructions text. When
                 None (the default) the loop loads the layered text
                 via engine_instructions at job start; pass
                 load_instructions=False to run with none.
    evidence:    E6 — the goal's declared evidence requirements
                 (see _norm_requirement for the shapes). Falls back
                 to job["evidence"] when the arg is None. When any
                 requirements are in force, a done claim must pass
                 the done-evidence gate (module docstring). E7 —
                 a requirement dict carrying "args" is verify-style:
                 it passes only on a recorded OK step from the
                 named (verify) tool with matching args, recorded
                 after the artifact's last write. E8 — the same
                 requirements also auto-close the run: the moment
                 a completed step leaves every requirement
                 satisfied, the loop ends the run DONE itself
                 ("evidence complete — auto-closed") instead of
                 waiting for the brain to declare done.

    Returns (status, output): status is "done" | "failed" |
    "stopped" | "unverified" (E6 — done claimed without the
    declared evidence); output is the done answer, the honest
    failure reason, or "".
    """
    brain = brain or worker_brain
    record = record or worker_record
    stop = stop or worker_stop
    by_name = {t["name"]: t for t in tools}
    history = [dict(h) for h in (seed_history or [])]
    # E10: on a resumed run, restore the plan from the seed record's
    # last set_plan step when the job dict does not already carry it
    # — the record is the persistence, not any runner's memory.
    if isinstance(job, dict) and not job.get("plan"):
        for h in history:
            if str(h.get("action") or "") == "set_plan":
                restored = _plan_from_result(h.get("result"))
                if restored:
                    job["plan"] = restored
    t0 = time.time()
    steps = int(step_offset or 0)
    pending_verify = str(verify_first_for or "") or None

    # E6: operating instructions, loaded at job start and handed to
    # the brain as its system context on every call — but only to
    # brains whose contract accepts them (worker_brain does; the
    # E1-signature rig brains are called exactly as before).
    instructions_text = None
    if instructions is not None:
        instructions_text = str(instructions)
    elif load_instructions:
        try:
            instructions_text, _manifest = \
                engine_instructions.load_instructions(job=job)
            if isinstance(job, dict):
                job["instructionsLoaded"] = _manifest
        except Exception as e:
            print("agent_loop: instruction loading failed:", e, flush=True)
            instructions_text = None
    brain_takes_instructions = bool(instructions_text) \
        and _takes_instructions(brain)

    # E6: the evidence this goal's done claim will be verified
    # against — OK steps the record already holds (seed history)
    # plus every OK step this run executes.
    evidence_reqs = evidence
    if evidence_reqs is None and isinstance(job, dict):
        evidence_reqs = job.get("evidence")
    ok_steps = []
    # E7: the same OK steps as events — tool + args + mutating +
    # sequence — for verify-style requirements. Seed-history
    # entries carry no structured args (their "arg" is a display
    # summary), so their events record args=None: they can never
    # satisfy a verify-style requirement, and a resumed run must
    # verify again in-run. That is the conservative direction —
    # a verify is cheap, a stale one is worthless.
    ok_events = []
    for i, h in enumerate(history):
        res = str(h.get("result") or "")
        if res.startswith("ok: "):
            ok_steps.append((str(h.get("action") or ""), res[4:]))
            ok_events.append({"tool": str(h.get("action") or ""),
                              "args": None, "mutating": False,
                              "seq": i - len(history)})
    verify_failures = 0

    def emit(entry):
        try:
            record(entry)
        except Exception as e:
            print("agent_loop: record failed:", e, flush=True)

    while steps < max_steps:
        if deadline_s is not None and time.time() - t0 > deadline_s:
            return "failed", f"Time limit ayipoyindhi ({steps} steps tarvatha)."
        # Stop is honoured at the checkpoint BEFORE the next step —
        # the same poll point browse/setup use (the app flips the job
        # state; the runner obeys on its next poll).
        try:
            if stop():
                emit({"n": steps, "tool": "stopped", "arg": "", "ok": True,
                      "result": "stop requested — loop halted at checkpoint",
                      "at": int(time.time() * 1000)})
                return "stopped", ""
        except Exception:
            pass  # a broken stop poll is "no signal", never a dead loop
        if brain_takes_instructions:
            action = brain(goal, list(history), tools, observation,
                           instructions=instructions_text)
        else:
            action = brain(goal, list(history), tools, observation)
        if action is None:
            return "failed", "Brain nunchi response raaledhu (agentstep unreachable) — step plan cheyyalekapoya."
        kind = str(action.get("action") or "").lower()
        steps += 1
        if kind == "done":
            answer = str(action.get("answer") or "").strip()
            if not answer:
                history.append({"action": "done",
                                "result": "rejected: empty answer — an answer must state what the tool results actually showed"})
                continue
            if evidence_reqs:
                # E6 done-evidence gate: the claim is verified
                # against the recorded steps BEFORE it is accepted.
                # A failing claim is fed back as a FAILED
                # verification step naming the exact gap; after
                # MAX_DONE_VERIFY_FAILURES failed verifications the
                # run ends UNVERIFIED — never done, never silent.
                gaps = _evidence_gaps(evidence_reqs, ok_steps,
                                      ok_events, job)
                if gaps:
                    verify_failures += 1
                    gap_text = "; ".join(gaps)
                    emit({"n": steps, "tool": "verify", "arg": "",
                          "ok": False, "phase": "verify",
                          "result": ("done claim rejected — missing "
                                     "evidence: " + gap_text)[:RESULT_CAP],
                          "at": int(time.time() * 1000)})
                    if verify_failures >= MAX_DONE_VERIFY_FAILURES:
                        reason = (f"UNVERIFIED: done was claimed "
                                  f"{verify_failures} times without the "
                                  f"declared evidence — {gap_text}")
                        emit({"n": steps, "tool": "unverified", "arg": "",
                              "ok": False,
                              "result": reason[:RESULT_CAP],
                              "at": int(time.time() * 1000)})
                        return "unverified", reason[:1800]
                    history.append(
                        {"action": "verify",
                         "result": ("FAILED: done rejected — missing "
                                    "evidence: " + gap_text + ". Produce "
                                    "the missing evidence with tool calls, "
                                    "then declare done again.")})
                    continue
            emit({"n": steps, "tool": "done", "arg": "", "ok": True,
                  "result": answer[:RESULT_CAP], "at": int(time.time() * 1000)})
            return "done", answer[:1800]
        if kind == "fail":
            reason = str(action.get("reason") or "Task complete avvaledu.")[:600]
            emit({"n": steps, "tool": "fail", "arg": "", "ok": False,
                  "result": reason, "at": int(time.time() * 1000)})
            return "failed", reason
        if kind != "tool":
            history.append({"action": kind or "?",
                            "result": f"FAILED: unknown action {kind!r} — reply with a tool call, done, or fail"})
            continue
        name = str(action.get("tool") or "")
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        tool = by_name.get(name)
        if tool is None:
            ok, result = False, f"unknown tool {name!r} — available tools: {', '.join(sorted(by_name)) or '(none)'}"
        elif pending_verify and (tool.get("mutating") or tool.get("needs_allow")):
            # E3 verify-first guard: a previous runner started the
            # pending_verify step and died before recording its
            # result, so that step's effect is UNKNOWN. Blindly
            # running another mutating call now could double-apply
            # it. The call is REFUSED as a FAILED step (the handler
            # never runs) until the brain verifies with a read-only
            # tool — mechanics, enforced here, not left to the brain.
            ok, result = False, (f"REFUSED (resume safety): step {pending_verify!r} was started by a "
                                 "previous runner but its result was never recorded — its effect is "
                                 "UNKNOWN. Verify it with a read-only tool first, then decide whether "
                                 "it must be redone. This mutating call was NOT executed.")
        elif tool.get("needs_allow") and not _allowed(allow, name, args):
            # E2 Allow gate: a mutating / external action without the
            # user's Allow is REFUSED — recorded as a FAILED step and
            # fed back to the brain like any other failure, so the
            # brain can ask the user or pick a read-only approach.
            # The handler is never executed silently.
            ok, result = False, (f"REFUSED: {name} is a mutating/external action and needs the user's Allow, "
                                 "which was not given — the tool was NOT executed. "
                                 "Ask the user for Allow, or use a read-only approach.")
        else:
            if record_started:
                # E3 checkpoint: mark the step started BEFORE the
                # handler runs. If this process dies inside the
                # handler, the record holds started-without-result —
                # exactly the UNKNOWN state resume_loop reads.
                emit({"n": steps, "tool": name, "arg": _arg_summary(action),
                      "ok": False, "result": "", "phase": "started",
                      "at": int(time.time() * 1000)})
            if callable(tool.get("cancel")):
                # E5: the tool declares cooperative cancellation —
                # it runs under stop polling, and a stop landing
                # mid-run signals its cancel hook and halts the
                # loop here: the interrupted step is recorded, the
                # halt is recorded, and NO further brain or tool
                # call happens after this point.
                outcome, ok, result = _call_handler_cancellable(
                    tool, args, stop)
                if outcome == "stopped":
                    emit({"n": steps, "tool": name,
                          "arg": _arg_summary(action), "ok": False,
                          "result": ("STOPPED mid-step: a stop was "
                                     "requested while this tool was "
                                     "running; its cancellation was "
                                     "signalled and the loop halted. "
                                     "The step's effect may be partial."),
                          "at": int(time.time() * 1000)})
                    emit({"n": steps, "tool": "stopped", "arg": "",
                          "ok": True,
                          "result": "stop requested — loop halted during tool execution",
                          "at": int(time.time() * 1000)})
                    return "stopped", ""
            else:
                ok, result = _call_handler(tool, args)
            if (pending_verify and ok and not tool.get("mutating")
                    and not tool.get("needs_allow")):
                # A read-only verification step completed — the brain
                # has now looked at the real state, so the guard
                # lifts and mutating calls are judged normally again.
                pending_verify = None
        result = result[:RESULT_CAP]
        if ok:
            # E6: a recorded OK result is evidence — the done gate
            # verifies later done claims against exactly this list
            # (plus the seed history's OK entries).
            ok_steps.append((name, result))
            # E7: the same step as an event, with the args it ran
            # with and whether its tool mutates — verify-style
            # requirements match on args, and order themselves
            # against the artifact's last write by step number.
            ok_events.append({"tool": name, "args": dict(args),
                              "mutating": bool(tool.get("mutating")),
                              "seq": steps})
        emit({"n": steps, "tool": name, "arg": _arg_summary(action),
              "ok": ok, "result": result, "at": int(time.time() * 1000)})
        # The result — success OR failure — becomes history, so the
        # brain sees exactly what happened and replans. This feedback
        # is the whole point of the loop (browse discipline).
        history.append({"action": name, "arg": _arg_summary(action),
                        "result": ("ok: " if ok else "FAILED: ") + result})
        if evidence_reqs and not _evidence_gaps(evidence_reqs,
                                                ok_steps, ok_events, job):
            # E8 evidence auto-close: every declared requirement is
            # now satisfied by the recorded steps, so the run IS
            # done — mechanically, whether or not the brain notices
            # (parity v2: its verify passed and it still wandered
            # to the step limit). End it here: terminal entry +
            # DONE, the answer a summary of the final step. No
            # further brain call is made.
            summary = (f"evidence complete — auto-closed after "
                       f"step {steps} ({name}: {result})")
            emit({"n": steps, "tool": "done", "arg": "", "ok": True,
                  "result": summary[:RESULT_CAP],
                  "at": int(time.time() * 1000)})
            return "done", summary[:1800]
    return "failed", f"Step limit ayipoyindhi ({max_steps} steps) — task inka complete avvaledu."


# ---------------------------------------------------------------- E3 resume
# The record is the job's memory; a runner is disposable. These
# helpers rebuild a loop from a recorded steps[] and continue it.
# Nothing here dispatches runners or touches production flows — the
# trigger helper only DECIDES resumability and starts the loop in
# resume mode; wiring it into dispatch/cron is a later phase.

TERMINAL_STATES = ("done", "failed", "stopped", "unverified")
TERMINAL_STEP_TOOLS = ("done", "fail", "stopped", "unverified")

UNKNOWN_RESULT = ("UNKNOWN: this step was started by a previous runner but its "
                  "result was never recorded — the runner died mid-step. Do NOT "
                  "assume it succeeded or failed. If the tool is mutating, verify "
                  "its effect with a read-only tool before deciding whether to "
                  "redo it; the loop enforces verify-first for mutating calls.")


def parse_recorded_steps(steps):
    """Split a recorded steps[] into what resume needs.

    Returns {"history", "completed", "inflight", "last_n", "terminal"}:
    - completed: entries with a recorded result — successes AND
      failures (a failed step was completed too: the brain saw its
      failure and replanned; resume preserves that exactly).
    - inflight: entries with a "started" marker and NO completion —
      the runner died mid-step; the step's effect is UNKNOWN.
    - history: brain history rebuilt in recorded order — completed
      steps as ("ok: " / "FAILED: ") results, inflight steps as the
      UNKNOWN_RESULT entry, started markers that DID complete folded
      into their completion (never shown twice).
    - last_n: highest step number recorded (resume continues from
      last_n + 1; a completed step number is never reused).
    - terminal: "done" | "fail" | "stopped" when the record itself
      carries a terminal step entry, else None.
    Entries without a phase (the E1/E2 shape) are completions."""
    completed = {}
    started = {}
    order = []
    last_n = 0
    terminal = None
    for e in (steps if isinstance(steps, list) else []):
        if not isinstance(e, dict):
            continue
        if e.get("phase") == "chain":
            # E4 chain-state marker: engine bookkeeping mirrored
            # into steps[] — never a step, never history, never
            # terminal, never counted in last_n.
            continue
        tool = str(e.get("tool") or "")
        try:
            n = int(e.get("n") or 0)
        except Exception:
            n = 0
        last_n = max(last_n, n)
        if tool in TERMINAL_STEP_TOOLS:
            terminal = tool
            continue
        if e.get("phase") == "started":
            if n not in started:
                order.append(("started", n))
            started[n] = e
        else:
            if n not in completed:
                order.append(("done", n))
            completed[n] = e
    history = []
    inflight = []
    for kind, n in order:
        if kind == "done":
            e = completed[n]
            history.append({"action": str(e.get("tool") or ""),
                            "arg": str(e.get("arg") or ""),
                            "result": ("ok: " if e.get("ok") else "FAILED: ")
                            + str(e.get("result") or "")})
        elif n not in completed:
            e = started[n]
            inflight.append(e)
            history.append({"action": str(e.get("tool") or ""),
                            "arg": str(e.get("arg") or ""),
                            "result": UNKNOWN_RESULT})
    return {"history": history,
            "completed": [completed[n] for kind, n in order if kind == "done"],
            "inflight": inflight,
            "last_n": last_n,
            "terminal": terminal}


def build_resume_history(steps):
    """The brain history a resumed loop starts from (see
    parse_recorded_steps for the exact reconstruction rules)."""
    return parse_recorded_steps(steps)["history"]


def job_terminal(job):
    """Terminal marker for a job record: its state, or the terminal
    step entry its loop recorded, or None when the job can still run.
    Terminal is final — the agentsteps endpoint already refuses to
    rewrite a terminal record, and resume honours the same rule."""
    if not isinstance(job, dict):
        return None
    state = str(job.get("state") or "")
    if state in TERMINAL_STATES:
        return state
    return parse_recorded_steps(job.get("steps"))["terminal"]


def is_resumable(job):
    """Resumability test for the trigger helper: a record exists, is
    NOT terminal, and holds at least one recorded step to resume
    from. (A non-terminal record with zero steps is a fresh run, not
    a resume — resume_loop still handles it, as a fresh run.)"""
    if not isinstance(job, dict) or job_terminal(job):
        return False
    steps = job.get("steps")
    return isinstance(steps, list) and len(steps) > 0


def resume_loop(job, tools=None, brain=None, record=None, stop=None, **kw):
    """Resume the agent loop for a job record (E3 entry point).

    The brain's history is rebuilt from the record's steps[] —
    completed steps are NEVER re-executed by the loop itself (they
    exist only as history; the loop runs nothing until the brain
    decides the next step), step numbering continues from the
    record, and an unfinished mutating step arms the loop's
    verify-first guard. A terminal job is NOT resumed. A record with
    zero steps behaves exactly like a fresh run.

    Returns (status, output) — run_loop's statuses, plus "terminal"
    when the job was already finished and nothing was run."""
    if not isinstance(job, dict):
        return "failed", "Resume asked for a job with no record."
    term = job_terminal(job)
    if term:
        return "terminal", f"Job already {term} — terminal jobs are not resumed."
    goal = str(job.get("task") or job.get("goal") or "").strip()
    if not goal:
        return "failed", "Agent job carries no task text."
    tools = tools if tools is not None else default_tools()
    parsed = parse_recorded_steps(job.get("steps"))
    by_name = {t["name"]: t for t in tools}
    verify_for = None
    for e in parsed["inflight"]:
        t = by_name.get(str(e.get("tool") or ""))
        if t and (t.get("mutating") or t.get("needs_allow")):
            verify_for = str(e.get("tool") or "")
            break
    kw.setdefault("record_started", True)
    return run_loop(goal, tools, brain=brain, record=record, stop=stop,
                    seed_history=parsed["history"],
                    step_offset=parsed["last_n"],
                    verify_first_for=verify_for, job=job, **kw)


def resume_trigger(job, tools=None, **kw):
    """Runner-side resume trigger: when the job is resumable (record
    exists, not terminal, has steps) start the loop in resume mode
    and return its (status, output); otherwise return None — the
    caller decides what a non-resumable job means (fresh dispatch,
    terminal report, ...). Production caller: agent_runner.py tries
    this first for every agent job it claims."""
    if not is_resumable(job):
        return None
    return resume_loop(job, tools, **kw)


def resume_current_job(tools=None, **kw):
    """Resume THIS runner's job: read the record through the runner
    channel (fetch_job_state — the same read job_state uses) and
    resume from it. An unreachable record fails honestly."""
    job = fetch_job_state()
    if job is None:
        return "failed", "Job record unreachable via the runner channel — cannot resume."
    return resume_loop(job, tools, **kw)


def run_agent_job(job, tools=None, **kw):
    """Thin convenience wrapper for a job record: the goal is the
    job's task text. Production caller: agent_runner.py (agent jobs
    created by POST /api/agent). E3: fresh runs through this wrapper
    checkpoint started markers by default, so a job started here is
    resumable if its runner dies."""
    goal = str(job.get("task") or job.get("goal") or "").strip()
    if not goal:
        return "failed", "Agent job carries no task text."
    kw.setdefault("record_started", True)
    return run_loop(goal, tools if tools is not None else default_tools(),
                    job=job, **kw)


# ---------------------------------------------------------------- E5 status
# Status-from-real-state: these builders read ONLY the job record —
# no brain call, no model, no invented percentages. What the record
# does not hold, the status does not claim.

def build_job_status(job):
    """Structured status for a job record, built from the record
    alone: job state, the current goal (the chain's current goal,
    or the job's task), step counts from steps[] (completed / ok /
    failed / in-flight), the last recorded step, the chain position
    when the job carries a chain, and the record's first/last
    activity timestamps. A record with nothing in it — or no record
    at all — returns {"has_data": False} and nothing else is
    claimed."""
    if not isinstance(job, dict):
        return {"has_data": False}
    steps = job.get("steps") if isinstance(job.get("steps"), list) else []
    parsed = parse_recorded_steps(steps)
    chain = _chain_state_from(job)
    state = str(job.get("state") or "")
    task = str(job.get("task") or job.get("goal") or "")
    if not (state or task or steps or chain):
        return {"has_data": False}
    completed = parsed["completed"]
    ok_n = sum(1 for e in completed if e.get("ok"))
    last = completed[-1] if completed else None
    ats = []
    for e in steps:
        if isinstance(e, dict):
            try:
                at = int(e.get("at") or 0)
            except Exception:
                at = 0
            if at:
                ats.append(at)
    chain_out = None
    goal = task or None
    if chain:
        goals = chain["goals"]
        chain_out = {"status": chain["status"],
                     "index": chain["index"],
                     "total": len(goals),
                     "completed": len(chain["handoffs"]),
                     "halt_reason": chain["haltReason"]}
        if chain["status"] != "done" and chain["index"] < len(goals):
            goal = goals[chain["index"]]["goal"] or goal
    return {
        "has_data": True,
        "state": state or None,
        "terminal": job_terminal(job),
        "goal": goal,
        "steps": {"recorded": len(completed) + len(parsed["inflight"]),
                  "completed": len(completed),
                  "ok": ok_n,
                  "failed": len(completed) - ok_n,
                  "inflight": len(parsed["inflight"])},
        "last_step": ({"n": _step_n(last),
                       "tool": str(last.get("tool") or ""),
                       "ok": bool(last.get("ok")),
                       "result": str(last.get("result") or ""),
                       "at": last.get("at")} if last else None),
        "chain": chain_out,
        "first_at": min(ats) if ats else None,
        "last_at": max(ats) if ats else None,
    }


def format_job_status(job):
    """The status as plain text lines, from build_job_status —
    counts and positions only, never a percentage. An empty record
    gets one plain sentence saying there is no data."""
    st = build_job_status(job)
    if not st["has_data"]:
        return "No job data recorded yet — there is nothing to report."
    lines = ["Job status (from the job record):"]
    lines.append(f"- state: {st['state'] or 'not recorded'}"
                 + (f" (terminal: {st['terminal']})" if st["terminal"] else ""))
    if st["goal"]:
        lines.append(f"- current goal: {st['goal']}")
    s = st["steps"]
    lines.append(f"- steps: {s['recorded']} recorded — {s['completed']} "
                 f"completed ({s['ok']} ok, {s['failed']} failed), "
                 f"{s['inflight']} in flight")
    if st["last_step"]:
        ls = st["last_step"]
        lines.append(f"- last step: #{ls['n']} {ls['tool']} — "
                     f"{'ok' if ls['ok'] else 'FAILED'} — {ls['result']}")
    else:
        lines.append("- last step: none recorded")
    if st["chain"]:
        c = st["chain"]
        lines.append(f"- chain: goal {c['index'] + 1} of {c['total']} "
                     f"({c['completed']} completed), status {c['status']}")
        if c["halt_reason"]:
            lines.append(f"- chain halt reason: {c['halt_reason']}")
        remaining = c["total"] - c["index"] - 1
        if c["status"] == "running" and remaining > 0:
            lines.append(f"- remaining: {remaining} goal(s) after the current one")
    return "\n".join(lines)


# ------------------------------------------------------------------ E4 chain
# Chain continuation for agent jobs (see the module docstring). The
# descriptor lives on the job record as job["chain"]:
#   {"goals": [{"goal": str,
#               "tools": [tool names]   (optional subset),
#               "allow": Allow          (optional, E2 semantics)}, ...],
#    "index": int,                      # next goal to run
#    "status": "pending" | "running" | "done" | "halted",
#    "haltReason": str,
#    "goalStartN": int,                 # step number the current goal
#                                       # started after (its recorded
#                                       # steps are the ones above it)
#    "handoffs": [str],                 # one summary per finished goal
#    "lastAnswer": str}
# The live state is mirrored into steps[] as {"phase": "chain"}
# markers through the same recorder the steps use, so the record
# alone reconstructs the chain after a runner dies.

MAX_CHAIN_GOALS = 10      # hard cap on goals a chain will run
HANDOFF_CAP = 1500        # chars per goal handoff summary
HANDOFF_STEP_CAP = 220    # chars per step line inside a handoff


def _step_n(e):
    try:
        return int(e.get("n") or 0)
    except Exception:
        return 0


def _goal_spec(g):
    """Normalize one chain goal entry: a bare string is a goal with
    the job's full tool set; a dict may narrow the tools to a subset
    and/or carry its own Allow (E2 semantics: True, a callable
    allow(name, args) -> bool, or a container of tool names). E6: a
    dict may also carry its own "evidence" requirements (the done
    gate's declared checks for this goal) and "instructions" text
    (the job instruction layer for this goal's run)."""
    if isinstance(g, str):
        return {"goal": g}
    if isinstance(g, dict):
        out = {"goal": str(g.get("goal") or "")}
        if isinstance(g.get("tools"), (list, tuple)) and g["tools"]:
            out["tools"] = [str(t) for t in g["tools"]]
        if "allow" in g:
            out["allow"] = g["allow"]
        if isinstance(g.get("evidence"), (list, tuple)) and g["evidence"]:
            out["evidence"] = list(g["evidence"])
        if str(g.get("instructions") or ""):
            out["instructions"] = str(g["instructions"])
        return out
    return {"goal": ""}


def make_chain(goals):
    """Build a chain descriptor for a job record (shape above).
    Goals beyond MAX_CHAIN_GOALS stay in the descriptor — the cap
    is enforced by run_chain, which halts the chain with the reason
    recorded rather than running on past it."""
    return {"goals": [_goal_spec(g) for g in (goals or [])],
            "index": 0, "status": "pending", "haltReason": "",
            "goalStartN": 0, "handoffs": [], "lastAnswer": ""}


def _chain_state_from(job):
    """Reconstruct the live chain state for a job record: the latest
    chain marker in steps[] wins (it is the newest progress); fall
    back to the descriptor the job was created with. Returns a
    normalized state dict, or None when the job carries no chain."""
    state = None
    if isinstance(job, dict) and isinstance(job.get("chain"), dict):
        state = dict(job["chain"])
    if isinstance(job, dict):
        for e in (job.get("steps") or []):
            if isinstance(e, dict) and e.get("phase") == "chain":
                try:
                    m = json.loads(str(e.get("result") or ""))
                except Exception:
                    continue
                if isinstance(m, dict) and isinstance(m.get("goals"), list):
                    state = m
    if state is None or not isinstance(state.get("goals"), list):
        return None
    out = make_chain(state["goals"])
    for k in ("index", "status", "haltReason", "goalStartN",
              "handoffs", "lastAnswer"):
        if k in state:
            out[k] = state[k]
    out["index"] = _step_n({"n": out.get("index")})
    out["goalStartN"] = _step_n({"n": out.get("goalStartN")})
    out["handoffs"] = [str(h) for h in (out.get("handoffs") or [])]
    out["status"] = str(out.get("status") or "pending")
    out["haltReason"] = str(out.get("haltReason") or "")
    out["lastAnswer"] = str(out.get("lastAnswer") or "")
    return out


def chain_state(job):
    """Public read: the job's live chain state (descriptor + progress
    + halt reason), reconstructed from the record alone."""
    return _chain_state_from(job)


def _chain_emit(record, state):
    """Mirror the chain state into the record as a chain marker
    entry, through the same recorder the steps use (the Worker
    appends it to steps[] via agentsteps in production)."""
    entry = {"n": 0, "tool": "chain", "phase": "chain",
             "ok": state.get("status") != "halted",
             "result": json.dumps(state, ensure_ascii=False, default=str),
             "at": int(time.time() * 1000)}
    try:
        record(entry)
    except Exception as e:
        print("agent_loop: chain record failed:", e, flush=True)


def build_handoff(goal_text, entries, answer):
    """The compact handoff one finished goal passes to the next: the
    goal, one line per completed step (tool + ok/FAILED + recorded
    result, capped), and the goal's final answer — built ONLY from
    the recorded steps, never the raw brain transcript."""
    lines = [f"Completed goal: {goal_text}"]
    for e in parse_recorded_steps(entries)["completed"]:
        lines.append(f"- {e.get('tool') or '?'}: "
                     f"{'ok' if e.get('ok') else 'FAILED'} — "
                     f"{str(e.get('result') or '')[:HANDOFF_STEP_CAP]}")
    lines.append(f"Final answer: {answer}")
    return "\n".join(lines)[:HANDOFF_CAP]


def run_chain(job, tools=None, brain=None, record=None, stop=None,
              max_goals=MAX_CHAIN_GOALS, **kw):
    """Run (or resume) the job's chain of goals, in order.

    Each goal runs through run_loop with that goal's tool subset and
    Allow. When a goal finishes DONE the engine builds its handoff
    and starts the next goal itself, seeding the brain with every
    previous handoff plus the current goal's own recorded history.
    A FAILED or STOPPED goal halts the chain: the chain state is
    marked halted with the reason, later goals never start, and a
    later run_chain on the same record reports "terminal" instead
    of retrying. Running past max_goals goals halts the chain the
    same way. A runner dying mid-goal (exception, kill) leaves the
    chain marker + step record behind; calling run_chain again on
    the record resumes the CURRENT goal under E3's rules — completed
    steps are history, never re-executed; an unfinished mutating
    step arms verify-first — with the chain position preserved.

    Extra **kw (max_steps, deadline_s, observation, allow) pass to
    run_loop; a goal's own "allow" overrides the chain-wide one.

    Returns (status, output): "done" with the last goal's answer,
    "failed" with the halt reason, "stopped", "unverified" (E6 —
    a goal's done claim failed its evidence gate), or "terminal"
    when the chain had already halted before this call."""
    if not isinstance(job, dict):
        return "failed", "Chain asked for a job with no record."
    state = _chain_state_from(job)
    if state is None or not state["goals"]:
        return "failed", "Job carries no chain of goals."
    if state["status"] == "done":
        return "done", state.get("lastAnswer") or ""
    if state["status"] == "halted":
        return "terminal", ("Chain already halted: "
                            + (state.get("haltReason") or "reason not recorded"))
    tools = tools if tools is not None else default_tools()
    base_record = record or worker_record
    snap0 = [e for e in (job.get("steps") or []) if isinstance(e, dict)]
    recorded_now = []

    def _record(entry):
        recorded_now.append(entry)
        base_record(entry)

    def _entries():
        return snap0 + recorded_now

    def _goal_entries():
        return [e for e in _entries()
                if e.get("phase") != "chain"
                and _step_n(e) > state["goalStartN"]]

    def _last_n():
        return parse_recorded_steps(_entries())["last_n"]

    state["status"] = "running"
    _chain_emit(_record, state)
    while state["index"] < len(state["goals"]):
        idx = state["index"]
        if idx >= max_goals:
            state["status"] = "halted"
            state["haltReason"] = (f"chain goal cap reached ({max_goals} goals) — "
                                   f"goal {idx + 1} and later goals were not run")
            _chain_emit(_record, state)
            return "failed", state["haltReason"]
        gspec = state["goals"][idx]
        goal_text = gspec["goal"]
        if not goal_text:
            state["status"] = "halted"
            state["haltReason"] = f"goal {idx + 1} carries no goal text"
            _chain_emit(_record, state)
            return "failed", state["haltReason"]
        gentries = _goal_entries()
        parsed = parse_recorded_steps(gentries)
        if parsed["terminal"]:
            # Crash window: the goal's loop recorded its terminal
            # step but the runner died before the chain marker
            # landed. Settle the goal from the record itself —
            # never re-run it.
            term_entry = {}
            for e in gentries:
                if str(e.get("tool") or "") in TERMINAL_STEP_TOOLS:
                    term_entry = e
            reason = str(term_entry.get("result") or "")
            state["goalStartN"] = _last_n()
            if parsed["terminal"] == "fail":
                state["status"] = "halted"
                state["haltReason"] = f"goal {idx + 1} failed: {reason}"
                _chain_emit(_record, state)
                return "failed", reason
            if parsed["terminal"] == "unverified":
                state["status"] = "halted"
                state["haltReason"] = f"goal {idx + 1} unverified: {reason}"
                _chain_emit(_record, state)
                return "unverified", reason
            if parsed["terminal"] == "stopped":
                state["status"] = "halted"
                state["haltReason"] = f"stopped during goal {idx + 1}"
                _chain_emit(_record, state)
                return "stopped", ""
            status, output = "done", reason
        else:
            by_name = {t["name"]: t for t in tools}
            verify_for = None
            for e in parsed["inflight"]:
                t = by_name.get(str(e.get("tool") or ""))
                if t and (t.get("mutating") or t.get("needs_allow")):
                    verify_for = str(e.get("tool") or "")
                    break
            if gspec.get("tools"):
                goal_tools = [t for t in tools if t["name"] in gspec["tools"]]
            else:
                goal_tools = tools
            seed = [{"action": "handoff", "arg": "", "result": h}
                    for h in state["handoffs"]] + parsed["history"]
            goal_kw = dict(kw)
            goal_kw["allow"] = (gspec["allow"] if "allow" in gspec
                                else goal_kw.get("allow"))
            # E6: this goal's run serves a per-goal view of the job
            # record — the goal's own instruction layer (when the
            # descriptor carries one) and its declared evidence
            # requirements ride into the loop with it.
            goal_job = dict(job)
            if gspec.get("instructions"):
                goal_job["instructions"] = gspec["instructions"]
            goal_kw["job"] = goal_job
            if "evidence" in gspec:
                goal_kw["evidence"] = gspec["evidence"]
            status, output = run_loop(goal_text, goal_tools, brain=brain,
                                      record=_record, stop=stop,
                                      seed_history=seed,
                                      step_offset=_last_n(),
                                      verify_first_for=verify_for,
                                      record_started=True, **goal_kw)
            # Re-capture BEFORE advancing goalStartN: the handoff is
            # built from this goal's entries, which the advance would
            # filter out.
            gentries = _goal_entries()
            state["goalStartN"] = _last_n()
        if status == "done":
            state["handoffs"].append(
                build_handoff(goal_text, gentries, output))
            state["lastAnswer"] = output
            state["index"] = idx + 1
            if state["index"] >= len(state["goals"]):
                state["status"] = "done"
                _chain_emit(_record, state)
                return "done", output
            _chain_emit(_record, state)
            continue
        if status == "stopped":
            state["status"] = "halted"
            state["haltReason"] = f"stopped during goal {idx + 1}"
            _chain_emit(_record, state)
            return "stopped", ""
        if status == "unverified":
            # E6: the goal's done claim never produced its declared
            # evidence — the chain halts with that reason recorded;
            # later goals never start on an unproven completion.
            state["status"] = "halted"
            state["haltReason"] = f"goal {idx + 1} unverified: {output}"
            _chain_emit(_record, state)
            return "unverified", output
        state["status"] = "halted"
        state["haltReason"] = f"goal {idx + 1} failed: {output}"
        _chain_emit(_record, state)
        return "failed", output
    # Index already past the end (a record whose final marker was
    # lost): the chain is complete by its own accounting.
    state["status"] = "done"
    _chain_emit(_record, state)
    return "done", state.get("lastAnswer") or ""
