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


def _brain_status_summary_lv():
    """PROOF-FIX 1: the brain ledger for the long result dict."""
    try:
        import brain_status as _bs
        return _bs.summary()
    except Exception:
        return {}


def _outline_prompt(target_minutes, chapters_wanted=None):
    """The outline prompt. target_minutes=None keeps the original 5-10 min
    shape; an explicit target (v69, up to 60) sizes the chapter count to
    it and demands terse chapter briefs so a 60-chapter outline still fits
    one LLM reply. v79 (R-P5): a chapter count stated in the prompt is
    a renderer parameter — the outline must produce exactly that many
    chapters."""
    if not target_minutes:
        return OUTLINE_PROMPT
    target = int(target_minutes)
    if chapters_wanted:
        lo = hi = int(chapters_wanted)
    else:
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


def outline(brief, chat, target_minutes=None, chapters_wanted=None,
            topic_history=None, exclusions=None):
    """Ask the LLM (same [{"role": ...}] message format as doc.plan) for a
    long-video outline. Returns {"title": ..., "chapters": [...]}.
    Without target_minutes: 3-6 chapters totalling 5-10 minutes (the
    original contract). With target_minutes (2-60): enough 1-2 minute
    chapters to total EXACTLY the target. Raises ValueError on bad JSON
    or on an outline that breaks the chapter/total rules.

    ROUND 4 (Fix 1a — TOPIC LOCK): `exclusions` (subjects the owner
    explicitly ruled out, from their own words) bind EVERY pick;
    `topic_history` (subjects already delivered as films) binds
    AUTO picks. Both ride INTO the prompt — the third film's
    exclusion died when the brief was rewritten to "topic AUTO",
    so the constraint now travels with the call, not the brief —
    and both are enforced AFTER the pick: a colliding title is
    rejected and re-picked (max 3 attempts), after which the
    outline raises with the conflict stated plainly instead of
    silently repeating a subject.
    """
    import topic_lock as _tl
    is_auto = not str(brief or "").strip() or bool(
        re.search(r"\bAUTO\b", str(brief or ""), re.I))
    lock_note = ""
    if exclusions:
        lock_note += (
            "\nTOPIC LOCK — the owner explicitly excluded these "
            "subjects: " + "; ".join(str(e) for e in exclusions)
            + ". Never pick an excluded subject.")
    if is_auto and topic_history:
        lock_note += (
            "\nTOPIC LOCK — these subjects were already delivered "
            "as films; pick a DIFFERENT subject, not a re-titled "
            "repeat: "
            + "; ".join(str(h) for h in topic_history) + ".")
    last_collision = None
    collision_kind = ""
    for _attempt in range(3):
        prompt = _outline_prompt(target_minutes, chapters_wanted) \
            + (brief or "AUTO") + lock_note
        if last_collision:
            prompt += (
                f"\nYour previous pick, '{last_collision}', "
                "violates the TOPIC LOCK above. Pick a genuinely "
                "different subject.")
        raw = chat([{"role": "system", "content": OUTLINE_SYSTEM},
                    {"role": "user", "content": prompt}])
        try:
            data = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))
        except Exception:
            raise ValueError(f"outline: LLM did not return JSON: {raw[:300]!r}")
        out = _validate_outline(data, target_minutes, chapters_wanted)
        title = out["title"]
        ex_hit = _tl.exclusion_hit(title, exclusions or [])
        hist_hit = _tl.history_hit(title, topic_history or []) \
            if is_auto else None
        if not ex_hit and not hist_hit:
            return out
        last_collision = title
        collision_kind = (f"excluded subject '{ex_hit}'" if ex_hit
                          else f"repeat of delivered film '{hist_hit}'")
        print(f"outline: TOPIC LOCK rejected pick '{title}' "
              f"({collision_kind}) — re-picking "
              f"({_attempt + 1}/3)")
    raise ValueError(
        f"outline: TOPIC LOCK — every pick collided with the "
        f"order's constraints (last pick '{last_collision}': "
        f"{collision_kind}); refusing to silently repeat a subject")


def _validate_outline(data, target_minutes=None, chapters_wanted=None):
    """The outline's structural rules (title + chapter count/total),
    unchanged from the original outline(): raises ValueError on any
    break, returns {"title": ..., "chapters": [...]}."""
    title = str(data.get("title", "")).strip()
    chapters = data.get("chapters", [])
    if target_minutes:
        target = int(target_minutes)
        if chapters_wanted:
            lo = hi = int(chapters_wanted)
        else:
            lo = 2 if target <= 4 else 3
            hi = target
    else:
        target, lo, hi = None, 3, 6
    if not title or not isinstance(chapters, list) \
            or not lo <= len(chapters) <= hi:
        raise ValueError(
            f"outline: need a title + {lo}-{hi} chapters, got: {data!r}"[:300])
    total = 0
    max_mins = 2
    if chapters_wanted and target_minutes:
        import math as _math
        max_mins = max(2, _math.ceil(int(target_minutes) / int(chapters_wanted)) + 1)
    for ch in chapters:
        if not isinstance(ch, dict) or not str(ch.get("title", "")).strip() \
                or not str(ch.get("brief", "")).strip():
            raise ValueError(f"outline: chapter needs title + brief: {ch!r}"[:300])
        try:
            mins = int(round(float(ch["minutes"])))
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"outline: chapter needs whole minutes: {ch!r}"[:300])
        if not 1 <= mins <= max_mins:
            raise ValueError(f"outline: chapter minutes must be 1-{max_mins}, got {mins}")
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


