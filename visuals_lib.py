"""
Divya rich visuals v30 - real-looking OBJECTS drawn in code (pure PIL + numpy), animated.
Same interface as motion_graphics.py:  vis_<name>(t, st=0, d=1.0, **opts) -> RGBA layer 720x1280.
These are building blocks AND examples: Divya's LLM should copy the method (shapes + text + shadow +
paper texture + one accent), then write NEW vis_ functions for objects of each new topic.

    from visuals_lib import VIS
    layer = VIS["india_map"](t, st=1.0, d=1.2, pins=[("Delhi",77.2,28.6)], fill_states=True)

Methods used (the "recipe" for any rich visual):
 1. silhouette  : polygon / rounded rect for the object's outline
 2. material    : flat colour + subtle noise texture (paper, plastic, metal)
 3. detail      : 2-4 inner lines/text that make it recognisable (headline, label, ruled lines)
 4. depth       : soft drop shadow (blurred dark copy offset 8-14 px)
 5. accent      : ONE element in the video accent colour (highlight, stamp, pin)
 6. motion      : build-in (pop / slide / draw-on) driven by p = progress 0..1
"""
import math, random, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

W, H = 720, 1280
SAFE = (int(W*.08), int(H*.10), int(W*.92), int(H*.90))
HERE = os.path.dirname(os.path.abspath(__file__))
Y = (255, 210, 0); WHITE = (255, 255, 255); INK = (30, 30, 34); RED = (225, 60, 60)
PAPER = (244, 238, 222); NEWS = (236, 233, 226)

def _font(size, kind="big"):
    files = {"big": "Anton.ttf", "small": "Oswald.ttf",
             "serif": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
             "serif_r": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
             "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"}
    f = files[kind]; f = f if os.path.isabs(f) else os.path.join(HERE, f)
    try: return ImageFont.truetype(f, size)
    except Exception: return ImageFont.load_default()
def _c(x): return max(0.0, min(1.0, x))
def _p(t, st, d): return _c((t-st)/d) if d > 0 else float(t >= st)
def _oe(x): return 1-(1-_c(x))**3
def _ob(x, s=1.70158): x = _c(x)-1; return 1+(s+1)*x**3+s*x**2
def _L(): return Image.new("RGBA", (W, H), (0, 0, 0, 0))

def texture(img, amount=10, seed=3):
    """Paper / plastic grain on an RGBA image (keeps alpha)."""
    a = np.asarray(img).astype(np.int16); rng = np.random.default_rng(seed)
    n = rng.integers(-amount, amount+1, a.shape[:2])[..., None]
    a[..., :3] = np.clip(a[..., :3]+n, 0, 255); return Image.fromarray(a.astype(np.uint8), "RGBA")

