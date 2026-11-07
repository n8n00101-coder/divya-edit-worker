"""Divya: make a faceless 9:16 Telugu explainer Short from ONLY a topic/brief (no raw footage).
Pipeline: LLM plan (Telugu VO lines + 1-3 word English labels + visual type) -> edge-tts Telugu voice
-> PIL animated scenes (dark bg, red accent, mono font, animated objects) -> ASS Telugu captions (libass shapes Telugu)
-> ffmpeg mux. Free, CPU only."""
import asyncio, json, math, os, random, re, subprocess, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
BG, RED, WHITE, GREEN, YEL, GREY = (12, 12, 14), (235, 50, 60), (240, 240, 240), (60, 210, 120), (250, 205, 60), (90, 90, 100)
VISUALS = ["counter", "bar", "chat", "check", "warning", "graph", "clock", "heart", "battery", "calendar", "list", "versus"]
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
VOICES = {"male": "te-IN-MohanNeural", "female": "te-IN-ShrutiNeural"}


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
check for good habits, versus for comparisons, counter for numbers, list for steps, heart for love/health, bar for progress).
If the owner did not give a clear topic (e.g. "nuvve select chesko", "any topic", empty), YOU pick one fresh, high-retention
topic for a Telugu faceless channel (psychology, relationships, money habits, health hacks, motivation, tech tips, facts) — avoid
these recent topics: {recent}. Also add "topic": "<the topic you chose>" to the JSON.
Topic/brief from owner: """ % VISUALS


def plan(brief, chat, recent=""):
    raw = chat([{"role": "system", "content": "You output strict JSON only."},
                {"role": "user", "content": PLAN_PROMPT.replace("{recent}", recent or "none") + (brief or "(none - you choose)")}])
    m = re.search(r"\{[\s\S]*\}", raw)
    p = json.loads(m.group(0))
    sc = [s for s in p.get("scenes", []) if s.get("vo")][:10]
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


def pop(t):  # overshoot pop 0->1
    t = max(0.0, min(1.0, t)); return 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2 if t < 1 else 1.0


def center_text(d, y, text, f, fill):
    w = d.textlength(text, font=f); d.text(((W - w) / 2, y), text, font=f, fill=fill)


def rrect(d, box, r, **kw):
    d.rounded_rectangle(box, r, **kw)


def num_of(v, default=7):
    m = re.search(r"\d+", v or ""); return int(m.group(0)) if m else default


def draw_visual(d, img, kind, value, t, cx=W // 2, cy=880):
    a = ease(t / 0.8)
    if kind == "counter":
        n = num_of(value, 100); cur = int(n * a)
        f = font(220); center_text(d, cy - 140, f"{cur}{'%' if '%' in value else ''}", f, RED)
    elif kind == "bar":
        p = num_of(value, 80) / 100 * a
        rrect(d, (140, cy - 50, W - 140, cy + 50), 20, outline=WHITE, width=5)
        rrect(d, (155, cy - 35, 155 + (W - 310) * min(p, 1), cy + 35), 14, fill=RED)
        center_text(d, cy + 80, f"{int(p*100)}%", font(64), WHITE)
    elif kind == "battery":
        p = max(0.05, 1 - 0.85 * a) if not value or "%" not in value else num_of(value) / 100
        rrect(d, (290, cy - 160, 790, cy + 160), 30, outline=WHITE, width=8)
        d.rectangle((790, cy - 50, 830, cy + 50), fill=WHITE)
        col = GREEN if p > 0.5 else YEL if p > 0.2 else RED
        rrect(d, (310, cy - 140, 310 + 460 * p, cy + 140), 18, fill=col)
    elif kind == "chat":
        bubbles = [("left", 0.0), ("right", 0.35), ("left", 0.7)]
        for i, (side, st) in enumerate(bubbles):
            k = pop((t - st) / 0.35)
            if k <= 0: continue
            y = cy - 260 + i * 190; w = 520 * k
            x0 = 120 if side == "left" else W - 120 - w
            rrect(d, (x0, y, x0 + w, y + 140), 40, fill=(45, 45, 52) if side == "left" else RED)
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
        d.polygon([(cx + sh, cy - s), (cx - s * 1.1 + sh, cy + s * 0.8), (cx + s * 1.1 + sh, cy + s * 0.8)], fill=RED)
        if k > 0.8: center_text(d, cy - 110, "!", font(240), WHITE)
    elif kind == "graph":
        pts = [(140 + i * 100, cy + 220 - (i ** 1.6) * 22 - random.Random(i).randint(0, 40)) for i in range(9)]
        n = max(2, int(len(pts) * a) + 1)
        d.line([(140, cy + 260), (W - 140, cy + 260)], fill=GREY, width=4); d.line([(140, cy - 300), (140, cy + 260)], fill=GREY, width=4)
        d.line(pts[:n], fill=GREEN if "down" not in (value or "").lower() else RED, width=14, joint="curve")
        x, y = pts[n - 1]; d.ellipse((x - 20, y - 20, x + 20, y + 20), fill=WHITE)
    elif kind == "clock":
        r = 260; d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=WHITE, width=12)
        for i in range(12):
            an = i * math.pi / 6; d.line([(cx + 220 * math.cos(an), cy + 220 * math.sin(an)), (cx + 240 * math.cos(an), cy + 240 * math.sin(an))], fill=GREY, width=8)
        an = -math.pi / 2 + t * 4; d.line([(cx, cy), (cx + 200 * math.cos(an), cy + 200 * math.sin(an))], fill=RED, width=14)
        an2 = -math.pi / 2 + t * 0.4; d.line([(cx, cy), (cx + 130 * math.cos(an2), cy + 130 * math.sin(an2))], fill=WHITE, width=18)
    elif kind == "heart":
        s = 1 + 0.08 * math.sin(t * 9)
        pts = [(cx + 16 * math.sin(u) ** 3 * 14 * s, cy - (13 * math.cos(u) - 5 * math.cos(2 * u) - 2 * math.cos(3 * u) - math.cos(4 * u)) * 14 * s) for u in np.linspace(0, 2 * math.pi, 120)]
        d.polygon(pts, fill=RED)
        ys = cy + 320; xs = np.linspace(140, W - 140, 60)
        line = [(x, ys - (90 if abs(x - (140 + (t * 500) % 800)) < 25 else 0)) for x in xs]
        d.line(line, fill=GREEN, width=8)
    elif kind == "calendar":
        rrect(d, (200, cy - 280, 880, cy + 300), 30, fill=(30, 30, 36)); d.rectangle((200, cy - 280, 880, cy - 170), fill=RED)
        n = num_of(value, 7); shown = int(min(28, 28 * a))
        for i in range(28):
            x = 240 + (i % 7) * 90; y = cy - 140 + (i // 7) * 100
            col = RED if i < min(n, shown) else GREY
            d.rectangle((x, y, x + 60, y + 60), outline=col, width=5)
            if i < min(n, shown): d.line([(x + 8, y + 8), (x + 52, y + 52)], fill=RED, width=6)
    elif kind == "list":
        for i in range(4):
            k = ease((t - i * 0.25) / 0.3)
            if k <= 0: continue
            y = cy - 260 + i * 150
            d.text((180 - 60 * (1 - k), y), f"[{i+1:02d}]", font=font(56), fill=RED)
            rrect(d, (360, y + 10, 360 + 520 * k, y + 50), 12, fill=(70, 70, 80))
    elif kind == "versus":
        k = ease(t / 0.6)
        rrect(d, (100 - 300 * (1 - k), cy - 220, 500 - 300 * (1 - k), cy + 220), 30, fill=(45, 45, 52))
        rrect(d, (580 + 300 * (1 - k), cy - 220, 980 + 300 * (1 - k), cy + 220), 30, fill=RED)
        center_text(d, cy - 50, "VS", font(90), YEL)
        d.text((230 - 300 * (1 - k), cy - 40), "✗", font=font(100), fill=RED)
        d.text((720 + 300 * (1 - k), cy - 40), "✓", font=font(100), fill=WHITE)


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
