"""
Divya effects library v26  (PIL + numpy, no AI image/video generator)
Every effect is a pure function of local time t (seconds) or progress p (0..1).
Layers: draw each element on its own RGBA layer, then apply an effect, then
composite onto the frame. Background is NEVER passed to camera effects.

Tags (pick by the hit word's meaning, see EFFECTS_GUIDE.md):
  number, shock, compare, list, time, growth, drop, warning, calm, reveal,
  tech, money, health, space, history, nature, funny
"""
import math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops

W, H = 1080, 1920  # Divya renders 1080x1920 (Hark kit is 720x1280); SAFE recomputed from these
SAFE = (int(W*.08), int(H*.10), int(W*.92), int(H*.90))   # x0,y0,x1,y1

# ---------------------------------------------------------------- easing
def cl(x): return max(0.0, min(1.0, x))
def linear(t): return cl(t)
def smooth(t): t = cl(t); return t*t*(3-2*t)                      # smoothstep
def smoother(t): t = cl(t); return t*t*t*(t*(6*t-15)+10)
def out_cubic(t): t = cl(t); return 1-(1-t)**3
def in_cubic(t): t = cl(t); return t**3
def in_out_cubic(t): t = cl(t); return 4*t**3 if t < .5 else 1-(-2*t+2)**3/2
def out_expo(t): t = cl(t); return 1 if t == 1 else 1-2**(-10*t)
def out_back(t, s=1.70158): t = cl(t)-1; return 1+(s+1)*t**3+s*t**2   # pop overshoot
def out_elastic(t):
    t = cl(t)
    if t in (0, 1): return t
    return 2**(-10*t)*math.sin((t*10-.75)*(2*math.pi/3))+1
def out_bounce(t):
    t = cl(t); n, d = 7.5625, 2.75
    if t < 1/d: return n*t*t
    if t < 2/d: t -= 1.5/d; return n*t*t+.75
    if t < 2.5/d: t -= 2.25/d; return n*t*t+.9375
    t -= 2.625/d; return n*t*t+.984375
def prog(t, start, dur): return cl((t-start)/dur) if dur > 0 else float(t >= start)

EASE = {"snappy": out_back, "smooth": smoother, "glitch": linear,
        "paper": out_cubic, "typewriter": linear, "bouncy": out_bounce,
        "elastic": out_elastic, "cinematic": in_out_cubic}

# ---------------------------------------------------------------- layer helpers
def blank(): return Image.new("RGBA", (W, H), (0, 0, 0, 0))
def alpha(layer, a):
    if a >= 1: return layer
    l = layer.copy(); l.putalpha(l.getchannel("A").point(lambda v: int(v*cl(a)))); return l
def transform(layer, scale=1.0, dx=0, dy=0, rot=0.0, cx=W/2, cy=H/2):
    """scale/rotate around (cx,cy) then shift. Used by every effect."""
    if scale == 1 and dx == 0 and dy == 0 and rot == 0: return layer
    a = math.radians(rot); c, s = math.cos(a)/scale, math.sin(a)/scale
    tx, ty = cx+dx, cy+dy
    coeffs = (c, s, cx-c*tx-s*ty, -s, c, cy+s*tx-c*ty)
    return layer.transform((W, H), Image.AFFINE, coeffs, resample=Image.BICUBIC)
def bbox_ok(layer, scale=1.0):
    """safe-margin check at max scale. Returns True if inside SAFE."""
    b = transform(layer, scale).getbbox()
    if not b: return True
    return b[0] >= SAFE[0] and b[1] >= SAFE[1] and b[2] <= SAFE[2] and b[3] <= SAFE[3]
def fit_safe(layer, max_scale=1.06):
    """shrink element until it stays inside SAFE at max_scale."""
    s = 1.0
    while not bbox_ok(transform(layer, s), max_scale) and s > .5: s -= .03
    return transform(layer, s)

# ================================================================ ENTER effects
def fade_in(L, t, st=0, d=.3): return alpha(L, smooth(prog(t, st, d)))                       # calm
def pop_in(L, t, st=0, d=.35, cx=W/2, cy=H/2):                                               # number, shock
    p = prog(t, st, d); return alpha(transform(L, max(.01, out_back(p)), cx=cx, cy=cy), min(1, p*3))
