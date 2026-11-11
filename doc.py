"""Divya documentary engine v2: topic (or AUTO) -> 45-60 s cinematic 9:16 video. No footage needed.
LLM story plan (hook -> context -> twist -> payoff -> CTA, per-scene mood) -> human-sounding neural voice
(English Andrew/Ava multilingual or Telugu Mohan/Shruti) with per-mood rate/pitch -> animated scenes
(mood palettes, bokeh, 3D-shaded character, animated objects, kinetic labels) -> camera push/pan/shake ->
6 transition kinds -> procedural cinematic music + whoosh/boom SFX, ducked under voice -> word-timed karaoke
captions (libass) -> film grade (vignette + grain). Rendered in parallel processes. Free, CPU only.
v29: Hark's effects.py (Blind) — 14 ENTER, 11 EMPHASIS, 12 TRANSITIONS, picked by the hit word's meaning, max 2x per video."""
import asyncio, json, math, multiprocessing as mp, os, random, re, subprocess, sys, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import create as C
import effects as FX  # v29: Hark's effects library (Blind, divya-v26-effects.zip) — 14 ENTER, 11 EMPHASIS, 12 TRANSITIONS, 10 easings
import transitions_lib as TL  # v29b: Hark's 379-transition library (Blind, divya-v29-transitions.zip) — 40 families, incl. 3D
# v29b: transitions slower than 200 ms/frame at 1080x1920 (measured on this VM;
# the render is offline + parallel, but these 10 would dominate it). Excluded
# from the pick pool; 369 remain.
TL_SLOW = {"wipe_0_hard_smooth", "heart_in", "zigzag_180_n6", "zoom_through_1.6_expo",
           "spin_zoom_0.6_smooth", "spin_zoom_0.6_expo", "spin_zoom_1.0_smooth",
           "spin_zoom_1.0_expo", "spin_zoom_1.6_smooth", "spin_zoom_1.6_expo"}
TL_FAST = [e for e in TL.REGISTRY if e["name"] not in TL_SLOW]
TL_BY_NAME = {e["name"]: e["fn"] for e in TL_FAST}
# v29b: the per-video custom effects module (video_fx.py, written by the LLM,
# sandbox-tested). Set by make_video(); None = library fallback only.
VIDEO_FX = None


W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
TR = 0.36  # transition length (s)
OUTRO = 2.2
MOODS = {  # top, bottom, accent, (rate, pitch)
    "calm": ((16, 30, 52), (4, 8, 16), (90, 170, 255), ("-3%", "-1Hz")),
    "tense": ((52, 12, 16), (8, 3, 5), (235, 50, 60), ("+3%", "-3Hz")),
    "hopeful": ((18, 48, 40), (3, 12, 10), (60, 215, 140), ("+2%", "+2Hz")),
    "sad": ((28, 30, 46), (7, 7, 12), (130, 140, 185), ("-9%", "-4Hz")),
    "excited": ((60, 30, 8), (10, 5, 3), (255, 170, 40), ("+9%", "+3Hz")),
    "mystery": ((34, 16, 52), (6, 4, 12), (175, 95, 255), ("-6%", "-3Hz")),
}
# v25 (R49, Hark aesthetic variety — ~/workspace/styles/HARK-AESTHETIC-VARIETY.md):
# one design system per TOPIC MOOD, never one fixed style. The topic picks the look
# (A-D); the title seed varies accent/font/layout inside it; the previous video's
# look is never repeated. Constants only: 9:16 safe margins, big readable captions,
# one idea per scene, one accent colour at a time.
LOOKS = {
    "A": {"name": "science", "top": (8, 24, 48), "bot": (6, 60, 70),
          "accents": [(60, 200, 230), (255, 180, 60)], "font": "anton", "chapter": "fig",
          "ease": "smooth", "motion": "push", "bg": "gradient",
          "motion_personality": "smooth glides", "transition_family": "zoom through the diagram",
          # v29 (Hark's effects.py): the look's transition TAG picks from FX.TRANSITIONS;
          # the camera moves are for narrow visuals only (WIDE_VISUALS get push-in).
          "fx_tag": "space", "moves": ["push", "pan", "drift"],
          "desc": "deep navy to teal gradient, cyan/amber accent, thin line diagrams, animated plots, clean sans — lightning, physics, how-things-work"},
    "B": {"name": "myth", "top": (10, 10, 10), "bot": (24, 24, 24),
          "accents": [(255, 40, 40), (255, 210, 0)], "font": "anton", "chapter": "stamp",
          "ease": "hard", "motion": "cut", "bg": "flat",
          "motion_personality": "snappy pops", "transition_family": "hard cut + stamp slam",
          "fx_tag": "warning", "moves": ["push", "whip"],
          "desc": "high-contrast black and white, one hot red or yellow accent, huge bold condensed type, hard cuts, stamp/strike-through — myths, warnings, versus"},
    "C": {"name": "story", "top": (40, 30, 20), "bot": (24, 18, 12),
          "accents": [(250, 230, 200), (230, 120, 50), (60, 170, 160)], "font": "serif", "chapter": "none",
          "ease": "slow", "motion": "push", "bg": "warm",
          "motion_personality": "slow push-ins", "transition_family": "paper tear / fade",
          "fx_tag": "history", "moves": ["push", "drift"],
          "desc": "warm film grain, soft vignette, serif/elegant type, slow push-ins, cream/orange/teal grade, minimal text — movies, history, emotion"},
    "D": {"name": "tech", "top": (12, 14, 28), "bot": (8, 10, 22),
          "accents": [(60, 255, 140), (170, 100, 255)], "font": "anton", "chapter": "counter",
          "ease": "snappy", "motion": "whip", "bg": "grid",
          "motion_personality": "snappy easing", "transition_family": "screen swipe / coin flip",
          "fx_tag": "tech", "moves": ["push", "pan", "whip"],
          "desc": "light or dark glassy UI, neon green/violet accent, big animated numbers, bar/line charts, grid backgrounds, snappy easing — stats, AI, finance"},
}
# v29: visuals that extend to the frame edges — only a centered push-in is safe
# for them (a pan/whip would push them off-screen, Ajju's complaint). Narrow,
# centered visuals can take any camera move.
WIDE_VISUALS = {"versus", "bar", "bar_compare", "graph", "list", "checklist",
                "arrows_steps", "dot_grid", "calendar", "chat", "battery"}
# v29: FX enter/emphasis effects that transform a whole RGBA layer (L, t, st).
# typewriter/draw_on_line/stagger draw their own content, so they are not used
# as layer effects here. The rest are chosen by the scene's hit_type tag.
FX_LAYER_ENTER = ["fade_in", "pop_in", "slide_in", "rise_in", "drop_in",
                  "zoom_in_blur", "wipe_in", "iris_in", "spin_in", "flip_in", "glitch_in"]
