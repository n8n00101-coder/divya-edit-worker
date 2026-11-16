"""colour_lint.py — Julie: per-shot colour / exposure lint (advisory).

Deterministic, ffmpeg-only (plus numpy for histogram maths). For each
shot it measures, via ffmpeg's `signalstats` filter:

    YMIN / YLOW   shadow floor + 1st-percentile luma
    YAVG          mean luma (exposure)
    YHIGH / YMAX  99th-percentile + peak luma
    SATAVG        mean saturation

plus a *selective histogram* pass: a few frames per shot are decoded
as raw greyscale and the fraction of pixels pinned at the black floor
(<=18) and at the white ceiling (>=234) is measured directly. The
histogram is what separates "a dark scene" (legit) from "crushed
blacks" (a third of the frame nailed to the floor with YLOW pinned).

Limited-range yuv420p anchors: black = 16, white = 235.

Findings (one dict per problem — a clean shot produces none):

    {"shot": <index or label>, "metric": <name>, "value": <number>,
     "verdict": "WARN" | "FAIL", "detail": <human line>,
     "scene": <scene id>, "start": s, "end": e}

Metrics: crushed_blacks, blown_highlights, underexposure,
overexposure, exposure_drift, colour_drift. Drift compares shots
that share a `scene` id (consecutive shots of the same scene should
not jump in exposure / saturation).

This module NEVER raises on a bad file: measurement failure returns
a single UNVERIFIED finding so callers stay honest (media_qc turns
every finding into a WARN — this lint is advisory by design).
"""

import json
import os
import re
import subprocess

DEFAULTS = {
    "black_floor": 18,        # Y <= this counts as "at the floor"
    "white_ceiling": 234,     # Y >= this counts as "at the ceiling"
    "crush_frame_frac": 0.60,  # >= this share of frames YLOW-pinned…
    "crush_hist_frac": 0.30,   # …and >= this share of pixels at floor
    "blown_frame_frac": 0.60,
    "blown_hist_frac": 0.20,
    "underexp_yavg": 45.0,    # shot mean luma below -> FAIL
    "underexp_warn": 60.0,    # below -> WARN
    "overexp_yavg": 215.0,
    "drift_yavg_abs": 28.0,   # same-scene consecutive-shot YAVG jump
    "drift_sat_abs": 35.0,    # same-scene SATAVG jump
}

_KEYS = ("YMIN", "YLOW", "YAVG", "YHIGH", "YMAX", "SATAVG")


def _cfg(cfg):
    out = dict(DEFAULTS)
    for k, v in (cfg or {}).items():
        if k in out and isinstance(v, (int, float)):
            out[k] = v
    return out


def _run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout)


def _probe_duration(path):
    try:
        r = _run(["ffprobe", "-v", "error", "-show_entries",
                  "format=duration", "-of", "json", str(path)],
                 timeout=60)
        return float((json.loads(r.stdout or "{}").get("format")
                      or {}).get("duration") or 0)
    except Exception:
        return 0.0


def _normalise_shots(shots, duration):
    """Accept None / [(start, end[, scene])] / [{start, end, scene,
    label}] and return a uniform list of shot dicts."""
    if not shots:
        return [{"index": 0, "label": "shot 1", "start": 0.0,
                 "end": float(duration or 0), "scene": 0}]
    out = []
    for i, s in enumerate(shots):
        if isinstance(s, dict):
            start = float(s.get("start", 0))
            end = float(s.get("end", s.get("start", 0)))
            scene = s.get("scene", 0)
            label = s.get("label") or f"shot {i + 1}"
        else:
            start, end = float(s[0]), float(s[1])
            scene = s[2] if len(s) > 2 else 0
            label = f"shot {i + 1}"
        out.append({"index": i, "label": label, "start": start,
                    "end": max(end, start), "scene": scene})
    return out


_FRAME_RE = re.compile(r"pts_time:([\d.]+)")
_STAT_RE = re.compile(r"lavfi\.signalstats\.(\w+)=([\d.]+)")


