"""videotastetest.py — taste-guarantee rig.

Proves the delivery-blocking mechanism: channel profiles exist, style
rules map to checks, brain-quality passes enrich/criticise plans, the
video director record is required, source cards need sources, caption
overlaps fail, and delivery is blocked unless the review delivers.
"""

import asyncio
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brain_quality
import compliance
import frame_taste_qc
import hf_primary
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
rep_plan = {"research": [{"title": "Spotlight effect: people overestimate attention",
                          "snippet": "study participants overestimated attention"}],
            "scenes": [
                {"no": 1, "vo": "In one study, 46 percent of people "
                                "overestimated the attention on them.",
                 "label": "The study", "queries": ["crowd people walking"]},
                {"no": 2, "vo": "Scientists found the effect grows with age.",
                 "label": "Growth", "queries": ["older man street"]}]}
brain_quality.repair_plan(rep_plan, prof)
check("T10 repair stamps matched source",
      rep_plan["scenes"][0].get("source") == "Spotlight effect: people overestimate attention",
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

# T11: variety repair demotes excess graphics to locked footage and
# the visual pass does not re-assign them.
var_plan = {"scenes": [{"no": i + 1, "vo": "The feeling grows later tonight.",
                        "label": "Feeling", "graphic_type": "diagram",
                        "diagram_kind": "growth",
                        "queries": ["person street night"]}
                       for i in range(12)]}
brain_quality.repair_plan(var_plan, prof)
brain_quality.enrich_visuals(var_plan["scenes"], prof)
var_fails2 = [c for c in taste_pack.profile_checks(var_plan, prof)
              if c["rule"] == "TASTE-VARIETY" and c["status"] == "FAIL"]
check("T11 variety repair caps diagrams", not var_fails2, str(var_fails2))
locked = [s for s in var_plan["scenes"] if s.get("graphic_locked")]
check("T11 demoted beats stay locked footage",
      len(locked) == 9 and all(s.get("graphic_type") == "footage" for s in locked),
      str([(s.get("no"), s.get("graphic_type")) for s in var_plan["scenes"]]))

# T12: restatement repair scores the COMBINED replacement against
# all beats (regression: tasteproof beats 4/11 shared 77% of content
# words after repair because only the first sentence was scored).
restate_plan = {"scenes": [
    {"no": 1, "vo": "Morning light spilled across the narrow street below.",
     "label": "MORNING", "queries": ["morning street light"]},
    {"no": 2, "vo": "A bicycle bell rang twice near the bakery corner.",
     "label": "BELL", "queries": ["bicycle bakery corner"]},
    {"no": 3, "vo": "Children chased paper planes beside the school gate.",
     "label": "PLANES", "queries": ["children paper planes"]},
    {"no": 4, "vo": "The quiet room kept the same heavy feeling while "
                    "everyone waited outside the door.",
     "label": "QUIET ROOM", "queries": ["quiet room door"]},
    {"no": 5, "vo": "Steam curled above a cup left beside the ledger.",
     "label": "STEAM", "queries": ["steam cup ledger"]},
    {"no": 6, "vo": "Footsteps echoed along the corridor after midnight.",
     "label": "STEPS", "queries": ["corridor footsteps night"]},
    {"no": 7, "vo": "A radio murmured weather reports from the kitchen shelf.",
     "label": "RADIO", "queries": ["kitchen radio shelf"]},
    {"no": 8, "vo": "Rain tapped the tin roof in uneven rhythms.",
     "label": "RAIN", "queries": ["rain tin roof"]},
    {"no": 9, "vo": "The gardener trimmed hedges beside the stone path.",
     "label": "GARDEN", "queries": ["gardener stone path"]},
    {"no": 10, "vo": "Distant trains crossed the bridge beyond the fields.",
     "label": "TRAINS", "queries": ["train bridge fields"]},
    {"no": 11, "vo": "The quiet room kept the same heavy feeling while "
                     "everyone waited near the bright window.",
     "label": "QUIET ROOM", "queries": ["quiet room door"]},
]}
pre_sim = brain_quality._line_sim(restate_plan["scenes"][3]["vo"],
                                  restate_plan["scenes"][10]["vo"])
check("T12 beats 4/11 start at 77% shared words", pre_sim > 0.65,
      f"pre_sim={pre_sim:.0%}")
brain_quality.repair_plan(restate_plan, prof)
post_sim = brain_quality._line_sim(restate_plan["scenes"][3]["vo"],
                                   restate_plan["scenes"][10]["vo"])
check("T12 repair brings beats 4/11 below threshold",
      post_sim <= brain_quality.RESTATE_THRESHOLD,
      f"post_sim={post_sim:.0%} vo={restate_plan['scenes'][10]['vo']}")
restate_fails = fails(brain_quality.story_checks(restate_plan["scenes"], prof),
                      "BRAIN-RESTATEMENT")
check("T12 no BRAIN-RESTATEMENT failures after repair", not restate_fails,
      str(restate_fails))

# T13: caption safe margins (ta57e022 step 7: caption cut by frame edge).
margin_checks = taste_pack.caption_events_ok([
    {"start": 0.0, "end": 1.0,
     "text": "extraordinary circumstances everywhere surrounding everything",
     "width": 1920, "font_size": 54}], prof)
check("T13 caption safe-margin breach rejected",
      bool(fails(margin_checks, "TASTE-CAPTION")), str(margin_checks))
check("T13 safe margin is 6% of 1920",
      taste_pack.caption_safe_margin_px(prof, 1920) == 115)
try:
    import doc as _doc_t13
    _doc_t13.W, _doc_t13.H = 1920, 1080
    _words_t13 = [(i * 0.4, 0.4, w) for i, w in enumerate(
        "extraordinary circumstances everywhere surrounding".split())]
    _plan_t13 = {"lang": "en",
                 "render_config": {"kind": "long",
                                   "taste_profile": "wtu_long_sheet"},
                 "scenes": [{"vo": "extraordinary circumstances "
                                    "everywhere surrounding",
                             "words": _words_t13, "adur": 1.6}],
                 "starts": [0.0]}
    with tempfile.TemporaryDirectory() as _td13:
        _ass_t13 = os.path.join(_td13, "subs.ass")
        _doc_t13.write_ass(_plan_t13, _ass_t13)
        _ass_txt = open(_ass_t13, encoding="utf-8").read()
    check("T13 ASS uses taste safe margins", ",115,115," in _ass_txt)
    check("T13 ASS has no 106% caption overshoot", "fscx106" not in _ass_txt)
    check("T13 wide phrase split inside margins",
          _ass_txt.count("Dialogue:") > 1, _ass_txt[:400])
except Exception as _e13:
    check("T13 ASS safe-margin render", False, str(_e13))

# T14: blocked runs carry a review-bearing director record.
blk_plan = {"topic": "blocked", "render_config": taste_pack.cfg_for_profile(prof),
            "scenes": [dict(sourced)]}
blk_err = video_director_gates.blocked_error(
    blk_plan, "TASTE DIRECTOR GATE: delivery blocked — review rework",
    defects=["step 5: frame shows the wrong subject"], profile=prof)
check("T14 blocked error carries record",
      bool(getattr(blk_err, "video_director", None)))
check("T14 blocked record has review for the Worker route",
      ((blk_err.video_director or {}).get("review") or {}).get("verdict") == "rework")
blk_allowed, _blk_why = video_director_gates.delivery_allowed(
    blk_plan, blk_plan["render_config"])
check("T14 blocked record still blocks delivery", not blk_allowed)

# T15: frame taste vision retry — 429 then answer passes; always
# failing stays UNVERIFIED (never upgraded).
try:
    with tempfile.TemporaryDirectory() as _td15:
        _vid15 = os.path.join(_td15, "v.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f",
                        "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
                        "-pix_fmt", "yuv420p", _vid15],
                       check=True, timeout=60)
        _calls15 = {"n": 0}

        async def _flaky15(images, question):
            _calls15["n"] += 1
            if _calls15["n"] == 1:
                raise RuntimeError("qwen 429")
            return ('{"shows": true, "fills_frame": true, "text_ok": true, '
                    '"source_card_ok": true, "graphic_ok": true, '
                    '"face_ok": true, "note": "shows the subject"}'), "stub"

        _rep15 = asyncio.run(frame_taste_qc.audit_beats(
            _vid15, [{"beat": 1, "line": "x", "promise": "y",
                      "start": 0, "duration": 2}],
            os.path.join(_td15, "frames"), vision=_flaky15,
            vision_attempts=2, retry_sleep_s=0, pace_s=0))
        check("T15 vision 429 retried then judged",
              _rep15["beats"][0]["status"] == "PASS" and _calls15["n"] == 2,
              str(_rep15))

        async def _dead15(images, question):
            raise RuntimeError("vision 429")

        _rep15b = asyncio.run(frame_taste_qc.audit_beats(
            _vid15, [{"beat": 1, "line": "x", "promise": "y",
                      "start": 0, "duration": 2}],
            os.path.join(_td15, "frames2"), vision=_dead15,
            vision_attempts=2, retry_sleep_s=0, pace_s=0))
        check("T15 vision outage stays UNVERIFIED",
              _rep15b["beats"][0]["status"] == "UNVERIFIED", str(_rep15b))
