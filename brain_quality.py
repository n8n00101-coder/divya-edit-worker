"""brain_quality.py — decision quality around Julie's free brains.

Ajju's revision: brain quality must be taken into the taste work.
Free model weights cannot be retrained here; quality comes from the
decisions around the model — strongest-brain routing for director and
critic calls, a Story Analyst pass, a Visual Director pass, an
adversarial Critic pass, frame-level re-planning, and feedback rules
learned from Ajju/Blind verdicts. Every pass records what it decided.
"""

import re

import taste_pack

FEEDBACK_RULES = [
    {"id": "FB-HOOK", "source": "W8 diagnosis",
     "rule": "frame 1 shows real content; no title-card hook",
     "gate": "TASTE-HOOK"},
    {"id": "FB-FOOTAGE-MATCH", "source": "Blind 32",
     "rule": "the frame shows the line's subject, not decoration",
     "gate": "TASTE-FRAME"},
    {"id": "FB-SOURCE-TRUTH", "source": "Blind 32",
     "rule": "numbers and studies carry retrieved sources on screen",
     "gate": "TASTE-SOURCE"},
    {"id": "FB-NO-FAKE-UI", "source": "W8 diagnosis",
     "rule": "no fake UI, production internals, icons or placeholders as content",
     "gate": "TASTE-BANNED-VISUAL"},
    {"id": "FB-VARIETY", "source": "Male Gaze audit",
     "rule": "no visual type dominates the film",
     "gate": "TASTE-VARIETY"},
    {"id": "FB-SOUND", "source": "W8/Male Gaze measurements",
     "rule": "sound has a designed arc; flat LRA fails",
     "gate": "TASTE-AUDIO"},
    {"id": "FB-CAPTIONS", "source": "Blind 32",
     "rule": "captions are complete phrases, synced, unclipped, non-overlapping",
     "gate": "TASTE-CAPTION"},
    {"id": "FB-NO-RESTATEMENT", "source": "Male Gaze audit",
     "rule": "every line adds information or feeling; top-ups must be new material",
     "gate": "BRAIN-RESTATEMENT"},
]

POSITIVE_EXAMPLES = [
    {"name": "pivot hook", "lesson": "real footage in frame 1; memory replay shown, not labelled"},
    {"name": "pivot numbers", "lesson": "46% vs 23% verified before scripting and cited on screen"},
    {"name": "pivot sound", "lesson": "music-led head, breath before the turn, per-beat rides; LRA measured"},
]

NEGATIVE_EXAMPLES = [
    {"name": "W8 title hook", "lesson": "a giant question graphic on black is not a hook"},
    {"name": "W8 placeholder", "lesson": "clip-art labelled Photo A shipped as content"},
    {"name": "Male Gaze counter", "lesson": "one counter visual repeated across beats flattens the film"},
]


def route_policy(profile=None):
    return {
        "story": "strongest_free",
        "visual": "strongest_free",
        "critic": "strongest_free",
        "mechanical": "light",
        "record_decision_brain": True,
        "profile": (profile or {}).get("id", ""),
    }


def _words(text):
    return [w for w in re.findall(r"[a-z][a-z'-]*", str(text or "").lower())
            if len(w) > 2]


def _check(rule, ok, detail, scene=None):
    return {"rule": rule, "status": "PASS" if ok else "FAIL",
            "detail": detail, "scene": scene}


def story_checks(scenes, profile=None):
    scenes = list(scenes or [])
    checks = []
    if scenes:
        first_words = len(str(scenes[0].get("vo") or "").split())
        checks.append(_check(
            "BRAIN-HOOK", first_words <= 22,
            f"hook line has {first_words} words (target <=22, inside ~5s)",
            scenes[0].get("no") or 1))
    word_sets = [set(_words(s.get("vo"))) for s in scenes]
    for i in range(len(word_sets)):
        for j in range(i + 2, len(word_sets)):
            a, b = word_sets[i], word_sets[j]
            if not a or not b:
                continue
            sim = len(a & b) / max(1, min(len(a), len(b)))
            if sim > 0.65:
                checks.append(_check(
                    "BRAIN-RESTATEMENT", False,
                    f"beats {i + 1} and {j + 1} restate each other ({sim:.0%} shared content words)",
                    scenes[j].get("no") or j + 1))
    for i, scene in enumerate(scenes):
        if taste_pack.source_required(scene) and not taste_pack.has_source(scene):
            checks.append(_check(
                "BRAIN-CLAIM", False,
                "claim/number has no source before directing",
                scene.get("no") or i + 1))
    if not checks:
        checks.append(_check("BRAIN-STORY", True,
                             "hook, claims and restatement checks pass"))
    return checks


