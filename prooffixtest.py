"""prooffixtest.py — PROOF-FIXES regression suite (2026-11-16).

Covers the five production blockers from the new-brain proof audit
(~/workspace/julie-newbrain-proof/DECISION_AUDIT.md):

  1. brain channel: per-stage pack slices fit the free channel and
     keep each stage's decisive rules; a failed brain stage is
     labelled FALLBACK in the brain ledger, never silent.
  2. footage gate: canvas-relative — 720p landscape accepted for a
     1920x1080 canvas, portrait rejected for landscape, portrait
     shorts keep the legacy 1080 floor.
  3. (Worker half lives in rig-prooffix/harness.mjs; the runner
     heartbeat is structural — see runner.create_job's note wrap.)
  4. topic tripwire: greeting seeds rewritten to AUTO.
  5. duration-by-hope: script-stage fit (rewrite + protected trim)
     and the post-TTS gate that raises instead of amputating.
  + fit_size keeps the native canvas (the 1080x608 fold-in).

Run: python3 prooffixtest.py   (exit 0 = all pass)
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = []
FAIL = []


def T(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra and not cond else ""))


# ---------------- fix 1: pack slicing ----------------
import pack_slicer as ps

FULL = None
for st in ("story", "visual", "editing", "qc"):
    s = ps.slice_for(st)
    T(f"slice[{st}] under budget", 0 < len(s) <= ps.SLICE_BUDGET,
      f"{len(s)} chars")
    T(f"slice[{st}] carries the globals",
      "Format literacy" in s and "Honesty contract" in s
      and "The one law" in s)
    if FULL is None:
        FULL = open(os.path.join(os.path.dirname(__file__),
                                 "skills", "taste_pack.md"),
                    encoding="utf-8").read()
    T(f"slice[{st}] is a strict subset of the pack",
      all(part.strip() in FULL for part in s.split("\n\n") if part.strip()))
T("full pack is the size that 413'd", len(FULL) > 50000, f"{len(FULL)}")
T("story slice keeps story rules",
  "Story shape" in ps.slice_for("story")
  and "Loops and re-hooks" in ps.slice_for("story"))
T("visual slice keeps composition rules",
  "Frame composition" in ps.slice_for("visual")
  and "Evidence is an apparatus" in ps.slice_for("visual"))
T("editing slice keeps beat + music rules",
  "Beat grammar" in ps.slice_for("editing")
  and "Music is edited" in ps.slice_for("editing"))
T("qc slice keeps finish rules",
  "Finish: matching" in ps.slice_for("qc"))

# ---------------- fix 1: the brain ledger ----------------
import brain_status as bs

bs.reset()
bs.record("story-analyst", True, "preflight ran")
bs.record("visual-director", False, "chat failed: 413 — v86 order kept")
_sum = bs.summary()
T("ledger records ok + fallback",
  _sum["story-analyst"]["status"] == "OK"
  and bs.fallbacks() == ["visual-director"])
T("ledger line labels the fallback",
  "FALLBACK" in bs.line() and "visual-director" in bs.line())
bs.reset()
T("ledger resets clean", bs.summary() == {} and bs.fallbacks() == [])

# story analyst: failure is labelled, success is labelled
import story_analyst as sa

SCENES = [{"vo": "Water boils at one hundred degrees.", "visual": "chart"},
          {"vo": "Steam rises and carries the heat away.", "visual": "photo"}]


def _boom(messages):
    raise RuntimeError("413 payload too large")


bs.reset()
out = sa.analyse_script(SCENES, _boom, taste="x" * 20000)
T("analyst failure returns None (degrades)", out is None)
T("analyst failure is labelled FALLBACK",
  bs.fallbacks() == ["story-analyst"],
  str(bs.summary()))


def _good_analyst(messages):
    return json.dumps({"scenes": [
        {"beat": 1, "job": "hook", "beat_type": "fact", "turn": "",
         "question": "why?", "visual_need": "evidence",
         "emphasis_word": "hundred"},
        {"beat": 2, "job": "explain", "beat_type": "fact", "turn": "",
         "question": "", "visual_need": "evidence",
         "emphasis_word": "steam"}],
        "preflight": {"verdict": "strong", "weakest_beat": 0,
                      "fix": "", "hook_variants": ["a", "b", "c"]}})


bs.reset()
out = sa.analyse_script(SCENES, _good_analyst, taste="x" * 20000,
                        topic="why water boils at 100 degrees",
                        sources=[{"title": "physics reference"}])
T("analyst success returns a sheet", bool(out and out.get("scenes")))
T("analyst success is labelled OK",
  bs.summary().get("story-analyst", {}).get("status") == "OK"
  and bs.fallbacks() == [])

# visual director: failure is labelled
import visual_director as vd

MENUS = [{"beat": 1, "line": "Water boils.", "role": "fact",
          "analyst": None,
          "candidates": [{"template": "chart", "asset_type": "chart",
                          "why": "shows the number"}]}]
bs.reset()
out = vd.choose_visuals(MENUS, _boom, taste="x" * 20000)
T("visual director failure returns {} (degrades)", out == {})
T("visual director failure is labelled FALLBACK",
  bs.fallbacks() == ["visual-director"], str(bs.summary()))

# ---------------- fix 2: the footage gate ----------------
import broll


def cand(cid, w, h, dur=30, up="someone"):
    return {"id": cid, "url": "https://x/" + cid, "width": w, "height": h,
            "duration": dur, "uploader": up, "provider": "pexels",
            "page_url": "https://x/" + cid}


LAND = (1920, 1080)
kept, rej = broll.filter_candidates(
    [cand("a", 1280, 720), cand("b", 1080, 1920), cand("c", 640, 360),
     cand("d", 1920, 1080)], 5, set(), "", canvas=LAND)
T("720p landscape accepted for a 1080 canvas",
  any(c["id"] == "a" for c in kept))
T("1080p landscape accepted for a 1080 canvas",
  any(c["id"] == "d" for c in kept))
T("portrait rejected for a landscape canvas",
  any(c["id"] == "b" and "portrait" in c["reason"] for c in rej))
T("360p rejected for a 1080 canvas (floor 480 — Wave 4 lowered "
  "the 540 floor: 506p stock died under it; >=480p landscape is "
  "now accepted + upscaled)",
  any(c["id"] == "c" and "480" in c["reason"] for c in rej))
kept, rej = broll.filter_candidates(
    [cand("a", 1280, 720), cand("e", 1080, 1920)], 5, set(), "")
T("no canvas: legacy floor keeps 1080p portrait",
  any(c["id"] == "e" for c in kept))
T("no canvas: legacy floor rejects 720p",
  any(c["id"] == "a" for c in rej))
kept, rej = broll.filter_candidates(
    [cand("a", 1280, 720), cand("e", 1080, 1920)], 5, set(), "",
    canvas=(1080, 1920))
T("portrait canvas: legacy floor (720p landscape rejected)",
  any(c["id"] == "a" for c in rej)
  and any(c["id"] == "e" for c in kept))
T("canvas floor helper", broll._min_height_for_canvas((1920, 1080)) == 480
  and broll._min_height_for_canvas(None) == 1080
  and broll._min_height_for_canvas((1080, 1920)) == 1080)

# ---------------- fix 4: the topic tripwire (runner half) ----------------
# runner.py self-executes main() on import — load its source with
# the entrypoint stripped, exactly the shipped bytes otherwise.
os.environ.setdefault("WORKER_URL", "https://example.invalid")
os.environ.setdefault("RUNNER_KEY", "test")
sys.argv = ["runner.py", "testjob000"]
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "runner.py"), encoding="utf-8").read()
_src = _src.replace("\nasyncio.run(main())\n", "\n")
runner = type(sys)("runner")
runner.__file__ = "runner.py"
exec(compile(_src, "runner.py", "exec"), runner.__dict__)

B = "topic: Helo\nmake the video"
T("greeting seed rewritten to AUTO",
  runner._sanitize_topic_seed(B).startswith("topic: AUTO"))
T("real topic seed untouched",
  runner._sanitize_topic_seed("topic: The Silk Road\nx")
  == "topic: The Silk Road\nx")
T("two-letter seed rewritten",
  runner._sanitize_topic_seed("topic: hi\nx").startswith("topic: AUTO"))
T("no seed line: brief untouched",
  runner._sanitize_topic_seed("just a brief") == "just a brief")

# ---------------- fix 5: duration enforcement ----------------
import doc

scenes30 = [{"vo": " ".join(["word"] * 25)} for _ in range(4)]  # en: 10s each + gaps
T("estimator matches the timing formula",
  abs(doc._estimate_script_s(scenes30, "en")
      - (0.4 + 4 * (25 / 2.5 + 0.45) + doc.OUTRO) < 0.01))
T("target from brief length line",
  doc._duration_target_s("x\nFINAL VIDEO LENGTH: exactly 30 seconds")
  == 30.0)
T("target from minutes line",
  doc._duration_target_s("FINAL VIDEO LENGTH: exactly 3 minutes") == 180.0)
T("no target when unordered",
  doc._duration_target_s("make something nice") is None)

# over-long script: 6 scenes x 30 en words = ~12.45s each -> ~76s vs 30s
LONG_VO = " ".join(["alpha"] * 30)
p = {"lang": "en", "scenes": [{"vo": LONG_VO} for _ in range(6)]}
SHORT_VO = " ".join(["beta"] * 8)


def _shortener(messages):
    return json.dumps({"scenes": [{"vo": SHORT_VO} for _ in range(6)]})


doc._fit_script_to_duration(
    p, "FINAL VIDEO LENGTH: exactly 30 seconds", _shortener)
fit = p.get("duration_fit") or {}
T("fit ran the writer rewrite", fit.get("action") == "writer-rewrite",
  str(fit))
T("rewritten script estimates within tolerance",
  fit.get("estimated_s", 999) <= 30 * 1.02 + 0.6, str(fit))

# rewrite keeps the hook/CTA (as instructed) but barely shortens
# the middles -> the deterministic trim must finish the job without
# ever touching scene 1 or the last scene
p2 = {"lang": "en",
      "scenes": [{"vo": "HOOK " + " ".join(["h"] * 13)}]
      + [{"vo": " ".join(["m"] * 30)} for _ in range(4)]
      + [{"vo": "CTA " + " ".join(["c"] * 13)}]}


def _stubborn(messages):
    rows = ([{"vo": "HOOK " + " ".join(["h"] * 13)}]
            + [{"vo": " ".join(["m"] * 28)} for _ in range(4)]
            + [{"vo": "CTA " + " ".join(["c"] * 13)}])
    return json.dumps({"scenes": rows})


doc._fit_script_to_duration(
    p2, "FINAL VIDEO LENGTH: exactly 30 seconds", _stubborn)
fit2 = p2.get("duration_fit") or {}
T("stubborn script gets trimmed", "trim" in str(fit2.get("action")),
  str(fit2))
T("trim never touches the hook scene",
  p2["scenes"][0]["vo"].startswith("HOOK"))
T("trim never touches the CTA scene",
  p2["scenes"][-1]["vo"].startswith("CTA"))
T("trimmed script estimates within tolerance",
  fit2.get("estimated_s", 999) <= 30 * 1.02 + 0.6, str(fit2))

# long jobs are exempt (chapter budgets own their lengths)
p3 = {"lang": "en", "scenes": [{"vo": LONG_VO} for _ in range(6)]}
doc._fit_script_to_duration(
    p3, "FINAL VIDEO LENGTH: exactly 30 seconds", _shortener,
    cfg={"kind": "long"})
T("long cfg exempt from the short fit", "duration_fit" not in p3)

# the post-TTS gate
try:
    doc._check_duration_gate(38.5, 30.0)
    T("post-TTS gate raises on the audit's overrun", False)
except doc.DurationOverrunError:
    T("post-TTS gate raises on the audit's overrun", True)
try:
    doc._check_duration_gate(31.5, 30.0)
    T("post-TTS gate passes within tolerance", True)
except doc.DurationOverrunError:
    T("post-TTS gate passes within tolerance", False)

# ---------------- fold-in: fit_size keeps the canvas ----------------
with tempfile.TemporaryDirectory() as td:
    src = os.path.join(td, "big.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=1920x1080:rate=30:duration=6",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src],
                   check=True)
    out = runner.fit_size(src, 1)  # 1 MB cap forces the re-encode
    probe = subprocess.run(["ffprobe", "-v", "quiet", "-print_format",
                            "json", "-show_streams", out],
                           capture_output=True, text=True)
    streams = json.loads(probe.stdout)["streams"]
    v = next(s for s in streams if s["codec_type"] == "video")
    T("fit_size copy keeps the 1920x1080 canvas",
      (v["width"], v["height"]) == (1920, 1080),
      f"{v['width']}x{v['height']}")
    T("fit_size copy is under the cap",
      os.path.getsize(out) <= 1.05e6, f"{os.path.getsize(out)}")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", *FAIL, sep="\n  ")
    sys.exit(1)
