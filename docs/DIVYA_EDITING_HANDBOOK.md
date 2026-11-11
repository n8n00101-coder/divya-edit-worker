# The Divya Editing Handbook

### Animation, editing, motion design, typography, sound and retention for 20-60 second vertical explainer shorts

**Audience:** Divya, an LLM-driven video editor that renders 720x1280 vertical shorts at 30 fps with Python (PIL, numpy, ffmpeg). Divya's house style: dark background, bold headline with one yellow keyword, flat icon infographics, word-by-word captions, voiceover, whoosh and pop sound effects, and an end card.

**What this handbook is:** a working manual. It takes the core ideas from the classic books on animation, film editing, motion design and graphic design, explains them in plain words, and turns each idea into numbers Divya can type into code. Nothing here is copied from the books. Every idea is restated in this handbook's own words and credited to the book and author it comes from, so Divya knows where to look for more depth. Where a number is given, it is a working default for shorts made in Divya's style, not a quote from any book.

**How to read it:** Parts 1 to 11 each cover one body of knowledge, in numbered chapters. Every chapter ends with an "Apply in code" note. Part 12 is the master checklist and a table that maps each principle to the effect families in `effects_lib` and the transition families in `transitions_lib`.

---

## Part 0. Shared conventions used throughout

All later chapters use these units.

### 0.1 Time units

- The project runs at **30 frames per second**. One frame is **33.3 ms**.
- Conversions:

| Frames | Milliseconds | Feels like |
|---|---|---|
| 1 | 33 | a single flash, barely seen |
| 2 | 67 | a hard snap |
| 3 | 100 | a fast pop |
| 4 | 133 | a quick blink |
| 6 | 200 | a crisp UI move |
| 8 | 267 | a confident entrance |
| 9 | 300 | a standard entrance |
| 12 | 400 | a relaxed move |
| 15 | 500 | a slow, deliberate move |
| 18 | 600 | a heavy or dramatic move |
| 24 | 800 | slow camera drift territory |
| 30 | 1000 | one full second |

- A 30-second short is 900 frames; a 60-second short is 1800.

### 0.2 Space units

- The canvas is **720 px wide, 1280 px tall**. Centre is (360, 640).
- **Safe zones for vertical platforms.** Reels, Shorts and TikTok draw their own interface over the video. Keep important content out of these regions:
  - Top 140 px (status bar, platform tabs, "Reels" label).
  - Bottom 260 px (caption text of the post, username, music ticker).
  - Right 110 px from roughly y = 600 to y = 1150 (like, comment, share buttons).
  - Left 40 px margin as basic breathing room.
- So the **working safe area** is roughly x = 40 to 610, y = 140 to 1020. The headline lives in the upper third of that box, the infographic in the middle, and captions in the lower third, ending above y ≈ 1020.
- A **grid unit** of 8 px keeps spacing consistent. Margins, gaps and paddings should be multiples of 8 (16, 24, 32, 48, 64).

### 0.3 Easing functions as code

The libraries already ship these curves in the `EASES` dictionary: `linear`, `smooth` (a quintic smoothstep, slow at both ends), `expo` (fast start, long gentle settle), `back` (overshoots its target a little, then settles), `elastic` (springs past and wobbles) and `bounce` (hits the end and rebounds). Every animated property in this handbook is written as:

```
q = clamp((t - start) / duration, 0, 1)   # progress 0..1
v = from + (to - from) * EASES[name](q)
```

When this handbook says "ease out", it means fast at the start and slow at the end: use `expo` or the decelerating half of `smooth`. "Ease in" means slow start, fast end: use `q*q` or `q**3`. "Ease in-out" means both: `smooth`. "Overshoot" means `back`. "Spring" means `elastic`.

### 0.4 Layers and timing

Every visual on screen is a layer: background, headline, keyword, icon group, caption line, progress bar, end card. Each layer has a `start` time, a `duration` for its entrance, a hold, and an optional exit. The effect functions in `effects_lib` take the shape `fn(layer_image, t, start, duration)` and return a transformed RGBA layer. Transitions in `transitions_lib` take two full frames and a progress value. Keep that model in mind; every chapter ends by telling Divya which layer to touch, when, and by how much.

---

## Part 1. Lessons from *The Animator's Survival Kit* (Richard Williams)

Richard Williams wrote his book as a practical course for character animators, built from decades of studio work and from what he learned from the great Disney and Warner animators. Its central message is that animation is about **timing and spacing**, and that the difference between stiff and alive motion lives in small decisions about how far a thing moves between each drawing. Divya does not draw characters, but every icon, word and card it moves obeys the same physics of perception. This part restates the book's main teachings and translates them for flat infographic shorts.

### Chapter 1.1 Timing versus spacing

Williams separates two ideas that beginners blur together.

- **Timing** is how long an action takes: how many frames from start to finish. A move of 9 frames feels quick; the same move over 24 frames feels slow and careful.
- **Spacing** is how the distance is divided among those frames. Two moves can both take 12 frames, yet one looks mechanical (equal steps every frame) and the other looks natural (tiny steps at the start, big steps in the middle, tiny steps at the end).

The book's key insight is that spacing, not timing, is what the eye reads as weight, intent and life. Timing sets the tempo; spacing sets the character.

**Shorts example.** A lightbulb icon slides up 120 px into place over 10 frames.

- Linear spacing: 12 px per frame, every frame. It looks like a slide on a conveyor belt. It starts and stops with a jolt.
- Ease-out spacing: roughly 30, 24, 18, 14, 10, 8, 6, 4, 3, 2 px on successive frames (sum ≈ 120). It arrives fast and settles softly, like something placed by a confident hand.

**Apply in code.**
- Never use `linear` for position, scale or rotation of a visible object unless you are deliberately making something feel robotic (a loading bar, a ticker, a conveyor).
- Default entrance spacing: `expo` or `smooth` over 8-12 frames.
- When reviewing a move, print the per-frame deltas. If the largest step is more than about 40 px on a 720-wide canvas, the eye starts to see a jump rather than motion; add motion blur (see Chapter 2.11) or lengthen the move by 2-3 frames.

### Chapter 1.2 Keys, extremes and breakdowns

Williams describes a planning method borrowed from classic studios. First you decide the **keys**: the storytelling poses that, on their own, tell what happens. Then the **extremes**: the furthest points of each movement. Then the **breakdowns**: the in-between position that decides how the motion travels from one extreme to the next (does the arm go straight, or swing in an arc, or lag behind?). Only after that come the plain in-betweens.

The lesson for an editor is to **plan by states, not by frames**. Decide what the screen must look like at each important moment, then decide how it gets there.

**Shorts example.** A 4-second beat explaining "Your phone tracks your sleep."

- Key A (0.0 s): headline "Your phone TRACKS your sleep", "TRACKS" in yellow, empty middle.
- Key B (0.8 s): phone icon in centre, at full size.
- Key C (2.0 s): moon icon and a small sleep chart orbiting beside the phone.
- Key D (3.6 s): chart bars filled, number "7h 12m" popped in.
- Breakdowns: between A and B the phone rises from below with a slight overshoot (that overshoot is the breakdown choice); between B and C the moon arcs in from upper right rather than sliding straight.

**Apply in code.**
- Write every beat's layout first as a list of key states with times, for example `keys = [(0.0, "headline"), (0.8, "phone_in"), (2.0, "moon_chart"), (3.6, "value")]`.
- Tie each key time to a spoken word timestamp (the word that names the thing).
- Only then choose effects for the transitions between keys.

### Chapter 1.3 Timing charts

In hand-drawn animation, the animator writes a small chart on each key drawing: a line from one key to the next, with tick marks showing where each in-between falls. Ticks bunched near a key mean the motion slows there (cushioning); evenly spaced ticks mean constant speed. The chart is a compact, visual description of spacing.

For Divya, the timing chart is just the sampled easing curve.

**Apply in code.**
- A helper that prints a timing chart is valuable for debugging:

```
def chart(ease, n):
    return [round(EASES[ease](i/(n-1)), 3) for i in range(n)]
# chart("smooth", 9) -> [0, .018, .104, .26, .5, .74, .896, .982, 1]
```

- Read the chart like an animator: `smooth` bunches ticks at both ends ("slow in and slow out"); `expo` bunches them at the end only; `back` goes past 1.0 before returning.
- When a move "feels wrong", look at the chart before changing the duration. Usually the spacing, not the timing, is the problem.

### Chapter 1.4 Slow in and slow out (cushioning)

Williams spends a lot of time on how objects accelerate away from a pose and decelerate into the next. Real things have mass, so they cannot reach full speed instantly or stop dead. The more frames you spend near the start and end of a move, the heavier and more controlled it looks. Remove the cushion and the object looks weightless or mechanical.

There are three common flavours:

1. **Ease out only (fast in, soft landing).** For things arriving: icons, words, cards. It reads as "decisive". Use `expo`.
2. **Ease in only (soft start, fast exit).** For things leaving: an icon accelerating off screen. It reads as "gone". Use `q**2` or `q**3`.
3. **Ease in and out.** For things that move from one resting spot to another while staying on screen: a chart sliding left to make room. Use `smooth`.

**Concrete numbers for shorts.**

| Move | Frames | Curve |
|---|---|---|
| Icon entrance, 100-200 px | 8-10 | expo or back |
| Word pop (caption) | 3-5 | back |
| Headline slide in | 9-12 | expo |
| Layout reshuffle on screen | 12-15 | smooth |
| Exit off screen | 6-8 | ease in (q³) |
| Slow background drift | whole beat | linear or very gentle smooth |

**Apply in code.** Exits are shorter than entrances by about one third. Something arriving deserves attention; something leaving should get out of the way.

### Chapter 1.5 Arcs

Williams stresses that living things almost never move in straight lines. Heads turn in arcs, arms swing in arcs, a thrown ball follows a curve. Straight-line motion is a sign of machines.

**Shorts example.** A coin icon flies from the headline area to a piggy bank icon in the middle. A straight diagonal looks like a cursor. Instead, move it on a parabola: x changes evenly with `smooth`, y follows `smooth` plus an upward bump of about 80 px at the midpoint.

**Apply in code.**

```
q = EASES["smooth"](p)
x = x0 + (x1 - x0) * q
y = y0 + (y1 - y0) * q - 80 * math.sin(math.pi * q)   # arc height 80 px
```

- Arc height of 10-20% of the travel distance looks natural. Above 35% looks like a throw.
- Add a small rotation that follows the direction of travel (±8 to ±15°) for thrown objects.

### Chapter 1.6 Anticipation

Before a big action there is a small action in the opposite direction. A jumper crouches before leaping; a pitcher winds back before throwing. Williams shows that anticipation tells the audience "something is about to happen, watch here", which is why it makes fast actions readable.

**Shorts example.** A "WARNING" badge is about to burst in. Before it grows, the empty circle that holds it shrinks to 92% for 3 frames, then explodes to 110%, then settles to 100%. The tiny shrink is the anticipation.

**Concrete numbers.**
- Anticipation size: 5-10% of the main action, opposite direction.
- Anticipation length: 2-5 frames (67-167 ms). The bigger the action, the longer the anticipation, up to about one third of the main move.
- For a slide in from the left, the anticipation can be the element appearing 10 px to the right of its start position and drifting back left for 3 frames before shooting right.

**Apply in code.** Use the `back` curve for an exit (it pulls backward before going), or build an explicit three-segment curve: `[0, 3 f] → 0.93`, `[3, 9 f] → 1.10`, `[9, 13 f] → 1.00`.

### Chapter 1.7 Overshoot, follow-through and settle

When a moving thing stops, parts of it carry on. Hair keeps swinging, a coat flaps, a heavy belly wobbles. Williams calls these follow-through and overlapping action. For flat graphics, the most useful form is **overshoot and settle**: the object passes its target slightly and comes back.

**Concrete numbers.**
- Overshoot amount: 4-12% in scale, or 6-20 px in position.
- One overshoot is "confident". Two diminishing overshoots is "springy, playful". Three or more is "cartoon jelly" and should be rare.
- Settle time: 4-8 frames after the peak.

**Apply in code.** `back` gives one gentle overshoot (about 10%). `elastic` gives several diminishing ones; reserve it for one hero element per video. The `jello` and `squash` effects in `effects_lib` are follow-through effects that can be layered on after an entrance lands.

### Chapter 1.8 Overlapping action and drag

Different parts of a body move at different times. When a character turns, the head leads, the torso follows a few frames later, the arms drag behind. Williams uses the idea of parts "breaking" their joints and catching up.

For a group of elements, overlapping action means **staggering**. A row of four icons should not land on the same frame. The first leads, and each one after it lags by a few frames, like a team that follows a leader.

