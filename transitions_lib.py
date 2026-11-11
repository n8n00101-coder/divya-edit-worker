"""
Divya transitions library v29 - 300+ procedural transitions, incl. 3D.
Pure Python: PIL + numpy. No AI image/video generator.

Every transition: fn(A, B, p) -> Image (RGB), A = outgoing frame, B = incoming,
p = 0..1 progress. Frames can be any size (720x1280 default).

Usage:
    from transitions_lib import REGISTRY, pick_transition
    t = pick_transition(tags={"space"}, used=set(), seed=42)
    frame = t["fn"](A, B, p)

Families (each is a generator, so count grows by combining parameters):
  masks     - wipes by shape x direction x softness   (linear, radial, diamond, clock,
              barn, blinds, checker, blocks, noise, spiral, box, star, heart, wave, zigzag)
  motion    - push / cover / uncover / split-slide x 8 directions
  zoom_blur - zoom-through, zoom-out, spin-zoom, whip-blur, blur-dissolve, stretch
  color     - dip to color, flash, luma fade, pixelate, rgb split glitch, posterize
  3d        - cube rotate, card flip, door open, fold, page turn, tilt-zoom, carousel,
              swing, roll, perspective slide
"""
import math, random
import numpy as np
from PIL import Image, ImageFilter, ImageDraw

# ---------- easing ----------
def _c(t): return max(0.0, min(1.0, t))
EASES = {
    "linear": lambda t: _c(t),
    "smooth": lambda t: (lambda x: x*x*x*(x*(6*x-15)+10))(_c(t)),
    "expo":   lambda t: (lambda x: 1 if x == 1 else 1-2**(-10*x))(_c(t)),
    "back":   lambda t: (lambda x: 1+2.70158*(x-1)**3+1.70158*(x-1)**2)(_c(t)),
}

def _arr(im): return np.asarray(im.convert("RGB"), dtype=np.float32)
def _img(a): return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
def _grid(w, h):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return x / max(w-1, 1), y / max(h-1, 1)          # 0..1 coords

def _mix(A, B, m):
    """m: HxW float mask 0..1 (1 = show B)."""
    a, b = _arr(A), _arr(B)
    return _img(a*(1-m[..., None]) + b*m[..., None])

def _soft(field, p, soft):
    """field: 0..1 'arrival order' map. Returns mask for progress p."""
    if soft <= 0:
        return (field <= p).astype(np.float32)
    lo = p*(1+soft) - soft
    return np.clip((p*(1+soft) - field) / soft, 0, 1) if True else lo

