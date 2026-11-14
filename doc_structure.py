"""doc_structure.py — Julie v84 Stage 4 (P2): whole-documentary
story intelligence for the long pipeline.

The failure this fixes (Blind's 32 mistakes): every chapter rendered
as an independent short — its own hook, its own CTA, its own ending —
so the assembled "documentary" was shorts joined together.

This module is deterministic (no model calls):

- ARC_ROLES: the documentary arc (hook, central question, context,
  evidence, contradictions, emotional development, turning points,
  build-up, payoff, conclusion).
- assign_arc(): maps chapter positions to arc roles for any chapter
  count, so chapter planning knows WHERE in the story it is.
- arc_context_block(): the text block long_video passes into every
  chapter brief, carrying the whole-documentary structure + the
  chapter's own role, and the standing rule that only the final
  chapter may close the story.
- structure_lints(): measurable structural checks over the chapter
  plans — multiple endings, repeated hooks, repeated CTAs/end cards,
  repeated chapter introductions — returned as compliance-shaped
  check dicts (rule/status/detail/scene).
"""

ARC_ROLES = ["hook", "central_question", "context", "evidence",
             "contradictions", "emotional_development", "turning_points",
             "build_up", "payoff", "conclusion"]


def assign_arc(n_chapters):
    """Arc role per chapter index for n chapters. First chapter is
    always the hook, last is always the conclusion; the middle walks
    the arc in order without repeats where the count allows."""
    if n_chapters <= 0:
        return []
    if n_chapters == 1:
        return ["hook"]
    if n_chapters == 2:
        return ["hook", "conclusion"]
    middle = ARC_ROLES[1:-1]
    slots = n_chapters - 2
    roles = ["hook"]
    for i in range(slots):
        # sample the arc evenly so late roles (turning points,
        # build-up, payoff) are never skipped on mid-length docs
        j = round(i * (len(middle) - 1) / max(1, slots - 1)) if slots > 1 else 0
        roles.append(middle[j])
    roles.append("conclusion")
    return roles


def arc_context_block(outline, idx, roles=None):
    """The whole-documentary context for chapter idx's brief."""
    chapters = (outline or {}).get("chapters") or []
    roles = roles or assign_arc(len(chapters))
    role = roles[idx] if idx < len(roles) else "evidence"
    titles = "; ".join(f"{i + 1}. {c.get('title', '')}"
                       for i, c in enumerate(chapters))
    last = idx == len(chapters) - 1
    return (
        f"\nDOCUMENTARY STRUCTURE: this is chapter {idx + 1} of "
        f"{len(chapters)} in ONE documentary, '{(outline or {}).get('title', '')}'. "
        f"Chapters: {titles}. This chapter's story role: {role}. "
        f"The documentary arc is: hook -> central question -> context "
        f"-> evidence -> contradictions -> emotional development -> "
        f"turning points -> build-up -> payoff -> conclusion. "
        + ("This is the FINAL chapter: it alone delivers the payoff "
           "and the one proper ending."
           if last else
           "Do NOT open with a new hook and do NOT end this chapter "
           "with an ending, CTA or end card — continue the story and "
           "hand over to the next chapter."))


_END_MARKERS = ("stay tuned", "next episode", "subscribe", "the end",
                "conclusion", "in conclusion", "to conclude", "finally,")
_CTA_MARKERS = ("comment", "like and", "follow for", "share this")


def _scene_titles(scenes):
    return [str(s.get("title") or "") for s in scenes or []]


def structure_lints(chapter_scenes):
    """chapter_scenes: list (per chapter) of scene dict lists.
    Returns compliance-shaped checks. A check is PASS only when it
    actually inspected something; empty input -> UNVERIFIED."""
    checks = []
    n_ch = len(chapter_scenes or [])
    if not n_ch:
        return [{"rule": "ST-1", "status": "UNVERIFIED",
                 "detail": "no chapter plans supplied to structure lint",
                 "scene": None}]
    # --- multiple endings / CTAs in non-final chapters
    ending_hits, cta_hits = [], []
    for ci, scenes in enumerate(chapter_scenes):
        if ci == n_ch - 1:
            continue
        for si, s in enumerate(scenes or []):
            text = (str(s.get("title") or "") + " " +
                    str(s.get("vo") or "")).lower()
            vis = str(s.get("visual") or "")
            if vis == "stamp_cta" or any(m in text for m in _CTA_MARKERS):
                cta_hits.append((ci + 1, si + 1))
            if any(m in text for m in _END_MARKERS):
                ending_hits.append((ci + 1, si + 1))
    checks.append({
        "rule": "ST-1", "scene": None,
        "status": "FAIL" if ending_hits else "PASS",
        "detail": (f"ending-style text in non-final chapter(s): "
                   f"{ending_hits[:5]} — one documentary, one ending"
                   if ending_hits else
                   "no ending-style text outside the final chapter")})
    checks.append({
        "rule": "ST-1-CTA", "scene": None,
        "status": "FAIL" if cta_hits else "PASS",
        "detail": (f"CTA/end-card scenes in non-final chapter(s): "
                   f"{cta_hits[:5]} — the CTA belongs at the very end only"
                   if cta_hits else
                   "no CTA/end-card scenes outside the final chapter")})
    # --- repeated hooks: identical opening line/title in >1 chapter
    openings = []
    for scenes in chapter_scenes:
        if scenes:
            first = scenes[0]
            openings.append((str(first.get("title") or "") + "|" +
                             str(first.get("vo") or "")[:60]).strip("| ").lower())
    dup = sorted({o for o in openings if o and openings.count(o) > 1})
    checks.append({
        "rule": "ST-3", "scene": None,
        "status": "FAIL" if dup else "PASS",
        "detail": (f"repeated chapter opening(s): {dup[:3]}"
                   if dup else "chapter openings are distinct")})
    # --- one opening + one ending overall
    total_scenes = sum(len(s or []) for s in chapter_scenes)
    checks.append({
        "rule": "ST-2", "scene": None,
        "status": "PASS" if total_scenes >= 2 else "UNVERIFIED",
        "detail": f"{n_ch} chapter(s), {total_scenes} scene(s): one "
                  f"opening (chapter 1) + one ending (final chapter) "
                  f"structure {'present' if total_scenes >= 2 else 'unverifiable'}"})
    return checks


if __name__ == "__main__":
    print(assign_arc(7))
    bad = [[{"title": "Intro", "vo": "Welcome back, subscribe now"}],
           [{"title": "Intro", "vo": "Welcome back, subscribe now"}]]
    for c in structure_lints(bad):
        print(c["rule"], c["status"], "-", c["detail"][:70])
    print("doc_structure self-check OK")