**Concrete numbers.**
- Stagger between sibling elements: 2-4 frames (67-133 ms).
- Stagger between letters in a kinetic headline: 1-2 frames.
- Stagger between a parent and its children (a card and the text inside it): 3-6 frames, children after parent.
- Total stagger spread should stay under about 15 frames, or the group stops reading as one unit.

**Apply in code.**

```
for i, icon in enumerate(icons):
    start_i = beat_start + i * 3/30
    layer = fx_pop(icon, t, start_i, 9/30)
```

### Chapter 1.9 Weight

Williams spends a lot of the book on weight: how a heavy object is slow to start, slow to stop, and squashes on landing, while a light object starts and stops easily and floats. Weight is communicated by timing (how long the move takes), by spacing (how much cushion), and by the reaction at contact.

**Shorts mapping.**

| Feeling | Frames for 200 px move | Curve | Landing reaction |
|---|---|---|---|
| Feather, light idea, soft fact | 15-18 | smooth | drift, no bounce |
| Normal icon | 9-12 | expo | tiny back overshoot |
| Heavy, important number | 6-8 falling, then stop | ease in (q²) on fall | squash 10-15% for 2 f, plus camera shake 4-6 px for 4-6 f, plus low "thud" |
| Rubber, playful | 10 | bounce | 2 rebounds |

**Apply in code.** The `drop` effect plus `squash` plus a brief `shake` on the whole frame is Divya's "heavy" recipe. Use it for the one big stat in a video.

### Chapter 1.10 Walks, cycles and loops applied to icons and text

The heart of the book is the walk: a repeating cycle where each step has a contact pose, a down pose (weight sinks), a passing pose, and an up pose (weight rises). Williams shows that a walk cycle is defined by its rhythm, and that tiny changes in the up-down pattern change the personality completely: a bouncy walk, a sneaky walk, a tired walk.

Divya has no legs to animate, but **cycles** are everywhere in shorts: idle motion on icons, breathing on a hero number, pulsing on a call-to-action, a looping arrow. The walk lesson translates as: **a cycle needs a rhythm, an up and a down, and a personality.**

**Cycle library for Divya.**

| Cycle | Period | Amplitude | Use |
|---|---|---|---|
| Float (bob up and down) | 1.6-2.4 s | 4-8 px | idle icons, keeps screen alive |
| Breathing scale | 1.2-2.0 s | 2-4% | hero object while voice explains it |
| Pulse | 0.6-1.0 s | 5-8% | call to action, warning |
| Heartbeat (double beat) | 0.9-1.1 s | 8% then 5% | health topics, emotion |
| Wiggle | 0.3-0.5 s, 2-3 cycles | 4-8° | "look here", error, funny |
| Spinner | 1.0-1.5 s per turn | 360° | loading, process |
| Arrow nudge | 0.8 s | 8-12 px along arrow | point to next item |

**The walk lesson about phase.** In a walk, the arms are opposite to the legs. Apply this to groups: if three icons float, offset their phases (0, 0.33, 0.66 of the period) so they bob like a group of living things rather than one rigid block.

**Apply in code.** `float`, `pulse` and `heartbeat` in `effects_lib` take an amplitude and a period. Always add a random phase per element. Never let more than two cycle types run at once on screen, and never let a cycle compete with an entrance: start cycles only after the entrance has fully settled.

### Chapter 1.11 Holds and moving holds

Williams warns that a dead hold (a completely frozen drawing) quickly looks like the film has stopped. Studios used "moving holds": the character keeps a tiny amount of drift so it stays alive while the audience reads the pose.

**For shorts**, a dead screen for more than about 1 second reads as a frozen video. Viewers swipe.

**Apply in code.**
- During every hold, at least one of these must be moving: a slow push-in on the whole frame (1-3% scale across the hold), a float on icons, a caption word popping, a progress element growing.
- The `push` and `pull` effects (slow camera zoom) are ideal for moving holds: 2-4% scale change over 2-4 seconds.

### Chapter 1.12 Accents and the rhythm of action

Williams talks about the "accent": the sharp moment in an action that the audience should feel. A hit, a snap, a punch. Accents land best when the motion before them is slower, so the change of speed is felt. He also notes that timing to a beat, whether music or dialogue, makes animation feel intentional.

**Shorts example.** The voice says "...and it costs NOTHING." The word "NOTHING" is the accent. Build up: the previous 10 frames have slow drift. On the first frame of "NOTHING": a 1-frame white flash at 30% opacity, the word scales from 130% to 100% in 4 frames, a pop SFX, a 4 px shake for 4 frames.

**Apply in code.** Mark accent words in the script (numbers, negatives, surprising words, the keyword). Allow one accent every 3-5 seconds at most; accents lose power when everything is accented.

### Chapter 1.13 Lip sync becomes word sync

The book treats lip sync with care: mouth shapes should be slightly ahead of the sound, because the eye needs a moment to register a shape and the brain expects to see a cause before the effect. Animators commonly lead the sound by one or two frames.

**For Divya**, this becomes the caption and visual lead rule.

**Apply in code.**
- Caption word highlight: lead the audio by 1-2 frames (33-67 ms). Never lag.
- An icon that the voice names: start its entrance 3-6 frames before the word, so it is already landing when the word is heard.
- A pop SFX on an icon: place it on the frame the icon reaches full size, not on the first frame of movement.

---

## Part 2. The twelve principles from *The Illusion of Life: Disney Animation* (Frank Thomas and Ollie Johnston)

Frank Thomas and Ollie Johnston were two of the core Disney animators, and their book records how the studio learned, over years of trial, what makes drawings feel alive and believable. Its best-known contribution is a list of twelve principles of animation. The book presents them as tools for creating the illusion of thinking, feeling characters. This part restates each principle in plain words, then gives Divya a shorts example and parameter ranges.

A general note: the book's deeper point is that the principles serve **appeal and believability**, not decoration. A principle applied without a reason makes motion fussy. For every effect Divya applies, it should be able to say which principle it serves and why that matters to the viewer's understanding.

### Chapter 2.1 Squash and stretch

**Idea.** An object changes shape under force while keeping roughly the same volume. A ball flattens when it hits the floor and stretches when it moves fast. This shows the object's material (rigid, soft, rubbery) and makes fast motion readable.

**Shorts example.** A notification bell icon drops into the frame. On impact it squashes to 115% width and 87% height for 2 frames, rebounds to 95% width and 106% height for 2 frames, then settles at 100%. The bell now reads as a physical, slightly soft object, and the landing has punch.

**Parameter ranges.**
- Squash on impact: width ×1.08-1.20, height ×0.84-0.93 (keep width × height ≈ 1).
- Stretch during fast travel: along the direction of motion ×1.05-1.25, across it ×0.85-0.95.
- Duration: impact squash 2-3 frames, recovery 3-5 frames.
- Rigid objects (a lock, a shield, a building, a bank card): use squash below 5% or not at all. Soft objects (a heart, a drop, a cartoon blob, a coin landing): up to 20%.
- Text: up to 8%. More than that distorts letterforms and hurts reading.

**Apply in code.** `squash(amt)` in `effects_lib` applies `sx = 1 + amt*env`, `sy = 1 - amt*env`. Use `amt` 0.08-0.15 for icons, 0.04-0.06 for text. The `stretch` effect is for fast entries along one axis. Anchor squash at the bottom of the object for landings, so it squashes into the floor rather than shrinking from the centre.

### Chapter 2.2 Anticipation

**Idea.** A preparatory move tells the audience an action is coming and where to look. Without it, sudden actions are missed or feel like glitches. The book notes that the amount of anticipation can be tuned to the surprise you want: big anticipation for clear storytelling, almost none for a deliberate shock.

**Shorts example.** Before a pie chart spins to reveal "73%", it rotates backwards 8° over 4 frames, then whips forward. Before a word flies off screen to the left, it leans right 10 px.

**Parameter ranges.**
- Size: 5-12% of the main action, in the opposite direction.
- Time: 2-6 frames. Comedic or very large actions: up to 10 frames.
- Shock moments (a "jump scare" fact): 0-1 frames, but pair with a big SFX so the viewer is not lost.

**Apply in code.** `back` easing contains built-in anticipation when used for exits (`1 - back(1-q)` shape) and overshoot when used for entrances. For explicit control, use piecewise keys: 0 → −0.1 (3 f) → 1.05 (6 f) → 1.0 (4 f).

### Chapter 2.3 Staging

**Idea.** Present each idea so it is unmistakably clear: one idea at a time, in a clear silhouette, in the place where the audience is already looking, against a background that does not compete. The book compares this to stage direction in theatre.

**Shorts example.** Explaining "UPI processes 12 billion payments a month." Bad staging: headline, a phone, a bank, a rupee symbol, a chart and a map all on screen. Good staging: the headline at top; a single phone in the middle; when "12 billion" is spoken, the phone shrinks and moves up and a giant "12B" takes centre; everything else is dimmed to 35% opacity.

**Parameter ranges.**
- Hero element size: 35-55% of the canvas width (250-400 px on a 720 canvas).
- Secondary elements: 40-60% of the hero's size.
- Dim non-focus elements to 30-50% opacity, or desaturate them.
- Maximum distinct objects visible at once: 3-5 (not counting the headline and captions).
- Keep the hero inside the centre column x = 120-600 and vertical band y = 380-900.

**Apply in code.** Give every beat one `hero` layer. When focus shifts, animate the old hero to a secondary scale (`scale` effect, 0.6×, 10 frames, smooth) and opacity (to 0.4) while the new hero enters.

### Chapter 2.4 Straight ahead action and pose to pose

**Idea.** Two ways to animate. Straight ahead: draw frame after frame in order, discovering the motion as you go; it is good for chaotic, flowing things like fire, water and splashes. Pose to pose: plan the key poses first, then fill in; it is good for clear, controlled acting. Studios mixed both.

**Shorts mapping.**
- **Pose to pose** is Divya's default: key states tied to words, eased transitions between them (see Chapter 1.2).
- **Straight ahead** corresponds to procedural, simulated motion: particles, confetti, noise-driven handheld drift, glitch noise, sparks. These are computed per frame from a rule or a random seed, not from keys.

**Parameter ranges.**
- Particle bursts: 12-40 particles, life 10-20 frames, initial speed 6-18 px/frame, gravity 0.4-0.8 px/frame², fade out over the last 40% of life.
- Handheld noise: 2-6 px amplitude, 0.5-2 Hz smoothed noise, plus 0.2-0.6° rotation.

**Apply in code.** Keep these two styles in separate layers. Keyframed layers must be deterministic; procedural layers must use a fixed seed per video so re-renders match.

### Chapter 2.5 Follow-through and overlapping action

**Idea.** When a body stops, loose parts keep moving and settle later. Different parts move at different rates. Nothing in a living body stops all at once. The book also describes "drag", where parts lag behind the main mass.

**Shorts example.** A card with a title and three bullet icons slides in from the right. The card lands at frame 10. The title inside lands at frame 12 with a small overshoot. The icons land at 14, 16 and 18. The card's drop shadow catches up last at frame 20. The group reads as one object with a living, flexible quality.

**Parameter ranges.**
- Child lag behind parent: 2-6 frames.
- Overshoot on followers: 3-8% scale or 4-12 px position.
- Secondary wobble after landing (rotation): ±2-5°, decaying over 8-12 frames.

**Apply in code.** Use `swing(deg)` for hanging objects (a price tag, a badge on a string): it decays a rotation around the top edge. Use `jello` for a soft wobble after an icon lands. Stagger child layers with a loop over start times.

### Chapter 2.6 Slow in and slow out

**Idea.** Motion is concentrated in the middle of an action; the extremes get more frames so the poses are seen and the motion feels physical. The book explains that this was how the studio made key poses register with audiences.

**Apply in code.** The numbers are the same as Chapter 1.4: entrances `expo` or `smooth` over 8-12 frames, on-screen moves `smooth` over 10-15, exits ease-in over 6-8, camera moves `smooth` over 20-60. Test: sample the curve at 10 points; at least 3 should sit within 10% of the start or end value.

### Chapter 2.7 Arcs

**Idea.** Natural motion follows curved paths. Mechanical straight lines feel lifeless. Even simple movements like a head turn dip slightly along an arc.

**Shorts example.** In a "money flows from you to the bank" graphic, rupee coins travel along curved arcs from the user icon to the bank icon, each coin's arc slightly different (heights of 60, 80, 100 px) so the stream looks organic.

