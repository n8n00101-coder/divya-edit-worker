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
OUTRO = 1.0  # v36 (Blind E4): the end card is 1 s (was 2.2)
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
    # v36 (Blind D — two topics must look different): the 4 looks are now
    # A Investigative (paper, stamps, red/black), B Science/health (clean,
    # blue/teal, diagrams), C Story/emotional (warm, photo frames, soft
    # light), D Data/money (charts, count-ups, green/yellow). Gutka -> A,
    # sleep -> B. Different font pairing, accent colour, layout and
    # transition family per look. The camera is STATIC in every look — the
    # "motion" fields below are the design personality, not camera moves
    # (Ajju's no-zoom ban, v33).
    "A": {"name": "investigative", "top": (28, 22, 18), "bot": (12, 10, 10),
          "accents": [(255, 40, 40), (255, 210, 0)], "font": "anton", "chapter": "none",
          "ease": "hard", "motion": "cut", "bg": "flat", "grain": 4,
          "motion_personality": "snappy pops", "transition_family": "hard cut + stamp slam",
          # v29 (Hark's effects.py): the look's transition TAG picks from FX.TRANSITIONS.
          "fx_tag": "warning", "moves": ["cut", "stamp"],
          "desc": "paper, stamps, red/black — investigations, bans, scams, law, myths busted"},
    "B": {"name": "science", "top": (8, 24, 48), "bot": (6, 60, 70),
          "accents": [(60, 200, 230), (255, 180, 60)], "font": "anton", "chapter": "none",
          "ease": "smooth", "motion": "push", "bg": "gradient", "grain": 5,
          "motion_personality": "smooth glides", "transition_family": "diagram wipe / clock wipe",
          "fx_tag": "space", "moves": ["wipe", "clock"],
          "desc": "clean blue/teal, diagrams — science, health, body, how things work"},
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
    # v36 (Blind D): investigative -> A (checked FIRST — a ban/scam/law topic
    # is always investigative), health + science -> B, motivation + history
    # -> C, money -> D.
    "investigative": {"look": "A", "grain": 4, "desc": "paper, stamps, red/black — ban, scam, law, court, myth, lie, danger, warning"},
    "health": {"look": "B", "grain": 6, "desc": "clean blue/teal — health, body, disease, sleep, food"},
    "science": {"look": "B", "grain": 5, "desc": "clean blue/teal diagrams — science, physics, space, how things work"},
    "motivation": {"look": "C", "grain": 7, "desc": "warm gold film grain — motivation, habits, discipline, focus"},
    "history": {"look": "C", "grain": 8, "desc": "sepia + warm grain — history, ancient, legend, culture"},
    "money": {"look": "D", "grain": 4, "desc": "green/black ledger — money, finance, price, salary, business"},
}
_FAMILY_WORDS = {
    "investigative": ["ban", "banned", "prohibit", "illegal", "scam", "fraud", "law", "court", "myth", "lie", "lies", "danger", "warning", "tobacco", "gutka", "smoking", "alcohol", "drugs", "exposed", "secret", "truth", "fake"],
    "health": ["health", "sleep", "food", "diet", "disease", "doctor", "body", "heart", "brain", "cancer", "medicine", "drug", "exercise", "weight"],
    "science": ["science", "physics", "lightning", "thunder", "space", "atom", "energy", "earth", "planet", "gravity", "biology", "experiment", "ocean", "volcano", "electric", "sound", "light", "weather"],
    "motivation": ["motivat", "discipline", "habit", "focus", "success", "goal", "mindset", "confidence", "routine", "productiv", "willpower", "consist"],
    "history": ["history", "ancient", "king", "queen", "war", "empire", "legend", "temple", "kingdom", "dynasty", "century", "historic", "civilization", "archaeolog"],
    "money": ["money", "finance", "rupee", "price", "salary", "bank", "invest", "stock", "crypto", "business", "startup", "wealth", "rich", "poor", "budget", "loan", "debt"],
}


def topic_family(brief):
    # v34: the topic family from the brief's keywords (most hits wins). "" = none.
    # v36 (Blind D): "investigative" is checked FIRST — any ban/scam/law/
    # court/myth/lie/danger/warning word makes the topic investigative
    # (look A), whatever else it matches. Then the most-hits rule.
    text = (brief or "").lower()
    if any(w in text for w in _FAMILY_WORDS["investigative"]):
        return "investigative"
    best, best_n = "", 0
    for fam, words in _FAMILY_WORDS.items():
        if fam == "investigative":
            continue
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
    # v36 (Blind D): A = investigative (ban/scam/law/myth/lie/danger/warning),
    # B = science + health (clean blue/teal). Gutka ("banned" + "gutka") -> A;
    # sleep ("sleep") -> B.
    "A": ["myth", "myths", "safety", "warning", "danger", "scam", "lie", "lies", "truth", "vs", "versus", "debate", "ban", "banned", "never", "don't", "mistake", "wrong", "fact", "fake", "car", "seat belt", "belt", "helmet", "rule", "law", "court", "tobacco", "gutka", "smoking", "alcohol", "drugs", "effects", "risk", "risks", "illegal", "prohibit"],
    "B": ["lightning", "thunder", "physics", "science", "how", "why", "earth", "space", "atom", "energy", "water", "rain", "magnet", "gravity", "biology", "brain", "body", "experiment", "plant", "animal", "sky", "sun", "moon", "weather", "electric", "sound", "light", "ocean", "volcano", "health", "sleep", "food", "diet", "disease", "doctor", "heart", "cancer", "medicine", "exercise", "weight"],
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


# v36 (Blind D — never the same look as the previous video; store the last
# 5 looks): the CODE side is a JSON file store (an audit trail) — the live
# Worker KV wiring is PENDING Ajju's go, so the Worker does NOT read/write
# KV for this. The runner sets DIVYA_LAST_LOOKS to a path in its workdir;
# otherwise the store lives at ~/workspace/divya-last-looks.json.
def _last_looks_path():
    return os.environ.get("DIVYA_LAST_LOOKS") or os.path.expanduser("~/workspace/divya-last-looks.json")


def load_last_looks(path=None):
    try:
        with open(path or _last_looks_path()) as f:
            data = json.load(f)
        return [s for s in (data if isinstance(data, list) else data.get("looks", [])) if s in LOOKS][-5:]
    except Exception:
        return []


def record_look(look, path=None):
    if look not in LOOKS:
        return
    p = path or _last_looks_path()
    looks = load_last_looks(p) + [look]
    try:
        with open(p, "w") as f:
            json.dump({"looks": looks[-5:], "updated": __import__("datetime").datetime.now().isoformat()}, f)
    except Exception:
        pass


