"""GitHub Actions edit runner for Divya. Gets job + creds from the Cloudflare Worker, edits, sends back on WhatsApp.
Never prints secrets (they are masked too)."""
import asyncio, json, os, re, sys, time, httpx

WORKER = os.environ["WORKER_URL"].rstrip("/")
KEY = os.environ["RUNNER_KEY"]
JOB = sys.argv[1]


def load_job():
    r = httpx.post(f"{WORKER}/job", json={"job": JOB}, headers={"x-runner-key": KEY}, timeout=30)
    r.raise_for_status()
    j = r.json()
    for k in ("WA_TOKEN", "GROQ_KEY", "PEXELS_KEY", "PIXABAY_KEY"):
        for v in str(j.get(k, "")).split(","):
            if v.strip():
                print(f"::add-mask::{v.strip()}")
    os.environ["WA_TOKEN"] = j["WA_TOKEN"]
    os.environ["WA_PHONE_ID"] = j["PHONE_ID"]
    os.environ["GROQ_KEY"] = j["GROQ_KEY"]
    # v69: stock B-roll keys (doc.py/broll.py). Optional — the Worker only
    # sends them when the secrets exist; absent/empty keeps today's
    # code-drawn-only behaviour.
    for k in ("PEXELS_KEY", "PIXABAY_KEY"):
        if j.get(k):
            os.environ[k] = str(j[k])
    os.environ.setdefault("DATA_DIR", "/tmp/divya")
    os.makedirs(os.environ["DATA_DIR"], exist_ok=True)
    return j


async def main():
    j = load_job()
    # v75: guaranteed terminal reporting. A job used to be able to die
    # with a traceback the Worker never heard about — both long-video
    # deaths (runs 43355930702, 43373013930) sat at "editing" until
    # the v73 rescue noticed. Now ANY exit path out of the job
    # (exception, SystemExit, a crash inside a chapter) posts
    # runner/state=failed first, which also triggers the Worker's
    # v73 token refund. At most once per process: branch handlers
    # post their own specific failure note first (see _FAILED_POSTED).
    try:
        return await _run_job(j)
    except BaseException as e:
        # v78: app_state itself stays silent when the result was already
        # delivered (delivered is terminal — see _RESULT_DELIVERED).
        if not _FAILED_POSTED:
            app_state("failed", f"Job fail ayyindi: {str(e)[:250]}")
        raise


async def edit_create_job(j, wa, note):
    """v79 (FIX 4): an EDIT of the user's last video — load its saved
    project (runner/artifacts), change ONLY what was asked, re-render
    from the saved plan, deliver like a create. The original video's
    History entry is untouched; this job gets its own."""
    import doc as _doc
    to = j["to"]
    proj_job = str(j.get("project_job") or "")
    pr = httpx.get(f"{WORKER}/api/runner/artifacts",
                   params={"job": proj_job, "name": "project.json"},
                   headers={"x-runner-key": KEY}, timeout=60)
    if pr.status_code != 200:
        msg = ("Edit cheyalenu — original video project dorakaledu "
               "(project save avvaledu leda expire ayyindi).")
        app_state("failed", msg)
        try:
            await wa.send_text(to, "⚠️ " + msg)
        except Exception:
            pass
        return
    try:
        project = json.loads(pr.text)
    except Exception:
        app_state("failed", "Edit cheyalenu — project file corrupt.")
        return
    wd = os.path.join(os.environ.get("DATA_DIR", "/tmp/divya"), f"edit_{JOB}")
    res = await _doc.apply_project_edit(
        project, str(j.get("user_prompt") or j.get("brief") or ""),
        groq_chat, workdir=wd, notify=note)
    print("edit video", res["path"], res.get("duration"),
          "changed scenes:", (res.get("edit") or {}).get("changed_scenes"))
    caption = str(res.get("caption", ""))[:300]
    _ed = res.get("edit") or {}
    qcline = ""
    if _ed.get("notes"):
        qcline += "\n✏️ Changes: " + "; ".join(_ed["notes"][:4])
    if res.get("compliance"):
        try:
            import compliance as _comp_mod
            qcline += "\n" + _comp_mod.done_not_done_line(res["compliance"])
        except Exception:
            pass
    try:
        up = fit_size(res["path"], 23)
        _note = (res.get("summary") or "Edit of video " + proj_job)[:290]
        rr = httpx.post(f"{WORKER}/api/runner/result",
                        params={"job": JOB, "note": _note},
                        content=open(up, "rb").read(),
                        headers={"x-runner-key": KEY,
                                 "content-type": "video/mp4"}, timeout=300)
        print("edit result upload", rr.status_code)
        if rr.status_code == 200:
            mark_result_delivered()  # v78: delivered is terminal
            upload_artifacts(res.get("workdir"))
    except Exception as e:
        print("edit result upload failed", str(e)[:200])
    try:
        size = os.path.getsize(res["path"]) / 1e6
        wa_path = fit_size(res["path"], 15) if size > 15.5 else res["path"]
        await wa.send_media(to, wa_path, "video",
                            caption=f"🎬 {res['title']} (edited)\n\n{caption}{qcline}")
    except Exception as e:
        print("wa send_media failed (post-result, non-fatal):", str(e)[:200])


async def _run_job(j):
    import whatsapp as wa, autoedit  # import after env is set (config reads env)
    to = j["to"]
    note = lambda t: wa.send_text(to, t)
    if j.get("mode") == "edit_create":
        return await edit_create_job(j, wa, note)
    if j.get("mode") == "create":
        return await create_job(j, wa, note)
    if j.get("app"):
        return await app_edit_job(j, wa)
    try:
        src = await wa.download_media(j["media_id"], "mp4")
        res = await autoedit.auto_edit(src, j["instruction"] + EDIT_PIPELINE + HARK_PIPELINE + HARK_LONG_PIPELINE + HARK_PROCESS + THEORY + HARK_BEHAVIOUR + HARK_AESTHETIC + HARK_NEAT + HARK_DIRECTOR, notify=note)
        size = os.path.getsize(res["path"]) / 1e6
        if size > 15.5:
            out = res["path"].replace(".mp4", "_wa.mp4")
            p = await asyncio.create_subprocess_exec("ffmpeg", "-y", "-i", res["path"], "-c:v", "libx264", "-b:v", "1800k",
                                                     "-c:a", "aac", "-b:a", "96k", out, stdout=asyncio.subprocess.DEVNULL,
                                                     stderr=asyncio.subprocess.DEVNULL)
            await p.wait(); res["path"] = out
        qa = "QA ✅" if res["review"].get("ok") else "QA note: " + "; ".join(res["review"].get("issues", [])[:2])
        try:
            up = fit_size(res["path"], 23)
            rr = httpx.post(f"{WORKER}/api/runner/result", params={"job": JOB, "note": f"{res.get('summary', '')[:200]}"[:290]}, content=open(up, "rb").read(), headers={"x-runner-key": KEY, "content-type": "video/mp4"}, timeout=300)
            print("result upload", rr.status_code)
            if rr.status_code == 200:
                mark_result_delivered()  # v78: delivered is terminal
        except Exception as e:
            print("result upload failed", str(e)[:200])
        # v78: the WhatsApp copy is best-effort once the result is in —
        # a WA failure (e.g. 413 on a long video) must never fail a
        # delivered job.
        try:
            await wa.send_media(to, res["path"], "video", caption=f"✨ Edit ready! {res['summary'][:300]}\n{qa}")
        except Exception as e:
            print("wa send_media failed (post-result, non-fatal):", str(e)[:200])
    except Exception as e:
        await wa.send_text(to, f"⚠️ Edit fail ayyindi: {str(e)[:300]}. Instruction konchem marchi malli try cheyyandi.")
        raise

