"""Engine v3 test harness for GitHub Actions. Fetches ONLY the brief + Groq creds from the Worker (/job), never touches
WhatsApp, renders with doc3 and leaves everything in ./out for the artifact. Never prints secrets (masked)."""
import asyncio, json, os, sys, httpx

WORKER = os.environ["WORKER_URL"].rstrip("/")
r = httpx.post(f"{WORKER}/job", json={"job": sys.argv[1]}, headers={"x-runner-key": os.environ["RUNNER_KEY"]}, timeout=30)
r.raise_for_status()
j = r.json()
for k in ("WA_TOKEN", "GROQ_KEY", "GEMINI_KEY"):
    for v in str(j.get(k) or "").split(","):
        if v.strip():
            print(f"::add-mask::{v.strip()}")
os.environ["GROQ_KEY"] = j["GROQ_KEY"]
if j.get("GEMINI_KEY"):
    os.environ["GEMINI_KEY"] = j["GEMINI_KEY"]
j.pop("WA_TOKEN", None)
print("gemini key present:", bool(os.environ.get("GEMINI_KEY")), "| groq keys:", len([x for x in j["GROQ_KEY"].split(",") if x.strip()]))
import doc3
secs = int(os.environ.get("SECONDS_TARGET", "60"))
res = asyncio.run(doc3.make_video(j.get("brief", "AUTO"), None, workdir=os.path.abspath("out"), seconds=secs, lang=j.get("lang", "en")))
print(json.dumps({k: res[k] for k in ("path", "title", "duration", "lang")}, default=str))
print("QC pass:", res["qc"].get("pass"), "| weak:", res["qc"].get("weak"))