def pick_look(brief, recent="", recent_styles=None, last_looks=None):
    """Topic mood -> design system (A/B/C/D). Never repeats the last 5 videos'
    looks: the Worker stores each finished video's look in KV (styles:<user>,
    most recent last) and passes the last 5 here as `recent_styles`. The kit's
    rule — the style plan must differ from the last 5 (palette + motion +
    transition). Deterministic — never random. v36: `last_looks` (from the
    JSON store, load_last_looks) is consulted the same way — the code-side
    record until the Worker KV wiring lands (pending Ajju's go)."""
    import zlib
    text = (brief or "").lower()
    scores = {k: sum(1 for w in words if w in text) for k, words in _LOOK_WORDS.items()}
    best = max(LOOKS, key=lambda k: scores[k])  # ties -> A (first), the safe default
    # v36: the JSON last-looks store counts as "used" too (same as KV).
    _ll = [s for s in (last_looks or []) if s in LOOKS][-5:]
    if recent_styles:
        used = [s for s in (recent_styles or []) if s in LOOKS][-5:] + _ll
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
    used = _ll
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
 "end_question": "<one short question to the viewers for the 1 s end card, e.g. 'Did you know this?'>",
 "scenes": [{"vo": "...", "label": "<the on-screen TITLE: a 1-3 word phrase from THIS scene's content, caps — never a production label like HOOK, FACT, CTA, NEXT, RECAP, STATS>", "mood": "calm|tense|hopeful|sad|excited|mystery",
             "visual": "<one of %s>", "value": "<short number/word for the visual>",
             "why": "<one sentence: why THIS visual for THIS line — it must mention a word from the vo line>",
             "queries": ["<stock-footage search query 1 that SHOWS the meaning of this line>", "<query 2, a different angle on the same meaning>"],
             "fulfils": ["<prompt requirement ids this scene satisfies, if a spec was given>"],
             "source": "<ONLY a source you are actually citing for this scene's claim, e.g. WHO 2023 — or empty. Never stamp a source you did not use>"}]}
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
build an emotional arc. SOURCE RULE (v79, Blind R5 — replaces the v36 rule): put a source ONLY when you are actually citing
that source for this scene's claim. If you do not know a real source for the claim, leave the source field EMPTY — a missing
source is honest, a stamped one (the same famous name on every scene) destroys trust and fails the compliance check.
SHOT LIST RULE (v79, Blind mail 1 Part 2 + R2/R10): choose every visual from the MEANING of the line — ask "what would a
person actually picture?" — never from the scene's type. Every scene carries "why" (one sentence tied to a word in the
line) and 2 footage "queries" that SHOW the meaning (for a liver line: "doctor holding liver scan", "hospital corridor
night" — never just the topic word). A clock only when the line is about time. A graphic only when the line has a real
number or a real list. Numbers: the "value" must be the exact number the vo line says, with its unit, and never 0.
Each visual must literally show the line's idea (battery=energy, chat=messages/people, graph=growth or fall,
clock=time, calendar=days, warning=danger/mistake, check=right way, versus=comparison, counter=a number, list=steps, heart=love/health,
bar=progress, dot_grid/donut=a percentage of people, gauge=a level, toggle=on/off, phone_buzz=phone notifications,
stick_figure=a person/feeling, quote_card=a quote, arrows_steps=a process, checklist=steps, document=a report,
polaroid=a memory, icon_row=a set of items, bar_compare=two numbers compared,
four=one-in-N people, question=a big question, card=a phone number or helpline,
watch=a stopwatch or rate, stamp=a ban or verdict, stamp_cta=the final call to action).
FRAME-FILL RULE (v79, Ajju A1 — hard rule): every scene must FILL the frame — full-frame footage, or a COMPOSED
graphic scene with several related elements (a document, a map, a photo card, a timeline, a split comparison).
A lone small widget floating on a plain gradient (one donut, one counter, one heart in empty space) is BANNED —
the delivery check measures each frame's content coverage and fails empty scenes.
CREATIVITY RULE (v79, Ajju A5): the number widgets (donut, counter, bar, graph, gauge, dot_grid) are a FALLBACK
for real numbers and lists ONLY — they are not the menu. Most scenes must be composed scenes pictured from the
line itself: photo_frame/polaroid (a photo of the thing), document/newspaper/receipt (papers, reports, headlines),
india_map/world_dots (places), timeline_cards (events over time), versus/balance_scale (two sides), filmstrip/
film_camera (media), speech_bubble/chat (what people say), magnifier (looking closer), product_packet (a product),
warning_sign (danger). Picture what a human editor would show for THIS line, not which widget is free.
If no clear topic is given ("nuvve select chesko", "any", "AUTO", empty) choose a fresh high-retention topic yourself (psychology,
history mysteries, science facts, money habits, health, tech, motivation). Avoid these recent topics: {recent}.
Owner request: """ % C.VISUALS


# v36 (Blind B3 — scene-specific transitions from the 379 library, picked by
# the TOPIC OBJECT of the incoming scene, not one family per video):
# gutka: packet tear wipe, smoke dissolve, stamp cut; sleep: blink
# close-open, clock wipe. "phone-screen zoom" is SKIPPED (Ajju's no-zoom
# ban) — a push is used for phone scenes instead. Never the same transition
# twice in a row, max 2 uses per video (enforced in plan()).
TOPIC_TRANSITIONS = [
    (("ban", "stamp"), "flash_white"),                    # stamp cut
    (("time", "clock"), "clock_0_cw"),                    # clock wipe
    (("phone", "card"), "push_right_smooth"),             # phone (push, not zoom)
    (("place", "document", "packet", "map"), "3d_page_turn_right_smooth"),  # packet tear / paper tear
    (("myth", "smoke"), "noise_dissolve_x1_s2"),          # smoke dissolve
    (("number", "money", "bill"), "wipe_0_hard_expo"),    # hard wipe for a number/bill reveal
    (("comparison", "versus"), "cover_right_smooth"),     # comparison cover
    (("warning",), "flash_white"),                        # hard flash for a warning
    (("list", "moon", "sleep"), "blinds_8_h"),            # blink close-open
]


def _topic_transition_name(sc):
    # The transition INTO this scene, from its topic object (fact type,
    # visual kind, voice-over keywords). Returns a TL name or None.
    txt = (str(sc.get("visual", "")) + " " + str(sc.get("fact_type", "")) + " " +
           str(sc.get("vo", "")) + " " + str(sc.get("label", ""))).lower()
    for keys, name in TOPIC_TRANSITIONS:
        if any(k in txt for k in keys) and name in TL_BY_NAME:
            return name
    return None


def _spec_block(spec):
    """FIX 3 (Blind mail 2): the script step receives prompt_spec.json.
    Every step downstream gets it too (it rides on the plan). The
    instruction is Blind's, verbatim in substance: implement every
    requirement exactly; do not replace them with the usual style."""
    if not spec:
        return ""
    lines = ["\nPROMPT SPEC (the user's contract — implement every requirement exactly. "
             "Do not replace them with your usual style. If you cannot do one, the "
             "compliance check will say which and why):"]
    for r in spec:
        lines.append(f"- {r.get('id')} [{r.get('type')}] {r.get('value')} (user said: \"{r.get('quote')}\")")
    lines.append("In every scene's \"fulfils\" list, name the requirement ids that scene satisfies. "
                 "Every requirement must be satisfied by at least one scene or step.")
    return "\n".join(lines) + "\n"


def plan(brief, chat, recent="", recent_styles=None, recent_families=(), spec=None, cfg=None):
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
    # v36: the JSON last-looks store counts the same way (the KV wiring is
    # pending Ajju's go — the file store is the code-side record).
    _ll = load_last_looks()
    look = pick_look(brief, recent, recent_styles, last_looks=_ll)
    # v34 (Hark blueprint §4): the TOPIC FAMILY picks the design system, so
    # two videos on different topics cannot look the same. The family's look
    # wins unless it was used in the last 5 videos (recent_styles / last-looks).
    fam = topic_family(brief)
    if fam and TOPIC_FAMILIES[fam]["look"] not in (recent_styles or []) and TOPIC_FAMILIES[fam]["look"] not in _ll:
        look = TOPIC_FAMILIES[fam]["look"]
    look_line = (f"DESIGN LOOK {look} ({LOOKS[look]['name']}): {LOOKS[look]['desc']}. "
                 f"Motion personality: {LOOKS[look]['motion_personality']}. "
                 f"Transition family: {LOOKS[look]['transition_family']}."
                 + (f" Topic family: {fam} ({TOPIC_FAMILIES[fam]['desc']})." if fam else ""))
    raw = chat([{"role": "system", "content": "You output strict JSON only."},
                {"role": "user", "content": PLAN.replace("{recent}", recent or "none").replace("{look}", look_line) + _spec_block(spec) + (brief or "AUTO")}])
    p = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))
    # v36 (Blind E4): the end card needs a question; default if the LLM omits it.
    if not str(p.get("end_question", "")).strip():
        p["end_question"] = "Did you know this?"
    sc = [s for s in p.get("scenes", []) if str(s.get("vo", "")).strip()][:16]
    if len(sc) < 4:
        raise ValueError("plan too short")
    for s in sc:
        s["vo"] = re.sub(r"[#*_`]", "", str(s["vo"])).strip()
        if s.get("visual") not in C.VISUALS: s["visual"] = random.choice(C.VISUALS)
        if s.get("mood") not in MOODS: s["mood"] = "calm"
        # v79 (R6): an empty label stays EMPTY — the old "WAIT" default
        # drew a meaningless title box (mail 3, mistake 17: empty title
        # box = fail). The enforcement pass derives a content title
        # from the line, or the scene renders with no title box at all.
        s["label"] = re.sub(r"[^A-Z0-9 %!?'&-]", "", str(s.get("label", "")).upper())[:20]
        s["value"] = str(s.get("value", ""))[:8]
        s["source"] = str(s.get("source", "") or "")[:40]
        # v79 shot list (mail 1 Part 2 / R2): the meaning record rides
        # with the scene — why this visual, the 2 footage queries that
        # show the meaning, and the spec ids the scene fulfils (FIX 3).
        s["why"] = str(s.get("why", "") or "")[:200]
        _q = s.get("queries") or []
        s["queries"] = [str(q)[:80] for q in _q if str(q).strip()][:2]
        _f = s.get("fulfils") or []
        s["fulfils"] = [str(x)[:8] for x in _f if str(x).strip()][:6]
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
    # v36 (Blind B3): the transition INTO a scene is picked by that scene's
    # TOPIC OBJECT first (packet tear, smoke dissolve, stamp cut, blink,
    # clock wipe...); never the same transition twice in a row, max 2 uses
    # per video. Only when no topic object matches does the look's tag pick.
    tag = LOOKS[look].get("fx_tag", "calm")
    tl_used = set()
    _tr_counts = {}
    _trans = []
    for j in range(max(0, len(sc) - 1)):
        _name = _topic_transition_name(sc[j + 1])
        # Never the same transition twice in a row, max 2 uses per video.
        if _name and ((_trans and _trans[-1] == _name) or _tr_counts.get(_name, 0) >= 2):
            _name = None
        if _name is None:
            _name = TL.pick_transition(tags={tag}, used=tl_used,
                                       seed=p["seed"] + j, recent_families=recent_families)["name"]
        tl_used.add(_name)
        _tr_counts[_name] = _tr_counts.get(_name, 0) + 1
        _trans.append(_name)
    p["transitions"] = _trans
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
    # v79 (Blind mail 4 Part 2 — the round-effects diagnosis): the old
    # v32 rule REPLACED the writer's visual with a fixed template per
    # fact type ("FACT -> donut", "HOOK -> clock", "STATS -> counter")
    # — with ~10 templates and 100+ scenes, every template HAD to
    # repeat 10+ times. That mapping is REMOVED. The visual the writer
    # chose from the line's MEANING stands; the only override left is
    # Blind's own widget-by-number-kind table (mail 1 Part 3), applied
    # when the scene actually carries a number: percentage -> donut,
    # "X times" -> two bars, count -> counter, years -> line chart,
    # "1 every N seconds" -> timer.
    import compliance as _comp
    for s in sc:
        ft = fact_type_of(s)
        s["fact_type"] = ft
        if str(s.get("value", "")).strip():
            _want = _comp.widget_for_number_kind(s.get("vo"), s.get("value"))
            if _want and _want in C.VISUALS:
                s["visual"] = _want
    # v34: "place" scenes get the real map from visuals_lib (india_map /
    # world_dots) via lib_visual — the codegen's own choice still overrides
    # this in load_video_fx.
    for s in sc:
        if s.get("fact_type") == "place" and not s.get("lib_visual"):
            _t = (str(s.get("label", "")) + " " + str(s.get("vo", ""))).lower()
            s["lib_visual"] = "india_map" if "india" in _t else "world_dots"
    # v34 (Hark stamp CTA, item 8): the last scene is the call to action — a
    # big word + a rotated stamp + a strikethrough, not a separate outro.
    # v79 (mail 3, R8): a LONG video has ONE CTA at the very end — a
    # chapter that is not the final chapter may not grow its own CTA
    # stamp (the compromise video grew 7 mini-endings). cfg carries
    # allow_cta=False for non-final chapters.
    _last = sc[-1]
    _cta = str(_last.get("label", "")).upper() in ("FOLLOW", "QUIT", "STOP", "TODAY", "SUBSCRIBE") or "follow" in str(_last.get("vo", "")).lower()
    if _cta and (not cfg or cfg.get("allow_cta", True)):
        _last["visual"] = "stamp_cta"
    # v32 (M9): surface the per-cut transition + one SFX per scene in the
    # plan (the codegen's PLAN call already picks per-cut transitions; the
    # transition here is the one that brings the viewer INTO the scene).
    for i, s in enumerate(sc):
        s["transition"] = p["transitions"][i - 1] if 0 < i <= len(p["transitions"]) else ""
        s["sfx"] = SCENE_SFX.get(s.get("fact_type") or s.get("hit_type") or "calm", "pop")
    # v79: the spec + render config ride on the plan (FIX 3 — every
    # step receives prompt_spec.json), and the plan is enforced against
    # Blind's rules BEFORE anything renders: audit -> repair, max 2
    # rounds (FIX 5 / R12 fix loop, at plan level where a scene can
    # still be re-picked). What still fails is recorded on the plan and
    # lands in compliance_report.json — never silently shipped.
    p["spec"] = spec or []
    p["render_config"] = cfg or {}
    if cfg:
        if cfg.get("lang"):
            p["lang"] = cfg["lang"]
        if cfg.get("accent"):
            p["accent"] = cfg["accent"]
        if cfg.get("end_card"):
            p["end_question"] = cfg["end_card"]
        if "zoom" in (cfg.get("excludes") or []):
            p["no_zoom"] = True
    _enforce_plan(p, brief)
    return p


def _enforce_plan(p, brief=""):
    """v79 plan enforcement: compliance.audit_plan + repair_plan,
    max 2 rounds. Repairs touch plan fields only (visual / title /
    transition / sfx / bg kind) — never the voice line."""
    import compliance as _comp
    cfg = p.get("render_config") or {"kind": "short"}
    pools = {"visuals": list(C.VISUALS),
             "transitions": sorted(TL_BY_NAME),
             "sfx": sorted(set(SCENE_SFX.values())),
             "bg_kinds": list(VL.SCENE_BG),
             "pattern_bg": "paper"}
    fixes_all = []
    checks = []
    for _round in range(3):  # audit, repair, audit, repair, audit
        checks = _comp.audit_plan(p["scenes"], cfg,
                                  topic_text=str(p.get("topic") or "") + " " + str(brief or ""),
                                  measure=lambda txt, size: _label_width(ImageDraw.Draw(Image.new("RGB", (8, 8))), txt) if txt else 0)
        fails = [c for c in checks if c["status"] == "FAIL"]
        if not fails or _round == 2:
            break
        fixes = _comp.repair_plan(p["scenes"], cfg, pools, checks)
        if not fixes:
            break
        fixes_all += fixes
    p["plan_checks"] = checks
    p["plan_fixes"] = fixes_all
    _bad = [c for c in checks if c["status"] == "FAIL"]
    if _bad:
        print(f"plan enforcement: {len(_bad)} check(s) still failing after repairs: "
              + "; ".join(f"{c['rule']} s{c.get('scene')}" for c in _bad[:5]))


# ---------------- voice ----------------
async def tts(text, voice, mood, out, rate_add=0):
    import edge_tts
    rate, pitch = MOODS[mood][3]
    if voice == "en-US-ChristopherNeural":  # v32 (M12, Mark): calm, deep
        rate, pitch = "-8%", "-4Hz"
    elif voice in ("en-US-AvaMultilingualNeural", "te-IN-ShrutiNeural", "hi-IN-SwaraNeural"):
        # v36 (Blind E2): the female voice runs at +8% (brighter, more
        # energetic); the pitch still comes from the mood. (Local tests use
        # Google TTS as a stand-in — edge-tts is blocked on this VM;
        # production uses real edge-tts.)
        rate = "+8%"
    if rate_add:
        # v71: pace-match adjustment (percentage POINTS on top of the
        # rate above, total clamped to ±25%). rate_add=0 (default) is
        # byte-identical to the old behaviour.
        try:
            _base = int(str(rate).rstrip("%"))
        except ValueError:
            _base = 0
        rate = f"{max(-25, min(25, _base + rate_add)):+d}%"
    # v75: the output file's directory must exist before the write.
    # A missing dir (long_video chapter dirs) used to surface only as
    # "TTS failed: [Errno 2] ... vo0.mp3" after 4 doomed retries — the
    # real cause (nothing created the directory) was masked as a
    # synthesis failure.
    _out_dir = os.path.dirname(os.path.abspath(out))
    if _out_dir:
        os.makedirs(_out_dir, exist_ok=True)
    last = None
    for attempt in range(4):
        try:
            words, buf = [], bytearray()
            async for ch in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary").stream():
                if ch["type"] == "audio": buf += ch["data"]
                elif ch["type"] == "WordBoundary": words.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
            if not buf: raise RuntimeError("no audio")
            open(out, "wb").write(bytes(buf))
            if not os.path.getsize(out):
                raise RuntimeError("synthesis wrote an empty file")
            return words
        except Exception as e:
            last = e; await asyncio.sleep(1.5 * (attempt + 1))
    # v75: name the exception TYPE so a masked cause can never hide
    # behind a bare errno string again.
    raise RuntimeError(f"TTS failed ({type(last).__name__}): {last}")


# ---------------- v71: reference voice (the user's own saved sample) ----
# The sample is the user's OWN voice clip, sent by them on WhatsApp and
# saved structurally by the Worker (meta source "user-sent" — that send
# is the consent; matching never uses anyone else's clip). v1 does NOT
# clone the timbre: it picks the closest built-in voice and matches the
# PACE. A future cloning engine replaces synth_voice() below only.
FEMALE_VOICES = {"en-US-AvaMultilingualNeural", "te-IN-ShrutiNeural", "hi-IN-SwaraNeural"}
REF_FEMALE_EN = "en-IN-NeerjaNeural"  # closest built-in: female, English (India)
VOICE_NOTE_REF = "reference-matched (pace + closest voice) — exact clone engine pending"


def pace_adjust_rate(ref_wpm, measured_wpm, cur_add=0):
    """Pure: the rate_add (percentage points) that moves the measured
    pace toward the reference pace. Inside a ±5% band -> no change.
    The implied total adjustment stays clamped to ±25 points."""
    if not ref_wpm or not measured_wpm:
        return cur_add
    ratio = float(ref_wpm) / float(measured_wpm)
    if 0.95 <= ratio <= 1.05:
        return cur_add
    return max(-25, min(25, cur_add + round((ratio - 1) * 100)))


def _vo_wpm(words, text):
    """Words per minute of a synthesised scene, from the edge-tts word
    timings [(start, dur, text), ...] — the real spoken pace."""
    if not words:
        return 0
    end = max(o + d for (o, d, _w) in words)
    if end <= 0:
        return 0
    return len(words) / (end / 60.0)


async def synth_voice(text, voice, mood, out, ref=None):
    """The single TTS entry point (v71). A future cloning engine
    replaces THIS function. ref = {"path", "wpm", "lang"} (the user's
    saved reference sample) or None.

    No ref (or no measured pace): exactly the old tts() call, and the
    plan's voice. With a ref: (a) closest built-in voice — a female
    English-India voice when the reference is English and a female
    voice is in use, else the plan's voice; (b) PACE MATCH — synthesise,
    measure the real wpm from the word timings, re-synthesis at an
    adjusted rate until within ~5% of the reference pace (max 2
    adjustments, total rate clamped to ±25%). Returns (words, voice).
    """
    if not ref or not ref.get("wpm"):
        return await tts(text, voice, mood, out), voice
    v = voice
    if str(ref.get("lang") or "").lower().startswith("en") and voice in FEMALE_VOICES:
        v = REF_FEMALE_EN
    add = 0
    words = await tts(text, v, mood, out, rate_add=add)
    for _ in range(2):
        new_add = pace_adjust_rate(ref["wpm"], _vo_wpm(words, text), add)
        if new_add == add:
            break
        add = new_add
        words = await tts(text, v, mood, out, rate_add=add)
    return words, v


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
# v36 (Blind C4): the palette changes by SECTION, so the viewer feels the
# story turn — problem = dark red, fact = deep blue, fix = teal.
SECTION_PALETTE = {
    "problem": ((48, 13, 17), (18, 6, 10)),
    "fact": ((14, 28, 52), (8, 14, 30)),
    "fix": ((10, 42, 44), (6, 22, 26)),
}


def background(mood, look=None, section=None):
    # v25: the LOOK sets the base gradient (the mood still tints the glow +
    # drives the voice). B = flat near-black; C = warm grade + grain; D = grid.
    # v36 (Blind C4): the background is NEVER flat — a RADIAL gradient
    # (centre light, edges dark), 3% film grain, a soft vignette, and the
    # palette changes by SECTION. The section is part of the cache key (it
    # varies scene to scene within one video).
    key = (mood, look, section)
    if key not in _bg:
        top, bot, acc, _ = MOODS[mood]
        if look and look in LOOKS:
            top, bot = LOOKS[look]["top"], LOOKS[look]["bot"]
            acc = LOOKS[look]["accents"][0]
        if section in SECTION_PALETTE:
            top, bot = SECTION_PALETTE[section]
        yy, xx = np.mgrid[0:H, 0:W]
        # Radial gradient: the centre is the light colour, the edges the dark.
        r2 = ((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.44) / (H * 0.62)) ** 2
        rr = np.clip(r2, 0, 1)[..., None]
        g = (np.array(top)[None, None] * (1 - rr) + np.array(bot)[None, None] * rr) * np.ones((1, W, 1))
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
        # like film rather than a flat digital slide. v36: 3% film grain
        # (+-8 in 0-255) for ALL looks, baked into the cached background once.
        _gr = 8
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

_par = {}


def _parallax_layer(mood, look, idx):
    """v36 (Blind C3 — depth): one FAR layer of large soft blurred shapes,
    cached at full size. idx 0 drifts at 2 px/s, idx 1 at 6 px/s (different
    speeds). The shapes are drawn small, blurred, then upscaled — the blur
    is baked once, not per frame."""
    key = (mood, look, idx)
    if key not in _par:
        rng = random.Random(hash(key) & 0x7FFFFFFF)
        small = Image.new("RGBA", (W // 4, H // 4), (0, 0, 0, 0)); dr = ImageDraw.Draw(small)
        for i in range(3):
            _x = rng.randint(0, W // 4); _y = rng.randint(50, H // 4 - 50)
            _r = rng.randint(35, 80)
            _col = MOODS[mood][2] if i == 0 else (120, 140, 180) if i == 1 else (200, 170, 120)
            dr.ellipse((_x - _r, _y - _r // 2, _x + _r, _y + _r // 2), fill=_col + (26,))
        _par[key] = small.filter(ImageFilter.GaussianBlur(10)).resize((W, H))
    return _par[key]


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

def _label_width(d, text):
    # v36: the label's width at the 132 px headline size (fit-to-width, min
    # 96 px) — used by the pattern-break highlight bar. Mirrors label()'s
    # sizing so the bar matches the text.
    words = text.split()
    size = 132
    while size > 96 and sum(d.textlength(w + " ", font=anton(size)) for w in words) > 908:
        size -= 4
    return sum(d.textlength(w, font=anton(size)) + 2 for w in words) - 2


def label(d, text, t, acc, idx, look=None, keyword=None, scale=1.0):
    # v36 (Blind A1/A4/C6 — fixed zones): the scene label ("title") lives in
    # the TITLE zone y 120-450 (frame), NOT at the bottom — it used to sit at
    # y 1190, inside the visual band, which is why "THE BILL" sat on the
    # receipt and "10 PM-6 AM" sat on "8 HOURS". Anton headline (C6), 96 px
    # minimum (A4), fit-to-width; exactly ONE keyword in yellow per line
    # (the value-matching word, else the longest word), the rest near-white;
    # tracking +2 (C6); word pops staggered 70 ms (C7, 60-80 ms).
    # v36: if the label still does not fit on ONE line at the 96 px floor,
    # it wraps to TWO lines (both inside the title zone) — never overflows
    # the frame, never shrinks below 96.
    words = text.split()
    # v79 (FIX 4): an edit's "make the title bigger" scales the start
    # size; the fit-to-width shrink and the 96 px floor are unchanged,
    # so a scaled title grows where the safe frame allows and never
    # overflows. scale=1.0 (every non-edit render) is the old path.
    size = max(96, int(132 * (scale or 1.0)))
    f = anton(size)
    # Fit to width (x 86..994 safe frame); shrink to the 96 px minimum, never below.
    while size > 96 and sum(d.textlength(w + " ", font=anton(size)) for w in words) > 908:
        size -= 4
        f = anton(size)
    _total = sum(d.textlength(w + " ", font=anton(96)) for w in words)
    lines = [words] if _total <= 908 else _split_lines(words, d, 96)
    # The keyword: the word matching the scene value, else the longest word.
    kw = keyword or ""
    _flat = [w for ln in lines for w in ln]
    if kw:
        _kwi = next((i for i, w in enumerate(_flat) if kw.lower() in w.lower()), -1)
    else:
        _kwi = -1
    if _kwi < 0 and _flat:
        _kwi = max(range(len(_flat)), key=lambda i: len(_flat[i]))
    _gi = 0  # global word index across lines (for the keyword + pop stagger)
    for li, ln in enumerate(lines):
        _widths = [d.textlength(w, font=f) + 2 for w in ln]
        _tot = sum(_widths) - 2
        x = (W - _tot) / 2
        cy = 285 if len(lines) == 1 else (225 if li == 0 else 355)
        for k, w in enumerate(ln):
            p = C.pop((t - 0.05 - _gi * 0.07) / 0.3)
            a = int(255 * clamp((t - 0.05 - _gi * 0.07) / 0.12))
            if a > 0:
                fs = anton(int(size * (0.6 + 0.4 * p)))
                cxw = x + d.textlength(w, font=f) / 2
                col = (255, 210, 0) if _gi == _kwi else (250, 245, 235)
                d.text((cxw + 6, cy + 6), w, font=fs, fill=(0, 0, 0, int(a * 0.7)), anchor="mm")
                d.text((cxw, cy), w, font=fs, fill=col + (a,), anchor="mm")
            x += _widths[k]
            _gi += 1
    ul = ease((t - 0.35) / 0.4) * sum(d.textlength(w + " ", font=f) for w in lines[-1])
    if ul > 0:
        _uw = sum(d.textlength(w + " ", font=f) for w in lines[-1])
        d.rectangle([(W - _uw) / 2, 405, (W - _uw) / 2 + ul, 415], fill=acc)


def _split_lines(words, d, size):
    """Split a label's words into 2 balanced lines (word boundaries only),
    each fitting the 908 px safe width at the given size."""
    f = anton(size)
    if len(words) <= 1:
        return [words]
    best, best_diff = None, None
    for cut in range(1, len(words)):
        a, b = words[:cut], words[cut:]
        wa = sum(d.textlength(w + " ", font=f) for w in a)
        wb = sum(d.textlength(w + " ", font=f) for w in b)
        if wa > 908 or wb > 908:
            continue
        diff = abs(wa - wb)
        if best_diff is None or diff < best_diff:
            best, best_diff = [a, b], diff
    return best or [words]


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
    # v79 (Ajju A2, 2026-11-13): REMOVED. The top strip — the video
    # title text ("ALCOHOL TRUTH") plus the segmented progress
    # dashes — is GONE from the scene design entirely (shorts and
    # long): Ajju circled it green as purposeless clutter that reads
    # as a bug, and Blind's review flagged its breadcrumb errors
    # (item 18). A chapter's name belongs on its chapter card only.
    # This function is kept as a no-op so the one historical call
    # site stays harmless; nothing may draw here again.
    return

# v32: plan visual kind -> visuals_lib name (used when the plan's kind has a
# richer VL equivalent; the scene's stored lib_visual wins over this map).
_VIS_NAME_MAP = {
    "document": "document", "polaroid": "polaroid", "warning": "warning_sign",
    "bar": "bracket_bars", "bar_compare": "bracket_bars", "versus": "balance_scale",
}
# v32: cached upscaled scene_bg layers, per bg_kind (built once per process).
_SBG = {}


def _fit_above_label(lay, extra_scale=1.0):
    # v36 (Blind A1 — fixed zones, 720-layer coords x1.5): a 1080x1920 visual
    # layer's CONTENT fits the VISUAL band y 480-1410 (below the title zone
    # 120-450, above the caption band 1440-1725). The old band was 200-1110,
    # which put the visual on top of the label (the label lived at y 1190).
    # Scale + shift so the content fits the band and is centred in it; a
    # layer that already fits is returned unchanged. The fit scale is stored
    # on the module (read by the frame-QC font check — a heavy downscale
    # would shrink the visual's text below the 44 px minimum).
    bb = lay.getbbox()
    if not bb:
        return lay
    top, bot = bb[1], bb[3]
    lo, hi = 480, 1410
    # The pre-render QC's auto-fix scale (80% when the visual overlaps
    # something); 1.0 normally. Applied on top of the band fit. A scaled
    # layer must ALWAYS go through the centering path below (it is smaller
    # than the frame) — never the early return.
    if extra_scale < 1.0:
        nw, nh = int(lay.size[0] * extra_scale), int(lay.size[1] * extra_scale)
        lay = lay.resize((nw, nh), Image.BICUBIC)
        bb = lay.getbbox()
        if not bb:
            return lay
        top, bot = bb[1], bb[3]
    elif top >= lo and bot <= hi:
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
        vlay.alpha_composite(_fit_above_label(lay720.resize((W, H), Image.BICUBIC),
                                              extra_scale=float(sc.get("_vis_scale", 1.0) or 1.0)))
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


# v35 (Ajju 2026-11-11: effects fall ONE ON TOP OF ANOTHER through the whole
# video — Hark: "animation = math formulas, ONE effect at a time").
# Effect durations (s) for the layer transforms in effects.py.
ENTER_DUR = {"fade_in": 0.3, "pop_in": 0.35, "slide_in": 0.4, "rise_in": 0.45,
             "drop_in": 0.6, "zoom_in_blur": 0.4, "wipe_in": 0.4, "iris_in": 0.45,
             "spin_in": 0.5, "flip_in": 0.45, "glitch_in": 0.35}
EMPH_DUR = {"punch": 0.3, "shake": 0.3, "pulse": 0.8, "wiggle": 0.5, "glow": 0.5}
# Visual kinds whose build-in animates with the spoken words / time (draw-on,
# count-up, type-out, fill, pins) — the build-in IS the motion, so no layer
# transform is ever applied on top of it. All visuals_lib kinds animate; the
# create.py kinds listed here animate with words/time too. Anything NOT here
# (versus, quote_card, stick_figure, toggle, phone_buzz, icon_row, lower_third,
# strike, curve) is treated as static and gets a single enter/emphasis instead.
WORD_TIMED_VISUALS = {
    # visuals_lib (all 23 kinds animate): document, bracket_bars, four,
    # question, card, watch, stamp_cta, india_map, world_dots, + the rest.
    "balance_scale", "bracket_bars", "card", "document", "film_camera",
    "filmstrip", "four", "india_map", "magnifier", "newspaper", "photo_frame",
    "polaroid", "product_packet", "question", "receipt", "source_line",
    "speech_bubble", "stamp_cta", "timeline_cards", "typewriter_page",
    "warning_sign", "watch", "world_dots",
    # create.py kinds that animate with words/time.
    "counter", "donut", "dot_grid", "clock", "bar", "bar_compare", "graph",
    "gauge", "battery", "calendar", "list", "checklist", "chat", "check",
    "heart", "arrows_steps", "warning", "stamp", "packets", "india_map",
}
# Hit types where a punch/shake AT the hit word is the point (a single
# transform). All other hit types use the enter as the single motion.
PUNCH_HIT_TYPES = {"number", "percent", "shock", "warning"}

def pick_one_effect(sc, idx, pop_t):
    """v36 (Blind A5/A6/A7 + v35 one-effect rule): decide the SINGLE motion
    effect for a scene (Hark: ONE effect at a time). Returns {vis, vis_name,
    vis_start, vis_dur, label_start} and logs the choice on
    sc['_effect_choice'] so the frame-QC audit can verify it.
    - vis: "build_in" (the visual animates itself — no layer transform),
      "enter" (one enter transform), "emphasis" (one punch/shake at the hit
      word), "fx_" (one custom per-video emphasis from video_fx.py).
    - TIMING (A6): the visual LANDS 80 ms before the spoken key word and the
      SFX hits ON the word. pop_t IS the word time minus 0.08 (set in
      make_video), and pt = t - pop_t, so a pt-time start of 0 lands the
      effect at word - 0.08. An ENTER is different: it is the visual
      ARRIVING, so it starts right after the transition tail (scene time
      TR/2) — in pt-time that is vis_start = TR/2 - pop_t (negative when
      the word is late; the FX functions clamp progress, so the enter is
      simply complete by the word). An enter delayed to the word would leave
      the scene empty until the word (a blank frame, A5). An EMPHASIS
      (punch/shake) starts at the word: vis_start = max(0, TR/2 - pop_t).
    - FINISH (A7): every discrete effect ends before the transition starts
      (scene time d - TR/2, i.e. >=150 ms before the cut); the start is
      clamped so the end never crosses it.
    - label_start: a FIXED early scene time (0.05 s for scene 1 — the hook,
      B4; TR/2 + 0.15 after that). The label is the scene's headline in its
      own zone (120-450) and cannot collide with the visual, so it does not
      wait for the visual's motion — it must be present from the start.
    - "pulse" is continuous (it never ends) so it can never be "one effect at
      a time" — it is mapped to "punch" whenever it would be chosen."""
    kind = sc.get("visual") or ""
    # The visual that will actually draw: custom vis_ > library visual >
    # mapped VL visual > plan kind. A custom vis_ always animates (the
    # codegen writes animated vis_ functions).
    if sc.get("custom_vis"):
        is_word_timed = True
    else:
        _vk = sc.get("lib_visual") or _VIS_NAME_MAP.get(kind) or kind
        is_word_timed = _vk in WORD_TIMED_VISUALS
    # The transition's second half runs loc in [0, TR/2] — a new scene's
    # motion must not start before it ends. tr_tail is the SCENE time at
    # which the transition ends; earliest_pt is the same instant in pt-time.
    tr_tail = TR / 2 if idx > 0 else 0.0
    earliest_pt = max(0.0, tr_tail - pop_t)
    # The latest a discrete effect may END (scene time): before the
    # transition into the next scene starts (d - TR/2, >=150 ms before the cut).
    d = float(sc.get("d", 1.0) or 1.0)
    latest_end_pt = (d - TR / 2) - pop_t
    label_start = 0.05 if idx == 0 else tr_tail + 0.15
    hit_type = sc.get("hit_type") or hit_type_of(sc)
    if is_word_timed:
        # The build-in (word-timed / draw-on) IS the motion. No enter, no
        # emphasis, no custom fx_ on top of it. The label starts at a fixed
        # early scene time (just after the transition tail) — NOT after the
        # hit word: the hit word can fall 4 s into a 5 s scene, and a label
        # tied to it would be missing at mid-scene (the frame-QC caught
        # this on sleep scene 3). The label is the scene's headline; it
        # must be present from the start of the scene.
        choice = {"vis": "build_in", "vis_name": kind, "vis_start": 0.0,
                  "vis_dur": float(sc["d"]), "label": "fade_in",
                  "label_start": label_start}
    elif hit_type in PUNCH_HIT_TYPES:
        emph = sc.get("emphasis") or "punch"
        if emph.startswith("fx_") and VIDEO_FX is not None and callable(getattr(VIDEO_FX, emph, None)):
            _dur = 0.3
            # The punch lands on the word (pt 0 = word - 0.08). If it would
            # run past the next transition, shorten it so it ends in time.
            if earliest_pt + _dur > latest_end_pt and latest_end_pt - earliest_pt > 0.05:
                _dur = latest_end_pt - earliest_pt
            choice = {"vis": "fx_", "vis_name": emph, "vis_start": earliest_pt,
                      "vis_dur": _dur, "label": "fade_in",
                      "label_start": label_start}
        elif emph in FX_LAYER_EMPHASIS:
            if emph == "pulse":
                emph = "punch"
            _d = EMPH_DUR.get(emph, 0.3)
            if earliest_pt + _d > latest_end_pt and latest_end_pt - earliest_pt > 0.05:
                _d = latest_end_pt - earliest_pt
            choice = {"vis": "emphasis", "vis_name": emph, "vis_start": earliest_pt,
                      "vis_dur": _d, "label": "fade_in",
                      "label_start": label_start}
        else:
            enter = sc.get("enter") or "pop_in"
            if enter not in FX_LAYER_ENTER:
                enter = "pop_in"
            _d = ENTER_DUR.get(enter, 0.35)
            # The enter starts right after the transition tail (scene time
            # tr_tail); in pt-time that is tr_tail - pop_t (negative when
            # the word is late — the FX functions clamp progress, so the
            # enter is simply complete by the word).
            choice = {"vis": "enter", "vis_name": enter, "vis_start": tr_tail - pop_t,
                      "vis_dur": _d, "label": "fade_in",
                      "label_start": label_start}
    else:
        enter = sc.get("enter") or "pop_in"
        if enter not in FX_LAYER_ENTER:
            enter = "pop_in"
        _d = ENTER_DUR.get(enter, 0.35)
        choice = {"vis": "enter", "vis_name": enter, "vis_start": tr_tail - pop_t,
                  "vis_dur": _d, "label": "fade_in",
                  "label_start": label_start}
    sc["_effect_choice"] = choice
    # v36 (Blind B2 — "ban" -> stamp slams with a screen shake, 6 px, 120 ms):
    # the shake is part of the slam (one combined effect, not a second
    # motion). It fires at the hit word (pop_t, scene time) and lasts 0.12 s.
    # The camera stays static — this is a 120 ms jolt at the slam, not a move.
    if sc.get("fact_type") == "ban" or kind in ("stamp", "stamp_cta"):
        choice["shake_at"] = pop_t
    return choice


