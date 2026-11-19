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
             allow=None):
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
    deadline_s:  optional wall-clock budget; None = no deadline.
    observation: optional extra context handed to the brain each step
                 (e.g. a page snapshot for browser-flavoured jobs).
    allow:       the E2 Allow grant for needs_allow tools — True, a
                 callable(name, args) -> bool, or a container of
                 allowed tool names. Default None = no Allow: a
                 needs_allow call is refused as a FAILED step (the
                 handler never runs) and the brain replans.

    Returns (status, output): status is "done" | "failed" | "stopped";
    output is the done answer, the honest failure reason, or "".
    """
    brain = brain or worker_brain
    record = record or worker_record
    stop = stop or worker_stop
    by_name = {t["name"]: t for t in tools}
    history = []
    t0 = time.time()
    steps = 0

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
            try:
                ok, result = _normalize(tool["run"](args))
            except Exception as e:
                ok, result = False, f"{name} error: {str(e)[:RESULT_CAP]}"
        result = result[:RESULT_CAP]
        emit({"n": steps, "tool": name, "arg": _arg_summary(action),
              "ok": ok, "result": result, "at": int(time.time() * 1000)})
        # The result — success OR failure — becomes history, so the
        # brain sees exactly what happened and replans. This feedback
        # is the whole point of the loop (browse discipline).
        history.append({"action": name, "arg": _arg_summary(action),
                        "result": ("ok: " if ok else "FAILED: ") + result})
    return "failed", f"Step limit ayipoyindhi ({max_steps} steps) — task inka complete avvaledu."


def run_agent_job(job, tools=None, **kw):
    """Thin convenience wrapper for a job record: the goal is the
    job's task text. NOT wired into any production dispatch yet —
    later engine phases call this from the runners."""
    goal = str(job.get("task") or job.get("goal") or "").strip()
    if not goal:
        return "failed", "Agent job carries no task text."
    return run_loop(goal, tools if tools is not None else default_tools(), **kw)
