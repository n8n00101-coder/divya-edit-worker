# Divya: Rich visuals, long videos, all books, all tutorials

## 0. About "Hark's per-video bundles" (honest answer)
There is no hidden folder of per-video code for those 7 reference videos (gutka ban, male gaze, choice
blindness ...). Each Hark video's drawing code is written fresh for that video and is not kept as a library.
That is exactly the method Divya must copy. So instead of old bundles, this kit gives:
- `visuals_lib.py` - 18 rich visuals written the same way, as building blocks AND examples:
  india_map, world_dots, document (+ highlight + BANNED stamp), newspaper (masthead, headline, photo, columns, spin-in),
  typewriter_page, receipt, product_packet (+ twin pack), polaroid (flat face or real photo), filmstrip,
  balance_scale, bracket_bars, magnifier (real zoom of what is under it), photo_frame (real photo + Ken Burns),
  film_camera (+ flash), timeline_cards, speech_bubble, warning_sign, source_line, and `scene_bg()` with 9
  per-scene background colours (gradient + vignette + grain). All render, 0 errors, preview in visuals_preview.png.
- `fewshot_visuals.py` - 3 NEW visuals written from scratch for 3 topics (storm bolt, coin stack, bed + phone glow).
  All pass the sandbox. These are the examples the LLM sees.
- `divya_codegen.py` now plans and writes `vis_` functions too (the main visual of every scene), not only `tr_`/`fx_`.
- `fx_sandbox.py` now tests `vis_` functions: RGBA 720x1280, visible when built, inside safe box, has a build-in
  animation, speed. Speed limit is `FX_MAX_MS` env (default 40, Divya can set 200 for offline render).

### How Divya decides the visual for a sentence (analysis -> code)
1. Read the sentence. Find the NOUN that carries the meaning ("ban", "India", "packet", "study", "newspaper").
2. Ask: what real object would a person draw on a whiteboard for this? (ban -> official paper + stamp;
   India -> map with pins; study result -> bars with bracket; old fact -> typewriter page / newspaper).
3. Ask: what text must be ON the object to make it real? (headline, number, place name, date, brand).
4. Ask: how does it arrive in a way that means something? (stamp slams = rule; newspaper spins = news;
   pin drops = place; bracket draws = difference; coin stacks = saving).
5. If a library visual fits exactly, use it with new text/colours. Otherwise write a new `vis_` with the
   6-step recipe: silhouette -> material/texture -> 2-4 details/real text -> shadow -> one accent -> build-in motion.
6. Add `source_line` whenever a fact or number appears.
7. Change `scene_bg` colour on every section change (not every sentence).

## 1. LONG VIDEOS (5-10 min) - how to structure code and edits
Same render approach (frames with PIL -> ffmpeg), different STRUCTURE. Never render 10 minutes as one script.

### 1.1 Structure
| Part | Length | Job |
|---|---|---|
| Cold open | 0:00-0:30 | strongest visual + the question; promise what they will learn |
| Title card | 3-5 s | name + one-line promise |
| Chapter 1..N | 60-120 s each, 4-7 chapters | one question per chapter, ends with a mini cliffhanger to the next |
| Recap + payoff | 30-45 s | answer the opening question, 3 key points on screen |
| End screen | 15-20 s | 2 video suggestions, subscribe |

### 1.2 Code layout
```
long_video/
  outline.json        # chapters -> beats -> sentences (LLM)
  style.json          # one look for the whole video (font, accent, bg palette per chapter, personality)
  ch01/ scenes.json, video_fx.py, render -> ch01.mp4
  ch02/ ...
  assemble.py         # ffmpeg concat + chapter title cards + music bed + loudness
```
- Each chapter is its own render job (parallel, retry one chapter without redoing all).
- `divya_codegen.py` runs ONCE PER CHAPTER (new visuals per chapter), with the same style.json so the
  video looks like one piece. recent_families = families used in earlier chapters of THIS video.
- Chapter title card: big number + chapter name, 2-3 s, same transition family every time (this
  repetition is a signal, keep it consistent).
- YouTube chapters: write timestamps into the description from the chapter start times.

### 1.3 Pacing over minutes
- A visual change every 3-6 s (shorts: every 1.5-3 s). A NEW kind of visual every 20-30 s.
- Pattern interrupt every 45-60 s: scene_bg colour change, a zoom into a detail, a question on screen,
  a sound stinger, a real photo, or a 1-second silence.
- Energy curve: high at open, dip slightly in the middle of each chapter (explanation), rise at chapter end.
- Re-hook at 30 s, 1 min, and the middle: "but here is the strange part".
- Scene count: about 10-14 scenes per minute; 60-120 scenes for a 7-min video.
- Music: change track or intensity per chapter; duck -12 dB under voice; silence before big reveals.

### 1.4 B-roll vs code-drawn
- Code-drawn: anything abstract (numbers, process, comparison, maps, timelines, documents) - this is Divya's strength.
- Real photo/B-roll (via `photo_frame` with Ken Burns): real people, places, events, products - only from
  free/licensed sources (Pexels, Pixabay, Unsplash, Wikimedia Commons) with credit in description.
- Mix for long videos: about 70% code-drawn, 30% photo/B-roll; never more than 20 s without movement.

### 1.5 Keeping viewers watching (long form)
- Promise in first 15 s, payoff at end; show a "map" of the video (3 chapters icons) early.
- Open loops: start a story, finish it later.
- Every chapter answers one question and raises the next.
- Captions bigger, fewer words (2-4) per caption line on long videos too; word-by-word for Shorts only.

