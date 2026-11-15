import sys, threading, glob, json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).parent))
import audit as A
PORT = 8941
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = ThreadingHTTPServer(("127.0.0.1", PORT), lambda *a, **k: Quiet(*a, directory=str(A.APP), **k))
threading.Thread(target=srv.serve_forever, daemon=True).start()
shell = sorted(glob.glob(str(Path.home() / ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell")))[-1]
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=shell)
    ctx = b.new_context(viewport={"width":360,"height":740}, is_mobile=True, has_touch=True, color_scheme="dark")
    ctx.add_init_script(A.seed_script(True, "en", False))
    page = ctx.new_page()
    page.route("**/api/**", A.make_handler("B"))
    for pat in ("**://cdn.jsdelivr.net/**", "**://esm.sh/**", "**://huggingface.co/**", "**://*.hf.co/**"):
        page.route(pat, lambda r: r.abort())
    page.on("pageerror", lambda e: print("PAGEERROR:", str(e)[:120], "\nSTACK:", (e.stack or "")[:600]))
    page.goto(f"http://127.0.0.1:{PORT}/index.html")
    page.wait_for_timeout(2500)
    for r in ("chat", "voice", "settings", "plan", "chat"):
        print("NAV", r)
        page.evaluate(f"location.hash = '#/{r}'")
        page.wait_for_timeout(1500)
    print("opening voice list")
    page.evaluate("location.hash = '#/settings'"); page.wait_for_timeout(800)
    page.evaluate("document.querySelector('#voiceRow')?.click()")
    page.wait_for_timeout(2500)
    print("state after boot:", page.evaluate("typeof kokoroStatus === 'function' ? JSON.stringify(kokoroStatus()) : 'n/a'"))
    b.close()
