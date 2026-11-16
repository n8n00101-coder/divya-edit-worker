#!/usr/bin/env python3
"""ROUND-5 tests — one block per fix from Ajju's rejection of the
third film (phone screenshots, 2026-11-16 ~22:01 IST: still
boring, no edits/VFX/animation/transitions, visuals STRETCHED,
stale "DIVYA" end card, a cartoon avatar card over a road shot,
"director sariga work avvatledhu").

Fix 1: DIRECTOR NO-SILENT-FALLBACK — per-chapter ledger windows,
       DIR-FALLBACK is boring-critical and rides the fix loop; a
       fix round clears it only when the brain stage really ran;
       taste-QC UNVERIFIED surfaces in the delivery summary data.
Fix 2: REAL MOTION IN HYPERFRAMES — plan transitions map to real
       xfades (duration-compensated), the pixel motion audit
       flags static beats, and the widget counter may only print
       numbers/percent the spoken line actually speaks.
Fix 3: FOOTAGE MOTION TREATMENT — stills and measured-static
       clips get a keyframed push-in; accent beats get a
       speedramp accent; treatments are logged.
Fix 4: STRETCH — fit helpers preserve aspect; the HF swap fits
       crop-to-fill (a round marker stays round).
Fix 5: BRANDING — the outro draws JULIE; a scan of the render
       path finds no user-facing DIVYA brand string.
Fix 6: AVATAR GATE — polaroid placeholder flagged by the audit,
       stripped at plan level, blocked in the render chain for
       faceless longs (and still allowed for shorts).

Run: python3 round5test.py
"""
import asyncio
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def T(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name
          + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


WD = tempfile.mkdtemp(prefix="round5_", dir=os.path.expanduser("~/workspace"))


def _mkclip(name, lavfi, dur=3.0):
    out = os.path.join(WD, name)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", lavfi, "-t", str(dur),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
                   check=True)
    return out


MOVING = _mkclip("moving.mp4", "testsrc2=size=320x180:rate=30")
STATIC = _mkclip("static.mp4", "color=c=red:size=320x180:rate=30")
RAW = _mkclip("raw.mp4", "testsrc2=size=320x180:rate=30", dur=6.0)

# ================= Fix 1: brain ledger windows =================
import brain_status as bs

bs.reset()
m0 = bs.mark()
bs.record("editing-director", False, "channel")
bs.record("visual-director", True, "")
m1 = bs.mark()
bs.record("editing-director", True, "")
T("F1 ledger: fallback_stages_since sees the window's fallback",
  bs.fallback_stages_since(m0, stages=("editing-director",
                                        "visual-director"))
  == ["editing-director"])
T("F1 ledger: a later OK does not resurrect the stage in a "
  "fresh window", bs.fallback_stages_since(m1) == [])
T("F1 ledger: outcomes_since reports the last outcome per stage",
  bs.outcomes_since(m0)["editing-director"]["status"] == "OK"
  and bs.outcomes_since(m0)["visual-director"]["status"] == "OK")
bs.reset()

import anti_boring as ab

T("F1 DIR-FALLBACK / MOTION-STATIC / PRESENTER-CARD are "
  "boring-critical",
  {"DIR-FALLBACK", "MOTION-STATIC", "PRESENTER-CARD"}
  <= ab.BORING_CRITICAL_RULES
  and len(ab.boring_critical_fails(
      [{"rule": "DIR-FALLBACK", "status": "FAIL"},
       {"rule": "R6", "status": "FAIL"}])) == 1)

# ---- render_chapters integration with a stubbed make_video ----
import doc
import long_video

_OUTLINE = {"title": "T", "chapters": [
    {"title": "C1", "brief": "the only chapter", "minutes": 1}]}


def _run_chapters(stub, results_out):
    orig = doc.make_video
    doc.make_video = stub
    try:
        wd = tempfile.mkdtemp(prefix="r5ch_", dir=WD)
        asyncio.run(long_video.render_chapters(
            _OUTLINE, lambda m: "{}", wd, results_out=results_out,
            spec=None, cfg={"kind": "long"}))
        return results_out
    finally:
        doc.make_video = orig


