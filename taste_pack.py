"""taste_pack.py — machine-readable channel style profiles for Julie.

The taste-guarantee mechanism is delivery blocking, not a promise that
taste can be proved mathematically. This module is the style half of
that mechanism: every channel profile names the format, caption rules,
source-card rules, graphics whitelist, banned visuals, footage floor
and audio floor that the video director gates enforce. A rule that is
not mapped to a check here or in QC does not count as implemented.
"""

import re

INTERNAL_LABELS = {
    "NEXT", "CHAPTER", "INTRO", "OUTRO", "TITLE", "END", "ENDING",
    "HOOK", "CTA", "TEASE", "TRANSITION", "EMOTION", "SCORE",
    "BEAT", "SCENE", "OPENING", "CLOSING", "INTERLUDE", "MONTAGE",
    "TITLE CARD", "CHAPTER CARD", "END CARD",
}
INTERNAL_MARKERS = (
    "the line", "line is about", "line itself", "emotion", "score",
    "stage direction", "writer's", "writer’s", "description",
    "internal", "placeholder", "lorem", "visual opportunity",
    "turning point",
)
NON_SEARCHABLE = (
    "film still", "movie still", "film scene", "movie scene",
    "screenshot", "screen capture", "screen grab", "trailer",
    "poster", "scene from", "clip from", "still from",
)
FACT_WORDS = (
    "study", "studies", "research", "researchers", "according",
    "percent", "%", "found", "showed", "survey", "experiment",
    "psychologists", "scientists", "data", "statistics",
)

