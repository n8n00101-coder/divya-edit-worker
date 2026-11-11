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

v39 (setup-flow fix, 2026-11-11 — the live test proved the Groq step
stalls silently): Groq's console auth is a JS-rendered combined
"Create Account or Login" page (console.groq.com/signup and /login serve
the same shell; the form renders client-side) offering Google / GitHub /
SSO / email. The runner must therefore NEVER fill email+password blindly:
it waits for the rendered auth form, detects which mode the page is in
(email+password / email-first / SSO-only / login), and — when the page
needs the user's own sign-in — posts a paused-signin progress WITH the
sign-in URL so the app surfaces "sign in here, then tap Continue"
instead of "Setup running…" forever. Every pause re-posts a heartbeat
while waiting (so the Worker's staleness watchdog can tell "waiting on
the user" from "runner dead"), and every progress post carries the pause
`reason` the Worker stores.
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
# v39 C7: Groq (Stytch) sends a MAGIC LINK, not a password step. The link
# is single-use: the user must NOT tap it themselves, or the runner's copy
# is dead. The runner opens the link (supplied via setup/continue) in its
# own browser, where the session must land.
VERIFY_NEEDLES = ["check your email", "email was sent", "verify your email", "verification link", "confirm your email", "sent you an email"]


def MAGIC_LINK_PAUSE_MSG(name):
    return (f"{name} verification link nee email ki vachindhi — link ni nuvvu tap cheyyaku, "
            f"Continue nokku, Divya ne link open chesi sign in avthundhi.")

def SIGNIN_PAUSE_MSG(name):
    # v39: the one plain line for a provider whose auth page needs the
    # USER's own sign-in (Groq SSO chooser / existing account). The app
    # shows this next to an "Open in browser" button for the sign-in URL.
    return f"{name} sign-in kavali — browser lo open chesi sign in cheyu, tarvatha Continue nokku, migilina anni nene chestha."

# v39: last progress payload, re-posted as a heartbeat while the runner
# waits on a pause — so the Worker's staleness watchdog sees a live
# runner (fresh upd) and never mistakes "waiting on the user" for dead.
LAST_PROGRESS = {"state": "running", "step": "", "note": "", "url": "", "reason": None}

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


def _pause_reason(step):
    """Pause reason for a step name (email/sms/captcha/signin), or None."""
    if step in ("verify-email", "email"):
        return "email"
    if step == "captcha":
        return "captcha"
    if step == "sms":
        return "sms"
    if step in ("google-signin", "signin"):
        return "signin"
    return None


def progress(state, step="", note="", url="", status=None, reason=None):
    """POST progress to the Worker (best-effort: never fails the setup).

    Payload carries BOTH shapes: the legacy {state, step, note, url} the
    current Worker stores in KV, and the new {provider, step, status,
    message} the setup/status endpoint reads. `status` defaults from
    state+step (paused-email / paused-captcha / paused-sms / ...).
    v39: `reason` is sent explicitly on pauses (email/sms/captcha/signin)
    — the Worker stores it as pauseReason, so the app shows the right
    user step instead of defaulting every pause to the email line.
    """
    st = status or (state if state != "paused" else _pause_status(step))
    rsn = reason or (st[len("paused-"):] if st.startswith("paused-") else _pause_reason(step))
    payload = {
        "provider": CURRENT_PROVIDER or PROVIDER,
        "step": step, "status": st, "message": note,
        "state": state, "note": note, "url": url,
    }
    if rsn:
        payload["reason"] = rsn
    LAST_PROGRESS.update({"state": state, "step": step, "note": note, "url": url, "reason": rsn})
    try:
        httpx.post(f"{WORKER}/api/setup/runner/progress", params={"job": JOB},
                   json=payload, headers=H, timeout=20)
    except Exception as e:
        print("progress failed:", e)


def heartbeat():
    """Re-post the last progress event (best-effort). Called while the
    runner waits on a user pause, so the Worker sees a live runner and
    its staleness watchdog does not mark a waiting run as dead."""
    try:
        httpx.post(f"{WORKER}/api/setup/runner/progress", params={"job": JOB},
                   json={"provider": CURRENT_PROVIDER or PROVIDER,
                         "step": LAST_PROGRESS["step"], "status": LAST_PROGRESS["state"] if LAST_PROGRESS["state"] != "paused" else _pause_status(LAST_PROGRESS["step"]),
                         "message": LAST_PROGRESS["note"], "state": LAST_PROGRESS["state"],
                         "note": LAST_PROGRESS["note"], "url": LAST_PROGRESS["url"],
                         "reason": LAST_PROGRESS["reason"]},
                   headers=H, timeout=20)
    except Exception:
        pass


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
    """True if the user stopped the job. Waits while paused (up to 30 min).

    v39: while paused, re-posts the last progress as a heartbeat (every
    poll, ~15s) so the Worker sees a LIVE runner waiting on the user —
    without it the Worker's staleness watchdog cannot tell a waiting run
    from a dead one, and the app would show "Setup running…" forever.
    """
    deadline = time.time() + 1800
    while True:
        j = get_job()
        st = j.get("state", "")
        if st == "stopped":
            return True
        if st == "paused":
            heartbeat()
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
        # v39: the first Whisper model download can take minutes on a cold
        # runner — say so, or the app shows a frozen "running" meanwhile.
        progress("running", "captcha", "Audio captcha transcribe chesthunna.", page.url)
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
    Take Control. Returns True when the page is clear (or was solved).
    v39 C7d: a provider's security iframe merely EXISTING (Stripe's
    invisible hCaptcha, always on the page) is not a challenge — only act
    when a captcha iframe is actually VISIBLE, or challenge text shows."""
    try:
        vis = False
        for sel in ("iframe[src*='recaptcha']", "iframe[src*='hcaptcha']", "iframe[title*='captcha' i]"):
            try:
                loc = page.locator(sel)
                for i in range(min(loc.count(), 4)):
                    if loc.nth(i).is_visible():
                        vis = True
                        break
                if vis:
                    break
            except Exception:
                pass
        if not vis:
            try:
                vis = page.locator("text=verify you are human, text=I'm not a robot, text=select all images").first.is_visible()
            except Exception:
                vis = False
        if not vis:
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


def tick_consent(page):
    """Tick the form's consent checkbox (e.g. OpenRouter's 'I agree to the
    Terms' legalAccepted box) before submitting. A signup submit without
    it is silently rejected client-side. Only consent-named boxes, or any
    visible checkbox in the auth form — the one-tap allow covers creating
    the account, ToS acceptance included. Returns True if one was ticked."""
    try:
        for sel in ("input[name*='legal' i]", "input[name*='terms' i]", "input[name*='agree' i]",
                    "input[id*='legal' i]", "input[type='checkbox']"):
            loc = page.locator(sel)
            for i in range(min(loc.count(), 3)):
                el = loc.nth(i)
                try:
                    if el.is_visible() and not el.is_checked():
                        el.check(timeout=3000)
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


def fill(page, selectors, value, timeout=8000):
    """Fill the first VISIBLE match (same hidden-first-match trap as click)."""
    for sel in selectors:
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 5)):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        el.fill(value, timeout=timeout)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
    return False


def click_submit(page):
    """Click the AUTH FORM's own submit button — the form holding the email
    field. Text matching alone is unsafe ('Sign up' is also the header nav
    button; 'Continue' also matches Groq's 'Continue with Google'), and
    the first type=submit in DOM order may belong to another form (the
    header search). Falls back to the old text/type list if no form found."""
    try:
        form = page.locator("form:has(input[type='email']), form:has(input[name*='email' i]), form:has(input[type='password'])").first
        if form.count():
            for sel in ("button[type='submit']", "button:has-text('Continue')",
                        "button:has-text('Sign up')", "button:has-text('Create account')"):
                loc = form.locator(sel)
                for i in range(min(loc.count(), 3)):
                    el = loc.nth(i)
                    try:
                        if el.is_visible():
                            el.click(timeout=8000)
                            return True
                    except Exception:
                        continue
    except Exception:
        pass
    return click(page, ["button:has-text('Continue')", "button[type='submit']"])


def click(page, selectors, timeout=8000):
    """Click the first VISIBLE match (v39 C7e): .first may be a hidden
    button (OpenRouter has two type=submit buttons; the first in DOM order
    is not the form's Continue)."""
    for sel in selectors:
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 5)):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        el.click(timeout=timeout)
                        return True
                except Exception:
                    continue
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