# ---------------- v69: stock B-roll backgrounds (broll.py) ----------------
# make_video() attaches footage to ~half the scenes (alternating, pattern-
# interrupt style): the clip is looped/trimmed by ffmpeg to the scene's
# duration, scaled/cropped to the frame and extracted as a JPG sequence
# under <workdir>/broll_frames/sc<idx>/. scene_frame() then uses the frame
# for the scene-local time t as the full-frame background. Every step is
# failure-grace: no API key / no network / no match / bad clip -> the
# scene keeps its code-drawn background, unchanged.
_BROLL_CACHE = {}
_BROLL_SHADE_IMG = None


def _broll_shade():
    """v79 (mail 1 Part 2): the text-on-footage scrim is a GRADIENT —
    top 0-35% and bottom 60-100%, black fading 70% -> 0 — not the old
    flat 25% shade (text fought the picture, mail 1 point 6). Cached
    per frame size."""
    global _BROLL_SHADE_IMG
    key = (W, H)
    if not isinstance(_BROLL_SHADE_IMG, dict):
        _BROLL_SHADE_IMG = {}
    if key not in _BROLL_SHADE_IMG:
        import numpy as _np
        ys = _np.linspace(0, 1, H)
        a = _np.zeros(H, dtype=_np.float32)
        top = ys < 0.35
        a[top] = 179.0 * (1.0 - ys[top] / 0.35)
        bot = ys > 0.60
        a[bot] = 179.0 * ((ys[bot] - 0.60) / 0.40)
        alpha = _np.repeat(a[:, None], W, axis=1).astype("uint8")
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        img.putalpha(Image.fromarray(alpha, "L"))
        _BROLL_SHADE_IMG[key] = img
    return _BROLL_SHADE_IMG[key]


