"""Divya: make a faceless 9:16 Telugu explainer Short from ONLY a topic/brief (no raw footage).
Pipeline: LLM plan (Telugu VO lines + 1-3 word English labels + visual type) -> edge-tts Telugu voice
-> PIL animated scenes (dark bg, red accent, mono font, animated objects) -> ASS Telugu captions (libass shapes Telugu)
-> ffmpeg mux. Free, CPU only."""
import asyncio, json, math, os, random, re, subprocess, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
BG, RED, WHITE, GREEN, YEL, GREY = (12, 12, 14), (235, 50, 60), (240, 240, 240), (60, 210, 120), (250, 205, 60), (90, 90, 100)
VISUALS = ["counter", "bar", "chat", "check", "warning", "graph", "clock", "heart", "battery", "calendar", "list", "versus",
           "dot_grid", "donut", "gauge", "toggle", "phone_buzz", "stick_figure", "quote_card", "arrows_steps",
           "checklist", "document", "polaroid", "icon_row", "bar_compare", "strike", "curve",
           # v34 (Hark engine): four/question/card/watch + stamp/stamp_cta.
           "four", "question", "card", "watch", "stamp", "stamp_cta"]
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
VOICES = {"male": "te-IN-MohanNeural", "female": "te-IN-ShrutiNeural"}
# Engine switch for create mode: env DIVYA_ENGINE=v3 -> doc3.py (engine v3), anything else -> doc.py (v2, default).
ENGINE = os.environ.get("DIVYA_ENGINE", "v2").strip().lower() or "v2"


def engine_module():
    import importlib
    return importlib.import_module("doc3" if ENGINE == "v3" else "doc")


def font(size, bold=True):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf",
              "/workspace/work/explainer/fonts/DejaVuSansMono-Bold.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


PLAN_PROMPT = """You plan a faceless Telugu YouTube Short / Instagram Reel (9:16, 25-45 seconds) from a topic.
Return ONLY JSON: {"title": "<2-5 word English banner, caps>", "voice": "male|female",
"scenes": [{"vo": "<one Telugu voice-over sentence in Telugu script, natural spoken Telugu, max 18 words>",
"label": "<1-3 word ENGLISH punch label, caps>", "visual": "<one of %s>", "value": "<short number or word for the visual, e.g. 80%%, 7, NO>"}]}
Rules: 6-9 scenes. Scene 1 = strong hook question. Last scene = takeaway + follow call. Each visual must literally show the line's idea
(battery for energy, chat for messages/relationships, graph for growth, clock for time, calendar for days, warning for mistakes,
check for good habits, versus for comparisons, counter for numbers, list for steps, heart for love/health, bar for progress,
dot_grid for a percentage of people, donut for a percentage ring, gauge for a level/meter, toggle for on/off, phone_buzz for phone
notifications, stick_figure for a person/feeling, quote_card for a quote, arrows_steps for a process, checklist for a to-do,
document for a report/study, polaroid for a memory/photo, icon_row for a set of items, bar_compare for two numbers compared,
strike for a myth/lie to cross out, curve for exponential growth (1%% better every day),
four for one-in-N people, question for a big question hook, card for a phone number or helpline,
watch for a stopwatch or rate, stamp for a ban or verdict, stamp_cta for the final call to action.
If the owner did not give a clear topic (e.g. "nuvve select chesko", "any topic", empty), YOU pick one fresh, high-retention
topic for a Telugu faceless channel (psychology, relationships, money habits, health hacks, motivation, tech tips, facts) — avoid
these recent topics: {recent}. Also add "topic": "<the topic you chose>" to the JSON.
Topic/brief from owner: """ % VISUALS


def target_seconds(brief):
    # v24: the brief carries "FINAL VIDEO LENGTH: exactly N seconds (±2s)"
    # (v23 startCreate). Parse it so the plan is built to fit — the LLM ignored
    # the text constraint and made 44s for a 30s request (video 5).
    m = re.search(r"FINAL VIDEO LENGTH:\s*exactly\s*(\d+)\s*seconds", brief or "")
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*min", brief or "")
    if m:
        return int(m.group(1)) * 60
    m = re.search(r"(\d+)\s*s\b", brief or "")
    if m:
        return int(m.group(1))
    return 30


