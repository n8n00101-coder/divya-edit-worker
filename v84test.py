"""v84test.py — Julie v84 mandated test suite (17 tests).

Run: python3 v84test.py   (exit 0 = all pass)
Offline by design: vision is stubbed, footage is generated locally
with ffmpeg, memory/KB use temp SQLite files. Each test prints one
PASS/FAIL line; a failure raises at the end with the list.
"""

import asyncio
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
        print(f"PASS  {name}")
    except Exception as e:
        RESULTS.append((name, False, str(e)[:200]))
        print(f"FAIL  {name}: {str(e)[:200]}")


def _mk_clip(path, color="red", seconds=2, tone=440):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", f"color=c={color}:s=540x960:d={seconds}:r=15",
                    "-f", "lavfi", "-i", f"sine=frequency={tone}:d={seconds}",
                    "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "44100", str(path)], check=True)
    return str(path)


def _missing(mod):
    try:
        __import__(mod)
        return False
    except ImportError:
        return True


TD = tempfile.mkdtemp(prefix="v84test_")
CLIP_A = _mk_clip(os.path.join(TD, "a.mp4"), "red")
CLIP_B = _mk_clip(os.path.join(TD, "b.mp4"), "red")  # same frames as A
CLIP_C = _mk_clip(os.path.join(TD, "c.mp4"), "blue", tone=660)


# 1 — QC runs when spec extraction fails (unconditional report)
def t1():
    import qc_core
    rep = qc_core.unconditional_long_report(
        CLIP_A, {"kind": "long"}, [], [[{"title": "x", "vo": "hello"}]],
        rounds=0, fixes=[], workdir=TD)
    assert rep["spec_present"] is False
    assert Path(TD, "compliance_report.json").exists()
    rules = {c["rule"] for c in rep["checks"]}
    assert "ST-1" in rules and "ST-2" in rules, rules
    assert all(c["status"] in ("PASS", "FAIL", "WARN", "UNVERIFIED")
               for c in rep["checks"])
check("01 QC runs when spec extraction fails", t1)


# 2 — Shorts still work (doc engine plan enforcement intact)
def t2():
    import doc
    assert callable(doc.make_video)
    p = {"scenes": [{"no": 1, "title": "HOOK", "vo": "A calm fact.",
                     "visual": "clock", "d": 4}],
         "topic": "compromise in daily life", "render_config": {"kind": "short"}}
    doc._enforce_plan(p, "compromise")
    assert "plan_fix_rounds" in p and isinstance(p["plan_fix_rounds"], int)
check("02 Shorts engine intact (plan enforcement + rounds field)", t2)


# 3 — Long pipeline still works (its own stub self-test)
def t3():
    import long_video
    long_video._self_test()
check("03 Long pipeline self-test", t3)


# 4 — v83 functionality intact
def t4():
    import doc
    import clone_tts  # noqa
    assert "tripti" in doc.CLONE_VOICES
    import spec_engine
    assert hasattr(spec_engine, "extract_spec")
check("04 v83 clone voice intact", t4)


# 5 — Nine-provider rotation intact (providers.py untouched)
def t5():
    import providers
    assert len(providers.PROVIDERS) == 9, len(providers.PROVIDERS)
    names = {p[0] for p in providers.PROVIDERS}
    assert {"groq", "gemini", "openrouter"} <= names
check("05 Nine-provider rotation intact", t5)


# 6 — Correction round count is accurate
def t6():
    import compliance as comp
    rep = comp.build_report([], {}, [], [], rounds=2, fixes=["a", "b"])
    assert rep["fix_rounds"] == 2
    import doc
    p = {"scenes": [{"no": 1, "title": "HOOK", "vo": "A calm fact.",
                     "visual": "clock", "d": 4}],
         "topic": "compromise in daily life", "render_config": {"kind": "short"}}
    doc._enforce_plan(p, "compromise")
    # the banned HOOK title forces at least one repair round
    assert p["plan_fix_rounds"] >= 1, p["plan_fix_rounds"]
check("06 Correction round count accurate", t6)


# 7 — Maximum correction rounds respected
def t7():
    import qc_core
    calls = {"n": 0}

    def check_fn():
        return [{"rule": "X", "status": "FAIL", "detail": "", "scene": None}]

    def correct_fn(failed, rnd):
        calls["n"] += 1
        return ["attempted"]
    checks, rounds, fixes, ok = qc_core.bounded_correct(
        check_fn, correct_fn, max_rounds=2)
    assert rounds == 2 and calls["n"] == 2 and ok is False