_STAGE_PCT = (("script ready", 35), ("codegen", 20), ("voice ready", 55), ("rendering", 80), ("download", 15), ("edit plan", 35), ("voice", 45), ("render", 75), ("export", 90), ("upload", 95), ("plan", 30))
def _pct_for(state, note):
    # v67 (Ajju): live progress % in the app — mapped from the REAL stage
    # the runner reports, never invented. Unknown stage -> None (the app
    # keeps the last real %). Done is always 100.
    if state == "done": return 100
    if state != "running": return None
    t = (note or "").lower()
    for k, v in _STAGE_PCT:
        if k in t: return v
    return None

_FAILED_POSTED = False  # v75: main()'s reporting guarantee fires at most once
# v78: set the moment a result post lands (HTTP 200 from /api/runner/result).
# A delivered video is TERMINAL: job 7aee5d2a (2026-11-13) rendered all 7
# chapters and its result uploaded fine, then the WhatsApp send_media of
# the 108 MB file threw HTTP 413, create_job's except posted
# state=failed, and the Worker flipped the delivered History entry to
# failed AND refunded the full 1.4M charge for a downloadable video.
# After delivery, failures are local log lines — never state posts.
_RESULT_DELIVERED = False


def mark_result_delivered():
    global _RESULT_DELIVERED
    _RESULT_DELIVERED = True


def app_state(state, note=""):
    global _FAILED_POSTED
    if state == "failed" and _RESULT_DELIVERED:
        print("app_state: failure AFTER result delivery — job stays done, "
              f"not reporting failed ({note[:150]})")
        return
    if state == "failed":
        _FAILED_POSTED = True
    try:
        httpx.post(f"{WORKER}/api/runner/state", params={"job": JOB}, json={"state": state, "note": note[:300], "pct": _pct_for(state, note)},
                   headers={"x-runner-key": KEY}, timeout=20)
    except Exception as e:
        print("state post failed", type(e).__name__)


def upload_artifacts(wd):
    """v79 (FIX 1/4/5): upload the video's contract artifacts —
    prompt_spec.json, footage.json, compliance_report.json and the
    saved project.json — to the Worker (runner/artifacts route), so
    they are retrievable with the result and Blind can review from
    them. Best-effort per file; a missing file is skipped, never
    fatal (delivery already happened)."""
    if not wd:
        return
    for name in ("prompt_spec.json", "footage.json",
                 "compliance_report.json", "project.json"):
        p = os.path.join(str(wd), name)
        try:
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as f:
                content = f.read()
            r = httpx.post(f"{WORKER}/api/runner/artifacts",
                           params={"job": JOB},
                           json={"name": name, "content": content},
                           headers={"x-runner-key": KEY}, timeout=60)
            print("artifact upload", name, r.status_code)
        except Exception as e:
            print("artifact upload failed", name, str(e)[:120])


def fetch_source(j) -> str:
    """App edit source: an upload kept by the Worker, or a link (Google Drive / YouTube / direct URL)."""
    import re, subprocess
    d = os.environ["DATA_DIR"]; out = os.path.join(d, f"in_{JOB}.mp4")
    if j.get("src") == "upload":
        r = httpx.get(f"{WORKER}/api/runner/src", params={"job": JOB}, headers={"x-runner-key": KEY}, timeout=120)
        r.raise_for_status(); open(out, "wb").write(r.content); return out
    url = j["video_url"]
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?(?:export=download&)?id=)([\w-]{20,})", url)
    if m:
        url = f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"
    if re.search(r"(youtube\.com|youtu\.be|instagram\.com|facebook\.com|fb\.watch|x\.com|twitter\.com|vimeo\.com)/", url):
        p = subprocess.run(["yt-dlp", "-q", "--no-playlist", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
                            "--max-filesize", "1500M", "-o", out, url], capture_output=True, text=True, timeout=1200)
        if p.returncode != 0 or not os.path.exists(out):
            raise RuntimeError("Link nunchi video download avvaledu (private/blocked kavachu). Public link leda direct file link ivvandi. " + p.stderr.strip()[-160:])
        return out
    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as r:
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "text/html" in ct:
            raise RuntimeError("Aa link video file kaadu (web page vachindi). Drive lo 'Anyone with the link' share cheyyandi, leda direct .mp4 link ivvandi.")
        n = 0
        with open(out, "wb") as f:
            for ch in r.iter_bytes(1 << 20):
                n += len(ch)
                if n > 1500 * 1024 * 1024:
                    raise RuntimeError("Video 1.5 GB kante pedda ga undi.")
                f.write(ch)
    return out


def fit_size(path, limit_mb):
    """Re-encode so the file is under limit_mb (keeps resolution up to 1080p)."""
    import subprocess, json as _j
    if os.path.getsize(path) / 1e6 <= limit_mb:
        return path
    dur = float(_j.loads(subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True).stdout)["format"]["duration"])
    kbps = max(250, int(limit_mb * 8000 * 0.92 / max(dur, 1)) - 96)
    out = path.replace(".mp4", f"_{int(limit_mb)}mb.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", "scale='min(1080,iw)':-2", "-c:v", "libx264", "-preset", "veryfast",
                    "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps*1.2)}k", "-bufsize", f"{kbps*2}k", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out], check=True)
    return out


# R26: Tab's 8-step editing method as a checklist, applied to every edit job
# instruction (app edits + WhatsApp edits). R36 (2026-11-09): Hark's own short
# method is NOW documented (~/workspace/styles/HARK-SHORT-METHOD.md, given by
# Hark himself) and wired in as HARK_PIPELINE below — per-topic sources,
# per-topic effects/transitions/mood, 7 checks + not-ready rule, work order.
# Tab 8-step stays for documentaries/long; Hark's method rules 9:16 shorts.
EDIT_PIPELINE = (
    " Edit pipeline (Tab 8-step method, apply in order):"
    " 1) Script+facts first — check every number/name/date, drop unverified claims."
    " 2) Structure — cold-open hook in the first 10-15s, chapters with title cards, end on a question."
    " 3) Voice — one consistent narrator, per-sentence placement, captions in sync."
    " 4) Captions — karaoke style, current word highlighted, bottom third, match the voice word for word."
    " 5) Footage — change shot every 3-6s, hold longer only on a number that must land."
    " 6) Music by section — tense pulse for the hook, somber for tragedy, low drone for science, reflective piano for the ending; duck ~20 dB under the voice."
    " 7) Mix — final loudness about -14 LUFS, true peak -1.5 dB."
    " 8) Check before sending — watch/grab frames: no empty boxes, no cut-off captions, no static slide over ~5s, no unplanned silence or clipping."
)