def chapter_brief(outline_data, idx, spec=None):
    """Brief for one chapter's doc.make_video call: chapter title + brief,
    plus the exact-length line so the chapter fits its allotted minutes
    and the v78 narration budget (words/chars) that actually fills them.
    v79 (FIX 3): the prompt spec rides in EVERY chapter brief too."""
    ch = outline_data["chapters"][idx]
    n = len(outline_data["chapters"])
    seconds = ch["minutes"] * 60
    b = chapter_budget(ch)
    out = (
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
    if spec:
        import doc as _doc
        out += "\n" + _doc._spec_block(spec)
    return out


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


def _fix_guidance100(failed):
    """v100 (Gate 3): per-class repair instructions for a chapter
    fix round, keyed on the rules that actually failed — a footage
    failure gets footage instructions, a fact failure gets fact
    instructions, not one generic 'fix these' line."""
    rules = {c.get("rule") for c in failed or []}
    g = []
    if rules & {"R10", "FG-SHARE", "PART2-RATIO"}:
        g.append("FOOTAGE: every beat needs stock-searchable "
                 "footage queries — generic visible subjects "
                 "(people, places, objects, actions); NEVER film "
                 "titles, film stills or people's names")
    if rules & {"VHIST", "R1", "A5", "PART3-CHANGE", "PART3-TYPES",
                "PART3-TRANS", "PART4-CHECK"}:
        g.append("VARIETY: no single visual type over a quarter "
                 "of the chapter's beats — picture each line with "
                 "a different composed visual")
    if rules & {"FG-FACT", "FG-TEASE"}:
        g.append("FACTS: cut or properly source every unsourced "
                 "statistic/claim, or hedge it; never invent "
                 "sources, movements or events; never tease a "
                 "chapter that does not exist")
    if "DEPICTION" in rules:
        g.append("DEPICTION: stop showing the thing each line "
                 "names — re-voice the beats as EVIDENCE (a "
                 "sourced document or data visual), CONTEXT "
                 "(setting, ambience, structure) or METAPHOR (a "
                 "symbolic visual); literal illustration must "
                 "fall to ~20% of the chapter's beats")
    if "R11" in rules:
        g.append("SOUND: no unexplained silence over 0.8 s; "
                 "loudness -14 LUFS, true peak <= -1 dB")
    if "FIDELITY" in rules:
        g.append("FIDELITY: every visual must picture the words "
                 "of ITS OWN line")
    if "DIR-FALLBACK" in rules:
        g.append("DIRECTOR: the previous pass was directed by "
                 "the deterministic FALLBACK because the brain "
                 "director stage could not run — this pass must "
                 "be directed in full (transitions, dynamics, "
                 "visual rhythm); a flat repeat of the fallback "
                 "plan does not clear this failure")
    if "MOTION-STATIC" in rules:
        g.append("MOTION: rendered beats must MOVE — animated "
                 "graphics over the footage, push-ins on stills "
                 "and static clips, speed accents on the number "
                 "and hit beats; a static title card is not a "
                 "beat")
    if "PRESENTER-CARD" in rules:
        g.append("PRESENTER: this is a faceless documentary — "
                 "no avatar/presenter placeholder card on any "
                 "beat; picture the line with footage, evidence "
                 "or a composed graphic instead")
    return g


def _director_check(stages, chapter_no):
    """ROUND 5 (Fix 1): the compliance form of a director
    fallback — boring-critical, so it rides the fix loop like
    any other boring-critical FAIL."""
    return {"rule": "DIR-FALLBACK", "status": "FAIL", "scene": None,
            "detail": f"chapter {chapter_no}: director stage(s) "
                      f"{', '.join(stages)} fell back (channel) — "
                      f"the chapter was directed by the "
                      f"deterministic fallback, not the brain "
                      f"director"}


def _round5_checks(res, presenter_allowed=False):
    """ROUND 5 (Fixes 2 + 6): the chapter's MOTION-STATIC and
    PRESENTER-CARD checks, computed from the plan that actually
    rendered (the HF report's pixel motion audit + the scene
    records' presenter audit). Returns (checks, info)."""
    checks = []
    plan = (res or {}).get("plan") or {}
    scenes = plan.get("scenes") or []
    flags = []
    try:
        import doc as _doc5
        import motion_audit as _ma5
        flags = _ma5.presenter_flags(
            scenes, presenter_allowed=presenter_allowed,
            mapped=_doc5._VIS_NAME_MAP)
    except Exception:
        flags = []
    if flags:
        checks.append({
            "rule": "PRESENTER-CARD", "status": "FAIL",
            "scene": flags[0]["scene"],
            "detail": "presenter/avatar placeholder card "
                      "(polaroid with no real photo) on scene(s) "
                      + ", ".join(str(f["scene"]) for f in flags)
                      + " of a faceless long-form documentary"})
    audit = ((plan.get("hyperframes_primary") or {})
             .get("motion_audit") or {})
    static_beats = audit.get("static_beats") or []
    if static_beats:
        checks.append({
            "rule": "MOTION-STATIC", "status": "FAIL",
            "scene": static_beats[0],
            "detail": f"{len(static_beats)} rendered beat(s) do "
                      f"not move (pixel motion audit): scene(s) "
                      + ", ".join(str(s) for s in static_beats)})
    return checks, {"presenter_flags": flags, "motion_audit": audit}


async def render_chapters(outline_data, chat, workdir, notify=None,
                          deadline=None, results_out=None, ref_voice=None,
                          amendments=None, spec=None, cfg=None, pool=None):
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
    _n_ch = len(outline_data["chapters"])
    for i in range(_n_ch):
        if deadline is not None and paths and time.monotonic() > deadline:
            print(f"render_chapters: time budget reached — stopping "
                  f"after {len(paths)}/{len(outline_data['chapters'])} chapters")
            break
        # ROUND 4 (Fix 4 — CHAPTER THROUGHPUT CAP): each chapter
        # gets an equal share of the REMAINING job budget
        # (remaining / chapters left, recomputed per chapter).
        # The third film spent its whole 3000 s budget on chapter
        # 1's render + top-up + correction rounds; chapters 2-5
        # were never attempted. Optional passes (top-up, fix
        # rounds) stop at the chapter's own deadline — the main
        # render always runs — so every chapter is attempted and
        # no chapter can eat the film.
        _ch_t0 = time.monotonic()
        _ch_deadline = None
        if deadline is not None:
            _ch_deadline = _ch_t0 + max(0.0, deadline - _ch_t0) \
                / max(1, _n_ch - i)
        _long_ctx = bool(cfg and cfg.get("kind") == "long")
        _gate_passes = []
        ch_dir = wd / f"ch{i + 1:02d}"
        # v75: the chapter dir must EXIST before make_video writes into
        # it. Nothing created it — codegen's plan.json write and the
        # vo0.mp3 write both died with ENOENT (run 43373013930).
        ch_dir.mkdir(parents=True, exist_ok=True)
        ch_brief = chapter_brief(outline_data, i, spec=spec)
        # v84 (Stage 4 / P2): every chapter brief now carries the
        # WHOLE-documentary structure — its arc role, the full chapter
        # list, and the rule that only the final chapter may close
        # the story. This is what stops chapters rendering as
        # independent shorts with their own hooks and endings.
        try:
            import doc_structure as _ds
            ch_brief += _ds.arc_context_block(outline_data, i)
        except Exception as _e:
            print(f"render_chapters: arc context failed ({str(_e)[:100]})")
        if amendments is not None:
            ch_brief = _fold_chapter_amendments(amendments, ch_brief, i + 1)
        # v79: footage-pool mark at this chapter's start — a compliance
        # retry that REPLACES the chapter also replaces its footage.json
        # segment, so the delivered record lists the final cut only.
        _pool_mark0 = len(pool.assignments) if pool is not None else 0
        # v79 (R8): only the FINAL chapter may carry the closing CTA —
        # every earlier chapter ending in NEXT/STAY TUNED/CTA was one
        # of the compromise video's structural mistakes.
        ch_cfg = None
        if cfg is not None:
            ch_cfg = dict(cfg)
            ch_cfg["allow_cta"] = (i == len(outline_data["chapters"]) - 1)
        # ROUND 5 (Fix 1): the brain-ledger window for THIS
        # chapter — the director-fallback verdict is per chapter,
        # not per job (film 3's job-level ledger hid that BOTH
        # passes of its only chapter were fallback-directed).
        try:
            import brain_status as _bs5m
            _bs5_mark = _bs5m.mark()
        except Exception:
            _bs5_mark = None
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
                                              if amendments is not None else {}),
                                           **({"spec": spec, "cfg": ch_cfg,
                                               "footage_pool": pool}
                                              if spec is not None or pool is not None
                                              or cfg is not None else {}))
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
        # ROUND 4 (Fix 2): the main pass's fact-gate event is
        # recorded on the chapter — every pass that reaches the
        # film leaves an event, and a missing one is labelled in
        # the record, never silent. (The fail-closed choke point
        # itself lives in doc.plan / doc.make_video: through the
        # real engine an ungated documentary pass cannot render.)
        if _long_ctx:
            _ev = (res.get("plan") or {}).get("fact_gate")
            _gate_passes.append(
                {"pass": "main", **_ev} if _ev is not None
                else {"pass": "main", "missing": True})
            if _ev is None:
                print(f"render_chapters: chapter {i + 1} main pass "
                      f"has NO fact-gate event — labelled in the "
                      f"chapter record")
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
            # ROUND 4 (Fix 4): the top-up is an optional pass — it
            # runs only inside the chapter's own budget share. A
            # short chapter whose share is spent ships at honest
            # length, labelled, and the remaining chapters keep
            # their shares.
            if dur < TOPUP_MIN_FRACTION * budget["seconds"] and \
                    _ch_deadline is not None and \
                    time.monotonic() > _ch_deadline:
                print(f"render_chapters: chapter {i + 1} is short "
                      f"({int(dur)}s of {budget['seconds']}s) but "
                      f"its budget share is spent — top-up skipped, "
                      f"chapter ships at honest length")
            if dur < TOPUP_MIN_FRACTION * budget["seconds"] and not (
                    _ch_deadline is not None
                    and time.monotonic() > _ch_deadline):
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
                    f"the earlier content. COMPRESSION PASS rule "
                    f"(taste pack): this top-up may only add NEW "
                    f"evidence, a NEW angle, or a NEW consequence — "
                    f"a claim, fact or example that appears nowhere "
                    f"earlier in the chapter. Restating the chapter's "
                    f"argument in other words is rejected by the "
                    f"length-honesty gate and the chapter ships at "
                    f"honest length instead.\n"
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
                       if amendments is not None else {}),
                    **({"spec": spec, "cfg": ch_cfg, "footage_pool": pool}
                       if spec is not None or cfg is not None else {}))
                # ROUND 4 (Fix 2): the top-up pass's fact-gate
                # event is recorded like every other pass — and a
                # top-up with NO gate event never joins the
                # chapter (fail closed at the join; see the
                # rejection chain below). Film 3's unsourced
                # "1,200 deaths" arrived through exactly this
                # pass, ungated and unlogged.
                _ext_gate = (ext.get("plan") or {}).get("fact_gate") \
                    if _long_ctx else None
                if _long_ctx:
                    _gate_passes.append(
                        {"pass": "topup", **_ext_gate}
                        if _ext_gate is not None else
                        {"pass": "topup", "missing": True})
                _ext_vo = [str(s.get("vo") or "") for s in
                           ((ext.get("plan") or {}).get("scenes")
                            or [])]
                # ROUND 4 (Fix 1c — TOPIC COHERENCE): the chapter's
                # subject was locked at plan time (film title +
                # chapter title + brief). A top-up whose scenes
                # barely touch that subject is not an extension —
                # it is a different film (film 3: seatbelts inside
                # an EV chapter). Novelty is checked below; this
                # checks the top-up is still ABOUT the chapter.
                _coh = None
                try:
                    import topic_lock as _tl4c
                    _anchors4 = _tl4c.subject_anchors(
                        outline_data.get("title"), ch.get("title"),
                        ch.get("brief"))
                    _coh = _tl4c.coherence_report(_ext_vo, _anchors4)
                except Exception as _e4c:
                    print(f"render_chapters: coherence check failed "
                          f"({str(_e4c)[:100]}) — top-up coherence "
                          f"unverified")
                # v100 (Gate 5 — LENGTH HONESTY): the extension may
                # only add NEW material. A restatement top-up (the
                # Male Gaze chapters "topped up" by repeating
                # themselves, then overshot their budgets) is
                # REJECTED: the chapter ships at its honest length
                # and the film's total adjusts to reality.
                _nov100 = None
                _rest100 = None
                try:
                    import anti_boring as _ab100t
                    _old_vo = [str(s.get("vo") or "") for s in
                               ((res.get("plan") or {}).get("scenes")
                                or [])]
                    _new_vo = [str(s.get("vo") or "") for s in
                               ((ext.get("plan") or {}).get("scenes")
                                or [])]
                    if _old_vo and _new_vo:
                        _nov100 = _ab100t.novelty_report(_new_vo,
                                                         _old_vo)
                        # NEXT-ROUND (Fix 1): the 4-gram gate only
                        # catches VERBATIM repetition — the second
                        # film's top-up was a paraphrase and scored
                        # 0.0. The semantic restatement report now
                        # judges the same pair; EITHER gate can
                        # reject.
                        _rest100 = _ab100t.restatement_report(
                            _new_vo, _old_vo)
                except Exception as _e100t:
                    print(f"render_chapters: novelty check failed "
                          f"({str(_e100t)[:100]}) — top-up kept, "
                          f"novelty unverified")
                _novelty_info = _nov100
                if _rest100 is not None:
                    _novelty_info = {"ngram": _nov100,
                                     "restatement": _rest100}
                _reject100 = None
                # The citation rides every rejection (round-3
                # ruling): the QC/teeth side names the taste-pack
                # rule the top-up broke — the compression pass.
                _cite100 = ("; taste pack, The compression pass: "
                            "a top-up may only add NEW evidence, "
                            "a NEW angle, or a NEW consequence")
                if _nov100 is not None and not _nov100["novel"]:
                    _reject100 = (
                        f"restatement (mean overlap "
                        f"{_nov100['mean_overlap']:.0%}, worst "
                        f"scene {_nov100['worst_overlap']:.0%})"
                        + _cite100)
                elif _rest100 is not None and \
                        _rest100["restatement"]:
                    _reject100 = (
                        f"restatement (paraphrase — mean content "
                        f"containment "
                        f"{_rest100['mean_containment']:.0%}, no "
                        f"new claim/fact/angle)"
                        + _cite100)
                if _reject100 is None and _long_ctx and \
                        _ext_gate is None:
                    _reject100 = (
                        "no fact-gate event on the top-up pass — "
                        "fail closed: ungated material never joins "
                        "a gated chapter (round 4, fix 2)")
                if _reject100 is None and _coh is not None and \
                        _coh["checked"] and not _coh["coherent"]:
                    _reject100 = (
                        f"topic drift — only "
                        f"{_coh['scenes_with_anchor']}/{_coh['scenes']} "
                        f"top-up scenes touch the chapter's locked "
                        f"subject (dominant new words: "
                        f"{', '.join(_coh['foreign_words']) or '—'}); "
                        f"a top-up extends the SAME chapter's "
                        f"subject (round 4, topic lock)")
                if _reject100 is not None:
                    res = {**res,
                           "topup_rejected": _reject100,
                           "honest_length": True,
                           "topup_novelty": _novelty_info}
                    if _coh is not None:
                        res["topup_coherence"] = _coh
                    print(f"render_chapters: chapter {i + 1} top-up "
                          f"REJECTED — {_reject100}; the chapter "
                          f"ships at its honest {int(dur)}s")
                else:
                    joined = _join_clips(
                        [res["path"], ext["path"]],
                        str(ch_dir / f"ch{i + 1:02d}_full.mp4"))
                    try:
                        new_dur = _probe_duration(joined)
                    except Exception:
                        new_dur = dur + float(ext.get("duration") or 0)
                    res = {**res, "path": joined, "duration": new_dur,
                           "topped_up": True,
                           "topup_seconds": missing_s,
                           "broll": (res.get("broll") or [])
                                    + (ext.get("broll") or [])}
                    if _novelty_info is not None:
                        res["topup_novelty"] = _novelty_info
                    if _coh is not None:
                        res["topup_coherence"] = _coh
                    print(f"render_chapters: chapter {i + 1} topped "
                          f"up ({int(dur)}s -> {int(new_dur)}s of "
                          f"{budget['seconds']}s budget)")
        except Exception as e:
            print(f"render_chapters: chapter {i + 1} top-up failed "
                  f"({str(e)[:150]}) — keeping the rendered chapter")
        # ROUND 4 (Fix 5 — DEPICTION BUDGET): count the chapter's
        # depiction mix from its plan BEFORE the fix loop, so an
        # over-literal chapter's DEPICTION FAIL rides the same
        # compliance teeth as any other boring-critical failure
        # (round-3 pack rule: literal illustration <= ~20% of
        # beats; film 3 measured 57.5% and nothing counted it).
        try:
            import depiction_qc as _dq4
            _dep_scenes = (res.get("plan") or {}).get("scenes") or []
            res["depiction"] = _dq4.depiction_report(_dep_scenes)
            _dep_checks = _dq4.depiction_checks(_dep_scenes)
            if _dep_checks:
                _rep4 = dict(res.get("compliance") or {})
                _rep4["checks"] = list(_rep4.get("checks") or []) \
                    + _dep_checks
                _rep4["checks_failed"] = sum(
                    1 for c in _rep4["checks"]
                    if c.get("status") == "FAIL")
                res["compliance"] = _rep4
                print(f"render_chapters: chapter {i + 1} depiction "
                      f"{res['depiction']['literal_share']:.0%} "
                      f"literal — over the "
                      f"{_dq4.LITERAL_BUDGET:.0%} budget; DEPICTION "
                      f"FAIL rides the fix loop")
        except Exception as _e4d:
            print(f"render_chapters: depiction count failed "
                  f"({str(_e4d)[:100]})")
        # ROUND 5 (Fix 1 + 2 + 6): the director-fallback verdict
        # for this chapter's passes, the pixel motion audit and
        # the presenter audit — all boring-critical, all riding
        # the fix loop below. Film 3 shipped a fallback-directed,
        # static-card chapter as if it were directed work.
        try:
            import brain_status as _bs5f
            _fb5 = (_bs5f.fallback_stages_since(
                _bs5_mark,
                stages=("editing-director", "visual-director"))
                if _bs5_mark is not None else [])
        except Exception:
            _fb5 = []
        if _fb5:
            res["director_fallback"] = {"stages": _fb5}
            _rep5 = dict(res.get("compliance") or {})
            _rep5["checks"] = [
                c for c in (_rep5.get("checks") or [])
                if c.get("rule") != "DIR-FALLBACK"] + [
                    _director_check(_fb5, i + 1)]
            res["compliance"] = _rep5
            print(f"render_chapters: chapter {i + 1} DIRECTOR "
                  f"FALLBACK ({', '.join(_fb5)}) — labelled, "
                  f"rides the fix loop")
        _r5_checks, _r5_info = _round5_checks(
            res, presenter_allowed=bool(
                (ch_cfg or cfg or {}).get("presenter")))
        if _r5_info["presenter_flags"]:
            res["presenter_flags"] = _r5_info["presenter_flags"]
        if _r5_checks:
            _rep5b = dict(res.get("compliance") or {})
            _rep5b["checks"] = list(_rep5b.get("checks") or []) \
                + _r5_checks
            _rep5b["checks_failed"] = sum(
                1 for c in _rep5b["checks"]
                if c.get("status") == "FAIL")
            res["compliance"] = _rep5b
            print(f"render_chapters: chapter {i + 1} round-5 "
                  f"checks: {[c['rule'] for c in _r5_checks]}")
        # v79 (R12 + FIX 5): a chapter whose compliance report still
        # FAILs is re-rendered with the failures named in its brief —
        # fix only that chapter, keep the best attempt.
        # A passed deadline skips retries (partial semantics win).
        #
        # v100 (Gate 3 — QC WITH TEETH): the loop no longer requires
        # a spec. The Male Gaze run was spec-less, so its 112
        # compliance FAILs were LOGGED and shipped with 0 fix
        # rounds. Now: with a spec, any FAIL triggers (existing
        # behaviour); without one, FAILs in the boring-critical
        # classes (anti_boring.BORING_CRITICAL_RULES — footage
        # share, variety, dead air, fact gate) trigger. Max 3
        # rounds (Ajju's production protocol: fix loop max 3).
        _fix_rounds_used = 0
        for _round in range(3):
            rep = res.get("compliance") or {}
            failed = [c for c in (rep.get("checks") or [])
                      if c.get("status") == "FAIL"]
            if spec is not None:
                trigger = failed
            else:
                try:
                    import anti_boring as _ab100f
                    trigger = _ab100f.boring_critical_fails(failed)
                except Exception:
                    trigger = []
            if not trigger:
                break
            # ROUND 4 (Fix 4): fix rounds are optional passes —
            # they stop at the CHAPTER's budget share, not the
            # job's, so one chapter's correction loop can no
            # longer consume the whole film budget.
            if _ch_deadline is not None \
                    and time.monotonic() > _ch_deadline:
                print(f"render_chapters: chapter {i + 1} fix "
                      f"rounds stop — the chapter's budget share "
                      f"is spent ({len(failed)} FAIL(s) remain, "
                      f"labelled in the report)")
                break
            _fix_rounds_used += 1
            fix_lines = "; ".join(
                f"{c.get('rule')} scene {c.get('scene')}: {c.get('detail', '')[:90]}"
                for c in trigger[:8])
            _guide100 = _fix_guidance100(trigger)
            if _guide100:
                fix_lines += "\n" + "\n".join(_guide100)
            fix_dir = ch_dir / f"fix{_round + 1}"
            fix_dir.mkdir(parents=True, exist_ok=True)
            _pool_mark = len(pool.assignments) if pool is not None else 0
            # ROUND 5 (Fix 1): this fix render's own ledger
            # window — its director verdict is judged on ITS
            # stages, not the chapter's earlier passes.
            try:
                import brain_status as _bs5fx
                _fix_mark5 = _bs5fx.mark()
            except Exception:
                _fix_mark5 = None
            try:
                res2 = await doc.make_video(
                    ch_brief + ("\nCOMPLIANCE FIXES REQUIRED — the "
                                "previous render of this chapter "
                                "failed these checks; fix exactly "
                                "these, change nothing else: "
                                + fix_lines),
                    chat, notify=notify, workdir=str(fix_dir),
                    **({"ref_voice": ref_voice}
                       if ref_voice is not None else {}),
                    **({"amendments": amendments}
                       if amendments is not None else {}),
                    **({"spec": spec, "cfg": ch_cfg,
                        "footage_pool": pool}
                       if spec is not None or pool is not None
                       or cfg is not None else {}))
            except Exception as e:
                print(f"render_chapters: chapter {i + 1} compliance "
                      f"retry {_round + 1} failed ({str(e)[:120]})")
                break
            # ROUND 4 (Fix 5): the fix pass is re-counted for
            # depiction too — its own mix is part of whether it
            # is an improvement.
            try:
                import depiction_qc as _dq4f
                _dep2 = _dq4f.depiction_checks(
                    (res2.get("plan") or {}).get("scenes") or [])
                if _dep2:
                    _rep2b = dict(res2.get("compliance") or {})
                    _rep2b["checks"] = list(
                        _rep2b.get("checks") or []) + _dep2
                    res2["compliance"] = _rep2b
            except Exception:
                pass
            # ROUND 5 (Fix 1): a fix round clears DIR-FALLBACK
            # only if the brain director ACTUALLY RAN in this
            # render — re-evaluate this pass's ledger window and
            # re-inject the FAIL when it fell back again. A
            # deterministic re-render is not a fix. The fix pass
            # is re-audited for motion + presenter the same way.
            try:
                import brain_status as _bs5x
                _fb2 = (_bs5x.fallback_stages_since(
                    _fix_mark5,
                    stages=("editing-director", "visual-director"))
                    if _fix_mark5 is not None else [])
            except Exception:
                _fb2 = []
            if _fb2:
                res2["director_fallback"] = {"stages": _fb2}
                _rep2c = dict(res2.get("compliance") or {})
                _rep2c["checks"] = [
                    c for c in (_rep2c.get("checks") or [])
                    if c.get("rule") != "DIR-FALLBACK"] + [
                        _director_check(_fb2, i + 1)]
                res2["compliance"] = _rep2c
            else:
                res2.pop("director_fallback", None)
            _r5c2, _r5i2 = _round5_checks(
                res2, presenter_allowed=bool(
                    (ch_cfg or cfg or {}).get("presenter")))
            if _r5i2["presenter_flags"]:
                res2["presenter_flags"] = _r5i2["presenter_flags"]
            if _r5c2:
                _rep2d = dict(res2.get("compliance") or {})
                _rep2d["checks"] = [
                    c for c in (_rep2d.get("checks") or [])
                    if c.get("rule") not in
                    ("MOTION-STATIC", "PRESENTER-CARD")] + _r5c2
                res2["compliance"] = _rep2d
            rep2 = res2.get("compliance") or {}
            failed2 = [c for c in (rep2.get("checks") or [])
                       if c.get("status") == "FAIL"]
            print(f"render_chapters: chapter {i + 1} compliance "
                  f"retry {_round + 1}: {len(failed)} -> "
                  f"{len(failed2)} failed checks")
            # ROUND 4 (Fix 2): the fix pass's fact-gate event is
            # recorded like every pass; an ungated fix pass is
            # NOT accepted over the gated render it would replace
            # (fail closed, labelled).
            _ev2 = (res2.get("plan") or {}).get("fact_gate") \
                if _long_ctx else None
            if _long_ctx:
                _gate_passes.append(
                    {"pass": f"fix{_round + 1}", **_ev2}
                    if _ev2 is not None else
                    {"pass": f"fix{_round + 1}", "missing": True})
            if len(failed2) <= len(failed):
                if _long_ctx and _ev2 is None:
                    print(f"render_chapters: chapter {i + 1} fix "
                          f"pass {_round + 1} carries NO fact-gate "
                          f"event — not accepted (fail closed)")
                else:
                    res = res2
                    if pool is not None:
                        pool.assignments = (
                            pool.assignments[:_pool_mark0]
                            + pool.assignments[_pool_mark:])
                        pool._save()
            if not failed2:
                break
        # ROUND 4: the chapter's FINAL records — the depiction
        # mix of the plan that actually ships (post fix rounds),
        # with exactly one DEPICTION check in its compliance
        # matching that mix; the per-pass fact-gate events; and
        # the chapter's budget share vs what it used.
        try:
            import depiction_qc as _dq4z
            _fin_scenes = (res.get("plan") or {}).get("scenes") or []
            res["depiction"] = _dq4z.depiction_report(_fin_scenes)
            _repF = dict(res.get("compliance") or {})
            _checksF = [c for c in (_repF.get("checks") or [])
                        if c.get("rule") != "DEPICTION"]
            _checksF += _dq4z.depiction_checks(_fin_scenes)
            _repF["checks"] = _checksF
            _repF["checks_failed"] = sum(
                1 for c in _checksF if c.get("status") == "FAIL")
            res["compliance"] = _repF
        except Exception:
            pass
        # ROUND 5: the shipped chapter's FINAL motion/presenter
        # checks (recomputed on the plan that actually ships,
        # like depiction above) and its director verdict.
        try:
            _r5F, _r5Fi = _round5_checks(
                res, presenter_allowed=bool(
                    (ch_cfg or cfg or {}).get("presenter")))
            _repF2 = dict(res.get("compliance") or {})
            _checksF2 = [c for c in (_repF2.get("checks") or [])
                         if c.get("rule") not in
                         ("MOTION-STATIC", "PRESENTER-CARD")]
            _checksF2 += _r5F
            _repF2["checks"] = _checksF2
            _repF2["checks_failed"] = sum(
                1 for c in _checksF2 if c.get("status") == "FAIL")
            res["compliance"] = _repF2
            if _r5Fi["presenter_flags"]:
                res["presenter_flags"] = _r5Fi["presenter_flags"]
            if _r5Fi["motion_audit"]:
                res["motion_audit"] = _r5Fi["motion_audit"]
        except Exception:
            pass
        res["director_fallback_final"] = bool(
            res.get("director_fallback")) or any(
            c.get("rule") == "DIR-FALLBACK"
            and c.get("status") == "FAIL"
            for c in ((res.get("compliance") or {})
                      .get("checks") or []))
        if _long_ctx:
            res["fact_gate_passes"] = _gate_passes
        if deadline is not None:
            res["chapter_budget"] = {
                "share_s": round(_ch_deadline - _ch_t0, 1)
                if _ch_deadline else None,
                "used_s": round(time.monotonic() - _ch_t0, 1)}
        # v84 (Stage 2): record the TRUE correction rounds this
        # chapter consumed — the long report used to hard-code 0.
        res["fix_rounds_used"] = _fix_rounds_used
        paths.append(res["path"])
        if results_out is not None:
            results_out.append(res)
        # The chapter mp4 is final — its extracted B-roll frames (tens of
        # MB per chapter) are dead weight on the runner disk from here.
        shutil.rmtree(ch_dir / "broll_frames", ignore_errors=True)
    return paths


