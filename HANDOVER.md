# Divya — handover for any agent working on it

Owner: WhatsApp +91 9951950173 (chats in romanized Telugu/Tenglish). Build goal: a WhatsApp agent that makes premium faceless videos (create mode) and edits the owner's footage, then posts to YouTube/Instagram. Free tools only, no paid TTS. Never post publicly without the owner's OK. Never print or share key values.

## Architecture
1. **WhatsApp Cloud API**: Meta app "Divya bot" (ID 1531290705716535), test number +1 555 040 6755 (phone ID 1404587642739329, WABA 1159269589866526). The test number reaches only verified recipients (max 5): the owner and friend +91 7993610173.
2. **Cloudflare Worker `divya`** (`https://divya.n8n00101.workers.dev`, account ba39b7fb8bae4e32999a8a77c8e04039), source `cfworker/divya.js`.
   - The webhook receives WhatsApp messages. Only OWNERS (var) and FRIENDS (var; defaults to 917993610173 in code) get replies.
   - Chat brain: Groq `openai/gpt-oss-120b`, with fallbacks in CHAT_MODELS. SYSTEM prompt is inside divya.js. Owner gets full self-description; friends get a restricted prompt.
   - KV namespace DIVYA (`ed334e71aaef476a89ec16836a4dc91c`): `h:<number>` chat history, `seen:<msgid>`, `groq:models`, job records, and leftover `dbg:*` keys.
   - Secrets: WA_TOKEN, GROQ_KEY, GH_TOKEN, VERIFY_TOKEN, RUNNER_KEY. Vars: PHONE_ID, OWNERS, GH_REPO.
   - Deploy: `cfworker/deploy.sh`. It PUTs divya.js and keeps existing bindings, and needs a Cloudflare token with Workers edit rights. You can also paste divya.js in Dashboard > Workers > divya > Edit code.
   - When the model replies `[[CREATE: ...]]`, the Worker stores a job in KV and dispatches GitHub workflow `edit.yml`.
3. **GitHub repo `n8n00101-coder/divya-edit-worker`** (public):
   - `edit.yml` → `runner.py` (fetches the job and creds from the Worker `/job` using RUNNER_KEY), then `create.py` / `doc.py` (create mode) or `editor.py` / `autoedit.py` (owner footage). The result goes back to WhatsApp.
   - `doc.py` v2: LLM plan, edge-tts, Pillow animated scenes, transitions, music, libass captions, 1080x1920.
   - Voice experiments: `voicetest.yml` (Chatterbox EN/HI), `telcb.yml` + `telcb.py` (Chatterbox Telugu fine-tune, CC-BY-4.0, attribution needed), `youngall.yml` (12 test voices, all rejected by owner). `teltest.yml` is dead.
   - `docs/` is GitHub Pages (privacy.html).

## Current status (2026-11-08)
- Owner verdict: the doc.py v2 videos are boring and same-style, with unwanted transitions. Root causes:
  - One fixed template with 12 generic icons, and structure labels (HOOK/STAT/CALL) shown on screen.
  - A transition at every scene.
  - Telugu captions are broken (no HarfBuzz/raqm shaping).
  - Facts aren't checked.
- **Next = engine v3**, built to Tab's editing standard:
  1. Script: a hook in the first 3 s, short sentences, one real sourced incident. Fact list with sources; drop anything unsourced. The end loops back to the hook.
  2. Visuals: a real image or clip per sentence (Wikimedia Commons, Pexels, Pixabay, archive.org). No repeats. A new visual every 3-5 s, Ken Burns on photos. Drawn animation only for numbers or processes.
  3. Captions: Anton ~56px, white, key word in yellow, max 4 words, bottom third. Telugu in Noto Sans Telugu with correct shaping.
  4. Voice: free TTS only, one clip per sentence, 250-600 ms pauses, 1.0x.
  5. Music: Kevin MacLeod (CC-BY, credit it) at about -22 dB, ducked. Whoosh on scene change, hit on numbers.
  6. Export: 1080x1920, 30 fps, h264+aac, -14 LUFS.
  7. QC before sending: a frame every 3 s checked by a vision model, plus speech-to-text vs script. Send only if it passes.
- Voice: the owner wants a sweet, young-sounding (adult) female voice with an Indian accent, free. All tries so far were rejected. Still open.
- Known issues:
  - Vision (screenshots) is dead because the llama vision models are gone.
  - The 24 h WhatsApp window isn't handled.
  - The privacy policy promises "delete my data", which isn't implemented.
  - The Worker `/job` returns secrets to any RUNNER_KEY holder.

