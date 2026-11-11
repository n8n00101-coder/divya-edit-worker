# Divya: write new effect code for every video (v29)

Goal: no two videos share the same look and motion. Divya does not only choose from a
fixed list. For each video it writes a small new Python file (`video_fx.py`) of custom
effects for that topic, tests it, and only then renders.

The library (`transitions_lib.py`, 379 transitions in 40 families, 3D included, plus
`effects.py`) is the toolbox and the fallback. The new code is built ON TOP of these
building blocks, the same way a human editor builds a custom effect from basic tools.

## Why the videos repeat now
The render code is hardcoded. The LLM only fills text slots. So motion never changes.
Fix: the LLM must write motion code, not only pick names.

## Per-video loop (add as steps 3b and 6b of DIVYA_PIPELINE_v26)

1. **Topic objects.** From the script, list 5-8 real objects of the topic.
   Example "phantom vibration": phone, buzz waves, pocket, brain, nerve signal.
2. **Motion idea per scene.** One sentence each, built from a topic object.
   Example: "transition = phone buzz waves spread out as rings and reveal next scene",
   "number 89% = battery bar fills to 89 and shakes once".
3. **Write `video_fx.py`.** The LLM writes 3-6 new functions with this exact interface:
   - transition: `def tr_<name>(A, B, p) -> Image`  (A, B = PIL RGB frames, p = 0..1)
   - enter/emphasis: `def fx_<name>(layer, t, start, dur) -> Image`  (RGBA layer)
   Allowed imports only: `math, random, numpy as np, PIL (Image, ImageDraw, ImageFilter,
   ImageChops)`, `effects`, `transitions_lib`. No files, no network, no subprocess.
   Build from primitives: masks (`transitions_lib.f_*` + `_soft` + `_mix`),
   3D quads (`_rot_plane`, `_project`, `_quad`), easings (`EASES`), `effects.transform`.
4. **Sandbox test** (`fx_sandbox.py`): import the file with a time limit, run every function
   on test frames at p = 0, .25, .5, .75, 1. Reject if: error, wrong size, > 40 ms per
   720x1280 frame, frame at p=0 not equal A or p=1 not equal B (transitions), content
   outside the safe box (8% sides, 10% top/bottom).
5. **Fix loop.** On reject, send the error text back to the LLM, max 2 retries. Still bad,
   use `pick_transition()` from the library with the scene tags.
6. **Mutate, don't copy.** Even library picks get new params per video: direction,
   easing, softness, number of strips, colour = the video's accent colour.
7. **Fingerprint and memory.** Save per video: list of transition families + motion
   personality + accent colours. Next video must not reuse any family used in the last
   5 videos (`pick_transition(..., recent_families=...)`). Store in KV.
8. **Frame check.** Render 1 frame every 0.5 s, LLM scores each scene 1-5 on
   "fits the sentence, neat, nothing cut at edges, new compared to last video". Below 4, fix.

## Prompt block for Divya's LLM (Divya's own words, add to DIVYA_SYSTEM_PROMPT.md)

```
You are writing NEW motion code for this one video. Topic: {topic}. Mood: {mood}.
Topic objects: {objects}. Scenes with hit words: {scenes}.
Families used in the last 5 videos (do not use): {recent_families}.

Write video_fx.py with 3 to 6 functions:
- tr_*(A, B, p) for scene changes, each shaped like a topic object
  (rings from a phone, a page from a book, a coin flip for money, a heartbeat line for health).
- fx_*(layer, t, start, dur) for the hit word of a scene.
Use only math, random, numpy, PIL, effects, transitions_lib. Build from their primitives.
p=0 must return A, p=1 must return B. Keep content inside the safe box. Under 40 ms per frame.
Above each function write one comment: which sentence it serves and why it fits.
Return only the Python file.
```

## 3D without a 3D engine
`transitions_lib` warps flat frames with real perspective (`_rot_plane` -> `_project` ->
`_quad`). That gives cube, flip, door, fold, page turn, carousel, tilt-zoom, perspective
slide. New 3D ideas use the same 3 calls: make a plane, rotate it, project it, paste it.
Example: a phone screen that tilts toward the viewer = one plane, angle 0 -> 0.4 rad on "y".

## Library at a glance (379)
masks 151 (wipe 8 angles, circle, diamond, box, barn, clock, blinds, checker, blocks,
noise dissolve, spiral, star, heart, wave, zigzag) - motion 76 (push, cover, uncover,
split x 8 directions) - zoom/blur 52 (zoom-through, zoom-out, spin-zoom, blur dissolve,
stretch, whip x 8) - colour 30 (dip to colour, flash, luma, pixelate, rgb split,
posterize) - 3D 70 (cube, flip, door, fold, tilt-zoom, carousel, page turn,
perspective slide, swing, roll).
Every entry has tags (space, money, health, tech, story, calm, energy, 3d ...) for
`pick_transition(tags, used, seed, recent_families)`.