def _signalstats(path):
    """Per-frame signalstats rows: [{t, YMIN, YLOW, YAVG, ...}]."""
    r = _run(["ffmpeg", "-v", "info", "-i", str(path), "-vf",
              "signalstats,metadata=mode=print", "-an", "-f", "null",
              "-"], timeout=600)
    frames, cur = [], None
    for line in (r.stderr or "").splitlines():
        m = _FRAME_RE.search(line)
        if m and "frame:" in line:
            cur = {"t": float(m.group(1))}
            frames.append(cur)
            continue
        m = _STAT_RE.search(line)
        if m and cur is not None and m.group(1) in _KEYS:
            cur[m.group(1)] = float(m.group(2))
    return [f for f in frames if "YAVG" in f]


def _histogram_fractions(path, shot, cfg):
    """(frac_at_black_floor, frac_at_white_ceiling) from up to 3
    raw greyscale frames sampled inside the shot. (None, None) when
    decoding fails."""
    import numpy as np
    dur = max(shot["end"] - shot["start"], 0.1)
    fracs_lo, fracs_hi = [], []
    for frac in (0.25, 0.5, 0.75):
        t = shot["start"] + dur * frac
        try:
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i",
                 str(path), "-frames:v", "1", "-f", "rawvideo",
                 "-pix_fmt", "gray", "-"], capture_output=True,
                timeout=120)
            if not r.stdout:
                continue
            arr = np.frombuffer(r.stdout, dtype=np.uint8)
            fracs_lo.append(float((arr <= cfg["black_floor"]).mean()))
            fracs_hi.append(
                float((arr >= cfg["white_ceiling"]).mean()))
        except Exception:
            continue
    if not fracs_lo:
        return None, None
    return (sum(fracs_lo) / len(fracs_lo),
            sum(fracs_hi) / len(fracs_hi))


def analyse_shots(path, shots=None, cfg=None):
    """Per-shot measured stats (no verdicts). [] when unmeasurable."""
    cfg = _cfg(cfg)
    duration = _probe_duration(path)
    shots = _normalise_shots(shots, duration)
    frames = _signalstats(path)
    if not frames:
        return []
    out = []
    for shot in shots:
        rows = [f for f in frames
                if shot["start"] - 0.05 <= f["t"] < shot["end"] + 0.05] \
            or frames
        n = len(rows)
        lo_frac = sum(1 for f in rows
                      if f.get("YLOW", 99) <= cfg["black_floor"]) / n
        hi_frac = sum(1 for f in rows
                      if f.get("YHIGH", 0) >= cfg["white_ceiling"]) / n
        hist_lo, hist_hi = _histogram_fractions(path, shot, cfg)
        out.append({
            **shot,
            "frames": n,
            "yavg": sum(f["YAVG"] for f in rows) / n,
            "satavg": sum(f.get("SATAVG", 0.0) for f in rows) / n,
            "ymin_min": min(f.get("YMIN", 0) for f in rows),
            "ymax_max": max(f.get("YMAX", 0) for f in rows),
            "ylow_pinned_frac": lo_frac,
            "yhigh_pinned_frac": hi_frac,
            "hist_black_frac": hist_lo,
            "hist_white_frac": hist_hi,
        })
    return out


