"""spec_engine.py — Julie v79: the prompt is a CONTRACT (Blind/Hark mails
2 + 2b, FIX 1/2/3/6 + R-P1..R-P7).

FIX 1: before anything else, the user's prompt is converted into a list
of small, checkable requirements (prompt_spec.json) — every item keeps
the user's exact words in "quote". Types: duration, language, voice,
topic, script, scene_order, scene_content, text_on_screen, colour,
font, footage, effects, transitions, music, sfx, captions, speed,
aspect_ratio, end_card, chapters, structure, exclude ("don't / no /
remove" items are requirements too).

FIX 2 priority order (enforced by resolve_render_config): safety >
prompt_spec > previous video state (edit mode) > Julie defaults. A
default that conflicts with a requirement is switched OFF, never the
other way round.

R-P3/R-P4/R-P5: format, size, duration, voice, caption spec, palette,
music and chapter structure come from the spec as renderer parameters.
Portrait 1080x1920 is the default ONLY when the prompt says nothing
(shorts); a long video is 1920x1080 landscape unless the prompt says
portrait (mail 3, R9). A requirement the engine cannot do raises
SpecImpossible BEFORE render — the job fails loudly with the reason
(mail 2b point 5); it never falls back silently.

Extraction is deterministic-first (regex over the user's exact words
for every render-critical parameter, so "no music" can never be lost
by an LLM summary) plus one LLM pass for the remaining requirement
kinds, merged with a read-back coverage check (mail 2b point 1: count
the requirements, re-read the prompt, look for anything not in the
list — numbers and negations must appear in some quote).

v79.1: "<Language> voice" ("Telugu voice", "voice in Hindi",
"Telugu lo voice") is a voice-LANGUAGE requirement that routes to the
engine's per-language edge-tts catalogue (LANGUAGE_VOICES) — it is
NOT a named voice. Only a genuinely unroutable ask (a language with
no TTS route, a named voice the engine lacks) stops upfront.
"""

import json
import re

# ------------------------------------------------------------------
# Capability list (mail 2b point 3): what the engine can actually do.
# The upfront check compares every requirement against this list.
# ------------------------------------------------------------------
MAX_SIDE = 1920
MIN_SIDE = 360
MAX_DURATION_S = 3600          # 60 minutes (long pipeline ceiling)
MAX_CHAPTERS = 30
LANGUAGES = {"en": ("english",), "te": ("telugu",), "hi": ("hindi",)}
_LANG_NAME_TO_CODE = {name: code for code, names in LANGUAGES.items()
                      for name in names}
_LANG_DISPLAY = {code: names[0].capitalize()
                 for code, names in LANGUAGES.items()}
# Per-language TTS routes (edge-tts) — mirrors doc.VOICES, the
# engine's actual synthesis catalogue (v79.1). A "<Language> voice"
# requirement resolves through this map (gender from the prompt when
# stated, DEFAULT_VOICE_GENDER otherwise, and the choice is recorded
# in cfg["voice_choice"]). doc.VOICES' ("en", "male_calm") mood
# variant is an engine default, not a prompt route, so it is absent.
LANGUAGE_VOICES = {
    "en": {"male": "en-US-AndrewMultilingualNeural",
           "female": "en-US-AvaMultilingualNeural"},
    "te": {"male": "te-IN-MohanNeural", "female": "te-IN-ShrutiNeural"},
    "hi": {"male": "hi-IN-MadhurNeural", "female": "hi-IN-SwaraNeural"},
}
# doc.py's own default when a plan says nothing about gender.
DEFAULT_VOICE_GENDER = "male"
# edge-tts voices the engine will pass through: the doc.VOICES catalogue
# plus any well-formed <lang>-<REGION>-<Name>Neural id (R-P5: a voice
# named in the prompt is a renderer parameter, never re-chosen).
VOICE_ID_RE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural$")
FONTS = {"montserrat", "anton", "noto sans telugu", "dejavu", "bebas"}
COLOURS = {
    "red": (230, 57, 70), "blue": (80, 140, 255), "green": (60, 180, 120),
    "amber": (255, 183, 3), "yellow": (250, 205, 60), "orange": (255, 140, 0),
    "white": (240, 240, 240), "black": (10, 10, 12), "pink": (255, 120, 180),
    "purple": (160, 110, 255), "teal": (40, 190, 180), "gold": (255, 190, 40),
}