FX_LAYER_EMPHASIS = ["punch", "shake", "pulse", "wiggle", "glow"]
_LOOK_WORDS = {
    "A": ["lightning", "thunder", "physics", "science", "how", "why", "earth", "space", "atom", "energy", "water", "rain", "magnet", "gravity", "biology", "brain", "body", "experiment", "plant", "animal", "sky", "sun", "moon", "weather", "electric", "sound", "light", "ocean", "volcano"],
    "B": ["myth", "myths", "safety", "warning", "danger", "scam", "lie", "lies", "truth", "vs", "versus", "debate", "ban", "never", "don't", "mistake", "wrong", "fact", "fake", "car", "seat belt", "belt", "helmet", "rule", "law", "court", "tobacco", "gutka", "smoking", "alcohol", "drugs", "effects", "risk", "risks", "health"],
    "C": ["story", "movie", "cinema", "history", "culture", "emotion", "love", "king", "queen", "war", "ancient", "legend", "film", "song", "festival", "hero", "empire", "temple", "village", "family", "mother", "father", "kingdom", "princess", "poet", "dance"],
    "D": ["ai", "tech", "money", "finance", "data", "stat", "app", "phone", "computer", "robot", "crypto", "stock", "price", "users", "percent", "growth", "startup", "internet", "software", "code", "digital", "online", "bank", "rupee", "dollar", "salary", "job", "business"],
}


def hit_type_of(s):
    # v29 (EFFECTS_GUIDE.md section 1): the hit word's MEANING picks the effect.
    # Derived from the scene's label + value + voice-over (no TTS timings needed
    # here — the timing itself still comes from the word timestamps in make_video).
    txt = (str(s.get("label", "")) + " " + str(s.get("vo", ""))).lower()
    val = str(s.get("value", ""))
    if "%" in val or "%" in txt: return "percent"
    if any(c.isdigit() for c in val): return "number"
    if any(w in txt for w in ("danger", "warning", "risk", "scam", "fake", "poison", "kill")): return "warning"
    if any(w in txt for w in ("but", "never", "only", "stop", "wrong", "lie", "myth")): return "shock"
    if any(w in txt for w in ("first", "second", "third", "three things", "three ways", "steps")): return "list"
    if any(w in txt for w in (" vs ", "versus", " than ", "better")): return "compare"
    if any(w in txt for w in ("rise", "grow", "increase", "more", "higher", "up")): return "growth"
    if any(w in txt for w in ("fall", "drop", "down", "less", "lower", "crash")): return "drop"
    if any(w in txt for w in ("clock", "time", "year", "history", "ancient", "ago")): return "time"
    if any(w in txt for w in ("money", "rupee", "price", "cost", "salary", "pay", "bank")): return "money"
    if any(w in txt for w in ("health", "body", "heart", "brain", "sleep", "food")): return "health"
    if any(w in txt for w in ("space", "lightning", "science", "sky", "star", "planet")): return "space"
    if any(w in txt for w in ("funny", "laugh", "joke")): return "funny"
    return "calm"


def pick_look(brief, recent="", recent_styles=None):
    """Topic mood -> design system (A/B/C/D). Never repeats the last 5 videos'
    looks: the Worker stores each finished video's look in KV (styles:<user>,
    most recent last) and passes the last 5 here as `recent_styles`. The kit's
    rule — the style plan must differ from the last 5 (palette + motion +
    transition). Deterministic — never random."""
    import zlib
    text = (brief or "").lower()
    scores = {k: sum(1 for w in words if w in text) for k, words in _LOOK_WORDS.items()}
    best = max(LOOKS, key=lambda k: scores[k])  # ties -> A (first), the safe default
    if recent_styles:
        used = [s for s in (recent_styles or []) if s in LOOKS][-5:]
        if best in used:
            # prefer a look NOT used in the last 5 (by keyword score);
            # if all 4 are used, take the least recently used one.
            unused = [k for k in LOOKS if k not in used]
            if unused:
                best = max(unused, key=lambda k: scores[k])
            else:
                last_seen = {k: max([i for i, s in enumerate(used) if s == k], default=-1) for k in LOOKS}
                best = min(LOOKS, key=lambda k: last_seen[k])
        return best
    # Fallback (no KV styles yet): derive the look of each of the last 5 topics
    # from the topic words (same keyword scoring) and avoid all of them. The
    # Worker passes the last 15 topics in `recent`, most recent last.
    used = []
    if recent:
        last = [s.strip() for s in str(recent).split(";") if s.strip()][-5:]
        for tp in last:
            ps = {k: sum(1 for w in words if w in tp.lower()) for k, words in _LOOK_WORDS.items()}
            if max(ps.values()) > 0:
                used.append(max(ps, key=lambda k: ps[k]))
    if used and best in used:
        unused = [k for k in LOOKS if k not in used]
        if unused:
            best = max(unused, key=lambda k: scores[k])
        else:
            last_seen = {k: max([i for i, s in enumerate(used) if s == k], default=-1) for k in LOOKS}
            best = min(LOOKS, key=lambda k: last_seen[k])
    return best


def look_seed(title, brief=""):
    import zlib
    return zlib.crc32((str(title or "") + "|" + str(brief or "")).encode()) & 0x7FFFFFFF
VOICES = {("en", "male"): "en-US-AndrewMultilingualNeural", ("en", "female"): "en-US-AvaMultilingualNeural",
          ("te", "male"): "te-IN-MohanNeural", ("te", "female"): "te-IN-ShrutiNeural",
          ("hi", "male"): "hi-IN-MadhurNeural", ("hi", "female"): "hi-IN-SwaraNeural"}

PLAN = """You are a top YouTube documentary-shorts writer and director. Plan ONE faceless 9:16 video from the owner's request.
Return ONLY JSON:
{"topic": "...", "title": "<2-5 word English title, caps>", "lang": "en|te|hi", "voice": "male|female",
 "caption": "<post caption with 3-5 hashtags>",
 "scenes": [{"vo": "...", "label": "<1-3 word ENGLISH punch label, caps>", "mood": "calm|tense|hopeful|sad|excited|mystery",
             "visual": "<one of %s>", "value": "<short number/word for the visual>"}]}
DESIGN LOOK (v25, Hark aesthetic variety): {look} — design every scene for this look: palette, background,
visuals and chapter style all follow it. A science: graph/clock/counter/bar visuals, diagram labels.
B myth/safety: warning/versus/check visuals, stamp chapter cards, huge bold labels.
C story/cinema: heart/check visuals, minimal text, NO chapter labels, elegant labels.
D tech/data: counter/bar/graph/list visuals, big number chapter cards, animated numbers.
New visuals (v28, Hark kit): dot_grid/donut for a percentage of people, gauge for a level,
toggle for on/off, phone_buzz for phone notifications, stick_figure for a person/feeling,
quote_card for a quote, arrows_steps for a process, checklist for steps, document for a
report, polaroid for a memory, icon_row for a set of items, bar_compare for two numbers.
Language: follow the owner. If they ask for English voice/voice-over -> lang "en" (vo in English). Telugu -> "te" (vo in Telugu script).
Hindi -> "hi". If they say nothing about language, use "te".
Length: honour any duration they ask (e.g. "1 min" = 60 s). Default 50-60 s. English speaks ~2.5 words/s, Telugu ~1.8 words/s:
size the total vo words to the target duration. 9-14 scenes, each vo 6-22 words.
Writing: documentary storytelling that sounds like a real human talking to a friend - contractions, short punchy sentences,
rhetorical questions, a surprising fact or tension in the first line (hook), then context, a twist, the payoff, and a short
call to follow at the end. Use commas, "..." and dashes for natural pauses. No emojis, no hashtags in vo. Vary the mood per scene to
build an emotional arc. Each visual must literally show the line's idea (battery=energy, chat=messages/people, graph=growth or fall,
clock=time, calendar=days, warning=danger/mistake, check=right way, versus=comparison, counter=a number, list=steps, heart=love/health,
bar=progress, dot_grid/donut=a percentage of people, gauge=a level, toggle=on/off, phone_buzz=phone notifications,
stick_figure=a person/feeling, quote_card=a quote, arrows_steps=a process, checklist=steps, document=a report,
polaroid=a memory, icon_row=a set of items, bar_compare=two numbers compared).
If no clear topic is given ("nuvve select chesko", "any", "AUTO", empty) choose a fresh high-retention topic yourself (psychology,
history mysteries, science facts, money habits, health, tech, motivation). Avoid these recent topics: {recent}.
Owner request: """ % C.VISUALS


