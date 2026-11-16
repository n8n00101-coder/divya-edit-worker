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


# RENDERER PIVOT (Phase 2a): the first v89-brain film's queries
# passed the v100 gate and still starved the pool — they were
# VOICE-LINE FRAGMENTS, shards of the narration sentence ("ever
# looked wondered who's", "nest hidden cracks sipping"), not
# subjects. A stock library tags NOUN PHRASES ("honeybee on
# rooftop hive"); a clause fragment matches nothing. Fragment
# detection is therefore part of searchability now.
_FRAGMENT_HEADS = {
    "who", "what", "when", "where", "why", "how", "which", "whose",
    "and", "but", "so", "if", "as", "while", "because", "then",
    "ever", "just", "also", "even", "still",
}
_FRAGMENT_TAILS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "and", "or",
    "for", "with", "from", "by", "is", "are", "was", "were", "be",
    "been", "being", "has", "have", "had", "do", "does", "did",
    "can", "could", "will", "would", "should", "may", "might",
    "who", "what", "ever", "just", "very", "so", "too", "up",
}
_ING_NOUNS = {"morning", "evening", "building", "buildings",
              "wedding", "lightning", "painting", "paintings",
              "drawing", "drawings", "ceiling", "spring"}
_CONTRACTION_RX = re.compile(r"\b\w+'(s|re|ve|ll|d|t)\b", re.I)


def query_is_fragment(q):
    """True when a query is a clause FRAGMENT rather than a
    subject noun phrase: it carries a contraction shard ("who's"),
    opens or trails on a function word, is mostly function words,
    or trails off on a bare participle ("...sipping")."""
    s = str(q or "").strip()
    if not s:
        return True
    if "?" in s or _CONTRACTION_RX.search(s):
        return True
    words = [w.strip(".,;:!?\"'").lower() for w in s.split()
             if w.strip(".,;:!?\"'")]
    if not words:
        return True
    if words[0] in _FRAGMENT_HEADS or words[-1] in _FRAGMENT_TAILS:
        return True
    if words[-1].endswith("ing") and words[-1] not in _ING_NOUNS:
        return True
    fn = sum(1 for w in words
             if w in _STOP or w in _FRAGMENT_TAILS
             or w in _FRAGMENT_HEADS)
    return len(words) > 0 and fn / len(words) > 0.5


def query_is_searchable(q):
    """True when a footage query names a concrete, stock-searchable
    subject: at least 2 content words, no copyrighted-artefact
    phrasing, not dominated by capitalised name/title words
    (a person's name, a film title — stock libraries tag visible
    subjects, not names) — and, since the renderer pivot, not a
    voice-line FRAGMENT (see query_is_fragment)."""
    s = str(q or "").strip()
    if len(s) < 3:
        return False
    low = s.lower()
    if any(p in low for p in _NON_SEARCHABLE):
        return False
    if query_is_fragment(s):
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


def _nounish(word):
    """A word that can anchor a stock query: a plural or a
    noun-shaped ending (the deterministic stand-in for POS
    tagging — the anchor of a subject phrase)."""
    w = str(word or "").lower()
    if "'" in w:
        return False
    return len(w) > 2 and (w.endswith("s") and not w.endswith(("ss", "us", "is"))
                           or w.endswith(("tion", "ness", "ment", "ity")))


def derive_subject_query(line, label="", topic=""):
    """RENDERER PIVOT (Phase 2a): rewrite a fragment into a
    SUBJECT query. Anchors on the topic's salient noun (its last
    content word — "bees" in "The Hidden Life of Urban Bees"),
    adds the line's noun-ish words and the scene label's content
    words, and validates the result against the same quality
    gate — a derivation that still reads as a fragment is not
    returned (the caller then asks the re-plan hook instead)."""
    anchor = ""
    tc = content_words(topic)
    if tc:
        anchor = tc[-1]
    words = []
    for w in content_words(label) + content_words(line):
        if _nounish(w) and w not in words:
            words.append(w)
    out = []
    if anchor and anchor not in words[:3]:
        out.append(anchor)
    out += [w for w in words if w not in out][:3]
    if len(out) < 2:
        out = content_words(label)[:3] or out
    q = " ".join(out[:4]).strip()
    if len(out) >= 2 and query_is_searchable(q):
        return q
    return ""


