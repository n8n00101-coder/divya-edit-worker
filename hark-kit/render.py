import json, math, subprocess, wave, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 720, 1280, 30
CX = W // 2
Y = (255, 210, 31); WH = (245, 245, 245); GR = (90, 90, 90); RD = (235, 60, 60)
AN = "Anton.ttf"; OS = "Oswald.ttf"
_fc = {}
def F(p, s):
    k = (p, int(s))
    if k not in _fc: _fc[k] = ImageFont.truetype(p, max(4, int(s)))
    return _fc[k]
def cl(x): return max(0.0, min(1.0, x))
def ease(t): t = cl(t); return t * t * (3 - 2 * t)
def eob(t):
    t = cl(t); c = 2.2; return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

VO = json.load(open("vo.json"))
GAP = 0.45
DUR = [v["dur"] + GAP for v in VO]; DUR[-1] += 1.8
START = np.cumsum([0] + DUR[:-1]).tolist(); TOTAL = sum(DUR); N = int(TOTAL * FPS)

HEAD = [  # tokens: (word, yellow)
    [("DID", 0), ("YOUR", 0), ("PHONE", 1), ("JUST", 0), ("VIBRATE?", 1)],
    [("YOU", 0), ("CHECK", 0), ("IT.", 0), ("NOTHING.", 1)],
    [("PHANTOM", 1), ("VIBRATION", 1)],
    [("IN", 0), ("ONE", 0), ("STUDY...", 0)],
    [("YOUR", 0), ("BRAIN", 1), ("IS", 0), ("ON", 0), ("ALERT", 1)],
    [("96", 1), ("TIMES", 0), ("A", 0), ("DAY", 0)],
    [("IT", 0), ("LEARNS", 0), ("WHAT", 0), ("YOU", 0), ("REPEAT", 1)],
    [("NEXT", 0), ("TIME,", 0), ("PAUSE.", 1)],
]

# ---------- background texture
rng = np.random.default_rng(3)
yy, xx = np.mgrid[0:H, 0:W]
vig = 1 - 0.55 * (((xx - CX) / W) ** 2 + ((yy - H * 0.45) / H) ** 2) * 2.2
noise = rng.normal(0, 6, (H, W))
base = np.clip((22 + noise) * vig, 0, 255)
BG = Image.fromarray(np.dstack([base, base, base * 1.05]).clip(0, 255).astype(np.uint8)).convert("RGBA")

def logo(d):
    d.ellipse([W - 70, 30, W - 34, 66], fill=Y)
    d.text((W - 52, 48), "D", font=F(AN, 24), fill=(20, 20, 20), anchor="mm")

def headline(d, toks, lt, y0=120):
    size = 66; f = F(AN, size); maxw = 620
    lines, cur, cw = [], [], 0
    for w, yl in toks:
        ww = d.textlength(w + " ", font=f)
        if cur and cw + ww > maxw: lines.append(cur); cur, cw = [], 0
        cur.append((w, yl, ww)); cw += ww
    lines.append(cur)
    k = 0
    for li, ln in enumerate(lines):
        tw = sum(x[2] for x in ln) - d.textlength(" ", font=f); x = CX - tw / 2
        for w, yl, ww in ln:
            p = eob((lt - 0.05 - k * 0.09) / 0.3); a = int(255 * cl((lt - 0.05 - k * 0.09) / 0.12))
            if a > 0:
                fs = F(AN, size * (0.6 + 0.4 * p))
                cxw = x + d.textlength(w, font=f) / 2; cy = y0 + li * 80 + 40
                d.text((cxw + 3, cy + 4), w, font=fs, fill=(0, 0, 0, int(a * .7)), anchor="mm")
                d.text((cxw, cy), w, font=fs, fill=(Y if yl else WH) + (a,), anchor="mm")
            x += ww; k += 1

def captions(d, words, lt):
    groups, g = [], []
    for w in words:
        g.append(w)
        if len(g) == 3 or w[0].endswith((",", ".", "?")): groups.append(g); g = []
    if g: groups.append(g)
    cur = None
    for gi, g in enumerate(groups):
        if lt >= g[0][1] - 0.05: cur = g
    if not cur: return
    f = F(AN, 40); toks = [w[0].upper().strip(",.") for w in cur]
    sp = d.textlength(" ", font=f); tw = sum(d.textlength(t, font=f) for t in toks) + sp * (len(toks) - 1)
    x = CX - tw / 2; y = 1075
    for j, (t, w) in enumerate(zip(toks, cur)):
        ww = d.textlength(t, font=f); on = w[1] - 0.05 <= lt
        nxt = cur[j + 1][1] - 0.05 if j + 1 < len(cur) else 99
        active = w[1] - 0.05 <= lt < nxt
        if active:
            d.rounded_rectangle([x - 8, y - 28, x + ww + 8, y + 30], 6, fill=Y)
            d.text((x, y), t, font=f, fill=(15, 15, 15), anchor="lm")
        else:
            d.text((x + 2, y + 3), t, font=f, fill=(0, 0, 0, 160), anchor="lm")
            d.text((x, y), t, font=f, fill=WH if on else (150, 150, 150), anchor="lm")
        x += ww + sp

