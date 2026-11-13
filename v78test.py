#!/usr/bin/env python3
"""v78 tests — delivered-wins + long-video length budgets.

Live evidence (job 7aee5d2a, GH run 43375582446, 2026-11-13): the
runner rendered all 7 chapters, the result upload answered 200 at
06:35:48Z — and at 06:35:50Z create_job died at
``await wa.send_media(...)`` with "WhatsApp upload failed: HTTP 413"
(the 108 MB file; the old fixed-1900k WA re-encode could never fit a
460 s video). The v75 terminal guard posted runner/state=failed, the
Worker flipped the DELIVERED History entry to failed and refunded the
full 1.4M charge for a video the user can download. Same job, second
bug: 14 minutes asked, 7 chapters "completed", assembled video 7.7 min
— outline minutes were never turned into a script budget and no
chapter's rendered duration was ever checked.

Sections:
1. runner.app_state: a failed post after mark_result_delivered() is
   suppressed (logged, not posted); before delivery it posts as ever.
2. Subprocess end-to-end (the v75 harness shape): a create whose
   result uploads 200 and whose WhatsApp send then raises the exact
   production 413 exits ZERO, posts the result once and posts NO
   state=failed; a create whose engine raises still exits non-zero
   with exactly one state=failed (v75 behaviour intact).
3. long_video budgets: chapter_budget sums for a 14-min outline
   (>=13 min of speech), the budget line lands in chapter_brief.
4. render_chapters top-up: a chapter at <80% of budget is topped up
   exactly ONCE (extension render + join); at >=80% no top-up; a
   still-short top-up is not repeated; a passed deadline skips it.
5. make_long_video summary: actual vs target is reported honestly
   (7.7 of 14 min says so; topped-up chapters are named).
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


# ------------------------------------------------- 1. app_state guard
def test_app_state_guard():
    os.environ.setdefault("WORKER_URL", "http://worker.invalid")
    os.environ.setdefault("RUNNER_KEY", "rk")
    argv = sys.argv
    sys.argv = ["runner.py", "JOBX"]
    try:
        src = (HERE / "runner.py").read_text(encoding="utf-8")
        src = src.replace("asyncio.run(main())", "")
        ns = {"__name__": "runner_v78"}
        exec(compile(src, "runner.py", "exec"), ns)
    finally:
        sys.argv = argv
    posts = []
    ns["httpx"] = types.SimpleNamespace(
        post=lambda url, **kw: posts.append((url, kw)) or object())
    ns["app_state"]("failed", "early failure")
    ok("app_state: failure BEFORE delivery is posted",
       len(posts) == 1 and "runner/state" in posts[0][0], str(posts))
    ns["mark_result_delivered"]()
    ok("mark_result_delivered sets the flag", ns["_RESULT_DELIVERED"] is True)
    ns["app_state"]("failed", "WhatsApp upload failed: HTTP 413")
    ok("app_state: failure AFTER delivery is NOT posted", len(posts) == 1,
       str(posts))
    ns["app_state"]("running", "still working")
    ok("app_state: non-failure posts still flow after delivery",
       len(posts) == 2, str(posts))


# --------------------------------------- 2. subprocess delivered-wins
def test_subprocess_delivered_wins():
    tmp = Path(tempfile.mkdtemp(prefix="v78_rep_"))
    shutil.copy(HERE / "runner.py", tmp / "runner.py")
    # a tiny REAL mp4 (>=10 KB, valid duration) for the analysis gate
    vid = tmp / "vid.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=320x240:rate=30", "-f", "lavfi",
                    "-i", "sine=frequency=440", "-t", "2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(vid)],
                   check=True)
    (tmp / "whatsapp.py").write_text(
        "import os\n"
        "async def send_text(to, text):\n    return True\n"
        "async def send_media(to, path, kind, caption=None):\n"
        "    if os.environ.get('V78_WA_MODE') == 'raise':\n"
        "        raise RuntimeError('WhatsApp upload failed: HTTP 413')\n"
        "    return True\n"
        "async def download_media(mid, ext):\n"
        "    raise RuntimeError('no media in test')\n")
    (tmp / "autoedit.py").write_text(
        "async def auto_edit(*a, **k):\n"
        "    raise RuntimeError('unused in test')\n")
    (tmp / "create.py").write_text(
        "import os, shutil, types\n"
        f"VID = {str(vid)!r}\n"
        "def engine_module():\n"
        "    m = types.ModuleType('doc')\n"
        "    async def make_video(brief, chat, notify=None, **kw):\n"
        "        if os.environ.get('V78_ENGINE_MODE') == 'raise':\n"
        "            raise RuntimeError('kaboom chapter')\n"
        "        out = os.path.join(os.environ['DATA_DIR'], 'made.mp4')\n"
        "        shutil.copyfile(VID, out)\n"
        "        return {'path': out, 'duration': 2.0, 'title': 'T',\n"
        "                'lang': 'en', 'caption': 'c', 'topic': 't',\n"
        "                'plan': {}, 'summary': 's'}\n"
        "    m.make_video = make_video\n"
        "    return m\n")

    posts = {"state": [], "result": 0}

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
                    posts["state"].append(json.loads(raw or b"{}"))
                except Exception:
                    posts["state"].append({})
                return self._reply({"ok": True})
            if self.path.startswith("/api/runner/result"):
                posts["result"] += 1
                return self._reply({"ok": True})
            return self._reply({"ok": True})

        def do_GET(self):
            return self._reply({"ok": True, "amendments": []})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    env = {k: v for k, v in os.environ.items()
           if "proxy" not in k.lower()}
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env.update({"WORKER_URL": f"http://127.0.0.1:{port}",
                "RUNNER_KEY": "rk", "DATA_DIR": str(tmp / "data")})
    try:
        # the production shape: result delivered, then WA 413
        posts["state"].clear(); posts["result"] = 0
        env["V78_WA_MODE"] = "raise"; env["V78_ENGINE_MODE"] = "ok"
        r = subprocess.run([sys.executable, str(tmp / "runner.py"), "JOBX"],
                           cwd=tmp, env=env, capture_output=True, text=True,
                           timeout=180)
        failed = [p for p in posts["state"] if p.get("state") == "failed"]
        ok("delivered+WA413: runner exits ZERO", r.returncode == 0,
           f"rc={r.returncode} tail={r.stderr[-300:]}")
        ok("delivered+WA413: result posted exactly once",
           posts["result"] == 1, str(posts))
        ok("delivered+WA413: NO state=failed posted", failed == [],
           str(posts["state"]))
        # control: engine failure still reports exactly once (v75)
        posts["state"].clear(); posts["result"] = 0
        env["V78_WA_MODE"] = "ok"; env["V78_ENGINE_MODE"] = "raise"
        r = subprocess.run([sys.executable, str(tmp / "runner.py"), "JOBX"],
                           cwd=tmp, env=env, capture_output=True, text=True,
                           timeout=180)
        failed = [p for p in posts["state"] if p.get("state") == "failed"]
        ok("engine-failure: runner exits non-zero", r.returncode != 0,
           f"rc={r.returncode}")
        ok("engine-failure: state=failed posted exactly once",
           len(failed) == 1, str(posts["state"]))
    finally:
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------ 3. budgets
def test_budgets():
    import long_video
    out = {"title": "T", "chapters": [
        {"title": f"C{i}", "brief": "b", "minutes": 2} for i in range(7)]}
    budgets = [long_video.chapter_budget(ch) for ch in out["chapters"]]
    ok("budget: 14-min outline seconds sum to 840 (>= 13 min)",
       sum(b["seconds"] for b in budgets) == 840)
    ok("budget: chars sum covers >=13 min of speech (850/min)",
       sum(b["chars"] for b in budgets) >= 13 * 850,
       str(sum(b["chars"] for b in budgets)))
    ok("budget: a 2-min chapter is 300 words / 1700 chars",
       budgets[0] == {"seconds": 120, "words": 300, "chars": 1700},
       str(budgets[0]))
    brief = long_video.chapter_brief(out, 0)
    ok("chapter_brief carries the narration budget",
       "NARRATION BUDGET" in brief and "300 words" in brief
       and "1700 characters" in brief, brief[-260:])


# ------------------------------------------------------ 4. top-up
def test_topup():
    import doc
    import long_video

    class FakeMV:
        def __init__(self, durations):
            self.durations = list(durations)
            self.calls = []

        async def __call__(self, brief, chat, notify=None, workdir=None,
                           **kw):
            self.calls.append(brief)
            d = self.durations.pop(0) if self.durations else 999.0
            p = Path(workdir) / f"fake_{len(self.calls)}.mp4"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"0" * 2048)
            return {"path": str(p), "duration": float(d), "title": "T",
                    "lang": "en", "caption": "", "topic": "t",
                    "plan": {}, "broll": []}

    real_mv, real_join = doc.make_video, long_video._join_clips
    joins = []
    long_video._join_clips = lambda paths, out: joins.append(list(paths)) or out
    one_ch = {"title": "T", "chapters": [
        {"title": "Only", "brief": "b", "minutes": 2}]}
    try:
        # short chapter (40s of 120s) -> exactly ONE top-up
        fake = FakeMV([40, 75])
        doc.make_video = fake
        results = []
        paths = asyncio.run(long_video.render_chapters(
            one_ch, None, tempfile.mkdtemp(prefix="v78_tu_"),
            results_out=results))
        ok("top-up: short chapter triggers exactly one extension render",
           len(fake.calls) == 2, str(len(fake.calls)))
        ok("top-up: extension brief asks for the missing 80s",
           len(fake.calls) == 2 and "EXTENSION" in fake.calls[1]
           and "exactly 80 seconds" in fake.calls[1],
           fake.calls[1][-200:] if len(fake.calls) > 1 else "")
        ok("top-up: chapter joined once, duration summed, flag set",
           len(joins) == 1 and len(paths) == 1
           and results and results[0].get("topped_up") is True
           and abs(results[0].get("duration", 0) - 115) < 0.01,
           str(results))
        # healthy chapter (100s of 120s = 83%) -> no top-up
        joins.clear()
        fake = FakeMV([100])
        doc.make_video = fake
        results = []
        asyncio.run(long_video.render_chapters(
            one_ch, None, tempfile.mkdtemp(prefix="v78_tu_"),
            results_out=results))
        ok("top-up: chapter at >=80% is left alone",
           len(fake.calls) == 1 and not results[0].get("topped_up"),
           str(len(fake.calls)))
        # boundary: exactly 80% (96s) -> no top-up
        fake = FakeMV([96])
        doc.make_video = fake
        asyncio.run(long_video.render_chapters(
            one_ch, None, tempfile.mkdtemp(prefix="v78_tu_")))
        ok("top-up: chapter at exactly 80% is left alone",
           len(fake.calls) == 1, str(len(fake.calls)))
        # still short after the top-up -> NOT topped up twice
        fake = FakeMV([40, 10])
        doc.make_video = fake
        results = []
        asyncio.run(long_video.render_chapters(
            one_ch, None, tempfile.mkdtemp(prefix="v78_tu_"),
            results_out=results))
        ok("top-up: still-short chapter is topped up ONCE only",
           len(fake.calls) == 2
           and abs(results[0].get("duration", 0) - 50) < 0.01,
           f"calls={len(fake.calls)} res={results}")
        # deadline already passed -> partial semantics, no top-up
        fake = FakeMV([40])
        doc.make_video = fake
        asyncio.run(long_video.render_chapters(
            one_ch, None, tempfile.mkdtemp(prefix="v78_tu_"),
            deadline=time.monotonic() - 1))
        ok("top-up: passed deadline skips the top-up",
           len(fake.calls) == 1, str(len(fake.calls)))
    finally:
        doc.make_video = real_mv
        long_video._join_clips = real_join


# ------------------------------------------------- 5. honest summary
def test_summary():
    import long_video
    outline_json = json.dumps({"title": "Compromise", "chapters": [
        {"title": f"C{i}", "brief": f"brief {i}", "minutes": 2}
        for i in range(7)]})
    chat = lambda messages: outline_json  # noqa: E731
    real_render = long_video.render_chapters
    real_assemble = long_video.assemble
    real_probe = long_video._probe_duration

    async def fake_render(outline_data, chat_, workdir, notify=None,
                          deadline=None, results_out=None, ref_voice=None,
                          amendments=None):
        if results_out is not None:
            results_out.append({"path": "/tmp/x.mp4", "duration": 66.0,
                                "lang": "en", "caption": "", "topic": "t",
                                "plan": {}, "broll": [],
                                "topped_up": True})
        return ["/tmp/x.mp4"] * len(outline_data["chapters"])

    long_video.render_chapters = fake_render
    long_video.assemble = lambda parts, out, titles: out
    long_video._probe_duration = lambda p: 460.0  # the production 7.7 min
    try:
        res = asyncio.run(long_video.make_long_video(
            "compromise", chat, tempfile.mkdtemp(prefix="v78_sum_"), 14))
        ok("summary: reports actual minutes (7.7)",
           "7.7 min" in res["summary"], res["summary"])
        ok("summary: names the 14-min target when under-filled",
           "target 14 min" in res["summary"], res["summary"])
        ok("summary: names the topped-up chapter",
           "topped up" in res["summary"], res["summary"])
        ok("summary: not flagged partial when all chapters rendered",
           res["partial"] is False and "PARTIAL" not in res["summary"],
           res["summary"])
    finally:
        long_video.render_chapters = real_render
        long_video.assemble = real_assemble
        long_video._probe_duration = real_probe


if __name__ == "__main__":
    test_app_state_guard()
    test_subprocess_delivered_wins()
    test_budgets()
    test_topup()
    test_summary()
    print(f"\nv78test: {len(_fails)} failure(s)" if _fails else "\nv78test: ALL PASS")
    sys.exit(1 if _fails else 0)
