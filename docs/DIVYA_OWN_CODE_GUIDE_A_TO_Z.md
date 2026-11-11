# DIVYA: How to write your own code for every video (A to Z)

This guide teaches Divya to do what a human motion editor does: read the topic, imagine the
motion, write new code for it, test it, fix it, and remember it. No template is reused as-is.

Files in this kit that this guide uses:
| File | Role |
|---|---|
| `divya_codegen.py` | The engine. Runs steps D to H below automatically with any OpenAI-compatible LLM. |
| `fx_sandbox.py` | The tester. Rejects broken, slow, edge-cutting or unsafe code. |
| `fewshot_examples.py` | 10 worked custom functions for 5 topics (money, sleep, space, history, health). All pass the sandbox. |
| `video_fx_example.py` | Short example (phone buzz). Used as the default few-shot. |
| `transitions_lib.py` | 379 transitions in 40 families incl. 70 3D. Building blocks + fallback. |
| `effects_lib.py` | 321 layer effects: 128 enter, 68 emphasis, 107 exit, 18 camera. Building blocks + fallback. |
| `visuals_lib.py` | 18 rich visuals (map, document+stamp, newspaper, packet, polaroid, filmstrip, scale, bracket bars, magnifier, photo, camera, timeline ...) + 9 scene backgrounds. |
| `fewshot_visuals.py` | 3 new visuals written from scratch (storm bolt, coin stack, bed+phone). Examples for the LLM. |
| `motion_graphics.py` | 41 animated infographic templates (counter, ring, charts, battery, phone, chat, map pin, ECG, confetti ...). |
| `VOICES.md` | 322 free edge-tts voices, with mood picks (Telugu, Hindi, Indian English included). |
| `DIVYA_EDITING_HANDBOOK.md` | The theory: timing, spacing, 12 principles, cutting, pacing, typography, colour, sound, retention. |

---

## Can a free model write this code?
Yes. Free and open models (on Groq, OpenRouter free tier, or Ollama) such as Llama 3.3 70B,
GPT-OSS 120B, Qwen coder models and DeepSeek coder models write this kind of Python well.
Small models make more mistakes, which is why the engine never trusts the first answer:
every file is tested by `fx_sandbox.py`, the error is sent back for a fix (2 tries), and
anything still broken is replaced by a library pick. So the video never breaks, and most of
the motion is still new.

Tips that make a free model write better code:
1. Split the job. One call to PLAN (ideas as JSON), one call to CODE. Never both in one prompt.
2. Give the exact function interface and the list of allowed helpers (done in `SYSTEM` in divya_codegen.py).
3. Show 1-2 few-shot examples from a DIFFERENT topic and say "do not copy the ideas".
4. Temperature 0.8-0.9 for ideas, 0.6 for fixes.
5. Ask for the whole file back on a fix, with only the listed problems fixed.
6. Keep each function small (10-25 lines). Many small functions beat one big one.

"Training" here does not mean fine-tuning a model. It means: the right prompt chain, good
examples, a tester, a fix loop, and memory of what was used. That is what changes the output.

---

## The process, step by step

### A. Understand the topic (LLM, 1 call, part of script step)
Answer 4 questions and save them in `style.json`:
- What is it about, in one sentence?
- What is the feeling? (fear, wonder, funny, calm, urgent, proud, sad)
- What is the one surprising fact? (this becomes the hook)
- Who watches and what do they get? (a tip, a shock, a laugh)

### B. Script with hit words
- Line 1 must hook inside 1 second (a number, a question, a "stop doing this").
- Each sentence gets ONE hit word: number > topic noun > shock word.
- 8-14 words per sentence, one idea per sentence.

### C. Voice and word timings
- Pick the voice from `VOICES.md` by mood; rate +6..+10% for energy, -4..-8% for calm.
- Get word timestamps from edge-tts (WordBoundary events). Every hit word now has a time.
- Rule: visual lands 80 ms (2-3 frames) BEFORE the hit word, SFX exactly on the word.

### D. Topic objects (PLAN call, inside divya_codegen.py)
List 6 real things that belong to the topic. Not generic shapes.
| Topic | Objects |
|---|---|
| phone addiction | phone, notification, thumb scroll, battery, brain, chain |
| money / saving | coin, wallet, piggy bank, note, graph, lock |
| sleep | moon, pillow, eyelids, clock, stars, bed |
| space | planet, orbit, black hole, rocket, star, light beam |
| history | scroll, map, stone tablet, seal stamp, book page, sword |
| health / heart | heart, ECG line, pulse, blood drop, stethoscope, pill |
| food | plate, steam, knife, spoon, fire, ingredients falling |
| study | book, pen, highlighter, notebook lines, bulb, timer |
| climate | sun, thermometer, ice melt, smoke, tree, water rise |
| relationship | chat bubbles, heart, two circles, phone call, message tick |