def searchable_queries(queries, line, label="", topic=""):
    """Filter a scene's footage queries down to stock-searchable
    ones (fragments now drop too — Phase 2a); when none survive,
    derive a SUBJECT query (topic-anchored), falling back to the
    v100 line derivation. Returns (kept, dropped) — the drop is
    always reported, never silent."""
    kept, dropped = [], []
    for q in queries or []:
        (kept if query_is_searchable(q) else dropped).append(str(q))
    if not kept:
        d = derive_subject_query(line, label, topic) \
            or derive_query(line, label)
        if d and query_is_searchable(d):
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


def _title_key(s):
    return re.sub(r"[^a-z0-9 ]+", "", str(s or "").lower()).strip()


def resolve_source(scene, research):
    """RENDERER PIVOT (Phase 4 — FACT GATE v2): the research-record
    entry backing this scene, or None. The scene points at the
    record via `source_ref` (or a `source` string that IS a record
    title); a free-text invention ("Nature 2022") matches no
    retrieved entry and resolves to nothing."""
    if not research:
        return None
    ref = _title_key((scene or {}).get("source_ref")
                     or (scene or {}).get("source"))
    if not ref:
        return None
    for e in research:
        t = _title_key(e.get("title"))
        if not t:
            continue
        if t == ref:
            return e
        # containment only for substantial titles — a 3-letter
        # title ("Bee") must not "match" inside a longer word
        if min(len(t), len(ref)) >= 4 and (t in ref or ref in t):
            return e
    return None


def resolved_source_title(scene, research):
    """The ONLY source title a stamp may print for this scene:
    the title of the retrieved record entry backing it ('' when
    nothing backs it — the stamp then prints nothing)."""
    e = resolve_source(scene, research)
    return str(e.get("title") or "") if e else ""


def _num_in_snippet(v, u, snippet):
    """Does the retrieved text actually carry this number? Accepts
    the plain form, a .0 form, thousands separators, and the
    spelled-out unit ('30 percent')."""
    text = str(snippet or "").replace(",", "")
    forms = {f"{v:g}", f"{v:.1f}".rstrip("0").rstrip("."),
             f"{int(v)}" if float(v) == int(v) else f"{v:g}"}
    for f in forms:
        if not f:
            continue
        if u == "%":
            if re.search(rf"(?<![\d.]){re.escape(f)}\s*(%|percent|per cent)",
                         text):
                return True
        elif re.search(rf"(?<![\d.]){re.escape(f)}(?![\d.])", text):
            return True
    return False


# NEXT-ROUND (Fix 4 — FACT GATE number sanity): digit containment
# alone let "every EV mile cuts CO2 by about 2.5 kg" resolve
# against a source whose 2.5 was TONNES OVER A LIFETIME — the
# digits matched, the claim was ~10x too high. A number now only
# supports a claim when an occurrence of that value in the
# retrieved text agrees on UNIT, SCALE (thousand/million/...) and
# BASIS (per-mile vs per-year vs lifetime vs total). A claim that
# states a basis its source occurrence does not carry is
# unresolved — it faces the same hedge-or-cut mechanics as any
# unsourced claim.
_UNIT_RES = (
    (r"percent|per\s*cent|%", "%"),
    (r"kilograms?|kg\b", "kg"),
    (r"tonnes?|tons?\b", "tonne"),
    (r"grams?\b", "g"),
    (r"miles?\b", "mile"),
    (r"kilometres?|kilometers?|km\b", "km"),
    (r"litres?|liters?\b", "l"),
    (r"kwh\b", "kwh"),
    (r"mwh\b", "mwh"),
    (r"hours?\b", "hour"),
    (r"minutes?\b", "minute"),
    (r"days?\b", "day"),
    (r"years?\b", "year"),
    (r"dollars?|usd\b", "usd"),
)
_MULT_RES = ((r"trillion", 1e12), (r"billion", 1e9),
             (r"million", 1e6), (r"thousand", 1e3))
