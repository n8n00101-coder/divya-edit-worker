"""video_director_gates.py — Director Layer gates for Julie video jobs.

Mirrors the agent-job Director Layer on the video path: a taste-profile
film needs a vision + per-beat acceptance record before render, checks
with evidence after render, and a final review. Delivery is allowed
only on a fresh `deliver` review. Failures are carried into defects
mechanically; the brain cannot hide them by wording.
"""

import time

import brain_quality
import taste_pack

CRITICAL_RULES = {
    "TASTE-SOURCE", "TASTE-SOURCE-CARD", "TASTE-LABEL", "TASTE-GRAPHIC",
    "TASTE-BANNED-VISUAL", "TASTE-HOOK", "TASTE-QUERY", "TASTE-CAPTION",
    "TASTE-VARIETY", "TASTE-FOOTAGE", "TASTE-AUDIO", "TASTE-FRAME",
    "TASTE-DURATION",
    "BRAIN-HOOK", "BRAIN-RESTATEMENT", "BRAIN-CLAIM", "CRITIC-HOOK",
    "FG-SHARE", "FG-FACT", "FG-TEASE", "VHIST", "MQ-LRA", "MQ-SILENCE",
    "MQ-BLACK", "MQ-FREEZE", "MQ-BLANK", "MQ-REPEAT", "MQ-AVSYNC",
    "R11", "MQ-LOUD",
}


def _now():
    return int(time.time() * 1000)


def build_record(plan, profile=None, brief=""):
    profile = profile or taste_pack.PROFILES["wtu_long_sheet"]
    scenes = (plan or {}).get("scenes") or []
    brain_quality.enrich_visuals(scenes, profile)
    topic = str((plan or {}).get("topic") or (plan or {}).get("title") or brief or "the topic")[:120]
    vision = (
        f"{profile['channel']} film about {topic}: every beat shows its line; "
        "sourced facts carry source cards; captions stay readable; "
        "delivery only after checks pass."
    )[:300]
    steps = []
    for i, scene in enumerate(scenes[:16]):
        title = str(scene.get("label") or scene.get("promise") or
                    f"Beat {i + 1}")[:48]
        acceptance = str(scene.get("acceptance") or
                         "frame shows the line subject; captions synced")[:240]
        steps.append({"title": title, "acceptance": acceptance})
    if not steps:
        steps = [{"title": "Beat 1", "acceptance": "frame shows the line subject"}]
    return {
        "profile": profile["id"],
        "plan": {
            "vision": vision,
            "steps": steps,
            "risks": [
                "free-brain decision quality varies; critic and frame QC must catch weak beats",
                "stock footage may miss a beat; re-plan instead of islanding it",
                "unsourced claims must be sourced or removed before delivery",
            ],
            "at": _now(),
        },
        "checks": [],
        "reviews": [],
        "rework_passes": 0,
    }


def validate_record(record):
    errors = []
    if not isinstance(record, dict):
        return ["video director record missing"]
    plan = record.get("plan") or {}
    if not str(plan.get("vision") or "").strip():
        errors.append("video director plan has no vision")
    steps = plan.get("steps") or []
    if not steps:
        errors.append("video director plan has no steps")
    for i, step in enumerate(steps, 1):
        if not str(step.get("title") or "").strip():
            errors.append(f"video director step {i} has no title")
        if not str(step.get("acceptance") or "").strip():
            errors.append(f"video director step {i} has no acceptance")
    if not taste_pack.get_profile(record.get("profile")):
        errors.append("video director record has no known taste profile")
    return errors


def ensure_record(plan, profile=None, brief=""):
    profile = profile or taste_pack.profile_for_job(brief, (plan or {}).get("render_config") or {})
    if not profile:
        return None
    rec = (plan or {}).get("video_director")
    if validate_record(rec):
        rec = build_record(plan, profile, brief)
        plan["video_director"] = rec
    plan["taste_profile"] = profile["id"]
    return rec


def require_record(plan, cfg=None, brief=""):
    cfg = cfg or (plan or {}).get("render_config") or {}
    if not taste_pack.is_taste_job(cfg, brief):
        return None
    profile = taste_pack.profile_for_job(brief, cfg)
    rec = ensure_record(plan, profile, brief)
    errors = validate_record(rec)
    if errors:
        raise RuntimeError("TASTE DIRECTOR GATE: " + "; ".join(errors))
    return rec


def _is_critical(check):
    return check.get("rule") in CRITICAL_RULES or str(check.get("rule") or "").startswith("TASTE-")