def slide_in(L, t, st=0, d=.4, frm="left", dist=260):                                        # list, compare
    p = out_cubic(prog(t, st, d)); k = (1-p)*dist
    dx, dy = {"left": (-k, 0), "right": (k, 0), "up": (0, -k), "down": (0, k)}[frm]
    return alpha(transform(L, dx=dx, dy=dy), p)
def rise_in(L, t, st=0, d=.45): return slide_in(L, t, st, d, "down", 120)                    # growth
def drop_in(L, t, st=0, d=.6):                                                               # drop, funny
    p = out_bounce(prog(t, st, d)); return transform(L, dy=-(1-p)*500)
def zoom_in_blur(L, t, st=0, d=.4):                                                          # reveal, cinematic
    p = out_expo(prog(t, st, d)); l = transform(L, 1.6-.6*p)
    r = (1-p)*12
    return alpha(l.filter(ImageFilter.GaussianBlur(r)) if r > .5 else l, p)
def wipe_in(L, t, st=0, d=.4, direction="left"):                                             # reveal, history
    p = in_out_cubic(prog(t, st, d)); m = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(m)
    if direction == "left": dr.rectangle([0, 0, int(W*p), H], 255)
    elif direction == "up": dr.rectangle([0, int(H*(1-p)), W, H], 255)
    else: dr.rectangle([int(W*(1-p)), 0, W, H], 255)
    out = L.copy(); out.putalpha(ImageChops.multiply(L.getchannel("A"), m)); return out
def iris_in(L, t, st=0, d=.45, cx=W/2, cy=H/2):                                              # space, reveal
    p = out_cubic(prog(t, st, d)); r = int(p*math.hypot(W, H))
    m = Image.new("L", (W, H), 0); ImageDraw.Draw(m).ellipse([cx-r, cy-r, cx+r, cy+r], 255)
    out = L.copy(); out.putalpha(ImageChops.multiply(L.getchannel("A"), m)); return out
def spin_in(L, t, st=0, d=.5, cx=W/2, cy=H/2):                                               # money (coin), funny
    p = out_back(prog(t, st, d)); return alpha(transform(L, max(.01, p), rot=(1-p)*180, cx=cx, cy=cy), cl(p))
def flip_in(L, t, st=0, d=.45, cx=W/2):                                                      # money, compare
    p = out_cubic(prog(t, st, d)); sx = max(.02, abs(math.cos((1-p)*math.pi/2)))
    a = math.radians(0); coeffs = (1/sx, 0, cx-cx/sx, 0, 1, 0)
    return L.transform((W, H), Image.AFFINE, coeffs, resample=Image.BICUBIC)
def glitch_in(L, t, st=0, d=.35, seed=1):                                                    # tech, warning
    p = prog(t, st, d)
    if p >= 1: return L
    rnd = random.Random(int(t*60)+seed); a = np.array(L); out = np.zeros_like(a)
    for y in range(0, H, 16):
        sh = int(rnd.uniform(-40, 40)*(1-p)); out[y:y+16] = np.roll(a[y:y+16], sh, axis=1)
    out[..., 0] = np.roll(out[..., 0], int(8*(1-p)), axis=1)                                  # RGB split
    return alpha(Image.fromarray(out), .4+.6*p)
def typewriter(draw_fn, text, t, st=0, cps=22):                                              # time, tech, history
    """draw_fn(text_so_far) -> layer. Characters appear at cps chars/sec."""
    n = int(cl((t-st)*cps/ max(1, len(text)))*len(text)); return draw_fn(text[:n])
def draw_on_line(points, t, st=0, d=.6, col=(255, 210, 0, 255), w=6):                         # growth, health, compare
    """stroke draws itself along a polyline (chart lines, heartbeat, arrows)."""
    p = smoother(prog(t, st, d)); L = blank(); dr = ImageDraw.Draw(L)
    seg = [math.dist(points[i], points[i+1]) for i in range(len(points)-1)]; tot = sum(seg)*p
    pts = [points[0]]
    for i, s in enumerate(seg):
        if tot >= s: pts.append(points[i+1]); tot -= s
        else:
            f = tot/s if s else 0; a, b = points[i], points[i+1]
            pts.append((a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f)); break
    if len(pts) > 1: dr.line(pts, fill=col, width=w, joint="curve")
    return L
