# Julie / Divya — Video Editing Playbook

A practical knowledge base for editing Shorts, Reels and YouTube videos. Read it as rules of thumb
from a working editor, not as law: when the owner asks for something different, the owner wins.

---

## 1. The core idea: retention

Every editing choice answers one question: *does the viewer keep watching?*
- Viewers decide in **1-2 seconds** whether to stay. The first frame and first spoken line matter more than everything else.
- Dead air, slow intros, logos, "hi guys welcome back" — cut them.
- Something must **change on screen every 2-4 seconds** (a cut, a zoom, a caption pop, a B-roll, a graphic).
- The ending should loop back or pay off; a clean loop on Shorts lifts rewatch rate.

---

## 2. Shorts / Reels pacing

| Item | Target |
|---|---|
| Length | 15-45 s (sweet spot 20-35 s); Shorts max 3 min, Reels max 3 min (90 s for best reach) |
| Hook | first 1-2 s, on screen + spoken |
| Average shot length | 2-4 s; faster (1-2 s) in montages, slower (4-6 s) only on emotional beats |
| Silence gaps | cut anything > 0.3-0.4 s between sentences |
| Pattern interrupt | every 5-8 s (B-roll, zoom, sound effect, graphic) |
| Payoff | before the last 3 s; then end or loop |

**Structure that works:** Hook (0-2 s) → Promise / context (2-5 s) → Value beats (one idea per 3-5 s) → Payoff → CTA or loop (last 1-2 s).

---

## 3. Hooks (first 1-2 seconds)

- Start **mid-action** or **mid-sentence** of the most interesting line. Move the best moment to the front if needed (cold open).
- Put a **hook text** on screen in the first frame: 3-7 words, big, high contrast (e.g. "IDI MEEKU TELIYADU", "3 mistakes everyone makes").
- Hook formulas: curiosity gap ("Nobody tells you this…"), bold claim, numbered list ("3 signs…"), direct question, visual surprise, before/after.
- The first frame must already look good as a still (it is often the thumbnail on Shorts).
- Never start on a black frame, a fade-in, or a logo.

---

## 4. Cutting techniques

- **Jump cuts:** remove pauses, ums, repeated takes. Keep the speaker's rhythm natural — leave 0.05-0.15 s of breath so it does not sound robotic.
- **Punch-ins (zoom cuts):** alternate framing 100% ↔ 110-120% on each jump cut to hide the jump and add energy. Punch in harder (130%) on punchlines.
- **J-cut:** next clip's **audio starts before** its picture (hear it, then see it). Smooth and conversational.
- **L-cut:** previous clip's **audio continues over** the next picture. Great for B-roll over talking.
- **Match cut:** cut on a matching shape or motion between two clips.
- **Cut on action:** cut in the middle of a movement; the motion hides the edit.
- **Smash cut:** abrupt cut from calm to loud (or vice versa) for comedy/drama.
- Hard cuts are the default. Transitions are seasoning, not the meal.

---

## 5. Captions

- Burned-in captions are mandatory for Shorts/Reels (most people watch muted at first).
- **Style:** 1-4 words per line, word-by-word highlight (current word in yellow/green), bold, thick black outline (4-6 px at 1080w) or soft shadow box.
- **Size:** about 55-75 px at 1080×1920 for punchy captions; never smaller than ~42 px.
- **Position:** lower-middle (about 60-72% down from the top) — clear of the platform UI.
- **Telugu:** use **Noto Sans Telugu** (Bold for captions). Check conjunct characters (ఒత్తులు) render correctly — libass with the right font handles shaping; drawtext may break complex shaping, so prefer ASS subtitles for Telugu.
- Fix typos and wrong transcriptions before burning in. Wrong Telugu words look worse than no captions.
- Emphasis words: colour change or scale pop (108-115%) for 0.1-0.15 s; don't animate every word.
- Emojis in captions only if the font supports them; otherwise skip.

### 9:16 safe zones (1080×1920)
- **Top ~250 px:** status bar / channel name — keep text out.
- **Bottom ~380-450 px:** caption/description, music ticker, buttons — keep important text out.
- **Right ~120-150 px:** like/comment/share buttons (Reels/TikTok/Shorts).
- Safe area for key text: roughly x 60-930, y 250-1450.

---

## 6. Audio (half of the "pro" feel)

- **Loudness:** final mix **-14 LUFS integrated**, true peak ≤ -1.5 dBTP (YouTube / Instagram / Spotify normalise to about -14).
  `loudnorm=I=-14:TP=-1.5:LRA=11`
