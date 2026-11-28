"""Hark gates — deterministic editing checks mined from Hark outputs
and Blind's 32-mistake diagnosis of Julie films (2026-11-13).

Each rule maps to a named, observed defect:
- HARK-CLIP-REUSE: same clip repeated in one edit.
- HARK-NUMBER-MATCH: on-screen number differs from the spoken number.
- HARK-HOOK-3S: opening beat is not footage with a scored hook line.
- HARK-PACING: shots outside the cut-density bounds (static drag or
  blink cuts).
- HARK-ENDINGS: more than one ending/CTA beat in a single film.
- HARK-AUDIO: true peak near clipping or long silent gaps.

Pure functions over a plan dict; measured values (loudness, gaps)
come from existing tools (audio_loudness, pause_cut_points). A FAIL
blocks delivery as success — rework or honest failure, never a
rationalized defect.
"""

import re

import hooks_lib

MAX_SHOT_S = 8.0
MIN_SHOT_S = 0.8
# Calibrated 2026-11-28: the hooks_lib panel rewards statistic bait
# (specificity), so honest emotional hooks cap near 46 while a
# channel-welcome line scores 21. Floor 40 keeps discrimination
# without forcing invented numbers (a Blind-listed defect).
HOOK_MIN_SCORE = 40
TRUE_PEAK_MAX_DB = -1.0
SILENCE_GAP_MAX_S = 1.5

_END_WORDS = ("stay tuned", "next episode", "next video", "subscribe",
              "follow for", "see you in the next")


def _check(rule, ok, detail, scene=None):
    return {"rule": rule, "status": "PASS" if ok else "FAIL",
            "detail": detail, "scene": scene}


def _clip_id(scene):
    for key in ("clip", "file", "source", "footage", "media"):
        value = scene.get(key)
        if value:
            return str(value)
    return None


def check_clip_reuse(scenes):
    seen = {}
    reused = []
    for i, scene in enumerate(scenes or []):
        clip = _clip_id(scene)
        if not clip or scene.get("repeat_ok"):
            continue
        if clip in seen:
            reused.append((clip, seen[clip], i))
        else:
            seen[clip] = i
    if reused:
        detail = "; ".join(
            f"clip {c} at scenes {a} and {b}" for c, a, b in reused)
        return [_check("HARK-CLIP-REUSE", False, detail)]
    return [_check("HARK-CLIP-REUSE", True, "no clip repeats")]


_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text):
    out = set()
    for raw in _NUM_RE.findall(str(text or "")):
        out.add(raw.replace(",", ""))
    return out


def check_number_match(scenes):
    checks = []
    for i, scene in enumerate(scenes or []):
        overlay = scene.get("overlay") or scene.get("on_screen") or ""
        shown = _numbers(overlay)
        if not shown:
            continue
        spoken = _numbers(scene.get("vo") or scene.get("line") or "")
        # A runtime promise ("in 30 seconds") is packaging, not a
        # factual claim: exempt only when the scene declares it and
        # the film keeps it. Factual numbers must still be spoken.
        promise = scene.get("runtime_promise_s")
        if promise is not None:
            spoken = spoken | {str(int(float(promise)))}
        extra = shown - spoken
        checks.append(_check(
            "HARK-NUMBER-MATCH", not extra,
            ("on-screen number(s) not spoken: " + ", ".join(sorted(extra)))
            if extra else "on-screen numbers match the voice",
            scene=i))
    if not checks:
        checks.append(_check("HARK-NUMBER-MATCH", True,
                             "no on-screen numbers to match"))
    return checks


def _is_footage(scene):
    kind = str(scene.get("kind") or scene.get("type") or "").lower()
    if kind in ("footage", "video", "clip", "broll", "b-roll"):
        return True
    return _clip_id(scene) is not None


def check_hook_opening(scenes, min_score=HOOK_MIN_SCORE):
    if not scenes:
        return [_check("HARK-HOOK-3S", False, "no scenes")]
    first = scenes[0]
    # The declared hook is the opening line the viewer meets; body
    # VO is judged only when no hook is declared.
    line = str(first.get("hook") or first.get("vo") or
               first.get("line") or "")
    scored = hooks_lib.score_hook(line)
    ok = _is_footage(first) and scored["total"] >= min_score
    detail = (f"opening footage={_is_footage(first)} "
              f"hook score={scored['total']} band={scored['band']}")
    return [_check("HARK-HOOK-3S", ok, detail, scene=0)]


