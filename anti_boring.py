"""anti_boring.py — Julie v100: the ANTI-BORING gates.

Why this module exists (Ajju, 2026-11-16): after the v85/v87/v88
samples and the monitored "Male Gaze" run (22 mistakes, 9 root
causes — ~/workspace/julie-malegaze/MONITORING_REPORT.md), the
pattern is proven: KNOWLEDGE was never the bottleneck — the
DECISION + FEEDBACK loop was. The brain knew the rules; nothing
forced them to happen. These gates are that forcing function.
Every function here is deterministic (no model calls except the
one explicitly injected `chat` in fact_gate's single rewrite
round), so each gate can be proven in a harness:

1. FOOTAGE-FIRST — footage queries must be stock-searchable
   (generic visible subjects; never film titles / film stills /
   people's names — the Male Gaze writer asked Commons for
   "Psycho film still female" and 26/26 requests were rejected,
   so the film shipped with 0% real footage). A beat whose
   footage search fails is RE-PLANNED (doc._attach_broll), never
   silently islanded; a beat that still gets no footage carries
   a logged waiver, and the achieved footage share is a QC
   check (FG-SHARE, target >= 70% of beats on documentary /
   long work).

2. FACT GATE — documentary scripts pass a claims check BEFORE
   directing: every statistic / event claim must carry a source
   (the scene's own citation, or an in-line "according to ...")
   or be hedged. An invented movement / hashtag / statistic
   (the Male Gaze film invented "#ViewersUnite" and a "30%
   rise") sends the script back for ONE rewrite round; a claim
   that survives the rewrite unsourced is REMOVED from the
   line, deterministically, sentence by sentence. Fake
   next-chapter teases are audited too (FG-TEASE): a film may
   only tease content that exists in its own plan.

3. QC WITH TEETH — BORING_CRITICAL_RULES names the failure
   classes that must trigger real fix rounds (long_video wires
   them): footage share, variety, dead air, fact gate. Log-only
   QC is what shipped the Male Gaze film with 112 FAILs and 0
   fix rounds.

4. DIRECTOR VARIETY CAPS — per chapter, no single visual type
   over ~25% of beats (VHIST). The Male Gaze director flattened
   the writer's varied proposals onto `counter` for 16/68
   beats. The histogram is computed from the director's own
   records; a violation re-plans before render (doc.plan) and
   FAILs in QC if it survives.

5. LENGTH HONESTY — chapter top-ups may only add NEW material:
   novelty_report() measures n-gram overlap between a proposed
   extension and the chapter it would extend. A restatement
   top-up is rejected and the chapter ships at its honest
   length (the Male Gaze top-ups restated and overshot).

6. SOUND FLOOR — the cue-sheet music curve must be EXECUTED,
   not just planned: media_qc measures the delivered loudness
   range (MQ-LRA, compliance.measure_lra) and a flat mix
   (< 5 LU on a long film) FAILs into a fix round that
   re-renders the flattest-curve chapters (long_video).
"""

import re
from collections import Counter

# ------------------------------------------------------------------
# shared text helpers
# ------------------------------------------------------------------

_STOP = {
    "the", "a", "an", "of", "in", "on", "at", "to", "and", "or",
    "is", "are", "was", "were", "it", "its", "this", "that",
    "with", "for", "from", "by", "as", "be", "been", "has",
    "have", "had", "not", "but", "so", "we", "you", "they",
    "he", "she", "his", "her", "their", "our", "your", "my",
    "one", "when", "what", "how", "why", "who", "which",
}


def content_words(text):
    """Lowercased content words of a line (stopwords removed)."""
    return [w for w in re.findall(r"[a-z][a-z'-]*", str(text or "").lower())
            if w not in _STOP and len(w) > 2]


# ------------------------------------------------------------------
# Gate 1 — stock-searchable footage queries
# ------------------------------------------------------------------

# Phrasings that name a copyrighted artefact instead of a visible
# subject. A stock library has none of these; the Male Gaze
# writer's queries were built from exactly these.
_NON_SEARCHABLE = (
    "film still", "movie still", "film scene", "movie scene",
    "screenshot", "screen capture", "screen grab", "trailer",
    "poster", "scene from", "clip from", "still from",
)


