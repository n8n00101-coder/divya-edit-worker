"""qc_core.py — Julie v84 Stages 1-2 (P0): unconditional QC, truthful
round counting, and the bounded correction loop.

Why this module exists (Gap G-1/G-2): on the long path the whole
compliance run used to be gated on `spec is not None` — a spec
extraction crash silently removed ALL quality control — and both
engines wrote build_report(rounds=0) no matter how many correction
rounds had actually happened.

What lives here (all deterministic, no model calls):

- routing_log_line(): the Stage 1 observability line — which engine,
  which job type, spec present or not, which optional modules
  engaged — printed by the runner for every create job.
- unconditional_long_report(): builds a compliance report for a long
  video WITHOUT a spec: media audit + chapter checks + structural
  lints. Checks that cannot run are UNVERIFIED, never PASS.
- bounded_correct(): the correction loop contract — run check ->
  if FAIL and rounds remain, call the corrector -> re-check. Records
  the TRUE number of rounds attempted; stops at max_rounds; an
  uncorrectable defect is returned honestly in the final report.
"""

import json
import os


def routing_log_line(engine_name, job_kind, spec_present, modules):
    """Stage 1: one greppable line per job. modules: dict name->bool."""
    mods = ",".join(f"{k}={'on' if v else 'off'}"
                    for k, v in sorted((modules or {}).items()))
    return (f"[routing] engine={engine_name} job={job_kind} "
            f"spec={'yes' if spec_present else 'no'} modules: {mods}")


def unconditional_long_report(final_path, cfg, chapter_checks, chapter_scenes,
                              rounds, fixes, workdir=None, chapter_breaks=None):
    """Build (and optionally write) a compliance report with NO spec.
    Returns the report dict. requirement verdicts are empty — with no
    spec there are no per-requirement claims to judge, and this
    function will not invent any."""
    import compliance as comp
    cfg = cfg or {"kind": "long"}
    checks = list(chapter_checks or [])
    try:
        import doc_structure
        checks += doc_structure.structure_lints(chapter_scenes or [])
    except Exception as e:
        checks.append({"rule": "ST-1", "status": "UNVERIFIED",
                       "detail": f"structure lint could not run: {str(e)[:100]}",
                       "scene": None})
    try:
        mchecks, _minfo = comp.audit_media(
            final_path, cfg, [], chapter_breaks=chapter_breaks or [])
        # With no spec there is no render config: a size/aspect
        # verdict has nothing to compare against, so it is
        # UNVERIFIED — reporting it as FAIL (or PASS) would be a lie.
        if not cfg.get("width"):
            for c in mchecks:
                if c.get("rule") == "R-P4" and c.get("status") in ("PASS", "FAIL"):
                    c["status"] = "UNVERIFIED"
                    c["detail"] = ("render size not verifiable: no spec / "
                                   "render config on this job ("
                                   + str(c.get("detail"))[:60] + ")")
        checks += mchecks
    except Exception as e:
        checks.append({"rule": "R12", "status": "UNVERIFIED",
                       "detail": f"media audit could not run: {str(e)[:100]}",
                       "scene": None})
    report = comp.build_report([], cfg, checks, [], rounds, fixes)
    report["spec_present"] = False
    report["note"] = ("unconditional QC (v84): no prompt spec was "
                      "available, so requirement verdicts are empty; "
                      "every check present here actually ran, anything "
                      "that could not run is UNVERIFIED")
    if workdir:
        try:
            with open(os.path.join(workdir, "compliance_report.json"),
                      "w", encoding="utf-8") as f:
                json.dump(report, f, indent=1)
        except OSError:
            pass
    return report


def bounded_correct(check_fn, correct_fn, max_rounds=2):
    """The bounded correction contract (Stage 2).

    check_fn() -> list of check dicts (status FAIL = defect).
    correct_fn(failed_checks, round_no) -> fixes list (may raise —
    a raising corrector ends the loop and is reported).
    Returns (final_checks, rounds_used, fixes, corrected_bool).
    Rounds are counted as corrections ACTUALLY attempted, and the
    loop never exceeds max_rounds."""
    fixes = []
    rounds = 0
    checks = check_fn()
    failed = [c for c in checks if c.get("status") == "FAIL"]
    while failed and rounds < int(max_rounds):
        rounds += 1
        try:
            made = correct_fn(failed, rounds) or []
        except Exception as e:
            fixes.append(f"round {rounds}: corrector failed: {str(e)[:120]}")
            break
        fixes += [str(x) for x in made]
        checks = check_fn()
        failed = [c for c in checks if c.get("status") == "FAIL"]
    return checks, rounds, fixes, not failed


async def bounded_correct_async(check_fn, correct_coro, max_rounds=2):
    """v85: the same bounded contract for pipelines that live inside
    an event loop (long_video.make_long_video): correct_coro is an
    async corrector (chapter re-renders are async doc.make_video
    calls). Semantics identical to bounded_correct — true round
    counts, hard stop at max_rounds, a raising corrector ends the
    loop and is reported in fixes."""
    fixes = []
    rounds = 0
    checks = check_fn()
    failed = [c for c in checks if c.get("status") == "FAIL"]
    while failed and rounds < int(max_rounds):
        rounds += 1
        try:
            made = await correct_coro(failed, rounds) or []
        except Exception as e:
            fixes.append(f"round {rounds}: corrector failed: {str(e)[:120]}")
            break
        fixes += [str(x) for x in made]
        checks = check_fn()
        failed = [c for c in checks if c.get("status") == "FAIL"]
    return checks, rounds, fixes, not failed


if __name__ == "__main__":
    print(routing_log_line("doc", "long", False,
                           {"spec_qc": False, "unconditional_qc": True}))
    state = {"n": 0}

    def check():
        return [{"rule": "X", "status": "FAIL" if state["n"] < 2 else "PASS",
                 "detail": "", "scene": None}]

    def fix(failed, rnd):
        state["n"] += 1
        return [f"fix attempt {rnd}"]

    checks, rounds, fixes, ok = bounded_correct(check, fix, max_rounds=2)
    assert rounds == 2 and ok, (rounds, ok)
    state["n"] = 0
    checks, rounds, fixes, ok = bounded_correct(check, lambda f, r: [], max_rounds=2)
    assert rounds == 2 and not ok, (rounds, ok)
    print("qc_core self-check OK")
