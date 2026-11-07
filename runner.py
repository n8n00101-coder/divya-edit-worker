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

asyncio.run(main())
