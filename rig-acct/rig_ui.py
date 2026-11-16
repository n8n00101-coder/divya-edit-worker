#!/usr/bin/env python3
"""v97 UI proof rig — real repo app/ served locally, API stubbed.
Proves: (1) YouTube row geometry matches normal rows @412/@360 incl.
the no-channel state; (2) accounts list renders with Add visible while
connected; Add click posts account:"new" and navigates to the OAuth
start; (3) cap state at 10 accounts; (4) #gBtn stays visible when a
Google account is connected; (5) Remove posts connect/remove.
"""
import json, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

RIG = Path(__file__).parent
APP = RIG.parent / "app"
SHOTS = RIG / "shots"; SHOTS.mkdir(parents=True, exist_ok=True)
PORT = 8932

PROV_BASE = [
    {"id": "youtube", "name": "YouTube", "desc": "Videos upload cheyadaniki", "connected": True, "who": 'channel "First Channel"', "ready": True, "noAccount": False},
    {"id": "google", "name": "Google", "desc": "Gmail, Drive", "connected": True, "who": "first@example.com", "ready": True, "noAccount": False},
    {"id": "instagram", "name": "Instagram", "desc": "Reels post cheyadaniki", "connected": False, "who": "", "ready": False, "noAccount": False},
    {"id": "facebook", "name": "Facebook", "desc": "Page lo post cheyadaniki", "connected": False, "who": "", "ready": False, "noAccount": False},
    {"id": "telegram", "name": "Telegram", "desc": "Telegram lo kuda Julie", "connected": False, "who": "", "ready": False, "noAccount": False},
]
ACCTS2 = [
    {"id": "aa1", "email": "first@example.com", "ytChannel": "First Channel", "ytNoChannel": False, "gmail": True, "yt": True, "state": "ok", "def": True},
    {"id": "aa2", "email": "second@example.com", "ytChannel": "", "ytNoChannel": True, "gmail": True, "yt": True, "state": "ok", "def": False},
]
SCEN = {
    "two": (PROV_BASE, ACCTS2),
    "yt_nochan": ([{**PROV_BASE[0], "who": "(ee account lo YouTube channel kanipinchaledu)", "noAccount": True}] + PROV_BASE[1:], ACCTS2),
    "cap": (PROV_BASE, [ {"id": f"ax{i}", "email": f"user{i}@example.com", "ytChannel": "", "ytNoChannel": False, "gmail": True, "yt": False, "state": "ok", "def": i == 0} for i in range(10) ]),
}
STATE = {"scen": "two", "calls": []}

def payload(path, body=None):
    p = path.split("?")[0]
    seg = p.rstrip("/").split("/")[-1]
    if p.endswith("/connect") or p == "connect":
        provs, accts = SCEN[STATE["scen"]]
        return {"ok": True, "providers": provs, "accounts": accts, "acctCap": 10, "acctDef": accts[0]["id"] if accts else None}
    if "connect/link" in p:
        return {"ok": True, "url": "https://divya-app.n8n00101.workers.dev/c/RIGSTATE"}
    if "connect/remove" in p or "connect/default" in p:
        return {"ok": True, "accounts": [], "acctDef": None}
    if seg == "me": return {"ok": True, "number": "", "account": {"name": "Probe", "email": "probe@example.com", "phone": ""}}
    if seg == "plan": return {"ok": True, "plan": "free", "tok": {"weekLeft": 500000, "pool": 0, "planLeft": 0}, "plans": {}}
    if seg == "status": return {"ok": True, "job": None}
    if seg == "history": return {"ok": True, "messages": []}
    if seg == "model": return {"ok": True, "model": None}
    if p.endswith("/setup/status") or p == "setup/status": return {"ok": True, "active": False, "needsSetup": True, "gmail": {"state": "ok"}}
    if seg == "keys": return {"ok": True, "keys": []}
    if seg == "health": return {"ok": True, "name": "divya"}
    return {"ok": True}

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=str(APP), **kw)
    def log_message(self, *a): pass

