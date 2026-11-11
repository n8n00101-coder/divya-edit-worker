"""
effects_lib.py — Divya effects wrapper (v32).

Thin, codegen-friendly layer on top of effects.py (Blind's v26 library).
Divya's codegen (divya_codegen.py) and its few-shot examples import these
names from here, so the names and behaviours below are a contract — do not
rename them.

What lives here vs effects.py:
  * EASES        — easing functions under the short names the few-shot
                   examples use (EASES["expo"], EASES["smooth"], ...).
                   Re-uses effects.py's functions; nothing re-implemented.
  * _xf          — non-uniform affine transform of an RGBA layer.
                   effects.transform() only does UNIFORM scale; _xf adds
                   independent sx / sy (and the s= shorthand) for squash
                   and stretch.
  * _alpha, _p   — aliases of effects.alpha / effects.prog.
  * _mask_reveal — multiply an "L" mask into a layer's alpha channel.
  * _bbox_field  — the layer's content bounding box (or None if empty).
  * pick_fx      — pick a layer-safe emphasis effect by tags, avoiding
                   repeats; returns the effect NAME (a string).

Layers are 1080x1920 RGBA (effects.W, effects.H).
"""
import math

from PIL import Image, ImageChops

import effects
from effects import (
    alpha,
    in_out_cubic,
    linear,
    out_back,
    out_bounce,
    out_cubic,
    out_elastic,
    out_expo,
    pick,
    prog,
    smooth,
    smoother,
    EMPHASIS,
    W,
    H,
)

__all__ = [
    "EASES",
    "_xf",
    "_alpha",
    "_p",
    "_mask_reveal",
    "_bbox_field",
    "pick_fx",
]

# ---------------------------------------------------------------- easing
# Canonical names + the aliases effects.EASE already defines, so both
# EASES["smooth"] (few-shot) and EASES["snappy"] (effects.EASE) work.
EASES = {
    "linear": linear,
    "smooth": smooth,            # smoothstep
    "smoother": smoother,        # smootherstep
    "cubic": out_cubic,
    "expo": out_expo,
    "back": out_back,
    "elastic": out_elastic,
    "bounce": out_bounce,
    "in_out": in_out_cubic,
    # aliases from effects.EASE
    "snappy": out_back,
    "glitch": linear,
    "paper": out_cubic,
    "typewriter": linear,
    "bouncy": out_bounce,
    "cinematic": in_out_cubic,
}

# ---------------------------------------------------------------- layer helpers
def _alpha(layer, a):
    """Scale the layer's alpha channel by a (a >= 1 returns it unchanged)."""
    return alpha(layer, a)


def _p(t, st, d):
    """Clamped progress (t - st) / d in [0, 1]; float(t >= st) if d <= 0."""
    return prog(t, st, d)


def _xf(layer, dx=0, dy=0, sx=1.0, sy=1.0, s=None, rot=0.0, cx=W / 2, cy=H / 2):
    """Non-uniform affine transform of an RGBA layer.

    Scale (sx, sy) around (cx, cy), rotate `rot` degrees, then shift by
    (dx, dy). If `s` is given it sets sx = sy = s (uniform scale).
    Returns the layer unchanged when the transform is the identity.
    """
    if s is not None:
        sx = sy = s
    if sx == 1 and sy == 1 and rot == 0 and dx == 0 and dy == 0:
        return layer
    # Guard against a zero scale (division by zero in the inverse).
    sx = sx if abs(sx) >= 0.01 else (0.01 if sx >= 0 else -0.01)
    sy = sy if abs(sy) >= 0.01 else (0.01 if sy >= 0 else -0.01)
    # Forward matrix M = T(cx+dx, cy+dy) . R(rot) . S(sx, sy) . T(-cx, -cy).
    # PIL Image.transform wants the INVERSE coefficients (output -> input):
    #   M^-1 = T(cx, cy) . S^-1 . R^-1 . T(-(cx+dx), -(cy+dy))
    # with S^-1 . R^-1 = [[cos/sx, sin/sx], [-sin/sy, cos/sy]].
    a = math.radians(rot)
    c, sn = math.cos(a), math.sin(a)
    tx, ty = cx + dx, cy + dy
    ia, ib = c / sx, sn / sx
    id_, ie = -sn / sy, c / sy
    coeffs = (ia, ib, cx - ia * tx - ib * ty,
              id_, ie, cy - id_ * tx - ie * ty)
    return layer.transform((W, H), Image.AFFINE, coeffs,
                           resample=Image.BICUBIC)


