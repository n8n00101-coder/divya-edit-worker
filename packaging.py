"""packaging.py — Julie v89: the delivery-end packaging step.

Runs AFTER a long video is assembled (wired in long_video.py, wrapped
in try/except there — a packaging failure never changes delivery).
Deterministic generation from structured inputs only: templates +
hooks_lib scoring for title ranking. No LLM, no network, no new deps.

Inputs: topic, final title, chapter list with timestamps, key
claims/sources. Output dict (also written as packaging.json):
  titles        10 candidates, each < 60 chars, ranked by hook score
  thumbnails    3 concepts: 2-3 words of text + one-line visual note
  pair_check    title <-> thumbnail validated AS A PAIR (thumbnail
                text must not duplicate title wording; combined
                curiosity gap scored); chosen pair passes or is flagged
  description   hook line + chapters with timestamps + sources list
  shorts        3 Shorts cut points from chapter boundaries /
                high-energy chapters, with a one-line rationale each
  first_comment a debate question (ends with '?')
"""

import re

try:
    import hooks_lib as _hooks
except Exception:  # packaging degrades to unscored ranking, never dies
    _hooks = None

_STOP = {"the", "a", "an", "of", "in", "on", "to", "and", "or", "is",
         "it", "its", "this", "that", "why", "how", "what", "your",
         "you", "we", "they", "for", "with", "from", "by", "at"}
_ENERGY = ("secret", "shock", "hidden", "reveal", "twist", "final",
           "truth", "vanish", "forgot", "climax", "payoff", "death",
           "last", "never", "nobody", "real")


def _fit60(text):
    """One title candidate, hard-capped under 60 chars."""
    t = " ".join(str(text or "").split()).strip(" .")
    if len(t) < 60:
        return t
    cut = t[:59].rsplit(" ", 1)[0].strip(" ,;:-")
    return (cut or t[:59]).strip()


def _content_words(text):
    return {w for w in re.findall(r"[a-z0-9']+", str(text).lower())
            if w not in _STOP and len(w) > 2}


def _fmt_ts(seconds):
    seconds = max(0, int(round(float(seconds or 0))))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _norm_chapters(chapters):
    """Accept [{title, start_s|start, end_s|end, duration_s}] or
    (title, start) tuples; return sorted [{title, start_s, end_s}]."""
    out = []
    for ch in chapters or []:
        if isinstance(ch, (list, tuple)):
            title = str(ch[0]) if ch else ""
            start = float(ch[1]) if len(ch) > 1 else 0.0
            end = float(ch[2]) if len(ch) > 2 else start + 60.0
        elif isinstance(ch, dict):
            title = str(ch.get("title") or "")
            start = float(ch.get("start_s", ch.get("start", 0)) or 0)
            if ch.get("end_s") is not None or ch.get("end") is not None:
                end = float(ch.get("end_s", ch.get("end")))
            elif ch.get("duration_s") or ch.get("duration"):
                end = start + float(ch.get("duration_s")
                                    or ch.get("duration"))
            else:
                end = start + 60.0
        else:
            continue
        if title.strip():
            out.append({"title": title.strip(), "start_s": start,
                        "end_s": max(end, start + 1.0)})
    out.sort(key=lambda c: c["start_s"])
    return out


def _score(text):
    if _hooks is None:
        return {"total": 0, "criteria": {}}
    try:
        return _hooks.score_hook(text)
    except Exception:
        return {"total": 0, "criteria": {}}


# ------------------------------------------------------------- titles
def title_candidates(topic, final_title, chapters):
    """10 deterministic title candidates (<60 chars), hook-scored and
    ranked best first. Built only from the given topic/title/chapter
    words — no invented claims or numbers."""
    topic = " ".join(str(topic or "").split()).strip()
    base = _fit60(final_title) or _fit60(topic) or "The Untold Story"
    subj = _fit60(topic) or base
    ch_titles = [c["title"] for c in chapters]
    last = ch_titles[-1] if ch_titles else "The Payoff"
    raw = [
        base,
        f"Why {subj}?",
        f"{subj}: What Nobody Tells You",
        f"The Hidden Truth Behind {subj}",
        f"{subj} — The Full Story",
        f"Nobody Talks About {subj}",
        f"{subj}: {last}",
        f"What Really Happened to {subj}",
        f"The Untold Story of {subj}",
        f"{subj}, Explained",
        f"Inside {subj}: {ch_titles[0]}" if ch_titles else
        f"Inside {subj}",
    ]
    seen, out = set(), []
    for t in raw:
        t = _fit60(t)
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append({"title": t, "score": _score(t)["total"]})
    out.sort(key=lambda r: -r["score"])
    return out[:10]


