"""Divya setup driver (R48): background browser for one-tap setup.

Runs on the GitHub runner (free, public repo) with Playwright headless
Chromium. No browser ever opens on the user's screen. Drives one provider
signup + API-key flow (or the whole chain groq -> openrouter -> gemini ->
cloudflare when PROVIDER=chain), posts progress to the Worker (the chat
mini-box reads it), and posts each created key back (never printed, never
logged).

Provider chain: the Worker normally dispatches one provider per run and
advances on progress state "done". This runner ALSO supports running the
whole chain in one invocation (PROVIDER=chain): if one provider's flow
breaks, it is logged, marked failed, and the runner MOVES ON to the next
provider — one provider never aborts the whole setup. Each provider gets
at most 2 tries.

Captcha: audio challenge is transcribed on-device (faster-whisper, tiny
model) — audio-first, always. An image challenge WITH an audio alternative
is solved the same way. Only when a challenge has NO audio alternative does
the job pause for Take Control (status "paused-captcha", resumable via
setup/continue). Never a third-party captcha service, never silent.

Pauses: only email verification ("paused-email") and SMS code
("paused-sms") pause for the user — plus the pre-existing last-resort
pauses "paused-captcha" (image challenge, no audio alternative) and
"paused-signin" (Gemini Google sign-in, which the headless browser cannot
do alone). Every pause waits on the existing poll mechanism (bounded,
30 min) and resumes on setup/continue.

Cloudflare flow: creates the Cloudflare account (email signup; signs in
instead if the account already exists), creates an API token with Workers
deploy permissions from the dashboard ("Edit Cloudflare Workers"
template), then deploys the user's own Worker (cfworker/divya.js from
this repo) via the raw Cloudflare API and enables its workers.dev
subdomain. No wrangler needed — httpx only. If a dashboard step cannot
be automated (layout changed), the flow logs the exact step that broke
and returns a clear error — never hangs, never crashes the chain.

Results: after each provider, the runner POSTs
{WORKER}/api/setup/runner/result with {provider, status, key?, error?,
account_id?} (status: done/failed/stopped) AND keeps the legacy posts the
current Worker already accepts: progress to /api/setup/runner/progress
(payload carries both the legacy {state, step, note, url} fields and the
new {provider, step, status, message} fields) and the verified key to
/api/setup/runner/key. Progress/reporting failures are best-effort: they
are logged and the setup continues. Keys are tested with one cheap API
call before they are posted anywhere.
"""
import os, sys, time, json, re
import httpx
from playwright.sync_api import sync_playwright

WORKER = os.environ["WORKER_URL"].rstrip("/")
KEY = os.environ["RUNNER_KEY"]
JOB = os.environ["JOB"]
PROVIDER = os.environ["PROVIDER"]
H = {"x-runner-key": KEY}

CHAIN_ORDER = ["groq", "openrouter", "gemini", "cloudflare"]
MAX_TRIES = 2
CURRENT_PROVIDER = None

EMAIL_PAUSE_MSG = "Nee email lo vachina link ni okkasari tap cheyu, migilina anni nene chestha"
SMS_PAUSE_MSG = "Nee phone ki vachina SMS code ni app lo enter chesi Continue nokku — migilina anni nene chestha."
CAPTCHA_PAUSE_MSG = "Image captcha — Take Control tho nuvve okka step cheyyi, tarvatha Continue nokku."
GOOGLE_PAUSE_MSG = "Google sign-in — Take Control tho nuvve sign in cheyyi, tarvatha Continue nokku."

CF_API = "https://api.cloudflare.com/client/v4"
CF_SCRIPT_NAME = "divya"


def _pause_status(step):
    if step in ("verify-email", "email"):
        return "paused-email"
    if step == "captcha":
        return "paused-captcha"
    if step == "sms":
        return "paused-sms"
    if step == "google-signin":
        return "paused-signin"
    return "paused"


def progress(state, step="", note="", url="", status=None):
    """POST progress to the Worker (best-effort: never fails the setup).

    Payload carries BOTH shapes: the legacy {state, step, note, url} the
    current Worker stores in KV, and the new {provider, step, status,
    message} the setup/status endpoint reads. `status` defaults from
    state+step (paused-email / paused-captcha / paused-sms / ...).
    """
    st = status or (state if state != "paused" else _pause_status(step))
    payload = {
        "provider": CURRENT_PROVIDER or PROVIDER,
        "step": step, "status": st, "message": note,
        "state": state, "note": note, "url": url,
    }
    try:
        httpx.post(f"{WORKER}/api/setup/runner/progress", params={"job": JOB},
                   json=payload, headers=H, timeout=20)
    except Exception as e:
        print("progress failed:", e)


