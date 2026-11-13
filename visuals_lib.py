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
def _ob(x, s=1.28): x = _c(x)-1; return 1+(s+1)*x**3+s*x**2  # v36: 6% overshoot (was 10%)
def _word_t(words, idx):
    # v34 (Hark word_t): start time of word idx in [(start, dur, text), ...].
    if not words: return 0.0
    i = max(0, min(int(idx), len(words) - 1))
    return float(words[i][0])
def _num_word_idx(words):
    # v34: index of the first word that is (or contains) a number.
    if not words: return None
    for i, (o, dd, w) in enumerate(words):
        ww = str(w).strip().lower().strip(".,!?\"'")
        if any(c.isdigit() for c in ww) or ww in ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "twenty", "thirty", "fifty", "hundred", "thousand", "million", "billion", "percent", "half"):
            return i
    return None
def _L(): return Image.new("RGBA", (W, H), (0, 0, 0, 0))

def texture(img, amount=10, seed=3):
    """Paper / plastic grain on an RGBA image (keeps alpha)."""
    a = np.asarray(img).astype(np.int16); rng = np.random.default_rng(seed)
    n = rng.integers(-amount, amount+1, a.shape[:2])[..., None]
    a[..., :3] = np.clip(a[..., :3]+n, 0, 255); return Image.fromarray(a.astype(np.uint8), "RGBA")

def shadow(obj, off=(0, 12), blur=18, alpha=90):
    """Return obj with a soft drop shadow under it (same size). v36 (Blind C2):
    blur 18, offset (0, 12), 35% black (alpha 90) — a rich, deep shadow."""
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
# v36 (Blind C1): the India outline is REAL shape data — INDIA_GEO from
# india_geo.py (johan/world.geo.json IND.geo.json, Natural Earth-derived,
# Douglas-Peucker simplified 136 -> 110 points), NOT a hand polygon.
try:
    from india_geo import INDIA_GEO as _INDIA_GEO
except Exception:
    _INDIA_GEO = None
INDIA = _INDIA_GEO or [(68.2,23.7),(70.0,20.8),(72.8,19.0),(73.4,16.0),(74.6,12.8),(76.3,9.5),(77.5,8.1),(78.2,9.0),(79.9,10.3),
 (80.3,13.0),(80.1,15.5),(82.3,17.0),(84.8,19.3),(86.9,21.3),(88.2,21.7),(89.0,22.0),(88.7,24.3),(89.8,25.9),(92.0,25.0),
 (92.6,22.0),(93.4,24.0),(94.6,25.6),(95.3,26.8),(97.3,28.0),(96.0,29.3),(94.0,28.9),(92.0,27.8),(89.7,26.8),(88.2,27.9),
 (85.0,27.4),(82.0,28.5),(80.1,30.2),(78.9,31.5),(78.4,32.6),(79.4,34.0),(77.8,35.5),(76.0,35.9),(74.5,34.6),(73.8,33.3),
 (74.6,32.0),(73.9,30.4),(72.0,28.5),(70.4,27.9),(69.5,26.5),(70.6,25.5),(69.2,24.3)]
def _proj(lon, lat, box=(90, 260, 630, 1000), lon0=67.5, lon1=98.0, lat0=7.5, lat1=36.5):
    x0, y0, x1, y1 = box; s = min((x1-x0)/(lon1-lon0), (y1-y0)/(lat1-lat0))
    ox = x0+((x1-x0)-s*(lon1-lon0))/2; oy = y0+((y1-y0)-s*(lat1-lat0))/2
    return ox+(lon-lon0)*s, oy+(lat1-lat)*s