def _submit_error(page):
    """Visible form/server error text after a submit, if any (e.g.
    OpenRouter's 'Temporary email services are not supported'). Lets the
    run fail with the provider's own words instead of a generic 'key not
    found' two steps later."""
    # Providers like Clerk render field errors in plain spans
    # with no error class/role — scan the visible body text for error
    # phrases and return the sentence around the match. render field errors in plain spans
    # with no error class/role — scan the visible body text for error
    # phrases and return the sentence around the match.
    try:
        txt = page.inner_text("body") or ""
        low = txt.lower()
        for phrase in ("not supported", "already exists", "already registered",
                       "invalid email", "invalid password", "incorrect password",
                       "something went wrong", "is required", "must be at least"):
            i = low.find(phrase)
            if i >= 0:
                start = max(0, txt.rfind(". ", 0, i) + 2 if txt.rfind(". ", 0, i) >= 0 else max(0, i - 60))
                return txt[start:i + 140].strip()[:200]
    except Exception:
        pass
    try:
        for sel in ("[role='alert']", "[class*='error' i]", "[class*='invalid' i]"):
            loc = page.locator(sel)
            for i in range(min(loc.count(), 3)):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        t = (el.inner_text() or "").strip()
                        if t:
                            return t[:200]
                except Exception:
                    continue
    except Exception:
        pass
    return ""


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