def query_is_searchable(q):
    """True when a footage query names a concrete, stock-searchable
    subject: at least 2 content words, no copyrighted-artefact
    phrasing, and not dominated by capitalised name/title words
    (a person's name, a film title — stock libraries tag visible
    subjects, not names)."""
    s = str(q or "").strip()
    if len(s) < 3:
        return False
    low = s.lower()
    if any(p in low for p in _NON_SEARCHABLE):
        return False
    words = [w.strip(".,;:!?\"'") for w in s.split() if w.strip(".,;:!?\"'")]
    content = [w for w in words if w.lower() not in _STOP and len(w) > 2]
    if len(content) < 2:
        return False
    caps = [w for w in content if w[:1].isupper()]
    if len(caps) * 2 >= len(content) and len(caps) >= 2:
        return False
    return True


def derive_query(line, label=""):
    """A generic subject query derived from the line itself: its
    first content words, lowercased (the form stock libraries
    tag). Falls back to the scene label. '' when nothing usable
    exists."""
    words = content_words(line)[:4]
    if len(words) < 2:
        words = content_words(label)[:4]
    return " ".join(words) if len(words) >= 2 else ""


def searchable_queries(queries, line, label=""):
    """Filter a scene's footage queries down to stock-searchable
    ones; when none survive, derive one from the line. Returns
    (kept, dropped) — the drop is always reported, never silent."""
    kept, dropped = [], []
    for q in queries or []:
        (kept if query_is_searchable(q) else dropped).append(str(q))
    if not kept:
        d = derive_query(line, label)
        if d:
            kept = [d]
    return kept[:2], dropped


def footage_share(scenes):
    """(have, total, share) of beats carrying real footage."""
    total = len(scenes or [])
    have = sum(1 for s in scenes or [] if s.get("has_footage"))
    return have, total, (have / total if total else 0.0)


def audit_footage_share(scenes, cfg, target=0.70):
    """FG-SHARE: the achieved real-footage share, reported in QC
    for every long film. FAIL below the documentary target —
    drawn/generated visuals are the justified exception (each
    carries a logged waiver), never the default."""
    if (cfg or {}).get("kind") != "long":
        return []
    have, total, share = footage_share(scenes)
    if not total:
        return []
    waived = sum(1 for s in scenes if s.get("footage_waived"))
    status = "PASS" if share >= target else "FAIL"
    return [{"rule": "FG-SHARE", "status": status,
             "detail": (f"real footage on {have}/{total} beats "
                        f"({share:.0%}); documentary target "
                        f">= {target:.0%}; {waived} beat(s) carry a "
                        f"logged no-footage waiver"),
             "scene": None}]


# ------------------------------------------------------------------
# Gate 2 — the fact gate
# ------------------------------------------------------------------

_HEDGES = (
    "reportedly", "roughly", "around ", "about ", "approximately",
    "estimates suggest", "some estimates", "may ", "might ",
    "believed to", "said to", "claims", "suggests that",
    "according to some",
)

_EVENT_PATTERNS = (
    re.compile(r"#\w+"),                                        # a hashtag = a named movement/campaign
    re.compile(r"\b(founded|launched|established|formed|began|started)\s+in\s+\d{4}\b", re.I),
    re.compile(r"\b(movement|campaign)\s+(began|started|launched|erupted|swept)\b", re.I),
    re.compile(r"\bwent\s+viral\b", re.I),
)


def scene_claims(scene):
    """The factual claims one scene makes, each judged:
    {kind: 'stat'|'event', text, sourced, hedged}.

    A claim is SOURCED when the scene carries its own citation
    (the `source` field the writer fills only for a source it is
    actually citing — compliance R5 polices stamping) or the line
    attributes in-line ("according to ..."). A claim is HEDGED
    when the line itself softens it (roughly / reportedly /
    estimates suggest ...). Unsourced + unhedged = invented
    until proven otherwise."""
    vo = str((scene or {}).get("vo") or "")
    low = " " + vo.lower() + " "
    sourced = bool(str((scene or {}).get("source") or "").strip()) \
        or "according to" in low
    hedged = any(h in low for h in _HEDGES)
    claims = []
    import compliance as _comp
    # A number reads as a STATISTIC claim when it carries a
    # statistic's shape: a % / x / ratio unit, or a magnitude
    # (>= 10 — quantities, counts, years, dates). A bare small
    # number word ("one plain fact", "the first thing") is
    # narrative, not a claim — flagging it would gut honest
    # scripts sentence by sentence.
    nums = [(v, u) for v, u in _comp.spoken_numbers(vo)
            if u in ("%", "x", "ratio") or v >= 10]
    if nums:
        claims.append({"kind": "stat",
                       "text": ", ".join(
                           f"{v:g}{u}" for v, u in nums[:3]),
                       "sourced": sourced, "hedged": hedged})
    for pat in _EVENT_PATTERNS:
        m = pat.search(vo)
        if m:
            claims.append({"kind": "event", "text": m.group(0)[:40],
                           "sourced": sourced, "hedged": hedged})
            break
    return claims