@reg("india_map", ["map", "india", "country", "ban", "law", "places", "geography"])
def vis_india_map(t, st=0, d=1.2, pins=(("Delhi", 77.2, 28.6), ("Mumbai", 72.8, 19.1)), accent=Y, land=(58, 66, 84), outline=WHITE, label="INDIA", words=None):
    """v36 (Blind C1 — rich, professional map): REAL GeoJSON shape (not a
    hand polygon), filled with a soft accent gradient, a 2 px light rim,
    an inner shadow (a dark ring just inside the edge), the states that
    matter as labelled pins with a glow pulse, and — on the verdict word
    ("banned"/"ban") — a red BANNED stamp slamming onto the map (B2).
    The map box (90..630, 260..1000) stays inside the safe frame."""
    L = _L(); dr = ImageDraw.Draw(L); q = _p(t, st, d)
    pts = [_proj(*p) for p in INDIA]; n = len(pts)
    _fa = _oe(_c((q - .08) / .35)) if q > .08 else 0.0
    if _fa > 0:
        # Glow: the polygon in accent, blurred, behind the fill.
        _glow = _L(); ImageDraw.Draw(_glow).polygon(pts, fill=accent + (110,))
        L.alpha_composite(_glow.filter(ImageFilter.GaussianBlur(18)))
        # Inner shadow: a dark ring just inside the edge — draw the dark
        # polygon first, then the gradient fill on a 3% inset polygon, so a
        # dark band shows between the edge and the fill.
        _cx = sum(p[0] for p in pts) / n; _cy = sum(p[1] for p in pts) / n
        _inset = [(_cx + (x - _cx) * 0.97, _cy + (y - _cy) * 0.97) for x, y in pts]
        ImageDraw.Draw(L).polygon(pts, fill=(10, 10, 16, int(200 * _fa)))
        # Gradient fill: light accent -> deep accent, clipped to the inset polygon.
        _bx0, _bx1 = int(min(p[0] for p in _inset)), int(max(p[0] for p in _inset))
        _by0, _by1 = int(min(p[1] for p in _inset)), int(max(p[1] for p in _inset))
        _bw, _bh = max(1, _bx1 - _bx0), max(1, _by1 - _by0)
        _top = np.array([min(255, int(v + (255 - v) * .45)) for v in accent], dtype=np.float32)
        _bot = np.array([int(v * .45) for v in accent], dtype=np.float32)
        _yy = np.linspace(0, 1, _bh)[:, None, None]
        _g = (_top * (1 - _yy) + _bot * _yy).astype(np.uint8)
        _gi = Image.fromarray(np.repeat(_g, _bw, axis=1), "RGB").convert("RGBA")
        _mask = Image.new("L", (_bw, _bh), 0)
        ImageDraw.Draw(_mask).polygon([(x - _bx0, y - _by0) for x, y in _inset], fill=int(255 * _fa))
        L.paste(_gi, (_bx0, _by0), _mask)
    k = int(n*_oe(min(1, q/.5)))+1                      # draw-on outline
    # v36: a 2 px light rim (was an 8 px heavy outline).
    dr.line(pts[:k]+([pts[0]] if k > n else []), fill=outline+(255,), width=2, joint="curve")
    f = _font(30, "small")
    for i, (name, lon, lat) in enumerate(pins):
        pq = _p(t, st+d*.6+i*.25, .35)
        if pq <= 0: continue
        x, y = _proj(lon, lat); drop = (1-_ob(pq))*60; r = 16
        # v36: a glow pulse at the pin (the "state that matters" highlighted).
        _pr = 26 + 10 * math.sin(t * 3 + i * 2)
        _pg = _L(); ImageDraw.Draw(_pg).ellipse((x-_pr, y-_pr, x+_pr, y+_pr), fill=accent+(70,))
        L.alpha_composite(_pg.filter(ImageFilter.GaussianBlur(10)))
        dr.ellipse((x-r*2.2, y-r*.6, x+r*2.2, y+r*.6), fill=(0, 0, 0, 90))
        dr.polygon([(x, y-drop), (x-r, y-2*r-drop), (x+r, y-2*r-drop)], fill=accent+(255,))
        dr.ellipse((x-r, y-3*r-drop, x+r, y-r-drop), fill=accent+(255,)); dr.ellipse((x-6, y-2*r-6-drop, x+6, y-2*r+6-drop), fill=INK+(255,))
        dr.text((x+r+8, y-2*r-drop), name, font=f, fill=WHITE+(int(255*pq),), anchor="lm")
    if label: dr.text((W/2, 220), label, font=_font(64), fill=WHITE+(int(255*_c(q*2)),), anchor="mm")
    # v36 (Blind B2 — "ban" -> stamp slams): a red BANNED stamp slamming onto
    # the map on the verdict word ("banned"/"ban"/"illegal"), not at a fixed time.
    _st = None
    if words:
        for i, (o, _dd, w) in enumerate(words):
            if str(w).strip().lower().strip(".,!?\"'") in ("banned", "ban", "illegal", "prohibited"):
                _st = float(o); break
    if _st is not None and (t - st) > _st:
        sq = _oe(_p(t, st + _st, .18))
        if sq > 0:
            s = Image.new("RGBA", (420, 130), (0, 0, 0, 0)); ds = ImageDraw.Draw(s)
            ds.rounded_rectangle((4, 4, 416, 126), 14, outline=RED+(255,), width=8)
            ds.text((210, 65), "BANNED", font=_font(72), fill=RED+(255,), anchor="mm")
            s = texture(s, 40, 9)
            L.alpha_composite(place(s, W/2, 640, scale=2.0-1.0*sq, rot=-14, alpha=_c(sq*3)))
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
            # v35 richness: brighter, more solid dots (the old pale grey
            # (200,205,220,170) read as flat/low-level).
            dr.ellipse((x-4, y-4, x+4, y+4), fill=(228, 232, 242, 215))
    for i, (lon, lat) in enumerate(hot):
        hq = _p(t, st+d*.7+i*.2, .5)
        if hq <= 0: continue
        x = x0+(lon+180)/360*(x1-x0); y = y0+(75-lat)/130*(y1-y0); r = 8+28*((t*1.2+i*.3) % 1)
        # v35 richness: a soft accent glow behind each hot spot.
        _hg = _L(); ImageDraw.Draw(_hg).ellipse((x-34, y-34, x+34, y+34), fill=accent+(70,))
        L.alpha_composite(_hg.filter(ImageFilter.GaussianBlur(14)))
        dr.ellipse((x-r, y-r, x+r, y+r), outline=accent+(int(200*(1-((t*1.2+i*.3) % 1))),), width=3)
        dr.ellipse((x-8, y-8, x+8, y+8), fill=accent+(255,))
    return L