def _designed_silence_windows(results, chapter_starts):
    """v88/v98.1: the Editing Director's sanctioned silence windows
    (silence_after_s on the chapter plans), mapped to absolute time
    in the assembled file from each chapter's start offset. The
    media meters report gaps inside these windows as DESIGNED
    instead of failing them as dead air — v87 shipped 5 such false
    FAILs and the correction loop re-rendered chapters over pauses
    the director had chosen.

    Shared by _correct_assembled and make_long_video's
    spec-compliance audit. Until v98.1 this lived ONLY as a nested
    helper inside _correct_assembled, so the compliance block's
    call to it threw NameError, was swallowed by its except, and
    spec jobs silently fell back to the unconditional QC report —
    the designed-silence awareness in spec compliance was dead
    code."""
    wins = []
    for ci, r in enumerate(results or []):
        plan = (r or {}).get("plan") or {}
        scs = plan.get("scenes") or []
        st = plan.get("starts") or []
        base = chapter_starts[ci] if ci < len(chapter_starts) else 0.0
        for j, s in enumerate(scs):
            sil = float(s.get("silence_after_s") or 0)
            if sil > 0 and j < len(st):
                a = base + float(st[j]) + float(s.get("d") or 0)
                wins.append((round(a, 2), round(a + sil, 2)))
    return wins