- **Clean voice chain:** high-pass 80 Hz → denoise (`afftdn=nf=-25`) → presence EQ (+2-3 dB at ~3 kHz) → compressor (3:1) → loudnorm.
- **De-ess** if sibilance is harsh: `deesser` filter or EQ dip at 6-8 kHz.
- **Music under voice:** voice dominant; music sits about **-18 dB under VO** (roughly 0.12-0.2 linear volume while speaking), ducked automatically with `sidechaincompress`. Music can rise between sentences and at the end.
- **Sound effects (SFX):** whoosh on transitions, pop on text appear, riser before reveal, bass hit on punchline. Keep them subtle (-10 to -6 dB below voice).
- Never let music have vocals fighting the speaker's words.
- Room tone: avoid total digital silence mid-video; it feels broken.
- Copyright: only use music the owner sent or royalty-free tracks.

---

## 7. Colour grading basics (ffmpeg)

Order: **fix exposure/white balance → contrast → saturation → creative look**.
- Exposure / contrast / saturation: `eq=brightness=0.03:contrast=1.08:saturation=1.15:gamma=1.0`
- White balance (warm): `colorbalance=rs=.06:gs=.01:bs=-.06`; (cool): `colorbalance=rs=-.05:bs=.07`
- S-curve for punch: `curves=preset=medium_contrast` or `curves=m='0/0 0.25/0.20 0.75/0.82 1/1'`
- Teal & orange (subtle): `colorbalance=rs=.05:bs=-.05:rh=-.03:bh=.05`
- Black & white: `hue=s=0,eq=contrast=1.15`
- LUT: `lut3d=file=look.cube` (keep intensity sane; blend via `split` + `blend=all_opacity=0.6` if too strong)
- Sharpen lightly: `unsharp=5:5:0.8:3:3:0.4`
- Vignette for focus: `vignette=PI/5`
- Skin tones must still look like skin. If faces look orange or grey, back off.
- Match colour between clips before applying a look.

---

## 8. Transitions

- Default: **hard cut**. Use transitions to signal a change of topic/place/time.
- Useful xfade kinds: `fade`, `dissolve`, `slideleft`, `smoothleft`, `circleopen` (iris), `wipeleft`, `zoomin`, `pixelize`, `hblur`, `fadeblack`.
- Duration: 0.2-0.4 s for Shorts, 0.5-1 s for long form.
- Whip/zoom transitions: pair with a whoosh SFX.
- Never more than 2-3 different transition styles in one video.

---

## 9. B-roll and visuals

- Cover jump cuts and abstract talk with B-roll that **shows** what is said (said "money" → show money/app/screen, not a random stock city).
- B-roll shots 1-3 s each; use L-cuts to keep the voice continuous.
- Screen recordings: zoom into the area being talked about; highlight with a box/arrow.
- Text graphics: 1-3 word labels beat full sentences.
- Avoid generic stock icons and overused stock footage; specific beats generic.

---

## 10. Retention tricks

- Open loops: "the third one is the worst" → keep them to the end.
- Progress cues: numbers (01/05), progress bar, checklist.
- Visual change every 2-4 s; audio change (SFX/music shift) every 5-10 s.
- Re-hook at ~40-50% of the video ("but here's where it gets interesting").
- Cut the outro. End on the payoff; on Shorts, make the last frame flow into the first (loop).
- Captions that **highlight keywords** keep eyes on screen.

---

## 11. Thumbnails (long-form; also Shorts cover frame)

- 1280×720 (16:9) for YouTube long-form; 1080×1920 cover frame for Shorts/Reels.
- One face with clear emotion + 2-4 words of big text + one strong focal object.
- High contrast, saturated, readable at phone size (test at ~150 px wide).
- Text must not repeat the title; it adds curiosity.
- Keep bottom-right clear on YouTube (timestamp overlay).

---

## 12. Export specs

| Platform | Resolution | FPS | Codec | Audio | Notes |
|---|---|---|---|---|---|
| YouTube Shorts | 1080×1920 (9:16) | 30 (or source 24/25/60) | H.264 High, yuv420p | AAC 128-320 kbps, 48 kHz | ≤ 3 min |
| Instagram Reels | 1080×1920 | 30 | H.264, yuv420p | AAC 128 kbps+, 44.1/48 kHz | ≤ 3 min; cover 1080×1920 |
| YouTube long-form | 1920×1080 (or 3840×2160) | source fps | H.264 High | AAC 384 kbps stereo | -14 LUFS |
| WhatsApp send | ≤ 16 MB | 30 | H.264 | AAC 96-128 kbps | compress or send link |

