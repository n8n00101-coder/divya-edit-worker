# Per-video code for "WHY YOUR PHONE STEALS YOUR SLEEP" (v32 test fixture).
# Blind interface: tr_(A, B, p) at 1080x1920, fx_(layer, t, start, dur),
# vis_(t, st, d, accent) -> 720x1280 RGBA. Fonts: hark-kit/Anton.ttf, hark-kit/Oswald.ttf.
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from transitions_lib import _mix, _grid, EASES

def _anton(s):
    return ImageFont.truetype("hark-kit/Anton.ttf", s)

def _oswald(s):
    return ImageFont.truetype("hark-kit/Oswald.ttf", s)

def _eio(x):
    x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)

def _p(t, start, dur):
    return max(0.0, min(1.0, (t - start) / max(dur, 0.01)))

# Scene change "your eyes close": eyelids sweep shut, then open on the new scene.
def tr_eyelids(A, B, p):
    if p <= 0: return A.copy()
    if p >= 1: return B.copy()
    w, h = A.size; x, y = _grid(w, h); src = A if p < .5 else B
    k = math.sin(math.pi * p)                                    # 0 -> 1 (closed) -> 0
    lid = np.abs(y - .5) * 2 + .25 * ((x - .5) * 2) ** 2         # curved lid shape
    m = (lid > (1 - k)).astype(np.float32)
    dark = Image.new("RGB", (w, h), (8, 8, 14))
    return _mix(src, dark, np.clip(m, 0, 1))

