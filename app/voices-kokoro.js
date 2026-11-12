/* Divya — Kokoro in-browser TTS (Phase 2, voice engines).
 * Lazy-loads kokoro-js v1.2.1 (PINNED) from the jsDelivr ESM CDN, esm.sh as
 * fallback, and runs the Kokoro-82M model 100% on-device (WebGPU/WASM via
 * @huggingface/transformers): no server, no key, no per-use cost. The ~90 MB
 * q8 model downloads once from the Hugging Face CDN and is cached by
 * transformers.js after that.
 * v39: every load attempt uses a fresh cache-busted URL (Chromium caches a
 * failed dynamic import per URL — re-importing the same URL can never
 * recover), import + model steps each have a real timeout (a hung download
 * used to stick on "loading" forever), and kokoroStatus() carries a short
 * plain-language reason so the UI can say WHY it failed, not just that it did.
 * R34: Kokoro is now the PRIMARY voice path for all 20 catalog voices —
 * callers must NEVER silently fall back to the phone system voice when this
 * fails; kokoroStatus() reports loading/ready/failed so the UI can say so.
 * Playback goes through an AudioContext so each voice can carry its own
 * pitch character (kokoroPitch: child higher, elder lower) on top of its
 * distinct Kokoro voice id. If decode fails, plain <audio> is the fallback.
 * Model: onnx-community/Kokoro-82M-v1.0-ONNX, Apache-2.0.
 * API (verified): KokoroTTS.from_pretrained(model_id, { dtype: "q8" }),
 * tts.generate(text, { voice, speed }), tts.list_voices().
 * Voice IDs: af_ and am_ = American English, bf_ and bm_ = British English,
 * hf_ and hm_ = Hindi. NOTE: kokoro-js RawAudio has toBlob(); if a future
 * version drops it, kokoroPlay() throws (callers report it, never fake it).
 */
const KOKORO_MODEL = "onnx-community/Kokoro-82M-v1.0-ONNX";
/* v39: PINNED kokoro-js version + a second CDN. The old code imported
 * "latest" from jsDelivr only, so any future breaking release — or any
 * jsDelivr outage — silently killed every voice. jsDelivr is tried first,
 * esm.sh second (both serve a real browser ESM build with rewritten deps).
 * Every load attempt uses a FRESH URL (see kokoroLoad): Chromium caches a
 * FAILED dynamic import() per URL and rejects a re-import of the identical
 * URL instantly without a network request — that is why v37's Retry could
 * never recover (proven in a headless-Chromium test, 2026-11-11: after one
 * failed import, both a direct re-import and kokoroRetry() failed in <1s
 * with no request issued, while a plain fetch() of the same URL returned
 * 200). A new query param per attempt bypasses the cached failure. */
const KOKORO_VERSION = "1.2.1";
const KOKORO_CDNS = [
  "https://cdn.jsdelivr.net/npm/kokoro-js@" + KOKORO_VERSION + "/+esm",
  "https://esm.sh/kokoro-js@" + KOKORO_VERSION,
];
const KOKORO_IMPORT_TIMEOUT_MS = 45000; // the library is ~11 KB + deps; 45s is generous
const KOKORO_MODEL_TIMEOUT_MS = 300000; // the ~90 MB model on a slow connection
const KOKORO_HI = { F: "hf_alpha", M: "hm_omega" }; // Hindi base voices (only 2 per gender exist)
const KOKORO_FALLBACK = { F: "af_heart", M: "am_michael" };
let kokoroTTS = null, kokoroLoading = null, kokoroVoices = null;
/* R34: load state the UI can read — "idle" | "loading" | "ready" | "failed". */
let kokoroState = "idle", kokoroError = "", kokoroErrorShort = "", kokoroPhase = "idle";
/* v39: kokoroAttempt numbers every fresh load (cache-bust query); kokoroGen
 * numbers the current attempt so a stale/hung attempt can never overwrite a
 * newer one's state. kokoroTriedCDN names the CDN the last attempt used. */
let kokoroAttempt = 0, kokoroGen = 0, kokoroTriedCDN = "";
const kokoroStatus = () => ({ state: kokoroState, error: kokoroError, short: kokoroErrorShort, phase: kokoroPhase, attempt: kokoroAttempt, cdn: kokoroTriedCDN });

