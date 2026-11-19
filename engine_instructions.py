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
- Prefer the fewest steps that honestly complete the goal."""

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
