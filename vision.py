"""Julie's eyes: read screenshots/photos and "watch" videos by sampling frames.
Free vision models with rotation (same comma-separated env keys as providers.py):
  Groq  (meta-llama/llama-4-scout-17b-16e-instruct, OpenAI-compatible, image_url base64)
  Gemini (gemini-2.5-flash, native generateContent with inline_data)
  OpenRouter free vision models, Mistral (pixtral) as fallbacks.
If one key/model is rate-limited it rests and the next one answers."""
import asyncio
import base64
import json
import os
import re
import tempfile
import time
import uuid

import httpx

from config import DATA

GROQ_MODELS = ["meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"]
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
OPENROUTER_MODELS = ["meta-llama/llama-4-scout:free", "google/gemma-3-27b-it:free",
                     "qwen/qwen2.5-vl-72b-instruct:free"]
MISTRAL_MODELS = ["pixtral-12b-latest", "mistral-small-latest"]

OPENAI_STYLE = {
    # name: (env var, base url, models, max images per request)
    "groq": ("GROQ_KEY", "https://api.groq.com/openai/v1", GROQ_MODELS, 5),
    "openrouter": ("OPENROUTER_KEY", "https://openrouter.ai/api/v1", OPENROUTER_MODELS, 5),
    "mistral": ("MISTRAL_KEY", "https://api.mistral.ai/v1", MISTRAL_MODELS, 8),
}
ORDER = ["groq", "gemini", "openrouter", "mistral"]
COOLDOWN: dict[str, float] = {}


def _keys(env):
    return [k.strip() for k in os.getenv(env, "").split(",") if k.strip()]


def available() -> bool:
    return any(_keys(e) for e in ("GROQ_KEY", "GEMINI_KEY", "OPENROUTER_KEY", "MISTRAL_KEY"))


# ---------- image prep ----------
async def _ff(*args):
    p = await asyncio.create_subprocess_exec("ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, err = await p.communicate()
    if p.returncode != 0:
        raise RuntimeError(err.decode()[-300:])


async def _prep(img, max_side=1024) -> bytes:
    """Path or bytes -> JPEG bytes, longest side <= max_side (keeps requests small, under Groq's 4 MB base64 cap)."""
    tmp_in = None
    if isinstance(img, (bytes, bytearray)):
        tmp_in = tempfile.NamedTemporaryFile(suffix=".img", delete=False, dir=DATA)
        tmp_in.write(img)
        tmp_in.close()
        src = tmp_in.name
    else:
        src = str(img)
    out = os.path.join(DATA, f"vis_{uuid.uuid4().hex[:8]}.jpg")
    try:
        await _ff("-i", src, "-frames:v", "1", "-vf",
                  f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'",
                  "-q:v", "4", out)
        with open(out, "rb") as f:
            return f.read()
    except RuntimeError:
        if tmp_in is None and os.path.exists(src):
            return open(src, "rb").read()      # let the model try the raw file
        return bytes(img)
    finally:
        for p in (out, tmp_in.name if tmp_in else None):
            if p and os.path.exists(p):
                os.remove(p)


# ---------- providers ----------
async def _openai_style(c, name, key, model, prompt, imgs):
    env, base, _, _ = OPENAI_STYLE[name]
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}
        for b in imgs]
    r = await c.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                     json={"model": model, "temperature": 0.2, "max_tokens": 1200,
                           "messages": [{"role": "user", "content": content}]})
    return r, (lambda: r.json()["choices"][0]["message"]["content"])