# ============================ PAPER ============================
def _doc_obj(title, lines, stamp, accent, w=520, h=680, highlight=1, seal=True):
    o = Image.new("RGBA", (w, h), PAPER+(255,)); dr = ImageDraw.Draw(o)
    dr.rectangle((0, 0, w-1, h-1), outline=(200, 190, 170, 255), width=2)
    if seal:  # v79.2: a plain seal ring — the old "GOI" letters put a
        # government attribution on every topic's document.
        dr.ellipse((w/2-34, 30, w/2+34, 98), outline=INK+(255,), width=3); dr.ellipse((w/2-5, 59, w/2+5, 69), fill=INK+(255,))
    dr.text((w/2, 130), title, font=_font(30, "serif"), fill=INK+(255,), anchor="mm")
    dr.line((40, 160, w-40, 160), fill=INK+(255,), width=2)
    f = _font(30, "serif_r"); y = 185
    for i, ln in enumerate(lines):
        for sub in wrap(ln, f, w-80, dr):
            if i == highlight: dr.rectangle((36, y-2, 44+dr.textlength(sub, font=f), y+26), fill=accent+(150,))
            dr.text((40, y), sub, font=f, fill=INK+(255,)); y += 32
        y += 10
    for k in range(int((h-110-y)/32)): dr.line((40, y+k*32+14, w-40-(k*37 % 120), y+k*32+14), fill=(170, 165, 150, 255), width=6)
    dr.line((w-210, h-70, w-50, h-70), fill=INK+(255,), width=2); dr.text((w-130, h-50), "Signature", font=_font(30, "serif_r"), fill=INK+(255,), anchor="mm")
    return texture(o, 8)

@reg("document", ["law", "rule", "ban", "government", "report", "study", "paper", "official"])
def vis_document(t, st=0, d=1.0, title="REPORT", lines=(), stamp="", accent=Y, highlight=0, cx=W/2, cy=640, words=None):
    """Official paper slides up, the key line gets highlighted, a red stamp slams down.
    v79.2 (defect 1): NO canned body — the old defaults were a past
    project's gutka-ban notification and rendered verbatim into
    unrelated videos (a
    sleep video's brain-cleaning scene). Title / lines / stamp are
    composed from the CURRENT scene by compliance.compose_visual;
    the bare defaults draw a blank ruled report, never another
    project's text."""
    q = _p(t, st, d*.5); doc = _doc_obj(title, lines, stamp, accent, highlight=highlight)
    L = place(shadow(doc), cx, cy+(1-_oe(q))*500, rot=-2*(1-_oe(q)))
    # v34 (Hark word_t): the stamp slams on the verdict word ("banned"/"ban"/
    # "illegal"), not at a fixed 70% of the scene.
    _st = None
    if words:
        for i, (o, _dd, w) in enumerate(words):
            if str(w).strip().lower().strip(".,!?\"'") in ("banned", "ban", "illegal", "prohibited", "banned."):
                _st = o; break
    sq = _p(t, st + (_st if _st is not None else d*.7), .25)
    if stamp and sq > 0:
        s = Image.new("RGBA", (360, 120), (0, 0, 0, 0)); ds = ImageDraw.Draw(s)
        ds.rounded_rectangle((4, 4, 356, 116), 14, outline=RED+(255,), width=8)
        ds.text((180, 60), stamp, font=_font(70), fill=RED+(255,), anchor="mm")
        s = texture(s, 40, 9); L.alpha_composite(place(s, cx+60, cy+180, scale=2.2-1.2*_oe(sq), rot=-14, alpha=_c(sq*3)))
    return L

@reg("newspaper", ["news", "media", "headline", "story", "report", "history"])
def vis_newspaper(t, st=0, d=1.0, paper="THE DAILY TIMES", headline="", photo=None, date="", accent=Y, cx=W/2, cy=640):
    # v79.2: headline/date come from the scene (compose_visual) — the
    # old defaults were a past project's study headline + a fake date.
    """Newspaper spins in (classic film move), with masthead, headline, photo and columns."""
    w, h = 560, 760; o = Image.new("RGBA", (w, h), NEWS+(255,)); dr = ImageDraw.Draw(o)
    dr.text((w/2, 50), paper, font=_font(44, "serif"), fill=INK+(255,), anchor="mm")
    dr.line((24, 86, w-24, 86), fill=INK+(255,), width=3)
    if date: dr.text((30, 96), date, font=_font(30, "serif_r"), fill=INK+(255,))
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

def typewriter_shown(text, elapsed, cps=18):
    """The typewriter's reveal rule, shared by vis_typewriter and the QC:
    WHOLE WORDS ONLY — word i appears complete when its last character's
    time arrives. Returns the shown string. The QC verifies this invariant
    (no trailing partial word) at several times (Blind A2/E6)."""
    _words = text.split()
    _ends, _pos = [], 0
    for _w in _words:
        _pos += len(_w) + 1
        _ends.append(_pos - 1)
    _el = max(0.0, elapsed) * cps
    return " ".join(_w for _w, _e in zip(_words, _ends) if _e <= _el)