def plan(brief, chat, recent=""):
    target = target_seconds(brief)
    # ~4.5s per scene (VO ~18 words max at ~150 wpm + a beat). Cap the scene
    # count so the video fits the target instead of running long.
    max_scenes = max(4, min(9, round(target / 4.5)))
    prompt = PLAN_PROMPT.replace("25-45 seconds", f"exactly {target} seconds").replace("Rules: 6-9 scenes.", f"Rules: {max_scenes} scenes (no more).")
    raw = chat([{"role": "system", "content": "You output strict JSON only."},
                {"role": "user", "content": prompt.replace("{recent}", recent or "none") + (brief or "(none - you choose)")}])
    m = re.search(r"\{[\s\S]*\}", raw)
    p = json.loads(m.group(0))
    sc = [s for s in p.get("scenes", []) if s.get("vo")]
    # Keep the hook (scene 1) and the takeaway/CTA (last scene); drop middle
    # scenes when the plan runs long.
    if len(sc) > max_scenes:
        sc = sc[:max_scenes - 1] + [sc[-1]]
    for s in sc:
        if s.get("visual") not in VISUALS:
            s["visual"] = random.choice(VISUALS)
        s["label"] = str(s.get("label", "")).upper()[:22]
        s["value"] = str(s.get("value", ""))[:8]
    if len(sc) < 3:
        raise ValueError("plan too short")
    p["scenes"] = sc
    p["title"] = str(p.get("title", "")).upper()[:28]
    return p


async def tts(text, voice, out):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="+8%").save(out)


