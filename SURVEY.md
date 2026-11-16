# F7 — Julie creates her own email-sending key: provider survey + live proof attempts

Mission (Ajju, 2026-11-16 19:52 IST): the `sendMailChannel()` key must be created
BY JULIE end-to-end — account creation → verification → API key → sealed → test
email arrives — with NO human step. This file is the evidence record: every
candidate, the route tried, and the exact wall or success point.

Method: (1) a door survey executed from the actual runner environment
(GitHub Actions, datacenter IPs — the same environment Julie's setup chains
run in), scratch repo run **43886004316**, evidence in
`survey-evidence/survey.json` + `survey-evidence/survey-shots/`; (2) full
live creation chains on real Julie setup jobs (branch
`feat/julie-f7-selfcreate`); (3) official-docs desk research. No captcha,
anti-abuse wall, or bot check was evaded anywhere — walls are recorded, not
defeated. No secret is printed anywhere in this record (presence/counts only).

## Live chain runs (the decisive evidence)

| Run | Job | Identity | Provider | Outcome |
|---|---|---|---|---|
| 43887401752 | `2a478acbaec7bee52564` | Divya Test (`u_c3a7…`) | Brevo | OAuth door: Google sign-in form (no session in sealed profile). Email path: register page loaded, then a **visible reCAPTCHA image challenge** → chain paused at `step=captcha` on `onboarding.brevo.com/account/register` (Worker status, pauseReason=captcha). Not evaded; run stopped by the agent to close it out. |
| 43889712897 | `7e3782ac3ab94875f93a` | Test account markk34200 (`u_1ae9…`) | Resend | Google door → sign-in form (no session). Email signup → **"Something went wrong while processing your request"** (anti-abuse refusal, reproduced). Login tail never advanced. Failed: sign-in incomplete. |
| 43891610814 | `7f1220b734946e18bf12` | Test account markk34200 | Resend | Google door → no session; **GitHub door → github.com/login form (no session)** — both doors now covered. Signup refused again. Login advanced to password, failed invalid → **password-reset submitted** for the chain email → no reset mail could be fed (this identity has no Gmail grant the Worker can read). Failed: password reset incomplete. |
| 43893050195 | `7d4babd3124030400043` | Divya Test (`u_c3a7…`) — the identity whose Google grant mailbox IS the chain email | Resend | Same door results (Google + GitHub: no session). Signup refused. Reset submitted 15:09:44Z; runner log: **"resend reset: no reset mail fed in 5 min"**. Worker feed reported `gmail.state = no-token` for this identity (see Finding F-FEED below). Failed: password reset incomplete. |
| 43891360694 (probe) | — | fresh context | Mailjet | Signup form filled successfully (first/last/email/password). **A visible reCAPTCHA iframe is present on the signup form from the runner** (`captcha_visible_after: true`). Probe limitation: the probe's submit-button selectors did not match Mailjet's button, so the submit itself was not executed; the wall classification rests on the visible captcha — the same signal that stopped Brevo's full flow. Evidence: `survey-evidence/probe2/`. |

## Per-provider survey table

| Provider | Signup doors (from the runner) | Captcha / anti-abuse from the runner | Verification needed | API key in dashboard | Free tier | Onboarding sender reach | Verdict |
|---|---|---|---|---|---|---|---|
| **Resend** | Email form + **"Log in with Google" + "Log in with GitHub"** (survey HTTP 200; both doors exercised live) | Email form: deterministic anti-abuse refusal "Something went wrong" (runs 6–7 in Nov 15 testing + reproduced twice 2026-11-16). hCaptcha signal on page | Email verification / fed-link reset supported by Julie's self-heal design | Yes — key dialog automated in the existing `flow_resend` | 3,000/mo, 100/day (desk) | `onboarding@resend.dev` sends **only to the account's own email**; arbitrary recipients need a verified domain (Ajju/Mark decision — do not invent a domain) | **WALLED**: OAuth doors need a Google/GitHub session the sealed profiles don't hold; email form refuses the datacenter runner; reset door blocked by Finding F-FEED |
| **Brevo** | Email form + **"Sign up with Google" + "Sign up with Apple"** (register 302 → onboarding.brevo.com, 200; "Free to use – no credit card required") | **Visible reCAPTCHA image challenge** on the register page (live run 43887401752) | Account-validation email — self-heal feedable in principle (VERIFY_PROVIDERS brevo entry added on this branch) | Yes — `flow_brevo` built on this branch (keys page → dialog → `xkeysib-` key) | 300/day (desk) | Sender = the account's validated address (production send-side already uses the project Gmail as Brevo sender); no own-domain requirement for the account's own validated sender | **WALLED** at the signup captcha; OAuth door also session-less |
| **MailerSend** | Form unreachable | **Cloudflare "Just a moment" bot wall, HTTP 403, cf-turnstile** (survey) | — | — | — | Desk: manual account approval + credit card required even for the Free plan | **WALLED** at page load (bot wall) + approval/card gates behind it |
| **Mailjet** | Email form only (first/last/email/password), **no OAuth** (survey) | **Visible reCAPTCHA on the signup form** (probe2, run 43891360694) | Email verification part of signup (desk) | Keys exist on the account; retrievable in dashboard (desk) | 6,000/mo, 200/day (desk) | Single verified sender address suffices (desk); new accounts may sit in Test Mode pending review (desk) | **WALLED** at the signup captcha (probe-level submit evidence — see run table) |
| **SMTP2GO** | Register URL redirects to marketing homepage; embedded form includes **phone field + verification-number inputs** (survey) | Phone verification at signup; desk: Gmail/Outlook/Yahoo addresses refused — an own-domain email is required, so the chain email itself is ineligible | Phone | — | 1,000/mo (desk) | Sender verification required | **WALLED**: phone verification + chain email ineligible |
| **Elastic Email** | Lands on a product picker, no direct form (survey) | — | Desk: a verified domain is required as the default sender before mailing | — | 3,000/mo (desk) | Blocked until a domain is verified | **WALLED** for a Gmail-based account (domain-first sending) |
| **Postmark** | Email form loads, no OAuth (survey); reCAPTCHA badge present | reCAPTCHA signal | Desk: **manual approval of every new account** (<24h weekdays); pre-approval sending only to own verified domains | Token available, sending gated by approval | 100/mo (desk) | Own verified domains only until approved | **WALLED** for an immediate zero-human proof (human approval review) |
| **Mailgun** | Signup form embeds **credit-card fields** (survey) + hCaptcha/reCAPTCHA signals | Desk: **phone verification mandatory** (mobile only, no VoIP) | Phone + email | — | Without a card: ≤5 Authorized Recipients (desk) | Sandbox/authorized recipients only without a card | **WALLED**: card fields + mandatory phone verification |
| **SendGrid** | Redirects to Twilio signup; "Sign up with Google" present (survey) | Desk: **phone verification mandatory** + captcha | Phone | — | **60-day trial only**, no permanent free tier (desk) | — | **WALLED**: mandatory phone verification; trial-only |