def stagger(items, t, st=0, gap=.12, fx=None, **kw):                                         # list
    """items: list of layers. Each enters gap seconds after the previous."""
    fx = fx or pop_in; L = blank()
    for i, it in enumerate(items): L.alpha_composite(fx(it, t, st+i*gap, **kw))
    return L

# ================================================================ EMPHASIS effects (on the hit word)
def punch(L, t, at, d=.3, amt=.10, cx=W/2, cy=H/2):                                          # shock, number
    p = prog(t, at, d); k = amt*math.sin(p*math.pi)*(1-p*.3); return transform(L, 1+k, cx=cx, cy=cy)
def shake(L, t, at, d=.3, px=10):                                                            # warning, shock
    p = prog(t, at, d)
    if p <= 0 or p >= 1: return L
    k = px*(1-p); return transform(L, dx=math.sin(t*90)*k, dy=math.cos(t*70)*k)
def pulse(L, t, period=.8, amt=.04, cx=W/2, cy=H/2):                                          # health, time
    return transform(L, 1+amt*(.5+.5*math.sin(2*math.pi*t/period)), cx=cx, cy=cy)
def wiggle(L, t, at, d=.5, deg=6, cx=W/2, cy=H/2):                                            # funny
    p = prog(t, at, d); return transform(L, rot=deg*math.sin(p*math.pi*6)*(1-p), cx=cx, cy=cy)
def glow(L, t, at, d=.5, col=(255, 210, 0), r=18):                                            # reveal, number
    p = prog(t, at, d); k = math.sin(p*math.pi) if 0 < p < 1 else 0
    if k <= 0: return L
    g = Image.new("RGBA", (W, H), col+(0,)); g.putalpha(L.getchannel("A").filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(v*k)))
    out = blank(); out.alpha_composite(g); out.alpha_composite(L); return out
def flash(t, at, d=.18, col=(255, 255, 255)):                                                 # shock (full-screen, very short)
    p = prog(t, at, d); a = int(120*(1-p)) if 0 < p < 1 else 0
    return Image.new("RGBA", (W, H), col+(a,))
def underline_draw(x0, x1, y, t, at, d=.3, col=(255, 210, 0, 255), w=8):                       # key word
    return draw_on_line([(x0, y), (x1, y)], t, at, d, col, w)
def circle_draw(cx, cy, r, t, at, d=.5, col=(255, 60, 60, 255), w=7):                          # warning, highlight
    pts = [(cx+r*math.cos(a), cy+r*.8*math.sin(a)) for a in np.linspace(-2.2, 2*math.pi-2.0, 60)]
    return draw_on_line(pts, t, at, d, col, w)
def count_up(t, st, d, target, fmt="{:,.0f}", ease_fn=out_expo):                              # number
    return fmt.format(target*ease_fn(prog(t, st, d)))
def ring_fill(cx, cy, r, pct, t, st, d=.9, col=(255, 210, 0, 255), bg=(255, 255, 255, 40), w=26):   # number (percent)
    L = blank(); dr = ImageDraw.Draw(L); box = [cx-r, cy-r, cx+r, cy+r]
    dr.arc(box, 0, 360, fill=bg, width=w)
    e = -90+360*pct/100*out_cubic(prog(t, st, d))
    if e > -90: dr.arc(box, -90, e, fill=col, width=w)
    return L
def bar_grow(x, y_base, bw, h_max, t, st, d=.6, col=(255, 210, 0, 255)):                       # compare, growth
    h = h_max*out_back(prog(t, st, d), 1.2); L = blank()
    ImageDraw.Draw(L).rounded_rectangle([x, y_base-h, x+bw, y_base], 10, fill=col); return L

# ================================================================ EXIT effects
def fade_out(L, t, st, d=.25): return alpha(L, 1-smooth(prog(t, st, d)))
def shrink_out(L, t, st, d=.25): p = in_cubic(prog(t, st, d)); return alpha(transform(L, max(.01, 1-p)), 1-p)
def slide_out(L, t, st, d=.3, to="left", dist=300):
    p = in_cubic(prog(t, st, d)); k = p*dist
    dx, dy = {"left": (-k, 0), "right": (k, 0), "up": (0, -k), "down": (0, k)}[to]
    return alpha(transform(L, dx=dx, dy=dy), 1-p)

# ================================================================ CAMERA (content layer only!)
def push_in(content, t, scene_dur, amt=.06):                                                  # calm, cinematic
    return transform(content, 1+amt*smooth(t/scene_dur))