def _flattest_music_chapters(results, limit=2):
    """v100 (Gate 6): chapter numbers (1-based) whose PLANNED
    music-intensity curve is flattest (smallest max-min spread
    across the chapter's beats) — the chapters a flat delivered
    mix is most likely made of. A chapter with no curve data
    sorts first: an absent curve is the flattest of all."""
    scored = []
    for i, r in enumerate(results or []):
        scenes = ((r or {}).get("plan") or {}).get("scenes") or []
        vals = [float(s["music_intensity"]) for s in scenes
                if isinstance(s, dict)
                and isinstance(s.get("music_intensity"), (int, float))]
        spread = (max(vals) - min(vals)) if len(vals) >= 2 else 0.0
        scored.append((spread, i + 1))
    scored.sort()
    return [ch for _sp, ch in scored[:int(limit)]]


async def _correct_assembled(final, paths, results, outline_data, chat,
                             workdir, titles, size, notify=None,
                             deadline=None, ref_voice=None,
                             amendments=None, spec=None, cfg=None,
                             pool=None, mq_cfg=None, size_explicit=False):
    """v85: the assembled-file correction loop, wired end-to-end.

    Inspect the ACTUAL assembled file with media_qc (deterministic
    ffmpeg/ffprobe measurement: black / frozen / blank frames, A/V
    mismatch, loudness, silence, colour drift, repeated visuals) ->
    map each defect to its chapter -> correct at CHAPTER level
    (re-render only the defective chapters, or fix the file-level
    audio in place) -> re-assemble -> inspect again. Maximum 3
    rounds (qc_core.bounded_correct_async; v100 — Ajju's fix-loop
    protocol); the TRUE round count
    and fixes are returned for the compliance report. Defects that
    cannot be corrected safely stay FAIL in the returned checks —
    warn-and-deliver, never a false PASS.
    Returns (mq_checks, rounds_used, fixes, final_path, paths)."""
    import media_qc as _mq
    import qc_core as _qcx
    state = {"final": str(final), "paths": [str(p) for p in paths],
             "dirty": False}

    def _starts():
        durs = []
        for p in state["paths"]:
            try:
                durs.append(_probe_duration(p))
            except Exception:
                durs.append(0.0)
        st, t = [], 0.0
        for i, d in enumerate(durs):
            st.append(t)
            t += d + (CARD_SECONDS if i < len(durs) - 1 else 0.0)
        return st

    expected = None
    if size:
        expected = (int(size[0]), int(size[1]))
    elif state["paths"]:
        _inf = _mq.probe(state["paths"][0])
        if _inf.get("video"):
            expected = (_inf["video"].get("width"),
                        _inf["video"].get("height"))

    def check_fn():
        ch, _info = _mq.inspect_file(
            state["final"],
            cfg={**(mq_cfg or {}), "kind": "long"},
            chapter_starts=_starts(),
            workdir=str(workdir), expected_size=expected,
            designed_silences=_designed_silence_windows(results,
                                                        _starts()))
        return ch

    async def correct_fn(failed, rnd):
        fixes = []
        by_ch = _mq.chapter_defect_map(failed)
        file_level = by_ch.get(None) or []
        # --- file-level: loudness fixed in place (no re-render)
        if any(c["rule"] == "MQ-LOUD" for c in file_level):
            tmp = state["final"] + ".loud.mp4"
            measured = _measure_loudness(state["final"])
            if measured is not None:
                p = _loudnorm_params(measured)
                af = ("loudnorm=I=-14:TP=-1.0:LRA=11"
                      f":measured_I={p['measured_I']}"
                      f":measured_TP={p['measured_TP']}"
                      f":measured_LRA={p['measured_LRA']}"
                      f":measured_thresh={p['measured_thresh']}"
                      f":offset={p['offset']}:linear={p['linear']}")
            else:
                af = "loudnorm=I=-14:TP=-1.0:LRA=11"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                            "-i", state["final"], "-af", af,
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                            "-movflags", "+faststart", tmp], check=True)
            os.replace(tmp, state["final"])
            fixes.append(f"round {rnd}: re-applied dual-pass loudnorm "
                         f"to the assembled file (no re-render)")
        # --- chapter-level: re-render only defective chapters
        _work = {}
        for _k in by_ch:
            if _k is not None:
                _work[_k] = sorted({c["rule"] for c in by_ch[_k]})
        # v100 (Gate 6 — SOUND FLOOR): MQ-LRA is a file-level
        # check, but its fix is chapter-level: re-render the
        # chapters whose planned music curve is flattest with the
        # cue-sheet brief. The curve must be EXECUTED — a flat
        # mix is re-edited, not just re-measured.
        if any(c["rule"] == "MQ-LRA" for c in file_level):
            for _chno100 in _flattest_music_chapters(results,
                                                     limit=2):
                _work.setdefault(_chno100, [])
                if "MQ-LRA" not in _work[_chno100]:
                    _work[_chno100].append("MQ-LRA")
        done = 0
        for chno in sorted(_work):
            if done >= 2:
                break
            rules = sorted(_work[chno])
            if not set(rules) & {"MQ-BLACK", "MQ-FREEZE", "MQ-BLANK",
                                 "MQ-SILENCE", "MQ-REPEAT", "MQ-LRA"}:
                continue
            if deadline is not None and time.monotonic() > deadline:
                fixes.append(f"round {rnd}: chapter {chno} fix skipped "
                             f"— job deadline passed")
                break
            i = int(chno) - 1
            fix_dir = Path(workdir) / f"ch{chno:02d}" / f"mqfix{rnd}"
            fix_dir.mkdir(parents=True, exist_ok=True)
            brief_i = chapter_brief(outline_data, i, spec=spec)
            try:
                import doc_structure as _ds
                brief_i += _ds.arc_context_block(outline_data, i)
            except Exception:
                pass
            _rq100 = [r for r in rules if r != "MQ-LRA"]
            if _rq100:
                brief_i += (
                    "\nQUALITY FIX — the previous render of this "
                    "chapter had these measured defects in the "
                    f"ASSEMBLED video: {', '.join(_rq100)}. "
                    "Regenerate the chapter with complete, varied "
                    "visuals: no black, frozen or blank frames, no "
                    "repeated footage, no unexplained silence.")
            if "MQ-LRA" in rules:
                brief_i += (
                    "\nSOUND FIX — the assembled film's loudness "
                    "range measured FLAT: the cue-sheet music "
                    "curve was planned but not executed. Re-edit "
                    "this chapter so the music intensity FOLLOWS "
                    "THE ARC and actually moves: hook 0.7, "
                    "context/evidence 0.5, contradiction 0.55, "
                    "turning point dips to 0.3, payoff lifts to "
                    "0.85, conclusion decays to 0.4; music ducks "
                    "under narration and lifts in non-narration "
                    "windows; SFX land on story beats only, not "
                    "on every cut.")
            ch_cfg = None
            if cfg is not None:
                ch_cfg = dict(cfg)
                ch_cfg["allow_cta"] = (
                    i == len(outline_data["chapters"]) - 1)
            res2 = await doc.make_video(
                brief_i, chat, notify=notify, workdir=str(fix_dir),
                **({"ref_voice": ref_voice} if ref_voice is not None else {}),
                **({"amendments": amendments} if amendments is not None else {}),
                **({"spec": spec, "cfg": ch_cfg, "footage_pool": pool}
                   if spec is not None or pool is not None
                   or cfg is not None else {}))
            state["paths"][i] = str(res2["path"])
            if i < len(results):
                results[i] = {**results[i], "path": str(res2["path"]),
                              "duration": res2.get("duration"),
                              "mq_fixed_round": rnd}
            state["dirty"] = True
            done += 1
            fixes.append(f"round {rnd}: re-rendered chapter {chno} "
                         f"({', '.join(rules)})")
        # --- A/V mismatch or chapter changes: re-assemble once
        if state["dirty"] or any(c["rule"] == "MQ-AVSYNC"
                                  for c in file_level):
            state["final"] = assemble(
                state["paths"], state["final"], titles,
                size=size, card_bg_from=list(state["paths"]),
                size_explicit=size_explicit)
            state["dirty"] = False
            fixes.append(f"round {rnd}: re-assembled the documentary "
                         f"from its chapters")
        return fixes

    # v100 (Gate 3): 3 rounds, per Ajju's production protocol
    # (fix loop max 3) — was 2.
    checks, rounds, fixes, _ok = await _qcx.bounded_correct_async(
        check_fn, correct_fn, max_rounds=3)
    return checks, rounds, fixes, state["final"], state["paths"]


