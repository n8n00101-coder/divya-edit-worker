#!/usr/bin/env python3
"""R5 proof rig: NO-BANDS floating chrome (Z1 glass/full-bleed, Z2 insets,
Z3 profile Tokens dedupe) + theme finding. Real repo app/ + stub API,
360px headless Chromium (Playwright), both themes."""
import glob, json, sys, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

RIG = Path(__file__).parent
APP = RIG.parent / "app"
SHOTS = RIG / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
NOW = int(time.time() * 1000)
ACCT = {"name": "Ajju", "email": "markk34200@gmail.com", "phone": "917993610173"}

MSGS = []
for i in range(1, 27):
    role = "user" if i % 2 else "assistant"
    body = (f"R5 probe message {i} — " +
            ("Julie, open YouTube and scroll the transcript panel step by step, then tell me the summary of the video. " if role == "user"
             else "Working on it — I opened the video page and I am reading the transcript panel carefully, section by section. ") +
            "This is a mid-length message so the list scrolls well past both chrome zones at 360px width.")
    MSGS.append({"r": role, "c": body})
TABS = {"activeId": "t1", "tabs": [{"id": "t1", "msgs": MSGS, "ts": NOW - 60000}]}

def api_payload(path):
    p = path.split("?")[0].rstrip("/").split("/")[-1]
    if p == "health": return {"ok": True, "name": "divya"}
    if path.endswith("referral/me"): return {"ok": True, "code": "DVJCZZ", "invites": 1, "earned": 1000000}
    if path.endswith("setup/status"): return {"ok": True, "active": False, "needsSetup": False, "state": "done", "steps": [], "autoLog": []}
    if p == "me": return {"ok": True, "number": "917993610173", "account": ACCT}
    if p == "status": return {"ok": True, "edits_left": 5, "edits_limit": 5, "edits_used": 0, "job": None}
    if p == "plan": return {"ok": True, "plan": "free",
                            "tok": {"weekLeft": 500000, "pool": 1000000000, "planLeft": 0, "videosWeek": 0, "weekEnds": "Monday"},
                            "plans": {"free": {"name": "Free", "monthly": 0, "grant": 500000, "voice": True},
                                      "creator": {"name": "Creator", "monthly": 129, "grant": 5000000, "voice": True},
                                      "pro": {"name": "Pro", "monthly": 499, "grant": 25000000, "voice": True}}}
    if p == "connect": return {"ok": True, "providers": [
        {"id": "youtube", "name": "YouTube", "connected": True, "who": "markk34200@gmail.com", "ready": True},
        {"id": "google", "name": "Google", "connected": True, "who": "markk34200@gmail.com", "ready": True},
        {"id": "instagram", "name": "Instagram", "connected": False, "ready": True, "desc": "Post Reels"},
        {"id": "facebook", "name": "Facebook", "connected": False, "ready": True, "desc": "Post to your Page"},
        {"id": "telegram", "name": "Telegram", "connected": False, "ready": False, "desc": "Julie on Telegram too"}]}
    if p == "history": return {"ok": True, "messages": []}
    if p == "videos": return {"ok": True, "videos": []}
    if p == "model": return {"ok": True, "model": None}
    return {"ok": True}

def make_handler():
    def handle(route):
        url = route.request.url
        if "/api/" in url:
            body = api_payload(url.split("/api/", 1)[1])
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        else:
            route.continue_()
    return handle

def seed_js(theme):
    items = {"dv_apiIdx": "1", "dv_lang": "en", "dv_consent": True,
             "dv_token": "test-token", "dv_number": "917993610173", "dv_acct": ACCT,
             "dv_chatTabs_917993610173": TABS}
    if theme: items["dv_theme"] = theme
    return "(() => { const items = %s; for (const [k,v] of Object.entries(items)) localStorage.setItem(k, JSON.stringify(v)); })()" % json.dumps(items)

