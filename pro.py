"""Julie's premium editing pack: animated word captions, pro audio, transitions, auto punch-ins, one-shot pro edit.
Every render is checked (video stream present, duration sane) before it is accepted."""
import asyncio
import json
import os
import httpx
import editor
from editor import run, duration, _out, ENC, FONT
from config import GROQ_KEY, WHISPER_MODEL

GROQ = "https://api.groq.com/openai/v1"

STYLES = {
    # name: (font size as fraction of height, base colour, highlight colour, outline)
    "bold":    (0.060, "&H00FFFFFF", "&H0000E5FF", 6),   # white, current word yellow
    "neon":    (0.055, "&H00FFFFFF", "&H00FF7CF5", 5),   # pink/purple pop
    "minimal": (0.045, "&H00FFFFFF", "&H00FFFFFF", 3),
    "green":   (0.060, "&H00FFFFFF", "&H0050FF7A", 6),
}


async def probe(path):
    p = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
        "-of", "json", path, stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    return json.loads(out or b"{}")


async def check(src, out, expect_duration=None):
    """Quality gate: reject broken renders so the user never gets a bad file."""
    info = await probe(out)
    streams = [s["codec_type"] for s in info.get("streams", [])]
    d = float(info.get("format", {}).get("duration", 0) or 0)
    if "video" not in streams or d < 0.3:
        raise RuntimeError("Render check failed (video missing). Malli try chestunna leka vere step cheppandi.")
    if expect_duration and abs(d - expect_duration) > max(1.0, expect_duration * 0.05):
        raise RuntimeError(f"Render check failed (length {d:.1f}s, expected {expect_duration:.1f}s).")
    return out


async def words(src, lang="te"):
    audio = _out("mp3")
    await run("-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", audio)
    async with httpx.AsyncClient(timeout=600) as c:
        with open(audio, "rb") as f:
            r = await c.post(f"{GROQ}/audio/transcriptions", headers={"Authorization": f"Bearer {GROQ_KEY}"},
                             data={"model": WHISPER_MODEL, "language": lang, "response_format": "verbose_json",
                                   "timestamp_granularities[]": ["word", "segment"]},
                             files={"file": ("a.mp3", f, "audio/mpeg")})
    r.raise_for_status()
    j = r.json()
    w = j.get("words") or []
    if not w:  # fall back: spread segment text evenly over its time
        for s in j.get("segments", []):
            toks = s["text"].split()
            step = (s["end"] - s["start"]) / max(len(toks), 1)
            w += [{"word": t, "start": s["start"] + i * step, "end": s["start"] + (i + 1) * step}
                  for i, t in enumerate(toks)]
    return [{"word": x["word"].strip(), "start": float(x["start"]), "end": float(x["end"])} for x in w if x["word"].strip()]


def _ts(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


async def animated_captions(src, lang="te", style="bold", words_per_line=3, position="lower", **_):
    """Word-by-word captions: the line appears with a pop, the spoken word lights up."""
    info = await probe(src)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    W, H = v["width"], v["height"]
    size_f, base, hi, outline = STYLES.get(style, STYLES["bold"])
    fs = int(H * size_f) if H > W else int(H * size_f * 1.25)
    margin = int(H * (0.28 if position == "lower" else 0.45 if position == "middle" else 0.75))
    font = os.path.splitext(os.path.basename(FONT))[0].replace("-", " ").replace(" Bold", "").replace(" Regular", "") or "Sans"
    ws = await words(src, lang)
    if not ws:
        return src
    lines = [ws[i:i + int(words_per_line)] for i in range(0, len(ws), int(words_per_line))]
    ev = []
    for ln in lines:
        for k, cur in enumerate(ln):
            end = ln[k + 1]["start"] if k + 1 < len(ln) else cur["end"]
            parts = []
            for j, w in enumerate(ln):
                txt = w["word"].upper() if lang == "en" else w["word"]
                parts.append(("{\\c" + hi + "&\\fscx112\\fscy112}" + txt + "{\\c" + base + "&\\fscx100\\fscy100}") if j == k else txt)
            pop = "{\\fad(60,0)\\t(0,90,\\fscx108\\fscy108)\\t(90,160,\\fscx100\\fscy100)}" if k == 0 else ""
            ev.append(f"Dialogue: 0,{_ts(cur['start'])},{_ts(end)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    ass = _out("ass")
    with open(ass, "w", encoding="utf-8") as f:
        f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{fs},{base},{base},&H00000000,&H80000000,1,0,0,0,100,100,1,0,1,{outline},2,2,40,40,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ev) + "\n")
    o = _out()
    fontsdir = os.path.dirname(FONT) if FONT else "/usr/share/fonts"
    await run("-i", src, "-vf", f"ass={ass}:fontsdir={fontsdir}", *ENC, o)
    return await check(src, o, await duration(src))