# Hit word "8 hours": the layer breathes slowly like a sleeping chest.
def fx_breathe(layer, t, start, dur):
    q = _p(t, start, dur); s = 1 + .04 * math.sin(q * math.pi * 2)
    w, h = layer.size
    nw, nh = int(w * s), int(h * s)
    big = layer.resize((nw, nh), Image.BICUBIC)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(big, ((w - nw) // 2, (h - nh) // 2))
    return out

# Scene 1 "Your phone glows at two AM": a bed with a glowing phone, glow grows.
def vis_bed_phone(t, st=0, d=1.0, accent=(255, 210, 0)):
    W, H = 720, 1280
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    k = _eio((t - st) / 0.6)
    if k <= 0: return lay
    # the bed (headboard + mattress + pillow)
    dr.rounded_rectangle([90, 700, 630, 980], 20, fill=(40, 60, 120))
    # v36 (Blind C2 — real objects with depth): the pillow is SHADED, not
    # flat white — a vertical gradient (light top-left, shadow bottom-right),
    # a soft shadow beneath it, and a fold/crease line.
    _pw, _ph = 190, 100
    _pg = Image.new("RGBA", (_pw, _ph), (0, 0, 0, 0))
    _top = np.array([245, 245, 250], dtype=np.float32); _bot = np.array([178, 184, 200], dtype=np.float32)
    _yy = np.linspace(0, 1, _ph)[:, None, None]
    _g = (_top * (1 - _yy) + _bot * _yy).astype(np.uint8)
    _pg = Image.fromarray(np.repeat(_g, _pw, axis=1), "RGB").convert("RGBA")
    _mask = Image.new("L", (_pw, _ph), 0)
    ImageDraw.Draw(_mask).rounded_rectangle([0, 0, _pw, _ph], 16, fill=255)
    _pg.putalpha(_mask)
    dr.rounded_rectangle([116, 626, 306, 726], 16, fill=(0, 0, 0, 90))  # soft shadow under the pillow
    lay.alpha_composite(_pg, (110, 620))
    dr.arc([130, 640, 280, 700], 20, 160, fill=(150, 155, 170, 255), width=3)  # fold/crease
    dr.rounded_rectangle([90, 700, 630, 760], 12, fill=(90, 140, 200))
    # the phone, glowing — the glow grows with k
    gx, gy = 420, 560
    r = int(60 + 140 * k)
    for rr in range(r, 20, -30):
        dr.ellipse([gx - rr, gy - rr, gx + rr, gy + rr], fill=(80, 160, 255, 40))
    dr.rounded_rectangle([gx - 55, gy - 100, gx + 55, gy + 100], 14, fill=(20, 20, 30), outline=(150, 200, 255), width=4)
    dr.rectangle([gx - 40, gy - 80, gx + 40, gy + 60], fill=(120, 180, 255))
    # v36 (Blind C2): the phone screen LIGHTS the scene — a soft blue pool
    # on the mattress below the phone, growing with the glow.
    for rr in range(int(120 * k), 20, -25):
        dr.ellipse([gx - rr, 740 - rr // 3, gx + rr, 740 + rr // 3], fill=(80, 160, 255, 22))
    # v33: no "2 AM" text here — the label already says "2 AM" (Ajju: the
    # visual's text duplicated the label, not accurate).
    return lay

# Scene 2 "The moon is up, but so are you": crescent moon + 5 stars, fading in.
def vis_moon(t, st=0, d=1.0, accent=(255, 210, 0)):
    W, H = 720, 1280
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    k = _eio((t - st) / 0.7)
    if k <= 0: return lay
    a = int(255 * k)
    cx, cy = 360, 560
    # crescent: a yellow disc with a shifted disc cut out (via a mask)
    moon = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(moon)
    md.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], fill=a)
    md.ellipse([cx - 60, cy - 170, cx + 170, cy + 130], fill=0)
    col = Image.new("RGBA", (W, H), (245, 220, 120, 255))
    lay.paste(col, (0, 0), moon)
    for i, (sx, sy) in enumerate([(120, 300), (560, 260), (620, 700), (90, 820), (540, 950)]):
        r = 14 + 6 * math.sin(t * 2 + i)
        dr.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(255, 255, 255, a))
    return lay

# Scene 4 "Eight hours is the prescription": a clock, 10 PM to 6 AM, hour hand sweeps.
# Built on a sub-layer and placed (a full-layer redraw per frame is wasteful).
# v36 (Blind B2 — story-synced): the hand sweeps 10 PM -> 6 AM over the first
# 70% of the scene, THEN jumps back to 10 PM as the phone lights up (the
# phone glow brightens for the last 30% — the screen stealing the sleep back).
def vis_clock(t, st=0, d=1.0, accent=(255, 210, 0)):
    W, H = 720, 1280
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    k = _eio((t - st) / 0.5)
    if k <= 0: return lay
    # sub-layer: the clock face
    S = 420
    sub = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sub)
    c = S // 2
    sd.ellipse([20, 20, S - 20, S - 20], outline=(255, 255, 255), width=10)
    for i in range(12):
        an = i * math.pi / 6
        sd.line([(c + 160 * math.sin(an), c - 160 * math.cos(an)),
                 (c + 180 * math.sin(an), c - 180 * math.cos(an))], fill=(200, 200, 200), width=6)
    # hour hand sweeps from 10 PM to 6 AM as the scene plays (v33: it used
    # to start at 12 and end at ~8 — not the sleep window. 10 is at -5pi/6,
    # 6 is at pi/2; the sweep is 4pi/3 = 8 hours.) v36: the sweep finishes
    # at 70% of the scene; then the hand JUMPS BACK to 10 PM (the phone
    # lights up and steals the sleep again).
    q = _p(t, st, d)
    if q < 0.7:
        ha = -5 * math.pi / 6 + (q / 0.7) * 4 * math.pi / 3
    else:
        ha = -5 * math.pi / 6
    sd.line([(c, c), (c + 120 * math.cos(ha), c + 120 * math.sin(ha))], fill=(255, 210, 0), width=12)
    sd.line([(c, c), (c + 170 * math.cos(-math.pi / 2 + 0.3), c + 170 * math.sin(-math.pi / 2 + 0.3))], fill=(255, 255, 255), width=8)
    sd.ellipse([c - 14, c - 14, c + 14, c + 14], fill=(255, 210, 0))
    lay.alpha_composite(sub, ((W - S) // 2, 480))
    dr = ImageDraw.Draw(lay)
    # v33: no "8 HOURS" text here — the label already says it. "10 PM - 6 AM"
    # stays (it is different info: the sleep window).
    dr.text((360, 1090), "10 PM - 6 AM", font=_oswald(40), fill=(220, 220, 220), anchor="mm")
    # v36: after the jump-back, the phone lights up below the clock — a
    # glowing phone screen (the sleep thief), brightening over the last 30%.
    if q >= 0.7:
        gq = _eio((q - 0.7) / 0.3)
        gx, gy = 360, 1180
        for rr in range(int(30 + 90 * gq), 10, -20):
            dr.ellipse([gx - rr, gy - rr, gx + rr, gy + rr], fill=(80, 160, 255, int(50 * gq)))
        dr.rounded_rectangle([gx - 34, gy - 58, gx + 34, gy + 58], 10, fill=(20, 20, 30), outline=(150, 200, 255), width=3)
        dr.rectangle([gx - 24, gy - 44, gx + 24, gy + 40], fill=(120, 180, 255, int(255 * gq)))
    return lay
