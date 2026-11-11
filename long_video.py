"""Long-form videos (5-10 min) for Divya (divya-edit-worker).

Structure follows DIVYA_LONG_VIDEOS_BOOKS_TUTORIALS.md section 1: never
render 10 minutes as one script. Instead:

1. :func:`outline` asks the LLM for an outline (hook -> chapters -> payoff).
2. :func:`render_chapters` renders each chapter as its own
   ``doc.make_video`` job (one chapter = one 60-120 s short, so a failed
   chapter can be retried without redoing the whole video).
3. :func:`assemble` concatenates the chapters with ffmpeg, inserts a
   chapter title card between chapters, loudness-normalises the final
   audio, and writes a ``chapters.txt`` with timestamps.

CLI: ``python long_video.py "<brief>" <out.mp4>`` — needs a live Groq key
(``GROQ_KEY`` env, same endpoint/models as ``runner.groq_chat``).
A full 5-minute render is NOT run as part of this module's tests; see the
``__main__`` self-test, which checks the outline parser against a stubbed
chat reply and ``assemble`` against two dummy clips.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import doc  # v2 engine: make_video(brief, chat, notify, workdir, ...) -> dict

# ---------------------------------------------------------------- outline
OUTLINE_SYSTEM = "You output strict JSON only."

OUTLINE_PROMPT = """You are a top YouTube documentary writer and director. Plan ONE faceless \
long-form video (5-10 minutes) from the owner's request below.
Structure it like doc.py's short plans, stretched over minutes: a hook in the \
first 15 seconds (strongest visual + the question, promise what they will learn), \
then chapters that each answer ONE question and end with a mini cliffhanger to \
the next, then a recap + payoff that answers the opening question (3 key points), \
then a short end screen.
Return ONLY JSON:
{"title": "<short English title>", "chapters": [{"title": "<chapter title>", "brief": "<what this chapter covers, 1-3 sentences, with the visual idea>", "minutes": <1 or 2>}, ...]}
Rules: 3-6 chapters; minutes are whole minutes, 1 or 2 each; the chapters must \
total 5-10 minutes. Keep each brief self-contained — a chapter is rendered on \
its own and must make sense without the others.
Owner request: """


def outline(brief, chat):
    """Ask the LLM (same [{"role": ...}] message format as doc.plan) for a
    long-video outline. Returns {"title": ..., "chapters": [...]} with
    3-6 chapters totalling 5-10 minutes. Raises ValueError on bad JSON or
    on an outline that breaks the chapter/total rules.
    """
    raw = chat([{"role": "system", "content": OUTLINE_SYSTEM},
                {"role": "user", "content": OUTLINE_PROMPT + (brief or "AUTO")}])
    try:
        data = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))
    except Exception:
        raise ValueError(f"outline: LLM did not return JSON: {raw[:300]!r}")
    title = str(data.get("title", "")).strip()
    chapters = data.get("chapters", [])
    if not title or not isinstance(chapters, list) or not 3 <= len(chapters) <= 6:
        raise ValueError(f"outline: need a title + 3-6 chapters, got: {data!r}"[:300])
    total = 0
    for ch in chapters:
        if not isinstance(ch, dict) or not str(ch.get("title", "")).strip() \
                or not str(ch.get("brief", "")).strip():
            raise ValueError(f"outline: chapter needs title + brief: {ch!r}"[:300])
        try:
            mins = int(round(float(ch["minutes"])))
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"outline: chapter needs whole minutes: {ch!r}"[:300])
        if mins not in (1, 2):
            raise ValueError(f"outline: chapter minutes must be 1 or 2, got {mins}")
        ch["minutes"] = mins
        total += mins
    if not 5 <= total <= 10:
        raise ValueError(f"outline: chapters total {total} min, need 5-10")
    return {"title": title, "chapters": chapters}


def chapter_brief(outline_data, idx):
    """Brief for one chapter's doc.make_video call: chapter title + brief,
    plus the exact-length line so the chapter fits its allotted minutes."""
    ch = outline_data["chapters"][idx]
    n = len(outline_data["chapters"])
    seconds = ch["minutes"] * 60
    return (
        f"Long video '{outline_data['title']}', chapter {idx + 1} of {n}: "
        f"{ch['title']}.\n{ch['brief']}\n"
        f"This chapter must stand alone and end with a hook into the next chapter.\n"
        f"FINAL VIDEO LENGTH: exactly {seconds} seconds"
    )


async def render_chapters(outline_data, chat, workdir, notify=None):
    """Render each chapter with doc.make_video (async), one chapter per
    sub-directory of workdir, sequentially — make_video already uses a
    process pool, so parallel chapters would oversubscribe the CPU.
    Returns the list of chapter mp4 paths, in order.
    """
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(len(outline_data["chapters"])):
        ch_dir = wd / f"ch{i + 1:02d}"
        res = await doc.make_video(chapter_brief(outline_data, i), chat,
                                   notify=notify, workdir=str(ch_dir))
        paths.append(res["path"])
    return paths


# ---------------------------------------------------------------- assemble
CARD_SECONDS = 1.5
CARD_BG = (8, 24, 48)      # doc.py look-A deep navy
CARD_ACCENT = (255, 210, 0)


def _probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of",
                        "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def _fmt_ts(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _load_font(size, bold=True):
    from PIL import ImageFont
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        str(Path(doc.__file__).resolve().parent / "fonts" / "Anton-Regular.ttf"),
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default(size=size) if hasattr(
        ImageFont, "load_default") else ImageFont.load_default()


def _title_card_image(number, title, out_png):
    """1.5 s chapter title card: solid navy 1080x1920, 'CHAPTER N' + title.
    Falls back to a plain black card only if PIL text rendering fails."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1080, 1920), CARD_BG)
    d = ImageDraw.Draw(img)
    try:
        small = _load_font(54)
        big = _load_font(110)
        d.rectangle([90, 880, 990, 890], fill=CARD_ACCENT)
        label = f"CHAPTER {number}"
        d.text((540, 800), label, font=small, fill=CARD_ACCENT, anchor="mm")
        lines = []
        for raw_line in str(title).split("\n"):
            lines.extend(textwrap.wrap(raw_line, width=14) or [""])
        lines = lines[:4]
        y = 960
        for line in lines:
            d.text((540, y), line, font=big, fill=(255, 255, 255), anchor="mm")
            y += 130
    except Exception:
        img = Image.new("RGB", (1080, 1920), (0, 0, 0))
    img.save(out_png)
    return out_png