def _mask_reveal(layer, mask):
    """Apply an "L"-mode mask image (same size as the layer) to the layer's
    alpha channel (multiply). Returns the masked RGBA layer."""
    out = layer.copy()
    out.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    return out


def _bbox_field(layer):
    """The layer's content bounding box (layer.getbbox()), or None if empty."""
    return layer.getbbox()


# ---------------------------------------------------------------- effect picking
# Only these 5 EMPHASIS effects are layer-safe (they transform / glow the
# layer itself). The rest (flash, underline_draw, circle_draw, count_up,
# ring_fill, bar_grow) draw full-screen or new content and are NOT picked here.
_LAYER_SAFE_EMPHASIS = ("punch", "shake", "pulse", "wiggle", "glow")
_EMPHASIS_TABLE = {k: EMPHASIS[k] for k in _LAYER_SAFE_EMPHASIS
                   if k in EMPHASIS}


def pick_fx(kind, tags, used=None):
    """Pick an emphasis effect by tags, avoiding ones used >= 2x this video.

    kind is "emphasis" (the only kind Divya's codegen asks for).
    `used` may be a dict (effects.pick's format: name -> count) or a set
    of names; a set gets the picked name added to it before returning.
    Returns the effect NAME (a string), never a dict.
    Falls back to any of the 5 layer-safe effects when no tag matches.
    """
    if kind != "emphasis":
        raise ValueError(f"pick_fx: unknown kind {kind!r} (only 'emphasis')")
    if isinstance(tags, str):
        tags = [tags]
    if used is None:
        used_dict, used_set = {}, None
    elif isinstance(used, set):
        used_dict, used_set = {k: 1 for k in used}, used
    elif isinstance(used, dict):
        used_dict, used_set = used, None
    else:
        raise TypeError("pick_fx: used must be a dict, a set, or None")
    name = pick(_EMPHASIS_TABLE, tags, used_dict)
    if used_set is not None:
        used_set.add(name)
    return name


if __name__ == "__main__":  # smoke test
    from PIL import ImageDraw

    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(L).rectangle([200, 500, 520, 780], fill=(255, 210, 0, 255))

    # _xf: non-uniform scale + shift (and the s= shorthand)
    x1 = _xf(L, dy=10, sx=1.2, sy=0.8)
    assert x1.size == (W, H) and x1.mode == "RGBA" and x1.getbbox()
    x2 = _xf(L, s=1.1, dy=20)
    assert x2.getbbox()
    x3 = _xf(L, sx=0.9, sy=1.1, rot=5, dx=15)
    assert x3.getbbox()
    assert _xf(L) is L  # identity returns the layer unchanged

    # _alpha / _p
    assert _alpha(L, 1) is L
    assert _alpha(L, 0.5).getchannel("A").getextrema()[1] <= 128
    assert _p(0.5, 0, 1) == 0.5 and _p(2, 0, 1) == 1.0 and _p(-1, 0, 1) == 0.0
    assert _p(5, 3, 0) == 1.0

    # _mask_reveal / _bbox_field
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([0, 0, W // 2, H], 255)
    m = _mask_reveal(L, mask)
    assert m.mode == "RGBA" and m.getbbox()[2] <= W // 2 + 1
    assert _bbox_field(L) == (200, 500, 521, 781)  # getbbox: exclusive upper bound
    assert _bbox_field(Image.new("RGBA", (W, H), (0, 0, 0, 0))) is None

    # pick_fx: string return, one of the 5, set and dict forms of `used`
    for _ in range(6):
        n = pick_fx("emphasis", ["shock", "number"])
        assert isinstance(n, str) and n in _LAYER_SAFE_EMPHASIS, n
    used_set = set()
    n = pick_fx("emphasis", ["no-such-tag"], used_set)
    assert n in _LAYER_SAFE_EMPHASIS and n in used_set
    used_dict = {}
    n = pick_fx("emphasis", ["funny"], used_dict)
    assert n == "wiggle" and used_dict.get("wiggle", 0) >= 1

    # EASES keys the few-shot examples use
    for k in ("expo", "smooth", "bounce"):
        assert k in EASES and callable(EASES[k])
    assert EASES["expo"](0.5) > 0.9 and EASES["bounce"](1.0) == 1.0

    print("ok")