**Parameter ranges.**
- Arc height: 10-25% of the travel distance.
- Rotation along the path: tangent angle × 0.3-0.6 (follow the path partly, not fully).
- For icons swinging into place, rotation of 10-20° that settles to 0 while landing.

**Apply in code.** Parameterise position with a quadratic Bézier: `P = (1-q)²·A + 2(1-q)q·C + q²·B`, with the control point C placed above the midpoint of A and B.

### Chapter 2.8 Secondary action

**Idea.** A smaller action that supports the main one adds richness and tells more about the character's state, without stealing attention. A character walking sadly might also kick a stone. The main action must still dominate.

**Shorts example.** The main action: a big "₹500" number pops in. Secondary action: three small sparkle shapes twinkle around it for 12 frames; a subtle yellow glow pulses once behind it. The number is still the story; the sparkles say "this is good news".

**Parameter ranges.**
- Secondary elements at 15-35% of the hero's visual weight (size × contrast).
- Start 2-6 frames after the main action, end before the next main action.
- Secondary motion amplitude roughly half of what it would be as a main action.

**Apply in code.** Secondary actions are small cycles (`glow`, `pulse`, `float`, sparkle particles). Mark them `role="secondary"` so the scheduler can drop them when the screen is busy.

### Chapter 2.9 Timing

**Idea.** The number of drawings for an action decides how it feels: quick or slow, light or heavy, eager or tired. The book also discusses how timing reveals personality and emotion, and how a pause before or after an action changes its meaning.

**Shorts timing table.**

| Intent | Entrance frames | Pause after | Example |
|---|---|---|---|
| Urgent, exciting | 4-6 | 3-6 f | "BREAKING", "STOP" |
| Confident, factual | 8-10 | 6-10 f | stat, icon |
| Calm, reassuring | 12-18 | 10-15 f | health tip |
| Dramatic reveal | 3 f anticipation + 6 f move | 15-20 f hold | the big answer |
| Comic | fast move 4 f, then hold 10 f | | punchline |

**Apply in code.** Pick a "tempo profile" for the whole video based on the topic (news = fast, wellbeing = calm) and scale all entrance durations by a factor 0.7-1.3. Keep the profile consistent: mixing tempos feels like two different editors.

### Chapter 2.10 Exaggeration

**Idea.** Push the essence of an action further than reality so it reads clearly. The book stresses that exaggeration is not distortion for its own sake; it is making the true thing clearer and more convincing.

**Shorts example.** The voice says "prices DOUBLED". The price tag does not just change number; it scales up to 140%, squashes on landing, shakes for 4 frames, and the bar chart beside it shoots up past the top margin before settling at its true height.

**Parameter ranges.**
- Scale overshoot on hero accents: 115-140% before settling.
- Shake on accents: 6-12 px, 4-8 frames.
- Colour exaggeration: bump the keyword's saturation and brightness to the palette maximum.
- Use strong exaggeration on at most 1-3 moments per video.

**Apply in code.** `punch(amt)` (amt 0.15-0.4) plus `shake(px)` are Divya's exaggeration tools. Tie them to accent words only.

### Chapter 2.11 Solid drawing

**Idea.** Drawings should feel three-dimensional and have weight, volume and balance, even in a flat style. Avoid "twins", where both sides of a figure are mirror images and the pose feels stiff.

**Shorts mapping for flat icons.**
- Give icons a consistent light direction: a soft shadow offset to the lower right (6-12 px, 30-45% opacity, 8-16 px blur), and the same on every element.
- Avoid perfectly symmetrical layouts of identical icons; vary sizes slightly or arrange on a gentle curve.
- In 3D transitions and `flip3d` effects, keep the perspective consistent (the libraries use one field of view; do not mix wildly different depths).
- Motion blur: for any move faster than about 30 px/frame, apply a directional blur of 0.5-1× the per-frame distance, or blend 2-3 sub-frames. It makes fast motion read as continuous rather than strobing.

**Apply in code.** A global `SHADOW = (8, 10, 12, 0.35)` (dx, dy, blur, alpha) applied to all icon layers. A `motion_blur(layer, dx, dy)` helper that averages 3 shifted copies when speed is high.

### Chapter 2.12 Appeal

**Idea.** Characters should have charisma: designs and motion that the audience enjoys watching. Appeal is not prettiness; a villain can have appeal. It comes from clear shapes, pleasing proportions, and confident motion.

**Shorts mapping.**
- Icons with rounded corners (radius 12-24 px on cards, 6-10 px on small chips) and simple, bold shapes read as friendly.
- Consistent stroke weights (for line icons, 6-10 px at 720-wide) and a limited palette.
- Proportions: hero icon about 1.6-2× the size of secondary icons (close to golden-ratio contrasts feel natural).
- Motion appeal: no jitter, no frame drops, no element popping into existence without any entrance (except deliberately on a hard beat).

**Apply in code.** A style check: every layer must come from the palette, every corner radius must be from a small set (8, 16, 24), and every entrance must use one of the approved curves.

### Chapter 2.13 Motivation and emotion

Beyond the list, the book is about believable, thinking characters. For an explainer that means every movement needs a cause (the voice, the story, or a rhythm), each beat needs a chosen feeling that drives its timing, colour and SFX, and the biggest fact deserves a 300-500 ms hold so the viewer can feel it.

---

## Part 3. Lessons from *In the Blink of an Eye* (Walter Murch)

Walter Murch, the film and sound editor behind many celebrated films, wrote a short, thoughtful book about why cutting works at all, and how an editor decides where to cut. It is less a manual of techniques than a way of thinking about the viewer's mind. Its ideas are especially relevant to shorts, which are almost entirely made of cuts and changes.

### Chapter 3.1 Why cuts work at all

**Idea.** Murch reflects on a puzzle: in real life our view never jumps instantly from one place to another, yet audiences accept cuts without confusion. His explanation is that our minds already work in a cut-like way. We constantly shift attention, we blink, we jump between thoughts. A well-placed cut mirrors a natural shift of thought, so the viewer experiences it as their own attention moving, not as a break.

**Lesson for Divya.** A cut or transition is acceptable when it lands at the moment the viewer's mind is ready to move on: when an idea has been delivered and the next one is being introduced. A cut in the middle of an idea feels like an interruption.

**Apply in code.**
- Place scene changes at the boundaries between sentences or clauses in the voiceover, not mid-phrase.
- Use word timestamps: find gaps of 120 ms or more between words, and punctuation marks (full stop, comma, question mark). These are natural cut points.
- If a beat has to change mid-sentence, change it on a stressed content word (a noun or number), not on a function word ("the", "of", "and").

### Chapter 3.2 The Rule of Six

**Idea.** Murch proposes a ranked list of six criteria for judging a cut. In his ordering, the most important is **emotion**: does the cut serve what the audience should feel at this moment? Next is **story**: does it move the story forward? Then **rhythm**: does it happen at a rhythmically right moment? Then **eye trace**: does it respect where the viewer's eye is on screen? Then **two-dimensional plane of screen**: does it respect screen direction and the line of action? Last is **three-dimensional space**: is the physical continuity of positions in the space consistent? He also suggests rough weights, with emotion counting for more than all the spatial considerations together, and the advice that when you must sacrifice something, sacrifice from the bottom of the list first.

**Divya's version of the Rule of Six, for each scene change:**

1. **Emotion (most important).** Does this change support the feeling of the moment? A gentle fact gets a soft blur dissolve; a shocking stat gets a hard cut with a flash.
2. **Story.** Does the new scene show the thing the voice is now talking about? If the voice moved on and the picture did not, or vice versa, fix it.
3. **Rhythm.** Does the change land on a word onset, a music beat, or a natural pause? Is it spaced well relative to the previous change (not too soon, not too late)?
4. **Eye trace.** Will the viewer's eye be in the right place? If the outgoing hero is at the top, the incoming hero should appear near the top, or the transition should carry the eye there (a push or wipe that moves in that direction).
5. **Screen plane / direction.** If things have been moving left-to-right as "progress", keep that convention. A "next step" should push in from the right, a "going back" from the left.
6. **Spatial continuity.** If a phone was on the left and we "zoom into" it, the zoom should centre on where it was.

**Apply in code.** Score each candidate transition per scene change. A simple scheme: emotion fit 0-5 (weight 5), story fit 0-5 (weight 4), rhythm fit 0-5 (weight 3), eye trace 0-5 (weight 2), direction 0-5 (weight 1), space 0-5 (weight 1). Pick the highest score among non-repeated families. When short of time, at minimum check the first three.

### Chapter 3.3 Blink theory

**Idea.** Murch noticed that people tend to blink at the moment they finish taking in one idea and are about to take in another. He relates this to cuts: a good cut often falls where an audience member might naturally blink, because that is the moment of mental punctuation. He also observed that actors deep in thought often blink at the end of a thought, and that cutting there feels right.

**Lessons for shorts.**
- The natural "blink moments" in a voiceover are the ends of sentences and the ends of clauses. The voice's breath pauses are the audience's blinks.
- After a surprising reveal, the viewer needs a beat to absorb it before the next blink; do not cut instantly.
- A very fast series of cuts can feel like a barrage of blinks, which is exciting in small doses but tiring for more than 2-3 seconds.

**Apply in code.**
- Cut point = end of the last word of a sentence + 2 to 6 frames (inside the breath gap), or exactly at the first frame of the next sentence's first word minus 1-2 frames.
- After a reveal of a key fact, hold at least 12-20 frames (400-670 ms) before the next scene change.
- Bursts of rapid cuts (under 15 frames apart) should last no more than 3 cuts in a row.

### Chapter 3.4 Cutting on the word and on the beat

Murch's book discusses how editors feel rhythm and the moment when a cut "wants" to happen, rather than placing cuts by rule. For Divya, rhythm can be made measurable.

**Rules of thumb.**
- **On the word.** The most powerful cut point is 1-2 frames before the onset of a stressed content word that names the new scene's subject. The picture appears just as the word begins, so sight and sound arrive together. Example: "And then came... ROBOTS." The robot scene cuts in 1 frame before "ROBOTS".
- **After the word.** For reflective or emotional moments, cut a little after a sentence ends, in the silence, so the last word can land.
- **On the beat.** If there is background music, snap scene changes to the nearest beat within ±3 frames, but only if that does not break the word rule. Voice wins over music.
- **Off the beat.** Occasional off-beat changes (on the "and" between beats) add syncopation and keep things from feeling mechanical. Use for 1 in 4 or 5 changes.

**Apply in code.**

```
def snap_cut(t_word_onset, beats, max_shift=3/30):
    t = t_word_onset - 1/30
    nearest = min(beats, key=lambda b: abs(b - t)) if beats else t
    return nearest if abs(nearest - t) <= max_shift else t
```

### Chapter 3.5 The editor as the audience's representative

**Idea.** Murch describes the editor's role as standing in for the audience: watching material fresh, noticing what they feel, and protecting that first impression even after seeing the footage many times. He talks about guarding against becoming too familiar with the material.

**For an automated editor**, "fresh eyes" means simple automated checks that simulate a first-time viewer.

**Apply in code (first-viewer checks).** Headline readable within 6 frames with sound off; no hold over 1.2 s without motion or new speech; every caption on screen for at least its reading time; every scene change on a sentence or clause boundary.

### Chapter 3.6 Fewer cuts versus more cuts

**Idea.** Murch makes the point that the number of cuts is not a measure of quality; each cut must justify itself, and leaving a shot alone can be the strongest choice. At the same time he acknowledges that rhythm and the audience's state change what feels right.

**Balancing this for shorts.** Short-form platforms reward visual change, but "change" does not require a full cut. Divya has three levels of change:

1. **Micro change** (within a scene): a caption word pops, an icon floats, a number counts up. Every 0.3-1 s.
2. **Meso change** (layout change): a new icon enters, focus shifts, a camera push starts. Every 1.5-3 s.
3. **Macro change** (scene transition): a full screen transition. Every 3-8 s.

**Apply in code.** A 30-second short typically has 5-8 macro changes, 12-20 meso changes, and constant micro changes. Prefer meso changes over extra macro cuts when the voice is still on the same idea.

---

## Part 4. Lessons from *Grammar of the Edit* (Roy Thompson and Christopher J. Bowen)

*Grammar of the Edit* is a widely used textbook that lays out the basic vocabulary of film and video editing: the types of transitions, what makes a cut acceptable, how to keep continuity, and how to pace a sequence. Its companion volume, *Grammar of the Shot*, covers framing. The book is organised around practical guidelines that editors can apply shot by shot. This part restates its key ideas and maps them to Divya's graphic world, where "shots" are scenes made of layers.

### Chapter 4.1 The basic transitions and what they mean

