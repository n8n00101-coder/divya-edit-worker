# ROUND 5 — Motion, Effects & Director Enforcement

**Trigger:** Ajju watched the third film himself (phone screenshots,
2026-11-16 ~22:01 IST) and rejected it: still boring, zero
edits/VFX/animation/transitions/trending effects, visuals look
STRETCHED, stale "DIVYA" branding on the end card ("READY FOR THE
NEXT TWIST? / DIVYA"), a cartoon avatar card overlapping a road
shot, and his conclusion: *"director sariga work avvatledhu"* —
the director is not working. The parent's standing commitment
(2026-11-16 12:31) is triggered: the card/template renderer has
hit its ceiling — this round makes the directed path *move*, and
makes a silent director fallback impossible to ship unnoticed.

**Sequencing:** this branch (`feat/julie-round5`) is stacked on
`feat/julie-round4` (PR #106) — it touches the same fix-round loop
and chapter records Round 4 just built. Merge #106 first, then
this PR rebases cleanly onto main.

**Tests:** `round5test.py` — 31 checks, ALL PASS. Regression:
round4test ALL PASS · nextroundtest ALL PASS · v100test PASS ·
prooffixtest 53/53 · hyperframestest PASS · toolstest PASS ·
pivottest ALL PASS (incl. the real end-to-end HF render through
the new treatment/transition/audit path).

---

## Fix 1 — Director no-silent-fallback gate

Film 3's editing director FELL BACK on both passes and the film
shipped as if directed; taste QC produced UNVERIFIED ×12 and
neither fact reached the delivery line.

- `brain_status` gains per-window attribution: `mark()`,
  `outcomes_since()`, `fallback_stages_since()` — the ledger was
  job-global, so nobody could say *which* chapter's director fell
  back.
- `render_chapters` opens a ledger window per chapter. If the
  editing/visual director fell back in it, the chapter is labelled
  `director_fallback` and a **`DIR-FALLBACK` compliance FAIL**
  (new boring-critical rule, `anti_boring.BORING_CRITICAL_RULES`)
  rides the existing fix-round loop with director-specific repair
  guidance.
- A fix round clears the FAIL **only if the brain stage actually
  ran in that render** — the fix pass's own ledger window is
  re-evaluated and the FAIL re-injected when it fell back again.
  Re-rendering with the deterministic director is not a fix.
- After the bounded rounds, a still-fallback chapter ships with
  `director_fallback_final` and the delivery summary states
  plainly: *"⚠ director: the brain director did NOT run for
  chapter(s) N — the deterministic fallback directed them"*.
  The result dict carries `director_fallback_chapters`.
- Taste QC: the UNVERIFIED verdict count (last round per chapter)
  is summed into the delivery summary — *"⚠ taste QC: UNVERIFIED
  (n beat verdict(s); vision …)"* — and onto the result dict as
  `taste_unverified_beats`.

## Fix 2 — Real motion in HyperFrames

- **Transitions.** Every HF beat now carries a transition: the
  editing plan's own per-scene transition field when it maps to a
  real xfade (dip→fadeblack, slide→slideleft/right, zoom→zoomin,
  wipe, dissolve, fade; a "match cut" maps to dissolve, noted in
  code), else a rule default — dip-from-black to open a chapter,
  dissolve into data beats, fade into maps, a rotating
  fade/slide/dissolve otherwise. A hard cut is never the default.
  `swap_spans` applies them as a real **xfade chain**,
  duration-compensated (clone-pad + cumulative real-duration
  offsets) so the chapter's total length — and its voice sync —
  does not drift; measured in tests (6.0s in, 6.0s out). An xfade
  graph failure retries as concat with the failure printed.
  `JULIE_HF_TRANSITIONS=0` restores hard-cut concat.
- **Motion audit** (new `motion_audit.py`). After the swap, every
  rendered beat is sampled at 25/55/85% and the pixel change is
  measured. Beats under the threshold are named in the HF report
  (`motion_audit.static_beats`) and become a boring-critical
  **MOTION-STATIC** FAIL in the chapter's fix loop.
- **The "1200%" path is dead.** The widget counter/bar in
  `create.draw_visual` now take the scene's spoken line: a counter
  whose number the line never speaks draws nothing, and a "%"
  prints only when the line actually speaks a percent. (The HF
  data-chart path already had the spoken-number rule; the widget
  layer did not.)

## Fix 3 — Footage motion treatment

`speedramp.py` and `beatgrid.py` existed but nothing in the render
path called them. Now, per HF beat (all logged in the report's
`motion_treatments`, failures in `motion_treatment_failed`):

- **Still images** → keyframed **push-in** on the media element
  (GSAP scale 1.03→1.14 over the beat, in `hyperframes_codegen`).
- **Measured-static clips** (motion is *measured* per clip with
  `motion_audit.clip_motion`, not assumed) → the same push-in.
- **Accent beats** (chapter open, a spoken-number/data beat, an
  effect hit) → a **speedramp accent** rendered by `speedramp.py`
  (0.8× ease-in over the first 45%, back through 1.15×; output ≥
  the beat window so timing holds), with a punch-in as the logged
  fallback when the ramp render fails.
- Beats measured static that somehow received no treatment are
  counted honestly as `untreated_static`.

## Fix 4 — Stretch defect

Ajju's screenshots show stretched visuals. Every fit-by-stretch
site in the long render path is fixed:

- `doc.fit_cover()` (scale-to-cover + centre crop) for scene
  backgrounds (`VL.scene_bg` was resized straight to (W, H));
- `doc.fit_inside_canvas()` (aspect-preserved, centred on a
  transparent canvas) for the 720×1280 visuals_lib layers
  (`_place720`) and the source-line layer — on a 1920×1080 long
  these were stretched ~2.7× sideways;
- `hf_primary.swap_spans` normalisation is now crop-to-fill
  (`force_original_aspect_ratio=increase` + crop), matching the
  broll extraction path, which already cropped correctly.
- Regression tests: a square marker stays square through both
  helpers, and a round marker in a square clip stays round
  (ratio ≈ 1.0, not 1.78) through the real swap.

## Fix 5 — Branding purge

The app is **Julie** (renamed 2026-11-12); infra names stay.

- `doc.outro` end card now draws **JULIE** (was the old brand —
  Ajju's first screenshot).
- `create` lower-third default name: JULIE.
- A scan test covers the render-path modules (doc, create,
  long_video, hf_primary, hyperframes_codegen, compliance,
  packaging, visuals_lib): any remaining `DIVYA` must match the
  infra allowlist (env vars like `DIVYA_LONG_BUDGET_S`, file names
  like `divya_doc.mp4`). A functional test renders the outro with
  a recording draw and asserts JULIE is drawn and the old brand
  never is.

## Fix 6 — Avatar card suppression in long films

The ROAD-beat cartoon face is `visuals_lib.vis_polaroid`: with no
real photo it draws a flat cartoon face (hair, dot eyes, smile)
inside a tilted polaroid. Three layers now keep it out of
faceless long-form documentaries:

- **Plan level** (`doc.plan`): for a long with no presenter
  request, polaroid choices are stripped (lib_visual cleared,
  mapped visual replaced) before anything renders.
- **Render level** (`doc.draw_scene_visual`): the same gate,
  keyed on the plan's own `render_config` (kind=long, no
  `presenter`), blocks the polaroid in the visual chain — shorts
  are unaffected (tested both ways).
- **Audit level** (`motion_audit.presenter_flags` +
  `long_video._round5_checks`): the shipped chapter's scene
  records are audited; a polaroid placeholder (a *real* photo in
  the card is content, not a violation) becomes a boring-critical
  **PRESENTER-CARD** FAIL in the fix loop.

## Honest limits

- The xfade blend window sits on the outgoing segment's
  clone-padded tail (the standard duration-compensation recipe):
  for 0.35s the outgoing side is a held frame while the incoming
  beat animates in. Total duration and sync are exact; the
  alternative (real-to-real blends) shortens the chapter and
  breaks voice sync.
- The motion audit measures *pixel change*, not taste: a moving
  but wrong clip passes it (that remains the vision verifier's
  job). An unmeasurable beat is reported as unmeasured, never as
  moving.
- `doc3.py` (the v3 engine, not the long path's default) was
  scanned: its only `DIVYA` strings are env-var infra names.
