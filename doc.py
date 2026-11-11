"""Divya documentary engine v2: topic (or AUTO) -> 45-60 s cinematic 9:16 video. No footage needed.
LLM story plan (hook -> context -> twist -> payoff -> CTA, per-scene mood) -> human-sounding neural voice
(English Andrew/Ava multilingual or Telugu Mohan/Shruti) with per-mood rate/pitch -> animated scenes
(mood palettes, bokeh, 3D-shaded character, animated objects, kinetic labels) -> camera push/pan/shake ->
6 transition kinds -> procedural cinematic music + whoosh/boom SFX, ducked under voice -> word-timed karaoke
captions (libass) -> film grade (vignette + grain). Rendered in parallel processes. Free, CPU only.
v29: Hark's effects.py (Blind) — 14 ENTER, 11 EMPHASIS, 12 TRANSITIONS, picked by the hit word's meaning, max 2x per video."""
import asyncio, inspect, json, math, multiprocessing as mp, os, random, re, subprocess, sys, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import create as C
import effects as FX  # v29: Hark's effects library (Blind, divya-v26-effects.zip) — 14 ENTER, 11 EMPHASIS, 12 TRANSITIONS, 10 easings
import transitions_lib as TL  # v29b: Hark's 379-transition library (Blind, divya-v29-transitions.zip) — 40 families, incl. 3D
import visuals_lib as VL  # v32: Blind's rich-visual library (18 real objects, scene_bg, pick_vis)
import codegen as CG  # v32: Divya's adapter for Blind's divya_codegen.py (per-video tr_/fx_/vis_ code)
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
          "accents": [(60, 200, 230), (255, 180, 60)], "font": "anton", "chapter": "none",
          "ease": "smooth", "motion": "push", "bg": "gradient", "grain": 5,
          "motion_personality": "smooth glides", "transition_family": "zoom through the diagram",
          # v29 (Hark's effects.py): the look's transition TAG picks from FX.TRANSITIONS;
          # the camera moves are for narrow visuals only (WIDE_VISUALS get push-in).
          "fx_tag": "space", "moves": ["push", "pan", "drift"],
          "desc": "deep navy to teal gradient, cyan/amber accent, thin line diagrams, animated plots, clean sans — lightning, physics, how-things-work"},
    "B": {"name": "myth", "top": (10, 10, 10), "bot": (24, 24, 24),
          "accents": [(255, 40, 40), (255, 210, 0)], "font": "bebas", "chapter": "none",
          "ease": "hard", "motion": "cut", "bg": "flat", "grain": 4,
          "motion_personality": "snappy pops", "transition_family": "hard cut + stamp slam",
          "fx_tag": "warning", "moves": ["push", "whip"],
          "desc": "high-contrast black and white, one hot red or yellow accent, huge bold condensed type, hard cuts, stamp/strike-through — myths, warnings, versus"},
    "C": {"name": "story", "top": (40, 30, 20), "bot": (24, 18, 12),
          "accents": [(250, 230, 200), (230, 120, 50), (60, 170, 160)], "font": "serif", "chapter": "none",
          "ease": "slow", "motion": "push", "bg": "warm", "grain": 7,
          "motion_personality": "slow push-ins", "transition_family": "paper tear / fade",
          "fx_tag": "history", "moves": ["push", "drift"],
          "desc": "warm film grain, soft vignette, serif/elegant type, slow push-ins, cream/orange/teal grade, minimal text — movies, history, emotion"},
    "D": {"name": "tech", "top": (12, 14, 28), "bot": (8, 10, 22),
          "accents": [(60, 255, 140), (170, 100, 255)], "font": "anton", "chapter": "none",
          "ease": "snappy", "motion": "whip", "bg": "grid", "grain": 5,
          "motion_personality": "snappy easing", "transition_family": "screen swipe / coin flip",
          "fx_tag": "tech", "moves": ["push", "pan", "whip"],
          "desc": "light or dark glassy UI, neon green/violet accent, big animated numbers, bar/line charts, grid backgrounds, snappy easing — stats, AI, finance"},
}
# v29: visuals that extend to the frame edges — only a centered push-in is safe
# for them (a pan/whip would push them off-screen, Ajju's complaint). Narrow,
# centered visuals can take any camera move.
WIDE_VISUALS = {"versus", "bar", "bar_compare", "graph", "list", "checklist",
                "arrows_steps", "dot_grid", "calendar", "chat", "battery"}
# v34 (Hark blueprint §4, style table per topic family): the TOPIC FAMILY
# picks the design system, so two videos on different topics cannot look the
# same. Health = dark red clinical, science = deep blue diagrams, motivation =
# warm gold film grain, history = sepia + warm grain, money = green/black ledger.
TOPIC_FAMILIES = {
    "health": {"look": "B", "grain": 6, "desc": "dark red clinical — health, body, disease, tobacco, sleep, food"},
    "science": {"look": "A", "grain": 5, "desc": "deep blue diagrams — science, physics, space, how things work"},
    "motivation": {"look": "C", "grain": 7, "desc": "warm gold film grain — motivation, habits, discipline, focus"},
    "history": {"look": "C", "grain": 8, "desc": "sepia + warm grain — history, ancient, legend, culture"},
    "money": {"look": "D", "grain": 4, "desc": "green/black ledger — money, finance, price, salary, business"},
}
_FAMILY_WORDS = {
    "health": ["health", "tobacco", "gutka", "smoking", "sleep", "food", "diet", "disease", "doctor", "body", "heart", "brain", "cancer", "medicine", "drug", "alcohol", "exercise", "weight"],
    "science": ["science", "physics", "lightning", "thunder", "space", "atom", "energy", "earth", "planet", "gravity", "biology", "experiment", "ocean", "volcano", "electric", "sound", "light", "weather"],
    "motivation": ["motivat", "discipline", "habit", "focus", "success", "goal", "mindset", "confidence", "routine", "productiv", "willpower", "consist"],
    "history": ["history", "ancient", "king", "queen", "war", "empire", "legend", "temple", "kingdom", "dynasty", "century", "historic", "civilization", "archaeolog"],
    "money": ["money", "finance", "rupee", "price", "salary", "bank", "invest", "stock", "crypto", "business", "startup", "wealth", "rich", "poor", "budget", "loan", "debt"],
}