def report_result(provider, status, key=None, error=None, extra=None):
    """POST the provider outcome to the Worker setup/result endpoint.

    Shape: {provider, status, key?, error?, ...extra} with status one of
    done/failed/stopped. Best-effort: a failed POST is logged and the
    setup continues. The key value is never printed or logged.
    """
    payload = {"provider": provider, "status": status}
    if key:
        payload["key"] = key
    if error:
        payload["error"] = error
    if extra:
        payload.update(extra)
    try:
        httpx.post(f"{WORKER}/api/setup/runner/result", params={"job": JOB},
                   json=payload, headers=H, timeout=20)
        return True
    except Exception as e:
        print("result report failed:", e)
        return False


def get_job():
    # v24: a failed job fetch must be LOUD, not a silent "no job record".
    # (The one-tap run 42813523727 exited 0 in ~6s having done nothing.)
    try:
        r = httpx.get(f"{WORKER}/api/setup/runner/job", params={"job": JOB}, headers=H, timeout=20)
    except Exception as e:
        print(f"SETUP FAIL: get_job request failed: {e}", flush=True)
        raise SystemExit(1)
    if r.status_code != 200:
        print(f"SETUP FAIL: get_job HTTP {r.status_code}: {r.text[:300]}", flush=True)
        raise SystemExit(1)
    try:
        j = r.json().get("job", {})
    except Exception:
        print(f"SETUP FAIL: get_job bad JSON: {r.text[:300]}", flush=True)
        raise SystemExit(1)
    if not j or not j.get("provider"):
        print(f"SETUP FAIL: no job record for {JOB} (provider missing)", flush=True)
        raise SystemExit(1)
    return j


def check_stop():
    """True if the user stopped the job. Waits while paused (up to 30 min)."""
    deadline = time.time() + 1800
    while True:
        j = get_job()
        st = j.get("state", "")
        if st == "stopped":
            return True
        if st == "paused":
            time.sleep(15)
            if time.time() > deadline:
                return True
            continue
        return False


def wait_pause():
    """Block until the job is running again (user tapped Continue) or stopped."""
    return check_stop()


def solve_audio_captcha(page):
    """Try the audio challenge: download the audio, transcribe on-device."""
    try:
        # Open the audio challenge (reCAPTCHA / hCaptcha audio button).
        for frame in page.frames:
            try:
                btn = frame.locator("button#recaptcha-audio-button, button[title*='audio' i], button[aria-label*='audio' i]").first
                if btn.count():
                    btn.click(timeout=5000)
                    break
            except Exception:
                pass
        time.sleep(2)
        audio_url = None
        for frame in page.frames:
            try:
                a = frame.locator("audio source, audio").first
                if a.count():
                    audio_url = a.get_attribute("src")
                    if audio_url:
                        break
            except Exception:
                pass
        if not audio_url:
            return False
        import urllib.request
        data = urllib.request.urlopen(audio_url, timeout=30).read()
        open("/tmp/captcha.mp3", "wb").write(data)
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segs, _ = model.transcribe("/tmp/captcha.mp3")
        text = "".join(s.text for s in segs).strip()
        digits = re.sub(r"[^0-9]", "", text)
        if len(digits) < 3:
            return False
        for frame in page.frames:
            try:
                inp = frame.locator("input#audio-response, input[name*='audio' i]").first
                if inp.count():
                    inp.fill(digits)
                    frame.locator("button#recaptcha-verify-button").first.click(timeout=5000)
                    time.sleep(2)
                    return True
            except Exception:
                pass
        return False
    except Exception as e:
        print("audio captcha failed:", e)
        return False