def shadow(obj, off=(10, 14), blur=14, alpha=150):
    """Return obj with a soft drop shadow under it (same size)."""
    a = obj.split()[3].point(lambda v: v*alpha//255)
    sh = Image.new("RGBA", obj.size, (0, 0, 0, 0)); sh.putalpha(a)
    sh = sh.filter(ImageFilter.GaussianBlur(blur)); out = Image.new("RGBA", obj.size, (0, 0, 0, 0))
    out.alpha_composite(sh, off); out.alpha_composite(obj); return out

def place(obj, cx, cy, scale=1.0, rot=0.0, alpha=1.0):
    """Put an RGBA object on a full-frame layer, centred at cx,cy."""
    L = _L()
    if scale <= 0.01 or alpha <= 0: return L
    o = obj
    if abs(scale-1) > 1e-3: o = o.resize((max(1, int(o.width*scale)), max(1, int(o.height*scale))), Image.BICUBIC)
    if abs(rot) > .05: o = o.rotate(rot, expand=True, resample=Image.BICUBIC)
    if alpha < 1: o.putalpha(o.split()[3].point(lambda v: int(v*alpha)))
    L.alpha_composite(o, (int(cx-o.width/2), int(cy-o.height/2))); return L

def wrap(text, font, width, draw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur+" "+w).strip()
        if draw.textlength(test, font=font) <= width: cur = test
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

VIS = {}
def reg(name, tags):
    def deco(fn): fn.tags = set(tags); VIS[name] = fn; return fn
    return deco

# ============================ MAPS ============================
INDIA = [(68.2,23.7),(70.0,20.8),(72.8,19.0),(73.4,16.0),(74.6,12.8),(76.3,9.5),(77.5,8.1),(78.2,9.0),(79.9,10.3),
 (80.3,13.0),(80.1,15.5),(82.3,17.0),(84.8,19.3),(86.9,21.3),(88.2,21.7),(89.0,22.0),(88.7,24.3),(89.8,25.9),(92.0,25.0),
 (92.6,22.0),(93.4,24.0),(94.6,25.6),(95.3,26.8),(97.3,28.0),(96.0,29.3),(94.0,28.9),(92.0,27.8),(89.7,26.8),(88.2,27.9),
 (85.0,27.4),(82.0,28.5),(80.1,30.2),(78.9,31.5),(78.4,32.6),(79.4,34.0),(77.8,35.5),(76.0,35.9),(74.5,34.6),(73.8,33.3),
 (74.6,32.0),(73.9,30.4),(72.0,28.5),(70.4,27.9),(69.5,26.5),(70.6,25.5),(69.2,24.3)]
def _proj(lon, lat, box=(90, 260, 630, 1000), lon0=67.5, lon1=98.0, lat0=7.5, lat1=36.5):
    x0, y0, x1, y1 = box; s = min((x1-x0)/(lon1-lon0), (y1-y0)/(lat1-lat0))
    ox = x0+((x1-x0)-s*(lon1-lon0))/2; oy = y0+((y1-y0)-s*(lat1-lat0))/2
    return ox+(lon-lon0)*s, oy+(lat1-lat)*s

@reg("india_map", ["map", "india", "country", "ban", "law", "places", "geography"])
def vis_india_map(t, st=0, d=1.2, pins=(("Delhi", 77.2, 28.6),), accent=Y, land=(58, 66, 84), outline=WHITE, label="INDIA"):
    """Outline draws on, land fills, pins drop one by one."""
    L = _L(); dr = ImageDraw.Draw(L); q = _p(t, st, d)
    pts = [_proj(*p) for p in INDIA]; n = len(pts)
    if q > .45: dr.polygon(pts, fill=land+(int(255*_oe((q-.45)/.3)),))
    k = int(n*_oe(min(1, q/.5)))+1                      # draw-on outline
    dr.line(pts[:k]+([pts[0]] if k > n else []), fill=outline+(255,), width=4, joint="curve")
    f = _font(30, "small")
    for i, (name, lon, lat) in enumerate(pins):
        pq = _p(t, st+d*.6+i*.25, .35)
        if pq <= 0: continue
        x, y = _proj(lon, lat); drop = (1-_ob(pq))*60; r = 16
        dr.ellipse((x-r*2.2, y-r*.6, x+r*2.2, y+r*.6), fill=(0, 0, 0, 90))
        dr.polygon([(x, y-drop), (x-r, y-2*r-drop), (x+r, y-2*r-drop)], fill=accent+(255,))
        dr.ellipse((x-r, y-3*r-drop, x+r, y-r-drop), fill=accent+(255,)); dr.ellipse((x-6, y-2*r-6-drop, x+6, y-2*r+6-drop), fill=INK+(255,))
        dr.text((x+r+8, y-2*r-drop), name, font=f, fill=WHITE+(int(255*pq),), anchor="lm")
    if label: dr.text((W/2, 220), label, font=_font(64), fill=WHITE+(int(255*_c(q*2)),), anchor="mm")
    return L

@reg("world_dots", ["map", "world", "global", "countries", "spread"])
def vis_world_dots(t, st=0, d=1.5, hot=((77, 22), (-100, 40), (10, 50)), accent=Y, seed=4):
    """Dotted world map (rough continents from ellipses) with pulsing hot spots."""
    L = _L(); dr = ImageDraw.Draw(L); q = _p(t, st, d)
    blobs = [(-100, 45, 32, 20), (-60, -15, 16, 24), (15, 50, 22, 12), (20, 5, 18, 26), (90, 45, 45, 18), (80, 22, 9, 10), (135, -25, 16, 10)]
    x0, x1, y0, y1 = 60, 660, 470, 830
    for lon in range(-170, 180, 6):
        for lat in range(-55, 75, 6):
            inside = any(((lon-a)/b)**2+((lat-c)/e)**2 < 1 for a, c, b, e in blobs)
            if not inside: continue
            x = x0+(lon+180)/360*(x1-x0); y = y0+(75-lat)/130*(y1-y0)
            if (x-x0)/(x1-x0) > q*1.2: continue
            dr.ellipse((x-3, y-3, x+3, y+3), fill=(200, 205, 220, 170))
    for i, (lon, lat) in enumerate(hot):
        hq = _p(t, st+d*.7+i*.2, .5)
        if hq <= 0: continue
        x = x0+(lon+180)/360*(x1-x0); y = y0+(75-lat)/130*(y1-y0); r = 8+28*((t*1.2+i*.3) % 1)
        dr.ellipse((x-r, y-r, x+r, y+r), outline=accent+(int(200*(1-((t*1.2+i*.3) % 1))),), width=3)
        dr.ellipse((x-8, y-8, x+8, y+8), fill=accent+(255,))
    return L

# ============================ PAPER ============================
def _doc_obj(title, lines, stamp, accent, w=520, h=680, highlight=1, seal=True):
    o = Image.new("RGBA", (w, h), PAPER+(255,)); dr = ImageDraw.Draw(o)
    dr.rectangle((0, 0, w-1, h-1), outline=(200, 190, 170, 255), width=2)
    if seal: dr.ellipse((w/2-34, 30, w/2+34, 98), outline=INK+(255,), width=3); dr.text((w/2, 64), "GOI", font=_font(22, "serif"), fill=INK+(255,), anchor="mm")
    dr.text((w/2, 130), title, font=_font(30, "serif"), fill=INK+(255,), anchor="mm")
    dr.line((40, 160, w-40, 160), fill=INK+(255,), width=2)
    f = _font(21, "serif_r"); y = 185
    for i, ln in enumerate(lines):
        for sub in wrap(ln, f, w-80, dr):
            if i == highlight: dr.rectangle((36, y-2, 44+dr.textlength(sub, font=f), y+26), fill=accent+(150,))
            dr.text((40, y), sub, font=f, fill=INK+(255,)); y += 32
        y += 10
    for k in range(int((h-110-y)/32)): dr.line((40, y+k*32+14, w-40-(k*37 % 120), y+k*32+14), fill=(170, 165, 150, 255), width=6)
    dr.line((w-210, h-70, w-50, h-70), fill=INK+(255,), width=2); dr.text((w-130, h-50), "Signature", font=_font(16, "serif_r"), fill=INK+(255,), anchor="mm")
    return texture(o, 8)

@reg("document", ["law", "rule", "ban", "government", "report", "study", "paper", "official"])
def vis_document(t, st=0, d=1.0, title="NOTIFICATION", lines=("Sale of gutka and pan masala is prohibited.", "Ban applies to all states from 2012.", "Violators face fines and jail."),
                 stamp="BANNED", accent=Y, highlight=0, cx=W/2, cy=640):
    """Official paper slides up, the key line gets highlighted, a red stamp slams down."""
    q = _p(t, st, d*.5); doc = _doc_obj(title, lines, stamp, accent, highlight=highlight)
    L = place(shadow(doc), cx, cy+(1-_oe(q))*500, rot=-2*(1-_oe(q)))
    sq = _p(t, st+d*.7, .25)
    if stamp and sq > 0:
        s = Image.new("RGBA", (360, 120), (0, 0, 0, 0)); ds = ImageDraw.Draw(s)
        ds.rounded_rectangle((4, 4, 356, 116), 14, outline=RED+(255,), width=8)
        ds.text((180, 60), stamp, font=_font(70), fill=RED+(255,), anchor="mm")
        s = texture(s, 40, 9); L.alpha_composite(place(s, cx+60, cy+180, scale=2.2-1.2*_oe(sq), rot=-14, alpha=_c(sq*3)))
    return L

@reg("newspaper", ["news", "media", "headline", "story", "report", "history"])
def vis_newspaper(t, st=0, d=1.0, paper="THE DAILY TIMES", headline="Study finds men look first", photo=None, date="NOV 11, 2026", accent=Y, cx=W/2, cy=640):
    """Newspaper spins in (classic film move), with masthead, headline, photo and columns."""
    w, h = 560, 760; o = Image.new("RGBA", (w, h), NEWS+(255,)); dr = ImageDraw.Draw(o)
    dr.text((w/2, 50), paper, font=_font(44, "serif"), fill=INK+(255,), anchor="mm")
    dr.line((24, 86, w-24, 86), fill=INK+(255,), width=3); dr.text((30, 96), date, font=_font(16, "serif_r"), fill=INK+(255,))
    dr.line((24, 120, w-24, 120), fill=INK+(255,), width=1)
    fy = 132
    for ln in wrap(headline.upper(), _font(46), w-48, dr): dr.text((w/2, fy), ln, font=_font(46), fill=INK+(255,), anchor="ma"); fy += 54
    ph = (24, fy+10, w-24, fy+300)
    if photo and os.path.exists(photo):
        im = ImageOps.fit(Image.open(photo).convert("L").convert("RGBA"), (ph[2]-ph[0], ph[3]-ph[1])); o.alpha_composite(im, ph[:2])
    else:
        dr.rectangle(ph, fill=(120, 120, 120, 255)); cxp = (ph[0]+ph[2])/2
        dr.ellipse((cxp-55, ph[1]+60, cxp+55, ph[1]+170), fill=(70, 70, 70, 255)); dr.pieslice((cxp-120, ph[1]+180, cxp+120, ph[3]+140), 180, 360, fill=(70, 70, 70, 255))
    y = ph[3]+20; colw = (w-48-20)/3
    for c in range(3):
        for k in range(int((h-20-y)/18)):
            x0 = 24+c*(colw+10); dr.line((x0, y+k*18, x0+colw-(k*13 % 40 if k % 5 == 4 else 0), y+k*18), fill=(110, 110, 110, 255), width=7)
    o = texture(o, 9); q = _p(t, st, d)
    return place(shadow(o), cx, cy, scale=.15+.85*_oe(q), rot=(1-_oe(q))*720, alpha=_c(q*3))

@reg("typewriter_page", ["history", "old", "letter", "secret", "file", "quote"])
def vis_typewriter(t, st=0, d=None, text="CLASSIFIED: subjects did not notice the swap.", cps=18, accent=Y, cx=W/2, cy=640):
    """Old paper, mono text typed letter by letter with a blinking caret."""
    w, h = 560, 420; o = Image.new("RGBA", (w, h), (236, 226, 200, 255)); dr = ImageDraw.Draw(o)
    f = _font(30, "mono"); n = int(max(0, t-st)*cps); shown = text[:n]; y = 40
    for ln in wrap(shown, f, w-60, dr) or [""]:
        dr.text((30, y), ln, font=f, fill=(35, 30, 25, 255)); y += 42
    if int(t*2) % 2 == 0 and n < len(text)+10:
        lw = dr.textlength((wrap(shown, f, w-60, dr) or [""])[-1], font=f); dr.rectangle((32+lw, y-40, 48+lw, y-8), fill=(35, 30, 25, 255))
    return place(shadow(texture(o, 14)), cx, cy)

@reg("receipt", ["money", "bill", "price", "shopping", "cost"])
def vis_receipt(t, st=0, d=1.0, items=(("Gutka x30", "Rs 300"), ("Doctor", "Rs 4,000"), ("Tests", "Rs 9,500")), total="Rs 13,800", accent=Y, cx=W/2, cy=640):
    """Receipt prints out from the top, line by line, total highlighted."""
    w = 420; h = 160+len(items)*56+120; o = Image.new("RGBA", (w, h), (250, 250, 248, 255)); dr = ImageDraw.Draw(o)
    for x in range(0, w, 20): dr.polygon([(x, h), (x+10, h-12), (x+20, h)], fill=(0, 0, 0, 0))
    dr.text((w/2, 50), "RECEIPT", font=_font(40, "mono"), fill=INK+(255,), anchor="mm")
    f = _font(26, "mono"); y = 120
    for a, b in items: dr.text((30, y), a, font=f, fill=INK+(255,)); dr.text((w-30, y), b, font=f, fill=INK+(255,), anchor="ra"); y += 56
    dr.line((30, y, w-30, y), fill=INK+(255,), width=2); dr.rectangle((24, y+20, w-24, y+80), fill=accent+(255,))
    dr.text((30, y+50), "TOTAL", font=f, fill=INK+(255,), anchor="lm"); dr.text((w-30, y+50), total, font=f, fill=INK+(255,), anchor="rm")
    q = _oe(_p(t, st, d)); shown = o.crop((0, 0, w, max(1, int(h*q))))
    L = _L(); L.alpha_composite(shadow(texture(shown, 6)), (int(cx-w/2), int(cy-h/2))); return L

# ============================ PRODUCTS / OBJECTS ============================
def _packet(brand, sub, col, w=230, h=330, seed=1):
    o = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dr = ImageDraw.Draw(o)
    dr.rounded_rectangle((0, 18, w, h-18), 16, fill=col+(255,))
    for yy in (0, h-26):                                         # crimped seal edges
        for x in range(0, w, 12): dr.polygon([(x, yy+26 if yy == 0 else yy), (x+6, yy if yy == 0 else yy+26), (x+12, yy+26 if yy == 0 else yy)], fill=tuple(int(c*.8) for c in col)+(255,))
    dr.ellipse((w/2-80, h/2-90, w/2+80, h/2+20), fill=(255, 240, 200, 255))
    dr.text((w/2, h/2-35), brand, font=_font(46), fill=col+(255,), anchor="mm")
    dr.text((w/2, h/2+60), sub, font=_font(22, "small"), fill=WHITE+(255,), anchor="mm")
    dr.rectangle((14, h-90, w-14, h-44), fill=(0, 0, 0, 255)); dr.text((w/2, h-67), "WARNING: TOBACCO KILLS", font=_font(15, "small"), fill=WHITE+(255,), anchor="mm")
    hl = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ImageDraw.Draw(hl).polygon([(w*.15, 18), (w*.35, 18), (w*.05, h-18), (0, h-18), (0, h*.5)], fill=(255, 255, 255, 45))
    o.alpha_composite(hl); return texture(o, 7, seed)

@reg("product_packet", ["product", "packet", "gutka", "snack", "brand", "tobacco", "food"])
def vis_packet(t, st=0, d=.6, brand="RAJ", sub="PAN MASALA", col=(200, 40, 40), twin=None, accent=Y, cx=W/2, cy=640):
    """A sealed packet pops in with a wobble; twin=(brand2, sub2, col2) adds the twin-pack beside it."""
    q = _p(t, st, d); wob = math.sin(q*math.pi*3)*(1-q)*10
    if not twin: return place(shadow(_packet(brand, sub, col)), cx, cy, scale=_ob(q), rot=wob)
    L = place(shadow(_packet(brand, sub, col)), cx-125, cy, scale=_ob(q), rot=6+wob)
    q2 = _p(t, st+.2, d); L.alpha_composite(place(shadow(_packet(*twin, seed=2)), cx+125, cy+20, scale=_ob(q2), rot=-6-wob)); return L

@reg("polaroid", ["photo", "memory", "face", "person", "choice", "experiment", "people"])
def vis_polaroid(t, st=0, d=.6, photo=None, caption="Photo A", hair=(60, 40, 30), skin=(230, 180, 140), cx=W/2, cy=640, rot=-6, accent=Y):
    """Instant photo drops in and settles with a tilt. Uses a real photo if given, else a flat-design face."""
    w, h = 380, 450; o = Image.new("RGBA", (w, h), (250, 250, 246, 255)); dr = ImageDraw.Draw(o); ph = (24, 24, w-24, 380)
    if photo and os.path.exists(photo): o.alpha_composite(ImageOps.fit(Image.open(photo).convert("RGBA"), (ph[2]-ph[0], ph[3]-ph[1])), ph[:2])
    else:
        dr.rectangle(ph, fill=(120, 170, 200, 255)); fx = w/2
        dr.pieslice((fx-120, 250, fx+120, 470), 180, 360, fill=(70, 90, 140, 255))
        dr.ellipse((fx-82, 100, fx+82, 290), fill=hair+(255,)); dr.ellipse((fx-68, 125, fx+68, 285), fill=skin+(255,))
        dr.chord((fx-82, 95, fx+82, 220), 180, 360, fill=hair+(255,))
        for ex in (-28, 28): dr.ellipse((fx+ex-7, 190, fx+ex+7, 204), fill=INK+(255,))
        dr.arc((fx-26, 220, fx+26, 255), 20, 160, fill=INK+(255,), width=4)
    dr.text((w/2, 415), caption, font=_font(30, "small"), fill=INK+(255,), anchor="mm")
    q = _p(t, st, d); return place(shadow(texture(o, 6)), cx, cy-(1-_oe(q))*300, scale=1.15-.15*_oe(q), rot=rot*_oe(q)+(1-q)*20, alpha=_c(q*3))

@reg("filmstrip", ["film", "movie", "camera", "memory", "history", "media", "sequence"])
def vis_filmstrip(t, st=0, d=2.0, frames=4, accent=Y, y=640, speed=120, colors=((80, 120, 170), (170, 110, 80), (90, 150, 110), (150, 90, 150))):
    """Film strip scrolls sideways with sprocket holes and coloured frames."""
    L = _L(); dr = ImageDraw.Draw(L); q = _p(t, st, .4); hgt = 260; top = y-hgt/2
    dr.rectangle((0, top, W, top+hgt), fill=(25, 25, 28, int(255*q)))
    off = -(t-st)*speed % 200
    for i in range(-1, 6):
        x = off+i*200-100
        for k in range(5):
            hx = x+k*40+8; dr.rounded_rectangle((hx, top+10, hx+22, top+30), 4, fill=(230, 230, 230, int(255*q))); dr.rounded_rectangle((hx, top+hgt-30, hx+22, top+hgt-10), 4, fill=(230, 230, 230, int(255*q)))
        c = colors[i % len(colors)]; dr.rectangle((x+12, top+44, x+188, top+hgt-44), fill=c+(int(255*q),))
    return L

@reg("balance_scale", ["compare", "justice", "law", "weigh", "choice", "versus", "fair"])
def vis_scale(t, st=0, d=1.2, left="COST", right="HEALTH", tilt=-14, accent=Y, cx=W/2, cy=700):
    """Scale builds, then tilts toward the heavier side with a damped wobble."""
    L = _L(); dr = ImageDraw.Draw(L); q = _p(t, st, d); col = (225, 225, 235, 255)
    a = math.radians(tilt*(1-math.exp(-4*q)*math.cos(10*q)) if q > 0 else 0)
    dr.polygon([(cx-90, cy+300), (cx+90, cy+300), (cx, cy+260)], fill=col); dr.rectangle((cx-8, cy-10, cx+8, cy+270), fill=col)
    arm = 230; lx, ly = cx-arm*math.cos(a), cy-arm*math.sin(a); rx, ry = cx+arm*math.cos(a), cy+arm*math.sin(a)
    dr.line((lx, ly, rx, ry), fill=col, width=12); dr.ellipse((cx-18, cy-18, cx+18, cy+18), fill=accent+(255,))
    for (x, yy), txt in (((lx, ly), left), ((rx, ry), right)):
        dr.line((x, yy, x-70, yy+150), fill=col, width=3); dr.line((x, yy, x+70, yy+150), fill=col, width=3)
        dr.chord((x-95, yy+110, x+95, yy+190), 0, 180, fill=col)
        dr.text((x, yy+95), txt, font=_font(36), fill=WHITE+(int(255*_c(q*2)),), anchor="mb")
    return L

@reg("bracket_bars", ["data", "compare", "study", "percent", "result", "chart"])
def vis_bracket_bars(t, st=0, d=1.2, values=(23, 67), labels=("BEFORE", "AFTER"), note="+44%", accent=Y, base=960, hmax=520):
    """Bar chart where a bracket draws between two bars and the difference label pops."""
    L = _L(); dr = ImageDraw.Draw(L); n = len(values); bw = 140; gap = (W-160-n*bw)/max(1, n-1); mx = max(values)
    tops = []
    for i, v in enumerate(values):
        q = _oe(_p(t, st+i*.15, d*.6)); x = 80+i*(bw+gap); hh = hmax*v/mx*q; c = accent if i == n-1 else (110, 120, 140)
        dr.rectangle((x, base-hh, x+bw, base), fill=c+(255,)); dr.text((x+bw/2, base+40), labels[i], font=_font(32, "small"), fill=WHITE+(255,), anchor="mm")
        dr.text((x+bw/2, base-hh-30), f"{int(v*q)}%", font=_font(44), fill=WHITE+(255,), anchor="mm"); tops.append((x+bw/2, base-hmax*v/mx))
    bq = _p(t, st+d*.75, .4)
    if bq > 0 and n >= 2:
        (x0, y0), (x1, y1) = tops[0], tops[-1]; yb = min(y0, y1)-110; xm = x0+(x1-x0)*_oe(bq)
        dr.line((x0, y0-70, x0, yb), fill=WHITE+(255,), width=4); dr.line((x0, yb, xm, yb), fill=WHITE+(255,), width=4)
        if bq > .8: dr.line((x1, yb, x1, y1-70), fill=WHITE+(255,), width=4)
        if bq > .6:
            s = _ob((bq-.6)/.4); dr.rounded_rectangle(((x0+x1)/2-90*s, yb-36*s, (x0+x1)/2+90*s, yb+36*s), 18, fill=accent+(255,))
            dr.text(((x0+x1)/2, yb), note, font=_font(int(44*s)+1), fill=INK+(255,), anchor="mm")
    return L

@reg("magnifier", ["detail", "search", "look", "study", "find", "clue", "inspect"])
def vis_magnifier(t, st=0, d=1.5, under=None, path=((200, 500), (500, 760)), zoom=2.0, accent=Y, r=120):
    """A magnifying glass moves across `under` (an RGBA frame or layer) and REALLY zooms what is beneath it."""
    L = _L(); q = _oe(_p(t, st, d)); x = path[0][0]+(path[1][0]-path[0][0])*q; y = path[0][1]+(path[1][1]-path[0][1])*q
    if under is not None:
        src = under.convert("RGBA"); box = (int(x-r/zoom), int(y-r/zoom), int(x+r/zoom), int(y+r/zoom))
        lens = src.crop(box).resize((2*r, 2*r), Image.BICUBIC); m = Image.new("L", (2*r, 2*r), 0); ImageDraw.Draw(m).ellipse((0, 0, 2*r, 2*r), fill=255)
        L.paste(lens, (int(x-r), int(y-r)), m)
    dr = ImageDraw.Draw(L); dr.ellipse((x-r, y-r, x+r, y+r), outline=(230, 230, 235, 255), width=14)
    hx, hy = x+r*.72, y+r*.72; dr.line((hx, hy, hx+110, hy+110), fill=(90, 60, 40, 255), width=30)
    dr.arc((x-r+20, y-r+20, x+r-20, y+r-20), 200, 250, fill=(255, 255, 255, 160), width=8); return L

@reg("photo_frame", ["photo", "real", "camera", "place", "person", "evidence"])
def vis_photo(t, st=0, d=4.0, photo=None, cx=W/2, cy=640, w=600, h=760, kb=(1.0, 1.12), border=12, caption="", accent=Y):
    """Real photo with Ken Burns slow zoom, white border and soft shadow. Needs a real file path."""
    L = _L()
    if not (photo and os.path.exists(photo)): return L
    q = _p(t, st, d); s = kb[0]+(kb[1]-kb[0])*q; im = Image.open(photo).convert("RGBA")
    big = ImageOps.fit(im, (int(w*s), int(h*s))); ox, oy = (big.width-w)//2, (big.height-h)//2
    pic = big.crop((ox, oy, ox+w, oy+h)); fr = Image.new("RGBA", (w+2*border, h+2*border), (250, 250, 250, 255)); fr.alpha_composite(pic, (border, border))
    if caption: ImageDraw.Draw(fr).text((border+16, h-30), caption, font=_font(24, "small"), fill=WHITE+(255,))
    return place(shadow(fr), cx, cy, alpha=_c(_p(t, st, .3)*1.0))

@reg("film_camera", ["camera", "film", "photo", "old", "history"])
def vis_camera(t, st=0, d=.6, body=(40, 40, 46), accent=Y, cx=W/2, cy=640, flash_at=None):
    """Flat-design film camera; optional white flash at flash_at seconds."""
    w, h = 460, 300; o = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dr = ImageDraw.Draw(o)
    dr.rounded_rectangle((0, 50, w, h), 30, fill=body+(255,)); dr.rounded_rectangle((40, 20, 160, 70), 10, fill=body+(255,))
    dr.rectangle((0, 120, w, 220), fill=(150, 110, 70, 255)); dr.ellipse((w/2-100, 75, w/2+100, 275), fill=(200, 200, 205, 255))
    dr.ellipse((w/2-75, 100, w/2+75, 250), fill=(20, 20, 26, 255)); dr.ellipse((w/2-30, 130, w/2+5, 165), fill=(255, 255, 255, 120))
    dr.rounded_rectangle((w-120, 70, w-40, 110), 8, fill=(230, 230, 240, 255)); dr.ellipse((60, 75, 90, 105), fill=accent+(255,))
    L = place(shadow(o), cx, cy, scale=_ob(_p(t, st, d)))
    if flash_at is not None and 0 <= t-flash_at < .25: L.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(255*(1-(t-flash_at)/.25)))))
    return L