def _make_card_clip(number, title, tmpdir):
    """Render one title card as a 1.5 s mp4 with silent audio, matching the
    chapters (1080x1920, 30 fps, 44100 Hz stereo) so the concat is clean."""
    png = _title_card_image(number, title, str(Path(tmpdir) / f"card{number}.png"))
    mp4 = str(Path(tmpdir) / f"card{number}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-loop", "1", "-t", str(CARD_SECONDS), "-i", png,
                    "-f", "lavfi", "-t", str(CARD_SECONDS),
                    "-i", "anullsrc=r=44100:cl=stereo",
                    "-vf", "scale=1080:1920,format=yuv420p",
                    "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", mp4], check=True)
    return mp4


def _loudnorm_params(measured):
    """Second-pass loudnorm params from a first-pass measurement dict."""
    return {
        "measured_I": measured["input_i"],
        "measured_TP": measured["input_tp"],
        "measured_LRA": measured["input_lra"],
        "measured_thresh": measured["input_thresh"],
        "offset": measured.get("target_offset", "0"),
        "linear": "true",
    }


def _measure_loudness(path):
    """First loudnorm pass (audio-only): return the measured_* JSON dict,
    or None if the measurement fails."""
    r = subprocess.run(["ffmpeg", "-i", str(path), "-vn",
                        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "")
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def assemble(parts, out_path, chapter_titles):
    """Concatenate chapter mp4s with ffmpeg, inserting a 1.5 s title card
    before every chapter after the first, loudness-normalising the final
    audio (loudnorm I=-14, TP=-1.5, LRA=11 — dual-pass, so the target is
    actually hit), and writing chapters.txt ('MM:SS Chapter title' per
    chapter start) next to the output. Returns the output path (str).
    """
    parts = [str(p) for p in parts]
    titles = [str(t) for t in chapter_titles]
    if not parts:
        raise ValueError("assemble: no chapter parts")
    if len(titles) != len(parts):
        raise ValueError("assemble: need one title per chapter part")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Chapter start times (content starts, not the card): ch1 at 0, each later
    # chapter after the previous part + its 1.5 s title card.
    durations = [_probe_duration(p) for p in parts]
    starts, t = [], 0.0
    for i, dur in enumerate(durations):
        starts.append(t)
        t += dur + (CARD_SECONDS if i < len(parts) - 1 else 0.0)

    with tempfile.TemporaryDirectory(prefix="longvid_cards_") as td:
        # Sequence: part1, card2, part2, card3, part3, ...
        segs = [parts[0]]
        for i in range(1, len(parts)):
            segs.append(_make_card_clip(i + 1, titles[i], td))
            segs.append(parts[i])
        inputs, filt = [], []
        for j, seg in enumerate(segs):
            inputs += ["-i", seg]
            filt.append(f"[{j}:v]fps=30,scale=1080:1920,format=yuv420p[v{j}];")
            filt.append(f"[{j}:a]aresample=44100,aformat=channel_layouts=stereo[a{j}];")
        filt.append("".join(f"[v{j}][a{j}]" for j in range(len(segs))))
        filt.append(f"concat=n={len(segs)}:v=1:a=1[vout][aout]")
        concat_mp4 = str(Path(td) / "concat.mp4")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs,
               "-filter_complex", "".join(filt),
               "-map", "[vout]", "-map", "[aout]",
               "-c:v", "libx264", "-preset", "medium", "-crf", "23",
               "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", concat_mp4]
        subprocess.run(cmd, check=True)
        # Dual-pass loudnorm: measure the concatenated audio, then apply the
        # measured values so the -14 LUFS target is actually hit (single-pass
        # loudnorm mis-measures on short/silent-heavy content). Video is
        # stream-copied in this pass, so it costs one fast audio pass.
        measured = _measure_loudness(concat_mp4)
        if measured is not None:
            p = _loudnorm_params(measured)
            af = ("loudnorm=I=-14:TP=-1.5:LRA=11"
                  f":measured_I={p['measured_I']}:measured_TP={p['measured_TP']}"
                  f":measured_LRA={p['measured_LRA']}"
                  f":measured_thresh={p['measured_thresh']}"
                  f":offset={p['offset']}:linear={p['linear']}")
        else:  # measurement failed: fall back to single-pass loudnorm
            af = "loudnorm=I=-14:TP=-1.5:LRA=11"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-i", concat_mp4, "-af", af,
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                        "-movflags", "+faststart", str(out_path)], check=True)

    chapters_txt = out_path.with_name("chapters.txt")
    chapters_txt.write_text("".join(
        f"{_fmt_ts(s)} {t}\n" for s, t in zip(starts, titles)), encoding="utf-8")
    return str(out_path)


