"""channel.py — RENDERER PIVOT Phase 1: the rate-limit-aware LLM
call layer for the runner pipeline (2026-11-16).

Why this exists: the first v89-brain film ("The Hidden Life of
Urban Bees", job 6dce25f4) proved the decision layer works — and
then died on CHANNEL CAPACITY. A long film needs ~40 LLM calls;
every one of them stormed the single free Groq channel
(runner.groq_chat's keys x models sweep with 5/15/45 s retries).
Once chapter 1 consumed the quota, chapter 2, both codegens, an
Editing Director pass and the v100 fix-round corrector all died on
HTTP 429 — each failure burning 65 s of retry storm first. 429 is
the new 413: the wall moved from payload size to rate limits.

This layer sits ABOVE the per-provider sweeps and is what the
pipeline now calls per LLM call:

- ROTATION: successive calls START on successive configured
  providers (round-robin), so a film's ~40 calls spread across
  every free quota Julie holds (her sealed key pool's env chain —
  the same PROVIDERS table providers.py rotates for chat) instead
  of draining one channel.
- FAILOVER, NOT STORMS: within one call, a provider that answers
  429 is cooled down and the call moves to the NEXT provider at
  once. The only retry-with-backoff left is inside the Groq leg
  (runner.groq_chat's pinned contract) — and once that leg reports
  a 429, the channel cools the whole Groq leg down too.
- PACING: a minimum interval (+ jitter) between successive calls
  keeps a burst of stage calls from tripping per-minute limits in
  the first place. Every pacing sleep is logged.
- PER-FILM BUDGET: begin_film() arms a call budget + deadline for
  the job. Calls past the budget, or a call no channel can serve,
  raise ChannelError — a RuntimeError whose message names the
  reason ("channel") — so every brain stage records its FALLBACK
  with reason "channel" on the brain ledger instead of dying
  silently or storming. Chapters continue on the strongest
  available channel; degradation is labelled, never hidden.
- 413 stays non-transient (payload != weather): it raises at once,
  exactly as PROOF-FIX 1 established.

The Groq leg is injected by the runner (runner.groq_chat — its
5/15/45 contract is pinned by v75test and does not change). When
nobody injects one (CLI tools, tests), a single-pass Groq sweep
stands in. All HTTP for the alternate providers goes through the
_post seam and all waiting through the _sleep seam, so a harness
can drive the whole layer deterministically.
"""

import os
import random
import time

import httpx

# The provider table is providers.py's — one chain definition for
# chat and for the pipeline, never two lists that can drift.
try:
    from providers import PROVIDERS as _PROVIDERS
except Exception:  # pragma: no cover — providers.py is in-repo
    _PROVIDERS = [
        ("groq", "GROQ_KEY", "https://api.groq.com/openai/v1",
         ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]),
    ]

# Test seams (monkeypatched by pivottest; production uses these).
_post = httpx.post
_sleep = time.sleep
_monotonic = time.monotonic

# ------------------------------------------------------------ state
_COOLDOWN = {}          # provider name -> monotonic time it may serve again
_CURSOR = {"provider": 0, "models": {}}
_LAST_CALL = {"t": 0.0}
_FILM = {"limit": 0, "used": 0, "deadline": None}
_LOG = []               # per-process call log (the pacing evidence)


class ChannelError(RuntimeError):
    """No channel could serve this call. A RuntimeError so every
    existing stage catch (which records FALLBACK from the exception
    text) keeps working; the message always carries the reason
    word "channel"."""

    def __init__(self, detail):
        super().__init__(f"LLM failed: channel — {detail}")
        self.reason = "channel"
        self.detail = detail


def _env_float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return float(default)


def _env_int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return int(default)


def min_interval_s():
    """Pacing floor between successive pipeline LLM calls."""
    return _env_float("JULIE_CHANNEL_MIN_INTERVAL_S", 1.2)


def cooldown_429_s():
    return _env_float("JULIE_CHANNEL_COOLDOWN_429_S", 120.0)