check("07 Max correction rounds (2) respected", t7)


# 8 — Irrelevant B-roll rejected (+ reason recorded in memory)
def t8():
    import broll_verify
    import edit_memory
    mem = edit_memory.EditMemory(os.path.join(TD, "m8.db"))
    v = broll_verify.BrollVerifier(
        call_budget=18, memory=mem, job_id="jobA",
        verifier=lambda frames, narr, why: {"verdict": "fail",
                                            "reason": "frames show a beach; narration is about crowds"})
    chosen, results = v.verify_scene(
        [{"id": "clipBeach", "path": CLIP_C}],
        "people feel alone in a crowded city", "crowd visual", workdir=TD)
    assert chosen is None and results[0]["verdict"] == "fail"
    assert mem.was_rejected("clipBeach") is not None
    mem.close()
check("08 Irrelevant B-roll rejected with reason", t8)


# 9 — Vision API limits respected
def t9():
    import broll_verify
    v = broll_verify.BrollVerifier(
        call_budget=2,
        verifier=lambda frames, narr, why: {"verdict": "uncertain", "reason": "stub"})
    for i, clip in enumerate((CLIP_A, CLIP_C)):
        v.verify_candidate({"id": f"c{i}", "path": clip},
                           f"narration number {i} unique", "why", workdir=TD)
    verdict, reason, _ = v.verify_candidate(
        {"id": "cX", "path": CLIP_A}, "a third distinct narration", "why", workdir=TD)
    assert v.calls_made <= 2, v.calls_made
    assert verdict == "unverified", verdict
check("09 Vision call budget respected", t9)


# 10 — Cache avoids repeat checks
def t10():
    import broll_verify
    v = broll_verify.BrollVerifier(
        call_budget=18, cache_path=os.path.join(TD, "vcache.json"),
        verifier=lambda frames, narr, why: {"verdict": "pass", "reason": "ok"})
    a = v.verify_candidate({"id": "k1", "path": CLIP_A}, "same narration", "same why", workdir=TD)
    b = v.verify_candidate({"id": "k1", "path": CLIP_A}, "same narration", "same why", workdir=TD)
    assert a[2] is False and b[2] is True and v.calls_made == 1, (a, b, v.calls_made)
check("10 Verdict cache avoids repeat vision calls", t10)


# 11 — Repeated footage detected
def t11():
    import broll_verify
    groups = broll_verify.find_repeated(
        [{"id": "one", "path": CLIP_A}, {"id": "two", "path": CLIP_B},
         {"id": "three", "path": CLIP_C}], workdir=TD)
    flat = [set(g) for g in groups]
    assert any({"one", "two"} <= g for g in flat), groups
check("11 Repeated footage detected by frame hash", t11)


# 12 — Multiple endings flagged
def t12():
    import doc_structure
    chapters = [
        [{"title": "Start", "vo": "In conclusion, stay tuned for more"}],
        [{"title": "Middle", "vo": "More evidence here"}],
        [{"title": "End", "vo": "The final word"}]]
    checks = {c["rule"]: c for c in doc_structure.structure_lints(chapters)}
    assert checks["ST-1"]["status"] == "FAIL", checks["ST-1"]
    good = [[{"title": "Start", "vo": "A question opens"}],
            [{"title": "End", "vo": "In conclusion, the answer"}]]
    checks2 = {c["rule"]: c for c in doc_structure.structure_lints(good)}
    assert checks2["ST-1"]["status"] == "PASS", checks2["ST-1"]
check("12 Multiple endings flagged by structure lint", t12)


# 13 — Director log-only = zero plan changes
def t13():
    import director
    plan = [{"no": 1, "visual": "clock", "vo": "Time passes slowly here.", "d": 3,
             "transition": "dissolve", "effect": "zoom", "fx": "sparkle", "sfx": "whoosh"},
            {"no": 2, "visual": "clock", "vo": "Again.", "d": 4},
            {"no": 3, "visual": "face", "vo": "The turn.", "d": 5, "arc_role": "turning_point"},
            {"no": 4, "visual": "sunrise", "vo": "Payoff.", "d": 5, "arc_role": "payoff"}]
    before = copy.deepcopy(plan)
    log = director.analyse_plan(plan)
    assert plan == before, "Director mutated the plan"
    assert log["mode"] == "LOG-ONLY" and len(log["recommendations"]) >= 3
    assert len(log["silence_map"]) >= 1 and len(log["music_curve"]) == 4
