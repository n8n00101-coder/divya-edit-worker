# video_visuals_example.py — example per-video visual code (v30).
# One vis_<i>(d, w, h, acc, t) per scene. d = PIL ImageDraw on a blank
# 1080x1920 RGBA layer; w=1080, h=1920; acc = accent (r,g,b); t = seconds in.
# Each draws the scene's OWN object — a map, a document, a scale, a chart —
# never a generic shape when a specific object fits. Keep content inside the
# safe box (8% sides, 10% top/bottom). Only math, random, numpy, PIL.
import math
from PIL import ImageFont

WH = (245, 245, 245)
GR = (150, 150, 150)


def _font(size):
    # Fonts live in hark-kit/ (repo root is the working dir); plain "Anton.ttf"
    # is NOT found, and the fallback bitmap font is tiny — always use this path.
    for p in ("hark-kit/Anton.ttf", "Anton.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


# scene 0: a phone with a bell (phantom buzz)
def vis_0(d, w, h, acc, t):
    cx, cy = w // 2, 750
    d.rounded_rectangle([cx - 110, cy - 200, cx + 110, cy + 200], 28, fill=(235, 235, 235))
    d.rounded_rectangle([cx - 95, cy - 170, cx + 95, cy + 160], 14, fill=(28, 28, 32))
    d.pieslice([cx - 40, cy - 60, cx + 40, cy + 20], 180, 360, fill=acc)
    d.polygon([(cx - 40, cy - 20), (cx + 40, cy - 20), (cx + 52, cy + 15), (cx - 52, cy + 15)], fill=acc)
    for k in range(3):
        r = 150 + k * 45 + int(10 * math.sin(t * 3))
        d.arc([cx - r, cy - r, cx + r, cy + r], -40, 40, fill=acc, width=6)
        d.arc([cx - r, cy - r, cx + r, cy + r], 140, 220, fill=acc, width=6)


# scene 1: a counting bar — 89% (dot grid + big number)
def vis_1(d, w, h, acc, t):
    cx = w // 2
    d.text((cx, 560), "89%", font=_font(130), fill=acc, anchor="mm")
    for i in range(20):
        r, c = divmod(i, 10)
        x = cx - 225 + c * 50
        y = 750 + r * 55
        col = acc if i < 18 else (70, 70, 70)
        d.ellipse([x - 16, y - 16, x + 16, y + 16], fill=col)


# scene 2: a document card with real text lines (the rich-visual proof)
def vis_2(d, w, h, acc, t):
    cx = w // 2
    d.rounded_rectangle([cx - 380, 480, cx + 380, 980], 18, fill=(250, 250, 245))
    d.rectangle([cx - 380, 480, cx + 380, 560], fill=acc)
    d.text((cx, 520), "BRAIN NOTE", font=_font(36), fill=(20, 20, 20), anchor="mm")
    for j, y in enumerate((620, 700, 780, 860)):
        d.rectangle([cx - 320, y, cx + 320, y + 14], fill=(120, 120, 120) if j % 2 else (60, 60, 60))


# scene 3: a 3-step checklist
def vis_3(d, w, h, acc, t):
    cx = w // 2
    for j, y in enumerate((560, 720, 880)):
        d.rounded_rectangle([cx - 320, y - 55, cx - 210, y + 55], 14, outline=acc, width=5)
        d.line([cx - 300, y, cx - 270, y + 28, cx - 225, y - 28], fill=acc, width=8)
        d.rectangle([cx - 180, y - 12, cx + 320, y + 12], fill=(90, 90, 90))


# scene 4: three steps with arrows (you decide)
def vis_4(d, w, h, acc, t):
    cx = w // 2
    for j, y in enumerate((560, 720, 880)):
        col = acc if j == 2 else WH
        d.rounded_rectangle([cx - 120, y - 55, cx + 120, y + 55], 16, fill=col)
        d.text((cx, y), str(j + 1), font=_font(64), fill=(20, 20, 20) if j == 2 else (20, 20, 20), anchor="mm")
        if j < 2:
            d.line([cx, y + 60, cx, y + 100], fill=acc, width=6)
            d.polygon([(cx - 16, y + 100), (cx + 16, y + 100), (cx, y + 122)], fill=acc)


# scene 5: a follow card (dot grid + follow)
def vis_5(d, w, h, acc, t):
    cx = w // 2
    for i in range(25):
        r, c = divmod(i, 5)
        x = cx - 200 + c * 100
        y = 560 + r * 90
        d.ellipse([x - 14, y - 14, x + 14, y + 14], fill=acc if (i % 3 == 0) else (70, 70, 70))
    d.text((cx, 1080), "FOLLOW", font=_font(90), fill=WH, anchor="mm")