SPEC_TYPES = ["duration", "language", "voice", "topic", "script",
              "scene_order", "scene_content", "text_on_screen", "colour",
              "font", "footage", "effects", "transitions", "music", "sfx",
              "captions", "speed", "aspect_ratio", "end_card", "chapters",
              "structure", "exclude"]


class SpecImpossible(Exception):
    """A prompt requirement the engine cannot do. Carries the
    requirement id + the one-line reason + the closest alternative —
    the upfront-honesty line (FIX 6 / mail 2b point 3)."""

    def __init__(self, req_id, reason, alternative=""):
        super().__init__(reason)
        self.req_id = req_id
        self.reason = reason
        self.alternative = alternative


# ------------------------------------------------------------------
# FIX 1 — deterministic extraction over the user's exact words
# ------------------------------------------------------------------
def _req(rtype, value, quote):
    return {"type": rtype, "value": value, "quote": quote.strip()}


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", text or "") if s.strip()]


def _parse_voice_language(value):
    """v79.1 classification: if a voice VALUE is really a voice-
    LANGUAGE ask — "Telugu", "Telugu voice", "female Telugu voice",
    "Telugu female", "voice in Hindi", "Telugu lo voice" — return
    (lang_code, gender|None). Anything else returns None: a named
    voice ("Rowan Telugu HD", "en-US-AndrewNeural") or a description
    ("a celebrity voice") is not a language, and the resolver treats
    it as a named voice (passing it through when it is a real
    edge-tts id, stopping upfront when the engine lacks it)."""
    v = " " + re.sub(r"[^a-z ]", " ", str(value).lower()) + " "
    gender = None
    for g in ("female", "male"):
        if f" {g} " in v:
            gender = g
            v = v.replace(f" {g} ", " ")
    v = re.sub(r"\b(voice|in|lo|a|an|the)\b", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    code = _LANG_NAME_TO_CODE.get(v)
    return (code, gender) if code else None


# Words that, sitting directly before "voice", do NOT name a voice:
# "slow the voice" is an edit instruction, "Rowan Telugu HD voice"
# is a named voice whose trailing word is a quality tag (the LLM
# pass carries the full name as the value in that case).
_VOICE_STOPWORDS = {"the", "a", "an", "my", "your", "his", "her",
                    "their", "our", "this", "that", "same", "own",
                    "hd", "uhd"}


def extract_deterministic(text):
    """Regex pass: every render-critical parameter that must never be
    lost — durations, sizes/aspect, negations (music/sfx/zoom/
    graphics/captions), language, voice, end card, chapters, colour,
    footage-only. Returns a list of requirement dicts (ids assigned
    later, in prompt order)."""
    text = str(text or "")
    low = text.lower()
    out = []

    def grab(rtype, value, m):
        if m:
            out.append(_req(rtype, value, m.group(0)))

    # duration: "30 seconds", "14 minutes", "1 min", "90s"
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|s)\b", low)
    if m:
        grab("duration", f"{m.group(1)}s", m)
    else:
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*(minutes?|mins?|mints)\b", low)
        if m:
            grab("duration", f"{int(float(m.group(1)) * 60)}s", m)

    # exact size: 1920x1080 / 1280x720
    m = re.search(r"\b(1920|1280|1080|720|854|640)\s*x\s*(1920|1280|1080|720|854|640)\b", low)
    if m:
        grab("aspect_ratio", f"{m.group(1)}x{m.group(2)}", m)
    else:
        m = re.search(r"\b16\s*[:x]\s*9\b|\blandscape\b", low)
        if m:
            grab("aspect_ratio", "16:9", m)
        else:
            m = re.search(r"\b9\s*[:x]\s*16\b|\bportrait\b|\bvertical\b", low)
            if m:
                grab("aspect_ratio", "9:16", m)

    # negations -> exclude / off switches (FIX 1: "don't" items are
    # requirements too)
    for pat, rtype, value in (
            (r"\bno\s+music\b|\bwithout\s+music\b|\bdon'?t\s+(?:add|use)\s+music\b|\bremove\s+(?:the\s+)?music\b", "music", "music OFF"),
            (r"\bno\s+(?:sfx|sound\s+effects)\b|\bwithout\s+(?:sfx|sound\s+effects)\b|\bremove\s+(?:the\s+)?(?:sfx|sound\s+effects)\b", "sfx", "sfx OFF"),
            (r"\bno\s+zoom\b|\bwithout\s+zoom\b", "exclude", "no zoom"),
            (r"\bno\s+graphics\b|\bno\s+animations?\b", "exclude", "no graphics"),
            (r"\bno\s+captions\b|\bwithout\s+captions\b|\bno\s+subtitles\b|\bremove\s+(?:the\s+)?captions\b", "captions", "captions OFF")):
        m = re.search(pat, low)
        grab(rtype, value, m)

    # footage-only / only real footage
    m = re.search(r"\bonly\s+(?:real\s+)?footage\b|\buse\s+only\s+(?:real\s+)?footage\b|\breal\s+footage\s+only\b", low)
    if m:
        grab("footage", "only real footage", m)

    # language
    for code, names in LANGUAGES.items():
        m = re.search(r"\b(" + "|".join(names) + r")\b", low)
        if m:
            grab("language", code, m)
            break

    # voice (v79.1 classification, in order): a named edge-tts id;
    # a voice-LANGUAGE ask ("Telugu voice", "voice in Hindi",
    # "Telugu lo voice", gender optional) — a language requirement
    # with language=<code> (+ gender when stated), NOT a named voice;
    # a bare gender ask; or any other "<word> voice" naming, kept
    # verbatim so resolve_render_config stops it upfront when the
    # engine truly lacks that voice — never silently dropped.
    m = re.search(r"\b[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural\b", text)
    if m:
        grab("voice", m.group(0), m)
    else:
        lang_alt = "|".join(_LANG_NAME_TO_CODE)
        m = (re.search(r"\b(?:(?:female|male)\s+)?(?:" + lang_alt + r")"
                       r"(?:\s+(?:female|male))?\s+voice\b", low)
             or re.search(r"\bvoice\s+in\s+(?:" + lang_alt + r")\b", low)
             or re.search(r"\b(?:" + lang_alt + r")\s+lo\s+voice\b", low))
        if m:
            code, gender = _parse_voice_language(m.group(0))
            req = _req("voice", _LANG_DISPLAY[code], m.group(0))
            req["language"] = code
            if gender:
                req["gender"] = gender
            out.append(req)
        else:
            m = re.search(r"\b(female|male)\s+voice\b|\bvoice\s*:\s*(female|male)\b", low)
            if m:
                grab("voice", m.group(1) or m.group(2), m)
            else:
                m = re.search(r"\b([a-z]+)\s+voice\b", low)
                if m and m.group(1) not in _VOICE_STOPWORDS:
                    grab("voice", m.group(1), m)

    # chapters: "8 chapters", "8-9 chapters"
    m = re.search(r"\b(\d+)\s*(?:-\s*\d+\s*)?chapters?\b", low)
    if m:
        grab("chapters", m.group(1), m)

    # end card: "end with X" / "ending with X"
    m = re.search(r"\bend(?:ing|s)?\s+with\s+(.+?)(?:[.!]|$)", text, re.I)
    if m and len(m.group(1)) <= 80:
        grab("end_card", m.group(1).strip(), m)

    # colour accent: "<colour> colour/color" or "in red"
    m = re.search(r"\b(" + "|".join(COLOURS) + r")\s+(?:colour|color|accent)\b", low)
    if m:
        grab("colour", f"{m.group(1)} accent", m)

    # captions style asks: "big white captions", "big captions"
    m = re.search(r"\bbig\s+(?:white\s+)?captions\b|\bbig\s+white\s+captions\b", low)
    if m:
        grab("captions", "big white captions", m)

    # FIX 1: the quote is the user's EXACT words — the matches above
    # ran over the lowercased text, so restore each quote's original
    # casing from the prompt itself.
    for it in out:
        m2 = re.search(re.escape(it["quote"]), text, re.I)
        if m2:
            it["quote"] = m2.group(0)
    return out