## 2. BOOKS - full list (the notes are in DIVYA_EDITING_HANDBOOK, ~18,000 words, our own words)
Core 6 (already in handbook): The Animator's Survival Kit (Richard Williams); The Illusion of Life
(Frank Thomas, Ollie Johnston); In the Blink of an Eye (Walter Murch); Grammar of the Edit (Roy Thompson,
Christopher Bowen); Design for Motion (Austin Shaw); The Non-Designer's Design Book (Robin Williams).
More, in priority order for our videos:
7. Grammar of the Shot - Roy Thompson, Christopher Bowen (framing, safe composition)
8. The Visual Story - Bruce Block (contrast, space, line, colour, rhythm; how visuals build intensity)
9. Thinking with Type - Ellen Lupton (typography)
10. Interaction of Color - Josef Albers (colour relationships)
11. Show Your Work / Steal Like an Artist - Austin Kleon (creative habits)
12. Cut by Cut - Gael Chandler (practical editing)
13. The Technique of Film and Video Editing - Ken Dancyger (editing theory + history)
14. Save the Cat! - Blake Snyder (story beats, useful for long-video structure)
15. Made to Stick - Chip and Dan Heath (why ideas stick: simple, unexpected, concrete, credible, emotional, stories)
16. Storyworthy - Matthew Dicks (storytelling, the 5-second moment)
17. The Elements of Typographic Style - Robert Bringhurst
18. Motion Graphic Design - Jon Krasner
19. Sound Design - David Sonnenschein (sound for picture)
20. YouTube Secrets - Sean Cannell, Benji Travis (platform, retention)
21. Information is Beautiful - David McCandless (data visuals)
22. The Visual Display of Quantitative Information - Edward Tufte (honest charts)
Most important chapters for 30-60 s + long explainers: Williams timing/spacing + easing; Thomas & Johnston
12 principles (squash, anticipation, follow-through, slow in/out, arcs, staging, exaggeration); Murch Rule
of Six (emotion first); Thompson & Bowen cut types and match cuts; Block contrast/affinity; Made to Stick
"unexpected" + "concrete"; Tufte data-ink. These are mapped to code in the handbook's Part 12 checklist.
Note: the books are copyrighted, so full text can't be copied in. Buying is NOT needed for Divya; the
handbook carries the ideas.

## 3. TUTORIALS - full list, in study order
### Stage 1: motion basics (week 1)
1. easings.net - every easing curve with graphs (https://easings.net)
2. Robert Penner's easing equations (http://robertpenner.com/easing/)
3. Alan Becker - "12 Principles of Animation" series (YouTube, search the title)
4. Material Design motion: easing and duration (https://m3.material.io/styles/motion/overview)
5. Freya Holmer - "The Beauty of Bezier Curves" (YouTube)
### Stage 2: motion design craft (week 2)
6. School of Motion - free articles and tutorials (https://www.schoolofmotion.com)
7. Ben Marriott - YouTube channel (motion design, transitions, shape animation)
8. Jake in Motion - YouTube (expressions, procedural motion ideas)
9. ECAbrams - YouTube (motion graphics tips)
10. Kurzgesagt - "How we make our videos" / behind-the-scenes (YouTube)
11. Vox - explainer graphics breakdowns (YouTube, search "how Vox makes explainer")
### Stage 3: editing, pacing, retention (week 3)
12. Every Frame a Painting - YouTube (editing, cuts, visual comedy)
13. Thomas Flight - YouTube (film editing essays)
14. Paddy Galloway - YouTube (retention analysis of big channels)
15. Film Riot - YouTube (practical editing and sound)
16. YouTube Creator Academy / Creator Insider (official retention and Shorts guidance)
### Stage 4: typography, colour, layout (week 4)
17. Butterick's Practical Typography (https://practicaltypography.com)
18. Refactoring UI tips (Steve Schoger, free tips on X/YouTube)
19. Adobe Color - palettes and harmony rules (https://color.adobe.com)
20. Coolors - palette generator (https://coolors.co)
### Stage 5: sound
21. Freesound - free SFX (https://freesound.org) with licence check
22. YouTube Audio Library - free music (inside YouTube Studio)
23. "Sound design for video" tutorials - Film Riot, Andrew Kramer (Video Copilot) sound episodes
### Stage 6: code-based editing (Divya's own tools)
24. FFmpeg filters documentation (https://ffmpeg.org/ffmpeg-filters.html)
25. Pillow (PIL) documentation (https://pillow.readthedocs.io)
26. NumPy documentation (https://numpy.org/doc/stable/)
27. Manim Community docs - math animation engine, great source of animation ideas (https://docs.manim.community)
28. 3Blue1Brown - YouTube (how code-made animation explains ideas)
29. The Coding Train - YouTube (generative and procedural animation, p5.js ideas port easily to numpy)
30. Inigo Quilez articles - distance functions and smooth shapes (https://iquilezles.org/articles/)
31. The Book of Shaders - procedural patterns, noise, masks (https://thebookofshaders.com)
32. edge-tts project page (https://github.com/rany2/edge-tts) - word timing (WordBoundary)

### Daily learning loop for Divya (R45)
- Each day: take ONE tutorial from this list (in order), write 5 rules from it in Divya's own words into the
  learning store, and write ONE new `vis_` or `tr_` function that uses the idea, tested by fx_sandbox.
- Keep only functions that pass the sandbox AND score >= 4 on the frame check. Add the best ones to the
  few-shot pool (max 12, rotate so the model keeps seeing different styles).
