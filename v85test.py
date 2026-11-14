"""v85test.py — targeted checks for the v85 completion wiring ONLY
(no new suite farming; the v84 suite + prior regressions still run
as-is). Covers:
  1. media_qc catches real defects in synthetic files: black frames,
     frozen+blank frames, blank-BLUE frames, missing audio, A/V
     duration mismatch — and stays quiet on a clean file.
  2. media_qc on a missing file FAILs truthfully (MQ-PROBE), never
     raises, never PASSes.
  3. Thresholds are configurable (KB-style cfg override).
  4. The assembled-file correction loop (long_video._correct_
     assembled) maps a black chapter to its chapter, re-renders ONLY
     that chapter (stubbed renderer), re-assembles, re-inspects and
     records exactly 1 round.
Run: python3 v85test.py   (exit 0 = all pass)
"""

import asyncio
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import media_qc
import long_video

PASS = []


def check(name, cond, extra=""):
    PASS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra else ""))
    if not cond:
        raise SystemExit(f"v85test FAILED at: {name}")


def _ff(args, out):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args, out],
                   check=True)
    return out


def _fails(checks, rule=None):
    return [c for c in checks if c["status"] == "FAIL"
            and (rule is None or c["rule"] == rule)]


def main():
    td = tempfile.mkdtemp(prefix="v85test_")
    # ---- synthetic media -------------------------------------------
    good = _ff(["-f", "lavfi", "-i", "testsrc2=size=320x568:rate=10:duration=5",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                "-shortest"], os.path.join(td, "good.mp4"))
    black = _ff(["-f", "lavfi", "-i", "color=c=black:size=320x568:rate=10:duration=4",
                 "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                 "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                 "-shortest"], os.path.join(td, "black.mp4"))
    blue = _ff(["-f", "lavfi", "-i", "color=c=0x082448:size=320x568:rate=10:duration=4",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                "-shortest"], os.path.join(td, "blue.mp4"))
    noaudio = _ff(["-f", "lavfi", "-i", "testsrc2=size=320x568:rate=10:duration=4",
                   "-c:v", "libx264", "-preset", "ultrafast"],
                  os.path.join(td, "noaudio.mp4"))
    mismatch = _ff(["-f", "lavfi", "-i", "testsrc2=size=320x568:rate=10:duration=6",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
                    "-preset", "ultrafast", "-c:a", "aac"],
                   os.path.join(td, "mismatch.mp4"))

    ch, _ = media_qc.inspect_file(good)
    check("clean file: no black/freeze/blank/avsync/probe FAILs",
          not _fails(ch, "MQ-BLACK") and not _fails(ch, "MQ-FREEZE")
          and not _fails(ch, "MQ-BLANK") and not _fails(ch, "MQ-AVSYNC")
          and not _fails(ch, "MQ-PROBE"),
          str([c for c in _fails(ch)]))
    ch, _ = media_qc.inspect_file(black)
    check("black file: MQ-BLACK FAIL", bool(_fails(ch, "MQ-BLACK")))
    ch, _ = media_qc.inspect_file(blue)
    bl = _fails(ch, "MQ-BLANK")
    check("blank-blue file: MQ-BLANK FAIL naming BLUE",
          bool(bl) and any("BLUE" in c["detail"] for c in bl),
          str(bl[:1]))
    check("solid colour file: MQ-FREEZE FAIL",
          bool(_fails(ch, "MQ-FREEZE")))
    ch, _ = media_qc.inspect_file(noaudio)
    check("no-audio file: MQ-PROBE FAIL (no audio stream)",
          any("no audio" in c["detail"] for c in _fails(ch, "MQ-PROBE")))
    ch, _ = media_qc.inspect_file(mismatch)
    check("A/V mismatch file: MQ-AVSYNC FAIL", bool(_fails(ch, "MQ-AVSYNC")))
    ch, _ = media_qc.inspect_file(os.path.join(td, "does_not_exist.mp4"))
    check("missing file: MQ-PROBE FAIL, no exception",
          bool(_fails(ch, "MQ-PROBE")))
    ch, _ = media_qc.inspect_file(blue, cfg={"blank_std_max": 0.0})
    check("configurable threshold: blank_std_max=0 clears MQ-BLANK",
          not _fails(ch, "MQ-BLANK"))
    dm = media_qc.chapter_defect_map(
        [{"rule": "MQ-BLACK", "status": "FAIL", "scene": 2, "detail": ""},
         {"rule": "MQ-LOUD", "status": "FAIL", "scene": None, "detail": ""},
         {"rule": "MQ-CUTS", "status": "WARN", "scene": 1, "detail": ""}])
    check("chapter_defect_map: FAILs grouped, WARN excluded",
          set(dm) == {2, None} and len(dm[2]) == 1 and len(dm[None]) == 1)

    # ---- assembled correction loop ---------------------------------
    async def _loop():
        ch1 = _ff(["-f", "lavfi", "-i",
                   "testsrc2=size=320x568:rate=10:duration=4",
                   "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                   "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                   "-shortest"], os.path.join(td, "ch1.mp4"))
        ch2 = _ff(["-f", "lavfi", "-i",
                   "color=c=black:size=320x568:rate=10:duration=4",
                   "-f", "lavfi", "-i", "sine=frequency=330:duration=4",
                   "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                   "-shortest"], os.path.join(td, "ch2.mp4"))
        final = long_video.assemble([ch1, ch2],
                                    os.path.join(td, "final.mp4"),
                                    ["Alpha", "Beta"], size=(320, 568),
                                    card_bg_from=[ch1, ch2])
        calls = []

        async def stub_make_video(brief, chat, notify=None, workdir=None,
                                  **kw):
            calls.append(brief)
            out = os.path.join(workdir, "stub.mp4")
            _ff(["-f", "lavfi", "-i",
                 "testsrc2=size=320x568:rate=10:duration=4",
                 "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                 "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                 "-shortest"], out)
            return {"path": out, "duration": 4.0}

        orig = long_video.doc.make_video
        long_video.doc.make_video = stub_make_video
        try:
            outline_data = {"title": "T", "chapters": [
                {"title": "Alpha", "brief": "a", "minutes": 1},
                {"title": "Beta", "brief": "b", "minutes": 1}]}
            checks, rounds, fixes, final2, paths2 = \
                await long_video._correct_assembled(
                    final, [ch1, ch2], [{}, {}], outline_data, None,
                    td, ["Alpha", "Beta"], (320, 568))
        finally:
            long_video.doc.make_video = orig
        return checks, rounds, fixes, calls

    checks, rounds, fixes, calls = asyncio.run(_loop())
    check("correction loop: exactly 1 round for one defective chapter",
          rounds == 1, f"rounds={rounds} fixes={fixes}")
    check("correction loop: only the defective chapter re-rendered",
          len(calls) == 1, f"renderer calls={len(calls)}")
    check("correction loop: black defect gone after fix",
          not _fails(checks, "MQ-BLACK"),
          str(_fails(checks)))
    check("correction loop: fix recorded naming chapter 2",
          any("chapter 2" in f for f in fixes), str(fixes))
    print(f"\nv85test: {sum(PASS)}/{len(PASS)} PASS")


if __name__ == "__main__":
    main()
