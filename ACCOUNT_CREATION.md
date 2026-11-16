# Account creation in Julie (v103)

Ajju's standing requirement (2026-11-16): account creation is CORE to
Julie, not a feature — "Mana Julie kuda ilanti works cheyyalepothe
inka Julie app work avthunnatta lenatta." The automate chain therefore
gains a CREATE stage: Julie drives a provider signup in the setup
browser, in the USER'S OWN identity, and the chain continues by
itself: account created → verification → API token created → sealed →
self-test → provider live in Setup.

The only user micro-steps are the ones that are legally/technically
the user's: an OTP code and a captcha. Both are asked as a normal
in-chat question and Julie enters the answer herself.

## The ask/resume protocol (AWAITING_USER)

Runner side (`setup.py`):

- `await_user_input(page, kind, prompt, field=None, ttl_s=None, attempt=1)`
  posts a progress update with state `paused`, step
  `await-otp` / `await-field` / `await-captcha`, and a structured
  `awaiting` block `{id, provider, kind, prompt, at, expires,
  attempts}`; then polls the job record until the Worker writes
  `userInput {value, askId}` (askId must match — one active ask per
  job), the job stops, or the TTL expires. TTLs: otp 10 min, field
  15 min, captcha 25 min. Heartbeats re-post the same awaiting block.
- Re-ask-once is structural: `attempt > 2` raises. A flow whose code
  is rejected re-asks with attempt 2; a second rejection fails the
  provider with a labelled wall (`otp-rejected:<step>`) and the chain
  continues — skip-and-continue, same as every provider failure.
- `await_captcha_gate(...)` posts the kind=captcha ask and hands the
  session to Take Control. A captcha is NEVER solved by Julie and
  NEVER sent to a third-party solver. If the provider offers no
  user-completable path from the runner session, the flow fails
  labelled with the exact wall.

Worker side (`cfworker/divya.js`):

- `setup/runner/progress` stores a validated `awaiting` block on the
  job record (kind/provider/prompt clamped, expiry clamped to
  ≤ 35 min, attempts clamped 1–2). When the ask id or attempt
  CHANGES, the prompt is appended to the user's chat history exactly
  once — Julie asks in chat; heartbeat re-posts never duplicate it.
  Any non-paused progress clears `awaiting` and `userInput`.
- Chat routing (`appTalk`): an intercept right after the model-key
  block calls `setupAwaitingReply`. While an ask is open:
  - kind=otp: only a code-shaped message (4–8 digits) is an answer;
    anything else flows on untouched and the ask stays open. A
    malformed code gets one in-chat correction line.
  - kind=field: a short plain value is the answer; questions,
    orders and bare approvals are not consumed.
  - kind=captcha: never answered by a value — resume is Take
    Control / Continue.
  - Stop words are never consumed.
  Delivery (`setupDeliverUserInput`) validates by kind, checks the
  TTL, writes `userInput` onto the job record, and the confirmation
  reply NEVER echoes the value. `POST /api/setup/answer {value}` is
  the same delivery for the Setup card's answer box.
- `setup/status` strips `userInput` (like `smsCode`/`pass`) — codes
  never reach an app-facing payload, a log, or a report.

## Identity rules

- Form fields come from the user's own account profile: the chain
  email (given at setup/start), `u.acct.name`, `u.acct.phone`
  (verified). The Worker copies name/phone onto the chain and job
  records (`userName` / `userPhone`).
- NEVER invented: no placeholder names, no generated phone numbers.
  A missing field is asked in chat (kind=field) via
  `creation_identity()` and the user's own answer is used.
- Passwords are the chain-generated ones (`setupPass()`), sealed in
  the profile as today (`upass:<n>`) — never printed or logged.

## Profile-serialization guard (the root defect)

Each identity has ONE sealed browser profile (`uprofile:<n>`).
Profile-mode jobs fetch it at start and push it at end with no lock —
two concurrent profile jobs silently erase each other's captured
sessions, last-writer-wins. The guard (`profileJobActive`) makes the
two job kinds mutually exclusive per identity:

- `startBrowseJob` refuses while a profile-mode setup chain is
  active (error `busy`, state `setup-chain`).
- `setup/start` refuses a profile-mode chain while a browse job is
  active (`profileBusy: true`). An explicitly ephemeral chain is
  exempt — it never touches the profile.
- The autonomous provision loop (`maybeAutoCheck`) skips with
  `profile-busy` while a browse job is active.

Proven both ways in `acctcreatetest.mjs`.

## Per-provider driver contract

A creation provider is a `FLOWS` entry with `flow: "<id>"` plus a
`flow_<id>(page, job, cfg)` in `setup.py` that:

1. Resolves identity via `creation_identity()` (ask, never invent).
2. Drives the provider's registration door (email door; the Google
   door via `_oauth_door()` when the chain runs in profile mode and
   a sealed Google session exists).
3. Handles verification through the ask protocol only: email code →
   OTP ask; email link → the self-heal feed (`pause_for_email_verify`
   + `VERIFY_PROVIDERS` entry); phone → OTP ask; captcha → the
   captcha gate or a labelled wall.
4. Creates the API token on the provider's own settings page and
   captures it in the provider's native shape.
5. Returns `_ok(key=<sealed payload>, extra={"created": True})` —
   the existing `submit_provider_result` then self-tests the key
   (`test_key`), seals it (`ukey:<n>:<provider>`) and reports done.
   CREATED ✓ counts only when the key is sealed AND the self-test
   passes. Every failure names the exact wall in `extra.wall`.

| Provider | Status | Verification | Token path | Self-test |
|---|---|---|---|---|
| Kaggle | **wired** (`flow_kaggle`, chain position before pexels) | email code or link; phone OTP via chat ask; captcha = gate/wall | Settings → API → Create New Token → kaggle.json download | GET kaggle.com/api/v1/datasets/list with Basic auth (user, key) |
| (GPU-pool + others) | pending survey | — | — | — |

Other providers slot in as their signup surveys land — no survey
results are recorded here until a real run produces them.

## Tests

- `acctcreatetest.py` — runner harness (fake Kaggle + fake Worker):
  ask round-trip, timeout, attempt cap, happy path end-to-end
  (register → email code → phone code → token → seal → self-test),
  wrong OTP re-ask-once → labelled fail, captcha gate (no solver
  call in `flow_kaggle`), missing identity asked and used,
  existing-account fork signs in instead of duplicating.
- `acctcreatetest.mjs` — Worker rig: guard both ways + ephemeral
  exemption, awaiting stored + chat ask exactly once per ask/re-ask,
  chat reply routed to the job without echoing the code, non-code
  messages not consumed, status strips `userInput`, `setup/answer`
  validation.
- `v81test.py` — chain order / cross-file consistency with kaggle in
  the chain.