async def _gemini(c, key, model, prompt, imgs):
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b).decode()}} for b in imgs]
    parts.append({"text": prompt})
    r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                     headers={"x-goog-api-key": key},          # header, so the key never lands in a URL/log
                     json={"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.2}})

    def text():
        cands = r.json().get("candidates") or []
        return "".join(p.get("text", "") for p in cands[0]["content"]["parts"]) if cands else ""
    return r, text


async def describe_images(images, question: str) -> tuple[str, str]:
    """Ask a vision model about one or more images (paths or bytes). Returns (answer, provider)."""
    if not images:
        raise ValueError("no images")
    imgs = [await _prep(i) for i in images]
    errors = []
    async with httpx.AsyncClient(timeout=120) as c:
        for name in ORDER:
            if name == "gemini":
                keys, models, cap = _keys("GEMINI_KEY"), GEMINI_MODELS, 16
            else:
                env, _, models, cap = OPENAI_STYLE[name]
                keys = _keys(env)
            for key in keys:
                for model in models:
                    tag = f"{name}|{key[-6:]}|{model}"
                    if COOLDOWN.get(tag, 0) > time.time():
                        continue
                    try:
                        if name == "gemini":
                            r, get = await _gemini(c, key, model, question, imgs[:cap])
                        else:
                            r, get = await _openai_style(c, name, key, model, question, imgs[:cap])
                        if r.status_code == 429:
                            COOLDOWN[tag] = time.time() + 120
                            errors.append(f"{name}:429")
                            break
                        if r.status_code in (401, 402, 403):
                            COOLDOWN.update({f"{name}|{key[-6:]}|{m}": time.time() + 86400 for m in models})
                            errors.append(f"{name}:{r.status_code}")
                            break
                        if r.status_code in (400, 404, 410):
                            COOLDOWN[tag] = time.time() + 3600
                            errors.append(f"{name}/{model}:{r.status_code}")
                            continue
                        r.raise_for_status()
                        ans = (get() or "").strip()
                        if ans:
                            return ans, name
                    except Exception as e:  # noqa
                        COOLDOWN[tag] = time.time() + 30
                        errors.append(f"{name}:{type(e).__name__}")
    raise RuntimeError("Vision models busy / no key: " + "; ".join(errors[-5:]))


async def describe_image(path_or_bytes, question: str = "") -> str:
    q = question.strip() or ("Ee image/screenshot lo emundi? Text unte exact ga chadivi cheppu, "
                             "errors/numbers/buttons important. Reply in romanized Telugu mixed with English, short.")
    ans, _ = await describe_images([path_or_bytes], q)
    return ans


# ---------- watching videos ----------
async def _duration(path):
    p = await asyncio.create_subprocess_exec("ffprobe", "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", path, stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    try:
        return float(out.decode().strip())
    except ValueError:
        return 0.0


async def frames_for_video(path: str, n: int = 6, width: int = 540) -> list[dict]:
    """Sample n evenly spaced frames (skipping the very first/last instants). Returns [{"t": sec, "path": jpg}]."""
    d = await _duration(path)
    n = max(1, int(n))
    times = [d * (i + 0.5) / n for i in range(n)] if d > 0 else [0.0]
    out = []
    for t in times:
        o = os.path.join(DATA, f"frame_{uuid.uuid4().hex[:8]}.jpg")
        try:
            await _ff("-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", o)
        except RuntimeError:
            continue
        if os.path.exists(o) and os.path.getsize(o) > 0:
            out.append({"t": round(t, 2), "path": o})
    return out


async def black_segments(path: str) -> list[tuple[float, float]]:
    """Deterministic check (no AI): black stretches >= 0.3 s."""
    p = await asyncio.create_subprocess_exec("ffmpeg", "-hide_banner", "-i", path, "-vf",
                                             "blackdetect=d=0.3:pix_th=0.10", "-an", "-f", "null", "-",
                                             stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
    _, err = await p.communicate()
    return [(float(a), float(b)) for a, b in
            re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err.decode(errors="ignore"))]


REVIEW_Q = """You are a strict video QA editor. These are {n} frames sampled in order from a finished
vertical Short/Reel (timestamps: {ts}). Check for: text or captions cut off at the frame edges, captions
overlapping other text/faces or sitting in the bottom ~20% / top ~12% platform UI zone, black or blank frames,
unreadable/tiny text, wrong aspect ratio or black bars, garbled characters/typos in visible text (incl. Telugu).
Reply ONLY JSON: {{"ok": true|false, "issues": ["short issue with timestamp"], "fix_hint": "short suggestion"}}"""


def parse_json(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.split("\n", 1)[1] if "\n" in t else t
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in reply")
    return json.loads(t[a:b + 1])


async def review_render(path: str, n: int = 6) -> dict:
    """Automatic quality check after an edit: deterministic black-frame scan + vision critique of sampled frames.
    Returns {"ok", "issues", "fix_hint", "checked_by"}. If no vision model answers, only the deterministic check counts."""
    issues = []
    d = await _duration(path)
    if d < 0.3:
        return {"ok": False, "issues": ["render empty / no duration"], "fix_hint": "re-render", "checked_by": "ffprobe"}
    for a, b in await black_segments(path):
        issues.append(f"black frames {a:.1f}s-{b:.1f}s")
    frames = await frames_for_video(path, n)
    res = {"ok": not issues, "issues": issues, "fix_hint": "", "checked_by": "ffmpeg"}
    if frames and available():
        try:
            ans, prov = await describe_images([f["path"] for f in frames],
                                              REVIEW_Q.format(n=len(frames), ts=", ".join(f"{f['t']}s" for f in frames)))
            j = parse_json(ans)
            res["issues"] += [str(x) for x in j.get("issues", []) if str(x).strip()]
            res["fix_hint"] = str(j.get("fix_hint", ""))
            res["ok"] = bool(j.get("ok", True)) and not issues
            res["checked_by"] = f"ffmpeg+{prov}"
        except Exception as e:  # noqa  vision is a bonus; never block delivery on it
            res["vision_error"] = str(e)[:120]
    for f in frames:
        try:
            os.remove(f["path"])
        except OSError:
            pass
    return res
