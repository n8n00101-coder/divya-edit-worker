#!/usr/bin/env python3
"""R4 full-app visual audit driver: real Julie app (repo app/) + stub API with
worst-case data, 360px headless Chromium (Playwright), per-screen automated
overflow/overlap detection (detect.js) + screenshots."""
import base64, json, sys, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

RIG = Path(__file__).parent
APP = RIG.parent / "app"
PASS = sys.argv[1] if len(sys.argv) > 1 else "pre"
SHOTS = RIG / "shots" / PASS
SHOTS.mkdir(parents=True, exist_ok=True)
DETECT = (RIG / "detect.js").read_text()
MEASURE_JS = r"""() => {
  const out = {};
  const bb = el => { if (!el) return null; const r = el.getBoundingClientRect(); return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), right: Math.round(r.right), bottom: Math.round(r.bottom)}; };
  out.header = { menu: bb(document.querySelector("#menuBtn")), plus: bb(document.querySelector("#newTabBtn")), tabchip: bb(document.querySelector("#tabCountBtn")), avatar: bb(document.querySelector("#avatarBtn")), position: getComputedStyle(document.querySelector(".appbar")).position };
  out.tabchipText = document.querySelector("#tabCountBtn") ? document.querySelector("#tabCountBtn").textContent.trim() : null;
  const send = document.querySelector("#chatSend"), ta = document.querySelector("#input");
  if (send && ta) { const cs = getComputedStyle(ta); out.composer = { send: bb(send), taBorderW: cs.borderTopWidth, taBorderStyle: cs.borderStyle, taBg: cs.backgroundColor, pill: bb(document.querySelector(".composer")) }; }
  const bar = document.querySelector(".tabbar"), act = document.querySelector(".tabbar a[aria-current=page]");
  if (bar) { const br = bar.getBoundingClientRect(); out.tabbar = { x: Math.round(br.x), right: Math.round(br.right), w: Math.round(br.width), radius: getComputedStyle(bar).borderRadius, labelWidths: [...bar.querySelectorAll("a > span:not(.tv-orb)")].map(sp => Math.round(sp.getBoundingClientRect().width)), active: act ? { bg: getComputedStyle(act).backgroundColor, w: Math.round(act.getBoundingClientRect().width), h: Math.round(act.getBoundingClientRect().height) } : null }; }
  return out;
}"""

FRAME_B64 = base64.b64encode((RIG / "frame.jpg").read_bytes()).decode()

ACCT = {"name": "Ajju Mark Kumar", "email": "markk34200@gmail.com", "phone": "917993610173"}
NOW = int(time.time() * 1000)

PROVIDERS = ["groq", "openrouter", "gemini", "cohere", "together", "sambanova", "fireworks",
             "cerebras", "nvidia", "mistral", "ai21", "voyage", "tavily", "serper", "exa",
             "deepgram", "assemblyai", "elevenlabs", "stability", "jina", "pexels"]
PNAMES = {"groq": "Groq", "openrouter": "OpenRouter", "gemini": "Gemini", "cohere": "Cohere",
          "together": "Together AI", "sambanova": "SambaNova", "fireworks": "Fireworks AI",
          "cerebras": "Cerebras", "nvidia": "NVIDIA NIM", "mistral": "Mistral AI", "ai21": "AI21",
          "voyage": "Voyage AI", "tavily": "Tavily", "serper": "Serper", "exa": "Exa",
          "deepgram": "Deepgram", "assemblyai": "AssemblyAI", "elevenlabs": "ElevenLabs",
          "stability": "Stability AI", "jina": "Jina AI", "pexels": "Pexels"}

def steps_a():
    out = []
    for i, p in enumerate(PROVIDERS):
        st = {"id": p, "name": PNAMES[p], "state": "queued"}
        if p == "groq":
            st.update(state="paused", kind="signin",
                      note="Sign-in kavali — console.groq.com lo login avvali, tarvatha Julie thane key create chesthundhi")
        elif p in ("openrouter", "gemini"):
            st.update(state="done")
        elif p == "cohere":
            st.update(state="failed",
                      note="Key create ayyindhi kaani test fail ayyindhi — invalid API key format, migilina steps tho continue chesthunna")
        out.append(st)
    return out

