"""v71 tests: reference voice — pace matching is PURE and honest.

1. pace_adjust_rate — the pure rate computation: ±5% deadband, linear
   correction, total clamp ±25, no-op on missing measurements.
2. _vo_wpm — pace measured from edge-tts word timings.
3. synth_voice with a stubbed tts: (a) no ref -> the old call, plan
   voice, one synth; (b) English ref + female voice -> the closest
   built-in (en-IN-NeerjaNeural) is picked; (c) pace converges toward
   the reference and stops at the ±25 clamp; (d) a non-English ref
   keeps the plan voice but still pace-matches.
4. make_video / long_video signatures accept ref_voice; doc3 (v3
   engine) deliberately does NOT grow synth_voice (runner guards on it).

No network, no edge-tts. Run: python v71test.py
"""

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import doc

fails = []


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- 1. pure
ok("pace: equal -> no change", doc.pace_adjust_rate(150, 150, 0) == 0)
ok("pace: within 5% -> no change", doc.pace_adjust_rate(150, 145, 3) == 3)
ok("pace: 100->150 clamps at +25", doc.pace_adjust_rate(150, 100, 0) == 25)
ok("pace: 150->120 = -20", doc.pace_adjust_rate(120, 150, 0) == -20)
ok("pace: cur respected (10 + 60 -> 25)", doc.pace_adjust_rate(160, 100, 10) == 25)
ok("pace: negative clamp (-10 - 50 -> -25)", doc.pace_adjust_rate(100, 200, -10) == -25)
ok("pace: missing ref -> cur", doc.pace_adjust_rate(0, 120, 7) == 7)
ok("pace: missing measured -> cur", doc.pace_adjust_rate(150, 0, -4) == -4)

# ---------------------------------------------------------------- 2. wpm
ok("wpm: 2 words in 1.0s = 120", doc._vo_wpm([(0.0, 0.5, "a"), (0.5, 0.5, "b")], "a b") == 120)
ok("wpm: empty -> 0", doc._vo_wpm([], "hello") == 0)

# ---------------------------------------------------------------- 3. synth
CALLS = []


async def fake_tts(text, voice, mood, out, rate_add=0):
    """Pace scales linearly with rate_add: 100 wpm at +0."""
    CALLS.append({"voice": voice, "rate_add": rate_add})
    wpm = 100 * (1 + rate_add / 100.0)
    ws = text.split()
    end = len(ws) / (wpm / 60.0)
    step = end / len(ws)
    return [(i * step, step, w) for i, w in enumerate(ws)]


real_tts = doc.tts
doc.tts = fake_tts
TEXT = " ".join(["word"] * 20)
try:
    CALLS.clear()
    words, v = asyncio.run(doc.synth_voice(TEXT, "en-US-AvaMultilingualNeural", "calm", "x.mp3", None))
    ok("synth no-ref: one call, plan voice, rate 0",
       len(CALLS) == 1 and CALLS[0]["voice"] == "en-US-AvaMultilingualNeural" and CALLS[0]["rate_add"] == 0 and v == "en-US-AvaMultilingualNeural")

    CALLS.clear()
    words, v = asyncio.run(doc.synth_voice(TEXT, "en-US-AvaMultilingualNeural", "calm", "x.mp3",
                                           {"path": "ref.audio", "wpm": 150, "lang": "en"}))
    ok("synth en-ref: closest voice = en-IN-NeerjaNeural", v == "en-IN-NeerjaNeural" and CALLS[0]["voice"] == "en-IN-NeerjaNeural")
    ok("synth en-ref: pace pushed to the +25 clamp in 2 synths",
       len(CALLS) == 2 and CALLS[-1]["rate_add"] == 25)

    CALLS.clear()
    words, v = asyncio.run(doc.synth_voice(TEXT, "en-US-AvaMultilingualNeural", "calm", "x.mp3",
                                           {"path": "ref.audio", "wpm": 100, "lang": "en"}))
    ok("synth en-ref at pace: single synth, still switches voice",
       len(CALLS) == 1 and v == "en-IN-NeerjaNeural")

    CALLS.clear()
    words, v = asyncio.run(doc.synth_voice(TEXT, "te-IN-ShrutiNeural", "calm", "x.mp3",
                                           {"path": "ref.audio", "wpm": 130, "lang": "te"}))
    ok("synth te-ref: plan voice kept, pace matched",
       v == "te-IN-ShrutiNeural" and len(CALLS) >= 2 and CALLS[-1]["rate_add"] == 25)

    CALLS.clear()
    words, v = asyncio.run(doc.synth_voice(TEXT, "en-US-AndrewMultilingualNeural", "calm", "x.mp3",
                                           {"path": "ref.audio", "wpm": 150, "lang": "en"}))
    ok("synth en-ref + male voice: no switch (female-only rule), pace matched",
       v == "en-US-AndrewMultilingualNeural" and CALLS[-1]["rate_add"] == 25)
finally:
    doc.tts = real_tts

# ---------------------------------------------------------------- 4. wiring
import inspect
ok("make_video takes ref_voice", "ref_voice" in inspect.signature(doc.make_video).parameters)
import long_video
ok("make_long_video takes ref_voice", "ref_voice" in inspect.signature(long_video.make_long_video).parameters)
ok("render_chapters takes ref_voice", "ref_voice" in inspect.signature(long_video.render_chapters).parameters)
import doc3
ok("doc3 has no synth_voice (runner capability guard excludes it)", not hasattr(doc3, "synth_voice"))
ok("voice note never claims a clone", "clone engine pending" in doc.VOICE_NOTE_REF and "same voice" not in doc.VOICE_NOTE_REF)

print("v71 tests:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
