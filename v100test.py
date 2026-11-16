"""v100test.py — harness for the v100 ANTI-BORING gates.

Ajju's verdict on the v85/v87/v88/Male-Gaze films was one word:
boring. The monitoring report (~/workspace/julie-malegaze/
MONITORING_REPORT.md) proved the cause: knowledge was never the
bottleneck — the decision + feedback loop was. These tests prove
each v100 gate FIRES, with stubbed LLM / pool / renderer where
the existing suites stub:

1. FOOTAGE-FIRST — a film-title query is not searchable; a
   no-match beat is RE-PLANNED into footage, and a beat that
   still misses carries a logged waiver (never a silent island);
   FG-SHARE reports the achieved share and FAILs below 70%.
2. FACT GATE — an unsourced statistic FAILs; sourced / hedged
   pass; the gate's rewrite round fixes a scene; a claim that
   survives the rewrite is REMOVED deterministically; fake
   next-chapter teases FAIL (FG-TEASE).
3. QC WITH TEETH — a spec-less chapter whose compliance FAILs
   in a boring-critical class is RE-RENDERED with the failures
   + gate guidance in its brief (the Male Gaze run shipped 112
   FAILs with 0 fix rounds); a non-critical FAIL alone does
   not trigger a round.
4. VARIETY CAPS — a flattened histogram FAILs VHIST; the real
   director's selection respects the soft cap; doc.plan
   RE-PLANS a flattened directed plan before render.
5. LENGTH HONESTY — a restatement top-up is REJECTED (no join;
   the chapter ships at its honest length); a novel top-up
   joins as before.
6. SOUND FLOOR — a flat mix FAILs MQ-LRA on a long film; a
   dynamic mix PASSes; the flattest-music-chapter picker names
   the chapters the fix round re-renders.
"""

import asyncio
import copy
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


import anti_boring as ab

# ---------------------------------------------------------- Gate 1a
check("query: 'Psycho film still female' is not searchable",
      not ab.query_is_searchable("Psycho film still female"))
check("query: 'Laura Mulvey gaze theory' is not searchable",
      not ab.query_is_searchable("Laura Mulvey gaze theory"))
check("query: 'woman looking in mirror' is searchable",
      ab.query_is_searchable("woman looking in mirror"))
check("query: 'doctor holding liver scan' is searchable",
      ab.query_is_searchable("doctor holding liver scan"))
_kept, _dropped = ab.searchable_queries(
    ["Psycho film still female"],
    "A woman studies her own reflection in the mirror", "MIRROR")
check("query hygiene: dead query dropped, line-derived query kept",
      _dropped and _kept and ab.query_is_searchable(_kept[0]),
      f"kept={_kept} dropped={_dropped}")

# ---------------------------------------------------------- Gate 1b
import doc


class _StubPool:
    """assign() lands a clip only for queries in `land_on`."""

    def __init__(self, land_on=()):
        self.land_on = tuple(land_on)
        self.assignments = []
        self.used_ids = []
        self.last_uploader = None
        self.calls = []

    def assign(self, scene_no, queries, dur_s, dl, orientation=None,
               line=""):
        self.calls.append(list(queries))
        if any(any(k in q for k in self.land_on) for q in queries):
            return {"path": "/tmp/clip.mp4", "clip_id": "stub:1",
                    "provider": "pexels",
                    "source_url": "https://example.invalid/clip",
                    "query": queries[0], "keyword": queries[0],
                    "start": 1.0, "static": False,
                    "uploader": "stub"}
        return None

    def footage_json(self):
        return {"assignments": self.assignments, "rejections": []}

    def _save(self):
        pass


