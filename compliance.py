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


def widget_for_number_kind(vo, value):
    """Mail 1 Part 3 — choose the widget BY THE KIND OF NUMBER:
    percentage of a whole -> donut or 10x10 icon grid (dot_grid);
    'X times more' -> two bars side by side (bar_compare); count of
    people -> big counter + person icons (counter / four); change
    over years -> line chart (graph); ranking/compare -> horizontal
    bars or filled map; '1 every N seconds' -> clock/timer (watch)."""
    txt = str(vo or "").lower()
    val, unit = parse_value(value)
    if re.search(r"\bevery\s+\d*\s*(second|minute|hour)s?\b", txt) or "per second" in txt or "per minute" in txt:
        return "watch"
    if re.search(r"\b(one|1|two|2|three|3)\s+in\s+(four|five|six|ten|4|5|6|10)\b", txt):
        return "four"
    if unit == "%" or "%" in str(value or "") or "percent" in txt:
        return "donut"
    if unit == "x" or re.search(r"\btimes\s+(more|higher|likely)\b", txt):
        return "bar_compare"
    if re.search(r"\b(since|from)\s+\d{4}\b|\bover\s+the\s+years\b|\beach\s+year\b", txt):
        return "graph"
    if re.search(r"\b(people|deaths|users|children|men|women|patients|cases)\b", txt) and val is not None:
        return "counter"
    if val is not None:
        return "counter"
    return None


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
                # the widget must be the one the number kind demands
                want = widget_for_number_kind(vo, s.get("value"))
                if want and kind_w and kind_w != want and kind_w in ("counter", "donut", "bar_compare", "graph", "watch", "four"):
                    add("PART3-WIDGET", "FAIL", f"number kind wants '{want}', scene uses '{kind_w}'", i + 1)
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
    if not long and len(scenes) >= 5 and any(c["rule"] == "PART3-PACING" for c in checks):
        mid = scenes[len(scenes) // 2]
        mid["pattern_break"] = True
        mid["bg_kind"] = pools.get("pattern_bg", mid.get("bg_kind"))
        fixes.append(f"scene {len(scenes) // 2 + 1}: pattern break marked (full-screen card)")
    return fixes


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
            elif cfg.get("caption_spec"):
                status = "PASS"
                evidence = "caption spec from the prompt was passed to the renderer"
        elif t == "voice":
            used = str(plan_info.get("voice_used") or "")
            if cfg.get("voice_id"):
                status = "PASS" if used == cfg["voice_id"] else "FAIL"
                evidence = f"voice used: {used or 'unknown'}"
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
