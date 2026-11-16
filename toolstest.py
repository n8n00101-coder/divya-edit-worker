"""toolstest.py — tests for the v89 editing tools: colour_lint,
beatgrid, speedramp (+ the media_qc advisory wiring).

All media is synthetic, generated locally with ffmpeg / stdlib:
- a colour clip with KNOWN crushed blacks (testsrc2 pushed through
  a contrast/brightness crush) vs a clean bright gradient clip;
- a click-track wav at EXACTLY 120 BPM written sample-accurately;
- a 4 s test clip run through a normal -> ramp-down -> hold-slow ->
  ramp-back spec whose output duration is known in closed form.

Run: python3 toolstest.py   (exit 1 on any failure)
"""

import math
import os
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


def _ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + args,
                   check=True, capture_output=True)


TD = tempfile.mkdtemp(prefix="toolstest_")

# ------------------------------------------------------------- colour_lint
import colour_lint

crushed = os.path.join(TD, "crushed.mp4")
_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=320x240:d=3:r=10",
         "-vf", "eq=brightness=-0.35:contrast=1.8,format=yuv420p",
         "-c:v", "libx264", crushed])
clean = os.path.join(TD, "clean.mp4")
_ffmpeg(["-f", "lavfi", "-i",
         "gradients=s=320x240:d=3:r=10:c0=0xE04040:c1=0x40E040:"
         "c2=0x4040E0:c3=0xE0E040",
         "-vf", "format=yuv420p", "-c:v", "libx264", clean])

f_crushed = colour_lint.lint_file(crushed)
check("colour_lint: crushed clip is flagged for crushed blacks",
      any(f["metric"] == "crushed_blacks" for f in f_crushed),
      f"{f_crushed}")
check("colour_lint: findings carry shot/metric/value/verdict",
      all(set(("shot", "metric", "value", "verdict")) <= set(f)
          for f in f_crushed) and len(f_crushed) > 0)
f_clean = colour_lint.lint_file(clean)
check("colour_lint: clean clip passes (no findings)",
      f_clean == [], f"{f_clean}")

# drift: two shots of one scene, second crushed dark -> YAVG drift
two = os.path.join(TD, "two_shots.mp4")
_ffmpeg(["-f", "lavfi", "-i",
         "gradients=s=320x240:d=2:r=10:c0=0xE04040:c1=0x40E040:"
         "c2=0x4040E0:c3=0xE0E040",
         "-f", "lavfi", "-i", "color=c=0x181818:s=320x240:d=2:r=10",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]",
         "-map", "[v]", "-c:v", "libx264", two])
f_drift = colour_lint.lint_file(
    two, shots=[{"start": 0, "end": 2, "scene": 0},
                {"start": 2, "end": 4, "scene": 0}])
check("colour_lint: same-scene exposure drift is flagged",
      any(f["metric"] == "exposure_drift" for f in f_drift),
      f"{f_drift}")

# ------------------------------------------------------------- media_qc wiring
import media_qc

checks_qc, _info = media_qc.inspect_file(crushed)
lint_checks = [c for c in checks_qc if c["rule"] == "MQ-COLOUR-LINT"]
check("media_qc: colour lint findings are wired in",
      len(lint_checks) > 0, f"{lint_checks}")
check("media_qc: colour lint is advisory — never a FAIL",
      all(c["status"] in ("WARN", "UNVERIFIED") for c in lint_checks),
      f"{lint_checks}")

# ------------------------------------------------------------- beatgrid
import beatgrid

sr = 22050
dur_s = 16.0
x = np.zeros(int(sr * dur_s), dtype=np.float32)
click_len = int(0.005 * sr)
click = (np.sin(2 * np.pi * 2000 * np.arange(click_len) / sr)
         * np.exp(-np.arange(click_len) / (click_len / 3))).astype(np.float32)
for k in range(int(dur_s * 2)):  # 120 BPM = one click every 0.5 s
    pos = int(k * 0.5 * sr)
    x[pos:pos + click_len] += click
click_wav = os.path.join(TD, "click120.wav")
with wave.open(click_wav, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())

grid = beatgrid.beat_grid(click_wav)
check("beatgrid: detects 120 BPM within ±3",
      abs(grid["bpm"] - 120.0) <= 3.0, f"bpm={grid['bpm']}")
beats = grid["beats"]
check("beatgrid: beats are strictly monotonic",
      len(beats) > 20 and all(b2 > b1 for b1, b2 in zip(beats, beats[1:])),
      f"{len(beats)} beats")
check("beatgrid: bars are every 4th beat (4/4)",
      grid["bars"] == beats[::4] and len(grid["bars"]) >= 5,
      f"{len(grid['bars'])} bars")
check("beatgrid: result is JSON-able",
      bool(__import__("json").dumps(grid)))

# ------------------------------------------------------------- speedramp
import speedramp

clip = os.path.join(TD, "clip4s.mp4")
_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=320x240:d=4:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", clip])

spec = [
    {"type": "normal", "duration": 1.0},
    {"type": "ramp_down", "duration": 1.0, "factor": 0.25},
    {"type": "hold_slow", "duration": 1.0, "factor": 0.25},
    {"type": "ramp_back", "duration": 1.0},
]
# closed form: 1/1 + ln(0.25)/(-0.75) + 1/0.25 + ln(4)/(0.75)
expected_math = 1.0 + math.log(0.25) / (0.25 - 1.0) + 4.0 \
    + math.log(1.0 / 0.25) / (1.0 - 0.25)
exp = speedramp.expected_duration(spec, 4.0)
check("speedramp: expected duration matches closed-form math",
      abs(exp - expected_math) < 0.01, f"exp={exp} math={expected_math}")

out = os.path.join(TD, "ramped.mp4")
res = speedramp.render(clip, out, spec)
check("speedramp: output file exists",
      os.path.exists(out) and os.path.getsize(out) > 0)
check("speedramp: rendered duration matches expected within 0.25s",
      abs(res["actual_duration"] - res["expected_duration"]) <= 0.25,
      f"actual={res['actual_duration']} expected={res['expected_duration']}")

# speed-up path (setpts supports up to 4x via the same machinery)
exp_up = speedramp.expected_duration(
    [{"type": "speed", "duration": 2.0, "factor": 2.0}], 2.0)
check("speedramp: 2x speed-up halves the duration",
      abs(exp_up - 1.0) < 1e-6, f"{exp_up}")

# whitelist validation
for bad, label in (
        ([{"type": "speed", "duration": 1.0, "factor": 5.0}], "factor 5.0"),
        ([{"type": "speed", "duration": 1.0, "factor": 0.05}], "factor 0.05"),
        ([{"type": "warp", "duration": 1.0}], "unknown type"),
        ([{"type": "normal", "duration": 0}], "zero duration")):
    try:
        speedramp.validate_spec(bad)
        ok = False
    except ValueError:
        ok = True
    check(f"speedramp: whitelist rejects {label}", ok)

print(f"\ntoolstest: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