def audit_claims(scenes):
    """FG-FACT checks: one FAIL per scene whose claim is neither
    sourced nor hedged."""
    checks = []
    for i, sc in enumerate(scenes or []):
        for c in scene_claims(sc):
            if not c["sourced"] and not c["hedged"]:
                checks.append({
                    "rule": "FG-FACT", "status": "FAIL",
                    "detail": (f"{c['kind']} claim '{c['text']}' has "
                               f"no source and is not hedged — cite "
                               f"a real source, hedge it, or cut it"),
                    "scene": i + 1})
    return checks


def _sentences(vo):
    parts = re.split(r"(?<=[.!?])\s+", str(vo or "").strip())
    return [p for p in parts if p.strip()]


def strip_claim_sentences(vo):
    """Remove the sentences of `vo` that carry an unsourced,
    unhedged claim. Returns (new_vo, removed_sentences). The
    deterministic half of the fact gate: what the rewrite round
    could not fix honestly does not ship."""
    kept, removed = [], []
    probe = {"source": ""}
    for sent in _sentences(vo):
        probe["vo"] = sent
        bad = any(not c["sourced"] and not c["hedged"]
                  for c in scene_claims(probe))
        (removed if bad else kept).append(sent)
    return " ".join(kept).strip(), removed


def fact_gate(scenes, chat=None, min_scenes=4):
    """Run the fact gate over a writer's scenes BEFORE directing.

    Round 1 (only when FAILs exist and a chat is injected): the
    offending scenes go back to the writer — cite a real source,
    hedge, or cut. Round 2 (deterministic): any claim still
    unsourced + unhedged is removed sentence-by-sentence; a
    scene left with nothing honest is dropped (never below
    `min_scenes` scenes — below that the FAIL is left standing
    in the returned checks instead of gutting the chapter).

    Returns {"scenes": [...], "log": {...}, "checks": [...]} —
    checks is the POST-gate audit (what still fails, honestly)."""
    scenes = [dict(s) for s in scenes or []]
    log = {"claims": sum(len(scene_claims(s)) for s in scenes),
           "rewrite_round": False, "removed": [], "dropped_scenes": [],
           "waived_below_min": []}
    fails = [c for c in audit_claims(scenes) if c["status"] == "FAIL"]
    if fails and chat is not None:
        bad = sorted({c["scene"] for c in fails if c.get("scene")})
        lines = []
        for n in bad:
            sc = scenes[n - 1]
            claims = "; ".join(
                f"{c['kind']} '{c['text']}'" for c in scene_claims(sc)
                if not c["sourced"] and not c["hedged"])
            lines.append(f"Scene {n}: \"{sc.get('vo', '')}\" "
                         f"[unsourced: {claims}]")
        prompt = (
            "You wrote documentary narration with claims you did "
            "not source. Rewrite ONLY these scenes. For every "
            "statistic or event claim: either name a REAL source "
            "you actually know in the source field, or hedge the "
            "line (roughly / reportedly / estimates suggest), or "
            "remove the claim. NEVER invent a source, a movement, "
            "an event or a number. Return strict JSON only: "
            "{\"scenes\": [{\"scene\": <number>, \"vo\": \"...\", "
            "\"source\": \"...\"}]}\n" + "\n".join(lines))
        try:
            raw = chat([{"role": "system",
                         "content": "You output strict JSON only."},
                        {"role": "user", "content": prompt}])
            data = __import__("json").loads(
                re.search(r"\{[\s\S]*\}", raw).group(0))
            for item in data.get("scenes") or []:
                try:
                    n = int(item.get("scene") or 0)
                except (TypeError, ValueError):
                    continue
                if 1 <= n <= len(scenes) and str(item.get("vo") or "").strip():
                    scenes[n - 1]["vo"] = re.sub(
                        r"[#*_`]", "", str(item["vo"])).strip()
                    scenes[n - 1]["source"] = str(
                        item.get("source") or "")[:40]
                    # a rewritten line may no longer speak the
                    # scene's number — the value must not outlive it
                    import compliance as _comp
                    if scenes[n - 1].get("value") and not _comp.spoken_numbers(
                            scenes[n - 1]["vo"]):
                        scenes[n - 1]["value"] = ""
            log["rewrite_round"] = True
        except Exception as e:
            log["rewrite_error"] = str(e)[:120]
    # deterministic removal for whatever still fails
    fails = [c for c in audit_claims(scenes) if c["status"] == "FAIL"]
    drop = set()
    for c in fails:
        i = (c.get("scene") or 0) - 1
        if not (0 <= i < len(scenes)) or i in drop:
            continue
        sc = scenes[i]
        new_vo, removed = strip_claim_sentences(sc.get("vo", ""))
        if not removed:
            continue
        if len(new_vo.split()) >= 4:
            sc["vo"] = new_vo
            import compliance as _comp
            if sc.get("value") and not _comp.spoken_numbers(new_vo):
                sc["value"] = ""
            log["removed"] += [
                {"scene": i + 1, "text": r[:80]} for r in removed]
        elif len(scenes) - len(drop) > min_scenes:
            drop.add(i)
            log["dropped_scenes"].append(
                {"scene": i + 1, "vo": str(sc.get("vo", ""))[:80]})
            log["removed"] += [
                {"scene": i + 1, "text": r[:80]} for r in removed]
        else:
            log["waived_below_min"].append(i + 1)
    if drop:
        scenes = [s for i, s in enumerate(scenes) if i not in drop]
    return {"scenes": scenes, "log": log,
            "checks": audit_claims(scenes)}


