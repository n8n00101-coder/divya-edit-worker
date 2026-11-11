# Example of a per-video file Divya's LLM writes. Topic: phantom phone vibration.
import math
import numpy as np
from PIL import Image
from transitions_lib import _mix, _soft, EASES, _grid

# Scene change "you feel your phone buzz": buzz rings spread from the phone spot and reveal B.
def tr_buzz_rings(A, B, p):
    w, h = A.size; x, y = _grid(w, h)
    d = np.sqrt(((x-.5)*w/h)**2 + (y-.62)**2); d = d/d.max()
    field = np.clip(d + .05*np.sin(d*40), 0, 1)
    q = EASES["expo"](p)
    if p <= 0: return A.copy()
    if p >= 1: return B.copy()
    return _mix(A, B, _soft(field, q, .12))

# Hit word "89%": the layer shakes like a buzzing phone, small and inside the safe box.
def fx_buzz(layer, t, start, dur):
    k = max(0.0, min(1.0, (t-start)/dur)); amp = 6*(1-k)*math.sin(k*math.pi*14)
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0)); out.paste(layer, (int(amp), 0), layer); return out