# --------------------------------------------------------- thumbnails
def thumbnail_concepts(topic, chapters):
    """3 concepts: 2-3 words of text each + a one-line visual note.
    Text words are drawn from the topic but kept SHORT and punchy."""
    words = [w for w in re.findall(r"[A-Za-z][a-z]+",
                                   str(topic or ""))
             if w.lower() not in _STOP]
    w1 = (words[0].upper() if words else "VANISHED")
    w2 = (words[1].upper() if len(words) > 1 else "FORGOTTEN")
    w3 = (words[2].upper() if len(words) > 2 else "MYSTERY")
    return [
        {"text": f"{w1} {w2}?",
         "visual": "One wide real-footage frame of the place, subject "
                   "large and off-centre, empty sky for the text."},
        {"text": f"NOBODY KNEW",
         "visual": "A single human detail in close-up (hands, a door, "
                   "a boat) filling the frame, face turned away."},
        {"text": f"{w3} REVEALED",
         "visual": "Before/after split of the same location, the "
                   "changed half brighter, text on the darker half."},
    ]


# ---------------------------------------------------------- pair check
def pair_check(title, thumb_text):
    """Validate a title <-> thumbnail PAIR. Fails when the thumbnail
    text duplicates title wording (shared content words) — the pair
    must ADD curiosity, not repeat. Combined curiosity gap is scored
    from hooks_lib on title + thumbnail together."""
    shared = _content_words(title) & _content_words(thumb_text)
    combined = _score(f"{title} {thumb_text}")
    curiosity = (combined.get("criteria") or {}).get(
        "curiosity_gap", combined["total"])
    issues = []
    if shared:
        issues.append(
            f"thumbnail repeats title word(s): {', '.join(sorted(shared))}")
    if curiosity < 25:
        issues.append(f"combined curiosity gap is low ({curiosity})")
    return {"title": title, "thumbnail_text": thumb_text,
            "passes": not issues, "issues": issues,
            "duplicated_words": sorted(shared),
            "combined_curiosity": curiosity,
            "combined_score": combined["total"]}


def choose_pair(titles, thumbnails):
    """Pick the best passing (title, thumbnail) pair; if every
    thumbnail duplicates a title, ADJUST the thumbnail text (swap in
    non-duplicating words) and re-check. Returns (pair, check,
    adjusted_flag). If nothing can pass, the check is returned with
    passes=False — the caller flags it, never fakes a pass."""
    fallbacks = ["NOBODY KNEW", "IT VANISHED", "STILL SECRET",
                 "LOOK CLOSER", "GONE QUIETLY"]
    for t in titles:
        for th in thumbnails:
            chk = pair_check(t["title"], th["text"])
            if chk["passes"]:
                return {"title": t["title"],
                        "thumbnail_text": th["text"],
                        "thumbnail_visual": th["visual"]}, chk, False
    for t in titles:
        for fb in fallbacks:
            chk = pair_check(t["title"], fb)
            if chk["passes"]:
                return {"title": t["title"], "thumbnail_text": fb,
                        "thumbnail_visual": thumbnails[0]["visual"]
                        if thumbnails else ""}, chk, True
    chk = pair_check(titles[0]["title"], thumbnails[0]["text"])
    return {"title": titles[0]["title"],
            "thumbnail_text": thumbnails[0]["text"],
            "thumbnail_visual": thumbnails[0]["visual"]}, chk, False


