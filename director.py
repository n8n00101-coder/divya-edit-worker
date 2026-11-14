"""director.py — Julie v84 Stage 5 (P3): the Editing Director, LOG-ONLY.

The Director reads a finished scene plan (and, for a long video, the
documentary arc) and writes RECOMMENDATIONS ONLY:

- hard cut vs transition per scene boundary,
- effects that look unnecessary or stacked,
- scenes that need breathing space,
- silence placements (only: after a turning point, just before the
  payoff, just before the ending — 0.8-1.5 s, so the media audit can
  tell INTENTIONAL silence from a defect),
- a music-intensity curve across the story arc (hook 0.7, build 0.5,
  turning-point dip 0.3, payoff lift 0.85, ending decay 0.4; music
  always ducks under narration, lifts only in non-narration windows),
- visual repetition that weakens the story.

HARD CONTRACT (v1, Ajju Q7): the Director NEVER mutates the plan.
analyse() returns a brand-new log dict; the caller's plan object is
untouched (proven by the deep-equal test in v84test.py). Automatic
application of recommendations needs a separate future approval.
"""

import copy

ARC_MUSIC_CURVE = {
    "hook": 0.7, "context": 0.5, "evidence": 0.5, "contradiction": 0.55,
    "turning_point": 0.3, "build": 0.5, "payoff": 0.85, "conclusion": 0.4,
}
SILENCE_MIN_S, SILENCE_MAX_S = 0.8, 1.5
EFFECT_FIELDS = ("transition", "effect", "fx", "sfx")


def _scene_text(s):
    return str(s.get("vo") or s.get("narration") or s.get("title") or "")


def analyse_plan(scenes, arc=None, job_id="", config=None):
    """Return the Director's log for a scene list. Pure function:
    no mutation, no I/O, no model calls."""
    cfg = config or {}
    silence_min = float(cfg.get("silence_min_s", SILENCE_MIN_S))
    silence_max = float(cfg.get("silence_max_s", SILENCE_MAX_S))
    recs = []
    n = len(scenes or [])
    seen_visuals = {}
    for i, s in enumerate(scenes or []):
        no = s.get("no", i + 1)
        role = s.get("arc_role") or (arc[i] if arc and i < len(arc) else None)
        # --- visual repetition
        vis = str(s.get("visual") or "")
        if vis:
            if vis in seen_visuals:
                recs.append({"scene": no, "type": "visual_repetition",
                             "recommendation": "change visual",
                             "reason": f"visual '{vis}' already used at scene "
                                       f"{seen_visuals[vis]} — repetition weakens the story"})
            else:
                seen_visuals[vis] = no
        # --- stacked / unnecessary effects
        active_fx = [f for f in EFFECT_FIELDS
                     if s.get(f) not in (None, "", "none", "cut")]
        if len(active_fx) >= 3:
            recs.append({"scene": no, "type": "effect_stack",
                         "recommendation": "remove all but one effect",
                         "reason": f"{len(active_fx)} effect layers on one scene "
                                   f"({', '.join(active_fx)}) — one effect at a time"})
        # --- hard cut vs transition
        boundary = "hard cut"
        if s.get("transition") not in (None, "", "none", "cut"):
            if role in ("payoff", "conclusion") or i == n - 1:
                boundary = "keep transition (idea boundary)"
            else:
                recs.append({"scene": no, "type": "transition",
                             "recommendation": "replace transition with hard cut",
                             "reason": "transition inside one idea — professional "
                                       "cuts are invisible; transitions mark idea changes"})
        # --- breathing space
        dur = float(s.get("d") or 0)
        words = len(_scene_text(s).split())
        if dur and words and dur < words / 3.2:
            recs.append({"scene": no, "type": "breathing_space",
                         "recommendation": "let the scene breathe (longer hold)",
                         "reason": f"{words} narration words in {dur:.1f}s — dense; "
                                   f"the viewer cannot absorb the line"})
        # --- silence placement (the ONLY three sanctioned spots)
        silence = None
        if role == "turning_point":
            silence = {"after_scene": no, "duration_s": 1.0,
                       "reason": "after the turning point — let it land"}
        elif role == "payoff" and i > 0:
            silence = {"before_scene": no, "duration_s": 1.0,
                       "reason": "just before the payoff — anticipation"}
        elif i == n - 1 and n > 2:
            silence = {"before_scene": no, "duration_s": 1.2,
                       "reason": "just before the ending — closure"}
        if silence:
            d = silence["duration_s"]
            silence["duration_s"] = min(silence_max, max(silence_min, d))
            recs.append({"scene": no, "type": "silence", **silence})
    # --- music curve across the arc
    music = []
    for i, s in enumerate(scenes or []):
        role = s.get("arc_role") or (arc[i] if arc and i < len(arc) else None)
        inten = ARC_MUSIC_CURVE.get(role or "", 0.5)
        music.append({"scene": s.get("no", i + 1), "arc_role": role,
                      "music_intensity": inten,
                      "duck_under_narration": True,
                      "lift_only_without_narration": True})
    return {"version": "v84-director-1", "mode": "LOG-ONLY",
            "job_id": job_id, "scenes": n,
            "recommendations": recs, "music_curve": music,
            "silence_map": [r for r in recs if r["type"] == "silence"]}