The book describes a small number of fundamental ways to go from one shot to the next, each carrying a different meaning to the viewer.

1. **The cut.** An instant change. It is invisible when motivated and keeps the pace up. It implies continuity of time: the next thing is happening now.
2. **The dissolve** (cross-fade). One image fades through the other. It suggests a passage of time, a change of place, a soft connection between ideas, or a dreamy, reflective tone. It slows pace.
3. **The wipe.** One image is pushed or revealed by a moving edge or shape. It is overt and graphic; it announces "new section". It was common in older serials and is common in graphic and playful video today.
4. **The fade** (to or from black or another colour). It marks the start or end of a major section, like opening or closing a chapter.

**Divya mapping.**

| Classic transition | Meaning | Divya families | Duration |
|---|---|---|---|
| Cut | same topic, new angle, energy | hard cut (no transition), flash, whip | 0-4 f |
| Dissolve | soft link, time passing, calm | blur_dissolve, noise_dissolve, luma, dip | 10-18 f |
| Wipe | new section, list item, playful | wipe, circle, diamond, box, barn, clock, blinds, checker, blocks, spiral, star, heart, wave, zigzag | 8-14 f |
| Fade | start or end of video, big chapter break | dip (to black or brand colour) | 12-20 f |
| Push/slide | sequence, next step, progress | push, cover, uncover, split | 8-12 f |
| Zoom | go into detail / pull back for context | zoom_through, zoom_out, spin_zoom | 8-14 f |
| 3D | change of perspective, flipping a card, "the other side" | 3d_flip, 3d_cube, 3d_door, 3d_page_turn, etc. | 12-18 f |

### Chapter 4.2 What makes a cut acceptable

The book gives criteria that help a cut feel smooth: there should be a **motivation** for the cut (a new piece of information, a reaction, a sound), the new shot should offer **new information**, the **composition** of the two shots should be compatible, the **camera angle** should change enough to be clearly a new shot (avoiding tiny changes that look like a mistake), and **continuity** of action, movement and sound should be respected.

**Divya translations.**
- **Motivation:** every scene change must be motivated by the voiceover (new idea), by a sound, or by an action on screen (an element flying towards the camera).
- **New information:** never cut to a scene that shows the same thing as before. If nothing new is ready, use a meso change instead.
- **Composition:** the hero in the outgoing and incoming scenes should sit in a compatible place, or the transition should travel between them.
- **Avoid the "jump cut by accident":** a change where the layout shifts only slightly (an icon moves 20 px, colour changes a little) looks like a glitch. Either change a lot (different scale, different layout, different colour emphasis), or animate the change smoothly.
- **Continuity:** keep the headline position, caption position, and palette consistent across scenes.

**Apply in code.** When comparing consecutive scenes, compute a simple "difference score" (mean pixel difference on downscaled frames). If the difference is between about 3% and 15%, the cut risks looking accidental: either animate it as a move or increase the change.

### Chapter 4.3 Match cuts

**Idea.** A match cut links two shots through a shared element: matching shape, matching movement, matching position, or matching idea. The viewer's eye stays in the same place while the content changes, which feels clever and smooth.

**Types and Divya examples.**
- **Graphic match (shape):** a round clock face becomes a round coin becomes a round planet, each in the same screen position and size. Use a quick cut or a `circle` wipe centred on that object.
- **Movement match:** an arrow flies right and exits; the next scene's element enters from the left moving right at the same speed.
- **Position match:** the outgoing hero and incoming hero occupy the same box on screen, so the eye does not search.
- **Idea match:** "Your brain..." shows a brain; "...is like a computer" cuts to a CPU chip at the same size and position.

**Parameter ranges.** Position mismatch under 30 px; size mismatch under 15%; speed mismatch under 20%.

**Apply in code.** When the outgoing hero's bounding box and the incoming hero's box overlap by more than 60% (intersection over union), prefer a hard cut, `circle` (centred on the hero), `zoom_through` (centred on the hero), or `luma`. Pass the hero centre as the transition centre.

### Chapter 4.4 J cuts and L cuts (split edits)

**Idea.** In a split edit, the sound and picture change at different moments. In a **J cut**, the sound of the next scene starts before its picture (on a timeline, the audio extends left, like the bottom of the letter J). In an **L cut**, the picture changes but the sound of the previous scene continues for a while. Both make transitions feel smooth and conversational.

**Divya translations.** Divya's voiceover is continuous, so split edits apply to sound effects, music and ambience, and to the relation between voice and picture.

- **Visual J cut:** the voice begins talking about the new idea slightly before the picture changes. Use for curiosity: the viewer hears "But here's the twist..." and the picture changes 6-10 frames later, on "twist". It builds a moment of anticipation.
- **Visual L cut:** the picture changes to the next scene while the voice finishes the previous sentence. Use when the next scene is a visual answer to the end of the sentence, or to keep pace high. Typically 4-10 frames.
- **SFX J cut:** the whoosh starts 4-8 frames before the transition and peaks on the cut. This is the most important split edit in shorts: the sound "pulls" the picture.
- **Ambience L cut:** a background tone or music stem from the previous scene tails out over 6-12 frames after the cut.

**Apply in code.** For each transition at time T: `whoosh_start = T - 5/30`, peak at T. For a J-style reveal: `picture_change = word_onset("twist") - 1/30`, while the sentence started 0.3-0.6 s before.

### Chapter 4.5 Continuity: screen direction and the 180-degree line

**Idea.** The book explains the 180-degree rule: when filming two people or a moving subject, the camera stays on one side of an imaginary line so that screen directions remain consistent (a person looking right keeps looking right; a car moving left keeps moving left). Breaking it confuses the audience about where things are.

**Divya translation: directional grammar.**
- Left-to-right = forward, progress, future, next step, cause to effect.
- Right-to-left = back, past, reversal, "but".
- Bottom-to-top = growth, rising, more.
- Top-to-bottom = falling, decrease, arrival, gravity, "landing" a fact.
- Inward zoom = detail, focus, inside.
- Outward zoom = context, big picture.

**Apply in code.** Assign a direction to each scene change based on the script's logic: `"next"` → push or wipe from the right (content moves left), `"but"` / `"however"` → from the left, `"rise"` / `"grow"` → from the bottom, `"result"` / `"so"` → zoom or drop from top. Keep the convention across the whole video.

### Chapter 4.6 Pacing and rhythm

**Idea.** The book treats pacing as the rate at which shots change and the rate at which information is delivered, chosen to fit the content and emotion. Action sequences use short shots; emotional or reflective sequences use longer ones. Pacing should vary across a piece to avoid monotony, and it can build towards a climax.

**Pacing for shorts.**

| Section | Typical scene length | Notes |
|---|---|---|
| Hook (0-3 s) | 0.8-1.5 s | fast, high contrast |
| Setup (3-10 s) | 2-3 s | explain the problem |
| Core (10-40 s) | 2.5-4 s | each fact one scene |
| Climax / reveal | hold 1.5-2.5 s | slow down on purpose |
| Payoff / CTA (last 3-5 s) | 2-3 s | end card |

- **Vary scene lengths.** A sequence of exactly equal lengths feels mechanical. Vary by ±20-30%.
- **Accelerate into climaxes.** Shorten scene lengths by about 15% each step for the 3 scenes leading to the big reveal, then hold the reveal longer.
- **Breathe after peaks.** After the most intense moment, give one slightly longer, calmer scene.

**Apply in code.** Compute scene durations from voiceover sentence lengths, then clamp: minimum 0.8 s, maximum 4.5 s (split longer sentences into two scenes with a meso change). Apply the acceleration rule to the 3 scenes before the climax tag.

### Chapter 4.7 When each transition is right

Here is a decision guide built from the book's principle that transitions carry meaning, mapped to Divya's library:

- **Hard cut:** default for most scene changes when the voice continues on the same thread. Fastest, cleanest. Pair with a subtle SFX tick only if needed.
- **Whip / push:** "next", list items, step-by-step. Duration 6-10 frames. Pair with whoosh.
- **Zoom through:** going deeper into a topic, "inside", "let's look closer". 8-12 frames.
- **Zoom out:** "the bigger picture", "overall", summary. 10-14 frames.
- **Circle / star / heart / diamond:** playful reveals, list reveals tied to a shape theme (heart for health or love, star for rating or best). 10-14 frames. Use sparingly; maximum 1-2 shape wipes per video.
- **Blinds / checker / blocks / pixelate:** tech, data, digital, "loading". 10-14 frames.
- **Glitch-type (rgb_split, pixelate, posterize):** hacking, error, AI, warnings, surprise. 4-8 frames.
- **Flash:** shock, a hard punch, before/after reveal. 2-4 frames. White flash at 40-80%.
- **Dip:** end of the main video into the end card, or a big chapter break. 10-16 frames.
- **Blur dissolve / noise dissolve / luma:** soft, emotional, health, nostalgia, "years later". 12-18 frames.
- **3D families:** "the other side" (3d_flip), "behind the scenes" (3d_door), "next page" (3d_page_turn), "turning to a new angle" (3d_cube, 3d_carousel). 12-18 frames. Maximum 2 per video.
- **Spin zoom / spiral:** dizziness, chaos, time travel, "mind-blowing". 10-14 frames. Maximum 1 per video.
- **Wave / zigzag:** water, sound, energy, electricity. 10-14 frames.

**Variety is not noise.** The book's recurring point is that the best editing serves the story and often goes unnoticed. Per video, choose a primary family (about half of changes), a secondary family (about a quarter), and 2-3 accent transitions for special moments, and never repeat the exact same variant twice in a row.

---

## Part 5. Lessons from *Design for Motion* (Austin Shaw)

Austin Shaw's *Design for Motion* is a guide to the design side of motion graphics: how the classic principles of graphic design (composition, typography, colour, image making) behave once they move, and how motion designers plan work through style frames and storyboards before animating. Its message is that motion graphics are designed first and animated second, and that good motion work is built on solid still frames.

### Chapter 5.1 Design first, motion second

**Idea.** Shaw emphasises that every moment of a motion piece is a composition, and that a piece is only as strong as its key frames. If a paused frame looks weak, the moving version will look weak too, just faster.

**Apply in code.** Before rendering the full video, render a **contact sheet**: one still per scene at its key-state time (when everything has landed). Check each still against Part 6's principles. A scene that fails as a still is redesigned, not rescued with effects.

```
for scene in scenes:
    frame = render_frame(scene.key_time)
    sheet.paste(frame.resize((180, 320)), position(scene.index))
```

### Chapter 5.2 Style frames

**Idea.** A style frame is a single, polished, finished-looking frame that defines the visual language of a piece: palette, type, textures, icon style, lighting. Shaw describes how motion designers present style frames to clients before animating, because they communicate the look precisely and cheaply.

**For Divya**, the style frame is the **design token set** chosen at the start of each video:

- Background: base colour, gradient or vignette, optional subtle texture (noise at 2-4% opacity).
- Headline font, size, weight, colour; keyword highlight colour (yellow by default).
- Icon style: flat fill, line weight, corner radius, shadow.
- Accent colour and secondary colour.
- Caption style: font, size, active-word colour, stroke.
- Transition primary family.

**Apply in code.** Build one `STYLE` dict per video and render "style frame 0" (the hook scene) first. Every later scene must pull every colour, font and radius from `STYLE`. Never introduce a new colour mid-video except as a deliberate topic-driven accent.

### Chapter 5.3 Storyboards and animatics

**Idea.** Shaw places storyboards and timed animatics before animation because timing problems are cheapest to fix there. **Apply in code:** build Divya's beat sheet, `(start, end, spoken text, key state, hero, transition in, SFX)`, from the word timestamps before rendering any frame, and preview at 360x640, 15 fps when possible.

### Chapter 5.4 Composition in motion

**Idea.** Shaw discusses how the classic tools of composition (balance, focal point, visual hierarchy, positive and negative space, framing, the rule of thirds, leading lines) work across time. Composition is not frozen: elements enter, the balance shifts, and the designer guides the eye along a path through the frame and through time.

**Key concepts for vertical shorts.**
- **Focal point.** One hero per moment, as in Chapter 2.3.
- **Thirds.** On 720x1280, the vertical thirds lines are at y ≈ 427 and y ≈ 853; horizontal at x = 240 and 480. Headlines sit near the top line (y 160-400); the hero sits around the centre and lower-third crossing (y 450-850); captions sit near y 880-1000.
- **Negative space.** Empty dark areas are not wasted; they make the hero read. Aim for 35-50% of the safe area to be empty at any key state.
- **Balance shifts.** When a new element enters on one side, the existing composition should rebalance (slide the hero slightly the other way, 20-40 px, smooth 12 f) so the frame does not tip.
- **Leading lines.** Arrows, connecting lines and directional motion lead the eye from the headline to the hero to the caption. Draw arrows with a 4-6 frame "draw on" (stroke reveal) rather than popping them.
- **Depth.** Even in flat style, three depth planes help: background (slow drift, dim), midground (hero, icons), foreground (captions, accents, particles). Parallax: when the camera pans, background moves at 0.3×, midground 1×, foreground 1.2×.

