"""GitHub Actions edit runner for Divya. Gets job + creds from the Cloudflare Worker, edits, sends back on WhatsApp.
Never prints secrets (they are masked too)."""
import asyncio, json, os, re, sys, httpx

WORKER = os.environ["WORKER_URL"].rstrip("/")
KEY = os.environ["RUNNER_KEY"]
JOB = sys.argv[1]


def load_job():
    r = httpx.post(f"{WORKER}/job", json={"job": JOB}, headers={"x-runner-key": KEY}, timeout=30)
    r.raise_for_status()
    j = r.json()
    for k in ("WA_TOKEN", "GROQ_KEY"):
        for v in str(j.get(k, "")).split(","):
            if v.strip():
                print(f"::add-mask::{v.strip()}")
    os.environ["WA_TOKEN"] = j["WA_TOKEN"]
    os.environ["WA_PHONE_ID"] = j["PHONE_ID"]
    os.environ["GROQ_KEY"] = j["GROQ_KEY"]
    os.environ.setdefault("DATA_DIR", "/tmp/divya")
    os.makedirs(os.environ["DATA_DIR"], exist_ok=True)
    return j


async def main():
    j = load_job()
    import whatsapp as wa, autoedit  # import after env is set (config reads env)
    to = j["to"]
    note = lambda t: wa.send_text(to, t)
    if j.get("mode") == "create":
        return await create_job(j, wa, note)
    if j.get("app"):
        return await app_edit_job(j, wa)
    try:
        src = await wa.download_media(j["media_id"], "mp4")
        res = await autoedit.auto_edit(src, j["instruction"] + EDIT_PIPELINE + HARK_PIPELINE + HARK_LONG_PIPELINE + HARK_PROCESS + THEORY, notify=note)
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
        except Exception as e:
            print("result upload failed", str(e)[:200])
        await wa.send_media(to, res["path"], "video", caption=f"✨ Edit ready! {res['summary'][:300]}\n{qa}")
    except Exception as e:
        await wa.send_text(to, f"⚠️ Edit fail ayyindi: {str(e)[:300]}. Instruction konchem marchi malli try cheyyandi.")
        raise

def app_state(state, note=""):
    try:
        httpx.post(f"{WORKER}/api/runner/state", params={"job": JOB}, json={"state": state, "note": note[:300]},
                   headers={"x-runner-key": KEY}, timeout=20)
    except Exception as e:
        print("state post failed", type(e).__name__)


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


# R37: Hark's long-video method (16:9, 8-15 min documentaries). Use for LONG
# videos; Hark short method rules 9:16 shorts; Tab 8-step stays as the base.
# Source: ~/workspace/styles/HARK-LONG-METHOD.md (given by Hark, 2026-11-09).
HARK_LONG_PIPELINE = (
    " Hark long method (16:9 long videos, 8-15 min): format 1920x1080, 30fps;"
    " structure Hook (0:00-0:30) -> Intro promise -> 4-6 chapters -> Twist -> Summary -> CTA;"
    " something changes on screen every 20-40s."
    " 1) Topic+angle — 5 surprising but provable angles (one-line hook, core question, why watch till the end); pick one with a clear question."
    " 2) Research — every fact/number/date with exact claim + official source + year + exact wording; mark unsure as UNVERIFIED;"
    " sources sheet: claim | source | link | year | exact wording. Open every source yourself."
    " 3) Outline — hook 30s, 5 chapters (one question + one proof + one visual each), twist, summary, CTA, timestamps."
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
        instruction = j["instruction"] + f" Style template: {tpl} (see video-kit/render.py TEMPLATES)." + EDIT_PIPELINE + HARK_PIPELINE + HARK_LONG_PIPELINE + HARK_PROCESS + THEORY
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


def groq_chat(messages):
    last = ""
    for k in [x.strip() for x in os.environ["GROQ_KEY"].split(",") if x.strip()]:
        for m in CHAT_MODELS:
            body = {"model": m, "messages": messages, "temperature": 0.8, "max_tokens": 2500}
            if m.startswith("openai/gpt-oss"):
                body["reasoning_effort"] = "low"
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                           headers={"Authorization": f"Bearer {k}"}, timeout=90)
            if r.status_code == 200:
                out = r.json()["choices"][0]["message"]["content"] or ""
                if out.strip():
                    return out
            last = f"{m} {r.status_code}"
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


async def create_job(j, wa, note):
    import create as _engines
    create = _engines.engine_module()  # DIVYA_ENGINE=v3 -> doc3, default doc (v2)
    to = j["to"]
    try:
        res = None
        for attempt in range(2):
            try:
                res = await create.make_video(j.get("brief", ""), groq_chat, notify=note, recent=j.get("recent", ""))
                break
            except (ValueError, KeyError) as e:  # bad plan JSON -> retry once
                if attempt:
                    raise
        size = os.path.getsize(res["path"]) / 1e6
        print("video", res["path"], round(size, 2), "MB", res.get("duration"))
        if size > 15.5:
            out = res["path"].replace(".mp4", "_wa2.mp4")
            subprocess_run(["ffmpeg", "-y", "-loglevel", "error", "-i", res["path"], "-b:v", "1900k", "-maxrate", "2000k", "-bufsize", "4000k", "-c:a", "aac", "-b:a", "128k", out])
            res["path"] = out
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
        try:
            up = fit_size(res["path"], 23)
            rr = httpx.post(f"{WORKER}/api/runner/result", params={"job": JOB, "note": f"{res.get('summary', '')[:200]}"[:290]}, content=open(up, "rb").read(), headers={"x-runner-key": KEY, "content-type": "video/mp4"}, timeout=300)
            print("result upload", rr.status_code)
        except Exception as e:
            print("result upload failed", str(e)[:200])
        await wa.send_media(to, res["path"], "video", caption=f"🎬 {res['title']} ({int(res['duration'])}s, {res['lang']})\n\n{caption}{qcline}")
        try:
            httpx.post(f"{WORKER}/done", json={"to": to, "topic": res["topic"], "job": JOB}, headers={"x-runner-key": KEY}, timeout=20)
        except Exception:
            pass
    except Exception as e:
        await wa.send_text(to, f"⚠️ Video create lo problem vachindi: {str(e)[:250]}. Malli try chestha, leda topic marchi adugu.")
        raise


def subprocess_run(cmd):
    import subprocess
    subprocess.run(cmd, check=True)


asyncio.run(main())
