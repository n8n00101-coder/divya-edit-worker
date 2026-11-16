#!/usr/bin/env python3
"""v96 APP rig — the in-app live view presenting a DESKTOP (1280x800)
frame on a 412px phone: fit + zoom, a ticking email-wait step line,
and the honest no-Gmail-permission line. Real repo app/ + stub API
(route interception, the r5-rig pattern)."""
import base64
import json
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

RIG = Path(__file__).parent
APP = RIG.parent / "app"
SHOTS = RIG / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
NOW = int(time.time() * 1000)
ACCT = {"name": "Ajju", "email": "markk34200@gmail.com", "phone": "917993610173"}
FRAME = {"b64": ""}  # filled from a real 1280x800 browser screenshot below

SETUP_STATUS = {
    "ok": True, "active": True, "state": "paused", "consent": True,
    "providers": ["groq"], "done": [],
    "current": {"state": "paused", "provider": "groq", "step": "verify-email",
                "note": "Groq verification link nee email ki vachindhi — link ni nuvvu tap cheyyaku, Julie ne Gmail nunchi link theesi open chesi sign in avthundhi.",
                "pauseReason": "email", "pausedAt": NOW - 61000, "mailTries": 3,
                "mailFetchAt": NOW - 5000, "url": "https://console.groq.com/login",
                "verifyWait": True},
    "steps": [{"id": "groq", "name": "Groq", "state": "paused", "kind": "email",
               "text": "Groq", "note": "Verification link kosam wait chesthundhi"}],
    "gmail": {"state": "no-mail-yet", "provider": "groq"},
    "keys": {}, "keyList": [], "autoLog": [], "needsSetup": False,
}


def api_payload(path):
    p = path.split("?")[0].rstrip("/")
    if p.endswith("setup/status"):
        return SETUP_STATUS
    if p.endswith("setup/tc"):
        return {"ok": True, "active": True, "img": FRAME["b64"], "url": "https://console.groq.com/login"}
    seg = p.split("/")[-1]
    if seg == "health":
        return {"ok": True, "name": "divya"}
    if p.endswith("referral/me"):
        return {"ok": True, "code": "DVJCZZ", "invites": 1, "earned": 1000000}
    if seg == "me":
        return {"ok": True, "number": "917993610173", "account": ACCT}
    if seg == "status":
        return {"ok": True, "edits_left": 5, "edits_limit": 5, "edits_used": 0, "job": None}
    if seg == "plan":
        return {"ok": True, "plan": "free",
                "tok": {"weekLeft": 500000, "pool": 1000000000, "planLeft": 0, "videosWeek": 0, "weekEnds": "Monday"},
                "plans": {}}
    if seg == "connect":
        return {"ok": True, "providers": []}
    if seg == "history":
        return {"ok": True, "messages": []}
    if seg == "videos":
        return {"ok": True, "videos": []}
    if seg == "model":
        return {"ok": True, "model": None}
    return {"ok": True}


def handle(route):
    url = route.request.url
    if "/api/" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(api_payload(url.split("/api/", 1)[1])))
    else:
        route.continue_()


SEED = {"dv_apiIdx": "1", "dv_lang": "en", "dv_consent": True,
        "dv_token": "test-token", "dv_number": "917993610173", "dv_acct": ACCT,
        "dv_chatTabs_917993610173": {"activeId": "t1", "tabs": [{"id": "t1", "msgs": [], "ts": NOW - 60000}]}}
SEED_JS = "(() => { const items = %s; for (const [k,v] of Object.entries(items)) localStorage.setItem(k, JSON.stringify(v)); })()" % json.dumps(SEED)

DESKTOP_PAGE = """<!doctype html><html><body style="margin:0;font-family:system-ui;background:#fff">
<div style="background:#111;color:#fff;padding:14px 22px;font-size:20px">console.groq.com — desktop site header</div>
<div style="display:grid;grid-template-columns:280px 1fr;gap:20px;padding:22px">
<div style="background:#eee;min-height:500px;padding:14px">DESKTOP SIDEBAR<br>Dashboard<br>API Keys<br>Settings</div>
<main><h1 style="font-size:34px">Check your email</h1><p style="font-size:18px">An email was sent to markk34200@gmail.com.</p>
<p style="font-size:15px">This frame is a real 1280x800 desktop page — wide two-column layout, desktop navigation.</p></main></div>
</body></html>"""

results = {}


def check(name, ok, detail=""):
    results[name] = {"pass": bool(ok), "detail": str(detail)[:300]}
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: Quiet(*a, directory=str(APP), **k))
threading.Thread(target=srv.serve_forever, daemon=True).start()
APPURL = f"http://127.0.0.1:{srv.server_address[1]}/"