**Apply in code.** A layout helper that places elements on a grid of 8 px, checks that the hero centre is within 80 px of a thirds intersection or the centre column, and computes negative space percentage.

### Chapter 5.5 Kinetic typography

**Idea.** Shaw treats type as a primary visual element in motion design, not just a carrier of words. Type can move, scale, rotate, change weight and colour, and its motion can express the meaning of the word itself.

**Principles for Divya's headlines.**
- **Hierarchy through motion.** The keyword (yellow) enters last and with the biggest motion; the rest of the headline enters first and calmly.
- **Meaning through motion.** "Rise" moves up; "fall" drops; "shake" shakes; "slow" eases in slowly; "explode" bursts. Use these sparingly but deliberately (1-3 per video).
- **Readability first.** Type in motion must be readable in the first 60% of its on-screen time. Any entrance longer than 12 frames for a headline word is too long.
- **Grouping.** Animate by word or by line, not by letter, for long headlines. Letter-by-letter is for short words (under 8 letters) at accent moments.

Part 8 develops kinetic type and captions in depth.

### Chapter 5.6 Colour in motion

**Idea.** Shaw covers colour as a tool for mood, hierarchy and brand, and notes that colour in motion can change over time to mark progression or emotion.

**Apply for Divya.**
- **Colour as hierarchy:** the keyword is the brightest, most saturated element on screen. Nothing else should be as bright as the yellow keyword in the headline area.
- **Colour as story:** shift accent colours to show change: a red "problem" section becomes green in the "solution" section. Transition the colour over 10-15 frames using the `tint` effect, not instantly.
- **Colour as rhythm:** brief colour flashes (a 2-3 frame accent-colour flash at 20-35% opacity) can mark beats.

Part 11 covers palettes in detail.

### Chapter 5.7 Transitions as storytelling

**Idea.** Shaw argues that in motion design, transitions are not just glue; they are part of the story. A great motion piece often uses **morphing and continuous transitions**, where one shape becomes the next, an element from scene A becomes the frame of scene B, or the camera travels through an object into the next idea. This is the motion designer's version of the match cut.

