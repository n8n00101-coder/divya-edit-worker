"""v81 tests: the widened automate setup chain (R59 — Julie creates
MORE kinds of free API keys herself).

1. CHAIN_ORDER: exact v81 order — originals keep their head order,
   then chat/vision, then search, then media, Pexels last.
2. FLOWS completeness: every chain id has a full FLOWS entry whose
   flow is dispatchable in run_flow, and every used flow is covered
   by the v68 entry wall check (fast wall -> Take Control).
3. Key patterns: canonical sample keys match; wrong-shape junk and
   prefix-less tokens do NOT match the prefixed providers.
4. test_key routing: each new provider probes its real endpoint with
   the right auth shape; trial-credit providers (together / ai21 /
   voyage) are proven with a real call, and a payment-held / zero-
   balance answer is a FAILURE, never a pass.
5. flow_jina reads an auto-generated key off a fake page; flow_mistral
   routes the phone gate to the human step (no number is invented).
6. Cross-file consistency: the Worker's SETUP_PROVIDERS / R55
   KEYLIST_PROVIDERS / setup-start default and the app's one-tap list
   + PNAMES all cover exactly the chain (app list = chain minus
   cloudflare, its standing exception).
7. Audit guard: providers classified NOT-FREE / WALLED in the v81
   audit (brave, deepseek, replicate, huggingface, github) are NOT
   in the chain.

No live browser, no live APIs. Run: python v81test.py
"""

import os
import re
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

os.environ.setdefault("WORKER_URL", "http://127.0.0.1:9")
os.environ.setdefault("RUNNER_KEY", "test-runner-key")
os.environ.setdefault("JOB", "v81testjob")
os.environ.setdefault("PROVIDER", "chain")

_pw = types.ModuleType("playwright")
_pw_api = types.ModuleType("playwright.sync_api")
_pw_api.sync_playwright = lambda: None
_pw.sync_api = _pw_api
sys.modules.setdefault("playwright", _pw)
sys.modules.setdefault("playwright.sync_api", _pw_api)

import setup  # noqa: E402

EXPECTED_CHAIN = ["groq", "openrouter", "gemini", "cloudflare",
                  "cohere", "together", "sambanova", "fireworks", "cerebras",
                  "nvidia", "mistral", "ai21", "voyage",
                  "tavily", "serper", "exa",
                  "deepgram", "assemblyai", "elevenlabs", "stability", "jina",
                  "pexels"]
NEW_IDS = EXPECTED_CHAIN[4:-1]


# ------------------------------------------------------------- 1. chain
def test_chain_order():
    assert setup.CHAIN_ORDER == EXPECTED_CHAIN, setup.CHAIN_ORDER
    assert len(set(setup.CHAIN_ORDER)) == len(setup.CHAIN_ORDER), "duplicate provider in chain"
    print("CHAIN_ORDER exact v81 order, no duplicates: PASS")


# ------------------------------------------------------------- 2. flows
def test_flows_complete():
    src = (HERE / "setup.py").read_text(encoding="utf-8")
    m = re.search(r'if flow in \(([^)]*)\)', src)
    wall_flows = set(re.findall(r'"([a-z]+)"', m.group(1)))
    for pid in EXPECTED_CHAIN:
        cfg = setup.FLOWS[pid]
        for field in ("name", "url", "keys_url", "flow", "key_patterns"):
            assert cfg.get(field), f"{pid} missing FLOWS[{field}]"
        # "google" is the one pre-existing exception (Gemini is
        # provisioned server-side; its runner flow self-loads). Every
        # NEW v81 provider's flow MUST be in the entry wall check.
        assert cfg["flow"] in wall_flows | {"google"}, f"{pid}: unknown flow {cfg['flow']}"
        if pid in NEW_IDS:
            assert cfg["flow"] in wall_flows, f"{pid}: flow {cfg['flow']} not in the entry wall check {wall_flows}"
    for flow in ("mistral", "jina"):
        assert f'if flow == "{flow}":' in src and f"return flow_{flow}(page, job, cfg)" in src
    print("FLOWS complete for all 22; every flow wall-checked + dispatched: PASS")