_EXTRACT_SYSTEM = (
    "You convert a user's video prompt into a requirements list. "
    "Output STRICT JSON only: a list of {\"type\": ..., \"value\": ..., "
    "\"quote\": ...}. Types: " + ", ".join(SPEC_TYPES) + ". "
    "One item per requirement: every number, size, colour, font, voice, "
    "caption rule, structure rule, scene-content ask and every "
    "\"don't / no / remove\" (type \"exclude\") becomes its own item, "
    "with the user's EXACT words in \"quote\". Do not invent "
    "requirements that are not in the prompt."
)


def extract_spec(prompt_text, chat=None):
    """FIX 1 + mail 2b point 1: prompt -> prompt_spec list with ids
    R1..Rn. Deterministic items (render-critical) are extracted from
    the user's exact words first; the LLM pass (when a chat callable
    is given) adds the rest; a read-back coverage check then verifies
    every number and negation in the prompt appears in some quote —
    uncovered fragments ride along in spec[-1] metadata via the
    returned (spec, gaps) only when called through extract_spec_full.
    This function returns just the spec list."""
    spec, _gaps = extract_spec_full(prompt_text, chat)
    return spec


def extract_spec_full(prompt_text, chat=None):
    """Returns (spec, coverage_gaps)."""
    text = str(prompt_text or "").strip()
    det = extract_deterministic(text)
    items = list(det)
    seen = {(i["type"], i["value"].lower()) for i in items}

    if chat is not None and text:
        try:
            raw = chat([{"role": "system", "content": _EXTRACT_SYSTEM},
                        {"role": "user", "content": text}])
            llm_items = json.loads(re.search(r"\[[\s\S]*\]", raw).group(0))
            for it in llm_items:
                if not isinstance(it, dict):
                    continue
                t = str(it.get("type", "")).strip().lower()
                v = str(it.get("value", "")).strip()
                q = str(it.get("quote", "")).strip()
                if t not in SPEC_TYPES or not v or not q:
                    continue
                if q not in text and q.lower() not in text.lower():
                    continue  # a quote that is not the user's words is not evidence
                item = {"type": t, "value": v, "quote": q}
                if t == "voice":
                    # v79.1: an LLM "voice: Telugu" item is a voice-
                    # LANGUAGE ask, not a named voice — normalise it
                    # to the same shape the deterministic pass emits
                    # (this exact shape stopped a valid job in
                    # production before the fix), BEFORE the dedupe
                    # below so it merges with the deterministic item
                    # instead of duplicating it.
                    parsed = _parse_voice_language(v)
                    if parsed:
                        item["value"] = _LANG_DISPLAY[parsed[0]]
                        item["language"] = parsed[0]
                        if parsed[1]:
                            item["gender"] = parsed[1]
                key = (t, item["value"].lower())
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
        except Exception:
            pass  # the deterministic pass stands on its own

    # Order by where the quote first appears in the prompt (the FIX 1
    # example is in prompt order); unknown positions go last, stable.
    low = text.lower()
    def _pos(it):
        i = low.find(it["quote"].lower()[:40])
        return i if i >= 0 else len(low) + 1
    items.sort(key=_pos)
    spec = [{"id": f"R{i + 1}", **it} for i, it in enumerate(items)]

    # Read-back coverage (mail 2b point 1): every number token and
    # every negation in the prompt must appear in some quote.
    quotes = " || ".join(i["quote"].lower() for i in spec)
    gaps = []
    for tok in set(re.findall(r"\d+(?:\.\d+)?", text)):
        if tok not in quotes:
            gaps.append(f"number {tok} not covered")
    for neg in ("no ", "don't", "dont", "never", "remove", "without"):
        if neg in low and neg.strip() not in quotes:
            # only a gap if NO exclude/off item exists at all
            if not any(i["type"] == "exclude" or "OFF" in i["value"] for i in spec):
                gaps.append(f"negation '{neg.strip()}' not covered")
    return spec, gaps