### E. Motion idea per scene and per cut (PLAN call)
Write one sentence per idea, built from an object, tied to the hit word.
Pattern: **"When the voice says <hit word>, <object> does <action>, because <meaning>."**
- "When the voice says 89%, the battery fills to 89 and shakes once, because the phone is nearly full of notifications."
- Cut between scene 2 and 3: "buzz rings spread from the phone and reveal the next scene."
Pick one motion personality for the whole video:
| Personality | Easing | Durations | Fits |
|---|---|---|---|
| snappy | back / expo out | 0.2-0.35 s | facts, tech, hype |
| smooth | smoother / cubic in-out | 0.4-0.7 s | calm, health, nature |
| heavy | expo in + bounce land | 0.35-0.5 s | money, history, impact |
| glitchy | linear + jitter | 0.15-0.3 s | phone, warning, cyber |
| playful | elastic / wiggle | 0.3-0.5 s | funny, food, kids |

### E2. Main visual per scene (PLAN call) - NEW in v30
For every scene: the real object to draw, the text on it, how it arrives.
"When the voice says 'banned in 2012', an official notice slides up, the line 'prohibited' gets highlighted,
a red BANNED stamp slams down." -> new `vis_` function (or `library:document` if it fits exactly).
Recipe: silhouette -> material + texture -> 2-4 details with REAL text -> shadow -> one accent -> build-in motion.
See DIVYA_LONG_VIDEOS_BOOKS_TUTORIALS section 0 for the 7-question analysis.

### F. Turn each idea into code (CODE call)
How an idea becomes code - choose the building block by what the object DOES:
| Object does | Build with |
|---|---|
| grows / opens from a point | radial field `f_radial` + `_soft` + `_mix` |
| sweeps across | linear field `f_linear(angle)` |
| closes like lids / doors | barn field or `abs(y-.5)` mask |
| turns / flips / page | `_rot_plane` -> `_project` -> `_quad` (3D) |
| falls / lands | `_xf(dy=...)` with bounce easing |
| beats / breathes | `_xf(s=1+a*sin(...))` |
| spins / swirls | `Image.rotate` + scale, or clock field |
| melts / dissolves | `f_noise` field |
| draws a line (graph, ECG, path) | `ImageDraw.line` with points up to progress |
| counts | `motion_graphics.MG["counter"]` / `ring_percent` |
| glitches | row shifts with numpy `np.roll` |
Rules for the code: interface exact; p=0 gives A, p=1 gives B; stay inside safe box
(8% sides, 10% top/bottom); numpy not pixel loops; < 40 ms per frame; one comment per function
saying which sentence it serves.

### G. Test (fx_sandbox.py, automatic)
Checks (tr_, fx_ and vis_): only allowed imports, no file/network/exec, every function runs at 5-6 time points,
right size, transitions start on A and end on B, effects never leave the safe box, speed.

### H. Fix loop (automatic)
Send the exact rejection lines back ("fx_coin_drop: KeyError('bounce')"). Max 2 fixes.
Still failing -> `pick_transition()` / `pick_fx()` with the scene's tags, never a repeat family.

### I. Render
- Background layer never moves (or only a slow drift). Camera moves act on the content layer only.
- Order per frame: background -> content (with camera) -> motion graphics -> captions -> transition.
- Captions word-by-word, hit word in accent colour.

### J. Look at the frames (self-check)
Take 1 frame every 0.5 s. LLM (vision model if available, else rules) scores each scene 1-5:
fits the sentence / neat / nothing cut / different from last video. Any score < 4 -> fix that
scene (change idea or params) and re-render that scene only.

### K. Sound
Whoosh on transitions (start 100 ms before the cut), pop/click on hit words, riser before the
reveal, music ducked -12 dB under voice, final loudness -14 LUFS.

### L. Remember
Save the fingerprint from `codegen_result.json` (personality, custom functions, library families,
accent) in KV. Next video: pass the last 5 fingerprints as `recent_families`, choose a different
personality and accent if the mood allows.

---

## How Divya knows "this topic needs this code"
It does not look it up in a fixed table. It reasons in 3 hops every time:
**topic -> objects -> what the object does -> building block.**
Example "Why we feel phantom phone vibrations":
1. Objects: phone, buzz waves, pocket, brain, nerve signal.
2. Scene "you feel a buzz" -> buzz waves spread -> radial field with ripples -> `tr_buzz_rings`.
3. Hit word "89%" -> phone shakes -> small x-shake on the number -> `fx_buzz`.
4. Scene "your brain is tricked" -> signal travels along a nerve -> line drawn up to progress + glow.
Same steps for any topic, so the code is always new but never random.

---

## Wiring into Divya (for Muse)
1. Add steps D-H after the script and voice step: `python divya_codegen.py plan.json work/<video_id>/`.
2. Renderer imports `work/<video_id>/video_fx.py` and calls the passed functions at the planned
   times; for any name in `fallback_from_library`, call the library entry instead.
3. Put `codegen_result.json -> fingerprint` into KV after delivery (last 5 kept).
4. Set env: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (best free coder model available).
5. Log every rejection reason; after 20 videos, add the 3 most common mistakes to the SYSTEM rules.