PROFILES = {
    "wtu_long_sheet": {
        "id": "wtu_long_sheet",
        "channel": "WHO TAUGHT US",
        "kind": "long",
        "width": 1920,
        "height": 1080,
        "orientation": "landscape",
        "duration_min_s": 60,
        "duration_max_s": 1200,
        "footage_share_min": 0.90,
        "lra_min": 6.0,
        "lufs_target": -14.0,
        "silence_max_s": 0.8,
        "caption": {"max_words": 6, "position": "bottom-centre",
                    "highlight": "keyword", "overlap_allowed": False},
        "source_card": {"required_for_sourced_facts": True,
                        "placement": "corner", "big_stat": True},
        "graphics_whitelist": ("source_card", "data_chart", "diagram",
                               "map_card", "lower_third", "footage"),
        "diagram_kinds": ("wave", "growth", "checks", "arrow"),
        "banned_visuals": ("polaroid", "stamp_cta", "stamp", "chat",
                           "phone", "notification", "fake_ui",
                           "document", "quote_card", "title",
                           "filmstrip", "icon_row", "checklist",
                           "dot_grid"),
        "banned_first_beat": ("title", "stamp_cta", "stamp", "card",
                              "quote_card"),
        "transition_rule": "idea boundaries only; plain cuts inside one idea",
        "music_rule": "duck under narration; lift only in gaps; executed curve",
        "language_rules": {
            "en": "English title, description and captions",
            "hi": "Hindi title; English description",
            "te": "Romanized Telugu title/description/captions where required",
        },
        "allow_cta": False,
        "requires_vision_qc": True,
    },
    "wtu_short": {
        "id": "wtu_short",
        "channel": "WHO TAUGHT US",
        "kind": "short",
        "width": 1080,
        "height": 1920,
        "orientation": "portrait",
        "duration_min_s": 15,
        "duration_max_s": 90,
        "footage_share_min": 0.80,
        "lra_min": 5.0,
        "lufs_target": -14.0,
        "silence_max_s": 0.8,
        "caption": {"max_words": 4, "position": "bottom-centre",
                    "highlight": "keyword", "overlap_allowed": False},
        "source_card": {"required_for_sourced_facts": True,
                        "placement": "corner", "big_stat": True},
        "graphics_whitelist": ("source_card", "data_chart", "diagram",
                               "lower_third", "footage"),
        "diagram_kinds": ("wave", "growth", "checks", "arrow"),
        "banned_visuals": ("polaroid", "fake_ui", "blur_pad",
                           "letterbox"),
        "banned_first_beat": ("title", "card"),
        "transition_rule": "fast hook; full-frame cuts; no blur-pad",
        "music_rule": "constant voice level; music under narration",
        "language_rules": {"en": "English", "hi": "Hindi", "te": "Romanized Telugu"},
        "allow_cta": True,
        "requires_vision_qc": True,
    },
    "todays_ai_ai1": {
        "id": "todays_ai_ai1",
        "channel": "@todays_ai",
        "kind": "short",
        "width": 1080,
        "height": 1920,
        "orientation": "portrait",
        "duration_min_s": 30,
        "duration_max_s": 45,
        "footage_share_min": 0.0,
        "lra_min": 4.0,
        "lufs_target": -14.0,
        "silence_max_s": 0.5,
        "caption": {"max_words": 4, "position": "bottom-centre",
                    "highlight": "accent", "overlap_allowed": False},
        "source_card": {"required_for_sourced_facts": False,
                        "placement": "card", "big_stat": False},
        "graphics_whitelist": ("ui_card", "terminal", "browser", "chat",
                               "price_tag", "notification", "cta"),
        "diagram_kinds": (),
        "banned_visuals": ("stock_image", "ai_video_clip", "fake_ui"),
        "banned_first_beat": (),
        "transition_rule": "one UI card per sentence; slide-in",
        "music_rule": "energetic bed under female voice",
        "language_rules": {"en": "English first; state who announced it"},
        "cta": "Comment KEYWORD",
        "footer": "@todays_ai",
        "allow_cta": True,
        "requires_vision_qc": True,
    },
    "todays_ai_ai2": {
        "id": "todays_ai_ai2",
        "channel": "@todays_ai",
        "kind": "short",
        "width": 720,
        "height": 1280,
        "orientation": "portrait",
        "duration_min_s": 35,
        "duration_max_s": 45,
        "footage_share_min": 0.0,
        "lra_min": 4.0,
        "lufs_target": -14.0,
        "silence_max_s": 0.3,
        "caption": {"max_words": 5, "position": "top-16pct",
                    "highlight": "current-word", "overlap_allowed": False},
        "source_card": {"required_for_sourced_facts": False,
                        "placement": "card", "big_stat": False},
        "graphics_whitelist": ("ui_mockup", "browser", "code_editor",
                               "terminal", "counter", "line_chart",
                               "social_card", "cta"),
        "diagram_kinds": ("growth", "arrow"),
        "banned_visuals": ("bottom_caption", "fake_ui"),
        "banned_first_beat": (),
        "transition_rule": "visual change every 1-2 seconds",
        "music_rule": "light beat under voice",
        "language_rules": {"en": "English first; state who announced it"},
        "cta": "Comment KEYWORD",
        "footer": "@todays_ai",
        "allow_cta": True,
        "requires_vision_qc": True,
    },
    "todays_ai_ai3": {
        "id": "todays_ai_ai3",
        "channel": "@todays_ai",
        "kind": "short",
        "width": 720,
        "height": 1280,
        "orientation": "portrait",
        "duration_min_s": 40,
        "duration_max_s": 45,
        "footage_share_min": 0.0,
        "lra_min": 4.0,
        "lufs_target": -14.0,
        "silence_max_s": 0.5,
        "caption": {"max_words": 1, "position": "y-72pct",
                    "highlight": "marker", "overlap_allowed": False},
        "source_card": {"required_for_sourced_facts": False,
                        "placement": "card", "big_stat": False},
        "graphics_whitelist": ("card", "terminal", "counter",
                               "progress", "checklist", "cta"),
        "diagram_kinds": ("growth", "checks"),
        "banned_visuals": ("presenter", "gradient", "fake_ui"),
        "banned_first_beat": (),
        "transition_rule": "one large card per scene; motion every 1-2 seconds",
        "music_rule": "soft pad plus pop SFX on scene entries",
        "language_rules": {"en": "English first; state who announced it"},
        "cta": "Comment KEYWORD",
        "footer": "@todays_ai",
        "allow_cta": True,
        "requires_vision_qc": True,
    },
    "quiet_page": {
        "id": "quiet_page",
        "channel": "Quiet Page",
        "kind": "short",
        "width": 1080,
        "height": 1920,
        "orientation": "portrait",
        "duration_min_s": 10,
        "duration_max_s": 60,
        "footage_share_min": 0.0,
        "lra_min": 3.0,
        "lufs_target": -16.0,
        "silence_max_s": 1.2,
        "caption": {"max_words": 6, "position": "paper-page",
                    "highlight": "none", "overlap_allowed": False},
        "source_card": {"required_for_sourced_facts": False,
                        "placement": "none", "big_stat": False},
        "graphics_whitelist": ("paper_page", "footage"),
        "diagram_kinds": (),
        "banned_visuals": ("nyt_cutz", "fake_ui"),
        "banned_first_beat": (),
        "transition_rule": "quiet page treatment; no loud graphics",
        "music_rule": "calm bed; voice level constant when voice exists",
        "language_rules": {"en": "English page text"},
        "branding": "QUIET_PAGE",
        "allow_cta": False,
        "requires_vision_qc": True,
    },
}

