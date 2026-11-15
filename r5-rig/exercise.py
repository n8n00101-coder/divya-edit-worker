#!/usr/bin/env python3
"""Round-5 (v51) client proofs: Q1 queue-label removal + silent batching,
F1 floating header geometry, F2b tab titles, F4 empty-tab hygiene,
F5 keyboard behaviour, F2 busy-state follow-up. Real app (repo app/) +
stub API at 360px, Playwright headless Chromium. Screenshots in shots/."""
import glob, json, sys, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

RIG = Path(__file__).parent
APP = RIG.parent / "app"
sys.path.insert(0, str(RIG.parent / "r4-rig"))
import audit as A  # seed_script + api_payload

PORT = 8941
BASE = f"http://127.0.0.1:{PORT}/index.html"
SHOTS = RIG / "shots"
SHOTS.mkdir(exist_ok=True)
BUSY_LINE = "The shared AI is busy right now — its free limit is full, so it can't answer at the moment. It clears on its own in a bit; please try again shortly."
MODES = {"batch": {"calls": []}, "busy": {"calls": []}}

def make_handler(mode):
    def handler(route):
        url = route.request.url
        if "/api/" not in url:
            return route.continue_()
        path = url.split("/api/", 1)[1]
        p = path.split("?")[0].rstrip("/").split("/")[-1]
        if path.startswith("setup/status"):
            quiet = {"ok": True, "active": False, "state": "done", "needsSetup": False,
                     "steps": [], "autoLog": [], "gmail": {"state": "ok", "provider": None},
                     "finished": {"state": "done", "at": 1730000000000, "done": []}}
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(quiet))
        if p == "assist":
            body = {}
            try: body = json.loads(route.request.post_data or "{}")
            except Exception: pass
            MODES[mode]["calls"].append(str(body.get("text", "")))
            n = len(MODES[mode]["calls"])
            if mode == "busy":
                payload = {"ok": True, "reply": BUSY_LINE if n == 1 else "Follow-up answer"}
            else:
                payload = {"ok": True, "reply": "First answer" if n == 1 else "Batched answer"}
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
        body = A.api_payload(path, "B")
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    return handler

RESULTS = []
def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))

FETCH_DELAY_INIT = """(() => {
  window.__assistN = 0;
  const of = window.fetch.bind(window);
  window.fetch = async (...a) => { const u = String((a[0] && a[0].url) || a[0] || "");
    if (u.includes("/api/assist")) { window.__assistN++; if (window.__assistN === 1) await new Promise(r => setTimeout(r, 3000)); }
    return of(...a); };
})()"""

