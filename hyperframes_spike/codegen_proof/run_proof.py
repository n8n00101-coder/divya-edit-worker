"""run_proof.py — the v89 codegen end-to-end proof.

Loads proof_script.json (pure data), generates the HyperFrames
project into ./project with hyperframes_codegen, lints it with the
spike's check command, renders the MP4 with the spike's render
command, probes the duration, and extracts one frame per scene into
this directory for eyeball verification.

    python3 run_proof.py            # generate + check only (fast)
    python3 run_proof.py --render   # + full render + frames (slow)
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)

import hyperframes_codegen as HFC

PROJECT = os.path.join(HERE, "project")
TMP = os.path.join(REPO, ".hyperframes-tmp")


def main():
    with open(os.path.join(HERE, "proof_script.json"),
              encoding="utf-8") as f:
        data = json.load(f)
    script = []
    for sc in data["scenes"]:
        sc = dict(sc)
        sc["footage"] = os.path.join(REPO, sc["footage"])
        script.append(sc)
    rep = HFC.generate_project(script, PROJECT,
                               name="julie-hyperframes-codegen-proof")
    print("GENERATED:", json.dumps(
        {k: rep[k] for k in ("scenes", "total_duration", "assets",
                             "flags")}, indent=2))
    chk = HFC.check_project(PROJECT, tmpdir=TMP)
    print("CHECK:", json.dumps(chk)[:1200])
    if "--render" not in sys.argv:
        print("stopping before render (pass --render for the full proof)")
        return
    mp4 = HFC.render_project(PROJECT, tmpdir=TMP)
    final = os.path.join(HERE, "codegen_render.mp4")
    shutil.copy2(mp4, final)
    print("RENDERED:", final)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-show_entries",
         "stream=codec_name,width,height", "-of", "json", final],
        capture_output=True, text=True, check=True)
    print("FFPROBE:", out.stdout)
    # one frame per scene, taken after that scene's graphics land
    for name, t in (("frame_scene1_title.png", 3.0),
                    ("frame_scene2_chart.png", 8.3),
                    ("frame_scene3_kinetic.png", 12.2)):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", final,
             "-frames:v", "1", os.path.join(HERE, name)],
            check=True)
        print("FRAME:", name, "at", t, "s")


if __name__ == "__main__":
    main()
