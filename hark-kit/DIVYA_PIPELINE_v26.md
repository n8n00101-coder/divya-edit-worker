# Divya Video Pipeline v26 (how Hark made the phantom-vibration video)

Run these steps in order. Save each step's output to KV (job_id/step) so a crash resumes from the last step.

## Step 1 - Angle (LLM)
Input: topic. Output angle.json
- 3 possible angles, pick the one with a surprise or a number.
- Hook: first line must be a question or shocking fact in under 8 words.
- 1 verified fact with source (name + year). No fact -> no number on screen.

## Step 2 - Script (LLM)
Output vo.json: 6-9 scenes, ONE sentence each, 6-14 words, total 20-35 s.
Each scene: {text, hit_word, hit_type: number|noun|shock|list|calm, visual_idea}
- visual_idea = a literal object/diagram for THAT sentence (never a mascot).

## Step 3 - Style plan (LLM)
Output style.json from topic mood:
{mood, bg (color/gradient + texture), accent1, accent2, font_head, font_body,
 motion: snappy|smooth|glitch|paper|typewriter, transition_family, sfx_set}
- Load last 5 style.json from KV. Must differ in accent1 + motion + transition_family.
- transition_family uses a topic object (phone swipe, heartbeat wipe, coin flip, paper tear, star zoom).

## Step 4 - Voice (code)
tts.py: edge-tts en-US-AndrewNeural (or te-IN-MohanNeural for Telugu).
Save mp3 per scene + WordBoundary events -> words.json [{word, start_ms, end_ms}].
Scene length = voice length + 0.25 s.

## Step 5 - Timeline (code, no LLM)
For each scene find hit_word in words.json.
- visual hit at word.start - 80 ms (2 frames at 25fps); SFX pop exactly at word.start.
- scene cut + whoosh at first word of next sentence.
- captions: word-by-word, current word in accent1.
Output timeline.json.

## Step 6 - Render (code)
render.py: PIL draws each frame, ffmpeg encodes.
- Background layer never scales. Content layer: push-in 1.00 -> 1.06 smoothstep.
- Pop: ease-out-back, max 1.10, settle 1.00 in 0.3 s.
- Safe box: x 8%-92%, y 10%-90%. Check every element's bbox at max scale; shrink element if outside.
- Max 2 accent colors, 1 font family pair, 1 effect at a time.
- Effects library: pick by hit_type tag (number -> count-up / ring fill; shock -> pop + flash; list -> one-by-one; calm -> slow push only).

## Step 7 - Audio mix (ffmpeg)
voice + SFX + music bed ducked (sidechaincompress) -> loudnorm I=-14 TP=-1.

## Step 8 - Self-check (LLM looks at frames)
Extract 1 frame per scene + 1 frame at each hit word. Score each 1-5:
clear, on-time, in-frame, on-topic, neat. Any < 4 -> fix that scene (change params), re-render only that scene. Max 2 loops.
Extra question: "With voice muted, can you guess the topic from visuals and transitions?" No -> redo Step 3.

## Step 9 - Deliver + learn
Send mp4 in chat. Ask: "Nachinda? 1 word cheppandi." Save feedback + style.json to KV; next video avoids what was disliked.

---

## Creative-director prompt for Divya (use as system prompt for Steps 1-3 and 8)

You are a short-video editor. You never fill a template. For every topic you think fresh:
1. Find the surprising angle and a hook under 8 words.
2. Write one sentence per scene. For each sentence choose ONE word that deserves an effect: a number first, then the topic noun, then a contrast word. No other word gets an effect.
3. Choose a visual that shows the literal meaning of that sentence. Never use a mascot or the same character across scenes.
4. Choose a style from the topic's mood, different from your last 5 videos. Transitions must use an object from the topic.
5. Less is neat: one idea per scene, two accent colors, one font pair, nothing on screen the voice does not mention.
6. After render, look at the frames like a strict human editor. If anything is cut at the edge, overlapping, busy, late, or off-topic, fix it before you send.
Output only valid JSON in the schema asked for.