_orig_extract = doc._extract_broll_frames
doc._extract_broll_frames = lambda *a, **k: 5
try:
    _wd = tempfile.mkdtemp(prefix="v100_")
    _scene = {"vo": "A woman studies her reflection and wonders "
                    "who is watching her",
              "label": "MIRROR", "queries": ["woman looking mirror"],
              "d": 3.0, "visual": "chat", "value": "", "source": ""}
    _tail = dict(_scene, vo="And so the watching never really ends",
                 label="ENDING")
    _p = {"topic": "The Male Gaze", "scenes": [dict(_scene),
                                               dict(_tail)],
          "render_config": {"kind": "long"}}
    _pool = _StubPool(land_on=("cinema audience",))
    doc._attach_broll(
        _p, _wd, cfg={"kind": "long"}, pool=_pool,
        replan=lambda sc, no: ["cinema audience watching screen"])
    check("footage re-plan: no-match beat re-planned into footage",
          _p["scenes"][0].get("has_footage") is True,
          f"scene={_p['scenes'][0]}")
    check("footage re-plan: landed beat carries NO waiver",
          "footage_waived" not in _p["scenes"][0])

    _p2 = {"topic": "The Male Gaze",
           "scenes": [dict(_scene), dict(_tail)],
           "render_config": {"kind": "long"}}
    _pool2 = _StubPool(land_on=())
    doc._attach_broll(
        _p2, _wd, cfg={"kind": "long"}, pool=_pool2,
        replan=lambda sc, no: ["cinema audience watching screen"])
    check("footage waiver: unmatchable beat is waived, not islanded "
          "silently",
          bool(_p2["scenes"][0].get("footage_waived"))
          and len(_p2.get("footage_waivers") or []) == 1,
          f"plan keys={sorted(_p2)}")
finally:
    doc._extract_broll_frames = _orig_extract

# FG-SHARE: the achieved share is reported; below target FAILs
_scs = [{"has_footage": i < 5} for i in range(10)]
_fg = ab.audit_footage_share(_scs, {"kind": "long"})
check("FG-SHARE: 50% footage FAILs with the share in the detail",
      _fg and _fg[0]["status"] == "FAIL" and "50%" in _fg[0]["detail"])
_scs = [{"has_footage": i < 8} for i in range(10)]
_fg = ab.audit_footage_share(_scs, {"kind": "long"})
check("FG-SHARE: 80% footage PASSes",
      _fg and _fg[0]["status"] == "PASS")
check("FG-SHARE: shorts are not gated",
      ab.audit_footage_share(_scs, {"kind": "short"}) == [])

# ---------------------------------------------------------- Gate 2
_stat = {"vo": "Alcohol causes 70 percent of all road deaths.",
         "source": "", "value": "70%"}
check("fact gate: unsourced statistic FAILs FG-FACT",
      any(c["rule"] == "FG-FACT"
          for c in ab.audit_claims([_stat])))
check("fact gate: sourced statistic passes",
      not ab.audit_claims([dict(_stat, source="WHO 2023")]))
check("fact gate: hedged statistic passes",
      not ab.audit_claims([dict(
          _stat, vo="Roughly 70 percent of road deaths involve "
                    "alcohol.")]))
check("fact gate: invented hashtag movement FAILs",
      any(c["rule"] == "FG-FACT" for c in ab.audit_claims(
          [{"vo": "Then the #ViewersUnite movement changed "
                  "everything.", "source": ""}])))


def _chat_rewrite(msgs):
    return ('{"scenes": [{"scene": 1, "vo": "Roughly 70 percent '
            'of road deaths involve alcohol.", "source": ""}]}')


_gate_in = [dict(_stat),
            {"vo": "Drivers should rest on long night journeys.",
             "source": "", "value": ""}]
_out = ab.fact_gate(copy.deepcopy(_gate_in), _chat_rewrite)
check("fact gate: rewrite round runs and fixes the claim",
      _out["log"]["rewrite_round"] is True and not _out["checks"],
      f"log={_out['log']}")


