"""v83: zero-shot voice CLONING for the runner — Chatterbox TTS.

The v71 seam (doc.synth_voice) matched a reference sample's PACE with
the closest built-in voice and said so honestly: "exact clone engine
pending". This module IS that engine. Given a reference WAV of a
consented speaker and a line of text, it synthesises the line in
THAT speaker's voice:

  engine  Chatterbox TTS (Resemble AI, MIT licence) — zero-shot
          English cloning from a short reference clip, CPU-feasible.
  ref     a clean WAV (24 kHz mono). Production storage is the v71
          refvoice mechanism (Worker KV); the runner hands the job's
          refvoice asset path in, exactly like user voices.
  text    generated phrase by phrase (split_phrases — see the
          delivery-lock notes below); units are synthesised with
          the SAME cached conditioning and concatenated with
          boundary-typed silences.
  level   the concatenated voice track is normalised to the
          pipeline's -14 LUFS class target (the same target doc.py's
          final mix loudnorms to), so a cloned scene sits at the
          constant level the pipeline promises.
  delivery lock (Ajju's verdict on the first proofs, 2026-11-14):
          the house speaker's delivery is CONTROLLED — measured on
          the Tripti sample: F0 p10–p90 168–311 Hz, onset rate
          5.24/s. At Chatterbox's default exaggeration (0.5) the
          clone swung F0 145–362 and delivered a question line ~24%
          SLOW (4.00 onsets/s). So generation now runs at
          EXAGGERATION 0.35, and every line passes a PACE GUARD:
          its onset rate must sit within ±15% of the reference's,
          else ONE regeneration, then (if still out) an atempo
          nudge clamped to 1.12x. What was applied is recorded in
          the synth result ("pace") and, via synth_to_file, in
          clone_tts.LAST_PACE for the job artifacts.
  phrase chunking (accent/delivery audit, 2026-11-14): word
          timestamps showed her emphasis is WORD-STRETCH (hinge
          words held: "or" 0.68 s, "we" 0.64 s), her one real pause
          is 0.66 s after a sentence, and she flows THROUGH commas
          with no gap — while the clone, given a whole sentence per
          generation, invented a 0.42 s mid-phrase gap. So text is
          now generated PHRASE by phrase (split_phrases): a unit
          ends at sentence punctuation (joined with her measured
          0.66 s gap) or at a comma/semicolon/colon (joined with
          0.06 s — a breath, not a pause), so pauses can only land
          where natural phrase boundaries are; and any long
          silence the engine still invents INSIDE a phrase is
          squashed (_squash_gaps_np). Cost honesty: each unit is
          one engine call, so a comma-rich line costs more calls
          than the old sentence packing did.

torch is imported LAZILY (engine load only): the pure helpers —
split_text / estimate_word_timings — import with no ML stack, so the
unit tests and the spec layer never pay for the engine.

CLI (proof + debugging):
  python3 clone_tts.py --ref ref.wav --text "Hello." --out line.mp3
"""

import json
import os
import re
import subprocess
import time

TARGET_LUFS = -14.0       # doc.py final-mix loudnorm target (I=-14)
TARGET_TP = -1.0
ENGINE_SR = 24000         # Chatterbox S3Gen output sample rate
MAX_CHUNK_CHARS = 260     # per-generation text cap (sentence-packed)
PHRASE_GAP_SENTENCE_S = 0.66  # join gap after . ? ! … — her measured
                          # pause; engine phrase tails are ~0.06 s
                          # (measured), so the join gap IS the pause
PHRASE_GAP_CLAUSE_S = 0.06    # join gap after , ; : — she flows through
MIN_PHRASE_CHARS = 10     # shorter fragments merge into the previous
                          # phrase (a 3-letter engine call sounds broken)
MAX_INTERNAL_GAP_S = 0.18  # a silence LONGER than this INSIDE one
                          # generated phrase is an engine-invented
                          # pause (hers has none) — squash it to…
KEEP_GAP_S = 0.05         # …this much of its own samples (no click)

# delivery lock (see module docstring): controlled, not theatrical.
EXAGGERATION = 0.35       # Chatterbox default is 0.5 — too dramatic
PACE_BAND_FRAC = 0.15     # line onset rate must be within ±15% of ref
PACE_MAX_NUDGE = 1.12     # atempo clamp for the pace guard's last step
FALLBACK_REF_ONSET_RATE = 5.24  # measured on the Tripti house sample;
                          # used only if the ref itself can't be measured

_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
_CLAUSE_RE = re.compile(r"(?<=[,;:])\s+")


