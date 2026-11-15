"""Round-4 X4 runner tests: fed_verify_link + wait_for_fed_link from setup.py.

setup.py is imported with its heavy deps stubbed the same way the repo's own
v-tests do it: only the pure helpers are exercised; get_job/heartbeat/time
are monkeypatched per test.
"""
import importlib.util
import sys
import types

# Stub optional heavy imports if the environment lacks them.
for mod in ("playwright", "playwright.sync_api"):
    if mod not in sys.modules:
        try:
            __import__(mod)
        except Exception:
            sys.modules[mod] = types.ModuleType(mod)

import os
os.environ.setdefault("WORKER_URL", "http://127.0.0.1:9")
os.environ.setdefault("RUNNER_KEY", "test")
os.environ.setdefault("JOB", "test-job")
os.environ.setdefault("PROVIDER", "groq")
spec = importlib.util.spec_from_file_location("setup_r4", "setup.py")
setup = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(setup)
except Exception as e:  # module-level side effects (env reads) — helpers may still exist
    print("module exec note:", e)

passed = failed = 0
def check(label, got, want):
    global passed, failed
    ok = got == want
    print(("PASS" if ok else "FAIL"), label, "" if ok else f"— got {got!r} want {want!r}")
    passed, failed = passed + ok, failed + (not ok)

LINK = "https://auth.stytch.com/v1/magic_links/authenticate?token=xyz"
check("snake_case link", setup.fed_verify_link({"verify_link": LINK}), LINK)
check("camelCase link", setup.fed_verify_link({"verifyLink": LINK}), LINK)
check("empty job", setup.fed_verify_link({}), "")
check("non-http rejected", setup.fed_verify_link({"verify_link": "javascript:alert(1)"}), "")
check("non-dict rejected", setup.fed_verify_link(None), "")

# wait_for_fed_link: link arrives on the 3rd poll
seq = iter([{"state": "paused"}, {"state": "paused"}, {"state": "paused", "verify_link": LINK}])
setup.get_job = lambda: next(seq)
setup.heartbeat = lambda: None
setup.time.sleep = lambda s: None
check("link on 3rd poll", setup.wait_for_fed_link(60, poll=0), LINK)

# wait_for_fed_link: job stopped -> ""
setup.get_job = lambda: {"state": "stopped"}
check("stopped -> ''", setup.wait_for_fed_link(60, poll=0), "")

# wait_for_fed_link: deadline passes with no link -> ""
import time as _time
real_time = _time.time
ticks = iter([0, 0, 100])  # start, mid-check, past deadline
setup.time.time = lambda: next(ticks, 200)
setup.get_job = lambda: {"state": "paused"}
check("deadline -> ''", setup.wait_for_fed_link(10, poll=0), "")
setup.time.time = real_time

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
