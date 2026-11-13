"""compliance.py — Julie v79: the auto-checklist (Blind/Hark mail 1
Part 4, mail 3 R1-R12, mail 2 FIX 5).

Every rule Blind wrote is checked BY CODE, on the plan (scenes.json
level, before render — where a failing scene can still be re-picked)
and on the rendered file (ffprobe / loudness / silence / frame
sampling). Results land in compliance_report.json next to the video,
with a per-requirement PASS / FAIL / UNVERIFIED verdict (FIX 5): a
requirement is only PASS with evidence; anything else is said plainly
(R-P7's done / not-done line is built from this report).

Plan repairs (fix rounds, max 2 — FIX 5 / R12) mutate ONLY plan
fields: a scene's visual (within the widget budget + the
widget-by-number-kind table), its title, its transition / SFX /
background kind (the 3-of-6 rule), a banned leftover word. The voice
line itself is never rewritten by a repair.
"""

import json
import os
import re
import subprocess

# ------------------------------------------------------------------
# Rule constants (quoted from the mails; see the spec files)
# ------------------------------------------------------------------
# Mail 1: ban list HOOK, INTRO, CTA, OUTRO, RISK, SCENE, FIG.
# Mail 3 R6: HOOK, FACT, CTA, TEASE, NEXT, RECAP, VISUAL, DATA, STATS,
# SETUP, METAPHOR, INSIGHT, CAUTION (+ E14's TEASER, WATCH, FOLLOW and
# the STAY TUNED / NEXT cards of R8).
BANNED_TITLES = {
    "HOOK", "INTRO", "CTA", "OUTRO", "RISK", "SCENE", "FIG", "FACT",
    "TEASE", "TEASER", "NEXT", "RECAP", "VISUAL", "DATA", "STATS",
    "SETUP", "METAPHOR", "INSIGHT", "CAUTION", "WATCH", "FOLLOW",
    "STAY TUNED", "STAY", "TUNED", "INTRODUCTION", "CONCLUSION",
}
# R3: template leftovers from other topics' videos (the tobacco /
# alcohol template in a compromise video). A word is only a leftover
# when the video's own topic is NOT about that subject.
LEFTOVER_WORDS = ["TOBACCO", "GUTKA", "CALL FOR HELP", "HELPLINE",
                  "QUITLINE", "COST", "HEALTH"]
LEFTOVER_OK_TOPICS = ("tobacco", "gutka", "smoking", "alcohol",
                      "health", "drug", "addiction", "quit")
# Sensitive-topic calm titles (mail 1 point 9).
CALM_TITLES = {"RAPES": "SEXUAL VIOLENCE", "RAPE": "SEXUAL VIOLENCE",
               "SUICIDE": "MENTAL HEALTH", "MURDER": "VIOLENT CRIME"}
# Caption chunks must never end on a weak word (mail 1 Part 3).
WEAK_END_WORDS = {"a", "an", "the", "and", "or", "but", "how", "of",
                  "to", "in", "on", "for", "with", "is", "are", "was",
                  "were", "it", "its", "that", "this", "at", "by",
                  "from", "as", "if", "so", "do", "does"}
# Visual kinds that count against the widget budget (mail 1 Part 3 /
# R1: donut, counter, line chart, bar, map, icon, heart, document,
# newspaper, timeline, split-compare, icon grid, quote card, photo
# card; mail 3 adds clock + gauge).
WIDGET_KINDS = {
    "counter", "donut", "gauge", "clock", "watch", "bar", "bar_compare",
    "graph", "curve", "list", "checklist", "icon_row", "dot_grid",
    "heart", "document", "timeline", "versus", "quote_card", "polaroid",
    "four", "card", "chat", "warning", "check", "battery", "calendar",
    "toggle", "phone_buzz", "stick_figure", "question", "arrows_steps",
    "stamp", "stamp_cta", "strike",
}
_LIB_ALIAS = {"balance_scale": "versus", "bracket_bars": "bar",
              "warning_sign": "warning", "india_map": "map",
              "world_dots": "map"}
ROUND_KINDS = {"clock", "watch", "donut", "gauge"}  # mail 3's repeat offenders
TIME_WORDS = {"time", "clock", "second", "seconds", "minute", "minutes",
              "hour", "hours", "day", "days", "year", "years", "ago",
              "deadline", "schedule", "wait", "waiting", "duration",
              "every", "per"}


def widget_kind(scene):
    """The budget kind a scene spends, or None (footage / no widget)."""
    v = str(scene.get("visual") or "")
    if v in WIDGET_KINDS:
        return v
    lv = str(scene.get("lib_visual") or "")
    if lv in _LIB_ALIAS:
        return _LIB_ALIAS[lv]
    if lv:
        return lv
    return None


# A4 (Ajju, 2026-11-13): the graphics that must NEVER be pasted over
# a footage subject — number widgets and icon widgets (the ASSAULTS
# warning triangle on the hand/bottle is the canonical failure).
# When one of these goes over footage, the footage is blurred +
# darkened so the graphic owns a treated frame (Blind mail 1 Part
# 2). Composed scene types (document, photo frame, timeline,
# versus...) are NOT in this set: they are full composed scenes,
# not pasted-on graphics.
BLUR_TREATMENT_VISUALS = {
    "counter", "donut", "gauge", "clock", "watch", "bar",
    "bar_compare", "graph", "curve", "dot_grid", "heart", "icon_row",
    "four", "warning", "warning_sign", "check", "battery", "calendar",
    "toggle", "phone_buzz", "stick_figure", "question",
    "arrows_steps", "stamp", "strike",
}


def needs_blur_treatment(scene):
    """True when the scene's graphic is a pasted-on widget/icon (A4)."""
    v = str(scene.get("visual") or "")
    if v in BLUR_TREATMENT_VISUALS:
        return True
    lv = str(scene.get("lib_visual") or "")
    return lv in BLUR_TREATMENT_VISUALS


# ------------------------------------------------------------------
# Numbers (R4 + mail 1 stat rules)
# ------------------------------------------------------------------
_NUMWORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
             "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
             "fourteen": 14, "fifteen": 15, "sixteen": 16,
             "seventeen": 17, "eighteen": 18, "nineteen": 19,
             "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
             "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1_000, "lakh": 100_000,
           "million": 1_000_000, "crore": 10_000_000,
           "billion": 1_000_000_000}


def _word_number(tokens, i):
    """Parse a number-word phrase starting at tokens[i] -> (value, n)
    or (None, 0). Handles 'two hundred thousand', 'thirty', 'half'
    (0.5) approximately — enough to compare a spoken number with the
    on-screen value."""
    total, cur, n = 0.0, 0.0, 0
    seen = False
    while i < len(tokens):
        t = tokens[i].strip(".,!?\"'").lower()
        if t in _NUMWORDS:
            cur += _NUMWORDS[t]; seen = True; n += 1; i += 1
        elif t in _SCALES:
            sc = _SCALES[t]
            if sc >= 1000:
                total = (total + (cur or 1)) * sc; cur = 0.0
            else:
                cur = (cur or 1) * sc
            seen = True; n += 1; i += 1
        elif t == "half":
            cur += 0.5; seen = True; n += 1; i += 1
        elif t == "and" and seen:
            i += 1
        else:
            break
    return ((total + cur), n) if seen else (None, 0)


def spoken_numbers(text):
    """All numbers a line speaks: [(value, unit)] with unit in
    {'%', 'x', ''}. Digit forms and number words both count."""
    text = str(text or "")
    out = []
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(%|percent|x\b|times)?", text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = "%" if (m.group(2) in ("%", "percent")) else ("x" if m.group(2) in ("x", "times") else "")
        out.append((v, unit))
    toks = text.split()
    i = 0
    while i < len(toks):
        v, n = _word_number(toks, i)
        if v is not None and n:
            unit = ""
            tail = " ".join(toks[i + n:i + n + 2]).lower()
            if "percent" in tail or "%" in tail:
                unit = "%"
            elif "times" in tail:
                unit = "x"
            out.append((v, unit))
            i += n
        else:
            i += 1
    # "one in four" style ratios the one_in_n visual speaks
    m = re.search(r"\b(one|two|three|1|2|3)\s+in\s+(four|five|six|ten|4|5|6|10)\b", text.lower())
    if m:
        a = _NUMWORDS.get(m.group(1), None) or float(m.group(1))
        b = _NUMWORDS.get(m.group(2), None) or float(m.group(2))
        out.append((a / b, "ratio"))
    return out