@reg("timeline_cards", ["history", "timeline", "years", "steps", "story", "events"])
def vis_timeline_cards(t, st=0, d=.5, events=(("1962", "Started"), ("2012", "Ban"), ("2026", "Today")), accent=Y, gap=.6):
    """Vertical timeline: line grows down, each event card slides in from alternating sides with a year chip."""
    L = _L(); dr = ImageDraw.Draw(L); n = len(events); top, bot = 260, 1040; x = W/2
    gq = _oe(_p(t, st, gap*n+d)); dr.line((x, top, x, top+(bot-top)*gq), fill=(200, 200, 210, 255), width=6)
    for i, (yr, txt) in enumerate(events):
        q = _p(t, st+i*gap, d)
        if q <= 0: continue
        yy = top+(bot-top)*(i+.5)/n; side = -1 if i % 2 == 0 else 1; e = _ob(q)
        dr.ellipse((x-16, yy-16, x+16, yy+16), fill=accent+(255,))
        cx = x+side*(170+(1-e)*200); card = (cx-140, yy-60, cx+140, yy+60)
        dr.rounded_rectangle(card, 18, fill=(40, 44, 56, int(255*_c(q*2))))
        dr.text((cx, yy-22), yr, font=_font(40), fill=accent+(255,), anchor="mm"); dr.text((cx, yy+26), txt, font=_font(28, "small"), fill=WHITE+(255,), anchor="mm")
    return L