# ------------------------------------------------------------------
# pure helpers (no torch)
# ------------------------------------------------------------------
def split_text(text, max_chars=MAX_CHUNK_CHARS):
    """Pack text into <= max_chars chunks at sentence boundaries.

    A single sentence longer than the cap is split at clause
    boundaries, then at word boundaries (hard split only for a
    single word longer than the cap). Empty/whitespace text -> [].
    """
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    pieces = []
    for sent in _SENTENCE_RE.split(text):
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) <= max_chars:
            pieces.append(sent)
            continue
        clauses = [c.strip() for c in _CLAUSE_RE.split(sent) if c.strip()]
        buf = ""
        for cl in clauses:
            if len(cl) > max_chars:  # pathological: split on words
                words = cl.split()
                for w in words:
                    if len(w) > max_chars:
                        if buf:
                            pieces.append(buf); buf = ""
                        pieces.extend(w[i:i + max_chars]
                                      for i in range(0, len(w), max_chars))
                    elif len(buf) + len(w) + 1 <= max_chars:
                        buf = (buf + " " + w).strip()
                    else:
                        pieces.append(buf); buf = w
                continue
            if len(buf) + len(cl) + 1 <= max_chars:
                buf = (buf + " " + cl).strip()
            else:
                if buf:
                    pieces.append(buf)
                buf = cl
        if buf:
            pieces.append(buf)
    chunks, buf = [], ""
    for p in pieces:
        if len(buf) + len(p) + 1 <= max_chars:
            buf = (buf + " " + p).strip()
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def split_phrases(text):
    """[(phrase, boundary)] — split at NATURAL PHRASE boundaries.

    boundary says what follows the phrase in speech: "sentence"
    (after . ? ! …), "clause" (after , ; :) or "end" (the last
    phrase). The synth joins phrases with PHRASE_GAP_SENTENCE_S /
    PHRASE_GAP_CLAUSE_S of silence, so a pause can only appear
    where a boundary is — the engine never gets a whole flowing
    sentence in which to invent a mid-phrase gap (the delivery
    audit's 0.42 s gap before "we"). Fragments shorter than
    MIN_PHRASE_CHARS merge into the previous phrase, keeping the
    fragment's boundary (the pause comes after the merged unit).
    """
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    raw = []
    for m in re.finditer(r"[^.!?…;,;:]+(?:[.!?…;,;:]+)?", text):
        piece = m.group(0).strip()
        if not piece:
            continue
        last = piece[-1]
        b = ("sentence" if last in ".!?…"
             else "clause" if last in ",;:" else "end")
        raw.append([piece, b])
    merged = []
    for piece, b in raw:
        if merged and len(piece) < MIN_PHRASE_CHARS:
            merged[-1][0] = (merged[-1][0] + " " + piece).strip()
            merged[-1][1] = b
        else:
            merged.append([piece, b])
    if merged:
        merged[-1][1] = "end"
    return [(p, b) for p, b in merged]


def _gap_after(boundary):
    return {"sentence": PHRASE_GAP_SENTENCE_S,
            "clause": PHRASE_GAP_CLAUSE_S,
            "end": 0.0}[boundary]


def _squash_gaps_np(x, sr):
    """Squash engine-invented pauses INSIDE one generated phrase.

    The accent audit caught the engine inserting a 0.46 s silence
    before "we" inside a 5-word phrase — her delivery has NO
    mid-phrase gap. Any low-energy run longer than
    MAX_INTERNAL_GAP_S strictly inside the phrase's speech bounds
    is cut down to KEEP_GAP_S of its own samples (keeping real
    samples, not zeros, so the splice cannot click). Leading and
    trailing silence is the join logic's business, untouched here.
    Pure numpy; x is a 1-D float array."""
    import numpy as np
    frame = max(1, int(0.02 * sr))  # 20 ms frames: a 10 ms grid lets
    n = len(x) // frame             # vocoder hiss spikes fragment a
    if n == 0:                      # real gap into sub-threshold runs
        return x
    rms = np.sqrt(np.mean(
        x[:n * frame].reshape(n, frame).astype(np.float64) ** 2,
        axis=1) + 1e-12)
    thr = rms.max() * 10 ** (-34 / 20)
    speech = rms > thr
    # close blips: a "speech" run of <= 2 frames (40 ms) wholly
    # inside a gap is floor noise, not a word — the measured Tripti
    # hole (-42 dB) fluctuated exactly like this and survived a
    # naive threshold.
    i = 0
    while i < n:
        if speech[i]:
            j = i
            while j < n and speech[j]:
                j += 1
            if 0 < i and j < n and j - i <= 2:
                speech[i:j] = False
            i = j
        else:
            i += 1
    if not speech.any():
        return x
    first = int(np.argmax(speech))
    last = n - int(np.argmax(speech[::-1]))
    out = [x[:first * frame]]
    i = first
    while i < last:
        j = i
        if speech[i]:
            while j < last and speech[j]:
                j += 1
            out.append(x[i * frame:j * frame])
        else:
            while j < last and not speech[j]:
                j += 1
            if (j - i) * (frame / sr) > MAX_INTERNAL_GAP_S:
                out.append(x[i * frame:i * frame + int(KEEP_GAP_S * sr)])
            else:
                out.append(x[i * frame:j * frame])
        i = j
    out.append(x[last * frame:])
    return np.concatenate(out) if len(out) > 1 else x