def _broll_frame(p, idx, t):
    """The B-roll background image for scene idx at scene-local time t,
    or None when the scene has no footage (or the frame is unreadable)."""
    try:
        info = (p.get("broll") or {}).get(idx)
        if not info:
            return None
        # v79: a scene longer than 4 s gets 2 shots (mail 1) — the
        # second clip's frames take over at the split point.
        if info.get("dir2") and float(t) >= float(info.get("split") or 0):
            lt = float(t) - float(info.get("split") or 0)
            n = int(max(0.0, lt) * FPS) % int(info["frames2"])
            key = (info["dir2"], n)
            img = _BROLL_CACHE.get(key)
            if img is None:
                fp = os.path.join(info["dir2"], f"f{n + 1:05d}.jpg")
                if not os.path.exists(fp):
                    return None
                img = Image.open(fp).convert("RGB")
                if len(_BROLL_CACHE) > 24:
                    _BROLL_CACHE.clear()
                _BROLL_CACHE[key] = img
            return img
        n = int(max(0.0, float(t)) * FPS) % int(info["frames"])
        key = (info["dir"], n)
        img = _BROLL_CACHE.get(key)
        if img is None:
            fp = os.path.join(info["dir"], f"f{n + 1:05d}.jpg")
            if not os.path.exists(fp):
                return None
            img = Image.open(fp).convert("RGB")
            if len(_BROLL_CACHE) > 24:
                _BROLL_CACHE.clear()
            _BROLL_CACHE[key] = img
        return img
    except Exception:
        return None


def _extract_broll_frames(clip_path, outdir, dur_s, start_s=1.0, static=False, blur=False):
    """Loop/trim clip_path to dur_s at the frame size (ffmpeg scale+crop)
    and extract it as f%05d.jpg frames at FPS. Returns the frame count
    (0 on any failure).

    v79 (mail 1 Part 2): start_s is the clip's most ACTIVE window
    (frame-difference scored in broll.active_window), not always the
    first seconds. A static clip gets a slow 3% push-in over the scene
    (per-frame crop shrink) so it never looks frozen. A graphic scene
    that owns the frame gets the footage blurred + darkened behind it
    (blur ~14, brightness ~45%) instead of the graphic pasted onto the
    subject (mail 3, mistake 9). Every clip passes the same mild grade
    so different clips feel like one film."""
    try:
        os.makedirs(outdir, exist_ok=True)
        dur_s = max(0.5, float(dur_s))
        if static:
            n_frames = max(2, int(dur_s * FPS))
            vf = (f"scale={int(W * 1.07)}:{int(H * 1.07)}:force_original_aspect_ratio=increase,"
                  f"crop=w='iw*(1-0.03*n/{n_frames})':h='ih*(1-0.03*n/{n_frames})'"
                  f":x='(iw-ow)/2':y='(ih-oh)/2',scale={W}:{H},fps={FPS}")
        else:
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},fps={FPS}")
        if blur:
            vf += ",gblur=sigma=14,eq=brightness=-0.30:saturation=0.85"
        else:
            vf += ",eq=contrast=1.05:saturation=1.07"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-stream_loop", "-1", "-i", str(clip_path),
                        "-ss", f"{max(0.0, float(start_s)):.2f}", "-t", f"{dur_s:.2f}",
                        "-vf", vf,
                        "-q:v", "5", os.path.join(outdir, "f%05d.jpg")],
                       check=True, timeout=300)
        return len([f for f in os.listdir(outdir) if f.endswith(".jpg")])
    except Exception:
        return 0


def _attach_broll(p, wd, all_scenes=False, cfg=None, pool=None):
    """v79: attach stock footage by Blind's METHOD (mail 1 Part 2 +
    mail 3 R10), replacing the v69 "~half the scenes, topic-word
    query" heuristic:

    - The shot list drives the search: each scene's own 2 meaning
      queries (plan's "queries"), never just the topic word.
    - The FootagePool enforces NO-REPEAT (used_ids for the whole
      video — a long video shares one pool across chapters), filters,
      scores, trims to the most active window, and logs rejections
      for footage.json.
    - Targets: footage-only / long videos -> every scene (a graphic
      scene gets the footage blurred + darkened behind the graphic);
      shorts -> the hook + ~55% alternating, never more than 2
      footage or 2 graphic scenes in a row, end card stays graphic.
    - A scene longer than 4 s gets 2 shots (a second clip at the
      halfway split).
    Sets p["broll"], p["broll_sources"] (legacy licence trail) and
    p["footage"] (the pool's footage.json data)."""
    import broll as _br
    import compliance as _comp
    cfg = cfg or p.get("render_config") or {}
    scenes = p["scenes"]
    n = len(scenes)
    orientation = cfg.get("orientation", "portrait")
    every = all_scenes or cfg.get("footage_only") or cfg.get("kind") == "long"
    if every:
        targets = [i for i in range(n) if i != n - 1 or not cfg.get("allow_cta", True)]
    else:
        targets = []
        want = max(1, round(0.55 * (n - 1)))
        flags = [False] * n
        if n > 1:
            flags[0] = True  # hook = strongest footage
        got = 1 if n > 1 else 0
        for i in range(1, n - 1):
            prev2 = flags[i - 2] if i >= 2 else None
            if prev2 is False and flags[i - 1] is False:
                flags[i] = True  # never 2 graphic scenes in a row... (this one breaks the run)
                got += 1
            elif prev2 is True and flags[i - 1] is True:
                flags[i] = False  # never 2 footage in a row beyond a pair
            elif got < want:
                flags[i] = True
                got += 1
        targets = [i for i in range(n - 1) if flags[i]]
    if pool is None:
        pool = _br.FootagePool(state_path=os.path.join(wd, "footage_state.json"))
    p["_footage_pool"] = pool
    attached, sources = {}, []
    dl = os.path.join(wd, "broll_dl")
    for i in targets:
        sc = scenes[i]
        queries = [q for q in (sc.get("queries") or []) if str(q).strip()]
        if not queries:
            topic = str(p.get("topic") or "").strip()
            label = str(sc.get("label") or "").strip()
            queries = [q for q in dict.fromkeys(
                (" ".join((topic + " " + label).split()), topic, label)) if q]
        dur_s = float(sc.get("d") or 6)
        # v79 (A4 — Ajju's ASSAULTS frame is the canonical failure: a
        # warning triangle pasted ON the hand/bottle): a widget/icon
        # scene NEVER pastes its graphic over the footage subject, in
        # shorts too — the footage under it is blurred + darkened so
        # the graphic owns a treated frame (Blind mail 1, Part 2).
        blur = bool(_comp.needs_blur_treatment(sc))
        rec = None
        # v79 (FIX 4): an edit render re-fetches the SAVED clip for a
        # scene the edit did not touch — same clip id, same start,
        # same push-in — so untouched scenes stay exactly the same.
        _saved_map = p.get("_saved_footage") or {}
        _saved = _saved_map.get(i + 1) or _saved_map.get(str(i + 1))
        if _saved and (i + 1) not in (p.get("_edit_changed") or set()):
            _got = pool.fetch_by_id(_saved.get("clip_id", ""), dl)
            if _got:
                _st, _mo = _br.active_window(_got["path"], dur_s)
                rec = {**_got, "query": _saved.get("query", ""),
                       "keyword": _saved.get("keyword", ""),
                       "start": _saved.get("start", _st),
                       "static": _saved.get("static", _mo < 1.2)}
                pool.used_ids.append(rec["clip_id"])
                pool.assignments.append(
                    {"scene": i + 1, "clip_id": rec["clip_id"],
                     "provider": rec["provider"],
                     "source_url": rec["source_url"],
                     "query": rec["query"], "keyword": rec["keyword"],
                     "start": rec["start"], "static": rec["static"]})
                pool.last_uploader = rec.get("uploader") or pool.last_uploader
                pool._save()
                print(f"broll scene {i + 1}: saved clip reused ({rec['clip_id']})")
        if rec is None:
            rec = pool.assign(i + 1, queries, dur_s, dl,
                              orientation=orientation, line=str(sc.get("vo") or ""))
        if not rec:
            continue
        fdir = os.path.join(wd, "broll_frames", f"sc{i}")
        # v79 (FIX 2): "no zoom" in the prompt switches the push-in
        # OFF too — the requirement wins over the footage default.
        _push = bool(rec.get("static")) and "zoom" not in (cfg.get("excludes") or [])
        nframes = _extract_broll_frames(rec["path"], fdir, dur_s,
                                        start_s=rec.get("start", 1.0),
                                        static=_push,
                                        blur=blur)
        if nframes <= 0:
            continue
        entry = {"dir": fdir, "frames": nframes}
        if dur_s > 4.0:
            rec2 = pool.assign(i + 1, queries, dur_s / 2, dl,
                               orientation=orientation, line=str(sc.get("vo") or ""))
            if rec2:
                fdir2 = os.path.join(wd, "broll_frames", f"sc{i}b")
                _push2 = bool(rec2.get("static")) and "zoom" not in (cfg.get("excludes") or [])
                nf2 = _extract_broll_frames(rec2["path"], fdir2, dur_s / 2,
                                            start_s=rec2.get("start", 1.0),
                                            static=_push2,
                                            blur=blur)
                if nf2 > 0:
                    entry.update({"dir2": fdir2, "frames2": nf2,
                                  "split": round(dur_s / 2, 2)})
                    sources.append({"scene": i + 1, "provider": rec2["provider"],
                                    "source_url": rec2["source_url"],
                                    "query": rec2["query"]})
        attached[i] = entry
        sc["has_footage"] = True
        sources.append({"scene": i + 1, "provider": rec["provider"],
                        "source_url": rec["source_url"],
                        "query": rec["query"]})
    if attached:
        p["broll"] = attached
        p["broll_sources"] = sources
        print(f"broll: footage on {len(attached)}/{n} scenes "
              f"({', '.join(s['provider'] for s in sources)})")
    p["footage"] = pool.footage_json()