def new_ctx(browser, mode):
    ctx = browser.new_context(viewport={"width": 360, "height": 740}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, color_scheme="dark",
                              user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36")
    ctx.add_init_script(A.seed_script(True, "en", False))
    if mode == "batch":
        ctx.add_init_script(FETCH_DELAY_INIT)
    page = ctx.new_page()
    page.route("**/api/**", make_handler(mode))
    for pat in ("**://cdn.jsdelivr.net/**", "**://esm.sh/**", "**://huggingface.co/**", "**://*.hf.co/**"):
        page.route(pat, lambda r: r.abort())
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

        # ================= session 1: Q1 + F1 + F2b + F4 + F5 =================
        ctx, page = new_ctx(browser, "batch")
        page.goto(BASE); page.wait_for_timeout(1500)
        go(page, "chat")

        # ---- F1: floating header geometry ----
        geo = page.evaluate("""() => {
          const bb = el => { const r = el.getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height) }; };
          const bar = document.querySelector(".appbar"), cs = getComputedStyle(bar);
          return { pos: cs.position, bg: cs.backgroundColor, pe: cs.pointerEvents,
                   btnPe: getComputedStyle(document.querySelector("#menuBtn")).pointerEvents,
                   bar: bb(bar), hero: bb(document.querySelector(".chat-hero")), msgs: bb(document.querySelector("#msgs")) };
        }""")
        check("F1 appbar fixed + transparent bg", geo["pos"] == "fixed" and geo["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), json.dumps(geo))
        check("F1 appbar click-through, buttons tappable", geo["pe"] == "none" and geo["btnPe"] == "auto", json.dumps(geo))
        check("F1 hero compact (logo + status pill only)", geo["hero"]["h"] <= 95, str(geo["hero"]["h"]))
        check("F1 msgs start below floating cluster", geo["msgs"]["top"] >= geo["bar"]["bottom"] - 2 and geo["msgs"]["top"] >= geo["hero"]["bottom"] - 2, json.dumps(geo))

        # ---- Q1: back-to-back sends during a turn — silent merge, NO queue UI ----
        page.fill("#input", "first question"); page.click("#chatSend")
        page.wait_for_timeout(400)  # first turn in flight (fetch held 3s)
        page.fill("#input", "Hiii"); page.click("#chatSend")
        page.fill("#input", "third point"); page.click("#chatSend")
        page.wait_for_timeout(300)
        q = page.evaluate("""() => { const m = document.querySelector("#msgs");
          return { text: m.innerText, queuedEls: m.querySelectorAll(".queued, .queued-tag").length,
                   mine: [...m.querySelectorAll(".msg.me")].map(x => x.textContent) }; }""")
        check("Q1 no 'Queued' text anywhere", "ueued" not in q["text"], q["text"][:120])
        check("Q1 no queue classes/tags in DOM", q["queuedEls"] == 0)
        check("Q1 follow-ups render instantly as plain user bubbles", len(q["mine"]) == 3, str(q["mine"])[:100])
        page.screenshot(path=str(SHOTS / "q1-during-turn.png"))
        page.wait_for_timeout(6500)  # held turn (3s) + batched turn
        calls = MODES["batch"]["calls"]
        check("Q1 exactly 2 assist calls (1 + 1 batched)", len(calls) == 2, str(calls)[:140])
        check("Q1 batch combines both follow-ups", len(calls) == 2 and "Hiii" in calls[1] and "third point" in calls[1], str(calls)[:140])
        replies = page.evaluate("[...document.querySelectorAll('#msgs .msg.bot')].map(m => m.textContent)")
        check("Q1 both answers arrive (one per turn)", any("First answer" in r for r in replies) and any("Batched answer" in r for r in replies), str(replies)[:100])
        check("Q1 typing indicator cleared", page.evaluate("document.querySelectorAll('#msgs .typing').length") == 0)

        # first message fully visible: scroll to top, first bubble not clipped by header
        page.evaluate("document.querySelector('#msgs').scrollTop = 0")
        page.wait_for_timeout(300)
        clip = page.evaluate("""() => { const m = document.querySelector("#msgs"), f = m.querySelector(".msg");
          const mr = m.getBoundingClientRect(), fr = f.getBoundingClientRect();
          return { msgsTop: Math.round(mr.top), firstTop: Math.round(fr.top) }; }""")
        check("F1 first message fully visible (not under header)", clip["firstTop"] >= clip["msgsTop"], json.dumps(clip))
        page.screenshot(path=str(SHOTS / "f1-chat-top.png"))

        # ---- F2b: tab titles only from user messages ----
        titles = page.evaluate("""() => ({
          botOnly: tabTitle({ msgs: [{ r: "bot", c: "The shared AI is busy right now — wall" }] }),
          botFirst: tabTitle({ msgs: [{ r: "bot", c: "wall" }, { r: "user", c: "Helo" }] }),
          empty: tabTitle({ msgs: [] }) })""")
        check("F2b bot-only tab -> 'New chat'", titles["botOnly"] == "New chat", titles["botOnly"])
        check("F2b title from first USER message", titles["botFirst"] == "Helo", titles["botFirst"])
        check("F2b empty tab -> 'New chat'", titles["empty"] == "New chat", titles["empty"])

        # ---- F4: empty tabs never pile up ----
        cnt = lambda: page.evaluate("document.querySelector('#tabCount').textContent")
        check("F4 starts with 1 tab", cnt() == "1", cnt())
        page.evaluate("createChatTab()"); page.wait_for_timeout(300)
        check("F4 new chat on a USED tab -> 2 tabs", cnt() == "2", cnt())
        page.evaluate("createChatTab()"); page.wait_for_timeout(300)
        check("F4 new chat on EMPTY tab reuses it (still 2)", cnt() == "2", cnt())
        page.evaluate("createChatTab()"); page.wait_for_timeout(300)
        check("F4 repeated new chat still 2", cnt() == "2", cnt())
        page.click("#tabCountBtn"); page.wait_for_timeout(400)
        rows = page.evaluate("[...document.querySelectorAll('.tab-item .tt b')].map(b => b.textContent)")
        check("F4 switcher shows user-title + New chat only", set(rows) == {"first question", "New chat"}, str(rows))
        page.screenshot(path=str(SHOTS / "f4-tab-switcher.png"))
        page.click("#tabSwitcherClose"); page.wait_for_timeout(300)

        # ---- F5: keyboard open hides the tab bar ----
        page.set_viewport_size({"width": 360, "height": 420})
        page.wait_for_timeout(600)
        kb = page.evaluate("""() => ({ on: document.body.classList.contains("kb-open"),
          bar: getComputedStyle(document.querySelector(".tabbar")).display })""")
        check("F5 keyboard-open state detected", kb["on"], json.dumps(kb))
        check("F5 tab bar hidden while keyboard open", kb["bar"] == "none", json.dumps(kb))
        page.screenshot(path=str(SHOTS / "f5-keyboard-open.png"))
        page.set_viewport_size({"width": 360, "height": 740})
        page.wait_for_timeout(600)
        kb2 = page.evaluate("""() => ({ on: document.body.classList.contains("kb-open"),
          bar: getComputedStyle(document.querySelector(".tabbar")).display })""")
        check("F5 tab bar returns when keyboard closes", not kb2["on"] and kb2["bar"] != "none", json.dumps(kb2))
        ctx.close()

        # ================= session 2: F2 busy state =================
        ctx, page = new_ctx(browser, "busy")
        page.goto(BASE); page.wait_for_timeout(1500)
        go(page, "chat")
        page.fill("#input", "Hello"); page.click("#chatSend")
        page.wait_for_timeout(900)
        busy = page.evaluate("[...document.querySelectorAll('#msgs .msg.bot')].map(m => m.textContent)")
        check("F2 busy reply is the ONE short line", busy and busy[-1].strip() == BUSY_LINE, str(busy)[:160])
        page.fill("#input", "Helo"); page.click("#chatSend")
        page.wait_for_timeout(900)
        allb = page.evaluate("[...document.querySelectorAll('#msgs .msg.bot')].map(m => m.textContent)")
        check("F2c follow-up during busy still answered", any("Follow-up answer" in r for r in allb), str(allb)[:120])
        check("F2c no hanging Typing state", page.evaluate("document.querySelectorAll('#msgs .typing').length") == 0
              and page.evaluate("document.querySelector('#liveStatus').textContent") == "Online")
        page.screenshot(path=str(SHOTS / "f2-busy-state.png"))
        ctx.close()
        browser.close()
    fails = [n for n, c in RESULTS if not c]
    print(f"\n{len(RESULTS) - len(fails)} passed, {len(fails)} failed")
    if fails: print("FAILED:", fails)
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