## Rules for whoever edits
- Test before telling the owner something works. Never say "ready" before the file has reached WhatsApp.
- Keep replies to the owner short, in Tenglish.
- Don't commit keys. Use the platforms' secret stores.

## Voice calls (built 2026-11-08)
- Flow: WhatsApp user calls +1 555 040 6755 → Meta "calls" webhook → Worker `/webhook` forwards any `changes[].field=="calls"` body (ctx.waitUntil, header `x-divya-key: FORWARD_SECRET`) to `CALL_URL` + `/calls` → media server answers with Pipecat WhatsAppClient (pre_accept + accept) → SmallWebRTC pipeline.
- Media server code: `agent/voicecall/` (server.py, bot.py, edge_tts_service.py, Dockerfile); also in GitHub repo under `voicecall/`. Workflow `.github/workflows/callimage.yml` builds `ghcr.io/n8n00101-coder/divya-call:latest` (public) on every push to `voicecall/**`.
- Host: SnapDeploy free container `divya-call` (id 54425e10-2b96-4129-8cd5-6f7229f618d4), https://divya-call.containers.snapdeploy.app (512 MB / 0.25 vCPU, 100 h/month, SLEEPS after 15 min idle, wakes only on a browser visit ~60 s, 5 deploys/12 h). HF Docker Spaces need PRO (402), so not used. Shell provider `snapdeploy` (header X-API-Key). Env: PORT, FORWARD_SECRET, CF_TURN_KEY_ID, CF_TURN_KEY_TOKEN. To pick up a new image: restart the container (costs 1 deploy) or PUT /env.
- Creds: the server fetches WA_TOKEN/GROQ_KEY/OWNERS/FRIENDS from Worker `POST /callcreds` (x-divya-key). Only OWNERS+FRIENDS calls are answered; others are rejected.
- NAT: SnapDeploy blocks outbound UDP to STUN (host candidates only), so Cloudflare Realtime TURN (key "divya-call", TCP/TLS URLs only, env TURN_TRANSPORTS=tcp) gives relay candidates. The Cloudflare token now has Account "Cloudflare Calls: Edit".
- Pipeline: Silero VAD → Groq whisper-large-v3 (STT_LANG=te) → Groq openai/gpt-oss-120b (reasoning low, 1-2 sentence persona, Telugu SCRIPT for correct TTS pronunciation; VOICE_SCRIPT=roman to switch) → edge-tts te-IN-ShrutiNeural (TTS_VOICE env) → WebRTC.
- Debug endpoints (need x-divya-key): GET /logs, GET /icetest, POST /selftest (loopback call inside the container: proves LLM+TTS audio). GET /health is public. Shared secret copy: /workspace/work/.forward_secret (chmod 600).
- Open: Meta app "calls" webhook field must be ticked in the dashboard (needs app token). First real call not yet tested (payment-method / country rules unknown until then).

## Divya app (PWA) — added 2026-11-08
- URL: https://divya-app.n8n00101.workers.dev (static Worker `divya-app`, same CF account). Cloudflare Pages direct-upload was blocked by the credential gateway (asset-upload JWT gets replaced), so the PWA is bundled into one Worker script instead. Free.
- Source: `built/divya-app/` (index.html, app.css, app.js, sw.js, manifest, icons); bundle+deploy: `python3 built/build_app_worker.py --deploy` (provider cloudflare-divya). Bump `V` in sw.js on each release. Copy also in repo `app/`.
- Backend: additive block `// ===== DIVYA APP API` in divya.js + one route line in fetch (`/api/*`) + WhatsApp `login` command in handle(). `work/merge_app.py <deployed> work/app_api.js <out>` re-merges idempotently into the live script.
- Routes: login/start, login/verify, logout, me, history, chat, voice (multipart `audio`), image (multipart `image`, uses env.GEMINI_KEY if set, else Groq vision, else "not available"), create, status, connect, connect/link. Auth = Bearer token, KV `sess:<token>` 30 d. OTP KV `otp:<num>` 10 min, 5 tries, 60 s resend cooldown. Only OWNERS/FRIENDS.
- App and WhatsApp share KV `h:<number>` (12-message window).