Standard Shorts/Reels encode:
```
ffmpeg -i in.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30" \
  -c:v libx264 -profile:v high -pix_fmt yuv420p -preset medium -crf 20 \
  -c:a aac -b:a 160k -ar 48000 -movflags +faststart out.mp4
```

---

## 13. ffmpeg recipe snippets

**Trim (accurate):** `ffmpeg -ss 00:00:05 -to 00:00:30 -i in.mp4 -c:v libx264 -c:a aac out.mp4`

**Vertical crop (centre):** `-vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"`

**Vertical with blurred background (keeps full 16:9 frame):**
```
-filter_complex "[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"
```

**Detect silence:** `ffmpeg -i in.mp4 -af silencedetect=noise=-32dB:d=0.5 -f null -`

**Punch-in on a time range:** `-vf "crop=iw/1.15:ih/1.15,scale=1080:1920" ` (apply to that segment, then concat) or overlay with `enable='between(t,4,8)'`.

**Slow Ken-Burns zoom on a still:** `zoompan=z='min(zoom+0.0015,1.2)':d=125:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30`

**Shake (impact):** `crop=iw-20:ih-20:10+8*sin(t*60):10+8*cos(t*50)` for 0.2-0.3 s.

**Text with Telugu font:** `drawtext=fontfile=/usr/share/fonts/truetype/noto/NotoSansTelugu-Bold.ttf:text='...':fontsize=64:fontcolor=white:borderw=5:bordercolor=black:x=(w-tw)/2:y=h*0.65` (prefer ASS for Telugu shaping).

**Burn ASS subtitles:** `-vf "ass=subs.ass:fontsdir=/usr/share/fonts/truetype/noto"`

**Music ducked under voice:**
```
[1:a]volume=0.35[m];[0:a]asplit[v][sc];[m][sc]sidechaincompress=threshold=0.03:ratio=10:attack=20:release=400[d];[v][d]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5
```

**Crossfade two clips:** `[0:v][1:v]xfade=transition=fade:duration=0.4:offset=<dur0-0.4>; [0:a][1:a]acrossfade=d=0.4`

**Speed ramp 1.5×:** `[0:v]setpts=PTS/1.5[v];[0:a]atempo=1.5[a]`

**Freeze frame 1 s at 3 s:** `tpad` / or split + `loop=loop=30:size=1:start=90`

**Extract frames to review:** `ffmpeg -ss 5 -i in.mp4 -frames:v 1 -q:v 3 f.jpg`

**Black frame detection:** `ffmpeg -i in.mp4 -vf blackdetect=d=0.2:pix_th=0.1 -f null -`

**Loudness measurement:** `ffmpeg -i in.mp4 -af loudnorm=print_format=summary -f null -`

**Render PIL frames → video:** pipe raw RGB frames to `ffmpeg -f rawvideo -pix_fmt rgb24 -s 1080x1920 -r 30 -i - -c:v libx264 -pix_fmt yuv420p out.mp4`

---

## 14. Quality checklist before sending

1. Plays from start to end, correct length, has a video stream and (if expected) audio.
2. No black/frozen frames at start or middle.
3. Captions inside safe zones, not cut off, no overlap with other text, no typos.
4. Audio around -14 LUFS, no clipping, music not louder than voice.
5. Hook visible in the first frame.
6. Correct aspect ratio (1080×1920 for Shorts/Reels).
7. File size fits the delivery channel (WhatsApp ≤ 16 MB, else link).

---

## 15. Split-screen explainer style guide (owner's signature style)

Turn each voice-over line into a real-life object/interface the viewer uses and make it do what the line says (silent treatment -> chat 'Seen' + SILENCE timer; past -> old Polaroid circled red; victim card -> playing card VICTIM; pause -> Q...GAP...A slider; hurts -> EKG under HURTS). Near-black bg, red accent, white bold caps, green positive, yellow emphasis; banner naming the list; card tag + number 04/07, progress bar, punch word, RED FLAG stamp; new card every 3-5s in 25-27s Short, hard cuts, small motion inside cards, end RECAP + FINAL WORD. Faceless 9:16; terminal mono font, typing cursor, [04/08], ASCII bar; small text (headers ~44px, body 26-42, punch ~58 at 1080w). Effects: kinetic text, counter roll-up, object animation, draw-on graph, before/after crack, zoom push + shake, paper card + highlight + stamp, glitch slice on card change. Visual-first: 1-3 word labels. Latest: one simple pawn/bean silhouette character, fake-3D shading, soft shadows, camera moves, creative transitions (iris, push, wipe, zoom-flash, blinds). Telugu VO via edge-tts te-IN-MohanNeural; Telugu subs Noto Sans Telugu; render PIL frames piped to ffmpeg; avoid generic stock icons; check typos.
