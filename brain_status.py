"""brain_status.py — the brain-stage ledger (PROOF-FIX 1, 2026-11-16).

The proof audit's ugliest finding was not that the v89 brain stages
failed — it was that they failed SILENTLY: the Story Analyst died on
HTTP 413, the pipeline directed with the pre-v89 deterministic
director, and the delivered job read as if the new brain had worked.
A fallback is a legitimate engineering choice; presenting it as
brain work is not (the honest-actions rule).

Every LLM brain stage now records its outcome here the moment it
succeeds or falls back. The record prints a greppable log line at
record time AND rides on the result dict (`brain_status`) into the
job's QC summary / delivery note, so a FALLBACK is labelled
FALLBACK wherever the job is reported. One ledger per process —
the runner serves one job per process, so the ledger IS the job's.
"""

_records = []          # [{stage, status, detail}] in call order
_latest = {}           # stage -> record (last outcome wins)


def record(stage, ok, detail=""):
    """Note one brain stage's outcome. ok=True: the LLM stage really
    ran. ok=False: the deterministic fallback carried the work —
    `detail` says why (the exception's first words)."""
    rec = {"stage": str(stage),
           "status": "OK" if ok else "FALLBACK",
           "detail": str(detail or "")[:160]}
    _records.append(rec)
    _latest[stage] = rec
    print(f"BRAIN-STAGE {rec['stage']}: {rec['status']}"
          + (f" — {rec['detail']}" if rec['detail'] else ""))
    return rec


def summary():
    """{stage: {status, detail}} — the result-dict form."""
    return {s: {"status": r["status"], "detail": r["detail"]}
            for s, r in _latest.items()}


def fallbacks():
    """[stage, ...] currently in FALLBACK state."""
    return [s for s, r in _latest.items() if r["status"] == "FALLBACK"]


def line():
    """One-line human summary for delivery notes / QC summaries:
    'Brain: story-analyst OK · visual-director FALLBACK (LLM failed:
    413) · editing-director OK'. Empty string when nothing ran."""
    if not _latest:
        return ""
    parts = []
    for stage, r in _latest.items():
        p = f"{stage} {r['status']}"
        if r["status"] == "FALLBACK" and r["detail"]:
            p += f" ({r['detail']})"
        parts.append(p)
    return "Brain: " + " · ".join(parts)


def reset():
    """Tests only — production processes are one-job-lived."""
    _records.clear()
    _latest.clear()