def _generation_units(text):
    """[(unit_text, gap_after_s)] for the engine: one unit per
    phrase; a phrase still over MAX_CHUNK_CHARS falls back to
    split_text sub-chunks joined at clause gaps."""
    units = []
    for phrase, boundary in split_phrases(text):
        if len(phrase) <= MAX_CHUNK_CHARS:
            units.append((phrase, _gap_after(boundary)))
            continue
        subs = split_text(phrase)
        for j, s in enumerate(subs):
            units.append((s, PHRASE_GAP_CLAUSE_S if j < len(subs) - 1
                          else _gap_after(boundary)))
    return units


def estimate_word_timings(text, total_dur):
    """[(start, dur, word)] spread over total_dur.

    The clone engine returns no word boundaries (edge-tts does);
    captions + hit-word timing need SOME timings, so durations are
    distributed in proportion to word length, with extra weight on
    sentence/clause-final words (the natural pause after them).
    Estimates, honestly labelled as such by the caller.
    """
    words = str(text or "").split()
    if not words or total_dur <= 0:
        return []
    weights = []
    for w in words:
        wt = len(w) + 1.0
        if w.endswith((".", "!", "?", "…")):
            wt += 3.0
        elif w.endswith((",", ";", ":")):
            wt += 1.5
        weights.append(wt)
    total_w = sum(weights)
    out, t = [], 0.0
    for w, wt in zip(words, weights):
        d = total_dur * wt / total_w
        out.append((round(t, 3), round(d, 3), w))
        t += d
    return out


def probe_duration(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(o.stdout.strip() or 0)


# ------------------------------------------------------------------
# pace guard (delivery lock) — onset rate vs the reference's
# ------------------------------------------------------------------
def pace_verdict(rate, ref_rate):
    """Pure: is `rate` (onsets/s of a generated line) within
    ±PACE_BAND_FRAC of the reference's rate? If not, the atempo
    factor that would centre it, clamped to ±PACE_MAX_NUDGE
    (atempo > 1 speeds up — a SLOW line, rate < ref, needs > 1)."""
    if not rate or not ref_rate:
        return {"in_band": True, "atempo": 1.0}
    lo = ref_rate * (1 - PACE_BAND_FRAC)
    hi = ref_rate * (1 + PACE_BAND_FRAC)
    if lo <= rate <= hi:
        return {"in_band": True, "atempo": 1.0}
    f = ref_rate / rate
    f = max(1.0 / PACE_MAX_NUDGE, min(PACE_MAX_NUDGE, f))
    return {"in_band": False, "atempo": round(f, 3)}


_ONSET_CACHE = {}


def onset_rate(path):
    """Onsets per second (librosa onset detection) — the pace proxy
    the delivery lock is judged by. Cached per (path, mtime): the
    reference is measured once per job. librosa is imported lazily
    (it ships with Chatterbox; the pure helpers/tests never pay)."""
    key = (os.path.abspath(path), os.path.getmtime(path))
    if key in _ONSET_CACHE:
        return _ONSET_CACHE[key]
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True)
    # onset_envelope + frames, NOT onset_detect(y=..., unit="time"):
    # librosa 0.11 forwards `unit` into peak_pick, which rejects it
    # (TypeError) — that crashed the first fixed-proof run AFTER
    # generation. Envelope frames are version-stable.
    env = librosa.onset.onset_strength(y=y, sr=sr)
    frames = librosa.onset.onset_detect(onset_envelope=env, sr=sr)
    dur = len(y) / sr
    rate = (len(frames) / dur) if dur > 0 else 0.0
    _ONSET_CACHE[key] = rate
    return rate


