"""yt_tools.py — Julie: deterministic YouTube packaging tools.

Additive port of the deterministic helpers from the MIT-licensed
youtube-agent-skill pack (Jakeschincariol/youtube-agent-skill,
Copyright (c) 2026 Jake Schincariol), re-implemented for Julie's
runner in the E7 style: pure functions over provided data, exact
outputs, no LLM, no network, no file writes. Hook scoring reuses
Julie's own hooks_lib (the 21 formulas already live there).

What is deliberately NOT here:
- No collection/scraping. yt_viral_rank only ranks data the caller
  already holds (provided JSON, official API exports, manual lists).
- No publishing. These tools lint, validate, rank and read — the
  upload stays with the team's own YouTube workflow.
- No duplication of packaging.py's generation-side pair_check or
  hooks_lib's scorer; this module adds the standalone lint/validate/
  rank/read surfaces the agent brain can call on arbitrary inputs.

Every function returns plain JSON-able data. Registration follows
the compute_tools pattern: register_yt_tools(reg) adds read-only
tools (mutating=False, needs_allow=False).
"""

import re
import statistics

import hooks_lib

# ------------------------------------------------------------ title lint

_DESKTOP, _MOBILE, _HARD = 60, 40, 100
_VAGUE = {"amazing", "incredible", "insane", "crazy", "huge", "massive",
          "ultimate", "best", "powerful", "secret", "revolutionary",
          "mindblowing", "epic", "perfect", "complete", "everything"}
_STOP = {"the", "a", "an", "of", "for", "to", "in", "on", "and", "or",
         "is", "are", "with", "your", "you", "my", "i", "this", "that",
         "it", "how", "what", "why"}


def _words(t):
    return re.findall(r"[a-z0-9']+", str(t or "").lower())


def lint_title_pair(title, thumb=None):
    """Lint one title (+ optional thumbnail text) as a pairing.

    Checks, in order: YouTube's 100-char hard limit, desktop (~60)
    and mobile (~40) truncation, all-caps ceiling, vague hype words,
    a concrete figure, front-loading, and — when thumbnail text is
    given — title/thumbnail word duplication and thumbnail word
    count. Score: 100 - 14 per issue + 4 per good point, clamped
    0..100. Deterministic; the same input always scores the same.
    """
    t = str(title or "").strip()
    n = len(t)
    issues, good = [], []
    if n > _HARD:
        issues.append(["length", f"{n} characters - YouTube's hard limit is {_HARD}"])
    elif n > _DESKTOP:
        issues.append(["length", f"{n} characters - desktop search cuts near {_DESKTOP}"])
    else:
        good.append(f"{n} characters, inside the {_DESKTOP}-character desktop cut")
    if n > _MOBILE:
        head = t[:_MOBILE].rsplit(" ", 1)[0]
        issues.append(["mobile", f'a mobile feed shows about "{head}..." - check the subject survives'])
    caps = [w for w in t.split() if len(w) > 2 and w.isupper()]
    if len(caps) > 2:
        issues.append(["shouting", f"{len(caps)} all-caps words - two is the ceiling before it reads as spam"])
    elif caps:
        good.append(f"{len(caps)} all-caps word for emphasis")
    vague = [w for w in _words(t) if w in _VAGUE]
    if vague:
        issues.append(["vague", f"{', '.join(sorted(set(vague)))} - swap for a number, a name or a date"])
    nums = re.findall(r"\d[\d,.]*%?", t)
    if nums:
        good.append(f"carries a concrete figure ({', '.join(nums[:3])})")
    else:
        issues.append(["no-number", "no number, date or name - the most reliable single fix"])
    if t.endswith("?"):
        good.append("open question in the title")
    front = [w for w in _words(t)[:3] if w not in _STOP]
    if not front:
        issues.append(["front-load", "the first three words are all filler - move the subject forward"])
    if thumb:
        shared = (set(_words(t)) - _STOP) & (set(_words(thumb)) - _STOP)
        if shared:
            issues.append(["duplicate",
                           f"thumbnail repeats the title on {', '.join(sorted(shared))} - "
                           "the thumbnail should say what the title does not"])
        else:
            good.append("thumbnail and title carry different words")
        if len(_words(thumb)) > 4:
            issues.append(["thumb-length",
                           f"{len(_words(thumb))} words on the thumbnail - three is the ceiling at feed size"])
    score = max(0, min(100, 100 - 14 * len(issues) + 4 * len(good)))
    return {"title": t, "thumbnail_text": thumb, "chars": n,
            "score": score, "issues": issues, "good": good}


# ------------------------------------------------------------ chapters