def checks_from_bundle(plan, profile=None, compliance_checks=None,
                       frame_qc=None, frame_taste=None, media_info=None):
    profile = profile or taste_pack.PROFILES["wtu_long_sheet"]
    scenes = (plan or {}).get("scenes") or []
    all_checks = []
    all_checks.extend(taste_pack.profile_checks(plan, profile))
    all_checks.extend(brain_quality.critic_review(plan, profile))
    all_checks.extend(compliance_checks or [])
    if frame_qc:
        for flaw in frame_qc.get("flaws") or []:
            all_checks.append({"rule": "TASTE-FRAME", "status": "FAIL",
                               "detail": str(flaw)[:240], "scene": None})
    taste_by_beat = {}
    for beat in (frame_taste or {}).get("beats") or []:
        taste_by_beat[int(beat.get("beat") or 0)] = beat
        if beat.get("status") in ("FAIL", "WARN"):
            all_checks.append({
                "rule": "TASTE-FRAME", "status": "FAIL",
                "detail": f"frame taste {beat.get('status')}: {beat.get('note') or ''}"[:240],
                "scene": beat.get("beat")})
        elif beat.get("status") == "UNVERIFIED" and profile.get("requires_vision_qc"):
            all_checks.append({
                "rule": "TASTE-FRAME", "status": "FAIL",
                "detail": f"frame taste UNVERIFIED: {beat.get('note') or 'vision unavailable'}"[:240],
                "scene": beat.get("beat")})
    if media_info:
        lra = media_info.get("lra")
        if lra is not None:
            ok = float(lra) >= float(profile.get("lra_min") or 0)
            all_checks.append({
                "rule": "TASTE-AUDIO", "status": "PASS" if ok else "FAIL",
                "detail": f"LRA {float(lra):.2f} (floor {float(profile.get('lra_min') or 0):.1f})",
                "scene": None})
        dur = media_info.get("duration")
        if dur is not None:
            dmin = float(profile.get("duration_min_s") or 0)
            dmax = float(profile.get("duration_max_s") or 0)
            ok = (not dmin or float(dur) >= dmin) and \
                 (not dmax or float(dur) <= dmax)
            all_checks.append({
                "rule": "TASTE-DURATION", "status": "PASS" if ok else "FAIL",
                "detail": f"duration {float(dur):.1f}s (profile {dmin:.0f}-{dmax:.0f}s)",
                "scene": None})
    director_checks = []
    for i, scene in enumerate(scenes, 1):
        beat_fails = [c for c in all_checks
                      if c.get("status") == "FAIL" and _is_critical(c)
                      and (c.get("scene") in (i, str(i)))]
        global_fails = [c for c in all_checks
                        if c.get("status") == "FAIL" and _is_critical(c)
                        and c.get("scene") is None]
        fails = beat_fails + (global_fails if i == 1 else [])
        if fails:
            evidence = "; ".join(f"{c.get('rule')}: {c.get('detail')}" for c in fails[:3])[:240]
            director_checks.append({"step": i, "verdict": "fail",
                                    "evidence": evidence, "at": _now()})
        else:
            tb = taste_by_beat.get(i) or {}
            evidence = str(tb.get("note") or "profile, compliance and frame checks pass")[:240]
            director_checks.append({"step": i, "verdict": "pass",
                                    "evidence": evidence, "at": _now()})
    return director_checks, all_checks


def final_review(record, director_checks, all_checks=None):
    record = record or {}
    fails = [c for c in director_checks or [] if c.get("verdict") == "fail"]
    defects = [f"step {c.get('step')}: {c.get('evidence')}"[:120] for c in fails[:6]]
    critical = [c for c in all_checks or []
                if c.get("status") == "FAIL" and _is_critical(c)]
    for c in critical[:6]:
        d = f"{c.get('rule')}: {c.get('detail')}"[:120]
        if d not in defects:
            defects.append(d)
    passes = int(record.get("rework_passes") or 0)
    if not fails and not critical:
        return {"verdict": "deliver",
                "summary": "All taste director checks pass; film may deliver.",
                "defects": [], "at": _now()}
    if passes < 2:
        return {"verdict": "rework",
                "summary": "Taste checks failed; re-plan failing beats and re-render within the bounded rework budget.",
                "defects": defects[:6], "at": _now()}
    return {"verdict": "fail",
            "summary": "Taste checks still fail after bounded rework; do not deliver as success.",
            "defects": defects[:6], "at": _now()}


def apply_checks_and_review(plan, profile=None, compliance_checks=None,
                            frame_qc=None, frame_taste=None, media_info=None):
    profile = profile or taste_pack.profile_for_job("", (plan or {}).get("render_config") or {})
    rec = ensure_record(plan, profile)
    if not rec:
        return None
    dchecks, all_checks = checks_from_bundle(
        plan, profile, compliance_checks, frame_qc, frame_taste, media_info)
    rec["checks"] = (rec.get("checks") or []) + dchecks
    review = final_review(rec, dchecks, all_checks)
    rec["reviews"] = (rec.get("reviews") or []) + [review]
    rec["review"] = review
    plan["video_director"] = rec
    plan["taste_checks"] = all_checks
    return review


def delivery_allowed(plan, cfg=None):
    cfg = cfg or (plan or {}).get("render_config") or {}
    if not taste_pack.is_taste_job(cfg, ""):
        return True, ""
    rec = (plan or {}).get("video_director") or {}
    errors = validate_record(rec)
    if errors:
        return False, "; ".join(errors)
    reviews = rec.get("reviews") or []
    if not reviews:
        return False, "no taste director review"
    latest = reviews[-1]
    if latest.get("verdict") != "deliver":
        return False, f"taste review verdict is {latest.get('verdict')}: {latest.get('summary')}"
    return True, ""


def rework_actions(checks):
    actions = []
    for c in checks or []:
        if c.get("status") != "FAIL":
            continue
        rule = str(c.get("rule") or "")
        if rule in ("TASTE-SOURCE", "BRAIN-CLAIM", "FG-FACT"):
            actions.append("source the claim from retrieved research or remove the claim")
        elif rule in ("TASTE-FOOTAGE", "FG-SHARE", "TASTE-QUERY"):
            actions.append("re-plan the beat with a visible-subject footage query")
        elif rule in ("TASTE-CAPTION",):
            actions.append("rebuild caption events phrase-level with capped ends")
        elif rule in ("TASTE-AUDIO", "MQ-LRA"):
            actions.append("remix with executed music curve and re-measure LRA")
        elif rule in ("TASTE-FRAME",):
            actions.append("re-plan the failing beat visual; do not re-render the same plan")
        else:
            actions.append(f"fix {rule} before delivery")
    return list(dict.fromkeys(actions))[:8]