# R36: Hark's short-video method (9:16 shorts). Classify the topic type FIRST,
# then pick sources/effects/transitions/mood FROM THE TABLES for that type —
# never one fixed style. Source: ~/workspace/styles/HARK-SHORT-METHOD.md.
HARK_PIPELINE = (
    " Hark short method (9:16 shorts, use alongside Tab 8-step):"
    " 1) Classify the topic type FIRST, then use its sources — Health: MoHFW/NTCP/ICMR/WHO India (backup Sansad/Lancet/PubMed);"
    " Laws: India Code/Gazette/FSSAI/CCPA (backup PIB/court orders); Money: RBI/FinMin/Budget/GST Council (backup NSO/IMF/World Bank);"
    " Population: Census/NFHS-5/NSSO/GATS (backup UN/World Bank); Psychology: peer-reviewed PubMed/APA;"
    " History: original paper/book/archive; Tech: company blog/docs/paper; News: PIB/Reuters/PTI/The Hindu."
    " Every number on screen gets a source line bottom-left; self-done math is shown as math."
    " 2) Pick effects from the table for the topic — RGB glitch: shocking facts/scams (hook + twist);"
    " stamp slam + shake: bans/verdicts/CTA; number counter: deaths/money/users/stats;"
    " typewriter + yellow marker: laws/rules/quotes; dot grid/people icons: '1 in 4';"
    " donut/bar/growth curve: percentages/comparison; stopwatch/calendar/clock: time facts;"
    " map draw + red fill: country/state/bans; pop-in icons: lists; strike-through: myth-busting;"
    " slow push-in zoom: every scene; blur: 'Or is it?' doubt moments."
    " Transitions — zoom-blur: calm/explainer; glitch cut: shocking/serious before a twist;"
    " hard cut: fast news; fade to black: end only."
    " Mood — serious: darker red/blue tint + slower voice; motivation: warmer tint + steady pace; news: faster cuts."
    " 3) Seven checks before sending — (1) fact: every number has an official source, wording matches exactly;"
    " (2) script: hook in first 2s, one idea per scene, 5-10 words per line, clear CTA;"
    " (3) legal/safety: no unproven claim about a person/brand, no medical advice beyond official guidance, no copyrighted music/clips;"
    " (4) visual: preview sheet, no clipped/overlapping text, readable contrast, inside 9:16 safe area;"
    " (5) caption: captions match voice word for word, numbers as digits (3,500), highlight on the right word;"
    " (6) audio: voice clear over music, SFX on the right beat, -14 LUFS, no clipping;"
    " (7) export: 1080x1920, 30fps, H.264 + AAC, duration correct, play once end to end."
    " NOT READY if: a fact has no source, any text is clipped, voice and captions are out of sync, or the hook is weak."
    " 4) Work order: topic -> angle/hook -> sources -> script -> fact check -> voice + word timings ->"
    " scene design (effects from table) -> animate -> transitions + SFX + music -> preview sheet -> fixes -> export -> final watch."
)


# R37: Hark's long-video method (16:9 documentaries). Use for LONG
# videos; Hark short method rules 9:16 shorts; Tab 8-step stays as the base.
# Source: ~/workspace/styles/HARK-LONG-METHOD.md (given by Hark, 2026-11-09).
# v67 (Ajju): long limit raised to 60 min — chapters scale with length.
HARK_LONG_PIPELINE = (
    " Hark long method (16:9 long videos, up to 60 min): format 1920x1080, 30fps;"
    " structure Hook (0:00-0:30) -> Intro promise -> chapters (about 1 chapter per 5 minutes: 8 min = 2-3 chapters, 30 min = 6, 60 min = 10-12) -> Twist -> Summary -> CTA;"
    " something changes on screen every 20-40s."
    " 1) Topic+angle — 5 surprising but provable angles (one-line hook, core question, why watch till the end); pick one with a clear question."
    " 2) Research — every fact/number/date with exact claim + official source + year + exact wording; mark unsure as UNVERIFIED;"
    " sources sheet: claim | source | link | year | exact wording. Open every source yourself."
    " 3) Outline — hook 30s, chapters scaled to the target length (one question + one proof + one visual each), twist, summary, CTA, timestamps."
    " 4) Script — short spoken sentences (max 15 words), one idea per line, numbers as digits, every fact followed by [SOURCE: name],"
    " [VISUAL: ...] under each line; 140-150 words = 1 minute. No claims outside the sources sheet."
    " 5) Fact check pass — script line by line against the sources sheet; rewrite any line whose number/wording/year/meaning differs."
    " 6) Scene plan — scene table: no | VO line | duration | headline | graphic type (counter, map, chart, document, icons, B-roll, stamp, quote card) | effect | transition | SFX | source line."
    " Long extras: chapter title cards (big number + title, 2s), lower-thirds, picture-in-picture, Ken Burns on photos, split screen for comparisons, progress bar/chapter tracker at top."
    " 7) Voiceover — edge-tts (en-IN-PrabhatNeural / hi-IN-MadhurNeural / te-IN-MohanNeural) or own mic, chapter by chapter, word timings;"
    " clean: noise reduce, cut breaths and gaps over 0.6s, -14 LUFS."
    " 8) Visuals — same Pillow + ffmpeg pipeline at 1920x1080; one design system (Anton headlines, Montserrat body, yellow highlight, bg texture, brand mark top-left);"
    " B-roll Pexels/Pixabay (check licence); pattern break every 2-3 min (zoom punch, color shift, question to viewer)."
    " 9) Captions — 1-2 lines bottom, 6-8 words per line, current word highlighted; SRT upload too (faster-whisper, hand-fixed)."
    " 10) Music — one calm bed per chapter (YouTube Audio Library/Pixabay), -25 dB under voice, change at chapters/twist;"
    " SFX: whoosh on transitions, hit on big numbers, typing on documents, riser before the twist."
    " 11) Review — 8 checks: fact (numbers match sources sheet), script (hook 30s, chapters answer their questions, no dead air over 1s),"
    " legal/safety (licences OK for music/B-roll), visual (no clipped text, safe margins, no frame unchanged over 40s),"
    " captions (match voice, numbers as digits, in sync), audio (voice clear, music ducked, -14 LUFS),"
    " retention (re-watch first 60s; if slow, cut it), export (resolution, duration, plays end to end)."
    " 12) Export + upload pack — ffmpeg libx264 veryfast crf 20 AAC 192k +faststart; thumbnail 1280x720, title,"
    " description with sources + chapter timestamps, tags, SRT; upload pack: 3 titles (under 60 chars), description, 15 tags, 3 thumbnail texts (max 4 words)."
    " NOT READY if: any fact without a source, any clipped text, voice/caption out of sync, a boring first 30 seconds, or music/B-roll without a licence."
)