_MIN_CHAPTER_S = 10.0
_CH_STOP = set(
    "the a an of for to in on and or is are was were be been with this "
    "that it as at by from you your i my we our they them he she but so "
    "if then than there here what which who how when where why not no "
    "yes do does did just really very like about into over out up down "
    "can could will would should have has had get got make made go "
    "going went one two".split())


def _mmss(t):
    t = int(t)
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _norm_cues(cues):
    out = []
    for c in cues or []:
        if isinstance(c, dict):
            start = float(c.get("start", 0) or 0)
            end = float(c.get("end", start) or start)
            text = str(c.get("text") or "")
        elif isinstance(c, (list, tuple)) and len(c) >= 3:
            start, end, text = float(c[0]), float(c[1]), str(c[2])
        else:
            continue
        out.append((start, end, text))
    out.sort(key=lambda x: x[0])
    return out


def validate_chapters(chapters, duration=None):
    """Check a chapter list against YouTube's rendering rules: the
    first entry must start at 0, there must be at least three, and
    every chapter must run at least 10 seconds. A list that breaks
    any rule silently never becomes chapters. `duration` (seconds)
    is needed to judge the final chapter's length; without it the
    last chapter is reported unchecked, never assumed fine."""
    rows = []
    for ch in chapters or []:
        if isinstance(ch, dict):
            start = float(ch.get("start", ch.get("start_s", 0)) or 0)
            title = str(ch.get("title") or ch.get("draft_title") or "")
        elif isinstance(ch, (list, tuple)) and ch:
            start = float(ch[0])
            title = str(ch[1]) if len(ch) > 1 else ""
        else:
            continue
        rows.append({"start": round(start, 2), "title": title})
    rows.sort(key=lambda r: r["start"])
    issues = []
    if not rows:
        issues.append("no chapters given")
    else:
        if rows[0]["start"] != 0:
            issues.append(f"first chapter starts at {rows[0]['start']}s - YouTube needs 0:00 first")
        if len(rows) < 3:
            issues.append(f"only {len(rows)} chapter(s) - YouTube needs at least 3")
    out = []
    for i, r in enumerate(rows):
        if i + 1 < len(rows):
            seconds = round(rows[i + 1]["start"] - r["start"], 2)
        elif duration is not None:
            seconds = round(float(duration) - r["start"], 2)
        else:
            seconds = None
        if seconds is not None and seconds < _MIN_CHAPTER_S:
            issues.append(f"chapter at {_mmss(r['start'])} runs {seconds}s - under the 10s minimum")
        out.append({"start": r["start"], "label": _mmss(r["start"]),
                    "title": r["title"], "seconds": seconds})
    return {"valid": not issues, "issues": issues, "chapters": out,
            "last_chapter_checked": duration is not None}


def _keywords(text):
    return {w for w in re.findall(r"[a-z']{4,}", str(text).lower())
            if w not in _CH_STOP}


def chapters_from_cues(cues, target=7):
    """Draft chapter boundaries from timestamped cues. Boundaries are
    scored by the pause before them plus how much the vocabulary
    shifts across them; picks keep the 10s minimum spacing. Titles
    are keyword drafts to retitle, never finished chapter names."""
    cues = _norm_cues(cues)
    if len(cues) < 6:
        return {"valid": False, "issues": ["too few cues to chapter"],
                "chapters": []}
    dur = cues[-1][1]
    cand = []
    for i in range(1, len(cues)):
        gap = cues[i][0] - cues[i - 1][1]
        before = " ".join(c[2] for c in cues[max(0, i - 12):i])
        after = " ".join(c[2] for c in cues[i:i + 12])
        kb, ka = _keywords(before), _keywords(after)
        shift = 1 - (len(kb & ka) / len(kb | ka)) if (kb | ka) else 0
        cand.append((gap * 1.6 + shift * 3.2, cues[i][0]))
    cand.sort(reverse=True)
    picked = [0.0]
    for _score, t in cand:
        if len(picked) >= int(target or 7):
            break
        if all(abs(t - p) >= _MIN_CHAPTER_S for p in picked) \
                and dur - t >= _MIN_CHAPTER_S:
            picked.append(t)
    picked.sort()
    chapters = []
    for n, t in enumerate(picked):
        end = picked[n + 1] if n + 1 < len(picked) else dur
        text = " ".join(c[2] for c in cues if c[0] >= t and c[1] <= end)
        kw = sorted(_keywords(text), key=lambda w: -text.lower().count(w))
        chapters.append({"start": round(t, 2),
                         "title": " ".join(w.capitalize() for w in kw[:3]) or "Section"})
    checked = validate_chapters(chapters, duration=dur)
    return {"valid": checked["valid"], "issues": checked["issues"],
            "chapters": checked["chapters"]}


# ------------------------------------------------------------ viral rank