except Exception as _e15:
    check("T15 frame taste retry rig", False, str(_e15))

# T16: audio repair — true peak ceiling + undesigned silence fill.
try:
    with tempfile.TemporaryDirectory() as _td16:
        _mix16 = os.path.join(_td16, "mix.wav")
        _bed16 = os.path.join(_td16, "bed.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-filter_complex",
             "[1:a]atrim=duration=1.2[s];[0:a]volume=0.95[a];"
             "[2:a]volume=0.95[b];[a][s][b]concat=n=3:v=0:a=1[o]",
             "-map", "[o]", "-c:a", "pcm_s16le", _mix16],
            check=True, timeout=60)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", "sine=frequency=220:duration=3.2", "-af",
             "volume=0.2", "-c:a", "pcm_s16le", _bed16],
            check=True, timeout=60)
        _rep16 = compliance.repair_audio_delivery(_mix16, bed_path=_bed16)
        check("T16 audio repair ran", bool(_rep16.get("repaired")),
              str(_rep16))
        check("T16 true peak at/below -1 dB after repair",
              _rep16.get("peak_after") is not None
              and _rep16["peak_after"] <= -1.0, str(_rep16))
        check("T16 undesigned silence filled",
              not _rep16.get("gaps_after"), str(_rep16))
except Exception as _e16:
    check("T16 audio repair rig", False, str(_e16))

# T17: strict footage verification has no unverified-candidate hole;
# taste transitions never dip through black.
_broll_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "broll.py"), encoding="utf-8").read()
check("T17 strict mode verifies every candidate",
      "strict_verify or _verified_count < 2" in _broll_src
      and "no verdict for candidate" in _broll_src)
check("T17 taste transition never fadeblack",
      hf_primary._xfade_for("dip to black", 1, [], taste=True) == "dissolve"
      and hf_primary._xfade_for("dip to black", 1, [], taste=False) == "fadeblack")

# T18: consecutive blank-ish frames count across kind changes.
try:
    import doc as _doc_t18
    _flaws18 = _doc_t18._consecutive_blank_flaws([
        ("f0091.jpg", "blank/black (mean 3.0)"),
        ("f0092.jpg", "solid colour (std 2.0)"),
        ("f0093.jpg", None),
        ("f0094.jpg", "blank/black (mean 2.0)")])
    check("T18 alternating blank kinds still flaw", len(_flaws18) == 1,
          str(_flaws18))
except Exception as _e18:
    check("T18 blank-run helper", False, str(_e18))

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    sys.exit(1)
print("VIDEOTASTETEST: ALL PASS")
