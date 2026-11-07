"""Divya documentary engine v2: topic (or AUTO) -> 45-60 s cinematic 9:16 video. No footage needed.
LLM story plan (hook -> context -> twist -> payoff -> CTA, per-scene mood) -> human-sounding neural voice
(English Andrew/Ava multilingual or Telugu Mohan/Shruti) with per-mood rate/pitch -> animated scenes
(mood palettes, bokeh, 3D-shaded character, animated objects, kinetic labels) -> camera push/pan/shake ->
6 transition kinds -> procedural cinematic music + whoosh/boom SFX, ducked under voice -> word-timed karaoke
captions (libass) -> film grade (vignette + grain). Rendered in parallel processes. Free, CPU only."""
import asyncio, json, math, multiprocessing as mp, os, random, re, subprocess, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import create as C

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
VOICES = {("en", "male"): "en-US-AndrewMultilingualNeural", ("en", "female"): "en-US-AvaMultilingualNeural",
          ("te", "male"): "te-IN-MohanNeural", ("te", "female"): "te-IN-ShrutiNeural",
          ("hi", "male"): "hi-IN-MadhurNeural", ("hi", "female"): "hi-IN-SwaraNeural"}

PLAN = """You are a top YouTube documentary-shorts writer and director. Plan ONE faceless 9:16 video from the owner's request.
Return ONLY JSON:
{"topic": "...", "title": "<2-5 word English title, caps>", "lang": "en|te|hi", "voice": "male|female",
 "caption": "<post caption with 3-5 hashtags>",
 "scenes": [{"vo": "...", "label": "<1-3 word ENGLISH punch label, caps>", "mood": "calm|tense|hopeful|sad|excited|mystery",
             "visual": "<one of %s>", "value": "<short number/word for the visual>"}]}
Language: follow the owner. If they ask for English voice/voice-over -> lang "en" (vo in English). Telugu -> "te" (vo in Telugu script).
Hindi -> "hi". If they say nothing about language, use "te".
Length: honour any duration they ask (e.g. "1 min" = 60 s). Default 50-60 s. English speaks ~2.5 words/s, Telugu ~1.8 words/s:
size the total vo words to the target duration. 9-14 scenes, each vo 6-22 words.
Writing: documentary storytelling that sounds like a real human talking to a friend - contractions, short punchy sentences,
rhetorical questions, a surprising fact or tension in the first line (hook), then context, a twist, the payoff, and a short
call to follow at the end. Use commas, "..." and dashes for natural pauses. No emojis, no hashtags in vo. Vary the mood per scene to
build an emotional arc. Each visual must literally show the line's idea (battery=energy, chat=messages/people, graph=growth or fall,
clock=time, calendar=days, warning=danger/mistake, check=right way, versus=comparison, counter=a number, list=steps, heart=love/health,
bar=progress).
If no clear topic is given ("nuvve select chesko", "any", "AUTO", empty) choose a fresh high-retention topic yourself (psychology,
history mysteries, science facts, money habits, health, tech, motivation). Avoid these recent topics: {recent}.
Owner request: """ % C.VISUALS


def plan(brief, chat, recent=""):
    raw = chat([{"role": "system", "content": "You output strict JSON only."},
                {"role": "user", "content": PLAN.replace("{recent}", recent or "none") + (brief or "AUTO")}])
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

_bg = {}
def background(mood):
    if mood not in _bg:
        top, bot, acc, _ = MOODS[mood]
        a = np.linspace(0, 1, H)[:, None, None]
        g = (np.array(top)[None, None] * (1 - a) + np.array(bot)[None, None] * a) * np.ones((1, W, 1))
        yy, xx = np.mgrid[0:H, 0:W]
        glow = np.exp(-(((xx - W / 2) / 520) ** 2 + ((yy - 860) / 620) ** 2))[..., None]
        g = g + glow * np.array(acc)[None, None] * 0.22
        im = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im)
        for y in range(0, H, 6): d.line([(0, y), (W, y)], fill=tuple(int(c * 0.93) for c in im.getpixel((5, y))))  # scanlines
        _bg[mood] = im
    return _bg[mood].copy()

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