def topic_family(brief):
    # v34: the topic family from the brief's keywords (most hits wins). "" = none.
    text = (brief or "").lower()
    best, best_n = "", 0
    for fam, words in _FAMILY_WORDS.items():
        n = sum(1 for w in words if w in text)
        if n > best_n:
            best, best_n = fam, n
    return best


# v32 (M8, Mark's fact-type -> visual table, 1a1c9017ef4ff629 §1): a scene's
# FACT TYPE picks its visual kind FIRST, before the LLM's own pick — so a
# number scene is *guaranteed* a counter, a % scene a donut, a myth scene a
# strike-through. Deterministic, and it makes the plan auditable. Applied in
# plan() (fact_type_of). "place" is left to the codegen (VL india_map), which
# has a real map; the 25-kind library has none.
FACT_VISUALS = {
    "number": "counter", "percent": "donut", "time": "clock", "ban": "stamp",
    "list": "list", "comparison": "versus", "myth": "strike", "quote": "quote_card",
    # v34 (Hark blueprint §3): "1 in N" -> people icons, phone -> type-out card,
    # a rate ("one life every 25 seconds") -> stopwatch. "place" is handled in
    # plan() via lib_visual (india_map / world_dots), because those live in
    # visuals_lib, not in create.VISUALS.
    "one_in_n": "four", "phone": "card", "rate": "watch",
}
# v32 (M9): one SFX per scene, picked from the fact type (surfaced in the
# plan; the audio mix uses the mood-based whoosh/boom as now).
SCENE_SFX = {
    "number": "pop", "percent": "pop", "time": "tick", "ban": "stamp",
    "list": "pop", "comparison": "whoosh", "myth": "glitch", "quote": "type",
    "warning": "boom", "shock": "boom", "growth": "rise", "drop": "fall",
    "money": "coin", "health": "beat", "space": "whoosh", "funny": "boing",
    "calm": "soft",
    # v34 (Hark blueprint §3): SFX for the new fact types.
    "one_in_n": "pop", "phone": "type", "rate": "tick", "place": "whoosh", "stamp": "stamp",
}

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


def fact_type_of(s):
    # v32 (M8): the scene's FACT TYPE (for FACT_VISUALS). Determined from the
    # label + value + voice-over, in the same spirit as hit_type_of but for
    # the visual kind, not the effect.
    # v34 (Hark blueprint §3): one_in_n / phone / rate / place added; the
    # specific types are checked BEFORE the generic number/time ones, so
    # "1 in 4" is people icons, not a counter, and "one life every 25 seconds"
    # is a stopwatch, not a clock.
    txt = (str(s.get("label", "")) + " " + str(s.get("vo", ""))).lower()
    val = str(s.get("value", ""))
    if re.search(r"\b(one|1|two|2|three|3)\s+in\s+(four|4|five|5|six|6|ten|10)\b", txt): return "one_in_n"
    if any(w in txt for w in ("call ", "phone number", "toll free", "helpline", "quitline", "1800", "1-800", "dial ")): return "phone"
    if re.search(r"\bevery\s+\d*\s*(second|seconds|minute|minutes|hour|hours)\b", txt) or "per second" in txt or "per minute" in txt: return "rate"
    if "%" in val or "%" in txt: return "percent"
    if any(c.isdigit() for c in val): return "number"
    if any(w in txt for w in ("ban", "banned", "prohibit", "prohibited", "illegal", "banned")): return "ban"
    if any(w in txt for w in ("india", "country", "state", "city", "world", "delhi", "mumbai", "map", "place", "village", "town", "global")): return "place"
    if any(w in txt for w in ("clock", "time", "year", "years", "day", "days", "hour", "minute", "am", "pm", "ago", "history", "ancient")): return "time"
    if any(w in txt for w in ("first", "second", "third", "three things", "three ways", "steps", "ways")): return "list"
    if any(w in txt for w in (" vs ", "versus", " than ", "better", "worse", "compare", "compared")): return "comparison"
    if any(w in txt for w in ("myth", "lie", "lies", "fake", "wrong", "never", "secret", "myths")): return "myth"
    if any(w in txt for w in ("said", "says", "quote", "law", "rule", "according", "study", "report")): return "quote"
    return ""


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
# v32 (M12, Mark 1a1c1028211d08d1 §3): en-US-ChristopherNeural, rate -8%,
# pitch -4Hz, "calm, deep" — the English male voice for calm/motivational
# topics. make_video() switches to it for calm/majority-calm or
# motivational briefs; tts() applies the -8%/-4Hz override.
VOICES = {("en", "male"): "en-US-AndrewMultilingualNeural", ("en", "female"): "en-US-AvaMultilingualNeural",
          ("en", "male_calm"): "en-US-ChristopherNeural",
          ("te", "male"): "te-IN-MohanNeural", ("te", "female"): "te-IN-ShrutiNeural",
          ("hi", "male"): "hi-IN-MadhurNeural", ("hi", "female"): "hi-IN-SwaraNeural"}