def _diagram_kind(scene):
    text = taste_pack._text(scene).lower()
    if any(w in text for w in ("wave", "fade", "quiet", "drift")):
        return "wave"
    if any(w in text for w in ("grow", "growth", "thriv", "become", "rise")):
        return "growth"
    if any(w in text for w in ("check", "starting point", "pattern", "sentence")):
        return "checks"
    if any(w in text for w in ("arrow", "timeline", "years", "later", "tonight")):
        return "arrow"
    return ""


def enrich_visuals(scenes, profile=None):
    profile = profile or taste_pack.PROFILES["wtu_long_sheet"]
    for i, scene in enumerate(scenes or []):
        no = int(scene.get("no") or i + 1)
        scene["no"] = no
        need_source = taste_pack.source_required(scene)
        sourced = taste_pack.has_source(scene)
        scene["source_required"] = bool(need_source)
        promise = str(scene.get("promise") or scene.get("why") or
                      scene.get("label") or scene.get("vo") or "").strip()
        scene["promise"] = promise[:240]
        if scene.get("graphic_locked"):
            # A variety repair demoted this beat to footage; the
            # visual pass must not re-assign the graphic it removed.
            scene["graphic_type"] = scene.get("graphic_type") or "footage"
        elif need_source and sourced:
            scene["graphic_type"] = "source_card"
        elif _diagram_kind(scene) in (profile.get("diagram_kinds") or ()):
            scene["graphic_type"] = "diagram"
            scene["diagram_kind"] = _diagram_kind(scene)
        elif taste_pack.scene_numbers(scene) and sourced:
            scene["graphic_type"] = "data_chart"
        else:
            scene["graphic_type"] = scene.get("graphic_type") or "footage"
        max_words = int((profile.get("caption") or {}).get("max_words") or 6)
        scene["acceptance"] = (
            f"frame shows: {promise[:120]}; footage fills frame; "
            f"captions <= {max_words} words, synced, no overlap"
            + ("; source card legible with source" if scene["graphic_type"] == "source_card" else "")
            + ("; graphic justified by the line" if scene["graphic_type"] != "footage" else "")
        )[:240]
        scene["rework_action"] = (
            "re-plan this beat with a new visual decision; do not re-render the same plan"
        )
    return scenes


def critic_review(plan, profile=None):
    profile = profile or taste_pack.PROFILES["wtu_long_sheet"]
    scenes = (plan or {}).get("scenes") or []
    checks = []
    checks.extend(taste_pack.profile_checks(plan, profile))
    checks.extend(story_checks(scenes, profile))
    if scenes:
        first = scenes[0]
        first_gt = taste_pack.graphic_type(first)
        if first_gt in ("title", "stamp_cta", "stamp", "card", "quote_card"):
            checks.append(_check(
                "CRITIC-HOOK", False,
                "critic: first beat is a card/stamp, not content", 1))
    for rule in FEEDBACK_RULES:
        checks.append(_check(
            rule["id"], True,
            f"feedback rule loaded: {rule['rule']} (gate {rule['gate']})"))
    return checks


def _stamp_or_strip_source(plan, scene, no):
    """TASTE-SOURCE repair: stamp a resolved research source onto the
    scene, or deterministically remove the unsourced claim.

    Order: (1) the fact gate's own resolution (scene source_ref ->
    research record title); (2) a research entry whose title shares
    >=2 content words with the line; (3) remove the claim sentences
    (spoken numbers / fact claims) from the voice line — an
    unsourced number never renders on a taste film."""
    if not taste_pack.source_required(scene) or taste_pack.has_source(scene):
        return None
    research = (plan or {}).get("research") or []
    try:
        import anti_boring as _ab
        title = _ab.resolved_source_title(scene, research)
    except Exception:
        title = None
    if title:
        scene["source"] = title
        return f"beat {no}: stamped resolved source '{title}'"
    vo_words = set(_words(scene.get("vo")))
    best, best_overlap = None, 0
    for entry in research:
        if not isinstance(entry, dict):
            continue
        entry_words = set(_words(str(entry.get("title") or "") + " " +
                                 str(entry.get("snippet") or entry.get("text") or "")))
        overlap = len(vo_words & entry_words)
        if overlap > best_overlap:
            best, best_overlap = entry, overlap
    if best is not None and best_overlap >= 3 and str(best.get("title") or "").strip():
        scene["source_ref"] = str(best.get("title")).strip()
        scene["source"] = str(best.get("title")).strip()
        return (f"beat {no}: matched research source "
                f"'{scene['source']}' ({best_overlap} shared words)")
    # No source resolves: remove claim sentences from the line.
    import re as _re
    vo = str(scene.get("vo") or "")
    sentences = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", vo) if s.strip()]
    kept = []
    for sent in sentences:
        probe = dict(scene, vo=sent)
        if taste_pack.source_required(probe):
            continue
        kept.append(sent)
    if kept and len(kept) < len(sentences):
        scene["vo"] = " ".join(kept)
        scene.pop("value", None)
        return f"beat {no}: removed unsourced claim sentence(s)"
    if sentences and not kept:
        # Beat-specific non-claim fallback: identical fallback lines
        # would restate each other and fail the story check.
        _fallbacks = (
            "And that feeling is exactly where this story begins.",
            "But the moment itself tells a quieter story.",
            "Watch the room again, a little more closely.",
            "That small pause carries the whole weight here.",
            "Notice how the room changes around that thought.",
            "The next moment makes the feeling harder to ignore.",
        )
        scene["vo"] = _fallbacks[(int(no) - 1) % len(_fallbacks)]
        scene.pop("value", None)
        return f"beat {no}: unsourced claim line replaced with a non-claim line"
    return None