def default_budget():
    return _env_int("JULIE_CHANNEL_CALL_BUDGET", 160)


def begin_film(limit=None, deadline=None):
    """Arm the per-film call budget (runner.create_job calls this
    once per job). limit=None -> the env default; deadline is a
    monotonic timestamp the backoff/pacing must respect (the job's
    own budget deadline)."""
    _FILM["limit"] = int(limit) if limit else default_budget()
    _FILM["used"] = 0
    _FILM["deadline"] = deadline
    _LOG.clear()
    print(f"channel: film budget armed — {_FILM['limit']} calls"
          + (f", deadline in {deadline - _monotonic():.0f}s"
             if deadline else ""))
    # NEXT-ROUND (Fix 5c): the pool's shape is declared up front,
    # in the log and (via film_stats) in the job report — a
    # single-provider film must never read as if failover stood
    # ready behind it.
    _st = channel_status()
    if _st["warning"]:
        print(_st["warning"] + " for this film")
        _LOG.append({"channel_warning": _st["warning"]})


def film_stats():
    return {"limit": _FILM["limit"], "used": _FILM["used"],
            "log": list(_LOG), "channel": channel_status()}


def reset():
    """Tests only — production processes are one-job-lived."""
    _COOLDOWN.clear()
    _CURSOR["provider"] = 0
    _CURSOR["models"] = {}
    _LAST_CALL["t"] = 0.0
    _FILM.update(limit=0, used=0, deadline=None)
    _LOG.clear()


# ------------------------------------------------------------ slots
def _scout_models():
    """The Worker scout's discovered free models ({provider: [ids]}),
    handed to the runner in the job payload (JULIE_SCOUT_MODELS) —
    the same list the chat chain appends to its rotations."""
    try:
        import json as _json
        d = _json.loads(os.environ.get("JULIE_SCOUT_MODELS", "") or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _custom_model():
    """NEXT-ROUND (Fix 5b): the job owner's sealed Add-Model
    record, handed over in the job payload (JULIE_CUSTOM_MODEL:
    {base, model, key}) — an OpenAI-compatible endpoint the owner
    connected in Setup. It joins the pool as a "custom" slot so a
    film can fail over to the owner's own model too."""
    try:
        import json as _json
        d = _json.loads(os.environ.get("JULIE_CUSTOM_MODEL", "")
                        or "null")
        if isinstance(d, dict) and d.get("base") and d.get("model") \
                and d.get("key"):
            return d
    except Exception:
        pass
    return None


def _slots():
    """Configured (name, keys, base, models) per provider, in chain
    order. The Groq leg is served by the injected sweep, not here."""
    scout = _scout_models()
    out = []
    for name, env, base, models in _PROVIDERS:
        keys = [k.strip() for k in
                os.environ.get(env, "").split(",") if k.strip()]
        if keys:
            ms = list(models)
            for m in scout.get(name) or []:
                if isinstance(m, str) and m and m not in ms:
                    ms.append(m)
            out.append((name, keys, base, ms))
    cm = _custom_model()
    if cm:
        out.append(("custom", [str(cm["key"])],
                    str(cm["base"]).rstrip("/"),
                    [str(cm["model"])]))
    return out


def configured_providers():
    return [s[0] for s in _slots()]


def channel_status():
    """NEXT-ROUND (Fix 5c): the pool's honest shape for the job
    report. A one-provider pool has NO failover — the second film
    burned ~70s per rate-limited stage while its report implied
    failover stood ready, because production held exactly one
    Groq key. When that is the shape, say so in plain words."""
    names = configured_providers()
    single = len(names) == 1
    return {"providers": names,
            "single_provider": single,
            "warning": (f"channel: single-provider ({names[0]}) — "
                        f"no failover possible"
                        if single else None)}


# ------------------------------------------------------------ the Groq leg
_groq_leg = None


def set_groq_leg(fn):
    """The runner injects runner.groq_chat here (its sweep contract
    is pinned by v75test)."""
    global _groq_leg
    _groq_leg = fn


def _default_groq_leg(messages):
    """Single-pass Groq sweep (CLI / tests — no retry storm)."""
    keys = [k.strip() for k in
            os.environ.get("GROQ_KEY", "").split(",") if k.strip()]
    models = ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905",
              "openai/gpt-oss-20b"]
    last = ""
    for k in keys:
        for m in models:
            body = {"model": m, "messages": messages,
                    "temperature": 0.8, "max_tokens": 2500}
            if m.startswith("openai/gpt-oss"):
                body["reasoning_effort"] = "low"
            try:
                r = _post("https://api.groq.com/openai/v1/chat/completions",
                          json=body,
                          headers={"Authorization": f"Bearer {k}"},
                          timeout=90)
            except Exception as e:
                last = f"{m} network {type(e).__name__}"
                continue
            if r.status_code == 200:
                out = r.json()["choices"][0]["message"]["content"] or ""
                if out.strip():
                    return out
                last = f"{m} empty"
                continue
            last = f"{m} {r.status_code}"
            if r.status_code == 413:
                raise ChannelError(
                    f"payload rejected (413) on groq/{m} — the "
                    f"prompt does not fit the free channel; this is "
                    f"not a rate limit and retrying cannot help")
    raise RuntimeError("LLM failed: " + (last or "groq unconfigured"))