ALIASES = {
    "wtu": "wtu_long_sheet",
    "wtu_long": "wtu_long_sheet",
    "sheet": "wtu_long_sheet",
    "sheet_style": "wtu_long_sheet",
    "long": "wtu_long_sheet",
    "short": "wtu_short",
    "ai1": "todays_ai_ai1",
    "ai-1": "todays_ai_ai1",
    "ai2": "todays_ai_ai2",
    "ai-2": "todays_ai_ai2",
    "ai3": "todays_ai_ai3",
    "ai-3": "todays_ai_ai3",
    "quiet": "quiet_page",
}


def normalize_profile_id(value):
    key = str(value or "").strip().lower().replace(" ", "_")
    return ALIASES.get(key, key)


def get_profile(value):
    pid = normalize_profile_id(value)
    return PROFILES.get(pid)


def profile_for_job(brief="", cfg=None, spec=None):
    cfg = cfg or {}
    for key in ("taste_profile", "tasteProfile", "profile",
                "channel_style", "style_profile"):
        prof = get_profile(cfg.get(key))
        if prof:
            return prof
    if cfg.get("tasteDirectorRequired") or cfg.get("taste_director_required"):
        return PROFILES["wtu_long_sheet"]
    text = " ".join([str(brief or ""), str(spec or "")]).lower()
    if "ai-1" in text or "ai1" in text:
        return PROFILES["todays_ai_ai1"]
    if "ai-2" in text or "ai2" in text:
        return PROFILES["todays_ai_ai2"]
    if "ai-3" in text or "ai3" in text:
        return PROFILES["todays_ai_ai3"]
    if "quiet page" in text or "quiet_page" in text:
        return PROFILES["quiet_page"]
    # Only EXPLICIT channel/style markers select a profile from text.
    # Generic words ("long", "documentary", "short") must not turn
    # every legacy job into a taste job — the Worker stamps
    # tasteProfile on the job record and the runner passes it via
    # cfg, which is the authoritative route.
    if "who taught us" in text or "wtu" in text or \
            "sheet style" in text or "wtu_long_sheet" in text:
        return PROFILES["wtu_long_sheet"]
    if "wtu_short" in text or "wtu short" in text:
        return PROFILES["wtu_short"]
    return None


def is_taste_job(cfg=None, brief="", spec=None):
    cfg = cfg or {}
    return bool(cfg.get("taste_profile") or cfg.get("tasteProfile") or
                cfg.get("tasteDirectorRequired") or
                cfg.get("taste_director_required") or
                profile_for_job(brief, cfg, spec))


def cfg_for_profile(profile):
    if not profile:
        return {}
    return {
        "taste_profile": profile["id"],
        "tasteDirectorRequired": True,
        "kind": profile["kind"],
        "width": profile["width"],
        "height": profile["height"],
        "orientation": profile["orientation"],
        "allow_cta": bool(profile.get("allow_cta", True)),
        "show_sources": bool(profile.get("source_card", {}).get(
            "required_for_sourced_facts")),
    }


