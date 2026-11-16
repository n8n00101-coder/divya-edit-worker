"""hyperframestest.py — unit tests for the v89 HyperFrames Director
codegen (hyperframes_codegen.py) and its guarded Visual Director
wiring (visual_director.emit_hyperframes_compositions).

Covers: a fixture scene script (DATA, not hand-written HTML) produces
the spike-shaped project (index.html + compositions/ + assets/ +
hyperframes.json + package.json + meta.json); the index carries the
summed duration; template output contains the script's exact headline
/ bar / source strings; a data chart WITHOUT a source is flagged in
the report AND rendered with the explicit NOT PROVIDED placeholder;
a map card always carries the "Illustrative map — not to scale"
honesty label; a scene with missing footage is a hard error
(graphics never replace footage); the Visual Director wiring is OFF
by default and, when enabled, converts only plan scenes carrying a
graphics spec. The end-to-end render itself is the manual proof in
hyperframes_spike/codegen_proof/ (render time on this VM is long),
not a unit test. Deterministic, no network, no model calls.
"""

import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


import hyperframes_codegen as HFC

# ------------------------------------------------------------ fixture
_TD = tempfile.mkdtemp(prefix="hftest_")
FOOT = os.path.join(_TD, "clip.mp4")
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
     "color=c=teal:s=640x360:d=30", "-c:v", "libx264",
     "-pix_fmt", "yuv420p", FOOT],
    check=True, capture_output=True)

SCRIPT = [
    {"footage": FOOT, "duration": 4.0,
     "layers": [
         {"type": "title", "kicker": "THE PACIFIC NORTHWEST",
          "headline": "The Vanishing Coast", "accent": "Vanishing",
          "sub": "How the Pacific is redrawing the shore"},
         {"type": "lower_third", "name": "Dr. Mara Ellison",
          "role": "Coastal geologist"}]},
    {"footage": FOOT, "duration": 5.0,
     "layers": [
         {"type": "data_chart", "title": "The rise is speeding up",
          "subtitle": "Global sea-level rise, millimetres per year",
          "bars": [{"label": "1993", "value": 2.1, "unit": "mm / yr"},
                   {"label": "2023", "value": 4.5, "unit": "mm / yr"}],
          "note": "x2.1 faster in one generation",
          "source": "NASA Sea Level Change, 2024"}]},
    {"footage": FOOT, "duration": 4.0,
     "layers": [
         {"type": "map_card", "title": "One coast, shrinking",
          "label": "NESKOWIN",
          "description": "The beach narrows a little more each winter."},
         {"type": "kinetic_caption", "phrase": "But how fast?",
          "accent": "fast?", "start": 0.6, "interval": 0.55}]},
]

OUT = os.path.join(_TD, "proj")
rep = HFC.generate_project(SCRIPT, OUT)

# ------------------------------------------------------- project shape
check("codegen: report counts 3 scenes / 13.0s total",
      rep["scenes"] == 3 and rep["total_duration"] == 13.0,
      f"{rep['scenes']} scenes, {rep['total_duration']}s")
for rel in ("index.html", "hyperframes.json", "package.json",
            "meta.json", "compositions/scene1_title.html",
            "compositions/scene2_data_chart.html",
            "compositions/scene3_map_card.html",
            "assets/clip.mp4"):
    check(f"codegen: project has {rel}",
          os.path.isfile(os.path.join(OUT, rel)))
index = open(rep["index"], encoding="utf-8").read()
check("codegen: index root duration is the summed 13s",
      'data-duration="13"' in index)
check("codegen: index references all 3 compositions",
      all(f'compositions/scene{i}_' in index for i in (1, 2, 3)))
check("codegen: sourced chart produces NO flags",
      rep["flags"] == [], f"{rep['flags']}")

s1 = open(os.path.join(OUT, "compositions", "scene1_title.html"),
          encoding="utf-8").read()
s2 = open(os.path.join(OUT, "compositions", "scene2_data_chart.html"),
          encoding="utf-8").read()
s3 = open(os.path.join(OUT, "compositions", "scene3_map_card.html"),
          encoding="utf-8").read()