def _chat_stubborn(msgs):
    # the rewrite round "answers" but changes nothing — the claim
    # comes back verbatim, so the deterministic removal must fire
    return ('{"scenes": [{"scene": 1, "vo": "Alcohol causes 70 '
            'percent of all road deaths. Night driving demands '
            'full attention.", "source": ""}]}')


_two = [dict(_stat,
             vo="Alcohol causes 70 percent of all road deaths. "
                "Night driving demands full attention."),
        {"vo": "Drivers should rest on long night journeys.",
         "source": "", "value": ""}]
_out2 = ab.fact_gate(copy.deepcopy(_two), _chat_stubborn)
check("fact gate: surviving invented stat is REMOVED, the honest "
      "sentence stays",
      _out2["scenes"]
      and "70 percent" not in _out2["scenes"][0]["vo"]
      and "full attention" in _out2["scenes"][0]["vo"]
      and _out2["log"]["removed"],
      f"out={_out2['scenes'][0] if _out2['scenes'] else None}")

# a scene that is ONLY an invented stat is dropped outright
# (when the chapter stays above the minimum scene count)
_five = [dict(_stat)] + [
    {"vo": f"Honest scene {i} carries the story forward.",
     "source": "", "value": ""} for i in range(4)]
_out3 = ab.fact_gate(copy.deepcopy(_five), None)
check("fact gate: a claim-only scene is dropped, chapter intact",
      len(_out3["scenes"]) == 4
      and _out3["log"]["dropped_scenes"]
      and not _out3["checks"],
      f"log={_out3['log']}")
check("fact gate: narrative number words are not statistics",
      not ab.audit_claims(
          [{"vo": "One morning, the first thing she noticed was "
                  "the silence.", "source": ""}]))

# teases: only content in the film's own plan may be teased
_tz = ab.audit_teases(
    [(1, "We begin the story here."),
     (3, "In chapter 4, we will see the real answer.")], 3)
check("FG-TEASE: a chapter beyond the plan FAILs",
      any(c["rule"] == "FG-TEASE" for c in _tz))
_tz2 = ab.audit_teases(
    [(1, "In the next chapter, the story turns."),
     (3, "That is the whole story.")], 3)
check("FG-TEASE: 'next chapter' in a non-final chapter is honest",
      not _tz2)
_tz3 = ab.audit_teases(
    [(3, "Join us in the next chapter for more.")], 3)
check("FG-TEASE: 'next chapter' promised by the FINAL chapter "
      "FAILs", any(c["rule"] == "FG-TEASE" for c in _tz3))
_tz4 = ab.audit_teases(
    [(3, "So the number on screen says it all.")], 3,
    last_scene={"value": "4", "visual": "counter"})
check("FG-TEASE: ending on the number chapters+1 FAILs",
      any(c["rule"] == "FG-TEASE" for c in _tz4))

# ---------------------------------------------------------- Gate 4
_flat = ([{"visual_concept": "counter"}] * 6
         + [{"visual_concept": "timeline"}] * 2
         + [{"visual_concept": "quote_typewriter"}] * 2)
_vh = ab.audit_variety(_flat)
check("VHIST: a flattened histogram FAILs with the histogram "
      "shown", _vh and _vh[0]["rule"] == "VHIST"
      and "counter" in _vh[0]["detail"])
_bal = [{"visual_concept": t} for t in
        ("counter", "timeline", "quote_typewriter", "stat_bars",
         "contrast_scale", "evidence_document", "question_card",
         "time_visual", "speech_bubble", "relation_heart")]
check("VHIST: a balanced chapter passes", not ab.audit_variety(_bal))
check("VHIST: short chapters are exempt",
      not ab.audit_variety(_flat[:5]))

import director

_wplan = {"topic": "Numbers", "title": "NUMBERS", "look": "A",
          "seed": 7,
          "scenes": [{"vo": f"The count reached {10 + i} units "
                            f"today.",
                      "label": f"COUNT {i + 1}", "visual": "chat",
                      "mood": "calm", "value": "", "source": "",
                      "why": "", "queries": []}
                     for i in range(40)]}