# R39: Hark's editing process as he explained it (2026-11-10,
# ~/workspace/styles/HARK-EDITING-PROCESS.md). The thinking is the language
# model; visuals are drawn pixel by pixel in code — no AI video/image
# generator. Applies to BOTH shorts and longs, alongside Tab 8-step,
# Hark short and Hark long methods.
HARK_PROCESS = (
    " Hark editing process (use for every video, shorts and longs):"
    " 1) Topic — surprising + relatable + provable with ONE fact."
    " 2) Script — hook (2s) -> setup -> 2-3 reveals -> twist -> follow; one line = one scene (2-4s)."
    " 3) Meaning -> visual, by rule — percentage: dot grid / donut ring; number: count-up + icons;"
    " feeling: stick figure + shake / glow; compare: side by side; shock / twist: quick zoom + red colour + pop sound;"
    " new topic: slide transition + whoosh; calm fact: slow push-in only."
    " 4) Fixed grid — headline top 25%, visual middle 50%, captions bottom 20%, sides 60px gap;"
    " timing comes from TTS word timings, so the word, its icon and its pop land on the same frame; nothing overlaps because every item has a fixed box."
    " 5) Animation is math — ease-in-out (smooth), ease-out-back (small bounce pop), slow 3% zoom-in so no scene is static,"
    " slide/whip transitions; ONE effect at a time."
    " 6) Effects + SFX from code — shapes, glow, grain, icons drawn in code; whoosh/pop synthesised from noise + frequency;"
    " nothing downloaded, no copyright issues."
    " 7) Music by mood — mystery/psychology: low dark pad; facts: light beat; voice -14 LUFS, music ducked under voice."
    " 8) Self-check — render, then check one frame per scene (overflow, overlap, contrast, duration, loudness);"
    " re-render ONLY the bad scene. Honest limit: no vision here — automated checks only (black/blank frames, loudness, export specs)."
    " NOT better than humans — faster at rules only; taste, trend feel and emotion still belong to a good human editor."
)


THEORY = (
    " Theory — books/tutorials/documentary practice, distilled as rules (follow like Hark):"
    " DESIGN: contrast first, one focal point per scene; hierarchy headline > visual > caption;"
    " max 2 fonts (Anton headlines, Montserrat body); colour = mood — red shock/urgent, dark blue serious,"
    " yellow highlight/energy, warm motivation; 60px side gap, nothing touches the edge; text centred on its ink;"
    " consistency IS the aesthetic — same grid, fonts, caption bar, source line, logo in every scene."
    " EDITING: one idea = one scene (2-4s); hook in first 2s; cut on the spoken word/beat; change shot every 3-6s,"
    " never static >5s; ONE effect at a time, every motion has a reason — zoom = emphasis, slide = new topic,"
    " push-in = calm, glitch = shock; if an effect adds no meaning, remove it; motion on every cut;"
    " video must make sense with sound off."
    " TIMING/SOUND: word timing drives everything — icon/number/effect lands on the word; voice -14 LUFS constant,"
    " music ducked ~20 dB under voice, rises in pauses; silence before a heavy line; SFX on every visual change;"
    " score by section/mood — tense pulse hook, somber strings tragedy, low drone science, reflective piano ending;"
    " no drums/upbeat under heavy narration."
    " DOCUMENTARY: script first, facts first — every number/name/date checked against the PRIMARY source;"
    " claims marked correct/wrong/outdated/unverifiable/legally risky, fix or cut; new fact + source chip every 20-30s;"
    " structure: cold-open hook (contradiction/shocking real number, first 10-15s) -> chapters with title cards -> end on a question;"
    " ask questions, never make claims; simple English; actual month/year, never 'last month';"
    " manual edits only, NO AI clips; real stock + code-drawn charts, every chart labelled with source; blur private faces;"
    " women faceless/clothed/blurred, never sexualised; karaoke captions word-for-word with voice;"
    " check before sending — frames at many points, no empty boxes, no cut-off captions, voice == captions, levels even."
    " TASTE: the viewer should remember the idea, not the effect. When in doubt, remove."
)


# R51 (v27): Hark's creative-director prompt (from Blind's kit,
# ~/workspace/hark-kit/DIVYA_PIPELINE_v26.md — the exact method/code that produced
# the phantom-vibration video). The LLM must think fresh per topic, never fill a template.
HARK_DIRECTOR = (
    " Creative-director rules (Hark's kit): You are a short-video editor. You never fill"
    " a template. For every topic you think fresh: (1) Find the surprising angle and a"
    " hook under 8 words. (2) Write one sentence per scene. For each sentence choose ONE"
    " word that deserves an effect: a number first, then the topic noun, then a contrast"
    " word. No other word gets an effect. (3) Choose a visual that shows the literal"
    " meaning of that sentence. Never use a mascot or the same character across scenes."
    " (4) Choose a style from the topic's mood, different from your last 5 videos."
    " Transitions must use an object from the topic. (5) Less is neat: one idea per"
    " scene, two accent colors, one font pair, nothing on screen the voice does not"
    " mention. (6) After render, look at the frames like a strict human editor. If"
    " anything is cut at the edge, overlapping, busy, late, or off-topic, fix it before"
    " you send."
)


# R50 (v26): neat edits — Ajju's verdict on v25 (2026-11-10): the videos show no
# change, nothing creative, and do not look like edits at all. The pawn, the zoom,
# and generic untimed effects are the defects. Hark was asked the same questions
# (thread 1a1c64a60e80fbe6); these rules are the fix until his reply arrives.
HARK_NEAT = (
    " Hark neat-edit rules (use for every video): NEVER a fixed mascot/character in"
    " every scene — the pawn/chess-soldier is REMOVED; every visual must be the"
    " topic's own idea, never a stock mascot. Camera moves are SUBTLE — max 3% zoom,"
    " small drift; nothing may leave the safe area or go outside the screen; the"
    " background must not visibly zoom. Effects are TOPIC-RELATED and VOICE-TIMED:"
    " the icon/effect/label pops on the exact spoken keyword (from the TTS word"
    " timings), never at a fixed scene time; a different effect per scene, never the"
    " same animation in every video. An edit must look neat and careful — if it looks"
    " like 'someone asked, so I made something', it is not ready."
)


HARK_AESTHETIC = (
    " Hark aesthetic variety (use for every video): the TOPIC MOOD picks the design system,"
    " then vary inside it (accent, font pair, transition set) from a seed of the title so no"
    " two videos match. Never pick fresh at random, never a template. Keep constant only:"
    " 9:16 safe margins, big readable captions, one idea per scene, one accent colour at a time."
    " FOUR LOOKS — A Science/Explainer: deep navy to teal gradient, cyan/amber accent, thin line"
    " diagrams, animated plots, clean sans (lightning, physics, how-things-work)."
    " B Myth/Debate/Safety: high-contrast black and white, one hot red or yellow accent, huge bold"
    " condensed type, hard cuts, stamp/strike-through (myths, warnings, versus)."
    " C Story/Culture/Cinema: warm film grain, soft vignette, serif/elegant type, slow push-ins,"
    " cream/orange/teal grade, minimal text (movies, history, emotion)."
    " D Tech/Money/Data: light or dark glassy UI, neon green/violet accent, big animated numbers,"
    " bar/line charts, grid backgrounds, snappy easing (stats, AI, finance)."
    " NEVER use the same look as the previous video on the channel. Chapter cards vary:"
    " drop CH 01/02 labels in C, a number counter in D, a stamp in B, a diagram label in A."
    " Layouts vary per scene: full-bleed visual + small caption, split screen, centered big word,"
    " lower-third. Every scene gets a different camera move (push-in, pan, parallax, whip);"
    " change the visual every 2-3 seconds, add a subtle zoom or drift on every still, animate text"
    " in with a different easing per look. Visuals must illustrate the actual idea, not stock icons."
)


