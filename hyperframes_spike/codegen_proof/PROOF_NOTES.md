# Codegen proof — notes (2026-11-16, this VM)

Pipeline: `proof_script.json` (pure data, 3 scenes over the spike's
real Oregon-coast drone clip) → `hyperframes_codegen.generate_project()`
→ `./project/` → `hyperframes check` → `hyperframes render` (the
spike's exact CLI) → `codegen_render.mp4`.

- Check: lint 0 errors / 0 warnings; runtime ok; layout ok with 3
  info-level findings (masked-rise title mid-animation under the
  scrim — intentional layering, same class as the spike's notes).
- Render: **13.000 s, 1920×1080, 30 fps, exactly 390 frames, H.264**
  — duration equals the summed scene durations (4 + 5 + 4). Output
  30.7 MB at the renderer's CRF-16 "looks" default (a delivery
  re-encode remains Julie's existing pipeline step, as with the spike).
- Render wall time on this 1.5-CPU shared VM: ~15 min for 13 s in
  screenshot-capture mode (the spike measured 21 min for 45 s).
  GitHub Actions timing is UNVERIFIED.
- Frames (eyeballed):
  - `frame_scene1_title.png` (t=3.0): full-frame coast footage;
    kicker "THE PACIFIC NORTHWEST", headline "THE VANISHING / COAST"
    with VANISHING in the accent colour, sub-line present.
  - `frame_scene2_chart.png` (t=8.3): full-frame coast footage at a
    later offset (media_start auto-advanced); panel with bars landed
    on the script's exact values — 1993 → 2.1 mm/yr (short blue bar),
    2023 → 4.5 mm/yr (full orange bar) — note and
    "Source: NASA Sea Level Change, 2024" on screen.
  - `frame_scene3_kinetic.png` (t=12.2): full-frame forest/coast
    footage; kinetic line "BUT HOW FAST?" with FAST? in accent.
- Reproduce: `python3 run_proof.py` (generate + check) or
  `python3 run_proof.py --render` (full proof; slow on this VM).
