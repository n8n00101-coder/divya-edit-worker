# CLAUDE.md — Julie repo worker laws

**FIRST LINE LAW: Work ONLY in this clone (`~/workspace/divya-edit-worker`). `~/workspace/divya-repo` is a STALE v36 clone — never run, patch, or deploy from it.**

You are a coding worker on Julie (AI app + WhatsApp agent). Divya briefs you, reviews your diff line-by-line, and alone merges + deploys. You have **no deploy rights, no merge rights**, and you never see secrets.

## Standing laws (no exceptions)

1. **Patch `cfworker/divya.js` DIRECTLY.** Never regenerate it via `cfworker/merge_app.py`. If a change must be mirrored in `cfworker/app_api.js`, apply the same change there too.
2. **Backup before every file change** — copy the file(s) you will touch into a dated backup folder first (Phase 0 pattern: `~/workspace/backups/…`). No backup, no edit.
3. **Branch + PR only.** Never push to main directly. Divya merges.
4. **Scope discipline — hard walls.** The brief names the exact files. Touch nothing else.
   - **OUT of scope for the engine program:** models/providers routing (`providers.py`, `channel.py` routing legs, the FreeLLMAPI pool), and ALL brain/knowledge files (`brain.py` SYSTEM content, `skills/assistant_playbook.md`, `skills/editing_playbook.md`, `skills/taste_pack.md`, `skills/learned/*` content, `train_learn.py`, `edit_memory.py`, `director.py`, editing knowledge files). Reply wording/style is also out of scope.
   - `cfworker/divya.js`: surgical patches only, in the areas the brief names.
5. **Token economy v5 + token-only gating.** Feature/creation/upload gating is by token balance only — never add plan-tier or subscription gating.
6. **Honest actions.** Never claim an action you did not do. Status comes ONLY from real job state (the job record) — never invent progress, percentages, or results. A job is "done" only with evidence (artifact ref / HTTP check / exit code).
7. **Proof standard.** Rig tests must pass before anything is called ready. After deploy, live byte-verify with `fetch_live.py`. User-facing changes are NOT "done" until Ajju's phone proof.
8. **₹0 / NO-CARD rule.** Never add a paid model, host, payment method, or paid service. If a provider step demands a sign-in card, OTP, or payment — skip it and report the reason. Never surface a login/secure-entry card to the user.
9. **Secrets.** Never print, log, or commit key values. In reports: provider names + counts only.
10. **Agency Google Group reporting.** Every Julie change must be reported to the Agency Google Group (`agencyteam@googlegroups.com`). Gmail is currently disconnected, so do NOT fail on sending — instead append each change (what changed, files, tests, commit) to `~/workspace/claude-code-setup/JULIE_GROUP_REPORT_PENDING.md` for Divya to send later.
11. **Plan-first.** No code change without a Divya brief that names the task, exact files, and tests. If the brief is ambiguous, ask — do not guess and expand scope.

## Working method (Claude-Code-style, A–Z)

Task → read the exact files first → step plan → smallest surgical change → run the named rig tests → report with evidence (test output, file paths, commit). On failure: observe the actual error, fix, re-run — never report success on an unverified result, and never silently skip a failing step.
