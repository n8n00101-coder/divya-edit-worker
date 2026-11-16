"""v99 tests: Julie's FIXED Telugu house voice (indicf5_tts).

Ajju (2026-11-16): the fixed13 ear-approved Telugu voice from the
julie-ai-voice-engine becomes Julie's Telugu voice. Covered here,
WITHOUT the ML stack (torch/whisper/resemblyzer stay uninstalled —
the heavy paths are stubbed or fail-honest):

  1. indicf5_tts pure helpers: whole-sentence splitting (never
     inside a sentence), script-language detection, the speed
     recalibration math, the shipped canonical refs (natspan2
     default, anchor 1.0, wav on disk).
  2. Engine lookup order (env -> ./engine -> dev clone) and the
     honest raise when a non-Telugu language is asked of the module.
  3. doc routing: a Telugu line under voice "tripti" routes to a
     stubbed indicf5_tts (records filed into CLONE_PACE_RECORDS);
     a Hindi line raises honestly; the English clone path is the
     v83 behaviour (covered by v83test).
  4. doc default: the make_video voice block defaults a spec-silent
     Telugu job to "tripti" (source-level, like v83test's checks).
  5. spec gate: Tripti + Telugu resolves via indicf5-fixed and
     passes capability_check; Tripti + Hindi stops upfront.

Run: python3 v99test.py   (exit 0 = all pass)
"""
import asyncio
import os
import sys
import types
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import indicf5_tts  # noqa: E402
import doc  # noqa: E402
import spec_engine as se  # noqa: E402

fails = []


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


TE_LINE = "మీరు నిద్రలోకి జారుకున్న క్షణం నుంచి, మీ మెదడు పని ఆపదు."
TE_TWO = TE_LINE + " నిజానికి, దాని అసలు పని అప్పుడే మొదలవుతుంది."
HI_LINE = "आप क्या सोचते हैं?"

# ---------------------------------------------------------------- 1. pure
sents = indicf5_tts.split_sentences(TE_TWO)
ok("split: two whole sentences", sents == [TE_LINE, TE_TWO[len(TE_LINE) + 1:]])
ok("split: a lone sentence is never cut", indicf5_tts.split_sentences(TE_LINE) == [TE_LINE])
ok("split: empty text -> []", indicf5_tts.split_sentences("  ") == [])
ok("detect: Telugu script -> te", indicf5_tts.detect_script_lang(TE_LINE) == "te")
ok("detect: Devanagari -> hi", indicf5_tts.detect_script_lang(HI_LINE) == "hi")
ok("detect: Latin -> None", indicf5_tts.detect_script_lang("Hello there.") is None)

ok("speed: too-fast take slows down",
   abs(indicf5_tts.adjust_speed(1.0, 2.6) - 2.2 / 2.6) < 1e-9)
ok("speed: too-slow take speeds up, damped",
   abs(indicf5_tts.adjust_speed(1.0, 1.0) - 1.25) < 1e-9)
ok("speed: unmeasured pace keeps the speed",
   indicf5_tts.adjust_speed(0.9, None) == 0.9)
ok("speed: clamped to the floor",
   indicf5_tts.adjust_speed(0.55, 4.0) == indicf5_tts.SPEED_MIN)

name, wav, text, anchor = indicf5_tts.load_refs()
ok("refs: default is natspan2", name == "natspan2")
ok("refs: natspan2 wav ships in the repo", os.path.exists(wav))
ok("refs: natspan2 anchor is 1.0 (lands in band uncorrected)", anchor == 1.0)
ok("refs: ref text is the crime-stats passage", "128.6" in text)

# ---------------------------------------------------------------- 2. engine
saved_env = os.environ.get("JULIE_VOICE_ENGINE_DIR")
os.environ["JULIE_VOICE_ENGINE_DIR"] = HERE  # no engine.py here -> falls through
ok("engine: a bogus env dir is ignored, a real one is found",
   indicf5_tts.engine_dir() is not None
   and os.path.isfile(os.path.join(indicf5_tts.engine_dir(), "engine.py")))
if saved_env is None:
    del os.environ["JULIE_VOICE_ENGINE_DIR"]
else:
    os.environ["JULIE_VOICE_ENGINE_DIR"] = saved_env

try:
    indicf5_tts.synth_to_file(HI_LINE, "/tmp/v99.mp3", lang="hi")
    ok("module: Hindi raises", False)
except RuntimeError as e:
    ok("module: Hindi raises honestly (no substitution)",
       "no fallback" in str(e))

# ---------------------------------------------------------------- 3. doc route
calls = {}
stub = types.ModuleType("indicf5_tts")
stub.detect_script_lang = indicf5_tts.detect_script_lang
stub.LAST_TELUGU = [{"sentence": "s1", "chosen_roll": 2, "ref": "natspan2"}]


def fake_synth(text, out, lang="te"):
    calls.update(text=text, out=out, lang=lang)
    Path(out).write_bytes(b"ID3")
    return [(0.0, 0.4, w) for w in text.split()]


stub.synth_to_file = fake_synth
saved_mod = sys.modules.get("indicf5_tts")
sys.modules["indicf5_tts"] = stub
try:
    doc.CLONE_PACE_RECORDS.clear()
    words, vused = asyncio.run(
        doc.synth_voice(TE_LINE, "tripti", "calm", "/tmp/v99_vo.mp3"))
    ok("doc: Telugu line routes to indicf5_tts", calls.get("lang") == "te")
    ok("doc: route returns the house voice id", vused == "tripti")
    ok("doc: word timings come back", len(words) == len(TE_LINE.split()))
    ok("doc: roll records filed for the job artifacts",
       len(doc.CLONE_PACE_RECORDS) == 1
       and doc.CLONE_PACE_RECORDS[0]["lang"] == "te"
       and doc.CLONE_PACE_RECORDS[0]["chosen_roll"] == 2)
    try:
        asyncio.run(doc.synth_voice(HI_LINE, "tripti", "calm", "/tmp/v99_vo.mp3"))
        ok("doc: Hindi line raises", False)
    except RuntimeError as e:
        ok("doc: Hindi line raises honestly", "no hi clone" in str(e))
finally:
    if saved_mod is not None:
        sys.modules["indicf5_tts"] = saved_mod

# ---------------------------------------------------------------- 4. default
_src = Path(os.path.join(HERE, "doc.py")).read_text(encoding="utf-8")
ok("doc: spec-silent Telugu jobs default to the fixed voice",
   'if p["lang"] == "te":\n            voice = "tripti"' in _src)

# ---------------------------------------------------------------- 5. spec gate
spec = se.extract_spec("make a video in Telugu, Tripti voice")
cfg = se.resolve_render_config(spec, "short")
ok("spec: Tripti + Telugu resolves to the house voice", cfg["voice_id"] == "tripti")
ok("spec: voice_choice names the indicf5-fixed engine",
   (cfg.get("voice_choice") or {}).get("engine") == "indicf5-fixed")
ok("spec: capability_check passes Tripti + Telugu",
   se.capability_check(spec, "short") == [])

spec = se.extract_spec("make a video in Hindi, Tripti voice")
probs = se.capability_check(spec, "short")
ok("spec: Tripti + Hindi stops upfront", len(probs) == 1)

print("v99 tests:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
