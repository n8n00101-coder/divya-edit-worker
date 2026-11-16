# HyperFrames spike — v89 renderer candidate (graphics layer over real footage)

**What this is.** A proof that HyperFrames (github.com/heygen-com/hyperframes,
Apache-2.0, CLI v0.9.55) can serve as Julie's typography / motion-graphics /
compositing layer **on top of real footage** — never as a footage replacement.
Julie's asset priority is unchanged: real footage first; HyperFrames only
draws the title treatments, data graphics, maps and captions that sit over it.

**The test scene.** `index.html` + `compositions/` — "The Vanishing Coast",
45.0 s, 1920×1080, 30 fps, three scenes over one real drone clip
(Wikimedia Commons, "Oregon Coast Odyssey" FPV footage, public domain):

1. `scene1_title.html` (0–15 s) — kicker + masked-rise title treatment + sub-line.
2. `scene2_data.html` (15–30 s) — animated bar chart with count-up values
   (NASA sea-level rates 2.1 → 4.5 mm/yr, source line on screen).
3. `scene3_map.html` (30–45 s) — stylised SVG map, coastline draw-on, place
   marker + pulse, erosion ticks, then a kinetic payoff line ("BUT HOW FAST?").
4. `captions.html` (0–45 s) — one captions host, 9 phrase captions timed to
   the scene's narration script, key words in the accent colour.

The same scene script (same lines, same beats) is what the v88 renderer
comparison must use, so Ajju's 3-way pick (current renderer / HyperFrames /
Blender) compares renderers, not content.

**Run it**

```bash
cd hyperframes_spike
npx --yes hyperframes@0.9.55 check --json   # 0 errors at spike time
TMPDIR=<a big disk dir> npx --yes hyperframes@0.9.55 render
```

- `TMPDIR` matters: this VM's `/tmp` is a 512 MB tmpfs and the renderer
  refuses to start under ~1 GB free. On GitHub Actions runners `/tmp` is
  disk-backed and large; keep the override in the job env anyway.
- No audio by design: voice and music remain Julie's existing pipeline
  stages. HyperFrames' `film_silent` warning is expected for this layer.
- Fonts: Oswald + Inter resolve from the HyperFrames bundle by name.

**Verified at spike time (2026-11-16, this VM)**

- `check`: 0 errors; remaining warnings are documented in the v89 report
  (caption-host density, 24 px source microcopy under the 28 px phone
  floor — accepted for attribution lines, payoff type is 118 px).
- Render: 45.000 s, 1920×1080, 30 fps, exactly 1,350 frames, H.264.
  Freezedetect: no freeze ≥2 s. Frames eyeballed at 10 timestamps:
  every frame is full-frame real footage (A1 by construction — graphics
  are overlays, never islands), bars land on the spoken values, the map
  draw-on and payoff line land on their beats.
- Cost of the proof: 21 min render for 45 s on this 1.5-CPU shared VM in
  screenshot-capture mode. Actions runners (4 cores) are UNVERIFIED for
  this renderer — measure there before any production commitment.
- Output was 121 MB at the renderer's CRF 16 "looks" default; a delivery
  re-encode (Julie's pipeline already does one) is required.

**Integration shape (when Ajju picks this renderer)**

- Julie's Visual Director emits a scene script (beats, lines, visual
  kinds) → a codegen step writes these HTML compositions (one scene file
  per beat group, captions host from the caption track) → HyperFrames
  renders over the beat's real footage file → Julie's existing audio
  mix, QC and delivery stages run unchanged.
- The Director's menus gain nothing new; only the *executor* for the
  title / data / map / caption visual kinds changes.
