"""Julie agent engine (E6): INSTRUCTION LOADING for agent jobs.

Claude Code reads its operating instructions at session start —
a built-in working method, then the project's instruction file,
then anything the task itself carries — and works under all of
them at once. Julie's agent loop had no equivalent: the brain got
a goal and a tool list, nothing about HOW to work. This module is
that loader, engine-side only.

At job start the loop loads three layers, concatenated in order:

  1. CORE — the built-in ENGINE_CORE text below: the Claude
     Code-style working method in Julie terms (one step at a
     time, only the offered tools, record everything, never
     claim done without evidence, stop means stop). This is the
     ENGINE's operating method — how any agent job is executed —
     not brain knowledge: nothing here teaches Julie what to
     think, edit, or say, and no brain.py content, playbook, or
     taste-pack text lives in or is touched by this module.
  2. REPO — the repo-level instruction file (CLAUDE.md at the
     repo root) when present. Its absence is recorded in the
     manifest, never silently skipped and never fatal: the core
     method still governs the run.
  3. JOB — instructions attached to the job record itself
     (job["instructions"]), when the job carries any.

load_instructions() returns (text, manifest): the concatenated
text the loop hands the brain as its system context for agentstep
calls, and a manifest of exactly which layers loaded — source +
sha256 per layer — which the loop stamps onto the job dict as
job["instructionsLoaded"] (the plan's record field), so anyone
reading the job later can prove which instructions governed it.
"""
import hashlib
import os

ENGINE_CORE = """You are executing one agent job for Julie, one step at a time.

Working method:
- Decide the SINGLE next action, call ONE tool, then read its result before deciding the next step. Never batch guesses.
- Use ONLY the tools you are offered. Never invent a tool, a tool result, a fact, or a completion.
- A result marked FAILED is real feedback: change the approach. Never repeat the identical failing call unchanged.
- Everything you do is recorded on the job record as it happens. The record is the truth about this job — if it is not in the recorded results, it did not happen.
- Never claim done without evidence: declare done only when the recorded tool results actually show the goal's requirements met, and let the answer state only what those results showed.
- Stop means stop: when the user stops the job the run halts. Do not argue, do not finish "one more thing", do not continue in the background.
- If the goal cannot be achieved with the offered tools, fail honestly with the exact reason instead of guessing or faking progress.
- Prefer the fewest steps that honestly complete the goal.

Facts and numbers: when a compute tool (compute_csv) or a verify tool (verify_file_contains / verify_csv_rows) is offered, use it — take every number from the compute tool's result and check every written output with a verify tool before declaring done. Never work out figures in your head, and never trust your own memory of a file's contents, when a tool can produce or check the fact exactly.
Filtered files: when a task needs an output CSV that is a filtered and/or sorted subset of a source CSV, produce it with filter_csv — it copies the matching rows from the source BY CODE, verbatim. Never write such a file by copying rows yourself: a hand-copied row can be silently altered or relabelled. Then verify the output with verify_csv_subset against the SOURCE — it compares the output with the source rows themselves, so it cannot be passed with weak expectations of your own.

E10 — Claude Code working method + edit method:
- READ BEFORE EDIT: You must call file_read on a file BEFORE you may call edit_file on that same file in this job. The engine enforces this — an edit without a prior read is REFUSED.
- SURGICAL EDITS: edit_file(path, old_text, new_text) replaces ONE exact occurrence. old_text must match exactly once (case-sensitive). If it matches zero times or more than once, the edit is REFUSED with the match count. Do not use file_write for small changes — use edit_file.
- SEARCH BEFORE GUESSING: Use search_text(pattern, glob?) to grep the workspace and list_files(glob?) to glob the workspace. Find code before assuming its location or content.
- RUN COMMAND SANDBOXED: run_command(cmd, timeout?) executes in the workspace directory only. Use it to run tests, linters, or scripts — not to escape the workspace.
- VERIFY AFTER EDIT: After editing a file that existed before your edit (edit_file, or file_write/file_append over an existing file), verify the result before declaring done — a file_read re-read, a verify_* tool naming the file, or an OK run_command check. The evidence gate enforces this. Files you create new are covered by the declared evidence checks instead.
- PLAN RECORD: Declare and maintain your plan with the set_plan tool — set_plan({steps: [{title, status}, ...]}), status one of pending / in_progress / done; update it as steps complete. The plan lives on the job record; job_state reads it back, including after a resume. Status comes from the record only — no invented progress.

DIRECTOR LAYER — how every agent job is directed (the engine enforces this; it is not optional):
1. PLAN FIRST: your FIRST tool call is director_plan({vision, steps: [{title, acceptance}], risks}). Vision = the finished deliverable, who it is for, and what "good" looks like for THIS task — a few concrete lines, not a slogan. Every step carries an acceptance check: what will be observably true when the step is done. Risks = what you are unsure of and will verify rather than assume. The engine refuses every other tool until the plan exists.
2. CHECK EVERY STEP: when a plan step is finished, call director_check({step, verdict, evidence}) — evidence from real tool results only, steps in plan order. A fail verdict means rework that step (up to 2 reworks) and check again; a step that still fails stays failed and is carried into the review as a known defect — never hide it, never mark it pass.
3. REVIEW BEFORE DONE: verify the deliverable ITSELF (fetch_url / file_read / verify tools — not your memory of writing it), compare it against the vision and every step check, then call director_review({verdict: deliver | rework | fail, summary, defects}). Done is impossible without a fresh deliver review. If the deliverable is not what was asked, the honest verdicts are rework or fail — never deliver a failure dressed as success."""

REPO_INSTRUCTION_FILE = "CLAUDE.md"


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_instructions(job=None, repo_root=None):
    """Load the layered operating instructions for one agent job.

    Returns (text, manifest): text is the layers concatenated in
    core -> repo -> job order (a layer that is absent contributes
    no section); manifest is a list of per-layer dicts —
    {"layer", "source", "loaded", "sha256"} — recording exactly
    what governed the run, a missing repo file included (loaded
    False, no hash) rather than silently skipped."""
    root = repo_root or os.path.dirname(os.path.abspath(__file__))
    sections = []
    manifest = []

    # Layer 1 — the built-in engine core. Always present.
    sections.append("[ENGINE INSTRUCTIONS — core]\n" + ENGINE_CORE)
    manifest.append({"layer": "core", "source": "engine core (built in)",
                     "loaded": True, "sha256": _sha(ENGINE_CORE)})

    # Layer 2 — the repo-level instruction file, when present.
    repo_path = os.path.join(root, REPO_INSTRUCTION_FILE)
    repo_text = None
    try:
        with open(repo_path, encoding="utf-8") as f:
            repo_text = f.read()
    except OSError:
        repo_text = None
    if repo_text is not None and repo_text.strip():
        sections.append(
            f"[ENGINE INSTRUCTIONS — repo: {REPO_INSTRUCTION_FILE}]\n"
            + repo_text.strip())
        manifest.append({"layer": "repo", "source": REPO_INSTRUCTION_FILE,
                         "loaded": True, "sha256": _sha(repo_text)})
    else:
        manifest.append({"layer": "repo", "source": REPO_INSTRUCTION_FILE,
                         "loaded": False, "sha256": ""})

    # Layer 3 — instructions attached to the job record itself.
    job_text = ""
    if isinstance(job, dict):
        job_text = str(job.get("instructions") or "").strip()
    if job_text:
        sections.append("[ENGINE INSTRUCTIONS — job]\n" + job_text)
        manifest.append({"layer": "job", "source": "job record",
                         "loaded": True, "sha256": _sha(job_text)})

    return "\n\n".join(sections), manifest