**Transition storytelling patterns for Divya.**
1. **Object becomes window:** the circle icon of scene A scales up to fill the screen and becomes the background of scene B (`zoom_through` centred on the icon, or a `circle` wipe from the icon's centre).
2. **Shape carry:** the yellow keyword underline extends into a wipe bar that reveals the next scene (`wipe` aligned with the underline's direction, same yellow edge).
3. **Number morph:** a stat counts from one value to the next instead of cutting.
4. **Direction carry:** an arrow pointing right becomes the motion of a `push` to the right.
5. **Flip to reveal:** a card flips (`3d_flip`) to show "the truth" on its back.
6. **Camera travel:** a continuous push-in (`zoom_through`) through three nested ideas: country → city → street.

**Apply in code.** Each transition can take a `center` and `angle` parameter. Derive them from the outgoing hero's bounding box and the direction of the last motion, so the transition feels like it grows out of the content.

---

## Part 6. Lessons from *The Non-Designer's Design Book* (Robin Williams)

Robin Williams' *The Non-Designer's Design Book* teaches design to people without design training. She organises good layout around four basic principles, often remembered as C.R.A.P.: **contrast, repetition, alignment, proximity**, plus clear guidance on type and on combining typefaces. These four ideas are perfect for an automated editor because each can be checked by code.

### Chapter 6.1 Contrast

**Idea.** If two things are not the same, make them very different. Weak, timid differences look like mistakes; strong differences create hierarchy and draw the eye. Contrast can come from size, weight, colour, shape, space or typeface.

**Divya rules.**
- **Size contrast:** headline 64-84 px; keyword same size or up to 1.1×; captions 44-56 px; small labels 26-32 px. Hero icon 260-380 px; secondary icons 100-160 px. Steps between levels should be at least 1.4×.
- **Weight contrast:** headline and captions in a heavy weight (Anton, Oswald Bold); small labels in a lighter weight if available.
- **Colour contrast:** keyword yellow (around #FFD400) vs white (#FFFFFF) headline vs dark background (#0B0F19 or similar). Text contrast ratio of at least 7:1 against its local background; for any text, never below 4.5:1.
- **No timid contrast:** do not use two almost-same greys or two almost-same sizes. If you want a difference, make it obvious.

**Apply in code.** Compute WCAG contrast ratio for each text layer against the average colour of the pixels behind it. Fail if under 4.5. Check size ratios between hierarchy levels.

```
def lum(c):
    def ch(v):
        v /= 255
        return v/12.92 if v <= .03928 else ((v+.055)/1.055)**2.4
    r, g, b = c
    return .2126*ch(r) + .7152*ch(g) + .0722*ch(b)
def contrast(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la+.05)/(lb+.05)
```

### Chapter 6.2 Repetition

**Idea.** Repeat visual elements throughout a design (colours, shapes, fonts, spacing, graphic devices) so it feels unified and organised. Repetition is consistency taken further: it is a deliberate visual theme.

**Divya rules.**
- Same headline position and style in every scene.
- Same caption position, font and highlight colour throughout.
- A repeated graphic device: for example, a yellow underline under the keyword, a rounded chip behind numbers, or a small dot motif. Pick one per video and use it in every scene.
- Same entrance style for the same kind of element (all icons enter with the same family; all numbers with another).
- Same SFX for the same kind of event (all icon pops use one pop sound family; all transitions use one whoosh family).

**Apply in code.** Assign effect families per **element role** at the start of the video (`role_fx = {"icon": "scale_back", "number": "punch", "label": "slide_up"}`), then vary only the parameters slightly. This gives repetition without exact copying.

### Chapter 6.3 Alignment

**Idea.** Nothing should be placed arbitrarily. Every element should have a visual connection to something else on the page. Strong alignment (especially a strong left or right edge) creates a clean, sophisticated look; mixing alignments (some centred, some left) without reason looks messy. Williams cautions that centred alignment is common but can look dull or amateur if used by default; it should be a choice.

**Divya rules.**
- Vertical shorts usually work best with **centred** alignment because the frame is narrow and viewers look at the centre. That is a valid choice; the key is to use it consistently.
- If a scene uses a list (three bullet points with icons), use a **strong left edge**: icons aligned on one x (for example x = 96), text aligned on another (x = 200). Do not centre each line individually.
- Align element centres to the column centre x = 360 (or slightly left, x ≈ 335, to compensate for the right-side button overlay).
- Snap all positions to the 8 px grid.

**Apply in code.** A lint check: collect left, centre and right x-values of all layers in a key state; they should cluster into at most 3 distinct alignment lines (within ±4 px).

### Chapter 6.4 Proximity

**Idea.** Group related items close together so they become one visual unit, and separate unrelated items. The space between things tells the reader what belongs together.

**Divya rules.**
- An icon and its label: gap 12-20 px.
- Items within a group: gap 24-40 px.
- Between groups: gap 64-120 px.
- The headline block is separated from the infographic by at least 64 px.
- Captions are separated from the infographic by at least 48 px.
- The relationship between inner gap and outer gap should be at least 1:2.

**Apply in code.** In layout, define `GAP_INNER = 16`, `GAP_GROUP = 32`, `GAP_SECTION = 80`. Never use arbitrary gaps.

### Chapter 6.5 Typography basics for screen

Williams explains type categories (oldstyle, modern, slab serif, sans serif, script, decorative) and how to combine them: either use one family with strong contrast of weight and size, or combine two clearly different typefaces, never two similar ones (two similar sans serifs fight each other). She also notes that all-caps text is harder to read in long passages because word shapes disappear, while short all-caps headings are fine.

**Divya typography rules.**
- **Fonts:** Anton (condensed, heavy) for headlines; Oswald (condensed, multiple weights) for captions and labels. They are related condensed sans faces, so keep contrast through size and weight, not by adding a third face.
- **All caps:** headlines of up to about 8 words can be all caps. Captions: either all caps for punchy energy, or sentence case for longer, calmer content. Do not mix.
- **Line length:** headline 2-3 lines, maximum about 16-20 characters per line at 72 px in Anton on a 640 px text width. Captions maximum 2 lines, 3-6 words per line.
- **Leading (line spacing):** headlines 0.95-1.1× font size (condensed caps can sit tight); captions 1.1-1.25×.

---

## Part 7. Material Design motion guidelines (Google)

Google's Material Design system publishes guidance on how interface elements should move: durations, easing curves and patterns for transitions between screens and states. Although written for apps, it is the most widely used, carefully reasoned set of numbers for "clean, modern UI motion", which is exactly the look of flat infographic shorts. The guidelines have evolved across versions (the original Material motion guidance and the later Material 3 "easing and duration tokens"); this part summarises the ideas and numbers commonly associated with them, in Divya's terms.

### Chapter 7.1 Purpose of motion

Material asks motion to inform (show relationships and results), focus attention, and express character. For Divya: every motion explains, guides the eye, and carries the channel's personality.

### Chapter 7.2 Duration tokens

Material 3 defines a scale of duration tokens grouped as short, medium, long and extra long, roughly spanning from about 50 ms up to around 1000 ms. The commonly published values are approximately:

| Token group | Values (ms) | Frames at 30 fps |
|---|---|---|
| Short 1-4 | 50, 100, 150, 200 | 1.5, 3, 4.5, 6 |
| Medium 1-4 | 250, 300, 350, 400 | 7.5, 9, 10.5, 12 |
| Long 1-4 | 450, 500, 550, 600 | 13.5, 15, 16.5, 18 |
| Extra long 1-4 | 700, 800, 900, 1000 | 21, 24, 27, 30 |

The older Material guidance described typical mobile transitions as roughly 200-300 ms, with elements entering a little slower than they exit, larger or longer-distance moves taking longer, and small changes (like a switch toggling) taking about 100 ms.

**Divya mapping (rounded to whole frames).**

| Use | Token | Frames |
|---|---|---|
| Caption word highlight | short 2 | 3 |
| Small icon pop | short 4 / medium 1 | 6-8 |
| Headline line entrance | medium 2 | 9 |
| Hero entrance, large move | medium 4 / long 1 | 12-14 |
| Full-screen transition | medium 4 - long 2 | 12-15 |
| Elaborate 3D transition | long 3 - long 4 | 16-18 |
| End card build | extra long 1-2 | 21-24 |

**Rule:** distance and area scale duration. A 50 px move takes the short end; a full-screen move takes the long end.

### Chapter 7.3 Easing tokens

Material 3 describes several families of easing:

- **Standard** easing, a gentle ease in-out used for elements that start and end on screen. Its commonly cited cubic Bézier is about (0.2, 0, 0, 1).
- **Standard decelerate** for entering elements (start fast, end slow), about (0, 0, 0, 1).
- **Standard accelerate** for exiting elements (start slow, leave fast), about (0.3, 0, 1, 1).
- **Emphasized** easing for expressive, hero transitions: a curve that moves quickly early and takes a long, gentle settle. Its decelerate variant is often cited around (0.05, 0.7, 0.1, 1) and its accelerate variant around (0.3, 0, 0.8, 0.15).

The older Material guidance used similar named curves: standard (0.4, 0, 0.2, 1), deceleration (0, 0, 0.2, 1), acceleration (0.4, 0, 1, 1), and sharp (0.4, 0, 0.6, 1) for elements that may return to the screen.

**Apply in code.** A small cubic-Bézier solver lets Divya use these exact curves:

```
def bezier(x1, y1, x2, y2):
    def f(t):
        # solve x(u) = t by Newton iteration, then return y(u)
        u = t
        for _ in range(8):
            x = 3*(1-u)**2*u*x1 + 3*(1-u)*u*u*x2 + u**3 - t
            dx = 3*(1-u)**2*x1 + 6*(1-u)*u*(x2-x1) + 3*u*u*(1-x2)
            if abs(dx) < 1e-6: break
            u = min(1, max(0, u - x/dx))
        return 3*(1-u)**2*u*y1 + 3*(1-u)*u*u*y2 + u**3
    return f
EASES["m3_standard"] = bezier(.2, 0, 0, 1)
EASES["m3_decel"]    = bezier(0, 0, 0, 1)
EASES["m3_accel"]    = bezier(.3, 0, 1, 1)
EASES["m3_emph_dec"] = bezier(.05, .7, .1, 1)
EASES["m3_emph_acc"] = bezier(.3, 0, .8, .15)
```

- Entrances: `m3_decel` or `m3_emph_dec` (close to `expo`).
- Exits: `m3_accel` or `m3_emph_acc`.
- On-screen repositioning: `m3_standard` (close to `smooth`).

### Chapter 7.4 Transition patterns

Material describes a set of reusable transition patterns for moving between screens:

1. **Container transform:** an element (a card) grows into the full screen that it represents, keeping a visual connection. Divya: an icon or card expands into the next scene (`zoom_through` or a `box` wipe from the card's bounds).
2. **Shared axis:** screens that have a spatial or navigational relationship move together along the x, y or z axis (sliding left/right for steps, up/down for hierarchy, scaling for depth). Divya: `push` (x), `push`/`cover` vertical (y), `zoom_through`/`zoom_out` (z).
3. **Fade through:** for screens with no strong relationship, the old fades out, then the new fades and scales in slightly (from about 92% to 100%). Divya: `dip` with a short dark middle, or `blur_dissolve` plus a scale on the incoming layer.
4. **Fade:** for elements appearing or disappearing within bounds (a dialog, a menu). Divya: `fade` + `scale` entrance for a popup label.

**Apply in code.** Map the script relation between consecutive scenes to a pattern: `"zoom_in_on_detail"` → container transform; `"next_step"` → shared x axis; `"sub_point"` → shared y axis; `"unrelated_topic"` → fade through.

### Chapter 7.5 Choreography and stagger

**Idea.** Material describes "choreography": when many elements move, they should be sequenced so the eye follows a clear path, with a shared direction and staggered timing. Items in a list should enter in order with small delays, and the overall sequence should still finish quickly.

**Numbers.** Stagger 20-50 ms (1-2 frames) for list items, up to about 80 ms (2-3 frames) for larger cards; cap the total sequence so it finishes within about 400-500 ms (12-15 frames).

**Apply in code.** `stagger = min(3/30, 0.45/len(items))`.

---

## Part 8. Kinetic typography and caption craft

This part combines ideas from motion design practice (including Shaw's *Design for Motion* and Material's type guidance) with the conventions that have emerged on short-form platforms. There is no single canonical book; the rules here are practical defaults for Divya's style.

### Chapter 8.1 Why captions matter in shorts

A large share of short-form viewers watch with sound off at least some of the time, and even with sound on, captions improve comprehension and retention by giving the eye something to follow. Captions are also a motion element: word-by-word highlighting creates constant micro-change (see Chapter 3.6), which holds attention.

### Chapter 8.2 Caption anatomy

- **Group size:** 2-5 words per caption group (a phrase). 3-4 is the sweet spot.
- **Lines:** 1-2 lines; prefer 1 line for punch, 2 lines when words are long.
- **Font size:** 48-60 px for Oswald/Anton-style condensed fonts on 720 wide. Never below 40 px.
- **Max width:** 600 px (x 60-660), or 560 px to stay clear of right-side buttons.
- **Position:** baseline around y = 900-1000. Never below y = 1020 (platform caption overlay), never overlapping the hero.
- **Colours:** inactive words white (#FFFFFF) at 100% or 85% opacity; active word yellow (#FFD400) or the video's accent; spoken words may stay white or dim to 70% after being spoken.
- **Legibility:** 5-6 px dark stroke (#000 at 85-100%) or a drop shadow (0, 4, blur 8, 70%). Optionally a rounded dark pill behind the group (#000 at 45-60%, radius 16, padding 12/20).

### Chapter 8.3 Timing captions to the voice

**Rules.**
- Show a caption group 2-4 frames before its first word is spoken (so the eye arrives in time).
- Highlight each word 1-2 frames before its spoken onset (from TTS word timestamps).
- Keep the group on screen until 2-4 frames after its last word ends, then cut instantly to the next group (no fade between groups: fades make captions feel laggy).
- If the gap between words is more than 400 ms, the group may leave the screen; if under 400 ms, the next group replaces it directly.
- Minimum on-screen time per group: 0.4 s, even for very fast speech; merge groups if needed.

**Apply in code.**

```
for g in groups:
    g.show = g.words[0].start - 3/30
    g.hide = next_group.show if next_group else g.words[-1].end + 3/30
    for w in g.words:
        w.hl_on = w.start - 1/30
```

### Chapter 8.4 Word entrance animations

Each newly highlighted word can get a small motion. Keep it subtle because it happens constantly.

| Style | Parameters | Feel |
|---|---|---|
| Pop | scale 1.18 → 1.0, 4 f, back | energetic default |
| Bounce up | y +10 → 0 px, 4 f, back | playful |
| Colour only | instant colour change | calm, documentary |
| Punch | scale 1.3 → 1.0, 5 f + 2 px shake | accent words only |
| Typewriter | words appear one by one, no scale | serious, news |

**Rule:** pick one default style per video. Use punch only for accent words (numbers, keywords, negatives), at most once per 3 seconds.

### Chapter 8.5 Headline kinetic type

The headline at the top (bold, with one yellow keyword) is the video's title card and anchor.

- **Entrance:** line by line, 9 f each, `expo`, slide up 30-50 px + fade; stagger lines by 3-4 f. The keyword enters last, with a scale punch (1.25 → 1.0, 6 f, back) and an optional yellow underline that draws in left to right over 6 f.
- **Keyword choice:** the single most meaningful word: the subject, the surprising number, or the emotional word. Never a function word.
- **Hold:** the headline stays all video (repetition), or changes per chapter for longer videos. If it changes, use the same entrance style.
- **Idle:** headline does not float; it is the stable anchor. The keyword may glow subtly (glow radius 8-14 px, yellow at 25-35%) or pulse once every few seconds (2%).
- **Size:** 68-84 px in Anton, 2-3 lines, total block height 180-280 px, top of block at y ≈ 150-180.

### Chapter 8.6 Numbers and counters

Numbers deserve their own kinetic grammar because they are often the most memorable content.

- **Count-up:** animate from 0 (or a smaller round number) to the target over 15-30 frames with `expo` easing, so it rushes then slows into the final value. Round intermediate values sensibly (no decimals flickering unless they are part of the final value).
- **Final value lands:** on the last frame, punch (1.2 → 1.0, 5 f) + pop SFX.
- **Use tabular (fixed-width) digits** or right-align so the number does not jitter in width while counting. If the font is proportional, centre on the final width.
- **Units:** smaller (0.5-0.6× size) and in white, next to the yellow number ("₹ 12 L", "73 %").

### Chapter 8.7 Expressive type: word means motion

| Word type | Motion |
|---|---|
| rise, grow, up, increase | slide up + scale up |
| fall, drop, down, crash | drop with squash, shake |
| fast, quick, instantly | whip in, motion blur |
| slow, calm, wait | long ease in, 18 f |
| break, crack, hack | glitch, rgb_jitter |
| love, heart, health | heartbeat |
| warning, danger, stop | red tint, shake, pulse |
| secret, hidden | blur in (blur 16 → 0) |
| big, huge | scale 0.6 → 1.15 → 1 |
| small, tiny | scale 1.4 → 0.9 → 1 |

Limit: 1-3 expressive treatments per video, on words the viewer must remember.

---

## Part 9. Sound design and audio mix for shorts

Murch's work (Part 3) and the general practice of film sound design teach that sound does at least half of the emotional work of a moving image. In shorts, sound is also a retention tool: a satisfying whoosh or pop makes a visual change feel deliberate. This part gives Divya concrete timing, levels and mixing rules.

### Chapter 9.1 The layers of a short's soundtrack

In priority order: voiceover (always intelligible), music bed (always under the voice), transition SFX (whooshes, risers, impacts), UI SFX (pops, clicks, ticks), accent SFX tied to meaning (thuds, glitch bursts, notification sounds), and optional room tone at a very low level to avoid digital silence.

### Chapter 9.2 SFX timing rules

The guiding idea, shared with Chapter 1.13: **sound should land on the frame where the visual event peaks**, and anticipatory sounds should start before.

| Event | SFX | Start | Peak | Length |
|---|---|---|---|---|
| Push/whip transition | whoosh | T − 4 to 6 f | at cut / mid-transition | 250-500 ms |
| Zoom through | whoosh with rising pitch | T − 6 f | at max zoom | 400-600 ms |
| Icon pop | pop / bubble | frame icon reaches full size (≈ 60-70% into entrance) | immediate | 60-150 ms |
| Word punch | soft click or thump | 0-1 f before word onset | immediate | 50-120 ms |
| Heavy drop | thud / low boom | impact frame | immediate | 200-500 ms |
| Flash | camera shutter or impact | flash frame | immediate | 100-300 ms |
| Glitch | digital burst | first glitch frame | | length of glitch |
| Count-up | ticks (optional) | each step or every 2 f | | ends with ding |
| End card | soft chime or riser + hit | 6-10 f before end card lands | land | 500-1200 ms |
| Reveal after build | riser | 1-2 s before reveal | at reveal (then cut riser) | 1-2 s |

**Rules.**
- Never place two SFX within 3 frames of each other unless they are part of one designed event (a whoosh and an impact).
- Maximum density: about 1 SFX per 0.7-1 s on average. More than that becomes noise and competes with the voice.
- Vary samples: rotate among 3-5 variants of each SFX type, and randomise pitch ±1-2 semitones and gain ±1.5 dB so repeated pops do not sound robotic.
- Do not put SFX on top of stressed syllables of the voice if they are loud; shift the SFX 2-3 frames earlier, or lower it.

### Chapter 9.3 Levels and loudness

Most major streaming and social platforms normalise loudness to a target around **−14 LUFS integrated** (some vary slightly). Mastering near that target means the video plays at the intended level without being turned down or sounding weak.

**Target mix levels (approximate, short-term loudness):**

| Layer | Level relative to VO | Typical peak |
|---|---|---|
| Voiceover | reference, about −14 to −16 LUFS short-term | peaks ≤ −3 dBFS |
| Music bed under voice | −18 to −24 dB below VO (about −30 to −36 LUFS) | |
| Music with no voice (intro/outro) | −6 to −10 dB below VO level | |
| Whooshes | −10 to −16 dB below VO | |
| Pops / clicks | −12 to −18 dB below VO | |
| Impacts / thuds on accents | −6 to −10 dB below VO | |

**Final master:**
- Integrated loudness: −14 LUFS (±1).
- True peak: ≤ −1 dBTP (−1.5 to be safe after lossy encoding).
- Loudness range: low (shorts should be consistent; aim LRA under about 6-8 LU).

**Apply in code (ffmpeg).** Two-pass loudness normalisation:

```
# pass 1: measure
ffmpeg -i mix.wav -af loudnorm=I=-14:TP=-1.5:LRA=7:print_format=json -f null -
# pass 2: apply with measured values
ffmpeg -i mix.wav -af loudnorm=I=-14:TP=-1.5:LRA=7:measured_I=...:measured_TP=...:measured_LRA=...:measured_thresh=...:offset=...:linear=true -ar 48000 out.wav
```

Encode audio as AAC 48 kHz, 128-192 kbps stereo (or mono duplicated to stereo).

### Chapter 9.4 Ducking

**Idea.** Ducking automatically lowers music when the voice speaks, and lets it rise in pauses. It keeps the voice intelligible while keeping the music present.

**Parameters.**
- Duck depth: music drops 8-14 dB when voice is present.
- Attack: 20-80 ms (fast enough that the first syllable is clear).
- Release: 250-600 ms (slow enough that the music does not "pump" between words).
- Only let music swell in pauses longer than about 600 ms.

**Apply in code (ffmpeg sidechain).**

```
ffmpeg -i music.wav -i vo.wav -filter_complex \
"[1:a]asplit=2[vo][sc];[0:a][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400:makeup=1[ducked];\
[ducked][vo]amix=inputs=2:duration=longest:normalize=0[mix]" -map "[mix]" mix.wav
```

Alternatively, compute a duck envelope from VO word timestamps in numpy: gain = −12 dB inside words (with 50 ms ramps in, 400 ms ramps out), 0 dB in gaps over 600 ms.

### Chapter 9.5 EQ and clarity

- **Voice:** high-pass at 80-100 Hz to remove rumble; a gentle presence boost of 2-3 dB around 3-5 kHz improves clarity on phone speakers; a de-esser if sibilance is harsh (around 6-8 kHz).
- **Music under voice:** cut 2-4 dB in the 1-4 kHz range so the voice has room ("carving a pocket").
- **Whooshes:** high-pass at 150-200 Hz so they do not muddy the voice; phone speakers will not reproduce deep lows anyway.
- **Impacts:** keep some low-mid (100-250 Hz) energy so they are felt on phones, which have little true bass.
- **Mono compatibility:** many phones play in near-mono; avoid wide stereo effects that disappear when summed.

**Apply in code.** `-af "highpass=f=90,equalizer=f=4000:t=q:w=1:g=2.5"` on VO; `-af "equalizer=f=2500:t=q:w=1.5:g=-3"` on music.

### Chapter 9.6 Silence and contrast

**Idea.** A moment of silence (or near-silence) before a key reveal makes the reveal hit harder. Sound designers often drop the music for a beat.

**Rule.** Before the biggest reveal, drop music to −40 dB or mute for 8-15 frames, let the voice say the key line, then bring music back with an impact on the reveal. Use once per video.

### Chapter 9.7 Music choice and tempo

- Tempo around 100-130 BPM suits most explainers; faster (130-150) for hype or tech; slower (70-90) for calm or wellbeing topics.
- At 120 BPM, one beat = 0.5 s = 15 frames, so 2-beat scene lengths (1 s) and 4-beat lengths (2 s) align naturally. At 30 fps, tempos that divide nicely: 120 BPM (15 f), 90 BPM (20 f), 100 BPM (18 f), 150 BPM (12 f).
- Start music on frame 0 (no silent lead-in). End music with a natural ending or a 0.5-1 s fade over the end card.

**Apply in code.** If beat times are known (or BPM and offset), quantise transitions to beats per Chapter 3.4, with voice timing taking priority.

---

## Part 10. Retention editing for Reels, Shorts and TikTok

These rules are drawn from widely shared creator practice and platform guidance rather than one book. They connect to the earlier parts: Murch's idea of cutting when attention is ready to move, Williams' and Thomas and Johnston's emphasis on clear staging, and Shaw's attention to the overall arc.

### Chapter 10.1 The first second decides

Short-form feeds let people swipe instantly. A large share of viewers decide within the first second or two. The opening must give a reason to stay before the viewer's thumb moves.

**Hook rules.**
- **Frame 0 is never empty.** The headline, the hero visual, or both must be visible on frame 0 (or fully in by frame 6). No logo intros, no fade from black.
- **Sound from frame 0.** The first word or an impact begins in the first 3 frames.
- **State the payoff or tension in the first sentence:** a surprising claim, a question, a number, a "you" statement. The headline shows the same idea visually with the yellow keyword.
- **Motion in the first 10 frames:** something must move decisively (a punch-in on the keyword, a hero pop) so the eye locks in.
- **Hook length:** the hook line should finish by 2-3 s.

**Example opening.** f0: headline "Your phone is LISTENING?" already visible, mic icon at centre with an impact; f0-6 the mic pops 0.9 → 1.08 → 1.0; f2 the VO starts; f75 first push to scene 2.

### Chapter 10.2 Pattern interrupts every 2-3 seconds

**Idea.** Attention fades when the screen stays visually similar. A pattern interrupt is any noticeable visual or audio change that resets attention: a new element, a camera move, a zoom, a colour shift, a sound accent, a scene change.

**Rules.**
- At least one meso change (Chapter 3.6) every 1.5-3 s.
- At least one macro change (scene transition) every 3-6 s on average.
- Vary the type of interrupt: alternate between scene changes, zoom punch-ins, element entrances, text accents and SFX. Repeating the same interrupt in the same rhythm becomes its own pattern and stops working.
- **Punch-in zooms** are cheap and effective: scale the whole frame 100% → 108-115% in 2-4 frames on a stressed word, hold, then return or cut. Use 1-3 per video.

**Apply in code.** Run a scan over the timeline: for every 2.5 s window, assert at least one event of type `scene_change | hero_entrance | punch_in | accent`. If missing, insert a meso change (an icon entrance tied to the nearest content word, or a 3% push-in).

### Chapter 10.3 Information density and clarity

One clear fact per scene, no filler. Script the VO at 140-170 words per minute, in sentences of 6-14 words with at most one number each, and add a mini-payoff every 3-4 sentences.

### Chapter 10.4 Open loops and curiosity

An open loop is a question the video raises and promises to answer later ("and the third reason is the strangest"). It gives the viewer a reason to stay.

**Rules.**
- Open one loop in the first 3 seconds, close it near 70-85% of the runtime.
- Visual support: show a placeholder for the answer (a "?" chip, a blurred card, a locked icon) that stays visible or returns, then resolves with a reveal (blur 16 → 0, `3d_flip`, unlock animation) at the payoff.

### Chapter 10.5 Progress cues

A thin progress element (a bar at the top, a numbered list "1/3, 2/3, 3/3", or dots) shows the viewer how much is left, which reduces drop-off in lists.

**Parameters.** Progress bar 6-8 px tall at y ≈ 130-140 (just under the top unsafe region), accent colour, linear growth (here linear is correct: it represents time). Numbered chips 44-56 px, same position each scene.

### Chapter 10.6 Loops

Platforms count replays, and a video that loops seamlessly gets watched again without the viewer noticing the restart.

**Loop techniques.**
- **Sentence loop:** the last line flows into the first ("...and that's why your phone is" → restart → "listening to you?").
- **Visual loop:** the end card or last scene matches the first scene's layout closely, so the restart feels like a continuation. End with the same background and hero position as frame 0.
- **Avoid a long end card** if looping matters: keep the end card 1.5-2.5 s, then the restart.
- **No fade to black at the end** if looping is the goal; cut directly.

**Apply in code.** Option `loop_mode=True`: final frame layout = first frame layout; final SFX is a whoosh that resolves at f0 of the loop; music cut at a bar boundary so the restart is on the downbeat.

### Chapter 10.7 The end card and call to action

- Land the end card with the same style as the hook (repetition).
- CTA: one action only (follow, save, comment a word). Show it as large text 56-72 px plus an icon, with a pulse (5%, 0.8 s) on the button shape.
- Duration: 1.5-3 s. Include a soft chime or a hit as it lands.
- Keep it inside the safe area; the bottom 260 px is covered by platform UI.

---

## Part 11. Colour theory and topic-to-palette mapping

Colour knowledge here draws on general colour theory as taught in design courses and books (including the colour chapters of Shaw's *Design for Motion* and Robin Williams' contrast principle), adapted for a dark-background, yellow-keyword style.

### Chapter 11.1 The basics in one page

- **Hue** is the colour family (red, yellow, blue). **Saturation** is intensity. **Value/lightness** is how light or dark.
- **Value contrast matters more than hue contrast** for readability. Yellow on near-black is one of the strongest value contrasts available, which is why it works for keywords.
- **Warm colours** (red, orange, yellow) advance and feel energetic; **cool colours** (blue, teal, purple) recede and feel calm or technical.
- **Colour harmonies:** complementary (opposites, like blue and orange: strong contrast), analogous (neighbours, like teal-blue-indigo: calm unity), triadic (three evenly spaced: lively), split-complementary (one colour plus the two neighbours of its opposite: contrast with less tension).
- **The 60-30-10 idea** from interior and graphic design: about 60% dominant colour (the dark background), 30% secondary (white text and neutral icon fills), 10% accent (yellow keyword and one topic accent).

### Chapter 11.2 Divya's base palette

| Role | Default | Notes |
|---|---|---|
| Background | #0B0F19 to #121826 | near-black with a blue tint feels richer than pure black |
| Background gradient/vignette | centre 8-12% lighter | radial gradient adds depth |
| Primary text | #FFFFFF | |
| Secondary text | #C9D1E0 | at least 7:1 on background |
| Keyword | #FFD400 (warm yellow) | never used for anything except emphasis |
| Card / panel | #1B2233, radius 16-24 | slight elevation |
| Shadow | #000000 at 35% | |
| Topic accent | from the table below | one per video, plus an optional second |

**Rule:** the keyword yellow is sacred. Topic accents must be clearly different from yellow (do not choose amber or gold as a topic accent unless the yellow is swapped).

### Chapter 11.3 Topic-to-palette mapping

Associations below are common in Western and Indian digital media; they are conventions, not universals. Pick the accent by topic, then check contrast.

| Topic | Accent 1 | Accent 2 | Mood |
|---|---|---|---|
| Money, finance, savings | #22C55E green | #10B981 emerald | growth, gain |
| Losses, debt, scams | #EF4444 red | #F97316 orange | danger, warning |
| Technology, AI, software | #3B82F6 blue | #8B5CF6 violet | intelligence, future |
| Cybersecurity, hacking | #22D3EE cyan | #EF4444 red | digital, threat |
| Health, medicine | #14B8A6 teal | #F43F5E rose | care, body |
| Fitness, energy | #F97316 orange | #EF4444 red | effort, heat |
| Mental wellbeing, sleep | #818CF8 indigo | #A78BFA lavender | calm, night |
| Nature, environment, farming | #84CC16 lime | #22C55E green | life |
| Space, science | #6366F1 indigo | #EC4899 magenta | wonder |
| Education, exams, careers | #3B82F6 blue | #22C55E green | trust, progress |
| History, culture | #D97706 ochre | #B45309 bronze | age, heritage (pick a yellow-safe tone) |
| Food | #F97316 orange | #EF4444 red | appetite |
| Love, relationships | #F43F5E rose | #EC4899 pink | warmth |
| Politics, government, law | #3B82F6 blue | #94A3B8 slate | authority |
| Water, weather, ocean | #0EA5E9 sky | #06B6D4 cyan | flow |
| Breaking news, alerts | #EF4444 red | #FFFFFF | urgency |
| Gaming, entertainment | #A855F7 purple | #22D3EE cyan | play |

### Chapter 11.4 Colour for story

- **Problem → solution:** red accent in the problem scenes, shifting to green or blue in the solution scenes. Animate the shift with `tint` over 10-15 frames at the turning point ("but here's the fix").
- **Before → after:** desaturated (grey icons, 30% saturation) for "before", full colour for "after".
- **Good vs bad comparisons:** consistent sides: good = accent green on the right, bad = red on the left, both kept for the whole video.
- **Emotional peaks:** a brief full-frame tint (accent at 10-20% opacity, 6-10 f) on the climax.

### Chapter 11.5 Accessibility and phone screens

- Never rely on red vs green alone to distinguish meaning; add icons (✓ / ✗), labels or position, because red-green colour blindness is common.
- Keep text contrast at least 4.5:1, preferably 7:1.
- Saturated pure blue (#0000FF) text on dark backgrounds is hard to read; use lighter blues (#60A5FA) for text.
- Phone screens in dark mode and at low brightness crush dark greys: keep background elements (cards, panels) at least 6-10% lighter than the background so they remain visible.
- Avoid large areas of pure saturated colour flashing quickly (photosensitivity): limit full-screen flashes to under 3 per second, and keep white flashes short (2-3 frames) and partial (under 80% opacity).

### Chapter 11.6 Apply in code

Keep a `TOPIC_PALETTES` dict keyed by topic tag (finance, scam, tech, health, sleep and so on) holding the two accents from the table, with a blue/cyan fallback. Validate each pick: the accent hue must sit at least 30° from the keyword yellow (about 50°) on the hue wheel, and reach 3:1 contrast against the background for icon fills and 4.5:1 for text.

---

## Part 12. The Divya master checklist and effect mapping

This final part brings the whole handbook together into one sequence Divya can run for every video, and one table connecting each principle to the effect and transition families in the code libraries.

### Chapter 12.1 Pre-production checklist (before rendering)

**Script and voice**
1. Hook line states tension, a number, or a "you" statement within the first 2-3 s. (Part 10)
2. VO at 140-170 words per minute; sentences 6-14 words. (Ch 10.3)
3. One open loop opened early, closed at 70-85%. (Ch 10.4)
4. Accent words marked: keyword, numbers, negatives, surprises. One per 3-5 s. (Ch 1.12, 2.10)
5. Word timestamps available from TTS.

**Style frame**
6. `STYLE` dict built: background, fonts, sizes, keyword yellow, topic accent, radius set, shadow, caption style. (Ch 5.2, Part 11)
7. Topic accent chosen from the palette table; contrast validated. (Ch 11.3, 11.6)
8. Primary, secondary and accent transition families chosen for the video. (Ch 4.7)
9. Role-to-effect mapping chosen (icons, numbers, labels, headline). (Ch 6.2)
10. Tempo profile chosen (fast / standard / calm) and its duration scale factor. (Ch 2.9)

**Beat sheet (animatic)**
11. Scenes split at sentence/clause boundaries; durations 0.8-4.5 s. (Ch 3.1, 4.6)
12. Each scene has one hero, key states tied to spoken words. (Ch 1.2, 2.3)
13. Each scene change has a relation tag (next, but, deeper, bigger picture, unrelated, reveal) and a direction. (Ch 4.5, 7.4)
14. Transition chosen by Rule-of-Six scoring and meaning guide, no immediate repeats. (Ch 3.2, 4.7)
15. SFX events listed with start, peak, and gain. (Ch 9.2)
16. Climax scene identified; acceleration before it, hold after it, silence before it. (Ch 4.6, 9.6)

### Chapter 12.2 Animation checklist (per scene)

17. All entrances eased (`expo`, `back`, `smooth`, or Material decel). No linear motion except progress bars and tickers. (Ch 1.1, 7.3)
18. Entrance durations: icons 8-10 f, headline lines 9 f, hero 12-14 f, words 3-5 f; exits two thirds of entrances. (Ch 1.4, 7.2)
19. Icons named by the VO enter 3-6 f before the word; caption highlights lead by 1-2 f. (Ch 1.13, 8.3)
20. Groups staggered 2-4 f, total spread under 15 f. (Ch 1.8, 7.5)
21. Travelling objects follow arcs (10-25% height). (Ch 1.5, 2.7)
22. Big moves get anticipation (5-12%, 2-6 f) and overshoot (4-12%). (Ch 1.6, 1.7)
23. Weight chosen per element: light / normal / heavy recipe. (Ch 1.9)
24. Squash/stretch within limits: icons ≤15%, text ≤8%, rigid objects ≤5%. (Ch 2.1)
25. Holds are moving holds: float, push-in 1-3%, or caption motion. No static second. (Ch 1.11)
26. Cycles offset in phase; at most two cycle types on screen; cycles start after entrances settle. (Ch 1.10)
27. Secondary actions are small (15-35% weight) and droppable when busy. (Ch 2.8)
28. Fast motion (>30 px/frame) gets motion blur. (Ch 2.11)
29. No more than two major moves in any 0.5 s window. (Ch 2.3)

**Layout and type**
30. Everything inside the safe area (x 40-610, y 140-1020). (Ch 0.2)
31. Spacing from the 8 px grid; inner/group/section gaps 16/32/80. (Ch 6.4)
32. At most 3 alignment lines per key state. (Ch 6.3)
33. Contrast: text ≥4.5:1 (prefer 7:1); hierarchy size steps ≥1.4×. (Ch 6.1)
34. Headline 68-84 px, 2-3 lines; keyword is the only yellow element. (Ch 8.5, 11.2)
35. Captions 48-60 px, 2-5 words, baseline y 900-1000, stroke 5-6 px. (Ch 8.2)
36. 35-50% negative space at each key state; one hero; 3-5 objects max. (Ch 2.3, 5.4)
37. Contact sheet reviewed: each key frame passes the five design questions. (Ch 5.1, 6.1-6.4)

**Editing and retention**
38. Frame 0 shows headline and hero; sound by frame 3; decisive motion by frame 10. (Ch 10.1)
39. Every 2.5 s window contains at least one interrupt; interrupt types vary. (Ch 10.2)
40. Scene changes on clause boundaries or 1-2 f before stressed content words; music snap within ±3 f only if the word rule holds. (Ch 3.4)
41. Hold 12-20 f after key reveals before cutting. (Ch 3.3)
42. Rapid-cut bursts no longer than 3 cuts. (Ch 3.3)
43. Avoid accidental near-identical cuts (3-15% frame difference): either animate or change more. (Ch 4.2)
44. Directional grammar consistent: forward = from right, back = from left, rise = from bottom. (Ch 4.5)
45. Match cuts used when consecutive heroes overlap (IoU > 60%); transition centre = hero centre. (Ch 4.3, 5.7)
46. Maximum: 2 shape wipes, 2 3D transitions, 1 spiral/spin zoom per video. (Ch 4.7)
47. Progress cue for list videos. (Ch 10.5)
48. End card 1.5-3 s, one CTA, pulse; loop-mode layout matches frame 0 if looping. (Ch 10.6, 10.7)

**Sound**
49. Whooshes start 4-6 f before cuts; pops on full-size frame; impacts on contact frame. (Ch 9.2)
50. No two SFX within 3 f unless designed; about one SFX per 0.7-1 s at most; variants rotated, pitch ±1-2 st. (Ch 9.2)
51. Music ducked 8-14 dB under VO, attack 20-80 ms, release 250-600 ms. (Ch 9.4)
52. VO high-passed at 90 Hz, presence +2-3 dB at 4 kHz; music carved −3 dB at 2.5 kHz. (Ch 9.5)
53. Master at −14 LUFS integrated, ≤ −1.5 dBTP, LRA under about 7. (Ch 9.3)

**Final render**
54. 720x1280, 30 fps constant, H.264 high profile, yuv420p, CRF 18-20, `+faststart`; AAC 48 kHz 160 kbps.
55. Watch once at full speed with sound, once muted. Muted viewing must still tell the story through headline, visuals and captions. (Ch 3.5)

### Chapter 12.3 Principle-to-effect mapping table

The table below links each principle from this handbook to the families in `effects_lib` (element-level effects with signature `fn(layer, t, start, duration)`) and `transitions_lib` (scene-level transitions). "Use for" gives the typical shorts moment; numbers are defaults.

| Principle (source) | effects_lib families | transitions_lib families | Use for / default numbers |
|---|---|---|---|
| Timing and spacing (Williams; Thomas & Johnston) | all, via EASES; fade, slide, scale | all, via ease argument | entrances 8-12 f expo; exits 6-8 f ease-in |
| Slow in / slow out | slide, scale, push, pull, pan | push, cover, uncover, zoom_through, zoom_out | smooth for on-screen moves 10-15 f |
| Squash and stretch | squash, stretch, jello, drop | stretch | landings: 2 f squash 10-15%, 4 f recover |
| Anticipation | scale (back), pull, swing | whip (with backward lean), spin_zoom | 5-12%, 2-6 f before main move |
| Follow-through / overlap | swing, jello, wiggle, float | split, blinds (staggered feel) | children lag 2-6 f |
| Arcs | spin, swing, drop (custom bezier path) | 3d_swing, 3d_roll, 3d_carousel | arc height 10-25% |
| Weight | drop, squash, shake, punch | dip, flash (for heavy impact) | heavy: 6-8 f fall + squash + 4-6 px shake |
| Staging | scale, fade, tint, blur (dim others) | zoom_through, circle (focus on hero) | 1 hero, others 30-50% opacity |
| Straight-ahead / procedural | glitch, rgb_jitter, handheld, shake | noise_dissolve, pixelate, rgb_split, posterize, blocks | seeded noise, 2-6 px |
| Secondary action | glow, float, pulse, heartbeat | — | 15-35% weight, start 2-6 f after hero |
| Exaggeration | punch, shake, flash, scale | flash, spin_zoom, zoom_through | 115-140% on 1-3 accents |
| Solid drawing / depth | flip3d, rotate, dutch | 3d_cube, 3d_flip, 3d_door, 3d_fold, 3d_tilt_zoom, 3d_persp_slide | consistent FOV and shadow |
| Appeal | reveal, scale (back), glow | circle, heart, star, diamond | rounded shapes, curve discipline |
| Cycles / walks | float, pulse, heartbeat, wiggle, spin | — | float 4-8 px / 2 s; pulse 5-8% / 0.8 s |
| Moving holds | push, pull, pan, handheld, float | — | 1-3% zoom over a hold |
| Cut on attention shift (Murch) | — | hard cut, whip, push | clause boundaries, 1-2 f before word |
| Emotion first (Rule of Six) | tint, blur, glow | blur_dissolve, luma, dip (soft); flash, rgb_split (shock) | choose by feeling first |
| Eye trace | slide (toward next focus), reveal | wipe, circle, box, zoom_through centred on hero | transition centre = hero centre |
| Blink / breath pause | fade | dip, blur_dissolve | cut inside 2-6 f of breath gap |
| Dissolve = time or soft link (Thompson & Bowen) | fade, blur | blur_dissolve, noise_dissolve, luma, dip | 12-18 f |
| Wipe = new section | reveal | wipe, clock, barn, blinds, checker, blocks, spiral, star, heart, wave, zigzag, diamond, box, circle | 8-14 f, one shape theme per video |
| Shared axis / sequence (Material) | slide, push | push, cover, uncover, split, 3d_persp_slide, 3d_carousel | next = from right; 8-12 f |
| Container transform | scale, reveal | zoom_through, box, circle | card grows into scene, 12-14 f |
| Fade through | fade, scale (0.92 → 1) | dip, blur_dissolve | unrelated topics, 10-14 f |
| Match cut | — | hard cut, circle, luma, zoom_through | hero IoU > 60% |
| Screen direction / 180° | slide (direction-coded), pan | push, wipe (angle-coded), 3d_door, 3d_page_turn | forward = right-to-left content motion |
| Contrast (R. Williams) | tint, glow, scale | flash, posterize | keyword sole yellow; size steps ≥1.4× |
| Repetition | role-locked families | primary/secondary family per video | 50% / 25% / accents |
| Alignment / proximity | slide along alignment axis | wipe aligned to layout edges | 8 px grid, 16/32/80 gaps |
| Kinetic type: meaning in motion | slide (rise), drop (fall), glitch (hack), heartbeat (love), blur (secret), shake (danger) | whip (fast), dip (pause) | 1-3 expressive words per video |
| Caption pop | scale (back), punch | — | 1.18 → 1.0, 4 f; lead 1-2 f |
| Pattern interrupt (retention) | punch, push (punch-in), shake, flash, glitch | any macro change | ≤2.5 s between interrupts |
| Hook impact | punch, scale, glow, flash | flash (from black only if instant) | decisive motion by f10 |
| Open-loop reveal | blur, reveal, flip3d, glow | 3d_flip, 3d_door, luma | blur 16 → 0 over 10 f |
| Loops | float, pulse | dip avoided; push or whip into f0 | last frame = first frame layout |
| Colour story (problem → solution) | tint | luma, blur_dissolve, posterize | tint shift over 10-15 f |
| Handheld / documentary feel | handheld, dutch, pan | — | 2-6 px, 0.2-0.6° |
| Digital / tech topics | glitch, rgb_jitter, flash | pixelate, rgb_split, blocks, checker, blinds, posterize | 4-8 f glitch bursts |
| Playful / soft topics | jello, wiggle, squash, heartbeat | heart, star, circle, wave, zigzag | bounce/back easing |
| Dramatic / premium topics | glow, push, rotate | 3d_cube, 3d_tilt_zoom, 3d_fold, 3d_page_turn, 3d_roll | 14-18 f, smooth |
| Energy / speed | spin, stretch, push | whip, spin_zoom, zoom_through, stretch | 6-10 f + motion blur + whoosh |
| End card | scale, glow, pulse, float | dip, zoom_out | 1.5-3 s, chime |

### Chapter 12.4 How to use the libraries with this handbook

- When calling `pick_fx(kind, tags, used, seed, recent_families)` or `pick_transition(tags, used, seed, recent_families)`, pass **meaning tags** derived from the script (for example `tech`, `warning`, `soft`, `next`, `reveal`, `energy`, `health`, `money`) so the picker selects families that match this handbook's mapping, and pass the last 2-3 families in `recent_families` to avoid repetition.
- After picking, apply this handbook's duration and easing defaults rather than any random value; then apply the tempo profile factor.
- Respect the per-video caps (shape wipes ≤2, 3D ≤2, spiral/spin_zoom ≤1, accents 1 per 3-5 s).
- Log every choice with its reason (`principle`, `meaning tag`, `word`), so a review can trace each effect back to the principle it serves.

### Chapter 12.5 Closing note and credits

The ideas in this handbook are restated in original words and adapted for vertical explainer shorts. For depth, Divya's human collaborators can study the source works directly:

- *The Animator's Survival Kit* by Richard Williams.
- *The Illusion of Life: Disney Animation* by Frank Thomas and Ollie Johnston.
- *In the Blink of an Eye* by Walter Murch.
- *Grammar of the Edit* by Roy Thompson and Christopher J. Bowen.
- *Design for Motion* by Austin Shaw.
- *The Non-Designer's Design Book* by Robin Williams.
- Google Material Design motion guidance (material.io / m3.material.io).

Numbers here are working defaults for Divya's 720x1280, 30 fps style; values from public specifications (Material tokens, the roughly −14 LUFS platform target, WCAG contrast) are approximate, so check the current specification when precision matters. The shared test of all these books stays the same: does the viewer understand, feel, and keep watching?
