"""Julie agent runner (engine integration): the PRODUCTION entry
point for agent jobs.

Until now the E1–E9 engine (agent_loop.py + tools_registry.py) was
proven only in rigs and parity harnesses: the Worker already held
the brain (setup/runner/agentstep), the step recorder
(setup/runner/agentsteps) and the job channel, but no production
flow CREATED an agent job and no runner CLAIMED one. This runner is
the claim, on the browse.py pattern: the Worker creates a
setupjob:<id> record with provider "agent" (POST /api/agent →
startAgentJob → agent.yml dispatch), and this process executes it.

Shape: the runner is the HANDS, the Worker is the BRAIN — the loop
(agent_loop.run_agent_job / resume_trigger) asks the Worker for one
step at a time through agentstep, executes it with the registry's
tools, and records every step on the job record through agentsteps,
so the record is the job's real state at all times. The job's
workspace is a per-job directory under the runner's jobs area
(DATA_DIR/agent/<job>); the record's seeded text files are written
into it (confinement-checked) before the loop starts, and every
file/compute tool is confined to it (E2.5/E7/E8). If the record
already holds steps from a dead runner, the run RESUMES from the
record (E3) instead of restarting.

Allow policy: the workspace-confined mutating tools (file_write /
file_append / filter_csv) are Allowed — they can only touch this
job's own sandbox, which exists precisely so the job can produce
its outputs there. No browser tools are registered in this runner
(no live page exists here), so no needs_allow tool that can touch
anything outside the sandbox is ever offered, let alone Allowed.

Terminal reporting mirrors browse.py exactly: report_result first
(the authoritative outcome — the Worker stores the answer, settles
the state, tells the owner, and refunds a failed/unverified job's
creation spend), then the terminal progress post. Statuses: done /
failed / stopped / unverified (the E6 evidence gate's honest
terminal state — a done claim the recorded evidence did not back).
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setup as S  # env + the proven runner channel (get_job / progress / report_result)
import agent_loop
import tools_registry
import workspace_tools

JOB = S.JOB
DEADLINE_S = 25 * 60  # workflow timeout is 35 min; finish well inside it
# The only needs_allow tools this runner Allows: the ones confined
# to the job's own workspace (see the module docstring).
# E10: edit_file joins them (it is workspace-confined like the
# writes). run_command does NOT: its sandbox is cwd + timeout +
# output cap, not filesystem confinement, and it inherits the
# runner's environment — so it stays behind a real Allow, which
# this unattended runner never grants; an agent job's brain gets
# the honest refusal and verifies with file_read / verify_* tools
# instead (divya's call, E10 review 2026-11-19).
SANDBOX_ALLOW = ("file_write", "file_append", "filter_csv",
                 "edit_file")


def workspace_root():
    """The per-job workspace: DATA_DIR/agent/<job> (DATA_DIR is the
    runner jobs area — /tmp/divya on Actions, the same default
    runner.py uses)."""
    base = os.environ.get("DATA_DIR", "/tmp/divya")
    return os.path.join(base, "agent", JOB)


def seed_files(job, root):
    """Write the job record's seeded text files into the workspace
    before the loop starts. Every name goes through the workspace
    confinement check (workspace_tools._confined — the same check
    the file tools enforce); a name that escapes the root is skipped
    with a log line, never written."""
    files = job.get("files")
    if not isinstance(files, dict) or not files:
        return
    root_real = os.path.realpath(root)
    os.makedirs(root_real, exist_ok=True)
    for name, content in files.items():
        target = workspace_tools._confined(root_real, str(name))
        if target is None or target == root_real:
            print(f"agent: seed file {name!r} refused (escapes workspace)", flush=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(str(content))
        print(f"agent: seeded {name} ({len(str(content))} chars)", flush=True)


def build_tools(root, job=None):
    """The registry for an agent job: the context-free tools
    (job_state + stubs) plus the workspace file tools and the
    deterministic compute/verify tools, all confined to the job
    workspace. Browser tools are NOT registered — this runner has
    no live page (browse jobs own the browser).

    E10: passes job record for read-before-edit enforcement."""
    reg = tools_registry.default_registry()
    tools_registry.register_workspace_tools(reg, root, job_record=job)
    tools_registry.register_compute_tools(reg, root)
    tools_registry.register_plan_tool(reg, job)
    return reg.as_tools()


def main():
    job = S.get_job()
    if job.get("provider") != "agent":
        print(f"agent: job {JOB} is provider {job.get('provider')!r}, not 'agent' — refusing to run it", flush=True)
        raise SystemExit(1)
    print(f"agent: job task={str(job.get('task') or '')[:80]!r}", flush=True)
    root = workspace_root()
    seed_files(job, root)
    tools = build_tools(root, job=job)
    S.progress("running", "start", "Agent job start ayyindhi — pani chesthunna.", "")
    try:
        # A record with steps from a dead runner resumes (E3); a
        # fresh record starts through run_agent_job. resume_trigger
        # returns None when the job is not resumable, and a terminal
        # tuple when the job already finished — reported by silence
        # below, because a terminal record is final.
        res = agent_loop.resume_trigger(job, tools, allow=SANDBOX_ALLOW,
                                        deadline_s=DEADLINE_S)
        if res is None:
            res = agent_loop.run_agent_job(job, tools, allow=SANDBOX_ALLOW,
                                           deadline_s=DEADLINE_S)
        status, out = res
    except Exception as e:
        status, out = "failed", f"Agent run aagipoyindhi: {str(e)[:200]}"
    if status == "terminal":
        print(f"agent: job already terminal ({out}) — nothing to run", flush=True)
        return
    if status == "done":
        S.report_result("agent", "done", extra={"answer": out})
        S.progress("done", "done", out[:280], "")
    elif status == "stopped":
        S.report_result("agent", "stopped")
        S.progress("stopped", "stopped", "Aapesaru — agent job stop ayyindhi.", "")
    elif status == "unverified":
        S.report_result("agent", "unverified", error=out)
        S.progress("unverified", "unverified", out[:280], "")
    else:
        S.report_result("agent", "failed", error=out)
        S.progress("failed", "failed", out[:280], "")


if __name__ == "__main__":
    main()