# ---------- icon helpers (draw on d, glow layer g)
def phone(d, g, x, y, s, screen="blank", shake=0):
    x += shake
    w, h = 150 * s, 280 * s
    d.rounded_rectangle([x - w/2, y - h/2, x + w/2, y + h/2], int(24 * s), fill=(235, 235, 235))
    d.rounded_rectangle([x - w/2 + 10*s, y - h/2 + 26*s, x + w/2 - 10*s, y + h/2 - 30*s], int(10 * s), fill=(28, 28, 32))
    d.ellipse([x - 9*s, y + h/2 - 23*s, x + 9*s, y + h/2 - 7*s], fill=(150, 150, 150))
    if screen == "bell":
        bell(d, g, x, y - 10*s, 0.9*s)
    if screen == "zero":
        d.text((x, y - 20*s), "0", font=F(AN, 90*s), fill=Y, anchor="mm")
        d.text((x, y + 45*s), "NOTIFICATIONS", font=F(OS, 15*s), fill=(180, 180, 180), anchor="mm")

def bell(d, g, x, y, s, col=Y):
    for L in (d, g):
        L.pieslice([x - 40*s, y - 45*s, x + 40*s, y + 35*s], 180, 360, fill=col)
        L.polygon([(x - 40*s, y - 5*s), (x + 40*s, y - 5*s), (x + 52*s, y + 30*s), (x - 52*s, y + 30*s)], fill=col)
        L.ellipse([x - 12*s, y + 26*s, x + 12*s, y + 48*s], fill=col)

def arcs(d, g, x, y, r0, t, col=Y):
    for k in range(3):
        ph = (t * 2.2 - k * 0.25) % 1
        a = int(255 * (1 - ph)); r = r0 + ph * 70
        for L in (d, g):
            L.arc([x - r, y - r * 1.4, x + r, y + r * 1.4], -40, 40, fill=col + (a,), width=6)
            L.arc([x - r, y - r * 1.4, x + r, y + r * 1.4], 140, 220, fill=col + (a,), width=6)

def stick(d, x, y, s, col=WH, arm="down", head_tilt=0):
    d.ellipse([x - 26*s, y - 150*s, x + 26*s, y - 98*s], fill=col)
    d.rounded_rectangle([x - 30*s, y - 92*s, x + 30*s, y + 10*s], int(14*s), fill=col)
    d.rectangle([x - 26*s, y + 10*s, x - 6*s, y + 100*s], fill=col); d.rectangle([x + 6*s, y + 10*s, x + 26*s, y + 100*s], fill=col)
    if arm == "head":
        d.line([x + 26*s, y - 80*s, x + 55*s, y - 120*s, x + 25*s, y - 140*s], fill=col, width=int(16*s), joint="curve")
        d.rectangle([x - 46*s, y - 85*s, x - 30*s, y], fill=col)
    elif arm == "phone":
        d.line([x + 26*s, y - 80*s, x + 50*s, y - 40*s, x + 30*s, y - 70*s], fill=col, width=int(16*s))
        d.rounded_rectangle([x + 22*s, y - 100*s, x + 50*s, y - 50*s], int(5*s), fill=Y)
        d.rectangle([x - 46*s, y - 85*s, x - 30*s, y], fill=col)
    else:
        d.rectangle([x - 46*s, y - 85*s, x - 30*s, y], fill=col); d.rectangle([x + 30*s, y - 85*s, x + 46*s, y], fill=col)