def label(d, text, t, acc, idx):
    k = C.pop((t - 0.12) / 0.38)
    if k <= 0: return
    f = anton(int(132 * max(k, 0.15)))
    w = d.textlength(text, font=f); x = (W - w) / 2 + (6 * math.sin(t * 60) if t < 0.5 and idx % 3 == 1 else 0)
    d.text((x + 6, 1196), text, font=f, fill=(0, 0, 0))
    d.text((x, 1190), text, font=f, fill=acc if idx % 2 == 0 else (250, 245, 235))
    ul = ease((t - 0.35) / 0.4) * w
    d.rectangle([(W - w) / 2, 1350, (W - w) / 2 + ul, 1360], fill=acc)

def header(d, p, idx, n, t, sc_d, acc):
    f = C.font(34)
    d.text((70, 92), f"CH {idx + 1:02d}", font=f, fill=acc)
    d.text((220, 92), p["title"][:26], font=f, fill=(225, 225, 230))
    seg = (W - 140) / n
    for i in range(n):
        x0 = 70 + i * seg; fill = 1 if i < idx else (clamp(t / max(sc_d, 0.1)) if i == idx else 0)
        d.rectangle([x0, 150, x0 + seg - 8, 156], fill=(60, 60, 70))
        if fill: d.rectangle([x0, 150, x0 + (seg - 8) * fill, 156], fill=acc)