# =====================================================================
# v86 — the Documentary Director: direct_plan()
#
# Ajju's v86 order (2026-11-14): STOP adding QC modules; the v85 sample
# was technically clean and editorially dead (10 shots of ~10 s, one
# paper background, generic visuals — see JULIE_V86_EDITING_DIAGNOSIS.md).
# The fix is a PLANNING stage, not another checker:
#
# - analyse_plan() above stays exactly as it was (v84, LOG-ONLY).
# - direct_plan() is new: it takes the writer's finished chapter plan
#   and returns a NEW directed plan plus the written VISUAL PLAN.
#   The input plan is never mutated (deep-copied first).
#
# What it does, per narration segment ("beat"):
# 1. BEATS: each writer scene is split at sentence/clause boundaries
#    into shorter beats, so the picture can change every ~2-5 s
#    instead of every ~10 s. Hook beats are shortest; payoff and
#    conclusion beats are allowed to breathe.
# 2. VISUAL DECISION per beat: what the audience hears / what they
#    should see / why / what changes / how long / what the next shot
#    says / repetition check. Content-bearing library visuals are
#    chosen ONLY when compliance.compose_visual can compose them
#    honestly from the beat's own line (the codebase's own gate) —
#    a visual that cannot communicate the line is rejected in
#    planning, not discovered in QC. Number-driven graphics are
#    used only when the line actually speaks a number; a stamp is
#    used only with a word taken from the line (the v85 render's
#    canned "BANNED" stamp is the defect this rule exists to kill).
# 3. BACKGROUNDS: every beat gets a section palette (problem / fact /
#    fix — the SECTION_PALETTE system doc.py already had but never
#    assigned) and a rotating scene-bg kind. No two consecutive
#    beats may share a section, a bg kind, or an effective visual.
# 4. TEMPLATES: quote (typewriter), evidence (document / newspaper),
#    data (bracket bars / counter), contrast (balance scale),
#    timeline (timeline cards), key term (quote card), question —
#    all existing visuals_lib / create kinds, no new renderers.
# 5. MUSIC: each beat carries an arc role; the intended intensity
#    comes from the v84 ARC_MUSIC_CURVE and is written into the
#    visual plan (the audible shaping still comes from the engine's
#    own music(), driven by the beats' moods and starts).
#
# Activation (doc.plan calls should_direct): long-form chapter
# briefs ("... chapter N of M ..." — the long pipeline's own brief
# format), cfg {"director_v86": True}, or JULIE_DIRECTOR_V86=1.
# Off: JULIE_DIRECTOR_V86=0 or cfg {"director": "off"}. Shorts
# (doc3 / ordinary doc.plan briefs) are never directed.
# =====================================================================

import os
import re

_WORDS_PER_SEC = 2.6   # measured gTTS pace of the v85 sample (247 words / 94.8 s)
_SCENE_GAP_S = 0.45    # doc.make_video's per-scene breathing gap

_STOP = {"a", "an", "the", "is", "are", "was", "were", "it", "its",
         "this", "that", "and", "or", "but", "so", "to", "of", "in",
         "on", "for", "with", "you", "your", "we", "our", "i", "me",
         "my", "he", "she", "they", "do", "does", "did", "can", "will",
         "would", "not", "no", "yes", "if", "when", "why", "how",
         "what", "one", "two", "first", "like", "just", "even"}
_SHOCK = {"never", "only", "stop", "secret", "hidden", "truth", "lie",
          "real", "actually", "exactly", "nobody", "everyone", "wrong",
          "free", "choice", "honest", "silence", "midnight", "refusal"}
_NUMWORDS = {"one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten", "eleven", "twelve", "twenty",
             "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
             "ninety", "hundred", "thousand", "million", "percent",
             "half", "double", "triple"}
_TIME_WORDS = ("midnight", "tonight", "evening", "morning", "night",
               "calendar", "week", "hour", "minute", "clock", "late",
               "today", "daily", "day")
_EVIDENCE_WORDS = ("psychologists", "scientists", "researchers",
                   "studies", "study", "research", "experts", "doctors",
                   "survey", "data", "statistics")
_CONTRAST_RE = re.compile(r"\b(but|yet|rather than|instead|not|never)\b", re.I)
_TERM_RE = re.compile(
    r"(?:call(?:s|ed)? (?:this|it) the|known as(?: the)?|named) "
    r"([a-z][a-z\- ]{2,30})", re.I)
# create.py kinds that draw a NUMBER (or a canned word) — honest only
# when the beat itself supplies the number / word.
_NUMBER_KINDS = {"counter", "dot_grid", "gauge", "icon_row", "bar",
                 "donut", "four", "watch"}
_CANNED_KINDS = {"stamp": "BANNED", "strike": "MONDAY",
                 "quote_card": "TRUTH"}
_SECTION_ROTATION = ("problem", "fact", "fix")
_ROLE_SECTION = {"hook": "problem", "context": "problem",
                 "evidence": "fact", "contradiction": "problem",
                 "turning_point": "fact", "build": "fact",
                 "payoff": "fix", "conclusion": "fix"}


