#!/usr/bin/env python3
"""Diagnosis rig — Connect page geometry + add-account affordances.
Real repo app/ served locally; API stubbed via route interception
(the established r5/v96 rig pattern). Scenarios vary the /connect payload.
"""
import json, sys, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

RIG = Path(__file__).parent
APP = RIG.parent / "app"
SHOTS = RIG / "shots"; SHOTS.mkdir(parents=True, exist_ok=True)
PORT = 8931

SCEN = {
  "none": [
    {"id": "youtube", "name": "YouTube", "desc": "Videos upload cheyadaniki", "connected": False, "who": "", "ready": True, "noAccount": False},
    {"id": "google", "name": "Google", "desc": "Gmail/Drive (basic profile)", "connected": False, "who": "", "ready": True, "noAccount": False},
    {"id": "instagram", "name": "Instagram", "desc": "Reels post cheyadaniki", "connected": False, "who": "", "ready": False, "noAccount": False},
    {"id": "facebook", "name": "Facebook", "desc": "Page lo post cheyadaniki", "connected": False, "who": "", "ready": False, "noAccount": False},
    {"id": "telegram", "name": "Telegram", "desc": "Telegram lo kuda Julie", "connected": False, "who": "", "ready": False, "noAccount": False},
  ],
  "google1": [
    {"id": "youtube", "name": "YouTube", "desc": "Videos upload cheyadaniki", "connected": False, "who": "", "ready": True, "noAccount": False},
    {"id": "google", "name": "Google", "desc": "Gmail/Drive (basic profile)", "connected": True, "who": "markk34200@gmail.com", "ready": True, "noAccount": False},
    {"id": "instagram", "name": "Instagram", "desc": "Reels post cheyadaniki", "connected": False, "who": "", "ready": False, "noAccount": False},
    {"id": "facebook", "name": "Facebook", "desc": "Page lo post cheyadaniki", "connected": False, "who": "", "ready": False, "noAccount": False},
    {"id": "telegram", "name": "Telegram", "desc": "Telegram lo kuda Julie", "connected": False, "who": "", "ready": False, "noAccount": False},
  ],
  "yt_nochan": [
    {"id": "youtube", "name": "YouTube", "desc": "Videos upload cheyadaniki", "connected": True, "who": "(ee account lo YouTube channel kanipinchaledu)", "ready": True, "noAccount": True},
    {"id": "google", "name": "Google", "desc": "Gmail/Drive (basic profile)", "connected": True, "who": "markk34200@gmail.com", "ready": True, "noAccount": False},
    {"id": "instagram", "name": "Instagram", "desc": "Reels post cheyadaniki", "connected": False, "who": "", "ready": False, "noAccount": False},
    {"id": "facebook", "name": "Facebook", "desc": "Page lo post cheyadaniki", "connected": False, "who": "", "ready": False, "noAccount": False},
    {"id": "telegram", "name": "Telegram", "desc": "Telegram lo kuda Julie", "connected": False, "who": "", "ready": False, "noAccount": False},
  ],
}
STATE = {"scen": "none", "link_calls": []}

def payload(path):
    p = path.split("?")[0]
    seg = p.rstrip("/").split("/")[-1]
    if p == "connect" or p.endswith("/connect"):
        return {"ok": True, "providers": SCEN[STATE["scen"]]}
    if p == "connect/link" or p.endswith("/connect/link"):
        return {"ok": True, "url": "https://divya.n8n00101.workers.dev/c/RIGSTATE"}
    if seg == "me":
        return {"ok": True, "number": "", "account": {"name": "Probe", "email": "probe@example.com", "phone": ""}}
    if seg == "plan":
        return {"ok": True, "plan": "free", "tok": {"weekLeft": 500000, "pool": 0, "planLeft": 0}, "plans": {}}
    if seg == "status":
        return {"ok": True, "job": None}
    if seg == "history":
        return {"ok": True, "messages": []}
    if seg == "model":
        return {"ok": True, "model": None}
    if p == "setup/status" or p.endswith("/setup/status"):
        return {"ok": True, "active": False, "needsSetup": True, "gmail": {"state": "ok"}}
    if p == "keys" or p.endswith("/keys"):
        return {"ok": True, "keys": []}
    if seg == "health":
        return {"ok": True, "name": "divya"}
    return {"ok": True}

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=str(APP), **kw)
    def log_message(self, *a): pass

def run():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    results = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for width in (412, 360):
            for scen in ("none", "google1", "yt_nochan"):
                STATE["scen"] = scen
                pg = b.new_page(viewport={"width": width, "height": 915})
                pg.add_init_script("""localStorage.setItem('dv_token', JSON.stringify('rig-token'));
                                      localStorage.setItem('dv_acct', JSON.stringify({name:'Probe', email:'probe@example.com'}));
                                      localStorage.setItem('dv_lang', JSON.stringify('en'));""")
                def handle(route):
                    u = route.request.url
                    if "/api/" in u:
                        if "connect/link" in u:
                            STATE["link_calls"].append(u)
                        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload(u.split("/api/")[1])))
                    elif "divya.n8n00101.workers.dev/c/" in u:
                        route.fulfill(status=200, content_type="text/html", body="<title>oauth-start-reached</title>reached")
                    else:
                        route.continue_()
                pg.route("**/*", handle)
                pg.on("console", lambda m: print("CONSOLE:", m.type, m.text[:160]))
                pg.on("pageerror", lambda e: print("PAGEERROR:", str(e)[:200]))
                reqs = []
                pg.on("request", lambda r: reqs.append(r.url) if "/api/" in r.url else None)
                pg.goto(f"http://127.0.0.1:{PORT}/index.html#/connect")
                pg.wait_for_timeout(2500)
                print("REQS:", [u.split("/api/")[1] for u in reqs])
                print("STATE:", pg.evaluate("""() => ({hash: location.hash, active: document.querySelector('#screens .screen.active')?.id, loginHidden: document.querySelector('#login')?.hidden, mainHidden: document.querySelector('#main')?.hidden, bodyText: document.body.innerText.slice(0,200)})"""))
                rows = pg.evaluate("""() => [...document.querySelectorAll('#provList .row')].map(r => {
                    const b = r.getBoundingClientRect();
                    const btns = [...r.querySelectorAll('button')].map(x => ({label: x.textContent.trim(), w: Math.round(x.getBoundingClientRect().width), h: Math.round(x.getBoundingClientRect().height)}));
                    return {name: r.querySelector('b')?.textContent, w: Math.round(b.width), h: Math.round(b.height), buttons: btns, text: r.innerText.replace(/\\n/g,' | ').slice(0,120)};
                })""")
                gbtn = pg.evaluate("""() => { const g = document.querySelector('#gBtn'); return g ? {hidden: g.hidden, visible: !!(g.offsetWidth || g.offsetHeight)} : null; }""")
                results[f"{width}/{scen}"] = {"rows": rows, "gBtn": gbtn}
                pg.screenshot(path=str(SHOTS / f"diag-{width}-{scen}.png"))
                pg.close()
        b.close()
    srv.shutdown()
    print(json.dumps(results, indent=1, ensure_ascii=False))

if __name__ == "__main__":
    run()
