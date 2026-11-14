"""v83 tests: the Tripti house CLONE voice (Chatterbox via clone_tts).

1. clone_tts.split_text — sentence packing under the cap, clause and
   word fallbacks for over-long sentences, empty text.
2. clone_tts.estimate_word_timings — count, monotonic starts, total
   duration conserved, sentence-final words get more time.
3. clone_tts.synth_wav guards fire BEFORE any engine load: a
   non-English language raises (the clone cannot speak Telugu —
   never faked), a missing reference raises.
4. doc: CLONE_VOICES registry; _clone_ref_path precedence (the job's
   refvoice asset for this voice > env override > house library; a
   USER ref asset without the voice marker never hijacks the house
   voice); synth_voice routes "tripti" to a stubbed clone_tts and
   returns voice id "tripti"; a missing reference raises honestly;
   the plain edge path is untouched.
5. spec_engine: "Tripti voice" PASSES the gate as a routable named
   (clone) voice, fixes narration language to English, records
   voice_choice via=clone; Tripti + Telugu narration stops upfront
   with the honest alternative; Telugu voice still routes to the
   Telugu built-in; an unknown named voice still stops.
6. Delivery lock: split_phrases boundaries + join gaps (pauses only
   where natural phrase boundaries are), pace_verdict band/clamps,
   exaggeration locked at 0.35, and synth_voice files each line's
   pace record into doc.CLONE_PACE_RECORDS for the job artifacts.

No network, no torch, no edge-tts. Run: python v83test.py
"""

import asyncio
import os
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import clone_tts
import doc
import spec_engine as se

fails = []


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- 1. chunking
ch = clone_tts.split_text(
    "Is this entertainment or business? Today we follow the money. "
    "But a bill has two sides.")
ok("chunk: short text packs into one chunk", len(ch) == 1)
long_text = " ".join(f"Sentence number {i} is here to fill space." for i in range(30))
ch = clone_tts.split_text(long_text)
ok("chunk: long text -> multiple chunks", len(ch) > 1)
ok("chunk: every chunk within cap",
   all(len(c) <= clone_tts.MAX_CHUNK_CHARS for c in ch))
ok("chunk: no text lost", " ".join(ch).split() == long_text.split())
one_long = "word " * 200 + "end."
ch = clone_tts.split_text(one_long.strip())
ok("chunk: one over-long sentence splits at words",
   len(ch) > 1 and all(len(c) <= clone_tts.MAX_CHUNK_CHARS for c in ch))
ok("chunk: empty text -> []", clone_tts.split_text("  \n ") == [])

# ---------------------------------------------------------------- 2. timings
tw = clone_tts.estimate_word_timings("Hello world. This is a longer line!", 4.0)
ok("timings: one per word", len(tw) == 7)
ok("timings: starts monotonic",
   all(tw[i][0] < tw[i + 1][0] for i in range(len(tw) - 1)))
ok("timings: durations sum to total",
   abs(sum(d for _s, d, _w in tw) - 4.0) < 0.05)
ok("timings: sentence-final word gets pause weight",
   tw[1][1] > tw[0][1])  # "world." vs "Hello"
ok("timings: empty -> []", clone_tts.estimate_word_timings("", 3.0) == [])

# ------------------------------------------------- 2a. delivery lock
# phrase chunking (accent audit): pauses only at natural boundaries.
ph = clone_tts.split_phrases(
    "Is this entertainment or business? So today we follow the money.")
ok("phrases: her exact line -> 2 phrases", len(ph) == 2)
ok("phrases: question ends a sentence phrase",
   ph[0] == ("Is this entertainment or business?", "sentence"))
ok("phrases: last phrase is end", ph[-1][1] == "end")
ph = clone_tts.split_phrases(
    "Sleep is when your brain cleans itself, repairs the body, "
    "and files the whole day away.")
ok("phrases: commas are clause boundaries",
   [b for _p, b in ph] == ["clause", "clause", "end"])
ok("phrases: micro-fragments merge",
   clone_tts.split_phrases("Well, ok. Go.") == [("Well, ok. Go.", "end")])
ok("phrases: empty -> []", clone_tts.split_phrases("  ") == [])
units = clone_tts._generation_units(
    "Is this entertainment or business? So today we follow the money.")
ok("units: sentence join gap is the sentence gap",
   [g for _t, g in units] == [clone_tts.PHRASE_GAP_SENTENCE_S, 0.0])
units = clone_tts._generation_units(
    "Sleep is when your brain cleans itself, repairs the body, "
    "and files the whole day away.")
ok("units: clause joins are breaths, not pauses",
   [g for _t, g in units] == [clone_tts.PHRASE_GAP_CLAUSE_S,
                              clone_tts.PHRASE_GAP_CLAUSE_S, 0.0])