def _has_audio_alternative(page):
    """True if an audio-challenge button exists anywhere (incl. iframes)."""
    try:
        if page.locator("button#recaptcha-audio-button, button[title*='audio' i], button[aria-label*='audio' i]").count():
            return True
        for frame in page.frames:
            try:
                if frame.locator("button#recaptcha-audio-button, button[title*='audio' i], button[aria-label*='audio' i]").count():
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def maybe_captcha(page):
    """If a captcha is showing, try to solve it with the user's one-allow
    consent. Audio-first, always; if an audio alternative exists, use it
    (one retry). Only a challenge with NO audio alternative pauses for
    Take Control. Returns True when the page is clear (or was solved)."""
    try:
        has = page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[title*='captcha' i]").count() > 0
        if not has:
            return True
        progress("running", "captcha", "Captcha vachindhi — ne permission tho solve chesthunna.", page.url)
        if solve_audio_captcha(page):
            time.sleep(2)
            return True
        # Audio solve failed but an audio alternative is present — retry once.
        if _has_audio_alternative(page):
            progress("running", "captcha", "Audio captcha malli try chesthunna.", page.url)
            if solve_audio_captcha(page):
                time.sleep(2)
                return True
        # Image challenge with no working audio alternative: last resort pause.
        progress("paused", "captcha", CAPTCHA_PAUSE_MSG, page.url)
        if wait_pause():
            return False
        return True
    except Exception:
        return True


def maybe_sms(page, job):
    """If the page asks for an SMS/phone verification code, pause for the
    user (status "paused-sms") and fill the code from the job record on
    resume. Returns the code string ("" if resumed without one), None if
    no SMS prompt is showing, or False if the user stopped the job."""
    try:
        asked = (
            page.locator("input[name*='sms' i], input[name*='otp' i], input[name*='verification-code' i], input[inputmode='numeric']").count() > 0
            or page.locator("text=enter the code, text=verification code, text=SMS code, text=phone verification").count() > 0
        )
        if not asked:
            return None
        progress("paused", "sms", SMS_PAUSE_MSG, page.url)
        if wait_pause():
            return False
        j = get_job()
        code = str(j.get("sms_code") or j.get("code") or "").strip()
        if code:
            fill(page, ["input[name*='sms' i]", "input[name*='otp' i]", "input[name*='verification-code' i]", "input[inputmode='numeric']"], code)
            click(page, ["button:has-text('Verify')", "button:has-text('Continue')", "button[type='submit']"])
            page.wait_for_timeout(3000)
        return code
    except Exception:
        return None


def fill(page, selectors, value, timeout=8000):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.fill(value, timeout=timeout)
                return True
        except Exception:
            pass
    return False


def click(page, selectors, timeout=8000):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count():
                loc.click(timeout=timeout)
                return True
        except Exception:
            pass
    return False


def extract_key(page, patterns):
    """Find an API key on the page (shown after creation) or in page text."""
    try:
        body = page.content()
        for pat in patterns:
            m = re.search(pat, body)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def _page_says(page, needles):
    """True if the page body text or URL contains any of the needles."""
    try:
        txt = page.inner_text("body").lower()
    except Exception:
        txt = ""
    try:
        url = page.url.lower()
    except Exception:
        url = ""
    return any(n.lower() in txt or n.lower() in url for n in needles)


def _ok(key=None, extra=None):
    return {"status": "done", "error": None, "key": key, "extra": extra or {}}


def _fail(error, key=None, extra=None):
    return {"status": "failed", "error": error, "key": key, "extra": extra or {}}


def _stopped():
    return {"status": "stopped", "error": None, "key": None, "extra": {}}


# ---------- Cloudflare API (raw API via httpx — no wrangler needed) ----------

def cf_api(token, method, path, **kw):
    """One Cloudflare API call. Returns the parsed JSON dict or None on
    network/parse failure. The token value is never printed or logged."""
    try:
        headers = dict(kw.pop("headers", {}) or {})
        headers["Authorization"] = "Bearer " + token
        r = httpx.request(method, CF_API + path, headers=headers, timeout=30, **kw)
        return r.json()
    except Exception as e:
        print(f"cloudflare api {method} {path} failed:", e)
        return None


def cf_verify_token(token):
    j = cf_api(token, "GET", "/user/tokens/verify")
    return bool(j and j.get("success") and (j.get("result") or {}).get("status") == "active")


def cf_get_account_id(token):
    j = cf_api(token, "GET", "/accounts?per_page=1")
    try:
        res = (j or {}).get("result") or []
        if res and res[0].get("id"):
            return res[0]["id"]
    except Exception:
        pass
    return None