_dplan, _recs = director.direct_plan(copy.deepcopy(_wplan),
                                     brief="", cfg=None, brain=None)
from collections import Counter as _Ctr
_hist = _Ctr(r["visual_concept"] for r in _recs)
_cap = max(3, -(-3 * len(_recs) // 10))
check("director soft cap: no template exceeds the selection cap",
      _recs and max(_hist.values()) <= _cap,
      f"hist={dict(_hist)} cap={_cap} beats={len(_recs)}")

# doc.plan RE-PLANS a flattened directed plan before render
import director as _dmod

_orig_sd, _orig_dp = _dmod.should_direct, _dmod.direct_plan
_calls = {"n": 0}


def _fake_direct(plan, brief="", cfg=None, brain=None, **kw):
    _calls["n"] += 1
    p = copy.deepcopy(plan)
    if _calls["n"] == 1:
        recs = [{"beat": i + 1, "visual_concept": "counter",
                 "heard": "x", "see": "counter", "why": "w",
                 "duration_est_s": 3.0, "arc_role": "context",
                 "music_intensity": 0.5} for i in range(12)]
    else:
        _exc = (brain or {}).get("exclude") or {}
        check("doc.plan re-plan: exclusions name the dominant "
              "template", any("counter" in v for v in _exc.values()),
              f"exclude={_exc}")
        kinds = ("counter", "timeline", "quote_typewriter",
                 "stat_bars")
        recs = [{"beat": i + 1, "visual_concept": kinds[i % 4],
                 "heard": "x", "see": kinds[i % 4], "why": "w",
                 "duration_est_s": 3.0, "arc_role": "context",
                 "music_intensity": 0.5} for i in range(12)]
    p["scenes"] = [{"vo": f"Beat {i + 1} speaks its own line.",
                    "label": f"BEAT {i + 1}", "visual": "chat",
                    "mood": "calm", "value": "", "source": "",
                    "why": "the line itself", "queries": [],
                    "d": 3.0} for i in range(12)]
    p["visual_plan"] = recs
    p["directed"] = "v86-documentary-director"
    return p, recs


def _writer_chat(msgs):
    scenes = [{"vo": f"Scene {i + 1} tells one plain fact of the "
                     f"story.",
               "label": f"SCENE {i + 1}", "visual": "chat",
               "mood": "calm", "value": "", "source": "", "why": "",
               "queries": ["people working together",
                           "city street morning"]}
              for i in range(12)]
    import json as _json
    return _json.dumps({"topic": "Teamwork", "title": "TEAMWORK",
                        "lang": "en", "voice": "female",
                        "caption": "c", "end_question": "Did you?",
                        "scenes": scenes})


_dmod.should_direct = lambda brief, cfg: True
_dmod.direct_plan = _fake_direct
try:
    _pp = doc.plan("Long video 'Teamwork', chapter 1 of 3: "
                   "How teams work.", _writer_chat,
                   cfg={"kind": "long"})
finally:
    _dmod.should_direct, _dmod.direct_plan = _orig_sd, _orig_dp
check("doc.plan: flattened plan is re-planned before render",
      _calls["n"] == 2 and (_pp.get("variety") or {}).get("replanned")
      is True and (_pp.get("variety") or {}).get("ok") is True,
      f"calls={_calls['n']} variety={_pp.get('variety')}")

# ---------------------------------------------------------- Gate 3
import long_video

_outline = {"title": "T", "chapters": [
    {"title": "C1", "brief": "the only chapter", "minutes": 1}]}


def _run_chapters(make_video_stub, **kw):
    _orig_mv = doc.make_video
    doc.make_video = make_video_stub
    try:
        _res_out = []
        _wd2 = tempfile.mkdtemp(prefix="v100_ch_")
        asyncio.run(long_video.render_chapters(
            _outline, lambda m: "{}", _wd2, results_out=_res_out,
            **kw))
        return _res_out
    finally:
        doc.make_video = _orig_mv


_calls3 = {"n": 0, "briefs": []}


async def _mv_critical(brief, chat, **kw):
    _calls3["n"] += 1
    _calls3["briefs"].append(brief)
    if _calls3["n"] == 1:
        return {"path": "ch1.mp4", "duration": 55.0,
                "compliance": {"checks": [
                    {"rule": "R10", "status": "FAIL",
                     "detail": "9/10 scenes have no footage",
                     "scene": None}]},
                "plan": {"scenes": []}}
    return {"path": "ch1_fix.mp4", "duration": 56.0,
            "compliance": {"checks": []}, "plan": {"scenes": []}}


_res3 = _run_chapters(_mv_critical, spec=None, cfg={"kind": "long"})
check("fix rounds: spec-less boring-critical FAIL re-renders "
      "the chapter", _calls3["n"] == 2
      and _res3 and _res3[0].get("fix_rounds_used") == 1
      and _res3[0].get("path") == "ch1_fix.mp4",
      f"calls={_calls3['n']} res={_res3}")
check("fix rounds: the fix brief names the failure + footage "
      "guidance", _calls3["briefs"] and len(_calls3["briefs"]) > 1
      and "COMPLIANCE FIXES REQUIRED" in _calls3["briefs"][1]
      and "FOOTAGE:" in _calls3["briefs"][1])

_calls3b = {"n": 0}


async def _mv_trivial(brief, chat, **kw):
    _calls3b["n"] += 1
    return {"path": "ch1.mp4", "duration": 55.0,
            "compliance": {"checks": [
                {"rule": "R6", "status": "FAIL",
                 "detail": "title too long", "scene": 1}]},
            "plan": {"scenes": []}}


_res3b = _run_chapters(_mv_trivial, spec=None, cfg={"kind": "long"})
check("fix rounds: a non-critical FAIL alone does NOT burn a "
      "re-render (spec-less)", _calls3b["n"] == 1
      and _res3b and _res3b[0].get("fix_rounds_used") == 0)

# boring-critical classifier itself
_mixed = [{"rule": "R10", "status": "FAIL"},
          {"rule": "R6", "status": "FAIL"},
          {"rule": "VHIST", "status": "FAIL"},
          {"rule": "FG-FACT", "status": "PASS"}]
check("boring-critical classifier keeps only critical FAILs",
      [c["rule"] for c in ab.boring_critical_fails(_mixed)]
      == ["R10", "VHIST"])

# ---------------------------------------------------------- Gate 5
_outline2 = {"title": "T", "chapters": [
    {"title": "C1", "brief": "the only chapter", "minutes": 2}]}
_VO_OLD = ("Alpha bravo charlie delta echo foxtrot golf hotel "
           "india juliet kilo lima.")
_VO_NEW = ("Zebra yachts xavier william victor uniform tango "
           "sierra romeo quebec papa.")
_joins = {"n": 0}


def _fake_join(paths, out):
    _joins["n"] += 1
    return out


def _run_topup(ext_vo):
    _orig_mv, _orig_join = doc.make_video, long_video._join_clips
    _orig_probe = long_video._probe_duration
    _state = {"n": 0}

    async def _mv(brief, chat, **kw):
        _state["n"] += 1
        if "EXTENSION" in brief:
            return {"path": "ext.mp4", "duration": 60.0,
                    "compliance": {"checks": []},
                    "plan": {"scenes": [{"vo": ext_vo}]}}
        return {"path": "ch1.mp4", "duration": 60.0,
                "compliance": {"checks": []},
                "plan": {"scenes": [{"vo": _VO_OLD}]}}

    doc.make_video = _mv
    long_video._join_clips = _fake_join
    long_video._probe_duration = lambda p: 120.0
    try:
        _res_out = []
        _wd3 = tempfile.mkdtemp(prefix="v100_tu_")
        asyncio.run(long_video.render_chapters(
            _outline2, lambda m: "{}", _wd3, results_out=_res_out,
            spec=None, cfg={"kind": "long"}))
        return _res_out, _state["n"]
    finally:
        doc.make_video = _orig_mv
        long_video._join_clips = _orig_join
        long_video._probe_duration = _orig_probe


_joins["n"] = 0
_res5, _n5 = _run_topup(_VO_OLD)
check("length honesty: restatement top-up is REJECTED — no join, "
      "honest length kept", _joins["n"] == 0 and _res5
      and _res5[0].get("honest_length") is True
      and _res5[0].get("path") == "ch1.mp4"
      and "topup_rejected" in _res5[0],
      f"res={_res5}")
_joins["n"] = 0
_res5b, _n5b = _run_topup(_VO_NEW)
check("length honesty: a NOVEL top-up joins as before",
      _joins["n"] == 1 and _res5b
      and _res5b[0].get("topped_up") is True)

# ---------------------------------------------------------- Gate 6
import compliance as _comp
import media_qc

_gd = tempfile.mkdtemp(prefix="v100_lra_")
_flat_mp4 = os.path.join(_gd, "flat.mp4")
_dyn_mp4 = os.path.join(_gd, "dyn.mp4")
subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error",
     "-f", "lavfi", "-i", "color=c=black:s=320x180:d=12:r=10",
     "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
     "-shortest", _flat_mp4], check=True)
subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error",
     "-f", "lavfi", "-i", "color=c=black:s=320x180:d=48:r=10",
     "-f", "lavfi", "-i",
     "aevalsrc='sin(2*PI*440*t)*(0.09+0.41*lt(mod(t,16),8))':d=48",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
     "-shortest", _dyn_mp4], check=True)
_lra_flat = _comp.measure_lra(_flat_mp4)
_lra_dyn = _comp.measure_lra(_dyn_mp4)
check("LRA measurement: flat tone measures near-zero range",
      _lra_flat is not None and _lra_flat < 5.0,
      f"flat={_lra_flat}")
check("LRA measurement: alternating mix measures a real range",
      _lra_dyn is not None and _lra_dyn > _lra_flat,
      f"dyn={_lra_dyn} flat={_lra_flat}")
_mqc, _ = media_qc.inspect_file(_flat_mp4, cfg={"kind": "long"})
check("MQ-LRA: flat mix FAILs on a long film",
      any(c["rule"] == "MQ-LRA" and c["status"] == "FAIL"
          for c in _mqc),
      f"lra checks={[c for c in _mqc if c['rule'] == 'MQ-LRA']}")
_mqc2, _ = media_qc.inspect_file(_dyn_mp4, cfg={"kind": "long"})
check("MQ-LRA: dynamic mix does not FAIL",
      not any(c["rule"] == "MQ-LRA" and c["status"] == "FAIL"
              for c in _mqc2),
      f"lra checks={[c for c in _mqc2 if c['rule'] == 'MQ-LRA']}")
_mqc3, _ = media_qc.inspect_file(_flat_mp4, cfg={})
check("MQ-LRA: flat mix only WARNs when not a long film",
      any(c["rule"] == "MQ-LRA" and c["status"] == "WARN"
          for c in _mqc3))

_flat_chs = long_video._flattest_music_chapters([
    {"plan": {"scenes": [{"music_intensity": v}
                         for v in (0.5, 0.5, 0.5)]}},
    {"plan": {"scenes": [{"music_intensity": v}
                         for v in (0.7, 0.5, 0.3, 0.85)]}},
    {"plan": {"scenes": [{"vo": "no curve data"}]}},
], limit=2)
check("sound floor: flattest-curve chapters are picked for the "
      "music fix round", _flat_chs == [1, 3], f"got={_flat_chs}")

print()
print(f"v100test: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