AUTOLOG = [
    {"at": NOW - 3600000, "provider": "openrouter", "action": "still-missing — OpenRouter key ledu", "why": "", "result": "failed"},
    {"at": NOW - 3600000, "provider": "groq", "action": "still-missing — Groq key ledu", "why": "https://console.groq.com/keys lo sign-in kosam wait chesthundhi", "result": "failed"},
    {"at": NOW - 7200000, "provider": "openrouter", "action": "provisioning — OpenRouter key ledu", "why": "", "result": "started"},
    {"at": NOW - 7200000, "provider": "gemini", "action": "provisioning — Gemini key create chesi test chesindhi, pani chesthundhi", "why": "", "result": "done"},
]

STATUS_A = {"ok": True, "active": True, "needsSetup": True, "state": "paused-signin", "keyTier": "inviter",
            "gmail": {"state": "no-mail-yet", "provider": "groq"}, "steps": steps_a(),
            "current": {"state": "paused", "site": "console.groq.com", "step": "verify-email",
                        "note": "Verification mail kosam chusthunna — mail vachaka Julie thane link open chesthundhi",
                        "url": "https://console.groq.com/keys"},
            "action": {"tc": True, "url": "https://console.groq.com/keys"}, "autoLog": AUTOLOG}
STATUS_B = {"ok": True, "active": True, "needsSetup": True, "state": "running", "keyTier": "own",
            "gmail": {"state": "ok", "provider": "groq"},
            "steps": [dict(s, state=("done" if s["id"] in ("openrouter", "gemini") else "running" if s["id"] == "groq" else "queued")) for s in steps_a()],
            "current": {"state": "running", "site": "youtube.com", "step": "transcript",
                        "note": "Opening the video page — scrolling to the transcript panel step by step",
                        "url": "https://www.youtube.com/watch?v=dQw4y9WgXcQ"},
            "action": {"tc": False, "url": "https://www.youtube.com/watch?v=dQw4y9WgXcQ"}, "autoLog": AUTOLOG}

def api_payload(path, scenario):
    p = path.split("?")[0].rstrip("/").split("/")[-1]
    if p == "health": return {"ok": True, "name": "divya"}
    if path.endswith("referral/me"): return {"ok": True, "code": "DVJCZZ", "invites": 1, "earned": 1000000}
    if path.endswith("setup/status"): return STATUS_A if scenario == "A" else STATUS_B
    if p == "me": return {"ok": True, "number": "917993610173", "account": ACCT}
    if p == "status": return {"ok": True, "edits_left": 2, "edits_limit": 5, "edits_used": 3,
                              "job": {"state": "done", "at": NOW - 5400000, "upd": NOW - 3600000,
                                      "note": "Rendering the solar system documentary — chapter 3 of 7, captions + music"}}
    if p == "plan": return {"ok": True, "plan": "free", "edits_left": 2, "edits_limit": 5, "edits_used": 3,
                            "tok": {"weekLeft": 499999, "pool": 1001000000, "planLeft": 0, "videosWeek": 2, "weekEnds": "Monday"},
                            "plans": {"free": {"name": "Free", "monthly": 0, "grant": 500000, "voice": True},
                                      "creator": {"name": "Creator", "monthly": 129, "grant": 5000000, "voice": True},
                                      "pro": {"name": "Pro", "monthly": 499, "grant": 25000000, "voice": True},
                                      "family": {"name": "Premium Unlimited Family", "monthly": 1299, "grant": 100000000, "voice": True}}}
    if p == "connect": return {"ok": True, "providers": [
        {"id": "youtube", "name": "YouTube", "connected": True, "noAccount": True, "who": "markk34200@gmail.com", "ready": True},
        {"id": "google", "name": "Google", "connected": True, "who": "markk34200@gmail.com", "ready": True},
        {"id": "instagram", "name": "Instagram", "connected": False, "ready": True, "desc": "Post Reels"},
        {"id": "facebook", "name": "Facebook", "connected": False, "ready": True, "desc": "Post to your Page"},
        {"id": "telegram", "name": "Telegram", "connected": False, "ready": False, "desc": "Julie on Telegram too"}]}
    if p == "keys": return {"ok": True, "count": 3, "keys": [
        {"name": "Groq", "version": "llama-3.3-70b-versatile", "ok": True, "source": "divya"},
        {"name": "Gemini", "version": "gemini-2.0-flash-exp", "ok": True, "source": "manual"},
        {"name": "OpenRouter", "version": "openai/gpt-oss-120b:free", "ok": False, "source": "divya"}]}
    if p == "tc": return {"ok": True, "active": True, "url": "https://console.groq.com/keys", "img": FRAME_B64}
    if p == "model": return {"ok": True, "model": {"name": "llama-3.3-70b-versatile"}}
    if p == "history": return {"ok": True, "messages": []}
    if p == "videos": return {"ok": True, "videos": [
        {"n": 1, "job": "job1", "title": "The Solar System Documentary — Full Narrated Version With Captions And Background Music", "kind": "long", "length": "7:42", "at": NOW - 86400000, "state": "done", "has_result": True,
         "yt": {"url": "https://youtube.com/watch?v=abcdefghijk"}, "ig": {"url": "https://instagram.com/reel/C1234567890abcdef"}},
        {"n": 2, "job": "job2", "title": "Morning motivation short", "kind": "short", "length": "0:45", "at": NOW - 3600000, "state": "running", "has_result": False},
        {"n": 3, "job": "job3", "title": "Failed edit with a somewhat long title to test wrapping behaviour", "kind": "short", "length": "0:30", "at": NOW - 7200000, "state": "failed", "has_result": False}]}
    return {"ok": True}

