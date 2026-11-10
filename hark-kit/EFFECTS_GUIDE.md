# Divya Effects Guide v26 — when and how to use each effect in effects.py

## 0. The 7 golden rules (from motion-design and film-editing practice)
1. Every effect must MEAN something. If the voice does not justify it, delete it.
2. One hit per sentence. One effect on screen at a time. Calm between hits.
3. Visual lands 2-3 frames (80 ms) before the spoken word; sound lands on the word.
4. Ease everything. Nothing linear except glitch and typewriter.
5. Enter fast (0.25-0.45 s), exit faster (0.2-0.3 s), hold long enough to read (min 1 s).
6. Background never moves with the camera. Content stays in the safe box (8% / 10%).
7. One video = one motion personality. Different videos = different personalities.

## 1. Map: meaning of the hit word -> effect
| Hit word / line meaning | Enter | Emphasis | Sound |
|---|---|---|---|
| A number ("96 times") | pop_in | count_up + punch | pop / tick |
| A percent ("89%") | fade_in | ring_fill + glow | rising tone |
| Shock / twist ("but", "never") | zoom_in_blur | punch 1.10 + flash (0.18 s) | hit / boom |
| Warning / danger | glitch_in | shake + circle_draw (red) | alarm blip |
| A list (3 things) | stagger(slide_in) | underline_draw on each | click per item |
| Compare A vs B | slide_in left + right | bar_grow | swoosh |
| Growth / rise | rise_in | draw_on_line (chart) | rising whoosh |
| Drop / fall | drop_in | shake small | thud |
| Time / clock / history | typewriter | pulse | ticking |
| Money | spin_in / flip_in | glow gold | coin |
| Health / body | fade_in | pulse (heartbeat) | heartbeat |
| Space / science | iris_in | glow | low hum |
| Funny | drop_in | wiggle | boing |
| Calm fact | fade_in | none (push_in only) | none |

## 2. Map: topic -> transition family (pick one family per video)
| Topic | Transition |
|---|---|
| Phone, apps, social media | screen_swipe, glitch |
| Tech, AI, hacking | glitch, whip |
| Space, science | zoom_through, iris |
| Money, business | coin_flip, wipe_bar |
| Health, body, mind | heartbeat, crossfade |
| History, facts, retro | paper_tear, wipe_in |
| News, bold claims | wipe_bar, push |
| Nature, art, calm | ink_spread, crossfade |
| Story / list videos | push |
Transition length 0.3-0.45 s, always on a sentence boundary with a whoosh.

## 3. Motion personality (style.json "motion")
- snappy: out_back, fast enters, punches. Facts, shocks, youth topics.
- smooth: smoother/out_cubic, long holds, push_in. Calm, emotional, science.
- glitch: linear + glitch_in/tr_glitch. Tech, phones, warnings.
- paper: out_cubic, wipe_in, paper_tear, grain texture. History, stories.
- typewriter: typewriter text, ticks. Time, mystery, documents.
- bouncy: out_bounce, drop_in, wiggle. Funny, kids.

## 4. Camera
- push_in 1.00 -> 1.06 per scene, content layer only. Never on scenes < 1.5 s.
- drift ±24 px for calm scenes instead of zoom (alternate, never both).
- Run fit_safe(layer, 1.10) on every element before rendering.

## 5. Neatness checklist (run on frames before delivering)
- Nothing touches the safe box edge. No overlapping text.
- Max 2 accent colors, 1 font pair, 1 effect at a time.
- Headline readable in 1 s (max 6 words on screen).
- Same keyword color and position every scene.
- Every visual is about the sentence being spoken. No mascot.
- Score every scene 1-5 (clear, on-time, in-frame, on-topic, neat). < 4 -> fix.

## 6. Study list (for continuous learning R45 — use these as rule sources)
Books
- "The Animator's Survival Kit" — Richard Williams (timing, spacing, easing, anticipation)
- "In the Blink of an Eye" — Walter Murch (when to cut; the Rule of Six: emotion > story > rhythm)
- "The Illusion of Life" — Thomas & Johnston (Disney's 12 principles of animation)
- "Design for Motion" — Austin Shaw (motion design fundamentals)
- "Grammar of the Edit" — Roy Thompson & Christopher Bowen (cut types, transitions, pacing)
- "The Non-Designer's Design Book" — Robin Williams (contrast, alignment, repetition, proximity)
Free tutorials / references
- easings.net — every easing curve with formulas (used in effects.py)
- School of Motion free tutorials and blog (schoolofmotion.com) — motion principles
- Google Material Design "Motion" guidelines (m3.material.io) — durations and easing
- Ben Marriott YouTube channel — motion design and kinetic typography
- Kurzgesagt / Johnny Harris / Vox style breakdowns on YouTube — explainer pacing and infographics
- ffmpeg filters documentation (ffmpeg.org/ffmpeg-filters.html) — audio ducking, loudnorm
Turn each chapter into rules in this same table format, not long text.