def _atempo_inplace(wav_path, factor):
    """ffmpeg atempo on a wav, in place (via a temp file)."""
    tmp = wav_path + ".atempo.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav_path,
                    "-af", f"atempo={factor}", tmp], check=True)
    os.replace(tmp, wav_path)


# ------------------------------------------------------------------
# loudness (ffmpeg, the pipeline's own tool)
# ------------------------------------------------------------------
def _loudnorm_to(src_wav, out_path):
    """Normalise src_wav to TARGET_LUFS / TARGET_TP and write
    out_path (format from the extension: wav -> pcm_s16le, mp3 ->
    libmp3lame). Two-pass (measured, linear) when the measurement
    parses, one-pass otherwise."""
    ext = os.path.splitext(out_path)[1].lower()
    codec = (["-c:a", "pcm_s16le"] if ext == ".wav"
             else ["-c:a", "libmp3lame", "-b:a", "160k"])
    base = ["ffmpeg", "-y", "-v", "error", "-i", src_wav]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    measured = None
    try:
        o = subprocess.run(base + ["-af",
                                   "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
                                   "-f", "null", "-"],
                           capture_output=True, text=True)
        m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", o.stderr or "")
        if m:
            measured = json.loads(m.group(0))
    except Exception:
        measured = None
    if measured:
        ln = (f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11:"
              f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
              f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
              f"offset={measured['target_offset']}:linear=true")
    else:
        ln = f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11"
    subprocess.run(base + ["-af", ln, "-ar", str(ENGINE_SR)] + codec + [out_path],
                   check=True)


# ------------------------------------------------------------------
# the engine (lazy torch import — the ONLY place torch is needed)
# ------------------------------------------------------------------
def _sanitize_proxy_env():
    """httpx (huggingface_hub's client) parses NO_PROXY entries as
    URL patterns and crashes on bracketed IPv6 entries
    ("Invalid port: ':1]'") — seen on this VM, whose no_proxy lists
    [fd8b:...] addresses. Drop ONLY those entries; the proxy itself
    stays. A no-op on normal runner environments."""
    for key in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(key)
        if val and "[" in val:
            kept = [p for p in val.split(",") if "[" not in p]
            os.environ[key] = ",".join(kept)


class CloneEngine:
    """One Chatterbox model per process; conditioning (the voice
    embedding extracted from the reference) is prepared ONCE per
    reference file and reused for every chunk of every line in the
    job — that is the per-job cache the engine allows."""

    def __init__(self, device=None):
        self.device = device or os.environ.get("DIVYA_CLONE_DEVICE", "cpu")
        self.model = None
        self._conds_ref = None
        self._has_prepare = False

    def _load(self):
        if self.model is not None:
            return
        _sanitize_proxy_env()
        import torch
        from chatterbox.tts import ChatterboxTTS
        # Thread count is a MEASURED choice, not cpu_count: on the
        # 1.5-core-capped dev VM, T3 decoding cost per token was
        # 2.51 s at 4 threads vs 0.61 s at 2 and 0.48 s at 1
        # (oversubscription thrash), while S3Gen's ~2 min fixed cost
        # per call barely moves (147/133/112 s at 1/2/4 threads).
        # 2 is the balanced default; DIVYA_CLONE_THREADS overrides.
        torch.set_num_threads(max(1, int(
            os.environ.get("DIVYA_CLONE_THREADS", "2"))))
        self.model = ChatterboxTTS.from_pretrained(device=self.device)
        self._has_prepare = hasattr(self.model, "prepare_conditionals")

    def generate(self, text, ref_wav, exaggeration=EXAGGERATION,
                 cfg_weight=0.5):
        """One chunk -> a wav tensor [1, N] at ENGINE_SR."""
        self._load()
        kw = {"exaggeration": exaggeration, "cfg_weight": cfg_weight}
        if self._has_prepare:
            if self._conds_ref != ref_wav:
                self.model.prepare_conditionals(ref_wav)
                self._conds_ref = ref_wav
            return self.model.generate(text, **kw)
        return self.model.generate(text, audio_prompt_path=ref_wav, **kw)


_ENGINE = None


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = CloneEngine()
    return _ENGINE


def _save_wav(path, wav_tensor, sr):
    """Write a [1, N] float tensor as a 16-bit PCM WAV.

    soundfile, NOT torchaudio.save: torchaudio >= 2.9 delegates
    save() to TorchCodec (a separate, version-locked package) and
    raises ImportError without it — that killed the first v83 proof
    run AFTER a full generation. soundfile ships with librosa,
    which Chatterbox already requires."""
    import soundfile as sf
    data = wav_tensor.detach().cpu().float().numpy()
    if data.ndim == 2:
        data = data[0]
    sf.write(path, data, sr, subtype="PCM_16")