async def make_long_video(brief, chat, workdir, target_minutes,
                          notify=None, deadline=None, ref_voice=None,
                          amendments=None, spec=None, cfg=None,
                          topic_history=None, topic_exclusions=None):
    """Runner entry point (v69): outline -> chaptered render -> assemble
    for a requested length of target_minutes (2-60). Returns a result
    dict shaped like doc.make_video's (path/title/duration/lang/caption/
    topic/plan) plus: broll (aggregated chapter B-roll sources), summary,
    partial, chapters_done, chapters_total, long=True. A partial result
    (deadline hit or a midway chapter failure) still returns the longest
    completed assembly — it never silently shortens a finished plan:
    `partial` says exactly how many chapters are missing.
    """
    # v79 (R-P5 / mail 2b point 5): with a prompt spec, the render
    # parameters come FROM the spec — target length, chapter count,
    # size — never re-chosen here. A spec that cannot resolve raises
    # SpecImpossible and the job fails loudly BEFORE any render.
    # v98 (portrait trap-door fix): the resolution is UNCONDITIONAL.
    # A long job with no spec contract now resolves the long defaults
    # (1920x1080 landscape) instead of running config-less — before
    # this, cfg stayed None for no-spec jobs, the chapters rendered
    # at the short engine's portrait default, and the assembly fell
    # back to the historical 1080x1920: EVERY long video Julie ever
    # delivered (v87, v88, the Compromise video) was portrait. Below
    # this block, cfg is ALWAYS a resolved long render config.
    import spec_engine as _se
    if cfg is None:
        cfg = _se.resolve_render_config(spec, "long")
    # ROUND 4 (Fix 1): the topic lock's data rides the render
    # config into every chapter (doc's plan_info reads it for the
    # per-chapter topic verdicts) and into the outline call below.
    if topic_history:
        cfg["topic_history"] = list(topic_history)
    if topic_exclusions:
        cfg["topic_exclusions"] = list(topic_exclusions)
    chapters_wanted = None
    if cfg.get("duration_s"):
        target_minutes = max(2, min(60, int(round(cfg["duration_s"] / 60))))
    chapters_wanted = cfg.get("chapters")
    out, last_err = None, None
    for attempt in range(2):
        try:
            b = brief if attempt == 0 else (
                (brief or "") +
                f"\n(The outline MUST total exactly {target_minutes} "
                f"minutes — count the chapter minutes.)")
            out = outline(b, chat, target_minutes,
                          chapters_wanted=chapters_wanted,
                          topic_history=topic_history,
                          exclusions=topic_exclusions)
            break
        except ValueError as e:
            last_err = e
    if out is None:
        raise last_err
    total_ch = len(out["chapters"])
    if notify:
        await notify(f"Long video: {out['title']} — {total_ch} chapters, "
                     f"~{target_minutes} min. Chapters render chestunna.")
    # v85: editing memory exists for EVERY long job — not only spec
    # jobs with vision verification on. Selections, rejections, QC
    # failures, corrections and the final result are recorded at the
    # end of the job (see the v85 block before the return), and the
    # verifier below reads the SAME database. Guarded: a memory
    # failure must never take the render down with it.
    _mem84 = None
    _job84 = str(Path(workdir).name)
    try:
        import edit_memory as _em85
        _mem84 = _em85.EditMemory(
            os.environ.get("JULIE_EDIT_MEMORY") or
            str(Path(workdir) / "edit_memory.db"))
        try:
            _em85.seed_knowledge_base(_mem84)
        except Exception:
            pass
    except Exception as _e:
        print(f"edit memory unavailable: {str(_e)[:120]}")
    # v79 (mail 1 Part 2): ONE footage pool for the whole video — the
    # NO-REPEAT used_ids rule spans chapters, not just scenes.
    # v88: the pool is also built when NO spec exists but a footage
    # route is available (a stock key, or the keyless Commons
    # provider) — v85-v87's spec-less runs silently had no pool at
    # all, so footage could never attach even where a route existed.
    pool = None
    import broll as _broll88
    if spec is not None or _broll88.providers_available():
        pool = _broll88.FootagePool(
            state_path=str(Path(workdir) / "footage_state.json"))
    if spec is not None:
        import broll as _broll
        # v84 (Stage 3 / P1): vision verification on the long path —
        # sampled frames vs narration, hash-cached verdicts, strict
        # call budget (default 80/job from edit_memory config; the
        # 60-90 s acceptance test passes 18). Vision unavailable ->
        # UNVERIFIED verdicts, never a silent pass. Disable with
        # JULIE_BROLL_VERIFY=0.
        if os.environ.get("JULIE_BROLL_VERIFY", "1") != "0":
            try:
                import broll_verify as _bv
                import edit_memory as _em
                _mem = _mem84 or _em.EditMemory(
                    os.environ.get("JULIE_EDIT_MEMORY") or
                    str(Path(workdir) / "edit_memory.db"))
                pool.verifier = _bv.BrollVerifier(
                    call_budget=int(os.environ.get(
                        "JULIE_VISION_BUDGET",
                        str(int(_mem.config("vision_max_calls_per_job"))))),
                    cache_path=str(Path(workdir) / "vision_cache.json"),
                    memory=_mem, job_id=str(Path(workdir).name))
                print(f"broll vision verification: ON "
                      f"(budget {pool.verifier.budget} calls)")
            except Exception as _e:
                print(f"broll vision verification unavailable: "
                      f"{str(_e)[:120]}")
    results = []
    # v98: cfg is ALWAYS resolved by now (top of this function), so
    # the render config rides into every long job's chapters — spec
    # contract or not. (The conditional-kwargs shape remains only as
    # a guard for callers that pass cfg=None explicitly.)
    # v88: a long documentary renders with ONE locked grade and the
    # full-frame composition rules (doc module flags — the runner
    # serves one job per process, and doc.plan stamps both onto the
    # plan so a later short in the same process is unaffected).
    doc.GRADE_LOCK = True
    doc.FULL_FRAME = True
    paths = await render_chapters(out, chat, workdir, notify=notify,
                                  deadline=deadline, results_out=results,
                                  ref_voice=ref_voice,
                                  amendments=amendments,
                                  **({"spec": spec, "cfg": cfg, "pool": pool}
                                     if spec is not None or pool is not None
                                     or cfg is not None else {}))
    if not paths:
        raise RuntimeError("long video: no chapters rendered")
    # v87 (role 4): TASTE QC — sampled frames judged against the
    # visual plan's own promises. FAIL beats are RE-PLANNED (the
    # Visual Director directs again with the failed templates
    # excluded) and the chapter is re-rendered from the corrected
    # plan; max 2 re-plan rounds per chapter. With no vision route,
    # every beat stays UNVERIFIED and chapters ship as rendered —
    # never a fake PASS.
    _taste87 = {"version": "v87-frame-taste-qc-1", "rounds": 0,
                "vision": "unavailable", "chapters": []}
    try:
        import copy as _copy87
        import director as _dir87
        import frame_taste_qc as _tq87
        import visual_director as _vd87
        _vision87 = None
        try:
            import vision as _vis87
            if _vis87.available():
                _vision87 = _vis87.describe_images
        except Exception:
            _vision87 = None
        _taste87["vision"] = "live" if _vision87 else "unavailable"
        # PROOF-FIX 1: taste QC's state is on the brain ledger too —
        # with no vision route every beat is UNVERIFIED, and the job
        # report must say the QC fell back, not imply it judged.
        try:
            import brain_status as _bs87lv
            if _vision87:
                _bs87lv.record("taste-qc", True, "vision route live")
            else:
                _bs87lv.record("taste-qc", False,
                               "no vision route — every beat UNVERIFIED, "
                               "chapters shipped as rendered")
        except Exception:
            pass
        for _ci in range(len(results)):
            _plan0 = results[_ci].get("plan") or {}
            _writer = _plan0.get("writer_scenes")
            if not _plan0.get("visual_plan") or not _writer:
                continue
            _entry = {"chapter": _ci + 1, "rounds": []}
            _taste87["chapters"].append(_entry)
            _excl = {}
            for _round in range(3):  # audit + up to 2 re-plan rounds
                _plan = results[_ci].get("plan") or {}
                _recs = _plan.get("visual_plan") or []
                _starts = _plan.get("starts") or []
                _scenes = _plan.get("scenes") or []
                _beats = []
                for _bi, _rec in enumerate(_recs):
                    _st = _starts[_bi] if _bi < len(_starts) else 0.0
                    _d = 3.0
                    if _bi < len(_scenes):
                        _d = float(_scenes[_bi].get("d")
                                   or _rec.get("duration_est_s") or 3)
                    _beats.append({"beat": _rec["beat"],
                                   "line": _rec["heard"],
                                   "promise": _rec["see"],
                                   "why": _rec.get("why", ""),
                                   "start": _st, "duration": _d})
                _rep = await _tq87.audit_beats(
                    results[_ci]["path"], _beats,
                    str(Path(workdir) / f"ch{_ci + 1:02d}" / "taste"),
                    vision=_vision87)
                _entry["rounds"].append(
                    {"round": _round, "vision": _rep["vision"],
                     "counts": _rep["counts"],
                     "beats": [{"beat": b["beat"],
                                "status": b["status"],
                                "note": b["note"]}
                               for b in _rep["beats"]]})
                print(f"taste QC v87: chapter {_ci + 1} round "
                      f"{_round} — {_rep['counts']}")
                if _mem84 is not None:
                    try:
                        for _b in _rep["beats"]:
                            _tpl = ""
                            _line = ""
                            if 0 < _b["beat"] <= len(_recs):
                                _tpl = _recs[_b["beat"] - 1].get(
                                    "visual_concept", "")
                            if 0 < _b["beat"] <= len(_beats):
                                _line = _beats[_b["beat"] - 1]["line"]
                            _mem84.record_taste_outcome(
                                _job84,
                                f"ch{_ci + 1} beat {_b['beat']}",
                                _tpl, _line, _b["status"], _b["note"])
                    except Exception:
                        pass
                _failed = [b for b in _rep["beats"]
                           if b["status"] == "FAIL"]
                if not _failed or _round >= 2 or _vision87 is None:
                    break
                for _b in _failed:
                    if 0 < _b["beat"] <= len(_recs):
                        _tpl = _recs[_b["beat"] - 1].get(
                            "visual_concept", "")
                        if _tpl:
                            _excl.setdefault(
                                _b["beat"], []).append(_tpl)
                _brief_i = chapter_brief(out, _ci, spec=spec)
                try:
                    import doc_structure as _ds87
                    _brief_i += _ds87.arc_context_block(out, _ci)
                except Exception:
                    pass
                _inp = _copy87.deepcopy(results[_ci].get("plan") or {})
                _inp["scenes"] = _copy87.deepcopy(_writer)
                import pack_slicer as _ps87lv
                _new_plan, _new_recs = _dir87.direct_plan(
                    _inp, brief=_brief_i, chapter_index=_ci,
                    chapter_count=len(out["chapters"]),
                    brain={"chat": chat,
                           "taste_visual": _ps87lv.slice_for("qc"),
                           "taste_editing": _ps87lv.slice_for("editing"),
                           "taste": _ps87lv.slice_for("qc"),
                           "beat_sheet": _inp.get("beat_sheet"),
                           "exclude": _excl})
                _new_plan["writer_scenes"] = _copy87.deepcopy(_writer)
                if _inp.get("beat_sheet"):
                    _new_plan["beat_sheet"] = _inp["beat_sheet"]
                _tdir = Path(workdir) / f"ch{_ci + 1:02d}" / \
                    f"taste{_round + 1}"
                _tdir.mkdir(parents=True, exist_ok=True)
                _ch_cfg = None
                if cfg is not None:
                    _ch_cfg = dict(cfg)
                    _ch_cfg["allow_cta"] = (
                        _ci == len(out["chapters"]) - 1)
                _res2 = await doc.make_video(
                    _brief_i, chat, notify=notify, workdir=str(_tdir),
                    plan_override=_new_plan,
                    **({"ref_voice": ref_voice}
                       if ref_voice is not None else {}),
                    **({"amendments": amendments}
                       if amendments is not None else {}),
                    **({"spec": spec, "cfg": _ch_cfg,
                        "footage_pool": pool}
                       if spec is not None or pool is not None
                       or cfg is not None else {}))
                _res2["fix_rounds_used"] = int(
                    results[_ci].get("fix_rounds_used") or 0)
                results[_ci] = _res2
                paths[_ci] = _res2["path"]
                _taste87["rounds"] += 1
                _entry["replanned"] = {str(k): v
                                       for k, v in _excl.items()}
                print(f"taste QC v87: chapter {_ci + 1} re-planned "
                      f"(excluded {_excl}) and re-rendered")
        with open(Path(workdir) / "taste_qc.json", "w",
                  encoding="utf-8") as _f:
            json.dump(_taste87, _f, indent=1)
    except Exception as e:
        print("taste QC v87 loop failed:", str(e)[:200])
        _taste87["error"] = str(e)[:200]
    titles = [ch["title"] for ch in out["chapters"]][:len(paths)]
    # v98 (portrait trap-door fix): the assembly size ALWAYS comes
    # from the resolved render config — the config-less assemble
    # call that silently produced portrait is gone. The size counts
    # as explicit (so an explicitly-asked portrait long video stays
    # possible) ONLY when the user's own spec stated the aspect/size.
    _size = (int(cfg["width"]), int(cfg["height"]))
    _size_explicit = "aspect_ratio" in (cfg.get("spec_ids") or {})
    final = assemble(paths, str(Path(workdir) / "long_final.mp4"), titles,
                     size=_size, card_bg_from=list(paths),
                     size_explicit=_size_explicit)
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
    # PROOF-FIX 2: the achieved footage share is in the delivery
    # summary — a long with no photographs must say so in numbers.
    _tot_sc = sum(len((r.get("plan") or {}).get("scenes") or [])
                  for r in results)
    _cov_sc = sum(1 for r in results
                  for s in ((r.get("plan") or {}).get("scenes") or [])
                  if s.get("has_footage"))
    if _tot_sc:
        summary += (f"; footage on {_cov_sc}/{_tot_sc} scenes "
                    f"({_cov_sc / _tot_sc:.0%})")
    # PROOF-FIX 1: the brain ledger line — any stage that fell back
    # to a deterministic stand-in is labelled in the delivery
    # summary itself, not buried in the run log.
    try:
        import brain_status as _bs_lv
        _bsline = _bs_lv.line()
        if _bsline:
            summary += f"; {_bsline}"
    except Exception:
        pass
    # NEXT-ROUND (Fix 5c): a single-provider film says so in its
    # own delivery summary — "channel: single-provider (groq) —
    # no failover possible" — instead of letting the failover
    # machinery imply a second provider stood ready.
    try:
        import channel as _chan_lv
        _cwarn = _chan_lv.channel_status().get("warning")
        if _cwarn:
            summary += f"; {_cwarn}"
    except Exception:
        pass
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
    # v79 (R12): the long video's own self-check — every chapter's
    # plan checks, the footage record, and a media audit of the
    # ASSEMBLED file (size from spec, duration within 10%, -14 LUFS /
    # -1 dBTP, no silence >0.8 s outside chapter breaks), sampled at
    # 1 frame / 4 s. The three artifacts land at the workdir root.
    # v100 (Gate 2 — FG-TEASE): the film may only tease content
    # that exists in its own plan. The Male Gaze film ended on a
    # giant "4" teasing a Chapter 4 that was never made. Audited
    # once here, over every chapter's lines + the end card, and
    # added to whichever compliance report the job produces.
    _tease100 = []
    try:
        import anti_boring as _ab100z
        _texts100 = []
        for _ci100, _r100 in enumerate(results):
            for _s100 in ((_r100.get("plan") or {}).get("scenes")
                          or []):
                _texts100.append((_ci100 + 1,
                                  str(_s100.get("vo") or "")))
        _last_plan100 = (results[-1].get("plan") or {}) if results \
            else {}
        _last_scenes100 = _last_plan100.get("scenes") or []
        _tease100 = _ab100z.audit_teases(
            _texts100, total_ch,
            end_question=str(_last_plan100.get("end_question")
                             or ""),
            last_scene=_last_scenes100[-1] if _last_scenes100
            else None)
        if _tease100:
            print(f"tease audit v100: {len(_tease100)} fake "
                  f"tease(s) found")
    except Exception as _e100z:
        print("tease audit v100 failed:", str(_e100z)[:120])
    report = None
    if spec is not None and cfg is not None:
        try:
            import compliance as _comp
            checks = []
            for ci, r in enumerate(results):
                for c in ((r.get("compliance") or {}).get("checks") or []):
                    checks.append({**c, "chapter": ci + 1})
            _durs = []
            for pth in paths:
                try:
                    _durs.append(_probe_duration(pth))
                except Exception:
                    _durs.append(0.0)
            _starts, _t = [], 0.0
            for _d in _durs:
                _starts.append(_t)
                _t += _d + CARD_SECONDS
            mchecks, minfo = _comp.audit_media(
                final, cfg, spec, chapter_breaks=_starts[1:],
                designed_silences=_designed_silence_windows(results,
                                                            _starts))
            checks += mchecks
            checks += _tease100
            diffs = _comp.sample_frame_diffs(final)
            frozen = 0
            run = 0
            for d in diffs:
                run = run + 1 if d < 0.5 else 0
                frozen = max(frozen, run)
            if frozen >= 4:
                checks.append({"rule": "R12", "status": "WARN",
                               "detail": f"frames nearly identical for ~{frozen * 4}s "
                                         f"(sampled 1 frame / 4 s) — a held/still stretch",
                               "scene": None})
            _tot_scenes = sum(len((r.get("plan") or {}).get("scenes") or [])
                              for r in results)
            _cov_scenes = sum(1 for r in results
                              for s in ((r.get("plan") or {}).get("scenes") or [])
                              if s.get("has_footage"))
            plan_info = {
                "lang": first.get("lang"), "topic": first.get("topic", brief),
                # ROUND 4 (Fix 1b): the film-level topic verdict
                # judges the DELIVERED title (the outline's pick)
                # against the lock — not a chapter's raw topic
                # string, and never the word "Auto".
                "title": out["title"],
                "topic_history": list(topic_history or []),
                "topic_exclusions": list(topic_exclusions or []),
                "voice_used": next((r.get("_voice_used") or (r.get("plan") or {}).get("_voice_used")
                                    for r in results if r), None) or first.get("voice_used"),
                "voice_gender": cfg.get("voice_gender"),
                "music_applied": cfg.get("music") is not False,
                "sfx_applied": cfg.get("sfx") is not False,
                "captions_applied": cfg.get("captions") is not False,
                # v79.2 parity with doc: caption script used +
                # whether source lines were drawn (items 5 + 7).
                "caption_script": cfg.get("caption_script"),
                "sources_shown": bool(cfg.get("show_sources")) and any(
                    s.get("source") for r in results
                    for s in ((r.get("plan") or {}).get("scenes") or [])),
                "camera_moves": False,
                "footage_coverage": (_cov_scenes / _tot_scenes) if _tot_scenes else 0.0,
                "end_card_text": (results[-1].get("plan") or {}).get("end_question", "") if results else "",
                "chapters_done": len(paths),
            }
            verdicts = _comp.requirement_verdicts(spec, cfg, plan_info, minfo)
            # v84 (Stage 2 / P0-D): structural documentary QC — one
            # opening, one ending, no repeated hooks/CTAs/intros.
            try:
                import doc_structure as _ds
                checks += _ds.structure_lints(
                    [((r.get("plan") or {}).get("scenes") or [])
                     for r in results])
            except Exception as _e:
                checks.append({"rule": "ST-1", "status": "UNVERIFIED",
                               "detail": f"structure lint failed: {str(_e)[:100]}",
                               "scene": None})
            # v84 (Stage 2): the TRUE correction-round count (was
            # hard-coded rounds=0 here as well).
            _rounds = sum(int(r.get("fix_rounds_used") or 0)
                          for r in results)
            report = _comp.build_report(spec, cfg, checks, verdicts,
                                        rounds=_rounds,
                                        fixes=[f for r in results
                                               for f in ((r.get("compliance") or {}).get("fixes_applied") or [])])
            for _name, _data in (("prompt_spec.json", spec),
                                 ("footage.json", pool.footage_json() if pool else {}),
                                 ("compliance_report.json", report)):
                try:
                    with open(Path(workdir) / _name, "w", encoding="utf-8") as _f:
                        json.dump(_data, _f, indent=1)
                except OSError:
                    pass
            _nf = [c for c in checks if c["status"] == "FAIL"]
            print(f"long compliance: {'PASS' if not _nf else f'{len(_nf)} FAIL'}")
        except Exception as e:
            print("long compliance run failed:", str(e)[:200])
    # v84 (Stage 1 / P0-A): UNCONDITIONAL QC. If the spec path did
    # not produce a report — no spec, or the spec run itself crashed
    # — the job STILL gets a truthful compliance_report.json: media
    # audit + structural lints + whatever chapter checks exist.
    # Checks that could not run are UNVERIFIED, never PASS (Q8:
    # warn-and-deliver; the video above is delivered regardless).
    if report is None:
        try:
            import qc_core as _qc84
            _ch_checks = []
            for _ci, _r in enumerate(results):
                for _c in ((_r.get("compliance") or {}).get("checks") or []):
                    _ch_checks.append({**_c, "chapter": _ci + 1})
            _ch_checks += _tease100
            _durs84 = []
            for _pth in paths:
                try:
                    _durs84.append(_probe_duration(_pth))
                except Exception:
                    _durs84.append(0.0)
            _starts84, _t84 = [], 0.0
            for _d in _durs84:
                _starts84.append(_t84)
                _t84 += _d + CARD_SECONDS
            report = _qc84.unconditional_long_report(
                final, {"kind": "long"}, _ch_checks,
                [((r.get("plan") or {}).get("scenes") or [])
                 for r in results],
                rounds=sum(int(r.get("fix_rounds_used") or 0)
                           for r in results),
                fixes=[f for r in results
                       for f in ((r.get("compliance") or {}).get("fixes_applied") or [])],
                workdir=str(Path(workdir)),
                chapter_breaks=_starts84[1:])
            _nf = [c for c in report["checks"] if c["status"] == "FAIL"]
            print(f"long compliance (unconditional, no spec): "
                  f"{'PASS' if not _nf else f'{len(_nf)} FAIL'}")
        except Exception as e:
            print("unconditional long compliance failed:", str(e)[:200])
    # v85: ASSEMBLED-FILE correction loop. The rendered documentary
    # itself is measured (media_qc: black/frozen/blank frames, A/V
    # mismatch, loudness, silence, colour drift, repeated visuals);
    # defects are corrected at chapter level and the file is
    # re-inspected, max 2 rounds, with the TRUE round count merged
    # into the compliance report. Uncorrectable defects stay FAIL —
    # warn-and-deliver (Q8), never a false PASS.
    _mq_rounds = 0
    _mq_fixes = []
    try:
        _mq_cfg = None
        if _mem84 is not None:
            try:
                _mq_cfg = {
                    "loud_target_lufs": float(
                        _mem84.config("loudness_lufs_target")),
                    "loud_tol_lufs": float(
                        _mem84.config("loudness_tolerance")),
                    "silence_min_s": float(
                        _mem84.config("silence_gap_max_s")),
                    "freeze_min_s": 2.0,
                }
            except Exception:
                _mq_cfg = None
        (_mq_checks, _mq_rounds, _mq_fixes, final, paths) = \
            await _correct_assembled(
                final, paths, results, out, chat, workdir, titles,
                _size,
                notify=notify, deadline=deadline, ref_voice=ref_voice,
                amendments=amendments, spec=spec, cfg=cfg, pool=pool,
                mq_cfg=_mq_cfg, size_explicit=_size_explicit)
        if report is not None:
            report["checks"] = [
                c for c in report["checks"]
                if not str(c.get("rule", "")).startswith("MQ-")
            ] + _mq_checks
            report["fix_rounds"] = int(report.get("fix_rounds") or 0) \
                + _mq_rounds
            report["fixes_applied"] = list(
                report.get("fixes_applied") or []) + _mq_fixes
            _failed85 = [c for c in report["checks"]
                         if c["status"] == "FAIL"]
            report["checks_failed"] = len(_failed85)
            report["passed"] = not _failed85 and not [
                v for v in (report.get("requirements") or [])
                if v["status"] == "FAIL"]
            try:
                with open(Path(workdir) / "compliance_report.json",
                          "w", encoding="utf-8") as _f:
                    json.dump(report, _f, indent=1)
            except OSError:
                pass
        try:
            duration = _probe_duration(final)
        except Exception:
            pass
        if _mq_rounds:
            summary += (f"; assembled-file QC corrections: "
                        f"{_mq_rounds} round(s)")
        _mq_left = [c for c in _mq_checks if c["status"] == "FAIL"]
        print(f"assembled media QC: {_mq_rounds} correction round(s), "
              f"{len(_mq_left)} defect(s) remaining")
    except Exception as e:
        print("assembled correction loop failed:", str(e)[:200])
    # ROUND 4 (fold-in): a film that ships with compliance FAILs
    # says so at DELIVERY level — in the summary the owner reads —
    # not only inside compliance_report.json. Film 3 shipped at
    # 19 FAILs after 3 correction rounds and the delivery line
    # never mentioned it.
    _comp_warn = ""
    if report is not None and int(report.get("checks_failed") or 0):
        _comp_warn = (
            f"⚠ compliance: {report['checks_failed']} check(s) "
            f"still FAIL after {int(report.get('fix_rounds') or 0)} "
            f"correction round(s) — shipped with known defects "
            f"(see compliance_report.json)")
        summary += "; " + _comp_warn
    # ROUND 5 (Fix 1): the director verdict and the taste-QC
    # verdict state at DELIVERY level. Film 3's editing director
    # fell back on both passes and its taste QC produced zero
    # verdicts (UNVERIFIED x12) — neither fact reached the
    # delivery line the owner reads.
    _dir_fb5 = [i + 1 for i, r in enumerate(results)
                if r.get("director_fallback_final")]
    if _dir_fb5:
        summary += (
            f"; ⚠ director: the brain director did NOT run for "
            f"chapter(s) {', '.join(map(str, _dir_fb5))} — the "
            f"deterministic fallback directed them (labelled "
            f"DIRECTOR-FALLBACK in the report)")
    _taste_unv5 = 0
    try:
        for _ch5 in (_taste87.get("chapters") or []):
            if _ch5.get("rounds"):
                _taste_unv5 += int(
                    (_ch5["rounds"][-1].get("counts") or {})
                    .get("UNVERIFIED") or 0)
    except Exception:
        pass
    if _taste87.get("vision") != "live" or _taste_unv5:
        summary += (
            f"; ⚠ taste QC: UNVERIFIED ({_taste_unv5} beat "
            f"verdict(s); vision {_taste87.get('vision')}) — "
            f"those beats shipped without a taste verdict")
    # v84 (Stage 5 / P3): Editing Director, LOG-ONLY. Reads the
    # chapter plans, writes director_log.json, changes NOTHING.
    _director_log = None
    try:
        import director as _dir84
        import doc_structure as _ds84
        _roles = _ds84.assign_arc(len(results))
        # v87: the arc follows the analyst's reading, not only the
        # arithmetic — a chapter whose script turns is the turning
        # point, wherever it sits.
        try:
            _roles, _arc_notes87 = _ds84.validate_arc_with_analyst(
                _roles, [(_r.get("plan") or {}).get("beat_sheet")
                         for _r in results])
            for _n87 in _arc_notes87:
                print("arc validation v87:", _n87)
        except Exception:
            pass
        _all_scenes = []
        for _ci, _r in enumerate(results):
            for _s in ((_r.get("plan") or {}).get("scenes") or []):
                _all_scenes.append({**_s, "arc_role": _roles[_ci]})
        _director_log = _dir84.analyse_plan(
            _all_scenes, job_id=str(Path(workdir).name))
        with open(Path(workdir) / "director_log.json", "w",
                  encoding="utf-8") as _f:
            json.dump(_director_log, _f, indent=1)
        print(f"director (log-only): "
              f"{len(_director_log['recommendations'])} recommendations")
    except Exception as e:
        print("director log failed:", str(e)[:150])
    # v86: aggregate the Director's VISUAL PLANS (decided inside
    # doc.plan, before rendering) across chapters: visual_plan.json +
    # VISUAL_PLAN.md in the workdir, and on the result dict.
    _visual_plan86 = []
    try:
        import director as _dir86b
        for _ci, _r in enumerate(results):
            for _rec in ((_r.get("plan") or {}).get("visual_plan") or []):
                _visual_plan86.append({**_rec, "chapter": _ci + 1})
        if _visual_plan86:
            with open(Path(workdir) / "visual_plan.json", "w",
                      encoding="utf-8") as _f:
                json.dump(_visual_plan86, _f, indent=1)
            with open(Path(workdir) / "VISUAL_PLAN.md", "w",
                      encoding="utf-8") as _f:
                _f.write(_dir86b.visual_plan_markdown(
                    _visual_plan86, title=out["title"]))
            print(f"director v86: visual plan — "
                  f"{len(_visual_plan86)} beats across "
                  f"{len(results)} chapter(s)")
        # v87: the Story Analyst's BEAT SHEETS ride with the delivery
        # (BEAT_SHEET.md + beat_sheet.json) — the readable structure
        # the whole brain planned from.
        import story_analyst as _sa87b
        _sheets87 = []
        _md87 = []
        for _ci, _r in enumerate(results):
            _sh = (_r.get("plan") or {}).get("beat_sheet")
            if _sh:
                _sheets87.append({**_sh, "chapter": _ci + 1})
                _md87.append(_sa87b.beat_sheet_markdown(
                    _sh, title=f"Chapter {_ci + 1}"))
        if _sheets87:
            with open(Path(workdir) / "beat_sheet.json", "w",
                      encoding="utf-8") as _f:
                json.dump(_sheets87, _f, indent=1)
            with open(Path(workdir) / "BEAT_SHEET.md", "w",
                      encoding="utf-8") as _f:
                _f.write("\n\n".join(_md87))
            print(f"story analyst v87: beat sheets for "
                  f"{len(_sheets87)} chapter(s)")
    except Exception as e:
        print("visual plan aggregation failed:", str(e)[:150])
    # v85: Director vs the ACTUAL render — the comparison the v84
    # design promised (recommendations counted against the defects
    # QC really found). Still log-only: nothing is mutated.
    if _director_log is not None and report is not None:
        try:
            import director as _dir85
            _director_log["render_comparison"] = \
                _dir85.compare_with_render(_director_log, report)
            with open(Path(workdir) / "director_log.json", "w",
                      encoding="utf-8") as _f:
                json.dump(_director_log, _f, indent=1)
        except Exception as e:
            print("director comparison failed:", str(e)[:120])
    # v85: editing memory writes for THIS real job + the learning
    # digest. Selections/rejections come from the footage pool, QC
    # failures and corrections from the final report. The digest
    # only PROPOSES rule changes — activation stays approval-gated
    # (learning_loop.activate refuses unapproved proposals).
    if _mem84 is not None:
        try:
            if pool is not None:
                for _a in pool.assignments:
                    _mem84.record_selection(
                        _job84, str(_a.get("scene", "")),
                        str(_a.get("clip_id", "")),
                        str(_a.get("query", "")),
                        detail={"provider": _a.get("provider"),
                                "verify": _a.get("verify")})
                for _r in pool.rejected:
                    _mem84.record_rejection(
                        _job84, str(_r.get("scene", "")),
                        str(_r.get("clip_id") or _r.get("id") or ""),
                        str(_r.get("query", "")),
                        str(_r.get("reason", ""))[:300])
            if report is not None:
                for _c in report.get("checks") or []:
                    if _c.get("status") == "FAIL":
                        _mem84.record_qc_failure(
                            _job84, str(_c.get("rule", "")),
                            str(_c.get("detail", ""))[:300],
                            str(_c.get("scene") or ""))
                for _fx in report.get("fixes_applied") or []:
                    _mem84.record_correction(_job84, "", str(_fx)[:200],
                                             "applied")
            _mem84.record_result(
                _job84,
                "partial" if partial else "delivered",
                detail={"duration_s": round(float(duration or 0), 1),
                        "chapters": f"{len(paths)}/{total_ch}",
                        "checks_failed": (report or {}).get(
                            "checks_failed")})
            import learning_loop as _ll85
            _digest = _ll85.build_digest(_mem84)
            with open(Path(workdir) / "learning_digest.json", "w",
                      encoding="utf-8") as _f:
                json.dump(_digest, _f, indent=1, default=str)
            print(f"edit memory: job {_job84} recorded; learning "
                  f"digest: {len(_digest.get('new_proposals') or [])} "
                  f"new proposal(s) (approval-gated)")
        except Exception as e:
            print("edit memory write failed:", str(e)[:150])
    # ROUND 4: film-level aggregates — the depiction mix over
    # every delivered beat, and every pass's fact-gate event, so
    # the QC surfaces exist on the delivery record itself.
    _dep_film = None
    _fg_film = []
    try:
        import depiction_qc as _dq4lv
        _dep_film = _dq4lv.depiction_report(
            [s for r in results
             for s in ((r.get("plan") or {}).get("scenes") or [])])
    except Exception:
        _dep_film = None
    for _ci, _r in enumerate(results):
        for _ev in (_r.get("fact_gate_passes") or []):
            _fg_film.append({"chapter": _ci + 1, **_ev})
    result = {"path": final, "title": out["title"], "duration": duration,
              "lang": first.get("lang", "te"),
              "caption": first.get("caption", ""),
              "topic": first.get("topic", brief),
              "plan": first.get("plan", {}),
              "broll": broll_sources, "summary": summary,
              "voice_note": voice_note,
              "amendments_applied": amend_applied,
              # v79: contract artifacts (FIX 1/5) for the runner upload.
              "spec": spec or [], "render_config": cfg or {},
              "compliance": report, "director": _director_log,
              "visual_plan": _visual_plan86,
              "taste_qc": _taste87,
              "workdir": str(workdir),
              "footage": pool.footage_json() if pool else {},
              # PROOF-FIX 1/2: brain ledger + achieved footage share.
              "brain_status": _brain_status_summary_lv(),
              # ROUND 5 (Fix 1): per-chapter director verdict +
              # the taste-QC UNVERIFIED count, on the result dict
              # next to the brain ledger — not only in logs.
              "director_fallback_chapters": _dir_fb5,
              "taste_unverified_beats": _taste_unv5,
              "footage_share": (round(_cov_sc / _tot_sc, 3)
                                if _tot_sc else 0.0),
              "partial": partial, "chapters_done": len(paths),
              "chapters_total": total_ch, "long": True,
              # ROUND 4: delivery-level compliance warning + the
              # film's depiction mix + per-pass fact-gate events.
              "compliance_warning": _comp_warn or None,
              "depiction": _dep_film,
              "fact_gate_passes": _fg_film}
    # v89: PACKAGING STEP (additive, delivery end) — 10 titles, 3
    # thumbnail concepts, a validated title<->thumbnail pair, the
    # description, 3 Shorts cut points and a debate-question first
    # comment, written to packaging.json and attached to the result.
    # Wrapped: a packaging failure NEVER changes delivery behaviour.
    try:
        import packaging as _pkg89
        _chs89, _t89 = [], 0.0
        for _i89, _ttl89 in enumerate(titles):
            try:
                _d89 = _probe_duration(paths[_i89])
            except Exception:
                _d89 = 60.0
            _chs89.append({"title": _ttl89, "start_s": _t89,
                           "end_s": _t89 + _d89})
            _t89 += _d89 + (CARD_SECONDS if _i89 < len(titles) - 1
                            else 0.0)
        _srcs89 = []
        for _r89 in results:
            for _s89 in ((_r89.get("plan") or {}).get("scenes") or []):
                if _s89.get("source"):
                    _srcs89.append(str(_s89["source"]))
        for _b89 in broll_sources:
            if isinstance(_b89, dict) and _b89.get("url"):
                _srcs89.append(str(_b89["url"]))
        # ROUND 4 (fold-in): packaging grades the DELIVERED film —
        # its topic is a real chapter topic or the delivered
        # title, never the raw order string. Film 3's pair check
        # graded 'Auto: What Nobody Tells You' × 'MYSTERY
        # REVEALED' because the topic passed in was the literal
        # brief word "Auto".
        _pkg_topic = ""
        for _r89 in results:
            _t89b = str((_r89.get("plan") or {}).get("topic")
                        or _r89.get("topic") or "").strip()
            if _t89b and _t89b.lower() != "auto":
                _pkg_topic = _t89b
                break
        if not _pkg_topic:
            _pkg_topic = out["title"]
        _pkg = _pkg89.build_packaging(
            _pkg_topic, out["title"], _chs89,
            sources=_srcs89,
            claims=[c["title"] for c in out["chapters"]][:3],
            duration=duration)
        result["packaging"] = _pkg
        with open(Path(workdir) / "packaging.json", "w",
                  encoding="utf-8") as _f:
            json.dump(_pkg, _f, indent=1)
        print(f"packaging v89: pair "
              f"{'PASS' if _pkg['pair_check']['passes'] else 'FLAGGED'} "
              f"— '{_pkg['chosen_pair']['title']}' x "
              f"'{_pkg['chosen_pair']['thumbnail_text']}'")
    except Exception as e:
        print("packaging v89 failed (delivery unchanged):",
              str(e)[:200])
    return result


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


