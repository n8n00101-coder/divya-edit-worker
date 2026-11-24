"""directortest.py — Director Layer rig for agent_loop.py.

Drives run_loop(director=True) with SCRIPTED FAKE BRAINS (no
model, no network) and proves the layer's mechanics — the same
mechanics the production runner (agent_runner, director=True)
enforces on real jobs:

  T1  plan gate: a tool call before any plan is REFUSED; the
      happy path (plan -> work -> check -> review -> done) ends
      done, and the director record holds plan/checks/review.
  T2  a brain that never plans fails honestly after the refusal
      budget — the job does not execute.
  T3  done claimed with unchecked steps is rejected, and after
      the gate budget the run ends UNVERIFIED, never done.
  T4  a failed check -> rework -> pass: the review carries NO
      defect for the step (its latest check passed).
  T5  a step failing past its rework budget is carried into the
      review's defects MECHANICALLY — a deliver verdict cannot
      hide it — and the job may still deliver, defect on record.
  T6  a rework review spends the rework loop; a second review
      (deliver) then lets done through.
  T7  a fail review ends the job as failed, reason = the
      review's own summary.
  T8  work after a deliver review makes it STALE: done is
      rejected until a fresh review lands.
  T9  director OFF (default): the pre-director loop is untouched
      (plain work + done, no plan needed).
  T10 checks land in plan order: checking step 2 before step 1
      is refused.
  T11 a review before every step is checked is refused.
  T12 the plan locks once checks exist: a second director_plan
      is refused.

Run: python3 directortest.py   (exit 1 on any failure)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Hermetic: no Worker channel (director posts become no-ops).
for _v in ("WORKER_URL", "RUNNER_KEY", "JOB"):
    os.environ.pop(_v, None)

import agent_loop
import tools_registry

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


class FakeBrain:
    def __init__(self, script):
        self.script = list(script)
        self.histories = []

    def __call__(self, goal, history, tools, observation=None):
        self.histories.append([dict(h) for h in history])
        if self.script:
            return self.script.pop(0)
        return {"action": "fail", "reason": "script exhausted"}


def tool(name, **args):
    return {"action": "tool", "tool": name, "args": args}


def done(answer="delivered"):
    return {"action": "done", "answer": answer}


PLAN2 = tool("director_plan",
             vision="A two-file deliverable for the test user: "
                    "a.txt and b.txt with exact contents; good = "
                    "both files present and verified by re-read.",
             steps=[{"title": "Write a.txt",
                     "acceptance": "a.txt exists containing HELLO"},
                    {"title": "Write b.txt",
                     "acceptance": "b.txt exists containing WORLD"}],
             risks=["file contents could be mistyped — re-read to verify"])
PLAN1 = tool("director_plan",
             vision="One file deliverable: a.txt containing HELLO, "
                    "verified by re-read before delivery.",
             steps=[{"title": "Write a.txt",
                     "acceptance": "a.txt exists containing HELLO"}],
             risks=[])
WRITE_A = tool("file_write", path="a.txt", content="HELLO")
WRITE_B = tool("file_write", path="b.txt", content="WORLD")
CHK1_PASS = tool("director_check", step=1, verdict="pass",
                 evidence="file_write ok and re-read shows HELLO")
CHK2_PASS = tool("director_check", step=2, verdict="pass",
                 evidence="file_write ok and re-read shows WORLD")
REVIEW_OK = tool("director_review", verdict="deliver",
                 summary="Both files verified against the vision.",
                 defects=[])

ALLOW = ("file_write", "file_append", "edit_file", "filter_csv")


def run(script, director=True, job=None):
    root = tempfile.mkdtemp(prefix="director-rig-")
    job = job if job is not None else {"task": "rig task"}
    reg = tools_registry.default_registry()
    tools_registry.register_workspace_tools(reg, root, job_record=job)
    tools_registry.register_compute_tools(reg, root)
    tools_registry.register_plan_tool(reg, job)
    if director:
        tools_registry.register_director_tools(reg, job)
    entries = []
    brain = FakeBrain(script)
    status, out = agent_loop.run_loop(
        "rig task", reg.as_tools(), brain=brain,
        record=entries.append, stop=lambda: False,
        allow=ALLOW, job=job, director=director,
        load_instructions=False, max_steps=40)
    return status, out, entries, job


def results(entries, name):
    return [e for e in entries if e.get("tool") == name]


# ------------------------------------------------------------ T1
status, out, entries, job = run([
    WRITE_A, PLAN2, WRITE_A, CHK1_PASS, WRITE_B, CHK2_PASS,
    REVIEW_OK, done("a.txt and b.txt delivered")])
first_write = results(entries, "file_write")[0]
d = job.get("director") or {}
check("T1 happy path ends done", status == "done", f"status={status} out={out[:120]}")
check("T1 pre-plan tool call refused by the plan gate",
      first_write.get("ok") is False
      and "director plan gate" in str(first_write.get("result")))
check("T1 director record holds plan/checks/review",
      bool((d.get("plan") or {}).get("vision"))
      and len(d.get("checks") or []) == 2
      and (d.get("reviews") or [{}])[-1].get("verdict") == "deliver")

# ------------------------------------------------------------ T2
status, out, entries, job = run([WRITE_A] * 12)
check("T2 no plan at all -> failed honestly",
      status == "failed" and "no plan was produced" in out,
      f"status={status} out={out[:120]}")
check("T2 nothing executed (no OK file_write)",
      all(e.get("ok") is False for e in results(entries, "file_write")))

# ------------------------------------------------------------ T3
status, out, entries, job = run([
    PLAN2, WRITE_A, done("done already"), done("really done")])
check("T3 unchecked done claims -> unverified",
      status == "unverified" and "director_check" in out,
      f"status={status} out={out[:160]}")
check("T3 gate rejections recorded with phase=director",
      any(e.get("phase") == "director" and e.get("ok") is False
          for e in entries))

# ------------------------------------------------------------ T4
status, out, entries, job = run([
    PLAN1, WRITE_A,
    tool("director_check", step=1, verdict="fail",
         evidence="re-read shows HELO — a letter missing"),
    tool("file_write", path="a.txt", content="HELLO"),
    CHK1_PASS, REVIEW_OK, done()])
rev = (job["director"]["reviews"] or [{}])[-1]
check("T4 fail->rework->pass ends done", status == "done",
      f"status={status}")
check("T4 review carries no defect for the reworked step",
      rev.get("defects") == [], f"defects={rev.get('defects')}")

# ------------------------------------------------------------ T5
chk_fail = tool("director_check", step=1, verdict="fail",
                evidence="re-read still shows the wrong contents")
status, out, entries, job = run([
    PLAN1, WRITE_A, chk_fail, chk_fail, chk_fail,
    REVIEW_OK, done()])
rev = (job["director"]["reviews"] or [{}])[-1]
check("T5 exhausted step still delivers (defect on record)",
      status == "done", f"status={status} out={out[:120]}")
check("T5 failed step mechanically carried into review defects",
      any("plan step 1 failed its check" in x
          for x in rev.get("defects") or []),
      f"defects={rev.get('defects')}")

# ------------------------------------------------------------ T6
status, out, entries, job = run([
    PLAN1, WRITE_A, CHK1_PASS,
    tool("director_review", verdict="rework",
         summary="The greeting is not verified yet.",
         defects=["no re-read evidence"]),
    tool("file_read", path="a.txt"), CHK1_PASS, REVIEW_OK, done()])
check("T6 rework loop then deliver ends done", status == "done",
      f"status={status} out={out[:120]}")
check("T6 two reviews recorded",
      len(job["director"].get("reviews") or []) == 2)

# ------------------------------------------------------------ T7
status, out, entries, job = run([
    PLAN1, WRITE_A, CHK1_PASS,
    tool("director_review", verdict="fail",
         summary="The file cannot be produced correctly here.",
         defects=["contents wrong"])])
check("T7 fail review ends the job failed with its summary",
      status == "failed" and "cannot be produced correctly" in out,
      f"status={status} out={out[:140]}")

# ------------------------------------------------------------ T8
status, out, entries, job = run([
    PLAN1, WRITE_A, CHK1_PASS, REVIEW_OK,
    tool("file_write", path="a.txt", content="HELLO!"),
    done("done"), REVIEW_OK, done("done")])
check("T8 stale review rejected, fresh review delivers",
      status == "done"
      and any(e.get("phase") == "director" for e in entries),
      f"status={status} out={out[:120]}")

# ------------------------------------------------------------ T9
status, out, entries, job = run([WRITE_A, done("plain done")],
                                director=False)
check("T9 director off: plain loop unchanged",
      status == "done" and "director" not in job,
      f"status={status}")

# ------------------------------------------------------------ T10
status, out, entries, job = run([
    PLAN2, CHK2_PASS, CHK1_PASS, CHK2_PASS, REVIEW_OK, done()])
chk_entries = results(entries, "director_check")
check("T10 out-of-order check refused, ordered checks pass",
      status == "done" and chk_entries[0].get("ok") is False
      and "plan order" in str(chk_entries[0].get("result")),
      f"status={status}")

# ------------------------------------------------------------ T11
status, out, entries, job = run([
    PLAN2, WRITE_A, CHK1_PASS, REVIEW_OK])
rev_entries = results(entries, "director_review")
check("T11 review before all checks refused",
      rev_entries and rev_entries[0].get("ok") is False
      and "no director_check" in str(rev_entries[0].get("result")))

# ------------------------------------------------------------ T12
status, out, entries, job = run([
    PLAN2, WRITE_A, CHK1_PASS, PLAN1])
plan_entries = results(entries, "director_plan")
check("T12 plan locks once checks exist",
      len(plan_entries) == 2 and plan_entries[1].get("ok") is False
      and "locked" in str(plan_entries[1].get("result")))

print()
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", ", ".join(FAIL))
    sys.exit(1)
print("DIRECTORTEST: ALL PASS")