def dur(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(o.stdout.strip() or 0)


# ---------------- drawing helpers ----------------
def ease(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3


def clamp(x, a=0.0, b=1.0):  # v34: was missing — _wprogress + card used it
    return max(a, min(b, x))


def pop(t):  # overshoot pop 0->1 (v36: 6% overshoot, was 5.3%)
    t = max(0.0, min(1.0, t)); return 1 + 2.2 * (t - 1) ** 3 + 1.25 * (t - 1) ** 2 if t < 1 else 1.0


def center_text(d, y, text, f, fill):
    w = d.textlength(text, font=f); d.text(((W - w) / 2, y), text, font=f, fill=fill)


def rrect(d, box, r, **kw):
    # v28: PIL's rounded_rectangle draws an inner rect at (x0+r+1, y0, x1-r-1, y1),
    # so the radius must be <= (width-2)/2 (not width/2) — a pop animation starting
    # at scale ~0 would otherwise raise ValueError. Too small for rounding: plain rect.
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0: return
    r = max(0, min(r, (x1 - x0 - 2) / 2, (y1 - y0 - 2) / 2))
    if r <= 0:
        d.rectangle(box, **kw)
        return
    d.rounded_rectangle(box, r, **kw)


def num_of(v, default=7):
    m = re.search(r"\d+", v or ""); return int(m.group(0)) if m else default


def draw_visual(d, img, kind, value, t, cx=W // 2, cy=880, acc=None, words=None):
    # v25: optional accent (the look's accent) — defaults to RED for the old engine.
    # v34 (Hark word_t): words = [(start, dur, text)] — the count/fill visuals
    # run while the NUMBER word is spoken, instead of a fixed 0.8 s build-in.
    acc = acc or RED
    a = ease(t / 0.8)
    _NUMW = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
             "eleven", "twelve", "twenty", "thirty", "fifty", "hundred", "thousand", "million",
             "billion", "percent", "half", "double", "triple", "zero")
    def _wprogress():
        if not words: return None
        for (o, dd, w) in words:
            ww = str(w).strip().lower().strip(".,!?\"'")
            if any(c.isdigit() for c in ww) or ww in _NUMW:
                return clamp((t - o) / max(dd + 0.3, 0.1))
        return None
    wp = _wprogress()
    if kind == "counter":
        n = num_of(value, 100); cur = int(n * (wp if wp is not None else a))
        f = font(220); center_text(d, cy - 140, f"{cur}{'%' if '%' in value else ''}", f, acc)
    elif kind == "bar":
        p = num_of(value, 80) / 100 * a
        rrect(d, (140, cy - 50, W - 140, cy + 50), 20, outline=WHITE, width=5)
        rrect(d, (155, cy - 35, 155 + (W - 310) * min(p, 1), cy + 35), 14, fill=acc)
        center_text(d, cy + 80, f"{int(p*100)}%", font(64), WHITE)
    elif kind == "battery":
        p = max(0.05, 1 - 0.85 * a) if not value or "%" not in value else num_of(value) / 100
        rrect(d, (290, cy - 160, 790, cy + 160), 30, outline=WHITE, width=8)
        d.rectangle((790, cy - 50, 830, cy + 50), fill=WHITE)
        col = GREEN if p > 0.5 else YEL if p > 0.2 else acc
        rrect(d, (310, cy - 140, 310 + 460 * p, cy + 140), 18, fill=col)
    elif kind == "chat":
        bubbles = [("left", 0.0), ("right", 0.35), ("left", 0.7)]
        for i, (side, st) in enumerate(bubbles):
            k = pop((t - st) / 0.35)
            if k <= 0: continue
            y = cy - 260 + i * 190; w = 520 * k
            x0 = 120 if side == "left" else W - 120 - w
            rrect(d, (x0, y, x0 + w, y + 140), 40, fill=(45, 45, 52) if side == "left" else acc)
            if k > 0.9:
                for j in range(3):
                    d.ellipse((x0 + 60 + j * 60, y + 55, x0 + 90 + j * 60, y + 85), fill=WHITE)
        if t > 1.2: d.text((W - 300, cy + 330), "Seen ✓✓", font=font(40), fill=GREY)
    elif kind == "check":
        k = pop(t / 0.5); r = 200 * k
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN)
        if t > 0.4:
            q = ease((t - 0.4) / 0.4)
            pts = [(cx - 100, cy), (cx - 30, cy + 80), (cx + 110, cy - 90)]
            seg = pts[:2] if q < 0.5 else pts
            end = (pts[0][0] + (pts[1][0] - pts[0][0]) * min(1, q * 2), pts[0][1] + (pts[1][1] - pts[0][1]) * min(1, q * 2)) if q < 0.5 else \
                (pts[1][0] + (pts[2][0] - pts[1][0]) * (q - 0.5) * 2, pts[1][1] + (pts[2][1] - pts[1][1]) * (q - 0.5) * 2)
            d.line(seg[:-1] + [end] if q >= 0.5 else [pts[0], end], fill=WHITE, width=40, joint="curve")
    elif kind == "warning":
        k = pop(t / 0.5); s = 260 * k; sh = 8 * math.sin(t * 40) if t < 0.9 else 0
        d.polygon([(cx + sh, cy - s), (cx - s * 1.1 + sh, cy + s * 0.8), (cx + s * 1.1 + sh, cy + s * 0.8)], fill=acc)
        if k > 0.8: center_text(d, cy - 110, "!", font(240), WHITE)
    elif kind == "graph":
        pts = [(140 + i * 100, cy + 220 - (i ** 1.6) * 22 - random.Random(i).randint(0, 40)) for i in range(9)]
        n = min(len(pts), max(2, int(len(pts) * a) + 1))
        d.line([(140, cy + 260), (W - 140, cy + 260)], fill=GREY, width=4); d.line([(140, cy - 300), (140, cy + 260)], fill=GREY, width=4)
        d.line(pts[:n], fill=GREEN if "down" not in (value or "").lower() else acc, width=14, joint="curve")
        x, y = pts[n - 1]; d.ellipse((x - 20, y - 20, x + 20, y + 20), fill=WHITE)
    elif kind == "clock":
        r = 260; d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=WHITE, width=12)
        for i in range(12):
            an = i * math.pi / 6; d.line([(cx + 220 * math.cos(an), cy + 220 * math.sin(an)), (cx + 240 * math.cos(an), cy + 240 * math.sin(an))], fill=GREY, width=8)
        an = -math.pi / 2 + t * 4; d.line([(cx, cy), (cx + 200 * math.cos(an), cy + 200 * math.sin(an))], fill=acc, width=14)
        an2 = -math.pi / 2 + t * 0.4; d.line([(cx, cy), (cx + 130 * math.cos(an2), cy + 130 * math.sin(an2))], fill=WHITE, width=18)
    elif kind == "heart":
        s = 1 + 0.08 * math.sin(t * 9)
        pts = [(cx + 16 * math.sin(u) ** 3 * 14 * s, cy - (13 * math.cos(u) - 5 * math.cos(2 * u) - 2 * math.cos(3 * u) - math.cos(4 * u)) * 14 * s) for u in np.linspace(0, 2 * math.pi, 120)]
        d.polygon(pts, fill=acc)
        ys = cy + 320; xs = np.linspace(140, W - 140, 60)
        line = [(x, ys - (90 if abs(x - (140 + (t * 500) % 800)) < 25 else 0)) for x in xs]
        d.line(line, fill=GREEN, width=8)
    elif kind == "calendar":
        rrect(d, (200, cy - 280, 880, cy + 300), 30, fill=(30, 30, 36)); d.rectangle((200, cy - 280, 880, cy - 170), fill=acc)
        n = num_of(value, 7); shown = int(min(28, 28 * a))
        for i in range(28):
            x = 240 + (i % 7) * 90; y = cy - 140 + (i // 7) * 100
            col = acc if i < min(n, shown) else GREY
            d.rectangle((x, y, x + 60, y + 60), outline=col, width=5)
            if i < min(n, shown): d.line([(x + 8, y + 8), (x + 52, y + 52)], fill=acc, width=6)
    elif kind == "list":
        for i in range(4):
            k = ease((t - i * 0.25) / 0.3)
            if k <= 0: continue
            y = cy - 260 + i * 150
            d.text((180 - 60 * (1 - k), y), f"[{i+1:02d}]", font=font(56), fill=acc)
            rrect(d, (360, y + 10, 360 + 520 * k, y + 50), 12, fill=(70, 70, 80))
    elif kind == "versus":
        k = ease(t / 0.6)
        rrect(d, (100 - 300 * (1 - k), cy - 220, 500 - 300 * (1 - k), cy + 220), 30, fill=(45, 45, 52))
        rrect(d, (580 + 300 * (1 - k), cy - 220, 980 + 300 * (1 - k), cy + 220), 30, fill=acc)
        center_text(d, cy - 50, "VS", font(90), YEL)
        d.text((230 - 300 * (1 - k), cy - 40), "✗", font=font(100), fill=acc)
        d.text((720 + 300 * (1 - k), cy - 40), "✓", font=font(100), fill=WHITE)
    # ---- v34 (Hark engine): four / question / card / watch / stamp / stamp_cta.
    elif kind == "four":  # people icons for "1 in N" facts (Hark `four`)
        n = max(2, min(6, num_of(value, 4)))
        _hot = wp if wp is not None else ease((t - 0.8) / 0.4)
        for i in range(n):
            k = pop((t - i * 0.15) / 0.35)
            if k <= 0: continue
            x = cx - (n - 1) * 110 + i * 220
            col = acc if (i == 0 and _hot > 0) else WHITE
            r = 55 * k
            d.ellipse([x - r, cy - 260 * k, x + r, cy - 150 * k], fill=col)
            d.rounded_rectangle([x - 70 * k, cy - 130 * k, x + 70 * k, cy + 130 * k], 30, fill=col)
            if i == 0 and _hot > 0:
                q = ease(_hot)
                d.rounded_rectangle([x - 100, cy - 300, x + 100, cy + 170], 20, outline=acc, width=int(3 + 6 * q))
    elif kind == "question":  # giant "?" over a blurred pack, wobbling (Hark `question`)
        k = pop((t - 0.3) / 0.4)
        if k > 0:
            rrect(d, (cx - 260, cy - 330, cx + 260, cy + 330), 24, fill=(60, 20, 22))
            d.text((cx, cy - 60), "TOBACCO", font=font(60), fill=(120, 90, 90), anchor="mm")
            sh = math.sin(t * 14) * 6 if t > 0.9 else 0
            d.text((cx + 60 + sh, cy + 40), "?", font=font(int(520 * (0.6 + 0.4 * k))), fill=YEL, anchor="mm")
    elif kind == "card":  # contact/helpline card, number typed out + yellow marker (Hark `card`)
        x0, y0, x1, y1 = cx - 420, cy - 260, cx + 420, cy + 260
        rrect(d, (x0, y0, x1, y1), 20, fill=(232, 226, 210))
        d.text((x0 + 40, y0 + 30), "CALL FOR HELP", font=font(48), fill=(30, 30, 30))
        d.line([(x0 + 40, y0 + 110), (x1 - 40, y0 + 110)], fill=(120, 120, 120), width=3)
        num = (value or "1800-11-2356").strip()
        _dig = [o for (o, _dd, w) in (words or []) if any(c.isdigit() for c in str(w))]
        _ts = _dig[0] if _dig else 0.5
        n = int(len(num) * clamp((t - _ts) / 1.8))
        n = max(0, min(len(num), n))
        if n >= len(num) and n > 0:
            q = ease((t - (_ts + 1.9)) / 0.35)
            if q > 0:
                wnum = d.textlength(num, font=font(88))
                d.rectangle([x0 + 36, y0 + 150, x0 + 36 + (wnum + 12) * q, y0 + 250], fill=(245, 205, 40))
        if n > 0:
            d.text((x0 + 40, y0 + 150), num[:n], font=font(88), fill=(25, 25, 25))
        d.text((x0 + 40, y1 - 70), "Free help, any time", font=font(44), fill=(60, 60, 60))
    elif kind == "watch":  # stopwatch, red sector sweeps + stamp (Hark `watch`)
        R = 250
        _dur = (words[-1][0] + words[-1][1]) if words else 4.0
        sweep = min(t / max(_dur - 0.3, 0.5), 1) * (25 / 60) * 360
        if sweep > 1:
            d.pieslice([cx - R + 20, cy - R + 20, cx + R - 20, cy + R - 20], -90, -90 + sweep, fill=(214, 40, 40))
        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=WHITE, width=12)
        for kk in range(12):
            an = kk * math.pi / 6
            d.line([(cx + (R - 25) * math.sin(an), cy - (R - 25) * math.cos(an)), (cx + (R - 6) * math.sin(an), cy - (R - 6) * math.cos(an))], fill=GREY, width=6)
        an = math.radians(-90 + sweep)
        d.line([(cx, cy), (cx + (R - 40) * math.cos(an), cy + (R - 40) * math.sin(an))], fill=YEL, width=10)
        d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=YEL)
        # v34 fix: the value text is NOT drawn here — the scene label below
        # the visual already shows it (v33 dup-text rule).
    elif kind == "stamp":  # a rotated stamp slamming in + shake (Hark `stamp`)
        word = (value or "BANNED")[:12].upper()
        q = ease((t - 0.5) / 0.2)
        if q > 0:
            sh = 6 * math.sin(t * 50) if t < 1.0 else 0
            f = font(110)
            w = d.textlength(word, font=f) + 80
            st = Image.new("RGBA", (int(w), 180), (0, 0, 0, 0))
            ds = ImageDraw.Draw(st)
            ds.rounded_rectangle([4, 4, w - 4, 176], 16, outline=acc + (255,), width=8)
            ds.text((w / 2, 90), word, font=f, fill=acc + (255,), anchor="mm")
            st = st.rotate(-12, expand=True, resample=Image.BICUBIC)
            sc = 2.2 - 1.2 * q
            st = st.resize((max(1, int(st.width * sc)), max(1, int(st.height * sc))), Image.BICUBIC)
            if img.mode == "RGBA":
                img.alpha_composite(st, (int(cx - st.width / 2 + sh), int(cy - st.height / 2)))
            else:
                img.paste(st, (int(cx - st.width / 2 + sh), int(cy - st.height / 2)), st)
    elif kind == "stamp_cta":  # final call to action: stamp slams + red strike grows (Hark stamp CTA)
        word = (value or "TODAY")[:12].upper()
        q = ease((t - 0.4) / 0.2)
        if q > 0:
            sh = 6 * math.sin(t * 50) if t < 0.9 else 0
            f = font(130)
            w = d.textlength(word, font=f) + 90
            st = Image.new("RGBA", (int(w), 200), (0, 0, 0, 0))
            ds = ImageDraw.Draw(st)
            ds.rounded_rectangle([4, 4, w - 4, 196], 18, outline=YEL + (255,), width=9)
            ds.text((w / 2, 100), word, font=f, fill=YEL + (255,), anchor="mm")
            st = st.rotate(-6, expand=True, resample=Image.BICUBIC)
            sc = 2.4 - 1.4 * q
            st = st.resize((max(1, int(st.width * sc)), max(1, int(st.height * sc))), Image.BICUBIC)
            if img.mode == "RGBA":
                img.alpha_composite(st, (int(cx - st.width / 2 + sh), int(cy - st.height / 2)))
            else:
                img.paste(st, (int(cx - st.width / 2 + sh), int(cy - st.height / 2)), st)
        q2 = ease((t - 0.9) / 0.3)
        if q2 > 0:
            x0, x1 = cx - 380, cx + 380
            d.line([(x0, cy + 220), (x0 + (x1 - x0) * q2, cy + 210)], fill=(220, 50, 50), width=14)
    # ---- v28 (Hark kit visual library): the kit's 18 visual types, grown from the
    # 12. Each one draws the LITERAL idea of the sentence (never a mascot).
    elif kind == "dot_grid":  # a percentage as 100 dots filling up (kit s3: 89%)
        n = num_of(value, 89); shown = int(100 * (wp if wp is not None else a))
        center_text(d, cy - 380, f"{n}%", font(120), acc)
        for i in range(100):
            r, c = divmod(i, 10); x = cx - 225 + c * 50; y = cy - 200 + r * 50
            if i >= shown: break
            rad = 15 * pop((t - i * 0.006) / 0.3)
            if rad <= 0: continue
            d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=acc if i < n else GREY)
    elif kind == "donut":  # a ring that fills to N% (kit s5: 96x ring)
        n = num_of(value, 75); R = 220
        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=GREY, width=28)
        ang = 360 * (n / 100) * (wp if wp is not None else a)
        if ang > 1: d.arc([cx - R, cy - R, cx + R, cy + R], -90, -90 + ang, fill=acc, width=28)
        center_text(d, cy - 60, f"{int(n * (wp if wp is not None else a))}{'%' if '%' in value else ''}", font(140), acc)
    elif kind == "gauge":  # a semicircular gauge with a needle
        n = num_of(value, 60); R = 280
        d.arc([cx - R, cy - R, cx + R, cy + R], 180, 360, fill=GREY, width=24)
        ang = 180 + 180 * (n / 100) * a
        if ang > 181: d.arc([cx - R, cy - R, cx + R, cy + R], 180, ang, fill=acc, width=24)
        na = math.radians(ang)
        d.line([(cx, cy), (cx + (R - 40) * math.cos(na), cy + (R - 40) * math.sin(na))], fill=WHITE, width=12)
        d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=WHITE)
        center_text(d, cy + 60, f"{int(n * a)}%", font(90), acc)
    elif kind == "toggle":  # an on/off switch (value ON/OFF/YES/NO)
        on = (value or "").strip().lower() in ("on", "yes", "true", "1", "y")
        x0, x1, y0, y1 = cx - 260, cx + 260, cy - 110, cy + 110
        rrect(d, (x0, y0, x1, y1), 100, fill=acc if on else (70, 70, 80))
        # the knob slides to the right for ON, stays left for OFF
        target = (x1 - 110) if on else (x0 + 110)
        kx = (x0 + 110) + (target - (x0 + 110)) * ease(t / 0.6)
        d.ellipse([kx - 95, cy - 95, kx + 95, cy + 95], fill=WHITE)
        center_text(d, cy + 180, "ON" if on else "OFF", font(90), acc if on else GREY)
    elif kind == "phone_buzz":  # a phone with vibration arcs (kit s0)
        sh = 8 * math.sin(t * 40) if t < 1.5 else 0
        w, h = 300, 560
        rrect(d, (cx - w / 2 + sh, cy - h / 2, cx + w / 2 + sh, cy + h / 2), 40, fill=(235, 235, 235))
        rrect(d, (cx - w / 2 + 20 + sh, cy - h / 2 + 50, cx + w / 2 - 20 + sh, cy + h / 2 - 60), 16, fill=(28, 28, 32))
        d.ellipse([cx - 18 + sh, cy + h / 2 - 46, cx + 18 + sh, cy + h / 2 - 14], fill=(150, 150, 150))
        for k in range(3):  # radiating arcs, growing with time
            r = 200 + ((t * 1.2 - k * 0.3) % 1) * 110
            d.arc([cx - r, cy - r, cx + r, cy + r], -50, 50, fill=acc, width=8)
            d.arc([cx - r, cy - r, cx + r, cy + r], 130, 230, fill=acc, width=8)
    elif kind == "stick_figure":  # a simple person (feeling / habit / action)
        k = pop(t / 0.5); s = max(k, 0.01)
        d.ellipse([cx - 50 * s, cy - 300 * s, cx + 50 * s, cy - 200 * s], fill=WHITE)
        rrect(d, [cx - 55 * s, cy - 190 * s, cx + 55 * s, cy + 20 * s], 25, fill=WHITE)
        d.rectangle([cx - 50 * s, cy + 20 * s, cx - 12 * s, cy + 200 * s], fill=WHITE)
        d.rectangle([cx + 12 * s, cy + 20 * s, cx + 50 * s, cy + 200 * s], fill=WHITE)
        if "phone" in (value or "").lower():  # arm raised, holding a phone
            d.line([(cx + 50 * s, cy - 160 * s), (cx + 110 * s, cy - 90 * s), (cx + 70 * s, cy - 130 * s)], fill=WHITE, width=28, joint="curve")
            rrect(d, [cx + 40 * s, cy - 210 * s, cx + 110 * s, cy - 110 * s], 10, fill=acc)
            d.rectangle([cx - 95 * s, cy - 170 * s, cx - 55 * s, cy + 10 * s], fill=WHITE)
        else:  # arms down
            d.rectangle([cx - 95 * s, cy - 170 * s, cx - 55 * s, cy + 10 * s], fill=WHITE)
            d.rectangle([cx + 55 * s, cy - 170 * s, cx + 95 * s, cy + 10 * s], fill=WHITE)
    elif kind == "quote_card":  # a big quote mark + the key word in a card
        k = pop(t / 0.5)
        x0, y0, x1, y1 = cx - 380, cy - 220, cx + 380, cy + 220
        rrect(d, (x0, y0, x1, y1), 24, fill=(30, 30, 36), outline=acc, width=6)
        d.text((x0 + 40, y0 + 20), "“", font=font(200), fill=acc)
        center_text(d, cy - 40, (value or "TRUTH")[:12], font(90), WHITE)
    elif kind == "arrows_steps":  # a process: numbered steps with arrows
        n = max(2, min(3, num_of(value, 3)))
        for i in range(n):
            k = ease((t - i * 0.3) / 0.3)
            if k <= 0: continue
            x0 = 140 + i * 300; y0 = cy - 100
            rrect(d, (x0, y0, x0 + 220, y0 + 200), 24, fill=acc if i == n - 1 else (45, 45, 52))
            d.text((x0 + 110, y0 + 100), str(i + 1), font=font(90), fill=WHITE, anchor="mm")
            if i < n - 1:
                d.polygon([(x0 + 240, cy), (x0 + 280, cy - 25), (x0 + 280, cy + 25)], fill=acc)
    elif kind == "checklist":  # a checklist: boxes that get ticked one by one
        for i in range(3):
            k = ease((t - i * 0.3) / 0.3)
            if k <= 0: continue
            y = cy - 240 + i * 180
            rrect(d, (200, y, 300, y + 100), 16, outline=acc, width=6)
            if k > 0.7:
                d.line([(215, y + 50), (245, y + 80), (290, y + 20)], fill=GREEN, width=12, joint="curve")
            rrect(d, (340, y + 25, 340 + 540 * k, y + 75), 12, fill=(70, 70, 80))
    elif kind == "document":  # a paper/report with lines + a seal
        k = pop(t / 0.5)
        x0, y0, x1, y1 = cx - 260, cy - 300, cx + 260, cy + 300
        rrect(d, (x0, y0, x1, y1), 20, fill=(240, 240, 235))
        d.rectangle([x0 + 40, y0 + 50, x1 - 40, y0 + 80], fill=acc)
        for i in range(5):
            kk = ease((t - 0.2 - i * 0.15) / 0.3)
            if kk <= 0: continue
            w = (x1 - x0 - 80) * (0.9 if i % 2 == 0 else 0.7) * kk
            d.rectangle([x0 + 40, y0 + 130 + i * 70, x0 + 40 + w, y0 + 150 + i * 70], fill=(120, 120, 120))
        d.ellipse([x1 - 140, y1 - 140, x1 - 40, y1 - 40], outline=acc, width=6)
        d.text((x1 - 90, y1 - 90), "✓", font=font(70), fill=acc, anchor="mm")
    elif kind == "polaroid":  # a photo frame with a caption
        k = pop(t / 0.5)
        x0, y0, x1, y1 = cx - 280, cy - 320, cx + 280, cy + 320
        rrect(d, (x0, y0, x1, y1), 16, fill=(245, 245, 240))
        d.rectangle([x0 + 30, y0 + 30, x1 - 30, y1 - 130], fill=(40, 40, 48))
        d.ellipse([cx - 60, y0 + 90, cx + 60, y0 + 210], fill=acc)
        d.polygon([(x0 + 30, y1 - 130), (cx - 40, y1 - 260), (cx + 60, y1 - 130)], fill=GREEN)
        center_text(d, y1 - 70, (value or "MEMORY")[:10], font(48), (60, 60, 60))
    elif kind == "icon_row":  # a row of numbered icons
        n = max(2, min(4, num_of(value, 3)))
        for i in range(n):
            k = pop((t - i * 0.25) / 0.4)
            if k <= 0: continue
            x = cx - (n - 1) * 130 + i * 260; r = 90 * k
            d.ellipse([x - r, cy - r, x + r, cy + r], fill=acc if i % 2 == 0 else (45, 45, 52))
            d.text((x, cy), str(i + 1), font=font(80), fill=WHITE, anchor="mm")
    elif kind == "bar_compare":  # two bars side by side (comparison of two numbers)
        nums = [int(x) for x in re.findall(r"\d+", value or "")]
        a1 = nums[0] if len(nums) > 0 else 70
        a2 = nums[1] if len(nums) > 1 else 40
        p1 = (a1 / 100) * a; p2 = (a2 / 100) * a
        d.text((140, cy - 260), f"{a1}", font=font(80), fill=acc)
        rrect(d, (140, cy - 160, 140 + (W - 280) * min(p1, 1), cy - 60), 16, fill=acc)
        d.text((140, cy + 20), f"{a2}", font=font(80), fill=GREY)
        rrect(d, (140, cy + 120, 140 + (W - 280) * min(p2, 1), cy + 220), 16, fill=GREY)
    # ---- v32 (M4/M5/M14 + M1, Mark's motivation short): the three graphics
    # Divya was missing — strike-through, exponential curve, lower-third.
    elif kind == "curve":  # exponential growth 1.01^x, axis labels, endpoint dot (1.01^365 = 37x)
        d.line([(cx - 380, cy + 260), (cx + 400, cy + 260)], fill=WHITE, width=5)
        d.line([(cx - 380, cy + 260), (cx - 380, cy - 260)], fill=WHITE, width=5)
        n = max(2, int(101 * a) + 1)
        pts = [(cx - 380 + i * 7.6, cy + 250 - ((1.01 ** (i * 3.65)) - 1) / 36.8 * 480) for i in range(n)]
        d.line(pts, fill=YEL, width=12, joint="curve")
        x, y = pts[-1]
        d.ellipse([x - 20, y - 20, x + 20, y + 20], fill=YEL)
        d.text((cx - 370, cy + 280), "DAY 1", font=font(50), fill=GREY)
        d.text((cx + 230, cy + 280), "DAY 365", font=font(50), fill=GREY)
        if value:
            center_text(d, cy - 330, str(value)[:6], font(90), YEL)
    elif kind == "strike":  # a word crossed out — red line, slight angle ("Not MONDAY")
        word = (value or "MONDAY")[:12].upper()
        f = font(130)
        w = d.textlength(word, font=f)
        k = pop((t - 0.3) / 0.4)
        if k > 0:
            d.text((cx, cy), word, font=font(int(130 * (0.6 + 0.4 * k))), fill=GREY, anchor="mm")
        q = ease((t - 0.6) / 0.3)  # the red strike grows left to right, right end 10 px higher
        if q > 0:
            x0, x1 = cx - w / 2 - 20, cx + w / 2 + 20
            d.line([(x0, cy + 5), (x0 + (x1 - x0) * q, cy + 5 - 10 * q)], fill=(220, 50, 50), width=14)
    elif kind == "lower_third":  # documentary name + title bar, bottom-left (value: "Name | Title")
        parts = [x.strip() for x in str(value or "").split("|")]
        name = parts[0][:24] if parts and parts[0] else "DIVYA"
        title = parts[1][:32] if len(parts) > 1 else ""
        k = ease(t / 0.4)
        y0, y1 = 1500, 1650
        w = 620 * k
        if w > 10:
            rrect(d, (120, y0, 120 + w, y1), 12, fill=(20, 20, 24))
            d.rectangle([120, y0, 132, y1], fill=acc)
            if k > 0.8:
                d.text((160, y0 + 18), name, font=font(64), fill=WHITE)
                if title:
                    d.text((160, y0 + 90), title, font=font(44), fill=GREY)


