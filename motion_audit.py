"""motion_audit.py — ROUND 5: the rendered film must MOVE, and a
long-form documentary must never carry a presenter/avatar card.

Two audits live here, both pure measurement (no opinions):

1. PIXEL MOTION — audit_video() samples frames inside each beat
   of a rendered video and measures the mean absolute pixel change
   between samples. A beat whose samples barely change is a
   STATIC CARD, whatever the plan claimed: film 3 shipped title
   cards and widget stills that read as frozen slides while every
   log line said "animated". clip_motion() is the same measure
   applied to a SOURCE clip (used by hf_primary to decide which
   beats need a motion treatment before render).

2. PRESENTER / AVATAR — presenter_flags() reads the chapter's own
   scene records: a beat whose chosen visual is the polaroid
   placeholder (visuals_lib.vis_polaroid with NO real photo draws
   a flat cartoon FACE — hair, dot eyes, smile) is a presenter
   card. In a long-form documentary that is banned unless the
   brief explicitly asked for a presenter (Ajju, film 3: a cartoon
   face card sat on top of a road shot in a faceless film).

Thresholds are module constants so tests and reports cite the
same numbers. Frame extraction is ffmpeg + PIL, downscaled to
160x90 gray — cheap, and more than enough to tell "moving" from
"a still with a caption".
"""

import os
import subprocess
import tempfile

import numpy as np
from PIL import Image

# Mean absolute gray-level change (0-255 scale) below which two
# samples count as "the same picture". A slow push-in on a still
# measures ~2-6 at this size; a frozen card measures < 0.5.
STATIC_MAX_DIFF = 1.2
# A source clip under this is treated as static footage.
CLIP_STATIC_MAX_DIFF = 1.5

# Visual names that draw a presenter/avatar placeholder when no
# real photo backs them. vis_polaroid is the film-3 offender.
PRESENTER_VISUALS = {"polaroid"}


def _frame_gray(path, t, wd):
    """One frame of `path` at `t` seconds as a 160x90 float array,
    or None when extraction fails."""
    out = os.path.join(wd, f"f_{abs(hash((path, round(float(t), 3))))}.png")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{float(t):.3f}",
             "-i", str(path), "-frames:v", "1", "-vf", "scale=160:90",
             out], check=True, capture_output=True, timeout=60)
        with Image.open(out) as im:
            return np.asarray(im.convert("L"), dtype=np.float32)
    except Exception:
        return None


def _diff(a, b):
    if a is None or b is None or a.shape != b.shape:
        return None
    return float(np.mean(np.abs(a - b)))


def clip_motion(path, start=0.0, duration=None):
    """Motion of a SOURCE clip inside [start, start+duration]:
    the max mean-abs-diff between frames sampled at 15% / 50% /
    85% of the window. Returns {"max_diff": float|None,
    "static": bool|None} — None values when the clip could not
    be probed (callers must treat unknown as unknown, never as
    moving)."""
    dur = duration
    if dur is None:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=30)
            dur = float(r.stdout.strip())
        except Exception:
            return {"max_diff": None, "static": None}
    dur = max(0.4, float(dur))
    base = float(start or 0)
    times = [base + dur * f for f in (0.15, 0.5, 0.85)]
    with tempfile.TemporaryDirectory(prefix="motion_probe_") as wd:
        frames = [_frame_gray(path, t, wd) for t in times]
    diffs = [d for d in (_diff(frames[0], frames[1]),
                         _diff(frames[1], frames[2])) if d is not None]
    if not diffs:
        return {"max_diff": None, "static": None}
    m = max(diffs)
    return {"max_diff": round(m, 3), "static": m < CLIP_STATIC_MAX_DIFF}


def audit_video(path, beats):
    """Pixel-motion audit of a RENDERED video. beats = [{scene,
    start, duration}]. Each beat is sampled at 25% / 55% / 85% of
    its span; a beat whose largest sample-to-sample change is
    under STATIC_MAX_DIFF is a static card. Returns
    {"beats": [{scene, max_diff, static}], "static_beats": [scene],
     "static_share": float, "unmeasured": [scene]}."""
    out = {"beats": [], "static_beats": [], "unmeasured": []}
    with tempfile.TemporaryDirectory(prefix="motion_audit_") as wd:
        for b in beats or []:
            start = float(b.get("start") or 0)
            dur = max(0.4, float(b.get("duration") or 0))
            times = [start + dur * f for f in (0.25, 0.55, 0.85)]
            frames = [_frame_gray(path, t, wd) for t in times]
            diffs = [d for d in (_diff(frames[0], frames[1]),
                                 _diff(frames[1], frames[2]))
                     if d is not None]
            scene = b.get("scene")
            if not diffs:
                out["beats"].append({"scene": scene, "max_diff": None,
                                     "static": None})
                out["unmeasured"].append(scene)
                continue
            m = max(diffs)
            static = m < STATIC_MAX_DIFF
            out["beats"].append({"scene": scene,
                                 "max_diff": round(m, 3),
                                 "static": static})
            if static:
                out["static_beats"].append(scene)
    measured = [b for b in out["beats"] if b["static"] is not None]
    out["static_share"] = (round(len(out["static_beats"])
                                 / len(measured), 3) if measured else 0.0)
    return out


def presenter_flags(scenes, presenter_allowed=False, mapped=None):
    """The scene records that would render a presenter/avatar
    card: the chosen library visual OR the mapped plan visual is
    a presenter visual (polaroid) with no real photo behind it.
    `mapped` maps a scene's plan visual name to its library name
    (doc._VIS_NAME_MAP) — passed in so this module stays free of
    doc.py's import weight. Returns [{scene, visual}] (1-based)."""
    if presenter_allowed:
        return []
    flags = []
    for i, sc in enumerate(scenes or []):
        names = {str(sc.get("lib_visual") or ""),
                 str((mapped or {}).get(str(sc.get("visual") or "")) or ""),
                 str(sc.get("visual") or "")}
        hit = names & PRESENTER_VISUALS
        if not hit:
            continue
        photo = str(sc.get("photo") or sc.get("photo_path") or "")
        if photo and os.path.isfile(photo):
            continue        # a REAL photo in the card is content
        flags.append({"scene": i + 1, "visual": sorted(hit)[0]})
    return flags