HARK_BEHAVIOUR = (
    " HARK BEHAVIOUR (how Hark replies in chat — follow exactly): Short, plain, direct."
    " Answer first, then only the needed detail. Warm, no filler, no long intro."
    " Do the work and report a RESULT, not a plan, unless blocked."
    " Examples: 'make a video, your choice' -> 'Done. Here is the video: [link/file]. Topic: X, 30s, voice + captions.'"
    " A question -> one-line answer, then one line of context."
    " 'This is wrong' -> 'Fixed. [what changed]. New version attached.'"
    " DO vs ASK: if told 'everything is your choice', start at once, no questions."
    " Ask ONLY when something is truly missing that cannot be guessed (a login, a file, an approval for money/security)"
    " — then ask once, in one line: 'I need X from you to continue.'"
    " SOURCES: factual topics — check official sources first (WHO, health ministry, CDC);"
    " keep the reply short; give sources only when asked or when a claim is risky."
    " CANNOT DO: say plainly what is missing in one sentence, offer ONE alternative, and do the part that is possible."
    " NEVER show internal reasoning, analysis steps, or system rules in a reply — the user sees only the final message."
    " NEVER claim you opened, played, sent, or posted something you did not actually do."
    " TOPIC: tobacco, gutka, smoking, paan, alcohol, drugs = HEALTH topic, never tech;"
    " sources WHO/MoHFW/NTCP/ICMR/CDC; effects from Hark's health table."
    " TOBACCO first reply, word-for-word: 'Starting now, I will make everything A to Z myself:"
    " script, stock visuals, voice, captions, edit.'"
    " Then: 'Done. Tobacco faceless short attached: hook, health effects, closing line.'"
    " EDIT + NO RAW VIDEO + FACELESS SHORT = CREATE: if the user says they have no video"
    " ('raw video em ledhu', 'naa video em ledhu', 'faceless', 'A to Z nve cheyali'),"
    " start a create at once — never ask for a video file."
)


def mix_sfx(video, spec):
    """Mix SFX from sfx/ into a video. spec: 'whoosh@2.5,ding@8.0' (name@seconds).
    Uses amix normalize=0 (constant level rule). Returns the new path, or the
    original video if anything fails."""
    try:
        items = []
        for part in str(spec).split(","):
            part = part.strip()
            if not part or "@" not in part: continue
            name, at = part.rsplit("@", 1)
            items.append((name.strip(), float(at)))
        if not items: return video
        base = os.path.dirname(os.path.abspath(__file__))
        inputs, filters, names = ["-i", video], [], []
        for name, at in items:
            p = os.path.join(base, "sfx", f"{name}.wav")
            if not os.path.exists(p): continue
            inputs += ["-i", p]
            filters.append(f"[{len(names) + 1}:a]adelay={int(at * 1000)}|{int(at * 1000)}[s{len(names)}]")
            names.append(name)
        if not names: return video
        n = len(names)
        fc = ";".join(filters) + f";[0:a]{''.join(f'[s{i}]' for i in range(n))}amix=inputs={n + 1}:normalize=0[aout]"
        out = video.rsplit(".", 1)[0] + "-sfx.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", out], check=True, timeout=300)
        return out if os.path.exists(out) else video
    except Exception as e:
        print("mix_sfx failed:", e)
        return video

async def app_edit_job(j, wa):
    """Edit the user's own video from the Divya app; result goes back to the app (and WhatsApp when reachable)."""
    import autoedit
    to, use_wa = j["to"], bool(j.get("wa"))
    async def note(t):
        app_state("running", t)
        if use_wa:
            try: await wa.send_text(to, t)
            except Exception: pass
    try:
        app_state("running", "Video download chestunna…")
        src = fetch_source(j)
        print("source", round(os.path.getsize(src) / 1e6, 1), "MB")
        app_state("running", "Edit plan chestunna…")
        tpl = str(j.get("template") or "dark-explainer")
        instruction = j["instruction"] + f" Style template: {tpl} (see video-kit/render.py TEMPLATES)." + EDIT_PIPELINE + HARK_PIPELINE + HARK_LONG_PIPELINE + HARK_PROCESS + THEORY + HARK_BEHAVIOUR + HARK_AESTHETIC + HARK_NEAT + HARK_DIRECTOR
        res = await autoedit.auto_edit(src, instruction, notify=note)
        if j.get("sfx"):
            res["path"] = mix_sfx(res["path"], str(j["sfx"]))
        qa = "QA ✅" if res["review"].get("ok") else "QA note: " + "; ".join(res["review"].get("issues", [])[:2])
        app_path = fit_size(res["path"], 23)
        r = httpx.post(f"{WORKER}/api/runner/result", params={"job": JOB, "note": f"{res['summary'][:200]} {qa}"[:290]},
                       content=open(app_path, "rb").read(), headers={"x-runner-key": KEY, "content-type": "video/mp4"}, timeout=300)
        print("result upload", r.status_code, round(os.path.getsize(app_path) / 1e6, 1), "MB")
        if r.status_code != 200:
            raise RuntimeError(f"result upload {r.status_code}")
        if use_wa:
            await wa.send_media(to, fit_size(res["path"], 15.5), "video", caption=f"✨ Edit ready! {res['summary'][:300]}\n{qa}")
    except Exception as e:
        app_state("failed", f"Edit fail ayyindi: {str(e)[:250]}")
        raise


CHAT_MODELS = ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905", "openai/gpt-oss-20b"]


_CHAT_BACKOFF_S = (5, 15, 45)


def _chat_sweep(messages):
    """One pass over every key x model (the historical behaviour).
    Returns (text, last, transient): text is None when the sweep
    failed; transient says whether at least one failure was retryable
    (HTTP 429 / 5xx, a transport error, or an empty reply)."""
    last = ""
    transient = False
    for k in [x.strip() for x in os.environ["GROQ_KEY"].split(",") if x.strip()]:
        for m in CHAT_MODELS:
            body = {"model": m, "messages": messages, "temperature": 0.8, "max_tokens": 2500}
            if m.startswith("openai/gpt-oss"):
                body["reasoning_effort"] = "low"
            try:
                r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                               headers={"Authorization": f"Bearer {k}"}, timeout=90)
            except httpx.HTTPError as e:
                last = f"{m} network {type(e).__name__}"
                transient = True
                continue
            if r.status_code == 200:
                out = r.json()["choices"][0]["message"]["content"] or ""
                if out.strip():
                    return out, last, transient
                last = f"{m} empty"
                transient = True
                continue
            last = f"{m} {r.status_code}"
            if r.status_code == 429 or r.status_code >= 500:
                transient = True
    return None, last, transient


def groq_chat(messages):
    # v75: retry transient failures with backoff (5s/15s/45s, 3
    # retries) before raising. Run 43355930702 died in chapter 1's
    # plan() on a single Groq 429 — a rate limit must never kill a
    # job outright. Non-transient failures (e.g. every model 400s)
    # raise immediately, exactly as before.
    last = ""
    for attempt in range(len(_CHAT_BACKOFF_S) + 1):
        out, last, transient = _chat_sweep(messages)
        if out is not None:
            return out
        if not transient or attempt == len(_CHAT_BACKOFF_S):
            break
        print(f"groq_chat: transient LLM failure ({last}) — "
              f"retry {attempt + 1} in {_CHAT_BACKOFF_S[attempt]}s")
        time.sleep(_CHAT_BACKOFF_S[attempt])
    raise RuntimeError("LLM failed: " + last)


