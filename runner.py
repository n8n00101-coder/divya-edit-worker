"""GitHub Actions edit runner for Divya. Gets job + creds from the Cloudflare Worker, edits, sends back on WhatsApp.
Never prints secrets (they are masked too)."""
import asyncio, json, os, sys, httpx

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
        res = await autoedit.auto_edit(src, j["instruction"], notify=note)
        size = os.path.getsize(res["path"]) / 1e6
        if size > 15.5:
            out = res["path"].replace(".mp4", "_wa.mp4")
            p = await asyncio.create_subprocess_exec("ffmpeg", "-y", "-i", res["path"], "-c:v", "libx264", "-b:v", "1800k",
                                                     "-c:a", "aac", "-b:a", "96k", out, stdout=asyncio.subprocess.DEVNULL,
                                                     stderr=asyncio.subprocess.DEVNULL)
            await p.wait(); res["path"] = out
        qa = "QA ✅" if res["review"].get("ok") else "QA note: " + "; ".join(res["review"].get("issues", [])[:2])
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
        res = await autoedit.auto_edit(src, j["instruction"], notify=note)
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
        await wa.send_media(to, res["path"], "video", caption=f"🎬 {res['title']} ({int(res['duration'])}s, {res['lang']})\n\n{res.get('caption','')[:300]}{qcline}")
        try:
            httpx.post(f"{WORKER}/done", json={"to": to, "topic": res["topic"]}, headers={"x-runner-key": KEY}, timeout=20)
        except Exception:
            pass
    except Exception as e:
        await wa.send_text(to, f"⚠️ Video create lo problem vachindi: {str(e)[:250]}. Malli try chestha, leda topic marchi adugu.")
        raise


def subprocess_run(cmd):
    import subprocess
    subprocess.run(cmd, check=True)


asyncio.run(main())
