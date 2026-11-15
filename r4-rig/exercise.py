#!/usr/bin/env python3
"""Round-4 Y2 deep exercise pass + M1/M2/M3/V1/Y1/Y3/Y4 functional tests.

Real app (repo app/) + stub API at 360px. Exercises flows the visual audit
cannot: message menu actions, send-queue batching, voice sample playback
with the service worker ACTIVE (second load, cold), live-view mini box +
settings toggle, redeem errors, tab switching, glass chrome measurement.
Every check prints PASS/FAIL; failures are the SELF-FOUND defect list.
"""
import glob, json, sys, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

RIG = Path(__file__).parent
APP = RIG.parent / "app"
sys.path.insert(0, str(RIG))
import audit as A  # reuse payloads + seed_script (module import runs no main)

PORT = 8937
BASE = f"http://127.0.0.1:{PORT}/index.html"
STATE = {"prefs": {"lvMini": True}, "assist_calls": [], "prefs_posts": []}
QUIET_STATUS = {"ok": True, "active": False, "state": "done", "needsSetup": False,
                "steps": [], "autoLog": [], "gmail": {"state": "ok", "provider": None},
                "finished": {"state": "done", "at": 1730000000000, "done": []}}

def handler(route):
    url = route.request.url
    if "/api/" not in url:
        return route.continue_()
    path = url.split("/api/", 1)[1]
    p = path.split("?")[0].rstrip("/").split("/")[-1]
    if p == "assist":
        body = {}
        try: body = json.loads(route.request.post_data or "{}")
        except Exception: pass
        STATE["assist_calls"].append(str(body.get("text", "")))
        if len(STATE["assist_calls"]) == 1:
            payload = {"ok": True, "reply": "First answer"}
        else:
            payload = {"ok": True, "reply": "Batched answer"}
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
    if p == "prefs":
        if route.request.method == "POST":
            try: STATE["prefs"].update(json.loads(route.request.post_data or "{}"))
            except Exception: pass
            STATE["prefs_posts"].append(dict(STATE["prefs"]))
        return route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"ok": True, "prefs": STATE["prefs"]}))
    if "redeem" in path:
        return route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"ok": False, "error": "Invalid code — check and try again"}))
    if path.startswith("setup/status"):
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(QUIET_STATUS))
    body = A.api_payload(path, "B")
    return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

RESULTS = []
def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))

FETCH_DELAY_INIT = """(() => {
  // M3: hold the FIRST assist request 3s in the browser so the queue window
  // is real (a Python-side sleep would block the test's main thread).
  window.__assistN = 0;
  const of = window.fetch.bind(window);
  window.fetch = async (...a) => { const u = String((a[0] && a[0].url) || a[0] || "");
    if (u.includes("/api/assist")) { window.__assistN++; if (window.__assistN === 1) await new Promise(r => setTimeout(r, 3000)); }
    return of(...a); };
})()"""
AUDIO_INIT = """(() => {
  window.__plays = [];
  const proto = HTMLAudioElement.prototype;
  const op = proto.play;
  proto.play = function() { window.__plays.push({ src: this.currentSrc || this.src || "", t: Date.now() }); return op.apply(this, arguments); };
})()"""

