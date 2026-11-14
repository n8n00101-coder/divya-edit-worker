"""media_qc.py — Julie v85: deterministic inspection of the ACTUAL
rendered media (assembled long video or a single chapter/short).

v84 audited the assembled long file only through compliance.audit_media
(probe + loudness + silence + a coarse 1-frame/4 s still check). That
missed the defects Ajju actually saw ship: blank-blue frames, black
frames, frozen stretches, A/V duration mismatch, missing audio,
per-chapter colour drift and repeated visual stretches. This module
measures the FILE with ffmpeg/ffprobe only — no model calls, no new
dependencies (ffmpeg, ffprobe, Pillow, numpy — all production deps).

Checks (rule ids MQ-*; each maps to a time interval, and — when
chapter start times are given — to the chapter that contains it):

- MQ-PROBE   file unreadable / no video stream / no audio stream
- MQ-ASPECT  rendered size differs from the expected size (when known)
- MQ-AVSYNC  audio and video stream durations differ by > threshold
- MQ-BLACK   blackdetect segments (near-black frames) beyond a blip
- MQ-FREEZE  freezedetect segments (video frozen while time passes)
- MQ-BLANK   sampled frames that are (near-)solid colour — incl. the
             blank-BLUE frame (solid navy background, no content)
- MQ-LOUD    integrated loudness / true peak vs configurable targets
- MQ-SILENCE silence gaps > threshold outside chapter breaks
- MQ-COLOUR  per-chapter mean-luma drift beyond threshold (the same
             scene family suddenly much darker/lighter = grade break)
- MQ-REPEAT  repeated visual stretches: sampled-frame dHashes that
             recur at distant timestamps (reused footage/graphics)
- MQ-CUTS    scene-cut density (0 cuts in a long chapter = one held
             shot; reported as WARN, never a hard FAIL on its own)

Thresholds are configurable via the `cfg` dict (Knowledge Base
category "media_qc" — see edit_memory.seed_knowledge_base notes and
the v85 defaults below). Everything is FAIL/UNVERIFIED-honest: a
measurement that cannot run yields UNVERIFIED, never PASS.
"""

import json
import os
import subprocess
import tempfile

DEFAULTS = {
    "black_min_s": 0.6,          # shorter black blips are transitions
    "black_pix_th": 0.10,        # blackdetect pixel threshold
    "freeze_min_s": 2.0,         # a held frame >= this is a defect
    "freeze_noise": 0.003,       # freezedetect noise tolerance
    "blank_std_max": 6.0,        # per-channel std below this = solid
    "blank_sample_every_s": 2.0,
    "av_mismatch_max_s": 0.5,
    "loud_target_lufs": -14.0,
    "loud_tol_lufs": 1.5,
    "peak_max_dbtp": -0.9,
    "silence_min_s": 0.8,
    "colour_drift_max": 0.35,    # relative mean-luma drift, chapter to chapter
    "repeat_hash_distance": 5,   # dHash hamming distance for "same visual"
    "repeat_min_gap_s": 8.0,     # recurrences closer than this are one stretch
    "card_allowance_s": 1.6,     # chapter title cards (1.5 s of dark
                                 # navy by design) are not black frames
}


def _in_card_window(a, b, starts, allow):
    """True when segment [a, b] lies entirely inside a chapter title
    card window — the card sits in the `allow` seconds immediately
    before a chapter's content start."""
    for s in (starts or [])[1:]:
        if a >= s - allow - 0.05 and b <= s + 0.05:
            return True
    return False


def _cfg(cfg):
    out = dict(DEFAULTS)
    for k, v in (cfg or {}).items():
        if k in out and isinstance(v, (int, float)):
            out[k] = v
    return out


def _run(cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout)


