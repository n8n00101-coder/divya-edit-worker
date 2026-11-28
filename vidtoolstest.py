"""vidtoolstest.py — rig for video_tools.py (scene list + word
transcript, tested on real footage 2026-11-28) + registry wiring
+ the ENGINE_CORE video-analysis rule.

  (a) scenes_from_boundaries: exact scenes, short-scene merge,
      out-of-range cuts dropped.
  (b) words_to_cues: exact cue text/timing, breaks on gap and on
      length.
  (c) pause_cut_points: exact gaps at the 0.6s threshold.
  (d) registry contract: tools registered read-only, confined
      paths refused outside the workspace, missing-dependency
      handlers fail honestly (never raise).
  (e) ENGINE_CORE carries the video-analysis rule.
"""

import os
import tempfile

import video_tools
import tools_registry
import engine_instructions

PASS = 0


def check(cond, label, extra=""):
    global PASS
    assert cond, f"FAIL: {label} {extra}"
    PASS += 1
    print(f"  ok {label}")


# (a) scenes ----------------------------------------------------------
sc = video_tools.scenes_from_boundaries([12.03, 23.07, 34.03, 45.10], 51.5)
check(len(sc) == 5, "a1 five scenes", str(sc))
check(sc[0] == {"start": 0.0, "end": 12.03, "duration": 12.03},
      "a2 first scene exact", str(sc[0]))
check(sc[-1] == {"start": 45.1, "end": 51.5, "duration": 6.4},
      "a3 last scene exact", str(sc[-1]))
sc2 = video_tools.scenes_from_boundaries([5.0, 5.3, 9.0], 10.0)
check(len(sc2) == 3 and sc2[0]["end"] == 5.3,
      "a4 sub-0.5s scene merged into previous", str(sc2))
sc3 = video_tools.scenes_from_boundaries([-1, 0, 99], 10.0)
check(sc3 == [{"start": 0.0, "end": 10.0, "duration": 10.0}],
      "a5 out-of-range cuts dropped", str(sc3))

# (b) cues ------------------------------------------------------------
words = [{"word": "You", "start": 0.0, "end": 0.4},
         {"word": "scroll,", "start": 0.68, "end": 1.2},
         {"word": "you", "start": 1.6, "end": 1.75},
         {"word": "eat,", "start": 1.8, "end": 2.2},
         {"word": "repeat.", "start": 3.66, "end": 3.76}]
cues = video_tools.words_to_cues(words)
check(len(cues) == 2, "b1 gap break makes two cues", str(cues))
check(cues[0] == {"start": 0.0, "end": 2.2,
                  "text": "You scroll, you eat,"},
      "b2 first cue exact", str(cues[0]))
check(cues[1]["text"] == "repeat." and cues[1]["start"] == 3.66,
      "b3 second cue exact", str(cues[1]))
long_words = [{"word": "abcdefghij", "start": float(i), "end": i + 0.5}
              for i in range(6)]
check(len(video_tools.words_to_cues(long_words, max_chars=25)) == 3,
      "b4 length break at max_chars")

# (c) pause cuts --------------------------------------------------------
cuts = video_tools.pause_cut_points(words)
check(len(cuts) == 1 and cuts[0]["after_word"] == "eat,"
      and cuts[0]["gap"] == 1.46,
      "c1 one pause cut, exact gap", str(cuts))
check(video_tools.pause_cut_points(words, min_gap=2.0) == [],
      "c2 higher threshold -> no cuts")

# (d) registry ----------------------------------------------------------
with tempfile.TemporaryDirectory() as root:
    reg = tools_registry.Registry()
    video_tools.register_video_tools(reg, root)
    names = reg.names()
    check("video_scene_list" in names and "video_word_transcript" in names,
          "d1 both tools registered", str(names))
    entry = reg.get("video_scene_list")
    check(entry is not None and not entry.get("mutating", True),
          "d2 scene tool read-only")
    tools = {t["name"]: t for t in reg.as_tools()}
    ok, res = tools["video_scene_list"]["run"]({"path": "../escape.mp4"})
    check(ok is False, "d3 path escape refused", str(res))
    ok, res = tools["video_word_transcript"]["run"]({"path": "missing.mp3"})
    check(ok is False, "d4 missing file fails honestly, no raise", str(res))

# (e) ENGINE_CORE -------------------------------------------------------
check("video_scene_list" in engine_instructions.ENGINE_CORE
      and "video_word_transcript" in engine_instructions.ENGINE_CORE,
      "e1 ENGINE_CORE carries video-analysis rule")

print(f"vidtoolstest: {PASS} checks passed")
