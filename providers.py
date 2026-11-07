"""Many free AI providers with automatic rotation. If one key/provider hits its limit, the next one answers.
Each env var may hold several keys separated by commas."""
import os
import time
import httpx

PROVIDERS = [
    # (name, env var, base url, preferred models — first that works is used)
    ("groq", "GROQ_KEY", "https://api.groq.com/openai/v1",
     ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]),
    ("cerebras", "CEREBRAS_KEY", "https://api.cerebras.ai/v1",
     ["gpt-oss-120b", "qwen-3-235b-a22b-instruct-2507", "llama-3.3-70b"]),
    ("gemini", "GEMINI_KEY", "https://generativelanguage.googleapis.com/v1beta/openai",
     ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]),
    ("openrouter", "OPENROUTER_KEY", "https://openrouter.ai/api/v1",
     ["openai/gpt-oss-120b:free", "meta-llama/llama-3.3-70b-instruct:free", "deepseek/deepseek-chat-v3-0324:free"]),
    ("sambanova", "SAMBANOVA_KEY", "https://api.sambanova.ai/v1",
     ["gpt-oss-120b", "Meta-Llama-3.3-70B-Instruct", "DeepSeek-V3-0324"]),
    ("nvidia", "NVIDIA_KEY", "https://integrate.api.nvidia.com/v1",
     ["nvidia/nemotron-3-super-120b-a12b", "deepseek-ai/deepseek-v4.1-flash", "moonshotai/kimi-k2.6", "openai/gpt-oss-20b"]),
    ("zai", "ZAI_KEY", "https://api.z.ai/api/paas/v4",
     ["glm-4.5-flash", "glm-4.7-flash"]),                       # free GLM "flash" models only
    ("mistral", "MISTRAL_KEY", "https://api.mistral.ai/v1",
     ["mistral-small-latest", "mistral-medium-latest", "open-mistral-nemo"]),   # free Experiment tier
    ("cohere", "COHERE_KEY", "https://api.cohere.ai/compatibility/v1",
     ["command-a-03-2025", "command-r-plus"]),
]

COOLDOWN: dict[str, float] = {}   # "provider|key|model" -> time when it may be used again
_free_models: dict[str, list] = {}


def slots():
    for name, env, base, models in PROVIDERS:
        for key in [k.strip() for k in os.getenv(env, "").split(",") if k.strip()]:
            yield name, key, base, models


async def _discover(c, name, base, key):
    """Ask the provider which models exist now (models get renamed/removed over time)."""
    if name in _free_models:
        return _free_models[name]
    try:
        r = await c.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
        data = r.json().get("data", [])
        ids = []
        for m in data:
            mid = m.get("id", "")
            if name == "openrouter" and not mid.endswith(":free"):
                continue
            if name == "zai" and "flash" not in mid:          # only GLM flash models are free
                continue
            if name == "gemini" and ("pro" in mid or "ultra" in mid):   # free tier = flash family
                continue
            if any(x in mid.lower() for x in ("whisper", "embed", "guard", "safety", "reward", "parse", "coder", "tts", "orpheus", "rerank", "vision-only")):
                continue
            ids.append(mid)
        _free_models[name] = ids[:5]
    except Exception:
        _free_models[name] = []
    return _free_models[name]


async def chat(messages, json_mode=True, temperature=0.2):
    errors = []
    async with httpx.AsyncClient(timeout=90) as c:
        for name, key, base, models in slots():
            cand = list(models) + [m for m in await _discover(c, name, base, key) if m not in models]
            for model in cand:
                tag = f"{name}|{key[-6:]}|{model}"
                if COOLDOWN.get(tag, 0) > time.time():
                    continue
                body = {"model": model, "temperature": temperature, "messages": messages}
                if json_mode and name not in ("cohere",):
                    body["response_format"] = {"type": "json_object"}
                try:
                    r = await c.post(f"{base}/chat/completions", json=body,
                                     headers={"Authorization": f"Bearer {key}"})
                    if r.status_code == 429:          # limit hit: rest this key for 2 minutes
                        COOLDOWN[tag] = time.time() + 120
                        errors.append(f"{name}:429")
                        break
                    if r.status_code in (401, 402, 403):   # bad key / no free credit: skip this key for a day
                        COOLDOWN.update({f"{name}|{key[-6:]}|{m}": time.time() + 86400 for m in cand})
                        errors.append(f"{name}:{r.status_code}")
                        break
                    if r.status_code in (404, 410) or (r.status_code == 400 and "model" in r.text.lower()):
                        COOLDOWN[tag] = time.time() + 3600
                        continue
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]["content"], name
                except Exception as e:  # noqa
                    COOLDOWN[tag] = time.time() + 30
                    errors.append(f"{name}:{str(e)[:60]}")
    raise RuntimeError("All AI providers busy right now: " + "; ".join(errors[-5:]))