def plan(brief, chat, recent="", recent_styles=None, recent_families=()):
    # v25: the TOPIC MOOD picks the design system (A/B/C/D) FIRST, so the LLM
    # designs every scene for that look — never one fixed style.
    # v27 (Hark kit style plan): the look also carries a motion personality +
    # transition family from the topic mood, so the motion differs per video too.
    # v28: recent_styles (the last 5 looks, from KV) keeps the look from repeating.
    # v29b: recent_families (transition families used in the last 5 videos, from
    # KV) keeps the TRANSITIONS from repeating too — step 7 of
    # DIVYA_NEW_CODE_EVERY_VIDEO.md. Empty until the Worker KV wiring lands
    # (needs Ajju's go); within-video no-repeat already works via `tl_used`.
    # v25: the TOPIC MOOD picks the design system (A/B/C/D) FIRST, so the LLM
    # designs every scene for that look — never one fixed style.
    # v27 (Hark kit style plan): the look also carries a motion personality +
    # transition family from the topic mood, so the motion differs per video too.
    # v28: recent_styles (the last 5 looks, from KV) keeps the look from repeating.
    look = pick_look(brief, recent, recent_styles)
    look_line = (f"DESIGN LOOK {look} ({LOOKS[look]['name']}): {LOOKS[look]['desc']}. "
                 f"Motion personality: {LOOKS[look]['motion_personality']}. "
                 f"Transition family: {LOOKS[look]['transition_family']}.")
    raw = chat([{"role": "system", "content": "You output strict JSON only."},
                {"role": "user", "content": PLAN.replace("{recent}", recent or "none").replace("{look}", look_line) + (brief or "AUTO")}])
    p = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))
    sc = [s for s in p.get("scenes", []) if str(s.get("vo", "")).strip()][:16]
    if len(sc) < 4:
        raise ValueError("plan too short")
    for s in sc:
        s["vo"] = re.sub(r"[#*_`]", "", str(s["vo"])).strip()
        if s.get("visual") not in C.VISUALS: s["visual"] = random.choice(C.VISUALS)
        if s.get("mood") not in MOODS: s["mood"] = "calm"
        s["label"] = re.sub(r"[^A-Z0-9 %!?'&-]", "", str(s.get("label", "")).upper())[:20] or "WAIT"
        s["value"] = str(s.get("value", ""))[:8]
    p["scenes"] = sc
    p["lang"] = p.get("lang") if p.get("lang") in ("en", "te", "hi") else "te"
    p["title"] = re.sub(r"[^A-Z0-9 %!?'&-]", "", str(p.get("title", "")).upper())[:26] or "WATCH THIS"
    # v25: the look + a title seed (so no two videos match inside a look).
    # v27: the style plan (motion personality + transition family) rides with it.
    p["look"] = look
    p["seed"] = look_seed(p["title"], brief)
    p["accent"] = LOOKS[look]["accents"][p["seed"] % len(LOOKS[look]["accents"])]
    p["motion_personality"] = LOOKS[look]["motion_personality"]
    p["transition_family"] = LOOKS[look]["transition_family"]
    # v29 (Hark's effects.py + EFFECTS_GUIDE.md): the effect for each scene is
    # CHOSEN ONCE HERE, from the hit word's meaning — never the same pop on
    # every scene. FX.pick() blocks any effect used more than 2x in one video,
    # so the motion actually varies. The choices ride in the plan; scene_frame
    # only applies them (deterministic per frame).
    used = {}
    enter_l = {k: v for k, v in FX.ENTER.items() if k in FX_LAYER_ENTER}
    emph_l = {k: v for k, v in FX.EMPHASIS.items() if k in FX_LAYER_EMPHASIS}
    for s in sc:
        s["hit_type"] = hit_type_of(s)
        s["enter"] = FX.pick(enter_l, [s["hit_type"]], used)
        s["emphasis"] = FX.pick(emph_l, [s["hit_type"]], used)
        s["label_enter"] = FX.pick(enter_l, [s["hit_type"]], used)
    # one transition per scene boundary, from the look's topic tag (guide s2).
    # v29b: Hark's 379-transition library — TL.pick_transition never repeats a
    # NAME in one video and skips families from the last 5 videos (recent_families,
    # from KV once the Worker wiring lands). Tags come from the look's fx_tag.
    tag = LOOKS[look].get("fx_tag", "calm")
    tl_used = set()
    p["transitions"] = [TL.pick_transition(tags={tag}, used=tl_used,
                        seed=p["seed"] + j, recent_families=recent_families)["name"]
                        for j in range(max(0, len(sc) - 1))]
    p["transition_families"] = [TL.family(n) for n in p["transitions"]]
    p["fx_used"] = used
    return p


# ---------------- voice ----------------
async def tts(text, voice, mood, out):
    import edge_tts
    rate, pitch = MOODS[mood][3]
    last = None
    for attempt in range(4):
        try:
            words, buf = [], bytearray()
            async for ch in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary").stream():
                if ch["type"] == "audio": buf += ch["data"]
                elif ch["type"] == "WordBoundary": words.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
            if not buf: raise RuntimeError("no audio")
            open(out, "wb").write(bytes(buf)); return words
        except Exception as e:
            last = e; await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"TTS failed: {last}")


def dur(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(o.stdout.strip() or 0)


# ---------------- drawing ----------------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def eio(x): x = clamp(x); return x * x * (3 - 2 * x)
_fc = {}
def anton(s):
    s = max(8, int(s))
    if s not in _fc: _fc[s] = ImageFont.truetype(os.path.join(FONTS, "Anton-Regular.ttf"), s)
    return _fc[s]

_ser = {}
def serif(s):
    # v25: look C (story/cinema) uses a serif/elegant face. System DejaVu Serif
    # on the runner; falls back to Anton when it is missing.
    s = max(8, int(s))
    if s not in _ser:
        for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
                  "/usr/share/fonts/dejavu/DejaVuSerif-Bold.ttf"]:
            if os.path.exists(p):
                _ser[s] = ImageFont.truetype(p, s); break
        else:
            _ser[s] = anton(s)
    return _ser[s]


def look_font(look, s):
    return serif(s) if LOOKS.get(look, {}).get("font") == "serif" else anton(s)


def ease_look(look, x):
    # v25: animate text in with a different easing per look.
    k = LOOKS.get(look, {}).get("ease", "smooth")
    if k == "hard": return clamp(x * 1.5)
    if k == "slow": return eio(clamp(x * 0.8))
    if k == "snappy": return C.pop(x)
    return eio(x)


