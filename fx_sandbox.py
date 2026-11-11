"""
Test a per-video video_fx.py written by the LLM before it is used in a render.
Usage: python fx_sandbox.py video_fx.py   -> prints JSON report, exit 0 if all pass.
Run it in a subprocess with a timeout (e.g. 90 s) from the pipeline.

v32 (merged Blind v30 + Divya): tr_/fx_ are tested at Divya's 1080x1920
(the render size); vis_ at Blind's 720x1280 (the vis_ interface returns a
720x1280 RGBA layer that Divya upscales 1.5x). Blind's vis_ checks (visible
when built, safe box, build-in animation) are kept. MAX_MS comes from the
FX_MAX_MS env (default 40); Divya's offline render sets 200 via codegen.py.
"""
import sys, json, time, ast, importlib.util, os
import numpy as np
from PIL import Image, ImageDraw

ALLOWED = {"math", "random", "numpy", "PIL", "effects", "effects_lib", "transitions_lib", "motion_graphics", "visuals_lib"}
MAX_MS = float(os.environ.get("FX_MAX_MS", "40"))
W, H = 1080, 1920  # Divya renders 1080x1920 (Hark kit is 720x1280)
SAFE = (int(W*.08), int(H*.10), int(W*.92), int(H*.90))
VW, VH = 720, 1280  # vis_ interface size (Blind)
VSAFE = (int(VW*.08), int(VH*.10), int(VW*.92), int(VH*.90))

def check_imports(path):
    tree = ast.parse(open(path).read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] not in ALLOWED: return f"import not allowed: {a.name}"
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] not in ALLOWED:
            return f"import not allowed: {n.module}"
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("open", "exec", "eval", "__import__"):
            return f"call not allowed: {n.func.id}"
    return None

def frames():
    A = Image.new("RGB", (W, H), (25, 50, 140)); B = Image.new("RGB", (W, H), (160, 35, 45))
    for im, t in ((A, "A"), (B, "B")): ImageDraw.Draw(im).rectangle(SAFE, outline=(255, 210, 0), width=6)
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(L).rectangle((200, 500, 520, 780), fill=(255, 210, 0, 255))
    return A, B, L

def diff(a, b): return float(np.abs(np.asarray(a, np.float32) - np.asarray(b, np.float32)).mean())

def outside_safe(layer, safe=SAFE):
    bb = layer.getbbox() if layer.mode == "RGBA" else None
    if not bb: return False
    return bb[0] < safe[0]-2 or bb[1] < safe[1]-2 or bb[2] > safe[2]+2 or bb[3] > safe[3]+2

def main(path):
    rep = {"file": path, "ok": True, "functions": {}}
    err = check_imports(path)
    if err: print(json.dumps({"ok": False, "error": err})); sys.exit(1)
    spec = importlib.util.spec_from_file_location("video_fx", path); mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    A, B, L = frames()
    for name in dir(mod):
        fn = getattr(mod, name)
        if not callable(fn) or not name.startswith(("tr_", "fx_", "vis_")): continue
        r = {"ok": True}
        try:
            t0 = time.time()
            if name.startswith("tr_"):
                outs = [fn(A, B, p) for p in (0, .25, .5, .75, 1)]
                if any(o.size != (W, H) for o in outs): r.update(ok=False, why="wrong size (tr_ must work at 1080x1920)")
                elif diff(outs[0], A) > 3: r.update(ok=False, why="p=0 is not A")
                elif diff(outs[-1], B) > 3: r.update(ok=False, why="p=1 is not B")
            elif name.startswith("vis_"):
                outs = [fn(t, 0.0, 1.0) for t in (0, .25, .5, 1.0, 2.0)]
                if any(o.size != (VW, VH) or o.mode != "RGBA" for o in outs): r.update(ok=False, why="must return RGBA 720x1280")
                elif outs[-2].getbbox() is None: r.update(ok=False, why="nothing visible at t=st+d")
                elif any(outside_safe(o, VSAFE) for o in outs[3:]): r.update(ok=False, why="visual leaves safe box when built")
                elif diff(outs[0], outs[3]) < .5: r.update(ok=False, why="no build-in animation (t=st looks same as t=st+d)")
            else:
                outs = [fn(L, t, 0.0, 0.6) for t in (0, .15, .3, .45, .6, 1.0)]
                if any(o.size != (W, H) for o in outs): r.update(ok=False, why="wrong size (fx_ must work at 1080x1920)")
                elif any(outside_safe(o) for o in outs): r.update(ok=False, why="content leaves safe box")
            ms = (time.time() - t0) * 1000 / len(outs)
            r["ms_per_frame"] = round(ms, 1)
            if r["ok"] and ms > MAX_MS: r.update(ok=False, why="too slow")
        except Exception as e:
            r.update(ok=False, why=repr(e))
        rep["functions"][name] = r; rep["ok"] &= r["ok"]
    if not rep["functions"]: rep.update(ok=False, error="no tr_/fx_/vis_ functions")
    print(json.dumps(rep, indent=1)); sys.exit(0 if rep["ok"] else 1)

if __name__ == "__main__":
    main(sys.argv[1])
