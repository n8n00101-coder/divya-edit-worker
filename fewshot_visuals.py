from visuals_lib import W, H
import math
from PIL import Image, ImageDraw
from visuals_lib import _L, _p, _ob, _oe, place, shadow, texture, _font, INK, Y
# Topic LIGHTNING: a storm cloud pops in, then a zig-zag bolt draws down from it.
def vis_storm_bolt(t, st=0, d=1.0, accent=Y):
    L = _L(); q = _p(t, st, d*.4); c = Image.new("RGBA", (420, 220), (0,0,0,0)); dc = ImageDraw.Draw(c)
    for x, y, r in ((110,130,80),(210,95,105),(320,130,85),(210,150,90)): dc.ellipse((x-r,y-r*.8,x+r,y+r*.8), fill=(150,155,170,255))
    L.alpha_composite(place(shadow(c), 360, 420, scale=_ob(q)))
    bq = _p(t, st+d*.45, d*.3); pts = [(360,500),(320,640),(380,650),(330,820),(400,600),(345,590),(380,500)]
    if bq > 0:
        k = max(2, int(len(pts)*_oe(bq))); ImageDraw.Draw(L).polygon(pts[:k] if k>2 else pts[:3], fill=accent+(255,))
    return L

# Topic SAVING MONEY: coins drop one by one and stack into a tower, the top coin gets the accent colour.
def vis_coin_stack(t, st=0, d=1.2, coins=8, accent=Y, cx=360, base=900):
    L = _L(); dr = ImageDraw.Draw(L)
    for i in range(coins):
        q = _p(t, st+i*d/coins, .3)
        if q <= 0: break
        y = base-i*34-(1-_ob(q))*400; col = accent if i == coins-1 else (215, 170, 60)
        dr.ellipse((cx-110, y-22, cx+110, y+22), fill=(150, 110, 30, 255)); dr.rectangle((cx-110, y-34, cx+110, y), fill=(150, 110, 30, 255))
        dr.ellipse((cx-110, y-56, cx+110, y-12), fill=col+(255,)); dr.ellipse((cx-80, y-48, cx+80, y-20), outline=(255, 235, 150, 255), width=3)
    return L

# Topic SLEEP / PHONE AT NIGHT: a bed with a glowing phone; screen glow grows and lights the pillow.
def vis_bed_phone(t, st=0, d=1.0, accent=Y):
    L = _L(); q = _p(t, st, d*.5); g = _p(t, st+d*.4, d*.6)
    bed = Image.new("RGBA", (520, 300), (0, 0, 0, 0)); db = ImageDraw.Draw(bed)
    db.rounded_rectangle((0, 120, 520, 260), 24, fill=(70, 80, 120, 255)); db.rectangle((0, 40, 40, 300), fill=(110, 80, 60, 255))
    db.rounded_rectangle((50, 80, 200, 150), 30, fill=(230, 230, 240, 255)); db.rounded_rectangle((180, 110, 520, 200), 30, fill=(120, 140, 200, 255))
    L.alpha_composite(place(shadow(bed), 370, 760+(1-_oe(q))*200, scale=.88))
    if g > 0:
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(glow); r = 40+110*_oe(g)
        gd.ellipse((300-r, 690-r, 300+r, 690+r), fill=(170, 210, 255, int(90*g)))
        from PIL import ImageFilter
        L.alpha_composite(glow.filter(ImageFilter.GaussianBlur(20)))
        ImageDraw.Draw(L).rounded_rectangle((275, 650, 325, 735), 10, fill=(200, 230, 255, 255))
    return L
