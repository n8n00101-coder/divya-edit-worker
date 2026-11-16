#!/usr/bin/env python3
"""NEXT-ROUND tests — one block per fix from the second film's QC
("The Rise of Electric Vehicles", job df871e60).

Fix 1: top-up restatement — the v100 4-gram novelty gate scored
       the film's paraphrase top-up 0.0; the semantic restatement
       report now sits on the same render_chapters path.
Fix 2: broll vision verifier bytes bug + outage surfacing.
Fix 3: HyperFrames text whitelist (viewer-facing text only).
Fix 4: fact-gate number sanity (value + unit + basis).
Fix 5: channel fail-fast (leg subordinated), key wiring (Worker
       harness in rig-nextround/), single-provider warning.

Run: python3 nextroundtest.py
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def T(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name
          + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ================= Fix 1: top-up restatement =================
import anti_boring as ab

# The second film's chapter 1 (pass 1) and its top-up (pass 2),
# from the delivered film's transcript.
OLD_VO = [
    "Electric cars are humming through city streets, like a quiet "
    "storm, but why this sudden surge?",
    "Around 2010, a widely available electric vehicle entered "
    "mass production, drawing notable public attention.",
    "Battery costs have reportedly declined substantially over "
    "recent years, contributing to the recent surge in electric "
    "vehicle sales.",
    "And governments worldwide now offer hefty tax breaks, making "
    "EVs cheaper than gas cars.",
    "Still, skeptics point to range anxiety and charging times "
    "as barriers.",
    "Yet, every mile driven by an EV cut CO2 by about 2.5 kg.",
    "A tiny but significant step.",
    "The Silent Revolution is not just about cars, it is "
    "reshaping cities, jobs and energy grids.",
    "So, as the roads fill with silent power, the next chapter "
    "asks, how will this change our future?",
]
FILM_TOPUP = [
    "The Silent Revolution is speeding past us, electric.",
    "Cars are flooding the streets.",
    "Today that number has risen significantly.",
    "Batteries have become cheaper and lighter, improving their "
    "range.",
    "Governments worldwide are adding incentives, tax cuts, "
    "free parking and zero emission zones.",
    "Automakers are racing to launch new models, each promising "
    "faster charging and smarter tech.",
    "But the transition is not smooth, charging infrastructure "
    "still lags in many regions.",
    "The momentum is undeniable, electric cars are expected to "
    "capture a growing share of traffic in the coming decade.",
]
NOVEL_TOPUP = [
    "In Norway, electric cars took 82 percent of new car sales "
    "in 2023.",
    "Oslo is replacing diesel buses with electric ones on every "
    "city route.",
    "Battery recycling plants now recover lithium from old packs "
    "for new cells.",
]

rep = ab.restatement_report(FILM_TOPUP, OLD_VO)
T("F1 the film's paraphrase top-up IS a restatement",
  rep["restatement"], str(rep))
T("F1 the 4-gram gate alone scored it 0.0 (the old blind spot)",
  ab.novelty_report(FILM_TOPUP, OLD_VO)["novel"])
rep = ab.restatement_report(NOVEL_TOPUP, OLD_VO)
T("F1 a top-up with new facts/places is NOT a restatement",
  not rep["restatement"] and rep["new_fact"], str(rep))
rep = ab.restatement_report(
    ["Zebra yachts xavier william victor uniform tango sierra "
     "romeo quebec papa."], [OLD_VO[0]])
T("F1 disjoint material is NOT a restatement",
  not rep["restatement"], str(rep))

# --- through the real render_chapters top-up path (v100test rig)
import doc
import long_video

_OUTLINE = {"title": "T", "chapters": [
    {"title": "C1", "brief": "the only chapter", "minutes": 2}]}
_joins = {"n": 0}


def _run_topup(ext_vo_list):
    orig_mv, orig_join = doc.make_video, long_video._join_clips
    orig_probe = long_video._probe_duration

    async def _mv(brief, chat, **kw):
        if "EXTENSION" in brief:
            return {"path": "ext.mp4", "duration": 43.0,
                    "compliance": {"checks": []},
                    "plan": {"scenes": [{"vo": v}
                                        for v in ext_vo_list]}}
        return {"path": "ch1.mp4", "duration": 59.0,
                "compliance": {"checks": []},
                "plan": {"scenes": [{"vo": v} for v in OLD_VO]}}

    def _fake_join(paths, out):
        _joins["n"] += 1
        return out

    doc.make_video = _mv
    long_video._join_clips = _fake_join
    long_video._probe_duration = lambda p: 102.0
    try:
        out = []
        wd = tempfile.mkdtemp(prefix="nr_tu_")
        asyncio.run(long_video.render_chapters(
            _OUTLINE, lambda m: "{}", wd, results_out=out,
            spec=None, cfg={"kind": "long"}))
        return out
    finally:
        doc.make_video = orig_mv
        long_video._join_clips = orig_join
        long_video._probe_duration = orig_probe


_joins["n"] = 0
_res = _run_topup(FILM_TOPUP)
T("F1 render_chapters REJECTS the film's top-up (no join, "
  "honest length flagged)",
  _joins["n"] == 0 and _res and _res[0].get("honest_length")
  is True and "paraphrase" in str(_res[0].get("topup_rejected")),
  str(_res)[:300])
T("F1 the rejection CITES the compression-pass rule (round 3)",
  _res and "compression pass" in str(
      _res[0].get("topup_rejected")).lower(), str(_res)[:300])
_joins["n"] = 0
_res = _run_topup(NOVEL_TOPUP)
T("F1 render_chapters ACCEPTS a genuinely novel top-up",
  _joins["n"] == 1 and _res and _res[0].get("topped_up") is True,
  str(_res)[:300])

# ================= Fix 4: fact-gate number sanity =================
EV_RECORD_LIFETIME = [{
    "title": "Electric car",
    "url": "https://en.wikipedia.org/wiki/Electric_car",
    "snippet": "Over its lifetime, an electric car saves about "
               "2.5 tonnes of CO2 compared with a petrol car, "
               "one widely cited estimate concludes."}]
EV_RECORD_PERMILE = [{
    "title": "Electric car",
    "url": "https://en.wikipedia.org/wiki/Electric_car",
    "snippet": "In this estimate, every mile driven by an EV "
               "cuts CO2 by about 2.5 kg per mile compared "
               "with petrol."}]
EV_RECORD_BASIS_ONLY = [{
    "title": "Electric car",
    "url": "https://en.wikipedia.org/wiki/Electric_car",
    "snippet": "An EV saves 2.5 kg of CO2 over its lifetime "
               "in this estimate."}]
FILM_CLAIM = {"vo": "Yet, every mile driven by an EV cuts CO2 "
                    "by about 2.5 kg.",
              "source_ref": "Electric car"}

claims = ab.scene_claims(FILM_CLAIM, EV_RECORD_LIFETIME)
T("F4 the film's exact claim vs its lifetime-basis source: "
  "UNRESOLVED", claims and not claims[0]["sourced"], str(claims))
claims = ab.scene_claims(FILM_CLAIM, EV_RECORD_PERMILE)
T("F4 a basis-matching source RESOLVES the same claim",
  claims and claims[0]["sourced"], str(claims))
claims = ab.scene_claims(FILM_CLAIM, EV_RECORD_BASIS_ONLY)
T("F4 same value + same unit, different basis: UNRESOLVED",
  claims and not claims[0]["sourced"], str(claims))

# gate integration: the unhedged version cannot ship
_unhedged = {"vo": "Every mile driven by an EV cuts CO2 by "
                   "2.5 kg per mile.",
             "source_ref": "Electric car"}
_fillers = [{"vo": f"Plain narration line number {i} about "
                   f"electric cars and city streets.",
             "label": f"S{i}", "d": 5} for i in range(4)]


def _echo_chat(messages):
    return json.dumps({"scenes": [
        {"scene": 1, "vo": _unhedged["vo"],
         "source_ref": "Electric car"}]})


gate = ab.fact_gate([dict(_unhedged)] + _fillers, _echo_chat,
                    research=EV_RECORD_BASIS_ONLY)
_joined = " ".join(s.get("vo", "") for s in gate["scenes"])
T("F4 the gate cuts the basis-mismatched claim it cannot fix",
  "2.5" not in _joined, _joined[:200])

# ================= Fix 2: vision verifier =================
import broll
import broll_verify

_td = tempfile.mkdtemp(prefix="nr_vis_")
_clip = os.path.join(_td, "clip.mp4")
subprocess.run(
    ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
     "-i", "testsrc=size=320x180:rate=10:duration=2",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", _clip],
    check=True)

# a doc3 stub that behaves like the real one: it base64-encodes
# every jpg it is handed (a str raises TypeError — the old bug)
_doc3_calls = {}


class _FakeDoc3:
    @staticmethod
    def vjson(prompt, jpgs, max_tokens=500):
        _doc3_calls["types"] = [type(j).__name__ for j in jpgs]
        for j in jpgs:
            base64.b64encode(j)  # raises on str, like doc3.vision
        return {"match": False,
                "reason": "an electric train, not an electric car"}


sys.modules["doc3"] = _FakeDoc3
_ver = broll_verify.BrollVerifier(call_budget=10)
_v, _reason, _cached = _ver.verify_candidate(
    {"id": "pexels:train", "path": _clip},
    "electric cars are reshaping our cities",
    "electric cars city streets", workdir=_td)
T("F2 the verifier now receives BYTES (no TypeError)",
  _doc3_calls.get("types") and all(
      t == "bytes" for t in _doc3_calls["types"]),
  str(_doc3_calls))
T("F2 a wrong-semantics clip is REJECTED by vision even though "
  "its keywords matched", _v == "fail" and "train" in _reason,
  f"{_v} / {_reason}")
T("F2 a healthy verifier is not an outage",
  not _ver.outage() and _ver.report()["answers"] == 1)


def _boom(frames, narration, why):
    raise RuntimeError("vision backend exploded")


_ver2 = broll_verify.BrollVerifier(call_budget=10, verifier=_boom)
for _i in range(2):
    _ver2.verify_candidate({"id": f"pexels:{_i}", "path": _clip},
                           "some line", "some query", workdir=_td)
T("F2 an always-erroring verifier is declared an OUTAGE",
  _ver2.outage() and _ver2.report()["outage"]
  and "OUTAGE" in _ver2.report()["note"], str(_ver2.report()))

# pool level: the kept clip is flagged keyword_only and the
# outage lands in footage_json
_pool = broll.FootagePool()
_pool.verifier = _ver2
_cand = {"id": "pexels:99", "provider": "pexels", "url": "x",
         "page": "https://example.invalid/clip", "uploader": "up",
         "duration": 30, "width": 1920, "height": 1080}
_orig = (broll.providers_available, broll._pexels_candidates,
         broll._download, broll.commons_enabled)
broll.providers_available = lambda: True
broll._pexels_candidates = lambda q, k, o: [dict(_cand)]
broll.commons_enabled = lambda: False


def _fake_download(url, dest):
    with open(_clip, "rb") as fsrc, open(dest, "wb") as fdst:
        fdst.write(fsrc.read())
    return True


broll._download = _fake_download
os.environ["PEXELS_KEY"] = "fixture"
try:
    _rec = _pool.assign(1, ["electric cars city streets"], 2,
                        _td, orientation="landscape",
                        line="electric cars are reshaping cities",
                        canvas=(1920, 1080))
finally:
    (broll.providers_available, broll._pexels_candidates,
     broll._download, broll.commons_enabled) = _orig
T("F2 the pool still returns the clip (fallback kept)",
  _rec is not None, str(_rec)[:200])
T("F2 the kept clip is flagged keyword_only",
  _rec and (_rec.get("verify") or {}).get("keyword_only") is True,
  str(_rec)[:300])
_fj = _pool.footage_json()
T("F2 footage_json declares the vision OUTAGE",
  (_fj.get("vision") or {}).get("outage") is True, str(_fj)[:300])

# ================= Fix 3: HF text whitelist =================
import hf_primary

PLAN = {"topic": "Electric Vehicles", "title": "EV",
        "research": EV_RECORD_PERMILE}
POISON_WHY = "the line is about time passing and a deadline"
s_next = {"label": "NEXT", "why": POISON_WHY,
          "vo": "Years passed and the city changed around them.",
          "d": 6}
s_emo = {"label": "EMOTION", "value": "0.1",
         "why": "internal emotion score for the beat",
         "vo": "Every mile driven by an EV cuts CO2 by about "
               "2.5 kg.", "d": 6}
s_lt = {"label": "BATTERY COSTS", "why": "the line lists its "
        "items one by one",
        "vo": "Battery costs have reportedly declined "
              "substantially over recent years.", "d": 6}
s_chart = {"label": "CARBON CUT", "value": "2.5",
           "why": "the writer's own visual for this beat",
           "vo": "Every mile driven by an EV cuts CO2 by about "
                 "2.5 kg.", "source_ref": "Electric car", "d": 6}

T("F3 a NEXT-titled beat produces NO layer",
  hf_primary.beat_layers(s_next, PLAN) is None)
T("F3 an EMOTION-score beat produces NO data chart",
  hf_primary.beat_layers(s_emo, PLAN) is None)
_l = hf_primary.beat_layers(s_lt, PLAN)
T("F3 a lower-third carries the spoken line, never the why",
  _l and _l[0]["type"] == "lower_third"
  and "the line" not in _l[0]["role"]
  and "Battery costs" in _l[0]["role"], str(_l)[:200])
_l = hf_primary.beat_layers(s_chart, PLAN)
T("F3 a spoken, sourced number still charts (positive control)",
  _l and _l[0]["type"] == "data_chart"
  and _l[0]["bars"][0]["display"] == "2.5"
  and _l[0]["source"] == "Electric car", str(_l)[:200])


class _Pool:
    assignments = [{"scene": i + 1, "path": _clip, "start": 0}
                   for i in range(4)]


_plan3 = {"topic": "Electric Vehicles", "title": "EV",
          "research": EV_RECORD_PERMILE,
          "scenes": [dict(s_next), dict(s_emo), dict(s_lt),
                     dict(s_chart)],
          "starts": [0, 6, 12, 18], "_footage_pool": _Pool()}
_wd3 = tempfile.mkdtemp(prefix="nr_hf_")
_beats, _rep3 = hf_primary.plan_beats(
    _plan3, _wd3, {"kind": "long", "width": 320, "height": 180})
T("F3 plan_beats: the EMOTION beat declines; NEXT survives only "
  "as the plan-title card (a packaging field)",
  [b["scene"] for b in _beats] == [1, 3, 4], str(_rep3))
_src = ""
for _root, _dirs, _files in os.walk(_wd3):
    for _f in _files:
        with open(os.path.join(_root, _f), encoding="utf-8",
                  errors="ignore") as fh:
            _src += fh.read()
T("F3 composition source carries NO internal text",
  "the line is about" not in _src and "the line lists" not in _src
  and "EMOTION" not in _src and "emotion score" not in _src
  and "NEXT" not in _src, _src[:200])

# ================= Fix 5a/5c: channel fail-fast + status =================
import channel

_saved_env = dict(os.environ)
for _k in list(os.environ):
    if _k.endswith("_KEY") or _k == "JULIE_CUSTOM_MODEL":
        del os.environ[_k]
os.environ["GROQ_KEY"] = "gk-fixture"
channel.reset()
_st = channel.channel_status()
T("F5c a one-key pool declares itself in plain words",
  _st["single_provider"]
  and _st["warning"] == "channel: single-provider (groq) — "
                        "no failover possible", str(_st))
os.environ["CEREBRAS_KEY"] = "ck-fixture"
_st = channel.channel_status()
T("F5c a two-provider pool carries no warning",
  not _st["single_provider"] and _st["warning"] is None
  and _st["providers"] == ["groq", "cerebras"], str(_st))
os.environ["JULIE_CUSTOM_MODEL"] = json.dumps(
    {"base": "https://api.example.invalid/v1", "model": "m1",
     "key": "fixture"})
_st = channel.channel_status()
T("F5b the owner's custom model joins the channel pool",
  "custom" in _st["providers"], str(_st))
os.environ.clear()
os.environ.update(_saved_env)

# --- the runner leg, exec'd like v75test execs it
import httpx as _real_httpx
import time as _time

os.environ.setdefault("WORKER_URL", "http://worker.invalid")
os.environ.setdefault("RUNNER_KEY", "rk")
os.environ["GROQ_KEY"] = "k1"
_argv = sys.argv
sys.argv = ["runner.py", "JOBX"]
try:
    _src = open(os.path.join(HERE, "runner.py"),
                encoding="utf-8").read().replace(
                    "asyncio.run(main())", "")
    _ns = {"__name__": "runner_nextround"}
    exec(compile(_src, "runner.py", "exec"), _ns)
finally:
    sys.argv = _argv


class _Resp:
    def __init__(self, status, text=""):
        self.status_code = status
        self._text = text

    def json(self):
        return {"choices": [{"message": {"content": self._text}}]}


_leg = {"calls": 0, "sleeps": []}


def _fake_post(url, json=None, headers=None, timeout=None):
    _leg["calls"] += 1
    return _Resp(429)


_ns["httpx"] = types.SimpleNamespace(
    post=_fake_post, HTTPError=_real_httpx.HTTPError)
_ns["time"] = types.SimpleNamespace(
    sleep=lambda s: _leg["sleeps"].append(s),
    monotonic=_time.monotonic, time=_time.time)

_leg.update(calls=0, sleeps=[])
try:
    _ns["groq_chat"]([{"role": "user", "content": "hi"}])
    _raised = False
except RuntimeError:
    _raised = True
T("F5a legacy mode keeps the v75 contract (5/15/45 retries)",
  _raised and _leg["sleeps"] == [5, 15, 45], str(_leg))

_ns["_set_channel_mode"](True)
_leg.update(calls=0, sleeps=[])
try:
    _ns["groq_chat"]([{"role": "user", "content": "hi"}])
    _raised = False
except RuntimeError:
    _raised = True
T("F5a channel mode hands a permanent 429 to the channel FAST "
  "(<=2s of leg sleep, was 65s)",
  _raised and sum(_leg["sleeps"]) <= 2 and _leg["calls"] == 6,
  str(_leg))

# --- and through the channel: failover actually happens, fast
for _k in list(os.environ):
    if _k.endswith("_KEY") or _k == "JULIE_CUSTOM_MODEL":
        del os.environ[_k]
os.environ["GROQ_KEY"] = "k1"
os.environ["CEREBRAS_KEY"] = "ck"


class _CResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._p = payload or {}

    def json(self):
        return self._p


def _chan_post(url, json=None, headers=None, timeout=None):
    if "cerebras" in url:
        return _CResp(200, {"choices": [
            {"message": {"content": "served-by-cerebras"}}]})
    return _CResp(429)


_chan_orig = (channel._post, channel._sleep)
channel._post = _chan_post
channel._sleep = lambda s: None
channel.set_groq_leg(_ns["groq_chat"])
channel.reset()
channel.begin_film(limit=10)
_leg["sleeps"] = []
_out = channel.chat([{"role": "user", "content": "write"}])
T("F5a the channel fails over to cerebras after the leg's fast "
  "429", _out == "served-by-cerebras"
  and sum(_leg["sleeps"]) <= 2, f"out={_out} leg={_leg}")
channel._post, channel._sleep = _chan_orig
_ns["_set_channel_mode"](False)
os.environ.clear()
os.environ.update(_saved_env)

# ================= Fix 5b: Worker payload harness =================
_rig = subprocess.run(
    ["node", os.path.join(HERE, "rig-nextround", "harness.mjs"),
     os.path.join(HERE, "cfworker", "divya.js")],
    capture_output=True, text=True, timeout=120)
print(_rig.stdout.strip()[-600:] if _rig.stdout else "")
T("F5b Worker /job payload wiring (node harness, real bytes)",
  _rig.returncode == 0 and "0 failed" in _rig.stdout,
  (_rig.stdout + _rig.stderr)[-400:])

# ================= Round 3: taste-pack integration =================
import pack_slicer as _ps
import visual_director as _vd

_pack = _vd.taste_pack()
T("R3 full load carries the round-3 sections + the "
  "meaning-trace ruling",
  len(_pack) > 60000 and all(s in _pack for s in (
      "## Style selection", "## The compression pass",
      "## The could/should audit", "MEANING-trace",
      "Literal is capped", "15-second promise",
      "anchors before words", "DYNAMICS column")),
  f"{len(_pack)} chars")
for _stage, _need in (
        ("story", ("Style selection", "The compression pass",
                   "top-up may only add NEW evidence",
                   "value proposition lands by")),
        ("visual", ("Literal is capped", "Media mix is a budget")),
        ("editing", ("could/should audit", "Stillness is a budget",
                     "DYNAMICS column")),
        ("qc", ("could/should audit", "Literal is capped",
                "Media mix is a budget"))):
    _n, _names, _dropped = _ps.slice_info(_stage)
    _slice = _ps.slice_for(_stage)
    T(f"R3 the {_stage} slice (<= budget) carries its round-3 "
      f"sections", _n <= _ps.SLICE_BUDGET and all(
          s in _slice for s in _need),
      f"{_n} chars; dropped={_dropped}")
T("R3 every slice carries the re-ruled one law (meaning-trace)",
  all("MEANING-trace" in _ps.slice_for(s)
      for s in ("story", "visual", "editing", "qc")))

print()
if fails:
    print(f"{len(fails)} FAILURES: {fails}")
    sys.exit(1)
print("ALL PASS")