def drift(content, t, scene_dur, px=24, direction=1):                                         # calm, nature
    return transform(content, dx=direction*px*(smooth(t/scene_dur)-.5))

# ================================================================ TRANSITIONS (A = old frame RGB, B = new frame RGB, p 0..1)
def tr_crossfade(A, B, p): return Image.blend(A, B, smooth(p))                                # calm
def tr_push(A, B, p, direction="left"):                                                       # list, story
    p = in_out_cubic(p); out = Image.new("RGB", (W, H)); k = int(W*p)
    if direction == "left": out.paste(A, (-k, 0)); out.paste(B, (W-k, 0))
    else: k = int(H*p); out.paste(A, (0, -k)); out.paste(B, (0, H-k))
    return out
def tr_whip(A, B, p):                                                                         # energetic, tech
    out = tr_push(A, B, p); r = 25*math.sin(p*math.pi)
    return out.filter(ImageFilter.BoxBlur(r)) if r > 1 else out
def tr_zoom_through(A, B, p):                                                                 # space, reveal
    if p < .5:
        s = 1+2*in_cubic(p*2); a = A.resize((int(W*s), int(H*s))); x, y = (a.width-W)//2, (a.height-H)//2
        return a.crop((x, y, x+W, y+H)).filter(ImageFilter.GaussianBlur(8*p))
    s = 1.6-.6*out_cubic((p-.5)*2); b = B.resize((int(W*s), int(H*s))); x, y = (b.width-W)//2, (b.height-H)//2
    return b.crop((x, y, x+W, y+H))
def tr_iris(A, B, p, cx=W/2, cy=H/2):                                                         # space, focus
    r = int(out_cubic(p)*math.hypot(W, H)); m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).ellipse([cx-r, cy-r, cx+r, cy+r], 255); return Image.composite(B, A, m)
def tr_wipe_bar(A, B, p, col=(255, 210, 0)):                                                  # bold, news
    p = in_out_cubic(p); out = A.copy() if p < .5 else B.copy(); dr = ImageDraw.Draw(out)
    x = int(-W*.3+W*1.6*p); dr.polygon([(x, 0), (x+W*.3, 0), (x+W*.1, H), (x-W*.2, H)], fill=col); return out
def tr_glitch(A, B, p, seed=3):                                                               # tech, phone, warning
    src = np.array(A if p < .5 else B); rnd = random.Random(int(p*30)+seed); k = math.sin(p*math.pi)
    for y in range(0, H, 24):
        if rnd.random() < .5*k: src[y:y+24] = np.roll(src[y:y+24], int(rnd.uniform(-80, 80)*k), axis=1)
    src[..., 2] = np.roll(src[..., 2], int(12*k), axis=1); return Image.fromarray(src)
def tr_paper_tear(A, B, p, seed=5):                                                           # history, retro
    rnd = random.Random(seed); y = H*in_out_cubic(p); m = Image.new("L", (W, H), 0)
    edge = [(x, y+rnd.uniform(-25, 25)) for x in range(0, W+40, 40)]
    ImageDraw.Draw(m).polygon([(0, 0), (W, 0), *reversed(edge)], 255)   # torn top part = new scene
    return Image.composite(B, A, m)
def tr_heartbeat(A, B, p, col=(255, 70, 90)):                                                 # health
    pts, cy = [], H/2
    for i, x in enumerate(range(0, W+1, 12)):
        f = x/W; yy = cy - (220 if .45 < f < .5 else -160 if .5 <= f < .55 else 0)
        pts.append((x, yy))
    base = A if p < .6 else B
    out = base.convert("RGBA"); out.alpha_composite(draw_on_line(pts, p, 0, .6, col+(255,), 8)); return out.convert("RGB")
