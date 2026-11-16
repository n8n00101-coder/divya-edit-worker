"""pack_slicer.py — per-stage slices of the v89 taste pack.

PROOF-FIX 1 (2026-11-16, from the new-brain proof audit): on long
videos EVERY LLM brain stage died with HTTP 413 on the free Groq
channel — each stage was handed the WHOLE 56K-char taste pack, and
the free channel's per-request limit cannot carry it. The stages
silently fell back to the pre-v89 deterministic director, so the
new brain never directed a long film while the job reported
business as usual.

The fix is a diet, not a deletion: the pack is split into its
`## ` sections once, and each stage receives only the sections
that govern ITS decisions, sized under a hard char budget:

  story    (Story Analyst)   — story shape, structure, hooks
  visual   (Visual Director) — asset priority, composition, evidence
  editing  (Editing Director)— beat grammar, sound, rhythm, restraint
  qc       (Taste QC re-plan)— frame rules, honesty, finish

Three sections are GLOBAL — they ride in every slice because they
are small and decisive everywhere: the one law, FORMAT LITERACY
(the P0 format rules; a stage that forgets them re-opens the
portrait trap), and the honesty contract.

If a stage's sections exceed the budget, sections drop from the
END of the stage's list (lowest priority last) and the drop is
LOGGED — a slice is never silently truncated mid-section the way
the old read caps cut the pack. slice_for() logs its size once
per stage per process, so a run log proves what each stage read.
"""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PACK = os.path.join(_HERE, "skills", "taste_pack.md")

# The free channel (Groq gpt-oss, free tier) rejects requests whose
# prompt + reserved output exceed its per-request token cap — the
# audit's 413s started at ~59K prompt chars. An 11,000-char slice
# (~3.1K tokens) leaves room for the stage's own content (script /
# beat menus / blocks, ~1-3K tokens) plus the 2,500-token output
# reservation and stays under the cap with a ~5x margin against
# the size that died. Section lists are ordered so the decisive
# sections fit inside the budget at the pack's current size.
SLICE_BUDGET = 11000

GLOBAL_SECTIONS = ("The one law", "Format literacy", "Honesty contract")

# Stage section lists, MOST decisive first — the budget trimmer
# drops from the end, so order is priority.
STAGE_SECTIONS = {
    "story": (
        "Story shape", "Documentary passes", "Documentary structure",
        "Loops and re-hooks", "Empathy and story economy",
        "Meaning first", "Phrasing", "Retention engineering",
        "Narrative scenes",
    ),
    "visual": (
        "Meaning first", "Frame composition", "Evidence is an apparatus",
        "Show it in its real form", "Numbers and anchors",
        "Composition before animation", "Maps and visual explanation",
        "Finish: matching", "Vertical is its own frame", "Kinetic type",
    ),
    "editing": (
        "Beat grammar", "Sound (planned AND executed", "Music is edited",
        "Transitions are a vocabulary", "Pace by phase",
        "Effects discipline", "Sound placement", "Sound decisions",
        "Beat craft", "Restraint", "Moves with names",
        "Sound design: layers", "Loops and re-hooks",
    ),
    "qc": (
        "Frame composition", "Effects discipline", "Finish: matching",
        "Evidence is an apparatus", "Numbers and anchors",
        "Colour is meaning",
    ),
}

_cache = {"sections": None}
_logged = set()


def sections():
    """{section header text: section text} for skills/taste_pack.md,
    parsed once. A section runs from its `## ` line to the next one."""
    if _cache["sections"] is None:
        out = {}
        try:
            with open(_PACK, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
        name, buf = None, []
        for ln in lines:
            if ln.startswith("## "):
                if name is not None:
                    out[name] = "\n".join(buf).strip()
                name, buf = ln[3:].strip(), [ln]
            elif name is not None:
                buf.append(ln)
        if name is not None:
            out[name] = "\n".join(buf).strip()
        _cache["sections"] = out
    return _cache["sections"]


def _find(secs, prefix):
    """The section whose header starts with `prefix` (headers carry
    parenthetical subtitles that vary), or None."""
    for name, text in secs.items():
        if name.startswith(prefix):
            return name, text
    return None, None


def slice_for(stage, budget=SLICE_BUDGET):
    """The taste-pack slice for one brain stage: GLOBAL sections +
    the stage's own, in pack order, trimmed to `budget` chars by
    dropping the stage's lowest-priority sections (never a global).
    Logs size + drops once per stage per process."""
    secs = sections()
    wanted = list(GLOBAL_SECTIONS) + list(STAGE_SECTIONS.get(stage, ()))
    picked = []          # (priority index, name, text)
    for prio, prefix in enumerate(wanted):
        name, text = _find(secs, prefix)
        if name and all(name != p[1] for p in picked):
            picked.append((prio, name, text))
    # Emit in PACK order (the pack's own reading flow), not priority
    # order — priority only decides what the trimmer drops.
    order = {name: i for i, name in enumerate(secs)}
    picked.sort(key=lambda p: order.get(p[1], 999))

    def _join(items):
        return "\n\n".join(t for _, _, t in items)

    dropped = []
    while len(_join(picked)) > budget:
        # drop the lowest-priority NON-global section still present
        non_global = [p for p in picked
                      if not any(p[1].startswith(g) for g in GLOBAL_SECTIONS)]
        if not non_global:
            break
        victim = max(non_global, key=lambda p: p[0])
        picked.remove(victim)
        dropped.append(victim[1])
    txt = _join(picked)
    if len(txt) > budget:  # globals alone over budget: hard cap, logged
        txt = txt[:budget]
        dropped.append("<hard-truncated>")
    if stage not in _logged:
        _logged.add(stage)
        print(f"pack slice [{stage}]: {len(txt)} chars, "
              f"{len(picked)} sections"
              + (f" (dropped: {', '.join(dropped)})" if dropped else "")
              + f" — full pack is {sum(len(t) for t in secs.values())} chars")
    return txt


def slice_info(stage, budget=SLICE_BUDGET):
    """Test/diagnostic view: (chars, [section names], [dropped])."""
    secs = sections()
    wanted = list(GLOBAL_SECTIONS) + list(STAGE_SECTIONS.get(stage, ()))
    picked = []
    for prio, prefix in enumerate(wanted):
        name, text = _find(secs, prefix)
        if name and all(name != p[1] for p in picked):
            picked.append((prio, name, text))
    dropped = []
    while len("\n\n".join(t for _, _, t in picked)) > budget:
        non_global = [p for p in picked
                      if not any(p[1].startswith(g) for g in GLOBAL_SECTIONS)]
        if not non_global:
            break
        victim = max(non_global, key=lambda p: p[0])
        picked.remove(victim)
        dropped.append(victim[1])
    return (len("\n\n".join(t for _, _, t in picked)),
            [n for _, n, _ in picked], dropped)
