"""Julie agent engine: STYLE-COPY + SCRIPT/AUDIO QC tools.

Antigravity-equivalent pieces, deterministic and measured:

  style_profile_extract  reference-video style from MEASURED data:
                         shot pacing (from video_scene_list scenes),
                         palette (from supplied color samples),
                         loudness — returned as a style profile with
                         a brand_patch the brand system can adopt.
  script_check           measures a voiceover script (words, WPM
                         estimate, hook length, AI-tell phrases,
                         locked outro). Measures; never judges taste.
  audio_loudness         ffmpeg ebur128 integrated LUFS + true
                         peak for a workspace file (the edit-kit's
                         final-check measurement, as an agent tool).

All read-only. audio_loudness loads ffmpeg lazily; a missing
binary is a FAILED step, never a crash or an invented number.
"""
import os
import re
import statistics
import subprocess

import workspace_tools

_AI_TELLS = [
    "delve", "tapestry", "in today's fast-paced", "ever-evolving",
    "game-changer", "game changer", "revolutionize", "unlock the power",
    "unleash", "seamless", "cutting-edge", "next level",
    "take it to the next level", "look no further", "imagine a world",
    "buckle up", "let's dive in", "without further ado",
    "it's not just", "more than just", "the best part?",
    "here's the thing", "picture this", "transform the way",
    "great question", "supercharge", "harness", "leverage", "robust",
    "in conclusion", "furthermore", "moreover",
]


def style_profile(scenes, palette_samples=None, loudness_lufs=None):
    """Pacing + palette from measured inputs. scenes: [{start,end}]
    or [{duration}]. palette_samples: list of '#rrggbb' strings."""
    durs = []
    for s in scenes or []:
        if not isinstance(s, dict):
            continue
        if isinstance(s.get("duration"), (int, float)):
            durs.append(float(s["duration"]))
        elif isinstance(s.get("start"), (int, float)) and \
                isinstance(s.get("end"), (int, float)):
            durs.append(float(s["end"]) - float(s["start"]))
    durs = [d for d in durs if d > 0]
    pacing = None
    if durs:
        total = sum(durs)
        pacing = {
            "shots": len(durs),
            "avg_shot_s": round(total / len(durs), 2),
            "median_shot_s": round(statistics.median(durs), 2),
            "min_shot_s": round(min(durs), 2),
            "max_shot_s": round(max(durs), 2),
            "cuts_per_min": round(len(durs) / (total / 60.0), 2)
            if total > 0 else None,
        }
    palette = []
    counts = {}
    for c in palette_samples or []:
        c = str(c or "").strip().lower()
        if re.match(r"^#[0-9a-f]{6}$", c):
            counts[c] = counts.get(c, 0) + 1
    for c, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        palette.append({"color": c, "samples": n})
    brand_patch = {}
    if pacing:
        brand_patch["pacing"] = {"avg_shot_s": pacing["avg_shot_s"]}
    if palette:
        brand_patch["colors"] = {"primary": palette[0]["color"]}
        if len(palette) > 1:
            brand_patch["colors"]["accent"] = palette[1]["color"]
    return {"pacing": pacing, "palette": palette,
            "loudness_lufs": loudness_lufs, "brand_patch": brand_patch}


def script_check(text, wpm=150, short=False, outro=None):
    """Measure a script. Returns words, estimated seconds at wpm,
    first-sentence (hook) word count, AI-tell hits, outro verdict."""
    body = str(text or "")
    words = re.findall(r"[A-Za-z0-9']+", body)
    n = len(words)
    rate = wpm if isinstance(wpm, (int, float)) and wpm > 0 else 150
    first = re.split(r"[.!?]", body.strip(), maxsplit=1)[0] if body.strip() else ""
    hook_words = len(re.findall(r"[A-Za-z0-9']+", first))
    low = body.lower()
    tells = [t for t in _AI_TELLS if t in low]
    issues = []
    if short and hook_words > 8:
        issues.append(f"short hook is {hook_words} words — aim for 8 or fewer")
    if tells:
        issues.append("AI-tell phrases present: " + ", ".join(tells))
    outro_ok = None
    if outro:
        outro_ok = body.strip().endswith(str(outro).strip())
        if not outro_ok:
            issues.append("script does not end with the locked outro line")
    return {"words": n, "est_seconds": round(n / rate * 60, 1),
            "wpm": rate, "hook_words": hook_words,
            "ai_tells": tells, "outro_ok": outro_ok,
            "issues": issues, "ok": not issues}


def audio_loudness(path):
    """Integrated LUFS + true peak via ffmpeg ebur128."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", path,
             "-af", "ebur128=peak=true", "-f", "null", "-"],
            capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        return False, "audio_loudness FAILED: ffmpeg not available"
    except subprocess.TimeoutExpired:
        return False, "audio_loudness FAILED: ffmpeg timed out"
    err = proc.stderr or ""
    integ = re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", err)
    peak = re.findall(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", err)
    if not integ:
        return False, "audio_loudness FAILED: no loudness summary in ffmpeg output"
    return True, {"integrated_lufs": float(integ[-1]),
                  "true_peak_dbfs": float(peak[-1]) if peak else None,
                  "youtube_target_lufs": -14.0}


def register_style_tools(reg, root):
    root_real = os.path.realpath(root)

    def _loud(args):
        target = workspace_tools._confined(root_real, args.get("path"))
        if target is None:
            return False, workspace_tools._refused(args.get("path"))
        return audio_loudness(target)

    reg.register(
        "style_profile_extract",
        "Build a style profile from MEASURED data: scenes "
        "[{start,end}] (from video_scene_list), palette_samples "
        "['#rrggbb'], loudness_lufs?. Returns pacing stats, "
        "palette ranking, and a brand_patch. Read-only.",
        {"scenes": {"type": "array", "required": True,
                    "desc": "scene rows with start/end or duration"},
         "palette_samples": {"type": "array", "required": False,
                             "desc": "hex color samples"},
         "loudness_lufs": {"type": "number", "required": False,
                           "desc": "measured integrated LUFS"}},
        lambda a: (True, style_profile(a.get("scenes"),
                                       a.get("palette_samples"),
                                       a.get("loudness_lufs"))),
        mutating=False, needs_allow=False, timeout=30)
    reg.register(
        "script_check",
        "Measure a voiceover script: words, estimated seconds, "
        "hook length, AI-tell phrases, locked-outro check. Args: "
        "{text, wpm?, short?, outro?}. Measures only. Read-only.",
        {"text": {"type": "string", "required": True,
                  "desc": "the script text"},
         "wpm": {"type": "number", "required": False,
                 "desc": "words per minute (default 150)"},
         "short": {"type": "boolean", "required": False,
                   "desc": "short-form: hook must be <= 8 words"},
         "outro": {"type": "string", "required": False,
                   "desc": "locked outro line the script must end with"}},
        lambda a: (True, script_check(a.get("text"), a.get("wpm") or 150,
                                      bool(a.get("short")),
                                      a.get("outro"))),
        mutating=False, needs_allow=False, timeout=30)
    reg.register(
        "audio_loudness",
        "Measure integrated LUFS + true peak of a workspace "
        "audio/video file (ffmpeg ebur128; YouTube target -14 "
        "LUFS). Args: {path}. Read-only.",
        {"path": {"type": "string", "required": True,
                  "desc": "workspace-relative media path"}},
        _loud, mutating=False, needs_allow=False, timeout=320)
    return reg