def probe(path):
    """ffprobe: duration, per-stream durations, size, fps. {} on error."""
    try:
        r = _run(["ffprobe", "-v", "error", "-show_entries",
                  "stream=codec_type,width,height,duration,avg_frame_rate",
                  "-show_entries", "format=duration",
                  "-of", "json", str(path)], timeout=60)
        data = json.loads(r.stdout or "{}")
    except Exception:
        return {}
    info = {"duration": float((data.get("format") or {}).get(
        "duration") or 0)}
    for s in data.get("streams") or []:
        if s.get("codec_type") == "video" and "video" not in info:
            info["video"] = {
                "width": s.get("width"), "height": s.get("height"),
                "duration": float(s.get("duration") or 0)}
            try:
                num, den = str(s.get("avg_frame_rate", "0/1")).split("/")
                info["video"]["fps"] = float(num) / float(den) if float(den) else 0
            except Exception:
                info["video"]["fps"] = 0
        elif s.get("codec_type") == "audio" and "audio" not in info:
            info["audio"] = {"duration": float(s.get("duration") or 0)}
    return info


def _chapter_of(t, starts):
    """Chapter index (0-based) containing timestamp t, or None."""
    if not starts:
        return None
    idx = 0
    for i, s in enumerate(starts):
        if t >= s:
            idx = i
    return idx


def _detect_segments(path, vf, start_key, end_key, timeout=600,
                     total=None):
    """Run an ffmpeg detect filter and collect (start, end) pairs
    from its log lines. blackdetect prints start AND end on one
    line; freezedetect prints only the start for a freeze that runs
    to EOF — a dangling start is closed at the file duration.
    Returns None if ffmpeg failed."""
    r = _run(["ffmpeg", "-v", "info", "-i", str(path), "-vf", vf,
              "-an", "-f", "null", "-"], timeout=timeout)
    if r.returncode != 0 and start_key not in (r.stderr or ""):
        return None
    segs, cur = [], None
    import re
    for line in (r.stderr or "").splitlines():
        ms = re.search(rf"{start_key}:\s*([\d.]+)", line)
        me = re.search(rf"{end_key}:\s*([\d.]+)", line)
        if ms:
            cur = float(ms.group(1))
        if me and cur is not None:
            segs.append((cur, float(me.group(1))))
            cur = None
    if cur is not None and total:
        segs.append((cur, float(total)))
    return segs


def black_segments(path, cfg, total=None):
    return _detect_segments(
        path, f"blackdetect=d={cfg['black_min_s']}:pic_th=0.98:"
              f"pix_th={cfg['black_pix_th']}",
        "black_start", "black_end", total=total)


def freeze_segments(path, cfg, total=None):
    return _detect_segments(
        path, f"freezedetect=n={cfg['freeze_noise']}:d={cfg['freeze_min_s']}",
        "freeze_start", "freeze_end", total=total)


def _frame_stats(path, every_s, workdir):
    """Sample frames; return [{t, mean_rgb, std, dhash}] (Pillow/numpy)."""
    import numpy as np
    from PIL import Image
    import broll_verify as bv
    out = []
    with tempfile.TemporaryDirectory(prefix="mq_frames_", dir=workdir) as td:
        _run(["ffmpeg", "-v", "error", "-i", str(path),
              "-vf", f"fps=1/{every_s},scale=96:96",
              os.path.join(td, "f%05d.jpg")], timeout=600)
        files = sorted(f for f in os.listdir(td) if f.endswith(".jpg"))
        for i, f in enumerate(files):
            fp = os.path.join(td, f)
            try:
                im = Image.open(fp).convert("RGB")
                arr = np.asarray(im, dtype=np.float32)
                out.append({
                    "t": i * every_s,
                    "mean": [float(arr[:, :, c].mean()) for c in range(3)],
                    # blank/solid = WITHIN-channel variation ~0. A
                    # whole-array std would mix the channel means
                    # themselves (solid navy 6/36/70 reads std 26).
                    "std": float(max(arr[:, :, c].std()
                                     for c in range(3))),
                    "dhash": bv.dhash_file(fp),
                })
            except Exception:
                continue
    return out