_bg = {}
def background(mood, look=None):
    # v25: the LOOK sets the base gradient (the mood still tints the glow +
    # drives the voice). B = flat near-black; C = warm grade + grain; D = grid.
    key = (mood, look)
    if key not in _bg:
        top, bot, acc, _ = MOODS[mood]
        if look and look in LOOKS:
            top, bot = LOOKS[look]["top"], LOOKS[look]["bot"]
            acc = LOOKS[look]["accents"][0]
        a = np.linspace(0, 1, H)[:, None, None]
        g = (np.array(top)[None, None] * (1 - a) + np.array(bot)[None, None] * a) * np.ones((1, W, 1))
        yy, xx = np.mgrid[0:H, 0:W]
        glow = np.exp(-(((xx - W / 2) / 520) ** 2 + ((yy - 860) / 620) ** 2))[..., None]
        g = g + glow * np.array(acc)[None, None] * 0.22
        im = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im)
        if look == "D":  # glassy grid
            for x in range(0, W, 90): d.line([(x, 0), (x, H)], fill=(22, 26, 44))
            for y in range(0, H, 90): d.line([(0, y), (W, y)], fill=(22, 26, 44))
        elif look == "C":  # warm film grain (subtle, not noisy)
            rng = np.random.RandomState(11)
            noise = rng.randint(-6, 7, size=(H // 6, W // 6, 1)).repeat(6, 0).repeat(6, 1)[:H, :W]
            g2 = np.clip(np.asarray(im).astype(int) + noise, 0, 255).astype(np.uint8)
            im = Image.fromarray(g2); d = ImageDraw.Draw(im)
            # soft vignette: darken the corners
            vig = np.zeros((H, W, 1))
            yy2, xx2 = np.mgrid[0:H, 0:W]
            r2 = ((xx2 - W / 2) / (W / 2)) ** 2 + ((yy2 - H / 2) / (H / 2)) ** 2
            vig = np.clip(1 - 0.28 * np.clip(r2 - 0.55, 0, 1), 0, 1)[..., None]
            im = Image.fromarray(np.clip(np.asarray(im).astype(float) * vig, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im)
        else:
            for y in range(0, H, 6): d.line([(0, y), (W, y)], fill=tuple(int(c * 0.93) for c in im.getpixel((5, y))))  # scanlines
        _bg[key] = im
    return _bg[key].copy()

_bok = {}
def bokeh(col, r):
    k = (col, r)
    if k not in _bok:
        s = Image.new("RGBA", (r * 4, r * 4), (0, 0, 0, 0)); m = Image.new("L", s.size, 0)
        ImageDraw.Draw(m).ellipse([r, r, r * 3, r * 3], fill=70); m = m.filter(ImageFilter.GaussianBlur(r * 0.45))
        s.paste(col + (255,), (0, 0), m); _bok[k] = s
    return _bok[k]

PART = [(random.Random(i).uniform(0, W), random.Random(i + 99).uniform(0, H), random.Random(i + 7).randint(10, 34),
         random.Random(i + 3).uniform(15, 55)) for i in range(16)]

# fake-3D shaded pawn character (single bean silhouette, no face) - user's chosen style
LV = np.array([-0.55, -0.7, 0.62]); LV /= np.linalg.norm(LV); HV = LV + np.array([0, 0, 1.0]); HV /= np.linalg.norm(HV)
def shade(mask, color, blur=18, spec=0.45, amb=0.42):
    m = np.asarray(mask).astype(np.float32) / 255; b = np.asarray(mask.filter(ImageFilter.GaussianBlur(blur))).astype(np.float32) / 255
    gy, gx = np.gradient(b); k = blur * 2.2
    n = np.stack([-gx * k, -gy * k, np.ones_like(b)], -1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    lum = amb + 0.75 * np.clip(n @ LV, 0, 1); sp = np.clip(n @ HV, 0, 1) ** 28
    rgb = np.array(color, np.float32)[None, None] * lum[..., None] + 255 * spec * sp[..., None]
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), (m * 255).astype(np.uint8)]), "RGBA")

_pawn = {}
def pawn(color):
    if color not in _pawn:
        m = Image.new("L", (240, 420), 0); d = ImageDraw.Draw(m)
        d.ellipse([60, 10, 180, 130], fill=255); d.polygon([(95, 120), (145, 120), (195, 360), (45, 360)], fill=255)
        d.ellipse([40, 300, 200, 410], fill=255); d.ellipse([85, 105, 155, 160], fill=255)
        m = m.filter(ImageFilter.GaussianBlur(2)).point(lambda v: 255 if v > 127 else 0)
        _pawn[color] = shade(m, color)
    return _pawn[color]

def put(im, spr, cx, by, s=1.0, rot=0, sx=1.0, sy=1.0):
    w, h = int(spr.width * s * sx), int(spr.height * s * sy)
    sp = spr.resize((w, h), Image.BILINEAR)
    if rot: sp = sp.rotate(rot, expand=True, resample=Image.BICUBIC)
    sh = Image.new("L", (int(w * 1.4), 50), 0); ImageDraw.Draw(sh).ellipse([0, 10, sh.width, 40], fill=110)
    sh = sh.filter(ImageFilter.GaussianBlur(9)); im.paste((0, 0, 0), (int(cx - sh.width / 2), int(by - 25)), sh)
    im.paste(sp, (int(cx - sp.width / 2), int(by - sp.height)), sp)

def character(im, mood, t, acc):
    x, by, rot, sx, sy = 175, 1530, 0, 1.0, 1.0
    if mood == "excited": by -= abs(math.sin(t * 7)) * 70; sy = 1 + 0.06 * math.sin(t * 14)
    elif mood == "sad": sy, rot, by = 0.9, 6, by + 10
    elif mood == "tense": x += 7 * math.sin(t * 55) * (t < 1.2); sx = 0.96
    elif mood == "hopeful": rot = -8 + 3 * math.sin(t * 2); by -= 12 * abs(math.sin(t * 3))
    elif mood == "mystery": rot = 4 * math.sin(t * 1.5)
    else: sy = 1 + 0.025 * math.sin(t * 3)
    put(im, pawn(tuple(int(c * 0.9 + 25) for c in acc)), x, by, 0.55, rot, sx, sy)

def label(d, text, t, acc, idx, look=None):
    # v27 (Hark kit headline()): word-by-word ease-out-back pops, 0.09s stagger.
    # Each word pops in like the kit's headline; the underline grows after.
    words = text.split()
    size = 104 if look == "C" else 132
    f = look_font(look, size)
    widths = [d.textlength(w + " ", font=f) for w in words]
    total = sum(widths) - d.textlength(" ", font=f)
    x = (W - total) / 2
    for k, w in enumerate(words):
        p = C.pop((t - 0.05 - k * 0.09) / 0.3)
        a = int(255 * clamp((t - 0.05 - k * 0.09) / 0.12))
        if a > 0:
            fs = look_font(look, int(size * (0.6 + 0.4 * p)))
            cxw = x + d.textlength(w, font=f) / 2
            d.text((cxw + 6, 1196), w, font=fs, fill=(0, 0, 0, int(a * 0.7)), anchor="mm")
            d.text((cxw, 1190), w, font=fs, fill=(acc if idx % 2 == 0 else (250, 245, 235)) + (a,), anchor="mm")
        x += widths[k]
    ul = ease((t - 0.35) / 0.4) * total
    if ul > 0:
        d.rectangle([(W - total) / 2, 1350, (W - total) / 2 + ul, 1360], fill=acc)


