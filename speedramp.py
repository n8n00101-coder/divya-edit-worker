"""speedramp.py — Julie: speed-ramp rendering (slow-down / speed-up).

A ramp spec is a list of segments that together consume the input
clip IN ORDER. Each segment:

    {"type": "normal",    "duration": d}                 # 1.0x
    {"type": "speed",     "duration": d, "factor": f}    # constant fx
    {"type": "hold_slow", "duration": d, "factor": f}    # constant fx
    {"type": "ramp_down", "duration": d, "factor": f}    # ramp current -> f
    {"type": "ramp_up",   "duration": d, "factor": f}    # ramp current -> f
    {"type": "ramp_back", "duration": d}                  # ramp current -> 1.0
    {"type": "ramp",      "duration": d,
     "from_factor": a, "to_factor": b}                   # explicit ramp

`duration` is SOURCE seconds consumed by the segment. `factor` is
playback speed: 0.25 = quarter-speed slow motion, 2.0 = double
speed. Whitelist: every factor must be in [0.1, 4.0]; durations in
(0, 3600]. Anything else raises ValueError — specs are validated,
never trusted. If the spec covers less than the input, the remaining
tail is appended as a normal-speed segment; if it covers more, the
last segment is clamped to the input end.

Rendering: each ramp is expanded into constant-factor
micro-segments (piecewise-constant setpts), at most RAMP_STEPS per
ramp and never fewer than ~3 source frames per micro-segment —
ffmpeg's concat filter duplicates the frame of a 1-frame segment. For a linear ramp in
source time from a to b over d source seconds, the exact output
duration is d * ln(b/a) / (b - a) (the integral of 1/factor); the
micro-segment sum converges to it, and expected_duration() reports
the exact integral, so rendered vs expected agree well inside 0.1 s.

Video filtergraph per micro-segment:
    [0:v]trim=start=S:duration=D,setpts=(PTS-STARTPTS)/F,settb=AVTB[vN]
then concat. (No per-segment fps conversion — re-quantising every
micro-segment to whole frames inflates the total duration.)

Audio CHOICE (documented): audio is handled per SEGMENT, not per
micro-segment. Normal segments pass through; constant-factor
segments are retimed with an atempo chain (<=2x steps) and then
padded/trimmed to the segment's exact expected output duration, so
A/V stay in sync (pitch shifts with speed — accepted for ramps);
RAMP segments are MUTED (a pitch sweep sounds broken) and replaced
by silence of exactly the ramp's integral duration. Clips without
an audio stream render video-only.
"""

import json
import math
import os
import subprocess

MIN_FACTOR, MAX_FACTOR = 0.1, 4.0
MAX_SEGMENT_S = 3600.0
RAMP_STEPS = 20

_TYPES = ("normal", "speed", "hold_slow", "ramp_down", "ramp_up",
          "ramp_back", "ramp")


def _run(cmd, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout)


def probe(path):
    """(duration, has_audio, fps). duration 0.0 when unreadable."""
    try:
        r = _run(["ffprobe", "-v", "error", "-show_entries",
                  "stream=codec_type,avg_frame_rate", "-show_entries",
                  "format=duration", "-of", "json", str(path)],
                 timeout=60)
        data = json.loads(r.stdout or "{}")
    except Exception:
        return 0.0, False, 30.0
    dur = float((data.get("format") or {}).get("duration") or 0)
    has_audio = False
    fps = 30.0
    for s in data.get("streams") or []:
        if s.get("codec_type") == "audio":
            has_audio = True
        elif s.get("codec_type") == "video":
            try:
                num, den = str(s.get("avg_frame_rate", "30/1")).split("/")
                if float(den):
                    fps = float(num) / float(den)
            except Exception:
                pass
    return dur, has_audio, fps