def _title_card_image(number, title, out_png, size=(1920, 1080), bg_png=None):
    """Chapter title card at the video's own size. v79 (R8): plain
    navy cards were one of the compromise mistakes — the card now
    sits ON the chapter's own footage (a frame of the chapter,
    darkened) whenever one is available; solid navy is the fallback
    only. 'CHAPTER N' + the chapter title, sized to the frame."""
    from PIL import Image, ImageDraw
    W, H = size
    img = None
    if bg_png:
        try:
            src = Image.open(bg_png).convert("RGB")
            sc = max(W / src.width, H / src.height)
            src = src.resize((int(src.width * sc + 0.5), int(src.height * sc + 0.5)))
            x = (src.width - W) // 2
            y = (src.height - H) // 2
            img = src.crop((x, y, x + W, y + H))
            img = Image.blend(img, Image.new("RGB", (W, H), (4, 8, 18)), 0.55)
        except Exception:
            img = None
    if img is None:
        img = Image.new("RGB", (W, H), CARD_BG)
    d = ImageDraw.Draw(img)
    try:
        small = _load_font(max(24, int(H * 0.028)))
        big = _load_font(max(36, int(H * 0.057)))
        cx = W // 2
        d.rectangle([int(W * 0.083), int(H * 0.458), int(W * 0.917), int(H * 0.463)],
                    fill=CARD_ACCENT)
        label = f"CHAPTER {number}"
        d.text((cx, int(H * 0.417)), label, font=small, fill=CARD_ACCENT, anchor="mm")
        wrap_w = max(10, int(W / (big.size * 0.62)))
        lines = []
        for raw_line in str(title).split("\n"):
            lines.extend(textwrap.wrap(raw_line, width=wrap_w) or [""])
        lines = lines[:4]
        y = int(H * 0.5)
        for line in lines:
            d.text((cx, y), line, font=big, fill=(255, 255, 255), anchor="mm")
            y += int(H * 0.068)
    except Exception:
        img = Image.new("RGB", (W, H), (0, 0, 0))
    img.save(out_png)
    return out_png