_BASIS_NOUNS = ("mile", "kilometre", "kilometer", "km", "year",
                "day", "hour", "month", "week", "vehicle", "car",
                "person", "capita")


def _ctx_unit(tail):
    for pat, canon in _UNIT_RES:
        if re.search(r"(?<![a-z])" + pat, tail):
            return canon
    return ""


def _ctx_basis(window):
    w = " " + str(window or "").lower() + " "
    if re.search(r"life\s?time|lifespan|life\s*cycle", w):
        return "lifetime"
    if re.search(r"\bin\s+total\b|\btotal\s+of\b|\baltogether\b", w):
        return "total"
    if re.search(r"\bannually\b|\byearly\b", w):
        return "per-year"
    if re.search(r"\bdaily\b", w):
        return "per-day"
    nouns = "|".join(_BASIS_NOUNS)
    m = re.search(rf"\b(?:per|every|each)\s+({nouns})\b", w)
    if m:
        return "per-" + (_ctx_unit(m.group(1)) or m.group(1))
    m = re.search(rf"\ba\s+({nouns})\b", w)
    if m:
        return "per-" + (_ctx_unit(m.group(1)) or m.group(1))
    return ""


def _number_contexts(text, value):
    """Every occurrence of `value` in `text`, each with the unit,
    scale multiplier and basis its local context states:
    [{unit, mult, basis}]. Empty when the value never appears in
    digit form (word-numbers fall back to legacy containment)."""
    text = str(text or "").replace(",", "")
    forms = {f"{value:g}",
             f"{value:.1f}".rstrip("0").rstrip("."),
             f"{int(value)}" if float(value) == int(value)
             else f"{value:g}"}
    out = []
    for f in sorted((x for x in forms if x), key=len, reverse=True):
        for m in re.finditer(
                rf"(?<![\d.]){re.escape(f)}(?!\d)(?!\.\d)", text):
            tail = text[m.end():m.end() + 48]
            window = text[max(0, m.start() - 48):m.end() + 64]
            mult = 1.0
            for pat, mv in _MULT_RES:
                if re.search(rf"^\s*{pat}\b", tail) or \
                        re.search(rf"\b{pat}\b", tail[:24]):
                    mult = mv
                    break
            out.append({"unit": _ctx_unit(tail[:40]),
                        "mult": mult,
                        "basis": _ctx_basis(window)})
        if out:
            break
    return out


def _num_supported(v, u, vo, snippet):
    """NEXT-ROUND Fix 4: does the retrieved text support THIS
    claim's number — same value, compatible unit and scale, and
    the same basis when the claim states one? Falls back to the
    legacy containment check only when the claim's number never
    appears in digit form in the line (word-numbers), where no
    context can be parsed."""
    claim_ctxs = _number_contexts(vo, v)
    if not claim_ctxs:
        return _num_in_snippet(v, u, snippet)
    src_ctxs = _number_contexts(snippet, v)
    if not src_ctxs:
        return False
    for c in claim_ctxs:
        cu = c["unit"] or ("%" if u == "%" else "")
        for s in src_ctxs:
            su = s["unit"] or ("%" if u == "%" else "")
            if cu and su != cu:
                continue            # 2.5 kg is not 2.5 tonnes
            if c["mult"] != s["mult"]:
                continue            # 2.5 is not 2.5 million
            if c["basis"] and s["basis"] != c["basis"]:
                continue            # per-mile is not per-lifetime
            return True
    return False