def _text(scene):
    # Viewer-facing claim text only: the spoken line, its label and
    # its spoken value. The director's internal `why` rationale is
    # never a viewer claim and must not trigger the source gate.
    return " ".join(str((scene or {}).get(k) or "")
                    for k in ("vo", "label", "value"))


def scene_numbers(scene):
    text = _text(scene)
    vals = []
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?\s*%?", text):
        vals.append(m.group(0).strip())
    return vals


def source_required(scene):
    text = _text(scene).lower()
    if scene_numbers(scene):
        return True
    return any(w in text for w in FACT_WORDS)


def has_source(scene):
    scene = scene or {}
    return bool(str(scene.get("source") or "").strip() or
                str(scene.get("source_ref") or "").strip() or
                str(scene.get("source_text") or "").strip())


def label_is_internal(label):
    lab = str(label or "").strip()
    if not lab:
        return False
    if lab.upper() in INTERNAL_LABELS:
        return True
    low = lab.lower()
    if any(m in low for m in INTERNAL_MARKERS):
        return True
    if re.match(r"^(chapter|scene|beat|part)\s*\d*$", low):
        return True
    return len(lab) > 44 or len(lab.split()) > 6


def graphic_type(scene):
    scene = scene or {}
    gt = str(scene.get("graphic_type") or "").strip().lower()
    if gt:
        return gt
    vis = str(scene.get("visual") or scene.get("lib_visual") or "").strip().lower()
    if vis in ("counter", "donut", "bar", "bar_compare", "graph", "gauge"):
        return "data_chart"
    if vis in ("india_map", "world_dots", "map"):
        return "map_card"
    if vis:
        return vis
    return "footage"


def query_is_visible_subject(query):
    q = str(query or "").strip().lower()
    if not q or any(bad in q for bad in NON_SEARCHABLE):
        return False
    words = [w for w in re.findall(r"[a-z][a-z'-]*", q)
             if w not in ("the", "a", "an", "of", "in", "on", "at", "to")]
    return len(words) >= 2


def _check(rule, ok, detail, scene=None):
    return {"rule": rule, "status": "PASS" if ok else "FAIL",
            "detail": detail, "scene": scene}


def validate_scene(scene, profile, beat_index=0):
    scene = scene or {}
    profile = profile or PROFILES["wtu_long_sheet"]
    no = int(scene.get("no") or beat_index + 1)
    checks = []
    need_source = source_required(scene)
    sourced = has_source(scene)
    checks.append(_check(
        "TASTE-SOURCE", (not need_source) or sourced,
        "sourced fact/number carries a source" if sourced or not need_source
        else "fact/number has no source — remove it or source it", no))
    gt = graphic_type(scene)
    checks.append(_check(
        "TASTE-SOURCE-CARD",
        gt != "source_card" or sourced,
        "source card is backed by a source" if gt != "source_card" or sourced
        else "source card requested without a source", no))
    checks.append(_check(
        "TASTE-LABEL", not label_is_internal(scene.get("label")),
        "label is viewer-facing" if not label_is_internal(scene.get("label"))
        else f"label '{scene.get('label')}' is internal/structural", no))
    whitelist = set(profile.get("graphics_whitelist") or ())
    checks.append(_check(
        "TASTE-GRAPHIC", (not whitelist) or gt in whitelist or gt == "footage",
        f"graphic '{gt}' is allowed by {profile['id']}" if gt in whitelist or gt == "footage"
        else f"graphic '{gt}' is not in the {profile['id']} whitelist", no))
    banned = set(profile.get("banned_visuals") or ())
    vis = str(scene.get("visual") or scene.get("lib_visual") or "").lower()
    checks.append(_check(
        "TASTE-BANNED-VISUAL", vis not in banned and gt not in banned,
        "visual is not banned by the profile" if vis not in banned and gt not in banned
        else f"visual '{vis or gt}' is banned by {profile['id']}", no))
    if beat_index == 0:
        bad_first = set(profile.get("banned_first_beat") or ())
        checks.append(_check(
            "TASTE-HOOK", vis not in bad_first and gt not in bad_first,
            "first beat opens on content, not a title/stamp card"
            if vis not in bad_first and gt not in bad_first
            else "first beat is a banned title/stamp/card hook", no))
    queries = [q for q in (scene.get("queries") or []) if str(q).strip()]
    if queries:
        bad_q = [q for q in queries if not query_is_visible_subject(q)]
        checks.append(_check(
            "TASTE-QUERY", not bad_q,
            "footage queries name visible subjects" if not bad_q
            else f"unsearchable footage query: {bad_q[0]}", no))
    return checks