def tr_coin_flip(A, B, p):                                                                    # money
    sx = abs(math.cos(p*math.pi)); src = A if p < .5 else B
    w = max(2, int(W*sx)); out = Image.new("RGB", (W, H), (10, 10, 10)); out.paste(src.resize((w, H)), ((W-w)//2, 0)); return out
def tr_screen_swipe(A, B, p, col=(20, 20, 24)):                                               # phone, apps
    p = in_out_cubic(p); out = A.copy(); k = int(H*p)
    out.paste(B.crop((0, H-k, W, H)), (0, H-k)) if k > 0 else None
    ImageDraw.Draw(out).rounded_rectangle([W*.35, H-k-14, W*.65, H-k-6], 4, fill=(230, 230, 230)); return out
def tr_ink_spread(A, B, p, seed=7):                                                           # art, nature
    rnd = random.Random(seed); m = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(m); r = out_cubic(p)*900
    for i in range(14):
        cx, cy = rnd.uniform(0, W), rnd.uniform(0, H); rr = r*rnd.uniform(.4, 1)
        dr.ellipse([cx-rr, cy-rr, cx+rr, cy+rr], 255)
    return Image.composite(B, A, m.filter(ImageFilter.GaussianBlur(6)))

TRANSITIONS = {
    "crossfade": (tr_crossfade, ["calm"]), "push": (tr_push, ["list", "story"]),
    "whip": (tr_whip, ["energetic", "tech"]), "zoom_through": (tr_zoom_through, ["space", "reveal"]),
    "iris": (tr_iris, ["space", "focus"]), "wipe_bar": (tr_wipe_bar, ["news", "bold"]),
    "glitch": (tr_glitch, ["tech", "phone", "warning"]), "paper_tear": (tr_paper_tear, ["history", "retro"]),
    "heartbeat": (tr_heartbeat, ["health"]), "coin_flip": (tr_coin_flip, ["money"]),
    "screen_swipe": (tr_screen_swipe, ["phone", "apps"]), "ink_spread": (tr_ink_spread, ["art", "nature"]),
}
ENTER = {"fade_in": ["calm"], "pop_in": ["number", "shock"], "slide_in": ["list", "compare"],
         "rise_in": ["growth"], "drop_in": ["drop", "funny"], "zoom_in_blur": ["reveal"],
         "wipe_in": ["reveal", "history"], "iris_in": ["space"], "spin_in": ["money", "funny"],
         "flip_in": ["money", "compare"], "glitch_in": ["tech", "warning"], "typewriter": ["time", "tech", "history"],
         "draw_on_line": ["growth", "health", "compare"], "stagger": ["list"]}
EMPHASIS = {"punch": ["shock", "number"], "shake": ["warning", "shock"], "pulse": ["health", "time"],
            "wiggle": ["funny"], "glow": ["reveal", "number"], "flash": ["shock"],
            "underline_draw": ["keyword"], "circle_draw": ["warning", "keyword"],
            "count_up": ["number"], "ring_fill": ["number", "percent"], "bar_grow": ["compare", "growth"]}

def pick(table, tags, used, rnd=random):
    """choose an effect whose tags match; avoid ones used >=2 times this video."""
    c = [k for k, v in table.items() if set(v if isinstance(v, list) else v[1]) & set(tags) and used.get(k, 0) < 2]
    if not c: c = [k for k in table if used.get(k, 0) < 2] or list(table)
    k = rnd.choice(c); used[k] = used.get(k, 0)+1; return k

if __name__ == "__main__":   # smoke test: renders a contact sheet of transitions
    A = Image.new("RGB", (W, H), (15, 15, 20)); ImageDraw.Draw(A).text((300, 600), "A", fill=(255, 210, 0))
    B = Image.new("RGB", (W, H), (30, 60, 90)); ImageDraw.Draw(B).text((300, 600), "B", fill=(255, 255, 255))
    tiles = [fn(A, B, .5).resize((180, 320)) for fn, _ in TRANSITIONS.values()]
    sheet = Image.new("RGB", (180*6, 320*2))
    for i, tl in enumerate(tiles): sheet.paste(tl, ((i % 6)*180, (i//6)*320))
    sheet.save("fx_test.png")
    L = blank(); ImageDraw.Draw(L).rectangle([200, 500, 520, 780], fill=(255, 210, 0, 255))
    for name in ["fade_in", "pop_in", "slide_in", "rise_in", "drop_in", "zoom_in_blur", "wipe_in", "iris_in", "spin_in", "flip_in", "glitch_in"]:
        globals()[name](L, .2, 0)
    for f in [punch, shake, wiggle, glow]: f(L, .1, 0)
    pulse(L, .3); ring_fill(360, 640, 200, 89, .5, 0); bar_grow(100, 900, 80, 300, .3, 0); count_up(.3, 0, .6, 96)
    print("ok", len(ENTER), "enter,", len(EMPHASIS), "emphasis,", len(TRANSITIONS), "transitions")
