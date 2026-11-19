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
e1test.py. It is NOT wired into any production job flow yet: browse.py,
setup.py and the video pipelines keep their current behaviour; E1 is
the engine core + proof, integration lands in later phases.

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
import json
import os
import time

import httpx

MAX_STEPS = 40        # same step budget as browse.py
HISTORY_WINDOW = 8    # brainstep/agentstep both see the last 8 steps
RESULT_CAP = 600      # chars of one tool result recorded / fed back


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


def worker_brain(goal, history, tools, observation=None):
    """Default brain: ask the Worker for the next action via
    /api/setup/runner/agentstep (agentstep is brainstep's general
    sibling). Returns the action dict, or None when the brain is
    unreachable / answered nothing usable — the loop then fails
    honestly, exactly like browse.brain_step."""
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


def _tool_job_state(args):
    """REAL read-only tool: this job's own record, read through the
    existing runner job endpoint (the same read setup.get_job does).
    Reports state/step/note only — no writes, nothing sealed."""
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
        {"name": "job_state", "desc": "Read this job's own record (state, current step, note, recorded step count). Read-only, no side effects.",
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


def run_loop(goal, tools, brain=None, record=None, stop=None,
             max_steps=MAX_STEPS, deadline_s=None, observation=None,
             allow=None, seed_history=None, step_offset=0,
             verify_first_for=None, record_started=False):
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

    Returns (status, output): status is "done" | "failed" | "stopped";
    output is the done answer, the honest failure reason, or "".
    """
    brain = brain or worker_brain
    record = record or worker_record
    stop = stop or worker_stop
    by_name = {t["name"]: t for t in tools}
    history = [dict(h) for h in (seed_history or [])]
    t0 = time.time()
    steps = int(step_offset or 0)
    pending_verify = str(verify_first_for or "") or None

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
            try:
                ok, result = _normalize(tool["run"](args))
            except Exception as e:
                ok, result = False, f"{name} error: {str(e)[:RESULT_CAP]}"
            if (pending_verify and ok and not tool.get("mutating")
                    and not tool.get("needs_allow")):
                # A read-only verification step completed — the brain
                # has now looked at the real state, so the guard
                # lifts and mutating calls are judged normally again.
                pending_verify = None
        result = result[:RESULT_CAP]
        emit({"n": steps, "tool": name, "arg": _arg_summary(action),
              "ok": ok, "result": result, "at": int(time.time() * 1000)})
        # The result — success OR failure — becomes history, so the
        # brain sees exactly what happened and replans. This feedback
        # is the whole point of the loop (browse discipline).
        history.append({"action": name, "arg": _arg_summary(action),
                        "result": ("ok: " if ok else "FAILED: ") + result})
    return "failed", f"Step limit ayipoyindhi ({max_steps} steps) — task inka complete avvaledu."


# ---------------------------------------------------------------- E3 resume
# The record is the job's memory; a runner is disposable. These
# helpers rebuild a loop from a recorded steps[] and continue it.
# Nothing here dispatches runners or touches production flows — the
# trigger helper only DECIDES resumability and starts the loop in
# resume mode; wiring it into dispatch/cron is a later phase.

TERMINAL_STATES = ("done", "failed", "stopped")
TERMINAL_STEP_TOOLS = ("done", "fail", "stopped")

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
                    verify_first_for=verify_for, **kw)


def resume_trigger(job, tools=None, **kw):
    """Runner-side resume trigger: when the job is resumable (record
    exists, not terminal, has steps) start the loop in resume mode
    and return its (status, output); otherwise return None — the
    caller decides what a non-resumable job means (fresh dispatch,
    terminal report, ...). NOT wired into production dispatch/cron
    yet; E3 is the mechanics + proof."""
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
    job's task text. NOT wired into any production dispatch yet —
    later engine phases call this from the runners. E3: fresh runs
    through this wrapper checkpoint started markers by default, so
    a job started here is resumable if its runner dies."""
    goal = str(job.get("task") or job.get("goal") or "").strip()
    if not goal:
        return "failed", "Agent job carries no task text."
    kw.setdefault("record_started", True)
    return run_loop(goal, tools if tools is not None else default_tools(), **kw)