# ------------------------------------------------------------------
# FIX 2 / R-P4 / R-P5 — spec -> renderer parameters.
# ------------------------------------------------------------------
def _find(spec, rtype):
    return [r for r in spec if r.get("type") == rtype]


def spec_duration_s(spec):
    for r in _find(spec, "duration"):
        m = re.match(r"\s*(\d+(?:\.\d+)?)s\s*$", str(r["value"]))
        if m:
            return float(m.group(1))
    return None


def resolve_render_config(spec, kind="short"):
    """The render configuration for a job: every field comes from the
    prompt_spec when the spec speaks (FIX 2: the requirement wins and
    the default is switched off); Julie's defaults apply only where
    the spec is silent. kind is "short" or "long" (the caller's
    routing). Raises SpecImpossible for a stated requirement the
    engine cannot do — the caller fails the job loudly BEFORE render
    (mail 2b point 5); there is no silent fallback."""
    spec = spec or []
    cfg = {"kind": kind, "spec_ids": {}}

    # --- size / aspect (R-P4) ---
    w = h = None
    for r in _find(spec, "aspect_ratio"):
        v = str(r["value"]).lower()
        m = re.match(r"\s*(\d+)\s*x\s*(\d+)\s*$", v)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
        elif v == "16:9":
            w, h = 1920, 1080
        elif v == "9:16":
            w, h = 1080, 1920
        cfg["spec_ids"]["aspect_ratio"] = r["id"]
    if w is None:
        # Defaults ONLY where the spec is silent: short = portrait
        # (R-P4), long = landscape 1920x1080 (mail 3 R9).
        w, h = (1920, 1080) if kind == "long" else (1080, 1920)
    if w > MAX_SIDE or h > MAX_SIDE or w < MIN_SIDE or h < MIN_SIDE:
        raise SpecImpossible(cfg["spec_ids"].get("aspect_ratio", ""),
                             f"size {w}x{h} is outside what the engine renders "
                             f"({MIN_SIDE}..{MAX_SIDE} px per side)",
                             "1920x1080 or 1080x1920")
    cfg["width"], cfg["height"] = w, h
    cfg["orientation"] = "portrait" if h >= w else "landscape"

    # --- duration ---
    dur = spec_duration_s(spec)
    if dur is not None:
        cfg["spec_ids"]["duration"] = _find(spec, "duration")[0]["id"]
        if dur > MAX_DURATION_S:
            raise SpecImpossible(cfg["spec_ids"]["duration"],
                                 f"duration {int(dur)}s is over the {MAX_DURATION_S}s engine ceiling",
                                 "up to 60 minutes")
    cfg["duration_s"] = dur

    # --- language + voice (R-P5: parameters, never re-chosen) ---
    lang = None
    for r in _find(spec, "language"):
        lang = str(r["value"]).lower()
        cfg["spec_ids"]["language"] = r["id"]
    cfg["lang"] = lang
    # v79.1: classify every voice requirement before deciding —
    # a named edge-tts id (passes through exactly), a voice-LANGUAGE
    # ask (routes via LANGUAGE_VOICES), a bare gender, or a genuinely
    # unknown naming (stops upfront). A language ask stated alongside
    # a named voice does not override the named voice.
    voice_id = voice_gender = None
    voice_choice = None
    named_voice = lang_voice = gender_ask = None
    for r in _find(spec, "voice"):
        v = str(r["value"]).strip()
        cfg["spec_ids"]["voice"] = r["id"]
        if VOICE_ID_RE.match(v):
            named_voice = v
            continue
        code = r.get("language")
        if code not in LANGUAGE_VOICES:
            code = _LANG_NAME_TO_CODE.get(str(code).lower()) if code else None
        parsed = _parse_voice_language(v)
        if parsed:
            code = code or parsed[0]
        if code:
            lang_voice = (code, r.get("gender") or (parsed[1] if parsed else None))
            continue
        if v.lower() in ("male", "female"):
            gender_ask = v.lower()
            continue
        if v:
            raise SpecImpossible(r["id"],
                                 f"voice '{v}' is not a voice the engine has",
                                 "a named edge-tts voice (e.g. en-US-AndrewNeural), "
                                 "male or female, or a voice language the engine "
                                 "speaks (English, Telugu, Hindi)")
    if named_voice:
        voice_id = named_voice
    elif lang_voice:
        code, gender = lang_voice
        use_gender = gender or gender_ask or DEFAULT_VOICE_GENDER
        voice_id = LANGUAGE_VOICES[code][use_gender]
        voice_gender = use_gender
        # Record the routing choice for the compliance artifacts
        # (R-P7: the delivery says what was actually used, and why).
        voice_choice = {"via": "language", "language": code,
                        "gender": use_gender,
                        "gender_source": "prompt" if (gender or gender_ask) else "default",
                        "voice_id": voice_id}
        if lang is None:
            # "Telugu voice" also fixes the narration language when
            # no separate language requirement spoke.
            lang = code
            cfg["lang"] = code
    elif gender_ask:
        voice_gender = gender_ask
    cfg["voice_id"], cfg["voice_gender"] = voice_id, voice_gender
    cfg["voice_choice"] = voice_choice

    # --- music / sfx / captions switches (FIX 2: a conflicting
    # default is switched off) ---
    cfg["music"] = True
    cfg["sfx"] = True
    cfg["captions"] = True
    cfg["caption_spec"] = {}
    for r in _find(spec, "music"):
        if "off" in str(r["value"]).lower():
            cfg["music"] = False
            cfg["spec_ids"]["music"] = r["id"]
    for r in _find(spec, "sfx"):
        if "off" in str(r["value"]).lower():
            cfg["sfx"] = False
            cfg["spec_ids"]["sfx"] = r["id"]
    for r in _find(spec, "captions"):
        v = str(r["value"]).lower()
        if "off" in v:
            cfg["captions"] = False
            cfg["spec_ids"]["captions"] = r["id"]
        else:
            if "big" in v:
                cfg["caption_spec"]["size_scale"] = 1.35
            if "white" in v:
                cfg["caption_spec"]["colour"] = (240, 240, 240)
            cfg["spec_ids"]["captions"] = r["id"]
    # caption chunk bounds: long R7 = 4-7 words; short mail 1 = 2-4.
    cfg["caption_spec"].setdefault(
        "words", (4, 7) if kind == "long" else (2, 4))

    # --- excludes (no zoom / no graphics ...) ---
    excludes = set()
    for r in _find(spec, "exclude"):
        v = str(r["value"]).lower()
        if "zoom" in v:
            excludes.add("zoom")
        if "graphic" in v or "animation" in v:
            excludes.add("graphics")
        cfg["spec_ids"].setdefault("exclude", r["id"])
    cfg["excludes"] = sorted(excludes)
    cfg["no_graphics"] = "graphics" in excludes or any(
        "only real footage" in str(r["value"]).lower()
        for r in _find(spec, "footage"))
    cfg["footage_only"] = cfg["no_graphics"]

    # --- colour accent ---
    cfg["accent"] = None
    for r in _find(spec, "colour"):
        v = str(r["value"]).lower()
        for name, rgb in COLOURS.items():
            if name in v:
                cfg["accent"] = list(rgb)
                cfg["spec_ids"]["colour"] = r["id"]
                break

    # --- font ---
    cfg["font"] = None
    for r in _find(spec, "font"):
        v = str(r["value"]).lower().strip()
        if v not in FONTS:
            raise SpecImpossible(r["id"], f"font '{v}' is not installed in the engine",
                                 "Montserrat, Anton, Bebas or Noto Sans Telugu")
        cfg["font"] = v
        cfg["spec_ids"]["font"] = r["id"]

    # --- chapters ---
    cfg["chapters"] = None
    for r in _find(spec, "chapters"):
        m = re.search(r"\d+", str(r["value"]))
        if m:
            n = int(m.group(0))
            if n > MAX_CHAPTERS:
                raise SpecImpossible(r["id"], f"{n} chapters is over the {MAX_CHAPTERS}-chapter ceiling",
                                     f"up to {MAX_CHAPTERS} chapters")
            cfg["chapters"] = n
            cfg["spec_ids"]["chapters"] = r["id"]

    # --- end card ---
    cfg["end_card"] = None
    for r in _find(spec, "end_card"):
        cfg["end_card"] = str(r["value"])
        cfg["spec_ids"]["end_card"] = r["id"]

    return cfg


# ------------------------------------------------------------------
# Mail 2b point 3 — the upfront capability check.
# ------------------------------------------------------------------
def capability_check(spec, kind="short", footage_available=True):
    """Compare every requirement against the capability list BEFORE
    render. Returns a list of problems: [{id, reason, alternative}].
    An empty list means every requirement can be attempted. Config
    resolution failures are problems too (never a silent fallback)."""
    problems = []
    try:
        resolve_render_config(spec, kind)
    except SpecImpossible as e:
        problems.append({"id": e.req_id, "reason": e.reason,
                         "alternative": e.alternative})
    for r in spec or []:
        if r.get("type") == "footage" and not footage_available:
            problems.append({
                "id": r["id"],
                "reason": "real footage needs a stock-footage key (Pexels/Pixabay) "
                          "and none is available to the engine right now",
                "alternative": "an animated-graphics video, or footage once a key is set up"})
    return problems


def upfront_line(problems):
    """FIX 6 / mail 2b point 3: the one-line upfront message."""
    if not problems:
        return ""
    p = problems[0]
    line = f"I can do everything except {p['reason']}."
    if p.get("alternative"):
        line += f" I can do {p['alternative']} instead. Shall I go ahead?"
    return line