@reg("typewriter_page", ["history", "old", "letter", "secret", "file", "quote"])
def vis_typewriter(t, st=0, d=None, text="", cps=18, accent=Y, cx=W/2, cy=640):
    """Old paper, mono text typed with a blinking caret. v36 (Blind A2):
    WHOLE WORDS ONLY — the old char-by-char cut rendered a trailing partial
    word ("CLASSIFIED: s"). Each word appears complete (it pops in whole
    when its last character's time arrives); once the full string is shown
    it HOLDS for 400 ms (no caret, no change) before the scene moves on."""
    if not str(text or "").strip():
        return _L()  # v79.2: nothing composed for this scene -> no page (never a canned classified text)
    w, h = 560, 420; o = Image.new("RGBA", (w, h), (236, 226, 200, 255)); dr = ImageDraw.Draw(o)
    f = _font(30, "mono")
    # Word boundaries: word i is revealed whole when its last char's time arrives.
    shown = typewriter_shown(text, max(0.0, t - st), cps)
    _done = shown == text
    y = 40
    for ln in wrap(shown, f, w-60, dr) or [""]:
        dr.text((30, y), ln, font=f, fill=(35, 30, 25, 255)); y += 42
    # Caret only while still typing (hidden once the full text holds).
    if int(t*2) % 2 == 0 and not _done:
        lw = dr.textlength((wrap(shown, f, w-60, dr) or [""])[-1], font=f); dr.rectangle((32+lw, y-40, 48+lw, y-8), fill=(35, 30, 25, 255))
    return place(shadow(texture(o, 14)), cx, cy)

@reg("receipt", ["money", "bill", "price", "shopping", "cost"])
def vis_receipt(t, st=0, d=1.0, items=(), total="", accent=Y, cx=W/2, cy=640):
    # v79.2: items/total are composed from the scene — the old defaults
    # were a past project's gutka bill, items and total alike.
    """Receipt prints out from the top, line by line, total highlighted."""
    w = 420; h = 160+len(items)*56+120; o = Image.new("RGBA", (w, h), (250, 250, 248, 255)); dr = ImageDraw.Draw(o)
    for x in range(0, w, 20): dr.polygon([(x, h), (x+10, h-12), (x+20, h)], fill=(0, 0, 0, 0))
    dr.text((w/2, 50), "RECEIPT", font=_font(40, "mono"), fill=INK+(255,), anchor="mm")
    f = _font(30, "mono"); y = 120
    for a, b in items: dr.text((30, y), a, font=f, fill=INK+(255,)); dr.text((w-30, y), b, font=f, fill=INK+(255,), anchor="ra"); y += 56
    dr.line((30, y, w-30, y), fill=INK+(255,), width=2)
    if total:
        dr.rectangle((24, y+20, w-24, y+80), fill=accent+(255,))
        dr.text((30, y+50), "TOTAL", font=f, fill=INK+(255,), anchor="lm"); dr.text((w-30, y+50), total, font=f, fill=INK+(255,), anchor="rm")
    q = _oe(_p(t, st, d)); shown = o.crop((0, 0, w, max(1, int(h*q))))
    L = _L(); L.alpha_composite(shadow(texture(shown, 6)), (int(cx-w/2), int(cy-h/2))); return L

# ============================ PRODUCTS / OBJECTS ============================
def _packet(brand, sub, col, w=230, h=330, seed=1, warning=""):
    """v36 (Blind C2 — real objects with depth): fold lines (two vertical
    side folds + a horizontal crease under the crimp), a highlight streak,
    and a rich drop shadow (blur 18, offset 0/12, 35% black — see shadow())."""
    o = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dr = ImageDraw.Draw(o)
    dr.rounded_rectangle((0, 18, w, h-18), 16, fill=col+(255,))
    for yy in (0, h-26):                                         # crimped seal edges
        for x in range(0, w, 12): dr.polygon([(x, yy+26 if yy == 0 else yy), (x+6, yy if yy == 0 else yy+26), (x+12, yy+26 if yy == 0 else yy)], fill=tuple(int(c*.8) for c in col)+(255,))
    # Fold lines: two vertical side folds + a horizontal crease under the top crimp.
    _fold = tuple(int(c*.72) for c in col) + (255,)
    dr.line((w*.22, 26, w*.22, h-26), fill=_fold, width=2)
    dr.line((w*.78, 26, w*.78, h-26), fill=_fold, width=2)
    dr.line((0, 44, w, 44), fill=tuple(int(c*.85) for c in col)+(255,), width=2)
    dr.ellipse((w/2-80, h/2-90, w/2+80, h/2+20), fill=(255, 240, 200, 255))
    if brand: dr.text((w/2, h/2-35), brand, font=_font(46), fill=col+(255,), anchor="mm")
    if sub: dr.text((w/2, h/2+60), sub, font=_font(30, "small"), fill=WHITE+(255,), anchor="mm")
    if warning:  # v79.2: a warning strip only when THIS scene carries one — never a canned tobacco warning on every packet.
        dr.rectangle((14, h-90, w-14, h-44), fill=(0, 0, 0, 255)); dr.text((w/2, h-67), warning, font=_font(30, "small"), fill=WHITE+(255,), anchor="mm")
    hl = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ImageDraw.Draw(hl).polygon([(w*.15, 18), (w*.35, 18), (w*.05, h-18), (0, h-18), (0, h*.5)], fill=(255, 255, 255, 45))
    o.alpha_composite(hl); return texture(o, 7, seed)