def run():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out = {}
    fails = []
    def T(name, cond, extra=""):
        out[name] = bool(cond)
        print(("PASS " if cond else "FAIL ") + name, extra if not cond else "")
        if not cond: fails.append(name)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for width in (412, 360):
            for scen in ("two", "yt_nochan", "cap"):
                STATE["scen"] = scen; STATE["calls"] = []
                pg = b.new_page(viewport={"width": width, "height": 915})
                pg.add_init_script("""localStorage.setItem('dv_token', JSON.stringify('rig-token'));
                                      localStorage.setItem('dv_acct', JSON.stringify({name:'Probe', email:'probe@example.com'}));
                                      localStorage.setItem('dv_lang', JSON.stringify('en'));""")
                pg.on("dialog", lambda d: d.accept())
                def handle(route):
                    u = route.request.url
                    if "/api/" in u:
                        STATE["calls"].append((u.split("/api/")[1], route.request.post_data or ""))
                        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload(u.split("/api/")[1])))
                    elif "workers.dev/c/" in u:
                        route.fulfill(status=200, content_type="text/html", body="<title>oauth-start-reached</title>reached")
                    else:
                        route.continue_()
                pg.route("**/*", handle)
                pg.goto(f"http://127.0.0.1:{PORT}/index.html#/connect")
                pg.wait_for_timeout(2200)
                m = pg.evaluate("""() => {
                  const rows = [...document.querySelectorAll('#provList .row')].map(r => ({name: r.querySelector('b')?.textContent, h: Math.round(r.getBoundingClientRect().height)}));
                  const accts = [...document.querySelectorAll('#acctList .row')].map(r => ({h: Math.round(r.getBoundingClientRect().height), text: r.innerText.replace(/\\n/g,' | ').slice(0,110)}));
                  const add = document.querySelector('#acctAdd');
                  const g = document.querySelector('#gBtn');
                  return { rows, accts, addVisible: !!add && !!(add.offsetWidth || add.offsetHeight), acctText: document.querySelector('#acctList')?.innerText || '',
                           gBtnHidden: g ? g.hidden : null };
                }""")
                yt = next((r for r in m["rows"] if r["name"] == "YouTube"), {})
                ig = next((r for r in m["rows"] if r["name"] == "Instagram"), {})
                gg = next((r for r in m["rows"] if r["name"] == "Google"), {})
                T(f"{width}/{scen} youtube row <= 88px", yt.get("h", 999) <= 88, f"h={yt.get('h')} rows={m['rows']}")
                T(f"{width}/{scen} youtube row ~ connected-row parity", yt.get("h", 999) <= max(ig.get("h", 0) * 1.35, gg.get("h", 0) + 4), f"yt={yt.get('h')} ig={ig.get('h')} gg={gg.get('h')}")
                if scen == "two":
                    T(f"{width}/two accounts list = 2 rows", len(m["accts"]) == 2, json.dumps(m["accts"]))
                    T(f"{width}/two account rows <= 100px", all(a["h"] <= 100 for a in m["accts"]), json.dumps(m["accts"]))
                    T(f"{width}/two Add visible while connected", m["addVisible"])
                    T(f"{width}/two gBtn NOT hidden", m["gBtnHidden"] is False, f"gBtnHidden={m['gBtnHidden']}")
                    # Add click -> connect/link {account:"new"} -> navigation to OAuth start
                    pg.click("#acctAdd"); pg.wait_for_timeout(1500)
                    link = [c for c in STATE["calls"] if "connect/link" in c[0]]
                    T(f"{width}/two Add posts account:new", bool(link) and '"new"' in link[-1][1], json.dumps(STATE["calls"]))
                    T(f"{width}/two Add navigates to OAuth start", "oauth-start-reached" in (pg.title() or "") or "workers.dev/c/" in pg.url, pg.url + " title=" + (pg.title() or ""))
                if scen == "cap":
                    T(f"{width}/cap no Add button at 10", not m["addVisible"])
                    T(f"{width}/cap cap text shown", "remove one" in m["acctText"], m["acctText"][:200])
                    T(f"{width}/cap 10 account rows", len(m["accts"]) == 10, str(len(m["accts"])))
                pg.screenshot(path=str(SHOTS / f"ui-{width}-{scen}.png"))
                pg.close()
        # Remove flow (single pass at 412/two)
        STATE["scen"] = "two"; STATE["calls"] = []
        pg = b.new_page(viewport={"width": 412, "height": 915})
        pg.add_init_script("""localStorage.setItem('dv_token', JSON.stringify('rig-token'));
                              localStorage.setItem('dv_acct', JSON.stringify({name:'Probe', email:'probe@example.com'}));
                              localStorage.setItem('dv_lang', JSON.stringify('en'));""")
        pg.on("dialog", lambda d: d.accept())
        def handle2(route):
            u = route.request.url
            if "/api/" in u:
                STATE["calls"].append((u.split("/api/")[1], route.request.post_data or ""))
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload(u.split("/api/")[1])))
            elif "workers.dev/c/" in u:
                route.fulfill(status=200, content_type="text/html", body="<title>oauth-start-reached</title>reached")
            else:
                route.continue_()
        pg.route("**/*", handle2)
        pg.goto(f"http://127.0.0.1:{PORT}/index.html#/connect")
        pg.wait_for_timeout(2200)
        pg.click("#acctList [data-acct-del='aa2']"); pg.wait_for_timeout(1200)
        rm = [c for c in STATE["calls"] if "connect/remove" in c[0]]
        T("remove posts connect/remove with account id", bool(rm) and "aa2" in rm[-1][1], json.dumps(STATE["calls"]))
        pg.close()
        b.close()
    srv.shutdown()
    print("\n== rig_ui:", "ALL PASS" if not fails else f"FAILS: {fails}")

if __name__ == "__main__":
    run()
