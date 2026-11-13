#!/usr/bin/env python3
"""v75 tests — long-video pipeline repair (the two live deaths:
run 43355930702 = Groq 429 in chapter 1's plan, no retry, no report;
run 43373013930 = ch01 never created -> plan.json ENOENT in codegen,
masked as a vo0.mp3 "TTS failed", no report).

Sections:
1. runner.groq_chat transient retry (429 sweeps, network errors,
   non-transient no-retry) — runner source exec'd with stubbed
   httpx/time, main() entry stripped.
2. doc.tts: output-dir guarantee + the REAL error surfaced (type +
   message), empty-synthesis failure — edge_tts stubbed in
   sys.modules with a fake that yields real silent-mp3 bytes.
3. long_video.render_chapters: a failed chapter is retried once;
   partial semantics after the retry are unchanged (fake make_video).
4. runner reporting guarantee, end-to-end at the process boundary:
   the REAL runner.py as a subprocess against a local stub Worker —
   a create whose engine raises RuntimeError, and one that raises
   SystemExit, must each post runner/state=failed exactly once
   (v73 refunds on that post) and exit non-zero.
5. REAL integration: render_chapters -> doc.make_video for one
   chapter on a real filesystem (chat stubbed with canned plan /
   codegen replies, edge-tts stubbed as in 2). Asserts the chapter
   mp4 exists and plan.json + codegen_result.json + vo0.mp3 landed
   in the chapter dir — the exact files whose absence killed run
   43373013930. Then the same render with codegen rigged to raise:
   the chapter must STILL be produced (library fallback), proving
   the codegen->TTS doom cascade is gone.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))
os.environ.pop("PEXELS_KEY", None)
os.environ.pop("PIXABAY_KEY", None)

_fails = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {extra}" if extra and not cond else ""), flush=True)
    if not cond:
        _fails.append(name)


async def _instant_sleep(*a, **k):
    return None


# ------------------------------------------------------------ silent mp3s
_silent_cache = {}


def silent_mp3(seconds):
    """Real silent-mp3 bytes (ffmpeg anullsrc) — the edge-tts fake
    yields these so doc.tts writes a genuine, ffprobe-able file."""
    seconds = max(1, int(round(seconds)))
    if seconds not in _silent_cache:
        p = Path(tempfile.mkdtemp(prefix="v75_mp3_")) / f"sil{seconds}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "anullsrc=r=44100:cl=mono", "-t", str(seconds),
                        "-c:a", "libmp3lame", "-q:a", "4", str(p)], check=True)
        _silent_cache[seconds] = p.read_bytes()
    return _silent_cache[seconds]


def install_fake_edge_tts(mode="good"):
    """mode: good (audio + word boundaries) | raise (synthesis error)
    | silent (no audio at all). Returns the previous module."""
    mod = types.ModuleType("edge_tts")

    class Communicate:
        def __init__(self, text, voice, rate=None, pitch=None, boundary=None):
            self.text = text

        async def stream(self):
            if mode == "raise":
                raise OSError("synth boom")
            if mode == "silent":
                return
                yield  # pragma: no cover - makes this an async generator
            words = self.text.split()
            yield {"type": "audio",
                   "data": silent_mp3(max(1, round(len(words) * 0.35)))}
            for i, w in enumerate(words):
                yield {"type": "WordBoundary",
                       "offset": int(i * 0.35 * 1e7),
                       "duration": int(0.35 * 1e7), "text": w}

    mod.Communicate = Communicate
    prev = sys.modules.get("edge_tts")
    sys.modules["edge_tts"] = mod
    return prev


def restore_edge_tts(prev):
    if prev is None:
        sys.modules.pop("edge_tts", None)
    else:
        sys.modules["edge_tts"] = prev


# ------------------------------------------------------------ 1. groq_chat
def test_groq_chat():
    import httpx as real_httpx
    os.environ.setdefault("WORKER_URL", "http://worker.invalid")
    os.environ.setdefault("RUNNER_KEY", "rk")
    os.environ["GROQ_KEY"] = "k1"
    argv = sys.argv
    sys.argv = ["runner.py", "JOBX"]
    try:
        src = (HERE / "runner.py").read_text(encoding="utf-8")
        src = src.replace("asyncio.run(main())", "")
        ns = {"__name__": "runner_under_test"}
        exec(compile(src, "runner.py", "exec"), ns)
    finally:
        sys.argv = argv
    groq_chat = ns["groq_chat"]

    class Resp:
        def __init__(self, status, text=""):
            self.status_code = status
            self._text = text

        def json(self):
            return {"choices": [{"message": {"content": self._text}}]}

    state = {"script": [], "calls": 0, "sleeps": []}

    def fake_post(url, json=None, headers=None, timeout=None):
        state["calls"] += 1
        item = state["script"].pop(0) if state["script"] else 429
        if item == "net":
            raise real_httpx.ConnectError("boom", request=None)
        if isinstance(item, tuple):
            return Resp(200, item[1])
        return Resp(item)

    ns["httpx"] = types.SimpleNamespace(
        post=fake_post, HTTPError=real_httpx.HTTPError)
    ns["time"] = types.SimpleNamespace(
        sleep=lambda s: state["sleeps"].append(s),
        monotonic=time.monotonic, time=time.time)

    # two full 429 sweeps, then success -> completes, backoff 5,15
    state.update(script=[429] * 6 + [("ok", "hello")], calls=0, sleeps=[])
    out = groq_chat([{"role": "user", "content": "hi"}])
    ok("groq_chat: 429 sweeps then success returns the reply", out == "hello")
    ok("groq_chat: backoff was 5s then 15s", state["sleeps"] == [5, 15],
       str(state["sleeps"]))
    ok("groq_chat: 7 posts for 2 failed sweeps + 1 success",
       state["calls"] == 7, str(state["calls"]))

    # a network error is transient too
    state.update(script=["net", ("ok", "back")], calls=0, sleeps=[])
    out = groq_chat([{"role": "user", "content": "hi"}])
    ok("groq_chat: network error retried within the sweep", out == "back")

    # permanent 429 -> raises after 4 sweeps (1 + 3 retries)
    state.update(script=[], calls=0, sleeps=[])
    try:
        groq_chat([{"role": "user", "content": "hi"}])
        ok("groq_chat: permanent 429 raises", False)
    except RuntimeError as e:
        ok("groq_chat: permanent 429 raises after all retries",
           "429" in str(e) and state["calls"] == 12
           and state["sleeps"] == [5, 15, 45],
           f"calls={state['calls']} sleeps={state['sleeps']} err={e}")

    # non-transient (400) -> raises after ONE sweep, no sleeps
    state.update(script=[400] * 50, calls=0, sleeps=[])
    try:
        groq_chat([{"role": "user", "content": "hi"}])
        ok("groq_chat: 400 raises immediately", False)
    except RuntimeError:
        ok("groq_chat: 400 raises immediately (1 sweep, no backoff)",
           state["calls"] == 3 and state["sleeps"] == [],
           f"calls={state['calls']} sleeps={state['sleeps']}")


# ------------------------------------------------------------ 2. doc.tts
def test_tts():
    import doc
    prev = install_fake_edge_tts("good")
    try:
        with tempfile.TemporaryDirectory(prefix="v75_tts_") as td:
            out = str(Path(td) / "deep" / "nested" / "vo0.mp3")
            words = asyncio.run(doc.tts("hello brave new world",
                                        "en-US-AvaMultilingualNeural",
                                        "calm", out))
            ok("tts: writes into a directory that did not exist",
               Path(out).is_file() and Path(out).stat().st_size > 0)
            ok("tts: word timings returned", len(words) == 4,
               str(words))
    finally:
        restore_edge_tts(prev)

    prev = install_fake_edge_tts("raise")
    try:
        with tempfile.TemporaryDirectory(prefix="v75_tts_") as td:
            with mock.patch.object(asyncio, "sleep", _instant_sleep):
                try:
                    asyncio.run(doc.tts("hello world",
                                        "en-US-AvaMultilingualNeural",
                                        "calm", str(Path(td) / "vo0.mp3")))
                    ok("tts: synthesis error surfaces", False)
                except RuntimeError as e:
                    ok("tts: the REAL synthesis error surfaces (type + cause)",
                       "synth boom" in str(e) and "OSError" in str(e), str(e))
    finally:
        restore_edge_tts(prev)

    prev = install_fake_edge_tts("silent")
    try:
        with tempfile.TemporaryDirectory(prefix="v75_tts_") as td:
            with mock.patch.object(asyncio, "sleep", _instant_sleep):
                try:
                    asyncio.run(doc.tts("hello world",
                                        "en-US-AvaMultilingualNeural",
                                        "calm", str(Path(td) / "vo0.mp3")))
                    ok("tts: empty synthesis fails", False)
                except RuntimeError as e:
                    ok("tts: empty synthesis fails honestly (no fake file)",
                       "no audio" in str(e) and
                       not Path(td, "vo0.mp3").exists(), str(e))
    finally:
        restore_edge_tts(prev)


# ------------------------------------------- 3. render_chapters retrying
def test_chapter_retry():
    import doc
    import long_video

    outline2 = {"title": "T", "chapters": [
        {"title": "One", "brief": "First.", "minutes": 1},
        {"title": "Two", "brief": "Second.", "minutes": 1}]}
    real_mv = doc.make_video
    calls = {"n": 0, "plan": None}

    def flaky(fail_first=0, fail_chapter=None):
        async def fake(brief, chat, notify=None, workdir=None, **kw):
            calls["n"] += 1
            if fail_chapter and f"chapter {fail_chapter} of" in brief:
                raise RuntimeError("chapter boom")
            if calls["n"] <= fail_first:
                raise RuntimeError("transient boom")
            p = Path(workdir) / "chapter.mp4"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"\x00" * 2048)
            return {"path": str(p)}
        return fake

    try:
        with tempfile.TemporaryDirectory(prefix="v75_ch_") as td:
            # chapter 1 fails once, then succeeds -> retried, completes
            calls["n"] = 0
            doc.make_video = flaky(fail_first=1)
            with mock.patch.object(asyncio, "sleep", _instant_sleep):
                paths = asyncio.run(long_video.render_chapters(
                    {"title": "T", "chapters": outline2["chapters"][:1]},
                    lambda m: "{}", td))
            ok("render_chapters: chapter retried once and completed",
               len(paths) == 1 and calls["n"] == 2,
               f"paths={paths} calls={calls['n']}")

            # chapter 1 always fails -> error propagates (job-level
            # failure, which section 4 proves is REPORTED)
            calls["n"] = 0
            doc.make_video = flaky(fail_first=99)
            with mock.patch.object(asyncio, "sleep", _instant_sleep):
                try:
                    asyncio.run(long_video.render_chapters(
                        {"title": "T", "chapters": outline2["chapters"][:1]},
                        lambda m: "{}", td))
                    ok("render_chapters: dead chapter 1 propagates", False)
                except RuntimeError:
                    ok("render_chapters: dead chapter 1 propagates "
                       "after exactly one retry", calls["n"] == 2,
                       str(calls["n"]))

            # chapter 2 dies after chapter 1 finished -> partial
            calls["n"] = 0
            doc.make_video = flaky(fail_chapter=2)
            with mock.patch.object(asyncio, "sleep", _instant_sleep):
                paths = asyncio.run(long_video.render_chapters(
                    outline2, lambda m: "{}", td))
            ok("render_chapters: later chapter failure -> finished "
               "chapters returned (partial)", len(paths) == 1,
               str(paths))
    finally:
        doc.make_video = real_mv


# ------------------------------------------- 4. reporting, process level
def test_reporting():
    tmp = Path(tempfile.mkdtemp(prefix="v75_rep_"))
    shutil.copy(HERE / "runner.py", tmp / "runner.py")
    (tmp / "whatsapp.py").write_text(
        "async def send_text(to, text):\n    return True\n"
        "async def send_media(to, path, kind, caption=None):\n"
        "    return True\n"
        "async def download_media(mid, ext):\n"
        "    raise RuntimeError('no media in test')\n")
    (tmp / "autoedit.py").write_text(
        "async def auto_edit(*a, **k):\n"
        "    raise RuntimeError('unused in test')\n")
    (tmp / "create.py").write_text(
        "import os, types\n"
        "def engine_module():\n"
        "    m = types.ModuleType('doc')\n"
        "    async def make_video(brief, chat, notify=None, **kw):\n"
        "        if os.environ.get('V75_STUB_MODE') == 'exit':\n"
        "            raise SystemExit(3)\n"
        "        raise RuntimeError('kaboom chapter')\n"
        "    m.make_video = make_video\n"
        "    return m\n")

    posts = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _reply(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            if self.path.startswith("/job"):
                return self._reply({
                    "mode": "create", "to": "12345", "WA_TOKEN": "tok",
                    "PHONE_ID": "ph", "GROQ_KEY": "gk",
                    "brief": "a short test topic"})
            if self.path.startswith("/api/runner/state"):
                try:
                    posts.append(json.loads(raw or b"{}"))
                except Exception:
                    posts.append({})
                return self._reply({"ok": True})
            return self._reply({"ok": True})

        def do_GET(self):
            return self._reply({"ok": True})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # Strip this VM's proxy env for the subprocess: its proxy vars
    # break httpx's URL parser outright (the broll.py lesson). The GH
    # runner has no such env — this mirrors production conditions.
    env = {k: v for k, v in os.environ.items()
           if "proxy" not in k.lower()}
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env.update({"WORKER_URL": f"http://127.0.0.1:{port}",
                "RUNNER_KEY": "rk", "DATA_DIR": str(tmp / "data")})
    try:
        for mode, want_rc in (("raise", 1), ("exit", 3)):
            posts.clear()
            env["V75_STUB_MODE"] = mode
            r = subprocess.run([sys.executable, str(tmp / "runner.py"),
                                "JOBX"], cwd=tmp, env=env,
                               capture_output=True, text=True, timeout=180)
            failed = [p for p in posts if p.get("state") == "failed"]
            ok(f"reporting[{mode}]: runner exits non-zero ({want_rc})",
               r.returncode == want_rc,
               f"rc={r.returncode} tail={r.stderr[-200:]}")
            ok(f"reporting[{mode}]: state=failed posted exactly once",
               len(failed) == 1, f"posts={posts}")
            if mode == "raise" and failed:
                ok("reporting[raise]: the failure note carries the cause",
                   "kaboom" in str(failed[0].get("note", "")),
                   str(failed))
    finally:
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------- 5. real chapter integration
PLAN_JSON = {
    "title": "COMPROMISE TEST", "lang": "en", "voice": "female",
    "end_question": "Where do you compromise?",
    "scenes": [
        {"vo": "Compromise means meeting halfway with patience.",
         "visual": "check", "mood": "calm", "label": "MIDDLE",
         "value": "", "source": ""},
        {"vo": "Families bend so nobody has to break.",
         "visual": "check", "mood": "calm", "label": "FAMILY",
         "value": "", "source": ""},
        {"vo": "Careers grow when egos quietly shrink.",
         "visual": "check", "mood": "calm", "label": "CAREER",
         "value": "", "source": ""},
        {"vo": "Choose the ground you never give up.",
         "visual": "check", "mood": "calm", "label": "GROUND",
         "value": "", "source": ""},
    ],
}
IDEAS_JSON = {"objects": [], "personality": "smooth", "scene_fx": [],
              "transitions": [], "visuals": []}


def stub_chat(messages):
    system = next((m["content"] for m in messages
                   if m.get("role") == "system"), "")
    user = next((m["content"] for m in messages
                 if m.get("role") == "user"), "")
    if "You score video scenes" in system:
        return "5\n5\n5\n5"
    if "MAIN VISUAL" in user:            # codegen step_plan
        return json.dumps(IDEAS_JSON)
    if "Write video_fx.py" in user:      # codegen step_code
        return "```python\n# v75 test: no custom fx\n```"
    return json.dumps(PLAN_JSON)         # doc.plan


def test_real_chapter():
    import doc
    import long_video
    os.environ["DIVYA_LAST_LOOKS"] = str(
        Path(tempfile.mkdtemp(prefix="v75_looks_")) / "looks.json")
    outline1 = {"title": "Compromise Test", "chapters": [
        {"title": "Chapter One", "brief": "Why people compromise.",
         "minutes": 1}]}
    prev = install_fake_edge_tts("good")
    try:
        with tempfile.TemporaryDirectory(prefix="v75_long_") as td:
            results = []
            paths = asyncio.run(long_video.render_chapters(
                outline1, stub_chat, td, results_out=results))
            ch = Path(td) / "ch01"
            ok("integration: chapter mp4 produced",
               len(paths) == 1 and Path(paths[0]).is_file()
               and Path(paths[0]).stat().st_size > 10000,
               str(paths))
            ok("integration: plan.json written in the chapter dir",
               (ch / "plan.json").is_file())
            ok("integration: codegen_result.json written (plan.json read "
               "back by the codegen)", (ch / "codegen_result.json").is_file())
            ok("integration: vo0.mp3 written in the chapter dir",
               (ch / "vo0.mp3").is_file())
            ok("integration: chapter result returned",
               len(results) == 1 and results[0].get("path") == paths[0])

        # codegen rigged to raise: the chapter must STILL render via
        # the library fallback — no vo0.mp3 doom cascade.
        real_run = doc.CG.run

        def boom(*a, **k):
            raise RuntimeError("codegen exploded")

        doc.CG.run = boom
        try:
            with tempfile.TemporaryDirectory(prefix="v75_long_cg_") as td:
                paths = asyncio.run(long_video.render_chapters(
                    outline1, stub_chat, td))
                ok("integration: codegen failure contained — chapter "
                   "still rendered", len(paths) == 1
                   and Path(paths[0]).is_file(), str(paths))
                ok("integration: vo0.mp3 exists despite codegen failure",
                   (Path(td) / "ch01" / "vo0.mp3").is_file())
        finally:
            doc.CG.run = real_run
    finally:
        restore_edge_tts(prev)


def main():
    test_groq_chat()
    test_tts()
    test_chapter_retry()
    test_reporting()
    test_real_chapter()
    if _fails:
        print(f"\nv75test: {len(_fails)} FAILURE(S): {_fails}")
        return 1
    print("\nv75test: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