def _clean_res():
    # the plan carries a fact-gate event, as doc.make_video's
    # documentary path always produces (round 4's fail-closed
    # rule rejects a fix pass without one)
    return {"path": "ch.mp4", "duration": 60.0,
            "compliance": {"checks": []},
            "plan": {"scenes": [],
                     "fact_gate": {"claims": 0, "rewrite_round": False,
                                   "removed": [], "dropped_scenes": []}}}


# Scenario A: main pass falls back, the fix round's director runs.
_callsA = {"n": 0}


async def _mv_A(brief, chat, **kw):
    _callsA["n"] += 1
    if _callsA["n"] == 1:
        bs.record("editing-director", False, "channel")
    else:
        bs.record("editing-director", True, "")
    return _clean_res()


bs.reset()
_resA = _run_chapters(_mv_A, [])
T("F1 fix round re-ran the brain director and cleared the "
  "fallback", _callsA["n"] == 2 and _resA
  and not _resA[0].get("director_fallback")
  and not _resA[0].get("director_fallback_final")
  and not [c for c in (_resA[0].get("compliance") or {})
           .get("checks") or [] if c.get("rule") == "DIR-FALLBACK"],
  f"calls={_callsA['n']} res={_resA}")

# Scenario B: every pass falls back — the label must survive.
_callsB = {"n": 0}


async def _mv_B(brief, chat, **kw):
    _callsB["n"] += 1
    bs.record("editing-director", False, "channel")
    bs.record("visual-director", False, "channel")
    return _clean_res()


bs.reset()
_resB = _run_chapters(_mv_B, [])
T("F1 persistent fallback stays labelled after the fix rounds",
  _callsB["n"] == 4 and _resB
  and _resB[0].get("director_fallback_final") is True
  and {tuple(sorted(_resB[0]["director_fallback"]["stages"]))}
  == {("editing-director", "visual-director")}
  and any(c.get("rule") == "DIR-FALLBACK"
          for c in (_resB[0].get("compliance") or {})
          .get("checks") or []),
  f"calls={_callsB['n']} res={_resB}")

# Scenario C: the director runs — no label, no fix rounds.
_callsC = {"n": 0}


async def _mv_C(brief, chat, **kw):
    _callsC["n"] += 1
    bs.record("editing-director", True, "")
    return _clean_res()


bs.reset()
_resC = _run_chapters(_mv_C, [])
T("F1 a directed chapter needs no fix round and carries no label",
  _callsC["n"] == 1 and _resC
  and not _resC[0].get("director_fallback_final"),
  f"calls={_callsC['n']}")
bs.reset()

T("F1 fix guidance names the director failure",
  any("DIRECTOR" in g for g in long_video._fix_guidance100(
      [{"rule": "DIR-FALLBACK", "status": "FAIL"}])))

# ================= Fix 2: transitions + motion audit + counter ==
import hf_primary
import motion_audit

T("F2 plan transition names map to real xfades",
  hf_primary._xfade_for("dip_to_black", 3, []) == "fadeblack"
  and hf_primary._xfade_for("slide", 3, []) == "slideleft"
  and hf_primary._xfade_for("zoom_in", 3, []) == "zoomin"
  and hf_primary._xfade_for("crossfade", 3, []) == "fade")
T("F2 rule defaults: dip-in open, dissolve into data, never "
  "an unnamed hard cut",
  hf_primary._xfade_for("", 0, ["title"]) == "fadeblack"
  and hf_primary._xfade_for(None, 2, ["data_chart"]) == "dissolve"
  and hf_primary._xfade_for("cut", 1, ["lower_third"])
  in hf_primary._XFADE_OK)

# swap with transitions keeps the chapter's total duration
spans = [(1.0, 2.0, MOVING), (4.0, 1.5, MOVING)]
out_swap = os.path.join(WD, "swapped.mp4")
ok = hf_primary.swap_spans(RAW, spans, out_swap, 320, 180,
                           transitions=["fadeblack", "dissolve"])
dur = hf_primary._probe_duration(out_swap) if ok else 0
T("F2 xfade swap preserves total duration (voice sync)",
  ok and abs(dur - 6.0) < 0.25, f"dur={dur}")

