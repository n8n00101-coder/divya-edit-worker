#!/usr/bin/env python3
"""ROUND-4 tests — one block per fix from the third film's QC
("The Rise of Electric Cars: Revolution on Wheels", job 2035f85b).

Fix 1: TOPIC LOCK — AUTO dedupe vs delivered history + exclusions
       (outline), compliance topic verdict, top-up coherence gate.
Fix 2: FACT GATE on every pass — per-pass events recorded, plan()
       fails closed in documentary contexts, make_video refuses an
       ungated plan_override, an ungated top-up never joins.
Fix 3: vision verifier decisiveness — "uncertain" is retried
       forced-choice, then resolves to pass/fail or UNDECIDED;
       indecision > 50% is declared an outage; undecided pool
       picks are flagged keyword_only.
Fix 4: chapter throughput cap — per-chapter budget shares; a
       chapter's optional passes stop at its own share and every
       chapter is still attempted.
Fix 5: depiction-budget counter — plan-level mix, DEPICTION FAIL
       rides the chapter fix loop.
Fix 6: frame_qc broadcast-shapes crash — backgrounds are built at
       the extracted frame's own shape (landscape included).
Fix 7: v87test taste-pack pin is integrity-based (asserted here
       against the same pack the pin reads).
Fold-ins: packaging grades the DELIVERED title, never "Auto".

Run: python3 round4test.py
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def T(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name
          + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


_FG = {"claims": 2, "rewrite_round": False, "removed": [],
       "dropped_scenes": []}

# ================= Fix 1a: outline topic lock =================
import long_video
import topic_lock as tl

T("F1a 'electric cars' and 'electric vehicles' are the same "
  "subject", tl.topics_collide("The Rise of Electric Vehicles",
                               "The Rise of Electric Cars: "
                               "Revolution on Wheels"))
T("F1a unrelated subjects do not collide",
  not tl.topics_collide("The Rise of Electric Vehicles",
                        "The Hidden Life of Urban Bees"))
T("F1a exclusion hits through the synonym fold",
  tl.exclusion_hit("The Rise of Electric Cars",
                   ["electric vehicles"]) == "electric vehicles")
_ex = tl.parse_exclusions(
    "make a 10 minute long documentary, topic AUTO, choose a "
    "strong subject, not electric vehicles and not bees please")
T("F1a exclusions parse from the owner's own words",
  "electric vehicles" in _ex and "bees" in _ex, str(_ex))
T("F1a manner phrases are not topic exclusions ('not too long')",
  tl.parse_exclusions("make a documentary about the moon, "
                       "not too long") == [])


def _outline_json(title):
    return json.dumps({"title": title, "chapters": [
        {"title": "One", "brief": "first part", "minutes": 1},
        {"title": "Two", "brief": "second part", "minutes": 1}]})


_picks = {"n": 0}


def _chat_repick(messages):
    _picks["n"] += 1
    if _picks["n"] == 1:
        return _outline_json("The Rise of Electric Cars")
    return _outline_json("The Hidden Life of Urban Bees")


_out = long_video.outline(
    "topic AUTO, long documentary", _chat_repick, target_minutes=2,
    topic_history=["The Rise of Electric Vehicles"],
    exclusions=["electric vehicles"])
T("F1a a colliding AUTO pick is rejected and re-picked",
  _out["title"] == "The Hidden Life of Urban Bees"
  and _picks["n"] == 2, str(_out)[:200])

try:
    long_video.outline(
        "topic AUTO, long documentary",
        lambda m: _outline_json("Electric Cars Forever"),
        target_minutes=2,
        topic_history=["The Rise of Electric Vehicles"],
        exclusions=[])
    _raised = ""
except ValueError as e:
    _raised = str(e)
T("F1a when every pick collides the conflict is stated plainly",
  "TOPIC LOCK" in _raised, _raised[:200])

_out2 = long_video.outline(
    "a documentary about electric vehicles",
    lambda m: _outline_json("The Rise of Electric Cars"),
    target_minutes=2,
    topic_history=["The Rise of Electric Vehicles"],
    exclusions=[])
T("F1a an explicitly ordered topic is NOT history-blocked",
  _out2["title"] == "The Rise of Electric Cars")

# ================= Fix 1b: compliance topic verdict =================
import compliance as comp

_SPEC_AUTO = [{"id": "R1", "type": "topic",
               "value": "AUTO (choose strong documentary subject)",
               "quote": "topic AUTO"}]
_v = comp.requirement_verdicts(
    _SPEC_AUTO, {}, {"title": "The Rise of Electric Cars",
                     "topic": "electric cars",
                     "topic_history": ["The Rise of Electric Vehicles"],
                     "topic_exclusions": ["electric vehicles"]}, {})
T("F1b film 3's verdict is now FAIL (exclusion + repeat), not "
  "the word-match PASS",
  _v[0]["status"] == "FAIL" and "Electric Cars" in _v[0]["evidence"],
  str(_v))
_v = comp.requirement_verdicts(
    _SPEC_AUTO, {}, {"title": "The Hidden Life of Urban Bees",
                     "topic": "urban bees",
                     "topic_history": ["The Rise of Electric Vehicles"],
                     "topic_exclusions": ["electric vehicles"]}, {})
T("F1b a clean AUTO pick PASSes against history + exclusions",
  _v[0]["status"] == "PASS", str(_v))
_v = comp.requirement_verdicts(
    _SPEC_AUTO, {}, {"title": "The Hidden Life of Urban Bees",
                     "topic": "urban bees"}, {})
T("F1b an AUTO pick with nothing on record is UNVERIFIED",
  _v[0]["status"] == "UNVERIFIED", str(_v))
_v = comp.requirement_verdicts(
    [{"id": "R1", "type": "topic", "value": "electric vehicles",
      "quote": "electric vehicles"}], {},
    {"title": "The Rise of Electric Cars", "topic": "electric cars"},
    {})
T("F1b a concrete topic is covered via the synonym fold",
  _v[0]["status"] == "PASS", str(_v))
_v = comp.requirement_verdicts(
    [{"id": "R1", "type": "topic", "value": "the deep ocean",
      "quote": "the deep ocean"}], {},
    {"title": "The Rise of Electric Cars", "topic": "electric cars"},
    {})
T("F1b a concrete topic the film did not deliver FAILs",
  _v[0]["status"] == "FAIL", str(_v))

# ============ Fix 1c + 2 + 4 + 5: render_chapters rigs ============
import doc

_EV_OUTLINE = {"title": "The Rise of Electric Cars", "chapters": [
    {"title": "Why Electric Cars Won",
     "brief": "electric vehicles, batteries and charging reshape "
              "cities", "minutes": 2}]}
_EV_MAIN = [
    "Electric cars are quietly taking over city streets.",
    "Battery packs now store far more energy than a decade ago.",
    "Charging networks are spreading along every highway.",
]
_SEATBELT_TOPUP = [
    "Did you know most drivers wear their seatbelts wrong?",
    "A twisted lap belt can cause serious internal injuries.",
    "Seatbelt reminder alerts now chime in every new model.",
]
_EV_TOPUP = [
    "In Norway, electric cars took most new car sales last year.",
    "Oslo is replacing diesel buses with electric ones.",
    "Battery factories are hiring across three continents.",
]


def _run_chapters(ext_scenes, outline=_EV_OUTLINE, main_dur=59.0,
                  ext_gate=True, deadline=None, ext_dur=60.0):
    orig_mv, orig_join = doc.make_video, long_video._join_clips
    orig_probe = long_video._probe_duration
    joins = {"n": 0}

    async def _mv(brief, chat, **kw):
        if "EXTENSION" in brief:
            plan = {"scenes": ext_scenes}
            if ext_gate:
                plan["fact_gate"] = dict(_FG)
            return {"path": "ext.mp4", "duration": ext_dur,
                    "compliance": {"checks": []}, "plan": plan}
        return {"path": "ch1.mp4", "duration": main_dur,
                "compliance": {"checks": []},
                "plan": {"fact_gate": dict(_FG),
                         "scenes": [{"vo": v} for v in _EV_MAIN]}}

    def _fake_join(paths, out):
        joins["n"] += 1
        return out

    doc.make_video = _mv
    long_video._join_clips = _fake_join
    long_video._probe_duration = lambda p: 119.0
    try:
        out = []
        wd = tempfile.mkdtemp(prefix="r4_ch_")
        asyncio.run(long_video.render_chapters(
            outline, lambda m: "{}", wd, results_out=out,
            deadline=deadline, spec=None, cfg={"kind": "long"}))
        return out, joins["n"]
    finally:
        doc.make_video = orig_mv
        long_video._join_clips = orig_join
        long_video._probe_duration = orig_probe


_res, _jn = _run_chapters([{"vo": v} for v in _SEATBELT_TOPUP])
T("F1c the seatbelt top-up is REJECTED as topic drift (no join)",
  _jn == 0 and _res and "topic drift" in str(
      _res[0].get("topup_rejected")), str(_res)[:300])
T("F1c the coherence report rides the chapter record",
  _res and (_res[0].get("topup_coherence") or {}).get("coherent")
  is False, str(_res)[:300])
_res, _jn = _run_chapters([{"vo": v} for v in _EV_TOPUP])
T("F1c an on-subject top-up joins as before",
  _jn == 1 and _res and _res[0].get("topped_up") is True,
  str(_res)[:300])
T("F2 every pass left a fact-gate event on the chapter record",
  _res and [p["pass"] for p in _res[0].get("fact_gate_passes") or []]
  == ["main", "topup"], str(_res)[:300])
_res, _jn = _run_chapters([{"vo": v} for v in _EV_TOPUP],
                          ext_gate=False)
T("F2 an UNGATED top-up never joins (fail closed at the join)",
  _jn == 0 and _res and "no fact-gate event" in str(
      _res[0].get("topup_rejected")), str(_res)[:300])

# ================= Fix 2: plan/make_video fail closed =================
import anti_boring
import research as _research_mod

_orig_fg, _orig_res = anti_boring.fact_gate, \
    _research_mod.build_research_record
anti_boring.fact_gate = lambda *a, **k: (_ for _ in ()).throw(
    RuntimeError("gate exploded"))
_research_mod.build_research_record = lambda topic: []
_PLAN_JSON = json.dumps({
    "title": "TEST FILM", "topic": "electric cars",
    "scenes": [{"vo": f"Scene {i} speaks plainly about cars.",
                "visual": "chat", "mood": "calm", "label": f"S{i}"}
               for i in range(4)]})
try:
    doc.plan("Long video 'X', chapter 1 of 2: Cars.",
             lambda m: _PLAN_JSON, cfg={"kind": "long"})
    _plan_raise = ""
except RuntimeError as e:
    _plan_raise = str(e)
finally:
    anti_boring.fact_gate = _orig_fg
    _research_mod.build_research_record = _orig_res
T("F2 plan() fails closed when the gate cannot run (doc context)",
  "FACT GATE fail-closed" in _plan_raise, _plan_raise[:200])


async def _mv_override():
    return await doc.make_video(
        "Long video 'X', chapter 1 of 2: Cars.", lambda m: "{}",
        plan_override={"title": "X", "scenes": [], "topic": "cars"},
        cfg={"kind": "long"})


try:
    asyncio.run(_mv_override())
    _mv_raise = ""
except RuntimeError as e:
    _mv_raise = str(e)
T("F2 make_video refuses a plan_override with no gate event",
  "FACT GATE fail-closed" in _mv_raise, _mv_raise[:200])

# ================= Fix 3: verifier decisiveness =================
import broll_verify

_td = tempfile.mkdtemp(prefix="r4_vis_")
_clip = os.path.join(_td, "clip.mp4")
subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
     "-i", "testsrc=size=320x180:rate=10:duration=2",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", _clip],
    check=True)

_calls = {"n": 0}


def _verdict_stub(seq):
    def v(frames, narration, why, forced=False):
        _calls["n"] += 1
        return seq[min(_calls["n"] - 1, len(seq) - 1)]
    return v


_calls["n"] = 0
_ver = broll_verify.BrollVerifier(
    call_budget=10,
    verifier=_verdict_stub([{"verdict": "uncertain", "reason": "?"},
                            {"verdict": "pass", "reason": "matches"}]))
_v, _r, _c = _ver.verify_candidate(
    {"id": "c1", "path": _clip}, "electric cars in the city",
    "electric cars", workdir=_td)
T("F3 an uncertain verdict is retried forced-choice and resolves",
  _v == "pass" and _ver.forced_retries == 1 and _ver.decisive == 1,
  f"{_v} / {_r}")

_calls["n"] = 0
_ver = broll_verify.BrollVerifier(
    call_budget=10,
    verifier=_verdict_stub([{"verdict": "uncertain", "reason": "?"}]))
_v, _r, _c = _ver.verify_candidate(
    {"id": "c2", "path": _clip}, "a line about nothing in frame",
    "nothing", workdir=_td)
T("F3 still-no-choice after the retry is UNDECIDED, not a keep",
  _v == "undecided" and _ver.undecided == 1, f"{_v} / {_r}")

_ver = broll_verify.BrollVerifier(
    call_budget=10,
    verifier=lambda frames, n, w: {"verdict": "uncertain",
                                   "reason": "stub"})
_v, _r, _c = _ver.verify_candidate(
    {"id": "c3", "path": _clip}, "another line", "another",
    workdir=_td)
T("F3 a 3-arg (pre-forced-mode) verifier still resolves undecided",
  _v == "undecided", f"{_v} / {_r}")

_ver = broll_verify.BrollVerifier(
    call_budget=20,
    verifier=_verdict_stub([{"verdict": "uncertain", "reason": "?"}]))
for _i in range(3):
    _ver.verify_candidate({"id": f"u{_i}", "path": _clip},
                          f"line number {_i} unique", "q",
                          workdir=_td)
_rep = _ver.report()
T("F3 >50% undecided is declared an outage in the report",
  _rep["outage"] is True and "INDECISIVE" in _rep.get("note", "")
  and _rep["undecided"] == 3, str(_rep))

# ================= Fix 4: chapter throughput cap =================
_SHARE_OUTLINE = {"title": "Three Chapters", "chapters": [
    {"title": f"C{i + 1}", "brief": "a chapter", "minutes": 1}
    for i in range(3)]}
_ext_calls = {"n": 0}


def _run_shares():
    orig_mv = doc.make_video
    orig_probe = long_video._probe_duration

    async def _mv(brief, chat, **kw):
        if "EXTENSION" in brief:
            if "chapter 1 of 3" in brief:
                _ext_calls["n"] += 1
            return {"path": "ext.mp4", "duration": 30.0,
                    "compliance": {"checks": []},
                    "plan": {"fact_gate": dict(_FG), "scenes": []}}
        if "chapter 1 of 3" in brief:
            await asyncio.sleep(1.2)  # chapter 1 eats past its share
        return {"path": "ch.mp4", "duration": 30.0,
                "compliance": {"checks": []},
                "plan": {"fact_gate": dict(_FG), "scenes": []}}

    doc.make_video = _mv
    long_video._probe_duration = lambda p: 30.0
    try:
        out = []
        wd = tempfile.mkdtemp(prefix="r4_sh_")
        asyncio.run(long_video.render_chapters(
            _SHARE_OUTLINE, lambda m: "{}", wd, results_out=out,
            deadline=time.monotonic() + 3.0,
            spec=None, cfg={"kind": "long"}))
        return out
    finally:
        doc.make_video = orig_mv
        long_video._probe_duration = orig_probe


_res = _run_shares()
T("F4 every chapter is attempted even when chapter 1 overspends",
  len(_res) == 3, f"{len(_res)} chapters")
T("F4 chapter 1's top-up is skipped once its share is spent",
  _ext_calls["n"] == 0 and not _res[0].get("topped_up"),
  str(_res[0])[:200])
T("F4 the chapter budget share is recorded (remaining / chapters "
  "left)", _res and abs(
      (_res[0].get("chapter_budget") or {}).get("share_s", 0) - 1.0)
  < 0.3, str(_res[0].get("chapter_budget")))

# ================= Fix 5: depiction counter =================
import depiction_qc as dq

T("F5 a source-backed beat is evidence",
  dq.classify_beat({"vo": "x", "visual": "chat",
                    "source_ref": "Electric car"}) == "evidence")
T("F5 a data visual carrying a spoken number is evidence",
  dq.classify_beat({"vo": "Sales rose 40 percent last year.",
                    "visual": "counter", "value": "40"}) == "evidence")
T("F5 footage whose queries name the line's subject is literal",
  dq.classify_beat({"vo": "Electric cars glide through the city.",
                    "visual": "chat", "has_footage": True,
                    "queries": ["electric cars city streets"]})
  == "literal")
T("F5 footage barely touching the line is context",
  dq.classify_beat({"vo": "Nobody saw the change coming.",
                    "visual": "chat", "has_footage": True,
                    "queries": ["aerial coastline waves"]})
  == "context")
T("F5 a symbolic visual is metaphor",
  dq.classify_beat({"vo": "The warning signs were everywhere.",
                    "visual": "icon_row"}) == "metaphor")
T("F5 a bare script scene is unclassifiable (excluded, not "
  "counted)", dq.classify_beat({"vo": "just words"}) is None)

_LIT = [{"vo": "Electric cars glide through city streets.",
         "visual": "chat", "has_footage": True,
         "queries": ["electric cars city"]} for _ in range(6)]
_rep = dq.depiction_report(_LIT)
T("F5 an all-literal chapter is over budget and FAILs",
  _rep["over_budget"] and _rep["literal_share"] == 1.0
  and dq.depiction_checks(_LIT)[0]["rule"] == "DEPICTION",
  str(_rep))
_MIX = _LIT[:1] + [
    {"vo": "Sales rose 40 percent.", "visual": "counter",
     "value": "40"},
    {"vo": "The mood shifted.", "visual": "icon_row"},
    {"vo": "Nobody saw it coming.", "visual": "chat",
     "has_footage": True, "queries": ["aerial coastline"]},
    {"vo": "A study counted the cost.", "visual": "chat",
     "source_ref": "Some Study"},
]
_rep = dq.depiction_report(_MIX)
T("F5 a mixed chapter at 20% literal is inside budget",
  not _rep["over_budget"] and _rep["literal_share"] == 0.2,
  str(_rep))


def _run_depiction():
    orig_mv = doc.make_video
    orig_probe = long_video._probe_duration
    calls = {"n": 0}

    async def _mv(brief, chat, **kw):
        calls["n"] += 1
        return {"path": "ch.mp4", "duration": 60.0,
                "compliance": {"checks": []},
                "plan": {"fact_gate": dict(_FG),
                         "scenes": [dict(s) for s in _LIT]}}

    doc.make_video = _mv
    long_video._probe_duration = lambda p: 60.0
    try:
        out = []
        wd = tempfile.mkdtemp(prefix="r4_dep_")
        asyncio.run(long_video.render_chapters(
            {"title": "T", "chapters": [
                {"title": "C1", "brief": "the only chapter",
                 "minutes": 1}]},
            lambda m: "{}", wd, results_out=out,
            spec=None, cfg={"kind": "long"}))
        return out, calls["n"]
    finally:
        doc.make_video = orig_mv
        long_video._probe_duration = orig_probe


_res, _ncalls = _run_depiction()
_dep_failed = [c for c in (_res[0].get("compliance") or {})
               .get("checks") or [] if c.get("rule") == "DEPICTION"
               and c.get("status") == "FAIL"]
T("F5 the DEPICTION FAIL rides the fix loop (bounded rounds) "
  "and stays on the shipped chapter",
  _ncalls == 4 and _res[0].get("fix_rounds_used") == 3
  and len(_dep_failed) == 1
  and (_res[0].get("depiction") or {}).get("over_budget") is True,
  f"calls={_ncalls} res={str(_res)[:300]}")

# ================= Fix 6: frame_qc broadcast shapes =================
import numpy as np

_bg = doc._qc_bg_gray("calm", "A", None, (152, 270))
T("F6 a landscape frame's background is built at ITS shape",
  _bg.shape == (152, 270), str(_bg.shape))
_bg2 = doc._qc_bg_gray("calm", "A", None, (480, 270))
T("F6 a portrait frame's background keeps the portrait shape",
  _bg2.shape == (480, 270), str(_bg2.shape))
_frame = np.zeros((152, 270), dtype=np.float32)
_diff = float(np.abs(_frame - _bg).mean())
T("F6 frame-minus-background broadcasts cleanly (the old crash)",
  _diff >= 0.0)

_td6 = tempfile.mkdtemp(prefix="r4_fq_")
_vid6 = os.path.join(_td6, "land.mp4")
subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
     "-i", "color=c=navy:s=320x180:d=1", "-pix_fmt", "yuv420p",
     _vid6], check=True)
_orig_sf, _orig_qa, _orig_qg = doc.scene_frame, doc._qc_audit, \
    doc._qc_geometry
doc.scene_frame = lambda *a, **k: (
    None, (10, 10, 60, 60), (10, 80, 60, 100), None, None)
doc._qc_audit = lambda sc, i: []
doc._qc_geometry = lambda *a, **k: ([], [])
try:
    _fq = doc.frame_qc(
        {"scenes": [{"vo": "A line.", "mood": "calm",
                     "visual": "chat", "d": 1.0, "label": "LINE"}],
         "look": "A", "starts": [0.0]}, _vid6, _td6)
finally:
    doc.scene_frame, doc._qc_audit, doc._qc_geometry = \
        _orig_sf, _orig_qa, _orig_qg
T("F6 frame_qc on a LANDSCAPE film has no broadcast flaw",
  not any("broadcast" in f for f in _fq["flaws"]),
  str(_fq["flaws"])[:300])

# ================= Fix 7: pack integrity =================
import visual_director as VD

_pack = VD.taste_pack()
T("F7 the pack loads in full (head + tail markers, sane band)",
  _pack.startswith("# JULIE TASTE PACK")
  and "Post-film self-grade" in _pack[-600:]
  and "delivery note." in _pack[-200:]
  and 40000 <= len(_pack) <= 120000, f"{len(_pack)} chars")

# ================= Fold-in: packaging grades the film =================
import packaging as pkg

_pkg = pkg.build_packaging(
    "Auto", "The Rise of Electric Cars: Revolution on Wheels",
    [{"title": "The Shift", "start_s": 0, "end_s": 100}],
    duration=100)
T("P1 packaging with an AUTO topic grades the DELIVERED title",
  "Auto" not in _pkg["chosen_pair"]["title"]
  and _pkg["topic"] == "The Rise of Electric Cars: "
  "Revolution on Wheels", str(_pkg["chosen_pair"]))

print(f"\nround4test: {len(fails)} failed")
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("round4test: ALL PASS")
