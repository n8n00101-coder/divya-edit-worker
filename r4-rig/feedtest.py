#!/usr/bin/env python3
"""Round-4 X2 regression: the chat feed must gain AT MOST one setup line per
state change, and no feed message may carry a provider dump.

Scenario: setup/status reports a FINISHED (done) run. Entering chat starts
pollSetup; leaving and re-entering restarts it. Pre-v50 each re-entry posted
"Setup is done ✓ — chat is ready now" again (Ajju saw it 4x). Post-v50 the
persisted signature in feedSetupOnce must keep the count at exactly 1.
Also: bubble() itself must collapse a raw provider dump to the one-liner.
"""
import functools, glob, http.server, json, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
APP = ROOT.parent / "app"
PORT = 8935
IDS = ["groq", "openrouter", "gemini", "cloudflare", "pexels", "cohere", "together", "sambanova",
       "fireworks", "cerebras", "nvidia", "mistral", "ai21", "voyage", "tavily", "serper", "exa",
       "deepgram", "assemblyai", "elevenlabs", "stability", "jina"]
KEYS = {i: "set" for i in IDS}
STEPS = [{"id": i, "state": "done", "note": ""} for i in IDS]
STATUS = {"ok": True, "active": False, "state": "done",
          "finished": {"state": "done", "at": 1730000000000, "done": IDS},
          "keys": KEYS, "keyList": [], "keyTier": "own", "ownKeyCount": 21,
          "needsSetup": False, "sharedFallback": False, "steps": STEPS,
          "gmail": {"state": "ok", "provider": None}, "autoLog": []}
ME = {"ok": True, "number": "917993610173", "owner": True, "premium": True,
      "account": {"name": "Ajju M", "email": "markk34200@gmail.com", "phone": "7993610173"},
      "keys": KEYS, "keyTier": "own", "ownKeyCount": 21}
PLAN = {"ok": True, "plan": "creator", "premium": True, "voice": True,
        "tok": {"total": 1001000000, "weekLeft": 400000, "pool": 1001000000, "bonus": 1000000000},
        "plans": {}, "refCode": "DVJCZZ", "refCount": 0}

def api_json(route):
    path = route.request.url.split("/api/", 1)[-1].split("?")[0]
    body = STATUS if path == "setup/status" else ME if path == "me" else PLAN if path == "plan" else {"ok": True, "messages": []}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

def main():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(APP))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    exe = sorted(glob.glob(str(Path.home() / ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")))[-1]
    results = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=exe, args=["--no-sandbox"])
        page = b.new_page(viewport={"width": 360, "height": 740}, device_scale_factor=2,
                          user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36")
        page.route("**/api/**", api_json)
        page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="load")
        page.evaluate("""() => { localStorage.setItem("dv_token", JSON.stringify("rig"));
          localStorage.setItem("dv_apiIdx", "1"); localStorage.setItem("dv_lang", JSON.stringify("en"));
          localStorage.setItem("dv_consent", "true");
          localStorage.setItem("dv_acct", JSON.stringify({name:"Ajju M", email:"markk34200@gmail.com"})); }""")
        page.reload(wait_until="load"); page.wait_for_timeout(2500)
        counts = []
        for visit in range(4):  # enter chat 4 times — the pre-fix bug posted the line every time
            page.evaluate("() => { location.hash = '#/chat'; }")
            page.wait_for_timeout(2200)
            counts.append(page.evaluate("""() => [...document.querySelectorAll('#msgs .msg.bot')]
              .filter(m => /Setup is done/.test(m.textContent)).length"""))
            page.evaluate("() => { location.hash = '#/home'; }")
            page.wait_for_timeout(500)
        results.append(("done-line count per chat visit (want [1,1,1,1])", counts, [1, 1, 1, 1]))
        # raw dump collapse: post Ajju's screenshot dump straight through bubble()
        page.evaluate("""() => { location.hash = '#/chat'; }"""); page.wait_for_timeout(800)
        dump = ("Paused — waiting for your one tap.⏸ Groq: Waiting · OpenRouter: Not set — waiting.· "
                "Gemini: Done ✓ · Cohere: Not set — waiting. · Together AI: Not set — waiting. · "
                "SambaNova: Not set — waiting. · Fireworks AI: Not set — waiting. · Cerebras: Done ✓ · "
                "NVIDIA NIM: Not set — waiting. · Mistral AI: Not set — waiting.")
        got = page.evaluate("""(txt) => { bubble("bot", txt);
          const ms = [...document.querySelectorAll('#msgs .msg.bot')]; return ms[ms.length - 1].textContent; }""", dump)
        names = ["Groq", "OpenRouter", "Gemini", "Cohere", "Together AI", "SambaNova", "Fireworks", "Cerebras", "NVIDIA", "Mistral"]
        hits = sum(1 for n in names if n in got)
        results.append(("dump collapsed to one-liner (provider names <= 1)", hits <= 1, True))
        results.append(("dump replaced by setupFeedLine", got.strip(), "Full setup status lives on the Setup screen — chat gets one line only."))
        b.close()
    httpd.shutdown()
    bad = 0
    for label, got, want in results:
        ok = got == want
        bad += (not ok)
        print(("PASS " if ok else "FAIL ") + label + ("" if ok else f" — got {got!r} want {want!r}"))
    print(f"\n{len(results) - bad} passed, {bad} failed")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