def check_pacing(scenes, max_shot_s=MAX_SHOT_S, min_shot_s=MIN_SHOT_S):
    bad = []
    for i, scene in enumerate(scenes or []):
        dur = scene.get("duration") or scene.get("dur_s")
        if dur is None:
            continue
        dur = float(dur)
        if dur > max_shot_s or dur < min_shot_s:
            bad.append((i, dur))
    if bad:
        detail = "; ".join(
            f"scene {i} is {d}s (bounds {min_shot_s}-{max_shot_s}s)"
            for i, d in bad)
        return [_check("HARK-PACING", False, detail)]
    return [_check("HARK-PACING", True, "all shots inside bounds")]


def _is_ending(scene):
    kind = str(scene.get("kind") or scene.get("label") or "").lower()
    if kind in ("end", "ending", "cta", "outro", "endcard"):
        return True
    text = str(scene.get("vo") or scene.get("line") or
               scene.get("overlay") or "").lower()
    return any(w in text for w in _END_WORDS)


def check_endings(scenes):
    endings = [i for i, s in enumerate(scenes or []) if _is_ending(s)]
    ok = len(endings) <= 1
    detail = (f"{len(endings)} ending beats at scenes {endings}"
              if endings else "no ending beat")
    return [_check("HARK-ENDINGS", ok, detail)]


def check_audio(loudness=None, silence_gaps=None):
    """loudness: dict from audio_loudness (true_peak_db). silence_gaps:
    list of gap seconds from pause analysis. Missing measurement is
    a FAIL — unmeasured audio never ships as checked."""
    checks = []
    peak = (loudness or {}).get("true_peak_db")
    if peak is None:
        checks.append(_check("HARK-AUDIO", False,
                             "true peak not measured"))
    else:
        checks.append(_check(
            "HARK-AUDIO", float(peak) <= TRUE_PEAK_MAX_DB,
            f"true peak {peak} dBTP (max {TRUE_PEAK_MAX_DB})"))
    gaps = [float(g) for g in (silence_gaps or [])]
    long_gaps = [g for g in gaps if g > SILENCE_GAP_MAX_S]
    checks.append(_check(
        "HARK-AUDIO", not long_gaps,
        (f"silent gaps over {SILENCE_GAP_MAX_S}s: {long_gaps}")
        if long_gaps else "no long silent gaps"))
    return checks


def hark_checks(plan):
    """All Hark gates over a plan dict: {scenes, loudness,
    silence_gaps}. Returns taste_pack-shaped check dicts."""
    plan = plan or {}
    scenes = plan.get("scenes") or []
    checks = []
    checks += check_clip_reuse(scenes)
    checks += check_number_match(scenes)
    checks += check_hook_opening(scenes)
    checks += check_pacing(scenes)
    checks += check_endings(scenes)
    checks += check_audio(plan.get("loudness"),
                          plan.get("silence_gaps"))
    return checks


def hark_critical_fails(checks):
    return [c for c in (checks or []) if c.get("status") == "FAIL"]


def register_hark_tools(reg):
    def _gate(args):
        plan = args.get("plan") or {}
        checks = hark_checks(plan)
        fails = hark_critical_fails(checks)
        return True, {"checks": checks, "fails": len(fails),
                      "delivery_allowed": not fails}

    reg.register(
        "hark_gate_check",
        "Run the Hark editing gates over a plan {scenes, loudness, "
        "silence_gaps}: clip reuse, spoken vs on-screen numbers, "
        "hook opening, pacing bounds, single ending, audio peak/gaps. "
        "delivery_allowed=false means rework, never ship as success. "
        "Read-only.",
        {"plan": {"type": "object", "required": True,
                  "desc": "plan dict with scenes list"}},
        _gate, mutating=False, needs_allow=False, timeout=15)
    return reg
