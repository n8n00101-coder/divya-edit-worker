"""v69 tests: long-video routing + stock B-roll (no live LLM, no live APIs).

1. runner.parse_requested_seconds — extracted from runner.py source
   (runner.py runs main() at import, so it cannot be imported directly)
   and checked against owner phrasings: short stays short, '10 min' /
   '1 hour' route long with the right totals.
2. long_video.outline with explicit targets (doc stubbed out — only the
   outline parser is exercised here; the shipped long_video self-test
   covers outline+assemble with the real doc import).
3. broll.fetch_broll failure-grace: no keys -> None fast; provider down
   -> None; stubbed provider hit -> dict + cache.
4. doc._extract_broll_frames / _broll_frame on a generated dummy clip
   (skipped if the full doc import is unavailable in this environment).

Run: python v69test.py  (prints PASS lines, raises on failure)
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


# ---------------------------------------------------------------- 1. routing
def _load_parse_fn():
    src = (HERE / "runner.py").read_text(encoding="utf-8")
    body = src.split("def parse_requested_seconds", 1)[1]
    body = body.split("\nasync def create_job", 1)[0]
    ns = {"re": re}
    exec("def parse_requested_seconds" + body, ns)
    return ns["parse_requested_seconds"]


def test_routing():
    parse = _load_parse_fn()

    def route(brief):
        s = parse(brief)
        return ("long", s) if s is not None and s > 90 else ("short", s)

    cases = [
        ("topic: chess history, female voice, length: short 30s 9:16",
         ("short", None)),
        ("topic: rain FINAL VIDEO LENGTH: exactly 30 seconds (±2s)",
         ("short", 30)),
        ("topic: oceans FINAL VIDEO LENGTH: exactly 10 minutes (±30s)",
         ("long", 600)),
        ("make a 10 min video on oceans, english female",
         ("long", 600)),
        ("1 hour documentary on the ocean, english",
         ("long", 3600)),
        ("one hour video on sleep, telugu",
         ("long", 3600)),
        ("2 hours on history",  # capped at Ajju's 1-hour order
         ("long", 3600)),
        ("long video on sleep science",  # bare 'long' -> 5-min default
         ("long", 300)),
        ("topic: space, length: long (up to 60 min, 16:9)",  # menu text
         ("long", 300)),  # 'up to 60 min' is NOT an owner-stated length
        ("5 minutes on rain habits",
         ("long", 300)),
        ("topic: rain", ("short", None)),
    ]
    for brief, want in cases:
        got = route(brief)
        assert got == want, f"routing {brief!r}: got {got}, want {want}"
        print(f"routing: {brief[:52]!r:56} -> {got} PASS")


# ------------------------------------------------------- 2. outline targets
def test_outline_targets():
    fake_doc = types.ModuleType("doc")
    fake_doc.__file__ = str(HERE / "doc.py")

    async def _no_make_video(*a, **k):
        raise RuntimeError("stub")
    fake_doc.make_video = _no_make_video
    sys.modules["doc"] = fake_doc
    import long_video

    def stub(n_ch, mins):
        def chat(messages):
            assert messages[0]["role"] == "system"
            return json.dumps({
                "title": "Target test",
                "chapters": [{"title": f"Chapter {i + 1}",
                              "brief": f"Covers part {i + 1}.",
                              "minutes": mins} for i in range(n_ch)]})
        return chat

    out = long_video.outline("ten minutes", stub(5, 2), target_minutes=10)
    assert sum(c["minutes"] for c in out["chapters"]) == 10
    print("outline target=10: PASS (5 chapters totalling 10 min)")
    out = long_video.outline("one hour", stub(30, 2), target_minutes=60)
    assert len(out["chapters"]) == 30
    assert sum(c["minutes"] for c in out["chapters"]) == 60
    print("outline target=60: PASS (30 chapters totalling 60 min)")
    try:
        long_video.outline("x", stub(4, 2), target_minutes=10)
    except ValueError:
        print("outline target=10 wrong total (8): PASS (ValueError)")
    else:
        raise AssertionError("outline accepted a wrong total")


# ---------------------------------------------------------------- 3. broll
def test_broll():
    import broll
    saved = {k: os.environ.pop(k, None) for k in ("PEXELS_KEY", "PIXABAY_KEY")}
    try:
        with tempfile.TemporaryDirectory() as td:
            t0 = time.time()
            assert broll.fetch_broll("ocean waves", td) is None
            assert time.time() - t0 < 5
            print("broll no keys: PASS (None, fast — engine unchanged)")

            os.environ["PEXELS_KEY"] = "test-key-not-real"
            real_get = broll._get_json

            def boom(*a, **k):
                raise RuntimeError("network down")
            broll._get_json = boom
            try:
                assert broll.fetch_broll("ocean waves", td) is None
            finally:
                broll._get_json = real_get
            print("broll provider down: PASS (None, no raise)")

            real_search, real_dl = broll._pexels_search, broll._download
            broll._pexels_search = lambda q, k, o: {
                "url": "https://cdn.example/clip.mp4",
                "page": "https://www.pexels.com/video/123/"}

            def fake_dl(url, dest):
                with open(dest, "wb") as f:
                    f.write(b"\0" * 60_000)
                return True
            broll._download = fake_dl
            try:
                hit = broll.fetch_broll("ocean waves", td)
                assert hit and hit["provider"] == "pexels"
                assert hit["source_url"] == "https://www.pexels.com/video/123/"
                assert Path(hit["path"]).stat().st_size == 60_000
                hit2 = broll.fetch_broll("ocean waves", td)
                assert hit2 and hit2["path"] == hit["path"]
            finally:
                broll._pexels_search, broll._download = real_search, real_dl
            print("broll stubbed hit: PASS (dict + source URL + cache)")
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# -------------------------------------- 4b. make_long_video end-to-end stub
def test_make_long_video():
    """Full long pipeline with a stubbed chapter renderer: outline ->
    3 chapter clips -> assemble, plus the deadline -> partial path."""
    import long_video

    def outline_chat(n_ch, mins):
        def chat(messages):
            return json.dumps({
                "title": "Stub long",
                "chapters": [{"title": f"Part {i + 1}",
                              "brief": f"Brief {i + 1}.",
                              "minutes": mins} for i in range(n_ch)]})
        return chat

    async def fake_make_video(brief, chat, notify=None, workdir=None):
        Path(workdir).mkdir(parents=True, exist_ok=True)
        out = str(Path(workdir) / "chapter.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i",
                        "color=c=navy:s=1080x1920:d=1:r=30",
                        "-f", "lavfi", "-i", "sine=frequency=330:d=1",
                        "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-ar", "44100", out], check=True)
        # v78: the stub stands in for a FULL 1-min chapter, so it must
        # report the duration the real doc.make_video always returns —
        # without it, render_chapters (correctly) probes the 1s file,
        # finds the chapter materially short of its 60s budget and
        # tops it up, which is v78 behaviour, not a v69 regression.
        return {"path": out, "title": "Stub long", "lang": "en",
                "caption": "cap", "topic": "stub", "plan": {},
                "duration": 60.0,
                "broll": [{"scene": 1, "provider": "pexels",
                           "source_url": "https://www.pexels.com/video/1/",
                           "query": "stub"}]}

    real_make_video = long_video.doc.make_video
    long_video.doc.make_video = fake_make_video
    try:
        with tempfile.TemporaryDirectory() as td:
            res = asyncio.run(long_video.make_long_video(
                "stub topic", outline_chat(3, 1), td, target_minutes=3))
            assert res["partial"] is False
            assert res["chapters_done"] == 3 and res["chapters_total"] == 3
            assert 5.0 < res["duration"] < 8.0, res["duration"]
            assert len(res["broll"]) == 3  # aggregated from the chapters
            assert Path(res["path"]).stat().st_size > 0
            assert "3/3 chapters" in res["summary"]
            print(f"make_long_video complete: PASS (3 chapters assembled, "
                  f"{res['duration']:.1f}s, broll aggregated)")

            res2 = asyncio.run(long_video.make_long_video(
                "stub topic", outline_chat(3, 1), td, target_minutes=3,
                deadline=time.monotonic() - 1))  # budget already spent
            # The first chapter always renders; the deadline stops the rest.
            assert res2["partial"] is True and res2["chapters_done"] == 1
            assert "PARTIAL" in res2["summary"]
            print("make_long_video deadline: PASS (1/3 chapters, "
                  "partial assembly delivered, flagged in summary)")
    finally:
        long_video.doc.make_video = real_make_video


# ------------------------------------------------- 5. doc frame extraction
def test_doc_broll_frames():
    sys.modules.pop("doc", None)  # drop the outline test's stub
    try:
        import doc
    except Exception as e:
        print(f"doc import unavailable here ({type(e).__name__}) — "
              f"frame-extraction test SKIPPED")
        return
    with tempfile.TemporaryDirectory() as td:
        clip = str(Path(td) / "clip.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i",
                        "color=c=teal:s=720x1280:d=3:r=30",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", clip],
                       check=True)
        fdir = str(Path(td) / "frames")
        n = doc._extract_broll_frames(clip, fdir, 2.0)
        assert 40 <= n <= 70, f"expected ~60 frames for 2 s, got {n}"
        p = {"broll": {0: {"dir": fdir, "frames": n}}, "scenes": [{}]}
        img = doc._broll_frame(p, 0, 0.5)
        assert img is not None and img.size == (doc.W, doc.H)
        assert doc._broll_frame(p, 1, 0.5) is None
        assert doc._broll_frame({"scenes": [{}]}, 0, 0.5) is None
        print(f"doc broll frames: PASS ({n} frames extracted at "
              f"{doc.W}x{doc.H}, lookup + miss both correct)")


if __name__ == "__main__":
    test_routing()
    test_outline_targets()
    test_broll()
    test_make_long_video()
    test_doc_broll_frames()
    print("v69 tests: ALL PASS")