MEASURE = r"""() => {
  const R = el => { if (!el) return null; const r = el.getBoundingClientRect(); return {x:r.x, y:r.y, w:r.width, h:r.height, right:r.right, bottom:r.bottom}; };
  const inter = (a,b) => !!(a && b && a.x < b.right - 1 && a.right > b.x + 1 && a.y < b.bottom - 1 && a.bottom > b.y + 1);
  const cs = (el, prop) => el ? getComputedStyle(el)[prop] : null;
  const alpha = c => { if (!c) return null; const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return c; const parts = m[1].split(','); return parts.length === 4 ? parseFloat(parts[3]) : 1; };
  const chips = ["#menuBtn", "#newTabBtn", "#tabCountBtn", "#avatarBtn"].map(s => R(document.querySelector(s)));
  const appbar = document.querySelector(".appbar"), main = document.querySelector("#main");
  const tabbar = document.querySelector(".tabbar"), wrap = document.querySelector(".composer-wrap");
  const chipEl = document.querySelector("#menuBtn"), comp = document.querySelector(".composer");
  return {
    appbarBg: cs(appbar, "backgroundColor"), mainPadTop: cs(main, "paddingTop"),
    tabbarPos: cs(tabbar, "position"), wrapPos: cs(wrap, "position"),
    chipBg: cs(chipEl, "backgroundColor"), chipAlpha: alpha(cs(chipEl, "backgroundColor")), chipFilter: cs(chipEl, "backdropFilter"),
    compBg: cs(comp, "backgroundColor"), compAlpha: alpha(cs(comp, "backgroundColor")), compFilter: cs(comp, "backdropFilter"),
    barBg: cs(tabbar, "backgroundColor"), barAlpha: alpha(cs(tabbar, "backgroundColor")), barFilter: cs(tabbar, "backdropFilter"),
    chips, chipsBottom: Math.max(...chips.filter(Boolean).map(c => c.bottom)),
    tabbarR: R(tabbar), wrapR: R(wrap), heroR: R(document.querySelector(".chat-hero")),
    bodyBg: cs(document.body, "backgroundColor"), dataTheme: document.documentElement.dataset.theme
  };
}"""

CHAT_CHECK = r"""() => {
  const R = el => { if (!el) return null; const r = el.getBoundingClientRect(); return {x:r.x, y:r.y, w:r.width, h:r.height, right:r.right, bottom:r.bottom}; };
  const inter = (a,b) => !!(a && b && a.x < b.right - 1 && a.right > b.x + 1 && a.y < b.bottom - 1 && a.bottom > b.y + 1);
  const msgs = [...document.querySelectorAll("#msgs .msg")];
  const byText = n => msgs.find(m => m.textContent.includes("R5 probe message " + n));
  const chips = ["#menuBtn", "#newTabBtn", "#tabCountBtn", "#avatarBtn"].map(s => R(document.querySelector(s))).filter(Boolean);
  const hero = R(document.querySelector(".chat-hero"));
  const wrap = R(document.querySelector(".composer-wrap")), bar = R(document.querySelector(".tabbar"));
  const first = byText(1), last = byText(26);
  const anyBehindTop = msgs.some(m => chips.some(c => inter(R(m), c)));
  const anyBehindBottom = msgs.some(m => inter(R(m), wrap) || inter(R(m), bar));
  return { count: msgs.length,
    firstVsChips: first ? chips.map(c => inter(R(first), c)) : null,
    firstVsHero: first ? inter(R(first), hero) : null,
    lastR: last ? R(last) : null, wrapTop: wrap ? wrap.y : null, barTop: bar ? bar.y : null,
    anyBehindTop, anyBehindBottom };
}"""