def brain(d, g, x, y, s, col=(240, 140, 170)):
    for (dx, dy, r) in [(-45, -20, 55), (0, -45, 60), (45, -20, 55), (-30, 25, 50), (30, 25, 50), (0, 10, 50)]:
        d.ellipse([x + (dx - r) * s, y + (dy - r) * s, x + (dx + r) * s, y + (dy + r) * s], fill=col)
    d.line([x, y - 100*s, x, y + 70*s], fill=(200, 100, 130), width=int(5*s))
    for k in range(4):
        d.arc([x - 90*s + k*10*s, y - 60*s + k*22*s, x - 10*s, y - 10*s + k*22*s], 200, 340, fill=(200, 100, 130), width=int(4*s))
        d.arc([x + 10*s, y - 60*s + k*22*s, x + 90*s - k*10*s, y - 10*s + k*22*s], 200, 340, fill=(200, 100, 130), width=int(4*s))

# ---------- scenes: draw(d, g, lt, dur) on content layer
def s0(d, g, lt, D):
    p = eob(lt / 0.5); sh = math.sin(lt * 60) * 9 * (1 if 0.4 < lt else 0)
    phone(d, g, CX, 640, 1.25 * p, "bell", sh)
    if lt > 0.4: arcs(d, g, CX, 640, 120, lt)

def s1(d, g, lt, D):
    stick(d, CX - 120, 760, 1.25, arm="phone")
    p = eob((lt - 0.2) / 0.5); phone(d, g, CX + 110, 610, 1.1 * max(p, .01), "zero")
    if lt > 1.0:
        a = int(255 * cl((lt - 1.0) / 0.2)); r = 34
        d.ellipse([CX + 200 - r, 450 - r, CX + 200 + r, 450 + r], fill=RD + (a,))
        d.line([CX + 186, 436, CX + 214, 464], fill=(255, 255, 255, a), width=7); d.line([CX + 214, 436, CX + 186, 464], fill=(255, 255, 255, a), width=7)

def s2(d, g, lt, D):
    fl = 0.55 + 0.45 * math.sin(lt * 7) ** 2; y = 640 + math.sin(lt * 3) * 12
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
    s = 1.25; w, h = 150 * s, 280 * s
    ld.rounded_rectangle([CX - w/2, y - h/2, CX + w/2, y + h/2], 30, outline=(200, 220, 255, int(230 * fl)), width=6)
    for k in range(5):  # ghost wavy bottom
        ld.ellipse([CX - w/2 + k * w/5, y + h/2 - 15, CX - w/2 + (k + 1) * w/5, y + h/2 + 25], fill=(200, 220, 255, int(110 * fl)))
    ld.ellipse([CX - 40, y - 60, CX - 14, y - 30], fill=(200, 220, 255, int(240 * fl))); ld.ellipse([CX + 14, y - 60, CX + 40, y - 30], fill=(200, 220, 255, int(240 * fl)))
    ld.ellipse([CX - 18, y + 10, CX + 18, y + 50], outline=(200, 220, 255, int(240 * fl)), width=5)
    d._image.alpha_composite(lay); g._image.alpha_composite(lay)
    arcs(d, g, CX, y, 120, lt, (170, 200, 255))
    d.text((CX, 930), "SYNDROME", font=F(OS, 30), fill=(170, 170, 170), anchor="mm")

def s3(d, g, lt, D):
    n = int(89 * ease((lt - 0.6) / 1.6))
    d.text((CX, 330), f"{n}%", font=F(AN, 120), fill=Y, anchor="mm"); g.text((CX, 330), f"{n}%", font=F(AN, 120), fill=Y, anchor="mm")
    for i in range(100):
        r, c = divmod(i, 10); x = CX - 225 + c * 50; y = 470 + r * 50
        pp = eob((lt - 0.1 - i * 0.006) / 0.3); rad = 15 * pp
        if rad <= 0: continue
        col = Y if i < n else (70, 70, 70)
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=col)
        if i < n: g.ellipse([x - rad, y - rad, x + rad, y + rad], fill=col)
    d.text((CX, 990), "OF STUDENTS FELT IT", font=F(OS, 26), fill=(170, 170, 170), anchor="mm")

def s4(d, g, lt, D):
    p = eob(lt / 0.5); brain(d, g, CX - 90, 630, 1.0 * max(p, .01))
    if lt > 1.6:
        pp = eob((lt - 1.6) / 0.4); bell(d, g, CX + 160, 600, 0.9 * pp)
        a = int(255 * cl((lt - 1.6) / 0.3)); arcs(d, g, CX + 160, 600, 70, lt)
    if lt > 2.8:  # itch -> arrow
        a = int(255 * cl((lt - 2.8) / 0.3))
        d.text((CX - 90, 830), "ITCH", font=F(AN, 40), fill=WH + (a,), anchor="mm")
        d.line([CX - 30, 830, CX + 100, 830], fill=Y + (a,), width=6); d.polygon([(CX + 100, 816), (CX + 125, 830), (CX + 100, 844)], fill=Y + (a,))
        d.text((CX + 190, 830), "ALERT!", font=F(AN, 40), fill=Y + (a,), anchor="mm")

