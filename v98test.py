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

Section D (v98.1) covers the follow-up flagged during that fix:
make_long_video's spec-compliance block called
_designed_silences(plans) — a name that existed only as a nested
helper inside _correct_assembled — so spec compliance threw
NameError, was swallowed, and silently fell back to the
unconditional QC report. The computation is now the module-level
_designed_silence_windows(), shared by both call sites.

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

# ------------------------------------------------------------------
# D. Spec-compliance designed silences (v98.1 regression — flagged
#    during the v98 fix, pre-existing on main): the spec-compliance
#    block in make_long_video called _designed_silences(plans), but
#    that name existed ONLY as a nested helper inside
#    _correct_assembled — so every spec job's compliance run threw
#    NameError, the except swallowed it, and the job silently fell
#    back to the unconditional QC report (which audits WITHOUT the
#    director's sanctioned silences). The computation is now a
#    module-level function shared by both call sites.
# ------------------------------------------------------------------
import contextlib
import io

_D_OUTLINE = json.dumps({"title": "Silence stub", "chapters": [
    {"title": "A", "brief": "a", "minutes": 1},
    {"title": "B", "brief": "b", "minutes": 1}]})

# Scene 1 runs 3 s and is followed by a director-sanctioned 2 s
# pause (silence_after_s) -> designed window (3.0, 5.0) absolute.
_PLAN_DSIL = {"scenes": [{"d": 3.0, "silence_after_s": 2.0,
                          "has_footage": True},
                         {"d": 3.0, "has_footage": True}],
              "starts": [0.0, 5.0]}
# Control: identical shape, NO sanctioned silence — the same audio
# gap must then FAIL as dead air.
_PLAN_PLAIN = {"scenes": [{"d": 3.0, "has_footage": True},
                          {"d": 3.0, "has_footage": True}],
               "starts": [0.0, 3.0]}

_fn = getattr(long_video, "_designed_silence_windows", None)
check("unit: module-level _designed_silence_windows exists "
      "(shared by compliance + correction loop)", _fn is not None)
if _fn is not None:
    check("unit: plan silence_after_s maps to absolute windows "
          "via the chapter start offset",
          _fn([{"plan": _PLAN_DSIL}], [10.0]) == [(13.0, 15.0)],
          str(_fn([{"plan": _PLAN_DSIL}], [10.0])))


def _run_spec_job(plan):
    """make_long_video with a spec, a stub renderer returning two
    chapters both planned by `plan`, and a stub assembler writing a
    REAL 8 s file: tone 0-3 s, dead silence 3-5 s, tone 5-8 s. (The
    second chapter's silence window lands past the file's end —
    harmless.) The assembled-file correction loop is stubbed out
    (not the subject here). Returns (result, workdir, stdout)."""
    wd = tempfile.mkdtemp(prefix="v98_dsil_")
    real_render = long_video.render_chapters
    real_assemble = long_video.assemble
    real_probe = long_video._probe_duration
    real_correct = long_video._correct_assembled

    async def fake_render(outline_data, chat_, workdir, notify=None,
                          deadline=None, results_out=None,
                          ref_voice=None, amendments=None, **kw):
        if results_out is not None:
            for _ in outline_data["chapters"]:
                results_out.append({"path": "/tmp/x.mp4",
                                    "duration": 8.0, "lang": "en",
                                    "caption": "", "topic": "t",
                                    "plan": plan, "broll": []})
        return ["/tmp/x.mp4"] * len(outline_data["chapters"])

    def fake_assemble(parts, out_path, titles, **kw):
        _ff(["-f", "lavfi", "-i",
             "testsrc2=size=1920x1080:rate=10:duration=8",
             "-f", "lavfi", "-i", "sine=frequency=1000:duration=8",
             "-af", "volume=0.3,volume=0:enable='between(t,3,5)'",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
             "-shortest"], out_path)
        return out_path

    async def fake_correct(final, paths, results_, *a, **kw):
        return [], 0, [], final, paths

    long_video.render_chapters = fake_render
    long_video.assemble = fake_assemble
    long_video._probe_duration = lambda p: 8.0
    long_video._correct_assembled = fake_correct
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            res = asyncio.run(long_video.make_long_video(
                "stub topic", lambda messages: _D_OUTLINE, wd, 2,
                spec=spec_engine.extract_spec(
                    "make a 16:9 long video about rivers")))
    finally:
        long_video.render_chapters = real_render
        long_video.assemble = real_assemble
        long_video._probe_duration = real_probe
        long_video._correct_assembled = real_correct
    return res, wd, buf.getvalue()


def _silence_fails(rep):
    return [c for c in rep["checks"]
            if c.get("rule") == "R11" and c.get("status") == "FAIL"
            and "silence(s) over 0.8" in str(c.get("detail", ""))]


res, wd, out = _run_spec_job(_PLAN_DSIL)
rep = json.load(open(os.path.join(wd, "compliance_report.json")))
check("spec compliance: designed-silence job completes",
      bool(res and res.get("path")), f"res={res and res.get('path')}")
check("spec compliance: block runs WITHOUT the swallowed NameError "
      "(no 'long compliance run failed'; spec line printed)",
      "long compliance run failed" not in out
      and "long compliance:" in out,
      "tail of stdout: " + out[-300:])
check("spec compliance: report is the SPEC report, not the "
      "unconditional fallback (spec_present is not False)",
      rep.get("spec_present") is not False,
      f"keys={sorted(rep)[:8]}")
check("spec compliance: the sanctioned 3-5 s silence is NOT "
      "failed as dead air", not _silence_fails(rep),
      str(_silence_fails(rep)))

res, wd, out = _run_spec_job(_PLAN_PLAIN)
rep = json.load(open(os.path.join(wd, "compliance_report.json")))
check("spec compliance (control): the SAME 3-5 s gap with no "
      "sanctioned silence_after_s DOES fail R11 as dead air",
      len(_silence_fails(rep)) == 1, str(rep["checks"]))

print(f"\nv98test: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
    sys.exit(1)
print("v98test: ALL PASS")
