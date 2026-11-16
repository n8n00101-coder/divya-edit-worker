"""beatgrid.py — Julie: beat grid for music-driven cutting.

Given an audio file, return a JSON-able dict:

    {"bpm": float, "beats": [t, ...], "bars": [t, ...],
     "beat_count": int, "duration": float, "method": str}

`bars` are 4/4 bar boundaries (every 4th beat, starting on beat 0),
so the Director can place cuts on bars.

Engine: librosa when importable; otherwise a self-contained
numpy/scipy fallback (this environment has NO librosa, so the
fallback is the production path here):

1. decode to mono wav via ffmpeg, read with the stdlib `wave` module;
2. onset envelope = spectral flux of an STFT magnitude spectrogram
   (Hann window, 2048/512) — clicks and drum hits spike it;
3. tempo = peak of the onset envelope's autocorrelation over lags
   corresponding to 40–240 BPM, with an octave preference for the
   70–180 BPM band and parabolic refinement;
4. phase = the offset within one period that maximises the summed
   onset strength on the beat positions; beats are then laid out
   every period from that phase.
"""

import json
import subprocess
import tempfile
import os
import wave

import numpy as np

MIN_BPM, MAX_BPM = 40.0, 240.0


def _decode_wav(path):
    """Decode any audio file to (samples float32 mono, sample_rate)."""
    with tempfile.TemporaryDirectory(prefix="bg_") as td:
        wav_path = os.path.join(td, "audio.wav")
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(path),
             "-ac", "1", "-ar", "22050", wav_path],
            capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not os.path.exists(wav_path):
            raise RuntimeError(
                f"ffmpeg decode failed: {(r.stderr or '')[:120]}")
        with wave.open(wav_path, "rb") as w:
            sr = w.getframerate()
            n = w.getnframes()
            raw = w.readframes(n)
            sampwidth = w.getsampwidth()
    if sampwidth == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:  # 8-bit unsigned
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
             - 128.0) / 128.0
    return x, sr


def _onset_envelope(x, sr, hop=512, win=2048):
    """Spectral-flux onset envelope; returns (env, frame_seconds)."""
    if len(x) < win:
        x = np.pad(x, (0, win - len(x)))
    window = np.hanning(win).astype(np.float32)
    n_frames = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = x[idx] * window
    mag = np.abs(np.fft.rfft(frames, axis=1))
    mag = np.log1p(10.0 * mag)
    flux = np.zeros(n_frames, dtype=np.float64)
    diff = np.diff(mag, axis=0)
    flux[1:] = np.maximum(diff, 0).sum(axis=1)
    # normalise: robust scale, keep clicks prominent
    med = np.median(flux)
    flux = np.maximum(flux - med, 0)
    peak = flux.max()
    if peak > 0:
        flux = flux / peak
    return flux, hop / sr


def _estimate_tempo(env, frame_s):
    """Autocorrelation tempo. Returns (bpm, period_frames_float)."""
    env = env - env.mean()
    n = len(env)
    corr = np.correlate(env, env, mode="full")[n - 1:]
    corr = corr / (corr[0] if corr[0] > 0 else 1.0)
    min_lag = max(1, int(round(60.0 / MAX_BPM / frame_s)))
    max_lag = min(n - 1, int(round(60.0 / MIN_BPM / frame_s)))
    if max_lag <= min_lag:
        return 120.0, 60.0 / 120.0 / frame_s
    seg = corr[min_lag:max_lag + 1].copy()
    # octave preference: mild boost for lags in the 70–180 BPM band
    lags = np.arange(min_lag, max_lag + 1)
    bpms = 60.0 / (lags * frame_s)
    seg *= np.where((bpms >= 70) & (bpms <= 180), 1.15, 1.0)
    best = int(np.argmax(seg)) + min_lag
    # parabolic refinement around the peak
    if 0 < best - min_lag < len(seg) - 1:
        a, b, c = seg[best - min_lag - 1], seg[best - min_lag], \
            seg[best - min_lag + 1]
        denom = a - 2 * b + c
        if denom != 0:
            shift = 0.5 * (a - c) / denom
            period = best + float(np.clip(shift, -0.5, 0.5))
        else:
            period = float(best)
    else:
        period = float(best)
    # Half-tempo disambiguation: a periodic train autocorrelates
    # almost as well at TWICE the true period (every other beat
    # still aligns, and the double lag often lands nearer an integer
    # frame count, so it can win outright). If the correlation at
    # half the chosen period is nearly as strong (>=80%), the true
    # beat is the half period — for a genuinely slow track the
    # half-lag lands BETWEEN beats and correlates ~0, so this is
    # safe. Interpolated, because the half period is fractional.
    def _corr_at(lag_f):
        lo = int(np.floor(lag_f))
        hi = min(lo + 1, len(corr) - 1)
        frac = lag_f - lo
        return corr[lo] * (1 - frac) + corr[hi] * frac

    for _ in range(2):
        half = period / 2.0
        if half < min_lag:
            break
        if _corr_at(half) >= 0.80 * _corr_at(period):
            period = half
        else:
            break
    return 60.0 / (period * frame_s), period


def _phase_and_beats(env, period_frames, frame_s, duration):
    """Pick the phase maximising onset strength on beat positions."""
    period = float(period_frames)
    best_phase, best_score = 0.0, -1.0
    steps = max(8, int(round(period)))
    for i in range(steps):
        phase = period * i / steps
        pos = np.arange(phase, len(env), period)
        if len(pos) < 2:
            continue
        idx = np.clip(np.round(pos).astype(int), 0, len(env) - 1)
        # small neighbourhood max tolerates hop quantisation
        score = 0.0
        for j in idx:
            score += env[max(0, j - 1):j + 2].max()
        score /= len(idx)
        if score > best_score:
            best_score, best_phase = score, phase
    beats = []
    t = best_phase * frame_s
    step = period * frame_s
    while t < duration:
        beats.append(round(float(t), 4))
        t += step
    return beats


def _grid_numpy(path):
    x, sr = _decode_wav(path)
    duration = len(x) / sr
    env, frame_s = _onset_envelope(x, sr)
    bpm, period = _estimate_tempo(env, frame_s)
    beats = _phase_and_beats(env, period, frame_s, duration)
    return bpm, beats, duration, "numpy-spectral-flux"


def _grid_librosa(path):
    import librosa
    y, sr = librosa.load(str(path), sr=22050, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="time")
    bpm = float(np.atleast_1d(tempo)[0])
    beats = [round(float(t), 4) for t in np.atleast_1d(beat_frames)]
    return bpm, beats, len(y) / sr, "librosa"


def beat_grid(path, beats_per_bar=4):
    """Full grid dict for one audio file. Raises on undecodable audio."""
    try:
        import librosa  # noqa: F401
        bpm, beats, duration, method = _grid_librosa(path)
    except ImportError:
        bpm, beats, duration, method = _grid_numpy(path)
    beats = sorted(float(b) for b in beats)
    bars = [beats[i] for i in range(0, len(beats), int(beats_per_bar))]
    return {
        "bpm": round(float(bpm), 2),
        "beats": beats,
        "bars": bars,
        "beat_count": len(beats),
        "duration": round(float(duration), 4),
        "method": method,
    }


# backwards/forwards-friendly alias
analyse = beat_grid
detect_beats = beat_grid


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(beat_grid(sys.argv[1]), indent=1))
    else:
        print("beatgrid: pass an audio file path")