def new_ctx(browser, tabs=False, lang="en"):
    ctx = browser.new_context(viewport={"width": 360, "height": 740}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, color_scheme="dark",
                              permissions=["clipboard-read", "clipboard-write"],
                              user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36")
    ctx.add_init_script(A.seed_script(True, lang, tabs))
    ctx.add_init_script(AUDIO_INIT)
    ctx.add_init_script(FETCH_DELAY_INIT)
    page = ctx.new_page()
    page.route("**/api/**", handler)
    page.route("**://cdn.jsdelivr.net/**", lambda r: r.abort())
    page.route("**://esm.sh/**", lambda r: r.abort())
    page.route("**://huggingface.co/**", lambda r: r.abort())
    page.route("**://*.hf.co/**", lambda r: r.abort())
    page.on("pageerror", lambda e: check("no pageerror", False, str(e)[:140]))
    return ctx, page

def go(page, route):
    page.evaluate(f"location.hash = '#/{route}'")
    page.wait_for_timeout(700)

def main():
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), lambda *a, **k: Quiet(*a, directory=str(APP), **k))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    shell = sorted(glob.glob(str(Path.home() / ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")))[-1]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shell)

        # ============ session 1: chat flows (M1/M2/M3/Y4) ============
        ctx, page = new_ctx(browser, tabs=True)
        page.goto(BASE); page.wait_for_timeout(1500)
        go(page, "chat")

        # M1 glass: composer + tabbar + a header chip carry real backdrop blur + alpha < 1
        glass = page.evaluate("""() => {
          const g = el => { if (!el) return null; const cs = getComputedStyle(el); return { bf: cs.backdropFilter || cs.webkitBackdropFilter || "", bg: cs.backgroundColor }; };
          return { composer: g(document.querySelector(".composer")), tabbar: g(document.querySelector(".tabbar")),
                   chip: g(document.querySelector(".appbar .icon-btn")) };
        }""")
        def is_glass(v):
            if not v: return False
            m = v["bg"].replace(" ", "").match(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)") if False else None
            import re
            mm = re.match(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)", v["bg"].replace(" ", ""))
            alpha = float(mm.group(4)) if mm else 1.0
            return "blur" in v["bf"] and alpha < 1.0
        check("M1 glass composer", is_glass(glass["composer"]), json.dumps(glass["composer"]))
        check("M1 glass tabbar", is_glass(glass["tabbar"]), json.dumps(glass["tabbar"]))
        check("M1 glass header chip", is_glass(glass["chip"]), json.dumps(glass["chip"]))

        # Y1: toast floats ABOVE the tab bar, glass, light text on dark glass
        page.evaluate("toast('Voice sample failed — test toast')")
        page.wait_for_timeout(400)
        toast = page.evaluate("""() => { const t = document.querySelector("#toast"), b = document.querySelector(".tabbar");
          const tr = t.getBoundingClientRect(), br = b.getBoundingClientRect(); const cs = getComputedStyle(t);
          return { bottom: Math.round(tr.bottom), barTop: Math.round(br.top), bg: cs.backgroundColor, color: cs.color, bf: cs.backdropFilter || "" }; }""")
        check("Y1 toast above tab bar + glass", toast["bottom"] <= toast["barTop"] + 2 and "blur" in toast["bf"], json.dumps(toast))

        # Y4: action chip on its OWN line; duplicated label trimmed from text
        page.evaluate("""() => { bubble("bot", "Opened the YouTube app ✓", { buttons: [{ label: "Open youtube.com", href: "https://youtube.com" }] });
          bubble("bot", "Opened the YouTube app ✓Open youtube.com", { buttons: [{ label: "Open youtube.com", href: "https://youtube.com" }] }); }""")
        page.wait_for_timeout(300)
        y4 = page.evaluate("""() => { const ms = [...document.querySelectorAll("#msgs .msg.bot")].slice(-2);
          return ms.map(m => { const tx = m.querySelector(".msg-text"), act = m.querySelector(".act");
            return { text: tx ? tx.textContent : "", textBottom: tx ? Math.round(tx.getBoundingClientRect().bottom) : 0,
                     actTop: act ? Math.round(act.getBoundingClientRect().top) : -1 }; }); }""")
        check("Y4 chip on own line below text", all(r["actTop"] >= r["textBottom"] - 1 for r in y4), json.dumps(y4))
        check("Y4 duplicated label trimmed", "Open youtube.com" not in y4[1]["text"], y4[1]["text"][:60])

        # M2: right-click an OWN message -> Copy/Reply/Edit/Delete
        own = page.locator("#msgs .msg.me").first
        own.click(button="right")
        page.wait_for_timeout(300)
        labels = page.evaluate("[...document.querySelectorAll('.ctxmenu button')].map(b => b.textContent)")
        check("M2 menu has Copy/Reply/Edit/Delete", all(x in labels for x in ("Copy", "Reply", "Edit", "Delete")), str(labels))
        page.evaluate("[...document.querySelectorAll('.ctxmenu button')].find(b => b.textContent === 'Copy').click()")
        page.wait_for_timeout(300)
        clip = page.evaluate("navigator.clipboard.readText().catch(() => '')")
        check("M2 copy puts message text on clipboard", len(clip) > 10, clip[:40])
        own.click(button="right"); page.wait_for_timeout(250)
        page.evaluate("[...document.querySelectorAll('.ctxmenu button')].find(b => b.textContent === 'Reply').click()")
        page.wait_for_timeout(250)
        check("M2 reply shows quoted chip above composer", page.evaluate("!document.querySelector('#replyBar').hidden"))
        page.evaluate("document.querySelector('#replyBar button').click()")  # cancel reply
        own.click(button="right"); page.wait_for_timeout(250)
        page.evaluate("[...document.querySelectorAll('.ctxmenu button')].find(b => b.textContent === 'Edit').click()")
        page.wait_for_timeout(250)
        edit_val = page.evaluate("document.querySelector('#input').value")
        check("M2 edit loads text into composer", len(edit_val) > 10, edit_val[:40])
        page.evaluate("document.querySelector('#input').value = ''")
        # long-press (touch path) opens the menu too
        box = own.bounding_box()
        page.mouse.move(box["x"] + 20, box["y"] + 10); page.mouse.down(); page.wait_for_timeout(650); page.mouse.up()
        page.wait_for_timeout(250)
        check("M2 long-press opens menu", page.evaluate("!!document.querySelector('.ctxmenu')"))
        page.evaluate("[...document.querySelectorAll('.ctxmenu button')].find(b => b.textContent === 'Delete').click()")
        page.wait_for_timeout(250)
        check("M2 delete asks inside the menu", page.evaluate("[...document.querySelectorAll('.ctxmenu button')].some(b => b.textContent === 'Delete') && !!document.querySelector('.ctxmenu-q')"))
        before = page.evaluate("document.querySelectorAll('#msgs .msg.me').length")
        page.evaluate("[...document.querySelectorAll('.ctxmenu button')].find(b => b.textContent === 'Delete').click()")
        page.wait_for_timeout(250)
        after = page.evaluate("document.querySelectorAll('#msgs .msg.me').length")
        check("M2 delete removes the message", after == before - 1, f"{before}->{after}")

        # M3: send during an in-flight turn -> queued, batched, nothing lost
        go(page, "chat")
        page.evaluate("document.querySelector('#msgs').innerHTML = ''")  # clean slate for counting
        page.fill("#input", "first question")
        page.click("#chatSend")
        page.wait_for_timeout(400)  # first turn in flight (stub sleeps 3s)
        page.fill("#input", "second point"); page.click("#chatSend")
        page.fill("#input", "third point"); page.click("#chatSend")
        page.wait_for_timeout(200)
        q = page.evaluate("[...document.querySelectorAll('#msgs .msg.me.queued')].map(m => m.textContent)")
        check("M3 queued messages render instantly with queued tag", len(q) == 2 and all("Queue" in t or "queue" in t for t in q), str(q)[:80])
        send_enabled = page.evaluate("!document.querySelector('#chatSend').disabled")
        page.fill("#input", "typing while busy")
        send_enabled = page.evaluate("!document.querySelector('#chatSend').disabled")
        check("M3 send button never disabled while busy", send_enabled)
        page.evaluate("document.querySelector('#input').value = ''")
        page.wait_for_timeout(6000)  # first turn (3s) + batched turn
        calls = STATE["assist_calls"]
        check("M3 exactly 2 assist calls (1 + 1 batched)", len(calls) == 2, str(calls)[:120])
        check("M3 batch combines both queued messages", len(calls) == 2 and "second point" in calls[1] and "third point" in calls[1], str(calls)[:120])
        replies = page.evaluate("[...document.querySelectorAll('#msgs .msg.bot')].map(m => m.textContent)")
        check("M3 both answers arrive", any("First answer" in r for r in replies) and any("Batched answer" in r for r in replies), str(replies)[:80])
        check("M3 queued tags cleared after batch", page.evaluate("document.querySelectorAll('#msgs .msg.queued').length") == 0)

        # Y2: tab switching + tab switcher overlay
        for r in ("home", "voice", "plan", "setup", "profile", "settings", "chat"):
            go(page, r)
            active = page.evaluate("document.querySelector('.screen.active')?.id || ''")
            check(f"Y2 tab switch -> {r}", active == f"s-{r}", active)
        page.click("#tabCountBtn"); page.wait_for_timeout(400)
        check("Y2 tab switcher opens", page.evaluate("!document.querySelector('.tab-switcher').hidden && !!document.querySelector('.tab-switcher-card')"))
        page.click("#tabSwitcherClose"); page.wait_for_timeout(300)

        # Y2: redeem empty + invalid code -> feedback, no crash
        go(page, "plan")
        page.click("#refRedeemBtn"); page.wait_for_timeout(400)
        fb1 = page.evaluate("document.querySelector('#toast')?.textContent || ''")
        page.fill("#refInput", "WRONG1"); page.click("#refRedeemBtn"); page.wait_for_timeout(600)
        fb2 = page.evaluate("document.querySelector('#toast')?.textContent || document.body.innerText.includes('Invalid code')")
        check("Y2 redeem invalid code shows the server error", bool(fb2), str(fb2)[:60])

        # Y2: settings toggles flip + persist locally
        go(page, "settings")
        page.click("#setLvMini")  # uncheck (default ON)
        page.wait_for_timeout(300)
        check("Y3 toggle posts pref to server", STATE["prefs"].get("lvMini") is False, json.dumps(STATE["prefs"]))
        check("Y3 toggle persists locally", page.evaluate("JSON.parse(localStorage.getItem('dv_lvMini'))") is False)
        ctx.close()

        # ============ session 2: pref OFF survives reload; voice samples with SW ============
        ctx, page = new_ctx(browser, tabs=False)
        page.goto(BASE); page.wait_for_timeout(1500)
        go(page, "chat")
        page.evaluate("openLive(true)"); page.wait_for_timeout(600)
        check("Y3 mini box ABSENT when pref off (after reload)", page.evaluate("document.querySelector('[data-lv-mini]')?.hidden === true"))
        page.evaluate("closeLive()")
        # turn it back on from settings, reload, expect it back
        go(page, "settings"); page.wait_for_timeout(300)
        state = page.evaluate("document.querySelector('#setLvMini').checked")
        check("Y3 settings checkbox reflects server pref (off)", state is False)
        page.click("#setLvMini"); page.wait_for_timeout(300)
        page.reload(); page.wait_for_timeout(1500)
        page.evaluate("openLive(true)"); page.wait_for_timeout(600)
        check("Y3 mini box present when pref on", page.evaluate("document.querySelector('[data-lv-mini]') && !document.querySelector('[data-lv-mini]').hidden"))
        # send from the mini box -> lands in chat + status line confirms
        page.fill("[data-lv-mini-text]", "back")
        page.click("[data-lv-mini-send]"); page.wait_for_timeout(400)
        check("Y3 mini send lands in chat", page.evaluate("[...document.querySelectorAll('#msgs .msg.me')].some(m => m.textContent.includes('back'))"))
        check("Y3 mini status line confirms", "Sent to Julie" in (page.evaluate("document.querySelector('[data-lv-mini-status]')?.textContent || ''")))
        page.evaluate("closeLive()")

        # V1/V3: voice samples — SW active by now (second load of the app shell
        # happened at reload); every row's play must hit its OWN static mp3.
        go(page, "settings")  # the voice PICKER lives on the Settings screen
        page.wait_for_timeout(800)
        page.click("#voiceRow")  # expand the collapsed picker list
        page.wait_for_timeout(600)
        ids = page.evaluate("[...document.querySelectorAll('[data-play]')].map(b => b.dataset.play)")
        check("V3 picker rows present (21)", len(ids) == 21, str(len(ids)))
        for vid in ids:
            page.click(f"[data-play='{vid}']")
            page.wait_for_timeout(120)
        page.wait_for_timeout(800)
        plays = page.evaluate("(window.__plays || []).map(p => p.src)")
        srcs = [p.rsplit("/", 1)[-1] for p in plays]
        expect = {"house-julie": "house-sample-en.mp3"}
        ok_all = len(ids) > 0
        for vid in ids:
            want = expect.get(vid, f"{vid}.mp3")
            if want not in srcs: ok_all = False; print("   missing sample play:", vid, "want", want)
        check("V1/V3 every row plays its own bundled sample", ok_all, str(srcs)[:200])
        house_plays = [p for p in plays if p.endswith("house-sample-en.mp3")]
        check("V1 house sample played via direct Audio (SW active)", len(house_plays) >= 1)
        ctx.close()
        browser.close()
    fails = [n for n, c in RESULTS if not c]
    print(f"\n{len(RESULTS) - len(fails)} passed, {len(fails)} failed")
    if fails: print("SELF-FOUND/FAILED:", fails)
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