def parse_value(raw):
    """A scene's on-screen value -> (value, unit) or (None, '')."""
    s = str(raw or "").strip()
    if not s:
        return None, ""
    m = re.match(r"^([\d,]+(?:\.\d+)?)\s*(%|x)?$", s)
    if m:
        return float(m.group(1).replace(",", "")), (m.group(2) or "")
    m = re.match(r"^(\d+)\s*(?:in|/)\s*(\d+)$", s)
    if m:
        return float(m.group(1)) / float(m.group(2)), "ratio"
    toks = s.replace("%", " % ").split()
    v, n = _word_number(toks, 0)
    if v is not None:
        return v, ("%" if "%" in s else "")
    return None, ""


_CYCLE_WORDS = ("cycle", "circle", "circular", "ring", "loop",
                "wheel", "orbit", "rotation", "rotating", "round")


def _cycle_line(txt):
    """The line is literally about a cycle / a round thing turning
    (a sleep cycle, a wheel, an orbit) — the ONLY lines a ring may
    illustrate (v79.2 ring discipline)."""
    return bool(re.search(r"\b(" + "|".join(_CYCLE_WORDS) + r")\b",
                          str(txt or "").lower()))


def _percent_of_whole(txt):
    """'30 percent of drivers' — a share of a whole, the case Blind's
    table gives to the donut / dot grid."""
    txt = str(txt or "").lower()
    return bool(re.search(r"percent\s+of\b", txt)
                or re.search(r"%\s*of\b", txt))


def widget_for_number_kind(vo, value):
    """Mail 1 Part 3 — choose the widget BY THE KIND OF NUMBER:
    percentage of a whole -> donut or 10x10 icon grid (dot_grid);
    'X times more' -> two bars side by side (bar_compare); count of
    people -> big counter + person icons (counter / four); change
    over years -> line chart (graph); ranking/compare -> horizontal
    bars or filled map; '1 every N seconds' -> clock/timer (watch).

    v79.2 (Ajju — ring discipline, 2026-11-13): the ring/donut is
    DEMOTED to a rare special. It is the default for NO plain
    percent: a percent that is not a share-of-a-whole and not a
    cycle line defaults to the big number COUNTER (or a bar). The
    test-1 heart scene (a 30% risk reduction) rendered the big
    round ring over the sleeper's face — the exact effect Ajju has
    repeatedly rejected. The ring survives for (a) a share of a
    whole (Blind's table) and (b) a line literally about a cycle /
    round thing."""
    txt = str(vo or "").lower()
    val, unit = parse_value(value)
    if re.search(r"\bevery\s+\d*\s*(second|minute|hour)s?\b", txt) or "per second" in txt or "per minute" in txt:
        return "watch"
    if re.search(r"\b(one|1|two|2|three|3)\s+in\s+(four|five|six|ten|4|5|6|10)\b", txt):
        return "four"
    if unit == "%" or "%" in str(value or "") or "percent" in txt:
        if _cycle_line(txt) or _percent_of_whole(txt):
            return "donut"
        return "counter"
    if unit == "x" or re.search(r"\btimes\s+(more|higher|likely)\b", txt):
        return "bar_compare"
    if re.search(r"\b(since|from)\s+\d{4}\b|\bover\s+the\s+years\b|\beach\s+year\b", txt):
        return "graph"
    if re.search(r"\b(people|deaths|users|children|men|women|patients|cases)\b", txt) and val is not None:
        return "counter"
    if val is not None:
        return "counter"
    return None


def acceptable_widgets_for_number(vo, value):
    """The widget kinds the audit accepts for this scene's number
    (the PART3-WIDGET check fails a number widget OUTSIDE this
    set). Mirrors widget_for_number_kind's branches; for a percent
    the acceptable set follows the ring discipline: cycle/share ->
    ring family (donut, dot_grid); a plain percent -> counter or
    bar, never the ring."""
    txt = str(vo or "").lower()
    val, unit = parse_value(value)
    if re.search(r"\bevery\s+\d*\s*(second|minute|hour)s?\b", txt) or "per second" in txt or "per minute" in txt:
        return {"watch"}
    if re.search(r"\b(one|1|two|2|three|3)\s+in\s+(four|five|six|ten|4|5|6|10)\b", txt):
        return {"four"}
    if unit == "%" or "%" in str(value or "") or "percent" in txt:
        if _cycle_line(txt) or _percent_of_whole(txt):
            return {"donut", "dot_grid"}
        return {"counter", "bar"}
    if unit == "x" or re.search(r"\btimes\s+(more|higher|likely)\b", txt):
        return {"bar_compare"}
    if re.search(r"\b(since|from)\s+\d{4}\b|\bover\s+the\s+years\b|\beach\s+year\b", txt):
        return {"graph"}
    if val is not None:
        return {"counter", "four"}
    return set()


# ------------------------------------------------------------------
# v79.2 — content composition + topic fidelity (defect 1 + the
# topic-fidelity guard). A content-bearing visual (document, stat,
# card, list...) may only render text composed from the CURRENT
# scene's own fields — its line, value, source, queries, label.
# The renderer used to fall back to visuals_lib's canned defaults:
# a past project's gutka notification rendered verbatim into a
# sleep video whose document scene was about the brain cleaning
# itself. compose_visual is the single composition source — doc.py's
# draw path passes its args to the visual, audit_plan checks the
# composed text against the scene (keyword overlap, the footage-query
# approach of broll._tokens / score_candidate) BEFORE render, and a
# visual that cannot compose honest content from a scene fails the
# audit for that scene (it must not be chosen for it).
# ------------------------------------------------------------------
CONTENT_TEXT_VISUALS = {"document", "receipt", "card", "newspaper",
                        "typewriter_page", "bracket_bars",
                        "balance_scale", "timeline_cards",
                        "product_packet", "question", "speech_bubble",
                        "stamp_cta"}
# Plan visual kind -> the visuals_lib name doc.py maps it to (mirrors
# doc._VIS_NAME_MAP; kept local so compliance stays importable
# without the engine).
_PLAN_TO_LIB = {"document": "document", "polaroid": "polaroid",
                "warning": "warning_sign", "bar": "bracket_bars",
                "bar_compare": "bracket_bars", "versus": "balance_scale"}
_FIDELITY_STOP = WEAK_END_WORDS | {
    "source", "report", "document", "value", "scene", "line", "video",
    "shows", "show", "visual", "percent"}


def effective_visual(scene):
    """The visual that will actually draw this scene's content:
    lib_visual wins, then the plan-kind map, then the plan kind."""
    lv = str(scene.get("lib_visual") or "")
    if lv:
        return lv
    v = str(scene.get("visual") or "")
    return _PLAN_TO_LIB.get(v, v)


def _fid_words(text):
    return {w for w in re.findall(r"[a-z]{3,}", str(text or "").lower())} - _FIDELITY_STOP


def _latin_line(text):
    """The scene's line when it is written in Latin script (the
    visuals' fonts carry no Telugu glyphs); '' otherwise — the
    scene's English queries / label carry the meaning then."""
    t = str(text or "").strip()
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return ""
    latin = sum(1 for c in letters if c.isascii())
    return t if latin >= 0.6 * len(letters) else ""