PLAN = """You are a top YouTube documentary-shorts writer and director. Plan ONE faceless 9:16 video from the owner's request.
Return ONLY JSON:
{"topic": "...", "title": "<2-5 word English title, caps>", "lang": "en|te|hi", "voice": "male|female",
 "caption": "<post caption with 3-5 hashtags>",
 "scenes": [{"vo": "...", "label": "<1-3 word ENGLISH punch label, caps>", "mood": "calm|tense|hopeful|sad|excited|mystery",
             "visual": "<one of %s>", "value": "<short number/word for the visual>",
             "source": "<short official source for the fact/number, e.g. WHO 2023, Govt of India 2012, Harvard 2020, or empty>"}]}
DESIGN LOOK (v25, Hark aesthetic variety): {look} — design every scene for this look: palette, background,
visuals and chapter style all follow it. A science: graph/clock/counter/bar visuals, diagram labels.
B myth/safety: warning/versus/check visuals, stamp chapter cards, huge bold labels.
C story/cinema: heart/check visuals, minimal text, NO chapter labels, elegant labels.
D tech/data: counter/bar/graph/list visuals, big number chapter cards, animated numbers.
New visuals (v28, Hark kit): dot_grid/donut for a percentage of people, gauge for a level,
toggle for on/off, phone_buzz for phone notifications, stick_figure for a person/feeling,
quote_card for a quote, arrows_steps for a process, checklist for steps, document for a
report, polaroid for a memory, icon_row for a set of items, bar_compare for two numbers.
New visuals (v34, Hark engine): four for one-in-N people, question for a big question hook,
card for a phone number or helpline, watch for a stopwatch or rate, stamp for a ban or
verdict, stamp_cta for the final call to action.
Language: follow the owner. If they ask for English voice/voice-over -> lang "en" (vo in English). Telugu -> "te" (vo in Telugu script).
Hindi -> "hi". If they say nothing about language, use "te".
Length: honour any duration they ask (e.g. "1 min" = 60 s). Default 50-60 s. English speaks ~2.5 words/s, Telugu ~1.8 words/s:
size the total vo words to the target duration. 9-14 scenes, each vo 6-22 words.
Writing: documentary storytelling that sounds like a real human talking to a friend - contractions, short punchy sentences,
rhetorical questions, a surprising fact or tension in the first line (hook), then context, a twist, the payoff, and a short
call to follow at the end. Use commas, "..." and dashes for natural pauses. No emojis, no hashtags in vo. Vary the mood per scene to
build an emotional arc. When a scene states a fact or a number, put its short official source (WHO, Govt of India, Harvard, RBI, Census)
in the source field; leave it empty when there is no fact. Each visual must literally show the line's idea (battery=energy, chat=messages/people, graph=growth or fall,
clock=time, calendar=days, warning=danger/mistake, check=right way, versus=comparison, counter=a number, list=steps, heart=love/health,
bar=progress, dot_grid/donut=a percentage of people, gauge=a level, toggle=on/off, phone_buzz=phone notifications,
stick_figure=a person/feeling, quote_card=a quote, arrows_steps=a process, checklist=steps, document=a report,
polaroid=a memory, icon_row=a set of items, bar_compare=two numbers compared,
four=one-in-N people, question=a big question, card=a phone number or helpline,
watch=a stopwatch or rate, stamp=a ban or verdict, stamp_cta=the final call to action).
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
    # v34 (Hark blueprint §4): the TOPIC FAMILY picks the design system, so
    # two videos on different topics cannot look the same. The family's look
    # wins unless it was used in the last 5 videos (recent_styles).
    fam = topic_family(brief)
    if fam and TOPIC_FAMILIES[fam]["look"] not in (recent_styles or []):
        look = TOPIC_FAMILIES[fam]["look"]
    look_line = (f"DESIGN LOOK {look} ({LOOKS[look]['name']}): {LOOKS[look]['desc']}. "
                 f"Motion personality: {LOOKS[look]['motion_personality']}. "
                 f"Transition family: {LOOKS[look]['transition_family']}."
                 + (f" Topic family: {fam} ({TOPIC_FAMILIES[fam]['desc']})." if fam else ""))
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
        s["source"] = str(s.get("source", "") or "")[:40]
    p["scenes"] = sc
    p["lang"] = p.get("lang") if p.get("lang") in ("en", "te", "hi") else "te"
    # v32 (Blind): the title is NOT truncated to 26 chars any more — header()
    # wraps it on word boundaries into 2 lines instead (a mid-word cut was a
    # defect Blind flagged: "PHANTOM VIBRAT").
    p["title"] = re.sub(r"[^A-Z0-9 %!?'&-]", "", str(p.get("title", "")).upper()) or "WATCH THIS"
    # v25: the look + a title seed (so no two videos match inside a look).
    # v27: the style plan (motion personality + transition family) rides with it.
    p["look"] = look
    p["family"] = fam
    p["grain"] = TOPIC_FAMILIES[fam]["grain"] if fam else LOOKS[look].get("grain", 5)
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
    # v32 (Blind): the background KIND changes per scene — but ONLY when the
    # mood changes (Hark's per-section bg rule). It rotates through VL's 9
    # kinds, starting from the title seed, so consecutive same-mood scenes
    # keep one bg and a mood change reads as a new section.
    _kinds = list(VL.SCENE_BG)
    _ki = p["seed"] % len(_kinds)
    _prev_mood = None
    for s in sc:
        if s["mood"] != _prev_mood:
            _ki = (_ki + 1) % len(_kinds)
            _prev_mood = s["mood"]
        s["bg_kind"] = _kinds[_ki]
    # v32 (M8): the fact type picks the visual kind FIRST (deterministic).
    for s in sc:
        ft = fact_type_of(s)
        s["fact_type"] = ft
        if ft in FACT_VISUALS:
            s["visual"] = FACT_VISUALS[ft]
    # v34: "place" scenes get the real map from visuals_lib (india_map /
    # world_dots) via lib_visual — the codegen's own choice still overrides
    # this in load_video_fx.
    for s in sc:
        if s.get("fact_type") == "place" and not s.get("lib_visual"):
            _t = (str(s.get("label", "")) + " " + str(s.get("vo", ""))).lower()
            s["lib_visual"] = "india_map" if "india" in _t else "world_dots"
    # v34 (Hark stamp CTA, item 8): the last scene is the call to action — a
    # big word + a rotated stamp + a strikethrough, not a separate outro.
    _last = sc[-1]
    _cta = str(_last.get("label", "")).upper() in ("FOLLOW", "QUIT", "STOP", "TODAY", "SUBSCRIBE") or "follow" in str(_last.get("vo", "")).lower()
    if _cta:
        _last["visual"] = "stamp_cta"
    # v32 (M9): surface the per-cut transition + one SFX per scene in the
    # plan (the codegen's PLAN call already picks per-cut transitions; the
    # transition here is the one that brings the viewer INTO the scene).
    for i, s in enumerate(sc):
        s["transition"] = p["transitions"][i - 1] if 0 < i <= len(p["transitions"]) else ""
        s["sfx"] = SCENE_SFX.get(s.get("fact_type") or s.get("hit_type") or "calm", "pop")
    return p


# ---------------- voice ----------------
async def tts(text, voice, mood, out):
    import edge_tts
    rate, pitch = MOODS[mood][3]
    if voice == "en-US-ChristopherNeural":  # v32 (M12, Mark): calm, deep
        rate, pitch = "-8%", "-4Hz"
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


def word_t(words, idx):
    # v34 (Hark word_t, hark_engine_tobacco.py): the start time (s, scene-local)
    # of word idx in a scene's word list [(start, dur, text), ...]; clamped to
    # the last word. Graphics time their animation to specific words with this.
    if not words: return 0.0
    i = max(0, min(int(idx), len(words) - 1))
    return float(words[i][0])


def word_span(words, i0, i1):
    # v34: (start, end) covering words i0..i1 inclusive — for a count/fill that
    # runs while a phrase is spoken.
    if not words: return (0.0, 0.0)
    i0 = max(0, min(int(i0), len(words) - 1)); i1 = max(i0, min(int(i1), len(words) - 1))
    return (float(words[i0][0]), float(words[i1][0]) + float(words[i1][1]))
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


_mont, _beb = {}, {}
def montserrat(s):
    # v32 (M7, Mark): Montserrat — the BODY font the prompts already promise
    # (runner.py + divya.js). hark-kit/Montserrat.ttf (variable font, loads
    # at its Regular instance); falls back to the repo fonts/ copy, then Anton.
    s = max(8, int(s))
    if s not in _mont:
        for p in [os.path.join(HERE, "hark-kit", "Montserrat.ttf"),
                  os.path.join(FONTS, "Montserrat.ttf")]:
            if os.path.exists(p):
                _f = ImageFont.truetype(p, s)
                try:  # the variable font defaults to Thin — pick SemiBold
                    _f.set_variation_by_name("SemiBold")
                except Exception:
                    pass
                _mont[s] = _f; break
        else:
            _mont[s] = anton(s)
    return _mont[s]


def bebas(s):
    # v32 (M7, Mark): Bebas Neue — the condensed HEADLINE font. Look B
    # ("huge bold condensed type") uses it; the other looks keep Anton.
    s = max(8, int(s))
    if s not in _beb:
        for p in [os.path.join(HERE, "hark-kit", "BebasNeue.ttf"),
                  os.path.join(FONTS, "BebasNeue.ttf")]:
            if os.path.exists(p):
                _beb[s] = ImageFont.truetype(p, s); break
        else:
            _beb[s] = anton(s)
    return _beb[s]


def look_font(look, s):
    _f = LOOKS.get(look, {}).get("font")
    if _f == "serif": return serif(s)
    if _f == "bebas": return bebas(s)
    return anton(s)


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
        elif look == "C":  # warm grade (grain + vignette now apply to ALL looks below)
            pass
        else:
            for y in range(0, H, 6): d.line([(0, y), (W, y)], fill=tuple(int(c * 0.93) for c in im.getpixel((5, y))))  # scanlines
        # v34 (Hark film look, make_bg + GRAIN): a subtle grain + soft vignette
        # on EVERY look, not just C — this is what makes the background feel
        # like film rather than a flat digital slide. Amount is per-look
        # (LOOKS[look]["grain"]); baked into the cached background once.
        _gr = LOOKS.get(look, {}).get("grain", 5) if look else 5
        rng = np.random.RandomState(11)
        noise = rng.randint(-_gr, _gr + 1, size=(H // 6, W // 6, 1)).repeat(6, 0).repeat(6, 1)[:H, :W]
        g2 = np.clip(np.asarray(im).astype(int) + noise, 0, 255).astype(np.uint8)
        im = Image.fromarray(g2); d = ImageDraw.Draw(im)
        _vig = 0.34 if look == "C" else 0.28
        yy2, xx2 = np.mgrid[0:H, 0:W]
        r2 = ((xx2 - W / 2) / (W / 2)) ** 2 + ((yy2 - H / 2) / (H / 2)) ** 2
        vig = np.clip(1 - _vig * np.clip(r2 - 0.55, 0, 1), 0, 1)[..., None]
        im = Image.fromarray(np.clip(np.asarray(im).astype(float) * vig, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im)
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

# v34 (Hark DUST): 70 drifting dust specks, drawn per frame in scene_frame().
# Deterministic (fixed seeds) so the render is reproducible.
_DUST = [(random.Random(i).uniform(0, W), random.Random(i + 500).uniform(0, H),
          random.Random(i + 9).uniform(1, 3), random.Random(i + 31).uniform(8, 28)) for i in range(70)]

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


def wrap_title(title, max_w, d, start=34, min_s=20):
    # v32 (Blind): wrap the title on WORD boundaries into <= 2 lines, shrinking
    # the font 34->20 until it fits. Never cuts a word mid-way — the old
    # title[:26] cut "PHANTOM VIBRATION" to "PHANTOM VIBRAT". Returns
    # (lines, size). If it still does not fit in 2 lines at the smallest size,
    # the extra words are dropped, never cut.
    words = title.split()
    for size in range(start, min_s - 1, -1):
        f = montserrat(size)
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if d.textlength(test, font=f) <= max_w:
                cur = test
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        if len(lines) <= 2:
            return lines, size
    f = montserrat(min_s)
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) <= max_w:
            cur = test
        else:
            if cur: lines.append(cur)
            if len(lines) == 2: break
            cur = w
    if cur and len(lines) < 2: lines.append(cur)
    return lines[:2], min_s


def header(d, p, idx, n, t, sc_d, acc, look=None):
    # v33 (Ajju 2026-11-11): NO chapter labels — "FIG 01 / FIG 02 ani ndhuku
    # chupisthunnav". The header is the title only (wrapped, full width) +
    # the progress bar. The old per-look chapter cards (FIG / stamp / counter)
    # are deleted; look C already had "none" and now every look is the same.
    # v27 (Hark kit safe box): content inside 8% left/right — x starts at 120.
    # v32: the title wraps on word boundaries (wrap_title) instead of the
    # [:26] cut; the progress bar drops to y=162 when the title needs 2 lines.
    seg = (W - 240) / n
    def progress(two=False):
        y = 162 if two else 150
        for i in range(n):
            x0 = 120 + i * seg; fill = 1 if i < idx else (clamp(t / max(sc_d, 0.1)) if i == idx else 0)
            d.rectangle([x0, y, x0 + seg - 8, y + 6], fill=(60, 60, 70))
            if fill: d.rectangle([x0, y, x0 + (seg - 8) * fill, y + 6], fill=acc)
    lines, sz = wrap_title(p["title"], W - 240, d, start=34)
    for k, ln in enumerate(lines):
        d.text((120, 92 + k * 36), ln, font=montserrat(sz), fill=(225, 225, 230))
    progress(len(lines) > 1)

# v32: plan visual kind -> visuals_lib name (used when the plan's kind has a
# richer VL equivalent; the scene's stored lib_visual wins over this map).
_VIS_NAME_MAP = {
    "document": "document", "polaroid": "polaroid", "warning": "warning_sign",
    "bar": "bracket_bars", "bar_compare": "bracket_bars", "versus": "balance_scale",
}
# v32: cached upscaled scene_bg layers, per bg_kind (built once per process).
_SBG = {}


def _fit_above_label(lay):
    # v32 (Blind): fit a 1080x1920 visual layer's CONTENT into the band
    # y 200-1150 (below the header, above the label at y 1190-1360). Scale +
    # shift so the content fits the band and is centred in it; a layer that
    # already fits is returned unchanged. (A document layer went from bbox
    # bottom 1471 to 1150, top 200, in the v32 session test.)
    bb = lay.getbbox()
    if not bb:
        return lay
    top, bot = bb[1], bb[3]
    lo, hi = 200, 1150
    if top >= lo and bot <= hi:
        return lay
    bh = bot - top
    span = hi - lo
    s = min(1.0, span / max(1, bh))
    if s < 1.0:
        nw, nh = int(lay.size[0] * s), int(lay.size[1] * s)
        lay = lay.resize((nw, nh), Image.BICUBIC)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bb = lay.getbbox()
    if not bb:
        return out
    top, bot = bb[1], bb[3]
    bh = bot - top
    dy = lo + (span - bh) // 2 - top
    dx = (W - lay.size[0]) // 2
    out.alpha_composite(lay, (dx, dy))
    return out


def _call_lib_vis(name, t, st, d, acc, words=None):
    # v32: call a visuals_lib VIS function. accent= is passed as a KEYWORD
    # only when the function accepts it (inspect.signature) — the 18
    # functions have VARYING signatures (vis_warning takes no accent).
    # v34: words= is passed the same way, when the function accepts it —
    # word-timed visuals (Hark word_t) animate to specific words.
    fn = VL.VIS[name]
    _sig = inspect.signature(fn).parameters
    kw = {}
    if "accent" in _sig:
        kw["accent"] = acc
    if words is not None and "words" in _sig:
        kw["words"] = words
    return fn(t, st, d, **kw)


def draw_scene_visual(vd, vlay, p, idx, sc, pt, cy, acc):
    # v32 (Blind codegen): the visual chain — 1) a custom per-video vis_
    # from video_fx.py (ideas.json, passed the sandbox), 2) a library visual
    # from visuals_lib (the ideas' "library:<name>", a sandbox fallback, or
    # the plan kind mapped through _VIS_NAME_MAP), 3) the 25-kind library
    # (create.draw_visual). A failed custom visual falls back to the library
    # so one bad function never kills the scene. An EMPTY layer is NOT a
    # failure (the visual is still building in before its hit word) — only
    # an exception or a wrong-size result falls back.
    def _place720(lay720):
        # 720x1280 -> 1080x1920, then fit above the label band.
        if lay720 is None or lay720.size != (720, 1280):
            return False
        vlay.alpha_composite(_fit_above_label(lay720.resize((W, H), Image.BICUBIC)))
        return True
    # v34 (Hark word_t): the scene's word timings [(start, dur, text)] — the
    # visual times its animation to specific words instead of sitting still
    # after popping in. Set in make_video() from the TTS WordBoundary events.
    words = sc.get("words")
    # 1) custom vis_ from video_fx.py (Blind interface: (t, st, d, accent),
    # v34: words= when the function accepts it).
    cv = sc.get("custom_vis")
    if cv and VIDEO_FX is not None:
        fn = getattr(VIDEO_FX, cv, None)
        if fn is not None:
            try:
                _kw = {"words": words} if words and "words" in inspect.signature(fn).parameters else {}
                if _place720(fn(pt, 0.0, sc["d"], acc, **_kw)):
                    return
            except Exception as e:
                print(f"custom vis {cv} scene {idx} failed: {str(e)[:120]}")
    # 2) a stored library visual (the ideas' choice, or a sandbox fallback)
    lv = sc.get("lib_visual")
    if lv and lv in VL.VIS:
        try:
            if _place720(_call_lib_vis(lv, pt, 0.0, sc["d"], acc, words=words)):
                return
        except Exception as e:
            print(f"library vis {lv} scene {idx} failed: {str(e)[:120]}")
    # 2b) the plan kind, mapped to a VL visual
    mv = _VIS_NAME_MAP.get(sc["visual"])
    if mv and mv in VL.VIS:
        try:
            if _place720(_call_lib_vis(mv, pt, 0.0, sc["d"], acc, words=words)):
                return
        except Exception as e:
            print(f"mapped vis {mv} scene {idx} failed: {str(e)[:120]}")
    # 3) the 25-kind library (create.draw_visual)
    C.draw_visual(vd, vlay, sc["visual"], sc.get("value", ""), pt, cy=cy, acc=acc, words=words)


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
    # v32 (Blind): per-scene background kind (changes only when the mood
    # changes, set in plan()) — VL.scene_bg upscaled, 35% alpha over the
    # look bg, cached per kind in _SBG.
    _bk = sc.get("bg_kind")
    if _bk and _bk in VL.SCENE_BG:
        if _bk not in _SBG:
            _sb = VL.scene_bg(_bk).resize((W, H), Image.BICUBIC).convert("RGBA")
            _sb.putalpha(_sb.split()[3].point(lambda v: int(v * 0.35)))
            _SBG[_bk] = _sb
        bg.alpha_composite(_SBG[_bk])
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for (x, y, r, sp) in PART:
        yy = (y - t * sp - idx * 140) % (H + 200) - 100
        b = bokeh(acc, r); lay.paste(b, (int(x + 20 * math.sin(t + r)), int(yy)), b)
    d = ImageDraw.Draw(lay, "RGBA")
    # v34 (Hark dust): 70 specks drifting slowly down, above the background
    # but below the visuals — part of the film texture.
    for (x, y, r, sp) in _DUST:
        yy = (y + t * sp) % (H + 40) - 20
        xx = x + 10 * math.sin(t * 0.5 + y)
        d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=(200, 200, 200, 70))
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
        draw_scene_visual(vd, vlay, p, idx, sc, pt, 900, acc)
        label(ld, sc["label"], pt, acc, idx, look)
    elif layout == 2:  # centered big word, visual small below
        label(ld, sc["label"], pt, acc, idx, look)
        draw_scene_visual(vd, vlay, p, idx, sc, pt, 750, acc)
    elif layout == 3:  # split
        draw_scene_visual(vd, vlay, p, idx, sc, pt, 650, acc)
        d.rectangle([(120, 1080), (W - 120, 1088)], fill=acc)
        label(ld, sc["label"], pt, acc, idx, look)
    else:  # standard
        draw_scene_visual(vd, vlay, p, idx, sc, pt, 800, acc)
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
    # v32 (Blind): the source line — a short official credit under the label
    # (VL.vis_source at y=930 in 720 coords -> ~1400 after upscale, above
    # the caption band). Only when the scene states a sourced fact.
    _src = sc.get("source")
    if _src:
        try:
            _sl = VL.VIS["source_line"](pt, 0.0, sc["d"], text=f"Source: {_src}", y=930, accent=acc)
            if _sl is not None and _sl.size == (720, 1280):
                lay.alpha_composite(_sl.resize((W, H), Image.BICUBIC))
        except Exception as e:
            print(f"source_line scene {idx} failed: {str(e)[:100]}")
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
    # v33 (Ajju 2026-11-11): the camera is STATIC — no zoom/pan/whip/drift.
    # A zoom running through the whole video is not a professional edit, and
    # the constant push-in is what made every video feel the same. The
    # camera() function stays (unused) for reference; motion now comes only
    # from the per-scene ENTER/EMPHASIS effects and the visual's own build-in.
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

def music(total, starts, moods, path, hits=None):
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
    # v34 (Hark SFX at word times, item 7): a hit on each scene's hit word
    # and ticks while a phone number is typed — placed at exact word times,
    # not scene boundaries. hits = [(time_s, kind), ...].
    if hits:
        Lh = int(0.5 * SR); th = np.arange(Lh) / SR
        hit = np.sin(2 * np.pi * np.cumsum(55 + 60 * np.exp(-th * 8)) / SR) * np.exp(-th * 6) * 0.8
        _pl = int(0.12 * SR)
        pop = np.sin(2 * np.pi * 600 * th[:_pl]) * np.exp(-th[:_pl] * 40) * 0.5
        _tl = int(0.03 * SR)
        tick = rng.randn(_tl) * np.exp(-np.arange(_tl) / SR * 200) * 0.6
        for (ht, kind) in hits:
            add(hit if kind == "hit" else pop if kind == "pop" else tick, ht)
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

def load_video_fx(p, wd):
    # v32 (Blind codegen): the per-video code (video_fx.py) was already written
    # + sandbox-tested by codegen.run() into wd/video_fx.py, with
    # codegen_result.json + ideas.json beside it. This LOADS it and applies
    # the ideas.json mapping EXACTLY — transitions by "between", fx by
    # "scene", vis by "scene" — using ONLY p["codegen"]["passed_custom"]
    # (functions that passed the sandbox). A custom function that failed the
    # sandbox is replaced by its library fallback from codegen_result.
    # Returns (n_custom, n_fallback) for the notify line.
    # NOTE: main's v30+v31 crew never actually ran — doc.py has no
    # `import teams`, so the crew raised NameError inside the try and fell
    # back to the single-agent path every time. v32 drops the crew entirely.
    global VIDEO_FX
    VIDEO_FX = None
    cg = p.get("codegen") or {}
    passed = set(cg.get("passed_custom") or [])
    fb = cg.get("fallback_from_library") or {}
    ideas_path = os.path.join(wd, "ideas.json")
    fx_path = os.path.join(wd, "video_fx.py")
    if not os.path.exists(ideas_path) or not os.path.exists(fx_path):
        return 0, 0
    try:
        spec = importlib.util.spec_from_file_location("video_fx", fx_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        VIDEO_FX = mod
    except Exception as e:
        print(f"load_video_fx: cannot import video_fx.py: {str(e)[:150]}")
        VIDEO_FX = None
    try:
        ideas = json.load(open(ideas_path))
    except Exception as e:
        print(f"load_video_fx: cannot read ideas.json: {str(e)[:150]}")
        return 0, 0
    n_custom = n_fb = 0
    tr_used, fx_used, vis_used = [], [], []
    # transitions: "between": [a, b] (1-based) -> boundary a-1
    for it in ideas.get("transitions", []):
        fn = it.get("fn", "")
        a = (it.get("between") or [0])[0]
        bi = a - 1
        if bi < 0 or bi >= len(p.get("transitions", [])):
            continue
        if fn in passed:
            p["transitions"][bi] = fn
            tr_used.append(fn); n_custom += 1
        elif fn in fb:
            p["transitions"][bi] = fb[fn]
            n_fb += 1
    # scene fx: "scene": N (1-based) -> scene N-1
    for it in ideas.get("scene_fx", []):
        fn = it.get("fn", "")
        si = (it.get("scene") or 0) - 1
        if si < 0 or si >= len(p["scenes"]):
            continue
        if fn in passed:
            p["scenes"][si]["emphasis"] = fn
            fx_used.append(fn); n_custom += 1
        elif fn in fb:
            p["scenes"][si]["emphasis"] = fb[fn]
            n_fb += 1
    # visuals: "scene": N -> scene N-1; fn is a custom vis_ OR "library:<name>"
    for it in ideas.get("visuals", []):
        fn = it.get("fn", "")
        si = (it.get("scene") or 0) - 1
        if si < 0 or si >= len(p["scenes"]):
            continue
        if fn.startswith("library:"):
            p["scenes"][si]["lib_visual"] = fn[len("library:"):]
            n_fb += 1
        elif fn in passed:
            p["scenes"][si]["custom_vis"] = fn
            vis_used.append(fn); n_custom += 1
        elif fn in fb:
            _f = fb[fn]
            # a failed vis_ falls back to "visuals_lib:<name>"
            p["scenes"][si]["lib_visual"] = _f[len("visuals_lib:"):] if _f.startswith("visuals_lib:") else _f
            n_fb += 1
    p["video_fx"] = {"tr": tr_used, "fx": fx_used}
    p["video_visuals"] = vis_used
    print(f"load_video_fx: {n_custom} custom (tr {tr_used}, fx {fx_used}, vis {vis_used}) + {n_fb} library fallbacks")
    return n_custom, n_fb


def qc_prompt(p):
    # The QC Reviewer's task: score each scene 1-5, name what is wrong.
    scenes = "; ".join(
        f"{i+1}. {s.get('label', '')}: {s.get('vo', '')[:60]} (visual: {s.get('visual', '')})"
        for i, s in enumerate(p["scenes"]))
    return (f"Score each scene 1-5 on: visual fits the sentence, nothing cut "
            f"at edges, text readable, different from the last video. Scenes: "
            f"{scenes}. Reply with one line per scene: <number> <score> "
            f"<what is wrong, or OK>.")


def preview_sheet(p, wd):
    # v34 (Hark PREV): 2 frames per scene (45% and 92% of each scene) into one
    # contact sheet, for fast layout QC before a full render. Durations are
    # estimated from the vo words when TTS has not run (preview mode).
    ims = []
    for i, s in enumerate(p["scenes"]):
        d = float(s.get("d") or (0.4 * len(str(s.get("vo", "")).split()) + 0.45))
        for fr in (0.45, 0.92):
            ims.append(scene_frame(p, i, d * fr).resize((270, 480)))
    cols = 6
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (270 * cols, 480 * rows))
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % cols) * 270, (k // cols) * 480))
    out = os.path.join(wd, "preview.png")
    sheet.save(out)
    return out


async def make_video(brief, chat, notify=None, workdir=None, recent="", workers=None, recent_styles=None, recent_families=(), preview=False):
    global _P
    wd = workdir or tempfile.mkdtemp(prefix="doc_")
    p = plan(brief, chat, recent, recent_styles, recent_families)
    # v32 (Blind codegen): ONE engine writes tr_/fx_/vis_ in a single call
    # (codegen.run: PLAN -> CODE -> sandbox -> fix x2 -> library fallback),
    # while the QC scores the plan in parallel. A failed custom function
    # falls back to the library — one bad function never kills the video.
    n_custom = n_fb = 0
    try:
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=2) as ex:
            fut_cg = ex.submit(CG.run, p, chat, wd, recent_families)
            fut_qc = ex.submit(chat, [{"role": "system", "content": "You score video scenes 1-5, one line per scene."},
                                      {"role": "user", "content": qc_prompt(p)}])
            fut_cg.result()
            p["team_qc"] = fut_qc.result()
        n_custom, n_fb = load_video_fx(p, wd)
    except Exception as e:
        print("codegen failed:", str(e)[:200])
    if notify and (n_custom or n_fb):
        await notify(f"Codegen: {n_custom} custom functions + {n_fb} library fallbacks for this video.")
    # v34 (Hark PREV, item 3): preview mode — render a contact sheet (2 frames
    # per scene) and exit, for fast layout QC. Durations + word timings are
    # estimated from the vo text (no TTS, no audio, no full render).
    if preview or os.environ.get("DIVYA_PREVIEW"):
        for s in p["scenes"]:
            _w = str(s.get("vo", "")).split()
            s["d"] = 0.4 * len(_w) + 0.45
            s["words"] = [(i * 0.4, 0.4, w) for i, w in enumerate(_w)]
        _prev = preview_sheet(p, wd)
        return {"path": _prev, "preview": True, "topic": p.get("topic", brief),
                "title": p["title"], "lang": p["lang"], "plan": p,
                "duration": sum(s["d"] for s in p["scenes"])}
    voice = VOICES.get((p["lang"], p.get("voice", "male")), VOICES[(p["lang"], "male")])
    # v32 (M12, Mark): ChristopherNeural (-8%, -4Hz, "calm, deep") for
    # calm/motivational English videos — majority-calm moods, or a brief
    # about motivation/discipline/calm. tts() applies the -8%/-4Hz override.
    _moods = [s.get("mood") for s in p["scenes"]]
    _br = str(brief).lower()
    if (p["lang"] == "en" and p.get("voice", "male") == "male" and
            (_moods.count("calm") >= len(_moods) / 2 or
             any(w in _br for w in ("motivat", "discipline", "calm", "focus", "habit")))):
        voice = VOICES[("en", "male_calm")]
    if notify: await notify(f"Script ready: {p['title']} ({len(p['scenes'])} scenes, {p['lang']}). Voice, animation, music chestunna.")
    gap = 0.45  # v32 (M13, Mark 1a1c1028211d08d1 §1 step 6): 0.45 s breathing room per scene
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
    # v34 (Hark SFX at word times, item 7): a hit on each scene's hit word
    # (pop_t, absolute time) + ticks while a phone number is typed.
    _hits = []
    for i, s in enumerate(p["scenes"]):
        _hits.append((starts[i] + float(s.get("pop_t", 0.0) or 0.0), "hit" if s.get("fact_type") in ("ban", "myth") else "pop"))
        if s.get("fact_type") == "phone":
            for (o, _d, _w) in (s.get("words") or []):
                if any(c.isdigit() for c in _w):
                    _hits.append((starts[i] + float(o), "tick"))
    # voice track positioned exactly
    ins = sum([["-i", s["audio"]] for s in p["scenes"]], [])
    fc = "".join(f"[{i}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{i}];" for i, st in enumerate(starts))
    fc += "".join(f"[a{i}]" for i in range(len(starts))) + f"amix=inputs={len(starts)}:normalize=0,apad,atrim=0:{total:.2f}[o]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", fc, "-map", "[o]", "-ar", str(SR), "-ac", "1", f"{wd}/voice.wav"], check=True)
    music(total, starts, [s["mood"] for s in p["scenes"]], f"{wd}/music.wav", hits=_hits)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{wd}/voice.wav", "-i", f"{wd}/music.wav", "-i", f"{wd}/music_sfx.wav", "-filter_complex",
                    "[0:a]asplit[v1][v2];[1:a]volume=0.55[m];[m][v2]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md];"
                    "[v1]highpass=f=70,acompressor=threshold=0.1:ratio=3,volume=1.5[vv];[2:a]volume=0.55[sx];"
                    # v32 (M6, Mark): final loudnorm -14 LUFS (was alimiter)
                    "[vv][md][sx]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[o]", "-map", "[o]", "-ar", str(SR), f"{wd}/mix.wav"], check=True)
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
    # v34 (Hark delivery, item 9): keep the CRF 23 master, then make a CRF 26
    # delivery copy (much smaller, faster to send) for sending to Ajju.
    # NOTE: the delivery is encoded from the SAME raw source as the master
    # (raw.mp4 + mix.wav + vf chain), NOT by re-encoding the master — a
    # re-encode of the grainy CRF 23 master at CRF 26 came out LARGER than
    # the master (1,290 kbps vs 1,080 kbps: the encoder chases the baked-in
    # grain + quantisation noise). Same input + higher CRF = guaranteed smaller.
    delivery = f"{wd}/divya_doc_delivery.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{wd}/raw.mp4", "-i", f"{wd}/mix.wav", "-vf", vf, "-c:v", "libx264", "-preset", "medium",
                    "-crf", "26", "-maxrate", "2300k", "-bufsize", "4600k", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", delivery], check=True)
    return {"path": out, "delivery_path": delivery, "topic": p.get("topic", brief), "title": p["title"], "lang": p["lang"],
            "script": "\n".join(s["vo"] for s in p["scenes"]), "caption": p.get("caption", ""), "plan": p, "duration": total}
