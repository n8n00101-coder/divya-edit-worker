"""v99: Julie's FIXED Telugu house voice — IndicF5 + the engine's ship bar.

WHY THIS EXISTS (Ajju, 2026-11-16): the WHO TAUGHT US Telugu voice was
solved in the julie-ai-voice-engine repo (fixed13, the first Telugu
ear-pass: "Eee rendi voices ok") and Ajju ordered it wired into Julie:
"ee voice ni julie ki use cheyamani chepu". This module is that wiring
for the edit runner. Telugu jobs whose voice is the house voice
("tripti") route here instead of a built-in edge-tts voice.

THE VOICE (locked, do not re-tune casually):
  engine  IndicF5 (AI4Bharat, MIT) zero-shot clone, run LOCALLY on the
          runner (the HF Space has no speed parameter; the fixed10
          speed calibration needs the local model's config.speed).
  refs    voices/telugu-fixed/natspan2.wav (default) + natspan3.wav —
          Demucs-cleaned NATURAL-pace Telugu Part 2 vocals, copied from
          the engine repo's canonical voice/refs/ (fixed13). Every ref
          before fixed13 came from a 1.4705x time-SQUEEZED copy of the
          narration and failed the owner's ear; these did not.
  speed   per-ref anchors from the engine's settings
          (telugu_indicf5.speed_anchors): natspan2 = 1.0 (lands in the
          pace band uncorrected), natspan3 = 0.81. Between rolls the
          speed is recalibrated from the measured pace (duration
          scales ~1/speed — the fixed10 rule).

SELF-CORRECTION (the owner's "zero word mistakes" order): every
sentence is generated as ONE WHOLE TAKE — never split, never spliced —
and gated by the engine's OWN ship bar, imported from the
julie-ai-voice-engine checkout (single source of truth; this module
does not re-implement the gates): gate 1 (no-hint language) + gate 2
(ghost scan) + Resemblyzer identity >= 0.85 + pace 1.9-2.5 wps, all on
the same take, via gates.run_all_gates + engine.ship_decision. A
sentence with no passing take in MAX_ROLLS rolls raises: the job fails
honestly and NO other voice is substituted, ever.

ENGINE LOOKUP (mirrors voice_job.py's ./engine pattern): the engine
checkout is found via (1) env JULIE_VOICE_ENGINE_DIR, (2) ./engine
next to this file (edit.yml checks it out, like voice.yml), (3) the
dev-VM clone ~/workspace/julie-ai-voice-engine. Missing -> RuntimeError.

DEPS: torch/transformers/faster-whisper/resemblyzer are NOT in
edit.yml's base install (only Telugu house-voice jobs need them), so
they are imported lazily and bootstrapped ONCE per job with the
teltest.yml-proven pins when missing. Bootstrap failure -> RuntimeError
with the missing piece named.

CONTRACT (mirrors clone_tts.synth_to_file): synth_to_file(text, out)
writes the mp3 and returns estimated word timings
[(start, dur, word), ...]; per-sentence roll records land in
LAST_TELUGU for the job record (doc.synth_voice drains it, the way it
files clone_tts.LAST_PACE).
"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REFS_DIR = os.path.join(HERE, "voices", "telugu-fixed")
SR = 24000
MAX_ROLLS = 6            # the engine's gates.max_rolls
PACE_TARGET_WPS = 2.2    # centre of the 1.9-2.5 ship band (her pace)
SPEED_MIN, SPEED_MAX = 0.5, 1.3
TARGET_LUFS = -14.0      # doc.py final-mix loudnorm class target

LAST_TELUGU = []         # per-sentence records of the last synth call

_SENTENCE_RE = re.compile(r"(?<=[.!?…।])\s+")
_TE_BLOCK = re.compile(r"[ఀ-౿]")
_HI_BLOCK = re.compile(r"[ऀ-ॿ]")

# teltest.yml-proven pins (+ the gate stack). Installed lazily, once,
# only when a Telugu house-voice job actually needs them.
_BOOTSTRAP = [
    [sys.executable, "-m", "pip", "install", "-q",
     "torch==2.6.0", "torchaudio==2.6.0",
     "--index-url", "https://download.pytorch.org/whl/cpu"],
    [sys.executable, "-m", "pip", "install", "-q",
     "git+https://github.com/ai4bharat/IndicF5.git",
     "transformers==4.49.0", "numpy<2", "soundfile", "datasets<3.2",
     "huggingface_hub<0.30", "pyarrow<18",
     "faster-whisper", "resemblyzer==0.1.4"],
]


# ------------------------------------------------------------------
# pure helpers (no ML stack — unit-testable)
# ------------------------------------------------------------------
def split_sentences(text):
    """Whole sentences only. A sentence is the smallest generation
    unit: the fixed voice NEVER generates inside a sentence, so this
    split is the only segmentation synth_to_file ever applies."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    return [p.strip() for p in _SENTENCE_RE.split(text) if p.strip()]