def header(d, p, idx, n, t, sc_d, acc, look=None):
    # v25: chapter cards vary by look — A "FIG 01" diagram label, B rotated STAMP,
    # C drops the chapter labels entirely (minimal), D a big NUMBER counter.
    # v27 (Hark kit safe box): content inside 8% left/right — x starts at 120
    # (11%) so it stays inside 8% even after the max 1.035 content-layer zoom.
    ch = LOOKS.get(look, {}).get("chapter", "fig")
    seg = (W - 240) / n
    def progress():
        for i in range(n):
            x0 = 120 + i * seg; fill = 1 if i < idx else (clamp(t / max(sc_d, 0.1)) if i == idx else 0)
            d.rectangle([x0, 150, x0 + seg - 8, 156], fill=(60, 60, 70))
            if fill: d.rectangle([x0, 150, x0 + (seg - 8) * fill, 156], fill=acc)
    if ch == "none":
        f = C.font(30)
        d.text((120, 92), p["title"][:26], font=f, fill=(225, 225, 230))
        return
    if ch == "stamp":
        f = C.font(34)
        box = (120, 84, 240, 132)
        d.rectangle(box, outline=acc, width=5)
        d.text((138, 92), f"{idx + 1:02d}", font=f, fill=acc)
        d.text((270, 92), p["title"][:26], font=f, fill=(225, 225, 230))
        progress()
        return
    if ch == "counter":
        f = anton(64)
        d.text((120, 74), f"{idx + 1:02d}", font=f, fill=acc)
        d.text((220, 92), p["title"][:26], font=C.font(34), fill=(225, 225, 230))
        progress()
        return
    # fig (A, default): "FIG 01" + a thin diagram tick
    f = C.font(34)
    d.text((120, 92), f"FIG {idx + 1:02d}", font=f, fill=acc)
    d.line([(250, 108), (290, 108)], fill=acc, width=4); d.ellipse([286, 104, 294, 112], fill=acc)
    d.text((310, 92), p["title"][:26], font=f, fill=(225, 225, 230))
    progress()

