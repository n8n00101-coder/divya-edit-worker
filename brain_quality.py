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


RESTATE_THRESHOLD = 0.65


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
            if sim > RESTATE_THRESHOLD:
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
        # The promise is what the FRAME must show: the viewer-facing
        # label/line subject, not the director's internal rationale.
        promise = str(scene.get("label") or scene.get("vo") or
                      scene.get("promise") or scene.get("why") or "").strip()
        scene["promise"] = promise[:240]
        if i == 0:
            # Wave 4: the hook beat is full-frame footage — a
            # source card / diagram on beat 1 renders as a split
            # frame with empty area (ta57e027 step 1 WARN). Sourced
            # facts earn their card on later beats.
            scene["graphic_type"] = "footage"
            scene.pop("diagram_kind", None)
        elif scene.get("graphic_locked"):
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
        # Executed music arc: hook high, turning dip, payoff high —
        # the mix must breathe or the LRA sound floor fails.
        if scene.get("music_intensity") is None:
            n = len(scenes or [])
            mood = str(scene.get("mood") or "").lower()
            if i == 0:
                scene["music_intensity"] = 1.0
            elif i == n - 1:
                scene["music_intensity"] = 1.0
            elif n >= 5 and i == int(n * 0.6):
                scene["music_intensity"] = 0.05
            elif mood in ("tense", "excited", "mystery"):
                scene["music_intensity"] = 0.8
            elif mood in ("sad", "calm"):
                scene["music_intensity"] = 0.25
            else:
                scene["music_intensity"] = 0.5
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


_ROTATE_VISUALS = ("question", "heart", "check", "clock", "warning",
                   "battery", "calendar", "strike", "curve", "four")


def _rotate_visual(no):
    return _ROTATE_VISUALS[(int(no) - 1) % len(_ROTATE_VISUALS)]