def analysis_gate(path, facts=None):
    """Pre-send analysis gate (correct analysis): content check + fact check.
    Returns (ok, flaws, dropped_facts). Critical flaw -> do NOT send.
    Minor flaws -> send with an honest flaw list. Never claims pass when unsure."""
    import subprocess as _sp
    flaws, dropped = [], []
    try:
        size = os.path.getsize(path)
    except OSError:
        return False, ["video file kanipinchaledu"], []
    if size < 10000:
        return False, ["video file chala chinna ga undi (corrupt?)"], []
    try:
        probe = json.loads(_sp.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path], capture_output=True, text=True, timeout=60).stdout or "{}")
        dur = float(probe.get("format", {}).get("duration") or 0)
        if dur <= 0:
            return False, ["video duration 0 (render fail?)"], []
        if not any(s.get("codec_type") == "audio" for s in probe.get("streams", [])):
            flaws.append("audio track ledu")
        # R36 Hark export check: 1080x1920, 30fps, 9:16 (flaw, not blocking).
        _vs = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
        if _vs:
            _w, _h = _vs.get("width"), _vs.get("height")
            if _w != 1080 or _h != 1920:
                flaws.append(f"resolution {_w}x{_h} — 1080x1920 kavali (Hark export check)")
            try:
                _num, _den = (str(_vs.get("r_frame_rate") or "30/1")).split("/")
                _fps = float(_num) / float(_den)
                if abs(_fps - 30) > 1:
                    flaws.append(f"fps {_fps:.1f} — 30fps kavali (Hark export check)")
            except Exception:
                pass
    except Exception as e:
        flaws.append(f"probe cheyalekapoya: {type(e).__name__}")
    # R39 Hark self-check, automated subset (no vision — never claim to have
    # watched frames): sample 8 frames across the video as 1x1 mean brightness
    # + blackdetect. Flags blank renders / black sections as flaws (not blocking).
    try:
        _dur = locals().get("dur") or 0
        if _dur > 0:
            _raw = _sp.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps=8/{max(_dur, 1):.2f},scale=1:1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, timeout=120).stdout or b""
            _vals = list(_raw[:8])
            if len(_vals) >= 4:
                _dark = sum(1 for v in _vals if v < 8)
                _bright = sum(1 for v in _vals if v > 247)
                if _dark >= max(4, len(_vals) - 2):
                    flaws.append("chala frames nalla/black ga unnayi (blank render?)")
                elif _bright >= max(4, len(_vals) - 2):
                    flaws.append("chala frames thella/white ga unnayi (blank render?)")
            _bd = _sp.run(["ffmpeg", "-v", "info", "-i", path, "-vf", "blackdetect=d=0.5:pix_th=0.10", "-f", "null", "-"], capture_output=True, text=True, timeout=120).stderr or ""
            _bt = sum(float(x) for x in re.findall(r"black_duration:\s*([\d.]+)", _bd))
            if _bt >= 1.0:
                flaws.append(f"black sections {_bt:.1f}s (blank parts?)")
    except Exception as e:
        flaws.append(f"frame check cheyalekapoya: {type(e).__name__}")
    try:
        vd = _sp.run(["ffmpeg", "-i", path, "-af", "volumedetect", "-vn", "-sn", "-dn", "-f", "null", "-"], capture_output=True, text=True, timeout=120).stderr or ""
        m = re.search(r"mean_volume:\s*(-?[\d.]+)", vd)
        if m:
            mean = float(m.group(1))
            if mean < -45:
                flaws.append(f"audio chala silent ga undi (mean {mean} dB)")
            elif mean > -3:
                flaws.append(f"audio clipping risk (mean {mean} dB)")
        else:
            flaws.append("audio level measure cheyalekapoya")
    except Exception as e:
        flaws.append(f"audio check fail: {type(e).__name__}")
    # R36 Hark not-ready rule: a fact VERIFIED FALSE (Groq answered "no") means
    # the video is NOT ready — fail the gate. A check that errored out is only a
    # minor flaw (send with the honest flaw list), never a silent pass.
    _critical = []
    for f in (facts or []):
        try:
            ans = groq_chat([{"role": "system", "content": "Answer ONLY yes or no."}, {"role": "user", "content": f"Is this true as of 2026? {f}"}])
            if not str(ans).strip().lower().startswith("yes"):
                dropped.append(f)
                _critical.append(f)
        except Exception:
            flaws.append(f"fact check cheyalekapoya: {str(f)[:80]}")
    if dropped:
        flaws.append(f"{len(dropped)} fact(s) verify avvaledu — caption nunchi teesesa")
    if _critical:
        return False, flaws + ["Hark not-ready: fact ki source ledu / fact thappu"], dropped
    return True, flaws, dropped


def parse_requested_seconds(brief):
    """v69: the length the owner actually asked for, in seconds (None =
    no length stated -> the short engine's default). The Worker's
    'FINAL VIDEO LENGTH: exactly ...' line (startCreate) is authoritative
    and wins first; then explicit hour/minute/second phrasing in the
    brief; a bare 'long'/'documentary' means the 5-minute long-form
    default. Capped at 3600 (1 hour — Ajju's order). 'up to N min'
    (the brain's menu phrasing) is NOT an owner-stated length."""
    b = brief or ""
    m = re.search(r"FINAL VIDEO LENGTH:\s*exactly\s*(\d+)\s*minutes", b, re.I)
    if m:
        return min(int(m.group(1)) * 60, 3600)
    m = re.search(r"FINAL VIDEO LENGTH:\s*exactly\s*(\d+)\s*seconds", b, re.I)
    if m:
        return int(m.group(1))
    if re.search(r"\bone\s+hour\b", b, re.I):
        return 3600
    m = re.search(r"(?<!up to )\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b", b, re.I)
    if m:
        return min(int(float(m.group(1)) * 3600), 3600)
    m = re.search(r"(?<!up to )\b(\d+)\s*(?:minutes?|mins?|mints?)\b", b, re.I)
    if m:
        return min(int(m.group(1)) * 60, 3600)
    m = re.search(r"\b(\d+)\s*seconds\b", b, re.I)
    if m:
        return int(m.group(1))
    if re.search(r"\b(?:long|documentary)\b", b, re.I):
        return 300
    return None


class Amendments:
    """v72: mid-flight production amendments for THIS job. The Worker
    stores them on the job record (amend:<job>) when the user sends a
    production instruction while the video renders; the engines poll
    at their checkpoints (doc: script/footage/audio/assembly; long:
    before each chapter) and mark what they applied, with the stage.
    fetch() always re-reads the record, so the delivery report below
    also catches amendments that arrived after the last checkpoint —
    those are reported as missed, never silently moved to a "next
    video" the user did not order."""

    def __init__(self):
        self.seen = {}

    def fetch(self):
        try:
            r = httpx.get(f"{WORKER}/api/runner/amendments", params={"job": JOB},
                          headers={"x-runner-key": KEY}, timeout=20)
            if r.status_code == 200:
                for it in (r.json().get("amendments") or []):
                    self.seen[it["id"]] = it
            else:
                print("amendments fetch:", r.status_code)
        except Exception as e:
            print("amendments fetch failed", str(e)[:120])
        return [self.seen[k] for k in sorted(self.seen)]

    def pending(self):
        return [it for it in self.fetch() if not it.get("stage")]

    def mark(self, ids, stage):
        ids = [int(i) for i in ids]
        if not ids:
            return
        for i in ids:
            if i in self.seen:
                self.seen[i]["stage"] = stage
        try:
            httpx.post(f"{WORKER}/api/runner/amendments", params={"job": JOB},
                       json={"ids": ids, "stage": stage},
                       headers={"x-runner-key": KEY}, timeout=20)
        except Exception as e:
            print("amendments mark failed", str(e)[:120])


