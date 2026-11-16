"""v98test.py — regression tests for the portrait long-video trap
doors (found 2026-11-16 by the format-literacy check).

THE BUG: spec_engine's long default was always correct (1920x1080),
but two trap doors let long jobs render PORTRAIT 1080x1920 — and
every long video delivered before this fix (v87, v88, the Compromise
video) was portrait because of them:
  1. long_video.assemble() fell back to the historical 1080x1920
     when called without a size.
  2. runner.py passed spec/cfg into the long pipeline ONLY when a
     spec contract existed — a no-spec long job assembled with no
     size at all, straight into trap door 1.

THE FIX (covered here):
  - A long job ALWAYS resolves its render config through
    spec_engine.resolve_render_config() (runner passes cfg
    unconditionally; make_long_video resolves unconditionally).
  - assemble() with no size resolves the LONG default 1920x1080 —
    never portrait. A portrait size is honoured ONLY when
    size_explicit says it came from the user's own spec; any other
    portrait size raises SpecImpossible (fail loudly).
  - Short jobs are unchanged: short config is still 1080x1920.

Run: python3 v98test.py   (exit 1 on any failure)
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import long_video
import spec_engine

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


def _ff(args, out):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args, out],
                   check=True)
    return out


def _size_of(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json",
         str(path)], capture_output=True, text=True)
    s = json.loads(out.stdout)["streams"][0]
    return (s["width"], s["height"])


TD = tempfile.mkdtemp(prefix="v98test_")

# ------------------------------------------------------------------
# A. Config resolution (pure)
# ------------------------------------------------------------------
cfg = spec_engine.resolve_render_config([], "long")
check("config: no-spec long resolves 1920x1080 landscape",
      (cfg["width"], cfg["height"]) == (1920, 1080)
      and cfg["orientation"] == "landscape",
      f"got {cfg['width']}x{cfg['height']}")

cfg = spec_engine.resolve_render_config(None, "long")
check("config: None-spec long resolves 1920x1080",
      (cfg["width"], cfg["height"]) == (1920, 1080),
      f"got {cfg['width']}x{cfg['height']}")

cfg = spec_engine.resolve_render_config([], "short")
check("config: short jobs unchanged — 1080x1920 portrait",
      (cfg["width"], cfg["height"]) == (1080, 1920)
      and cfg["orientation"] == "portrait",
      f"got {cfg['width']}x{cfg['height']}")

spec = spec_engine.extract_spec("make a long video in portrait")
cfg = spec_engine.resolve_render_config(spec, "long")
check("config: explicit portrait spec resolves 1080x1920 AND is "
      "marked as coming from the spec",
      (cfg["width"], cfg["height"]) == (1080, 1920)
      and "aspect_ratio" in cfg["spec_ids"],
      f"got {cfg['width']}x{cfg['height']} ids={cfg['spec_ids']}")

spec = spec_engine.extract_spec("make a 16:9 long video about rivers")
cfg = spec_engine.resolve_render_config(spec, "long")
check("config: explicit 16:9 spec resolves 1920x1080",
      (cfg["width"], cfg["height"]) == (1920, 1080)
      and "aspect_ratio" in cfg["spec_ids"],
      f"got {cfg['width']}x{cfg['height']} ids={cfg['spec_ids']}")

# ------------------------------------------------------------------
# B. assemble() — tiny REAL assemblies
# ------------------------------------------------------------------
clip = _ff(["-f", "lavfi", "-i",
            "color=c=navy:size=320x180:rate=10:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
            "-shortest"], os.path.join(TD, "clip.mp4"))

out = long_video.assemble([clip], os.path.join(TD, "nosize.mp4"),
                          ["Only chapter"])
check("assemble: no size -> 1920x1080 (the portrait default is gone)",
      _size_of(out) == (1920, 1080), f"got {_size_of(out)}")

try:
    long_video.assemble([clip], os.path.join(TD, "trap.mp4"),
                        ["Only chapter"], size=(320, 568))
    check("assemble: portrait size without explicit spec RAISES",
          False, "no exception raised")
except spec_engine.SpecImpossible as e:
    check("assemble: portrait size without explicit spec RAISES "
          "(SpecImpossible)", "portrait" in e.reason, e.reason)

out = long_video.assemble([clip], os.path.join(TD, "explicit.mp4"),
                          ["Only chapter"], size=(320, 568),
                          size_explicit=True)
check("assemble: explicit-spec portrait size is honoured (320x568)",
      _size_of(out) == (320, 568), f"got {_size_of(out)}")

# ------------------------------------------------------------------
# C. make_long_video end-to-end (stubbed renderer/assembler,
#    mirroring v78test): the resolved config must FLOW — chapters
#    receive it, and the assembly is called with it.
# ------------------------------------------------------------------
_OUTLINE = json.dumps({"title": "Stub", "chapters": [
    {"title": "A", "brief": "a", "minutes": 1},
    {"title": "B", "brief": "b", "minutes": 1}]})


def _run_stubbed(**mlv_kwargs):
    captured = {}
    real_render = long_video.render_chapters
    real_assemble = long_video.assemble
    real_probe = long_video._probe_duration

    async def fake_render(outline_data, chat_, workdir, notify=None,
                          deadline=None, results_out=None,
                          ref_voice=None, amendments=None, **kw):
        captured["render_kw"] = kw
        if results_out is not None:
            for _ in outline_data["chapters"]:
                results_out.append({"path": "/tmp/x.mp4",
                                    "duration": 60.0, "lang": "en",
                                    "caption": "", "topic": "t",
                                    "plan": {}, "broll": []})
        return ["/tmp/x.mp4"] * len(outline_data["chapters"])

    def fake_assemble(parts, out_path, titles, **kw):
        captured["assemble_kw"] = kw
        captured["assemble_parts"] = parts
        return out_path

    long_video.render_chapters = fake_render
    long_video.assemble = fake_assemble
    long_video._probe_duration = lambda p: 120.0
    try:
        res = asyncio.run(long_video.make_long_video(
            "stub topic", lambda messages: _OUTLINE,
            tempfile.mkdtemp(prefix="v98_mlv_"), 2, **mlv_kwargs))
    finally:
        long_video.render_chapters = real_render
        long_video.assemble = real_assemble
        long_video._probe_duration = real_probe
    return res, captured


# C1: NO spec, NO cfg — the exact shape of every pre-fix delivery.
res, cap = _run_stubbed()
rcfg = (cap.get("render_kw") or {}).get("cfg") or {}
check("e2e no-spec long: chapters receive the resolved long config",
      (rcfg.get("width"), rcfg.get("height")) == (1920, 1080)
      and rcfg.get("kind") == "long",
      f"render cfg={rcfg.get('width')}x{rcfg.get('height')}")
akw = cap.get("assemble_kw") or {}
check("e2e no-spec long: assembly called at 1920x1080, not explicit",
      akw.get("size") == (1920, 1080) and akw.get("size_explicit") is False,
      f"assemble kw={akw}")
check("e2e no-spec long: job completes and returns the assembly",
      bool(res and res.get("path")), f"res={res and res.get('path')}")

# C2: explicit portrait spec — the ONLY way a long video may be
# portrait, and the explicitness must reach the assembly.
portrait_spec = spec_engine.extract_spec("make a long video in portrait")
res, cap = _run_stubbed(spec=portrait_spec)
rcfg = (cap.get("render_kw") or {}).get("cfg") or {}
check("e2e portrait-spec long: chapters receive 1080x1920",
      (rcfg.get("width"), rcfg.get("height")) == (1080, 1920),
      f"render cfg={rcfg.get('width')}x{rcfg.get('height')}")
akw = cap.get("assemble_kw") or {}
check("e2e portrait-spec long: assembly at 1080x1920, marked explicit",
      akw.get("size") == (1080, 1920) and akw.get("size_explicit") is True,
      f"assemble kw={akw}")

print(f"\nv98test: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
    sys.exit(1)
print("v98test: ALL PASS")