## Divya app v2 (2026-11-08 afternoon) — menu, home, Hey Divya, setup, freemium
- UI: monochrome (black/white/grays) light+dark, hamburger drawer (Home, Chat, Create video, Voice assistant, Connect accounts, Server & API setup, Subscription, Download app, Settings, Logout), hash routes `#/home` etc. Home = greeting, big "Hey Divya" button, 8-icon grid (Chat, Create video, Voice, Connect, Server setup, Subscription, Download, Settings), recent video job card. Monochrome icons regenerated. sw.js `V = divya-v4`.
- Accessibility: every control has a label (aria-label/label), 44px+ targets, skip link, drawer aria-expanded + Escape + focus return, each screen sets the title, focuses the h1 and announces "<name> screen" in a live region. Settings "Voice-first mode": speaks every result + screen names, and keeps listening after each answer (while open). Not yet tested with a real TalkBack/VoiceOver device.
- Hey Divya: Web Speech API (webkitSpeechRecognition, continuous, te-IN/en-IN) only while the app is open on screen; wake regex hey/hi divya + హే దివ్య; chime + animated orb; command -> `POST /api/assist`; reply spoken with speechSynthesis. No SR (Firefox, some iOS) -> hold-to-talk on the orb (MediaRecorder -> `/api/voice` with `assist=1`). Chrome sends audio to Google for recognition (stated in-app).
- Freemium assistant (`/api/assist` in app_api.js): rules first, then a Groq JSON classifier (gpt-oss-20b -> llama-3.1-8b) when the text looks like an action. FREE intents: call (tel:), whatsapp (wa.me/<num>?text=, or wa.me/?text= to pick a contact), open (app/site map incl. Telugu names), play (YouTube search; Android intent to the YouTube app), reminder (in-app timer only while open + Google Calendar link), time, weather (Open-Meteo, no key), short chat. PREMIUM: videos, multi-step agent work, long research, account automation -> free users get "needs subscription" + button to #/plan. KV `tier:<num>` = premium|free; default premium for OWNERS+FRIENDS (so every current user is premium). Contacts (name->number) are stored only in the phone's localStorage ("save amma 98..." or Contact Picker on Android Chrome).
- Video quota: `vday:<num>:<IST date>`; non-owners 1/day (env DAILY_VIDEOS overrides), owners unlimited. Enforced in app create, app chat [[CREATE]] and WhatsApp create path (merge_app.py patches handle()).
- Per-user API keys: KV `ukey:<num>:<provider>` = AES-GCM ciphertext (AAD `<num>:<provider>`), key = Worker secret `APP_KEK` (copy: /workspace/work/.app_kek, chmod 600 — losing it makes stored keys unreadable). Routes: GET keys, POST keys/save {provider,key,consent:true} (tests first, stores only if valid), keys/test, keys/delete, keys/openrouter {code,verifier}. Providers + test call: groq (/models), openrouter (/key, falls back to a free chat call), gemini (/models), cloudflare (tokens/verify or /accounts), github (/user), huggingface (whoami-v2). Brain: user's Groq key -> user's OpenRouter key (free models) -> shared GROQ_KEY; `/api/chat|assist` replies include `brain`. Image route prefers the user's Gemini key.
- Setup automation — what is automatic vs guided:
  - Fully automatic (one tap + provider consent): OpenRouter key (OAuth PKCE, callback https://divya-app.n8n00101.workers.dev/setup, server-side exchange). Tested end-to-end 2026-11-08 on the owner's OpenRouter account; a fresh key returned 401 "User not found" for ~3 min, then worked.
  - One tap: "Continue with Google" (existing Worker Google OAuth, provider `google`) gives the user's email.
  - Guided (no OAuth available): Groq, Gemini, Cloudflare (pre-filled token template URL: Workers Scripts edit, KV edit, Account Settings read), GitHub PAT, Hugging Face token. Divya speaks each step, opens the key page, on return reads the clipboard (or the paste field) and auto-detects the key format, then saves after ONE confirmation.
  - Not done: GitHub/HF OAuth apps (need app registration in their web UI) -> "Soon". Auto-deploying the user's own Worker/server with their Cloudflare token -> "Soon". Divya never creates accounts silently, never bypasses captchas, never stores passwords.
- Subscription screen: Free vs "Pro — coming soon", "Price: soon". TODO: payments need the owner's choice of provider (e.g. Razorpay) and the owner's explicit approval before any signup or live payments.
- Deploy helpers: `work/deploy_api.sh` (download live -> merge_app.py -> node --check -> backup -> deploy.sh). Tests: `work/ui_test3.py [url]` (3 sizes x light/dark, overflow, labels, targets, JS errors), `work/ui_test4.py`, `work/ui_test5.py` (live flows). Harness quirk: with the sandbox proxy, Chromium input freezes after a cross-origin fetch with an Authorization header unless the test calls `page.route(API/**, continue)`.