check("13 Director log-only, zero plan mutation", t13)


# 14 — Editing memory works across two jobs
def t14():
    import edit_memory
    mem = edit_memory.EditMemory(os.path.join(TD, "m14.db"))
    mem.record_rejection("job1", "s3", "clipBeach",
                         "people feel alone in a crowd",
                         "clip shows an empty beach, unrelated")
    avoid, rec = mem.should_avoid(
        "clipBeach", "people feel alone even in a crowd of strangers")
    assert avoid and "beach" in rec["reason"]
    # different context -> not avoided (no over-blocking)
    avoid2, _ = mem.should_avoid("clipBeach", "ocean waves at sunrise, coastal weather")
    assert avoid2 is False
    # via the verifier: Job 2 rejects at zero vision cost
    import broll_verify
    calls = {"n": 0}

    def counting(frames, narr, why):
        calls["n"] += 1
        return {"verdict": "pass", "reason": "ok"}
    v = broll_verify.BrollVerifier(call_budget=18, memory=mem, job_id="job2",
                                   verifier=counting)
    verdict, reason, _ = v.verify_candidate(
        {"id": "clipBeach", "path": CLIP_C},
        "people feel alone in a crowd today", "crowd visual", workdir=TD)
    assert verdict == "fail" and calls["n"] == 0 and v.calls_made == 0
    mem.close()
check("14 Editing memory across two jobs", t14)


# 15 — Knowledge Base rules load + search
def t15():
    import edit_memory
    mem = edit_memory.EditMemory(os.path.join(TD, "m15.db"))
    n = edit_memory.seed_knowledge_base(mem)
    rules = mem.load_rules()
    assert n >= 14 and len(rules) >= 14, (n, len(rules))
    ids = {r["rule_id"] for r in rules}
    assert {"ST-1", "VF-1", "AU-1", "QC-1", "QC-2"} <= ids
    hits = mem.search_rules("silence")
    assert any(r["rule_id"] == "AU-2" for r in hits), hits
    assert all(r["approval_status"] == "approved" for r in rules)
    mem.close()
check("15 Knowledge Base rules load and search", t15)


# 16 — Learning proposals require approval
def t16():
    import edit_memory
    import learning_loop
    mem = edit_memory.EditMemory(os.path.join(TD, "m16.db"))
    for j in ("j1", "j2"):
        mem.record_qc_failure(j, "R12", "frozen frames")
        mem.record_qc_failure(j, "R12", "frozen frames again")
    d = learning_loop.build_digest(mem)
    assert d["approval_required"] is True and d["proposals"]
    pid = d["proposals"][0]["id"]
    assert learning_loop.activate(mem, pid) is False  # gate holds
    assert learning_loop.approve(mem, pid) is True
    assert learning_loop.activate(mem, pid) is True
    assert any(r["rule_id"] == f"LRN-{pid}" for r in mem.load_rules())
    mem.close()
check("16 Learning proposals require approval", t16)


# 17 — Missing optional tools do not crash the pipeline
def t17():
    # PySceneDetect and faster-whisper are NOT installed in this
    # environment; nothing in the v84 layer may require them (or
    # OpenCV). Scene detection uses ffmpeg, which is present.
    assert _missing("scenedetect") and _missing("faster_whisper")
    import broll_verify
    import director
    import doc_structure
    import edit_memory
    import learning_loop
    import qc_core  # noqa — all import cleanly without the optionals
    # vision stack down -> UNVERIFIED, never a crash, never a pass
    def boom(frames, narr, why):
        raise RuntimeError("no vision provider available")
    v = broll_verify.BrollVerifier(call_budget=5, verifier=boom)
    verdict, reason, _ = v.verify_candidate(
        {"id": "z1", "path": CLIP_A}, "narration", "why", workdir=TD)
    assert verdict == "unverified", verdict
    # unwritable memory path -> disabled gracefully, reads safe
    mem = edit_memory.EditMemory("/nonexistent-dir-xyz/m.db")
    assert mem.ok is False and mem.load_rules() == []
    assert mem.should_avoid("anything", "any context") == (False, None)
check("17 Missing optional tools degrade gracefully", t17)


if __name__ == "__main__":
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\nv84test: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS")
    if failed:
        print("FAILED:", "; ".join(failed))
        sys.exit(1)
    print("v84test: ALL PASS")
