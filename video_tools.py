"""Julie agent engine: VIDEO ANALYSIS TOOLS (tested 2026-11-28).

Two read-only tools that give the loop measured facts about a
workspace video/audio file instead of guesses:

  video_scene_list       shot boundaries via PySceneDetect
                         (BSD-3-Clause). Tested on real footage:
                         hard cuts are found reliably; gradual
                         crossfades in dark footage can merge
                         neighbouring shots (5-7 of 9 known
                         segments on the loneliness v2 reel), so
                         treat the list as a floor, not gospel.
  video_word_transcript  word-level timestamps via faster-whisper
                         (MIT), local only. Tested: exact
                         transcripts + per-word times on the
                         loneliness VO segments. Julie's older
                         autoedit.transcript() returns plain text
                         only; this tool adds word timing, caption
                         cues, and pause cut candidates.

Both tools lazy-import their heavy dependencies. When a dependency
or ffmpeg is absent the handler returns a FAILED step naming the
missing piece — never an exception, never a fabricated result.
Audio is decoded through ffmpeg to raw float32 because the PyAV
build bundled with some faster-whisper installs rejects files
directly (observed 2026-11-28).

Paths are confined to the job workspace with the same helper the
E2.5 file tools use.
"""

import os
import subprocess

import workspace_tools


# --- pure helpers (rig-tested without heavy deps) -----------------

def scenes_from_boundaries(boundaries, duration, min_scene_s=0.5):
    """Scene list from cut boundary seconds.

    boundaries: sorted cut times (seconds, excluding 0). Scenes
    shorter than min_scene_s are merged into the previous scene.
    Returns [{start, end, duration}] rounded to 2dp.
    """
    dur = float(duration or 0)
    cuts = sorted({round(float(b), 2) for b in (boundaries or [])
                   if 0 < float(b) < dur})
    points = [0.0] + cuts + [dur]
    scenes = []
    for a, b in zip(points, points[1:]):
        if scenes and (b - a) < min_scene_s:
            scenes[-1]["end"] = round(b, 2)
            scenes[-1]["duration"] = round(b - scenes[-1]["start"], 2)
        else:
            scenes.append({"start": round(a, 2), "end": round(b, 2),
                           "duration": round(b - a, 2)})
    return scenes


def words_to_cues(words, max_chars=42, max_gap=0.8):
    """Group timed words into caption cues.

    words: [{word, start, end}]. A cue breaks when adding the next
    word would exceed max_chars or the gap before it exceeds
    max_gap seconds. Returns [{start, end, text}].
    """
    cues, cur = [], None
    for w in words or []:
        word = str(w.get("word", "")).strip()
        if not word:
            continue
        start, end = float(w["start"]), float(w["end"])
        if cur is None:
            cur = {"start": start, "end": end, "text": word}
            continue
        gap = start - cur["end"]
        if gap > max_gap or len(cur["text"]) + 1 + len(word) > max_chars:
            cues.append(cur)
            cur = {"start": start, "end": end, "text": word}
        else:
            cur["text"] += " " + word
            cur["end"] = end
    if cur:
        cues.append(cur)
    return [{"start": round(c["start"], 2), "end": round(c["end"], 2),
             "text": c["text"]} for c in cues]


def pause_cut_points(words, min_gap=0.6):
    """Cut candidates at pauses between words.

    Returns [{after_word, gap_start, gap_end, gap}] for every
    inter-word gap >= min_gap seconds — the safe places to cut
    speech without clipping a word.
    """
    out = []
    ws = [w for w in (words or []) if str(w.get("word", "")).strip()]
    for prev, nxt in zip(ws, ws[1:]):
        gap = float(nxt["start"]) - float(prev["end"])
        if gap >= min_gap:
            out.append({"after_word": str(prev["word"]).strip(),
                        "gap_start": round(float(prev["end"]), 2),
                        "gap_end": round(float(nxt["start"]), 2),
                        "gap": round(gap, 2)})
    return out