# ---------------------------------------------------------------- CLI
def _groq_chat(messages):
    """Sync chat via Groq, same endpoint/models as runner.groq_chat.
    Needs GROQ_KEY (comma-separated keys OK). Raises RuntimeError if unset
    or all models fail."""
    import httpx
    keys = [k.strip() for k in os.environ.get("GROQ_KEY", "").split(",") if k.strip()]
    if not keys:
        raise RuntimeError("GROQ_KEY is not set — set it to run long_video.py")
    models = ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905",
              "openai/gpt-oss-20b"]
    last = ""
    for k in keys:
        for m in models:
            body = {"model": m, "messages": messages, "temperature": 0.8,
                    "max_tokens": 2500}
            if m.startswith("openai/gpt-oss"):
                body["reasoning_effort"] = "low"
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                           json=body, headers={"Authorization": f"Bearer {k}"},
                           timeout=90)
            if r.status_code == 200:
                out = r.json()["choices"][0]["message"]["content"] or ""
                if out.strip():
                    return out
            last = f"{m} {r.status_code}"
    raise RuntimeError("LLM failed: " + last)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print('usage: python long_video.py "<brief>" <out.mp4>', file=sys.stderr)
        return 2
    brief, out_path = argv
    out = outline(brief, _groq_chat)
    total = sum(ch["minutes"] for ch in out["chapters"])
    print(f"outline: {out['title']} — {len(out['chapters'])} chapters, "
          f"{total} min")
    for i, ch in enumerate(out["chapters"], 1):
        print(f"  ch{i}: {ch['title']} ({ch['minutes']} min)")
    with tempfile.TemporaryDirectory(prefix="longvid_") as wd:
        parts = asyncio.run(render_chapters(out, _groq_chat, wd))
        titles = [ch["title"] for ch in out["chapters"]]
        result = assemble(parts, out_path, titles)
    print(f"done: {result}")
    print(f"chapters: {Path(out_path).with_name('chapters.txt')}")
    return 0