def _light_sweep(img, q):
    """v36 (Blind C5 — materials): a light sweep across a metal/plastic
    object, ONCE per scene — a diagonal white band that crosses the object
    as q goes 0 -> 1 (the caller drives q from the scene progress)."""
    w, h = img.size
    sw = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ds = ImageDraw.Draw(sw)
    x = -60 + q * (w + 120)
    ds.polygon([(x, 0), (x + 50, 0), (x - 30, h), (x - 80, h)], fill=(255, 255, 255, 70))
    out = img.copy(); out.alpha_composite(sw); return out

@reg("product_packet", ["product", "packet", "gutka", "snack", "brand", "tobacco", "food"])
def vis_packet(t, st=0, d=.6, brand="", sub="", col=(200, 40, 40), twin=None, accent=Y, cx=W/2, cy=640, warning=""):
    # v79.2: brand/sub come from the scene — the old defaults were a
    # past project's RAJ pan-masala packet.
    """A sealed packet pops in with a wobble; twin=(brand2, sub2, col2) adds the twin-pack beside it.
    v36 (Blind C5): a light sweep crosses the packet once per scene."""
    q = _p(t, st, d); wob = math.sin(q*math.pi*3)*(1-q)*10
    if not twin: return place(shadow(_light_sweep(_packet(brand, sub, col, warning=warning), q)), cx, cy, scale=_ob(q), rot=wob)
    L = place(shadow(_packet(brand, sub, col, warning=warning)), cx-125, cy, scale=_ob(q), rot=6+wob)
    q2 = _p(t, st+.2, d); L.alpha_composite(place(shadow(_packet(*twin, seed=2)), cx+125, cy+20, scale=_ob(q2), rot=-6-wob)); return L

@reg("polaroid", ["photo", "memory", "face", "person", "choice", "experiment", "people"])
def vis_polaroid(t, st=0, d=.6, photo=None, caption="Photo A", hair=(60, 40, 30), skin=(230, 180, 140), cx=W/2, cy=640, rot=-2, accent=Y):
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
def vis_scale(t, st=0, d=1.2, left="", right="", tilt=-14, accent=Y, cx=W/2, cy=700, words=None):
    # v79.2: the pan labels come from the scene — the old COST/HEALTH
    # defaults were a past project's scales and leaked into other topics.
    """Scale builds upright, then tips toward the heavier side ON the
    comparative word (B2, Blind): "more"/"less"/"than" — or the side's own
    word ("cost"/"health") — starts the tip. Before that word the scale is
    level; the tip is a damped wobble to the final tilt. v36: words= is the
    scene's word timings; without it the tip falls back to 60% of the scene."""
    L = _L(); dr = ImageDraw.Draw(L); q = _p(t, st, d); col = (225, 225, 235, 255)
    # The tip TIME is the first comparative ("more"/"less"/"than"/
    # "versus") or side word ("cost"/"health"). The tip DIRECTION follows
    # the LAST side word in the vo — the conclusion, not the introduction.
    # (v36 fix: "One side is the cost. The other side is your health.
    # The scale never lies." — the first word was "cost" so the scale
    # tipped COST down, but the point is health outweighs the cost, so
    # HEALTH must go down. The last side word is "health" -> HEALTH down.)
    _tip_t, _tip_dir = None, -1
    if words:
        _last_side = None
        for i, (o, _dd, w) in enumerate(words):
            ww = str(w).strip().lower().strip(".,!?\"'")
            if _tip_t is None and ww in ("more", "less", "than", "versus", "vs", "cost", "health"):
                _tip_t = float(o)
            if ww == "cost":
                _last_side = 1
            elif ww == "health":
                _last_side = -1
        if _last_side is not None:
            _tip_dir = _last_side
    if _tip_t is None:
        _tip_t = d * 0.6
    # The tilt: 0 until the tip word, then a damped wobble to the final tilt.
    _tq = _p(t, st + _tip_t, 0.45)
    _tilt = tilt * _tip_dir * (1 - math.exp(-4 * _tq) * math.cos(10 * _tq)) if _tq > 0 else 0
    a = math.radians(_tilt)
    dr.polygon([(cx-90, cy+300), (cx+90, cy+300), (cx, cy+260)], fill=col); dr.rectangle((cx-8, cy-10, cx+8, cy+270), fill=col)
    # v35: the arm (230) + pan radius (95) put the pans at x 35..685 in the
    # 720 layer — upscaled 1.5x that is x 52..1028 in 1080, outside the safe
    # frame (86..994). The frame-QC caught it. Arm 190 + radius 80 keeps the
    # pans at x 90..630 (135..945 in 1080), inside the safe frame.
    arm = 190; lx, ly = cx-arm*math.cos(a), cy-arm*math.sin(a); rx, ry = cx+arm*math.cos(a), cy+arm*math.sin(a)
    dr.line((lx, ly, rx, ry), fill=col, width=12); dr.ellipse((cx-18, cy-18, cx+18, cy+18), fill=accent+(255,))
    for (x, yy), txt in (((lx, ly), left), ((rx, ry), right)):
        dr.line((x, yy, x-70, yy+150), fill=col, width=3); dr.line((x, yy, x+70, yy+150), fill=col, width=3)
        dr.chord((x-80, yy+110, x+80, yy+190), 0, 180, fill=col)
        dr.text((x, yy+95), txt, font=_font(36), fill=WHITE+(int(255*_c(q*2)),), anchor="mb")
    return L