def make_handler(scenario):
    def handle(route):
        url = route.request.url
        if "/api/" in url:
            path = url.split("/api/", 1)[1]
            body = api_payload(path, scenario)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        else:
            route.continue_()
    return handle

STRESS_MSGS = [
    {"r": "user", "c": "Please upload this video to my YouTube channel https://www.youtube.com/watch?v=dQw4y9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf and also check https://console.groq.com/keys/settings/billing-overview for the API key"},
    {"r": "assistant", "c": "Sure — I opened the video page and I am scrolling to the transcript panel step by step. " + "a" * 120 + " (that long token should wrap, not spill)"},
    {"r": "user", "c": "ok"},
    {"r": "assistant", "c": "Done ✓ — video 1 is ready. Watch it here: https://divya.n8n00101.workers.dev/api/result?job=abcdef0123456789abcdef0123456789"},
]
STRESS_TABS = {"activeId": "t1", "tabs": [
    {"id": "t1", "msgs": STRESS_MSGS, "ts": NOW - 60000},
    {"id": "t2", "msgs": [{"r": "user", "c": "A chat with an extremely long first message that becomes the tab title in the switcher list and must not break the row layout"}], "ts": NOW - 120000},
    {"id": "t3", "msgs": [], "ts": NOW - 180000}]}

results = {}