# -------------------------------------------------------------- shorts
def shorts_cut_points(chapters, duration):
    """3 Shorts windows (30-45 s) anchored at chapter starts, preferring
    high-energy chapters (energy words / longest), all inside the
    video duration. One-line rationale each."""
    if not chapters:
        return []
    dur = float(duration or chapters[-1]["end_s"])

    def energy(c):
        hits = sum(1 for w in _ENERGY if w in c["title"].lower())
        return hits * 1000 + (c["end_s"] - c["start_s"])

    ranked = sorted(chapters, key=energy, reverse=True)
    picked, used_starts = [], []
    for c in ranked:
        if len(picked) >= 3:
            break
        start = c["start_s"]
        if any(abs(start - s) < 30 for s in used_starts):
            continue
        end = min(start + 40.0, dur, c["end_s"] if
                  c["end_s"] - start >= 25 else dur)
        if end - start < 20:
            continue
        used_starts.append(start)
        why = ("high-energy chapter ('%s') — opens on its strongest "
               "beat" % c["title"] if any(
                   w in c["title"].lower() for w in _ENERGY)
               else "chapter boundary at '%s' — a self-contained "
                    "beat that starts clean" % c["title"])
        picked.append({"start_s": round(start, 1),
                       "end_s": round(end, 1),
                       "start": _fmt_ts(start), "end": _fmt_ts(end),
                       "chapter": c["title"], "rationale": why})
    picked.sort(key=lambda p: p["start_s"])
    return picked


# ------------------------------------------------------------ main API
def build_packaging(topic, final_title, chapters, sources=None,
                    claims=None, duration=None):
    """The full packaging dict for one finished long video.

    ROUND 4 (fold-in): an AUTO/empty topic is not a topic — the
    pair check once graded the string 'Auto: What Nobody Tells
    You' against a film actually titled 'The Rise of Electric
    Cars'. When the topic is the AUTO placeholder, packaging
    falls back to the delivered final title as its subject."""
    if not str(topic or "").strip() \
            or str(topic).strip().lower().startswith("auto"):
        topic = final_title
    chs = _norm_chapters(chapters)
    dur = float(duration or (chs[-1]["end_s"] if chs else 0))
    titles = title_candidates(topic, final_title, chs)
    thumbs = thumbnail_concepts(topic, chs)
    pair, chk, adjusted = choose_pair(titles, thumbs)
    chk = {**chk, "adjusted": adjusted,
           "flagged": not chk["passes"]}
    hook_line = pair["title"]
    desc = [hook_line, ""]
    if claims:
        desc += [str(c) for c in claims[:3]] + [""]
    desc.append("Chapters:")
    for c in chs:
        desc.append(f"{_fmt_ts(c['start_s'])} {c['title']}")
    src_lines = []
    for s in sources or []:
        if isinstance(s, dict):
            src_lines.append(str(s.get("url") or s.get("title")
                                 or s.get("source") or "").strip())
        else:
            src_lines.append(str(s).strip())
    src_lines = [s for s in src_lines if s]
    if src_lines:
        desc += ["", "Sources:"] + [f"- {s}" for s in src_lines]
    first_comment = (
        f"Be honest: is {str(topic or 'this place').strip().lower()} "
        f"gone for good, or could it still come back?")
    if not first_comment.endswith("?"):
        first_comment += "?"
    return {"version": "v89-packaging-1", "topic": topic,
            "titles": titles, "thumbnails": thumbs,
            "chosen_pair": pair, "pair_check": chk,
            "description": "\n".join(desc),
            "shorts": shorts_cut_points(chs, dur),
            "first_comment": first_comment,
            "duration_s": dur}


if __name__ == "__main__":
    pkg = build_packaging(
        "the vanishing fishing village",
        "The Village the Sea Took Back",
        [{"title": "The Last Harbour", "start_s": 0, "end_s": 95},
         {"title": "The Hidden Tide Tables", "start_s": 95,
          "end_s": 210},
         {"title": "The Final Boat", "start_s": 210, "end_s": 300}],
        sources=["https://example.org/tide-study"], duration=300)
    assert len(pkg["titles"]) == 10
    assert all(len(t["title"]) < 60 for t in pkg["titles"])
    assert pkg["pair_check"]["passes"], pkg["pair_check"]
    assert pkg["first_comment"].endswith("?")
    print("packaging self-check OK")