# ---------------------------------------------------------------- self-test
def _stub_chat_factory(reply):
    def chat(messages):
        assert isinstance(messages, list) and messages[0]["role"] == "system"
        return reply
    return chat


def _self_test():
    """No live LLM, no full render: stubbed outline() + assemble() on two
    1 s dummy clips. Prints PASS lines; raises on failure."""
    stub = _stub_chat_factory(json.dumps({
        "title": "Why the sky is blue",
        "chapters": [
            {"title": "The question", "brief": "Ask why the sky is blue.", "minutes": 2},
            {"title": "The scattering", "brief": "Explain Rayleigh scattering.", "minutes": 2},
            {"title": "Sunsets", "brief": "Why sunsets turn red.", "minutes": 1},
        ]}))
    out = outline("why is the sky blue", stub)
    assert out["title"] == "Why the sky is blue" and len(out["chapters"]) == 3
    assert sum(c["minutes"] for c in out["chapters"]) == 5
    brief = chapter_brief(out, 1)
    assert "FINAL VIDEO LENGTH: exactly 120 seconds" in brief
    print("outline() stub test: PASS (3 chapters, 5 min total, "
          "exact-length line present)")
    try:
        outline("x", _stub_chat_factory("not json at all"))
    except ValueError:
        print("outline() bad-JSON test: PASS (ValueError raised)")
    else:
        raise AssertionError("outline() should raise ValueError on bad JSON")

    with tempfile.TemporaryDirectory(prefix="longvid_test_") as td:
        dummies = []
        for i, color in enumerate(("red", "blue")):
            p = str(Path(td) / f"dummy{i}.mp4")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                            "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:d=1:r=30",
                            "-f", "lavfi", "-i", "sine=frequency=440:d=1",
                            "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-ar", "44100", p], check=True)
            dummies.append(p)
        result = assemble(dummies, str(Path(td) / "final.mp4"),
                          ["First chapter", "Second chapter"])
        assert Path(result).is_file() and Path(result).stat().st_size > 0
        dur = _probe_duration(result)
        assert 3.0 < dur < 4.5, f"unexpected assembled duration {dur}"
        ct = Path(td, "chapters.txt").read_text()
        assert "00:00 First chapter" in ct and "00:02 Second chapter" in ct, ct
        print(f"assemble() dummy test: PASS (out={result}, "
              f"duration={dur:.2f}s, chapters.txt:\n{ct.strip()})")
    print("long_video self-test: ALL PASS")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        _self_test()
    else:
        raise SystemExit(main())
