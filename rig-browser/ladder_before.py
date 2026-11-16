#!/usr/bin/env python3
"""REPRODUCTION LADDER (before fix) — drives Julie's PRODUCTION browser
primitives (setup.py from main, imported unmodified — the exact file the
GitHub runner executes) against real, benign public tasks.

A stub Worker on loopback records every progress/frame post, proving the
Worker glue the runner would use. All page actions go through setup.py's
own helpers (goto / dismiss_cookie_banner / click / fill / _page_says) —
the same helpers the provider flows use. Where a capability does not
exist in setup.py at all, the rung records that as the failure.
"""
import json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = Path(__file__).parent / "before"
OUT.mkdir(parents=True, exist_ok=True)

# Stub Worker (records the runner->Worker glue)
POSTS = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, body, code=200):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        self._send(json.dumps({"ok": True, "job": {"provider": "browse", "state": "running", "tcInputs": []}}))
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try: payload = json.loads(raw or b"{}")
        except Exception: payload = {"_raw_len": len(raw)}
        POSTS.append({"path": self.path, "payload": {k: (v[:80] + "…" if isinstance(v, str) and len(v) > 80 else v) for k, v in payload.items() if k != "img"}, "img_len": len(payload.get("img") or "")})
        self._send(json.dumps({"ok": True}))

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

# Local-VM harness adaptations ONLY (production GitHub runners have direct
# egress and no proxy env): (1) this VM's ambient no_proxy contains bracketed
# IPv6 entries that make httpx choke while building its client (rig-v96 hit
# the same) — pin both cases to loopback so stub-Worker posts stay local.
os.environ["no_proxy"] = "127.0.0.1,localhost"
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

# (2) This VM's egress is a TLS-intercepting proxy requiring PREEMPTIVE
# Basic auth (curl sends it; Chromium waits for a 407 that never comes ->
# ERR_TUNNEL_CONNECTION_FAILED) and its intercept CA is trusted by the
# system bundle but not by Playwright's Chromium (-> CERT_AUTHORITY_INVALID).
# So the ladder runs a tiny in-process CONNECT relay on loopback that adds
# the auth (parsed from the ambient env in-process, never printed/stored),
# and creates its context with ignore_https_errors=True. Neither exists in
# production; every primitive under test below is unmodified setup.py code.
import base64, socket
from urllib.parse import urlparse
def _start_relay():
    pu = urlparse(os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or "")
    if not pu.hostname:
        return None
    cred = base64.b64encode(f"{pu.username}:{pu.password}".encode()).decode()
    up_addr = (pu.hostname, pu.port)
    def pipe(a, b):
        try:
            while True:
                d = a.recv(65536)
                if not d: break
                b.sendall(d)
        except Exception: pass
        try: b.shutdown(socket.SHUT_WR)
        except Exception: pass
    def handle(c):
        try:
            buf = b""
            while b"\r\n\r\n" not in buf:
                d = c.recv(4096)
                if not d: c.close(); return
                buf += d
            head, rest = buf.split(b"\r\n\r\n", 1)
            parts = head.split(b"\r\n")[0].decode("latin1").split(" ")
            if parts[0].upper() != "CONNECT":
                c.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n"); c.close(); return
            target = parts[1]
            up = socket.create_connection(up_addr, timeout=15)
            up.sendall((f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
                        f"Proxy-Authorization: Basic {cred}\r\n\r\n").encode())
            rbuf = b""
            while b"\r\n\r\n" not in rbuf:
                d = up.recv(4096)
                if not d: c.close(); up.close(); return
                rbuf += d
            if b" 200 " not in rbuf.split(b"\r\n")[0]:
                c.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n"); c.close(); up.close(); return
            c.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if rest: up.sendall(rest)
            threading.Thread(target=pipe, args=(c, up), daemon=True).start()
            pipe(up, c)
            c.close(); up.close()
        except Exception:
            try: c.close()
            except Exception: pass
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 18080)); srv.listen(50)
    def serve():
        while True:
            c, _ = srv.accept()
            threading.Thread(target=handle, args=(c,), daemon=True).start()
    threading.Thread(target=serve, daemon=True).start()
    return "http://127.0.0.1:18080"
