# Per-video code for "WHY INDIA BANNED GUTKA AND PAN MASALA" (v32 test fixture).
# Blind interface: tr_(A, B, p) at 1080x1920, fx_(layer, t, start, dur),
# vis_(t, st, d, accent) -> 720x1280 RGBA. Fonts: hark-kit/Anton.ttf, hark-kit/Oswald.ttf.
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def _anton(s):
    return ImageFont.truetype("hark-kit/Anton.ttf", s)

def _oswald(s):
    return ImageFont.truetype("hark-kit/Oswald.ttf", s)

def _eio(x):
    x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)

# Scene change "the ban lands": the new scene stamps down (scales in from
# 1.12 with a red flash) over the old one.
def tr_stamp(A, B, p):
    if p <= 0: return A.copy()
    if p >= 1: return B.copy()
    w, h = A.size
    s = 1.12 - 0.12 * _eio(p)
    nw, nh = int(w * s), int(h * s)
    b = B.resize((nw, nh), Image.BICUBIC)
    out = A.copy()
    out.paste(b, ((w - nw) // 2, (h - nh) // 2))
    if p < 0.25:  # red stamp flash at the start of the cut
        fl = Image.new("RGB", (w, h), (255, 40, 40))
        out = Image.blend(out, fl, 0.25 * (1 - p / 0.25))
    return out

# Hit word "banned": the layer punches (scales 1 -> 1.06 -> 1) on the word.
def fx_stamp(layer, t, start, dur):
    q = max(0.0, min(1.0, (t - start) / max(dur, 0.01)))
    s = 1.0 + 0.06 * math.sin(q * math.pi)
    w, h = layer.size
    nw, nh = int(w * s), int(h * s)
    big = layer.resize((nw, nh), Image.BICUBIC)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(big, ((w - nw) // 2, (h - nh) // 2))
    return out

# Scene 2 "Two packets, one habit": twin RAJ gutka packets, red + green, pop in.
def vis_packet(t, st=0, d=1.0, accent=(255, 210, 0)):
    W, H = 720, 1280
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    k = _eio((t - st) / 0.5)
    if k <= 0: return lay
    # red packet (left), green packet (right), popping in with a slight tilt
    for i, col in enumerate([(200, 40, 40), (40, 160, 60)]):
        x0 = 90 + i * 300
        y0 = int(420 + (1 - k) * 120)
        y1 = int(900 - (1 - k) * 60)
        dr.rounded_rectangle([x0, y0, x0 + 230, y1], 18, fill=col, outline=(255, 255, 255), width=5)
        dr.rectangle([x0 + 20, y0 + 30, x0 + 210, y0 + 70], fill=(255, 255, 255))
        dr.text((x0 + 115, y0 + 170), "RAJ", font=_anton(64), fill=(255, 255, 255), anchor="mm")
        dr.text((x0 + 115, y0 + 250), "GUTKA", font=_oswald(36), fill=(255, 255, 255), anchor="mm")
        dr.text((x0 + 115, y0 + 310), "Rs 30", font=_oswald(40), fill=(255, 220, 0), anchor="mm")
    return lay

# Scene 3 "The bill is bigger than the packet": the receipt, sliding in.
# Gutka x30 Rs 300 / Doctor Rs 4,000 / Tests Rs 9,500 / TOTAL Rs 13,800.
def vis_receipt(t, st=0, d=1.0, accent=(255, 210, 0)):
    W, H = 720, 1280
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    k = _eio((t - st) / 0.5)
    if k <= 0: return lay
    x0, y0, x1, y1 = 90, 300, 630, 980
    dx = int((1 - k) * 300)
    dr.rounded_rectangle([x0 + dx, y0, x1 + dx, y1], 14, fill=(245, 245, 240), outline=(200, 200, 190), width=3)
    dr.text((360 + dx, y0 + 60), "RECEIPT", font=_anton(52), fill=(30, 30, 30), anchor="mm")
    dr.line([(x0 + 30 + dx, y0 + 110), (x1 - 30 + dx, y0 + 110)], fill=(180, 180, 170), width=3)
    rows = [("Gutka x30", "Rs 300"), ("Doctor", "Rs 4,000"), ("Tests", "Rs 9,500")]
    for i, (a, b) in enumerate(rows):
        y = y0 + 180 + i * 90
        dr.text((x0 + 30 + dx, y), a, font=_oswald(40), fill=(40, 40, 40))
        dr.text((x1 - 30 + dx, y), b, font=_oswald(40), fill=(40, 40, 40), anchor="ra")
    dr.line([(x0 + 30 + dx, y0 + 470), (x1 - 30 + dx, y0 + 470)], fill=(180, 180, 170), width=3)
    dr.text((x0 + 30 + dx, y0 + 510), "TOTAL", font=_anton(48), fill=(200, 40, 40))
    dr.text((x1 - 30 + dx, y0 + 510), "Rs 13,800", font=_anton(48), fill=(200, 40, 40), anchor="ra")
    return lay
