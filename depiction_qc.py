"""depiction_qc.py — Julie ROUND 4 (third-film QC, fix 5): the
DEPICTION-BUDGET counter.

Round 3 put the depiction budget in the taste pack — fern's
584-shot measurement: evidence ~35% / context ~33% / literal ~19% /
metaphor ~13%, so literal illustration is capped at ~20% of beats.
Julie's grammar was near-100% literal ("show the thing the line
names"), which IS the slideshow feel — and nothing in the pipeline
even counted it. The third film measured 57.5% literal by hand and
no QC surface noticed.

This module counts, deterministically, from the plan's own beat
metadata (what the brain SAID each beat would show):

- evidence — the beat shows proof: a retrieved source backs it
  (source_ref / source_text on the scene), a document visual, or a
  data visual (counter / chart / donut / dot grid) carrying a
  number the line actually speaks.
- literal — the beat shows the very thing the line names: footage
  whose search queries share the line's subject words, or a direct
  picture visual (photo / map).
- metaphor — a symbolic stand-in: icon rows, stamps, strike-through,
  warnings, quote cards, big-word typography, or footage chosen as
  a symbol (its `why` says so).
- context — everything else: setting / ambience footage (queries
  barely touch the line's words) and structural visuals (lists,
  versus, steps, clocks) that organise rather than depict.

It is a PLAN-LEVEL estimate — it classifies the recorded intent,
not the rendered pixels (the frame-level read stays with taste
QC). Scenes carrying no visual metadata at all are UNCLASSIFIABLE
and excluded from the mix; a chapter with too few classifiable
beats reports the mix but raises no FAIL.

The FAIL (rule DEPICTION, in anti_boring.BORING_CRITICAL_RULES)
rides the chapter's compliance checks, so the existing fix loop in
long_video.render_chapters treats an over-literal chapter exactly
like any other boring-critical failure: re-render with guidance,
bounded rounds, honest length otherwise.
"""

import re

# The Round-3 pack budget: literal illustration <= ~20% of beats.
LITERAL_BUDGET = 0.20
# A mix is only enforced on chapters with enough classifiable
# beats to mean anything.
MIN_CLASSIFIABLE = 5

_DATA_VISUALS = {"counter", "donut", "bar", "bar_compare", "graph",
                 "dot_grid", "watch", "four", "chart", "data_chart"}
_DOC_VISUALS = {"evidence_document", "document"}
_PICTURE_VISUALS = {"picture", "photo", "image", "india_map",
                    "world_dots", "map"}
_SYMBOLIC_VISUALS = {"icon_row", "stamp", "strike", "warning",
                     "quote_card", "quote", "big_word",
                     "typewriter_page", "battery"}

_STOP = {
    "the", "a", "an", "of", "in", "on", "to", "and", "or", "is",
    "it", "its", "this", "that", "why", "how", "what", "your",
    "you", "we", "they", "for", "with", "from", "by", "at", "are",
    "was", "were", "be", "been", "has", "have", "had", "about",
    "into", "over", "under", "than", "then", "so", "as", "if",
    "but", "all", "any",
}


def _words(text):
    return {w for w in re.findall(r"[a-z0-9']+", str(text or "").lower())
            if len(w) > 2 and w not in _STOP}


def _has_number(text):
    return bool(re.search(r"\d", str(text or "")))


def classify_beat(scene):
    """One beat's depiction mode, or None when the scene carries
    no visual metadata to classify (bare script stubs, pre-v79
    plans). Order matters: proof first, then the literal picture,
    then the symbolic stand-in, then context."""
    if not isinstance(scene, dict):
        return None
    visual = str(scene.get("visual") or "").strip().lower()
    has_footage = bool(scene.get("has_footage"))
    if not visual and not has_footage and not scene.get("source_ref"):
        return None
    vo = str(scene.get("vo") or "")
    # evidence — a retrieved source backs the beat, a document is
    # shown, or a data visual carries a number the line speaks.
    if scene.get("source_ref") or scene.get("source_text"):
        return "evidence"
    if visual in _DOC_VISUALS:
        return "evidence"
    if visual in _DATA_VISUALS and (scene.get("value")
                                   or _has_number(vo)):
        return "evidence"
    # metaphor — a symbolic visual, or footage the director chose
    # AS a symbol (its recorded why says so).
    if visual in _SYMBOLIC_VISUALS:
        return "metaphor"
    why = str(scene.get("why") or "").lower()
    if has_footage and ("symbol" in why or "metaphor" in why):
        return "metaphor"
    # literal vs context for footage: does the clip's search
    # language share the line's subject words (the clip shows the
    # named thing), or is it setting/ambience around the line?
    if has_footage:
        line_words = _words(vo)
        query_words = set()
        for q in scene.get("queries") or []:
            query_words |= _words(q)
        if line_words and query_words:
            overlap = len(line_words & query_words) / len(query_words)
            return "literal" if overlap >= 0.25 else "context"
        return "context"
    if visual in _PICTURE_VISUALS:
        return "literal"
    return "context"


def depiction_report(scenes):
    """The mix over a chapter's (or film's) beats:
    {beats, classifiable, counts, shares, literal_share, budget,
    over_budget}. over_budget only when enough beats classified."""
    counts = {"literal": 0, "evidence": 0, "context": 0,
              "metaphor": 0}
    n = 0
    for sc in scenes or []:
        mode = classify_beat(sc)
        if mode is None:
            continue
        counts[mode] += 1
        n += 1
    shares = {k: (round(v / n, 3) if n else 0.0)
              for k, v in counts.items()}
    literal_share = shares["literal"]
    return {"beats": len(scenes or []), "classifiable": n,
            "counts": counts, "shares": shares,
            "literal_share": literal_share,
            "budget": LITERAL_BUDGET,
            "over_budget": bool(n >= MIN_CLASSIFIABLE
                                and literal_share > LITERAL_BUDGET)}


def depiction_checks(scenes):
    """Compliance-shaped checks for one chapter: one DEPICTION
    FAIL when the literal share breaks the budget (empty list
    otherwise — a chapter inside budget, or too thin to judge,
    produces no check at all)."""
    rep = depiction_report(scenes)
    if not rep["over_budget"]:
        return []
    return [{"rule": "DEPICTION", "status": "FAIL",
             "detail": (f"depiction mix is {rep['literal_share']:.0%} "
                        f"literal illustration (plan-level count over "
                        f"{rep['classifiable']} beats: "
                        f"{rep['counts']}) — the Round-3 budget is "
                        f"<= {LITERAL_BUDGET:.0%}; re-voice the beats "
                        f"as evidence, context or metaphor instead of "
                        f"showing the thing each line names"),
             "scene": None, "depiction": rep}]
