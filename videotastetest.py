"""videotastetest.py — taste-guarantee rig.

Proves the delivery-blocking mechanism: channel profiles exist, style
rules map to checks, brain-quality passes enrich/criticise plans, the
video director record is required, source cards need sources, caption
overlaps fail, and delivery is blocked unless the review delivers.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brain_quality
import hyperframes_codegen
import taste_pack
import video_director_gates

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


def fails(checks, rule=None):
    return [c for c in checks or [] if c.get("status") == "FAIL"
            and (rule is None or c.get("rule") == rule)]


# T1: channel profiles exist and resolve.
for pid in ("wtu_long_sheet", "wtu_short", "todays_ai_ai1",
            "todays_ai_ai2", "todays_ai_ai3", "quiet_page"):
    check(f"T1 profile {pid}", bool(taste_pack.get_profile(pid)))
check("T1 WTU long is 1920x1080",
      taste_pack.PROFILES["wtu_long_sheet"]["width"] == 1920 and
      taste_pack.PROFILES["wtu_long_sheet"]["height"] == 1080)
check("T1 AI-2 captions are top-16pct",
      taste_pack.PROFILES["todays_ai_ai2"]["caption"]["position"] == "top-16pct")

# T2: sourced fact gets source-card eligibility; unsourced number fails.
prof = taste_pack.PROFILES["wtu_long_sheet"]
sourced = {"no": 1, "vo": "Students guessed 46% had noticed.",
           "label": "THE GUESS", "value": "46%",
           "source": "Gilovich, Medvec & Savitsky (2000)",
           "queries": ["students classroom doorway"]}
unsourced = {"no": 2, "vo": "Sales rose 30% overnight.",
             "label": "SALES", "value": "30%", "source": "",
             "queries": ["people shopping street"]}
brain_quality.enrich_visuals([sourced, unsourced], prof)
check("T2 sourced fact -> source_card", sourced.get("graphic_type") == "source_card",
      str(sourced))
check("T2 unsourced number blocked",
      bool(fails(taste_pack.validate_scene(unsourced, prof, 1), "TASTE-SOURCE")))
check("T2 source_card without source blocked",
      bool(fails(taste_pack.validate_scene(
          {**unsourced, "graphic_type": "source_card"}, prof, 1),
          "TASTE-SOURCE-CARD")))

# T3: internal labels and banned first-beat hooks fail.
bad_label = {"no": 1, "vo": "You remember the pause.", "label": "HOOK",
             "visual": "card", "queries": ["person awake night"]}
check("T3 internal label rejected",
      bool(fails(taste_pack.validate_scene(bad_label, prof, 0), "TASTE-LABEL")))
check("T3 title/card hook rejected",
      bool(fails(taste_pack.validate_scene(bad_label, prof, 0), "TASTE-HOOK")))

# T4: caption overlap and long phrases fail.
cap_checks = taste_pack.caption_events_ok([
    {"start": 0.0, "end": 1.2, "text": "one two three four five six seven"},
    {"start": 1.1, "end": 2.0, "text": "overlap here"},
], prof)
check("T4 caption overlap/long phrase rejected", bool(fails(cap_checks, "TASTE-CAPTION")))

# T5: brain quality records route, story checks and critic checks.
plan = {"topic": "spotlight effect", "title": "SPOTLIGHT EFFECT",
        "render_config": taste_pack.cfg_for_profile(prof),
        "scenes": [dict(sourced), {"no": 2, "vo": "The room was busy with its own life.",
                                   "label": "THE ROOM", "visual": "card",
                                   "queries": ["busy crowd walking"]}]}
critic = brain_quality.apply(plan, prof)
check("T5 brain route recorded",
      (plan.get("brain_quality") or {}).get("route", {}).get("critic") == "strongest_free")
check("T5 critic checks recorded", bool(critic) and bool(plan["brain_quality"]["critic_checks"]))
check("T5 scenes enriched with acceptance",
      all(s.get("acceptance") and s.get("promise") for s in plan["scenes"]))

# T6: director record required and delivery blocked before review.
rec = video_director_gates.ensure_record(plan, prof, "spotlight effect")
check("T6 director record valid", not video_director_gates.validate_record(rec))
allowed, why = video_director_gates.delivery_allowed(plan, plan["render_config"])
check("T6 delivery blocked before review", not allowed and "review" in why, why)

# T7: passing bundle delivers; failing bundle reworks then fails after budget.
for s in plan["scenes"]:
    s["has_footage"] = True
review = video_director_gates.apply_checks_and_review(plan, prof)
check("T7 clean bundle delivers", review.get("verdict") == "deliver", str(review))
allowed, why = video_director_gates.delivery_allowed(plan, plan["render_config"])
check("T7 delivery allowed after deliver review", allowed, why)

bad_plan = {"topic": "bad", "render_config": taste_pack.cfg_for_profile(prof),
            "scenes": [dict(unsourced)]}
video_director_gates.ensure_record(bad_plan, prof)
bad_review = video_director_gates.apply_checks_and_review(bad_plan, prof)
check("T7 failing bundle -> rework", bad_review.get("verdict") == "rework", str(bad_review))
bad_plan["video_director"]["rework_passes"] = 2
bad_review2 = video_director_gates.apply_checks_and_review(bad_plan, prof)
check("T7 exhausted rework -> fail", bad_review2.get("verdict") == "fail", str(bad_review2))

# T8: HyperFrames knows source_card + diagram layers.
check("T8 source_card layer exists", "source_card" in hyperframes_codegen.LAYER_TYPES)
check("T8 diagram layer exists", "diagram" in hyperframes_codegen.LAYER_TYPES)

# T9: every taste rule maps to a gate/test.
rmap = taste_pack.rule_map()
check("T9 rule map complete",
      all(k in rmap for k in ("TASTE-SOURCE", "TASTE-CAPTION", "TASTE-AUDIO", "TASTE-FRAME")))

# T10: source repair stamps a matched research source and strips an
# unresolvable claim; the variety cap ignores footage (sheet default).
rep_plan = {"research": [{"title": "Spotlight effect study Gilovich",
                          "snippet": "people overestimate attention"}],
            "scenes": [
                {"no": 1, "vo": "In one study, 46 percent of people "
                                "overestimated the attention on them.",
                 "label": "The study", "queries": ["crowd people walking"]},
                {"no": 2, "vo": "Scientists found the effect grows with age.",
                 "label": "Growth", "queries": ["older man street"]}]}
brain_quality.repair_plan(rep_plan, prof)
check("T10 repair stamps matched source",
      rep_plan["scenes"][0].get("source") == "Spotlight effect study Gilovich",
      str(rep_plan["scenes"][0]))
check("T10 repair strips unresolvable claim",
      not taste_pack.source_required(rep_plan["scenes"][1]),
      str(rep_plan["scenes"][1]))
many_footage = {"scenes": [{"no": i + 1, "vo": "A quiet street at dawn.",
                            "label": "Street", "graphic_type": "footage",
                            "queries": ["quiet street dawn"]}
                           for i in range(10)]}
var_fails = [c for c in taste_pack.profile_checks(many_footage, prof)
             if c["rule"] == "TASTE-VARIETY" and c["status"] == "FAIL"]
check("T10 variety cap ignores footage", not var_fails, str(var_fails))

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    sys.exit(1)
print("VIDEOTASTETEST: ALL PASS")