def detect_script_lang(text):
    """'te' / 'hi' when the text is written in that script, else None.
    Used to route a house-voice line whose job ref carries no lang."""
    text = str(text or "")
    if _TE_BLOCK.search(text):
        return "te"
    if _HI_BLOCK.search(text):
        return "hi"
    return None


def adjust_speed(speed, wps, target=PACE_TARGET_WPS):
    """Pure: the next roll's speed after a pace miss. IndicF5 duration
    scales ~1/speed, so wps scales ~speed: move speed by
    target/measured, damped to [0.8, 1.25] per step and clamped to
    [SPEED_MIN, SPEED_MAX] overall. wps None -> keep the speed."""
    if not wps or wps <= 0:
        return speed
    factor = max(0.8, min(1.25, target / float(wps)))
    return max(SPEED_MIN, min(SPEED_MAX, speed * factor))


def load_refs():
    with open(os.path.join(REFS_DIR, "refs.json"), encoding="utf-8") as fh:
        idx = json.load(fh)
    name = idx.get("default", "natspan2")
    ref = idx["refs"][name]
    return name, os.path.join(HERE, ref["wav"]), ref["text"], \
        float(idx.get("speed_anchors", {}).get(name, 1.0))


# ------------------------------------------------------------------
# engine checkout (the gates' single source of truth)
# ------------------------------------------------------------------
def engine_dir():
    """Where the julie-ai-voice-engine checkout lives, in order:
    (1) env JULIE_VOICE_ENGINE_DIR; (2) ./engine next to this file
    (the voice.yml / edit.yml checkout); (3) the dev-VM clone."""
    env = os.environ.get("JULIE_VOICE_ENGINE_DIR")
    if env and os.path.isfile(os.path.join(env, "engine.py")):
        return env
    sib = os.path.join(HERE, "engine")
    if os.path.isfile(os.path.join(sib, "engine.py")):
        return sib
    dev = os.path.expanduser("~/workspace/julie-ai-voice-engine")
    if os.path.isfile(os.path.join(dev, "engine.py")):
        return dev
    return None


def _load_engine():
    d = engine_dir()
    if d is None:
        raise RuntimeError(
            "telugu fixed voice: julie-ai-voice-engine checkout not "
            "found (looked in $JULIE_VOICE_ENGINE_DIR, ./engine, "
            "~/workspace/julie-ai-voice-engine) — the ship gates live "
            "in the engine repo and are never re-implemented here")
    if d not in sys.path:
        sys.path.insert(0, d)
    import engine as voice_engine
    import gates as voice_gates
    return voice_engine, voice_gates


# ------------------------------------------------------------------
# lazy ML stack
# ------------------------------------------------------------------
def _ensure_deps():
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        import soundfile  # noqa: F401
        import faster_whisper  # noqa: F401
        import resemblyzer  # noqa: F401
        return
    except ImportError:
        pass
    print("indicf5_tts: bootstrapping Telugu voice deps (one-time "
          "per job)…", flush=True)
    for cmd in _BOOTSTRAP:
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(
                "telugu fixed voice: dependency bootstrap failed: "
                + (p.stderr or p.stdout)[-300:])
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        import soundfile  # noqa: F401
        import faster_whisper  # noqa: F401
        import resemblyzer  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            f"telugu fixed voice: dependency still missing after "
            f"bootstrap: {e}")


_MODEL = None


def _load_model():
    global _MODEL
    if _MODEL is None:
        _ensure_deps()
        import torch
        from transformers import AutoModel
        torch.set_num_threads(os.cpu_count() or 4)
        _MODEL = AutoModel.from_pretrained(
            "Aditya02/IndicF5", trust_remote_code=True)
    return _MODEL


def _synth_raw(model, text, ref_wav, ref_text, speed, out_wav):
    """ONE whole take at the given generation speed -> out_wav."""
    import numpy as np
    import soundfile as sf
    model.config.speed = speed  # forward() reads config at call time
    audio = model(text, ref_audio_path=ref_wav, ref_text=ref_text)
    if getattr(audio, "dtype", None) is not None and \
            audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    audio = np.array(audio, dtype=np.float32)
    sf.write(out_wav, audio, SR)
    return len(audio) / SR