# The most recent line's pace-guard record (see synth_wav's "pace").
# doc.synth_voice reads this after each clone line and files it in
# the job artifacts — what correction was applied is never silent.
LAST_PACE = None


def synth_wav(text, ref_wav, out_wav, lang="en", engine=None):
    """Synthesise `text` in the voice of `ref_wav` -> out_wav (24 kHz
    mono wav, NOT yet loudness-normalised). English only: Chatterbox's
    English model has no Telugu/Hindi — anything else raises, so the
    caller can never fake a language the clone cannot speak.
    Returns {"duration_s", "chunks", "gen_s", "pace"} where "pace"
    records the delivery-lock verdict and any correction applied
    ("none" | "regen" | "regen+atempo" | "unmeasured")."""
    if str(lang or "en").lower() not in ("en", "en-in", "en-us", "en-gb"):
        raise ValueError(f"clone engine speaks English only, not {lang!r}")
    if not os.path.exists(ref_wav):
        raise FileNotFoundError(f"clone reference not found: {ref_wav}")
    units = _generation_units(text)
    if not units:
        raise ValueError("clone synth: empty text")
    import torch
    eng = engine or get_engine()
    t0 = time.time()
    os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)

    def _render():
        parts = []
        for unit_text, gap_s in units:
            wav = eng.generate(unit_text, ref_wav)
            if wav.dim() == 1:
                wav = wav.unsqueeze(0)
            arr = _squash_gaps_np(
                wav.detach().cpu().float().numpy()[0], ENGINE_SR)
            parts.append(torch.from_numpy(arr).unsqueeze(0))
            if gap_s > 0:
                parts.append(torch.zeros(1, int(gap_s * ENGINE_SR)))
        _save_wav(out_wav, torch.cat(parts, dim=-1), ENGINE_SR)

    _render()
    # ---- pace guard: onset rate within ±15% of the reference's ----
    pace = {"action": "unmeasured"}
    try:
        try:
            ref_rate = onset_rate(ref_wav)
        except Exception:
            ref_rate = FALLBACK_REF_ONSET_RATE
        rate = onset_rate(out_wav)
        pace = {"ref_rate": round(ref_rate, 2), "rate": round(rate, 2),
                "action": "none"}
        verdict = pace_verdict(rate, ref_rate)
        if not verdict["in_band"]:
            _render()  # ONE regeneration — the engine is stochastic
            rate = onset_rate(out_wav)
            pace["rate_after_regen"] = round(rate, 2)
            verdict = pace_verdict(rate, ref_rate)
            if verdict["in_band"]:
                pace["action"] = "regen"
            else:
                _atempo_inplace(out_wav, verdict["atempo"])
                pace["action"] = "regen+atempo"
                pace["atempo"] = verdict["atempo"]
                pace["rate_final"] = round(onset_rate(out_wav), 2)
    except Exception as e:  # measurement must never kill a synth
        pace = {"action": "unmeasured", "error": str(e)[:120]}
    return {"duration_s": round(probe_duration(out_wav), 3),
            "chunks": len(units), "gen_s": round(time.time() - t0, 2),
            "pace": pace}


def synth_to_file(text, ref_wav, out, lang="en"):
    """doc.synth_voice's clone route: synth -> loudnorm to the
    pipeline's -14 LUFS target -> write `out` (mp3/wav by extension).
    Returns estimated word timings [(start, dur, word)]; the line's
    pace-guard record is left in LAST_PACE for the job artifacts."""
    global LAST_PACE
    tmp = os.path.splitext(out)[0] + ".clone-raw.wav"
    info = synth_wav(text, ref_wav, tmp, lang=lang)
    LAST_PACE = {"text": str(text)[:80], **info["pace"]}
    try:
        _loudnorm_to(tmp, out)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return estimate_word_timings(text, probe_duration(out))


# ----------------- CLI (proof + debugging) -----------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Clone-TTS one line")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="en")
    a = ap.parse_args()
    t0 = time.time()
    info = synth_wav(a.text, a.ref, a.out + ".raw.wav", lang=a.lang)
    _loudnorm_to(a.out + ".raw.wav", a.out)
    os.remove(a.out + ".raw.wav")
    print(json.dumps({"out": a.out, "wall_s": round(time.time() - t0, 2),
                      **info}))