@reg("speech_bubble", ["talk", "quote", "say", "people", "chat", "opinion"])
def vis_bubble(t, st=0, d=.4, text="Did you notice?", cx=W/2, cy=520, tail="left", col=WHITE, ink=INK, accent=Y):
    """Comic speech bubble pops with overshoot, text wrapped inside."""
    dr0 = ImageDraw.Draw(_L()); f = _font(44, "small"); lines = wrap(text, f, 460, dr0); h = 70+len(lines)*56; w = 540
    o = Image.new("RGBA", (w, h+60), (0, 0, 0, 0)); dr = ImageDraw.Draw(o); dr.rounded_rectangle((0, 0, w, h), 40, fill=col+(255,))
    tx = 90 if tail == "left" else w-90; dr.polygon([(tx-30, h-5), (tx+30, h-5), (tx-40 if tail == "left" else tx+40, h+55)], fill=col+(255,))
    for i, ln in enumerate(lines): dr.text((w/2, 35+i*56), ln, font=f, fill=ink+(255,), anchor="ma")
    return place(shadow(o), cx, cy, scale=_ob(_p(t, st, d)))

@reg("warning_sign", ["danger", "warning", "risk", "health", "stop", "alert"])
def vis_warning(t, st=0, d=.5, text="!", col=(255, 200, 0), cx=W/2, cy=620, pulse=True):
    """Triangle warning sign pops and pulses."""
    s = 200; o = Image.new("RGBA", (2*s+20, 2*s), (0, 0, 0, 0)); dr = ImageDraw.Draw(o)
    pts = [(s+10, 10), (2*s+10, 2*s-10), (10, 2*s-10)]; dr.polygon(pts, fill=INK+(255,)); dr.polygon([(s+10, 50), (2*s-25, 2*s-30), (45, 2*s-30)], fill=col+(255,))
    dr.text((s+10, s+40), text, font=_font(170), fill=INK+(255,), anchor="mm")
    q = _p(t, st, d); sc = _ob(q)*(1+.05*math.sin(t*8) if pulse and q >= 1 else 1)
    return place(shadow(o), cx, cy, scale=sc)