# ------------------------------------------------------------ one provider attempt
def _try_provider(name, keys, base, models, messages):
    """One pass over a provider's keys x models — NO retry storm:
    a 429 cools the provider and returns at once so the caller can
    fail over. Returns the reply text, or None when this provider
    cannot serve right now. Raises ChannelError on 413."""
    start = _CURSOR["models"].get(name, 0) % max(1, len(models))
    ordered = [models[(start + i) % len(models)]
               for i in range(len(models))]
    last = ""
    for key in keys:
        for model in ordered:
            body = {"model": model, "messages": messages,
                    "temperature": 0.8, "max_tokens": 2500}
            if "gpt-oss" in model:
                body["reasoning_effort"] = "low"
            if name not in ("cohere",):
                body["response_format"] = {"type": "json_object"}
            try:
                r = _post(f"{base}/chat/completions", json=body,
                          headers={"Authorization": f"Bearer {key}"},
                          timeout=90)
            except Exception as e:
                last = f"{name}/{model} network {type(e).__name__}"
                continue
            if r.status_code == 200:
                try:
                    out = r.json()["choices"][0]["message"]["content"] or ""
                except Exception:
                    out = ""
                if out.strip():
                    _CURSOR["models"][name] = \
                        (ordered.index(model) + 1) % len(models)
                    return out
                last = f"{name}/{model} empty"
                continue
            last = f"{name}/{model} {r.status_code}"
            if r.status_code == 413:
                raise ChannelError(
                    f"payload rejected (413) on {name}/{model} — "
                    f"not a rate limit; retrying cannot help")
            if r.status_code == 429:
                _COOLDOWN[name] = _monotonic() + cooldown_429_s()
                print(f"channel: {name} 429 — cooled down "
                      f"{cooldown_429_s():.0f}s, failing over")
                return None
            if r.status_code in (401, 402, 403):
                _COOLDOWN[name] = _monotonic() + 3600
                print(f"channel: {name} {r.status_code} — key "
                      f"rested 1h, failing over")
                return None
            # 404 / model 400s: try the next model on this provider.
    if last:
        print(f"channel: {name} could not serve ({last})")
    return None


def _pace():
    """Enforce the min interval (+ jitter) since the previous
    call's first attempt. Logged — the pacing evidence."""
    iv = min_interval_s()
    if iv <= 0 or not _LAST_CALL["t"]:
        return
    wait = _LAST_CALL["t"] + iv + random.uniform(0, 0.5) - _monotonic()
    if _FILM["deadline"]:
        wait = min(wait, max(0.0, _FILM["deadline"] - _monotonic()))
    if wait > 0.05:
        print(f"channel: pacing — sleeping {wait:.2f}s "
              f"(min interval {iv:.1f}s between calls)")
        _LOG.append({"pace_sleep_s": round(wait, 3)})
        _sleep(wait)