def audit(page, name, scope=None):
    page.wait_for_timeout(350)
    try: page.evaluate("document.fonts && document.fonts.ready.then(()=>1)")
    except Exception: pass
    page.wait_for_timeout(150)
    hits = page.evaluate(DETECT, scope)
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    # scroll the active scroller to bottom and re-audit (below-fold elements)
    page.evaluate("""() => { const s = document.querySelector('.screen.active .scroll') || document.querySelector('#msgs');
      if (s) s.scrollTop = s.scrollHeight; const m = document.querySelector('#msgs'); if (m) m.scrollTop = m.scrollHeight; }""")
    page.wait_for_timeout(300)
    hits2 = page.evaluate(DETECT, scope)
    page.screenshot(path=str(SHOTS / f"{name}-bottom.png"))
    page.evaluate("() => { const s = document.querySelector('.screen.active .scroll'); if (s) s.scrollTop = 0; }")
    merged = {"defects": hits.get("defects", []) + hits2.get("defects", []),
              "infos": hits.get("infos", []) + hits2.get("infos", [])}
    # dedupe
    seen = set(); dd = []
    for d in merged["defects"]:
        k = json.dumps(d, sort_keys=True)
        if k not in seen: seen.add(k); dd.append(d)
    merged["defects"] = dd
    results[name] = merged
    (RIG / f"report-{PASS}.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"[{name}] defects={len(dd)} infos={len(merged['infos'])}")
    for d in dd[:14]:
        print("   ", json.dumps(d, ensure_ascii=False)[:260])
    return merged

def seed_script(token, lang, tabs=False):
    items = {"dv_apiIdx": "1", "dv_lang": lang, "dv_consent": True}
    if token:
        items.update({"dv_token": "test-token", "dv_number": "917993610173", "dv_acct": ACCT,
                      "dv_chatTabs_917993610173": STRESS_TABS if tabs else {"activeId": "t1", "tabs": [{"id": "t1", "msgs": [], "ts": NOW}]}})
    js = "(() => { const items = %s; for (const [k,v] of Object.entries(items)) localStorage.setItem(k, JSON.stringify(v)); })()" % json.dumps(items)
    return js

def new_page(browser, token, lang, scenario, tabs=False):
    ctx = browser.new_context(viewport={"width": 360, "height": 740}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, color_scheme="dark",
                              user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36")
    ctx.add_init_script(seed_script(token, lang, tabs))
    page = ctx.new_page()
    page.route("**/api/**", make_handler(scenario))
    page.route("**://cdn.jsdelivr.net/**", lambda r: r.abort())
    page.route("**://huggingface.co/**", lambda r: r.abort())
    page.route("**://*.hf.co/**", lambda r: r.abort())
    page.on("pageerror", lambda e: print("  pageerror:", str(e)[:160]))
    return ctx, page

def go(page, route):
    page.evaluate(f"location.hash = '#/{route}'")
    page.wait_for_timeout(800)

def main():
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    handler = lambda *a, **k: Quiet(*a, directory=str(APP), **k)
    srv = ThreadingHTTPServer(("127.0.0.1", 8931), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:8931/index.html"
    with sync_playwright() as pw:
        import glob as _g
        _shell = sorted(_g.glob(str(Path.home() / ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")))[-1]
        browser = pw.chromium.launch(executable_path=_shell)
        # ---------- login (EN) ----------
        ctx, page = new_page(browser, False, "en", "A")
        page.goto(base); page.wait_for_timeout(1200)
        audit(page, "login-pw")
        page.click("#tab-su"); page.wait_for_timeout(300); audit(page, "login-signup")
        page.click("#tab-wa"); page.wait_for_timeout(300); audit(page, "login-wa")
        page.click("#tab-pw"); page.click("#forgotBtn"); page.wait_for_timeout(300); audit(page, "login-forgot")
        # forced states: reset / verify-phone / wa-code forms (real flow states)
        for fid, nm in [("rsForm", "login-reset-forced"), ("pvForm", "login-verifyphone-forced"), ("codeForm", "login-wacode-forced")]:
            page.evaluate(f"""() => {{ ['pwForm','suForm','numForm','codeForm','fgForm','rsForm','pvForm'].forEach(id => {{ const f = document.getElementById(id); if (f) f.hidden = id !== '{fid}'; }}); }}""")
            audit(page, nm)
        ctx.close()
        # ---------- main app, scenario A (paused setup + TC), EN ----------
        ctx, page = new_page(browser, True, "en", "A", tabs=True)
        page.goto(base + "#/home"); page.wait_for_timeout(1500)
        audit(page, "home")
        go(page, "chat"); page.wait_for_timeout(600)
        audit(page, "chat-setupbox-tc")
        results.setdefault("measures", {})["chatA"] = page.evaluate(MEASURE_JS)
        _y0 = page.evaluate("() => Math.round(document.querySelector('#menuBtn').getBoundingClientRect().y)")
        page.evaluate("() => { const m = document.querySelector('#msgs'); if (m) m.scrollTop = 400; window.scrollTo(0, 300); }")
        page.wait_for_timeout(250)
        _y1 = page.evaluate("() => Math.round(document.querySelector('#menuBtn').getBoundingClientRect().y)")
        results["measures"]["headerScrollY"] = {"before": _y0, "after": _y1}
        page.wait_for_timeout(2600)  # setup prompt sheet may appear (checkSetupPrompt @3s)
        if page.evaluate("() => { const s = document.querySelector('#sheet'); return s && !s.hidden; }"):
            audit(page, "sheet-setup-ask", "#sheet")
            page.evaluate("() => { const b = [...document.querySelectorAll('#sheetBtns .btn')]; if (b.length) b[b.length-1].click(); }")
            page.wait_for_timeout(400)
        go(page, "setup"); audit(page, "setup")
        go(page, "connect"); audit(page, "connect")
        go(page, "voice"); audit(page, "voice")
        go(page, "plan"); audit(page, "plan")
        go(page, "download"); audit(page, "download")
        go(page, "profile"); audit(page, "profile")
        page.click("#delOpen"); page.wait_for_timeout(300); audit(page, "profile-delete-open")
        go(page, "settings"); audit(page, "settings")
        page.click("#voiceRow"); page.wait_for_timeout(500); audit(page, "settings-voicelist")
        go(page, "history"); audit(page, "history")
        page.click("#menuBtn"); page.wait_for_timeout(450); audit(page, "drawer", "#drawer")
        page.evaluate("() => document.querySelector('#drawerBg').click()"); page.wait_for_timeout(300)
        go(page, "chat"); page.click("#tabCountBtn"); page.wait_for_timeout(450); audit(page, "tabswitcher", "#tabSwitcher")
        page.evaluate("() => document.querySelector('#tabSwitcherClose').click()"); page.wait_for_timeout(300)
        # forced overlays: bubble panel, toast, update banner
        page.evaluate("() => { const b = document.querySelector('#bubble'); b.hidden = false; const p = document.querySelector('#bubblePanel'); p.hidden = false; }")
        audit(page, "bubble-panel-forced", "#bubble")
        page.evaluate("() => { document.querySelector('#bubble').hidden = true; }")
        page.evaluate("() => { const e = document.querySelector('#toast'); e.textContent = 'Setup ayyindhi ✓ — chat ippudu ready, nee anni accounts connect ayyayi'; e.classList.add('show'); }")
        audit(page, "toast-forced", "#toast")
        page.evaluate("() => { const u = document.querySelector('#updBanner'); document.querySelector('#updText').textContent = 'Julie kotha version ready — refresh chesthe anni kotha features vasthayi'; u.hidden = false; }")
        audit(page, "updbanner-forced", "#updBanner")
        ctx.close()
        # ---------- scenario B (running + browser card + live view), EN ----------
        ctx, page = new_page(browser, True, "en", "B", tabs=True)
        page.goto(base + "#/chat"); page.wait_for_timeout(1800)
        audit(page, "chat-browsercard")
        results.setdefault("measures", {})["chatB"] = page.evaluate(MEASURE_JS)
        page.evaluate("() => { const b = document.querySelector(\".setup-box [data-a='live']\"); if (b) { b.scrollIntoView(); b.click(); } }"); page.wait_for_timeout(1200)
        audit(page, "liveview", "#liveView")
        page.evaluate("() => { const b = document.querySelector('[data-lv-take]'); if (b) b.click(); }"); page.wait_for_timeout(600)
        audit(page, "liveview-takecontrol", "#liveView")
        ctx.close()
        # ---------- locales TE + HI (subset) ----------
        for lang in ("te", "hi"):
            ctx, page = new_page(browser, False, lang, "A")
            page.goto(base); page.wait_for_timeout(1200)
            audit(page, f"login-{lang}")
            ctx.close()
            ctx, page = new_page(browser, True, lang, "A", tabs=True)
            page.goto(base + "#/home"); page.wait_for_timeout(1500)
            audit(page, f"home-{lang}")
            go(page, "chat"); page.wait_for_timeout(600); audit(page, f"chat-{lang}")
            go(page, "setup"); audit(page, f"setup-{lang}")
            go(page, "plan"); audit(page, f"plan-{lang}")
            go(page, "voice"); audit(page, f"voice-{lang}")
            go(page, "settings"); audit(page, f"settings-{lang}")
            page.click("#voiceRow"); page.wait_for_timeout(500); audit(page, f"settings-voicelist-{lang}")
            ctx.close()
        browser.close()
    out = RIG / f"report-{PASS}.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    total = sum(len(v["defects"]) for v in results.values())
    print(f"\nTOTAL defects: {total} across {len(results)} screens → {out}")
    for name, v in results.items():
        if v["defects"]:
            print(f"\n== {name} ({len(v['defects'])}) ==")
            for d in v["defects"]: print("  ", json.dumps(d, ensure_ascii=False)[:300])

if __name__ == "__main__":
    main()