def cf_deploy_worker(token, account_id, script):
    """PUT the Worker script, then enable its workers.dev subdomain.
    Returns (ok, error)."""
    try:
        r = httpx.request("PUT", f"{CF_API}/accounts/{account_id}/workers/scripts/{CF_SCRIPT_NAME}",
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/javascript"},
                          content=script.encode("utf-8"), timeout=60)
        j = r.json()
    except Exception as e:
        return False, f"deploy request failed: {e}"
    if not (j or {}).get("success"):
        errs = ((j or {}).get("errors") or [{}])
        msg = "; ".join(str(e.get("message", e)) for e in errs)[:300]
        return False, f"Worker script upload failed: {msg or 'unknown error'}"
    try:
        r2 = httpx.request("PATCH", f"{CF_API}/accounts/{account_id}/workers/scripts/{CF_SCRIPT_NAME}/subdomain",
                           headers={"Authorization": "Bearer " + token,
                                    "Content-Type": "application/json"},
                           json={"enabled": True}, timeout=30)
        j2 = r2.json()
    except Exception as e:
        return False, f"workers.dev subdomain enable failed: {e}"
    if not (j2 or {}).get("success"):
        return False, "Worker script uploaded but workers.dev subdomain enable failed"
    return True, ""


def read_worker_script():
    """The divya.js Worker source from this repo (checked out on the runner)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cfworker", "divya.js")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print("read_worker_script failed:", e)
        return None


# ---------- key testing + posting (single place; never logs a key) ----------

def test_key(provider, key):
    """One cheap API call to verify a freshly created key. Never logs it."""
    try:
        if provider == "groq":
            r = httpx.get("https://api.groq.com/openai/v1/models",
                          headers={"Authorization": "Bearer " + key}, timeout=20)
            return r.status_code == 200
        if provider == "openrouter":
            r = httpx.get("https://openrouter.ai/api/v1/models",
                          headers={"Authorization": "Bearer " + key}, timeout=20)
            return r.status_code == 200
        if provider == "gemini":
            r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                          params={"key": key}, timeout=20)
            return r.status_code == 200
        if provider == "cloudflare":
            return cf_verify_token(key)
    except Exception as e:
        print(f"key test failed for {provider}:", e)
    return False


def post_key_legacy(provider, key):
    """POST the verified key to the legacy /api/setup/runner/key endpoint
    (job-keyed; the current Worker stores it as the user's own key)."""
    try:
        r = httpx.post(f"{WORKER}/api/setup/runner/key", params={"job": JOB},
                       json={"key": key}, headers=H, timeout=20)
        return r.status_code == 200
    except Exception as e:
        print("key post failed:", e)
        return False


def submit_provider_result(provider, name, result):
    """Terminal handling for one provider: test its key (if any), post the
    verified key via the legacy endpoint, report {provider, status, key?,
    error?, ...} to setup/result, and emit the terminal progress event
    (the Worker advances the chain on progress state "done")."""
    key = result.get("key")
    verified = False
    if key:
        progress("running", "api-key", "Key vachindhi — verify chesthunna.", "")
        verified = test_key(provider, key)
        if verified:
            post_key_legacy(provider, key)
        else:
            # Unverified key: the provider outcome is a failure, and the
            # key is stored nowhere (neither legacy nor result endpoint).
            err = (result.get("error") or "") + " (key verification failed — key store cheyyaledu)"
            result = dict(result, status="failed", error=err.strip(), key=None)
            key = None
    report_result(provider, result["status"],
                  key=key if verified else None,
                  error=result.get("error"), extra=result.get("extra") or None)
    if result["status"] == "done":
        progress("done", "done", f"{name} ready — app lo save ayyindhi.", "")
    elif result["status"] == "failed":
        progress("failed", "error", result.get("error") or "Setup aagipoyindhi — Take Control tho try cheyyi.", "")
    else:
        progress("stopped", "stopped", "Setup aapesaaru.", "")
    return result


# ---------- provider flows (each returns {"status","error","key","extra"}) ----------

def flow_email_signup(page, job, cfg):
    """Generic email-signup flow: signup page -> email+password -> verify
    (pause) -> keys page -> create key -> extract."""
    email, password = job["email"], job["pass"]
    progress("running", "signup", f"{cfg['name']} account create chesthunna.", cfg["url"])
    page.goto(cfg["url"], timeout=60000)
    page.wait_for_timeout(2500)
    if check_stop():
        return _stopped()
    maybe_captcha(page)
    if check_stop():
        return _stopped()
    ok = fill(page, ["input[type='email']", "input[name='email']", "input[placeholder*='email' i]"], email)
    ok = fill(page, ["input[type='password']", "input[name='password']"], password) and ok
    if not ok:
        return _fail("Signup form kanipinchaledu — site layout marindhi (step: signup form). Take Control tho try cheyyi.")
    click(page, ["button[type='submit']", "button:has-text('Sign up')", "button:has-text('Create account')", "button:has-text('Continue')"])
    page.wait_for_timeout(4000)
    maybe_captcha(page)
    if check_stop():
        return _stopped()
    sms = maybe_sms(page, job)
    if sms is False:
        return _stopped()
    # Email verification: Divya cannot open the user's mailbox yet (Gmail
    # connect pending) — pause and let the user tap the link + Continue.
    if _page_says(page, ["verify your email", "check your email", "verification"]):
        progress("paused", "verify-email", EMAIL_PAUSE_MSG, page.url)
        if wait_pause():
            return _stopped()
        page.wait_for_timeout(3000)
    if check_stop():
        return _stopped()
    progress("running", "api-key", "API key create chesthunna.", page.url)
    page.goto(cfg["keys_url"], timeout=60000)
    page.wait_for_timeout(2500)
    maybe_captcha(page)
    click(page, ["button:has-text('Create')", "button:has-text('New key')", "button:has-text('Generate')", "button:has-text('Create API key')", "button:has-text('Create key')"])
    page.wait_for_timeout(4000)
    key = extract_key(page, cfg["key_patterns"])
    if not key:
        # The key may be in a modal/input — look for a long token-like value.
        try:
            txt = page.inner_text("body")
            m = re.search(r"\b(sk-[A-Za-z0-9_\-]{20,}|gsk_[A-Za-z0-9]{20,})\b", txt)
            if m:
                key = m.group(1)
        except Exception:
            pass
    if key:
        return _ok(key=key)
    return _fail("Key kanipinchaledu — site layout marindhi (step: key creation). Take Control tho try cheyyi.")


def flow_google(page, job, cfg):
    """Google-OAuth provider (Gemini): the headless browser has no Google
    session, so pause at sign-in for Take Control, then resume and take the key."""
    progress("running", "signin", f"{cfg['name']} — Google sign-in kosam pause avthundhi.", cfg["url"])
    page.goto(cfg["url"], timeout=60000)
    page.wait_for_timeout(2500)
    click(page, ["button:has-text('Sign in')", "a:has-text('Sign in')", "button:has-text('Get started')"])
    page.wait_for_timeout(3000)
    progress("paused", "google-signin", GOOGLE_PAUSE_MSG, page.url)
    if wait_pause():
        return _stopped()
    page.wait_for_timeout(3000)
    if check_stop():
        return _stopped()
    progress("running", "api-key", "API key create chesthunna.", page.url)
    page.goto(cfg["keys_url"], timeout=60000)
    page.wait_for_timeout(2500)
    click(page, ["button:has-text('Create API key')", "button:has-text('Get API key')", "button:has-text('Create')"])
    page.wait_for_timeout(4000)
    key = extract_key(page, cfg["key_patterns"])
    if key:
        return _ok(key=key)
    return _fail("Key kanipinchaledu (step: key creation). Take Control tho try cheyyi.")


def flow_cloudflare(page, job, cfg):
    """Cloudflare (server) flow: create the account (or sign in if it
    already exists) -> create a Workers-deploy API token in the dashboard
    -> deploy the user's own Worker via the Cloudflare API -> enable
    workers.dev. Every dashboard step names itself in its failure so a
    layout change is diagnosable, never a silent hang."""
    email, password = job["email"], job["pass"]
    progress("running", "signup", "Cloudflare account create chesthunna.", cfg["url"])
    page.goto(cfg["url"], timeout=60000)
    page.wait_for_timeout(2500)
    if check_stop():
        return _stopped()
    maybe_captcha(page)
    if check_stop():
        return _stopped()
    ok = fill(page, ["input[type='email']", "input[name='email']", "input[placeholder*='email' i]"], email)
    ok = fill(page, ["input[type='password']", "input[name='password']"], password) and ok
    if not ok:
        return _fail("Cloudflare signup form kanipinchaledu — dashboard layout marindhi (step: signup form). Take Control tho try cheyyi.")
    click(page, ["button[type='submit']", "button:has-text('Sign up')", "button:has-text('Create account')", "button:has-text('Continue')"])
    page.wait_for_timeout(4000)
    maybe_captcha(page)
    if check_stop():
        return _stopped()
    # Idempotent: if the account already exists, sign in instead of signing up.
    if _page_says(page, ["already exists", "already have an account", "already registered"]):
        progress("running", "signin", "Cloudflare account already undhi — sign in chesthunna.", cfg["login_url"])
        page.goto(cfg["login_url"], timeout=60000)
        page.wait_for_timeout(2500)
        ok = fill(page, ["input[type='email']", "input[name='email']", "input[placeholder*='email' i]"], email)
        ok = fill(page, ["input[type='password']", "input[name='password']"], password) and ok
        if not ok:
            return _fail("Cloudflare login form kanipinchaledu — dashboard layout marindhi (step: login form). Take Control tho try cheyyi.")
        click(page, ["button[type='submit']", "button:has-text('Log in')", "button:has-text('Sign in')"])
        page.wait_for_timeout(4000)
        maybe_captcha(page)
        if check_stop():
            return _stopped()
    sms = maybe_sms(page, job)
    if sms is False:
        return _stopped()
    # Email verification pause (same as the other providers).
    if _page_says(page, ["verify your email", "check your email", "verification"]):
        progress("paused", "verify-email", EMAIL_PAUSE_MSG, page.url)
        if wait_pause():
            return _stopped()
        page.wait_for_timeout(3000)
    if check_stop():
        return _stopped()
    # (b) API token with Workers deploy permissions, via the dashboard.
    progress("running", "api-token", "Cloudflare API token create chesthunna.", cfg["keys_url"])
    page.goto(cfg["keys_url"], timeout=60000)
    page.wait_for_timeout(2500)
    maybe_captcha(page)
    if check_stop():
        return _stopped()
    if not click(page, ["button:has-text('Create Token')", "a:has-text('Create Token')"]):
        # The template list may already be showing — only fail if it is not.
        if not _page_says(page, ["Edit Cloudflare Workers"]):
            return _fail("Cloudflare dashboard step failed: 'Create Token' button kanipinchaledu — dashboard layout marindhi (step: API Tokens > Create Token). Take Control tho try cheyyi.")
    page.wait_for_timeout(2000)
    if not click(page, ["button:has-text('Edit Cloudflare Workers')", "a:has-text('Edit Cloudflare Workers')", "text=Edit Cloudflare Workers"]):
        return _fail("Cloudflare dashboard step failed: 'Edit Cloudflare Workers' template kanipinchaledu — dashboard layout marindhi (step: API Tokens > Create Token > template). Take Control tho try cheyyi.")
    page.wait_for_timeout(2000)
    if not click(page, ["button:has-text('Continue to summary')", "button:has-text('Continue')"]):
        # The template may open the editor directly — proceed if Create Token is there.
        if not page.locator("button:has-text('Create Token')").count():
            return _fail("Cloudflare dashboard step failed: 'Continue to summary' button kanipinchaledu — dashboard layout marindhi (step: token template > summary). Take Control tho try cheyyi.")
    page.wait_for_timeout(1500)
    if not click(page, ["button:has-text('Create Token')", "button[type='submit']"]):
        return _fail("Cloudflare dashboard step failed: final 'Create Token' button kanipinchaledu — dashboard layout marindhi (step: token summary > Create Token). Take Control tho try cheyyi.")
    page.wait_for_timeout(4000)
    token = extract_key(page, cfg["key_patterns"])
    if not token:
        return _fail("Cloudflare dashboard step failed: token kanipinchaledu after Create Token — dashboard layout marindhi (step: token created). Take Control tho try cheyyi.")
    # (c) Deploy the user's own Worker via the raw Cloudflare API.
    progress("running", "deploy", "Cloudflare token vachindhi — Worker deploy chesthunna.", "")
    if not cf_verify_token(token):
        return _fail("Cloudflare token verify avvaledu — token create ayyindhi kani verify kaledu. Malli setup run cheyyi (account already undhi kabatti sign in avthundhi).")
    account_id = cf_get_account_id(token)
    if not account_id:
        return _fail("Cloudflare account id dorakaledu — token save ayyindhi, deploy malli try cheyyali.", key=token)
    script = read_worker_script()
    if not script:
        return _fail("Worker deploy cheyyalekapoyanu: cfworker/divya.js repo lo dorakaledu — token save ayyindhi.", key=token, extra={"account_id": account_id})
    dep_ok, dep_err = cf_deploy_worker(token, account_id, script)
    if not dep_ok:
        # Token is good and stored — only the deploy failed, so a later
        # run can deploy without re-creating the account or token.
        return _fail(f"Cloudflare Worker deploy avvaledu: {dep_err} — token save ayyindhi.", key=token, extra={"account_id": account_id})
    return _ok(key=token, extra={"account_id": account_id})


FLOWS = {
    "groq": {"name": "Groq", "url": "https://console.groq.com/signup",
             "keys_url": "https://console.groq.com/keys", "flow": "email",
             "key_patterns": [r"(gsk_[A-Za-z0-9]{20,})"]},
    "openrouter": {"name": "OpenRouter", "url": "https://openrouter.ai/sign-up",
                   "keys_url": "https://openrouter.ai/keys", "flow": "email",
                   "key_patterns": [r"(sk-or-v1-[A-Za-z0-9\-]{20,})", r"(sk-or-[A-Za-z0-9\-]{20,})"]},
    "gemini": {"name": "Gemini", "url": "https://aistudio.google.com/",
               "keys_url": "https://aistudio.google.com/apikey", "flow": "google",
               "key_patterns": [r"(AIza[A-Za-z0-9_\-]{20,})"]},
    "cloudflare": {"name": "Cloudflare", "url": "https://dash.cloudflare.com/sign-up",
                   "login_url": "https://dash.cloudflare.com/login",
                   "keys_url": "https://dash.cloudflare.com/profile/api-tokens",
                   "flow": "cloudflare",
                   "key_patterns": [r"\b([A-Za-z0-9_\-]{40})\b"]},
}


def run_flow(page, job, cfg):
    """Run one provider's flow. Never raises: any exception becomes a
    failed result with the error text, so the chain can move on."""
    global CURRENT_PROVIDER
    flow = job.get("flow") or cfg.get("flow") or "email"
    try:
        if flow in ("cloudflare", "token"):
            return flow_cloudflare(page, job, cfg)
        if flow == "google":
            return flow_google(page, job, cfg)
        return flow_email_signup(page, job, cfg)
    except Exception as e:
        print(f"flow error for {cfg['name']}:", e)
        return _fail(f"{cfg['name']} flow aagipoyindhi: {e}. Take Control tho try cheyyi.")


def run_provider(browser, job, cfg, provider):
    """Run one provider with a bounded retry (max 2 tries). A failure is
    returned, never raised — the caller moves on to the next provider."""
    last = _fail(f"{cfg['name']} setup start avvaledu.")
    for attempt in range(1, MAX_TRIES + 1):
        if attempt > 1:
            progress("running", "retry", f"{cfg['name']} malli try chesthunna (attempt {attempt}/{MAX_TRIES}).", cfg["url"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        try:
            last = run_flow(page, job, cfg)
        except Exception as e:
            print(f"provider error for {cfg['name']}:", e)
            last = _fail(f"{cfg['name']} flow aagipoyindhi: {e}. Take Control tho try cheyyi.")
        finally:
            try:
                ctx.close()
            except Exception:
                pass
        if last["status"] in ("done", "stopped"):
            return last
        # "failed": retry once (bounded), then give up on THIS provider only.
    return last


def main():
    # v24: get_job() raises SystemExit(1) on any failure (loud + non-zero),
    # so a bad job fetch can never look like a successful run again.
    global CURRENT_PROVIDER
    job = get_job()
    if PROVIDER in ("chain", "all"):
        # Whole chain in one run: job["chain"] is the Worker's provider list.
        wanted = job.get("chain") or CHAIN_ORDER
        providers = [p for p in CHAIN_ORDER if p in wanted]
        if not providers:
            providers = list(CHAIN_ORDER)
    else:
        providers = [job.get("provider") or PROVIDER]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for pid in providers:
                cfg = FLOWS.get(pid)
                if not cfg:
                    print(f"SETUP FAIL: no flow for provider {pid}")
                    report_result(pid, "failed", error=f"Ee provider ki flow ledu: {pid}.")
                    progress("failed", "start", "Ee provider ki flow ledu.", "")
                    continue
                CURRENT_PROVIDER = pid
                progress("running", "start", f"{cfg['name']} setup start chesthunna — background lo.", cfg["url"])
                result = run_provider(browser, job, cfg, pid)
                submit_provider_result(pid, cfg["name"], result)
                if result["status"] == "stopped":
                    break
        finally:
            browser.close()


if __name__ == "__main__":
    main()