def s5(d, g, lt, D):
    n = int(96 * ease((lt - 0.3) / 2.0)); cy = 620; R = 170
    d.ellipse([CX - R, cy - R, CX + R, cy + R], outline=(60, 60, 60), width=22)
    ang = 360 * n / 96
    for L in (d, g): L.arc([CX - R, cy - R, CX + R, cy + R], -90, -90 + ang, fill=Y, width=22)
    d.text((CX, cy - 10), f"×{n}", font=F(AN, 110), fill=Y, anchor="mm"); g.text((CX, cy - 10), f"×{n}", font=F(AN, 110), fill=Y, anchor="mm")
    d.text((CX, cy + 75), "CHECKS / DAY", font=F(OS, 24), fill=(170, 170, 170), anchor="mm")

def s6(d, g, lt, D):
    cy = 640; p = eob(lt / 0.5)
    brain(d, g, CX - 150, cy, 0.7 * max(p, .01)); phone(d, g, CX + 160, cy, 0.75 * max(p, .01), "bell")
    a0 = lt * 160
    for k in range(2):
        st = a0 + k * 180
        for L in (d, g): L.arc([CX - 210, cy - 200, CX + 210, cy + 200], st, st + 120, fill=Y, width=8)
        ang = math.radians(st + 120); ax, ay = CX + 210 * math.cos(ang), cy + 200 * math.sin(ang)
        tx, ty = -math.sin(ang), math.cos(ang)
        d.polygon([(ax + tx * 22, ay + ty * 22), (ax - ty * 14, ay + tx * 14), (ax + ty * 14, ay - tx * 14)], fill=Y)
    d.text((CX, 900), "REPEAT  →  HABIT", font=F(AN, 40), fill=WH, anchor="mm")

def s7(d, g, lt, D):
    p = eob(lt / 0.5); stick(d, CX - 70, 760, 1.25 * max(p, .01), arm="head")
    if lt > 0.6:
        pp = eob((lt - 0.6) / 0.4); phone(d, g, CX + 150, 560, 0.6 * max(pp, .01), "blank", math.sin(lt * 50) * 4)
    if lt > 1.4:
        q = eob((lt - 1.4) / 0.4)
        d.text((CX + 150, 380), "?", font=F(AN, int(110 * max(q, .05))), fill=Y, anchor="mm"); g.text((CX + 150, 380), "?", font=F(AN, int(110 * max(q, .05))), fill=Y, anchor="mm")
    end = D - 1.9
    if lt > end:  # end card
        a = int(235 * cl((lt - end) / 0.3))
        d.rectangle([0, 0, W, H], fill=(18, 18, 18, a))
        k = eob((lt - end - 0.1) / 0.4)
        if k > 0:
            d.text((CX, 560), "FOLLOW", font=F(AN, int(90 * max(k, .05))), fill=WH, anchor="mm")
            d.text((CX, 660), "FOR MORE", font=F(AN, int(90 * max(k, .05))), fill=Y, anchor="mm"); g.text((CX, 660), "FOR MORE", font=F(AN, int(90 * max(k, .05))), fill=Y, anchor="mm")
            d.text((CX, 760), "BRAIN FACTS", font=F(OS, 34), fill=(180, 180, 180), anchor="mm")

SC = [s0, s1, s2, s3, s4, s5, s6, s7]

def frame(i):
    t = i / FPS
    si = max(k for k in range(len(START)) if START[k] <= t + 1e-9); lt = t - START[si]; D = DUR[si]
    im = BG.copy()
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay, "RGBA"); g = ImageDraw.Draw(gl, "RGBA")
    SC[si](d, g, lt, D)
    end_card = si == 7 and lt > D - 1.9
    if not end_card:
        headline(d, HEAD[si], lt)
        captions(d, VO[si]["words"], lt)
    # push-in
    z = 1 + 0.035 * lt / D
    if z != 1:
        lay = lay.resize((int(W * z), int(H * z))).crop((int(W * (z - 1) / 2), int(H * (z - 1) / 2), int(W * (z - 1) / 2) + W, int(H * (z - 1) / 2) + H))
        gl = gl.resize((int(W * z), int(H * z))).crop((int(W * (z - 1) / 2), int(H * (z - 1) / 2), int(W * (z - 1) / 2) + W, int(H * (z - 1) / 2) + H))
    # transitions: slide-in from below + fade
    off = int(90 * (1 - ease(lt / 0.22))) if si > 0 else 0
    alpha = ease(lt / 0.18) if si > 0 else 1
    if si < 7 and lt > D - 0.12:
        off = -int(60 * ease((lt - (D - 0.12)) / 0.12)); alpha = 1 - ease((lt - (D - 0.12)) / 0.12)
    gb = gl.filter(ImageFilter.GaussianBlur(14))
    for L in (gb, lay):
        if alpha < 1:
            a = L.getchannel("A").point(lambda v: int(v * alpha)); L.putalpha(a)
        im.alpha_composite(L, (0, off))
    d2 = ImageDraw.Draw(im); logo(d2)
    d2.text((CX, 1230), "DIVYA EXPLAINS", font=F(OS, 16), fill=(110, 110, 110), anchor="mm")
    return im.convert("RGB")

