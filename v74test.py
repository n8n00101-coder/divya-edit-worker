"""v74 python tests — delivery/setup transport hardening.
whatsapp.py: send_text retries transient Meta failures and reports its
result; send_media raises when the final send fails (it used to be
unchecked — media could upload and never arrive); download_media
validates both responses instead of saving an error page as the video.
setup.py: report_result retries the authoritative outcome POST
(a single lost POST used to lose a created API key + stall the chain).
Run: python3 v74test.py
"""
import asyncio
import os
import sys
import types

os.environ.setdefault("WA_TOKEN", "test-token")
os.environ.setdefault("WA_PHONE_ID", "12345")
os.environ.setdefault("DATA_DIR", "/tmp/v74test-data")
os.environ.setdefault("WORKER_URL", "https://worker.test")
os.environ.setdefault("RUNNER_KEY", "rk")
os.environ.setdefault("JOB", "jobv74")
os.environ.setdefault("PROVIDER", "groq")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = []
FAIL = []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name)


# ---------- whatsapp.py with a scripted fake httpx ----------
import httpx  # noqa: E402


class FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text or ""

    def json(self):
        return self._payload


class FakeClient:
    script = []       # list of FakeResp or Exception, consumed in order
    calls = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        FakeClient.calls.append(("POST", url))
        item = FakeClient.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def get(self, url, **kw):
        FakeClient.calls.append(("GET", url))
        item = FakeClient.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


_real_client = httpx.AsyncClient
httpx.AsyncClient = FakeClient
import whatsapp as wa  # noqa: E402

wa_asyncio_sleep = asyncio.sleep


async def _no_sleep(_):
    return None


asyncio.sleep = _no_sleep  # keep retries instant in tests


async def wa_tests():
    # send_text: 429 then 200 -> True, 2 attempts
    FakeClient.script = [FakeResp(429), FakeResp(200)]
    FakeClient.calls = []
    ok1 = await wa.send_text("919999999999", "hello")
    check("wa send_text retries a 429 and succeeds", ok1 is True and len(FakeClient.calls) == 2)

    # send_text: persistent 500 -> False after 3 attempts (not silent)
    FakeClient.script = [FakeResp(500), FakeResp(500), FakeResp(500)]
    FakeClient.calls = []
    ok2 = await wa.send_text("919999999999", "hello")
    check("wa send_text reports persistent failure (False, 3 attempts)", ok2 is False and len(FakeClient.calls) == 3)

    # send_media: upload OK, final send 400 -> raises (was unchecked)
    FakeClient.script = [FakeResp(200, {"id": "mid1"}), FakeResp(400, text="bad")]
    path = os.path.join(os.environ["DATA_DIR"], "t.mp4")
    os.makedirs(os.environ["DATA_DIR"], exist_ok=True)
    open(path, "wb").write(b"\x00" * 64)
    try:
        await wa.send_media("919999999999", path, "video", caption="c")
        check("wa send_media raises when the send fails", False)
    except RuntimeError:
        check("wa send_media raises when the send fails", True)

    # send_media: upload OK + send OK -> returns cleanly
    FakeClient.script = [FakeResp(200, {"id": "mid2"}), FakeResp(200)]
    try:
        await wa.send_media("919999999999", path, "video", caption="c")
        check("wa send_media happy path", True)
    except Exception:
        check("wa send_media happy path", False)

    # download_media: meta 401 -> raises instead of writing an error page
    FakeClient.script = [FakeResp(401)]
    try:
        await wa.download_media("midX", "mp4")
        check("wa download_media raises on meta failure", False)
    except RuntimeError:
        check("wa download_media raises on meta failure", True)


asyncio.run(wa_tests())
asyncio.sleep = wa_asyncio_sleep
httpx.AsyncClient = _real_client

# ---------- setup.py report_result with a scripted sync httpx ----------
# setup.py imports playwright at module level; it is not installed in
# this environment, so stub the module (report_result never touches it).
pw = types.ModuleType("playwright")
pw_sync = types.ModuleType("playwright.sync_api")
pw_sync.sync_playwright = lambda *a, **k: None
pw.sync_api = pw_sync
sys.modules.setdefault("playwright", pw)
sys.modules.setdefault("playwright.sync_api", pw_sync)

setup_calls = {"n": 0, "statuses": []}
_real_post = httpx.post


def fake_post(url, **kw):
    setup_calls["n"] += 1
    status = setup_calls["statuses"].pop(0) if setup_calls["statuses"] else 200
    if isinstance(status, Exception):
        raise status
    return FakeResp(status)


httpx.post = fake_post
import setup as setup_mod  # noqa: E402

setup_mod.time.sleep = lambda s: None  # instant backoff in tests

setup_calls["statuses"] = [500, 200]
setup_calls["n"] = 0
check("setup report_result retries a 500 then succeeds",
      setup_mod.report_result("groq", "done", key="gsk_test") is True and setup_calls["n"] == 2)

setup_calls["statuses"] = [Exception("net down"), 503, 200]
setup_calls["n"] = 0
check("setup report_result retries network errors + 503",
      setup_mod.report_result("groq", "done", key="gsk_test") is True and setup_calls["n"] == 3)

setup_calls["statuses"] = [500, 500, 500, 500]
setup_calls["n"] = 0
check("setup report_result gives up loudly after 4 attempts (False)",
      setup_mod.report_result("groq", "failed", error="x") is False and setup_calls["n"] == 4)

httpx.post = _real_post

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