def _make_card_clip(number, title, tmpdir, size=(1920, 1080), bg_from=None):
    """Render one title card as a 1.5 s mp4 with silent audio, matching
    the chapters' size (30 fps, 44100 Hz stereo) so the concat is
    clean. v79 (R8): with a chapter video to take a frame from, the
    card carries that footage WITH a slow push-in (motion), not a
    frozen still."""
    W, H = size
    bg_png = None
    if bg_from:
        cand = str(Path(tmpdir) / f"cardbg{number}.jpg")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                            "-ss", "2", "-i", str(bg_from),
                            "-frames:v", "1", cand],
                           capture_output=True)
        if r.returncode == 0 and os.path.exists(cand):
            bg_png = cand
    png = _title_card_image(number, title, str(Path(tmpdir) / f"card{number}.png"),
                            size=size, bg_png=bg_png)
    mp4 = str(Path(tmpdir) / f"card{number}.mp4")
    if bg_png:
        vf = (f"scale={W * 2}:{H * 2},zoompan=z='1+0.05*on/45':x='iw/2-(iw/zoom/2)'"
              f":y='ih/2-(ih/zoom/2)':d=45:s={W}x{H}:fps=30,format=yuv420p")
    else:
        vf = "format=yuv420p"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-loop", "1", "-t", str(CARD_SECONDS), "-i", png,
                    "-f", "lavfi", "-t", str(CARD_SECONDS),
                    "-i", "anullsrc=r=44100:cl=stereo",
                    "-vf", vf,
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
                        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json",
                        "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "")
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def assemble(parts, out_path, chapter_titles, size=None, card_bg_from=None,
             size_explicit=False):
    """Concatenate chapter mp4s with ffmpeg, inserting a 1.5 s title card
    before every chapter after the first, loudness-normalising the final
    audio (loudnorm I=-14, TP=-1.0, LRA=11 — dual-pass, so the target is
    actually hit), and writing chapters.txt ('MM:SS Chapter title' per
    chapter start) next to the output. Returns the output path (str).

    v79: `size` is the video's own frame size (from prompt_spec via
    the render config — 1920x1080 for long by R9). `card_bg_from` =
    the chapter mp4 paths, for footage-backed chapter cards (R8).

    v98 (portrait trap-door fix): the old no-`size` fallback was the
    historical 1080x1920 — and every long job that reached assemble
    without a size (any no-spec job: v87, v88, the Compromise video)
    silently shipped PORTRAIT. That fallback is gone: no size now
    resolves the LONG default, 1920x1080 landscape. A portrait size
    is honoured ONLY when `size_explicit` says it came from the
    user's own spec (an aspect_ratio requirement resolved by
    spec_engine); any other portrait size raises SpecImpossible —
    fail loudly, never silently portrait.
    """
    if size is None:
        size = (1920, 1080)
    W, H = int(size[0]), int(size[1])
    if H > W and not size_explicit:
        import spec_engine as _se
        raise _se.SpecImpossible(
            "", f"long-video assembly was handed a portrait size "
            f"{W}x{H} that did not come from an explicit user spec — "
            f"a long video is landscape unless the prompt itself "
            f"asks for portrait",
            "1920x1080 landscape, or a prompt that explicitly asks "
            "for portrait / 9:16 / a portrait size")
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
            bg = None
            if card_bg_from and i < len(card_bg_from):
                bg = card_bg_from[i]
            segs.append(_make_card_clip(i + 1, titles[i], td, size=(W, H),
                                        bg_from=bg))
            segs.append(parts[i])
        inputs, filt = [], []
        for j, seg in enumerate(segs):
            inputs += ["-i", seg]
            # v98: setsar=1 — scaling a chapter whose own size differs
            # from the assembly size (a portrait chapter into a
            # landscape long video, a re-rendered chapter at another
            # size) leaves a non-1 SAR on the scaled stream, and the
            # concat then refuses to join it with the title cards
            # (SAR mismatch). Normalising SAR per segment makes the
            # assembly size authoritative, whatever the chapters' own
            # sizes are.
            filt.append(f"[{j}:v]fps=30,scale={W}:{H},setsar=1,format=yuv420p[v{j}];")
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
            af = ("loudnorm=I=-14:TP=-1.0:LRA=11"
                  f":measured_I={p['measured_I']}:measured_TP={p['measured_TP']}"
                  f":measured_LRA={p['measured_LRA']}"
                  f":measured_thresh={p['measured_thresh']}"
                  f":offset={p['offset']}:linear={p['linear']}")
        else:  # measurement failed: fall back to single-pass loudnorm
            af = "loudnorm=I=-14:TP=-1.0:LRA=11"
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