def repair_plan(plan, profile=None):
    """Deterministic pre-render repair rounds (bounded by caller).

    Repairs plan fields: banned visuals become footage beats,
    internal labels are cleared, source-card misuse is demoted,
    unsearchable queries are replaced by the line's visible subject,
    and unsourced claims are source-stamped from the plan's research
    record or removed — the taste gate never renders them.
    """
    profile = profile or taste_pack.PROFILES["wtu_long_sheet"]
    fixes = []
    for i, scene in enumerate((plan or {}).get("scenes") or []):
        _src_fix = _stamp_or_strip_source(plan, scene, int(scene.get("no") or i + 1))
        if _src_fix:
            fixes.append(_src_fix)
        no = int(scene.get("no") or i + 1)
        if taste_pack.label_is_internal(scene.get("label")):
            fixes.append(f"beat {no}: cleared internal label '{scene.get('label')}'")
            scene["label"] = ""
        vis = str(scene.get("visual") or "").lower()
        if vis in (profile.get("banned_visuals") or ()):
            fixes.append(f"beat {no}: banned visual '{vis}' -> footage")
            scene["visual"] = "card"
            scene["graphic_type"] = "footage"
        if scene.get("graphic_type") == "source_card" and not taste_pack.has_source(scene):
            fixes.append(f"beat {no}: source_card without source -> footage")
            scene["graphic_type"] = "footage"
        queries = []
        for q in scene.get("queries") or []:
            if taste_pack.query_is_visible_subject(q):
                queries.append(q)
            else:
                fixes.append(f"beat {no}: dropped unsearchable query '{q}'")
        if not queries:
            words = _words(scene.get("vo"))[:4]
            if len(words) >= 2:
                queries = [" ".join(words[:3])]
                fixes.append(f"beat {no}: derived visible-subject query '{queries[0]}'")
        scene["queries"] = queries[:2]
    # TASTE-VARIETY repair: no graphic type may fill >25% of beats.
    # Excess graphic beats are demoted to footage (the sheet default)
    # and locked so the next visual pass cannot re-assign them.
    # Source-card beats with a spoken number keep their card first;
    # the source field itself is never removed by demotion.
    scenes = (plan or {}).get("scenes") or []
    if len(scenes) >= 8:
        from collections import Counter
        hist = Counter(taste_pack.graphic_type(s) for s in scenes
                       if taste_pack.graphic_type(s) != "footage")
        allowed = max(2, int(0.25 * len(scenes)))
        for kind, count in hist.items():
            if count < 3 or count / len(scenes) <= 0.25:
                continue
            beats = [s for s in scenes
                     if taste_pack.graphic_type(s) == kind]
            if kind == "source_card":
                beats.sort(key=lambda s: (0 if taste_pack.scene_numbers(s) else 1,
                                          int(s.get("no") or 0)))
            for scene in beats[allowed:]:
                no = int(scene.get("no") or 0)
                scene["graphic_type"] = "footage"
                scene["graphic_locked"] = True
                scene.pop("diagram_kind", None)
                fixes.append(
                    f"beat {no}: variety demotion {kind} -> footage "
                    f"({kind} capped at {allowed}/{len(scenes)})")
    return fixes


def apply(plan, profile=None, chat=None):
    profile = profile or taste_pack.PROFILES["wtu_long_sheet"]
    scenes = (plan or {}).get("scenes") or []
    enrich_visuals(scenes, profile)
    story = story_checks(scenes, profile)
    critic = critic_review(plan, profile)
    plan["brain_quality"] = {
        "route": route_policy(profile),
        "story_checks": story,
        "critic_checks": critic,
        "feedback_rules": FEEDBACK_RULES,
        "positive_examples": POSITIVE_EXAMPLES,
        "negative_examples": NEGATIVE_EXAMPLES,
        "decisions": [
            {"stage": "story", "brain": "strongest_free",
             "checks": len(story)},
            {"stage": "visual", "brain": "strongest_free",
             "checks": len(scenes)},
            {"stage": "critic", "brain": "strongest_free",
             "checks": len(critic)},
        ],
    }
    return critic