def scene_frame(p, idx, t):
    sc = p["scenes"][idx]; n = len(p["scenes"]); mood = sc["mood"]
    # v25: the look + title seed drive the palette, chapter card, layout and move.
    look = p.get("look", "A"); seed = p.get("seed", 0)
    acc = tuple(p.get("accent") or LOOKS[look]["accents"][0])
    # v27 (Hark kit): LAYER SPLIT — the background is FIXED and never scales/zooms.
    # Content (bokeh, header, visual, label, cold-open title) is drawn on a
    # transparent layer; the camera push-in applies ONLY to that layer, then the
    # layer is composited onto the background. This is the fix for Ajju's
    # "background colour zooms" complaint — Divya's old camera cropped the WHOLE
    # frame (bg + content), so the bg zoomed and content went outside the screen.
    bg = background(mood, look).convert("RGBA")
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for (x, y, r, sp) in PART:
        yy = (y - t * sp - idx * 140) % (H + 200) - 100
        b = bokeh(acc, r); lay.paste(b, (int(x + 20 * math.sin(t + r)), int(yy)), b)
    d = ImageDraw.Draw(lay, "RGBA")
    header(d, p, idx, n, t, sc["d"], acc, look)
    # v29 (Hark's effects.py): the visual and the label are drawn on SEPARATE
    # layers, each given its own ENTER effect (chosen in plan() from the hit
    # word's meaning) + an EMPHASIS on the hit word, then composited onto the
    # content layer. This is the fix for "the same old effect on every scene":
    # the motion now comes from Hark's library, picked by meaning, max 2x/video.
    pt = max(0.0, t - float(sc.get("pop_t", 0.0) or 0.0))
    layout = (idx + seed) % 4
    vlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vlay, "RGBA")
    llay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(llay, "RGBA")
    if layout == 1:  # full-bleed
        C.draw_visual(vd, vlay, sc["visual"], sc.get("value", ""), pt, cy=900, acc=acc)
        label(ld, sc["label"], pt, acc, idx, look)
    elif layout == 2:  # centered big word, visual small below
        label(ld, sc["label"], pt, acc, idx, look)
        C.draw_visual(vd, vlay, sc["visual"], sc.get("value", ""), pt, cy=1500, acc=acc)
    elif layout == 3:  # split
        C.draw_visual(vd, vlay, sc["visual"], sc.get("value", ""), pt, cy=650, acc=acc)
        d.rectangle([(120, 1080), (W - 120, 1088)], fill=acc)
        label(ld, sc["label"], pt, acc, idx, look)
    else:  # standard
        C.draw_visual(vd, vlay, sc["visual"], sc.get("value", ""), pt, cy=800, acc=acc)
        label(ld, sc["label"], pt, acc, idx, look)
    enter = sc.get("enter") or "pop_in"
    emph = sc.get("emphasis") or "punch"
    label_enter = sc.get("label_enter") or "pop_in"
    if enter in FX_LAYER_ENTER:
        vlay = getattr(FX, enter)(vlay, pt, 0)
    if emph in FX_LAYER_EMPHASIS:
        # pulse is continuous (its 3rd arg is period, not the hit time) — the
        # other emphasis effects take (L, t, at) with at = the hit word time.
        if emph == "pulse":
            vlay = FX.pulse(vlay, pt)
        else:
            vlay = getattr(FX, emph)(vlay, pt, 0)
    elif emph and emph.startswith("fx_") and VIDEO_FX is not None:
        # v29b: a custom per-video emphasis from video_fx.py — (layer, t, start, dur).
        fn = getattr(VIDEO_FX, emph, None)
        if callable(fn):
            vlay = fn(vlay, pt, 0, sc["d"])
    if label_enter in FX_LAYER_ENTER:
        llay = getattr(FX, label_enter)(llay, pt, 0)
    lay.alpha_composite(vlay)
    lay.alpha_composite(llay)
    # v26: the pawn character is REMOVED — Ajju calls it 'ah chess board shipai';
    # a fixed mascot in every scene of every video is not an edit, and it has
    # nothing to do with the topic. Scenes now carry only the topic's own visuals.
    if idx == 0 and t < 2.4:  # cold-open title
        k = ease(t / 0.5) * (1 - ease((t - 1.9) / 0.5))
        d.rectangle([0, 0, W, H], fill=(0, 0, 0, int(150 * k)))
        txt = p["title"]; words = txt.split(); lines = [" ".join(words[:max(1, len(words) // 2)]), " ".join(words[max(1, len(words) // 2):])]
        lines = [l for l in lines if l]
        fs = 150
        while fs > 60 and max(d.textlength(l, font=look_font(look, fs)) for l in lines) > W - 120: fs -= 8
        f = look_font(look, fs)
        for li, ln in enumerate(lines):
            w = d.textlength(ln, font=f); d.text(((W - w) / 2, 700 + li * 190 + 40 * (1 - k)), ln, font=f, fill=acc if li else (255, 255, 255))
    # v29: the camera move VARIES per scene — but only for NARROW, centered
    # visuals. Wide visuals (VS cards, bars, graphs) extend to the frame edges,
    # so a pan/whip would push them off-screen (Ajju's complaint); they get a
    # centered push-in only. No move on scenes under 1.5s.
    if sc["d"] >= 1.5:
        if sc.get("visual") in WIDE_VISUALS:
            move = "push"
        else:
            moves = LOOKS[look].get("moves", ["push"])
            move = moves[(idx + seed) % len(moves)]
        lay = camera(lay, idx, t, sc["d"], mood, move)
    return Image.alpha_composite(bg, lay).convert("RGB")

def camera(im, idx, t, d, mood, move="push"):
    # v29: the camera move VARIES per scene (push / pan / whip / drift / parallax),
    # chosen by the look + scene seed. v27 cut it to push-in only because pan/whip
    # pushed WIDE visuals off-screen — the fix is in scene_frame, which only
    # allows a move for NARROW, centered visuals (WIDE_VISUALS get push-in only).
    # The background is a separate fixed image and never scales/zooms.
    # Works on RGB or RGBA.
    z, dx, dy = 1.0, 0.0, 0.0
    q = eio(t / max(d, 0.1))
    if move == "push":  # slow 3.5% push-in (kit render.py: z = 1 + 0.035 * lt / D)
        z = 1.0 + 0.035 * q
    elif move == "pan":  # gentle horizontal pan
        z = 1.015; dx = -16 + 32 * q
    elif move == "whip":  # quick pan, still inside the frame
        z = 1.02; dx = -28 + 56 * clamp(t / max(d, 0.1) * 1.6)
    elif move == "drift":  # slow diagonal
        z = 1.01 + 0.015 * q; dx = 10 * q; dy = 8 * q
    elif move == "parallax":  # zoom + opposite horizontal shift (reads as depth vs the fixed bg)
        z = 1.0 + 0.02 * q; dx = 18 - 36 * q
    sx = sy = 0
    if mood in ("tense", "excited") and t < 0.45: sx, sy = random.uniform(-14, 14), random.uniform(-14, 14)
    cw, ch = W / z, H / z; x0 = (W - cw) / 2 + dx + sx; y0 = (H - ch) / 2 + dy + sy
    return im.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.BILINEAR)

def outro(p, t):
    # v25: outro uses the video's look accent, not the last scene's mood accent.
    # v26: no pawn here either (see scene_frame).
    acc = tuple(p.get("accent") or MOODS[p["scenes"][-1]["mood"]][2])
    im = background(p["scenes"][-1]["mood"], p.get("look"))
    d = ImageDraw.Draw(im)
    k = C.pop(t / 0.5); f = anton(int(140 * max(k, 0.2)))
    for li, (ln, col) in enumerate([("FOLLOW", (255, 255, 255)), ("FOR MORE", acc)]):
        w = d.textlength(ln, font=f); d.text(((W - w) / 2, 640 + li * 180), ln, font=f, fill=col)
    return im

def transition(a, b, p, name, acc):
    # v29b: Hark's 379-transition library (transitions_lib.py) replaces the
    # 12-transition effects.py set. The NAME is chosen in plan() via
    # TL.pick_transition (tags from the look, never reused in a video, families
    # from the last 5 videos skipped). A name starting with "tr_" is a custom
    # per-video function from video_fx.py (VIDEO_FX); anything else falls back
    # to the old FX library. All take (A, B, p) and return an RGB frame.
    p = clamp(p)
    if name and name.startswith("tr_") and VIDEO_FX is not None:
        fn = getattr(VIDEO_FX, name, None)
        if callable(fn):
            return fn(a, b, p)
    fn = TL_BY_NAME.get(name)
    if fn is not None:
        return fn(a, b, p)
    fn = FX.TRANSITIONS.get(name, (FX.tr_crossfade, []))[0]
    return fn(a, b, p)

def frame_at(p, T):
    st = p["starts"]; n = len(st); end = p["voice_end"]
    if T >= end: return outro(p, T - end)
    i = max([k for k in range(n) if st[k] <= T] or [0]); loc = max(0.0, T - st[i])
    nxt = st[i + 1] if i + 1 < n else end
    # v29: the transition NAME comes from p["transitions"] (chosen in plan()
    # from the look's topic tag); the outro uses a crossfade.
    trs = p.get("transitions") or []
    def tname(j):
        return trs[j] if 0 <= j < len(trs) else "crossfade"
    if i + 1 < n and nxt - T < TR / 2:
        return transition(scene_frame(p, i, loc), scene_frame(p, i + 1, 0), (T - (nxt - TR / 2)) / TR, tname(i), MOODS[p["scenes"][i + 1]["mood"]][2])
    if i > 0 and loc < TR / 2:
        return transition(scene_frame(p, i - 1, T - st[i - 1]), scene_frame(p, i, loc), (loc + TR / 2) / TR, tname(i - 1), MOODS[p["scenes"][i]["mood"]][2])
    if i + 1 >= n and end - T < TR / 2:
        return transition(scene_frame(p, i, loc), outro(p, 0), (T - (end - TR / 2)) / TR, "crossfade", (255, 255, 255))
    return scene_frame(p, i, loc)

_P = None
def _render_chunk(args):
    f0, f1, out = args
    random.seed(f0)
    pr = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        pr.stdin.write(frame_at(_P, fi / FPS).tobytes())
    pr.stdin.close(); pr.wait(); return out


# ---------------- audio ----------------
SR = 44100
def note(m): return 440 * 2 ** ((m - 69) / 12)

def music(total, starts, moods, path):
    n = int(SR * total); out = np.zeros(n); rng = np.random.RandomState(7)
    dark = sum(m in ("tense", "sad", "mystery") for m in moods) >= len(moods) / 2
    prog = [[50, 57, 62, 65], [46, 53, 58, 62], [48, 55, 60, 64], [45, 52, 57, 61]] if dark else \
           [[48, 55, 60, 64], [45, 52, 57, 60], [41, 48, 53, 57], [43, 50, 55, 59]]
    seg = 4 * 60 / 84 * 2  # 2 bars at 84 bpm
    for k in range(int(total / seg) + 1):
        a = int(k * seg * SR); b = min(n, int((k + 1) * seg * SR + SR * 0.8))
        if a >= n: break
        tt = np.arange(b - a) / SR; env = np.minimum(1, tt / 1.0) * np.minimum(1, ((b - a) / SR - tt) / 0.8)
        for m in prog[k % 4]:
            f = note(m); out[a:b] += 0.045 * env * (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * f * 2.003 * tt) + 0.2 * np.sin(2 * np.pi * f * 0.5 * tt))
    beat = 60 / 84
    arp = [0, 7, 12, 7, 3 if dark else 4, 7, 12, 15 if dark else 16]
    for k in range(int(total / (beat / 2))):
        st = k * beat / 2; ch = prog[int(st / seg) % 4]; m = ch[0] + 12 + arp[k % 8]
        L = int(0.5 * SR); a = int(st * SR); tt = np.arange(L) / SR; g = 0.022 + 0.02 * min(1, st / (total * 0.6))
        s = np.sin(2 * np.pi * note(m) * tt) * np.exp(-tt * 8) * g; e = min(n, a + L); out[a:e] += s[:e - a]
        if k % 2 == 0 and st > 2.5:  # soft pulse kick
            L2 = int(0.3 * SR); tt2 = np.arange(L2) / SR; kk = np.sin(2 * np.pi * np.cumsum(45 + 70 * np.exp(-tt2 * 30)) / SR) * np.exp(-tt2 * 10) * 0.14
            e = min(n, a + L2); out[a:e] += kk[:e - a]
    sfx = np.zeros(n)
    def add(sig, t0):
        a = int(t0 * SR); e = min(n, a + len(sig))
        if 0 <= a < n: sfx[a:e] += sig[:e - a]
    L = int(0.55 * SR); tt = np.arange(L) / SR; nz = rng.randn(L)
    whoosh = np.convolve(nz, np.ones(18) / 18, "same") * np.sin(np.pi * tt / tt[-1]) ** 2 * 0.22
    Lb = int(1.4 * SR); tb = np.arange(Lb) / SR
    boom = (np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-tb * 6)) / SR) * np.exp(-tb * 3.5) + 0.3 * rng.randn(Lb) * np.exp(-tb * 25)) * 0.5
    add(boom, 0.02)
    for i, s in enumerate(starts[1:], 1):
        add(whoosh, s - 0.3)
        if moods[i] in ("tense", "excited", "mystery"): add(boom * 0.6, s)
    fade = np.minimum(1, (total - np.arange(n) / SR) / 2.0); out = out / (np.abs(out).max() + 1e-6) * 0.6 * fade
    for arr, pth in ((out, path), (sfx / (np.abs(sfx).max() + 1e-6) * 0.7, path.replace(".wav", "_sfx.wav"))):
        w = wave.open(pth, "w"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(arr, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()


# ---------------- captions ----------------
def ass_t(s):
    s = max(0, s); return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"

def write_ass(p, path):
    fn = "Noto Sans Telugu" if p["lang"] == "te" else "Anton"
    size = 70 if p["lang"] == "te" else 96
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: K,{fn},{size},&H0040D8FF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,1,0,1,6,3,2,80,80,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for s, st in zip(p["scenes"], p["starts"]):
        ws = s["words"]
        if not ws:  # proportional fallback
            toks = s["vo"].split(); tot = sum(len(x) for x in toks) or 1; acc = 0.0; ws = []
            for x in toks:
                d = (s["adur"]) * len(x) / tot; ws.append((acc, d, x)); acc += d
        chunk = 3 if p["lang"] != "te" else 2
        groups = [ws[i:i + chunk] for i in range(0, len(ws), chunk)]
        for gi, g in enumerate(groups):
            a = st + g[0][0]; b = st + (groups[gi + 1][0][0] if gi + 1 < len(groups) else g[-1][0] + g[-1][1] + 0.25)
            parts = []
            for wi, (o, d, txt) in enumerate(g):
                nxt = g[wi + 1][0] if wi + 1 < len(g) else o + d
                parts.append("{\\k%d}%s" % (max(1, int((nxt - o) * 100)), txt.upper() if p["lang"] == "en" else txt))
            ev.append(f"Dialogue: 0,{ass_t(a)},{ass_t(b)},K,,0,0,0,,{{\\fad(40,0)\\fscx80\\fscy80\\t(0,110,\\fscx106\\fscy106)\\t(110,200,\\fscx100\\fscy100)}}" + " ".join(parts))
    open(path, "w", encoding="utf-8").write(head + "\n".join(ev) + "\n")


# ---------------- main ----------------
# ---------------- per-video custom effects (v29b) ----------------
# DIVYA_NEW_CODE_EVERY_VIDEO.md (Blind): the library is only the toolbox — for
# EACH video the LLM writes a NEW video_fx.py (3-6 functions) shaped like the
# topic's own objects, sandbox-tested, max 2 retries, else library fallback.
# Custom tr_ functions replace the first scene boundaries; custom fx_ functions
# replace the library emphasis on the first scenes. VIDEO_FX is the loaded
# module (None = library only).
import importlib.util
import subprocess as _sp

VIDEO_FX_PROMPT = (
    "You are writing NEW motion code for this one video. Topic: {topic}. "
    "Mood: {mood}. Topic objects: {objects}. Scenes with hit words: {scenes}. "
    "Families used in the last 5 videos (do not use): {recent_families}.\n\n"
    "Write video_fx.py with 3 to 6 functions:\n"
    "- tr_*(A, B, p) for scene changes, each shaped like a topic object "
    "(rings from a phone, a page from a book, a coin flip for money, a heartbeat line for health).\n"
    "- fx_*(layer, t, start, dur) for the hit word of a scene.\n"
    "Use only math, random, numpy, PIL, effects, transitions_lib. Build from their primitives.\n"
    "p=0 must return A, p=1 must return B. Keep content inside the safe box. Under 200 ms per frame.\n"
    "Above each function write one comment: which sentence it serves and why it fits.\n"
    "Return only the Python file."
)

def _sandbox_ok(path):
    # Run the adapted fx_sandbox.py (1080x1920, 200 ms/frame) on the file.
    # Returns (ok, detail) — detail is the sandbox JSON or the raw error.
    sb = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fx_sandbox.py")
    try:
        r = _sp.run([sys.executable, sb, path], capture_output=True, text=True, timeout=180)
        out = (r.stdout or "").strip()
        dd = json.loads(out[out.index("{"):])
        return bool(dd.get("ok")), dd
    except Exception as e:
        return False, str(e)

def gen_video_fx(p, chat, wd, recent_families=()):
    # Build the prompt from the plan, ask the LLM for video_fx.py, sandbox-test
    # it (max 2 retries with the error fed back), load it into VIDEO_FX.
    # Returns the number of custom functions loaded (0 = library fallback).
    global VIDEO_FX
    VIDEO_FX = None
    topic = p.get("title", "WATCH THIS")
    mood = LOOKS.get(p.get("look"), {}).get("name", p.get("look", ""))
    words = [w for w in re.split(r"[^A-Z0-9]+", topic.upper()) if len(w) > 3]
    objs = sorted(set(words + [s.get("visual", "") for s in p["scenes"]]))[:8]
    scenes = "; ".join(
        f"{s.get('label', '')}: {s.get('vo', '')[:60]} (hit: {s.get('hit_type', '')})"
        for s in p["scenes"])
    prompt = VIDEO_FX_PROMPT.format(
        topic=topic, mood=mood, objects=", ".join(objs) or "none",
        scenes=scenes, recent_families=", ".join(recent_families) or "none")
    code = None
    err = None
    for attempt in range(3):  # 1 try + 2 retries
        try:
            raw = chat([{"role": "system", "content": "You output Python code only, no markdown fences."},
                        {"role": "user", "content": prompt if attempt == 0 else
                         f"The sandbox rejected your code: {err}. Fix it and return the full corrected video_fx.py."}])
        except Exception as e:
            err = str(e)
            continue
        m = re.search(r"```(?:python)?\s*([\s\S]*?)```", raw)
        code = (m.group(1) if m else raw).strip()
        if not code.startswith(("import ", "from ", "#", "def ")):
            err = "no Python code returned"
            continue
        path = os.path.join(wd, "video_fx.py")
        with open(path, "w") as f:
            f.write(code)
        ok, detail = _sandbox_ok(path)
        if ok:
            spec = importlib.util.spec_from_file_location("video_fx", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            VIDEO_FX = mod
            tr_names = [n for n in dir(mod) if n.startswith("tr_") and callable(getattr(mod, n))]
            fx_names = [n for n in dir(mod) if n.startswith("fx_") and callable(getattr(mod, n))]
            # custom transitions replace the first boundaries; custom fx_
            # replace the library emphasis on the first scenes.
            for i, name in enumerate(tr_names):
                if i < len(p.get("transitions", [])):
                    p["transitions"][i] = name
            for i, name in enumerate(fx_names):
                if i < len(p["scenes"]):
                    p["scenes"][i]["emphasis"] = name
            p["video_fx"] = {"tr": tr_names, "fx": fx_names}
            return len(tr_names) + len(fx_names)
        err = str(detail)
    return 0

async def make_video(brief, chat, notify=None, workdir=None, recent="", workers=None, recent_styles=None):
    global _P
    wd = workdir or tempfile.mkdtemp(prefix="doc_")
    p = plan(brief, chat, recent, recent_styles)
    # v29b: per-video custom effects — the LLM writes a NEW video_fx.py for
    # this topic, sandbox-tested, max 2 retries; 0 = library fallback.
    n_fx = gen_video_fx(p, chat, wd)
    if notify and n_fx:
        await notify(f"Custom effects: {n_fx} new functions for this video "
                     f"({', '.join(p.get('video_fx', {}).get('tr', []) + p.get('video_fx', {}).get('fx', []))}).")
    voice = VOICES.get((p["lang"], p.get("voice", "male")), VOICES[(p["lang"], "male")])
    if notify: await notify(f"Script ready: {p['title']} ({len(p['scenes'])} scenes, {p['lang']}). Voice, animation, music chestunna.")
    gap = 0.32
    for i, s in enumerate(p["scenes"]):
        a = f"{wd}/vo{i}.mp3"; s["words"] = await tts(s["vo"], voice, s["mood"], a)
        s["audio"] = a; s["adur"] = dur(a); s["d"] = s["adur"] + gap
    # v27 (Hark kit): hit-word timing — ONE hit word per sentence, priority =
    # number > topic noun > contrast/shock word. The visual lands 80 ms BEFORE
    # the word starts (ears lag eyes); the SFX pop lands exactly on the word.
    # pop_t = word.start - 0.08 (clamped >= 0).
    _STOP = {"a", "an", "the", "is", "are", "was", "were", "it", "its", "this", "that",
             "and", "or", "but", "so", "to", "of", "in", "on", "for", "with", "you", "your",
             "we", "our", "i", "me", "my", "he", "she", "they", "do", "does", "did", "can",
             "will", "would", "not", "no", "yes", "if", "when", "why", "how", "what"}
    _SHOCK = {"but", "never", "only", "not", "no", "stop", "secret", "shocking", "surprise",
              "hidden", "truth", "lie", "fake", "real", "actually", "exactly", "nobody", "everyone"}
    _NUMWORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                 "eleven", "twelve", "twenty", "thirty", "fifty", "hundred", "thousand", "million",
                 "billion", "percent", "half", "double", "triple", "zero"}
    _TOPIC = {w.strip().lower().strip(".,!?\"'") for w in str(p.get("title", "")).split()
              if len(w.strip().strip(".,!?\"'")) > 3}
    for s in p["scenes"]:
        words = [(float(o), str(w).strip().lower().strip(".,!?\"'")) for (o, _d, w) in (s.get("words") or [])]
        # the scene's label is the punch keyword the LLM chose for this scene —
        # the hit word should match it (e.g. label "MYTH 1" -> vo word "myth").
        _LABEL = {w.strip().lower() for w in str(s.get("label", "")).split() if len(w.strip()) > 1}
        # v28: search only the FIRST 60% of the words — a hit word at the end of
        # the sentence (e.g. "repeat" as the last word) would hide the visual and
        # the label for most of the scene. An early hit word keeps the scene alive.
        early = words[:max(1, int(len(words) * 0.6) + 1)]
        hit = None
        for (o, ww) in early:  # 1. a number (digit, or a spelled-out number word)
            if any(c.isdigit() for c in ww) or ww in _NUMWORDS:
                hit = o; break
        if hit is None:
            for (o, ww) in early:  # 2. a word from the scene's label
                if ww in _LABEL:
                    hit = o; break
        if hit is None:
            for (o, ww) in early:  # 3. a topic noun (a word from the title)
                if ww in _TOPIC and ww not in _STOP:
                    hit = o; break
        if hit is None:
            for (o, ww) in early:  # 4. a contrast/shock word
                if ww in _SHOCK:
                    hit = o; break
        if hit is None:  # fallback: first content word
            for (o, ww) in words:
                if len(ww) > 3 and ww not in _STOP:
                    hit = o; break
        s["pop_t"] = max(0.0, float(hit or 0.0) - 0.08)
    starts, t = [], 0.4  # 0.4 s pre-roll for the boom
    for s in p["scenes"]: starts.append(t); t += s["d"]
    p["starts"] = starts; p["voice_end"] = t; total = t + OUTRO
    # voice track positioned exactly
    ins = sum([["-i", s["audio"]] for s in p["scenes"]], [])
    fc = "".join(f"[{i}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{i}];" for i, st in enumerate(starts))
    fc += "".join(f"[a{i}]" for i in range(len(starts))) + f"amix=inputs={len(starts)}:normalize=0,apad,atrim=0:{total:.2f}[o]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", fc, "-map", "[o]", "-ar", str(SR), "-ac", "1", f"{wd}/voice.wav"], check=True)
    music(total, starts, [s["mood"] for s in p["scenes"]], f"{wd}/music.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{wd}/voice.wav", "-i", f"{wd}/music.wav", "-i", f"{wd}/music_sfx.wav", "-filter_complex",
                    "[0:a]asplit[v1][v2];[1:a]volume=0.55[m];[m][v2]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md];"
                    "[v1]highpass=f=70,acompressor=threshold=0.1:ratio=3,volume=1.5[vv];[2:a]volume=0.55[sx];"
                    "[vv][md][sx]amix=inputs=3:normalize=0,alimiter=limit=0.95[o]", "-map", "[o]", "-ar", str(SR), f"{wd}/mix.wav"], check=True)
    # video, parallel chunks
    _P = p; nf = int(total * FPS); k = workers or max(1, min(4, os.cpu_count() or 1))
    cuts = [nf * i // k for i in range(k + 1)]
    jobs = [(cuts[i], cuts[i + 1], f"{wd}/part{i}.mp4") for i in range(k)]
    with mp.get_context("fork").Pool(k) as pool:
        parts = pool.map(_render_chunk, jobs)
    open(f"{wd}/parts.txt", "w").write("".join(f"file '{x}'\n" for x in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{wd}/parts.txt", "-c", "copy", f"{wd}/raw.mp4"], check=True)
    ass = f"{wd}/subs.ass"; write_ass(p, ass)
    out = f"{wd}/divya_doc.mp4"
    vf = f"vignette=PI/4.5,eq=contrast=1.06:saturation=1.08,noise=alls=7:allf=t,ass={ass}:fontsdir={FONTS}"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{wd}/raw.mp4", "-i", f"{wd}/mix.wav", "-vf", vf, "-c:v", "libx264", "-preset", "medium",
                    "-crf", "23", "-maxrate", "2300k", "-bufsize", "4600k", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out], check=True)
    if os.path.getsize(out) > 15_000_000:  # WhatsApp media limit is 16 MB
        kb = max(600, int(14.2 * 8192 / total) - 140)
        small = f"{wd}/divya_doc_wa.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out, "-c:v", "libx264", "-preset", "medium", "-b:v", f"{kb}k",
                        "-maxrate", f"{int(kb * 1.15)}k", "-bufsize", f"{kb * 2}k", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", small], check=True)
        out = small
    return {"path": out, "topic": p.get("topic", brief), "title": p["title"], "lang": p["lang"],
            "script": "\n".join(s["vo"] for s in p["scenes"]), "caption": p.get("caption", ""), "plan": p, "duration": total}
