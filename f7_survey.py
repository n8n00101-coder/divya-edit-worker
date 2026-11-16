#!/usr/bin/env python3
"""F7 Phase-1 survey: visit each candidate provider's signup page from
the ACTUAL runner environment (GitHub Actions, same as setup.py runs)
with a fresh ephemeral desktop Chromium and record, per provider:
  - final URL / title / load state
  - OAuth doors (Google / GitHub / Apple / SSO buttons or links)
  - form fields (email / password / name / phone / company)
  - captcha & anti-abuse signals (recaptcha / hcaptcha / turnstile /
    arkose / funcaptcha / datadome iframes or challenge text)
  - phone-verification and credit-card signals in visible text
  - a visible-text excerpt + full-page screenshot (survey-shots/)
NO form is filled and NO signup is submitted by this script — it is a
door survey only. Results land in survey.json next to this file.
"""
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

CANDIDATES = [
    ("resend", "https://resend.com/signup"),
    ("brevo", "https://app.brevo.com/account/register"),
    ("mailersend", "https://app.mailersend.com/register"),
    ("mailjet", "https://app.mailjet.com/signup"),
    ("smtp2go", "https://app.smtp2go.com/register"),
    ("elasticemail", "https://elasticemail.com/account#/create-account"),
    ("postmark", "https://account.postmarkapp.com/sign_up"),
    ("mailgun", "https://signup.mailgun.com/new/signup"),
    ("sendgrid", "https://signup.sendgrid.com/"),
]

CAPTCHA_RX = re.compile(
    r"recaptcha|hcaptcha|turnstile|arkose|funcaptcha|datadome|"
    r"are you (a )?human|verify you are|i'm not a robot|security check|"
    r"unusual traffic|automated", re.I)
PHONE_RX = re.compile(r"phone|mobile|sms|whatsapp", re.I)
CARD_RX = re.compile(r"credit card|payment method|billing", re.I)
OAUTH_RX = re.compile(r"google|github|apple|sso|single sign", re.I)


def probe(page, name, url):
    rec = {"provider": name, "url": url}
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        rec["http"] = resp.status if resp else None
    except Exception as e:
        rec["error"] = f"goto: {type(e).__name__}: {str(e)[:160]}"
    page.wait_for_timeout(6000)
    try:
        rec["final_url"] = page.url
        rec["title"] = page.title()
        data = page.evaluate("""() => {
          const vis = el => !!(el.offsetWidth || el.offsetHeight);
          const texts = [];
          document.querySelectorAll('button, a').forEach(el => {
            if (vis(el)) { const t = (el.innerText || el.textContent || '').trim();
              if (t && t.length <= 80) texts.push(t); }
          });
          const inputs = [];
          document.querySelectorAll('input, select').forEach(el => {
            inputs.push({type: el.type || el.tagName, name: el.name || '',
                         ph: el.placeholder || '', id: el.id || ''});
          });
          const frames = [];
          document.querySelectorAll('iframe').forEach(f => frames.push(f.src || ''));
          const body = (document.body && document.body.innerText) || '';
          return {texts: [...new Set(texts)].slice(0, 60), inputs: inputs.slice(0, 30),
                  frames, body: body.slice(0, 4000)};
        }""")
        body = data.get("body") or ""
        rec["oauth_buttons"] = [t for t in data["texts"] if OAUTH_RX.search(t)]
        rec["inputs"] = data["inputs"]
        frames = " ".join(data["frames"])
        rec["captcha_signals"] = sorted(set(
            m.group(0).lower() for m in CAPTCHA_RX.finditer(frames + " " + body)))
        rec["phone_signals"] = bool(PHONE_RX.search(
            json.dumps(data["inputs"]) + " " + body[:1500]))
        rec["card_signals"] = bool(CARD_RX.search(body[:2500]))
        rec["text_excerpt"] = re.sub(r"\s+", " ", body)[:1200]
        try:
            page.screenshot(path=f"survey-shots/{name}.png", full_page=True)
            rec["screenshot"] = f"survey-shots/{name}.png"
        except Exception as e:
            rec["screenshot_error"] = str(e)[:120]
    except Exception as e:
        rec["error"] = (rec.get("error") or "") + f" probe: {type(e).__name__}: {str(e)[:160]}"
    return rec


def main():
    import os
    os.makedirs("survey-shots", exist_ok=True)
    out = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "env": "github-actions-runner (f7survey.yml)", "results": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for name, url in CANDIDATES:
            ctx = browser.new_context(viewport={"width": 1280, "height": 800},
                                      user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
            page = ctx.new_page()
            rec = probe(page, name, url)
            out["results"].append(rec)
            print(f"== {name}: final={rec.get('final_url')} http={rec.get('http')} "
                  f"oauth={rec.get('oauth_buttons')} captcha={rec.get('captcha_signals')} "
                  f"phone={rec.get('phone_signals')} err={rec.get('error', '')}", flush=True)
            ctx.close()
        browser.close()
    with open("survey.json", "w") as f:
        json.dump(out, f, indent=1)
    print("survey.json written", flush=True)


if __name__ == "__main__":
    sys.exit(main())
