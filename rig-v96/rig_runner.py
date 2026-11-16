#!/usr/bin/env python3
"""v96 RUNNER rig — desktop viewport, cookie-banner dismissal, visible
email-verification wait. Drives the REAL setup.py (this branch) against
a stub Worker + local test pages, and asserts on what the stub Worker
received (frames + progress) and what the pages show."""
import hashlib
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RIG = Path(__file__).parent
ROOT = RIG.parent
SHOTS = RIG / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

# The VM's egress-proxy env makes httpx choke while building its client
# (Invalid port ':1]'); production runners have no proxy vars, and the
# stub Worker is on loopback anyway.
for _v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy",
           "NO_PROXY", "no_proxy"):
    os.environ.pop(_v, None)
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

STATE = {"polls": 0, "frames": [], "progress": [], "feed_on_poll": 3}
BASE = ""

CHECK_EMAIL = """<!doctype html><html><head><meta charset="utf-8"><title>Groq — check email</title>
<style>body{font-family:system-ui;margin:0} #layout{display:grid;grid-template-columns:300px 1fr;gap:24px;padding:32px}
#side{background:#111;color:#fff;padding:20px;min-height:400px} #badge{font-weight:800;font-size:28px}
.truste_box_overlay{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:2px solid #333;padding:18px;z-index:999}
button{padding:10px 18px;margin-right:8px}</style></head><body>
<div id="layout"><div id="side">SIDEBAR — desktop only nav</div>
<main><div id="badge">…</div><h1>Check your email</h1><p>An email was sent to rig@example.com.</p><button>Try again</button></main></div>
<div id="truste-consent-track"><div class="truste_box_overlay"><h3>We Value Your Privacy</h3>
<p>We and our vendors use cookies and similar technologies to enhance your experience.</p>
<button id="acc">Accept All</button><button id="rej">Reject All</button><button id="cust">Customize My Choices</button></div></div>
<script>
document.getElementById('badge').textContent = window.innerWidth >= 1024 ? 'DESKTOP LAYOUT' : 'MOBILE LAYOUT';
const kill = v => { window.__bannerChoice = v; try { localStorage.setItem('__bannerChoice', v); } catch (e) {} document.getElementById('truste-consent-track').remove(); };
document.getElementById('rej').onclick = () => kill('reject');
document.getElementById('acc').onclick = () => kill('accept');
</script></body></html>"""

LANDING = """<!doctype html><html><head><meta charset="utf-8"><title>Verify</title></head><body>
<h1>Confirm your sign in</h1><p>One more step.</p>
<button id="cfm">Confirm sign in</button>
<script>document.getElementById('cfm').onclick = () => { document.body.innerHTML = '<h1>Confirmed</h1>'; setTimeout(() => location.href = '/t/keys', 900); };</script>
</body></html>"""

KEYS = """<!doctype html><html><head><meta charset="utf-8"><title>Console</title></head><body>
<h1>API Keys</h1><button>Create API Key</button><p>Your keys live here.</p></body></html>"""

PAGES = {"/t/check-email": CHECK_EMAIL, "/landing": LANDING, "/t/keys": KEYS}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in PAGES:
            return self._send(PAGES[path], "text/html; charset=utf-8")
        if "/api/setup/runner/job" in self.path:
            STATE["polls"] += 1
            job = {"state": "paused", "provider": "groq", "tcInputs": []}
            if STATE["polls"] >= STATE["feed_on_poll"]:
                job = {"state": "running", "provider": "groq", "tcInputs": [],
                       "verifyLink": BASE + "/landing"}
            return self._send(json.dumps({"job": job}))
        return self._send(json.dumps({"ok": True}))

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        if "/tcframe" in self.path:
            img = data.get("img") or ""
            STATE["frames"].append({"at": time.time(),
                                     "sha": hashlib.sha256(img.encode()).hexdigest()[:12],
                                     "url": data.get("url", ""), "kb": round(len(img) * 3 / 4096)})
        elif "/progress" in self.path:
            STATE["progress"].append({"at": time.time(), "state": data.get("state"),
                                       "step": data.get("step"), "note": data.get("note", "")})
        return self._send(json.dumps({"ok": True}))


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
BASE = f"http://127.0.0.1:{srv.server_address[1]}"
threading.Thread(target=srv.serve_forever, daemon=True).start()

os.environ.update({"WORKER_URL": BASE, "RUNNER_KEY": "rig", "JOB": "rigjob",
                   "PROVIDER": "groq", "BROWSER_MODE": "ephemeral"})
