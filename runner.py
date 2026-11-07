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
    import doc as create
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
        await wa.send_media(to, res["path"], "video", caption=f"🎬 {res['title']} ({int(res['duration'])}s, {res['lang']})\n\n{res.get('caption','')[:300]}")
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