def rank_viral(videos, min_multiple=1.5):
    """Rank PROVIDED videos by multiple over each channel's own
    median views. Channels with fewer than four videos are skipped
    and reported — a median off one or two videos is not a median.
    Formula labels come from hooks_lib and judge title words only.
    This function never collects data; the caller supplies rows."""
    by = {}
    for v in videos or []:
        if isinstance(v, dict):
            by.setdefault(str(v.get("channel") or "?"), []).append(v)
    out, thin = [], []
    for ch, vids in by.items():
        views = [float(v.get("views", 0) or 0) for v in vids]
        if len(vids) < 4:
            thin.append([ch, len(vids)])
            continue
        med = statistics.median(views) if views else 0
        for v in vids:
            mult = (float(v.get("views", 0) or 0) / med) if med else 0
            name, _hits = hooks_lib.classify_hook(str(v.get("title") or ""))
            out.append({"channel": ch,
                        "title": str(v.get("title") or ""),
                        "views": int(float(v.get("views", 0) or 0)),
                        "median": int(med),
                        "multiple": round(mult, 2),
                        "formula": name or "Unclassified",
                        "url": str(v.get("url") or "")})
    out = [r for r in out if r["multiple"] >= float(min_multiple or 1.5)]
    out.sort(key=lambda r: -r["multiple"])
    return {"outliers": out, "skipped_thin_channels": thin}


# ------------------------------------------------------------ retention

def read_retention(rows, duration=None, cues=None):
    """Read audience-retention points [[position, pct_still_watching]]
    and report the three distinct problems: hook leak (lost in the
    first 30s, or first 10% on a percent axis without duration),
    cliffs (steepest single drops), and slide (mean bleed rate
    after the hook window). With cues + duration, each cliff names
    what was being said near it."""
    pts = []
    for r in rows or []:
        if isinstance(r, (list, tuple)) and len(r) >= 2:
            try:
                pts.append((float(r[0]), float(r[1])))
            except (TypeError, ValueError):
                continue
        elif isinstance(r, dict):
            try:
                pts.append((float(r.get("x", r.get("position"))),
                            float(r.get("y", r.get("retention")))))
            except (TypeError, ValueError):
                continue
    pts.sort(key=lambda p: p[0])
    if len(pts) < 8:
        return {"ok": False, "reason": "could not read at least 8 data points"}
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    pct_axis = max(xs) <= 100.5
    dur = float(duration) if duration else None

    def at_seconds(x):
        if pct_axis and dur:
            return round(x / 100.0 * dur, 1)
        return round(x, 1) if not pct_axis else None

    start = ys[0] or 100.0
    cutoff = 30.0 if not pct_axis else (30.0 / dur * 100 if dur else 10.0)
    hook_end = min((y for x, y in pts if x <= cutoff), default=start)
    hook_leak = round(start - hook_end, 2)
    drops = []
    for i in range(1, len(pts)):
        d = ys[i - 1] - ys[i]
        span = xs[i] - xs[i - 1] or 1
        drops.append((d / span, xs[i - 1], xs[i], d))
    drops.sort(reverse=True)
    cliffs = [{"from": round(a, 2), "to": round(b, 2),
               "lost": round(d, 2), "at_seconds": at_seconds(a)}
              for _rate, a, b, d in drops[:5] if d > 0.8]
    mid = [rate for rate, x0, _x1, _d in drops if x0 > cutoff]
    slide = round(sum(mid) / len(mid), 3) if mid else 0
    said = {}
    norm = _norm_cues(cues)
    if norm:
        for c in cliffs:
            if c["at_seconds"] is None:
                continue
            t = c["at_seconds"]
            near = [q[2] for q in norm if q[0] <= t + 4 and q[1] >= t - 4]
            said[str(c["from"])] = " ".join(near)[:140]
    return {"ok": True, "points": len(pts), "start": start,
            "hook_leak": hook_leak, "end": ys[-1], "cliffs": cliffs,
            "slide_per_unit": slide, "said": said}


# ------------------------------------------------------------ hooks + package

def score_hooks(hooks):
    """Score hook candidates with Julie's hooks_lib panel, best first.
    The score is a heuristic: low means look again, high promises
    nothing."""
    out = []
    for h in hooks or []:
        text = str(h or "").strip()
        if not text:
            continue
        sc = hooks_lib.score_hook(text)
        out.append({"hook": text, "criteria": sc["criteria"],
                    "total": sc["total"], "band": sc["band"],
                    "formula": sc["formula"]})
    out.sort(key=lambda r: -r["total"])
    return {"ranked": out}