def _check_factor(f, where):
    f = float(f)
    if not (MIN_FACTOR <= f <= MAX_FACTOR):
        raise ValueError(
            f"{where}: factor {f} outside whitelist "
            f"[{MIN_FACTOR}, {MAX_FACTOR}]")
    return f


def validate_spec(spec):
    """Validate + normalise a ramp spec. Returns a list of segments
    with explicit from_factor/to_factor/duration. Raises ValueError."""
    if not isinstance(spec, (list, tuple)) or not spec:
        raise ValueError("speedramp spec must be a non-empty list")
    out = []
    current = 1.0
    for i, seg in enumerate(spec):
        if not isinstance(seg, dict):
            raise ValueError(f"segment {i}: not a dict")
        kind = str(seg.get("type", "speed")).lower()
        if kind not in _TYPES:
            raise ValueError(f"segment {i}: unknown type {kind!r}")
        d = float(seg.get("duration", 0))
        if not (0 < d <= MAX_SEGMENT_S):
            raise ValueError(
                f"segment {i}: duration {d} outside (0, {MAX_SEGMENT_S}]")
        if kind == "normal":
            a = b = 1.0
        elif kind in ("speed", "hold_slow"):
            a = b = _check_factor(seg.get("factor", current),
                                  f"segment {i}")
        elif kind in ("ramp_down", "ramp_up"):
            a = current
            b = _check_factor(seg.get("factor"), f"segment {i}")
        elif kind == "ramp_back":
            a, b = current, float(seg.get("factor", 1.0))
            b = _check_factor(b, f"segment {i}")
        else:  # explicit ramp
            a = _check_factor(seg.get("from_factor", current),
                              f"segment {i}")
            b = _check_factor(seg.get("to_factor", a),
                              f"segment {i}")
        out.append({"type": kind, "duration": d,
                    "from_factor": a, "to_factor": b})
        current = b
    return out


def _segment_output_duration(seg):
    """Exact output seconds for one normalised segment."""
    d, a, b = seg["duration"], seg["from_factor"], seg["to_factor"]
    if abs(b - a) < 1e-9:
        return d / a
    return d * math.log(b / a) / (b - a)


def expected_duration(spec, input_duration=None):
    """Mathematically expected output duration (seconds, float).

    With input_duration, the spec is clamped / tail-extended exactly
    as render() does, so the number predicts the rendered file."""
    segs = validate_spec(spec)
    if input_duration is not None:
        segs = _fit_to_input(segs, float(input_duration))
    return sum(_segment_output_duration(s) for s in segs)


def _fit_to_input(segs, input_duration):
    """Clamp the spec to the input length; append a normal tail
    when the spec under-covers the input."""
    out, used = [], 0.0
    for seg in segs:
        if used >= input_duration:
            break
        seg = dict(seg)
        if used + seg["duration"] > input_duration:
            seg["duration"] = input_duration - used
        out.append(seg)
        used += seg["duration"]
    if used < input_duration - 1e-6:
        out.append({"type": "normal",
                    "duration": input_duration - used,
                    "from_factor": 1.0, "to_factor": 1.0})
    return out


def _micro_segments(segs, fps=30.0):
    """Expand normalised segments into constant-factor micro
    segments: [{start, duration, factor}] in source time.

    Step count is capped so every micro-segment holds at least ~3
    source frames: ffmpeg's concat filter DUPLICATES the frame of
    a 1-frame segment, which silently inflates the output duration
    (measured: 20 steps on a 1 s / 30 fps ramp -> +19 frames)."""
    micros, t = [], 0.0
    for seg in segs:
        d, a, b = seg["duration"], seg["from_factor"], seg["to_factor"]
        if abs(b - a) < 1e-9:
            micros.append({"start": t, "duration": d, "factor": a})
        else:
            steps = max(1, min(RAMP_STEPS,
                               int(d / (3.0 / max(float(fps), 1.0)))))
            step = d / steps
            for k in range(steps):
                f0 = a + (b - a) * k / steps
                f1 = a + (b - a) * (k + 1) / steps
                micros.append({"start": t + k * step,
                               "duration": step,
                               "factor": (f0 + f1) / 2.0})
        t += d
    return micros


