"""v70 tests: Julie creates her OWN Pexels key in the setup chain.

1. CHAIN_ORDER / FLOWS wiring (setup.py imported with a stubbed
   playwright — the runner-only browser lib is absent in this env, and
   importing setup.py reads env vars, so they are set first).
2. classify_pexels_page — the three API-page states, all covered:
   has-key / can-request / paused (Pexels has paused new-key issuance,
   verified live 2026-11-13).
3. parse_pexels_key — reads the key from the "Your API Key" spots only;
   page hash-soup and stray tokens are never mistaken for a key.
4. flow_pexels against a FakePage: the paused page ends as the honest
   UNAVAILABLE failure (status "failed" — the chain advances on failed;
   only "stopped" ends a chain — plus no_retry, so no retry-grind), and
   a page showing an existing key returns it; submit_provider_result
   then saves it through the standard runner key path.
5. run_provider contract: a no_retry unavailable result is attempted
   exactly ONCE (no retry-grind against a paused provider).
6. test_key("pexels") — the Pexels probe uses the raw-key Authorization
   header (no Bearer), matching broll.py.

No live browser, no live APIs. Run: python v70test.py
"""

import os
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

os.environ.setdefault("WORKER_URL", "http://127.0.0.1:9")
os.environ.setdefault("RUNNER_KEY", "test-runner-key")
os.environ.setdefault("JOB", "v70testjob")
os.environ.setdefault("PROVIDER", "pexels")

# setup.py imports playwright at module level; stub it (not installed here).
_pw = types.ModuleType("playwright")
_pw_api = types.ModuleType("playwright.sync_api")
_pw_api.sync_playwright = lambda: None
_pw.sync_api = _pw_api
sys.modules.setdefault("playwright", _pw)
sys.modules.setdefault("playwright.sync_api", _pw_api)

import setup  # noqa: E402

FAKE_KEY = "Ab1" * 18 + "Zz"  # 56 chars, alnum, letters + digits
assert len(FAKE_KEY) == 56


# ------------------------------------------------------------- 1. wiring
def test_wiring():
    assert setup.CHAIN_ORDER == ["groq", "openrouter", "gemini", "cloudflare", "pexels"], setup.CHAIN_ORDER
    print("CHAIN_ORDER ends with pexels (after cloudflare): PASS")
    cfg = setup.FLOWS["pexels"]
    assert cfg["name"] == "Pexels" and cfg["flow"] == "pexels"
    assert cfg["url"] == "https://www.pexels.com/api/" and cfg["keys_url"] == cfg["url"]
    assert cfg["key_patterns"], "pexels needs fallback key patterns"
    src = (HERE / "setup.py").read_text(encoding="utf-8")
    assert 'if flow == "pexels":' in src and "return flow_pexels(page, job, cfg)" in src
    assert '"pexels")' in src  # entry wall check covers the pexels flow
    print("FLOWS['pexels'] + run_flow dispatch + wall-check coverage: PASS")


# ------------------------------------------------- 2. page-state helpers
def test_classify():
    html_key = f'<div>Your API Key</div><input type="text" readonly value="{FAKE_KEY}">'
    text_key = "Your API Key — use this key in the Authorization header."
    assert setup.classify_pexels_page(text_key, html_key) == "has-key"
    print("classify has-key (key input on the page): PASS")

    text_paused = ("Pexels API. New API key issuance is currently paused "
                   "and cannot be requested. Get Started")
    assert setup.classify_pexels_page(text_paused, "<html></html>") == "paused"
    print("classify paused (issuance-paused notice): PASS")

    text_form = "Pexels API — Get Started. Tell us about your project to request access."
    assert setup.classify_pexels_page(text_form, "<html></html>") == "can-request"
    print("classify can-request (signed in, form live): PASS")

    # A paused page that ALSO shows an existing key is has-key first:
    # issuance being paused never hides a key the account already has.
    assert setup.classify_pexels_page(text_paused + " Your API Key", html_key) == "has-key"
    print("classify has-key beats paused (existing key still read): PASS")


def test_parse():
    html = f'<input type="text" class="api-key-field" readonly value="{FAKE_KEY}">'
    assert setup.parse_pexels_key(html, "") == FAKE_KEY
    print("parse from the readonly key input: PASS")

    text = f"Your API Key\n{FAKE_KEY}\nKeep it secret."
    assert setup.parse_pexels_key("", text) == FAKE_KEY
    print("parse from bare text after the 'Your API Key' label: PASS")

    # Hash soup elsewhere on the page is NOT a key.
    soup = '<input type="hidden" value="deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef">'
    assert setup.parse_pexels_key(soup, "some page text") is None
    print("parse ignores hidden-input hex hashes: PASS")

    # A key-shaped token NOT in a trusted spot is not a key.
    plain = f'<input type="search" value="{FAKE_KEY}">'
    assert setup.parse_pexels_key(plain, "search the site") is None
    stray = f"a random token {FAKE_KEY} in body text with no label nearby"
    assert setup.parse_pexels_key("", stray) is None
    print("parse ignores tokens outside the key spots: PASS")


# ------------------------------------------------------- 3. flow (fake)
class FakeLocator:
    def __init__(self):
        self.first = self

    def count(self):
        return 0

    def is_visible(self):
        return False


class FakePage:
    """The smallest page surface flow_pexels touches on the paused /
    has-key / form-grace paths: no visible controls anywhere."""

    def __init__(self, text="", html=""):
        self._text, self._html = text, html
        self.url = "https://www.pexels.com/api/"
        self.frames = []

    def goto(self, url, **kw):
        self.url = url

    def wait_for_timeout(self, ms):
        pass

    def inner_text(self, sel):
        return self._text

    def content(self):
        return self._html

    def title(self):
        return "Pexels API"

    def locator(self, sel):
        return FakeLocator()