def scene_frame(p, idx, t, return_layers=False):
    # return_layers (v35 frame-QC): also return the visual/label layer alpha
    # bboxes + the effect choice, so the QC can check geometry (overlap,
    # cutoff, collisions) on the actual layers instead of guessing from a
    # flat composited frame. Returns (rgb, vlay_bbox, llay_bbox, choice).
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
    # v69 (Ajju — Hark uses real footages, Divya used only plain drawn
    # backgrounds): if make_video attached a stock B-roll clip to this
    # scene (p["broll"]), the footage frame IS the full-frame background
    # and every overlay below (header, visual, label, source, captions)
    # draws over it exactly as before. A slight dark shade keeps the
    # labels readable on bright footage. No clip -> the code-drawn
    # background below, byte-for-byte the old behaviour.
    _fb = _broll_frame(p, idx, t)
    if _fb is not None:
        bg = _fb.convert("RGBA")
        bg.alpha_composite(_broll_shade())
    else:
        bg = background(mood, look, sc.get("section")).convert("RGBA")
        # v36 (Blind C3): the FAR layer — two soft shape layers drifting at
        # 2 px/s and 6 px/s (different speeds), tiled so they wrap. The camera
        # stays static — only the background layers drift. (Bokeh = mid, dust = near.)
        for _idx, _spd in ((0, 2.0), (1, 6.0)):
            _pl = _parallax_layer(mood, look, _idx)
            _off = int(-_spd * t) % W
            bg.alpha_composite(_pl, (_off, 0))
            bg.alpha_composite(_pl, (_off - W, 0))
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
    # v35 (Ajju: effects stack one on top of another — Hark: ONE effect at a
    # time). The choice is made ONCE here, before the layout draws anything,
    # so the visual and the label can never be given two motions at once.
    _ch = pick_one_effect(sc, idx, float(sc.get("pop_t", 0.0) or 0.0))
    # The label's word pops start at label_start (a SCENE-local time, not
    # a delay after the hit word — a late hit word must not hide the label
    # for half the scene). label_t is the label's own clock; before
    # label_start it is 0 and the label is invisible.
    label_t = max(0.0, t - _ch.get("label_start", 0.35))
    # v36 (Blind A1/B5 — fixed zones + pattern break): the label is ALWAYS
    # the top headline (title zone 120-450, drawn by label()); the visual
    # lives in the band 480-1410. Layouts: 0 standard (visual centred,
    # cy 945), 2 compact (visual lower/smaller, cy 1050). Layout 1 is
    # RESERVED for the pattern break — the scene at 50% of the video gets a
    # full-bleed visual (scaled 1.15x, bleeding off the band edges) + a
    # yellow highlight bar behind the label, so one scene reads clearly
    # different (B5: "full-bleed visual, or split screen").
    n_sc = len(p["scenes"])
    _pb = max(1, min(n_sc - 2, int(n_sc * 0.5))) if n_sc >= 4 else -1
    if idx == _pb:
        layout = 1
    else:
        layout = ((idx + seed) % 2) * 2
    vlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vlay, "RGBA")
    llay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(llay, "RGBA")
    # v34: the stamp visual itself carries the word (e.g. BANNED) — drawing
    # the scene label too duplicates it (v33 dup-text rule), so skip it.
    nolabel = sc.get("visual") == "stamp"
    _kw = str(sc.get("value", "") or "")
    if layout == 1:  # pattern break: full-bleed
        draw_scene_visual(vd, vlay, p, idx, sc, pt, 945, acc)
        # full-bleed: scale the visual layer 1.15x about its centre so it
        # bleeds off the band edges (the excess is clipped by the frame).
        _bw, _bh = vlay.size
        _big = vlay.resize((int(_bw * 1.15), int(_bh * 1.15)), Image.BICUBIC)
        vlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        vlay.alpha_composite(_big, ((_bw - _big.width) // 2, (_bh - _big.height) // 2))
        # yellow highlight bar behind the label (drawn first on the label layer).
        if not nolabel:
            _lw = _label_width(ld, sc["label"])
            ld.rectangle([(W - _lw) / 2 - 24, 205, (W + _lw) / 2 + 24, 365], fill=(255, 210, 0, 90))
        label(ld, sc["label"], label_t, acc, idx, look, keyword=_kw, scale=float(p.get("title_scale") or 1.0)) if not nolabel else None
    elif layout == 2:  # compact: visual lower/smaller
        draw_scene_visual(vd, vlay, p, idx, sc, pt, 1050, acc)
        label(ld, sc["label"], label_t, acc, idx, look, keyword=_kw, scale=float(p.get("title_scale") or 1.0)) if not nolabel else None
    else:  # standard
        draw_scene_visual(vd, vlay, p, idx, sc, pt, 945, acc)
        label(ld, sc["label"], label_t, acc, idx, look, keyword=_kw, scale=float(p.get("title_scale") or 1.0)) if not nolabel else None
    # v35: ONE motion effect on the visual layer — the choice made above by
    # pick_one_effect(). "build_in" means the visual animates itself (word-
    # timed / draw-on) and NO layer transform is applied on top of it; that
    # was the stacking (enter + emphasis + build-in all at once, plus the
    # transition across the cut). "enter" / "emphasis" / "fx_" is the single
    # transform, started after the transition tail (vis_start). The label
    # gets NO layer transform at all — its motion is its word-by-word pops
    # (label(), starting at label_start above), so it can never clash with
    # the visual. The camera stays STATIC (v33).
    if _ch["vis"] == "enter":
        vlay = getattr(FX, _ch["vis_name"])(vlay, pt, _ch["vis_start"])
    elif _ch["vis"] == "emphasis":
        vlay = getattr(FX, _ch["vis_name"])(vlay, pt, _ch["vis_start"])
    elif _ch["vis"] == "fx_":
        _fn = getattr(VIDEO_FX, _ch["vis_name"], None)
        if callable(_fn):
            vlay = _fn(vlay, pt, _ch["vis_start"], sc["d"])
    # "build_in": no transform — the visual's own animation is the motion.
    # v35 frame-QC: the alpha bboxes of the two layers (their real extents
    # after the single effect was applied) — captured here, before they are
    # composited onto the content layer.
    _vb = vlay.getchannel("A").getbbox()
    _lb = llay.getchannel("A").getbbox()
    lay.alpha_composite(vlay)
    lay.alpha_composite(llay)
    # v36 (Blind A1/E3 — fixed zones): the source line lives in the SOURCE
    # zone y 1755-1845 (frame) = y 1170-1230 in the 720-layer coords the VL
    # function uses. It used to be drawn at y=930 (frame ~1395), inside the
    # caption band. Only when the scene states a sourced fact (E3: a source
    # line on every fact/number).
    _src = sc.get("source")
    _src_bb = None
    # The pre-render QC drops the source line (the smaller item) when it
    # still collides after the visual is scaled to 80%.
    if _src and not sc.get("_drop_source"):
        try:
            _sl = VL.VIS["source_line"](pt, 0.0, sc["d"], text=f"Source: {_src}", y=1200, accent=acc)
            if _sl is not None and _sl.size == (720, 1280):
                lay.alpha_composite(_sl.resize((W, H), Image.BICUBIC))
                _sw = ImageDraw.Draw(lay).textlength(f"Source: {_src}", font=VL._font(34, "small")) * 1.5
                _src_bb = (int(W / 2 - _sw / 2), 1782, int(W / 2 + _sw / 2), 1818)
        except Exception as e:
            print(f"source_line scene {idx} failed: {str(e)[:100]}")
    # v36 (Blind B4 — hook in the first 1 s): NO slow fade-in cold-open.
    # The old cold-open (a dark overlay + the big video title fading in over
    # 0.5 s, covering the visual for the first 2.4 s) hid the hook. The hook
    # is now scene 1's label + visual, present at frame 1 with no fade
    # (the label's first word pops at 0.05 s, the visual builds in from t=0).
    # v33 (Ajju 2026-11-11): the camera is STATIC — no zoom/pan/whip/drift.
    # A zoom running through the whole video is not a professional edit, and
    # the constant push-in is what made every video feel the same. The
    # camera() function stays (unused) for reference; motion now comes only
    # from the visual's own build-in (v35: one effect at a time).
    _img = Image.alpha_composite(bg, lay).convert("RGB")
    # v36 (Blind B2): the stamp-slam screen shake — 6 px, 120 ms, at the
    # hit word (recorded as shake_at in the effect choice). A jolt, not a
    # camera move: the frame is offset by +/-6 px on alternate frames.
    _shake_at = (sc.get("_effect_choice") or {}).get("shake_at")
    if _shake_at is not None and _shake_at <= t < _shake_at + 0.12:
        _dx = 6 if int(t * 60) % 2 == 0 else -6
        _dy = -6 if int(t * 60) % 2 == 0 else 6
        _shaken = Image.new("RGB", (W, H), (0, 0, 0))
        _shaken.paste(_img, (_dx, _dy))
        _img = _shaken
    if return_layers:
        return _img, _vb, _lb, sc.get("_effect_choice"), _src_bb
    return _img

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
    # v36 (Blind E4): the end card is 1 s — a QUESTION to the viewers +
    # the channel name, not a plain fade. The question comes from
    # p["end_question"] (set by plan()); the channel name is "DIVYA".
    # The question is a title line (Anton 96 px, the title minimum, word
    # boundaries only, max 2 lines — extra words are dropped, never cut).
    acc = tuple(p.get("accent") or MOODS[p["scenes"][-1]["mood"]][2])
    im = background(p["scenes"][-1]["mood"], p.get("look"), p["scenes"][-1].get("section"))
    d = ImageDraw.Draw(im)
    q = (p.get("end_question") or "Did you know this?").strip().upper()
    f = anton(96)
    lines, cur = [], ""
    for w in q.split():
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) <= W - 160:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
            if len(lines) >= 2:
                break
    if cur and len(lines) < 2:
        lines.append(cur)
    k = C.pop(t / 0.5)
    y = 700
    for ln in lines[:2]:
        w = d.textlength(ln, font=f); d.text(((W - w) / 2, y), ln, font=f, fill=(255, 255, 255))
        y += 130
    f2 = anton(int(110 * max(k, 0.2)))
    w = d.textlength("DIVYA", font=f2); d.text(((W - w) / 2, y + 120), "DIVYA", font=f2, fill=acc)
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

def _payoff_idx(p):
    """v36 (Blind E1): the payoff scene — the biggest fact (the largest number
    in the value/label). If no scene has a number, the verdict scene
    (ban/myth) is the payoff."""
    best, best_n = 0, -1
    for i, s in enumerate(p["scenes"]):
        _nums = re.findall(r"\d+(?:\.\d+)?", str(s.get("value", "")) + " " + str(s.get("label", "")))
        _n = max((float(x) for x in _nums), default=0)
        if _n > best_n:
            best, best_n = i, _n
    if best_n <= 0:
        for i, s in enumerate(p["scenes"]):
            if s.get("fact_type") in ("ban", "myth"):
                return i
    return best


def music(total, starts, moods, path, hits=None, payoff=None):
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
        # v36 (Blind E1): the whoosh lands 100 ms BEFORE the cut (was 300 ms).
        add(whoosh, s - 0.1)
        if moods[i] in ("tense", "excited", "mystery"): add(boom * 0.6, s)
    # v36 (Blind E1): a soft riser builds for 1.5 s before the payoff (the
    # biggest fact), then 200 ms of SILENCE before the fact lands — the
    # classic hook-payoff shape. The riser is a rising sine sweep; the
    # silence mutes both the music and the SFX in that window.
    if payoff is not None and 1.7 < payoff < total - 1:
        _rl = int(1.3 * SR); _rt = np.arange(_rl) / SR
        _f0, _f1 = 220.0, 880.0
        _riser = np.sin(2 * np.pi * (_f0 * _rt + (_f1 - _f0) * _rt ** 2 / (2 * 1.3))) * (_rt / 1.3) * 0.12
        _a = int((payoff - 1.5) * SR); _e = min(n, _a + _rl)
        out[_a:_e] += _riser[:_e - _a]
        _sa, _se = int((payoff - 0.2) * SR), int(payoff * SR)
        out[_sa:_se] = 0; sfx[_sa:_se] = 0
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
    # v36 (Blind A1/A4 — fixed zones): the caption band is y 1440-1725
    # (frame), captions ONLY. MarginV 200 puts the caption bottom at 1720.
    # Min caption font 72 px (A4): English 96, Telugu 72 (was 70).
    # MarginL/R 80 keeps the 40 px side margin with room.
    # v79 (R-P5 + R7 + mail 1 Part 3): the caption spec is a RENDERER
    # PARAMETER from prompt_spec — chunk bounds (short 2-4 words, long
    # 4-7), size and colour come from p["render_config"], and chunks
    # break on PHRASE BOUNDARIES (compliance.chunk_caption_words),
    # never mid-phrase on a fixed word count. PlayRes follows the
    # actual frame size. Long videos get the dark band behind the
    # captions (R7: BorderStyle 3 box).
    import compliance as _comp
    cfg = p.get("render_config") or {}
    cspec = cfg.get("caption_spec") or {}
    wmin, wmax = cspec.get("words") or ((4, 7) if cfg.get("kind") == "long" else (2, 4))
    size = 72 if p["lang"] == "te" else 96
    size = max(40, int(round(size * (H / 1920.0) * float(cspec.get("size_scale") or 1.0))))
    _col = cspec.get("colour")
    primary = "&H0040D8FF"
    if _col:
        r, g, b = (int(_col[0]), int(_col[1]), int(_col[2]))
        primary = f"&H00{b:02X}{g:02X}{r:02X}"
    border_style = 3 if cfg.get("kind") == "long" else 1
    margin_v = int(round(200 * (H / 1920.0))) or 60
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: K,{fn},{size},{primary},&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,1,0,{border_style},6,3,2,80,80,{margin_v},1

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
        groups = _comp.chunk_caption_words(ws, wmin, wmax)
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


def _qc_geometry(vb, lb, has_source, expect_label=True, src_bb=None):
    """v36 (Blind A1/A4 — fixed zones): geometry checks on one scene's layer
    bboxes (mid-scene, settled). Zones (1080x1920 frame): title/label
    120-450, visual 480-1410, caption band 1440-1725 (captions ONLY),
    source 1755-1845. vb = visual-layer alpha bbox, lb = label-layer alpha
    bbox, src_bb = source-line bbox (or None). A flaw is a real defect
    (clipped at the frame edge, overlapping, missing, colliding, or in the
    caption band). Sitting outside the 40 px margin while still inside the
    frame is only a WARNING — the bold full-bleed visuals (four, card,
    stamp_cta, and the pattern-break scene) do that by design."""
    flaws, warnings = [], []
    # Caption band: NOTHING except the karaoke captions may touch it.
    for _name, _bb in (("visual", vb), ("label", lb), ("source", src_bb)):
        if _bb is None:
            continue
        if _bb[1] < 1725 and _bb[3] > 1440:
            flaws.append(f"{_name} intrudes into the caption band (bbox y {_bb[1]}..{_bb[3]})")
    if vb is None:
        flaws.append("visual missing/empty at mid-scene")
    else:
        if vb[0] <= 2 or vb[2] >= W - 2:
            flaws.append(f"visual clipped at frame edge (bbox x {vb[0]}..{vb[2]})")
        elif vb[0] < 40 or vb[2] > W - 40:
            warnings.append(f"visual outside 40 px margin (bbox x {vb[0]}..{vb[2]})")
        if vb[1] < 470:
            flaws.append(f"visual collides with title zone (bbox top y {vb[1]})")
        if vb[3] > 1420:
            flaws.append(f"visual overflows into caption band (bbox bottom y {vb[3]})")
    if lb is None:
        # A missing label at mid-scene is a flaw — unless the scene is a
        # stamp visual (expect_label=False), where the label is skipped by
        # design because the stamp itself carries the word.
        if expect_label:
            flaws.append("label missing at mid-scene")
    else:
        if lb[0] <= 2 or lb[2] >= W - 2:
            flaws.append(f"label clipped at frame edge (bbox x {lb[0]}..{lb[2]})")
        elif lb[0] < 40 or lb[2] > W - 40:
            warnings.append(f"label outside 40 px margin (bbox x {lb[0]}..{lb[2]})")
        if lb[1] < 110:
            flaws.append(f"label collides with header (bbox top y {lb[1]})")
        if lb[3] > 460:
            flaws.append(f"label overflows below its zone (bbox bottom y {lb[3]})")
    if src_bb is not None:
        if src_bb[1] < 1745 or src_bb[3] > 1855:
            flaws.append(f"source line outside its zone (bbox y {src_bb[1]}..{src_bb[3]})")
    if vb is not None and lb is not None and expect_label:
        # The visual and the label live in separate zones — any overlap is
        # the "text sits on the visual" defect Blind flagged.
        if vb[3] > lb[1] + 10 and vb[1] < lb[3] - 10:
            flaws.append(f"label overlaps visual (visual y {vb[1]}..{vb[3]}, label y {lb[1]}..{lb[3]})")
    return flaws, warnings


def _qc_audit(sc, idx):
    """v36: verify the one-effect decision for one scene (the stacking audit).
    Returns a list of flaw strings (empty = clean). Rules (Blind A6/A7):
    - exactly one motion per layer, the label an alpha-only fade;
    - an ENTER starts right after the transition tail (scene time TR/2);
      an EMPHASIS/fx_ starts at the hit word (pt 0 = word - 0.08) or right
      after the transition tail, whichever is later;
    - every discrete effect ENDS before the next transition starts
      (scene time d - TR/2, i.e. >=150 ms before the cut);
    - the label starts early (0.05 s scene 1, TR/2 + 0.15 after that) and
      never later than 1.0 s — it is the headline and must be present from
      the start (it lives in its own zone, so it cannot clash with the
      visual)."""
    flaws = []
    ch = sc.get("_effect_choice")
    if not ch:
        return ["no effect choice logged (pick_one_effect never ran)"]
    if ch.get("vis") not in ("build_in", "enter", "emphasis", "fx_"):
        flaws.append(f"visual motion is not a single choice: {ch.get('vis')}")
    if ch.get("label") != "fade_in":
        flaws.append(f"label motion is not fade_in: {ch.get('label')}")
    pop_t = float(sc.get("pop_t", 0.0) or 0.0)
    d = float(sc.get("d", 1.0) or 1.0)
    tr_tail = TR / 2 if idx > 0 else 0.0
    # The label must start early (after the transition tail, never late).
    _earliest_label = 0.05 if idx == 0 else tr_tail + 0.1
    if ch.get("label_start", 0.0) < _earliest_label - 0.01:
        flaws.append("label starts inside the transition tail")
    if ch.get("label_start", 0.0) > 1.0:
        flaws.append("label starts too late in the scene")
    if ch.get("vis") == "build_in":
        # No layer transform — the build-in IS the scene's entrance and the
        # crossfade is the scene arriving, so they do not stack on the same
        # layer. Delaying a build-in would desync it from its hit word.
        return flaws
    # A layer transform: it must start at/after the transition tail (in
    # scene time) and end before the next transition starts.
    start_scene = pop_t + ch.get("vis_start", 0.0)
    end_scene = start_scene + ch.get("vis_dur", 0.35)
    if start_scene < tr_tail - 0.01:
        flaws.append("visual motion starts inside the transition tail")
    if end_scene > d - TR / 2 + 0.05:
        flaws.append(f"visual motion runs into the next transition (ends {end_scene:.2f}s, scene {d:.2f}s)")
    return flaws


def _log_rejection(p, fq, wd=None):
    """v36 (Blind E7): log EVERY rejection (a video whose frame QC fails) as
    one JSON line — per-video in wd/qc_rejections.jsonl (the test script
    copies it to ~/workspace/qc_rejections.jsonl). After 20 videos the top
    3 mistakes are added to the SYSTEM rules in divya_codegen.py (see
    qc_top_mistakes there) — that rule-update is a future step, not now."""
    if fq.get("passed"):
        return None
    rec = {"title": p.get("title"), "topic": p.get("topic"), "look": p.get("look"),
           "flaws": fq.get("flaws", []), "warnings": fq.get("warnings", []),
           "scenes": [{"idx": sc["idx"], "flaws": sc["flaws"]} for sc in fq.get("scenes", []) if sc["flaws"]]}
    try:
        import datetime as _dt
        rec["at"] = _dt.datetime.now().isoformat()
        _p = os.path.join(wd or tempfile.gettempdir(), "qc_rejections.jsonl")
        with open(_p, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return _p
    except Exception:
        return None


def frame_qc(p, video_path, wd=None):
    """v35 (Ajju: "Divya is not checking at all"). Automated post-render
    frame check. The old team_qc scores the PLAN text and never looks at a
    rendered frame — that is why stacked effects shipped. This checks the
    actual rendered output, per scene:
      (a) the effect audit — exactly one motion per layer, sequenced, no
          motion overlapping the transition tail;
      (b) the layer geometry — visual and label present, inside the safe
          frame, not overlapping each other, not colliding with the header
          or the source line, nothing in the caption band except captions.
          Checked at THREE times per scene (early, mid, late), not just
          mid-scene (v36, Blind E6);
      (c) the encoded frames themselves — sampled from the video file every
          0.5 s (v36, Blind E6), not blank, not a solid colour, and never a
          blank frame (mean brightness change < 1% vs the background for
          > 200 ms = fail, Blind A5);
      (d) the typewriter invariant — a typewriter scene never shows a
          trailing partial word (v36, Blind A2/E6; checked in code, the
          reveal rule is whole words only by construction);
      (e) the fonts — the label is a title (>= 96 px, enforced by the
          fit-to-width floor in label()) and the captions are >= 72 px
          (write_ass); both are code constants, verified here.
    Returns {"passed": bool, "scenes": [{idx, passed, flaws}], "flaws": [...]}.
    A failing scene is FLAGGED, never silently shipped. Rejections are
    logged by _log_rejection (Blind E7)."""
    scenes_out, all_flaws, all_warnings = [], [], []
    starts = p.get("starts") or []
    n = len(p.get("scenes") or [])
    # (c) the encoded frames, every 0.5 s — one ffmpeg pass (fps=2), not one
    # call per frame. _P is the plan (for the background comparison).
    _frames = []
    try:
        _fd = tempfile.mkdtemp(prefix="v36_qc_")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video_path, "-vf",
                        "fps=2,scale=270:-1", os.path.join(_fd, "f%04d.jpg")],
                       check=True, timeout=120)
        _frames = sorted(os.listdir(_fd))
        _fdir = _fd
    except Exception as e:
        all_flaws.append(f"frame extract failed: {str(e)[:100]}")
        _fdir = None
    for i in range(n):
        sc = p["scenes"][i]
        flaws, warnings = [], []
        d = float(sc.get("d", 1.0) or 1.0)
        # The render runs in forked child processes (mp.Pool), so the
        # _effect_choice set by pick_one_effect() during the render lives
        # only in the children's copies — the parent's plan never gets it.
        # Call scene_frame() HERE (in the parent) first, so it populates
        # _effect_choice, THEN run the audit on it.
        # (a) the effect audit (the stacking check, on the decision itself).
        try:
            scene_frame(p, i, d / 2, return_layers=True)
        except Exception:
            pass
        flaws += [f"scene {i + 1}: {f}" for f in _qc_audit(sc, i)]
        # (b) the layer geometry at THREE times (early / mid / late) — the
        # enter is done by the early check (0.5 s in), the label is present
        # by then (it starts at 0.05 s scene 1, TR/2 + 0.15 after that).
        for _tt in (0.5, d / 2, max(0.6, d - 0.4)):
            try:
                _img, _vb, _lb, _ch, _sb = scene_frame(p, i, _tt, return_layers=True)
            except Exception as e:
                flaws.append(f"scene {i + 1}: geometry check failed to run at {_tt:.1f}s: {str(e)[:100]}")
                continue
            _nolabel = sc.get("visual") == "stamp"
            _gf, _gw = _qc_geometry(_vb, _lb, bool(sc.get("source")), expect_label=not _nolabel, src_bb=_sb)
            # A word-timed build-in (counter, donut, stamp...) is EMPTY until
            # its hit word is spoken — that is the design (the visual lands
            # on the word, Blind A6), not a defect. So at the early check
            # (0.5 s), a missing visual is only a flaw if the hit word
            # (pop_t) has already passed. At mid/late it is always a flaw.
            # Likewise, a visual may still be ENTERING at 0.5 s (sliding in)
            # and legitimately touch the frame edge mid-slide — edge
            # clipping only counts at mid/late, when the enter is done.
            if _tt == 0.5:
                _pop = float(sc.get("pop_t", 0.0) or 0.0)
                _is_buildin = (sc.get("_effect_choice") or {}).get("vis") == "build_in"
                if _is_buildin and _pop > 0.5:
                    _gf = [f for f in _gf if "visual missing/empty" not in f]
                _gf = [f for f in _gf if "clipped at frame edge" not in f]
            flaws += [f"scene {i + 1} @{_tt:.1f}s: {f}" for f in _gf]
            warnings += [f"scene {i + 1} @{_tt:.1f}s: {w}" for w in _gw]
        # (d) the typewriter invariant (whole words only, never a partial word).
        if sc.get("visual") == "typewriter_page":
            _txt = "CLASSIFIED: subjects did not notice the swap."
            for _el in (0.3, 0.8, 1.5, 2.5, 4.0):
                _shown = VL.typewriter_shown(_txt, _el)
                if _shown and not _txt.startswith(_shown):
                    flaws.append(f"scene {i + 1}: typewriter shows a partial word at {_el}s: '{_shown}'")
                    break
                if _shown and _shown != _txt and not _txt[len(_shown)] == " ":
                    flaws.append(f"scene {i + 1}: typewriter cuts a word at {_el}s: '{_shown}'")
                    break
        # (e) the fonts (code constants — the fit floors, not a measurement).
        # label() fits to width with a 96 px floor; write_ass uses 96 (en) /
        # 72 (te) captions; the source line is 30 px; in-visual fonts are
        # >= 30 px (720 coords = 44 px frame). If any of these floors were
        # lowered, this check fails loudly.
        try:
            import inspect as _insp
            _src = _insp.getsource(label)
            if "96" not in _src:
                flaws.append(f"scene {i + 1}: label font floor is not 96 px")
        except Exception:
            pass
        scenes_out.append({"idx": i, "passed": not flaws, "flaws": flaws, "warnings": warnings})
        all_flaws += flaws
        all_warnings += warnings
    # (c, continued) the 0.5 s frames: not blank/solid, and never a blank
    # frame (mean brightness change < 1% vs the background for > 200 ms).
    if _fdir and _frames:
        try:
            # Each 0.5 s frame is compared to ITS OWN scene's background
            # (the section palette changes the bg per scene) — a frame whose
            # mean brightness change vs its bg is < 1% is blank (no element).
            # A blank only counts if it PERSISTS (Blind A5: > 200 ms): one
            # dark frame can be a blink (the eyelids transition's closed
            # point is ~60 ms), so a flaw needs TWO consecutive 0.5 s
            # samples both blank/solid/unchanged (>= 0.5 s of blank).
            _bgs = {}
            _prev = None  # (kind, fn) of the previous frame's blank, if any
            for _k, _fn in enumerate(_frames):
                _im = np.asarray(Image.open(os.path.join(_fdir, _fn)).convert("L"), dtype=np.float32)
                _mean, _std = float(_im.mean()), float(_im.std())
                _kind = None
                if _mean < 8:
                    _kind = f"blank/black (mean {_mean:.1f})"
                elif _mean > 245:
                    _kind = f"blown out (mean {_mean:.1f})"
                elif _std < 5:
                    _kind = f"solid colour (std {_std:.1f})"
                else:
                    _t = _k * 0.5
                    _si = max([j for j, _st in enumerate(starts) if _st <= _t] or [0])
                    if _si not in _bgs:
                        _bgs[_si] = np.asarray(background(p["scenes"][_si]["mood"], p.get("look"),
                                                          p["scenes"][_si].get("section")).resize((270, 480)).convert("L"), dtype=np.float32)
                    if float(np.abs(_im - _bgs[_si]).mean()) < 2.55:
                        _kind = f"blank vs background (t={_t:.1f}s, scene {_si + 1}, <1% change)"
                if _kind and _prev and _prev[0] == _kind.split(" (")[0]:
                    all_flaws.append(f"rendered frames {_prev[1]} + {_fn} are {_kind} for >= 0.5 s")
                _prev = (_kind.split(" (")[0], _fn) if _kind else None
        except Exception as e:
            all_flaws.append(f"frame check failed: {str(e)[:100]}")
    result = {"passed": not all_flaws, "scenes": scenes_out, "flaws": all_flaws,
              "warnings": all_warnings}
    _log_rejection(p, result, wd)
    return result


