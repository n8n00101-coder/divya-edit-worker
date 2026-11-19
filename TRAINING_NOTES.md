# CCTRAIN Session 1 — Training Notes

**Date:** 2026-11-19  
**Branch:** claude/julie-cc-train-1  
**Worker:** Julie repo at ~/workspace/julie-cctrain-wt  

---

## 1. Gap Audit — Julie's Engine vs Claude Code Working Method

Ranked by real-world value for multi-step agent work:

| Rank | Gap | Description | Impact |
|------|-----|-------------|--------|
| **1** | **Context handling across long jobs** | HISTORY_WINDOW=8 limits brain context; no retrieval mechanism for steps beyond the window. Brain forgets early steps, cannot reference prior evidence, plans, or facts. | **HIGH** — jobs >8 steps lose all earlier context. The brain operates blind on long tasks. |
| **2** | **Error recovery / self-correction after failed tool calls** | Loop feeds failures back, but brain has no structured way to diagnose, retry with adjusted args, or escalate. No "try-catch" equivalent at the brain level. | **HIGH** — failures often end jobs instead of triggering adaptation. |
| **3** | **Planning quality** | set_plan tool exists (E10) but no enforced planning discipline. Brain can wander without a plan, no mid-course correction of plan steps, no plan-aware tool selection. | **MEDIUM-HIGH** — unplanned work drifts, wastes steps, misses verification gates. |
| **4** | **Verification beyond files** | E7–E8 verify CSV/file content exactly. No verification for: API responses, browser state, computed facts in memory, cross-step consistency. | **MEDIUM** — "done" claims can pass with hallucinated external state. |
| **5** | **Honest stop reporting instead of looping** | Loop stops at MAX_STEPS/stop flag, but brain has no "I'm stuck" signal. No structured "fail with reason" that surfaces to the user as actionable status. | **MEDIUM** — silent loops or opaque failures erode trust. |

**Top gap selected:** Context handling across long jobs (Rank 1).

---

## 2. Implementation — get_history Tool

**Files changed:**
- `agent_loop.py` — added `_tool_get_history()` function (lines ~398-448) and registered it in `default_tools()` (lines ~451-466)

**What the tool does:**
- **Read-only** (`mutating=False`, `needs_allow=False`, `stub=False`) — never triggers Allow gate, never changes state
- **Pagination:** `limit` (default 50) and `offset` (default 0) args for stepping through history
- **Full history access:** Returns ALL recorded steps from the job record, regardless of HISTORY_WINDOW
- **Resumed jobs:** Reads from `job["steps"]` only — `seed_history` (from previous run) is NOT in the record, so get_history correctly shows only steps recorded in this run
- **Empty state:** Returns helpful message "No steps recorded yet (total=0)" instead of empty string
- **Schema:** `{limit: {type: number, required: false, desc: "max steps to return (default 50)"}, offset: {type: number, required: false, desc: "skip N most recent steps (default 0)"}}`

**Key design decisions:**
- Reads from `fetch_job_state()` → `job["steps"]` — same source as `job_state` tool, so it's always consistent with the persisted record
- Does NOT read from the brain's `history` parameter (which is truncated to HISTORY_WINDOW)
- The loop passes `history` to the brain (truncated), but the tool reads the full record — brain can recover context beyond the window
- Offset is applied AFTER limit: we slice `steps[-limit:]` then `result[offset:]` — this means "most recent N, then skip M of those"

**Why this solves the top gap:**
Before: brain sees only last 8 steps → on step 20, steps 1-12 are gone forever  
After: brain calls `get_history` with limit/offset → can retrieve any step, rebuild context, reference earlier evidence/plans/facts

---

## 3. Tests Added — cctrain1test.py

**19 tests, all passing:**

| Case | Description |
|------|-------------|
| (a) | Basic get_history returns full step history |
| (b) | Pagination: limit=2 returns most recent 2; limit=1 offset=1 skips prior get_history call |
| (c) | Resumed job: seed_history not in record; get_history shows only new recorded steps |
| (d) | Empty job: returns helpful "no steps recorded" message |
| (e) | Tool metadata: read-only, no Allow, not stub, correct schema |
| (f) | Context recovery: job with HISTORY_WINDOW+3 steps; get_history returns ALL steps |

**Test style:** Follows e-series rig pattern — FakeBrain scripted queue, recorder appending to job steps, `unittest.mock.patch` for `fetch_job_state`, no live network.

---

## 4. Existing Test Suites — All Green

| Suite | Status | Notes |
|-------|--------|-------|
| e1test.py | ✅ 29/29 pass | Updated expectation for default tool set (now includes get_history) |
| e2test.py | ✅ 27/27 pass | |
| e3test.py | ✅ 27/27 pass | |
| e4test.py | ✅ 30/30 pass | |
| e56test.py | ✅ 31/31 pass | |
| e7test.py | ✅ 33/33 pass | |
| e8test.py | ✅ 28/28 pass | |
| e9test.py | ✅ 23/23 pass | |
| e10test.py | ✅ 45/45 pass | |
| cctrain1test.py | ✅ 19/19 pass | New rig for get_history |
| integrationtest.py | ⚠️ Skipped | Requires Playwright (not installed in this env) — known dependency gap, not a regression |

**No regressions introduced.** All existing engine rigs pass.

---

## 5. Deliberate Omissions — What Was NOT Done

| Item | Reason |
|------|--------|
| **Automatic context injection** (prepending history to brain prompt) | Would change brain contract; get_history is opt-in, brain decides when to retrieve. Keeps loop simple, brain in control. |
| **Search/filter on history** (by tool name, step number, text) | scope creep — pagination (limit/offset) is sufficient for the brain to walk history. Can add later if needed. |
| **Seed history in get_history** | By design — seed_history is from the *previous* run, not recorded as steps in this run. The record is the source of truth. |
| **Brain-side context management** (summarization, compression) | Out of scope for engine — that's a brain/prompting concern, not a tool contract. |
| **cfworker/divya.js changes** | Not needed — get_history is a pure engine tool, no Worker channel involvement. |
| **Plan-tool integration** (auto-fetch history when plan references old steps) | Premature — let the brain use get_history explicitly first. |

---

## 6. Verification Evidence

- **All e-series rigs pass** (273 tests total)
- **New cctrain1test.py passes** (19 tests)
- **e1test.py updated** to expect get_history in default tool set
- **No changes to brain, providers, routing, skills, or knowledge files** — scope walls respected
- **Backup created** at `~/workspace/backups/julie-cctrain-1-2026-11-19/`

---

## 7. Commit Summary

```
feat(engine): add get_history tool for long-job context recovery

- Added _tool_get_history() to agent_loop.py: read-only tool with
  limit/offset pagination returning full job step history beyond
  HISTORY_WINDOW=8
- Registered in default_tools() with proper E2 metadata (mutating=False,
  needs_allow=False, stub=False, schema)
- Created cctrain1test.py with 19 rig tests covering basic use,
  pagination, resume behavior, empty state, metadata, and context recovery
- Updated e1test.py expectation for default tool set
- All 273 existing e-series tests pass; no regressions
- Closes TOP gap from gap audit: context handling across long jobs
```