def lint_file(path, shots=None, cfg=None):
    """Lint one file. Returns a list of finding dicts (problems
    only); an unmeasurable file yields one UNVERIFIED finding."""
    cfg = _cfg(cfg)
    if not os.path.exists(str(path)):
        return [{"shot": None, "metric": "probe", "value": 0,
                 "verdict": "UNVERIFIED",
                 "detail": "colour lint: file not found",
                 "scene": None, "start": None, "end": None}]
    try:
        stats = analyse_shots(path, shots, cfg)
    except Exception as e:
        stats = []
        err = str(e)[:80]
    else:
        err = ""
    if not stats:
        return [{"shot": None, "metric": "probe", "value": 0,
                 "verdict": "UNVERIFIED",
                 "detail": f"colour lint could not measure the file"
                           f"{(': ' + err) if err else ''}",
                 "scene": None, "start": None, "end": None}]
    findings = []

    def add(st, metric, value, verdict, detail):
        findings.append({
            "shot": st["label"], "metric": metric,
            "value": round(float(value), 3), "verdict": verdict,
            "detail": detail, "scene": st["scene"],
            "start": round(st["start"], 2),
            "end": round(st["end"], 2)})

    for st in stats:
        # crushed blacks: percentile pinned AND histogram mass at floor
        hist_lo = st["hist_black_frac"]
        if st["ylow_pinned_frac"] >= cfg["crush_frame_frac"] and \
                hist_lo is not None and hist_lo >= cfg["crush_hist_frac"]:
            add(st, "crushed_blacks", hist_lo, "FAIL",
                f"{st['label']}: {hist_lo:.0%} of pixels at the black "
                f"floor, YLOW pinned in {st['ylow_pinned_frac']:.0%} "
                f"of frames — shadow detail crushed")
        elif st["ylow_pinned_frac"] >= cfg["crush_frame_frac"]:
            add(st, "crushed_blacks",
                st["ylow_pinned_frac"], "WARN",
                f"{st['label']}: YLOW pinned at the black floor in "
                f"{st['ylow_pinned_frac']:.0%} of frames")
        # blown highlights: mirror image at the white ceiling
        hist_hi = st["hist_white_frac"]
        if st["yhigh_pinned_frac"] >= cfg["blown_frame_frac"] and \
                hist_hi is not None and hist_hi >= cfg["blown_hist_frac"]:
            add(st, "blown_highlights", hist_hi, "FAIL",
                f"{st['label']}: {hist_hi:.0%} of pixels at the white "
                f"ceiling, YHIGH pinned in "
                f"{st['yhigh_pinned_frac']:.0%} of frames — highlights blown")
        elif st["yhigh_pinned_frac"] >= cfg["blown_frame_frac"]:
            add(st, "blown_highlights",
                st["yhigh_pinned_frac"], "WARN",
                f"{st['label']}: YHIGH pinned at the white ceiling in "
                f"{st['yhigh_pinned_frac']:.0%} of frames")
        # exposure level
        if st["yavg"] < cfg["underexp_yavg"]:
            add(st, "underexposure", st["yavg"], "FAIL",
                f"{st['label']}: mean luma {st['yavg']:.0f} — underexposed")
        elif st["yavg"] < cfg["underexp_warn"]:
            add(st, "underexposure", st["yavg"], "WARN",
                f"{st['label']}: mean luma {st['yavg']:.0f} — dark shot")
        elif st["yavg"] > cfg["overexp_yavg"]:
            add(st, "overexposure", st["yavg"], "WARN",
                f"{st['label']}: mean luma {st['yavg']:.0f} — overexposed")
    # drift between consecutive shots of the SAME scene
    for prev, cur in zip(stats, stats[1:]):
        if prev["scene"] != cur["scene"]:
            continue
        dy = cur["yavg"] - prev["yavg"]
        if abs(dy) > cfg["drift_yavg_abs"]:
            add(cur, "exposure_drift", dy, "WARN",
                f"{cur['label']}: mean luma {cur['yavg']:.0f} vs "
                f"{prev['label']} {prev['yavg']:.0f} "
                f"({dy:+.0f}) in the same scene — exposure drift")
        ds = cur["satavg"] - prev["satavg"]
        if abs(ds) > cfg["drift_sat_abs"]:
            add(cur, "colour_drift", ds, "WARN",
                f"{cur['label']}: saturation {cur['satavg']:.0f} vs "
                f"{prev['label']} {prev['satavg']:.0f} "
                f"({ds:+.0f}) in the same scene — colour drift")
    return findings


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(lint_file(sys.argv[1]), indent=1))
    else:
        print("colour_lint: pass a media file path to lint it")