async def clean_audio(src, **_):
    """Noise reduction + voice EQ + broadcast loudness (-14 LUFS, YouTube/Instagram standard)."""
    o = _out()
    af = ("highpass=f=80,afftdn=nf=-25,equalizer=f=3000:t=q:w=1.5:g=3,"
          "acompressor=threshold=-20dB:ratio=3:attack=5:release=80,loudnorm=I=-14:TP=-1.5:LRA=11")
    await run("-i", src, "-af", af, "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", o)
    return await check(src, o, await duration(src))


async def music_ducked(src, music_path=None, volume=0.35, **_):
    """Background music that automatically dips whenever someone speaks."""
    if not music_path:
        raise RuntimeError("Music file (mp3) pampandi first.")
    o = _out()
    fc = (f"[1:a]volume={float(volume)},aformat=channel_layouts=stereo[m];"
          "[0:a]aformat=channel_layouts=stereo,asplit=2[v][sc];"
          "[m][sc]sidechaincompress=threshold=0.03:ratio=10:attack=20:release=400[duck];"
          "[v][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5[a]")
    await run("-i", src, "-stream_loop", "-1", "-i", music_path, "-filter_complex", fc,
              "-map", "0:v", "-map", "[a]", "-shortest", *ENC, o)
    return await check(src, o, await duration(src))


async def transitions(paths, kind="fade", dur=0.5, **_):
    """Join clips with smooth transitions (fade, slideleft, wipeleft, circleopen, smoothleft, dissolve, zoomin)."""
    norm = []
    for p in paths:
        n = _out()
        await run("-i", p, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-vf",
                  "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                  "-map", "0:v", "-map", "0:a?", "-map", "1:a", "-shortest", "-ar", "44100", "-ac", "2", *ENC, n)
        norm.append(n)
    if len(norm) == 1:
        return norm[0]
    durs = [await duration(n) for n in norm]
    inputs = sum([["-i", n] for n in norm], [])
    vf, af, off, lv, la = [], [], 0.0, "[0:v]", "[0:a]"
    for i in range(1, len(norm)):
        off += durs[i - 1] - dur
        vf.append(f"{lv}[{i}:v]xfade=transition={kind}:duration={dur}:offset={off:.2f}[v{i}]")
        af.append(f"{la}[{i}:a]acrossfade=d={dur}[a{i}]")
        lv, la = f"[v{i}]", f"[a{i}]"
    o = _out()
    await run(*inputs, "-filter_complex", ";".join(vf + af), "-map", lv, "-map", la, *ENC, o)
    return await check(None, o, sum(durs) - dur * (len(norm) - 1))


async def punch_ins(src, every=4.0, factor=1.12, **_):
    """Editor-style jump zooms: alternates normal / punched-in framing every few seconds."""
    d = await duration(src)
    f = float(factor)
    # normal segments show the full frame, punched segments show a centred crop
    vf = (f"split[a][b];[b]crop=iw/{f}:ih/{f},scale=iw*{f}:ih*{f}[z];"
          f"[a][z]overlay=enable='gte(mod(t,{2 * every}),{every})',scale=trunc(iw/2)*2:trunc(ih/2)*2")
    o = _out()
    await run("-i", src, "-filter_complex", vf, *ENC, o)
    return await check(src, o, d)


async def sharpen(src, **_):
    o = _out()
    await run("-i", src, "-vf", "unsharp=5:5:0.8:3:3:0.4,eq=contrast=1.05:saturation=1.12", *ENC, o)
    return await check(src, o, await duration(src))


async def auto_pro(src, lang="te", style="bold", music_path=None, vertical=True, **_):
    """One-shot premium Short/Reel: jump-cut silences -> 9:16 -> punch-ins -> grade -> clean audio
    -> ducked music (if sent) -> animated captions. Each step is quality-checked."""
    steps = []
    cur = src
    cur = await editor.remove_silence(cur); steps.append("silences cut")
    if vertical:
        cur = await editor.vertical(cur); steps.append("9:16")
    cur = await punch_ins(cur); steps.append("punch-in zooms")
    cur = await sharpen(cur); steps.append("sharpen + grade")
    cur = await clean_audio(cur); steps.append("clean audio -14 LUFS")
    if music_path:
        cur = await music_ducked(cur, music_path=music_path); steps.append("music with ducking")
    cur = await animated_captions(cur, lang=lang, style=style); steps.append(f"{style} animated captions")
    return cur, steps