with sync_playwright() as pw:
    b = pw.chromium.launch()
    # the "runner frame": a genuine 1280x800 desktop-page screenshot
    dctx = b.new_context(viewport={"width": 1280, "height": 800})
    dp = dctx.new_page()
    dp.set_content(DESKTOP_PAGE)
    dp.wait_for_timeout(300)
    FRAME["b64"] = base64.b64encode(dp.screenshot(type="jpeg", quality=60)).decode()
    dctx.close()

    ctx = b.new_context(viewport={"width": 412, "height": 915}, is_mobile=True, has_touch=True, color_scheme="dark")
    ctx.add_init_script(SEED_JS)
    page = ctx.new_page()
    page.route("**/api/**", handle)
    for pat in ("**://cdn.jsdelivr.net/**", "**://esm.sh/**", "**://huggingface.co/**", "**://*.hf.co/**"):
        page.route(pat, lambda r: r.abort())
    page.goto(APPURL)
    page.wait_for_timeout(3500)

    # drive the real status path: pollSetup -> renderSetupBox stashes
    # __lvJob/__lvGmail and renders the chat browser card
    page.evaluate("pollSetup()")
    page.wait_for_timeout(1500)
    stash = page.evaluate("({job: window.__lvJob || null, gmail: window.__lvGmail || null})")
    check("status path stashed the mail-wait fields", bool(stash["job"]) and stash["job"].get("mailTries") == 3
          and stash["gmail"] == "no-mail-yet", json.dumps(stash)[:200])

    page.evaluate("openLive(false)")
    page.wait_for_timeout(2200)
    nat = page.evaluate("(() => { const im = document.querySelector('[data-lv-img]'); return im ? [im.naturalWidth, im.naturalHeight] : null; })()")
    check("live view frame is the DESKTOP 1280x800 frame", nat == [1280, 800], str(nat))
    line1 = page.evaluate("document.querySelector('[data-lv-step]').textContent")
    check("wait line: doing + check count", "Waiting for the verification mail" in line1 and "check 3" in line1, line1)
    page.screenshot(path=str(SHOTS / "app-live-wait.png"))
    page.wait_for_timeout(3400)
    line2 = page.evaluate("document.querySelector('[data-lv-step]').textContent")
    check("wait line TICKS (elapsed time moves)", line1 != line2, f"{line1!r} -> {line2!r}")

    # honest no-permission state (what renderSetupBox stashes when the
    # Worker reports gmail.state = no-token)
    page.evaluate("window.__lvGmail = 'no-token'")
    page.wait_for_timeout(2000)
    line3 = page.evaluate("document.querySelector('[data-lv-step]').textContent")
    check("no-Gmail-permission line is honest + names the one fix",
          "doesn't have your Gmail permission" in line3 and "Allow Gmail access" in line3, line3)
    page.screenshot(path=str(SHOTS / "app-live-notoken.png"))
    page.evaluate("window.__lvGmail = 'no-mail-yet'")

    # zoom: desktop frame at 200%, pannable
    page.click("[data-lv-zoom]")
    page.wait_for_timeout(400)
    zoom = page.evaluate("(() => { const st = document.querySelector('.lv-stage'); const im = document.querySelector('[data-lv-img]'); return {cls: st.className, iw: im.getBoundingClientRect().width, sw: st.getBoundingClientRect().width}; })()")
    check("zoom toggles a pannable 200% view", "zoom" in zoom["cls"] and zoom["iw"] > zoom["sw"] * 1.5,
          json.dumps(zoom))
    page.screenshot(path=str(SHOTS / "app-live-zoom.png"))
    page.click("[data-lv-zoom]")  # back to fit

    # controls intact
    btns = page.evaluate("['data-lv-stop','data-lv-take','data-lv-done','data-lv-mini'].map(a => !!document.querySelector('[' + a + ']'))")
    check("Stop / Take control / I-did-it / mini box all present", all(btns), str(btns))
    page.evaluate("closeLive()")
    page.wait_for_timeout(600)
    page.evaluate("go('chat')")
    page.wait_for_timeout(1200)

    # chat browser card now carries the desktop frame ratio
    card = page.evaluate("(() => { const im = document.querySelector('.browser-card img'); if (!im) return null; const r = im.getBoundingClientRect(); return {w: r.width, h: r.height, ratio: r.height ? +(r.width / r.height).toFixed(2) : 0}; })()")
    check("chat browser-card shows the desktop frame (16/10)", bool(card) and 1.45 <= card["ratio"] <= 1.75,
          json.dumps(card))
    page.screenshot(path=str(SHOTS / "app-chat-card.png"))
    ctx.close()
    b.close()

fails = [k for k, v in results.items() if not v["pass"]]
(RIG / "report-app.json").write_text(json.dumps({"results": results}, indent=1))
print("RESULT:", "ALL PASS" if not fails else f"FAILURES: {fails}")
sys.exit(1 if fails else 0)