def scene_claims(scene, research=None):
    """The factual claims one scene makes, each judged:
    {kind: 'stat'|'event', text, sourced, hedged}.

    v1 sourcing: the scene carries its own citation (the `source`
    field) or the line attributes in-line ("according to ...").
    FACT GATE v2 (research given): a free-text source NO LONGER
    counts — the claim is sourced only when resolve_source finds
    the retrieved record entry backing the scene AND, for a stat,
    the entry's retrieved text actually carries the claim's
    number. A claim is HEDGED when the line itself softens it
    (roughly / reportedly / estimates suggest ...). Unsourced +
    unhedged = invented until proven otherwise."""
    vo = str((scene or {}).get("vo") or "")
    low = " " + vo.lower() + " "
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
    # NEXT-ROUND Fix 4: a SMALL number carrying a physical unit is
    # a statistic too ("cuts CO2 by about 2.5 kg" — the second
    # film's wrong number slipped the gate partly because 2.5 < 10
    # read as narrative). A bare small number with no unit stays
    # narrative, exactly as before.
    _seen_n = {v for v, _u in nums}
    for v, u in _comp.spoken_numbers(vo):
        if v not in _seen_n and not u:
            if any(c["unit"] for c in _number_contexts(vo, v)):
                nums.append((v, u))
                _seen_n.add(v)
    if research is None:
        sourced = bool(str((scene or {}).get("source") or "").strip()) \
            or "according to" in low
        stat_sourced = sourced
    else:
        entry = resolve_source(scene, research)
        # NEXT-ROUND Fix 4: containment is now basis-aware — the
        # number must appear in the retrieved text with a
        # compatible unit/scale and the claim's own basis.
        stat_sourced = bool(entry) and bool(nums) and all(
            _num_supported(v, u, vo, entry.get("snippet"))
            for v, u in nums)
        sourced = bool(entry)
    if nums:
        claims.append({"kind": "stat",
                       "text": ", ".join(
                           f"{v:g}{u}" for v, u in nums[:3]),
                       "sourced": stat_sourced, "hedged": hedged})
    for pat in _EVENT_PATTERNS:
        m = pat.search(vo)
        if m:
            claims.append({"kind": "event", "text": m.group(0)[:40],
                           "sourced": sourced, "hedged": hedged})
            break
    return claims


def audit_claims(scenes, research=None):
    """FG-FACT checks: one FAIL per scene whose claim is neither
    sourced nor hedged (v2: sourced = resolved against the
    research record when one is given)."""
    checks = []
    for i, sc in enumerate(scenes or []):
        for c in scene_claims(sc, research):
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


def strip_claim_sentences(vo, research=None, scene=None):
    """Remove the sentences of `vo` that carry an unsourced,
    unhedged claim. Returns (new_vo, removed_sentences). The
    deterministic half of the fact gate: what the rewrite round
    could not fix honestly does not ship. Under v2 the probe
    carries the scene's own source pointers, judged against the
    research record."""
    kept, removed = [], []
    probe = {"source": (scene or {}).get("source", ""),
             "source_ref": (scene or {}).get("source_ref", "")}
    for sent in _sentences(vo):
        probe["vo"] = sent
        bad = any(not c["sourced"] and not c["hedged"]
                  for c in scene_claims(probe, research))
        (removed if bad else kept).append(sent)
    return " ".join(kept).strip(), removed