# ---------------- v72: mid-flight amendments ----------------
# While a video renders, the user can send production instructions
# ("real footage kuda include cheyu, sfx use cheyu, transitions
# marchu"). The Worker stores them on the job record; the runner hands
# make_video a provider (pending() / mark(ids, stage)); the checkpoints
# below consume what each stage can still honour. An amendment that
# arrives after the last checkpoint it could use is reported MISSED —
# never silently retargeted to a future video, never faked as applied.
AMENDMENTS = True  # runner capability flag (mirrors the synth_voice gate)

_AMEND_NEG = r"(?:vaddu|off|aapu|stop|remove|teesi|ledhu|ledu|no|without|don'?t)"


def _amend_negated(t, kw):
    return bool(re.search(_AMEND_NEG + r"[^.]{0,24}\b(?:" + kw + r")\b", t)
                or re.search(r"\b(?:" + kw + r")\b[^.]{0,12}" + _AMEND_NEG, t))


def classify_amendment(text):
    """Map one amendment message to the concrete engine effects it asks
    for (PURE — the test suite pins this mapping). Keys: sfx / music /
    captions ("on"|"off"), broll ("on"|"off"), transitions
    ("change"|"off"), style_note (free text the remaining stages keep
    as a production note), content (a point to fold into the narration
    — set only when nothing else matched)."""
    raw = str(text or "").strip()
    t = " " + re.sub(r"\s+", " ", raw.lower()) + " "
    fx = {}
    if re.search(r"\bsfx\b|sound\s*effects?", t):
        fx["sfx"] = "off" if _amend_negated(t, r"sfx|sound\s*effects?") else "on"
    if re.search(r"\bmusic\b|\bbgm\b|background\s*score", t):
        fx["music"] = "off" if _amend_negated(t, r"music|bgm") else "on"
    if re.search(r"captions?|subtitles?", t):
        fx["captions"] = "off" if _amend_negated(t, r"captions?|subtitles?") else "on"
    if re.search(r"footage|b[-\s]?roll|broll|stock\s*(?:video|footage|clips?)", t):
        fx["broll"] = "off" if _amend_negated(t, r"footage|b-?roll|broll|stock") else "on"
    if re.search(r"transitions?", t):
        fx["transitions"] = "off" if _amend_negated(t, r"transitions?") else "change"
    if re.search(r"animations?|visual\s*effects?|\beffects?\b|\bzoom\b|\bstyle\b|\blook\b|graphics?", t):
        fx["style_note"] = raw[:200]
    if not fx:
        fx["content"] = raw[:300]
    return fx


class _AmendBox:
    """Per-render amendment tracker: pulls new items from the provider,
    applies effects stage by stage, and remembers exactly what was
    applied (with the stage) vs what was never consumed (missed)."""

    def __init__(self, provider):
        self.pv = provider
        self.fx = {}            # id -> remaining effects dict
        self.texts = {}         # id -> original text
        self.applied = []       # [{id, text, stage, desc}]
        self._applied_ids = set()

    def _pull(self):
        if not self.pv:
            return
        try:
            items = self.pv.pending()
        except Exception as e:
            print("amendments poll failed:", str(e)[:120])
            return
        for it in items or []:
            i = it.get("id")
            if i is not None and i not in self.fx and i not in self._applied_ids:
                self.fx[i] = classify_amendment(it.get("text", ""))
                self.texts[i] = it.get("text", "")

    def pending_items(self):
        self._pull()
        return [(i, self.texts[i], self.fx[i]) for i in sorted(self.fx)]

    def apply(self, i, stage, desc, keys):
        fx = self.fx.get(i)
        if fx is None:
            return
        for k in keys:
            fx.pop(k, None)
        rec = next((a for a in self.applied if a["id"] == i), None)
        if rec is None:
            self.applied.append({"id": i, "text": self.texts.get(i, ""),
                                 "stage": stage, "desc": desc})
            self._applied_ids.add(i)
        else:
            rec["stage"] = stage
            rec["desc"] = (rec["desc"] + "; " + desc) if rec["desc"] else desc
        if not fx:
            del self.fx[i]
            if self.pv:
                try:
                    self.pv.mark([i], stage)
                except Exception:
                    pass

    def finish(self):
        """Mark every item that got at least one real application (a
        multi-effect item may still hold effects whose stage never came
        due — it WAS partially applied; its desc says with what)."""
        if self.pv:
            for a in self.applied:
                try:
                    self.pv.mark([a["id"]], a["stage"])
                except Exception:
                    pass

    def missed(self):
        self._pull()
        return [self.texts[i] for i in sorted(self.fx)
                if i not in self._applied_ids]