# ------------------------------------------- exact strings from script
def _text(html_src):
    """Rendered text content of a composition (tags stripped) — the
    accent word is wrapped in a <span>, so the exact headline string
    is contiguous in the text, not in the raw markup."""
    return re.sub(r"<[^>]+>", " ", html_src)


check("title: exact headline in generated composition text",
      "The Vanishing Coast" in
      " ".join(_text(s1).split()))
check("title: exact kicker + sub in generated HTML",
      "THE PACIFIC NORTHWEST" in s1
      and "How the Pacific is redrawing the shore" in s1)
check("title: accent word is wrapped in the accent span",
      '<span class="accent">Vanishing</span>' in s1)
check("lower_third: exact name + role in generated HTML",
      "Dr. Mara Ellison" in s1 and "Coastal geologist" in s1)
check("chart: exact bar labels + source line in generated HTML",
      "1993" in s2 and "2023" in s2
      and "Source: NASA Sea Level Change, 2024" in s2)
check("chart: count-up targets are the script's exact values",
      "v: 2.1" in s2 and "v: 4.5" in s2)
check("chart: footage is a full-frame video clip under the panel",
      "<video" in s2 and 'src="assets/clip.mp4"' in s2
      and "object-fit: cover" in s2)
check("kinetic: exact phrase words in generated HTML",
      all(w in s3 for w in ("But", "how", "fast?")))
check("kinetic: accent word wrapped",
      '<span id="s3-kin-w2" class="accent">fast?</span>' in s3)

# --------------------------------------------------------- honesty rules
check("map: honesty label present in generated HTML",
      HFC.MAP_HONESTY_LABEL in s3)
check("map: honesty marker attribute present",
      'data-honesty="illustrative-map-not-to-scale"' in s3)

NOSRC = [{"footage": FOOT, "duration": 4.0,
          "layers": [{"type": "data_chart", "title": "Unsourced",
                      "bars": [{"label": "A", "value": 1.0}]}]}]
rep2 = HFC.generate_project(NOSRC, os.path.join(_TD, "proj2"))
s_nosrc = open(rep2["compositions"][0], encoding="utf-8").read()
check("chart without source: flagged in the report",
      any("NO source" in f for f in rep2["flags"]),
      f"{rep2['flags']}")
check("chart without source: placeholder line rendered + marked",
      HFC.MISSING_SOURCE_LINE in s_nosrc
      and 'data-source-missing="true"' in s_nosrc)

try:
    HFC.generate_project(
        [{"footage": os.path.join(_TD, "nope.mp4"), "duration": 3.0,
          "layers": [{"type": "title", "headline": "X"}]}],
        os.path.join(_TD, "proj3"))
    _raised = False
except ValueError:
    _raised = True
check("missing footage: hard ValueError (no graphics-only scene)",
      _raised)

# ------------------------------------------------- visual_director wire
import visual_director as VD

plan = {"scenes": [
    {"no": 1, "vo": "The coast is vanishing.", "label": "COAST",
     "footage_path": FOOT, "duration": 4.0,
     "graphics": {"type": "title", "headline": "The Vanishing Coast",
                  "accent": "Vanishing"}},
    {"no": 2, "vo": "A beat with no graphics spec.", "label": "PLAIN",
     "footage_path": FOOT, "duration": 4.0},
]}
OUT4 = os.path.join(_TD, "proj4")
check("wiring: default is OFF (returns None, writes nothing)",
      VD.emit_hyperframes_compositions(plan, OUT4) is None
      and not os.path.exists(OUT4))
rep4 = VD.emit_hyperframes_compositions(plan, OUT4, enabled=True)
check("wiring: enabled converts only graphics-carrying scenes",
      rep4 is not None and rep4["scenes"] == 1
      and os.path.isfile(os.path.join(OUT4, "index.html")),
      f"{rep4}")
wired = open(rep4["compositions"][0], encoding="utf-8").read() \
    if rep4 else ""
check("wiring: converted scene carries the plan's headline",
      "The Vanishing Coast" in " ".join(_text(wired).split()))

print(f"\nhyperframestest: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