def caption_events_ok(events, profile):
    profile = profile or PROFILES["wtu_long_sheet"]
    max_words = int((profile.get("caption") or {}).get("max_words") or 6)
    checks = []
    prev_end = None
    for i, ev in enumerate(events or []):
        start = float(ev.get("start") or 0)
        end = float(ev.get("end") or start)
        words = len(str(ev.get("text") or "").split())
        if words > max_words:
            checks.append(_check(
                "TASTE-CAPTION", False,
                f"caption event {i + 1} has {words} words (max {max_words})",
                ev.get("scene")))
        if prev_end is not None and start < prev_end - 0.001:
            checks.append(_check(
                "TASTE-CAPTION", False,
                f"caption event {i + 1} overlaps the previous event",
                ev.get("scene")))
        prev_end = max(prev_end or end, end)
    if not checks:
        checks.append(_check("TASTE-CAPTION", True,
                             "caption events are phrase-level and non-overlapping"))
    return checks


def profile_checks(plan, profile):
    plan = plan or {}
    profile = profile or PROFILES["wtu_long_sheet"]
    scenes = plan.get("scenes") or []
    checks = []
    for i, scene in enumerate(scenes):
        checks.extend(validate_scene(scene, profile, i))
    if len(scenes) >= 8:
        from collections import Counter
        # Footage is the sheet default, not a graphic — the variety
        # cap governs GRAPHIC types only (a film that is mostly
        # footage is correct, not repetitive).
        hist = Counter(graphic_type(s) for s in scenes
                       if graphic_type(s) != "footage")
        for kind, count in hist.items():
            if count >= 3 and count / len(scenes) > 0.25:
                checks.append(_check(
                    "TASTE-VARIETY", False,
                    f"graphic type '{kind}' fills {count}/{len(scenes)} beats (>25%)"))
    if scenes and any("has_footage" in s for s in scenes):
        share = sum(1 for s in scenes if s.get("has_footage")) / len(scenes)
        checks.append(_check(
            "TASTE-FOOTAGE", share >= float(profile.get("footage_share_min") or 0),
            f"footage share {share:.0%} (floor {float(profile.get('footage_share_min') or 0):.0%})"))
    if plan.get("caption_events"):
        checks.extend(caption_events_ok(plan.get("caption_events"), profile))
    return checks


def rule_map():
    return {
        "TASTE-SOURCE": "videotastetest.py + fact gate + TASTE-SOURCE QC",
        "TASTE-SOURCE-CARD": "videotastetest.py + hf_primary source_card choice",
        "TASTE-LABEL": "videotastetest.py + hf_primary viewer-text whitelist",
        "TASTE-GRAPHIC": "videotastetest.py + hyperframes layer whitelist",
        "TASTE-BANNED-VISUAL": "videotastetest.py + critic pass",
        "TASTE-HOOK": "videotastetest.py + critic pass",
        "TASTE-QUERY": "videotastetest.py + broll query gate",
        "TASTE-CAPTION": "videotastetest.py + caption boundary QC",
        "TASTE-VARIETY": "videotastetest.py + VHIST/QC",
        "TASTE-FOOTAGE": "videotastetest.py + FG-SHARE/QC",
        "TASTE-AUDIO": "media_qc MQ-LRA + silence QC",
        "TASTE-FRAME": "frame_taste_qc vision audit",
    }