# the pixel motion audit: a solid-colour beat is a static card,
# a testsrc beat moves
_aud_s = motion_audit.audit_video(
    STATIC, [{"scene": 1, "start": 0.0, "duration": 2.5}])
_aud_m = motion_audit.audit_video(
    MOVING, [{"scene": 1, "start": 0.0, "duration": 2.5}])
T("F2 motion audit flags the static beat and passes the "
  "moving one", _aud_s["static_beats"] == [1]
  and _aud_m["static_beats"] == []
  and _aud_s["static_share"] == 1.0,
  f"static={_aud_s} moving={_aud_m}")
_cm = motion_audit.clip_motion(STATIC, 0, 2.5)
T("F2 clip_motion measures a static source clip as static",
  _cm["static"] is True, str(_cm))

# ---- the widget counter: only spoken numbers / percents ----
import create as _create
from PIL import Image, ImageDraw

_drawn = []
_orig_ct = _create.center_text
_create.center_text = lambda d, y, text, f, fill: _drawn.append(text)
try:
    _img = Image.new("RGB", (200, 200))
    _d = ImageDraw.Draw(_img)
    _drawn.clear()
    _create.draw_visual(_d, _img, "counter", "1200%", 1.0,
                        vo="About 1,200 preventable deaths in "
                           "the US alone")
    T("F2 counter: an unspoken % is never printed (film 3's "
      "'1200%')", _drawn and all("%" not in t for t in _drawn),
      str(_drawn))
    _drawn.clear()
    _create.draw_visual(_d, _img, "counter", "45%", 1.0,
                        vo="It rose by 45 percent this year")
    T("F2 counter: a spoken percent still prints",
      any("%" in t for t in _drawn), str(_drawn))
    _drawn.clear()
    _create.draw_visual(_d, _img, "counter", "900", 1.0,
                        vo="Nothing numeric is said in this line")
    T("F2 counter: an unspoken number is not headlined",
      _drawn == [], str(_drawn))
    _drawn.clear()
    _create.draw_visual(_d, _img, "bar", "80", 1.0,
                        vo="Most drivers wear them wrong")
    T("F2 bar: no % label when the line speaks no percent",
      all("%" not in t for t in _drawn), str(_drawn))
finally:
    _create.center_text = _orig_ct

# ================= Fix 3: footage motion treatments ============
from PIL import Image as _Im

_still = os.path.join(WD, "still.jpg")
_Im.new("RGB", (640, 360), (90, 120, 160)).save(_still)


class _Pool:
    def __init__(self, path):
        self.assignments = [{"scene": 1, "path": path, "start": 0.0}]


_plan = {"topic": "Roads", "title": "ROADS", "starts": [0.0],
         "_footage_pool": _Pool(_still),
         "scenes": [{"vo": "The road ahead is still being built.",
                     "label": "THE ROAD AHEAD", "d": 3.0}]}
_beats, _rep = hf_primary.plan_beats(
    _plan, WD, {"kind": "long", "width": 320, "height": 180})
T("F3 a still-image beat gets a push-in treatment, logged",
  _beats and _beats[0]["treatment"]["kind"] == "push_in"
  and _rep["motion_treatments"]
  and _rep["motion_treatments"][0]["source"] == "still",
  str(_rep)[:200])
_comp = ""
if _beats:
    _cdir = os.path.join(_beats[0]["project_dir"], "compositions")
    for _f in os.listdir(_cdir):
        _comp += open(os.path.join(_cdir, _f)).read()
T("F3 the composition keyframes the media element itself",
  "#s1-media" in _comp and "scale: 1.14" in _comp,
  _comp[:200])

_failures = []
_tr = hf_primary._treat_beat({}, STATIC, 0.0, 2.5,
                             os.path.join(WD, "tb1"), 5,
                             [{"type": "lower_third"}], _failures)
T("F3 a measured-static clip gets a push-in",
  _tr[0] and _tr[0]["kind"] == "push_in"
  and _tr[0]["source"] == "static_clip", str(_tr))