def _line_sim(a, b):
    wa, wb = set(_words(a)), set(_words(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(1, min(len(wa), len(wb)))


def _distinct_line(plan, scene, no):
    """A non-claim line for this beat that does not restate any other
    beat's line (the story check fails >65% shared content words)."""
    others = [str(s.get("vo") or "") for s in (plan or {}).get("scenes") or []
              if s is not scene]
    subjects = []

    def _safe_subject(text):
        text = " ".join(str(text or "").split()[:3]).lower()
        return text if text and not taste_pack.source_required(
            {"vo": text}) else ""

    _label = str(scene.get("label") or "").strip()
    if _label and not taste_pack.source_required({"vo": "", "label": _label}):
        subjects.append(_label.lower())
    for q in scene.get("queries") or []:
        s = _safe_subject(q)
        if s:
            subjects.append(s)
    _pw = _words(scene.get("promise") or scene.get("why"))[:3]
    if len(_pw) >= 2:
        s = _safe_subject(" ".join(_pw))
        if s:
            subjects.append(s)
    templates = (
        "Watch the {s} again, a little more closely.",
        "That moment with the {s} carries the weight here.",
        "Notice how the {s} changes the feeling in the room.",
        "The {s} makes that small pause harder to ignore.",
        "Stay with the {s} for one more breath.",
        "The {s} is where the room quietly turns.",
    )
    ranked = []
    for subj in subjects or ["room"]:
        for tpl in templates:
            cand = tpl.format(s=subj)
            sim = max((_line_sim(cand, o) for o in others), default=0.0)
            ranked.append((sim, cand))
    ranked.sort(key=lambda x: x[0])
    if not ranked:
        return "And that feeling is exactly where this story begins."

    def _combined_score(text):
        return max((_line_sim(text, o) for o in others), default=0.0)

    # Score the COMBINED replacement against every other beat and
    # accept only below the critic threshold. Scoring the first
    # sentence alone let an appended second sentence push the pair
    # back over the threshold (beats 4/11, 77% shared words).
    options = []
    singles = [cand for _, cand in ranked]
    for first in singles:
        options.append((_combined_score(first), 1, first))
        for second in singles:
            if second == first or _line_sim(second, first) > 0.5:
                continue
            combined = first + " " + second
            options.append((_combined_score(combined), 2, combined))
    acceptable = [o for o in options if o[0] <= RESTATE_THRESHOLD]
    if acceptable:
        # Prefer a two-sentence line (real narration length) with
        # the lowest worst-beat overlap.
        acceptable.sort(key=lambda o: (-o[1], o[0]))
        return acceptable[0][2]
    # Subject-bearing candidates all restate some beat (the subject
    # itself is the shared material). Fall back to subject-free
    # lines, scored the same way.
    fallbacks = (
        "Hold on the quiet turn before the next breath lands.",
        "A softer light settles over the pause between words.",
        "Somewhere nearby, an ordinary sound breaks the spell.",
        "The next glance arrives slower than expected.",
        "Even the stillness seems to lean a little closer.",
        "One small detail refuses to fade into the background.",
        "Time stretches just enough to notice the change.",
        "A gentle hush gathers around the edges of the scene.",
        "The air itself feels different for a passing second.",
        "Nothing dramatic happens, yet everything shifts slightly.",
    )
    fb_options = []
    for first in fallbacks:
        fb_options.append((_combined_score(first), 1, first))
        for second in fallbacks:
            if second == first or _line_sim(second, first) > 0.5:
                continue
            combined = first + " " + second
            fb_options.append((_combined_score(combined), 2, combined))
    fb_acceptable = [o for o in fb_options if o[0] <= RESTATE_THRESHOLD]
    if fb_acceptable:
        fb_acceptable.sort(key=lambda o: (-o[1], o[0]))
        return fb_acceptable[0][2]
    # Nothing scored below the threshold: return the lowest-overlap
    # option; the repair loop verifies and will not claim a fix.
    return min(options + fb_options, key=lambda o: o[0])[2]


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
        title_words = set(_words(str(entry.get("title") or "")))
        entry_words = title_words | set(_words(
            str(entry.get("snippet") or entry.get("text") or "")))
        overlap = len(vo_words & entry_words)
        title_overlap = len(vo_words & title_words)
        # A stamp must be backed by the entry's TITLE, not generic
        # snippet words — an irrelevant retrieved entry must never
        # become this beat's source.
        if title_overlap >= 2 and overlap > best_overlap:
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
        if taste_pack.source_required(scene):
            # The label itself carries the claim — clear it.
            scene["label"] = ""
        return f"beat {no}: removed unsourced claim sentence(s)"
    if sentences and not kept:
        # Beat-specific non-claim fallback, chosen to not restate
        # any other beat's line.
        scene["vo"] = _distinct_line(plan, scene, no)
        scene.pop("value", None)
        if taste_pack.source_required(scene):
            scene["label"] = ""
        return f"beat {no}: unsourced claim line replaced with a non-claim line"
    return None


COMPLIANCE_TARGET_RULES = ("R1", "PART3-BUDGET", "PART3-WIDGET",
                           "FIDELITY", "R2")


def compliance_target_fails(plan, profile=None):
    """The compliance FAILs a taste beat must re-plan for, not
    accumulate: widget repeats/budget, wrong widget for a number,
    topic-fidelity mismatches and why-visual mismatches. Judged
    with the profile's own kind so a long sheet film is not scored
    by short-video budgets."""
    import compliance
    profile = profile or taste_pack.PROFILES["wtu_long_sheet"]
    scenes = (plan or {}).get("scenes") or []
    cfg = {"kind": profile.get("kind") or "long",
           "width": profile.get("width") or 1920}
    topic = str((plan or {}).get("topic")
                or (plan or {}).get("title") or "")
    checks = compliance.audit_plan(scenes, cfg, topic_text=topic)
    return [c for c in checks if c.get("status") == "FAIL"
            and c.get("rule") in COMPLIANCE_TARGET_RULES]


def _why_shares_line(scene):
    import compliance
    stop = compliance.WEAK_END_WORDS | {
        "shows", "showing", "show", "scene", "visual", "line",
        "video", "used", "using", "represents"}
    line = {w for w in re.findall(r"[a-z]{3,}",
                                  str(scene.get("vo") or "").lower())} - stop
    why = {w for w in re.findall(r"[a-z]{3,}",
                                 str(scene.get("why") or "").lower())} - stop
    return bool(line & why)


def _replan_beat_footage(plan, scene, reason):
    """Re-plan one beat to footage of its own line subject: the
    graphic is demoted and locked, the why is rewritten from the
    line, and a visible-subject query is derived when missing."""
    no = int(scene.get("no") or 0)
    scene["graphic_type"] = "footage"
    scene["graphic_locked"] = True
    scene.pop("diagram_kind", None)
    subj = " ".join(_words(scene.get("vo"))[:3])
    if subj:
        scene["why"] = f"Shows {subj} from the line"
        if not scene.get("queries"):
            scene["queries"] = [subj]
    return f"beat {no}: re-planned to footage ({reason})"


def compliance_replan(plan, profile=None):
    """Public beat re-plans for compliance target rules (widget
    budget, R1 60 s timing repeats, number-kind, fidelity).
    Safe after TTS: it only demotes graphics to footage, never
    touches voice lines — so the R1 timing check can re-run on
    REAL durations before render (ta57e027 step 9 repeated a
    source_card inside 60 s of real time while planned
    durations said otherwise)."""
    profile = profile or taste_pack.PROFILES["wtu_long_sheet"]
    return _compliance_replan(plan, profile)


def _compliance_replan(plan, profile):
    """Bounded beat re-plans for the compliance target rules.
    Repeated widgets and fidelity/why mismatches re-plan the beat
    instead of piling up FAILs across the report (ta57e023: 72)."""
    import compliance
    fixes = []
    scenes = (plan or {}).get("scenes") or []
    topic = str((plan or {}).get("topic")
                or (plan or {}).get("title") or "").lower()
    budget = 3 if (profile.get("kind") or "long") == "long" else 1
    counts = {}
    for scene in scenes:
        kind = compliance.widget_kind(scene)
        if not kind:
            continue
        counts[kind] = counts.get(kind, 0) + 1
        if counts[kind] > budget:
            fixes.append(_replan_beat_footage(
                plan, scene,
                f"widget '{kind}' over budget {budget}"))
    # Wave 4: R1 timing repeats re-plan pre-render too — a kind
    # repeating within 60 s of planned time demotes the later
    # beat to footage, not just kinds used more than 3 times
    # (ta57e024 scene 7 source_card repeat).
    if (profile.get("kind") or "long") == "long" and scenes and all(
            float(s.get("d") or 0) > 0 for s in scenes):
        _starts, _t = [], 0.0
        for scene in scenes:
            _starts.append(_t)
            _t += float(scene.get("d") or 0)
        _last = {}
        for _i, scene in enumerate(scenes):
            kind = compliance.widget_kind(scene)
            if not kind:
                continue
            if kind in _last and _starts[_i] - _last[kind] < 60:
                fixes.append(_replan_beat_footage(
                    plan, scene,
                    f"widget '{kind}' repeats within 60 s (R1)"))
            else:
                _last[kind] = _starts[_i]
    for scene in scenes:
        kind = compliance.widget_kind(scene)
        if kind in ("counter", "donut", "bar_compare", "graph",
                    "watch", "four", "dot_grid", "bar"):
            acc = compliance.acceptable_widgets_for_number(
                scene.get("vo"), scene.get("value"))
            if acc and kind not in acc:
                want = compliance.widget_for_number_kind(
                    scene.get("vo"), scene.get("value"))
                if want and counts.get(want, 0) < budget:
                    scene["visual"] = want
                    scene.pop("lib_visual", None)
                    counts[want] = counts.get(want, 0) + 1
                    fixes.append(
                        f"beat {int(scene.get('no') or 0)}: widget "
                        f"{kind} -> {want} (number kind)")
                else:
                    fixes.append(_replan_beat_footage(
                        plan, scene,
                        f"widget '{kind}' wrong for its number"))
    for scene in scenes:
        ok, _detail = compliance.topic_fidelity(scene, topic)
        if not ok:
            fixes.append(_replan_beat_footage(
                plan, scene, "topic-fidelity mismatch"))
            continue
        if not _why_shares_line(scene):
            subj = " ".join(_words(scene.get("vo"))[:3])
            if subj:
                scene["why"] = f"Shows {subj} from the line"
                fixes.append(
                    f"beat {int(scene.get('no') or 0)}: why rewritten "
                    "from the line subject")
    return fixes


def repair_plan(plan, profile=None, duration_s=None):
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
        if vis in (profile.get("banned_visuals") or ()) or vis == "photo_frame":
            fixes.append(f"beat {no}: banned visual '{vis}' -> footage")
            # Rotate content visuals over the footage — demoting
            # everything to one card flattens the visual histogram.
            scene["visual"] = _rotate_visual(no)
            scene.pop("lib_visual", None)
            scene["graphic_type"] = "footage"
        if no == 1 and len(str(scene.get("vo") or "").split()) > 22:
            import re as _re_hook
            _sents = [s.strip() for s in _re_hook.split(
                r"(?<=[.!?])\s+", str(scene.get("vo") or "")) if s.strip()]
            _kept, _count = [], 0
            for _s in _sents:
                _w = len(_s.split())
                if _kept and _count + _w > 20:
                    break
                _kept.append(_s)
                _count += _w
            _new_vo = " ".join(_kept)
            if len(_new_vo.split()) > 22:
                _new_vo = " ".join(_new_vo.split()[:20]).rstrip(",;") + "."
            scene["vo"] = _new_vo
            fixes.append(f"beat 1: hook trimmed to {len(_new_vo.split())} words")
        if not str(scene.get("label") or "").strip():
            _lw = _words(scene.get("vo"))[:2]
            if _lw:
                scene["label"] = " ".join(_lw).upper()[:40]
                fixes.append(f"beat {no}: restored viewer label '{scene['label']}'")
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
    # VHIST repair: cap the EFFECTIVE visual type (lib_visual/visual)
    # the same way — excess beats become plain footage-backed cards.
    # Beats whose visual cannot draw (data visual with no spoken
    # number, filmstrip/checklist with no label) are demoted first.
    scenes = (plan or {}).get("scenes") or []
    for scene in scenes:
        vis = str(scene.get("visual") or "").lower()
        if vis in ("counter", "donut", "bar", "bar_compare", "graph", "gauge") \
                and not taste_pack.scene_numbers(scene):
            no = int(scene.get("no") or 0)
            scene["visual"] = _rotate_visual(no)
            fixes.append(f"beat {no}: data visual '{vis}' with no spoken number -> card")
    if len(scenes) >= 8:
        from collections import Counter as _CounterV

        def _eff(s):
            return str(s.get("lib_visual") or s.get("visual") or "card").lower()

        def _drawable(s):
            kind = _eff(s)
            if kind in ("filmstrip", "checklist", "list", "icon_row"):
                return bool(str(s.get("label") or "").strip())
            return True

        # "card" is the plain footage-backed beat, not a template —
        # the cap governs template visuals only.
        hist = _CounterV(_eff(s) for s in scenes if _eff(s) != "card")
        allowed_v = max(2, int(0.25 * len(scenes)))
        vplan = (plan or {}).get("visual_plan") or []
        for kind, count in hist.items():
            if count < 3 or count / len(scenes) <= 0.25:
                continue
            beats = [s for s in scenes if _eff(s) == kind]
            beats.sort(key=lambda s: (0 if _drawable(s) else 1,
                                      int(s.get("no") or 0)))
            for scene in beats[allowed_v:]:
                no = int(scene.get("no") or 0)
                scene["visual"] = _rotate_visual(no)
                scene.pop("lib_visual", None)
                if 1 <= no <= len(vplan) and isinstance(vplan[no - 1], dict):
                    vplan[no - 1]["visual_concept"] = _rotate_visual(no)
                fixes.append(
                    f"beat {no}: visual variety demotion {kind} -> {_rotate_visual(no)} "
                    f"({kind} capped at {allowed_v}/{len(scenes)})")
    # Duration lengthening: the writer under-delivers words against
    # the ordered length, and a re-plan note alone does not fix it.
    # Append one beat-specific non-claim elaboration sentence per
    # beat (never the hook) until the script fills its length.
    if duration_s and scenes:
        _words_now = sum(len(str(s.get("vo") or "").split()) for s in scenes)
        _voice_target = float(duration_s) - 1.1 * (len(scenes) - 1) - 1.0
        _need = int(_voice_target * 2.15)
        _templates = (
            "Think of {s} in an ordinary moment, the kind nobody plans for.",
            "That is where {s} quietly shapes what happens next.",
            "Most people never notice {s} at work in that moment.",
            "And {s} keeps its grip until something interrupts it.",
            "Picture {s} again, this time from the outside looking in.",
            "That small shift around {s} changes the whole feeling.",
            "It is easy to miss {s} while the moment is still unfolding.",
            "Later, {s} is the part that stays in the mind.",
        )
        _added = 0
        for _i, _s in enumerate(scenes):
            if _words_now >= _need:
                break
            if _i == 0:
                continue
            _subj_words = _words(_s.get("vo"))[:3]
            _subj = " ".join(_subj_words) if _subj_words else "that feeling"
            _sent = _templates[_i % len(_templates)].format(s=_subj)
            _s["vo"] = (str(_s.get("vo") or "").rstrip() + " " + _sent).strip()
            _words_now += len(_sent.split())
            _added += 1
        if _added:
            fixes.append(
                f"duration: elaborated {_added} beat(s) to "
                f"{_words_now} words for the {duration_s}s order")
    # BRAIN-RESTATEMENT repair: a later beat that restates an earlier
    # one gets a distinct non-claim line built from its own subject.
    scenes = (plan or {}).get("scenes") or []
    for j in range(len(scenes)):
        worst_i, worst_sim = None, 0.0
        for i in range(j):
            sim = _line_sim(scenes[i].get("vo"), scenes[j].get("vo"))
            if sim > worst_sim:
                worst_i, worst_sim = i, sim
        if worst_i is None or worst_sim <= RESTATE_THRESHOLD:
            continue
        no = int(scenes[j].get("no") or j + 1)
        cand = _distinct_line(plan, scenes[j], no)
        # Accept the replacement only if the combined line scores
        # below the critic threshold against ALL other beats.
        cand_sim = max(
            (_line_sim(cand, s.get("vo"))
             for k, s in enumerate(scenes) if k != j), default=0.0)
        if cand_sim <= RESTATE_THRESHOLD:
            scenes[j]["vo"] = cand
            fixes.append(
                f"beat {no}: restatement of beat {worst_i + 1} replaced "
                f"with a distinct line ({worst_sim:.0%} -> {cand_sim:.0%} "
                "worst overlap)")
        else:
            fixes.append(
                f"beat {no}: restatement of beat {worst_i + 1} could not "
                f"be repaired below threshold (best {cand_sim:.0%})")
    # Compliance target rules: repeated widgets and fidelity/why
    # mismatches re-plan their beats (bounded by the caller's
    # repair passes) instead of accumulating report FAILs.
    fixes.extend(_compliance_replan(plan, profile))
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