@reg("bracket_bars", ["data", "compare", "study", "percent", "result", "chart"])
def vis_bracket_bars(t, st=0, d=1.2, values=(), labels=(), note="", accent=Y, base=960, hmax=520, words=None):
    # v79.2: values/labels/note are composed from the scene's spoken
    # numbers — the old defaults were fabricated stats (23/67/+44%).
    """Bar chart where a bracket draws between two bars and the difference label pops."""
    L = _L(); dr = ImageDraw.Draw(L); n = len(values)
    if not n: return L  # no composed numbers -> no chart
    bw = 140; gap = (W-160-n*bw)/max(1, n-1); mx = max(values)
    tops = []
    for i, v in enumerate(values):
        q = _oe(_p(t, st+i*.15, d*.6)); x = 80+i*(bw+gap); hh = hmax*v/mx*q; c = accent if i == n-1 else (110, 120, 140)
        dr.rectangle((x, base-hh, x+bw, base), fill=c+(255,)); dr.text((x+bw/2, base+40), labels[i] if i < len(labels) else "", font=_font(32, "small"), fill=WHITE+(255,), anchor="mm")
        dr.text((x+bw/2, base-hh-30), f"{int(v*q)}%", font=_font(44), fill=WHITE+(255,), anchor="mm"); tops.append((x+bw/2, base-hmax*v/mx))
    # v34 (Hark word_t): the bracket + difference note pop on the number word.
    _ni = _num_word_idx(words)
    bq = _p(t, st + (_word_t(words, _ni) if _ni is not None else d*.75), .4)
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
    if caption: ImageDraw.Draw(fr).text((border+16, h-30), caption, font=_font(30, "small"), fill=WHITE+(255,))
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
def vis_timeline_cards(t, st=0, d=.5, events=(), accent=Y, gap=.6):
    # v79.2: events come from the scene — the old defaults were a past
    # project's timeline (1962 / 2012 Ban / 2026).
    """Vertical timeline: line grows down, each event card slides in from alternating sides with a year chip."""
    L = _L(); dr = ImageDraw.Draw(L); n = len(events)
    if not n: return L  # no composed events -> no timeline
    top, bot = 260, 1040; x = W/2
    gq = _oe(_p(t, st, gap*n+d)); dr.line((x, top, x, top+(bot-top)*gq), fill=(200, 200, 210, 255), width=6)
    for i, (yr, txt) in enumerate(events):
        q = _p(t, st+i*gap, d)
        if q <= 0: continue
        yy = top+(bot-top)*(i+.5)/n; side = -1 if i % 2 == 0 else 1; e = _ob(q)
        dr.ellipse((x-16, yy-16, x+16, yy+16), fill=accent+(255,))
        cx = x+side*(170+(1-e)*200); card = (cx-140, yy-60, cx+140, yy+60)
        dr.rounded_rectangle(card, 18, fill=(40, 44, 56, int(255*_c(q*2))))
        dr.text((cx, yy-22), yr, font=_font(40), fill=accent+(255,), anchor="mm"); dr.text((cx, yy+26), txt, font=_font(30, "small"), fill=WHITE+(255,), anchor="mm")
    return L

@reg("speech_bubble", ["talk", "quote", "say", "people", "chat", "opinion"])
def vis_bubble(t, st=0, d=.4, text="", cx=W/2, cy=520, tail="left", col=WHITE, ink=INK, accent=Y):
    """Comic speech bubble pops with overshoot, text wrapped inside."""
    if not str(text or "").strip(): return _L()  # v79.2: no composed text -> no bubble
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
def vis_source(t, st=0, d=.4, text="", y=1110, accent=Y):
    # v79.2: no default credit — the old default fabricated a WHO
    # attribution on any scene that forgot to pass its real source.
    """Source credit that fades up at the bottom of the safe box.
    v79 (Ajju A3, 2026-11-13): LEGIBLE OR NOTHING — Ajju circled the
    old faint dark-grey microtext ('Source: ICMR 2021') yellow: he
    did not even know what it was. The line now renders at 34 px on
    this 720-wide layer (= 51 px at the 1080 frame, above the 30 px
    floor Blind's method sets) in near-white (255,255,255 at ~92%
    alpha — above the 60%-white floor). Whether a line appears at
    all is governed by R5 (a real source for that exact claim, or
    none) at plan/compliance level."""
    L = _L(); q = _oe(_p(t, st, d)); ImageDraw.Draw(L).text((W/2, y+(1-q)*20), text, font=_font(34, "small"), fill=(255, 255, 255, int(235*q)), anchor="mm"); return L