def frame(p, idx, sc, t, total_sc):
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    # grid + brackets
    for x in range(0, W, 90): d.line([(x, 0), (x, H)], fill=(20, 20, 24))
    for y in range(0, H, 90): d.line([(0, y), (W, y)], fill=(20, 20, 24))
    L = 70
    for (x, y, sx, sy) in [(40, 40, 1, 1), (W - 40, 40, -1, 1), (40, H - 40, 1, -1), (W - 40, H - 40, -1, -1)]:
        d.line([(x, y), (x + sx * L, y)], fill=RED, width=8); d.line([(x, y), (x, y + sy * L)], fill=RED, width=8)
    # banner + counter + progress
    center_text(d, 120, p["title"], font(48), WHITE)
    d.text((80, 210), f"> [{idx+1:02d}/{total_sc:02d}]", font=font(40), fill=RED)
    filled = int(20 * (idx + min(t / max(sc['d'], .1), 1)) / total_sc)
    d.text((440, 210), "[" + "#" * filled + "." * (20 - filled) + "]", font=font(40), fill=GREY)
    # visual
    draw_visual(d, img, sc["visual"], sc.get("value", ""), t)
    # punch label with pop + cursor
    k = pop((t - 0.15) / 0.4)
    if k > 0:
        f = font(int(96 * max(k, 0.2)))
        lab = sc["label"] + ("_" if int(t * 3) % 2 == 0 else " ")
        center_text(d, 1260, lab, f, RED if idx % 2 == 0 else YEL)
    # glitch on scene start
    if t < 0.12:
        a = np.array(img); sh = random.randint(-40, 40); y0 = random.randint(300, 1500)
        a[y0:y0 + 60] = np.roll(a[y0:y0 + 60], sh, axis=1); a[y0:y0 + 6, :, 0] = 255
        img = Image.fromarray(a)
    return img