def audit_teases(chapter_texts, chapter_count, end_question="",
                 last_scene=None):
    """FG-TEASE: a film may only tease content that exists in its
    own plan. chapter_texts = [(chapter_no, text), ...] over the
    WHOLE film. FAILs: a reference to a chapter beyond the plan;
    a 'next chapter / next part' promise inside the FINAL
    chapter (there is none — the Male Gaze film ended on a giant
    '4' teasing a Chapter 4 that was never made); a final scene
    whose number visual counts one past the last chapter."""
    checks = []
    total = int(chapter_count or 0)
    if not total:
        return checks
    for chno, text in chapter_texts or []:
        for m in re.finditer(r"chapter\s+(\d+)", str(text or ""), re.I):
            if int(m.group(1)) > total:
                checks.append({
                    "rule": "FG-TEASE", "status": "FAIL",
                    "detail": (f"chapter {chno} teases 'chapter "
                               f"{m.group(1)}' but the film has "
                               f"{total} chapter(s)"),
                    "scene": None})
        if chno >= total and re.search(
                r"\b(next\s+chapter|next\s+part|part\s+two|"
                r"in\s+the\s+next\s+episode)\b", str(text or ""), re.I):
            checks.append({
                "rule": "FG-TEASE", "status": "FAIL",
                "detail": ("the final chapter promises a next "
                           "chapter/part that does not exist in "
                           "this film's plan"),
                "scene": None})
    if end_question and re.search(r"chapter\s+(\d+)",
                                  str(end_question), re.I):
        m = re.search(r"chapter\s+(\d+)", str(end_question), re.I)
        if int(m.group(1)) > total:
            checks.append({
                "rule": "FG-TEASE", "status": "FAIL",
                "detail": (f"the end card teases 'chapter "
                           f"{m.group(1)}' but the film has "
                           f"{total} chapter(s)"),
                "scene": None})
    if last_scene is not None:
        val = str(last_scene.get("value") or "").strip()
        vis = str(last_scene.get("visual") or "")
        if val == str(total + 1) and vis in (
                "counter", "four", "dot_grid", "donut", "gauge",
                "bar", "bar_compare", "graph"):
            checks.append({
                "rule": "FG-TEASE", "status": "FAIL",
                "detail": (f"the film ends on the number "
                           f"{total + 1} — a tease for a chapter "
                           f"{total + 1} that does not exist"),
                "scene": None})
    return checks


# ------------------------------------------------------------------
# Gate 4 — director variety caps
# ------------------------------------------------------------------

VARIETY_CAP = 0.25


def visual_histogram(items):
    """{visual type: beat count} over director records
    (visual_concept) or engine scenes (effective visual)."""
    keys = []
    for it in items or []:
        if isinstance(it, dict) and it.get("visual_concept"):
            keys.append(str(it["visual_concept"]))
        elif isinstance(it, dict):
            import compliance as _comp
            keys.append(_comp.effective_visual(it))
        else:
            keys.append(str(it))
    return dict(Counter(keys))