# ============================ HARK ENGINE (v34) ============================
def _person(col, s=1.0):
    # v34 (Hark sprite_person): a flat person icon — head + body.
    w, h = int(90*s), int(170*s); im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
    dr.ellipse([w*.28, 0, w*.72, h*.26], fill=col); dr.rounded_rectangle([w*.1, h*.3, w*.9, h], int(w*.3), fill=col)
    return im

@reg("four", ["people", "one_in_n", "ratio", "adults", "population", "share"])
def vis_four(t, st=0, d=1.0, n=4, accent=Y, cx=W/2, cy=640, words=None):
    """People icons for '1 in N' facts: they pop in one by one; the 1st turns
    red + gets a box when the 'one in N' word is spoken (Hark `four`)."""
    L = _L()
    _ni = _num_word_idx(words)
    hot_t = _word_t(words, _ni) if _ni is not None else d*.6
    for k in range(n):
        p = _ob(_p(t, st+k*.08, .35))  # v36 (Blind C7): stagger 60-80 ms (was 120)
        if p <= 0: continue
        red = k == 0 and (t - st) > hot_t
        spr = _person(RED if red else (200, 200, 205), 1.3)
        # 720-wide layer: 4 people at spacing 160 (cx-240..cx+240) with a
        # 117-wide sprite fit with margin; 220 spacing + 1.6 scale overflowed
        # and cut the 1st/4th person off the frame edges.
        L.alpha_composite(place(spr, cx-240+k*160, cy, scale=p, alpha=min(1, p+.01)))
    if (t - st) > hot_t:
        q = _oe(_p(t, st+hot_t, .3))
        dr = ImageDraw.Draw(L)
        dr.rounded_rectangle([cx-240-85, cy-170, cx-240+85, cy+170], 20, outline=RED+(255,), width=int(2+5*q))
    return L

@reg("question", ["question", "safe", "hook", "doubt", "risk", "wonder"])
def vis_question(t, st=0, d=1.0, pack_text="", accent=Y, cx=W/2, cy=640, words=None):
    # v79.2: the pack carries the scene's own word — the old default
    # printed TOBACCO on every topic's question scene.
    """A giant '?' over a blurred pack, wobbling (Hark `question`)."""
    L = _L()
    # the pack, blurred (drawn on its own layer, Gaussian-blurred, pasted)
    pk = Image.new("RGBA", (380, 500), (0, 0, 0, 0)); dp = ImageDraw.Draw(pk)
    dp.rounded_rectangle([8, 8, 372, 492], 16, fill=(170, 28, 30, 255))
    dp.rectangle([8, 8, 372, 68], fill=(130, 18, 20, 255))
    dp.ellipse([76, 168, 304, 298], fill=(60, 10, 10, 255))
    dp.text((190, 220), pack_text, font=_font(54), fill=(240, 240, 240, 255), anchor="mm")
    pk = pk.filter(ImageFilter.GaussianBlur(6))
    L.alpha_composite(place(pk, cx-60, cy))
    p = _ob(_p(t, st+.5, .4))
    if p > 0:
        q = Image.new("RGBA", (420, 560), (0, 0, 0, 0)); dq = ImageDraw.Draw(q)
        dq.text((210, 280), "?", font=_font(520), fill=accent+(255,), anchor="mm")
        sh = math.sin(t*14)*4 if (t-st) > 0.9 else 0
        q = q.rotate(sh, expand=True, resample=Image.BICUBIC)
        L.alpha_composite(place(q, cx+170, cy-30, scale=p))
    return L

@reg("card", ["helpline", "quitline"])
def vis_card(t, st=0, d=1.0, title="", subtitle="", number="", footer="", accent=Y, cx=W/2, cy=640, words=None):
    # v79.2: title/number/footer are composed from the scene — the old
    # defaults were a past project's tobacco quitline card, number and
    # all, rendered into any topic that picked a card.
    """A contact/helpline card: cream card, title, divider, the phone number
    typed out character by character + a yellow marker sweep (Hark `card`).
    620 wide so it fits the 720-wide layer with margin (860 overflowed and
    cut the title + number off both frame edges)."""
    p = _oe(_p(t, st, .4))
    if p <= 0: return _L()
    w, h = 620, 440
    o = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dr = ImageDraw.Draw(o)
    dr.rectangle([18, 22, 612, 436], fill=(0, 0, 0, 120)); dr.rectangle([8, 8, 604, 428], fill=(232, 226, 210, 255))
    dr.text((40, 35), title, font=_font(30, "small"), fill=INK+(255,))
    dr.text((40, 85), subtitle, font=_font(30, "small"), fill=(170, 40, 40, 255))
    dr.line([40, 125, 580, 125], fill=(120, 120, 120, 255), width=2)
    # the number types out from the first digit word (Hark word_t); 1.8 s.
    _dig = [o2 for (o2, _dd, w2) in (words or []) if any(c.isdigit() for c in str(w2))]
    ts = _dig[0] if _dig else .5
    n = int(len(number)*min(1, max(0, (t-st-ts)/1.8))) if (t-st) > ts else 0
    fm = _font(72, "mono")
    if n > 0:
        if (t-st) > ts+1.9:
            q = _oe(_p(t, st+ts+1.9, .35))
            dr.rectangle([36, 165, 36+(dr.textlength(number, font=fm)+12)*q, 265], fill=(245, 205, 40, 255))
        dr.text((42, 170), number[:n], font=fm, fill=(25, 25, 25, 255))
        if int(t*4) % 2 == 0 and n < len(number):
            hw = dr.textlength(number[:n], font=fm)
            dr.rectangle([46+hw, 175, 52+hw, 255], fill=(25, 25, 25, 255))
    dr.text((40, 350), footer, font=_font(30, "small"), fill=(60, 60, 60, 255))
    o = texture(o, 8)
    return place(shadow(o), cx, cy+(1-p)*120, rot=-2, alpha=p)