def compose_visual(scene, name=None, topic=""):
    """Compose a content-bearing visual's text args from THIS scene.
    Returns (args, text): args is the kwargs dict for the visual, or
    None when the scene carries nothing honest for it (the visual
    must not be chosen for this scene); text is every composed word,
    for the fidelity check. Non-content visuals return ({}, '')."""
    name = name or effective_visual(scene)
    if name not in CONTENT_TEXT_VISUALS:
        return {}, ""
    label = str(scene.get("label") or "").strip()
    value = str(scene.get("value") or "").strip()
    source = str(scene.get("source") or "").strip()
    vo = str(scene.get("vo") or "")
    vo_latin = _latin_line(vo)
    queries = [str(q).strip() for q in (scene.get("queries") or [])
               if str(q).strip()]

    if name == "document":
        lines = []
        for q in queries[:3]:
            lines.append(q[:1].upper() + q[1:].rstrip(".") + ".")
        if not lines and vo_latin:
            lines = [vo_latin]
        if source:
            lines.append(f"Source: {source}")
        if not lines and label:
            lines = [label.title()]
        if not lines:
            return None, ""
        stamp = ""
        if str(scene.get("fact_type") or "") == "ban" or \
                re.search(r"\b(banned|ban|prohibited|illegal)\b", vo.lower()):
            stamp = "BANNED"
        args = {"title": label.title() if label else "Report",
                "lines": tuple(lines), "stamp": stamp}
        return args, " ".join([args["title"]] + list(lines))
    if name == "receipt":
        pairs = []
        if isinstance(scene.get("items"), (list, tuple)):
            for it in scene["items"]:
                if isinstance(it, (list, tuple)) and len(it) == 2:
                    pairs.append((str(it[0]), str(it[1])))
        if not pairs:
            return None, ""
        total = str(scene.get("total") or value or "")
        args = {"items": tuple(pairs), "total": total}
        return args, " ".join(f"{a} {b}" for a, b in pairs) + " " + total
    if name == "card":
        m = re.search(r"\d[\d\s-]{6,}\d", value) or \
            re.search(r"\d[\d\s-]{6,}\d", vo)
        number = re.sub(r"\s+", " ", m.group(0)).strip() if m else ""
        if not number or len(re.sub(r"\D", "", number)) < 7:
            return None, ""
        args = {"title": label.title() or "Call for help",
                "subtitle": "", "number": number, "footer": ""}
        return args, f"{args['title']} {number}"
    if name == "newspaper":
        headline = label.title() if label else \
            (vo_latin.split(".")[0].strip() if vo_latin else "")
        if not headline:
            return None, ""
        return {"headline": headline}, headline
    if name == "typewriter_page":
        text = vo_latin or " ".join(
            x for x in [label.title(),
                        queries[0] if queries else ""] if x).strip()
        if not text:
            return None, ""
        return {"text": text}, text
    if name == "bracket_bars":
        nums = []
        pv, _pu = parse_value(value)
        if pv is not None:
            nums.append(pv)
        for v, _u in spoken_numbers(vo):
            if v not in nums:
                nums.append(v)
            if len(nums) >= 2:
                break
        if not nums:
            return None, ""
        args = {"values": tuple(nums),
                "labels": tuple("" for _ in nums), "note": value}
        return args, " ".join([label, value] +
                              [("%g" % n) for n in nums])
    if name == "balance_scale":
        left = str(scene.get("left") or "").strip()
        right = str(scene.get("right") or "").strip()
        if not (left and right):
            m = re.search(r"(.{2,24}?)\s+vs\.?\s+(.{2,24})",
                          label or vo_latin, re.I)
            if m:
                left, right = m.group(1).strip(), m.group(2).strip()
        if not (left and right):
            return None, ""
        args = {"left": left.upper(), "right": right.upper()}
        return args, f"{left} {right}"
    if name == "timeline_cards":
        pairs = []
        if isinstance(scene.get("events"), (list, tuple)):
            for ev in scene["events"]:
                if isinstance(ev, (list, tuple)) and len(ev) == 2:
                    pairs.append((str(ev[0]), str(ev[1])))
        if len(pairs) < 2:
            return None, ""
        return {"events": tuple(pairs)}, \
            " ".join(f"{a} {b}" for a, b in pairs)
    if name == "product_packet":
        brand = value if value and not any(c.isdigit() for c in value) \
            else label
        if not brand:
            return None, ""
        return {"brand": brand.upper()[:14], "sub": ""}, brand
    if name == "question":
        pack = (value or label)[:12].upper()
        if not pack:
            return None, ""
        return {"pack_text": pack}, pack
    if name == "speech_bubble":
        text = label.title() if label else vo_latin[:60].strip()
        if not text:
            return None, ""
        return {"text": text}, text
    if name == "stamp_cta":
        word = (value or label)[:12].upper()
        if not word:
            return None, ""
        return {"word": word, "stamp": "", "strike": ""}, word
    return {}, ""


def topic_fidelity(scene, topic_text=""):
    """(ok, detail) for the scene's content-bearing visual: the
    composed text's keywords must overlap the scene's own anchor —
    its line, its footage queries and the video topic (keyword
    intersection, the footage-query overlap approach). A visual
    that cannot compose from the scene at all is not ok. Scenes
    without a content-bearing visual are trivially ok."""
    name = effective_visual(scene)
    if name not in CONTENT_TEXT_VISUALS:
        return True, ""
    args, text = compose_visual(scene, name, topic_text)
    if args is None:
        return False, (f"'{name}' cannot compose honest text from this "
                       f"scene (nothing in its line / value / source / "
                       f"queries for it) — a visual that cannot be "
                       f"composed from the scene must not be chosen "
                       f"for it")
    words = _fid_words(text)
    anchor = (_fid_words(scene.get("vo"))
              | _fid_words(" ".join(str(q) for q in
                                    (scene.get("queries") or [])))
              | _fid_words(topic_text))
    if words and not (words & anchor):
        return False, (f"composed text for '{name}' shares no keyword "
                       f"with the scene's line/topic: '{text[:60]}'")
    return True, ""


# ------------------------------------------------------------------
# Captions (mail 1 Part 3 + R7): phrase-boundary chunking
# ------------------------------------------------------------------
_CLAUSE_END = {",", ";", ":", "—", "–"}
_SENT_END = {".", "!", "?"}


def chunk_caption_words(words, wmin=2, wmax=4):
    """Split word timings [(offset, dur, text), ...] into caption
    chunks of wmin..wmax words that END ON A PHRASE BOUNDARY: a
    sentence/clause punctuation mark when one is in range, else the
    last non-weak word at or before wmax. A chunk never ends on a weak
    word (a/the/and/how/of...) and never splits a number from its
    unit (the unit word stays with the number)."""
    words = list(words or [])
    chunks, i = [], 0
    n = len(words)
    while i < n:
        remaining = n - i
        if remaining <= wmax:
            chunks.append(words[i:])
            break
        # search the best end in [i+wmin-1, i+wmax-1]
        best = None
        for j in range(i + wmin - 1, min(i + wmax, n)):
            tok = str(words[j][2]).strip()
            last = tok[-1:] if tok else ""
            if last in _SENT_END or last in _CLAUSE_END:
                best = j
                break
        if best is None:
            # last position <= wmax whose word is not weak and does not
            # strand a number from its unit
            for j in range(min(i + wmax, n) - 1, i + wmin - 2, -1):
                w = str(words[j][2]).strip(".,!?\"'").lower()
                nxt = str(words[j + 1][2]).strip(".,!?\"'").lower() if j + 1 < n else ""
                if w in WEAK_END_WORDS:
                    continue
                if any(c.isdigit() for c in w) and nxt in ("%", "percent", "seconds", "minutes", "people", "times"):
                    continue  # number keeps its unit in the next chunk check below
                best = j
                break
        if best is None:
            best = i + wmax - 1
        # a number at the end keeps its unit: pull the unit in
        if best + 1 < n:
            w = str(words[best][2]).strip(".,!?\"'").lower()
            nxt = str(words[best + 1][2]).strip(".,!?\"'").lower()
            if any(c.isdigit() for c in w) and nxt in ("%", "percent", "seconds", "minutes", "people", "times"):
                best += 1
        chunks.append(words[i:best + 1])
        i = best + 1
    # A trailing chunk shorter than wmin borrows ONE word from the
    # previous chunk — only when the previous chunk stays >= wmin and
    # does not end on a weak word afterwards. (Merging wholesale
    # would break the wmax cap; a short FINAL chunk is acceptable,
    # a mid-video one cannot occur by construction.)
    if len(chunks) > 1 and len(chunks[-1]) < wmin and len(chunks[-2]) > wmin:
        prev, last = chunks[-2], chunks[-1]
        cand_end = str(prev[-2][2]).strip(".,!?\"'").lower() if len(prev) >= 2 else ""
        if cand_end not in WEAK_END_WORDS:
            chunks[-2] = prev[:-1]
            chunks[-1] = [prev[-1]] + last
    return chunks


def caption_chunk_text_ok(text, wmin, wmax):
    """One chunk's text against mail 1/R7: word count in range, does
    not end on a weak word."""
    ws = str(text or "").split()
    if not ws:
        return False
    if len(ws) > wmax:
        return False
    last = ws[-1].strip(".,!?\"'").lower()
    return last not in WEAK_END_WORDS


# ------------------------------------------------------------------
# Plan audit (scenes.json level)
# ------------------------------------------------------------------
def _title_of(scene):
    return str(scene.get("label") or "").strip().upper()


