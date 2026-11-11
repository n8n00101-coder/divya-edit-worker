#!/usr/bin/env python3
"""Sandbox-test a per-video video_visuals.py (v30, Hark's per-video visual code).

Usage: python3 visuals_sandbox.py <file> [n_scenes]
Prints one JSON object: {"file": ..., "ok": bool, "functions": {name: {...}}}.

Each scene gets one function: vis_<i>(d, w, h, acc, t) -> None, where
  d   = PIL ImageDraw on a blank 1080x1920 RGBA layer (the visual layer)
  w,h = 1080, 1920
  acc = the video's accent colour, an (r, g, b) tuple
  t   = time into the scene in seconds (0..scene duration)
The function draws the scene's visual with PIL only. Allowed imports:
math, random, numpy, PIL, effects, transitions_lib. No files, no network,
no subprocess. Content must stay inside the safe box (8% sides, 10% top/
bottom) and each call must finish in under 200 ms (Divya renders offline).
"""
import ast, importlib.util, json, sys, time

W, H = 1080, 1920
SAFE = (int(W * 0.08), int(H * 0.10), W - int(W * 0.08), H - int(H * 0.10))
ALLOWED = {"math", "random", "numpy", "np", "PIL", "Image", "ImageDraw",
           "ImageFilter", "ImageChops", "effects", "transitions_lib"}


def check_imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED:
                    return False, f"import {a.name} not allowed"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED:
                return False, f"import {node.module} not allowed"
        elif isinstance(node, ast.Name) and node.id in ("open", "exec", "eval", "__import__"):
            return False, f"{node.id} not allowed"
    return True, ""


def main():
    path = sys.argv[1]
    n_scenes = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    src = open(path).read()
    tree = ast.parse(src)
    ok, why = check_imports(tree)
    result = {"file": path, "ok": False, "functions": {}}
    if not ok:
        result["why"] = why
        print(json.dumps(result, indent=1))
        return
    from PIL import Image, ImageDraw
    spec = importlib.util.spec_from_file_location("video_visuals", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = [n for n in dir(mod) if n.startswith("vis_") and callable(getattr(mod, n))]
    if n_scenes and len(names) < n_scenes:
        result["why"] = f"only {len(names)} vis_ functions for {n_scenes} scenes"
        print(json.dumps(result, indent=1))
        return
    all_ok = True
    for name in sorted(names):
        fn = getattr(mod, name)
        r = {"ok": True}
        try:
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay, "RGBA")
            t0 = time.perf_counter()
            fn(d, W, H, (255, 210, 31), 0.5)
            ms = (time.perf_counter() - t0) * 1000
            r["ms_per_call"] = round(ms, 1)
            if ms > 200:
                r.update(ok=False, why="too slow")
            bbox = lay.getbbox()
            if bbox:
                x0, y0, x1, y1 = bbox
                if x0 < SAFE[0] or y0 < SAFE[1] or x1 > SAFE[2] or y1 > SAFE[3]:
                    r.update(ok=False, why=f"content outside safe box {bbox}")
        except Exception as e:
            r.update(ok=False, why=f"{type(e).__name__}: {e}"[:200])
        result["functions"][name] = r
        all_ok = all_ok and r["ok"]
    result["ok"] = all_ok and bool(names)
    if not names:
        result["why"] = "no vis_ functions found"
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