def fact_gate(scenes, chat=None, min_scenes=4, research=None):
    """Run the fact gate over a writer's scenes BEFORE directing.

    Round 1 (only when FAILs exist and a chat is injected): the
    offending scenes go back to the writer — cite a real source,
    hedge, or cut. Round 2 (deterministic): any claim still
    unsourced + unhedged is removed sentence-by-sentence; a
    scene left with nothing honest is dropped (never below
    `min_scenes` scenes — below that the FAIL is left standing
    in the returned checks instead of gutting the chapter).

    FACT GATE v2 (research given — a list of RETRIEVED sources
    from research.build_research_record): a claim counts as
    sourced ONLY when it resolves against the record (see
    scene_claims); the rewrite round may cite ONLY record titles
    (in "source_ref") — a citation the writer invents is
    discarded by validation, and the claim then faces the same
    hedge-or-cut mechanics. An EMPTY record is a valid, strict
    input: nothing resolves, everything must hedge or cut.

    Returns {"scenes": [...], "log": {...}, "checks": [...]} —
    checks is the POST-gate audit (what still fails, honestly)."""
    scenes = [dict(s) for s in scenes or []]
    log = {"claims": sum(len(scene_claims(s, research)) for s in scenes),
           "rewrite_round": False, "removed": [], "dropped_scenes": [],
           "waived_below_min": []}
    if research is not None:
        log["research"] = {"entries": len(research)}
    fails = [c for c in audit_claims(scenes, research)
             if c["status"] == "FAIL"]
    if fails and chat is not None:
        bad = sorted({c["scene"] for c in fails if c.get("scene")})
        lines = []
        for n in bad:
            sc = scenes[n - 1]
            claims = "; ".join(
                f"{c['kind']} '{c['text']}'"
                for c in scene_claims(sc, research)
                if not c["sourced"] and not c["hedged"])
            lines.append(f"Scene {n}: \"{sc.get('vo', '')}\" "
                         f"[unsourced: {claims}]")
        if research is not None:
            rec_lines = "\n".join(
                f"- {e.get('title', '')} ({e.get('url', '')})"
                for e in research) or "(no sources were retrieved)"
            prompt = (
                "You wrote documentary narration with claims no "
                "retrieved source backs. Rewrite ONLY these scenes. "
                "For every statistic or event claim: either cite "
                "one of the RETRIEVED sources below — copy its "
                "title EXACTLY into source_ref, and only when that "
                "source's subject actually covers the claim — or "
                "hedge the line (roughly / reportedly / estimates "
                "suggest), or remove the claim. A source you name "
                "that is not in this list is discarded and the "
                "claim is cut. NEVER invent a source, a movement, "
                "an event or a number. RETRIEVED SOURCES:\n"
                + rec_lines
                + "\nReturn strict JSON only: {\"scenes\": "
                "[{\"scene\": <number>, \"vo\": \"...\", "
                "\"source_ref\": \"...\"}]}\n" + "\n".join(lines))
        else:
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
                    if research is not None:
                        # v2: the citation is validated against the
                        # record — an invented one is discarded, and
                        # the display source becomes the RETRIEVED
                        # title, never the writer's string.
                        probe = {"source_ref": str(
                            item.get("source_ref")
                            or item.get("source") or "")}
                        entry = resolve_source(probe, research)
                        if entry:
                            scenes[n - 1]["source_ref"] = entry["title"]
                            scenes[n - 1]["source"] = entry["title"]
                            # the retrieved text itself — the only
                            # words a document visual may show
                            scenes[n - 1]["source_text"] = \
                                str(entry.get("snippet") or "")[:400]
                        else:
                            scenes[n - 1].pop("source_ref", None)
                            scenes[n - 1]["source"] = ""
                    else:
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
    fails = [c for c in audit_claims(scenes, research)
             if c["status"] == "FAIL"]
    drop = set()
    for c in fails:
        i = (c.get("scene") or 0) - 1
        if not (0 <= i < len(scenes)) or i in drop:
            continue
        sc = scenes[i]
        new_vo, removed = strip_claim_sentences(
            sc.get("vo", ""), research, sc)
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
    if research is not None:
        log["research"]["resolved_claims"] = sum(
            1 for s in scenes for c in scene_claims(s, research)
            if c["sourced"])
    return {"scenes": scenes, "log": log,
            "checks": audit_claims(scenes, research)}


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


# NEXT-ROUND (Fix 1 — top-up restatement, semantic layer):
# novelty_report's word 4-grams only catch VERBATIM repetition.
# The second film's top-up ("The Rise of Electric Vehicles",
# 59s -> 102s) was a compressed PARAPHRASE of the same chapter —
# it scored 0.0 on the 4-gram gate and shipped, so the viewer
# heard one 59-second argument twice. restatement_report judges
# the top-up the way a viewer hears it: stemmed content words,
# synonym/concept normalisation (declined == cheaper == ~down;
# tax breaks == incentives), and fact novelty (a number or a
# named entity the chapter does not already carry). A top-up
# that adds no new claim/fact/angle is a restatement, however
# fresh its wording.
_STOPWORDS = frozenset("""
the a an and or but if then else of at by for with about against
between into through during before after above below to from up
down in out on off over under again further once here there when
where why how all any both each few more most other some such no
nor not only own same so than too very can will just is are was
were be been being have has had having do does did doing would
should could ought i you he she it we they them his her its our
their this that these those am an as are us now still yet also
one two first second get gets got make makes made take takes
""".split())