# ------------------------------------------------------------------
# per-sentence self-correction loop
# ------------------------------------------------------------------
def _voice_sentence(model, gates, engine, settings, sent, ref_wav,
                    ref_text, speed0, workdir, tag):
    """Roll whole takes of ONE sentence until the engine's ship bar
    passes; recalibrate speed from measured pace between rolls.
    Returns (take_wav, record). Raises when the budget runs out —
    a failed take is never shipped."""
    speed = speed0
    record = {"sentence": tag, "rolls": [], "speed_start": speed0}
    for roll in range(1, MAX_ROLLS + 1):
        take = os.path.join(workdir, f"{tag}_r{roll}.wav")
        dur = _synth_raw(model, sent, ref_wav, ref_text, speed, take)
        rep = gates.run_all_gates(take, "te", sent, settings)
        ship, extra = engine.ship_decision(take, "te", sent, settings,
                                           rep)
        entry = {"roll": roll, "speed": round(speed, 3),
                 "duration_s": round(dur, 2), "ship": bool(ship),
                 **({k: extra[k] for k in
                     ("identity", "pace_wps", "identity_pass",
                      "pace_pass") if k in extra} or {})}
        record["rolls"].append(entry)
        print(f"indicf5_tts {tag} roll {roll}: speed={speed:.2f} "
              f"dur={dur:.2f}s ship={ship} "
              f"id={entry.get('identity')} wps={entry.get('pace_wps')}",
              flush=True)
        if ship:
            record["chosen_roll"] = roll
            record["speed_final"] = round(speed, 3)
            return take, record
        if extra.get("pace_wps"):
            speed = adjust_speed(speed, extra["pace_wps"])
    raise RuntimeError(
        f"telugu fixed voice: sentence {tag} never passed the ship "
        f"bar in {MAX_ROLLS} whole-take rolls — shipping nothing "
        f"(rolls: {record['rolls']})")


def _assemble(take_paths, out, settings):
    """Join chosen whole takes with the engine's locked sentence gap
    (digital silence), plain-gain level match to the median RMS, ONE
    loudnorm to the pipeline target. No inside-sentence edits."""
    import numpy as np
    import soundfile as sf
    gap_s = float(settings.get("assembly", {}).get("sentence_gap_s", 0.6))
    gap = np.zeros(int(gap_s * SR), dtype=np.float32)
    takes = []
    for p in take_paths:
        y, sr = sf.read(p)
        if sr != SR:
            raise RuntimeError(f"take {p} at {sr} Hz, expected {SR}")
        takes.append(np.asarray(y, dtype=np.float32))
    rms = [float(np.sqrt(np.mean(y ** 2))) if len(y) else 0.0
           for y in takes]
    live = sorted(r for r in rms if r > 0)
    med = live[len(live) // 2] if live else 0.0
    parts = []
    for i, y in enumerate(takes):
        if med > 0 and rms[i] > 0:
            y = y * (med / rms[i])
        parts.append(y)
        if i < len(takes) - 1:
            parts.append(gap)
    full = np.concatenate(parts) if parts else gap[:0]
    tmp = tempfile.mktemp(suffix=".wav")
    sf.write(tmp, full, SR)
    try:
        p = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", tmp,
             "-af", f"loudnorm=I={TARGET_LUFS}:TP=-1.0:LRA=11",
             "-ar", "44100", out],
            capture_output=True, text=True)
        if p.returncode != 0 or not os.path.exists(out):
            raise RuntimeError(
                "telugu fixed voice: loudnorm/encode failed: "
                + (p.stderr or "")[-300:])
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return len(full) / SR


def synth_to_file(text, out, lang="te"):
    """Synthesise `text` in the FIXED Telugu house voice -> mp3 at
    `out`; returns estimated word timings (clone_tts contract).
    Telugu only: any other language raises — the house clone's
    English route stays in clone_tts, and there is no Hindi clone."""
    global LAST_TELUGU
    if lang != "te":
        raise RuntimeError(
            f"indicf5_tts serves the fixed Telugu voice only, not "
            f"{lang!r} — no fallback voice is substituted")
    sentences = split_sentences(text)
    if not sentences:
        return []
    engine, gates = _load_engine()
    settings = engine.load_settings()
    ref_name, ref_wav, ref_text, anchor = load_refs()
    if not os.path.exists(ref_wav):
        raise RuntimeError(
            f"telugu fixed voice: canonical ref missing at {ref_wav}")
    model = _load_model()
    LAST_TELUGU = []
    workdir = tempfile.mkdtemp(prefix="julie_te_voice_")
    chosen = []
    for i, sent in enumerate(sentences, start=1):
        take, record = _voice_sentence(
            model, gates, engine, settings, sent, ref_wav, ref_text,
            anchor, workdir, f"s{i}")
        record["ref"] = ref_name
        LAST_TELUGU.append(record)
        chosen.append(take)
    total = _assemble(chosen, out, settings)
    import clone_tts
    return clone_tts.estimate_word_timings(text, total)