def _quiet_setup():
    """Silence setup.py's network helpers for the fake-page flows."""
    saved = {"progress": setup.progress, "get_job": setup.get_job}
    calls = []
    setup.progress = lambda *a, **k: calls.append((a, k))
    setup.get_job = lambda: {"state": "running"}
    return saved, calls


def _restore(saved):
    setup.progress, setup.get_job = saved["progress"], saved["get_job"]


def test_flow_paused():
    saved, calls = _quiet_setup()
    try:
        page = FakePage(text=("Pexels API. New API key issuance is currently "
                              "paused and cannot be requested."))
        res = setup.flow_pexels(page, {"email": "u@example.com"}, setup.FLOWS["pexels"])
    finally:
        _restore(saved)
    assert res["status"] == "failed", res  # failed advances the chain; only "stopped" ends it
    assert res["status"] != "stopped"
    assert res["key"] is None
    assert (res["extra"] or {}).get("outcome") == "unavailable"
    assert (res["extra"] or {}).get("no_retry") is True
    assert "paused" in (res["error"] or "")
    print("flow paused -> honest unavailable failure (chain advances, no retry): PASS")
    # The key (there is none) aside, no progress payload may ever carry a key.
    assert all(FAKE_KEY not in str(c) for c in calls)
    print("flow paused -> no key material in progress payloads: PASS")


def test_flow_has_key_and_save_path():
    saved, _calls = _quiet_setup()
    try:
        page = FakePage(
            text="Your API Key — use this key in the Authorization header.",
            html=f'<input type="text" readonly value="{FAKE_KEY}">')
        res = setup.flow_pexels(page, {"email": "u@example.com"}, setup.FLOWS["pexels"])
        assert res["status"] == "done" and res["key"] == FAKE_KEY, res

        # The standard save path: verify -> legacy key post (the Worker
        # seals it as ukey:<user>:pexels) -> result report.
        posted, reported = [], []
        real_test, real_post, real_report = setup.test_key, setup.post_key_legacy, setup.report_result
        setup.test_key = lambda provider, key: True
        setup.post_key_legacy = lambda provider, key: posted.append((provider, key)) or True
        setup.report_result = lambda provider, status, key=None, error=None, extra=None: reported.append((provider, status)) or True
        try:
            setup.submit_provider_result("pexels", "Pexels", res)
        finally:
            setup.test_key, setup.post_key_legacy, setup.report_result = real_test, real_post, real_report
    finally:
        _restore(saved)
    assert posted == [("pexels", FAKE_KEY)], posted
    assert reported == [("pexels", "done")], reported
    print("flow has-key -> key read + saved via the standard runner key path: PASS")


def test_flow_form_unusable_fails_clean():
    saved, _calls = _quiet_setup()
    try:
        page = FakePage(text="Pexels API — Get Started. Tell us about your project.")
        res = setup.flow_pexels(page, {"email": "u@example.com"}, setup.FLOWS["pexels"])
    finally:
        _restore(saved)
    assert res["status"] == "failed" and res["key"] is None
    assert "API access form" in (res["error"] or "")
    print("flow can-request but form unusable -> clean named failure, no hang: PASS")


# ------------------------------------------- 4. run_provider retry rule
class FakeContext:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page

    def close(self):
        pass


class FakeBrowser:
    def __init__(self, page):
        self._page = page
        self.contexts = 0

    def new_context(self, **kw):
        self.contexts += 1
        return FakeContext(self._page)


def test_run_provider_no_retry_on_unavailable():
    saved, _calls = _quiet_setup()
    try:
        page = FakePage(text=("New API key issuance is currently paused "
                              "and cannot be requested."))
        browser = FakeBrowser(page)
        job = {"email": "u@example.com", "flow": "pexels"}
        res = setup.run_provider(browser, job, setup.FLOWS["pexels"], "pexels")
    finally:
        _restore(saved)
    assert browser.contexts == 1, f"expected exactly 1 attempt, got {browser.contexts}"
    assert res["status"] == "failed" and (res["extra"] or {}).get("outcome") == "unavailable"
    print("run_provider: unavailable attempted exactly once (no retry-grind): PASS")


# ------------------------------------------------------------ 5. test_key
def test_test_key():
    class R:
        def __init__(self, sc):
            self.status_code = sc

    seen = {}
    real_get = setup.httpx.get

    def fake_get(url, **kw):
        seen["url"], seen["kw"] = url, kw
        return R(seen.pop("sc", 200))

    setup.httpx.get = fake_get
    try:
        assert setup.test_key("pexels", FAKE_KEY) is True
        assert seen["url"] == "https://api.pexels.com/v1/curated"
        assert seen["kw"]["headers"]["Authorization"] == FAKE_KEY  # raw key, no Bearer
        seen["sc"] = 401
        assert setup.test_key("pexels", FAKE_KEY) is False
    finally:
        setup.httpx.get = real_get
    print("test_key pexels: curated probe, raw-key Authorization header: PASS")


if __name__ == "__main__":
    test_wiring()
    test_classify()
    test_parse()
    test_flow_paused()
    test_flow_has_key_and_save_path()
    test_flow_form_unusable_fails_clean()
    test_run_provider_no_retry_on_unavailable()
    test_test_key()
    print("v70 tests: ALL PASS")
