"""Divya setup driver (R48): background browser for one-tap setup.

Runs on the GitHub runner (free, public repo) with Playwright headless
Chromium. No browser ever opens on the user's screen. Drives one provider
signup + API-key flow, posts progress to the Worker (the chat mini-box reads
it), and posts the extracted key back (never printed, never logged).

Captcha: audio challenge is transcribed on-device (faster-whisper, tiny
model). Image challenge has no vision here -> the job pauses and the chat box
offers Take Control (the user solves that one step by hand). Never a
third-party captcha service, never silent.
"""
import os, sys, time, json, re
import httpx
from playwright.sync_api import sync_playwright

WORKER = os.environ["WORKER_URL"].rstrip("/")
KEY = os.environ["RUNNER_KEY"]
JOB = os.environ["JOB"]
PROVIDER = os.environ["PROVIDER"]
H = {"x-runner-key": KEY}


def progress(state, step="", note="", url=""):
    try:
        httpx.post(f"{WORKER}/api/setup/runner/progress", params={"job": JOB},
                   json={"state": state, "step": step, "note": note, "url": url},
                   headers=H, timeout=20)
    except Exception as e:
        print("progress failed:", e)


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


def maybe_captcha(page):
    """If a captcha is showing, try to solve it with the user's one-allow
    consent. Returns True when the page is clear (or was solved)."""
    try:
        has = page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[title*='captcha' i]").count() > 0
        if not has:
            return True
        progress("running", "captcha", "Captcha vachindhi — ne permission tho solve chesthunna.", page.url)
        if solve_audio_captcha(page):
            time.sleep(2)
            return True
        # Image challenge: no vision here -> pause for Take Control.
        progress("paused", "captcha", "Image captcha — Take Control tho nuvve okka step cheyyi, tarvatha Continue nokku.", page.url)
        if wait_pause():
            return False
        return True
    except Exception:
        return True


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


def flow_email_signup(page, job, cfg):
    """Generic email-signup flow: signup page -> email+password -> verify
    (pause) -> keys page -> create key -> extract."""
    email, password = job["email"], job["pass"]
    progress("running", "signup", f"{cfg['name']} account create chesthunna.", cfg["url"])
    page.goto(cfg["url"], timeout=60000)
    page.wait_for_timeout(2500)
    if check_stop():
        return
    maybe_captcha(page)
    if check_stop():
        return
    ok = fill(page, ["input[type='email']", "input[name='email']", "input[placeholder*='email' i]"], email)
    ok = fill(page, ["input[type='password']", "input[name='password']"], password) and ok
    if not ok:
        progress("failed", "signup", "Signup form kanipinchaledu — site layout marindhi. Take Control tho try cheyyi.", page.url)
        return
    click(page, ["button[type='submit']", "button:has-text('Sign up')", "button:has-text('Create account')", "button:has-text('Continue')"])
    page.wait_for_timeout(4000)
    maybe_captcha(page)
    if check_stop():
        return
    # Email verification: Divya cannot open the user's mailbox yet (Gmail
    # connect pending) — pause and let the user tap the link + Continue.
    if "verify" in page.url.lower() or page.locator("text=verify your email, text=check your email, text=verification").count():
        progress("paused", "verify-email", "Verification mail pampincha — nee email lo link nokku, tarvatha Continue nokku.", page.url)
        if wait_pause():
            return
        page.wait_for_timeout(3000)
    if check_stop():
        return
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
        httpx.post(f"{WORKER}/api/setup/runner/key", params={"job": JOB}, json={"key": key}, headers=H, timeout=20)
        progress("done", "done", f"{cfg['name']} API key ready — app lo save ayyindhi.", page.url)
    else:
        progress("failed", "api-key", "Key kanipinchaledu — site layout marindhi. Take Control tho try cheyyi.", page.url)


def flow_google(page, job, cfg):
    """Google-OAuth provider (Gemini): the headless browser has no Google
    session, so pause at sign-in for Take Control, then resume and take the key."""
    progress("running", "signin", f"{cfg['name']} — Google sign-in kosam pause avthundhi.", cfg["url"])
    page.goto(cfg["url"], timeout=60000)
    page.wait_for_timeout(2500)
    click(page, ["button:has-text('Sign in')", "a:has-text('Sign in')", "button:has-text('Get started')"])
    page.wait_for_timeout(3000)
    progress("paused", "google-signin", "Google sign-in — Take Control tho nuvve sign in cheyyi, tarvatha Continue nokku.", page.url)
    if wait_pause():
        return
    page.wait_for_timeout(3000)
    if check_stop():
        return
    progress("running", "api-key", "API key create chesthunna.", page.url)
    page.goto(cfg["keys_url"], timeout=60000)
    page.wait_for_timeout(2500)
    click(page, ["button:has-text('Create API key')", "button:has-text('Get API key')", "button:has-text('Create')"])
    page.wait_for_timeout(4000)
    key = extract_key(page, cfg["key_patterns"])
    if key:
        httpx.post(f"{WORKER}/api/setup/runner/key", params={"job": JOB}, json={"key": key}, headers=H, timeout=20)
        progress("done", "done", f"{cfg['name']} API key ready — app lo save ayyindhi.", page.url)
    else:
        progress("failed", "api-key", "Key kanipinchaledu — Take Control tho try cheyyi.", page.url)


FLOWS = {
    "groq": {"name": "Groq", "url": "https://console.groq.com/signup",
             "keys_url": "https://console.groq.com/keys",
             "key_patterns": [r"gsk_([A-Za-z0-9]{20,})"]},
    "openrouter": {"name": "OpenRouter", "url": "https://openrouter.ai/sign-up",
                   "keys_url": "https://openrouter.ai/keys",
                   "key_patterns": [r"sk-or-v1-([A-Za-z0-9\-]{20,})", r"sk-or-([A-Za-z0-9\-]{20,})"]},
    "gemini": {"name": "Gemini", "url": "https://aistudio.google.com/",
               "keys_url": "https://aistudio.google.com/apikey",
               "key_patterns": [r"AIza([A-Za-z0-9_\-]{20,})"]},
}


def main():
    # v24: get_job() raises SystemExit(1) on any failure (loud + non-zero),
    # so a bad job fetch can never look like a successful run again.
    job = get_job()
    cfg = FLOWS.get(job["provider"])
    if not cfg:
        progress("failed", "start", "Ee provider ki flow ledu.", "")
        return
    progress("running", "start", f"{cfg['name']} setup start chesthunna — background lo.", cfg["url"])
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        try:
            if job.get("flow") == "google":
                flow_google(page, job, cfg)
            else:
                flow_email_signup(page, job, cfg)
        except Exception as e:
            print("setup failed:", e)
            progress("failed", "error", "Setup aagipoyindhi — Take Control tho try cheyyi.", page.url if page else "")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