## Finding F-FEED — the Worker verification feed cannot use the legacy Google grant

The Resend password-reset door is the one route that got *past* the provider:
the runner submitted the reset and waited for Julie's own self-heal feed to
hand it the emailed link (the designed zero-human path). The feed answered
`no-gmail-token` for the Divya Test identity even though:

- a legacy grant record `tok:<n>:google` exists for that identity with
  `who` = the chain email's mailbox, scope including `gmail.readonly`, and a
  refresh token present (record written 2026-11-12; nominal 7-day refresh
  window runs to ~2026-11-19);
- code inspection of `fetchVerifyLink` / `gAccts` / `googleToken` shows the
  legacy fallback path is correctly wired (synthesized account index,
  default-account key resolution to the legacy slot, refresh-on-expiry).

So the failure sits in one of two places, not distinguishable from outside:
(a) the Durable-Object facade's view of the legacy `tok:` record, or
(b) Google refusing the refresh of the 2026-11-12 Testing-mode grant.
Either way the practical fix is the same and is NOT an account-creation step:
reconnect that Google account once in the app so a fresh v97 grant is
registered — after which the feed can read the mailbox and the reset door
becomes testable end-to-end. Note carefully: fixing F-FEED does **not** by
itself create an account — it only unblocks the reset door *if* a Resend
account for the chain email actually exists (the Nov 15 fed-link-era attempt
may have created one; Resend's anti-enumeration reset response neither
confirms nor denies it, and the mailbox could not be read through any
approved path available to this mission to confirm the reset mail arrived).

## What was built (branch `feat/julie-f7-selfcreate`)

- `setup.py`: shared `_oauth_door()` — tries **every** OAuth door the signup
  page offers (Google, then GitHub; a no-session on one no longer hides the
  other), completes chooser + first-grant consent when the sealed profile
  holds a session, and records `ok` / `no-session` / `blocked` without ever
  evading a sign-in form or a secure-browser refusal. Wired into
  `flow_resend` (before the email form) and the new `flow_brevo`.
- `setup.py`: **`flow_brevo` + `_brevo_create_key`** — fast path → OAuth door
  → signup → already-exists → login → email-validation pause (fed by the
  Worker's sweep) → API-key dialog (`xkeysib-…`). Registered in `FLOWS` and
  the wall-check routing.
- `cfworker/divya.js`: `SETUP_PROVIDERS` += Brevo (flow `brevo`);
  `VERIFY_PROVIDERS` += Brevo (brevo.com / sendinblue.com matchers) so the
  self-heal sweep feeds Brevo validation mail deterministically once merged.
  (Production still lacks these two entries until the PR merges — the live
  Brevo run above ran against the generic matcher, which the captcha made
  moot.)
- Key sealing needed no new code: `setup/runner/key` already mirrors
  resend/brevo keys into the sealed `sys` slot that `sendMailChannel()`
  reads (Resend first, Brevo fallback — unchanged).

## Conclusion (per the failure contract — exact walls, no "owner must do it")

Julie cannot yet create her own sending key with zero human steps, and the
blockers are specific, per provider: Resend's email form refuses the
datacenter runner outright and its Google/GitHub doors need a signed-in
session no sealed profile holds (its reset door is additionally blocked by
the Worker-side feed finding F-FEED); Brevo and Mailjet put a visible
reCAPTCHA challenge on signup; MailerSend is behind a Cloudflare bot wall;
SMTP2GO and Mailgun demand phone verification (Mailgun also card fields);
SendGrid demands phone verification on a 60-day trial; Postmark demands a
human approval review; Elastic Email demands a verified domain before any
sending. The two structural unlocks, in order: (1) fix F-FEED (one Google
reconnect in-app) and retest the Resend reset door — the only route observed
to get past a provider; (2) any future identity whose sealed profile holds a
live Google session makes the Resend/Brevo OAuth doors completable by the
chain as built — the doors, flows, feed matchers, and sealing are all in
place on this branch.