_RNG_CACHE = {}
def _noise(w, h, seed, scale=1):
    key = (w, h, seed, scale)
    if key not in _RNG_CACHE:
        r = np.random.default_rng(seed)
        small = r.random((max(2, h//(8*scale)), max(2, w//(8*scale)))).astype(np.float32)
        _RNG_CACHE[key] = np.asarray(Image.fromarray((small*255).astype(np.uint8)).resize((w, h), Image.BICUBIC), dtype=np.float32)/255
    return _RNG_CACHE[key]

# ---------- mask field shapes (return 0..1 "when does this pixel switch") ----------
def f_linear(w, h, angle):
    x, y = _grid(w, h); a = math.radians(angle)
    v = x*math.cos(a) + y*math.sin(a)
    return (v - v.min())/(v.max() - v.min() + 1e-6)
def f_radial(w, h, cx=.5, cy=.5, inv=False):
    x, y = _grid(w, h); d = np.sqrt(((x-cx)*w/h)**2 + (y-cy)**2); d = d/d.max()
    return 1-d if inv else d
def f_diamond(w, h, inv=False):
    x, y = _grid(w, h); d = np.abs(x-.5)*w/h + np.abs(y-.5); d = d/d.max()
    return 1-d if inv else d
def f_box(w, h, inv=False):
    x, y = _grid(w, h); d = np.maximum(np.abs(x-.5), np.abs(y-.5)); d = d/d.max()
    return 1-d if inv else d
def f_clock(w, h, start=0, ccw=False):
    x, y = _grid(w, h); a = (np.arctan2(y-.5, x-.5) + math.pi/2 - math.radians(start)) % (2*math.pi)
    v = a/(2*math.pi); return 1-v if ccw else v
def f_barn(w, h, vertical=False, inv=False):
    x, y = _grid(w, h); d = np.abs((y if vertical else x)-.5)*2
    return 1-d if inv else d
def f_blinds(w, h, n, vertical=False):
    x, y = _grid(w, h); c = y if vertical else x
    return (c*n) % 1.0
def f_checker(w, h, n):
    x, y = _grid(w, h); cx = np.floor(x*n); cy = np.floor(y*n*h/w)
    par = (cx+cy) % 2; local = (x*n) % 1
    return np.clip(par*.5 + local*.5, 0, 1)
def f_blocks(w, h, n, seed):
    x, y = _grid(w, h); r = np.random.default_rng(seed)
    cols, rows = n, max(1, int(n*h/w)); vals = r.random((rows, cols)).astype(np.float32)
    return vals[np.minimum((y*rows).astype(int), rows-1), np.minimum((x*cols).astype(int), cols-1)]
def f_noise(w, h, seed, scale): return _noise(w, h, seed, scale)
def f_spiral(w, h, turns, ccw=False):
    x, y = _grid(w, h); a = (np.arctan2(y-.5, x-.5) + math.pi)/(2*math.pi)
    if ccw: a = 1-a
    d = np.sqrt(((x-.5)*w/h)**2 + (y-.5)**2); d = d/d.max()
    v = (a + d*turns) / (1+turns); return v
def f_star(w, h, points):
    x, y = _grid(w, h); a = np.arctan2(y-.5, x-.5); d = np.sqrt(((x-.5)*w/h)**2 + (y-.5)**2)
    r = d / (0.6 + 0.4*np.cos(points*a)); return r/r.max()
def f_heart(w, h):
    x, y = _grid(w, h); X = (x-.5)*2.4*w/h; Y = -(y-.45)*2.4
    v = (X**2 + Y**2 - 1)**3 - X**2*Y**3
    v = np.cbrt(v); v = (v - v.min())/(v.max()-v.min()); return v
def f_wave(w, h, angle, freq, amp=.08):
    base = f_linear(w, h, angle); x, y = _grid(w, h)
    perp = y if angle % 180 in (0,) else x
    v = base + amp*np.sin(perp*freq*2*math.pi); return (v-v.min())/(v.max()-v.min())
def f_zigzag(w, h, angle, n, amp=.06):
    base = f_linear(w, h, angle); x, y = _grid(w, h)
    perp = y if angle % 180 == 0 else x
    tri = np.abs((perp*n) % 1 - .5)*2
    v = base + amp*tri; return (v-v.min())/(v.max()-v.min())

_FIELD_CACHE = {}
def _field(key, w, h, fn):
    k = (key, w, h)
    if k not in _FIELD_CACHE:
        _FIELD_CACHE[k] = fn(w, h).astype(np.float32)
    return _FIELD_CACHE[k]

def make_mask_tr(key, fieldfn, soft, ease):
    e = EASES[ease]
    def tr(A, B, p):
        w, h = A.size; f = _field(key, w, h, fieldfn)
        return _mix(A, B, _soft(f, e(p), soft))
    return tr

# ---------- motion ----------
DIRS = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1),
        "up_left": (-1, -1), "up_right": (1, -1), "down_left": (-1, 1), "down_right": (1, 1)}

def make_motion_tr(kind, d, ease):
    e = EASES[ease]; dx, dy = DIRS[d]
    def tr(A, B, p):
        w, h = A.size; q = e(p); out = Image.new("RGB", (w, h))
        ox, oy = int(dx*w*q), int(dy*h*q)        # A moves this way
        if kind == "push":
            out.paste(A, (ox, oy)); out.paste(B, (ox - dx*w, oy - dy*h))
        elif kind == "cover":
            out.paste(A, (0, 0)); out.paste(B, (int(-dx*w*(1-q)), int(-dy*h*(1-q))))
        elif kind == "uncover":
            out.paste(B, (0, 0)); out.paste(A, (ox, oy))
        elif kind == "split":                     # A splits in two halves moving apart
            out.paste(B, (0, 0))
            if dy == 0:
                top = A.crop((0, 0, w, h//2)); bot = A.crop((0, h//2, w, h))
                out.paste(top, (int(-w*q*abs(dx)) if dx < 0 else int(w*q), 0)); out.paste(bot, (int(w*q) if dx < 0 else int(-w*q), h//2))
            else:
                l = A.crop((0, 0, w//2, h)); r = A.crop((w//2, 0, w, h))
                out.paste(l, (0, int(-h*q) if dy < 0 else int(h*q))); out.paste(r, (w//2, int(h*q) if dy < 0 else int(-h*q)))
        return out
    return tr

# ---------- zoom / blur ----------
def _scale_center(im, s, rot=0):
    w, h = im.size
    if rot: im = im.rotate(rot, resample=Image.BILINEAR)
    nw, nh = max(1, int(w*s)), max(1, int(h*s)); r = im.resize((nw, nh), Image.BILINEAR)
    out = Image.new("RGB", (w, h)); out.paste(r, ((w-nw)//2, (h-nh)//2)); return out

def make_zoom_tr(kind, strength, ease):
    e = EASES[ease]
    def tr(A, B, p):
        q = e(p); w, h = A.size
        if kind == "zoom_through":
            a = _scale_center(A, 1+strength*q); b = _scale_center(B, 1/(1+strength*(1-q))*1.0 if q > 0 else .01)
            if q < .5: return Image.blend(a, a.filter(ImageFilter.GaussianBlur(8*q)), .5)
            return Image.blend(a, _scale_center(B, 1+strength*(1-q)), min(1, (q-.4)/.6))
        if kind == "zoom_out":
            return Image.blend(_scale_center(A, max(.05, 1-.5*strength*q)), _scale_center(B, 1+.3*strength*(1-q)), q)
        if kind == "spin_zoom":
            a = _scale_center(A, 1+strength*q, rot=90*q*strength); b = _scale_center(B, 1+strength*(1-q), rot=-90*(1-q)*strength)
            return Image.blend(a, b, q)
        if kind == "blur_dissolve":
            r = 18*strength*math.sin(math.pi*q)
            return Image.blend(A, B, q).filter(ImageFilter.GaussianBlur(r)) if r > .5 else Image.blend(A, B, q)
        if kind.startswith("whip_"):
            d = kind.split("_")[1]; dx, dy = DIRS[d]; out = make_motion_tr("push", d, "expo")(A, B, p)
            k = int(2 + 60*strength*math.sin(math.pi*q))
            arr = _arr(out); acc = np.zeros_like(arr)
            for i in range(0, k, max(1, k//6)):
                acc += np.roll(arr, (i*dy, i*dx), axis=(0, 1))
            return _img(acc/len(range(0, k, max(1, k//6))))
        if kind.startswith("stretch_"):
            vertical = kind.endswith("v")
            s = 1+3*strength*math.sin(math.pi*q)
            src = A if q < .5 else B
            if vertical: r = src.resize((w, int(h*s))); return r.crop((0, (r.height-h)//2, w, (r.height-h)//2+h))
            r = src.resize((int(w*s), h)); return r.crop(((r.width-w)//2, 0, (r.width-w)//2+w, h))
        return Image.blend(A, B, q)
    return tr

# ---------- color ----------
COLORS = {"black": (0, 0, 0), "white": (255, 255, 255), "yellow": (255, 210, 0),
          "red": (230, 50, 60), "blue": (40, 110, 255), "brand_dark": (18, 18, 24)}

def make_color_tr(kind, param, ease):
    e = EASES[ease]
    def tr(A, B, p):
        q = e(p); w, h = A.size
        if kind == "dip":
            c = Image.new("RGB", (w, h), COLORS[param])
            return Image.blend(A, c, q*2) if q < .5 else Image.blend(c, B, (q-.5)*2)
        if kind == "flash":
            c = Image.new("RGB", (w, h), COLORS[param]); k = max(0, 1-abs(q-.5)*6)
            return Image.blend(A if q < .5 else B, c, k)
        if kind == "luma":
            la = np.asarray(A.convert("L"), dtype=np.float32)/255
            f = la if param == "bright_first" else 1-la
            return _mix(A, B, _soft(f, q, .25))
        if kind == "pixelate":
            n = max(1, int(param*math.sin(math.pi*q)))+1; src = A if q < .5 else B
            return src.resize((max(1, w//n), max(1, h//n)), Image.NEAREST).resize((w, h), Image.NEAREST)
        if kind == "rgb_split":
            src = _arr(A if q < .5 else B); k = int(param*math.sin(math.pi*q))
            out = src.copy(); out[..., 0] = np.roll(src[..., 0], k, 1); out[..., 2] = np.roll(src[..., 2], -k, 1)
            return _img(out)
        if kind == "posterize":
            lv = max(2, int(2 + (param-2)*(1-math.sin(math.pi*q))))
            mixd = _arr(Image.blend(A, B, q)); step = 255/(lv-1)
            return _img(np.round(mixd/step)*step)
        return Image.blend(A, B, q)
    return tr

# ---------- 3D (true perspective warp) ----------
def _persp_coeffs(dst, src):
    """dst: 4 corner points where src corners land. Returns PIL PERSPECTIVE coeffs."""
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u*x, -u*y]); m.append([0, 0, 0, x, y, 1, -v*x, -v*y])
    A = np.array(m, dtype=np.float64); b = np.array([c for pt in src for c in pt], dtype=np.float64)
    return np.linalg.lstsq(A, b, rcond=None)[0].tolist()

def _project(pts3, w, h, fov=1.6):
    f = fov*w; out = []
    for x, y, z in pts3:
        z = z + f; out.append((w/2 + x*f/z, h/2 + y*f/z))
    return out

def _quad(img, quad, canvas):
    w, h = img.size; src = [(0, 0), (w, 0), (w, h), (0, h)]
    xs = [q[0] for q in quad]; ys = [q[1] for q in quad]
    if (max(xs)-min(xs)) < 2 or (max(ys)-min(ys)) < 2: return canvas
    co = _persp_coeffs(quad, src)
    warped = img.convert("RGBA").transform(canvas.size, Image.PERSPECTIVE, co, Image.BILINEAR)
    mask = Image.new("L", canvas.size, 0); ImageDraw.Draw(mask).polygon(quad, fill=255)
    canvas.paste(warped, (0, 0), mask); return canvas

def _rot_plane(w, h, ang, axis, pivot_z=0, pivot_x=0, pivot_y=0, shift=(0, 0, 0)):
    """corners of a w x h plane centred at origin, rotated about axis through pivot."""
    c, s = math.cos(ang), math.sin(ang); out = []
    for x, y in [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]:
        x0, y0, z0 = x-pivot_x, y-pivot_y, -pivot_z
        if axis == "y": x1, y1, z1 = x0*c + z0*s, y0, -x0*s + z0*c
        else:           x1, y1, z1 = x0, y0*c - z0*s, y0*s + z0*c
        out.append((x1+pivot_x+shift[0], y1+pivot_y+shift[1], z1+pivot_z+shift[2]))
    return out

def make_3d_tr(kind, d, ease, bg=(10, 10, 14)):
    e = EASES[ease]
    sign = 1 if d in ("left", "up") else -1
    axis = "y" if d in ("left", "right") else "x"
    def tr(A, B, p):
        w, h = A.size; q = e(p); cv = Image.new("RGBA", (w, h), bg + (255,))
        size = w if axis == "y" else h
        if kind == "cube":
            a = sign*q*math.pi/2; half = size/2
            fa = _rot_plane(w, h, a, axis, pivot_z=half); fb = _rot_plane(w, h, a - sign*math.pi/2, axis, pivot_z=half)
            faces = [(A, fa), (B, fb)]
            faces.sort(key=lambda t: -sum(pt[2] for pt in t[1]))
            for im, pts in faces:
                if sum(pt[2] for pt in pts)/4 < half*1.01: cv = _quad(im, _project(pts, w, h), cv)
        elif kind == "flip":
            a = sign*q*math.pi
            if q < .5: cv = _quad(A, _project(_rot_plane(w, h, a, axis, shift=(0, 0, 0)), w, h), cv)
            else:      cv = _quad(B, _project(_rot_plane(w, h, a - sign*math.pi, axis), w, h), cv)
        elif kind == "door":
            cv.paste(B.convert("RGBA"), (0, 0)); a = sign*q*math.pi*.55
            px = (-w/2 if sign > 0 else w/2) if axis == "y" else 0; py = 0 if axis == "y" else (-h/2 if sign > 0 else h/2)
            cv = _quad(A, _project(_rot_plane(w, h, a, axis, pivot_x=px, pivot_y=py), w, h), cv)
        elif kind == "fold":
            cv.paste(B.convert("RGBA"), (0, 0)); a = sign*q*math.pi/2
            if axis == "y":
                l = A.crop((0, 0, w//2, h)); r = A.crop((w//2, 0, w, h))
                cv = _quad(l, _project(_rot_plane(w/2, h, a, "y", pivot_x=-w/4, shift=(-w/4, 0, 0)), w, h), cv)
                cv = _quad(r, _project(_rot_plane(w/2, h, -a, "y", pivot_x=w/4, shift=(w/4, 0, 0)), w, h), cv)
            else:
                t = A.crop((0, 0, w, h//2)); b = A.crop((0, h//2, w, h))
                cv = _quad(t, _project(_rot_plane(w, h/2, a, "x", pivot_y=-h/4, shift=(0, -h/4, 0)), w, h), cv)
                cv = _quad(b, _project(_rot_plane(w, h/2, -a, "x", pivot_y=h/4, shift=(0, h/4, 0)), w, h), cv)
        elif kind == "tilt_zoom":
            a = sign*math.sin(math.pi*q)*.35; z = size*1.2*math.sin(math.pi*q)
            cv = _quad(A if q < .5 else B, _project(_rot_plane(w, h, a, axis, shift=(0, 0, z)), w, h), cv)
        elif kind == "carousel":
            R = size*.9; a = sign*q*math.pi/2.2
            for im, off in ((A, 0), (B, -sign*math.pi/2.2)):
                ang = a+off; sx = R*math.sin(ang) if axis == "y" else 0; sy = R*math.sin(ang) if axis == "x" else 0
                pts = _rot_plane(w*.8, h*.8, ang, axis, shift=(sx, sy, R*(1-math.cos(ang))+size*.25))
                cv = _quad(im, _project(pts, w, h), cv)
        elif kind == "swing":
            px = 0; py = -h/2 if axis == "y" else 0
            a = (1-q)*sign*math.pi/2*(1 if q < 1 else 0)
            cv.paste(A.convert("RGBA"), (0, 0))
            cv = _quad(B, _project(_rot_plane(w, h, a, "x", pivot_y=-h/2), w, h), cv)
        elif kind == "roll":
            src = A if q < .5 else B; rot = sign*(q*360 if q < .5 else (q-1)*360)
            s = 1-.5*math.sin(math.pi*q); im = _scale_center(src, s, rot=rot); cv.paste(im.convert("RGBA"), (0, 0))
        elif kind == "page_turn":
            cv.paste(B.convert("RGBA"), (0, 0)); a = sign*q*math.pi
            pts = _rot_plane(w, h, a, axis, pivot_x=(-w/2 if axis == "y" else 0), pivot_y=(0 if axis == "y" else -h/2))
            shade = A if q < .5 else Image.blend(A.transpose(Image.FLIP_LEFT_RIGHT), Image.new("RGB", (w, h), (235, 235, 235)), .6)
            cv = _quad(shade, _project(pts, w, h), cv)
        elif kind == "persp_slide":
            for im, off in ((A, -q), (B, 1-q)):
                x = off*w*sign*-1 if axis == "y" else 0; y = off*h*sign*-1 if axis == "x" else 0
                pts = _rot_plane(w, h, .45*off*sign, axis, shift=(x, y, abs(off)*size*.5))
                cv = _quad(im, _project(pts, w, h), cv)
        return cv.convert("RGB")
    return tr

# ---------- registry ----------
REGISTRY = []
def _add(name, fn, tags): REGISTRY.append({"name": name, "fn": fn, "tags": set(tags)})

def _build():
    soft_opts = {"hard": 0.0, "soft": 0.18}
    # masks
    for ang in (0, 45, 90, 135, 180, 225, 270, 315):
        for sk, sv in soft_opts.items():
            for ez in ("smooth", "expo"):
                _add(f"wipe_{ang}_{sk}_{ez}", make_mask_tr(f"lin{ang}", lambda w, h, a=ang: f_linear(w, h, a), sv, ez), ["reveal", "list", "news", "history"])
    for inv in (False, True):
        for sk, sv in soft_opts.items():
            for ez in ("smooth", "expo"):
                n = "out" if inv else "in"
                _add(f"circle_{n}_{sk}_{ez}", make_mask_tr(f"rad{inv}", lambda w, h, i=inv: f_radial(w, h, inv=i), sv, ez), ["space", "focus", "reveal"])
                _add(f"diamond_{n}_{sk}_{ez}", make_mask_tr(f"dia{inv}", lambda w, h, i=inv: f_diamond(w, h, i), sv, ez), ["bold", "game", "reveal"])
                _add(f"box_{n}_{sk}_{ez}", make_mask_tr(f"box{inv}", lambda w, h, i=inv: f_box(w, h, i), sv, ez), ["tech", "frame", "compare"])
                for vert in (False, True):
                    _add(f"barn_{'v' if vert else 'h'}_{n}_{sk}_{ez}", make_mask_tr(f"barn{vert}{inv}", lambda w, h, v=vert, i=inv: f_barn(w, h, v, i), sv, ez), ["story", "compare", "cinematic"])
    for start in (0, 90, 180, 270):
        for ccw in (False, True):
            _add(f"clock_{start}_{'ccw' if ccw else 'cw'}", make_mask_tr(f"clk{start}{ccw}", lambda w, h, s=start, c=ccw: f_clock(w, h, s, c), .04, "smooth"), ["time", "history", "process"])
    for n in (4, 6, 8, 12, 16, 24):
        for vert in (False, True):
            _add(f"blinds_{n}_{'v' if vert else 'h'}", make_mask_tr(f"bl{n}{vert}", lambda w, h, k=n, v=vert: f_blinds(w, h, k, v), .05, "smooth"), ["retro", "list", "tech"])
    for n in (4, 6, 8, 12):
        _add(f"checker_{n}", make_mask_tr(f"ch{n}", lambda w, h, k=n: f_checker(w, h, k), .05, "smooth"), ["game", "fun", "tech"])
        for seed in (1, 2, 3):
            _add(f"blocks_{n}_s{seed}", make_mask_tr(f"blk{n}{seed}", lambda w, h, k=n, s=seed: f_blocks(w, h, k, s), .06, "linear"), ["tech", "data", "glitch"])
    for scale in (1, 2, 4):
        for seed in (1, 2, 3, 4):
            _add(f"noise_dissolve_x{scale}_s{seed}", make_mask_tr(f"nz{scale}{seed}", lambda w, h, sc=scale, s=seed: f_noise(w, h, s, sc), .15, "smooth"), ["nature", "art", "dream", "calm"])
    for turns in (1, 2, 3):
        for ccw in (False, True):
            _add(f"spiral_{turns}_{'ccw' if ccw else 'cw'}", make_mask_tr(f"sp{turns}{ccw}", lambda w, h, t=turns, c=ccw: f_spiral(w, h, t, c), .06, "smooth"), ["space", "fun", "mind"])
    for pts in (4, 5, 6, 8):
        _add(f"star_{pts}", make_mask_tr(f"st{pts}", lambda w, h, k=pts: f_star(w, h, k), .05, "expo"), ["celebration", "fun", "reward"])
    _add("heart_in", make_mask_tr("heart", f_heart, .05, "smooth"), ["love", "health", "relationship"])
    for ang in (0, 90, 180, 270):
        for fq in (2, 4, 7):
            _add(f"wave_{ang}_f{fq}", make_mask_tr(f"wv{ang}{fq}", lambda w, h, a=ang, f=fq: f_wave(w, h, a, f), .08, "smooth"), ["water", "nature", "music", "calm"])
        for n in (6, 12):
            _add(f"zigzag_{ang}_n{n}", make_mask_tr(f"zz{ang}{n}", lambda w, h, a=ang, k=n: f_zigzag(w, h, a, k), .03, "expo"), ["energy", "warning", "sport"])
    # motion
    for kind in ("push", "cover", "uncover"):
        for d in DIRS:
            for ez in ("smooth", "expo", "back"):
                _add(f"{kind}_{d}_{ez}", make_motion_tr(kind, d, ez), ["story", "list", "phone", "energy"])
    for d in ("left", "up"):
        for ez in ("smooth", "expo"):
            _add(f"split_{d}_{ez}", make_motion_tr("split", d, ez), ["reveal", "compare", "bold"])
    # zoom / blur
    for kind in ("zoom_through", "zoom_out", "spin_zoom", "blur_dissolve", "stretch_h", "stretch_v"):
        for st in (.6, 1.0, 1.6):
            for ez in ("smooth", "expo"):
                _add(f"{kind}_{st}_{ez}", make_zoom_tr(kind, st, ez), ["space", "cinematic", "reveal", "dream"])
    for d in DIRS:
        for st in (.6, 1.0):
            _add(f"whip_{d}_{st}", make_zoom_tr(f"whip_{d}", st, "expo"), ["energy", "tech", "sport", "news"])
    # color
    for c in COLORS:
        for ez in ("smooth", "linear"):
            _add(f"dip_{c}_{ez}", make_color_tr("dip", c, ez), ["calm", "cinematic", "story"])
        _add(f"flash_{c}", make_color_tr("flash", c, "linear"), ["shock", "energy", "reveal"])
    for prm in ("bright_first", "dark_first"):
        for ez in ("smooth", "linear"):
            _add(f"luma_{prm}_{ez}", make_color_tr("luma", prm, ez), ["art", "dream", "cinematic"])
    for n in (12, 24, 48):
        _add(f"pixelate_{n}", make_color_tr("pixelate", n, "linear"), ["game", "retro", "tech"])
        _add(f"rgb_split_{n}", make_color_tr("rgb_split", n, "linear"), ["glitch", "tech", "warning", "phone"])
    for lv in (4, 8):
        _add(f"posterize_{lv}", make_color_tr("posterize", lv, "smooth"), ["art", "retro"])
    # 3D
    for kind in ("cube", "flip", "door", "fold", "tilt_zoom", "carousel", "page_turn", "persp_slide"):
        for d in ("left", "right", "up", "down"):
            for ez in ("smooth", "back"):
                _add(f"3d_{kind}_{d}_{ez}", make_3d_tr(kind, d, ez), ["3d", "compare", "story", "money", "reveal", "tech"])
    for ez in ("smooth", "expo"):
        _add(f"3d_swing_{ez}", make_3d_tr("swing", "left", ez), ["3d", "fun", "sign"])
        for d in ("left", "right"):
            _add(f"3d_roll_{d}_{ez}", make_3d_tr("roll", d, ez), ["3d", "fun", "energy"])

_build()
BY_NAME = {t["name"]: t for t in REGISTRY}

def family(name): return name.split("_")[0] if not name.startswith("3d_") else "3d_" + name.split("_")[1]

def pick_transition(tags, used, seed=None, recent_families=()):
    """Pick a transition matching tags; never reuse a name in this video, avoid families
    used in the last scenes/videos (recent_families). Falls back to any unused one."""
    rnd = random.Random(seed); tags = set(tags)
    pool = [t for t in REGISTRY if t["name"] not in used and family(t["name"]) not in recent_families and t["tags"] & tags]
    if not pool: pool = [t for t in REGISTRY if t["name"] not in used]
    t = rnd.choice(pool); used.add(t["name"]); return t

if __name__ == "__main__":
    print(len(REGISTRY), "transitions")
