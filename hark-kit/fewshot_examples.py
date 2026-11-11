# Five worked examples of per-video custom code. Each block is a different topic.
# Divya's LLM sees one or two of these as style reference, never to copy.
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from transitions_lib import _mix, _soft, _grid, _rot_plane, _project, _quad
from effects_lib import _xf, _alpha, _p, EASES

# ---------- Topic: MONEY / saving (objects: coin, wallet, piggy bank, bill, graph) ----------
# Scene change "you save 500 rupees a month": next scene is revealed through a coin-shaped hole that grows and spins.
def tr_coin_hole(A, B, p):
    if p <= 0: return A.copy()
    if p >= 1: return B.copy()
    w, h = A.size; x, y = _grid(w, h); q = EASES["expo"](p)
    sq = abs(math.cos(q*math.pi*2))*.6+.4                     # coin turning = ellipse width changes
    d = np.sqrt((((x-.5)*w/h)/sq)**2 + (y-.5)**2)/.9
    return _mix(A, B, _soft(np.clip(d, 0, 1), q, .04))

# Hit word "500": number drops in like a coin, lands with one small bounce.
def fx_coin_drop(layer, t, start, dur):
    q = _p(t, start, dur); y = -260*(1-EASES["bounce"](q))
    return _alpha(_xf(layer, dy=y, sx=1+.06*math.sin(q*math.pi*3)*(1-q)), min(1, q*3))

# ---------- Topic: SLEEP (objects: moon, pillow, eyelids, clock, stars) ----------
# Scene change "your eyes close": two eyelids (top and bottom) close over A, open on B.
def tr_eyelids(A, B, p):
    if p <= 0: return A.copy()
    if p >= 1: return B.copy()
    w, h = A.size; x, y = _grid(w, h); src = A if p < .5 else B
    k = math.sin(math.pi*p)                                    # 0 -> 1 (closed) -> 0
    lid = np.abs(y-.5)*2 + .25*((x-.5)*2)**2                   # curved lid shape
    m = (lid > (1-k)).astype(np.float32)
    dark = Image.new("RGB", (w, h), (8, 8, 14))
    return _mix(src, dark, np.clip(m, 0, 1))

# Hit word "8 hours": text breathes slowly like a sleeping chest.
def fx_breathe(layer, t, start, dur):
    q = _p(t, start, dur); s = 1+.04*math.sin(q*math.pi*2)
    return _xf(layer, s=s, dy=-6*math.sin(q*math.pi*2))

# ---------- Topic: SPACE / black hole (objects: black hole, star, orbit, light, rocket) ----------
# Scene change "light can't escape": A is pulled into the centre with a twist, B appears from the dark.
def tr_black_hole(A, B, p):
    if p <= 0: return A.copy()
    if p >= 1: return B.copy()
    w, h = A.size; q = EASES["smooth"](p)
    if q < .5:
        k = q*2; s = max(.02, 1-k); im = A.rotate(200*k, resample=Image.BILINEAR)
        im = im.resize((max(1, int(w*s)), max(1, int(h*s)))); out = Image.new("RGB", (w, h), (0, 0, 0)); out.paste(im, ((w-im.width)//2, (h-im.height)//2)); return out
    k = (q-.5)*2; x, y = _grid(w, h); d = np.sqrt(((x-.5)*w/h)**2+(y-.5)**2)/.72
    return _mix(Image.new("RGB", (w, h), (0, 0, 0)), B, _soft(np.clip(d, 0, 1), k, .2))

# Hit word "escape": word stretches toward the centre then snaps back.
def fx_spaghettify(layer, t, start, dur):
    q = _p(t, start, dur); k = math.sin(math.pi*q)
    return _xf(layer, sx=1-.25*k, sy=1+.35*k)

# ---------- Topic: HISTORY / old empire (objects: scroll, map, stone, seal, book) ----------
# Scene change "in 1500 years ago": next scene arrives as a page turning in 3D.
def tr_page(A, B, p):
    if p <= 0: return A.copy()
    if p >= 1: return B.copy()
    w, h = A.size; cv = Image.new("RGBA", (w, h), (0, 0, 0, 255)); cv.paste(B.convert("RGBA"), (0, 0))
    a = EASES["smooth"](p)*math.pi
    pts = _rot_plane(w, h, a, "y", pivot_x=-w/2)
    face = A if p < .5 else Image.blend(A.transpose(Image.FLIP_LEFT_RIGHT), Image.new("RGB", (w, h), (225, 205, 160)), .7)
    return _quad(face, _project(pts, w, h), cv).convert("RGB")

# Hit word "1500": number appears like a seal stamped down: big, fast, small shake.
def fx_stamp(layer, t, start, dur):
    q = _p(t, start, dur); s = 1.8-.8*EASES["expo"](q*1.5)
    shake = 5*math.sin(q*60)*max(0, 1-q*2) if q > .33 else 0
    return _alpha(_xf(layer, s=s, dx=shake), min(1, q*4))

# ---------- Topic: HEALTH / heart (objects: heart, ECG line, blood, pulse, doctor) ----------
# Scene change "your heart beats faster": B is revealed along a moving ECG line from left to right.
def tr_ecg_wipe(A, B, p):
    if p <= 0: return A.copy()
    if p >= 1: return B.copy()
    w, h = A.size; x, y = _grid(w, h); ph = (x*3) % 1
    spike = .12*np.exp(-((ph-.5)/.03)**2)
    field = np.clip(x - spike*np.sign(y-.5), 0, 1)
    return _mix(A, B, _soft(field, EASES["smooth"](p), .03))

# Hit word "faster": two quick beats (lub-dub).
def fx_lub_dub(layer, t, start, dur):
    q = _p(t, start, dur); k = math.exp(-((q-.15)/.06)**2)+.7*math.exp(-((q-.38)/.06)**2)
    return _xf(layer, s=1+.10*k)