def _atempo_chain(factor):
    """atempo filter chain expressing one factor (each atempo step
    stays inside [0.5, 2.0])."""
    parts, f = [], float(factor)
    while f < 0.5:
        parts.append("atempo=0.5")
        f /= 0.5
    while f > 2.0:
        parts.append("atempo=2.0")
        f /= 2.0
    parts.append(f"atempo={f:.6f}")
    return ",".join(parts)


def build_filtergraph(spec, input_duration, has_audio=True, fps=30.0):
    """Return (filter_complex, micros) for a validated spec fitted
    to the input. Pure string building — unit-testable without
    rendering."""
    segs = _fit_to_input(validate_spec(spec), float(input_duration))
    micros = _micro_segments(segs, fps=fps)
    lines = []
    v_labels = []
    for i, m in enumerate(micros):
        lines.append(
            f"[0:v]trim=start={m['start']:.4f}:duration={m['duration']:.4f},"
            f"setpts=(PTS-STARTPTS)/{m['factor']:.6f},settb=AVTB[v{i}]")
        v_labels.append(f"[v{i}]")
    lines.append("".join(v_labels) + f"concat=n={len(micros)}:v=1:a=0[outv]")
    if has_audio:
        # per-SEGMENT audio (see module docstring for the choice):
        # exact-length segments keep A/V locked to the video maths.
        a_labels, t = [], 0.0
        for j, seg in enumerate(segs):
            out_d = _segment_output_duration(seg)
            base = (f"[0:a]atrim=start={t:.4f}:"
                    f"duration={seg['duration']:.4f},asetpts=PTS-STARTPTS")
            if seg["from_factor"] != seg["to_factor"]:
                # ramp: muted, silence of exactly the integral length
                lines.append(
                    f"{base},volume=0,apad,atrim=0:{out_d:.4f}[a{j}]")
            elif seg["from_factor"] == 1.0:
                lines.append(f"{base}[a{j}]")
            else:
                lines.append(
                    f"{base},{_atempo_chain(seg['from_factor'])},"
                    f"apad,atrim=0:{out_d:.4f}[a{j}]")
            a_labels.append(f"[a{j}]")
            t += seg["duration"]
        lines.append("".join(a_labels)
                     + f"concat=n={len(segs)}:v=0:a=1[outa]")
    return ";".join(lines), micros


def render(input_path, output_path, spec):
    """Render the ramped clip. Returns a dict with the output path,
    the mathematically expected duration, the measured duration and
    the segment plan. Raises ValueError on a bad spec and
    RuntimeError when ffmpeg fails."""
    duration, has_audio, fps = probe(input_path)
    if not duration:
        raise RuntimeError(f"speedramp: cannot probe {input_path}")
    expected = expected_duration(spec, duration)
    fc, micros = build_filtergraph(spec, duration, has_audio, fps=fps)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(input_path),
           "-filter_complex", fc, "-map", "[outv]"]
    if has_audio:
        cmd += ["-map", "[outa]", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(output_path)]
    r = _run(cmd)
    if r.returncode != 0 or not os.path.exists(str(output_path)):
        raise RuntimeError(
            f"speedramp render failed: {(r.stderr or '')[:200]}")
    actual = probe(output_path)[0]
    return {
        "output": str(output_path),
        "expected_duration": round(expected, 4),
        "actual_duration": round(actual, 4),
        "input_duration": round(duration, 4),
        "segments": micros,
        "filtergraph": fc,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 3:
        spec = json.loads(sys.argv[3])
        print(json.dumps(render(sys.argv[1], sys.argv[2], spec),
                         indent=1, default=str))
    else:
        print("speedramp: input output '<spec json>'")