def package_rank(titles, thumbs):
    """Rank every title x thumbnail-text pairing deterministically:
    lint score first, combined curiosity (hooks_lib on title+thumb)
    as tie-break. The brain generates candidates; this only judges
    the pairing, it never invents titles."""
    pairs = []
    for title in titles or []:
        for thumb in thumbs or []:
            lint = lint_title_pair(str(title), str(thumb))
            combined = hooks_lib.score_hook(f"{title} {thumb}")
            pairs.append({
                "title": str(title), "thumbnail_text": str(thumb),
                "lint_score": lint["score"], "issues": lint["issues"],
                "good": lint["good"],
                "combined_curiosity": combined["criteria"]["curiosity_gap"],
                "combined_total": combined["total"]})
    pairs.sort(key=lambda p: (-p["lint_score"], -p["combined_curiosity"]))
    return {"pairs": pairs, "best": pairs[0] if pairs else None}


# ------------------------------------------------------------ registry

def register_yt_tools(reg):
    """Register the read-only YouTube packaging tools. All handlers
    are pure functions over their args — no files, no network."""
    reg.register(
        "yt_hook_score",
        "Score YouTube hook candidates with the 21-formula panel (heuristic, not a promise). Args: {hooks: [strings]}. Returns ranked scores + formula names. Read-only.",
        {"hooks": {"type": "array", "required": True,
                   "desc": "hook candidate lines to score"}},
        lambda a: (True, score_hooks(a.get("hooks"))),
        mutating=False, needs_allow=False, timeout=30)
    reg.register(
        "yt_title_lint",
        "Lint a YouTube title + thumbnail text as ONE pairing (length cuts, duplication, vague words, caps). Args: {title, thumb?}. Read-only.",
        {"title": {"type": "string", "required": True, "desc": "the title text"},
         "thumb": {"type": "string", "required": False, "desc": "thumbnail text (optional)"}},
        lambda a: (True, lint_title_pair(a.get("title"), a.get("thumb"))),
        mutating=False, needs_allow=False, timeout=30)
    reg.register(
        "yt_chapters_validate",
        "Validate a chapter list against YouTube's rules (0:00 first, 3+, 10s minimum). Args: {chapters: [{start,title}], duration?}. Read-only.",
        {"chapters": {"type": "array", "required": True, "desc": "chapter rows with start seconds"},
         "duration": {"type": "number", "required": False, "desc": "video duration seconds (judges the last chapter)"}},
        lambda a: (True, validate_chapters(a.get("chapters"), a.get("duration"))),
        mutating=False, needs_allow=False, timeout=30)
    reg.register(
        "yt_chapters_from_cues",
        "Draft chapter boundaries from timestamped transcript cues (pauses + vocabulary shift), validated. Args: {cues: [{start,end,text}], target?}. Titles are drafts to retitle. Read-only.",
        {"cues": {"type": "array", "required": True, "desc": "timestamped transcript cues"},
         "target": {"type": "number", "required": False, "desc": "chapter count to aim for (default 7)"}},
        lambda a: (True, chapters_from_cues(a.get("cues"), a.get("target") or 7)),
        mutating=False, needs_allow=False, timeout=30)
    reg.register(
        "yt_viral_rank",
        "Rank PROVIDED videos by multiple over each channel's own median views (channels under 4 videos skipped). Args: {videos: [{channel,title,views,url}], min_multiple?}. Never collects data. Read-only.",
        {"videos": {"type": "array", "required": True, "desc": "collected video rows supplied by the caller"},
         "min_multiple": {"type": "number", "required": False, "desc": "outlier threshold (default 1.5)"}},
        lambda a: (True, rank_viral(a.get("videos"), a.get("min_multiple") or 1.5)),
        mutating=False, needs_allow=False, timeout=30)
    reg.register(
        "yt_retention_read",
        "Read audience-retention points [[position, pct]]: hook leak, cliffs, slide; names what was said at cliffs when cues+duration given. Args: {rows, duration?, cues?}. Read-only.",
        {"rows": {"type": "array", "required": True, "desc": "retention points [position, percent still watching]"},
         "duration": {"type": "number", "required": False, "desc": "video duration seconds"},
         "cues": {"type": "array", "required": False, "desc": "timestamped cues for cliff narration"}},
        lambda a: (True, read_retention(a.get("rows"), a.get("duration"), a.get("cues"))),
        mutating=False, needs_allow=False, timeout=30)
    reg.register(
        "yt_package_rank",
        "Rank title x thumbnail-text pairings (lint score + combined curiosity). Args: {titles: [strings], thumbs: [strings]}. Judges pairings only; never invents titles. Read-only.",
        {"titles": {"type": "array", "required": True, "desc": "title candidates"},
         "thumbs": {"type": "array", "required": True, "desc": "thumbnail text candidates"}},
        lambda a: (True, package_rank(a.get("titles"), a.get("thumbs"))),
        mutating=False, needs_allow=False, timeout=30)
    return reg