async def create_job(j, wa, note):
    import create as _engines
    create = _engines.engine_module()  # DIVYA_ENGINE=v3 -> doc3, default doc (v2)
    to = j["to"]
    # v72: mid-flight amendments provider for this job (see Amendments).
    amend = Amendments()
    # v71: the owner's saved reference voice (flagged in the job by the
    # Worker). Bytes come from the job-scoped runner route; the dict is
    # passed ONLY to engines that take it (doc.py, via synth_voice) —
    # mirrors the recent_styles capability pattern below.
    _ref = None
    _rv = j.get("refvoice") or {}
    if _rv.get("present"):
        try:
            _rr = httpx.get(f"{WORKER}/api/runner/refvoice", params={"job": JOB},
                            headers={"x-runner-key": KEY}, timeout=60)
            if _rr.status_code == 200 and len(_rr.content) > 1000:
                _rp = os.path.join(os.environ["DATA_DIR"], f"ref_voice_{JOB}.audio")
                open(_rp, "wb").write(_rr.content)
                _ref = {"path": _rp, "wpm": _rv.get("wpm") or 0, "lang": _rv.get("lang") or ""}
                print("refvoice: downloaded", len(_rr.content), "bytes, wpm", _ref["wpm"], "lang", _ref["lang"])
            else:
                print("refvoice: route answered", _rr.status_code, "— continuing without it")
        except Exception as e:
            print("refvoice download failed:", str(e)[:150])
    # v79 (FIX 1/2/6 + R-P1..R-P7): the user's prompt is a CONTRACT.
    # Extract prompt_spec from the user's EXACT words (the Worker
    # stores them on the job as user_prompt; the brief is the
    # fallback), resolve the render config from the spec, and check
    # every requirement against the capability list BEFORE rendering.
    # An impossible requirement fails the job HERE with the one-line
    # upfront message — never a silent substitution, never a render
    # first and an apology after (mail 2b, point 5).
    _spec, _cfg = [], None
    _target_s = parse_requested_seconds(j.get("brief", ""))
    _kind = "long" if (_target_s is not None and _target_s > 90) else "short"
    if getattr(create, "__name__", "") == "doc":
        try:
            import spec_engine as _se
            import broll as _broll_mod
            _src_text = str(j.get("user_prompt") or j.get("brief") or "")
            _spec = _se.extract_spec(_src_text, chat=groq_chat)
            _problems = _se.capability_check(
                _spec, _kind,
                footage_available=_broll_mod.FootagePool().available())
            if not _problems:
                try:
                    _cfg = _se.resolve_render_config(_spec, _kind)
                except _se.SpecImpossible as _e:
                    _problems = [{"id": _e.req_id, "reason": _e.reason,
                                  "alternative": _e.alternative}]
            if _problems:
                _line = _se.upfront_line(_problems)
                print("v79 upfront stop:", _line)
                app_state("failed", _line)
                try:
                    await wa.send_text(to, _line)
                except Exception:
                    pass
                return
            print(f"v79 spec: {len(_spec)} requirements, cfg "
                  f"{_cfg['width']}x{_cfg['height']} music={_cfg['music']} "
                  f"lang={_cfg['lang']}")
        except Exception as e:
            # The spec machinery itself must never kill a job it
            # cannot read — but a failure HERE is logged loudly, and
            # extraction problems (capability_check) above already
            # returned. A crash in extraction = no spec = old path.
            print("v79 spec extraction failed (continuing without spec):",
                  str(e)[:200])
            _spec, _cfg = [], None
    try:
        res = None
        # v69 FIX (Ajju 2026-11-13): WhatsApp creates only ever made ~1-min
        # videos — create_job always called the SHORT engine (doc.py,
        # default 50-60 s) and long_video.py was never routed to, while
        # the Worker charged for up to 60 min. Now: a requested length
        # over ~90 s goes to the chaptered long pipeline (long_video.
        # make_long_video, totals up to 60 min). Short orders keep the
        # exact old path. The long pipeline renders via doc.make_video,
        # so it only applies when the live engine is doc (v2).
        if _target_s is not None and _target_s > 90 \
                and getattr(create, "__name__", "") == "doc":
            import time as _time
            import long_video
            _target_min = max(2, int(round(_target_s / 60)))
            _budget = int(os.environ.get("DIVYA_LONG_BUDGET_S", "3000") or 3000)
            print(f"long route: target {_target_min} min, budget {_budget}s")
            res = await long_video.make_long_video(
                j.get("brief", ""), groq_chat,
                workdir=os.path.join(os.environ.get("DATA_DIR", "/tmp/divya"),
                                     f"long_{JOB}"),
                target_minutes=_target_min, notify=note,
                deadline=_time.monotonic() + _budget,
                ref_voice=_ref, amendments=amend,
                # spec/cfg ride only when a real contract exists —
                # the codebase's conditional-kwargs pattern (cf.
                # ref_voice/amendments): an empty spec is no contract,
                # and engine-shaped callers keep their old signature.
                **({"spec": _spec, "cfg": _cfg} if _spec else {}))
            print("long video", res["path"], res.get("duration"),
                  "partial" if res.get("partial") else "complete")
        else:
            for attempt in range(2):
                try:
                    # v28: the last 5 looks (from KV, via the job) so the look never
                    # repeats — only the v2 engine (doc.py, pick_look) takes it.
                    kw = {"recent": j.get("recent", "")}
                    if hasattr(create, "pick_look"):
                        kw["recent_styles"] = j.get("recent_styles") or []
                    if _ref is not None and hasattr(create, "synth_voice"):
                        kw["ref_voice"] = _ref
                    if getattr(create, "AMENDMENTS", False):
                        kw["amendments"] = amend
                    # v79: the contract (spec + resolved config) rides
                    # into the engine — every step renders FROM it.
                    # Only when the spec is non-empty (see the long
                    # call): an empty spec is no contract.
                    if _cfg is not None and _spec:
                        kw["spec"] = _spec
                        kw["cfg"] = _cfg
                    res = await create.make_video(j.get("brief", ""), groq_chat, notify=note, **kw)
                    print("look", res.get("plan", {}).get("look"), res.get("plan", {}).get("accent"))
                    break
                except (ValueError, KeyError) as e:  # bad plan JSON -> retry once
                    if attempt:
                        raise
        size = os.path.getsize(res["path"]) / 1e6
        print("video", res["path"], round(size, 2), "MB", res.get("duration"))
        # v24 duration backstop: the brief's hard length was ignored (video 5 =
        # 44.46s for a 30s request). Trim to the target so the delivered video
        # is never longer than asked (±2s).
        try:
            _bm = re.search(r"FINAL VIDEO LENGTH:\s*exactly\s*(\d+)\s*seconds", j.get("brief", "") or "")
            _target = int(_bm.group(1)) if _bm else None
        except Exception:
            _target = None
        if _target and float(res.get("duration") or 0) > _target + 2:
            _trim = res["path"].replace(".mp4", "_trim.mp4")
            subprocess_run(["ffmpeg", "-y", "-loglevel", "error", "-i", res["path"], "-t", str(_target), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-b:a", "128k", _trim])
            res["path"] = _trim
            res["duration"] = _target
            size = os.path.getsize(res["path"]) / 1e6
            print("trimmed to", _target, "s")
        # v78: no pre-emptive WhatsApp re-encode here any more. The old
        # fixed-1900k _wa2 swap produced ~109 MB for a 460 s video (the
        # bitrate never accounted for duration), so the WA send was
        # guaranteed to 413 — and it silently became the result-upload
        # source too. The result below uploads from the ORIGINAL file;
        # the WA copy is duration-fitted (fit_size) after delivery.
        qc = res.get("qc") or {}
        qcline = "" if not qc else ("\nQC ✅" if qc.get("pass") else "\nQC weak: " + "; ".join(qc.get("weak", [])[:3])[:250])
        gate_ok, gate_flaws, dropped = analysis_gate(res["path"], res.get("facts"))
        if not gate_ok:
            await wa.send_text(to, f"⚠️ Video analysis lo problem: {'; '.join(gate_flaws)[:250]}. Malli try chestha.")
            raise RuntimeError("analysis gate failed: " + "; ".join(gate_flaws))
        caption = res.get("caption", "")[:300]
        for f in dropped:
            caption = caption.replace(f, "").strip()
        if gate_flaws:
            qcline += "\nFlaws: " + "; ".join(gate_flaws)[:250]
        # v69: honest long-video + B-roll notes on the delivery caption.
        if res.get("partial"):
            qcline += f"\n⚠️ Long video partial: {res.get('chapters_done')}/{res.get('chapters_total')} chapters (job time limit) — longest completed version pampincha."
        _broll_used = res.get("broll") or []
        if _broll_used:
            qcline += f"\n🎞️ B-roll: {len(_broll_used)} stock footage clips ({', '.join(sorted({s.get('provider', '') for s in _broll_used}))})"
        # v71: honest voice line — what was actually used (never "clone").
        if res.get("voice_note"):
            qcline += f"\n🎙️ Voice: {res['voice_note']}"
        # v72: the amendment book, read back from the job record —
        # applied (with the stage that consumed each) vs missed (they
        # arrived after the last checkpoint that could use them). A
        # missed amendment is said plainly + a redo is offered; it is
        # NEVER quietly promised into a "next video".
        _am_all = amend.fetch()
        _am_applied = [it for it in _am_all if it.get("stage")]
        _am_missed = [it for it in _am_all if not it.get("stage")]
        _am_note = ""
        if _am_applied:
            _am_note = "Amendments applied: " + "; ".join(f"{it['text'][:40]} [{it['stage']}]" for it in _am_applied[:4])
            qcline += "\n✅ Add chesina changes: " + "; ".join(f"{it['text'][:50]} ({it['stage']})" for it in _am_applied[:4])
        if _am_missed:
            _am_note = (_am_note + " Amendments missed: " + "; ".join(it["text"][:40] for it in _am_missed[:3])).strip()
            qcline += "\n⚠️ Ee changes ee video ki time ki andaledhu: " + "; ".join(it["text"][:50] for it in _am_missed[:3]) + " — ivvi kavali ante \"cancel chesi malli chey\" ani cheppu; nene ee video ni aa changes tho malli chestha."
        # v79 (R-P7): every delivery carries the compliance
        # done / not-done line — what was asked, what was done, what
        # could not be done and why. No silent substitutions, ever.
        if res.get("compliance"):
            try:
                import compliance as _comp_mod
                qcline += "\n" + _comp_mod.done_not_done_line(res["compliance"])
            except Exception as e:
                print("done/not-done line failed:", str(e)[:120])
        try:
            up = fit_size(res["path"], 23)
            # v28: report the chosen style (look + motion + transition) so the
            # Worker stores it in KV (styles:<user>) for the next video's no-repeat.
            _pl = res.get("plan", {}) or {}
            # v69: the result note carries the B-roll licence trail
            # (provider page URLs) when the summary doesn't already.
            _note = (res.get("summary") or "")[:200]
            if _broll_used and "B-roll" not in _note:
                _note = (_note + " B-roll sources: " + ", ".join(s.get("source_url", "") for s in _broll_used[:3]))[:290]
            if _am_note:
                _note = (_note + " " + _am_note)[:290]
            rr = httpx.post(f"{WORKER}/api/runner/result", params={"job": JOB, "note": _note,
                            "look": str(_pl.get("look", "")), "motion": str(_pl.get("motion_personality", "")),
                            "transition": str(_pl.get("transition_family", ""))}, content=open(up, "rb").read(), headers={"x-runner-key": KEY, "content-type": "video/mp4"}, timeout=300)
            print("result upload", rr.status_code)
            if rr.status_code == 200:
                mark_result_delivered()  # v78: delivered is terminal
                # v79: the contract artifacts travel with the result.
                upload_artifacts(res.get("workdir"))
        except Exception as e:
            print("result upload failed", str(e)[:200])
        # v78: WhatsApp delivery is best-effort AFTER the app result —
        # job 7aee5d2a died exactly here (send_media HTTP 413 on the
        # 108 MB file) and took the delivered job down with it. Fit a
        # ≤15 MB copy for WA (duration-aware bitrate) and never raise.
        try:
            wa_path = fit_size(res["path"], 15) if size > 15.5 else res["path"]
            await wa.send_media(to, wa_path, "video", caption=f"🎬 {res['title']} ({int(res['duration'])}s, {res['lang']})\n\n{caption}{qcline}")
        except Exception as e:
            print("wa send_media failed (post-result, non-fatal):", str(e)[:200])
        try:
            httpx.post(f"{WORKER}/done", json={"to": to, "topic": res["topic"], "job": JOB}, headers={"x-runner-key": KEY}, timeout=20)
        except Exception:
            pass
    except Exception as e:
        # v78: an error AFTER the result was delivered changes nothing —
        # the video is in the app, the charge stands, the job is done.
        # Log locally and finish cleanly (no failed post, no alarming
        # WA text, no non-zero exit for a delivered job).
        if _RESULT_DELIVERED:
            print("create_job: error after result delivery (ignored):",
                  str(e)[:250])
            return
        # v75: report the failure to the Worker (refund + honest job
        # state), not only to WhatsApp — this except used to be the
        # silent-death path: WA got a text, the Worker heard nothing.
        app_state("failed", f"Video create fail ayyindi: {str(e)[:250]}")
        await wa.send_text(to, f"⚠️ Video create lo problem vachindi: {str(e)[:250]}. Malli try chestha, leda topic marchi adugu.")
        raise


def subprocess_run(cmd):
    import subprocess
    subprocess.run(cmd, check=True)


asyncio.run(main())
