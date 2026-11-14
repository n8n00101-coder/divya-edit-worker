"""director.py — Julie v84 Stage 5 (P3): the Editing Director, LOG-ONLY.

The Director reads a finished scene plan (and, for a long video, the
documentary arc) and writes RECOMMENDATIONS ONLY:

- hard cut vs transition per scene boundary,
- effects that look unnecessary or stacked,
- scenes that need breathing space,
- silence placements (only: after a turning point, just before the
  payoff, just before the ending — 0.8-1.5 s, so the media audit can
  tell INTENTIONAL silence from a defect),
- a music-intensity curve across the story arc (hook 0.7, build 0.5,
  turning-point dip 0.3, payoff lift 0.85, ending decay 0.4; music
  always ducks under narration, lifts only in non-narration windows),
- visual repetition that weakens the story.

HARD CONTRACT (v1, Ajju Q7): the Director NEVER mutates the plan.
analyse() returns a brand-new log dict; the caller's plan object is
untouched (proven by the deep-equal test in v84test.py). Automatic
application of recommendations needs a separate future approval.
"""

import copy

ARC_MUSIC_CURVE = {
    "hook": 0.7, "context": 0.5, "evidence": 0.5, "contradiction": 0.55,
    "turning_point": 0.3, "build": 0.5, "payoff": 0.85, "conclusion": 0.4,
}
SILENCE_MIN_S, SILENCE_MAX_S = 0.8, 1.5
EFFECT_FIELDS = ("transition", "effect", "fx", "sfx")


def _scene_text(s):
    return str(s.get("vo") or s.get("narration") or s.get("title") or "")


def analyse_plan(scenes, arc=None, job_id="", config=None):
    """Return the Director's log for a scene list. Pure function:
    no mutation, no I/O, no model calls."""
    cfg = config or {}
    silence_min = float(cfg.get("silence_min_s", SILENCE_MIN_S))
    silence_max = float(cfg.get("silence_max_s", SILENCE_MAX_S))
    recs = []
    n = len(scenes or [])
    seen_visuals = {}
    for i, s in enumerate(scenes or []):
        no = s.get("no", i + 1)
        role = s.get("arc_role") or (arc[i] if arc and i < len(arc) else None)
        # --- visual repetition
        vis = str(s.get("visual") or "")
        if vis:
            if vis in seen_visuals:
                recs.append({"scene": no, "type": "visual_repetition",
                             "recommendation": "change visual",
                             "reason": f"visual '{vis}' already used at scene "
                                       f"{seen_visuals[vis]} — repetition weakens the story"})
            else:
                seen_visuals[vis] = no
        # --- stacked / unnecessary effects
        active_fx = [f for f in EFFECT_FIELDS
                     if s.get(f) not in (None, "", "none", "cut")]
        if len(active_fx) >= 3:
            recs.append({"scene": no, "type": "effect_stack",
                         "recommendation": "remove all but one effect",
                         "reason": f"{len(active_fx)} effect layers on one scene "
                                   f"({', '.join(active_fx)}) — one effect at a time"})
        # --- hard cut vs transition
        boundary = "hard cut"
        if s.get("transition") not in (None, "", "none", "cut"):
            if role in ("payoff", "conclusion") or i == n - 1:
                boundary = "keep transition (idea boundary)"
            else:
                recs.append({"scene": no, "type": "transition",
                             "recommendation": "replace transition with hard cut",
                             "reason": "transition inside one idea — professional "
                                       "cuts are invisible; transitions mark idea changes"})
        # --- breathing space
        dur = float(s.get("d") or 0)
        words = len(_scene_text(s).split())
        if dur and words and dur < words / 3.2:
            recs.append({"scene": no, "type": "breathing_space",
                         "recommendation": "let the scene breathe (longer hold)",
                         "reason": f"{words} narration words in {dur:.1f}s — dense; "
                                   f"the viewer cannot absorb the line"})
        # --- silence placement (the ONLY three sanctioned spots)
        silence = None
        if role == "turning_point":
            silence = {"after_scene": no, "duration_s": 1.0,
                       "reason": "after the turning point — let it land"}
        elif role == "payoff" and i > 0:
            silence = {"before_scene": no, "duration_s": 1.0,
                       "reason": "just before the payoff — anticipation"}
        elif i == n - 1 and n > 2:
            silence = {"before_scene": no, "duration_s": 1.2,
                       "reason": "just before the ending — closure"}
        if silence:
            d = silence["duration_s"]
            silence["duration_s"] = min(silence_max, max(silence_min, d))
            recs.append({"scene": no, "type": "silence", **silence})
    # --- music curve across the arc
    music = []
    for i, s in enumerate(scenes or []):
        role = s.get("arc_role") or (arc[i] if arc and i < len(arc) else None)
        inten = ARC_MUSIC_CURVE.get(role or "", 0.5)
        music.append({"scene": s.get("no", i + 1), "arc_role": role,
                      "music_intensity": inten,
                      "duck_under_narration": True,
                      "lift_only_without_narration": True})
    return {"version": "v84-director-1", "mode": "LOG-ONLY",
            "job_id": job_id, "scenes": n,
            "recommendations": recs, "music_curve": music,
            "silence_map": [r for r in recs if r["type"] == "silence"]}


def compare_with_render(log, report):
    """Stage-7 comparison helper: how many Director recommendations
    correspond to defects the compliance report actually found?
    Returns counts only — still no mutation of anything."""
    checks = (report or {}).get("checks") or []
    failed_rules = {c.get("rule") for c in checks if c.get("status") == "FAIL"}
    rec_types = {r["type"] for r in (log or {}).get("recommendations", [])}
    return {"recommendations": len((log or {}).get("recommendations", [])),
            "qc_failed_rules": sorted(x for x in failed_rules if x),
            "director_flagged_types": sorted(rec_types)}


if __name__ == "__main__":
    plan = [{"no": 1, "visual": "clock", "vo": "Time passes.", "d": 4,
             "transition": "dissolve", "effect": "zoom", "fx": "sparkle", "sfx": "whoosh"},
            {"no": 2, "visual": "clock", "vo": "And passes.", "d": 4},
            {"no": 3, "visual": "face", "vo": "The turn.", "d": 5, "arc_role": "turning_point"},
            {"no": 4, "visual": "sunrise", "vo": "The payoff lands now.", "d": 5, "arc_role": "payoff"}]
    before = copy.deepcopy(plan)
    log = analyse_plan(plan)
    assert plan == before, "Director mutated the plan!"
    print("director self-check OK:", len(log["recommendations"]),
          "recommendations,", len(log["silence_map"]), "silence placements")