/* Short, plain-language reason for a load failure (shown under Retry). */
function kokoroShortError(e, phase) {
  const m = String((e && e.message) || e || "");
  if (/timed out after/.test(m)) return phase === "model" ? "voice model download timed out (~90 MB — slow connection?)" : "voice library download timed out";
  if (/Failed to fetch dynamically imported module/.test(m)) return "couldn't reach the voice library — check internet";
  if (/Failed to fetch|NetworkError|network error|ERR_/i.test(m)) return "network error while loading voices";
  if (/superseded/.test(m)) return "";
  return m.slice(0, 90);
}
function kokoroWithTimeout(promise, ms, phase) {
  let timer = null;
  const secs = ms >= 10000 ? Math.round(ms / 1000) + "s" : (ms / 1000).toFixed(1) + "s";
  const timeout = new Promise((_, rej) => { timer = setTimeout(() => rej(new Error("kokoro: " + phase + " timed out after " + secs)), ms); });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function kokoroLoad() {
  if (kokoroTTS) return kokoroTTS;
  if (kokoroLoading) return kokoroLoading;
  const gen = ++kokoroGen, attempt = ++kokoroAttempt;
  kokoroState = "loading"; kokoroError = ""; kokoroErrorShort = ""; kokoroPhase = "import";
  kokoroLoading = (async () => {
    // Import step: try each CDN with a fresh URL. A hung import (dead proxy,
    // captive portal) used to hang forever with NO timeout and NO failure —
    // the UI sat on "Loading voices…" and Retry never appeared.
    let KokoroTTS = null, lastErr = null;
    for (const base of KOKORO_CDNS) {
      kokoroTriedCDN = base;
      const url = base + (base.includes("?") ? "&" : "?") + "v39=" + attempt;
      try {
        ({ KokoroTTS } = await kokoroWithTimeout(import(url), KOKORO_IMPORT_TIMEOUT_MS, "import"));
        break;
      } catch (e) {
        lastErr = e;
        if (gen !== kokoroGen || /superseded/.test(String(e && e.message))) throw e;
        // otherwise fall through to the next CDN
      }
    }
    if (!KokoroTTS) throw lastErr || new Error("kokoro: voice library unreachable");
    if (gen !== kokoroGen) throw new Error("kokoro: superseded");
    // Model step: the ~90 MB q8 model from Hugging Face, cached by
    // transformers.js after the first download. Timed out honestly instead
    // of hanging the voice picker forever on a stalled connection.
    kokoroPhase = "model";
    let tts;
    try { tts = await kokoroWithTimeout(KokoroTTS.from_pretrained(KOKORO_MODEL, { dtype: "q8" }), KOKORO_MODEL_TIMEOUT_MS, "model"); }
    catch (e1) { // v67 (Ajju): on slow phones the ~90 MB q8 download never finishes and voices "don't load" — fall back to the ~half-size q4 model before giving up.
      tts = await kokoroWithTimeout(KokoroTTS.from_pretrained(KOKORO_MODEL, { dtype: "q4" }), KOKORO_MODEL_TIMEOUT_MS, "model"); }
    if (gen !== kokoroGen) throw new Error("kokoro: superseded");
    kokoroTTS = tts;
    try { kokoroVoices = await tts.list_voices(); } catch { kokoroVoices = null; }
    kokoroState = "ready"; kokoroPhase = "ready";
    return tts;
  })().catch(e => {
    if (gen !== kokoroGen) throw e; // stale attempt: state belongs to the newer one
    const failedPhase = kokoroPhase; // "import" or "model" — kept for the short reason
    kokoroLoading = null; kokoroState = "failed"; kokoroPhase = "failed";
    kokoroError = String(e && e.message || e);
    kokoroErrorShort = kokoroShortError(e, failedPhase);
    throw e;
  });
  return kokoroLoading;
}
/* Fire-and-forget warm-up (called after login) so the first voice reply does
 * not wait on the ~90 MB download. Failures land in kokoroStatus(). */
function kokoroWarm() { return kokoroLoad(); }
/* v37: retry after a failed load — resets the failed state so kokoroLoad()
 * starts a fresh import + download instead of staying failed until reload.
 * v39: ALSO abandons a HUNG load (state "loading" — v37 only reset when
 * already "failed", so a stalled download could never be retried), bumps the
 * generation so the abandoned attempt can never overwrite the new one's
 * state, and the new attempt gets a fresh cache-busted URL (Chromium caches
 * a failed dynamic import per URL — re-importing the identical URL was the
 * reason Retry never fixed anything). */
function kokoroRetry() {
  kokoroGen++;
  kokoroLoading = null; kokoroState = "idle"; kokoroError = ""; kokoroErrorShort = ""; kokoroPhase = "idle";
  return kokoroLoad();
}
/* Pick the Kokoro voice for a catalog voice + text. Devanagari text uses the
 * voice's own kokoroHi id (Kokoro has only hf_alpha/hf_beta + hm_omega/hm_psi,
 * so Hindi replies vary by voice + rate, not by 20 distinct models — honest
 * limit, noted in the v11 requirements doc); otherwise the catalog voice's
 * kokoro id, validated against list_voices() with an English fallback. */
function kokoroVoiceFor(voice, text) {
  const gender = voice && voice.gender === "M" ? "M" : "F";
  let id;
  if (/[\u0900-\u097F]/.test(text || "")) id = (voice && voice.kokoroHi) || KOKORO_HI[gender];
  else id = (voice && voice.kokoro) || KOKORO_FALLBACK[gender];
  // v37: validate ONLY against a real, non-empty string list. An empty list
  // (list_voices() returning []) used to fail includes() for EVERY voice and
  // collapse all 20 catalog voices to the single fallback voice per gender —
  // exactly the "only one voice plays" complaint. A missing/unreadable list
  // keeps the catalog id as-is instead of collapsing.
  if (Array.isArray(kokoroVoices) && kokoroVoices.length) {
    const names = kokoroVoices.map(v => typeof v === "string" ? v : (v && (v.id || v.name || v.voice))).filter(Boolean);
    if (names.length && !names.includes(id)) id = KOKORO_FALLBACK[gender];
  }
  return id;
}
async function kokoroSpeak(text, voice) {
  const tts = await kokoroLoad();
  const audio = await tts.generate(text, { voice: kokoroVoiceFor(voice, text), speed: (voice && voice.rate) || 1 });
  return audio; // RawAudio: .toBlob() / .save() / .data
}
/* Shared AudioContext for pitched playback (child higher, elder lower). */
let kokoroCtx = null;
function kokoroAudioCtx() {
  const C = window.AudioContext || window.webkitAudioContext;
  if (!C) return null;
  kokoroCtx = kokoroCtx || new C();
  if (kokoroCtx.state === "suspended") kokoroCtx.resume().catch(() => {});
  return kokoroCtx;
}
async function kokoroPlay(text, voice) {
  const audio = await kokoroSpeak(text, voice);
  if (!audio.toBlob) throw new Error("kokoro: no toBlob");
  const blob = audio.toBlob();
  const pitch = (voice && voice.kokoroPitch) || 1;
  // Pitched path: decode + AudioBufferSourceNode with playbackRate.
  const ctx = kokoroAudioCtx();
  if (ctx && pitch !== 1) {
    try {
      const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
      return new Promise((resolve, reject) => {
        const src = ctx.createBufferSource();
        src.buffer = buf; src.playbackRate.value = pitch;
        src.onended = () => resolve();
        src.connect(ctx.destination);
        try { src.start(); } catch (e) { reject(e); }
        setTimeout(() => resolve(), Math.max(30000, (buf.duration / pitch) * 1000 + 2000));
      });
    } catch { /* fall through to plain <audio> below */ }
  }
  // Plain path (pitch 1, or decode unavailable): real <audio> element.
  const url = URL.createObjectURL(blob);
  return new Promise((resolve, reject) => {
    const a = new Audio(url);
    a.onended = () => { URL.revokeObjectURL(url); resolve(); };
    a.onerror = e => { URL.revokeObjectURL(url); reject(e); };
    a.play().catch(e => { URL.revokeObjectURL(url); reject(e); });
  });
}
const kokoroReady = () => !!kokoroTTS;