_tr2 = hf_primary._treat_beat({}, MOVING, 0.0, 2.5,
                              os.path.join(WD, "tb2"), 5,
                              [{"type": "lower_third"}], _failures)
T("F3 a moving clip needs no treatment",
  _tr2[0] is None and _tr2[1] is None, str(_tr2))
_tr3 = hf_primary._treat_beat({"_effect_choice": {"shake_at": 0.5}},
                              MOVING, 0.0, 2.5,
                              os.path.join(WD, "tb3"), 5,
                              [{"type": "lower_third"}], _failures)
T("F3 an accent beat gets a rendered speedramp accent",
  _tr3[0] and _tr3[0]["kind"] == "speed_accent"
  and os.path.isfile(_tr3[2]), str(_tr3))

# ================= Fix 4: stretch ==============================
import doc as _doc
import numpy as _np

_src = _Im.new("RGBA", (100, 200), (0, 0, 0, 0))
_ds = ImageDraw.Draw(_src)
_ds.rectangle([40, 90, 60, 110], fill=(255, 255, 255, 255))
_cov = _doc.fit_cover(_src, 400, 200)
_arr = _np.asarray(_cov.convert("L"))
_ys, _xs = _np.where(_arr > 128)
_ratio = ((_xs.max() - _xs.min() + 1) / (_ys.max() - _ys.min() + 1)
          ) if len(_xs) else 0
T("F4 fit_cover keeps a square marker square (no stretch)",
  _cov.size == (400, 200) and 0.8 < _ratio < 1.25,
  f"size={_cov.size} ratio={_ratio}")
_ins = _doc.fit_inside_canvas(_src, 400, 200)
_ibb = _ins.getbbox()
T("F4 fit_inside_canvas preserves aspect inside the canvas",
  _ins.size == (400, 200) and _ibb is not None
  and (_ibb[2] - _ibb[0]) == (_ibb[3] - _ibb[1]) == 21,
  f"bbox={_ibb}")

# geometry through the real swap: a round marker in a SQUARE
# clip must stay round on the 320x180 canvas (crop-to-fill),
# where a stretch fit would flatten it to a 1.78 ellipse.
_sq = _Im.new("RGB", (200, 200), (0, 0, 0))
_dsq = ImageDraw.Draw(_sq)
_dsq.ellipse([60, 60, 140, 140], fill=(255, 255, 255))
_sqpng = os.path.join(WD, "sq.png")
_sq.save(_sqpng)
_sqclip = os.path.join(WD, "sq.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1",
                "-i", _sqpng, "-t", "3", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", _sqclip], check=True)
_geo_out = os.path.join(WD, "geo.mp4")
hf_primary.swap_spans(RAW, [(0.5, 2.5, _sqclip)], _geo_out, 320, 180,
                      transitions=["fade"])
_fr = os.path.join(WD, "geo_frame.png")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.7",
                "-i", _geo_out, "-frames:v", "1", _fr], check=True)
_garr = _np.asarray(_Im.open(_fr).convert("L"))
_gys, _gxs = _np.where(_garr > 128)
_gratio = ((_gxs.max() - _gxs.min() + 1) / (_gys.max() - _gys.min() + 1)
           ) if len(_gxs) else 0
T("F4 swap fits crop-to-fill: the circle stays a circle",
  0.75 < _gratio < 1.33, f"ratio={_gratio}")

# ================= Fix 5: branding =============================
import re as _re

_drawn5 = []
_orig_draw = ImageDraw.Draw


class _RecDraw:
    def __init__(self, im):
        self._real = _orig_draw(im)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def text(self, xy, s, **kw):
        _drawn5.append(str(s))
        return self._real.text(xy, s, **kw)

    def textlength(self, s, **kw):
        return self._real.textlength(s, **kw)


_orig_bg = _doc.background
_doc.background = lambda mood, look=None, section=None: \
    _Im.new("RGB", (_doc.W, _doc.H), (10, 10, 20))
ImageDraw.Draw = _RecDraw
try:
    _plan5 = {"scenes": [{"mood": "calm", "section": None}],
              "look": None, "accent": (255, 200, 0),
              "end_question": "READY FOR THE NEXT TWIST?"}
    _doc.outro(_plan5, 0.6)