# internal-gap squash: the engine's invented mid-phrase pause dies,
# leading/trailing silence and short natural gaps survive.
import numpy as _np
_sr = 24000
_t = _np.arange(int(0.5 * _sr)) / _sr
_tone = (0.5 * _np.sin(2 * _np.pi * 200 * _t)).astype(_np.float32)
_quiet = (0.004 * _np.sin(2 * _np.pi * 200 *
          _np.arange(int(0.46 * _sr)) / _sr)).astype(_np.float32)
_x = _np.concatenate([_np.zeros(int(0.1 * _sr), dtype=_np.float32),
                      _tone, _quiet, _tone,
                      _np.zeros(int(0.1 * _sr), dtype=_np.float32)])
_y = clone_tts._squash_gaps_np(_x, _sr)
ok("squash: 0.46s internal gap cut to the kept 0.05s",
   abs(len(_y) / _sr - 1.25) < 0.03)
_q2 = (0.004 * _np.sin(2 * _np.pi * 200 *
       _np.arange(int(0.10 * _sr)) / _sr)).astype(_np.float32)
_x2 = _np.concatenate([_tone, _q2, _tone])
ok("squash: a 0.10s natural gap is untouched",
   len(clone_tts._squash_gaps_np(_x2, _sr)) == len(_x2))
ok("squash: pure silence passes through",
   len(clone_tts._squash_gaps_np(
       _np.zeros(_sr, dtype=_np.float32), _sr)) == _sr)

# pace guard verdicts (pure): band ±15% around the ref's 5.24/s.
ok("pace: in-band line passes untouched",
   clone_tts.pace_verdict(5.16, 5.24) == {"in_band": True, "atempo": 1.0})
_v = clone_tts.pace_verdict(4.00, 5.24)
ok("pace: the old slow line 1 is out of band",
   _v["in_band"] is False)
ok("pace: slow line's nudge clamps at 1.12x",
   _v["atempo"] == clone_tts.PACE_MAX_NUDGE)
_v = clone_tts.pace_verdict(7.0, 5.24)
ok("pace: fast line nudges down, clamped",
   _v["in_band"] is False
   and _v["atempo"] == round(1 / clone_tts.PACE_MAX_NUDGE, 3))
ok("pace: unmeasured never blocks",
   clone_tts.pace_verdict(0, 5.24)["in_band"] is True)
import inspect as _insp
ok("delivery: exaggeration locked at 0.35",
   clone_tts.EXAGGERATION == 0.35
   and _insp.signature(clone_tts.CloneEngine.generate)
       .parameters["exaggeration"].default == 0.35)

# ------------------------------------------------------- 2b. wav saving
# torchaudio >= 2.9 save() needs TorchCodec and raises without it —
# saves must go through clone_tts._save_wav (soundfile). Source-level
# guard: cheap, and it pins the regression that killed proof run 1.
_src = Path(clone_tts.__file__).read_text()
ok("save: _save_wav uses soundfile", "soundfile" in _src and "_save_wav" in _src)
ok("save: torchaudio.save never called", "torchaudio.save(" not in _src)
ok("save: thread default is measured (2), env-overridable",
   "DIVYA_CLONE_THREADS" in _src)

# ---------------------------------------------------------------- 3. guards
try:
    clone_tts.synth_wav("namaste", __file__, "/tmp/x.wav", lang="te")
    ok("guard: Telugu raises", False)
except ValueError:
    ok("guard: Telugu raises (clone speaks English only)", True)
try:
    clone_tts.synth_wav("hello", "/nonexistent/ref.wav", "/tmp/x.wav")
    ok("guard: missing ref raises", False)
except FileNotFoundError:
    ok("guard: missing ref raises FileNotFoundError", True)

# ---------------------------------------------------------------- 4. doc routing
ok("doc: tripti registered as an English clone voice",
   doc.CLONE_VOICES.get("tripti", {}).get("langs") == ("en",))
ok("doc: clone note names it honestly",
   doc.CLONE_VOICES["tripti"]["note"] == "tripti (clone of house sample)")

