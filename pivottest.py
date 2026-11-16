#!/usr/bin/env python3
"""RENDERER PIVOT tests — one block per phase.

Phase 1: channel pacing/failover (stubbed transports; the primary
channel 429s permanently and the pipeline stages still complete).
Phase 2: query-quality rewrite + 540p acceptance + share report.
Phase 3: ONE length authority (runner + Worker helpers via node).
Phase 4: fact gate v2 (source-resolution) + fake-document ban.
Phase 5: HyperFrames-primary beat decisions + a REAL rendered
segment swapped into a raw timeline, frame-checked.

Run: python3 pivottest.py (the Phase 5 render takes a minute or
two — it drives the real HyperFrames CLI).
"""
import importlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Phase 1 env must exist BEFORE providers.py reads it at import.
os.environ["GROQ_KEY"] = "gsk-test-a,gsk-test-b"
os.environ["CEREBRAS_KEY"] = "csk-test"
os.environ["OPENROUTER_KEY"] = "sk-or-test"

fails = []


def T(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name
          + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---------------- Phase 1: the channel layer ----------------
import channel


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._p = payload or {}
        self.text = json.dumps(self._p)

    def json(self):
        return self._p


_OK = {"choices": [{"message": {"content": "served"}}]}
_state = {"openrouter_dead": False}
_leg_calls = {"n": 0}


def _stub_post(url, json=None, headers=None, timeout=None):
    if "cerebras" in url:
        return _Resp(429, {"error": {"message": "rate limited"}})
    if "openrouter" in url:
        if _state["openrouter_dead"]:
            return _Resp(429, {"error": {"message": "rate limited"}})
        return _Resp(200, _OK)
    return _Resp(500, {})


def _dead_groq_leg(messages):
    _leg_calls["n"] += 1
    raise RuntimeError("LLM request failed (429)")


channel._post = _stub_post
channel.set_groq_leg(_dead_groq_leg)
os.environ["JULIE_CHANNEL_MIN_INTERVAL_S"] = "0.3"
channel.begin_film(limit=160)

out = channel.chat([{"role": "user", "content": "hi"}])
T("P1 failover: groq 429 + cerebras 429 -> openrouter serves",
  out == "served")
st = channel.film_stats()
T("P1 call log records the serving provider",
  any(e.get("provider") == "openrouter" for e in st["log"]),
  str(st)[:300])
out2 = channel.chat([{"role": "user", "content": "again"}])
st = channel.film_stats()
T("P1 cooled-down groq leg is skipped, not re-stormed",
  out2 == "served" and _leg_calls["n"] == 1,
  f"leg calls={_leg_calls['n']}")
T("P1 pacing: a min-interval sleep is recorded between calls",
  any(e.get("pace_sleep_s", 0) > 0 for e in st["log"]),
  str([e for e in st["log"] if "pace_sleep_s" in e])[:200])


def _stage(name, chat):
    """A brain-stage stand-in with brain_status semantics: a stage
    that cannot get a channel is FALLBACK, reason in the detail."""
    try:
        return name, "OK", chat([{"role": "user", "content": "x"}])
    except Exception as e:
        return name, "FALLBACK", str(e)


res = [_stage(n, channel.chat)
       for n in ("story_analyst", "visual_director", "editing")]
T("P1 stages complete via failover while the primary is dead",
  all(r[1] == "OK" for r in res), str(res))

_state["openrouter_dead"] = True
channel.reset()
channel._post = _stub_post
channel.set_groq_leg(_dead_groq_leg)
channel.begin_film(limit=160)
name, status, detail = _stage("story_analyst", channel.chat)
T("P1 no channel anywhere: stage FALLBACK, reason says 'channel'",
  status == "FALLBACK" and "channel" in detail, detail[:160])

channel.reset()
channel._post = _stub_post
channel.set_groq_leg(_dead_groq_leg)
_state["openrouter_dead"] = False
channel.begin_film(limit=2)
channel.chat([{"role": "user", "content": "1"}])
channel.chat([{"role": "user", "content": "2"}])
try:
    channel.chat([{"role": "user", "content": "3"}])
    T("P1 per-film budget stops with a 'channel' error", False,
      "third call did not raise")
except RuntimeError as e:
    T("P1 per-film budget stops with a 'channel' error",
      "channel" in str(e), str(e)[:120])
_state["openrouter_dead"] = False

# ---------------- Phase 2: footage supply ----------------
import anti_boring as ab
import broll
import doc

T("P2 fragment detected: voice-line shard",
  ab.query_is_fragment("ever looked wondered who's")
  and not ab.query_is_searchable("ever looked wondered who's"))
T("P2 fragment detected: participle tail",
  ab.query_is_fragment("nest hidden cracks sipping"))
T("P2 subject queries pass",
  ab.query_is_searchable("honeybee on rooftop hive")
  and ab.query_is_searchable("doctor holding liver scan")
  and ab.query_is_searchable("cinema audience watching screen"))
kept, dropped = ab.searchable_queries(
    ["ever looked wondered who's"],
    "Have you ever looked up and wondered who's buzzing between "
    "the skyscrapers", "HOOK", "The Hidden Life of Urban Bees")
T("P2 fragment rewritten to a subject query before the pool",
  dropped and kept and all(ab.query_is_searchable(q) for q in kept),
  f"kept={kept} dropped={dropped}")


def _cand(cid, w, h, prov="pexels", slug="bees hive"):
    return {"id": cid, "url": "https://x/" + cid, "width": w,
            "height": h, "duration": 30, "uploader": "u",
            "provider": prov, "page_url": "https://x/" + cid,
            "slug": slug}


kept_c, rej_c = broll.filter_candidates(
    [_cand("lo", 960, 540), _cand("tiny", 640, 360),
     _cand("hd", 1920, 1080)], 5, set(), "", canvas=(1920, 1080))
T("P2 540p landscape accepted for a 1080 canvas",
  any(c["id"] == "lo" for c in kept_c))
T("P2 360p still rejected", any(c["id"] == "tiny" for c in rej_c))
T("P2 ranking prefers HD, then Pexels",
  broll.score_candidate(_cand("a", 1920, 1080), "bees hive")
  > broll.score_candidate(_cand("b", 960, 540), "bees hive")
  > broll.score_candidate(_cand("c", 960, 540, prov="pixabay"),
                          "bees hive"))


class _SharePool:
    """Lands footage for the first 3 of 4 scenes; records queries."""

    def __init__(self):
        self.assignments = []
        self.used_ids = []
        self.last_uploader = ""
        self.seen_queries = []

    def assign(self, scene_no, queries, needed_s, workdir, **kw):
        self.seen_queries.append(list(queries))
        if scene_no <= 3:
            self.assignments.append(
                {"scene": scene_no, "clip_id": f"c{scene_no}",
                 "provider": "pexels", "source_url": "https://x",
                 "query": queries[0] if queries else "",
                 "keyword": "", "start": 0.0, "static": False,
                 "path": "/nonexistent/c.mp4"})
            return {"path": "/nonexistent/c.mp4", "start": 0.0,
                    "static": False, "provider": "pexels",
                    "source_url": "https://x", "query": queries[0]}
        return None

    def footage_json(self):
        return {"clips": [], "rejected": []}

    def _save(self):
        pass


doc._extract_broll_frames = lambda *a, **k: 3
_pool = _SharePool()
_p = {"topic": "The Hidden Life of Urban Bees",
      "render_config": {"kind": "long", "width": 1920,
                        "height": 1080, "orientation": "landscape"},
      "scenes": [
          {"vo": "Have you ever looked up and wondered who's "
                 "buzzing between the skyscrapers",
           "label": "HOOK", "d": 5,
           "queries": ["ever looked wondered who's"]},
          {"vo": "Rooftop hives sit above the traffic",
           "label": "ROOFTOP HIVES", "d": 5,
           "queries": ["honeybee on rooftop hive"]},
          {"vo": "Heat gathers on the glass towers",
           "label": "HEAT", "d": 5,
           "queries": ["city skyline summer heat"]},
          {"vo": "No clip exists for this line at all",
           "label": "VOID", "d": 5,
           "queries": ["woman looking in mirror"]}]}
_wd = tempfile.mkdtemp(prefix="pivot2_")
doc._attach_broll(_p, _wd, cfg=_p["render_config"], pool=_pool)
T("P2 no fragment ever reached the pool",
  all(ab.query_is_searchable(q)
      for qs in _pool.seen_queries for q in qs),
  str(_pool.seen_queries)[:240])
T("P2 footage share reported per film (3/4 = 0.75)",
  _p.get("footage_share") == 0.75, str(_p.get("footage_share")))

# ---------------- Phase 3: one length authority ----------------
os.environ.setdefault("WORKER_URL", "https://example.invalid")
os.environ.setdefault("RUNNER_KEY", "test")
sys.argv = ["runner.py", "testjob000"]
_src = open(os.path.join(HERE, "runner.py"), encoding="utf-8").read()
_src = _src.replace("\nasyncio.run(main())\n", "\n")
runner = type(sys)("runner")
runner.__file__ = "runner.py"
exec(compile(_src, "runner.py", "exec"), runner.__dict__)

BRIEF = ("topic: bees\nFINAL VIDEO LENGTH: exactly 3 minutes\n"
         "a 10 minute documentary in spirit")
T("P3 spec (600s) beats the brief's conflicting numbers",
  runner.authoritative_target_s(
      BRIEF, [{"type": "duration", "value": "600s"}]) == 600)
T("P3 no spec duration: the brief line is the fallback",
  runner.authoritative_target_s(BRIEF, []) == 180)
T("P3 spec seconds win too",
  runner.authoritative_target_s(
      BRIEF, [{"type": "duration", "value": "45s"}]) == 45)

# Worker helpers, evaluated from the shipped source with node.
api_src = open(os.path.join(HERE, "cfworker", "app_api.js"),
               encoding="utf-8").read()
wkr_src = open(os.path.join(HERE, "cfworker", "divya.js"),
               encoding="utf-8").read()


def _const_line(src, name):
    for line in src.splitlines():
        if line.startswith(f"const {name} ="):
            return line
    return ""


helpers = "\n".join(_const_line(api_src, n)
                    for n in ("parseMins", "specDurationS",
                              "lengthMins"))
js = helpers + """
const assert = (c, m) => { if (!c) { console.error("FAIL " + m); process.exit(1); } };
assert(specDurationS("make a 10 minute documentary") === 600, "spec 10min");
assert(specDurationS("a 600 seconds film") === 600, "spec 600s");
assert(specDurationS("no length here") === null, "spec none");
assert(lengthMins("make a 10 minute documentary", "3 minutes") === 10, "user spec prices");
assert(lengthMins("no length here", "3 minutes") === 3, "brief fallback prices");
console.log("worker length helpers OK");
"""
with tempfile.NamedTemporaryFile("w", suffix=".js",
                                 delete=False) as f:
    f.write(js)
    js_path = f.name
r = subprocess.run(["node", js_path], capture_output=True, text=True)
T("P3 Worker helpers: the user's spec is the only authority",
  r.returncode == 0 and "OK" in r.stdout,
  (r.stdout + r.stderr)[:200])
T("P3 Worker mirror + call sites use the authority",
  _const_line(wkr_src, "specDurationS")
  == _const_line(api_src, "specDurationS")
  and "specDurationS(userPrompt)" in wkr_src
  and "lengthMins(text" in wkr_src
  and "lengthMins(cleanText" in wkr_src
  and "lengthMins(cleanText" in api_src)

# ---------------- Phase 4: fact gate v2 ----------------
import compliance
import research

RECORD = [
    {"title": "Urban beekeeping",
     "url": "https://en.wikipedia.org/wiki/Urban_beekeeping",
     "snippet": "Urban beekeeping is the practice of keeping bee "
                "colonies in urban areas. Studies report yields "
                "vary widely by city and season."},
    {"title": "Bee",
     "url": "https://en.wikipedia.org/wiki/Bee",
     "snippet": "Bees are winged insects. A colony can contain "
                "up to 60,000 workers in summer."},
]
BEES_SCENE = {"vo": "City bees produce up to 30% more honey "
                    "than rural bees.",
              "source": "Nature 2022", "label": "CLAIM", "d": 5}
claims = ab.scene_claims(BEES_SCENE, RECORD)
T("P4 invented source string no longer counts",
  claims and not claims[0]["sourced"], str(claims))
ok_scene = {"vo": "A colony can contain up to 60,000 workers "
                  "in summer.",
            "source_ref": "Bee", "label": "COLONY", "d": 5}
claims = ab.scene_claims(ok_scene, RECORD)
T("P4 retrieved source + number in its text: claim resolves",
  claims and claims[0]["sourced"], str(claims))
wrong_num = {"vo": "A colony can contain up to 90,000 workers.",
             "source_ref": "Bee", "label": "COLONY", "d": 5}
claims = ab.scene_claims(wrong_num, RECORD)
T("P4 real source, wrong number: still unresolved",
  claims and not claims[0]["sourced"], str(claims))
T("P4 stamps print only retrieved titles",
  ab.resolved_source_title(BEES_SCENE, RECORD) == ""
  and ab.resolved_source_title(ok_scene, RECORD) == "Bee")


def _inventing_chat(messages):
    return json.dumps({"scenes": [
        {"scene": 1, "vo": BEES_SCENE["vo"],
         "source_ref": "Nature 2022"}]})


fillers = [{"vo": f"Plain narration line number {i} about bees "
                  f"and rooftops and summer light.",
            "label": f"S{i}", "d": 5} for i in range(4)]
gate = ab.fact_gate([dict(BEES_SCENE)] + fillers,
                    _inventing_chat, research=RECORD)
joined = " ".join(s.get("vo", "") for s in gate["scenes"])
T("P4 gate: invented citation discarded, claim cut",
  "30%" not in joined and "Nature 2022" not in joined,
  joined[:200])
T("P4 gate log carries the research record",
  gate["log"].get("research", {}).get("entries") == 2,
  str(gate["log"])[:200])

args, text = compliance.compose_visual(
    {"label": "CLAIM", "vo": BEES_SCENE["vo"],
     "queries": ["Graph showing temperature vs bee activity."],
     "source": "Nature 2022"}, "document")
T("P4 fake document banned (plan text as evidence)",
  args is None, str(args)[:120])
args, text = compliance.compose_visual(
    {"label": "COLONY", "vo": ok_scene["vo"],
     "source_ref": "Bee",
     "source_text": RECORD[1]["snippet"]}, "document")
T("P4 real retrieved document composes from its own text",
  args is not None and "Source: Bee" in text
  and "winged insects" in text, str(args)[:200])

# research record builder against a stubbed Wikipedia transport
research.set_transport(lambda url: {"query": {"pages": {
    "1": {"title": "Urban beekeeping",
          "fullurl": "https://en.wikipedia.org/wiki/Urban_beekeeping",
          "extract": "Urban beekeeping is the practice of keeping "
                     "bee colonies in urban areas."}}}})
rec = research.build_research_record("urban bees")
T("P4 research record carries retrieved title/URL/snippet",
  rec and rec[0]["title"] == "Urban beekeeping"
  and rec[0]["url"].startswith("https://")
  and "practice" in rec[0]["snippet"], str(rec)[:200])
research.set_transport(None)

# ---------------- Phase 5: HyperFrames primary ----------------
import hf_primary

T("P5 enabled for documentary longs only",
  hf_primary.enabled_for({"kind": "long"})
  and not hf_primary.enabled_for({"kind": "short"})
  and not hf_primary.enabled_for(
      {"kind": "long", "excludes": ["graphics"]}))
plan = {"topic": "Urban Bees", "title": "URBAN BEES",
        "research": RECORD}
layers = hf_primary.beat_layers(
    {"label": "COLONY", "value": "60,000", "vo": ok_scene["vo"],
     "source_ref": "Bee"}, plan)
T("P5 sourced number beat -> data_chart with the retrieved source",
  layers and layers[0]["type"] == "data_chart"
  and layers[0]["source"] == "Bee", str(layers)[:200])
layers = hf_primary.beat_layers(
    {"label": "CLAIM", "value": "30%", "vo": BEES_SCENE["vo"],
     "source": "Nature 2022"}, plan)
T("P5 unsourced number -> chart with NO source (unverified stamp)",
  layers and layers[0]["type"] == "data_chart"
  and layers[0]["source"] == "", str(layers)[:200])
T("P5 document beats decline (real-source path renders them)",
  hf_primary.beat_layers(
      {"label": "DOC", "visual": "document",
       "lib_visual": "document", "fact_type": "stat"},
      plan) is None)

# The proof render: a real 2-beat timeline, HF spans swapped in.
# (Workdir on the big disk, NOT /tmp — this VM's /tmp is a 512 MB
# tmpfs and the HyperFrames renderer refuses to start under ~1 GB
# free, the spike README's warning.)
_wd5 = tempfile.mkdtemp(prefix="pivot5_",
                        dir=os.path.expanduser("~/workspace"))
raw = os.path.join(_wd5, "raw.mp4")
clip = os.path.join(_wd5, "footage.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f",
                "lavfi", "-i", "testsrc2=size=960x540:rate=30",
                "-t", "6", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", raw], check=True)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f",
                "lavfi", "-i", "smptebars=size=960x540:rate=30",
                "-t", "6", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", clip], check=True)


class _Pool5:
    assignments = [
        {"scene": 1, "path": clip, "start": 0.0},
        {"scene": 2, "path": clip, "start": 0.0}]


_p5 = {"topic": "Urban Bees", "title": "URBAN BEES",
       "research": RECORD, "starts": [0.0, 3.0],
       "_footage_pool": _Pool5(),
       "scenes": [
           {"vo": "Welcome to the hidden life of urban bees.",
            "label": "THE HIDDEN LIFE", "d": 3.0},
           {"vo": ok_scene["vo"], "label": "COLONY",
            "value": "60,000", "source_ref": "Bee", "d": 3.0}]}
_cfg5 = {"kind": "long", "width": 960, "height": 540}
rep5 = hf_primary.render_and_swap(_p5, _wd5, _cfg5, raw)
T("P5 proof: both footage beats rendered by HyperFrames",
  rep5["beats_rendered"] == 2, str(rep5)[:300])
dur = hf_primary._probe_duration(raw)
T("P5 proof: swapped timeline keeps its duration",
  abs(dur - 6.0) < 0.6, f"dur={dur}")


def _frame(video, t, out_png):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss",
                    str(t), "-i", video, "-frames:v", "1", out_png],
                   check=True)


_orig = os.path.join(_wd5, "orig.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f",
                "lavfi", "-i", "testsrc2=size=960x540:rate=30",
                "-t", "6", "-c:v", "libx264", "-pix_fmt",
                "yuv420p", _orig], check=True)
from PIL import Image, ImageChops
diffs = []
for t in (1.5, 4.5):
    a, b = (os.path.join(_wd5, f"hf_{t}.png"),
            os.path.join(_wd5, f"or_{t}.png"))
    _frame(raw, t, a)
    _frame(_orig, t, b)
    d = ImageChops.difference(Image.open(a).convert("RGB"),
                              Image.open(b).convert("RGB"))
    px = list(d.resize((48, 27)).getdata())
    diffs.append(sum(sum(p) for p in px) / len(px) / 3)
T("P5 proof: HF spans visibly differ from the widget timeline "
  "(footage + graphics composited)",
  all(d > 4 for d in diffs), f"diffs={diffs}")

print()
if fails:
    print(f"pivottest: {len(fails)} FAILED: {fails}")
    sys.exit(1)
print("pivottest: ALL PASS")
