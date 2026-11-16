"""proof_run.py — PROOF-FIX 1 production-shape proof run.

WHY THIS EXISTS: the mission demands a production-path long run
whose logs show the real v89 brain stages executing (pre-flight,
hook scoring, LLM director) — not just unit tests. A TRUE app-path
run is impossible before this branch merges: startCreate hardcodes
the Actions dispatch ref to "main", job records live in the
JulieState DO, and the /job route needs the Worker RUNNER_KEY
secret. So this run drives the EXACT production entry the runner
uses — long_video.make_long_video(brief, chat, ...) with the cfg
resolved by spec_engine exactly as runner.create_job resolves it —
with two honest substitutions, both forced by this VM:

  chat  — production's channel is Groq free (models gpt-oss-120b /
          kimi-k2 / gpt-oss-20b, max_tokens 2500). No GROQ_KEY
          exists on this VM. The substitute is the keyless
          Pollinations endpoint serving GPT-OSS 20B — literally
          production's third sweep model — behind a simulator of
          the free channel's per-request cap: any call whose
          estimated request size (prompt chars/4 + 2500 reserved
          output) exceeds 8000 tokens raises the production-shaped
          413 error. If the pack still rode whole into any stage,
          that stage would die here exactly as it died in the
          audit. Slices must keep every call under the cap.
          One stand-in adjustment, found by the finisher's probes
          (2026-11-16): Pollinations' upstream counts the model's
          reasoning tokens against the output budget and at its
          default effort GPT-OSS exhausts the 2500-token budget
          before answering script-sized prompts (HTTP 400
          output_token_limit_exceeded — this, not size, is what
          killed the first proof attempt's writer calls; a 15K-char
          filler prompt answers fine). The request therefore sets
          max_tokens 2500 (production's exact reservation) and
          reasoning_effort "low", so the exchange stays
          production-shaped: same model, same output budget, same
          cap simulator.
  voice — edge-tts is TLS-blocked on this VM (doc.py's own comment
          documents the local-test stand-in): doc.tts is replaced
          with gTTS + evenly fabricated word timings. Voice is not
          what this proof is about; the brain stages are.

Everything else — writer, Story Analyst, Visual Director, Editing
Director, codegen, director gates, assembly, packaging — is the
shipped code on this branch, unmodified.

Run: python3 rig-prooffix/proof_run.py [minutes]
Log greps that matter: "pack slice", "BRAIN-STAGE", "story analyst
v87", "visual director v87", "editing director v87", "preflight",
"proof chat call".
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CAP_TOKENS = 8000          # simulated free-channel per-request cap
OUT_RESERVE = 2500         # runner groq_chat's max_tokens
URL = "https://text.pollinations.ai/openai"


def proof_chat(messages):
    n_chars = sum(len(str(m.get("content", ""))) for m in messages)
    est = n_chars // 4 + OUT_RESERVE
    print(f"proof chat call: {n_chars} chars (~{est} tok est)", flush=True)
    if est > CAP_TOKENS:
        # the production-shaped failure: groq_chat raises this after
        # the sweep; the stage's fallback must now LABEL itself.
        raise RuntimeError(
            "chat failed: all models failed (last: gpt-oss-20b 413)")
    body = json.dumps({"model": "openai-fast",
                       "messages": messages,
                       "max_tokens": OUT_RESERVE,
                       "reasoning_effort": "low"}).encode()
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                URL, data=body,
                headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.loads(r.read().decode())
            content = data["choices"][0]["message"]["content"]
            if content and content.strip():
                return content
            last = RuntimeError("empty completion")
        except Exception as e:  # 429 / 5xx / network: production retries too
            last = e
            print(f"proof chat attempt {attempt + 1} failed: "
                  f"{type(e).__name__} {str(e)[:100]}", flush=True)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"chat failed: {last}")


def _install_tts_standin():
    import doc
    from gtts import gTTS

    def _dur(path):
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", path], capture_output=True, text=True).stdout
        return float(json.loads(out)["format"]["duration"])

    async def fake_tts(text, voice, mood, out, rate_add=0):
        lang = (str(voice or "en").split("-")[0] or "en").lower()
        if lang not in ("en", "te", "hi"):
            lang = "en"
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        await asyncio.to_thread(
            lambda: gTTS(str(text), lang=lang).save(out))
        total = _dur(out)
        words = str(text).split()
        if not words:
            return []
        step = total / len(words)
        return [(i * step, step, w) for i, w in enumerate(words)]

    doc.tts = fake_tts
    print("tts stand-in installed (gTTS — edge-tts is blocked on "
          "this VM; production uses real edge-tts)", flush=True)


async def _notify(t):
    print("NOTIFY:", str(t)[:200], flush=True)


async def main():
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    _install_tts_standin()
    import brain_status
    brain_status.reset()
    import long_video
    import spec_engine as se

    brief = ("topic: The Silk Road — how a trade route stitched two "
             "worlds together, make a long documentary video in "
             "English, 16:9 landscape, chapters with title cards, "
             f"FINAL VIDEO LENGTH: exactly {minutes} minutes")
    # resolve the render config exactly as runner.create_job does
    spec, cfg = [], None
    try:
        spec = se.extract_spec(brief, chat=proof_chat)
        cfg = se.resolve_render_config(spec, "long")
        print(f"spec: {len(spec)} requirements, cfg "
              f"{cfg['width']}x{cfg['height']}", flush=True)
    except Exception as e:
        print("spec path failed, long defaults:", str(e)[:150], flush=True)
        cfg = se.resolve_render_config([], "long")

    workdir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "proof_workdir")
    os.makedirs(workdir, exist_ok=True)
    t0 = time.monotonic()
    res = await long_video.make_long_video(
        brief, proof_chat, workdir=workdir, target_minutes=minutes,
        notify=_notify, deadline=t0 + 3300, spec=spec, cfg=cfg)
    print("PROOF RESULT:", json.dumps({
        "path": res.get("path"), "duration": res.get("duration"),
        "partial": res.get("partial"),
        "chapters": f"{res.get('chapters_done')}/{res.get('chapters_total')}",
        "footage_share": res.get("footage_share"),
        "brain_status": res.get("brain_status"),
    }, indent=1), flush=True)
    print("BRAIN LINE:", brain_status.line(), flush=True)
    print(f"proof run wall time: {time.monotonic() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
