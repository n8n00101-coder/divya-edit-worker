"""Long-form videos (up to 60 min) for Divya (divya-edit-worker).

Structure follows DIVYA_LONG_VIDEOS_BOOKS_TUTORIALS.md section 1: never
render a long video as one script. Instead:

1. :func:`outline` asks the LLM for an outline (hook -> chapters -> payoff)
   whose chapters total the requested length (v69: up to 60 minutes;
   without an explicit target it keeps the original 5-10 minute shape).
2. :func:`render_chapters` renders each chapter as its own
   ``doc.make_video`` job (one chapter = one 60-120 s short, so a failed
   chapter can be retried without redoing the whole video).
3. :func:`assemble` concatenates the chapters with ffmpeg, inserts a
   chapter title card between chapters, loudness-normalises the final
   audio, and writes a ``chapters.txt`` with timestamps.

:func:`make_long_video` is the runner entry point (v69): outline ->
chapters -> assemble, honouring an optional wall-clock deadline — when
the budget runs out (or a chapter fails midway) it assembles whatever
chapters finished and flags the result partial instead of failing the
whole job.

CLI: ``python long_video.py "<brief>" <out.mp4> [minutes]`` — needs a live
Groq key (``GROQ_KEY`` env, same endpoint/models as ``runner.groq_chat``).
A full render is NOT run as part of this module's tests; see the
``__main__`` self-test, which checks the outline parser against a stubbed
chat reply and ``assemble`` against two dummy clips.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
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


def _outline_prompt(target_minutes):
    """The outline prompt. target_minutes=None keeps the original 5-10 min
    shape; an explicit target (v69, up to 60) sizes the chapter count to
    it and demands terse chapter briefs so a 60-chapter outline still fits
    one LLM reply."""
    if not target_minutes:
        return OUTLINE_PROMPT
    target = int(target_minutes)
    lo = 2 if target <= 4 else 3
    hi = target  # every chapter at 1 minute
    return (
        "You are a top YouTube documentary writer and director. Plan ONE "
        f"faceless long-form video of exactly {target} minutes from the "
        "owner's request below.\n"
        "Structure: a hook in the first 15 seconds (strongest visual + the "
        "question, promise what they will learn), then chapters that each "
        "answer ONE question and end with a mini cliffhanger to the next, "
        "then a recap + payoff that answers the opening question (3 key "
        "points), then a short end screen.\n"
        "Return ONLY JSON:\n"
        '{"title": "<short English title>", "chapters": [{"title": '
        '"<chapter title>", "brief": "<what this chapter covers, with the '
        'visual idea>", "minutes": <1 or 2>}, ...]}\n'
        f"Rules: {lo}-{hi} chapters; minutes are whole minutes, 1 or 2 "
        f"each; the chapters must total EXACTLY {target} minutes. Keep "
        "every chapter brief under 15 words — the outline is long. Keep "
        "each brief self-contained — a chapter is rendered on its own and "
        "must make sense without the others.\n"
        "Owner request: "
    )


def outline(brief, chat, target_minutes=None):
    """Ask the LLM (same [{"role": ...}] message format as doc.plan) for a
    long-video outline. Returns {"title": ..., "chapters": [...]}.
    Without target_minutes: 3-6 chapters totalling 5-10 minutes (the
    original contract). With target_minutes (2-60): enough 1-2 minute
    chapters to total EXACTLY the target. Raises ValueError on bad JSON
    or on an outline that breaks the chapter/total rules.
    """
    raw = chat([{"role": "system", "content": OUTLINE_SYSTEM},
                {"role": "user", "content": _outline_prompt(target_minutes)
                 + (brief or "AUTO")}])
    try:
        data = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))
    except Exception:
        raise ValueError(f"outline: LLM did not return JSON: {raw[:300]!r}")
    title = str(data.get("title", "")).strip()
    chapters = data.get("chapters", [])
    if target_minutes:
        target = int(target_minutes)
        lo = 2 if target <= 4 else 3
        hi = target
    else:
        target, lo, hi = None, 3, 6
    if not title or not isinstance(chapters, list) \
            or not lo <= len(chapters) <= hi:
        raise ValueError(
            f"outline: need a title + {lo}-{hi} chapters, got: {data!r}"[:300])
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
    if target is not None:
        if total != target:
            raise ValueError(
                f"outline: chapters total {total} min, need exactly {target}")
    elif not 5 <= total <= 10:
        raise ValueError(f"outline: chapters total {total} min, need 5-10")
    return {"title": title, "chapters": chapters}


# v78: per-chapter narration budget. doc.py's plan prompt sizes voice-over
# at "English ~2.5 words/s" (150 words/min); at ~5.7 chars/word that is
# ~850 chars/min of speech. The outline's chapter minutes were never
# translated into a script size before, so chapters under-filled badly:
# job 7aee5d2a's 7 chapters "totalled" 14 planned minutes on the outline
# but the assembled video was 7.7 min — nothing checked the words
# against the minutes. Budgets turn the minutes into a words/chars
# target for the planner, and render_chapters verifies each chapter's
# rendered duration against them (one top-up per short chapter).
CHARS_PER_MIN = 850
WORDS_PER_MIN = 150  # doc.py plan rate: English ~2.5 words/s
TOPUP_MIN_FRACTION = 0.8  # a chapter under 80% of budget is topped up once


def chapter_budget(ch):
    """The narration budget for one outline chapter: its allotted
    seconds plus the words/chars of voice-over needed to fill them."""
    mins = int(ch["minutes"])
    return {"seconds": mins * 60, "words": mins * WORDS_PER_MIN,
            "chars": mins * CHARS_PER_MIN}


def chapter_brief(outline_data, idx):
    """Brief for one chapter's doc.make_video call: chapter title + brief,
    plus the exact-length line so the chapter fits its allotted minutes
    and the v78 narration budget (words/chars) that actually fills them."""
    ch = outline_data["chapters"][idx]
    n = len(outline_data["chapters"])
    seconds = ch["minutes"] * 60
    b = chapter_budget(ch)
    return (
        f"Long video '{outline_data['title']}', chapter {idx + 1} of {n}: "
        f"{ch['title']}.\n{ch['brief']}\n"
        f"This chapter must stand alone and end with a hook into the next chapter.\n"
        f"FINAL VIDEO LENGTH: exactly {seconds} seconds\n"
        f"NARRATION BUDGET: the voice-over across all scenes must total "
        f"about {b['words']} words (~{b['chars']} characters). At normal "
        f"English speech (~150 words/min) that is what actually fills "
        f"{ch['minutes']} minute(s) — a shorter script renders a "
        f"shorter chapter."
    )


def _fold_chapter_amendments(provider, brief, chapter_no):
    """v72: before a chapter renders, fold the amendments that can
    still land in it. Content points + style notes go INTO the chapter
    brief — the chapter's own plan weaves them in (a real script-level
    fold for this chapter onward) — and are marked applied at this
    chapter. Pure toggles (B-roll / SFX / music / transitions /
    captions) are left pending: the chapter's doc.make_video consumes
    them at its own checkpoints."""
    try:
        items = provider.pending()
    except Exception as e:
        print("amendments poll failed:", str(e)[:120])
        return brief
    extra = []
    for it in items or []:
        fx = doc.classify_amendment(it.get("text", ""))
        if "content" in fx or "style_note" in fx:
            extra.append(str(it.get("text", ""))[:200])
            try:
                provider.mark([it["id"]], f"chapter {chapter_no}")
            except Exception:
                pass
    if extra:
        brief += ("\nViewer-requested additions — include them from "
                  "THIS chapter: " + " | ".join(extra))
    return brief


def _join_clips(paths, out_path):
    """Concatenate same-engine mp4s into one file (the v78 top-up join).
    Re-encodes through the concat demuxer so the join is robust to
    timestamp/container quirks between the two renders."""
    out_path = str(out_path)
    lst = out_path + ".txt"
    with open(lst, "w") as f:
        for p in paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat",
                    "-safe", "0", "-i", lst, "-c:v", "libx264", "-preset",
                    "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "128k",
                    out_path], check=True)
    return out_path


async def render_chapters(outline_data, chat, workdir, notify=None,
                          deadline=None, results_out=None, ref_voice=None,
                          amendments=None):
    """Render each chapter with doc.make_video (async), one chapter per
    sub-directory of workdir, sequentially — make_video already uses a
    process pool, so parallel chapters would oversubscribe the CPU.
    Returns the list of chapter mp4 paths, in order.

    v69: `deadline` is a time.monotonic() wall — once it passes, no NEW
    chapter is started and the chapters finished so far are returned
    (the caller assembles them as a partial). A chapter that raises
    midway likewise stops the loop when at least one chapter is done;
    with zero chapters done the error propagates. Chapter result dicts
    are appended to `results_out` when given.

    v72: with an amendments provider, each chapter first folds the
    content amendments that arrived since the last chapter into its
    brief (see _fold_chapter_amendments), and the provider itself is
    forwarded to doc.make_video for its per-chapter checkpoints.
    """
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(len(outline_data["chapters"])):
        if deadline is not None and paths and time.monotonic() > deadline:
            print(f"render_chapters: time budget reached — stopping "
                  f"after {len(paths)}/{len(outline_data['chapters'])} chapters")
            break
        ch_dir = wd / f"ch{i + 1:02d}"
        # v75: the chapter dir must EXIST before make_video writes into
        # it. Nothing created it — codegen's plan.json write and the
        # vo0.mp3 write both died with ENOENT (run 43373013930).
        ch_dir.mkdir(parents=True, exist_ok=True)
        ch_brief = chapter_brief(outline_data, i)
        if amendments is not None:
            ch_brief = _fold_chapter_amendments(amendments, ch_brief, i + 1)
        # v75: ONE retry per chapter — a transient sub-step failure
        # (LLM blip, TTS error) must not kill the chapter outright.
        # After the retry the old semantics hold: with finished
        # chapters we assemble them as a partial; with none, the error
        # propagates and the runner reports the job failed.
        res, last_err = None, None
        for _attempt in range(2):
            try:
                # ref_voice / amendments are passed only when set, so
                # engine-shaped callers/stubs without those parameters
                # stay compatible.
                res = await doc.make_video(ch_brief, chat,
                                           notify=notify, workdir=str(ch_dir),
                                           **({"ref_voice": ref_voice}
                                              if ref_voice is not None else {}),
                                           **({"amendments": amendments}
                                              if amendments is not None else {}))
                break
            except Exception as e:
                last_err = e
                if _attempt == 0:
                    print(f"render_chapters: chapter {i + 1} attempt 1 "
                          f"failed ({str(e)[:150]}) — retrying once")
                    await asyncio.sleep(5)
        if res is None:
            if not paths:
                raise last_err
            print(f"render_chapters: chapter {i + 1} failed "
                  f"({str(last_err)[:150]}) — assembling the {len(paths)} "
                  f"finished chapters")
            break
        # v78: verify the chapter against its narration budget. A
        # chapter that rendered materially short (<80% of its allotted
        # seconds) is topped up ONCE — an extension render of NEW
        # scenes for the missing seconds, joined onto the chapter —
        # instead of silently assembling a short video (job 7aee5d2a:
        # 14 min asked, 7.7 min delivered, every chapter "completed").
        # A passed deadline skips the top-up: partial-budget semantics
        # stay exactly as they were.
        try:
            budget = chapter_budget(outline_data["chapters"][i])
            dur = res.get("duration")
            if not (isinstance(dur, (int, float)) and dur > 0):
                dur = _probe_duration(res["path"])
            if dur < TOPUP_MIN_FRACTION * budget["seconds"] and not (
                    deadline is not None and time.monotonic() > deadline):
                missing_s = max(10, int(round(budget["seconds"] - dur)))
                missing_w = max(20, int(round(missing_s / 60 * WORDS_PER_MIN)))
                missing_c = max(100, int(round(missing_s / 60 * CHARS_PER_MIN)))
                ch = outline_data["chapters"][i]
                ext_brief = (
                    f"Long video '{outline_data['title']}', chapter "
                    f"{i + 1} of {len(outline_data['chapters'])} "
                    f"EXTENSION: {ch['title']}.\n{ch['brief']}\n"
                    f"The main part of this chapter rendered only "
                    f"{int(dur)}s of its {budget['seconds']}s. Continue "
                    f"the SAME chapter with NEW scenes — do not repeat "
                    f"the earlier content.\n"
                    f"FINAL VIDEO LENGTH: exactly {missing_s} seconds\n"
                    f"NARRATION BUDGET: the voice-over across all scenes "
                    f"must total about {missing_w} words "
                    f"(~{missing_c} characters)."
                )
                ext_dir = ch_dir / "ext"
                ext_dir.mkdir(parents=True, exist_ok=True)
                ext = await doc.make_video(
                    ext_brief, chat, notify=notify, workdir=str(ext_dir),
                    **({"ref_voice": ref_voice}
                       if ref_voice is not None else {}),
                    **({"amendments": amendments}
                       if amendments is not None else {}))
                joined = _join_clips([res["path"], ext["path"]],
                                     str(ch_dir / f"ch{i + 1:02d}_full.mp4"))
                try:
                    new_dur = _probe_duration(joined)
                except Exception:
                    new_dur = dur + float(ext.get("duration") or 0)
                res = {**res, "path": joined, "duration": new_dur,
                       "topped_up": True, "topup_seconds": missing_s,
                       "broll": (res.get("broll") or [])
                                + (ext.get("broll") or [])}
                print(f"render_chapters: chapter {i + 1} topped up "
                      f"({int(dur)}s -> {int(new_dur)}s of "
                      f"{budget['seconds']}s budget)")
        except Exception as e:
            print(f"render_chapters: chapter {i + 1} top-up failed "
                  f"({str(e)[:150]}) — keeping the rendered chapter")
        paths.append(res["path"])
        if results_out is not None:
            results_out.append(res)
        # The chapter mp4 is final — its extracted B-roll frames (tens of
        # MB per chapter) are dead weight on the runner disk from here.
        shutil.rmtree(ch_dir / "broll_frames", ignore_errors=True)
    return paths


async def make_long_video(brief, chat, workdir, target_minutes,
                          notify=None, deadline=None, ref_voice=None,
                          amendments=None):
    """Runner entry point (v69): outline -> chaptered render -> assemble
    for a requested length of target_minutes (2-60). Returns a result
    dict shaped like doc.make_video's (path/title/duration/lang/caption/
    topic/plan) plus: broll (aggregated chapter B-roll sources), summary,
    partial, chapters_done, chapters_total, long=True. A partial result
    (deadline hit or a midway chapter failure) still returns the longest
    completed assembly — it never silently shortens a finished plan:
    `partial` says exactly how many chapters are missing.
    """
    out, last_err = None, None
    for attempt in range(2):
        try:
            b = brief if attempt == 0 else (
                (brief or "") +
                f"\n(The outline MUST total exactly {target_minutes} "
                f"minutes — count the chapter minutes.)")
            out = outline(b, chat, target_minutes)
            break
        except ValueError as e:
            last_err = e
    if out is None:
        raise last_err
    total_ch = len(out["chapters"])
    if notify:
        await notify(f"Long video: {out['title']} — {total_ch} chapters, "
                     f"~{target_minutes} min. Chapters render chestunna.")
    results = []
    paths = await render_chapters(out, chat, workdir, notify=notify,
                                  deadline=deadline, results_out=results,
                                  ref_voice=ref_voice,
                                  amendments=amendments)
    if not paths:
        raise RuntimeError("long video: no chapters rendered")
    titles = [ch["title"] for ch in out["chapters"]][:len(paths)]
    final = assemble(paths, str(Path(workdir) / "long_final.mp4"), titles)
    duration = _probe_duration(final)
    broll_sources = []
    for r in results:
        broll_sources += (r.get("broll") or [])
    first = results[0] if results else {}
    partial = len(paths) < total_ch
    summary = (f"{out['title']} — long video, {len(paths)}/{total_ch} "
               f"chapters, {duration / 60:.1f} min")
    if partial:
        summary += (" (PARTIAL — job time budget reached; longest "
                    "completed assembly delivered)")
    # v78: honest actual-vs-target reporting. Topped-up chapters are
    # named, and a complete-but-short assembly says so against the
    # target instead of letting the minutes line pass silently.
    topped = sum(1 for r in results if r.get("topped_up"))
    if topped:
        summary += f"; {topped} chapter(s) topped up to reach their length"
    if not partial and duration < target_minutes * 60 - 30:
        summary += (f" (target {target_minutes} min — chapters "
                    f"under-filled)")
    if broll_sources:
        summary += (f"; B-roll: {len(broll_sources)} stock clips "
                    f"({', '.join(sorted({s.get('provider', '') for s in broll_sources}))})")
    # v71: honest voice label, aggregated from the chapter results.
    voice_note = next((r.get("voice_note") for r in results
                       if r.get("voice_note")), None)
    if voice_note:
        summary += f"; Voice: {voice_note}"
    # v72: mid-flight amendments applied inside the chapters (the
    # runner re-reads the job record for the authoritative delivery
    # list — this aggregation is for the summary line only).
    amend_applied = []
    for r in results:
        amend_applied += (r.get("amendments_applied") or [])
    if amend_applied:
        summary += (f"; Changes add chesina: {len(amend_applied)} "
                    f"mid-flight amendment(s) ee video lone apply ayyayi")
    return {"path": final, "title": out["title"], "duration": duration,
            "lang": first.get("lang", "te"),
            "caption": first.get("caption", ""),
            "topic": first.get("topic", brief),
            "plan": first.get("plan", {}),
            "broll": broll_sources, "summary": summary,
            "voice_note": voice_note,
            "amendments_applied": amend_applied,
            "partial": partial, "chapters_done": len(paths),
            "chapters_total": total_ch, "long": True}


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
    # v75: same transient-retry contract as runner.groq_chat — a 429 /
    # 5xx / network blip retries the sweep with 5s/15s/45s backoff
    # instead of killing the call (and with it, the whole long video).
    last = ""
    for attempt in range(4):
        transient = False
        for k in keys:
            for m in models:
                body = {"model": m, "messages": messages, "temperature": 0.8,
                        "max_tokens": 2500}
                if m.startswith("openai/gpt-oss"):
                    body["reasoning_effort"] = "low"
                try:
                    r = httpx.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        json=body, headers={"Authorization": f"Bearer {k}"},
                        timeout=90)
                except httpx.HTTPError as e:
                    last = f"{m} network {type(e).__name__}"
                    transient = True
                    continue
                if r.status_code == 200:
                    out = r.json()["choices"][0]["message"]["content"] or ""
                    if out.strip():
                        return out
                    last = f"{m} empty"
                    transient = True
                    continue
                last = f"{m} {r.status_code}"
                if r.status_code == 429 or r.status_code >= 500:
                    transient = True
        if not transient or attempt == 3:
            break
        time.sleep((5, 15, 45)[attempt])
    raise RuntimeError("LLM failed: " + last)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) not in (2, 3):
        print('usage: python long_video.py "<brief>" <out.mp4> [minutes]',
              file=sys.stderr)
        return 2
    brief, out_path = argv[0], argv[1]
    if len(argv) == 3:  # v69: explicit target length -> the runner path
        target = int(argv[2])
        wd = str(Path(out_path).resolve().parent / "longvid_work")
        res = asyncio.run(make_long_video(brief, _groq_chat, wd, target))
        if os.path.abspath(res["path"]) != os.path.abspath(out_path):
            shutil.copyfile(res["path"], out_path)
        print(f"done: {out_path} — {res['summary']}")
        print(f"chapters: {Path(res['path']).with_name('chapters.txt')}")
        return 0
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

    # v69: explicit targets — a 10-min outline (5 x 2 min) and a full
    # 60-min outline (30 x 2 min) must validate; a wrong total must not.
    def _mk_stub(n_ch, mins):
        return _stub_chat_factory(json.dumps({
            "title": "Target test",
            "chapters": [{"title": f"Chapter {i + 1}",
                          "brief": f"Covers part {i + 1}.",
                          "minutes": mins} for i in range(n_ch)]}))
    out10 = outline("ten minutes please", _mk_stub(5, 2), target_minutes=10)
    assert sum(c["minutes"] for c in out10["chapters"]) == 10
    print("outline(target=10) stub test: PASS (5 chapters, 10 min total)")
    out60 = outline("one hour please", _mk_stub(30, 2), target_minutes=60)
    assert len(out60["chapters"]) == 30
    assert sum(c["minutes"] for c in out60["chapters"]) == 60
    print("outline(target=60) stub test: PASS (30 chapters, 60 min total)")
    try:
        outline("x", _mk_stub(4, 2), target_minutes=10)  # totals 8, need 10
    except ValueError:
        print("outline(target=10) wrong-total test: PASS (ValueError raised)")
    else:
        raise AssertionError("outline() should reject a wrong total")

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