_CONCEPTS = {}


def _concept(*words, name):
    for w in words:
        _CONCEPTS[w] = "~" + name


_concept("declin", "drop", "fell", "fall", "decreas", "reduc",
         "cheaper", "lower", "plunge", "slump", name="down")
_concept("cost", "price", name="cost")
_concept("car", "vehicle", "automobile", name="vehicle")
_concept("tax", "incentive", "subsidy", "rebate", "break",
         name="incentive")
_concept("charg", "charge", "charger", name="charging")
_concept("lag", "barrier", "obstacle", "bottleneck",
         name="obstacle")
_concept("surge", "risen", "rise", "rose", "growth", "grow",
         "momentum", "increas", "climb", name="growth")
_concept("co2", "carbon", name="emissions")
del _concept


def _stem(w):
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    if len(w) > 4 and w.endswith("ly"):
        w = w[:-2]
    return w


def _content_words(text):
    out = set()
    for w in re.findall(r"[a-z][a-z'-]*", str(text or "").lower()):
        w = w.strip("'-")
        if len(w) < 3 or w in _STOPWORDS:
            continue
        s = _stem(w)
        out.add(_CONCEPTS.get(s, s))
    return out


def _entities(text):
    """Named entities a line carries: capitalised words away from
    a sentence start, plus acronyms. Crude by design — it only
    has to notice when a top-up names something NEW."""
    out = set()
    for sent in _sentences(text):
        toks = re.findall(r"[A-Za-z][A-Za-z'-]*", sent)
        for i, t in enumerate(toks):
            if i == 0:
                continue
            if len(t) >= 3 and t[0].isupper() and not t.isupper():
                out.add(t.lower())
            elif len(t) >= 2 and t.isupper():
                out.add(t.lower())
    return out


def _numbers_of(text):
    try:
        import compliance as _comp
        vals = {round(float(v), 4)
                for v, _u in _comp.spoken_numbers(text)}
    except Exception:
        vals = {float(x.replace(",", ""))
                for x in re.findall(r"\d[\d,]*(?:\.\d+)?",
                                     str(text or ""))}
    # "zero emission zones" speaks the WORD zero as an adjective,
    # not a statistic — a lone 0 is never a top-up's new fact.
    vals.discard(0.0)
    return vals


def restatement_report(new_texts, existing_texts):
    """Is this proposed top-up a RESTATEMENT of the chapter it
    extends? A scene counts as NEW material when it carries a
    number or a named entity the chapter lacks, or when most of
    its content is new to the chapter. The top-up is a
    restatement when most scenes individually restate, or when
    NOTHING in it is a new fact/entity and its mean content
    containment in the chapter stays high, or when its mean
    containment is overwhelming on its own."""
    existing_words = set()
    for t in existing_texts or []:
        existing_words |= _content_words(t)
    existing_nums = set()
    existing_ents = set()
    for t in existing_texts or []:
        existing_nums |= _numbers_of(t)
        existing_ents |= _entities(t)
    containments, restating, any_new_fact = [], [], False
    for i, t in enumerate(new_texts or []):
        words = _content_words(t)
        c = (len(words & existing_words) / len(words)) if words \
            else 0.0
        containments.append(round(c, 3))
        new_fact = bool((_numbers_of(t) - existing_nums)
                        or (_entities(t) - existing_ents))
        any_new_fact = any_new_fact or new_fact
        if not new_fact and c >= 0.5:
            restating.append(i + 1)
    n = len(containments)
    mean = (sum(containments) / n) if n else 0.0
    restatement = bool(n) and (
        len(restating) >= 0.6 * n
        or (not any_new_fact and mean >= 0.35)
        or mean >= 0.6)
    return {"restatement": restatement,
            "mean_containment": round(mean, 3),
            "scene_containments": containments,
            "restating_scenes": restating,
            "new_fact": any_new_fact}


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
    "DEPICTION",                   # round 4: literal-illustration budget
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