def scene_frame(p, idx, t):
    sc = p["scenes"][idx]; n = len(p["scenes"]); mood = sc["mood"]; acc = MOODS[mood][2]
    im = background(mood)
    for (x, y, r, sp) in PART:
        yy = (y - t * sp - idx * 140) % (H + 200) - 100
        b = bokeh(acc, r); im.paste(b, (int(x + 20 * math.sin(t + r)), int(yy)), b)
    d = ImageDraw.Draw(im)
    header(d, p, idx, n, t, sc["d"], acc)
    C.draw_visual(d, im, sc["visual"], sc.get("value", ""), t, cy=800)
    label(d, sc["label"], t, acc, idx)
    character(im, mood, t, acc)
    if idx == 0 and t < 2.4:  # cold-open title
        k = ease(t / 0.5) * (1 - ease((t - 1.9) / 0.5))
        ov = Image.new("L", (W, H), 0); ImageDraw.Draw(ov).rectangle([0, 0, W, H], fill=int(150 * k)); im.paste((0, 0, 0), (0, 0), ov)
        f = anton(150); txt = p["title"]; words = txt.split(); lines = [" ".join(words[:max(1, len(words) // 2)]), " ".join(words[max(1, len(words) // 2):])]
        lines = [l for l in lines if l]
        fs = 150
        while fs > 60 and max(d.textlength(l, font=anton(fs)) for l in lines) > W - 120: fs -= 8
        f = anton(fs)
        for li, ln in enumerate(lines):
            w = d.textlength(ln, font=f); d.text(((W - w) / 2, 700 + li * 190 + 40 * (1 - k)), ln, font=f, fill=acc if li else (255, 255, 255))
    return camera(im, idx, t, sc["d"], mood)

def camera(im, idx, t, d, mood):
    z = 1.0 + 0.075 * eio(t / max(d, 0.1)); dx = (1 if idx % 2 else -1) * 28 * eio(t / max(d, 0.1))
    sx = sy = 0
    if mood in ("tense", "excited") and t < 0.45: sx, sy = random.uniform(-14, 14), random.uniform(-14, 14)
    cw, ch = W / z, H / z; x0 = (W - cw) / 2 + dx + sx; y0 = (H - ch) / 2 + sy
    return im.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.BILINEAR)

def outro(p, t):
    acc = MOODS[p["scenes"][-1]["mood"]][2]; im = background(p["scenes"][-1]["mood"]); d = ImageDraw.Draw(im)
    k = C.pop(t / 0.5); f = anton(int(140 * max(k, 0.2)))
    for li, (ln, col) in enumerate([("FOLLOW", (255, 255, 255)), ("FOR MORE", acc)]):
        w = d.textlength(ln, font=f); d.text(((W - w) / 2, 640 + li * 180), ln, font=f, fill=col)
    character(im, "excited", t, acc)
    return im

def transition(a, b, p, kind, acc):
    p = eio(p)
    if kind == 0:
        m = Image.new("L", (W, H), 0); r = p * 1250; ImageDraw.Draw(m).ellipse([W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r], fill=255)
        return Image.composite(b, a, m)
    if kind == 1:
        o = Image.new("RGB", (W, H)); x = int(p * W); o.paste(a, (-x, 0)); o.paste(b, (W - x, 0)); return o
    if kind == 2:
        m = Image.new("L", (W, H), 0); dd = ImageDraw.Draw(m); x = -W + p * W * 2.4
        dd.polygon([(-300, H), (x - 300, H), (x + 600, 0), (-300, 0)], fill=255); o = Image.composite(b, a, m)
        ImageDraw.Draw(o).polygon([(x - 300, H), (x - 230, H), (x + 670, 0), (x + 600, 0)], fill=acc); return o
    if kind == 3:
        src, z = (a, 1 + p * 3) if p < 0.5 else (b, 4 - p * 3)
        cw, ch = W / z, H / z; im = src.crop((int(W / 2 - cw / 2), int(H / 2 - ch / 2), int(W / 2 + cw / 2), int(H / 2 + ch / 2))).resize((W, H))
        return Image.blend(im, Image.new("RGB", (W, H), (255, 255, 255)), (1 - abs(p - 0.5) * 2) * 0.75)
    if kind == 4:
        m = Image.new("L", (W, H), 0); dd = ImageDraw.Draw(m)
        for i in range(9): dd.rectangle([0, i * H / 9, W, i * H / 9 + H / 9 * p], fill=255)
        return Image.composite(b, a, m)
    src = np.array(a if p < 0.5 else b); rng = random.Random(int(p * 100))  # glitch slices + RGB split
    for _ in range(9):
        y = rng.randint(0, H - 80); h = rng.randint(20, 120); src[y:y + h] = np.roll(src[y:y + h], rng.randint(-160, 160), axis=1)
    src[:, :, 0] = np.roll(src[:, :, 0], 14, axis=1); src[:, :, 2] = np.roll(src[:, :, 2], -14, axis=1)
    return Image.fromarray(src)

def frame_at(p, T):
    st = p["starts"]; n = len(st); end = p["voice_end"]
    if T >= end: return outro(p, T - end)
    i = max([k for k in range(n) if st[k] <= T] or [0]); loc = max(0.0, T - st[i])
    nxt = st[i + 1] if i + 1 < n else end
    if i + 1 < n and nxt - T < TR / 2:
        return transition(scene_frame(p, i, loc), scene_frame(p, i + 1, 0), (T - (nxt - TR / 2)) / TR, (i + 1) % 6, MOODS[p["scenes"][i + 1]["mood"]][2])
    if i > 0 and loc < TR / 2:
        return transition(scene_frame(p, i - 1, T - st[i - 1]), scene_frame(p, i, loc), (loc + TR / 2) / TR, i % 6, MOODS[p["scenes"][i]["mood"]][2])
    if i + 1 >= n and end - T < TR / 2:
        return transition(scene_frame(p, i, loc), outro(p, 0), (T - (end - TR / 2)) / TR, 3, (255, 255, 255))
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
async def make_video(brief, chat, notify=None, workdir=None, recent="", workers=None):
    global _P
    wd = workdir or tempfile.mkdtemp(prefix="doc_")
    p = plan(brief, chat, recent)
    voice = VOICES.get((p["lang"], p.get("voice", "male")), VOICES[(p["lang"], "male")])
    if notify: await notify(f"Script ready: {p['title']} ({len(p['scenes'])} scenes, {p['lang']}). Voice, animation, music chestunna.")
    gap = 0.32
    for i, s in enumerate(p["scenes"]):
        a = f"{wd}/vo{i}.mp3"; s["words"] = await tts(s["vo"], voice, s["mood"], a)
        s["audio"] = a; s["adur"] = dur(a); s["d"] = s["adur"] + gap
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