def _repick_transitions(p):
    """A fresh transition set for every boundary (the assembly-stage
    answer to "transitions marchu"): the current names sit in the
    used-set, so every boundary really changes."""
    tag = LOOKS[p.get("look", "A")].get("fx_tag", "calm")
    used = set(p.get("transitions") or [])
    out = []
    for j in range(max(0, len(p["scenes"]) - 1)):
        name = TL.pick_transition(tags={tag}, used=used,
                                  seed=(p.get("seed", 0) + 5000 + j))["name"]
        used.add(name)
        out.append(name)
    p["transitions"] = out
    p["transition_families"] = [TL.family(n) for n in out]
    for i, s in enumerate(p["scenes"]):
        s["transition"] = out[i - 1] if 0 < i <= len(out) else ""


def _transitions_off(p):
    """Simple cuts everywhere: the renderer falls back to a plain
    crossfade for the "crossfade" name — no library transition runs."""
    n = max(0, len(p["scenes"]) - 1)
    p["transitions"] = ["crossfade"] * n
    p["transition_families"] = [TL.family("crossfade")] * n
    for i, s in enumerate(p["scenes"]):
        s["transition"] = "crossfade" if i > 0 else ""


def _silence_wav(path, seconds):
    w = wave.open(path, "w")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(b"\x00\x00" * int(SR * max(0.0, seconds)))
    w.close()


def _amend_checkpoint(box, p, stage, chat=None):
    """Consume the pending amendments THIS stage can honour; return the
    flags this stage decided ({broll, sfx, music, captions}). Stages:
    script (after plan, before voice) -> footage (before the B-roll
    attach) -> audio (before the music/SFX mix) -> assembly (before
    the frame render + caption burn — the last checkpoint)."""
    flags = {}
    if box is None:
        return flags
    for (i, text, fx) in box.pending_items():
        if stage == "script":
            if "content" in fx:
                line = None
                if chat is not None:
                    try:
                        line = str(chat([
                            {"role": "system", "content": "You write narration for a documentary-style video. Reply with ONLY one short sentence (max 15 words), in the video's language, no quotes, no preamble."},
                            {"role": "user", "content": f"Video title: {p.get('title', '')}. Weave this viewer-requested point into the narration as one sentence: {text}"},
                        ]) or "").strip().strip('"')
                    except Exception as e:
                        print("amendment content line failed:", str(e)[:120])
                tgt = next((s for s in reversed(p["scenes"])
                            if s.get("visual") != "stamp_cta"), p["scenes"][-1])
                if line and len(line) <= 200 and "[[" not in line:
                    tgt["vo"] = (str(tgt.get("vo", "")) + " " + line).strip()
                    box.apply(i, "script", "content point narration loki add chesa", ["content"])
                else:
                    p.setdefault("amend_notes", []).append(text)
                    box.apply(i, "script", "note ga add chesa", ["content"])
            if "style_note" in fx:
                p.setdefault("amend_notes", []).append(text)
                box.apply(i, "script", "style note add chesa", ["style_note"])
        elif stage == "footage":
            if "broll" in fx:
                flags["broll"] = fx["broll"]
                box.apply(i, "footage",
                          "B-roll off chesa" if fx["broll"] == "off"
                          else "B-roll on — footage anni scenes ki try chesa", ["broll"])
            if "style_note" in fx:
                p.setdefault("amend_notes", []).append(text)
                box.apply(i, "footage", "style note add chesa", ["style_note"])
        elif stage == "audio":
            if "sfx" in fx:
                flags["sfx"] = fx["sfx"]
                box.apply(i, "audio", "SFX " + fx["sfx"], ["sfx"])
            if "music" in fx:
                flags["music"] = fx["music"]
                box.apply(i, "audio", "Music " + fx["music"], ["music"])
            if "style_note" in fx:
                p.setdefault("amend_notes", []).append(text)
                box.apply(i, "audio", "style note add chesa", ["style_note"])
        elif stage == "assembly":
            if "transitions" in fx:
                if fx["transitions"] == "off":
                    _transitions_off(p)
                    box.apply(i, "assembly", "transitions off (simple cuts)", ["transitions"])
                else:
                    _repick_transitions(p)
                    box.apply(i, "assembly", "transitions marchesa (fresh set)", ["transitions"])
            if "captions" in fx:
                flags["captions"] = fx["captions"]
                box.apply(i, "assembly", "Captions " + fx["captions"], ["captions"])
            if "style_note" in fx:
                p.setdefault("amend_notes", []).append(text)
                box.apply(i, "assembly", "style note add chesa", ["style_note"])
            # "content" at assembly is too late for a short — it stays
            # unconsumed and is reported missed. Never faked as applied.
    return flags


