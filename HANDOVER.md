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