# ---------- v39: auth-page detection (the Groq stall fix) ----------
# Groq's console auth (and other providers' pages) is a JS-rendered
# combined "Create Account or Login" page: the form appears only after
# client-side render, and it may offer Google/GitHub/SSO buttons with NO
# password field at all. Filling email+password blindly after a fixed
# sleep either fails or — worse — sits silently on the login page. So the
# runner waits for the rendered form, detects its mode, and surfaces a
# sign-in pause (with the page URL) whenever the user must sign in.

_AUTH_EMAIL = ["input[type='email']", "input[name='email']", "input[autocomplete='email']", "input[placeholder*='email' i]"]
_AUTH_PASS = ["input[type='password']", "input[name='password']", "input[autocomplete='current-password']", "input[autocomplete='new-password']"]
_AUTH_SSO = ["button:has-text('Google')", "a:has-text('Google')", "button:has-text('GitHub')", "a:has-text('GitHub')", "button:has-text('SSO')", "a:has-text('SSO')"]


def _visible(page, selectors):
    """True if any of the selectors matches a VISIBLE element."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                return True
        except Exception:
            pass
    return False


def _any_visible(page, selectors):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                return sel
        except Exception:
            pass
    return None


def wait_for_auth_form(page, cfg, timeout_s=60):
    """Wait for the rendered auth form (up to timeout_s). Posts progress
    while waiting so the app shows movement, never a frozen "running".
    Returns a controls dict, or None if no auth control ever appeared."""
    progress("running", "signin-page", f"{cfg['name']} sign-in page load avthondhi…", page.url)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ctrls = {
            "email": _visible(page, _AUTH_EMAIL),
            "password": _visible(page, _AUTH_PASS),
            "sso": _visible(page, _AUTH_SSO),
        }
        if ctrls["email"] or ctrls["password"] or ctrls["sso"]:
            return ctrls
        if check_stop():
            return {"stopped": True}
        page.wait_for_timeout(2000)
    return None


def detect_auth_mode(ctrls):
    """email-password | email-first | sso-only | unknown."""
    if not ctrls or ctrls.get("stopped"):
        return "unknown"
    if ctrls.get("password") and ctrls.get("email"):
        return "email-password"
    if ctrls.get("email"):
        return "email-first"
    if ctrls.get("sso"):
        return "sso-only"
    return "unknown"


def goto(page, url, timeout=60000, tries=3):
    """Navigate with retries. The egress proxy intermittently stalls a fresh
    Chromium connection (net::ERR_TIMED_OUT on the HTML itself); a fresh
    navigation usually clears it. Returns True on success, False after all
    tries. Callers fail clearly on False (the step is named)."""
    for attempt in range(1, tries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return True
        except Exception as e:
            print(f"goto attempt {attempt}/{tries} failed for {url}: {e}")
            if attempt < tries:
                page.wait_for_timeout(2000)
    return False


def pause_for_email_verify(page, job, cfg):
    """Magic-link verification pause (v39 C7): Groq (Stytch) sends a link
    instead of a password step. Pause with reason=email so the app surfaces
    the verification step; on resume, open the link the user supplied via
    setup/continue (job.verify_link) in THIS browser — that is where the
    session must land — then verify the console is reachable signed-in.
    Returns True only when signed in; False when stopped or the sign-in
    did not complete (the caller fails clearly, never hangs)."""
    name = cfg["name"]
    progress("paused", "verify-email", MAGIC_LINK_PAUSE_MSG(name), page.url, reason="email")
    if wait_pause():
        return False
    page.wait_for_timeout(2000)
    j = get_job()
    link = str(j.get("verify_link") or j.get("verifyLink") or "").strip()
    if link.startswith("http"):
        progress("running", "verify-link", f"{name} verification link open chesthunna — sign in avthundhi.", link)
        try:
            goto(page, link)
        except Exception:
            pass
        # The link may redirect (Stytch discovery) — give it up to 30s to
        # leave the redirect host before checking the console.
        for _ in range(15):
            page.wait_for_timeout(2000)
            if "stytch.com" not in page.url:
                break
            if _page_says(page, ["dashboard", "api keys", "create api key", "log out", "sign out"]):
                break
    try:
        goto(page, cfg["keys_url"])
    except Exception:
        pass
    page.wait_for_timeout(3000)
    if _page_says(page, ["create an account or login", "continue with email", "continue with google"]):
        return False
    ctrls = wait_for_auth_form(page, cfg, timeout_s=15)
    if ctrls is None:
        return True  # no auth form any more — signed in
    return False


def pause_for_signin(page, cfg, note=None):
    """Surface the sign-in step: post paused-signin WITH the current page
    URL, then wait for the user to sign in + tap Continue. Returns True
    if the user resumed (runner should re-detect the page), False if the
    user stopped the job. Never hangs silently: wait_pause is bounded
    (30 min) and heartbeats while waiting."""
    progress("paused", "google-signin", note or SIGNIN_PAUSE_MSG(cfg["name"]), page.url, reason="signin")
    if wait_pause():
        return False
    page.wait_for_timeout(3000)
    return True


def try_login(page, job, cfg):
    """Sign in with the job's email+pass on the provider login page.

    Used when the account already exists (auto-provision of a replacement
    key reuses the sealed setup password, so this usually just works).
    Returns True when the auth form is gone afterwards (signed in), False
    when still on an auth page — the caller then surfaces the sign-in
    pause instead of looping or hanging."""
    login_url = cfg.get("login_url") or cfg["url"]
    if not goto(page, login_url):
        return False
    page.wait_for_timeout(2500)
    if check_stop():
        return False
    ctrls = wait_for_auth_form(page, cfg, timeout_s=30)
    if ctrls is None or ctrls.get("stopped"):
        return False
    if detect_auth_mode(ctrls) == "sso-only":
        return False
    ok = fill(page, _AUTH_EMAIL, job["email"])
    ok = fill(page, _AUTH_PASS, job["pass"]) and ok
    if not ok:
        return False
    click(page, ["button[type='submit']", "button:has-text('Log in')", "button:has-text('Sign in')", "button:has-text('Continue')"])
    page.wait_for_timeout(4000)
    maybe_captcha(page)
    if check_stop():
        return False
    if _page_says(page, ["dashboard", "api keys", "create api key", "log out", "sign out", "api key"]):
        return True
    ctrls2 = wait_for_auth_form(page, cfg, timeout_s=20)
    if ctrls2 is None:
        return True  # no auth form any more — signed in
    return False


def flow_email_signup(page, job, cfg):
    """Email-signup flow, v39: detect the rendered auth page first.

    signup page -> detect mode -> (email+password | email-first, then
    password | SSO-only: pause for the user's sign-in) -> verify (pause)
    -> keys page -> create key -> extract. Any page that never renders a
    usable form FAILS with the exact step named — never hangs."""
    email, password = job["email"], job["pass"]
    name = cfg["name"]
    progress("running", "signup", f"{name} account create chesthunna.", cfg["url"])
    if not goto(page, cfg["url"]):
        return _fail(f"{name} sign-in page load avvaledu — site open avvaledu (step: sign-in page, {cfg['url']}). Take Control tho try cheyyi.")
    page.wait_for_timeout(1500)
    if check_stop():
        return _stopped()
    maybe_captcha(page)
    if check_stop():
        return _stopped()
    ctrls = wait_for_auth_form(page, cfg, timeout_s=60)
    if ctrls is None:
        return _fail(f"{name} sign-in page load avvaledu — form kanipinchaledu (step: sign-in page, {cfg['url']}). Take Control tho try cheyyi.")
    if ctrls.get("stopped"):
        return _stopped()
    mode = detect_auth_mode(ctrls)
    if mode == "sso-only":
        # The page offers ONLY Google/GitHub/SSO — the runner has no
        # session to sign in with. Surface the step, do not fill blindly.
        progress("running", "signin", f"{name} — sign-in page lo Google/GitHub matrame undhi.", page.url)
        if not pause_for_signin(page, cfg):
            return _stopped()
        if check_stop():
            return _stopped()
        # After resume, re-detect: signed in (dashboard/keys reachable)
        # or still on the auth page (user did not finish signing in).
        ctrls = wait_for_auth_form(page, cfg, timeout_s=30)
        if ctrls is None or ctrls.get("stopped"):
            return _stopped() if (ctrls or {}).get("stopped") else _fail(f"{name} sign-in tarvatha page load avvaledu — sign in ayyindha check chesi malli try cheyyi (step: sign-in).")
        mode = detect_auth_mode(ctrls)
        if mode == "sso-only":
            return _fail(f"{name} sign-in complete avvaledu — inka sign-in page lone undhi. Browser lo open chesi sign in chesi malli setup run cheyyi (step: sign-in).")
        if mode == "unknown":
            # Not on an auth form any more — likely signed in. Continue
            # to key creation below.
            pass
    elif mode == "email-first":
        if not fill(page, _AUTH_EMAIL, email):
            return _fail(f"{name} signup form lo email field kanipinchaledu (step: signup form). Take Control tho try cheyyi.")
        click(page, ["button:has-text('Continue')", "button:has-text('Sign up')", "button:has-text('Create account')", "button[type='submit']"])
        page.wait_for_timeout(3000)
        maybe_captcha(page)
        if check_stop():
            return _stopped()
        # The password field appears after Continue — or SSO buttons do —
        # or the provider sent a MAGIC LINK instead (Groq/Stytch: the page
        # shows "Check your email" and no auth form at all). That screen
        # is a verification pause, never a failure.
        ctrls2 = wait_for_auth_form(page, cfg, timeout_s=30)
        if ctrls2 is None:
            if _page_says(page, VERIFY_NEEDLES):
                if pause_for_email_verify(page, job, cfg):
                    pass  # verified + signed in — fall through to key creation
                else:
                    return _fail(f"{name} sign-in complete avvaledu — verification link open chesi sign in ayyaka malli setup run cheyyi (step: email verification).", extra={"no_retry": True})
            else:
                return _fail(f"{name} — email tarvatha next step load avvaledu (step: signup form). Take Control tho try cheyyi.")
        if ctrls2.get("stopped"):
            return _stopped()
        mode2 = detect_auth_mode(ctrls2)
        if mode2 == "sso-only":
            if not pause_for_signin(page, cfg):
                return _stopped()
            if check_stop():
                return _stopped()
        elif mode2 in ("email-password", "email-first"):
            if not fill(page, _AUTH_PASS, password):
                return _fail(f"{name} signup form lo password field kanipinchaledu (step: signup form). Take Control tho try cheyyi.")
            tick_consent(page)
            click_submit(page)
            page.wait_for_timeout(4000)
        # mode2 == "unknown": no auth form any more — proceed to key creation.
    elif mode == "email-password":
        ok = fill(page, _AUTH_EMAIL, email)
        ok = fill(page, _AUTH_PASS, password) and ok
        if not ok:
            return _fail(f"{name} signup form kanipinchaledu — site layout marindhi (step: signup form). Take Control tho try cheyyi.")
        tick_consent(page)
        click_submit(page)
        page.wait_for_timeout(4000)
        maybe_captcha(page)
        if check_stop():
            return _stopped()
    # else mode == "unknown": the auth form vanished (already signed in,
    # or a redirect) — proceed; the steps below fail clearly if not.
    # A visible submit error (e.g. OpenRouter rejecting a temporary-email
    # domain) fails here with the provider's own words — never silently
    # proceed to key creation, where it would surface as a generic miss.
    # Give the server response a moment to render first (the error shows
    # ~5s after submit; the branch waited only ~4s).
    page.wait_for_timeout(2500)
    err = _submit_error(page)
    if err:
        return _fail(f"{cfg['name']} signup error: {err} (step: signup form).")
    # The account may already exist: the page says so instead of signing
    # up. First try signing in with the job's password (an auto-provision
    # run reuses the sealed setup password, so this usually just works).
    # Only if that fails does the runner surface the sign-in step.
    if _page_says(page, ["already exists", "already registered", "account already exists", "email already in use", "email is already registered", "an account with this email"]):
        progress("running", "signin", f"{name} account already undhi — sign in chesthunna.", cfg.get("login_url") or cfg["url"])
        if try_login(page, job, cfg):
            progress("running", "signin", f"{name} sign-in ayyindhi — key create chesthunna.", page.url)
        else:
            if check_stop():
                return _stopped()
            if not pause_for_signin(page, cfg, note=f"{name} account already undhi — browser lo open chesi sign in cheyu, tarvatha Continue nokku, migilina anni nene chestha."):
                return _stopped()
            if check_stop():
                return _stopped()
            # After the user signs in + Continue, verify we are actually in.
            ctrls3 = wait_for_auth_form(page, cfg, timeout_s=20)
            if ctrls3 and not ctrls3.get("stopped") and detect_auth_mode(ctrls3) != "unknown":
                return _fail(f"{name} sign-in complete avvaledu — inka sign-in page lone undhi. Browser lo open chesi sign in chesi malli setup run cheyyi (step: sign-in).")
    sms = maybe_sms(page, job)
    if sms is False:
        return _stopped()
    # Email verification: Divya cannot open the user's mailbox yet (Gmail
    # connect pending) — pause and let the user tap the link + Continue.
    # v39 C7: the magic-link resume opens the supplied link in this browser
    # (session must land here) and verifies the console before proceeding.
    if _page_says(page, VERIFY_NEEDLES):
        if not pause_for_email_verify(page, job, cfg):
            return _fail(f"{cfg['name']} sign-in complete avvaledu — verification link open chesi sign in ayyaka malli setup run cheyyi (step: email verification).", extra={"no_retry": True})
    if check_stop():
        return _stopped()
    progress("running", "api-key", "API key create chesthunna.", page.url)
    goto(page, cfg["keys_url"])
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
    if not goto(page, cfg["url"]):
        return _fail(f"{cfg['name']} page load avvaledu — site open avvaledu (step: sign-in page, {cfg['url']}).")
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
    goto(page, cfg["keys_url"])
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
    if not goto(page, cfg["url"]):
        return _fail("Cloudflare signup page load avvaledu — site open avvaledu (step: signup page).")
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
    click(page, ["button:has-text('Sign up')", "button:has-text('Create account')", "button:has-text('Continue')", "button[type='submit']"])
    page.wait_for_timeout(4000)
    maybe_captcha(page)
    if check_stop():
        return _stopped()
    # Idempotent: if the account already exists, sign in instead of signing up.
    if _page_says(page, ["already exists", "already registered", "account already exists", "email already in use", "email is already registered", "an account with this email"]):
        progress("running", "signin", "Cloudflare account already undhi — sign in chesthunna.", cfg["login_url"])
        goto(page, cfg["login_url"])
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
    # Email verification pause (same as the other providers, v39 C7).
    if _page_says(page, VERIFY_NEEDLES):
        if not pause_for_email_verify(page, job, cfg):
            return _fail(f"{cfg['name']} sign-in complete avvaledu — verification link open chesi sign in ayyaka malli setup run cheyyi (step: email verification).", extra={"no_retry": True})
    if check_stop():
        return _stopped()
    # (b) API token with Workers deploy permissions, via the dashboard.
    progress("running", "api-token", "Cloudflare API token create chesthunna.", cfg["keys_url"])
    goto(page, cfg["keys_url"])
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
             "login_url": "https://console.groq.com/login",
             "keys_url": "https://console.groq.com/keys", "flow": "email",
             "key_patterns": [r"(gsk_[A-Za-z0-9]{20,})"]},
    "openrouter": {"name": "OpenRouter", "url": "https://openrouter.ai/sign-up",
                   "login_url": "https://openrouter.ai/sign-in",
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
        # v39 C7: a verification-resume failure must NOT retry — retrying
        # re-submits the email, sends another magic link and pauses again.
        if (last.get("extra") or {}).get("no_retry"):
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
