"""topic_lock.py — Julie ROUND 4 (third-film QC, fix 1): the TOPIC LOCK.

The third film ("The Rise of Electric Cars", job 2035f85b) failed on
topic in three separate places, and nothing in the chain owned any of
them:

1. AUTO picked the SECOND film's exact subject (electric vehicles)
   against an explicit exclusion in the order. The exclusion lived
   only in the user's words; the Worker's rewritten brief said
   "topic AUTO (choose strong documentary subject)" and the pick
   ignored the constraint. There was no delivered-topic history
   anywhere in the pick path.
2. Compliance marked the topic requirement PASS by matching the
   word "Auto" — it checked a word, not the pick.
3. The chapter top-up ABANDONED the chapter's subject (an EV
   chapter became a seatbelt-safety mini-documentary). The v100 /
   next-round gates check that a top-up is NEW; nothing checked
   that it is still ABOUT the chapter.

This module is the deterministic half of the lock, shared by the
outline picker (long_video.outline), the top-up gate
(long_video.render_chapters) and the compliance verdict
(compliance.requirement_verdicts):

- content-word normalisation (plural folding + a small vehicle
  synonym map, so "electric cars" and "electric vehicles" are the
  same subject),
- topic collision detection (delivered-history dedupe),
- exclusion matching + deterministic exclusion extraction from the
  owner's own words,
- chapter subject anchors + the top-up coherence report.

No LLM, no network — the same inputs always give the same verdict,
so the gates are testable offline and cannot be talked around.
"""

import re

_STOP = {
    "the", "a", "an", "of", "in", "on", "to", "and", "or", "is",
    "it", "its", "this", "that", "why", "how", "what", "your",
    "you", "we", "they", "for", "with", "from", "by", "at", "are",
    "was", "were", "be", "been", "has", "have", "had", "not", "no",
    "do", "does", "did", "will", "would", "can", "could", "should",
    "about", "into", "over", "under", "than", "then", "so", "as",
    "if", "but", "all", "any", "one", "two", "first", "rise",
    "too", "very",
    "story", "untold", "hidden", "truth", "really", "nobody",
    "tells", "explained", "inside", "full",
}

# Subject synonyms: the same documentary subject under its common
# names. Film 3's exclusion said "vehicles"; its title said "Cars".
_SYNONYMS = {
    "car": "vehicle", "cars": "vehicle", "automobile": "vehicle",
    "automobiles": "vehicle", "vehicles": "vehicle",
    "ev": "electric vehicle", "evs": "electric vehicle",
}


def _norm_word(w):
    w = w.lower().strip("'")
    if w in _SYNONYMS:
        return _SYNONYMS[w]
    if len(w) > 3 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return _SYNONYMS.get(w, w)


def content_words(text):
    """The subject-bearing words of a topic/title/line: stopwords
    and packaging filler removed, plurals folded, synonyms mapped.
    Multi-word synonym outputs ("electric vehicle") are split back
    into single tokens so set maths stays uniform."""
    out = set()
    for w in re.findall(r"[a-z0-9']+", str(text or "").lower()):
        if len(w) <= 2 or w in _STOP:
            continue
        for tok in _norm_word(w).split():
            if len(tok) > 2 and tok not in _STOP:
                out.add(tok)
    return out


def topics_collide(a, b):
    """True when two topic/title strings name the same subject:
    containment of the smaller subject in the larger >= 0.6, or
    Jaccard >= 0.4. ("The Rise of Electric Vehicles" vs "The Rise
    of Electric Cars: Revolution on Wheels" — shared subject words
    {electric, vehicle} contain 2 of the smaller set's 2.)"""
    wa, wb = content_words(a), content_words(b)
    if not wa or not wb:
        return False
    inter = wa & wb
    if not inter:
        return False
    containment = len(inter) / min(len(wa), len(wb))
    jaccard = len(inter) / len(wa | wb)
    return containment >= 0.6 or jaccard >= 0.4


def exclusion_hit(topic, exclusions):
    """The exclusion string a topic violates, or None. An exclusion
    hits when its subject words are contained in the topic's words
    (>= 60% of the exclusion's words present — one shared subject
    word of a two-word exclusion is not enough on its own unless
    the other is a synonym-folded match)."""
    tw = content_words(topic)
    if not tw:
        return None
    for ex in exclusions or []:
        ew = content_words(ex)
        if not ew:
            continue
        if len(ew & tw) / len(ew) >= 0.6:
            return ex
    return None