# ------------------------------------------------------------ the call
def chat(messages):
    """The pipeline's LLM call. Same contract as runner.groq_chat
    (returns the reply text; raises RuntimeError when nothing can
    serve) — but paced, rotated across every configured free
    provider, failover on 429, and bounded by the per-film budget.
    """
    _n_chars = sum(len(str(m.get("content", ""))) for m in messages)
    if _FILM["limit"] and _FILM["used"] >= _FILM["limit"]:
        raise ChannelError(
            f"per-film call budget exhausted ({_FILM['used']}/"
            f"{_FILM['limit']} calls) — this stage falls back "
            f"instead of burning more channel")
    _pace()
    _LAST_CALL["t"] = _monotonic()
    _FILM["used"] += 1
    call_no = _FILM["used"]
    slots = _slots()
    names = [s[0] for s in slots]
    print(f"channel: call {call_no}"
          + (f"/{_FILM['limit']}" if _FILM["limit"] else "")
          + f" — prompt {_n_chars} chars (~{_n_chars // 4} tok est); "
          + f"providers: {', '.join(names) or 'none configured'}")
    if not slots:
        raise ChannelError("no LLM provider is configured "
                           "(no keys in the environment)")
    # rotation: this call starts where the cursor points, then
    # walks the whole chain; cooled-down providers are skipped
    # unless EVERY provider is cooling (then the earliest-expiring
    # one is tried anyway — a film must not stall on bookkeeping).
    start = _CURSOR["provider"] % len(slots)
    order = [slots[(start + i) % len(slots)] for i in range(len(slots))]
    _CURSOR["provider"] = (start + 1) % len(slots)
    now = _monotonic()
    ready = [s for s in order if _COOLDOWN.get(s[0], 0) <= now]
    attempt_order = ready if ready else [
        min(order, key=lambda s: _COOLDOWN.get(s[0], 0))]
    reasons = []
    for name, keys, base, models in attempt_order:
        try:
            if name == "groq":
                leg = _groq_leg or _default_groq_leg
                out = leg(messages)
            else:
                out = _try_provider(name, keys, base, models, messages)
        except ChannelError:
            raise
        except RuntimeError as e:
            msg = str(e)
            if "429" in msg:
                _COOLDOWN[name] = _monotonic() + cooldown_429_s()
                print(f"channel: {name} leg reported 429 — cooled "
                      f"down {cooldown_429_s():.0f}s, failing over")
            reasons.append(f"{name}: {msg[:80]}")
            out = None
        if out:
            _LOG.append({"call": call_no, "provider": name,
                         "chars": _n_chars})
            print(f"channel: call {call_no} served by {name}")
            return out
        reasons.append(f"{name}: unavailable")
    raise ChannelError(
        "every provider failed or is rate-limited ("
        + "; ".join(reasons[-4:]) + ") — this stage falls back "
        "with reason 'channel' and the film continues on the "
        "strongest remaining channel")


if __name__ == "__main__":
    # deterministic self-check: rotation + failover with stub seams
    import json as _json

    calls = []

    class _R:
        def __init__(self, status, text=""):
            self.status_code = status
            self._text = text

        def json(self):
            return {"choices": [{"message": {"content": self._text}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(url)
        if "groq" in url:
            return _R(429)
        return _R(200, "served-by-alternate")

    _orig = (_post, _sleep, _monotonic)
    globals()["_post"] = fake_post
    globals()["_sleep"] = lambda s: None
    os.environ["GROQ_KEY"] = "gk"
    os.environ["CEREBRAS_KEY"] = "ck"
    try:
        reset()
        begin_film(limit=10)
        out = chat([{"role": "user", "content": "hi"}])
        assert out == "served-by-alternate", out
        assert film_stats()["used"] == 1
        print("channel self-check OK")
    finally:
        globals()["_post"], globals()["_sleep"], globals()["_monotonic"] = _orig
        os.environ.pop("CEREBRAS_KEY", None)