def audio(path):
    sr = 44100; n = int(sr * TOTAL) + sr; out = np.zeros(n); t = np.arange(n) / sr
    # music bed: dark pulse 100bpm
    beat = 60 / 100
    for b in np.arange(0, TOTAL - 1, beat):
        i0 = int(b * sr); L = int(0.3 * sr); tt = np.arange(L) / sr
        out[i0:i0 + L] += 0.25 * np.sin(2 * np.pi * (50 + 70 * np.exp(-tt * 35)) * tt) * np.exp(-tt * 10)
    for b in np.arange(beat / 2, TOTAL - 1, beat):
        i0 = int(b * sr); L = int(0.05 * sr)
        out[i0:i0 + L] += 0.03 * rng.standard_normal(L) * np.exp(-np.arange(L) / L * 6)
    pad = sum(np.sin(2 * np.pi * f * t) for f in (110, 164.8, 220)) * 0.025 * (0.7 + 0.3 * np.sin(2 * np.pi * 0.2 * t))
    out += pad
    sfx = np.zeros(n)
    for k, st in enumerate(START):
        if k > 0:  # whoosh
            i0 = int((st - 0.25) * sr); L = int(0.5 * sr); nz = np.convolve(rng.standard_normal(L), np.ones(25) / 25, "same")
            sfx[i0:i0 + L] += 0.9 * nz * np.sin(np.pi * np.arange(L) / L) ** 2
        for j in range(len(HEAD[k])):  # pops
            i0 = int((st + 0.05 + j * 0.09) * sr); L = int(0.06 * sr); tt = np.arange(L) / sr
            sfx[i0:i0 + L] += 0.12 * np.sin(2 * np.pi * 900 * tt * (1 - tt * 4)) * np.exp(-tt * 60)
    voice = np.zeros(n)
    for k, st in enumerate(START):
        raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", f"vo{k}.mp3", "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"])
        v = np.frombuffer(raw, np.int16) / 32768.0; i0 = int((st + 0.05) * sr); voice[i0:i0 + len(v)] += v[: n - i0]
    duck = np.convolve((np.abs(voice) > 0.02).astype(float), np.ones(int(0.2 * sr)) / (0.2 * sr), "same")
    mix = (out + sfx * 0.6) / max(1e-6, np.max(np.abs(out + sfx * 0.6))) * 0.35 * (1 - 0.45 * np.clip(duck * 3, 0, 1)) + voice * 1.0
    mix[: int(TOTAL * sr)] *= 1; mix = mix[: int(TOTAL * sr)]
    fade = np.clip((TOTAL - np.arange(len(mix)) / sr) / 0.8, 0, 1); mix *= fade
    mix = mix / np.max(np.abs(mix)) * 0.92
    with wave.open(path, "wb") as wv:
        wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(sr); wv.writeframes((mix * 32767).astype(np.int16).tobytes())

if __name__ == "__main__":
    if len(sys.argv) > 1:
        ts = [float(x) for x in sys.argv[1:]]
        ims = [frame(int(x * FPS)).resize((240, 427)) for x in ts]
        c = Image.new("RGB", (240 * len(ims), 427)); [c.paste(m, (k * 240, 0)) for k, m in enumerate(ims)]; c.save("prev.png"); sys.exit()
    audio("mix.wav")
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-i", "mix.wav", "-af", "loudnorm=I=-14:TP=-1:LRA=11", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                          "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", "phantom_vibration.mp4"], stdin=subprocess.PIPE)
    for i in range(N): p.stdin.write(frame(i).tobytes())
    p.stdin.close(); p.wait(); print("done", p.returncode, round(TOTAL, 2))