def inspect_file(path, cfg=None, chapter_starts=None, workdir=None,
                 expected_size=None):
    """Full deterministic inspection of one rendered file.
    Returns (checks, info). checks use the compliance check shape
    {rule, status, detail, scene} — `scene` carries the CHAPTER
    number (1-based) when the defect maps to one, else None."""
    cfg = _cfg(cfg)
    checks = []
    info = probe(path)
    if not info.get("duration"):
        return ([{"rule": "MQ-PROBE", "status": "FAIL",
                  "detail": "rendered file is unreadable by ffprobe",
                  "scene": None}], info)
    if "video" not in info:
        checks.append({"rule": "MQ-PROBE", "status": "FAIL",
                       "detail": "no video stream in rendered file",
                       "scene": None})
    if "audio" not in info:
        checks.append({"rule": "MQ-PROBE", "status": "FAIL",
                       "detail": "no audio stream in rendered file",
                       "scene": None})
    if expected_size and "video" in info:
        w, h = info["video"].get("width"), info["video"].get("height")
        if (w, h) != tuple(expected_size):
            checks.append({"rule": "MQ-ASPECT", "status": "FAIL",
                           "detail": f"rendered {w}x{h}, expected "
                                     f"{expected_size[0]}x{expected_size[1]}",
                           "scene": None})
    if "video" in info and "audio" in info:
        dv, da = info["video"]["duration"], info["audio"]["duration"]
        if dv and da and abs(dv - da) > cfg["av_mismatch_max_s"]:
            checks.append({"rule": "MQ-AVSYNC", "status": "FAIL",
                           "detail": f"video {dv:.1f}s vs audio {da:.1f}s "
                                     f"(mismatch {abs(dv - da):.1f}s)",
                           "scene": None})
    # --- black + freeze segments, mapped to chapters
    for rule, segs, label in (
            ("MQ-BLACK", black_segments(path, cfg, info["duration"]),
             "black frames"),
            ("MQ-FREEZE", freeze_segments(path, cfg, info["duration"]),
             "frozen frames")):
        if segs is None:
            checks.append({"rule": rule, "status": "UNVERIFIED",
                           "detail": f"{label} detection could not run",
                           "scene": None})
            continue
        for a, b in segs:
            if rule == "MQ-BLACK" and _in_card_window(
                    a, b, chapter_starts, cfg["card_allowance_s"]):
                continue  # a chapter title card, not a defect
            ch = _chapter_of(a, chapter_starts)
            checks.append({
                "rule": rule, "status": "FAIL",
                "detail": f"{label} {a:.1f}s-{b:.1f}s ({b - a:.1f}s)",
                "scene": (ch + 1) if ch is not None else None,
                "start": round(a, 2), "end": round(b, 2)})
    # --- sampled-frame analysis: blank/solid, colour drift, repeats
    try:
        stats = _frame_stats(path, cfg["blank_sample_every_s"], workdir)
    except Exception as e:
        stats = None
        checks.append({"rule": "MQ-BLANK", "status": "UNVERIFIED",
                       "detail": f"frame sampling failed: {str(e)[:80]}",
                       "scene": None})
    if stats:
        for s in stats:
            if s["std"] < cfg["blank_std_max"] and not _in_card_window(
                    s["t"], s["t"] + 0.1, chapter_starts,
                    cfg["card_allowance_s"]):
                r, g, b = s["mean"]
                kind = ("blank BLUE frame" if b > r + 25 and b > g + 10
                        else "blank/solid frame")
                ch = _chapter_of(s["t"], chapter_starts)
                checks.append({
                    "rule": "MQ-BLANK", "status": "FAIL",
                    "detail": f"{kind} at {s['t']:.0f}s "
                              f"(mean RGB {r:.0f}/{g:.0f}/{b:.0f}, "
                              f"std {s['std']:.1f})",
                    "scene": (ch + 1) if ch is not None else None,
                    "start": round(s["t"], 2),
                    "end": round(s["t"] + cfg["blank_sample_every_s"], 2)})
        # colour consistency: mean luma per chapter window
        if chapter_starts and len(chapter_starts) > 1:
            luma = {}
            for s in stats:
                ch = _chapter_of(s["t"], chapter_starts)
                luma.setdefault(ch, []).append(
                    0.2126 * s["mean"][0] + 0.7152 * s["mean"][1]
                    + 0.0722 * s["mean"][2])
            means = {c: sum(v) / len(v) for c, v in luma.items() if v}
            base = means.get(0)
            if base:
                for c, m in sorted(means.items()):
                    if c and base > 8 and abs(m - base) / base > cfg["colour_drift_max"]:
                        checks.append({
                            "rule": "MQ-COLOUR", "status": "WARN",
                            "detail": f"chapter {c + 1} mean luma {m:.0f} "
                                      f"vs chapter 1 {base:.0f} "
                                      f"({(m - base) / base:+.0%}) — grade drift",
                            "scene": c + 1})
        # repeated visual stretches (distant dHash recurrences)
        seen = {}
        for s in stats:
            h = s.get("dhash")
            if not h:
                continue
            for prev_t, prev_h in seen.items():
                import broll_verify as bv
                if abs(s["t"] - prev_t) >= cfg["repeat_min_gap_s"] and \
                        bv.hamming_hex(h, prev_h) <= cfg["repeat_hash_distance"]:
                    ch = _chapter_of(s["t"], chapter_starts)
                    checks.append({
                        "rule": "MQ-REPEAT", "status": "WARN",
                        "detail": f"visual at {s['t']:.0f}s repeats the "
                                  f"visual at {prev_t:.0f}s (dHash near-match)",
                        "scene": (ch + 1) if ch is not None else None,
                        "start": round(s["t"], 2)})
                    break
            seen[s["t"]] = h
    # --- loudness + silence (reuse the compliance measurements)
    try:
        import compliance as comp
        i_lufs, tp = comp.measure_loudness(path)
        if i_lufs is None:
            checks.append({"rule": "MQ-LOUD", "status": "UNVERIFIED",
                           "detail": "loudness measurement failed",
                           "scene": None})
        else:
            if abs(i_lufs - cfg["loud_target_lufs"]) > cfg["loud_tol_lufs"]:
                checks.append({"rule": "MQ-LOUD", "status": "FAIL",
                               "detail": f"loudness {i_lufs:.1f} LUFS "
                                         f"(target {cfg['loud_target_lufs']:.0f} "
                                         f"± {cfg['loud_tol_lufs']})",
                               "scene": None})
            if tp is not None and tp > cfg["peak_max_dbtp"]:
                checks.append({"rule": "MQ-LOUD", "status": "FAIL",
                               "detail": f"true peak {tp:.1f} dBTP "
                                         f"(max {cfg['peak_max_dbtp']})",
                               "scene": None})
        gaps = comp.silence_gaps(path, max_gap=cfg["silence_min_s"])
        breaks = list(chapter_starts or [])[1:]
        real = [(a, b) for a, b in gaps
                if not any(abs(a - cb) < 1.6 for cb in breaks)]
        for a, b in real:
            ch = _chapter_of(a, chapter_starts)
            checks.append({"rule": "MQ-SILENCE", "status": "FAIL",
                           "detail": f"silence {a:.1f}s-{b:.1f}s "
                                     f"({b - a:.1f}s) outside chapter breaks",
                           "scene": (ch + 1) if ch is not None else None,
                           "start": round(a, 2), "end": round(b, 2)})
    except Exception as e:
        checks.append({"rule": "MQ-LOUD", "status": "UNVERIFIED",
                       "detail": f"audio checks failed: {str(e)[:80]}",
                       "scene": None})
    # --- cut density (WARN only): one held shot for a whole chapter
    try:
        r = _run(["ffmpeg", "-v", "info", "-i", str(path),
                  "-vf", "select='gt(scene,0.4)',showinfo", "-an",
                  "-f", "null", "-"], timeout=600)
        cuts = (r.stderr or "").count("showinfo")
        info["scene_cuts"] = cuts
        if info["duration"] > 45 and cuts < 3:
            checks.append({"rule": "MQ-CUTS", "status": "WARN",
                           "detail": f"only {cuts} scene cut(s) in "
                                     f"{info['duration']:.0f}s — long held shots",
                           "scene": None})
    except Exception:
        info["scene_cuts"] = None
    info["checks_summary"] = {
        s: sum(1 for c in checks if c["status"] == s)
        for s in ("FAIL", "WARN", "UNVERIFIED")}
    return checks, info


def chapter_defect_map(checks):
    """{chapter_no (1-based): [failed checks]} for corrective action.
    Only FAIL checks with a chapter/scene mapping are correctable at
    chapter level; file-level FAILs return under key None."""
    out = {}
    for c in checks or []:
        if c.get("status") != "FAIL":
            continue
        out.setdefault(c.get("scene"), []).append(c)
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        ch, inf = inspect_file(sys.argv[1])
        print(json.dumps({"checks": ch, "info": inf}, indent=1, default=str))
    else:
        print("media_qc: pass a media file path to inspect it")
