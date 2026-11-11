/* Divya — Kokoro in-browser TTS (Phase 2, voice engines).
 * Lazy-loads kokoro-js from the jsDelivr ESM CDN on first use and runs the
 * Kokoro-82M model 100% on-device (WebGPU/WASM via @huggingface/transformers):
 * no server, no key, no per-use cost. The ~90 MB q8 model downloads once
 * from the Hugging Face CDN and is cached by transformers.js after that.
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
const KOKORO_CDN = "https://cdn.jsdelivr.net/npm/kokoro-js/+esm"; // latest; pin a version in production
const KOKORO_HI = { F: "hf_alpha", M: "hm_omega" }; // Hindi base voices (only 2 per gender exist)
const KOKORO_FALLBACK = { F: "af_heart", M: "am_michael" };
let kokoroTTS = null, kokoroLoading = null, kokoroVoices = null;
/* R34: load state the UI can read — "idle" | "loading" | "ready" | "failed". */
let kokoroState = "idle", kokoroError = "";
const kokoroStatus = () => ({ state: kokoroState, error: kokoroError });

async function kokoroLoad() {
  if (kokoroTTS) return kokoroTTS;
  if (!kokoroLoading) {
    kokoroState = "loading"; kokoroError = "";
    kokoroLoading = (async () => {
      const { KokoroTTS } = await import(KOKORO_CDN);
      const tts = await KokoroTTS.from_pretrained(KOKORO_MODEL, { dtype: "q8" });
      kokoroTTS = tts;
      try { kokoroVoices = await tts.list_voices(); } catch { kokoroVoices = null; }
      kokoroState = "ready";
      return tts;
    })().catch(e => { kokoroLoading = null; kokoroState = "failed"; kokoroError = String(e && e.message || e); throw e; });
  }
  return kokoroLoading;
}
/* Fire-and-forget warm-up (called after login) so the first voice reply does
 * not wait on the ~90 MB download. Failures land in kokoroStatus(). */
function kokoroWarm() { return kokoroLoad(); }
/* v37: retry after a failed load — resets the failed state so kokoroLoad()
 * starts a fresh import + download instead of staying failed until reload. */
function kokoroRetry() {
  if (kokoroState === "failed") { kokoroLoading = null; kokoroState = "idle"; kokoroError = ""; }
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