# ------------------------------------------------------- 3. key patterns
# Fake canonical-shape samples, assembled from pieces at runtime on
# purpose: a contiguous realistic token literal in source trips
# GitHub's secret-scanning push protection (it cannot know the token
# is invented). These are NOT real keys — they only exercise the
# extraction regexes.
SAMPLES = {
    "cohere": "Ab1Cd2" + "Ef3Gh4" + "Ij5Kl6" + "Mn7Op8" + "Qr9St0" + "Uv1Wx2" + "Yz34",
    "together": "0123456789abcdef" * 4,
    "sambanova": "123e4567-e89b-12d3-a456-426614174000",
    "fireworks": "Fw9" + "a1B2" * 11 + "Zz",
    "cerebras": "csk-" + "ab12CD34" * 6,
    "nvidia": "nvapi-" + "Ab1_-" * 9 + "Zz9",
    "mistral": "Mi9" + "x7Qp" * 7 + "Z",  # exactly 32 chars, the real key shape
    "ai21": "Ai9" + "k3Lm" * 11 + "Qp7",
    "voyage": "pa-" + "Vy8" + "m4Nq" * 10,
    "tavily": "tvly-dev-" + "Tv5" + "z8Ws" * 8,
    "serper": "fedcba98" + "76543210" + "fedcba98" + "76543210" + "fedcba98",  # 40 hex
    "exa": "9b2f4c1e-7a3d-4e5f-9a8b-1c2d3e4f5a6b",
    "deepgram": "abcdef01" + "23456789" * 4,  # 40 hex
    "assemblyai": "0123abcd" + "5678ef90" * 3,  # 32 hex
    "elevenlabs": "sk_" + "ef01" * 12,
    "stability": "sk-" + "St7" + "u2Vw" * 11 + "Xy",
    "jina": "jina_" + "Jn6" + "p9Qr" * 14,
}


def _matches(pid, text):
    return any(re.search(p, text) for p in setup.FLOWS[pid]["key_patterns"])


def test_key_patterns():
    for pid, sample in SAMPLES.items():
        assert len(sample) >= 32
        assert _matches(pid, f"prefix text {sample} suffix"), f"{pid}: canonical sample did not match"
    for pid in ("cerebras", "nvidia", "voyage", "jina", "tavily", "stability", "elevenlabs"):
        bare = re.sub(r"^(csk-|nvapi-|pa-|jina_|tvly-|sk-|sk_)", "", SAMPLES[pid])
        assert not _matches(pid, bare), f"{pid}: prefix-less token must not match"
    for pid in NEW_IDS:
        assert not _matches(pid, "short"), f"{pid}: junk matched"
    print("key patterns: canonical samples match, prefix-less/junk rejected: PASS")