def audit_plan(scenes, cfg, topic_text="", measure=None, have_timing=False):
    """Run every plan-level rule. Returns a list of checks:
    {rule, status: PASS/FAIL, detail, scene (1-based or None)}.
    cfg is the spec_engine render config (kind drives the budgets:
    short mail-1, long mail-3/R1 — the stricter wins per the v79
    reconciliation)."""
    kind = (cfg or {}).get("kind", "short")
    long = kind == "long"
    checks = []

    def add(rule, status, detail, scene=None):
        checks.append({"rule": rule, "status": status,
                       "detail": detail, "scene": scene})

    topic_low = str(topic_text or "").lower()
    leftover_ok = any(t in topic_low for t in LEFTOVER_OK_TOPICS)

    # R1 / Part 3 — widget budgets
    counts, last_used = {}, {}
    starts, t = [], 0.0
    for s in scenes:
        starts.append(t)
        t += float(s.get("d") or 0)
    for i, s in enumerate(scenes):
        k = widget_kind(s)
        if not k:
            continue
        counts[k] = counts.get(k, 0) + 1
        if long:
            if counts[k] > 3:
                add("R1", "FAIL", f"widget '{k}' used {counts[k]} times in one long video (max 3)", i + 1)
            if k in last_used and have_timing and starts[i] - last_used[k] < 60:
                add("R1", "FAIL", f"widget '{k}' repeats within 60 s", i + 1)
        else:
            if counts[k] > 1:
                add("PART3-BUDGET", "FAIL", f"widget '{k}' used {counts[k]} times in a 1-min video (max 1)", i + 1)
        last_used[k] = starts[i]
        # R1: clocks only when the line talks about time
        if k in ("clock", "watch"):
            line_words = set(re.findall(r"[a-z]+", str(s.get("vo") or "").lower()))
            if k == "clock" and not (line_words & TIME_WORDS):
                add("R1", "FAIL", "clock visual on a line that is not about time", i + 1)
    distinct = {widget_kind(s) for s in scenes} - {None}
    if not long and len(scenes) >= 6 and len(distinct) < 6:
        add("PART3-TYPES", "FAIL", f"only {len(distinct)} different visual types (need 6+)", None)
    # v79.2 (Ajju — ring discipline): the ring FAMILY (donut /
    # clock / watch / gauge — ROUND_KINDS) has ONE budget in a
    # short: a second ring-family visual fails, whatever its kind.
    # The ring is a rare special, never a rotation. The repair
    # swaps the extra ring scenes to non-ring visuals.
    if not long:
        _rings = 0
        for i, s in enumerate(scenes):
            if widget_kind(s) in ROUND_KINDS:
                _rings += 1
                if _rings > 1:
                    add("PART3-RING", "FAIL",
                        f"ring visual '{widget_kind(s)}' is ring-family "
                        f"visual #{_rings} in one short (max 1) — the "
                        f"ring is a rare special, not a rotation", i + 1)
    # A5 (Ajju, 2026-11-13 — "own creativity"): the number-widget
    # pool is a FALLBACK for real numbers, not the menu. When more
    # than half the scenes are number widgets (donut / counter /
    # bars / graph / gauge...), Julie is rotating her pool instead
    # of picturing the lines — FAIL, and the repair swaps the
    # value-less widget scenes to composed scene types.
    _num_widgets = {"donut", "counter", "bar", "bar_compare", "graph",
                    "gauge", "battery", "dot_grid", "four", "watch",
                    "clock"}
    _graphic_scenes = [s for s in scenes if not s.get("has_footage")]
    _widget_scenes = [s for s in _graphic_scenes
                      if (s.get("visual") or "") in _num_widgets
                      or (s.get("lib_visual") or "") in _num_widgets]
    if len(_graphic_scenes) >= 4 and len(_widget_scenes) * 2 > len(_graphic_scenes):
        add("A5", "FAIL", f"{len(_widget_scenes)}/{len(_graphic_scenes)} scenes are "
                          f"number widgets — the widget pool is a fallback for real "
                          f"numbers, not the menu (A5); picture the lines with "
                          f"composed scenes (photo, document, map, timeline...)", None)
    # pattern break at 40-60% (Part 3, shorts)
    if not long and len(scenes) >= 5:
        mid = scenes[len(scenes) // 2]
        if not (mid.get("pattern_break") or widget_kind(mid) in ("question", "quote_card")):
            add("PART3-PACING", "FAIL", "no pattern break (full-screen card / colour flip) at 40-60%", len(scenes) // 2 + 1)

    prev_title = None
    for i, s in enumerate(scenes):
        vo = str(s.get("vo") or "")
        title = _title_of(s)
        # R2 — meaning check: the stored "why this visual" must
        # mention a word from the line it illustrates (content words
        # only — "the" matching "the" proves nothing).
        why = str(s.get("why") or "")
        if why:
            _stop = WEAK_END_WORDS | {"shows", "showing", "show", "scene",
                                      "visual", "line", "video", "used",
                                      "using", "represents", "represents"}
            line_words = {w for w in re.findall(r"[a-z]{3,}", vo.lower())} - _stop
            why_words = {w for w in re.findall(r"[a-z]{3,}", why.lower())} - _stop
            if not (line_words & why_words):
                add("R2", "FAIL", f"'why this visual' shares no word with the voice line: {why[:60]}", i + 1)
        elif widget_kind(s):
            add("R2", "FAIL", "scene with a graphic has no 'why this visual' (meaning not recorded)", i + 1)
        # R3 — banned leftovers in every text layer
        layers = " ".join([title, str(s.get("value") or ""), vo,
                           str(s.get("source") or "")]).upper()
        for w in LEFTOVER_WORDS:
            if w in ("COST", "HEALTH"):
                hit = "COST" in layers and "HEALTH" in layers  # the scales pair
                label = "COST/HEALTH scales"
            else:
                hit = w in layers
                label = w
            if hit and not leftover_ok:
                add("R3", "FAIL", f"banned leftover '{label}' in a video whose topic is not {label.lower()}", i + 1)
                break
        # v79.2 — topic fidelity: a content-bearing visual's text is
        # composed from THIS scene (compose_visual); it must overlap
        # the scene's line/topic, and a visual that cannot compose
        # from the scene must not be chosen for it. (The sleep video
        # shipped a gutka notification as its "document" — the canned
        # body this rule exists to make impossible.)
        _fok, _fdetail = topic_fidelity(s, topic_low)
        if not _fok:
            add("FIDELITY", "FAIL", _fdetail, i + 1)
        # R6 / mail 1 — titles
        if not title:
            add("R6", "FAIL", "empty title (an empty title box must never be drawn)", i + 1)
        else:
            toks = title.split()
            if all(tok in BANNED_TITLES for tok in toks) or title in BANNED_TITLES:
                add("R6", "FAIL", f"production label used as on-screen title: '{title}'", i + 1)
            maxw = 3 if long else 4
            if len(toks) > maxw:
                add("R6", "FAIL", f"title '{title}' is {len(toks)} words (max {maxw})", i + 1)
            if title == prev_title:
                add("R6", "FAIL", f"same title twice in a row: '{title}'", i + 1)
            for harsh, calm in CALM_TITLES.items():
                if harsh in toks:
                    add("PART1-TONE", "FAIL", f"sensitive topic: title '{title}' should be '{calm}' (calmer wording)", i + 1)
            if measure is not None:
                width = measure(title, 96)
                frame_w = (cfg or {}).get("width", 1080)
                if width > frame_w - 160:
                    add("R6", "FAIL", f"title '{title}' does not fit the frame width at label size", i + 1)
        prev_title = title
        # R4 — numbers
        val, unit = parse_value(s.get("value"))
        kind_w = widget_kind(s)
        if kind_w in ("counter", "donut", "gauge", "bar", "bar_compare", "four", "watch", "graph") or val is not None:
            if val is None:
                add("R4", "FAIL", "number scene has no readable on-screen value", i + 1)
            elif val == 0:
                add("R4", "FAIL", "on-screen number is 0 — a counter/donut must never end at 0", i + 1)
            else:
                spoken = spoken_numbers(vo)
                match = any(abs(v - val) < 0.01 and (u == unit or u == "" or unit == "")
                            for v, u in spoken)
                if not match:
                    add("R4", "FAIL", f"on-screen number {s.get('value')} is not spoken in this scene's line", i + 1)
                # the widget must be one the number kind accepts
                # (v79.2: a SET, not one kind — the ring discipline
                # makes a plain percent accept counter/bar and
                # reject the ring, while a share/cycle percent
                # accepts the ring family).
                want = widget_for_number_kind(vo, s.get("value"))
                _acc = acceptable_widgets_for_number(vo, s.get("value"))
                if _acc and kind_w and kind_w not in _acc and kind_w in ("counter", "donut", "bar_compare", "graph", "watch", "four", "dot_grid", "bar"):
                    add("PART3-WIDGET", "FAIL", f"number kind wants '{want}' (accepts {sorted(_acc)}), scene uses '{kind_w}'", i + 1)
            # the counter must land before the scene ends
            if have_timing and s.get("d"):
                land = float(s.get("pop_t") or 0) + 1.0
                if land > float(s["d"]):
                    add("R4", "FAIL", "counter lands after the scene ends", i + 1)
        # R5 — sources: real-or-none; the stamp pattern (one source
        # rubber-stamped on most scenes) is the compromise disease.
        src = str(s.get("source") or "").strip()
        if src and val is None and not re.search(r"\d", vo):
            add("R5", "FAIL", f"source line '{src}' on a scene with no fact or number", i + 1)
    srcs = [str(s.get("source") or "").strip() for s in scenes if str(s.get("source") or "").strip()]
    if len(srcs) >= 4 and len(set(srcs)) <= max(1, len(srcs) // 4):
        add("R5", "FAIL", f"sources look stamped: {len(srcs)} lines from {len(set(srcs))} source(s)", None)

    # Part 3 — 3-of-6 scene change
    def signature(s):
        return (("footage" if s.get("has_footage") else str(s.get("bg_kind") or "bg")),
                widget_kind(s) or "none",
                str(s.get("layout") or ("wide" if str(s.get("visual") or "") in ("versus", "bar", "bar_compare", "graph", "list", "checklist") else "centre")),
                str(s.get("transition") or ""),
                str(s.get("sfx") or ""),
                str(s.get("camera") or "push"))
    for i in range(1, len(scenes)):
        a, b = signature(scenes[i - 1]), signature(scenes[i])
        changed = sum(1 for x, y in zip(a, b) if x != y)
        if changed < 3:
            add("PART3-CHANGE", "FAIL", f"only {changed} of 6 things change vs the previous scene (need 3+)", i + 1)

    # Part 3 — transitions pool: at least 8 in the pool, max 2 uses
    # each; checklist wants 4+ different types actually used.
    trans = [str(s.get("transition") or "") for s in scenes[1:]]
    used_t = [t for t in trans if t]
    if used_t:
        from collections import Counter
        c = Counter(used_t)
        for name, n in c.items():
            if n > 2:
                add("PART3-TRANS", "FAIL", f"transition '{name}' used {n} times (max 2)", None)
        if len(scenes) >= 6 and len(c) < 4:
            add("PART4-CHECK", "FAIL", f"only {len(c)} different transitions used (need 4+)", None)
    sfxs = [str(s.get("sfx") or "") for s in scenes if s.get("sfx")]
    if sfxs:
        from collections import Counter
        c = Counter(sfxs)
        if len(scenes) >= 6 and len(c) < 4:
            add("PART4-CHECK", "FAIL", f"only {len(c)} different SFX used (need 4+)", None)
        run = 1
        for a, b in zip(sfxs, sfxs[1:]):
            run = run + 1 if a == b else 1
            if run > 2:
                add("PART3-SFX", "FAIL", f"SFX '{b}' more than 2 times in a row", None)
                break
    return checks


def audit_footage(scenes, cfg):
    """Footage ratio rules AFTER attach: mail 1 Part 2 (short: 50-60%
    footage scenes, never more than 2 footage or 2 graphic scenes in
    a row, hook = strongest footage) and R10 (long: at most 10% of
    scenes without footage; scene change = new clip — uniqueness is
    the pool's used_ids, audited in footage.json)."""
    checks = []
    if not scenes:
        return checks
    kind = (cfg or {}).get("kind", "short")
    flags = [bool(s.get("has_footage")) for s in scenes]
    n = len(flags)
    have = sum(flags)
    if kind == "long":
        if have < 0.9 * n:
            checks.append({"rule": "R10", "status": "FAIL",
                           "detail": f"{n - have}/{n} scenes have no footage (max 10%)", "scene": None})
    else:
        share = have / n
        if not (0.45 <= share <= 0.65):
            checks.append({"rule": "PART2-RATIO", "status": "FAIL",
                           "detail": f"footage on {have}/{n} scenes ({share:.0%}); mail 1 wants 50-60%", "scene": None})
        run_f = run_g = 0
        for i, f in enumerate(flags):
            run_f, run_g = (run_f + 1, 0) if f else (0, run_g + 1)
            if run_f > 2 or run_g > 2:
                checks.append({"rule": "PART2-RATIO", "status": "FAIL",
                               "detail": "more than 2 footage or 2 graphic scenes in a row", "scene": i + 1})
                break
        if n > 1 and not flags[0]:
            checks.append({"rule": "PART2-RATIO", "status": "FAIL",
                           "detail": "the hook scene has no footage (hook = strongest footage)", "scene": 1})
    return checks


# ------------------------------------------------------------------
# Repairs (fix rounds) — plan fields only, never the voice line
# ------------------------------------------------------------------
def repair_plan(scenes, cfg, pools, checks):
    """Apply one round of plan repairs for the given failed checks.
    pools = {visuals: [...kinds available], transitions: [...],
    sfx: [...], bg_kinds: [...]}. Returns the list of applied fixes
    (strings). A repair never re-introduces a banned title, a zero
    number or an over-budget widget."""
    kind = (cfg or {}).get("kind", "short")
    long = kind == "long"
    budget = 3 if long else 1
    fixes = []
    by_scene = {}
    for c in checks:
        if c["status"] == "FAIL" and c.get("scene"):
            by_scene.setdefault(c["scene"], []).append(c["rule"])

    def counts():
        from collections import Counter
        return Counter(widget_kind(s) for s in scenes if widget_kind(s))

    def free_visual(exclude=()):
        cnt = counts()
        for v in pools.get("visuals", []):
            if v not in exclude and cnt.get(v, 0) < budget:
                return v
        return None

    for idx, rules in sorted(by_scene.items()):
        s = scenes[idx - 1]
        if any(r in rules for r in ("R1", "PART3-BUDGET", "PART3-WIDGET")):
            want = widget_for_number_kind(s.get("vo"), s.get("value")) \
                if "PART3-WIDGET" in rules else None
            cnt = counts()
            new = None
            if want and cnt.get(want, 0) < budget and want != widget_kind(s):
                new = want
            elif widget_kind(s) and cnt.get(widget_kind(s), 0) > budget:
                new = free_visual(exclude=(widget_kind(s),))
            elif "R1" in rules and widget_kind(s) in ("clock", "watch"):
                new = free_visual(exclude=("clock", "watch"))
            if new:
                fixes.append(f"scene {idx}: visual {s.get('visual')} -> {new} ({'/'.join(rules)})")
                s["visual"] = new
                s.pop("lib_visual", None)
        if "PART3-RING" in rules:
            # v79.2 ring discipline: swap the extra ring scene to a
            # non-ring visual — but only if it is STILL a ring (an
            # earlier branch this round may already have moved it,
            # e.g. PART3-WIDGET taking a plain-percent donut to the
            # counter the number kind wants).
            if widget_kind(s) in ROUND_KINDS:
                new = free_visual(
                    exclude=tuple(ROUND_KINDS) + (widget_kind(s),))
                if new:
                    fixes.append(f"scene {idx}: ring-budget swap "
                                 f"{s.get('visual')} -> {new} (ring "
                                 f"family max 1 per short)")
                    s["visual"] = new
                    s.pop("lib_visual", None)
        if "R6" in rules or "PART1-TONE" in rules:
            title = _title_of(s)
            for harsh, calm in CALM_TITLES.items():
                if harsh in title.split():
                    s["label"] = calm
                    fixes.append(f"scene {idx}: title '{title}' -> '{calm}' (calm wording)")
                    title = calm
            if title in BANNED_TITLES or all(t in BANNED_TITLES for t in title.split()):
                # derive a content title from the line: the two most
                # contentful words, never a production label
                words = [w for w in re.findall(r"[A-Za-z]{3,}", str(s.get("vo") or ""))
                         if w.upper() not in BANNED_TITLES and w.lower() not in WEAK_END_WORDS]
                newt = " ".join(words[:2]).upper() if words else ""
                if newt:
                    s["label"] = newt
                    fixes.append(f"scene {idx}: banned title '{title}' -> '{newt}'")
            if idx > 1 and _title_of(s) == _title_of(scenes[idx - 2]):
                words = [w for w in re.findall(r"[A-Za-z]{3,}", str(s.get("vo") or ""))
                         if w.upper() not in BANNED_TITLES]
                newt = " ".join(words[-2:]).upper() if len(words) >= 2 else ""
                if newt and newt != _title_of(s):
                    s["label"] = newt
                    fixes.append(f"scene {idx}: repeated title -> '{newt}'")
        if "R3" in rules:
            for field in ("label", "value", "source"):
                v = str(s.get(field) or "")
                for w in LEFTOVER_WORDS:
                    if w in v.upper():
                        s[field] = ""
                        fixes.append(f"scene {idx}: removed leftover '{w}' from {field}")
            if not str(s.get("label") or "").strip():
                words = [w for w in re.findall(r"[A-Za-z]{3,}", str(s.get("vo") or ""))]
                s["label"] = " ".join(words[:2]).upper()
        if "FIDELITY" in rules:
            # v79.2: one plan-level fix round — swap the scene's
            # visual to an abstract, text-free visual (filmstrip:
            # coloured frames, no composed text) via lib_visual,
            # which the draw path honours first, and record the
            # swap. If the re-audit still fails, the FAIL stands in
            # the report — never a silent pass.
            old = effective_visual(s)
            if old != "filmstrip":
                s["visual"] = "filmstrip"
                s["lib_visual"] = "filmstrip"
                fixes.append(f"scene {idx}: topic-fidelity swap "
                             f"{old} -> filmstrip (abstract, no "
                             f"composed text)")
        if "R4" in rules:
            val, _u = parse_value(s.get("value"))
            if val is None or val == 0:
                spoken = spoken_numbers(s.get("vo"))
                good = [v for v, _u2 in spoken if v != 0]
                if good:
                    s["value"] = ("%g" % good[0]) + ("%" if _u == "%" else "")
                    fixes.append(f"scene {idx}: on-screen number set to the spoken {s['value']}")
                else:
                    # no real number in the line: the stat visual goes
                    new = free_visual(exclude=("counter", "donut", "gauge"))
                    if new:
                        s["visual"] = new
                        s["value"] = ""
                        fixes.append(f"scene {idx}: numberless stat visual -> {new}")
        if "PART3-CHANGE" in rules and idx > 1:
            prev = scenes[idx - 2]
            changed = []
            for name in pools.get("transitions", []):
                if name != s.get("transition") and name != prev.get("transition"):
                    s["transition"] = name
                    changed.append("transition")
                    break
            for name in pools.get("sfx", []):
                if name != s.get("sfx") and name != prev.get("sfx"):
                    s["sfx"] = name
                    changed.append("sfx")
                    break
            for bgk in pools.get("bg_kinds", []):
                if bgk != s.get("bg_kind") and bgk != prev.get("bg_kind"):
                    s["bg_kind"] = bgk
                    changed.append("background")
                    break
            if changed:
                fixes.append(f"scene {idx}: 3-of-6 repair changed {', '.join(changed)}")
    # pattern break insertion (shorts)
    # A5 repair: swap value-less number-widget scenes to composed
    # scene types until widgets are at most half the graphic scenes.
    # Scenes carrying a real spoken number keep their widget (the
    # number-kind table governs those).
    if any(c["rule"] == "A5" for c in checks):
        # v79.2: timeline_cards / receipt are NOT in this pool any
        # more — a scene without events/items cannot compose them
        # honestly, so an A5 swap to them would create a FIDELITY
        # failure in the next round.
        _composed = ["photo_frame", "document", "newspaper",
                     "filmstrip", "speech_bubble", "magnifier"]
        _num_widgets = {"donut", "counter", "bar", "bar_compare",
                        "graph", "gauge", "battery", "dot_grid",
                        "four", "watch", "clock"}
        _ci = 0
        for s in scenes:
            _graphic = [x for x in scenes if not x.get("has_footage")]
            _widgets = [x for x in _graphic
                        if (x.get("visual") or "") in _num_widgets
                        or (x.get("lib_visual") or "") in _num_widgets]
            if len(_widgets) * 2 <= len(_graphic):
                break
            if (s.get("visual") or "") in _num_widgets and not s.get("value"):
                s["visual"] = _composed[_ci % len(_composed)]
                if s.get("lib_visual"):
                    s["lib_visual"] = s["visual"]
                _ci += 1
                fixes.append(f"A5: a value-less widget scene became a "
                             f"composed '{s['visual']}' scene")
    if not long and len(scenes) >= 5 and any(c["rule"] == "PART3-PACING" for c in checks):
        mid = scenes[len(scenes) // 2]
        mid["pattern_break"] = True
        mid["bg_kind"] = pools.get("pattern_bg", mid.get("bg_kind"))
        fixes.append(f"scene {len(scenes) // 2 + 1}: pattern break marked (full-screen card)")
    return fixes


# ------------------------------------------------------------------
# Frame fill (Ajju A1, 2026-11-13) — the measurable gate
# ------------------------------------------------------------------
# Ajju's red marks on the ALCOHOL TRUTH frames: whole scenes were an
# empty brown/black gradient with ONE small centred element (a lone
# "0", a donut, a heart). HARD RULE: no scene may be mostly empty
# background — every frame is FILLED with meaningful content
# (full-frame footage, or a composed graphic scene). The gate:
# downscale the scene's mid frame to 96x170, take the border median
# as the background colour, and measure (a) content share = pixels
# farther than 0.16 (of max RGB distance) from that background, and
# (b) edge density = mean absolute gradient. A graphic scene FAILS
# when content share < 0.18 AND edge density < 0.03 — the signature
# of a lone element floating on a plain gradient. (Calibration: the
# lone-"0" frame measures ~0.09 share; the lone-heart frame ~0.15
# with near-zero edges; a composed document/map scene > 0.30 share
# with dense edges; footage scenes are exempt — full-frame by
# construction.)
FRAME_FILL_MIN_SHARE = 0.18
FRAME_FILL_MIN_EDGE = 0.03


def frame_fill_metrics(img):
    """(content_share, edge_density) for a PIL image (any size)."""
    import numpy as np
    a = np.asarray(img.convert("RGB").resize((96, 170)),
                   dtype=np.float32)
    border = np.concatenate([a[0].reshape(-1, 3), a[-1].reshape(-1, 3),
                             a[:, 0].reshape(-1, 3), a[:, -1].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2)) / 441.673
    share = float((dist > 0.16).mean())
    gray = a.mean(axis=2)
    edge = float((np.abs(np.diff(gray, axis=0)).mean()
                  + np.abs(np.diff(gray, axis=1)).mean()) / 2 / 255.0)
    return share, edge


def audit_frame_fill(frames):
    """frames: iterable of (scene_no, PIL image, has_footage).
    Returns A1 checks — FAIL for a graphic scene that is mostly
    empty background."""
    out = []
    for no, img, has_footage in frames:
        if has_footage or img is None:
            continue
        try:
            share, edge = frame_fill_metrics(img)
        except Exception:
            continue
        if share < FRAME_FILL_MIN_SHARE and edge < FRAME_FILL_MIN_EDGE:
            out.append({"rule": "A1", "status": "FAIL",
                        "detail": f"scene is mostly empty background "
                                  f"(content share {share:.2f} < "
                                  f"{FRAME_FILL_MIN_SHARE}, edge density "
                                  f"{edge:.3f} < {FRAME_FILL_MIN_EDGE}) — "
                                  f"a lone element on a plain gradient "
                                  f"is banned; fill the frame (footage "
                                  f"or a composed scene)",
                        "scene": no})
    return out


# ------------------------------------------------------------------
# Full-screen compositions (Ajju item 8, 2026-11-13) — "screen
# motham kuda effects use cheyamani chepu": a scene's main visual
# must use the full frame as its canvas, not sit as a small island
# in the centre of an empty gradient. Judged on the visual layer's
# alpha bbox inside the visual band (frame coords, band y
# 480-1410 of 1920 — doc._fit_above_label's zones): an island is a
# bbox that is small in area AND narrow AND short AND has dead
# margins on ALL four sides. A frame the check cannot judge (no
# visual bbox at all) reports UNVERIFIED, never a silent PASS.
# ------------------------------------------------------------------
def island_metrics(vb, width=1080, height=1920, band=(480, 1410)):
    """(is_island, detail) for a visual bbox (x0, y0, x1, y1), or
    None when there is no bbox to judge."""
    if not vb:
        return None
    x0, y0, x1, y1 = (float(v) for v in vb)
    w, h = max(0.0, x1 - x0), max(0.0, y1 - y0)
    if w <= 0 or h <= 0:
        return None
    band_h = float(band[1] - band[0])
    area_share = (w * h) / (width * band_h)
    left, right = x0 / width, (width - x1) / width
    top_dead = max(0.0, y0 - band[0]) / band_h
    bot_dead = max(0.0, band[1] - y1) / band_h
    island = (area_share < 0.38 and w < 0.72 * width
              and h < 0.72 * band_h and left > 0.13 and right > 0.13
              and top_dead > 0.08 and bot_dead > 0.08)
    detail = (f"visual {w:.0f}x{h:.0f} in a {width:.0f}x{band_h:.0f} "
              f"band (area {area_share:.2f}), margins L{left:.2f} "
              f"R{right:.2f} T{top_dead:.2f} B{bot_dead:.2f}")
    return island, detail


def audit_central_island(frames):
    """frames: iterable of (scene_no, visual_bbox, has_footage).
    FAIL for a graphic scene whose main visual is a small central
    island with dead margins on all sides; UNVERIFIED when a frame
    cannot be judged (no visual layer — the check says so instead
    of passing silently). Footage scenes are full-frame by
    construction and are skipped."""
    out = []
    for no, vb, has_footage in frames:
        if has_footage:
            continue
        m = island_metrics(vb)
        if m is None:
            out.append({"rule": "A6", "status": "UNVERIFIED",
                        "detail": "no visual layer on the sampled "
                                  "frame — the full-screen check "
                                  "cannot judge this scene",
                        "scene": no})
        elif m[0]:
            out.append({"rule": "A6", "status": "FAIL",
                        "detail": f"main visual is a small central "
                                  f"island ({m[1]}) — the composition "
                                  f"must use the full frame (background "
                                  f"+ subject + foreground in "
                                  f"relationship), not a lone centred "
                                  f"widget on an empty gradient",
                        "scene": no})
    return out


def audit_music_default(spec, cfg, plan_info):
    """Item 9 (Ajju, 2026-11-13): "topic ki thagga background music
    kuda undali" — music defaults ON, chosen for the topic's mood,
    whenever the prompt is SILENT on music. A silent-prompt render
    with no music track is a FAIL. An explicit ask (a music
    requirement in the spec, on or off) governs instead and is
    judged by its own verdict — 'no music' stays correct
    (FIX-7 test 1)."""
    if any(r.get("type") == "music" for r in (spec or [])):
        return []
    if (plan_info or {}).get("music_applied"):
        return []
    return [{"rule": "MUSIC-DEFAULT", "status": "FAIL",
             "detail": "the prompt says nothing about music, but "
                       "the render has no background track — music "
                       "defaults ON, topic-matched to the scene "
                       "moods (music_choice in the artifacts)",
             "scene": None}]


# ------------------------------------------------------------------
# Media checks (rendered file) — FIX 5 automatic checks + R9/R11
# ------------------------------------------------------------------
def _ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height", "-show_entries",
                        "format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def probe_media(path):
    d = _ffprobe(path)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
    return {"width": v.get("width"), "height": v.get("height"),
            "duration": float((d.get("format") or {}).get("duration") or 0),
            "has_audio": bool(a)}


def measure_loudness(path):
    """(integrated LUFS, true peak dB) or (None, None). R11 targets:
    -14 LUFS, true peak -1 dB."""
    r = subprocess.run(["ffmpeg", "-i", str(path), "-vn", "-af",
                        "loudnorm=print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "")
    if not m:
        return None, None
    try:
        d = json.loads(m.group(0))
        return float(d["input_i"]), float(d["input_tp"])
    except Exception:
        return None, None


def silence_gaps(path, max_gap=0.8, noise="-45dB"):
    """Silences longer than max_gap seconds: [(start, end)]. R11: no
    silence over 0.8 s except at chapter breaks (the caller filters
    the break positions out)."""
    r = subprocess.run(["ffmpeg", "-i", str(path), "-af",
                        f"silencedetect=noise={noise}:d={max_gap}",
                        "-f", "null", "-"], capture_output=True, text=True)
    err = r.stderr or ""
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(starts, ends))


def sample_frame_diffs(path, every_s=4.0, still_thresh=2.0):
    """R12 sampling, light version: extract 1 frame every `every_s`
    seconds and return the list of mean abs diffs between consecutive
    sampled frames (PIL+numpy). A run of near-zero diffs marks a held
    / frozen stretch (Part 4 frame-difference check)."""
    import tempfile
    import numpy as np
    from PIL import Image
    diffs = []
    with tempfile.TemporaryDirectory(prefix="v79frames_") as td:
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(path),
                        "-vf", f"fps=1/{every_s},scale=96:96",
                        os.path.join(td, "f%04d.jpg")], check=False)
        files = sorted(f for f in os.listdir(td) if f.endswith(".jpg"))
        prev = None
        for f in files:
            im = np.asarray(Image.open(os.path.join(td, f)).convert("L"), dtype=np.float32)
            if prev is not None:
                diffs.append(float(np.mean(np.abs(im - prev))))
            prev = im
    return diffs


def audit_media(path, cfg, spec, chapter_breaks=()):
    """Media-level checks on the rendered file. Returns checks +
    the probe dict."""
    checks = []
    info = probe_media(path)
    if not info["duration"]:
        return [{"rule": "MEDIA", "status": "FAIL", "detail": "rendered file is unreadable", "scene": None}], info
    if (cfg.get("width"), cfg.get("height")) != (info["width"], info["height"]):
        checks.append({"rule": "R-P4", "status": "FAIL",
                       "detail": f"rendered {info['width']}x{info['height']}, config says {cfg.get('width')}x{cfg.get('height')}",
                       "scene": None})
    dur_req = cfg.get("duration_s")
    if dur_req:
        tol = max(2.0, 0.10 * dur_req) if cfg.get("kind") == "long" else 2.0
        if abs(info["duration"] - dur_req) > tol:
            checks.append({"rule": "R9" if cfg.get("kind") == "long" else "FIX5-DURATION",
                           "status": "FAIL",
                           "detail": f"duration {info['duration']:.1f}s vs asked {dur_req:.0f}s (tolerance {tol:.0f}s)",
                           "scene": None})
    i_lufs, tp = measure_loudness(path)
    if i_lufs is not None:
        if abs(i_lufs - (-14.0)) > 1.5:
            checks.append({"rule": "R11", "status": "FAIL",
                           "detail": f"loudness {i_lufs:.1f} LUFS (target -14)", "scene": None})
        if tp is not None and tp > -0.9:
            checks.append({"rule": "R11", "status": "FAIL",
                           "detail": f"true peak {tp:.1f} dB (must be <= -1 dB)", "scene": None})
    gaps = silence_gaps(path)
    real_gaps = [(a, b) for a, b in gaps
                 if not any(abs(a - cb) < 1.6 for cb in chapter_breaks)]
    if real_gaps:
        checks.append({"rule": "R11", "status": "FAIL",
                       "detail": f"{len(real_gaps)} silence(s) over 0.8 s outside chapter breaks (first at {real_gaps[0][0]:.1f}s)",
                       "scene": None})
    return checks, info


# Rules whose checks are produced by audit_media — they describe the
# measured file, so a re-measure replaces them wholesale.
MEDIA_CHECK_RULES = {"MEDIA", "R-P4", "FIX5-DURATION", "R9", "R11"}


def refresh_report_for_final_file(report, cfg, delivered_path,
                                  extra_fixes=()):
    """v79.2 (defect 2): the compliance report must describe the
    FINAL delivered artifact. The engine audits the master it
    rendered inside make_video, but the runner's duration backstop
    may trim that master to the asked length afterwards — the
    report then records a duration FAIL for a file the user never
    received (the test-1 report measured 37.2 s; the delivered file
    is exactly 30.000 s). Re-probe the delivered file, replace the
    media-derived checks with the fresh measurement, refresh the
    duration / aspect verdicts from the new probe, and record what
    was done (extra_fixes — e.g. "duration trimmed 37.2s → 30.0s to
    meet R1") in fixes_applied. Plan-derived verdicts (voice, music,
    language...) do not depend on the file and carry over untouched."""
    if not report:
        return report
    cfg = cfg or {}
    mchecks, minfo = audit_media(delivered_path, cfg, [])
    checks = [c for c in (report.get("checks") or [])
              if c.get("rule") not in MEDIA_CHECK_RULES] + mchecks
    verdicts = []
    for v in report.get("requirements") or []:
        v = dict(v)
        if v.get("type") == "duration" and cfg.get("duration_s"):
            d = minfo.get("duration") or 0
            tol = max(2.0, 0.10 * cfg["duration_s"]) \
                if cfg.get("kind") == "long" else 2.0
            v["status"] = "PASS" if abs(d - cfg["duration_s"]) <= tol \
                else "FAIL"
            v["evidence"] = (f"ffprobe duration {d:.1f}s vs asked "
                             f"{cfg['duration_s']:.0f}s "
                             f"(final delivered file)")
        elif v.get("type") == "aspect_ratio" and minfo.get("duration"):
            ok = (minfo.get("width"), minfo.get("height")) == \
                (cfg.get("width"), cfg.get("height"))
            v["status"] = "PASS" if ok else "FAIL"
            v["evidence"] = (f"rendered {minfo.get('width')}x"
                             f"{minfo.get('height')} "
                             f"(final delivered file)")
        verdicts.append(v)
    fixes = list(report.get("fixes_applied") or []) + list(extra_fixes)
    return build_report([], cfg, checks, verdicts,
                        report.get("fix_rounds", 0), fixes)


# ------------------------------------------------------------------
# FIX 5 — per-requirement verdicts + the report
# ------------------------------------------------------------------
def requirement_verdicts(spec, cfg, plan_info, media_info):
    """One verdict per prompt_spec requirement. plan_info carries the
    engine's own attested facts (lang, voice used, music/sfx/captions
    actually applied, chapters done, footage coverage, end card text)
    — a PASS needs evidence; anything unprovable is UNVERIFIED with
    the reason, never a silent PASS."""
    out = []
    plan_info = plan_info or {}
    for r in spec or []:
        t, v = r.get("type"), str(r.get("value") or "")
        status, evidence = "UNVERIFIED", "no automatic check for this requirement type yet"
        vl = v.lower()
        if t == "duration":
            if media_info and cfg.get("duration_s"):
                d = media_info.get("duration") or 0
                tol = max(2.0, 0.10 * cfg["duration_s"]) if cfg.get("kind") == "long" else 2.0
                status = "PASS" if abs(d - cfg["duration_s"]) <= tol else "FAIL"
                evidence = f"ffprobe duration {d:.1f}s vs asked {cfg['duration_s']:.0f}s"
        elif t == "aspect_ratio":
            if media_info:
                ok = (media_info.get("width"), media_info.get("height")) == (cfg.get("width"), cfg.get("height"))
                status = "PASS" if ok else "FAIL"
                evidence = f"rendered {media_info.get('width')}x{media_info.get('height')}"
        elif t == "music":
            if "off" in vl:
                status = "PASS" if plan_info.get("music_applied") is False else "FAIL"
                evidence = "engine attests the music track was silenced for this render"
        elif t == "sfx":
            if "off" in vl:
                status = "PASS" if plan_info.get("sfx_applied") is False else "FAIL"
                evidence = "engine attests the SFX track was silenced for this render"
        elif t == "captions":
            if "off" in vl:
                status = "PASS" if plan_info.get("captions_applied") is False else "FAIL"
                evidence = "engine attests no captions were burned"
            elif "script" in vl or "lipi" in vl:
                # v79.2 (Ajju's caption rule): native script was
                # explicitly asked — PASS only when the render
                # actually used it. (Romanized captions are the
                # DEFAULT for Telugu/Hindi and are never a language
                # failure; they are not judged here at all.)
                status = "PASS" if plan_info.get("caption_script") == "native" else "FAIL"
                evidence = f"caption script used: {plan_info.get('caption_script') or 'unknown'} (native script was asked)"
            elif cfg.get("caption_spec"):
                status = "PASS"
                evidence = "caption spec from the prompt was passed to the renderer"
        elif t == "sources":
            # v79.2 (Ajju item 7): sources are drawn into frames
            # ONLY on this explicit ask.
            status = "PASS" if plan_info.get("sources_shown") else "FAIL"
            evidence = ("source lines were drawn in the frames, as "
                        "asked" if plan_info.get("sources_shown")
                        else "sources were asked for but no source "
                             "line was drawn")
        elif t == "voice":
            used = str(plan_info.get("voice_used") or "")
            if cfg.get("voice_id"):
                status = "PASS" if used == cfg["voice_id"] else "FAIL"
                evidence = f"voice used: {used or 'unknown'}"
                vc = cfg.get("voice_choice")
                if vc:
                    # v79.1: a voice-LANGUAGE ask — record how it was
                    # routed (which language, which concrete voice,
                    # whose gender choice) in the report.
                    evidence += (f" ({vc['language']} voice routed to "
                                 f"{vc['voice_id']}, gender {vc['gender']} "
                                 f"— {vc['gender_source']} choice)")
            elif cfg.get("voice_gender"):
                status = "PASS" if cfg["voice_gender"] in used.lower() or plan_info.get("voice_gender") == cfg["voice_gender"] else "UNVERIFIED"
                evidence = f"voice gender asked {cfg['voice_gender']}, used {used or 'unknown'}"
        elif t == "language":
            status = "PASS" if plan_info.get("lang") == cfg.get("lang") else "FAIL"
            evidence = f"plan language {plan_info.get('lang')}"
        elif t == "colour":
            status = "PASS" if cfg.get("accent") else "UNVERIFIED"
            evidence = "accent colour from the prompt drove the look" if cfg.get("accent") else "colour not resolved"
        elif t == "footage":
            if "only" in vl:
                cov = plan_info.get("footage_coverage")
                status = "PASS" if cov == 1.0 and cfg.get("no_graphics") else "FAIL"
                evidence = f"footage coverage {cov}"
        elif t == "chapters":
            done = plan_info.get("chapters_done")
            status = "PASS" if done == cfg.get("chapters") else "FAIL"
            evidence = f"chapters rendered {done} of {cfg.get('chapters')} asked"
        elif t == "end_card":
            ec = str(plan_info.get("end_card_text") or "")
            status = "PASS" if v.lower() in ec.lower() else "FAIL"
            evidence = f"end card shows: {ec[:60] or 'nothing recorded'}"
        elif t == "exclude":
            if "zoom" in vl:
                status = "PASS" if plan_info.get("camera_moves") is False else "FAIL"
                evidence = "camera moves disabled for this render"
            elif "graphic" in vl:
                status = "PASS" if cfg.get("no_graphics") else "FAIL"
                evidence = "graphics disabled; footage carries the scenes"
        elif t == "topic":
            topic = str(plan_info.get("topic") or "").lower()
            status = "PASS" if any(w in topic for w in re.findall(r"[a-z]{3,}", vl)) else "UNVERIFIED"
            evidence = f"video topic: {plan_info.get('topic')}"
        out.append({"id": r.get("id"), "type": t, "value": v,
                    "quote": r.get("quote", ""), "status": status,
                    "evidence": evidence})
    return out


def build_report(spec, cfg, checks, verdicts, rounds, fixes):
    """compliance_report.json (FIX 5 + Part 4 + R12 in one file)."""
    failed = [c for c in checks if c["status"] == "FAIL"]
    done = [v["id"] for v in verdicts if v["status"] == "PASS"]
    not_done = [{"id": v["id"], "reason": v["evidence"]}
                for v in verdicts if v["status"] != "PASS"]
    return {
        "version": "v79",
        "requirements": verdicts,
        "checks": checks,
        "checks_failed": len(failed),
        "fix_rounds": rounds,
        "fixes_applied": fixes,
        "done": done,
        "not_done": not_done,
        "passed": not failed and not [v for v in verdicts if v["status"] == "FAIL"],
    }


def done_not_done_line(report):
    """R-P7: the short delivery line — what was done, what was not,
    in plain words. Never claims a not-done item."""
    done = report.get("done") or []
    not_done = report.get("not_done") or []
    line = ""
    if done:
        line += "Done: " + ", ".join(done) + ". "
    if not_done:
        line += "Could not do: " + "; ".join(
            f"{n['id']} ({n['reason']})" for n in not_done[:4]) + ". "
    if report.get("checks_failed"):
        line += f"{report['checks_failed']} quality check(s) still failing — see compliance_report.json. "
    return line.strip()