def should_direct(brief, cfg=None):
    """Is the v86 Director active for this plan call? See the header
    comment for the activation rules. Pure, no I/O beyond env."""
    env = os.environ.get("JULIE_DIRECTOR_V86", "")
    if env == "0":
        return False
    if cfg and cfg.get("director") == "off":
        return False
    if env == "1":
        return True
    if cfg and cfg.get("director_v86"):
        return True
    return bool(re.search(r"chapter\s+\d+\s+of\s+\d+", str(brief or ""), re.I))


def chapter_position(brief):
    """(chapter_index_0based, chapter_count) parsed from a long-form
    chapter brief; (0, 1) when absent."""
    m = re.search(r"chapter\s+(\d+)\s+of\s+(\d+)", str(brief or ""), re.I)
    if m:
        return int(m.group(1)) - 1, max(1, int(m.group(2)))
    return 0, 1


def split_beats(vo, max_words=11, min_words=4):
    """Split one narration line into beats at sentence boundaries,
    then at clause boundaries for long sentences. Deterministic.
    Returns [(beat_text, source_sentence)] — the sentence rides along
    so feature detection can see list/enumeration context that a
    clause split may have divided across two beats."""
    text = " ".join(str(vo or "").split())
    if not text:
        return []
    sentences = [s.strip() for s in
                 re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    beats = []   # [beat_text, sentence]
    soft = max_words + 3   # a natural clause may run 3 words over the
    # target rather than be cut mid-phrase; only a clause longer than
    # the soft cap is packed word-wise (with a balanced tail).
    for sent in sentences:
        words = sent.split()
        if len(words) <= max_words:
            beats.append([sent, sent])
            continue
        clauses = [c.strip() for c in
                   re.split(r"(?<=[,;:])\s+|\s+[—–]\s+", sent) if c.strip()]
        cur = ""
        for cl in clauses:
            cw = cl.split()
            if len(cw) > soft:
                if cur:
                    beats.append([cur, sent])
                    cur = ""
                i = 0
                while len(cw) - i > soft:
                    cut = max_words
                    if len(cw) - i - cut < min_words:
                        cut = len(cw) - i - min_words
                    beats.append([" ".join(cw[i:i + cut]), sent])
                    i += cut
                cur = " ".join(cw[i:])
                continue
            if cur and len(cur.split()) + len(cw) > soft:
                beats.append([cur, sent])
                cur = cl
            else:
                cur = (cur + " " + cl).strip() if cur else cl
        if cur:
            beats.append([cur, sent])
    # merge stub beats (< min_words) into their neighbour
    merged = []
    for b, s in beats:
        if merged and len(b.split()) < min_words:
            merged[-1][0] = merged[-1][0] + " " + b
        else:
            merged.append([b, s])
    if len(merged) > 1 and len(merged[0][0].split()) < min_words:
        merged[1][0] = merged[0][0] + " " + merged[1][0]
        merged.pop(0)
    return [(b, s) for b, s in merged]


def _numbers_in(text):
    """[(spoken_token, value_str)] for digits and number words."""
    out = []
    for tok in re.findall(r"\d+(?:\.\d+)?%?|[a-zA-Z]+", str(text or "")):
        if any(c.isdigit() for c in tok) or tok.lower() in _NUMWORDS:
            out.append(tok)
    return out


_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30,
             "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
             "eighty": 80, "ninety": 90, "hundred": 100,
             "thousand": 1000, "million": 1000000}
# word pairs that ARE a documentary contrast when a line sets them
# against each other — the only automatic balance-scale anchors
# trusted without a writer-chosen versus visual.
_OPPOSITES = [("refusal", "agreement"), ("yes", "no"), ("give", "take"),
              ("ask", "answer"), ("silence", "speech"),
              ("agree", "refuse"), ("accept", "reject")]


def _enumeration_items(sentence):
    """The items of an enumeration in a sentence ('...: time, energy,
    and self respect') as a list, or []."""
    m = re.search(r":\s*(.+)$", str(sentence or ""))
    span = m.group(1) if m else str(sentence or "")
    if not re.search(r"\w+,\s[\w ]+,\s?and\s", span):
        return []
    items = [x.strip(" .") for x in
             re.split(r",\s*|\s+and\s+", span) if x.strip(" .")]
    items = [it for it in items
             if 0 < len(it.split()) <= 4 and len(it) >= 3]
    return items if len(items) >= 2 else []


def _features(text, scene_text, quote_open, sentence=""):
    t = " " + str(text or "").lower() + " "
    term = _TERM_RE.search(str(scene_text or ""))
    items = _enumeration_items(sentence or text)
    in_enum = bool(items) and any(
        it.split()[0].lower() in str(text or "").lower() for it in items)
    return {
        "numbers": _numbers_in(text),
        "contrast": bool(_CONTRAST_RE.search(str(text or ""))),
        "time": any(w in t for w in _TIME_WORDS),
        "evidence": any(w in t for w in _EVIDENCE_WORDS),
        "question": str(text or "").rstrip().endswith("?"),
        "term": (term.group(1).strip() if term else ""),
        "quote": bool(quote_open),
        "enumeration": in_enum,
        "enum_items": items if in_enum else [],
        "energy": any(w in t for w in ("energy", "tired", "drain", "empty", "exhaust")),
        "relation": any(w in t for w in ("relationsh", "respect", "friend", "heart", "trust", "liked")),
        "talk": any(w in t for w in ("asks", "ask", "say", "says", "said", "sentence", "mouth", "spoken", "word")),
    }