finally:
    ImageDraw.Draw = _orig_draw
    _doc.background = _orig_bg
T("F5 the end card brands JULIE, never DIVYA",
  any(t == "JULIE" for t in _drawn5)
  and not any("DIVYA" in t for t in _drawn5), str(_drawn5))

_ALLOW = _re.compile(r"DIVYA_[A-Z_]+|divya_doc|DIVYA \(|# DIVYA")
_bad = []
for _mod in ("doc.py", "create.py", "long_video.py", "hf_primary.py",
             "hyperframes_codegen.py", "compliance.py", "packaging.py",
             "visuals_lib.py"):
    for _ln, _line in enumerate(
            open(os.path.join(HERE, _mod), encoding="utf-8"), 1):
        if "DIVYA" in _line and not _ALLOW.search(_line):
            _bad.append(f"{_mod}:{_ln}: {_line.strip()[:80]}")
T("F5 no user-facing DIVYA brand string in the render path "
  "(infra names only, allowlisted)", not _bad, "; ".join(_bad[:5]))

# ================= Fix 6: presenter / avatar gate ==============
_scenes6 = [{"lib_visual": "polaroid"},
            {"visual": "polaroid"},
            {"lib_visual": "card"},
            {"lib_visual": "polaroid", "photo": _still}]
_flags6 = motion_audit.presenter_flags(
    _scenes6, presenter_allowed=False,
    mapped=_doc._VIS_NAME_MAP)
T("F6 the audit flags polaroid placeholders (lib + mapped), "
  "not real photos or other visuals",
  [f["scene"] for f in _flags6] == [1, 2], str(_flags6))
T("F6 an explicit presenter request allows the card",
  motion_audit.presenter_flags(
      _scenes6, presenter_allowed=True,
      mapped=_doc._VIS_NAME_MAP) == [])

# render-chain gate: draw_scene_visual must not call the
# polaroid visual for a faceless long, and must still call it
# for a short
import visuals_lib as _VL

_calls6 = {"n": 0}


def _spy_polaroid(t, st=0, d=1.0, accent=None, words=None, **kw):
    _calls6["n"] += 1
    return _Im.new("RGBA", (720, 1280), (0, 0, 0, 0))


_orig_pol = _VL.VIS["polaroid"]
_VL.VIS["polaroid"] = _spy_polaroid
try:
    _vlay = _Im.new("RGBA", (_doc.W, _doc.H), (0, 0, 0, 0))
    _vd = ImageDraw.Draw(_vlay)
    _sc6 = {"lib_visual": "polaroid", "visual": "card", "d": 3.0,
            "vo": "The road ahead is still being built."}
    _doc.draw_scene_visual(_vd, _vlay,
                           {"render_config": {"kind": "long"},
                            "topic": "Roads"},
                           0, _sc6, 0.5, 800, (255, 200, 0))
    _long_calls = _calls6["n"]
    _doc.draw_scene_visual(_vd, _vlay,
                           {"render_config": {"kind": "short"},
                            "topic": "Roads"},
                           0, dict(_sc6), 0.5, 800, (255, 200, 0))
    _short_calls = _calls6["n"]
finally:
    _VL.VIS["polaroid"] = _orig_pol
T("F6 render chain: polaroid blocked in a faceless long, "
  "allowed in a short", _long_calls == 0 and _short_calls == 1,
  f"long={_long_calls} short={_short_calls}")

_checks6, _info6 = long_video._round5_checks(
    {"plan": {"scenes": [{"lib_visual": "polaroid"}],
              "hyperframes_primary": {
                  "motion_audit": {"static_beats": [2]}}}})
T("F6+F2 the chapter audit emits PRESENTER-CARD and "
  "MOTION-STATIC checks",
  {c["rule"] for c in _checks6}
  == {"PRESENTER-CARD", "MOTION-STATIC"}, str(_checks6))

print()
if fails:
    print(f"ROUND5: {len(fails)} FAIL(s): {fails}")
    sys.exit(1)
print("ROUND5: ALL PASS")