PROF_CHECK = r"""() => {
  const R = el => { if (!el) return null; const r = el.getBoundingClientRect(); return {x:r.x, y:r.y, w:r.width, h:r.height, right:r.right, bottom:r.bottom}; };
  const inter = (a,b) => !!(a && b && a.x < b.right - 1 && a.right > b.x + 1 && a.y < b.bottom - 1 && a.bottom > b.y + 1);
  const chips = ["#menuBtn", "#newTabBtn", "#tabCountBtn", "#avatarBtn"].map(s => R(document.querySelector(s))).filter(Boolean);
  const head = R(document.querySelector(".prof-head"));
  const rows = [...document.querySelectorAll("#s-profile .list .row")];
  const tokRows = rows.filter(rw => (rw.querySelector("span")?.textContent || "").trim() === "Tokens");
  const logout = R(document.querySelector("#profLogout"));
  const bar = R(document.querySelector(".tabbar"));
  return { headVsChips: head ? chips.map(c => inter(head, c)) : null, headTop: head ? head.y : null,
    chipsBottom: Math.max(...chips.map(c => c.bottom)),
    tokensRows: tokRows.length, tokensRowTag: tokRows[0] ? tokRows[0].tagName : null,
    tokensRowHref: tokRows[0] ? tokRows[0].getAttribute("href") : null,
    logoutBottom: logout ? logout.bottom : null, barTop: bar ? bar.y : null };
}"""

def run_theme(browser, base, theme, scheme):
    ctx = browser.new_context(viewport={"width": 360, "height": 740}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, color_scheme=scheme,
                              user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36")
    ctx.add_init_script(seed_js(theme))
    page = ctx.new_page()
    page.route("**/api/**", make_handler())
    for pat in ("**://cdn.jsdelivr.net/**", "**://huggingface.co/**", "**://*.hf.co/**"):
        page.route(pat, lambda r: r.abort())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)[:140]))
    tag = theme or f"auto-{scheme}"
    page.goto(base + "#/chat"); page.wait_for_timeout(1600)
    m = page.evaluate(MEASURE)
    top = page.evaluate(CHAT_CHECK)
    page.evaluate("() => { const m = document.querySelector('#msgs'); m.scrollTop = Math.round(m.scrollHeight * 0.45); }")
    page.wait_for_timeout(350)
    mid = page.evaluate(CHAT_CHECK)
    page.screenshot(path=str(SHOTS / f"chat-mid-{tag}.png"))
    page.evaluate("() => { const m = document.querySelector('#msgs'); m.scrollTop = m.scrollHeight; }")
    page.wait_for_timeout(350)
    bot = page.evaluate(CHAT_CHECK)
    page.screenshot(path=str(SHOTS / f"chat-bottom-{tag}.png"))
    page.evaluate("location.hash = '#/profile'"); page.wait_for_timeout(900)
    prof = page.evaluate(PROF_CHECK)
    page.screenshot(path=str(SHOTS / f"profile-top-{tag}.png"))
    page.evaluate("() => { const s = document.querySelector('#s-profile .scroll'); s.scrollTop = s.scrollHeight; }")
    page.wait_for_timeout(350)
    profBot = page.evaluate(PROF_CHECK)
    page.screenshot(path=str(SHOTS / f"profile-bottom-{tag}.png"))
    ctx.close()
    return {"measure": m, "chatTop": top, "chatMid": mid, "chatBottom": bot,
            "profile": prof, "profileBottom": profBot, "pageerrors": errs}

def main():
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    handler = lambda *a, **k: Quiet(*a, directory=str(APP), **k)
    srv = ThreadingHTTPServer(("127.0.0.1", 8935), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:8935/index.html"
    out = {}
    with sync_playwright() as pw:
        shell = sorted(glob.glob(str(Path.home() / ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")))[-1]
        browser = pw.chromium.launch(executable_path=shell)
        out["dark"] = run_theme(browser, base, "dark", "dark")
        out["light"] = run_theme(browser, base, "light", "light")
        out["autoLight"] = run_theme(browser, base, None, "light")
        out["autoDark"] = run_theme(browser, base, None, "dark")
    (RIG / "report.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)[:6000])

if __name__ == "__main__":
    main()