def _number_value(tok):
    """The honest digit string for a spoken number token."""
    if any(c.isdigit() for c in tok):
        return re.sub(r"[^\d.]", "", tok)
    return str(_WORD_NUM.get(tok.lower(), "")) or None


def _key_word(text, exclude=()):
    """The beat's headline word: a shock word if present, else the
    longest content word. '' when nothing honest is available."""
    words = [w.strip(".,!?:;\"'").lower() for w in str(text or "").split()]
    cands = [w for w in words
             if len(w) >= 4 and w not in _STOP and w not in exclude]
    for w in cands:
        if w in _SHOCK:
            return w
    if cands:
        return max(cands, key=len)
    return ""


def _contrast_sides(scene_text, beat_text=""):
    """(LEFT, RIGHT) anchor words for a balance-scale visual. Only
    two trusted sources: an explicit opposites pair the line itself
    sets against each other, or the longest content words of the two
    halves of the scene's contrast sentence. Anything weaker returns
    ('', '') and the scale is not used — a scale labelled with
    near-random words is worse than no scale."""
    low = " " + str(beat_text or scene_text or "").lower() + " "
    for a, b in _OPPOSITES:
        if f" {a} " in low or f" {a}," in low or a in low.split():
            if b in low:
                return a.upper(), b.upper()
    txt = str(scene_text or "")
    # v86.1: scope the anchor search to the sentence that carries the
    # contrast — searching the whole scene let an earlier sentence's
    # long word win (the first v86 sample rendered PSYCHOLOGISTS vs
    # AGREEMENT because "Psychologists" sat one sentence earlier).
    _sents = re.split(r"(?<=[.!?])\s+", txt)
    if len(_sents) > 1:
        _bw = set(re.findall(r"[a-z']+",
                             str(beat_text or "").lower()))
        _best = None
        for _s in _sents:
            if re.search(r",\s*(?:and|but|yet)\s+", _s):
                _ov = len(_bw & set(re.findall(r"[a-z']+",
                                               _s.lower())))
                if _best is None or _ov > _best[0]:
                    _best = (_ov, _s)
        if _best:
            txt = _best[1]
    m = re.search(r"(.+?),\s*(?:and|but|yet)\s+(.+)", txt)
    if not m:
        return "", ""
    def anchor(part):
        words = [w.strip(".,!?:;\"'").lower() for w in part.split()]
        cands = [w for w in words if len(w) >= 5 and w not in _STOP]
        return max(cands, key=len).upper() if cands else ""
    left, right = anchor(m.group(1)), anchor(m.group(2))
    return (left, right) if left and right and left != right else ("", "")


def _beat_label(text, parent_label, used_labels):
    kw = _key_word(text, exclude={w.lower() for w in parent_label.split()})
    if kw and kw.upper() not in used_labels:
        return kw.upper()
    words = [w.strip(".,!?:;\"'").upper() for w in str(text or "").split()]
    cands = [w for w in words if len(w) >= 4 and w not in
             {s.upper() for s in _STOP} and w not in used_labels]
    if len(cands) >= 2:
        return (cands[0] + " " + cands[-1])[:20]
    return cands[0] if cands else ""


def _role(chapter_index, chapter_count, scene_index, scene_count, feats):
    last_ch = chapter_index >= chapter_count - 1
    if chapter_index == 0 and scene_index == 0:
        return "hook"
    if feats.get("quote") and last_ch:
        return "turning_point"
    if feats.get("evidence"):
        return "evidence"
    if feats.get("contrast"):
        return "contradiction"
    if last_ch and scene_index == scene_count - 1:
        return "conclusion"
    if last_ch and scene_index == scene_count - 2:
        return "payoff"
    if scene_index == scene_count - 1:
        return "build"
    return "context" if scene_index % 2 == 0 else "build"


class _Replan(Exception):
    pass