with tempfile.TemporaryDirectory() as td:
    asset = os.path.join(td, "asset.wav")
    Path(asset).write_bytes(b"RIFF")
    ok("refpath: job asset for this voice wins",
       doc._clone_ref_path("tripti", {"voice_id": "tripti", "path": asset}) == asset)
    os.environ["DIVYA_VOICE_REF_TRIPTI"] = "/env/ref.wav"
    ok("refpath: env override next",
       doc._clone_ref_path("tripti", None) == "/env/ref.wav")
    ok("refpath: a user ref (no voice marker) never hijacks",
       doc._clone_ref_path("tripti", {"path": asset}) == "/env/ref.wav")
    del os.environ["DIVYA_VOICE_REF_TRIPTI"]
    ok("refpath: house library default",
       doc._clone_ref_path("tripti", None).endswith("voice-lib/tripti/tripti-ref.wav"))

    # synth_voice with a stubbed clone_tts module
    calls = {}
    stub = types.ModuleType("clone_tts")
    def fake_synth_to_file(text, ref_path, out, lang="en"):
        calls.update(text=text, ref=ref_path, out=out, lang=lang)
        Path(out).write_bytes(b"ID3")
        return [(0.0, 0.4, w) for w in text.split()]
    stub.synth_to_file = fake_synth_to_file
    stub.LAST_PACE = {"text": "Hello there.", "action": "regen",
                      "ref_rate": 5.24, "rate": 4.31,
                      "rate_after_regen": 5.02}
    saved = sys.modules.get("clone_tts")
    sys.modules["clone_tts"] = stub
    try:
        refw = os.path.join(td, "tripti-ref.wav")
        Path(refw).write_bytes(b"RIFF")
        os.environ["DIVYA_VOICE_REF_TRIPTI"] = refw
        out = os.path.join(td, "vo0.mp3")
        doc.CLONE_PACE_RECORDS.clear()
        words, vused = asyncio.run(
            doc.synth_voice("Hello there.", "tripti", "calm", out))
        ok("synth: clone route returns voice id tripti", vused == "tripti")
        ok("synth: pace correction filed for the job artifacts",
           len(doc.CLONE_PACE_RECORDS) == 1
           and doc.CLONE_PACE_RECORDS[0]["action"] == "regen"
           and doc.CLONE_PACE_RECORDS[0]["voice"] == "tripti")
        ok("synth: clone route used the house ref", calls.get("ref") == refw)
        ok("synth: clone route wrote the scene file", os.path.exists(out))
        ok("synth: clone route returns word timings", len(words) == 2)
        os.environ["DIVYA_VOICE_REF_TRIPTI"] = os.path.join(td, "gone.wav")
        try:
            asyncio.run(doc.synth_voice("Hello.", "tripti", "calm", out))
            ok("synth: missing house ref raises", False)
        except RuntimeError as e:
            ok("synth: missing house ref raises honestly",
               "not attached" in str(e))
        del os.environ["DIVYA_VOICE_REF_TRIPTI"]
    finally:
        if saved is not None:
            sys.modules["clone_tts"] = saved

# the plain edge path is untouched: no ref -> tts() with the plan voice
async def _fake_tts(text, voice, mood, out, rate_add=0):
    return [(0.0, 0.4, w) for w in text.split()]
_saved_tts = doc.tts
doc.tts = _fake_tts
try:
    _w, _v = asyncio.run(doc.synth_voice(
        "Plain line.", "en-US-AvaMultilingualNeural", "calm", "/tmp/v83.mp3"))
    ok("synth: built-in voice path unchanged", _v == "en-US-AvaMultilingualNeural")
finally:
    doc.tts = _saved_tts

# ---------------------------------------------------------------- 5. spec gate
spec = se.extract_spec("make a 30 second video on sleep, Tripti voice")
cfg = se.resolve_render_config(spec, "short")
ok("spec: Tripti voice resolves to the clone id", cfg["voice_id"] == "tripti")
ok("spec: voice_choice records the clone route",
   (cfg.get("voice_choice") or {}).get("via") == "clone")
ok("spec: clone ask fixes narration language to English", cfg["lang"] == "en")
ok("spec: capability_check passes Tripti",
   se.capability_check(spec, "short") == [])

spec = se.extract_spec("make a video in Telugu, Tripti voice")
probs = se.capability_check(spec, "short")
ok("spec: Tripti + Telugu stops upfront",
   len(probs) == 1 and "English clone" in probs[0]["reason"])
ok("spec: the upfront line offers the honest alternative",
   "English narration in the Tripti voice" in se.upfront_line(probs))

spec = se.extract_spec("make a video, Telugu voice")
cfg = se.resolve_render_config(spec, "short")
ok("spec: Telugu voice still routes to the Telugu built-in",
   cfg["voice_id"] in ("te-IN-MohanNeural", "te-IN-ShrutiNeural"))

# an unknown NAMED voice (the LLM-extraction shape, as in v79test)
# still stops upfront — the clone registry did not open the gate.
spec = [{"id": "R1", "type": "voice", "value": "Rowan Telugu HD",
         "quote": "Rowan Telugu HD voice"}]
ok("spec: an unknown named voice still stops",
   len(se.capability_check(spec, "short")) == 1)

print("v83 tests:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
