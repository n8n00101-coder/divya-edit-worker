"""Video editing with ffmpeg. Every op takes an input path and returns a new output path."""
import asyncio
import os
import re
import uuid
from config import DATA
import brain

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansTelugu-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf",
    "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT = next((f for f in FONT_CANDIDATES if os.path.exists(f)), "")


def _out(ext="mp4"):
    return os.path.join(DATA, f"edit_{uuid.uuid4().hex[:8]}.{ext}")


async def run(*args):
    p = await asyncio.create_subprocess_exec("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, err = await p.communicate()
    if p.returncode != 0:
        raise RuntimeError(err.decode()[-500:])


async def duration(path):
    p = await asyncio.create_subprocess_exec("ffprobe", "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", path, stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    try:
        return float(out.decode().strip())
    except ValueError:
        return 0.0


ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k",
       "-movflags", "+faststart"]


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%")


async def trim(src, start="0", end=None, **_):
    o = _out()
    args = ["-ss", str(start), "-i", src]
    if end:
        args = ["-ss", str(start), "-to", str(end), "-i", src]
    await run(*args, *ENC, o)
    return o


async def vertical(src, **_):
    o = _out()
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    await run("-i", src, "-vf", vf, *ENC, o)
    return o


async def captions(src, lang="te", **_):
    audio = _out("mp3")
    await run("-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", audio)
    segs = await brain.transcribe(audio, lang)
    if not segs:
        return src
    filters = []
    for s in segs:
        words = s["text"]
        lines = [words[i:i + 28] for i in range(0, len(words), 28)][:2]
        txt = _esc("\n".join(lines))
        filters.append(
            f"drawtext=fontfile='{FONT}':text='{txt}':fontcolor=white:fontsize=h/22:borderw=4:bordercolor=black:"
            f"x=(w-text_w)/2:y=h*0.72:enable='between(t,{s['start']:.2f},{s['end']:.2f})'")
    o = _out()
    script = _out("txt")
    with open(script, "w", encoding="utf-8") as f:
        f.write(",\n".join(filters))
    await run("-i", src, "-filter_script:v", script, *ENC, o)
    return o


async def text(src, text="", position="bottom", start=0, end=None, **_):
    y = {"top": "h*0.08", "center": "(h-text_h)/2", "bottom": "h*0.85"}.get(position, "h*0.85")
    en = f":enable='between(t,{float(start)},{float(end)})'" if end else ""
    vf = (f"drawtext=fontfile='{FONT}':text='{_esc(text)}':fontcolor=white:fontsize=h/18:borderw=5:"
          f"bordercolor=black:x=(w-text_w)/2:y={y}{en}")
    o = _out()
    await run("-i", src, "-vf", vf, *ENC, o)
    return o


async def music(src, music_path=None, volume=0.25, **_):
    if not music_path:
        raise RuntimeError("Music file pampandi (audio/mp3) first.")
    o = _out()
    fc = (f"[1:a]volume={float(volume)}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]")
    try:
        await run("-i", src, "-stream_loop", "-1", "-i", music_path, "-filter_complex", fc,
                  "-map", "0:v", "-map", "[a]", "-shortest", *ENC, o)
    except RuntimeError:  # video has no audio track
        await run("-i", src, "-stream_loop", "-1", "-i", music_path, "-filter_complex",
                  f"[1:a]volume={float(volume)}[a]", "-map", "0:v", "-map", "[a]", "-shortest", *ENC, o)
    return o


async def speed(src, factor=1.5, **_):
    f = max(0.25, min(4.0, float(factor)))
    atempo, r = [], f
    while r > 2.0:
        atempo.append("atempo=2.0"); r /= 2.0
    while r < 0.5:
        atempo.append("atempo=0.5"); r /= 0.5
    atempo.append(f"atempo={r:.3f}")
    o = _out()
    try:
        await run("-i", src, "-filter_complex", f"[0:v]setpts=PTS/{f}[v];[0:a]{','.join(atempo)}[a]",
                  "-map", "[v]", "-map", "[a]", *ENC, o)
    except RuntimeError:
        await run("-i", src, "-vf", f"setpts=PTS/{f}", "-an", *ENC, o)
    return o


async def remove_silence(src, **_):
    p = await asyncio.create_subprocess_exec("ffmpeg", "-i", src, "-af", "silencedetect=noise=-32dB:d=0.6",
                                             "-f", "null", "-", stderr=asyncio.subprocess.PIPE)
    _, err = await p.communicate()
    log = err.decode()
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    total = await duration(src)
    keep, cur = [], 0.0
    for s, e in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if s - cur > 0.15:
            keep.append((cur, s + 0.1))
        cur = max(cur, e - 0.1)
    if total - cur > 0.15:
        keep.append((cur, total))
    if len(keep) <= 1:
        return src
    sel = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in keep)
    o = _out()
    await run("-i", src, "-vf", f"select='{sel}',setpts=N/FRAME_RATE/TB",
              "-af", f"aselect='{sel}',asetpts=N/SR/TB", *ENC, o)
    return o


async def merge(paths, **_):
    norm = []
    for pth in paths:
        n = _out()
        await run("-i", pth, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-vf",
                  "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
                  "-map", "0:v", "-map", "0:a?", "-map", "1:a", "-shortest", "-ar", "44100", "-ac", "2", *ENC, n)
        norm.append(n)
    lst = _out("txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{x}'\n" for x in norm)
    o = _out()
    await run("-f", "concat", "-safe", "0", "-i", lst, *ENC, o)
    return o


async def zoom(src, factor=1.15, **_):
    d = max(await duration(src), 1)
    f = float(factor)
    vf = f"scale=iw*{f}:ih*{f},crop=iw/{f}*(1+({f}-1)*(1-t/{d})):ih/{f}*(1+({f}-1)*(1-t/{d}))".replace(
        "crop=", "crop=")
    # simpler, reliable punch-in: scale up over time then crop centre to original size
    vf = (f"scale='iw*(1+({f}-1)*t/{d})':'ih*(1+({f}-1)*t/{d})':eval=frame,"
          f"crop='iw/(1+({f}-1)*t/{d})':'ih/(1+({f}-1)*t/{d})',scale=trunc(iw/2)*2:trunc(ih/2)*2")
    o = _out()
    try:
        await run("-i", src, "-vf", vf, *ENC, o)
    except RuntimeError:
        await run("-i", src, "-vf", f"scale=iw*{f}:ih*{f},crop=iw/{f}:ih/{f}", *ENC, o)
    return o


async def color(src, preset="vivid", **_):
    vf = {"warm": "colorbalance=rs=.08:gs=.02:bs=-.08,eq=saturation=1.15",
          "cool": "colorbalance=rs=-.06:bs=.08",
          "bw": "hue=s=0,eq=contrast=1.15",
          "vivid": "eq=saturation=1.35:contrast=1.08"}.get(preset, "eq=saturation=1.3")
    o = _out()
    await run("-i", src, "-vf", vf, *ENC, o)
    return o


async def mute(src, **_):
    o = _out()
    await run("-i", src, "-an", "-c:v", "copy", o)
    return o


async def compress(src, target_mb=15, **_):
    d = max(await duration(src), 1)
    kbps = int(target_mb * 8192 / d) - 128
    kbps = max(kbps, 300)
    o = _out()
    await run("-i", src, "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{kbps}k",
              "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k", "-vf", "scale='min(1080,iw)':-2",
              "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", o)
    return o


async def thumbnail(src, time="00:00:01", **_):
    o = _out("jpg")
    await run("-ss", str(time), "-i", src, "-frames:v", "1", "-q:v", "2", o)
    return o