def ass_time(s):
    h = int(s // 3600); m = int(s % 3600 // 60); sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"


def write_ass(scenes, path):
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: T,Noto Sans Telugu,58,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,0,2,90,90,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []; t0 = 0.0
    for s in scenes:
        words = s["vo"].split(); chunks = [" ".join(words[i:i + 5]) for i in range(0, len(words), 5)] or [s["vo"]]
        per = s["d"] / len(chunks)
        for i, c in enumerate(chunks):
            lines.append(f"Dialogue: 0,{ass_time(t0 + i * per)},{ass_time(t0 + (i + 1) * per)},T,,0,0,0,,{{\\fad(80,40)}}{c}")
        t0 += s["d"]
    open(path, "w", encoding="utf-8").write(head + "\n".join(lines) + "\n")


async def make_video(brief, chat, notify=None, workdir=None, recent=""):
    wd = workdir or tempfile.mkdtemp(prefix="create_")
    p = plan(brief, chat, recent)
    if notify: await notify(f"📝 Script ready: {p['title']} ({len(p['scenes'])} scenes). Voice + animation chestunna...")
    voice = VOICES.get(p.get("voice", "male"), VOICES["male"])
    for i, s in enumerate(p["scenes"]):
        a = f"{wd}/vo{i}.mp3"; await tts(s["vo"], voice, a)
        s["audio"] = a; s["d"] = dur(a) + 0.35
    # concat audio with small gaps
    lst = f"{wd}/a.txt"
    with open(lst, "w") as f:
        for s in p["scenes"]:
            f.write(f"file '{s['audio']}'\n")
    pads = "".join(f"[{i}:a]apad=pad_dur=0.35[a{i}];" for i in range(len(p["scenes"])))
    ins = sum([["-i", s["audio"]] for s in p["scenes"]], [])
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex",
                    pads + "".join(f"[a{i}]" for i in range(len(p["scenes"]))) + f"concat=n={len(p['scenes'])}:v=0:a=1[o]",
                    "-map", "[o]", "-ar", "44100", f"{wd}/voice.m4a"], check=True)
    # frames -> raw video
    raw = f"{wd}/raw.mp4"
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                             "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", raw], stdin=subprocess.PIPE)
    n = len(p["scenes"])
    for i, s in enumerate(p["scenes"]):
        for fi in range(int(s["d"] * FPS)):
            proc.stdin.write(frame(p, i, s, fi / FPS, n).tobytes())
    proc.stdin.close(); proc.wait()
    ass = f"{wd}/subs.ass"; write_ass(p["scenes"], ass)
    out = f"{wd}/divya_short.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-i", f"{wd}/voice.m4a", "-vf", f"ass={ass}:fontsdir={FONTS}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out], check=True)
    script = "\n".join(s["vo"] for s in p["scenes"])
    return {"path": out, "topic": p.get("topic", brief), "title": p["title"], "script": script, "plan": p}