@reg("source_line", ["source", "study", "credit", "fact"])
def vis_source(t, st=0, d=.4, text="Source: WHO, 2023", y=1110, accent=Y):
    """Small source credit that fades up at the bottom of the safe box (always add when a fact is shown)."""
    L = _L(); q = _oe(_p(t, st, d)); ImageDraw.Draw(L).text((W/2, y+(1-q)*20), text, font=_font(24, "small"), fill=(200, 200, 210, int(220*q)), anchor="mm"); return L

# ============================ BACKGROUNDS ============================
SCENE_BG = {"dark": ((14, 16, 22), (28, 32, 44)), "navy": ((10, 20, 44), (24, 48, 90)), "wine": ((40, 10, 20), (80, 24, 40)),
            "forest": ((8, 30, 22), (20, 64, 46)), "paper": ((222, 214, 196), (240, 234, 220)), "mustard": ((60, 46, 6), (120, 96, 20)),
            "teal": ((6, 36, 40), (16, 80, 86)), "plum": ((30, 12, 44), (64, 30, 90)), "slate": ((30, 34, 40), (60, 66, 76))}
def scene_bg(kind="dark", t=0.0, vignette=True, grain=6, seed=0):
    """Per-scene background: vertical gradient + slow drift + vignette + film grain. Change kind per scene/section."""
    a, b = SCENE_BG.get(kind, SCENE_BG["dark"]); y = np.linspace(0, 1, H)[:, None]
    shift = .08*math.sin(t*.3); g = np.clip(y+shift, 0, 1)
    img = np.zeros((H, W, 3), np.float32)
    for c in range(3): img[..., c] = a[c]+(b[c]-a[c])*(1-g)
    if vignette:
        xx, yy = np.meshgrid(np.linspace(-1, 1, W), np.linspace(-1, 1, H)); img *= (1-.35*np.clip(xx**2*.6+yy**2*.4, 0, 1))[..., None]
    if grain: img += np.random.default_rng(seed+int(t*12)).normal(0, grain, (H, W, 1))
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")

def pick_vis(tags, used=(), seed=None):
    rnd = random.Random(seed); tags = set(tags)
    scored = sorted(((len(fn.tags & tags), rnd.random(), k) for k, fn in VIS.items() if k not in used), reverse=True)
    return scored[0][2] if scored else None