def history_hit(topic, history):
    """The delivered-history entry a pick repeats, or None."""
    for h in history or []:
        if topics_collide(topic, h):
            return h
    return None


_EXCL_RX = re.compile(
    r"\b(?:not|never|no|avoid|except|excluding|exclude|without)\b"
    r"\s+(?:a\s+|an\s+|the\s+)?"
    r"([a-z][a-z0-9'\- ]{2,60}?)"
    r"(?=[,.;)\n]|$|\b(?:and|or|topic|subject|video|film|documentary|please)\b)",
    re.I)
_DONOT_RX = re.compile(
    r"\b(?:do\s*not|don't|dont|not)\s+(?:pick|choose|select|make|do|use)\b"
    r"\s+(?:a\s+|an\s+|the\s+)?"
    r"([a-z][a-z0-9'\- ]{2,60}?)"
    r"(?=[,.;)\n]|$|\b(?:and|or)\b)", re.I)
_EXCL_TAIL = {"topic", "subject", "video", "film", "documentary",
              "again", "this", "that", "one", "it"}
# Manner/length words are production constraints, not subjects:
# "not too long" must never become a topic exclusion (it would
# bind any title containing "long").
_EXCL_JUNK = {"long", "short", "big", "small", "much", "many",
              "more", "less", "fast", "slow", "loud", "quiet",
              "longer", "shorter", "bigger", "smaller"}


def parse_exclusions(text):
    """Deterministic topic exclusions from the owner's own words:
    "not electric vehicles", "avoid bees", "except the war",
    "don't pick space". Best-effort by design — the phrases are
    also carried verbatim into the outline prompt, so a phrase the
    regex trims imperfectly still binds the picker through the
    prompt; this list is what the ENFORCEMENT checks against."""
    out = []
    for rx in (_EXCL_RX, _DONOT_RX):
        for m in rx.finditer(str(text or "")):
            words = [w for w in re.findall(r"[a-z0-9']+", m.group(1).lower())
                     if w not in _EXCL_TAIL]
            phrase = " ".join(words[:5]).strip()
            cw = content_words(phrase)
            if len(cw) >= 1 and not cw <= _EXCL_JUNK \
                    and phrase not in out:
                out.append(phrase)
    return out


def subject_anchors(*texts):
    """The locked subject of a chapter: content words of the film
    title + the chapter title + the chapter brief, unioned."""
    anchors = set()
    for t in texts:
        anchors |= content_words(t)
    return anchors


# A top-up whose scenes barely touch the chapter's subject words
# is not a top-up — it is a different film wearing the chapter's
# title (film 3: 60 s of seatbelts inside an EV chapter).
COHERENCE_MIN_SCENE_SHARE = 1.0 / 3.0
# Below this many distinct anchor words the anchor set is too thin
# to judge (degenerate outlines in tests, one-word chapters): the
# gate reports UNVERIFIED and does not reject.
COHERENCE_MIN_ANCHORS = 4


def coherence_report(new_vos, anchors):
    """Is this proposed top-up still ABOUT the chapter's locked
    subject? Returns {checked, coherent, scene_share,
    scenes_with_anchor, scenes, foreign_words}. `checked` False =
    too few anchors to judge (never a rejection). A scene is on
    subject when its content words intersect the anchors."""
    anchors = set(anchors or set())
    vos = [str(v or "") for v in (new_vos or [])]
    if len(anchors) < COHERENCE_MIN_ANCHORS or not vos:
        return {"checked": False, "coherent": True, "scene_share": 0.0,
                "scenes_with_anchor": 0, "scenes": len(vos),
                "foreign_words": []}
    hits = 0
    foreign = {}
    for vo in vos:
        words = content_words(vo)
        if words & anchors:
            hits += 1
        for w in words - anchors:
            foreign[w] = foreign.get(w, 0) + 1
    share = hits / len(vos)
    top_foreign = [w for w, _ in sorted(
        foreign.items(), key=lambda kv: -kv[1])[:5]]
    return {"checked": True,
            "coherent": bool(hits) and share >= COHERENCE_MIN_SCENE_SHARE,
            "scene_share": round(share, 3),
            "scenes_with_anchor": hits, "scenes": len(vos),
            "foreign_words": top_foreign}