# ------------------------------------------------------------ 4. test_key
class _R:
    def __init__(self, sc, payload=None):
        self.status_code = sc
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_test_key_routing():
    calls = []
    plan = {"get": [], "post": []}

    def fake_get(url, **kw):
        calls.append(("GET", url, kw.get("headers") or {}))
        return plan["get"].pop(0) if plan["get"] else _R(200)

    def fake_post(url, **kw):
        calls.append(("POST", url, kw.get("headers") or {}))
        return plan["post"].pop(0) if plan["post"] else _R(200)

    real_get, real_post = setup.httpx.get, setup.httpx.post
    setup.httpx.get, setup.httpx.post = fake_get, fake_post
    try:
        def last():
            return calls[-1]

        assert setup.test_key("cohere", "x" * 40) and last()[1] == "https://api.cohere.com/v1/models" and last()[2]["Authorization"].startswith("Bearer ")
        assert setup.test_key("cerebras", "csk-x") and "api.cerebras.ai" in last()[1]
        assert setup.test_key("nvidia", "nvapi-x") and "integrate.api.nvidia.com" in last()[1]
        assert setup.test_key("mistral", "x" * 32) and "api.mistral.ai" in last()[1]
        assert setup.test_key("sambanova", "k") and "api.sambanova.ai" in last()[1]
        assert setup.test_key("fireworks", "k") and "api.fireworks.ai" in last()[1]
        print("test_key models/chat probes (cohere/cerebras/nvidia/mistral/sambanova/fireworks): PASS")

        # together: free model from the live list, then a real chat.
        plan["get"] = [_R(200, {"data": [{"id": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"}]})]
        plan["post"] = [_R(200)]
        assert setup.test_key("together", "k") is True
        assert "api.together.xyz" in calls[-1][1]
        # together with a payment-held chat (402) is NOT a working key.
        plan["get"] = [_R(200, {"data": [{"id": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free"}]})]
        plan["post"] = [_R(402)]
        assert setup.test_key("together", "k") is False
        print("test_key together: real free-model chat; 402 = not verified: PASS")

        # ai21: first model id 404s, second answers.
        plan["post"] = [_R(404), _R(200)]
        assert setup.test_key("ai21", "k") is True
        # voyage: first model id 404s, second answers.
        plan["post"] = [_R(404), _R(200)]
        assert setup.test_key("voyage", "k") is True
        print("test_key ai21/voyage: model-id fallback loop: PASS")

        assert setup.test_key("tavily", "tvly-x") and "api.tavily.com/search" in last()[1]
        assert setup.test_key("serper", "k") and last()[2].get("X-API-KEY") == "k"
        assert setup.test_key("exa", "k") and last()[2].get("x-api-key") == "k"
        assert setup.test_key("deepgram", "k") and last()[2]["Authorization"] == "Token k"
        assert setup.test_key("assemblyai", "k") and last()[2]["Authorization"] == "k"
        assert setup.test_key("elevenlabs", "k") and last()[2].get("xi-api-key") == "k"
        assert setup.test_key("stability", "sk-x") and "user/balance" in last()[1]
        assert setup.test_key("jina", "jina_x") and "api.jina.ai/v1/embeddings" in last()[1]
        print("test_key search/media probes + auth header shapes: PASS")

        # A 401 anywhere is a failure, never a pass.
        plan["get"] = [_R(401)]
        assert setup.test_key("cohere", "bad") is False
        plan["post"] = [_R(401)]
        assert setup.test_key("tavily", "bad") is False
        print("test_key: 401 = not verified: PASS")
    finally:
        setup.httpx.get, setup.httpx.post = real_get, real_post


# ------------------------------------------------------------- 5. flows
class FakeLocator:
    def __init__(self):
        self.first = self

    def count(self):
        return 0

    def is_visible(self):
        return False


class FakePage:
    def __init__(self, text="", html=""):
        self._text, self._html = text, html
        self.url = "https://jina.ai/embeddings"

    def goto(self, url, **kw):
        self.url = url

    def wait_for_timeout(self, ms):
        pass

    def inner_text(self, sel):
        return self._text

    def content(self):
        return self._html

    def title(self):
        return "Jina AI"

    def locator(self, sel):
        return FakeLocator()


def _quiet():
    saved = {"progress": setup.progress, "get_job": setup.get_job}
    setup.progress = lambda *a, **k: None
    setup.get_job = lambda: {"state": "running"}
    return saved


def _restore(saved):
    setup.progress, setup.get_job = saved["progress"], saved["get_job"]


def test_flow_jina_reads_key():
    saved = _quiet()
    try:
        key = SAMPLES["jina"]
        page = FakePage(text=f"Your API key {key} — 10M free tokens", html=f"<code>{key}</code>")
        res = setup.flow_jina(page, {"email": "u@example.com"}, setup.FLOWS["jina"])
    finally:
        _restore(saved)
    assert res["status"] == "done" and res["key"] == key, res
    print("flow_jina: auto-generated key read off the page: PASS")


def test_flow_mistral_phone_gate():
    saved = _quiet()
    real_generic, real_pause = setup.flow_email_signup, setup.pause_for_signin
    setup.flow_email_signup = lambda page, job, cfg: setup._fail("Key kanipinchaledu — site layout marindhi (step: key creation). Take Control tho try cheyyi.")
    setup.pause_for_signin = lambda page, cfg, note=None: False
    try:
        page = FakePage(text="Verify your phone number to activate the Experiment plan.")
        res = setup.flow_mistral(page, {"email": "u@example.com"}, setup.FLOWS["mistral"])
    finally:
        setup.flow_email_signup, setup.pause_for_signin = real_generic, real_pause
        _restore(saved)
    assert res["status"] == "failed" and res["key"] is None
    assert (res["extra"] or {}).get("no_retry") is True
    assert "phone verification" in (res["error"] or "")
    print("flow_mistral: phone gate -> human step, honest no-retry failure: PASS")


# ------------------------------------------- 6. cross-file consistency
def test_cross_file_consistency():
    worker = (HERE / "cfworker" / "divya.js").read_text(encoding="utf-8")
    block = re.search(r"const SETUP_PROVIDERS = \{(.*?)\n\};", worker, re.S).group(1)
    worker_ids = set(re.findall(r"^  (\w+): \{", block, re.M))
    assert worker_ids == set(EXPECTED_CHAIN), worker_ids ^ set(EXPECTED_CHAIN)
    keylist = re.search(r"const KEYLIST_PROVIDERS = \[(.*?)\];", worker, re.S).group(1)
    for pid in NEW_IDS:
        assert f'["{pid}"' in keylist, f"KEYLIST missing {pid}"
    default_list = re.search(r"body\.providers : \[([^\]]+)\]", worker).group(1)
    assert [x.strip().strip('"') for x in default_list.split(",")] == EXPECTED_CHAIN
    app = (HERE / "app" / "app.js").read_text(encoding="utf-8")
    tap = re.search(r'setup/start", \{ method: "POST", json: \{ email, providers: \[([^\]]+)\]', app).group(1)
    assert [x.strip().strip('"') for x in tap.split(",")] == [p for p in EXPECTED_CHAIN if p != "cloudflare"]
    pnames = re.search(r"const PNAMES = \{(.*?)\};", app).group(1)
    for pid in EXPECTED_CHAIN:
        assert re.search(rf"\b{pid}:", pnames), f"PNAMES missing {pid}"
    print("cross-file: Worker SETUP_PROVIDERS/KEYLIST/default + app one-tap/PNAMES == chain: PASS")


# ---------------------------------------------------- 7. audit exclusions
def test_audit_exclusions():
    for pid in ("brave", "deepseek", "replicate", "huggingface", "github", "unsplash", "pixabay"):
        assert pid not in setup.CHAIN_ORDER and pid not in setup.FLOWS, pid
    print("audit exclusions absent from the chain (not-free / walled / already-covered): PASS")


if __name__ == "__main__":
    test_chain_order()
    test_flows_complete()
    test_key_patterns()
    test_test_key_routing()
    test_flow_jina_reads_key()
    test_flow_mistral_phone_gate()
    test_cross_file_consistency()
    test_audit_exclusions()
    print("v81 tests: ALL PASS")