sys.path.insert(0, str(ROOT))
import setup  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

results = {}


def check(name, ok, detail=""):
    results[name] = {"pass": bool(ok), "detail": str(detail)[:300]}
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


with sync_playwright() as pw:
    browser = setup.launch_browser(pw)
    ctx = setup.open_context(browser)
    page = ctx.new_page()
    setup._CUR["page"] = page

    # 1. desktop viewport + desktop layout + banner auto-dismissed by goto()
    setup.goto(page, BASE + "/t/check-email")
    page.wait_for_timeout(600)
    iw, ih = page.evaluate("[window.innerWidth, window.innerHeight]")
    check("viewport is desktop 1280x800", (iw, ih) == (1280, 800), f"{iw}x{ih}")
    badge = page.text_content("#badge")
    check("site renders DESKTOP layout", badge == "DESKTOP LAYOUT", badge)
    choice = page.evaluate("window.__bannerChoice || ''")
    gone = page.evaluate("!document.getElementById('truste-consent-track')")
    check("cookie banner auto-dismissed on goto (Reject chosen)", choice == "reject" and gone,
          f"choice={choice} gone={gone}")
    cur = page.evaluate("(() => { const c = document.getElementById('__julie_cursor'); return c ? c.style.left + ',' + c.style.top : 'missing'; })()")
    check("agent cursor present and travelled to the click", cur not in ("missing", "0px,0px", ","), f"cursor at {cur}")
    page.screenshot(path=str(SHOTS / "runner-desktop-nobanner.png"))

    # profile-mode kwargs carry the desktop viewport too
    kw = setup.profile_context_kwargs()
    check("profile context kwargs are desktop", kw["viewport"] == {"width": 1280, "height": 800}
          and not kw.get("is_mobile") and not kw.get("has_touch"), json.dumps(kw.get("viewport")))

    # pill mechanism
    setup.set_pill(page, "TEST PILL 123")
    page.wait_for_timeout(200)
    pill = page.evaluate("(() => { const t = document.getElementById('__julie_pill_text'); const p = document.getElementById('__julie_pill'); return t ? t.textContent + '|' + p.style.display : 'missing'; })()")
    check("status pill renders in-page", pill.startswith("TEST PILL 123"), pill)
    setup.set_pill(page, "")

    # 2. the email-verification wait — banner returns on a fresh load,
    #    the pause entry must clear it, the wait must visibly tick, the
    #    fed link must be opened + Confirm clicked + sign-in verified.
    page.goto(BASE + "/t/check-email")  # raw goto: banner is back
    page.wait_for_timeout(400)
    t0 = time.time()
    frames_before = len(STATE["frames"])
    cfg = {"name": "Groq", "keys_url": BASE + "/t/keys"}
    ok = setup.pause_for_email_verify(page, {}, cfg)
    check("pause_for_email_verify completes via fed link", ok is True, f"took {time.time()-t0:.0f}s")
    choice2 = page.evaluate("localStorage.getItem('__bannerChoice') || ''")
    check("banner dismissed at pause entry too", choice2 == "reject", f"choice={choice2}")
    wait_frames = [f for f in STATE["frames"][frames_before:] if t0 <= f["at"] <= t0 + 45]
    distinct = {f["sha"] for f in wait_frames}
    check("wait streamed >=3 DISTINCT frames (pill ticking)", len(wait_frames) >= 3 and len(distinct) >= 3,
          f"{len(wait_frames)} frames, {len(distinct)} distinct, sizes kb={ [f['kb'] for f in wait_frames[:5]] }")
    notes = [p["note"] for p in STATE["progress"] if "check" in (p["note"] or "")]
    check("job note ticked with check counts", len(notes) >= 1 and any("check 1" in n for n in notes),
          notes[-1] if notes else "no check notes")
    check("final page is the signed-in keys page", page.url.endswith("/t/keys"), page.url)
    page.screenshot(path=str(SHOTS / "runner-keys-signedin.png"))
    ctx.close()
    browser.close()

fails = [k for k, v in results.items() if not v["pass"]]
(RIG / "report.json").write_text(json.dumps({"base": BASE, "results": results,
                                            "frames_total": len(STATE["frames"]),
                                            "progress_posts": len(STATE["progress"])}, indent=1))
print("RESULT:", "ALL PASS" if not fails else f"FAILURES: {fails}")
sys.exit(1 if fails else 0)