# --- media probes --------------------------------------------------

def _duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def _decode_audio(path):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le",
         "-ac", "1", "-ar", "16000", "-"], capture_output=True)
    if p.returncode != 0 or not p.stdout:
        return None
    import numpy as np
    return np.frombuffer(p.stdout, dtype=np.float32)


# --- tool bodies ---------------------------------------------------

def scene_list(path, threshold=27.0):
    try:
        from scenedetect import ContentDetector, detect
    except ImportError:
        return (False, "video_scene_list unavailable: scenedetect "
                       "is not installed on this runner")
    duration = _duration(path)
    if duration <= 0:
        return (False, f"video_scene_list: cannot read duration of {path!r}")
    try:
        found = detect(path, ContentDetector(threshold=float(threshold)))
    except Exception as e:  # noqa: BLE001 - report, never crash the loop
        return (False, f"video_scene_list failed: {e}")
    boundaries = [s.seconds for s, _e in found if s.seconds > 0]
    scenes = scenes_from_boundaries(boundaries, duration)
    return (True, {"duration": round(duration, 2),
                   "scene_count": len(scenes), "scenes": scenes,
                   "note": "gradual crossfades can merge shots; "
                           "treat as a floor"})


def word_transcript(path, model_name=None):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return (False, "video_word_transcript unavailable: "
                       "faster-whisper is not installed on this runner")
    audio = _decode_audio(path)
    if audio is None:
        return (False, f"video_word_transcript: cannot decode audio of {path!r}")
    name = model_name or os.getenv("LOCAL_WHISPER", "tiny")
    try:
        model = WhisperModel(name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio, word_timestamps=True)
        segs, words = [], []
        for s in segments:
            segs.append({"start": round(s.start, 2),
                         "end": round(s.end, 2),
                         "text": s.text.strip()})
            for w in (s.words or []):
                words.append({"word": w.word.strip(),
                              "start": round(w.start, 2),
                              "end": round(w.end, 2)})
    except Exception as e:  # noqa: BLE001
        return (False, f"video_word_transcript failed: {e}")
    return (True, {"language": getattr(info, "language", None),
                   "model": name, "segments": segs, "words": words,
                   "cues": words_to_cues(words),
                   "pause_cuts": pause_cut_points(words)})


# --- registration --------------------------------------------------

def register_video_tools(reg, root):
    """Register the read-only video analysis tools, confined to the
    job workspace root."""
    root_real = os.path.realpath(root)

    def _scene(args):
        target = workspace_tools._confined(root_real, args.get("path"))
        if target is None:
            return (False, workspace_tools._refused(args.get("path")))
        return scene_list(target, args.get("threshold") or 27.0)

    def _transcript(args):
        target = workspace_tools._confined(root_real, args.get("path"))
        if target is None:
            return (False, workspace_tools._refused(args.get("path")))
        return word_transcript(target, args.get("model"))

    reg.register(
        "video_scene_list",
        "List shot boundaries of a workspace video (PySceneDetect). Args: {path, threshold?}. Returns duration + scenes [{start,end,duration}]. Crossfades can merge shots — a floor, not gospel. Read-only.",
        {"path": {"type": "string", "required": True,
                  "desc": "workspace-relative video path"},
         "threshold": {"type": "number", "required": False,
                       "desc": "content threshold (default 27; lower = more cuts)"}},
        _scene, mutating=False, needs_allow=False, timeout=600)
    reg.register(
        "video_word_transcript",
        "Transcribe a workspace audio/video file locally with per-word timestamps (faster-whisper). Args: {path, model?}. Returns segments, words, caption cues, and pause cut points. Read-only, no network.",
        {"path": {"type": "string", "required": True,
                  "desc": "workspace-relative audio/video path"},
         "model": {"type": "string", "required": False,
                   "desc": "whisper model name (default LOCAL_WHISPER or tiny)"}},
        _transcript, mutating=False, needs_allow=False, timeout=900)
