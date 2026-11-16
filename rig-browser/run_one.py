# After-ladder subprocess entry: runs browse.py's REAL main() for one
# job against the stub Worker, with ONLY the two local-egress
# adaptations the before-ladder needed (CONNECT relay proxy +
# ignore_https_errors for the intercept CA). Production code is not
# modified — the patches are monkeypatches applied in this process.
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ["no_proxy"] = "127.0.0.1,localhost"

from relay import start_relay
RELAY = start_relay()

import setup as S


def launch_patched(p):
    kw = {"headless": True, "proxy": {"server": RELAY} if RELAY else None}
    if S.PROFILE_MODE:
        try:
            return p.chromium.launch(channel="chromium", **kw)
        except Exception:
            pass
    return p.chromium.launch(**kw)


def open_context_patched(browser):
    if S.PROFILE_MODE:
        ctx = browser.new_context(**S.profile_context_kwargs(), ignore_https_errors=True)
    else:
        ctx = browser.new_context(viewport={"width": 1280, "height": 800}, ignore_https_errors=True)
    try:
        ctx.add_init_script(S.CURSOR_JS)
    except Exception:
        pass
    return ctx


S.launch_browser = launch_patched
S.open_context = open_context_patched

import browse
browse.main()