def audit_variety(items, cap=VARIETY_CAP, min_beats=8):
    """VHIST: per chapter, no single visual type may exceed the
    cap share of beats. Returns FAIL checks (the histogram rides
    in the detail). Chapters shorter than min_beats are exempt —
    the cap polices flattening, not small samples."""
    items = list(items or [])
    n = len(items)
    if n < min_beats:
        return []
    hist = visual_histogram(items)
    checks = []
    for kind, count in sorted(hist.items(), key=lambda kv: -kv[1]):
        if count >= 3 and count / n > cap:
            checks.append({
                "rule": "VHIST", "status": "FAIL",
                "detail": (f"visual type '{kind}' fills {count}/{n} "
                           f"beats ({count / n:.0%}) — cap "
                           f"{cap:.0%}; the plan was flattened onto "
                           f"one template. Histogram: "
                           + ", ".join(f"{k}×{v}" for k, v in
                                       sorted(hist.items(),
                                              key=lambda kv: -kv[1]))),
                "scene": None})
    return checks


# ------------------------------------------------------------------
# Gate 5 — length honesty (top-up novelty)
# ------------------------------------------------------------------

def _grams(text, n=4):
    words = re.findall(r"[a-z][a-z'-]*", str(text or "").lower())
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def novelty_report(new_texts, existing_texts):
    """How much of the proposed NEW material already exists in
    the chapter it would extend (word 4-gram overlap). A top-up
    is novel when every new scene is mostly new AND the mean
    overlap stays low — restatement padding fails both."""
    existing = set()
    for t in existing_texts or []:
        existing |= _grams(t)
    ratios = []
    for t in new_texts or []:
        g = _grams(t)
        ratios.append((len(g & existing) / len(g)) if g else 0.0)
    mean = (sum(ratios) / len(ratios)) if ratios else 0.0
    worst = max(ratios) if ratios else 0.0
    novel = bool(ratios) and worst <= 0.6 and mean <= 0.4
    return {"novel": novel, "mean_overlap": round(mean, 3),
            "worst_overlap": round(worst, 3),
            "offending": [i + 1 for i, r in enumerate(ratios)
                          if r > 0.6]}


# ------------------------------------------------------------------
# Gate 3 — the boring-critical failure classes
# ------------------------------------------------------------------

# Compliance / media rules whose FAIL must trigger a real fix
# round (re-plan + re-render), never a log line. These are the
# classes that made the v85/v87/v88/Male-Gaze films boring:
# no footage, one-template flattening, dead air, invented facts.
BORING_CRITICAL_RULES = {
    "R10", "PART2-RATIO",          # footage share (legacy rules)
    "FG-SHARE",                    # footage share (v100 gate)
    "FG-FACT", "FG-TEASE",         # fact gate
    "VHIST",                       # variety histogram cap
    "R1", "A5", "PART3-CHANGE", "PART3-TYPES", "PART3-TRANS",
    "PART4-CHECK",                 # variety / rotation budgets
    "FIDELITY",                    # visual must picture THIS line
    "R11",                         # chapter-level dead air / loudness
    "MQ-SILENCE", "MQ-LRA",        # assembled-level dead air / flat mix
}


def boring_critical_fails(checks):
    """The FAIL checks (of a compliance / media report) that sit
    in a boring-critical class."""
    return [c for c in checks or []
            if c.get("status") == "FAIL"
            and c.get("rule") in BORING_CRITICAL_RULES]


if __name__ == "__main__":
    # deterministic self-checks (the full harness is v100test.py)
    assert not query_is_searchable("Psycho film still female")
    assert not query_is_searchable("Laura Mulvey gaze theory")
    assert query_is_searchable("woman looking in mirror")
    assert query_is_searchable("doctor holding liver scan")
    sc = [{"vo": "Alcohol causes 70 percent of all road deaths.",
           "source": ""}]
    assert audit_claims(sc)[0]["rule"] == "FG-FACT"
    sc[0]["source"] = "WHO 2023"
    assert not audit_claims(sc)
    sc[0]["source"] = ""
    sc[0]["vo"] = "Roughly 70 percent of road deaths involve alcohol."
    assert not audit_claims(sc)
    recs = ([{"visual_concept": "counter"}] * 6
            + [{"visual_concept": "timeline"}] * 2
            + [{"visual_concept": "quote_typewriter"}] * 2)
    assert audit_variety(recs)[0]["rule"] == "VHIST"
    rep = novelty_report(
        ["Alcohol causes 70 percent of all road deaths today"],
        ["Alcohol causes 70 percent of all road deaths"])
    assert not rep["novel"], rep
    print("anti_boring self-check OK")