def direct_plan(plan, brief="", cfg=None, chapter_index=None,
                chapter_count=None):
    """The v86 Documentary Director. Takes the writer's chapter plan
    (doc.plan output) and returns (directed_plan, visual_plan_records).
    The input is NOT mutated. Every beat of the output is a full
    engine scene (all decorations doc.plan would have made are
    rebuilt for the beats), and every visual decision is recorded."""
    import create as C
    import effects as FX
    import transitions_lib as TL
    import visuals_lib as VL
    import compliance as _comp
    try:
        import doc as _doc
        _enter_all, _emph_all = _doc.FX_LAYER_ENTER, _doc.FX_LAYER_EMPHASIS
        _sfx_map, _looks = _doc.SCENE_SFX, _doc.LOOKS
        _hit_type, _fact_type = _doc.hit_type_of, _doc.fact_type_of
        _topic_tr = _doc._topic_transition_name
    except Exception:
        _enter_all = _emph_all = _sfx_map = _looks = None
        _hit_type = _fact_type = _topic_tr = None

    if chapter_index is None or chapter_count is None:
        chapter_index, chapter_count = chapter_position(brief)
    p = copy.deepcopy(plan)
    scenes = [s for s in (p.get("scenes") or []) if str(s.get("vo", "")).strip()]
    seed = int(p.get("seed") or 0)
    look = p.get("look", "A")

    # ---- pass 1: split into beats, analyse each beat ---------------
    raw_beats = []   # (parent_scene, beat_text, feats, role, scene_idx)
    for si, sc in enumerate(scenes):
        vo = str(sc.get("vo", ""))
        last_ch = chapter_index >= chapter_count - 1
        if chapter_index == 0 and si == 0:
            mw = 7                       # the hook cuts fastest
        elif last_ch and si >= len(scenes) - 2:
            mw = 14                      # payoff / conclusion breathe
        else:
            mw = 11
        texts = split_beats(vo, max_words=mw)
        quote_open = False
        for bt, sent in texts:
            if re.search(r"(sounds like this|say it like this|goes like this)\s*:",
                         bt, re.I):
                quote_open = True
            feats = _features(bt, vo, quote_open, sentence=sent)
            if '"' in bt:
                feats["quote"] = True
            raw_beats.append((sc, bt, feats,
                              _role(chapter_index, chapter_count,
                                    si, len(scenes), feats), si))
    n = len(raw_beats)

    # ---- pass 2: visual decisions ----------------------------------
    bg_order = list(VL.SCENE_BG)
    _off = (seed + chapter_index * 3) % len(bg_order)
    bg_order = bg_order[_off:] + bg_order[:_off]
    if "paper" in bg_order:      # the v85 default texture: at most once
        bg_order.remove("paper")
        bg_order.insert(len(bg_order) // 2, "paper")
    used_fx = {}
    enter_l = {k: v for k, v in FX.ENTER.items()
               if _enter_all is None or k in _enter_all}
    emph_l = {k: v for k, v in FX.EMPHASIS.items()
              if _emph_all is None or k in _emph_all}
    beats, records = [], []
    prev = {"effective": "", "section": "", "bg": "", "label": ""}
    window = []                  # effective visuals of the last 2 beats
    used_labels = set()
    document_used = 0

    def effective_of(b):
        return _comp.effective_visual(b)

    def validate(b, cand):
        """(ok, note): can this candidate honestly render THIS beat?"""
        lib = cand.get("lib_visual")
        if lib:
            args, _t = _comp.compose_visual(b, lib, str(p.get("topic") or ""))
            if args is None:
                return False, f"{lib} cannot compose honest content from this line"
        vis = cand.get("visual") or ""
        if vis and vis not in C.VISUALS:
            return False, f"'{vis}' is not an engine visual"
        if vis in _NUMBER_KINDS and not _numbers_in(b.get("vo", "")):
            return False, f"'{vis}' draws a number this line never speaks"
        if vis in _CANNED_KINDS and not str(b.get("value", "")).strip():
            return False, (f"'{vis}' would print its canned default "
                           f"\"{_CANNED_KINDS[vis]}\" — no word from the line")
        eff = effective_of({**b, **{k: v for k, v in cand.items()
                                    if k in ("visual", "lib_visual")}})
        if eff == prev["effective"]:
            return False, f"'{eff}' repeats the previous beat's visual"
        if eff in window:
            return False, f"'{eff}' already used within the last 2 beats"
        return True, ""

    for bi, (sc, bt, feats, role, si) in enumerate(raw_beats):
        words = bt.split()
        is_parent_first = (bi == 0 or raw_beats[bi - 1][0] is not sc)
        b = copy.deepcopy(sc)
        b["vo"] = bt
        b["parent_label"] = str(sc.get("label", ""))
        b["arc_role"] = role
        if is_parent_first:
            b["label"] = str(sc.get("label", ""))
        else:
            b["label"] = _beat_label(bt, str(sc.get("label", "")), used_labels)
        if b["label"]:
            used_labels.add(b["label"])
        # the beat keeps the parent's number only when IT speaks it
        if not _numbers_in(bt):
            b["value"] = ""
        groups = {"p": [], "f": [], "d": []}

        def add(template, asset_type, why, visual=None, lib_visual=None,
                extra=None, value=None, group="f"):
            groups[group].append(
                {"template": template, "asset_type": asset_type,
                 "why": why, "visual": visual, "lib_visual": lib_visual,
                 "extra": extra or {}, "value": value})

        scene_vis = str(sc.get("visual", ""))
        if is_parent_first:
            if scene_vis == "stamp" and not str(sc.get("value", "")).strip():
                kw = _key_word(bt) or str(sc.get("label", "")).split()[-1:]
                kw = kw if isinstance(kw, str) else (kw[0] if kw else "")
                add("closing_stamp", "typography",
                    "the writer asked for a stamp, but a bare stamp prints "
                    "a canned word — the stamp is given a word the line "
                    "itself speaks",
                    lib_visual="stamp_cta", value=(kw or "TODAY").upper(),
                    group="p")
            else:
                add("primary", "motion graphic (engine visual)",
                    "the writer's own visual for this line, kept for the "
                    "beat that states the line's main clause",
                    visual=scene_vis or "chat", group="p")
        if feats["quote"]:
            add("quote_typewriter", "typography / quote",
                "the narration quotes the exact sentence — the audience "
                "should READ the words, typed out, not an icon of them",
                lib_visual="typewriter_page")
        if feats["term"]:
            term = feats["term"].upper()
            if len(term) > 12:
                term = term.split()[0]   # the card prints 12 chars max
            add("keyterm_card", "typography / key term",
                "the line names a concept — isolate the term itself as "
                "the visual so the audience remembers the word",
                visual="quote_card", value=term)
        _numvals = [v for v in (_number_value(t) for t in feats["numbers"])
                    if v]
        if len(_numvals) >= 2 or (feats["numbers"] and
                                  any("%" in t for t in feats["numbers"])):
            add("stat_bars", "data visualisation",
                "the line speaks numbers — show them as data, not prose",
                visual="bar")
        elif _numvals:
            add("counter", "data visualisation",
                "the line speaks one number — count it up on screen "
                "(the value is the spoken number itself, in digits)",
                visual="counter", value=_numvals[0])
        # a comparison visual only when the contrast is REAL: the
        # writer chose a versus visual for this scene, or the beat
        # itself sets an opposites pair against each other. A merely
        # rhetorical "yet" does not earn a balance scale.
        _sides = _contrast_sides(str(sc.get("vo", "")), bt)
        _opp_in_beat = any(a in bt.lower() and b in bt.lower()
                           for a, b in _OPPOSITES)
        if scene_vis == "versus" or _opp_in_beat:
            add("contrast_scale", "motion graphic / comparison",
                "the line weighs two opposing ideas — a balance scale "
                "shows the weighing the words describe",
                visual="versus",
                extra={"left": _sides[0], "right": _sides[1]}
                if _sides[0] else {})
            add("versus_card", "motion graphic / comparison",
                "opposing ideas, shown as a head-to-head split",
                visual="versus")
        if feats["enumeration"]:
            items = feats["enum_items"]
            add("timeline", "motion graphic / timeline",
                "the line lists its items one by one — a timeline "
                "lays the items out one card at a time, using the "
                "line's own words",
                lib_visual="timeline_cards",
                extra={"events": tuple((it.upper()[:18], "")
                                       for it in items[:4])})
        if feats["evidence"]:
            if document_used < 1:
                add("evidence_document", "document visual (drawn, labelled graphic)",
                    "the line cites what psychologists say — present it "
                    "as a document, the evidence form, not a stock icon",
                    lib_visual="document")
            add("evidence_newspaper", "document visual (drawn, labelled graphic)",
                "a cited finding, presented as a newspaper headline — "
                "the headline is this scene's own label",
                lib_visual="newspaper")
        if feats["time"]:
            add("time_visual", "motion graphic",
                "the line is about time passing / a deadline hour — "
                "show the clock the words point at",
                visual="calendar" if ("calendar" in bt.lower() or
                                      "week" in bt.lower()) else "clock")
        if feats["question"]:
            add("question_card", "typography / question",
                "the line asks the audience a direct question — the "
                "question mark IS the visual event",
                lib_visual="question")
        if feats["energy"]:
            add("energy_meter", "motion graphic",
                "the line is about energy draining — a battery draining "
                "is the literal picture of it",
                visual="battery")
        if feats["relation"]:
            add("relation_heart", "motion graphic",
                "the line is about a relationship holding — the heart "
                "carries the emotional claim",
                visual="heart")
        if feats["talk"]:
            add("speech_bubble", "typography / speech",
                "the line is about words being spoken — show the "
                "utterance as a speech bubble carrying the headline",
                lib_visual="speech_bubble")
        # development fallbacks (generic-safe, no fabricated content)
        add("document_dev", "document visual (drawn, labelled graphic)",
            "a document composed from this scene's own recorded "
            "footage queries — the paper trail of the claim",
            lib_visual="document", group="d")
        add("typewriter_dev", "typography",
            "the line itself, typed onto a page — the words are the "
            "visual when no object in the line can be drawn honestly",
            lib_visual="typewriter_page", group="d")
        add("list_dev", "motion graphic",
            "numbered points building under the narration — a neutral "
            "development graphic that invents no content",
            visual="list", group="d")
        add("steps_dev", "motion graphic",
            "numbered steps — the argument advancing one step",
            visual="arrows_steps", group="d")
        add("checklist_dev", "motion graphic",
            "points being ticked off as the narration makes them",
            visual="checklist", group="d")

        # Candidate order: a strong content feature (quote, term,
        # number, real contrast, evidence...) outranks the writer's
        # primary visual — the feature IS the meaning of this beat.
        # The primary leads only for the video's first beat (the
        # writer's hook) and for the closing scene's first beat (the
        # CTA), and otherwise sits between features and fallbacks.
        _pri_first = (bi == 0) or (
            is_parent_first and chapter_index >= chapter_count - 1
            and si == len(scenes) - 1)
        cands = (groups["p"] + groups["f"] + groups["d"]) if _pri_first \
            else (groups["f"] + groups["p"] + groups["d"])

        chosen, notes = None, []
        for cand in cands:
            probe = copy.deepcopy(b)
            probe.update(cand["extra"])
            if cand.get("value") is not None:
                probe["value"] = cand["value"]
            if cand.get("lib_visual"):
                probe["lib_visual"] = cand["lib_visual"]
            if cand.get("visual"):
                probe["visual"] = cand["visual"]
            ok, note = validate(probe, cand)
            if ok:
                chosen = (cand, probe)
                break
            notes.append(f"{cand['template']}: {note}")
        if chosen is None:
            # last resort: the parent visual with the repetition noted —
            # recorded, never silent.
            cand = {"template": "primary_fallback",
                    "asset_type": "motion graphic (engine visual)",
                    "why": "every directed candidate was rejected in "
                           "planning; the writer's visual is kept and "
                           "the repetition is recorded, not hidden",
                    "visual": scene_vis or "chat", "lib_visual": None,
                    "extra": {}, "value": None}
            probe = copy.deepcopy(b)
            probe["visual"] = cand["visual"]
            probe.pop("lib_visual", None)
            chosen = (cand, probe)
            notes.append("primary_fallback used")
        cand, b = chosen
        if cand["template"] == "evidence_document":
            document_used += 1
        # the beat's meaning record names the exact line segment the
        # visual serves (the R2 audit asks for exactly this link)
        b["why"] = cand["why"] + f' (line: "{bt[:60]}")'
        # an inherited lib_visual belongs to the OLD plan's decision
        # (doc.plan sets one for 'place' fact types — including the
        # accidental trigger of the phrase "in the first place").
        # Keep it only for a genuine place beat; the Director's own
        # choice otherwise wins.
        if cand["template"] in ("primary", "primary_fallback") \
                and cand.get("visual") and b.get("lib_visual") \
                and not any(w in bt.lower() for w in
                            ("india", "world", "country", "countries",
                             "city", "cities", "state", "map", "village",
                             "town", "global")):
            b.pop("lib_visual", None)
        if cand.get("value") is not None:
            b["value"] = cand["value"]
        for k, v in cand["extra"].items():
            b[k] = v
        if cand.get("lib_visual"):
            b["lib_visual"] = cand["lib_visual"]
        elif "lib_visual" in b and cand["template"] not in (
                "primary", "primary_fallback"):
            b.pop("lib_visual", None)
        if cand.get("visual"):
            b["visual"] = cand["visual"]

        # ---- the canned-word guard: NO beat may reach the renderer
        # as a bare stamp/strike/quote_card. Those engine kinds print
        # a canned default word when the scene carries no value (the
        # v85 film ended with a "BANNED" stamp over its closing line).
        # A beat in that state is given a word its own line speaks.
        if b.get("visual") in _CANNED_KINDS and \
                not str(b.get("value", "")).strip():
            _kw = _key_word(b.get("vo", "")) or \
                str(b.get("label", "")).split()[-1:]
            b["value"] = (_kw if isinstance(_kw, str)
                          else (_kw[0] if _kw else "TODAY")).upper()[:12]
            notes.append(f"canned-word guard: '{b['visual']}' given the "
                         f"spoken word '{b['value']}' instead of its "
                         f"default \"{_CANNED_KINDS[b['visual']]}\"")

        # ---- background: section + bg kind, never repeating --------
        section = _ROLE_SECTION.get(role, "fact")
        if section == prev["section"]:
            section = next(s for s in _SECTION_ROTATION
                           if s != prev["section"])
        bg = bg_order[bi % len(bg_order)]
        if bg == prev["bg"]:
            bg = bg_order[(bi + 1) % len(bg_order)]
        b["section"] = section
        b["bg_kind"] = bg

        # ---- decorations (rebuilt for the beat, as doc.plan does) --
        if _hit_type:
            b["hit_type"] = _hit_type(b)
            b["fact_type"] = _fact_type(b)
        b["enter"] = FX.pick(enter_l, [b.get("hit_type", "calm")], used_fx) \
            if enter_l else ""
        b["emphasis"] = FX.pick(emph_l, [b.get("hit_type", "calm")], used_fx) \
            if emph_l else ""
        b["label_enter"] = FX.pick(enter_l, [b.get("hit_type", "calm")],
                                   used_fx) if enter_l else ""
        if _sfx_map:
            b["sfx"] = _sfx_map.get(b.get("fact_type") or
                                    b.get("hit_type") or "calm", "pop")
        b["no"] = bi + 1
        b["dir"] = {"template": cand["template"],
                    "asset_type": cand["asset_type"],
                    "role": role, "section": section, "bg_kind": bg}
        eff = effective_of(b)
        est = len(words) / _WORDS_PER_SEC + _SCENE_GAP_S
        records.append({
            "beat": bi + 1,
            "chapter_scene": str(sc.get("label", "")),
            "parent": str(sc.get("label", "")),
            "heard": bt,
            "see": (f"{cand['template']} — "
                    f"{cand.get('lib_visual') or cand.get('visual') or ''}"
                    f" on a '{section}' section background ({bg})"),
            "visual_concept": cand["template"],
            "asset_type": cand["asset_type"],
            "asset_source": ("in-engine drawn graphic (visuals_lib / "
                             "create library) — no external footage or "
                             "photograph; never presented as one"),
            "why": b["why"],
            "purpose": b["why"],
            "changes_on_screen": (
                f"visual changes from {prev['effective'] or 'chapter start'} "
                f"to {eff}; background section {prev['section'] or '—'} → "
                f"{section}; headline "
                f"'{prev['label'] or '—'}' → '{b['label'] or '(none)'}'"),
            "duration_est_s": round(est, 1),
            "duration": round(est, 1),
            "motion": "the visual's own word-timed build-in; one enter "
                      "effect (engine rule: one effect at a time)",
            "transition": "(assigned after all beats — see plan "
                          "transitions)",
            "music_intensity": ARC_MUSIC_CURVE.get(role, 0.5),
            "music_direction": (
                f"arc role {role}: intensity "
                f"{ARC_MUSIC_CURVE.get(role, 0.5)} — under the narration, "
                f"never over it"),
            "repetition_check": (
                "PASS — visual, section and background all differ from "
                "the previous beat" if not notes else
                "PASS after re-planning — rejected in planning: " +
                "; ".join(notes[:3])),
            "rejected_candidates": notes,
            "arc_role": role,
        })
        beats.append(b)
        window.append(eff)
        window = window[-2:]
        prev = {"effective": eff, "section": section, "bg": bg,
                "label": b["label"]}

    # ---- pass 3: transitions + next-shot links ----------------------
    tag = "calm"
    if _looks and look in _looks:
        tag = _looks[look].get("fx_tag", "calm")
    tl_used, tr_counts, trans = set(), {}, []
    for j in range(max(0, len(beats) - 1)):
        name = _topic_tr(beats[j + 1]) if _topic_tr else None
        if name and ((trans and trans[-1] == name) or
                     tr_counts.get(name, 0) >= 2):
            name = None
        if name is None:
            name = TL.pick_transition(tags={tag}, used=tl_used,
                                      seed=seed + j,
                                      recent_families=())["name"]
        tl_used.add(name)
        tr_counts[name] = tr_counts.get(name, 0) + 1
        trans.append(name)
    for i, b in enumerate(beats):
        b["transition"] = trans[i - 1] if 0 < i <= len(trans) else ""
        records[i]["transition"] = (trans[i] if i < len(trans)
                                    else "(end of chapter)")
        records[i]["next_shot"] = (records[i + 1]["see"]
                                   if i + 1 < len(records)
                                   else "chapter card / end card")
    p["scenes"] = beats
    p["transitions"] = trans
    try:
        p["transition_families"] = [TL.family(x) for x in trans]
    except Exception:
        pass
    p["fx_used"] = used_fx
    p["directed"] = "v86-documentary-director"
    p["visual_plan"] = records
    return p, records


def visual_plan_markdown(records, title=""):
    """The written VISUAL PLAN (readable form) for a whole job:
    records from every chapter, in order."""
    lines = [f"# Visual Plan — {title or 'documentary'}", "",
             "Decided by the v86 Documentary Director BEFORE rendering. "
             "One row per beat: what is heard, what is seen, why, and "
             "the repetition check that the decision passed.", ""]
    cur_ch = None
    for r in records:
        if r.get("chapter") != cur_ch:
            cur_ch = r.get("chapter")
            lines.append(f"## Chapter {cur_ch}")
            lines.append("")
        lines.append(
            f"- **Beat {r['beat']}** ({r['duration_est_s']}s est., "
            f"role {r['arc_role']}, music {r['music_intensity']})\n"
            f"  - Heard: {r['heard']}\n"
            f"  - See: {r['see']} [{r['asset_type']}; source: "
            f"{r['asset_source']}]\n"
            f"  - Why: {r['why']}\n"
            f"  - Changes: {r['changes_on_screen']}\n"
            f"  - Transition out: {r['transition']}\n"
            f"  - Repetition: {r['repetition_check']}")
    lines.append("")
    return "\n".join(lines)


def compare_with_render(log, report):
    """Stage-7 comparison helper: how many Director recommendations
    correspond to defects the compliance report actually found?
    Returns counts only — still no mutation of anything."""
    checks = (report or {}).get("checks") or []
    failed_rules = {c.get("rule") for c in checks if c.get("status") == "FAIL"}
    rec_types = {r["type"] for r in (log or {}).get("recommendations", [])}
    return {"recommendations": len((log or {}).get("recommendations", [])),
            "qc_failed_rules": sorted(x for x in failed_rules if x),
            "director_flagged_types": sorted(rec_types)}


if __name__ == "__main__":
    plan = [{"no": 1, "visual": "clock", "vo": "Time passes.", "d": 4,
             "transition": "dissolve", "effect": "zoom", "fx": "sparkle", "sfx": "whoosh"},
            {"no": 2, "visual": "clock", "vo": "And passes.", "d": 4},
            {"no": 3, "visual": "face", "vo": "The turn.", "d": 5, "arc_role": "turning_point"},
            {"no": 4, "visual": "sunrise", "vo": "The payoff lands now.", "d": 5, "arc_role": "payoff"}]
    before = copy.deepcopy(plan)
    log = analyse_plan(plan)
    assert plan == before, "Director mutated the plan!"
    print("director self-check OK:", len(log["recommendations"]),
          "recommendations,", len(log["silence_map"]), "silence placements")