RELAY = _start_relay()
os.environ["WORKER_URL"] = f"http://127.0.0.1:{port}"
os.environ["RUNNER_KEY"] = "ladder-stub-key"
os.environ["JOB"] = "ladderjob1"
os.environ["PROVIDER"] = "browse"
os.environ["BROWSER_MODE"] = "ephemeral"
sys.path.insert(0, str(ROOT))
import setup as S  # the production runner module, unmodified
from playwright.sync_api import sync_playwright

RESULTS = []
def rung(name, fn):
    t0 = time.time()
    try:
        ev = fn()
        RESULTS.append({"rung": name, "ok": True, "evidence": ev, "secs": round(time.time() - t0, 1)})
        print(f"[PASS] {name}: {json.dumps(ev)[:400]}", flush=True)
    except Exception as e:
        RESULTS.append({"rung": name, "ok": False, "evidence": {"error": f"{type(e).__name__}: {e}"}, "secs": round(time.time() - t0, 1)})
        print(f"[FAIL] {name}: {type(e).__name__}: {e}", flush=True)

def main():
    with sync_playwright() as p:
        # Launch + context replicate S.launch_browser / S.open_context
        # with only the two local-egress adaptations above (relay proxy,
        # ignore_https_errors for the intercept CA).
        browser = p.chromium.launch(headless=True, proxy={"server": RELAY} if RELAY else None)
        ctx = browser.new_context(**S.profile_context_kwargs(), ignore_https_errors=True)
        try: ctx.add_init_script(S.CURSOR_JS)
        except Exception: pass
        page = ctx.new_page()
        S._CUR["page"] = page

        # ---- Rung A: open a public site, dismiss cookie banner, navigate, report headline
        def rung_a():
            ev = {}
            ok = S.goto(page, "https://www.cookiebot.com/en/")
            ev["goto_cookiebot"] = ok
            ev["title_before"] = page.title()
            hit = S.dismiss_cookie_banner(page)
            ev["banner_dismissed_via"] = hit or "(none reported)"
            ev["banner_still_present"] = S._consent_banner_present(page)
            ok2 = S.goto(page, "https://en.wikipedia.org/wiki/Main_Page")
            ev["goto_wikipedia"] = ok2
            ev["wiki_title"] = page.title()
            clicked = S.click(page, ["a[href='/wiki/Portal:Current_events']"])
            ev["section_click"] = clicked
            page.wait_for_timeout(1500)
            ev["final_url"] = page.url
            ev["final_title"] = page.title()
            h = page.locator("h1").first.inner_text() if page.locator("h1").count() else ""
            ev["headline_h1"] = h.strip()
            S.progress("running", "rung-a", f"On {ev['final_title']}", page.url)
            if not (ok2 and clicked and "Current events" in ev["final_title"]):
                raise RuntimeError(f"navigation incomplete: {ev}")
            return ev
        rung("A open+dismiss+navigate+report", rung_a)

        # ---- Rung B: search -> click result -> extract a fact
        def rung_b():
            ev = {}
            ok = S.goto(page, "https://html.duckduckgo.com/html/?q=capital+of+norway+wikipedia")
            ev["goto_ddg"] = ok
            ev["ddg_title"] = page.title()
            clicked = S.click(page, ["a.result__a"])
            ev["result_click"] = clicked
            page.wait_for_timeout(2500)
            ev["final_url"] = page.url
            ev["final_title"] = page.title()
            txt = page.inner_text("body")[:2000]
            ev["fact_found"] = "capital" in txt.lower() and ("oslo" in txt.lower())
            ev["text_head"] = " ".join(txt.split())[:220]
            if not (clicked and ev["fact_found"]):
                raise RuntimeError(f"search flow incomplete: {ev}")
            return ev
        rung("B search+click+extract fact", rung_b)

        # ---- Rung C: demo form — fill fields, choose options, submit, read confirmation
        def rung_c():
            ev = {}
            ok = S.goto(page, "https://testpages.eviltester.com/styled/basic-html-form-test.html")
            ev["goto_form"] = ok
            ev["fill_username"] = S.fill(page, ["input[name='username']"], "ladder_user")
            ev["fill_password"] = S.fill(page, ["input[name='password']"], "ladder_pass_1")
            ev["fill_comments"] = S.fill(page, ["textarea[name='comments']"], "ladder comment")
            ev["check_box"] = S.click(page, ["input[name='checkboxes[]'][value='cb3']"])
            ev["radio"] = S.click(page, ["input[name='radioval'][value='rd2']"])
            # <select>: setup.py has NO select helper — fill() is the only tool; try it.
            ev["select_via_fill"] = S.fill(page, ["select[name='dropdown']"], "dd5")
            sel_val = page.locator("select[name='dropdown']").input_value()
            ev["dropdown_value_after_fill"] = sel_val
            ev["submit_click"] = S.click(page, ["input[type='submit']"])
            page.wait_for_timeout(2000)
            ev["final_url"] = page.url
            body = page.inner_text("body")
            ev["echo_username"] = "ladder_user" in body
            ev["echo_dropdown_dd5"] = "dd5" in body
            if not (ev["echo_username"] and ev["submit_click"]):
                raise RuntimeError(f"form flow incomplete: {ev}")
            if not ev["select_via_fill"] or sel_val != "dd5":
                ev["GAP"] = "no working <select> path in setup.py primitives"
            return ev
        rung("C demo form fill+submit+confirm", rung_c)

        # ---- Rung D: redirect chain + multi-page click-through with waits
        def rung_d():
            ev = {}
            ok = S.goto(page, "https://httpbin.org/redirect/3")
            ev["goto_redirect"] = ok
            page.wait_for_timeout(1000)
            ev["landed_url"] = page.url
            ok2 = S.goto(page, "https://en.wikipedia.org/wiki/Oslo")
            ev["goto_oslo"] = ok2
            clicked = S.click(page, ["a[href='/wiki/Norway']"])
            ev["article_click"] = clicked
            page.wait_for_timeout(2000)
            ev["final_title"] = page.title()
            ev["final_url"] = page.url
            if not ("/get" in ev["landed_url"] and "Norway" in ev["final_title"]):
                raise RuntimeError(f"redirect/multipage incomplete: {ev}")
            return ev
        rung("D redirect chain + multi-page", rung_d)

        # ---- Rung E: live-view frame + progress glue (what the app would show)
        def rung_e():
            ev = {}
            S.progress("running", "rung-e", "Frame check on Wikipedia Norway page", page.url)
            time.sleep(0.2)
            frames = [x for x in POSTS if "tcframe" in x["path"]]
            progs = [x for x in POSTS if "progress" in x["path"]]
            ev["frames_posted"] = len(frames)
            ev["frame_img_bytes"] = frames[-1]["img_len"] if frames else 0
            ev["progress_posts"] = len(progs)
            if not frames or frames[-1]["img_len"] < 1000:
                raise RuntimeError(f"no real frame streamed: {ev}")
            return ev
        rung("E live frame + progress glue", rung_e)

        browser.close()
    (OUT / "results.json").write_text(json.dumps({"results": RESULTS, "worker_posts": POSTS}, indent=1))
    print("\n=== LADDER SUMMARY ===")
    for r in RESULTS:
        print(("PASS " if r["ok"] else "FAIL ") + r["rung"])
    print(f"worker posts recorded: {len(POSTS)}")

if __name__ == "__main__":
    main()