async def make_video(brief, chat, notify=None, workdir=None, recent="", workers=None, recent_styles=None, recent_families=(), preview=False, ref_voice=None, amendments=None, spec=None, cfg=None, footage_pool=None, plan_override=None):
    global _P, W, H
    wd = workdir or tempfile.mkdtemp(prefix="doc_")
    # v75: a caller-supplied workdir is NOT created for us (the default
    # mkdtemp is). long_video's chapter dirs never existed on disk, so
    # the plan.json + vo*.mp3 writes inside died with ENOENT. The dir
    # this function writes into must provably exist from here on.
    os.makedirs(wd, exist_ok=True)
    abox = _AmendBox(amendments) if amendments is not None else None
    aflags = {}
    # v79 (FIX 1/2 + R-P4/R-P5): the render config comes from
    # prompt_spec — spec wins over every engine default. Resolving it
    # can raise SpecImpossible BEFORE anything renders (mail 2b point
    # 5: fail the job loudly, never fall back silently). The frame
    # size is set from the config: the runner process serves one job
    # and every make_video call sets it before drawing, so no stale
    # size is ever used.
    if cfg is None and spec is not None:
        import spec_engine as _se
        cfg = _se.resolve_render_config(spec, "short")
    cfg = cfg or {}
    if cfg.get("width") and cfg.get("height"):
        W, H = int(cfg["width"]), int(cfg["height"])
    if plan_override is not None:
        # v79 (FIX 4): an EDIT render — the saved project plan is used
        # AS SAVED (the edit already changed exactly what was asked;
        # no re-plan, no compliance repair touching other scenes).
        import copy as _copy
        p = _copy.deepcopy(plan_override)
        if spec:
            p["spec"] = spec
        if cfg:
            p["render_config"] = cfg
        for _s in p.get("scenes") or []:
            _s.pop("has_footage", None)  # re-attached fresh below
        print(f"edit render: saved plan, {len(p.get('scenes') or [])} scenes")
    else:
        p = plan(brief, chat, recent, recent_styles, recent_families, spec=spec, cfg=cfg)
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
    # v72 checkpoint 1 (script): content points + style notes fold into
    # the plan BEFORE any voice is synthesised.
    aflags.update(_amend_checkpoint(abox, p, "script", chat))
    # v79 (R-P5): the voice is a renderer PARAMETER from the spec —
    # a named voice or gender in the prompt is used exactly, never
    # re-chosen. The v32 calm swap below is an engine DEFAULT: it
    # applies only when the spec says nothing about the voice.
    if cfg.get("voice_id"):
        voice = cfg["voice_id"]
    elif cfg.get("voice_gender"):
        voice = VOICES.get((p["lang"], cfg["voice_gender"]), VOICES[(p["lang"], "male")])
    else:
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
    p["_voice_used"] = voice
    if notify: await notify(f"Script ready: {p['title']} ({len(p['scenes'])} scenes, {p['lang']}). Voice, animation, music chestunna.")
    gap = 0.45  # v32 (M13, Mark 1a1c1028211d08d1 §1 step 6): 0.45 s breathing room per scene
    # v71: with a saved reference voice, every scene goes through
    # synth_voice (closest voice + pace match); the voice it picks on
    # the first scene carries to the rest. Without one: plain tts().
    for i, s in enumerate(p["scenes"]):
        a = f"{wd}/vo{i}.mp3"
        if ref_voice:
            s["words"], voice = await synth_voice(s["vo"], voice, s["mood"], a, ref_voice)
        elif p.get("voice_rate_add"):
            # v79 (FIX 4): an edit's "slow the voice a little" — a rate
            # offset on every line (the whole voice is the setting the
            # user named). Absent = the exact old call.
            s["words"] = await tts(s["vo"], voice, s["mood"], a,
                                   rate_add=int(p["voice_rate_add"]))
        else:
            s["words"] = await tts(s["vo"], voice, s["mood"], a)
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
    if notify: await notify("Voice ready. Scenes render chestunna (animation + music).")
    # v69: stock B-roll for ~half the scenes (see _attach_broll). Runs
    # BEFORE the pre-render geometry QC so the QC renders the real
    # footage-backed frames. Any failure leaves the plan untouched.
    # v72 checkpoint 2 (footage): a mid-flight B-roll instruction lands
    # here — "off" skips the attach entirely; "on" tries footage on
    # EVERY scene instead of the default ~half.
    aflags.update(_amend_checkpoint(abox, p, "footage"))
    if aflags.get("broll") == "off":
        print("amendments: B-roll OFF — attach skipped")
    else:
        try:
            _attach_broll(p, wd, all_scenes=(aflags.get("broll") == "on"),
                          cfg=cfg, pool=footage_pool)
        except Exception as e:
            print("broll attach failed:", str(e)[:150])
    if p.get("broll_sources") and notify:
        await notify(f"B-roll: {len(p['broll_sources'])} stock footage clips "
                     f"({', '.join(sorted({s['provider'] for s in p['broll_sources']}))}).")
    # v36 (Blind E6 — pre-render geometry QC + auto-fix): BEFORE the chunk
    # render, check every scene's layer geometry at mid-scene. If two layers
    # intersect, scale the visual to 80% and re-check; still hitting, drop
    # the smaller item (the source line). Max 2 tries per scene. A scene
    # that still fails is logged and left for the post-render frame_qc to
    # flag — never silently shipped.
    for _i, _sc in enumerate(p["scenes"]):
        for _try in range(2):
            try:
                _img, _vb, _lb, _ch, _sb = scene_frame(p, _i, float(_sc.get("d", 1.0) or 1.0) / 2, return_layers=True)
                _gf, _gw = _qc_geometry(_vb, _lb, bool(_sc.get("source")), expect_label=_sc.get("visual") != "stamp", src_bb=_sb)
            except Exception as e:
                _gf = [f"geometry check failed: {str(e)[:80]}"]
            if not _gf:
                break
            if _try == 0:
                _sc["_vis_scale"] = 0.8
                print(f"pre-render QC scene {_i + 1}: overlap, scaling visual to 80% ({_gf[0][:80]})")
            else:
                _sc["_drop_source"] = True
                print(f"pre-render QC scene {_i + 1}: still overlapping, dropping the source line ({_gf[0][:80]})")
    # v34 (Hark SFX at word times, item 7): a hit on each scene's hit word
    # + ticks while a phone number is typed. v36 (Blind A6/E1): the SFX
    # lands ON the word — pop_t is the word time minus 0.08 (the visual
    # lands 80 ms before the word), so the hit is at pop_t + 0.08. And a
    # count-up (B2, price) gets ticking SFX while the number counts.
    _hits = []
    for i, s in enumerate(p["scenes"]):
        _word_t = float(s.get("pop_t", 0.0) or 0.0) + 0.08
        _hits.append((starts[i] + _word_t, "hit" if s.get("fact_type") in ("ban", "myth") else "pop"))
        if s.get("fact_type") == "phone":
            for (o, _d, _w) in (s.get("words") or []):
                if any(c.isdigit() for c in _w):
                    _hits.append((starts[i] + float(o), "tick"))
        if s.get("visual") == "counter":
            # Ticks while the counter counts up (from the number word, ~1.2 s).
            _nw = [o for (o, _d, _w) in (s.get("words") or [])
                   if any(c.isdigit() for c in str(_w)) or str(_w).strip().lower() in
                   ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                    "eleven", "twelve", "twenty", "thirty", "fifty", "hundred", "thousand")]
            if _nw:
                _t0 = float(_nw[0])
                for _k in range(10):
                    _hits.append((starts[i] + _t0 + _k * 0.12, "tick"))
    # voice track positioned exactly
    ins = sum([["-i", s["audio"]] for s in p["scenes"]], [])
    fc = "".join(f"[{i}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{i}];" for i, st in enumerate(starts))
    fc += "".join(f"[a{i}]" for i in range(len(starts))) + f"amix=inputs={len(starts)}:normalize=0,apad,atrim=0:{total:.2f}[o]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", fc, "-map", "[o]", "-ar", str(SR), "-ac", "1", f"{wd}/voice.wav"], check=True)
    _payoff = starts[_payoff_idx(p)] if starts else None
    if notify: await notify("Rendering: final video assemble chestunna.")
    # v72 checkpoint 3 (audio): SFX / music instructions land BEFORE
    # the mix. "off" silences the finished track afterwards, so the
    # mix graph (and the loudness design) stays exactly as built.
    aflags.update(_amend_checkpoint(abox, p, "audio"))
    music(total, starts, [s["mood"] for s in p["scenes"]], f"{wd}/music.wav", hits=_hits, payoff=_payoff)
    # v79 (FIX 2): a spec switch ("no music" / "no SFX" in the prompt)
    # outranks the engine default AND a mid-flight amendment — the
    # requirement wins, the default is switched off.
    if aflags.get("music") == "off" or cfg.get("music") is False:
        _silence_wav(f"{wd}/music.wav", total)
    if aflags.get("sfx") == "off" or cfg.get("sfx") is False:
        _silence_wav(f"{wd}/music_sfx.wav", total)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{wd}/voice.wav", "-i", f"{wd}/music.wav", "-i", f"{wd}/music_sfx.wav", "-filter_complex",
                    # v36 (Blind E1): the music is ducked -12 dB under the voice
                    # (volume 0.55 -> 0.45, sidechain threshold 0.02 -> 0.015).
                    "[0:a]asplit[v1][v2];[1:a]volume=0.45[m];[m][v2]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=350[md];"
                    "[v1]highpass=f=70,acompressor=threshold=0.1:ratio=3,volume=1.5[vv];[2:a]volume=0.55[sx];"
                    # v32 (M6, Mark): final loudnorm -14 LUFS (was alimiter)
                    # v79 (R11): true peak -1 dB (was -1.5; the compromise
                    # video peaked at 0.0 and clipped).
                    "[vv][md][sx]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.0:LRA=11[o]", "-map", "[o]", "-ar", str(SR), f"{wd}/mix.wav"], check=True)
    # v72 checkpoint 4 (assembly): transitions + captions land before
    # the frame render and the caption burn — the last point where
    # they can still change THIS video.
    aflags.update(_amend_checkpoint(abox, p, "assembly"))
    # video, parallel chunks
    _P = p; nf = int(total * FPS); k = workers or max(1, min(4, os.cpu_count() or 1))
    cuts = [nf * i // k for i in range(k + 1)]
    jobs = [(cuts[i], cuts[i + 1], f"{wd}/part{i}.mp4") for i in range(k)]
    with mp.get_context("fork").Pool(k) as pool:
        parts = pool.map(_render_chunk, jobs)
    open(f"{wd}/parts.txt", "w").write("".join(f"file '{x}'\n" for x in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{wd}/parts.txt", "-c", "copy", f"{wd}/raw.mp4"], check=True)
    ass = f"{wd}/subs.ass"
    _cap_off = aflags.get("captions") == "off" or cfg.get("captions") is False
    if not _cap_off:
        write_ass(p, ass)
    out = f"{wd}/divya_doc.mp4"
    vf = f"vignette=PI/4.5,eq=contrast=1.06:saturation=1.08" + ("" if _cap_off else f",ass={ass}:fontsdir={FONTS}")
    # v36 (Blind E5/C4): NO temporal noise filter in the vf chain. The old
    # chain had noise=alls=7:allf=t (new random noise every frame) on top of
    # the baked-in 3% film grain + dust + vignette. At CRF 18 the encoder
    # preserves that per-frame noise faithfully: a 10 s clip took >2 min and
    # the 37 s master ballooned past 400 MB and never converged (measured).
    # Without it the same 10 s encodes in 24 s to 3.4 MB. The film look is
    # kept by the baked-in grain (3%, in background()) + the drifting dust +
    # the vignette — the per-frame noise filter was redundant.
    # v36 (Blind E5): the master is CRF 18, yuv420p, +faststart (was CRF 23).
    # No maxrate cap — it would fight CRF 18. Preset is MEDIUM, not slow:
    # preset slow on this grainy content took 20+ min and 400 MB for a 37 s
    # video on this VM (the temporal noise filter + slow motion search on
    # noisy frames) and never converged — medium gives the same CRF 18
    # visual quality (preset is a speed knob at fixed CRF, not a quality
    # spec) at ~4x the speed. The master is archival; the WhatsApp bitrate
    # copy below is the deliverable.
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{wd}/raw.mp4", "-i", f"{wd}/mix.wav", "-vf", vf, "-c:v", "libx264", "-preset", "medium",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out], check=True)
    if os.path.getsize(out) > 15_000_000:  # WhatsApp media limit is 16 MB
        kb = max(600, int(14.2 * 8192 / total) - 140)
        small = f"{wd}/divya_doc_wa.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out, "-c:v", "libx264", "-preset", "medium", "-b:v", f"{kb}k",
                        "-maxrate", f"{int(kb * 1.15)}k", "-bufsize", f"{kb * 2}k", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", small], check=True)
        out = small
    # v36 (Blind E5): the delivery IS the CRF 18 master — no separate CRF 26
    # re-encode any more (the v34 delivery copy is dropped). The >15 MB
    # WhatsApp bitrate copy above is kept (out may already be that copy).
    delivery = out
    # v35 (Ajju: "Divya is not checking at all"): automated frame-level QC
    # AFTER the render. The old team_qc scores the PLAN text and never looks
    # at a rendered frame — that is why stacked effects shipped. frame_qc
    # checks the effect audit + the layer geometry + the encoded frames, per
    # scene. A failing scene is FLAGGED in the returned dict ("qc_passed":
    # False) — never silently shipped as if it passed.
    _fq = frame_qc(p, out, wd)
    print(f"frame_qc: {'PASS' if _fq['passed'] else 'FAIL'} — " + ("; ".join(_fq["flaws"][:6]) if _fq["flaws"] else "all scenes clean") + ((" | warnings: " + "; ".join(_fq["warnings"][:4])) if _fq.get("warnings") else ""))
    # v79 (FIX 5 + Part 4 + R12): the compliance run — plan checks
    # (with timing, after the real durations exist), footage ratio,
    # media checks (ffprobe / -14 LUFS / -1 dBTP / silence), and a
    # per-requirement verdict for every line of prompt_spec. The
    # artifacts (prompt_spec.json, footage.json,
    # compliance_report.json) are written next to the video, and the
    # PROJECT is saved (FIX 4: script, scenes, footage, audio, voice,
    # look, render settings) so a later edit loads THIS state instead
    # of regenerating.
    _report = None
    try:
        import compliance as _comp
        _checks = _comp.audit_plan(p["scenes"], cfg or {"kind": "short"},
                                   topic_text=str(p.get("topic") or "") + " " + str(brief or ""),
                                   measure=lambda txt, size: _label_width(ImageDraw.Draw(Image.new("RGB", (8, 8))), txt) if txt else 0,
                                   have_timing=True)
        _checks += _comp.audit_footage(p["scenes"], cfg or {"kind": "short"})
        # v79 (A1): the frame-fill gate — one mid-scene frame per
        # scene, measured for content coverage. A graphic scene that
        # is mostly empty background FAILS (Ajju's red marks).
        try:
            _frames = []
            for _i, _s in enumerate(p["scenes"]):
                # the closing CTA card is a deliberate card (like a
                # chapter card), not a scene — exempt from the gate.
                if _i == len(p["scenes"]) - 1 and _s.get("visual") == "stamp_cta":
                    continue
                _img = scene_frame(p, _i, max(0.6, float(_s.get("d") or 4) / 2))
                _frames.append((_i + 1, _img, bool(_s.get("has_footage"))))
            _checks += _comp.audit_frame_fill(_frames)
        except Exception as _e:
            print("frame-fill audit failed:", str(_e)[:120])
        _mchecks, _minfo = _comp.audit_media(out, cfg or {"kind": "short"}, spec or [])
        _checks += _mchecks
        _plan_info = {
            "lang": p.get("lang"), "topic": p.get("topic", brief),
            "voice_used": p.get("_voice_used", voice),
            "voice_gender": cfg.get("voice_gender") or p.get("voice"),
            "music_applied": not (cfg.get("music") is False or aflags.get("music") == "off"),
            "sfx_applied": not (cfg.get("sfx") is False or aflags.get("sfx") == "off"),
            "captions_applied": not _cap_off,
            "camera_moves": False,  # v33: the engine's camera is static
            "footage_coverage": (sum(1 for s in p["scenes"] if s.get("has_footage")) / max(1, len(p["scenes"]))),
            "end_card_text": p.get("end_question", ""),
            "chapters_done": None,
        }
        _verdicts = _comp.requirement_verdicts(spec or [], cfg or {}, _plan_info, _minfo)
        _report = _comp.build_report(spec or [], cfg or {}, _checks, _verdicts,
                                     rounds=0, fixes=p.get("plan_fixes") or [])
        p["compliance"] = _report
        for _name, _data in (("prompt_spec.json", spec or []),
                             ("footage.json", p.get("footage") or {}),
                             ("compliance_report.json", _report)):
            try:
                with open(os.path.join(wd, _name), "w", encoding="utf-8") as _f:
                    json.dump(_data, _f, indent=1)
            except OSError:
                pass
        try:
            _proj = {"version": "v79", "brief": brief, "spec": spec or [],
                     "render_config": cfg or {},
                     "plan": {k: v for k, v in p.items()
                              if k not in ("broll", "_footage_pool", "words",
                                           "_saved_footage", "_edit_changed")},
                     "footage": p.get("footage") or {},
                     "voice_used": p.get("_voice_used", voice),
                     "workdir_files": {"video": os.path.basename(out)}}
            with open(os.path.join(wd, "project.json"), "w", encoding="utf-8") as _f:
                json.dump(_proj, _f, indent=1, default=str)
        except Exception as _e:
            print("project save failed:", str(_e)[:120])
        _nf = [c for c in _checks if c["status"] == "FAIL"]
        print(f"compliance: {'PASS' if not _nf else f'{len(_nf)} FAIL'} — "
              + ("; ".join(f"{c['rule']}: {c['detail'][:60]}" for c in _nf[:4]) if _nf else "all checks clean"))
    except Exception as _e:
        print("compliance run failed:", str(_e)[:200])
    # v36 (Blind D): record this video's look so the next video never repeats it.
    record_look(p.get("look"))
    # v72: close the amendment book — everything the engine applied is
    # marked on the job record; the runner re-reads the record for the
    # delivery report (its list also catches post-checkpoint arrivals).
    if abox:
        abox.finish()
    return {"path": out, "delivery_path": delivery, "topic": p.get("topic", brief), "title": p["title"], "lang": p["lang"],
            "script": "\n".join(s["vo"] for s in p["scenes"]), "caption": p.get("caption", ""), "plan": p, "duration": total,
            "broll": p.get("broll_sources", []),
            # v71: honest label of what the voice actually is — set ONLY
            # when a reference sample drove the synth (pace + closest
            # voice). Never worded as a clone.
            "voice_note": VOICE_NOTE_REF if ref_voice else None,
            # v72: which mid-flight instructions were applied (with the
            # stage + what was done) and which missed this video.
            "amendments_applied": abox.applied if abox else [],
            "amendments_missed": abox.missed() if abox else [],
            # v79: the contract artifacts (FIX 1/5) + the saved project
            # (FIX 4) + the compliance report for the delivery line.
            "spec": spec or [], "render_config": cfg or {},
            "compliance": _report, "workdir": wd,
            "frame_qc": _fq, "qc_passed": _fq["passed"]}


# ---------------- v79: edit mode (FIX 4) ----------------
# Blind FIX 4, verbatim intent: "When the user asks to CHANGE
# something in the video just made ('make the title bigger', 'change
# scene 2 to a clock', 'remove the music'), do NOT regenerate the
# whole video. Save each video as a PROJECT (script, scenes,
# footage, audio, voice settings, look, settings). On an edit
# request: load the project, change ONLY what was asked, re-render
# only the changed scenes. Untouched scenes remain exactly the
# same." The engine renders a video as one frame stream, so the
# re-render runs from the SAVED plan with only the named
# scenes/settings changed (plan_override) — untouched scenes'
# plan entries are byte-identical, their footage is re-fetched by
# exact clip id, and the frame test in v79test proves their frames
# come out byte-identical. Full regeneration happens only when the
# user says "make a new one" (a fresh CREATE — handled by the
# brain, never reaching here).

EDIT_VISUAL_WORDS = {"clock": "clock", "watch": "clock",
                     "map": "world_dots", "chart": "graph",
                     "graph": "graph", "donut": "donut",
                     "counter": "counter", "list": "list",
                     "heart": "heart", "scales": "versus",
                     "scale": "versus", "balance": "versus"}


def merge_specs(orig, edit):
    """An edit's requirements replace the original's per TYPE (the
    latest word wins); the rest of the contract still stands.
    Renumbered R1..Rn."""
    etypes = {r.get("type") for r in edit}
    merged = [r for r in orig if r.get("type") not in etypes] + list(edit)
    return [dict(r, id=f"R{i + 1}") for i, r in enumerate(merged)]


def plan_project_edit(project, edit_spec, edit_text):
    """Pure edit planning (FIX 4): returns (plan, cfg, changed, notes)
    — the saved plan/cfg with ONLY the asked changes applied.
    changed = the set of scene numbers whose content changed;
    settings-only edits (music off, title bigger, voice slower)
    change no scene's content."""
    import copy as _copy
    import spec_engine as _se
    plan = _copy.deepcopy(project.get("plan") or {})
    cfg = _copy.deepcopy(project.get("render_config") or {})
    low = str(edit_text or "").lower()
    changed, notes = set(), []
    kind = cfg.get("kind", "short")
    try:
        ecfg = _se.resolve_render_config(edit_spec, kind)
    except Exception:
        ecfg = {}
    etypes = {r.get("type") for r in edit_spec}
    if "music" in etypes:
        cfg["music"] = ecfg.get("music", cfg.get("music"))
        notes.append(f"music {'OFF' if cfg['music'] is False else 'ON'}")
    if "sfx" in etypes:
        cfg["sfx"] = ecfg.get("sfx", cfg.get("sfx"))
        notes.append(f"sfx {'OFF' if cfg['sfx'] is False else 'ON'}")
    if "captions" in etypes:
        cfg["captions"] = ecfg.get("captions", cfg.get("captions"))
        cfg["caption_spec"] = ecfg.get("caption_spec", cfg.get("caption_spec"))
        notes.append("captions updated")
    if "colour" in etypes and ecfg.get("accent"):
        cfg["accent"] = ecfg["accent"]
        plan["accent"] = ecfg["accent"]
        notes.append("colour updated")
    if "aspect_ratio" in etypes:
        cfg["width"], cfg["height"] = ecfg["width"], ecfg["height"]
        notes.append(f"size -> {cfg['width']}x{cfg['height']}")
    if "end_card" in etypes:
        cfg["end_card"] = ecfg.get("end_card")
        if ecfg.get("end_card"):
            plan["end_question"] = ecfg["end_card"]
        notes.append("end card updated")
    if "language" in etypes and ecfg.get("lang"):
        cfg["lang"] = ecfg["lang"]
        plan["lang"] = ecfg["lang"]
        notes.append(f"language -> {ecfg['lang']}")
    if "voice" in etypes:
        if ecfg.get("voice_id"):
            cfg["voice_id"] = ecfg["voice_id"]
        if ecfg.get("voice_gender"):
            cfg["voice_gender"] = ecfg["voice_gender"]
        notes.append("voice updated")
    scenes = plan.get("scenes") or []
    for m in re.finditer(
            r"scene\s*(\d+)\s*(?:to|as|with|into)\s+(?:a\s+|an\s+)?([a-z]+)",
            low):
        n, word = int(m.group(1)), m.group(2)
        vis = EDIT_VISUAL_WORDS.get(word)
        if vis and 1 <= n <= len(scenes) and vis in C.VISUALS:
            scenes[n - 1]["visual"] = vis
            scenes[n - 1]["why"] = f"changed to a {word} by the owner's edit"
            changed.add(n)
            notes.append(f"scene {n} visual -> {word}")
        else:
            notes.append(f"scene {n}: could not change to '{word}' "
                         f"(unknown visual or no such scene)")
    if re.search(r"title\s+(bigger|larger|big)\b|bigger\s+title|"
                 r"make\s+the\s+title\s+bigger", low):
        plan["title_scale"] = round(float(plan.get("title_scale") or 1.0) * 1.3, 3)
        notes.append(f"title scale -> {plan['title_scale']}")
    if re.search(r"slow\s+(?:down\s+)?(?:the\s+)?voice|voice\s+"
                 r"(?:a\s+bit\s+|a\s+little\s+)?slow", low):
        plan["voice_rate_add"] = int(plan.get("voice_rate_add") or 0) - 10
        notes.append("voice slowed by 10%")
    saved = {}
    for c in (project.get("footage") or {}).get("clips") or []:
        if isinstance(c, dict) and c.get("scene") is not None:
            saved.setdefault(c["scene"], c)
    if saved:
        plan["_saved_footage"] = saved
    plan["_edit_changed"] = changed
    return plan, cfg, changed, notes


async def apply_project_edit(project, edit_text, chat, workdir=None,
                             notify=None):
    """FIX 4 entry point: extract the edit's own spec, plan the edit
    against the saved project, and re-render from the saved plan.
    Returns make_video's result dict plus res['edit'] = {changed
    scenes, notes, the edit's spec}."""
    import spec_engine as _se
    edit_spec = _se.extract_spec(edit_text, chat=chat)
    plan2, cfg2, changed, notes = plan_project_edit(project, edit_spec,
                                                    edit_text)
    merged = merge_specs(project.get("spec") or [], edit_spec)
    res = await make_video(project.get("brief") or "", chat,
                           notify=notify, workdir=workdir, spec=merged,
                           cfg=cfg2, plan_override=plan2)
    res["edit"] = {"changed_scenes": sorted(changed), "notes": notes,
                   "edit_spec": edit_spec}
    return res
