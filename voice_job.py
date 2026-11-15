#!/usr/bin/env python3
"""Julie house-voice job runner (v50, V4).

Runs on GitHub Actions (voice.yml) on the same rails as setup.py:
the Worker stored a vjob (text + lang) and dispatched this workflow with
the job id. This script:
  1. fetches the job text from the Worker (x-runner-key auth),
  2. synthesizes it with the LOCKED julie-ai-voice-engine — cloned by the
     workflow into ./engine — via its own CLI (engine.py --text --lang
     --out), settings.json exactly as shipped in that repo (zero changes),
  3. posts the finished mp3 back to the Worker as base64.

Any failure is reported to the Worker (voice/runner/fail) so the app can
tell the user honestly — a different voice is NEVER substituted.
"""
import base64
import os
import subprocess
import sys

import httpx

WORKER = os.environ["WORKER_URL"].rstrip("/")
KEY = os.environ["RUNNER_KEY"]
JOB = os.environ["JOB"]
H = {"x-runner-key": KEY}
ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine")


def fail(msg):
    try:
        httpx.post(f"{WORKER}/api/voice/runner/fail", params={"job": JOB},
                   headers=H, json={"error": str(msg)[:120]}, timeout=20)
    except Exception:
        pass
    print("FAILED:", msg, flush=True)
    sys.exit(1)


def main():
    r = httpx.get(f"{WORKER}/api/voice/runner/job", params={"job": JOB},
                  headers=H, timeout=30)
    if r.status_code != 200:
        fail(f"job fetch {r.status_code}")
    spec = r.json()
    text = str(spec.get("text") or "").strip()
    lang = str(spec.get("lang") or "en")
    if lang not in ("en", "te", "hi"):
        lang = "en"
    if not text:
        fail("empty text")
    out = os.path.join(ENGINE, "out.mp3")
    print(f"synthesizing {len(text)} chars, lang={lang}", flush=True)
    proc = subprocess.run(
        [sys.executable, "engine.py", "--text", text, "--lang", lang,
         "--out", out],
        cwd=ENGINE, capture_output=True, text=True, timeout=3000)
    print(proc.stdout[-3000:], flush=True)
    if proc.returncode != 0 or not os.path.exists(out):
        print(proc.stderr[-3000:], flush=True)
        fail(f"engine exit {proc.returncode}")
    with open(out, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    print(f"posting {len(b64)} b64 chars", flush=True)
    r = httpx.post(f"{WORKER}/api/voice/runner/result", params={"job": JOB},
                   headers=H, json={"audio_b64": b64}, timeout=120)
    if r.status_code != 200:
        fail(f"result post {r.status_code}")
    print("done", flush=True)


if __name__ == "__main__":
    main()
