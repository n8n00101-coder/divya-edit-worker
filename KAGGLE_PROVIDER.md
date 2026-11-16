# Kaggle GPU compute provider (v84)

Julie can voice a whole script on **your own Kaggle account's free
GPU** instead of only on GitHub Actions CPU runners — and if Kaggle
hits a limit mid-job, the job **automatically continues on GitHub
Actions**. No job dies because a provider ran out of quota.

## What you do (one time)

1. Go to **kaggle.com** and create your account **yourself** — Julie
   never creates accounts, never sees a captcha, never asks for your
   Kaggle password (guided-only rule R18).
2. Complete Kaggle's **phone verification** (Kaggle asks for it
   before GPU notebooks run).
3. In your notebook settings later, Kaggle needs **Internet: On** —
   the kernel Julie pushes already requests it.
4. Kaggle → your avatar → **Settings → API → Create New Token**.
   Your browser downloads `kaggle.json` — it holds your **username**
   and **API key**. Keep it private; it is a key to your account.
5. In the Julie app: **Setup → Kaggle GPU card** → paste the username
   + API key → **Test and Save**. Julie tests the pair against
   Kaggle, then seals it in your own storage (AES-GCM, the same
   sealing as every API key). The key is never shown again, never
   logged, never shared — the status line shows only your username.

That's all. You never touch Kaggle again unless you want to.

## What Julie does automatically

- A voice-batch job's lines are **split between the two providers**:
  Kaggle's GPU takes the head share, GitHub Actions runners take the
  rest, both at the same time, and the results are merged back by
  original line number.
- On Kaggle, Julie pushes a private kernel (built from the voice
  engine's gpu-pack contract) with the job's lines inside it, starts
  the GPU run, and polls it. The kernel runs the **same engine, same
  voice, same quality gates** — only faster. Output comes back as
  `out.zip` (`<nnn>.mp3` per passing line + `batch.qc.json`).
- The job's live status shows in chat while it runs
  ("Kaggle GPU lo voice avthundhi…").

## Failover — the promise

If Kaggle errors, times out, or reports its quota/limit — or the
result comes back without its QC record — **the unfinished lines
continue on GitHub Actions automatically**, and you get **one** chat
line saying the switch happened and why. The same works in reverse
(Actions trouble → Kaggle). Lines that failed the engine's quality
gates are *not* switched (another provider would run the same gates);
they are reported honestly in the batch QC.

If you never connect Kaggle, nothing changes: voice batches use
GitHub Actions exactly as before.

## Honest limits

- Kaggle's free GPU is **≈30 hours/week per account**, sessions are
  time-limited, and the first run pays a few minutes of dependency
  install + model download. A 209-line script fits comfortably.
- **One Kaggle account per person** is Kaggle's own rule. Julie
  deliberately does **not** rotate multiple accounts to dodge the
  quota — that risks bans. The safety net is the *other provider*,
  not another account.
- For the Actions leg, the job's lines file is briefly written into
  the engine repo (`jobs/<job>.txt`) because the workflow reads its
  lines from a repo file; it is deleted when the run ends. A future
  workflow input can remove even that.
- Telugu/Hindi voice batches: the gpu-pack GPU patch targets the
  English clone path and the gate ASR; for te/hi the Actions route
  remains the proven path today.

## Where things live

- Worker: `cfworker/divya.js` — `KEYPROV.kaggle`, the `keys/kaggle`
  connect/status routes, the Setup keys-list row, the `/job`
  runner-channel credential hand-off, `startVoiceBatch`.
- App: Setup → Kaggle GPU card (`app/index.html`, `app/app.js`).
- Runner: `voicecompute.py` (Kaggle client, Actions client, hybrid
  split + failover), wired as the `voicebatch` mode in `runner.py`.
- Tests: `python3 kaggletest.py` (providers/failover vs fake APIs),
  `node kaggleworkertest.mjs` (Worker routes + sealing, end to end).