@reg("watch", ["stopwatch", "rate", "seconds", "time", "every", "interval"])
def vis_watch(t, st=0, d=1.0, seconds=25, stamp="25 SECONDS", accent=Y, cx=W/2, cy=640, words=None):
    """A stopwatch with a sweeping red sector + a stamp when the rate word is
    spoken (Hark `watch`). Divya's clock has static hands; this one sweeps."""
    L = _L(); R = 250; a = _oe(_p(t, st, .4))
    if a <= 0: return L
    sub = Image.new("RGBA", (600, 700), (0, 0, 0, 0)); dd = ImageDraw.Draw(sub); c = (300, 380)
    dd.rectangle([270, 60, 330, 110], fill=WHITE+(255,)); dd.ellipse([c[0]-R, c[1]-R, c[0]+R, c[1]+R], outline=WHITE+(255,), width=12)
    for k in range(60):
        an = k*math.pi/30; r1 = R-(30 if k % 5 == 0 else 15)
        dd.line([c[0]+r1*math.sin(an), c[1]-r1*math.cos(an), c[0]+(R-6)*math.sin(an), c[1]-(R-6)*math.cos(an)], fill=WHITE+(255,), width=5 if k % 5 == 0 else 2)
    sweep = min((t-st)/max(d-.3, .5), 1)*(seconds/60)*2*math.pi
    dd.pieslice([c[0]-R+20, c[1]-R+20, c[0]+R-20, c[1]+R-20], -90, -90+math.degrees(sweep), fill=(214, 40, 40, 110))
    dd.line([c[0], c[1], c[0]+(R-40)*math.sin(sweep), c[1]-(R-40)*math.cos(sweep)], fill=Y+(255,), width=10)
    dd.ellipse([c[0]-16, c[1]-16, c[0]+16, c[1]+16], fill=Y+(255,))
    L.alpha_composite(place(sub, cx, cy-30, scale=.85+.15*a, alpha=a))
    # v34 fix: the stamp text ("25 SECONDS") is NOT drawn here — the scene
    # label below the visual already shows it (v33 dup-text rule). The watch
    # face + sweeping red sector + hand is the visual; the label carries the
    # number.
    return L

@reg("stamp_cta", ["cta", "quit", "stop", "today", "follow", "action", "stamp"])
def vis_stamp_cta(t, st=0, d=1.0, word="", stamp="", strike="", accent=Y, cx=W/2, cy=640, words=None):
    # v79.2: word/stamp/strike come from the scene — the old defaults
    # were a past project's quit-smoking CTA wording.
    """The last scene is a stamp CTA (Hark `stamp`): a huge word, a rotated
    stamp slamming in, and a strikethrough animating across the dismissive phrase."""
    L = _L()
    a1 = _ob(_p(t, st, .35))
    if a1 > 0:
        dr = ImageDraw.Draw(L)
        dr.text((cx, 620), word, font=_font(280), fill=WHITE+(255,), anchor="mm")
    _ni = _num_word_idx(words)
    _tl = _word_t(words, 1) if words and len(words) > 1 else d*.4
    if stamp and (t-st) > _tl:
        q = _oe(_p(t, st+_tl, .12))
        s = Image.new("RGBA", (900, 300), (0, 0, 0, 0)); ds = ImageDraw.Draw(s)
        ds.rounded_rectangle([10, 10, 890, 290], 20, outline=Y+(255,), width=16)
        ds.text((450, 150), stamp, font=_font(220), fill=Y+(255,), anchor="mm")
        s = s.rotate(-6, expand=True, resample=Image.BICUBIC)
        L.alpha_composite(place(s, cx, 960, scale=2.4-1.4*q, alpha=q))
    _tn = _word_t(words, 3) if words and len(words) > 3 else d*.7
    if strike and (t-st) > _tn:
        q = _oe(_p(t, st+_tn, .3))
        dr = ImageDraw.Draw(L)
        f = _font(120)
        dr.text((cx, 1290), strike, font=f, fill=(150, 150, 150, int(255*q)), anchor="mm")
        w = dr.textlength(strike, font=f)
        dr.line([cx-w/2-10, 1290, cx-w/2-10+(w+20)*_oe(_p(t, st+_tn+.25, .3)), 1283], fill=RED+(255,), width=14)
    return L

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
