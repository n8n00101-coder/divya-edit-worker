"""packagingtest.py — unit tests for the v89 pipeline adds: the
21-hook-formula library (hooks_lib), the topic pre-flight checklist
(story_analyst.preflight + hook variants on the analysis result), and
the delivery-end packaging step (packaging.py).

Deterministic, no network, no model calls — fixtures only, in the
style of v88test.py.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------- hooks_lib
import hooks_lib

check("hooks_lib: exactly 21 formulas loaded",
      len(hooks_lib.FORMULAS) == 21, f"{len(hooks_lib.FORMULAS)}")
check("hooks_lib: every formula carries name + shape + example",
      all(f.get("name") and f.get("shape") and f.get("example")
          for f in hooks_lib.FORMULAS))

strong = hooks_lib.score_hook(
    "97% of channels quit before video 30 — here is what the other "
    "3% do in the next 7 days, and why nobody tells you")
weak = hooks_lib.score_hook(
    "Welcome to my channel, today we talk about videos and stuff")
check("hooks_lib: a strong hook scores above a weak one",
      strong["total"] > weak["total"],
      f"strong {strong['total']} vs weak {weak['total']}")
check("hooks_lib: per-criterion scores are all present",
      set(strong["criteria"]) == {"curiosity_gap", "specificity",
                                  "timeframe", "contrarian_stakes",
                                  "clarity"},
      f"{sorted(strong['criteria'])}")
check("hooks_lib: the strong hook names its formula (The Statistic)",
      strong["formula"] == "The Statistic", f"{strong['formula']}")
_name, _hits = hooks_lib.classify_hook(
    "Everyone says post daily. Everyone is wrong about it.")
check("hooks_lib: classifier names the Contrarian Flip",
      _name == "Contrarian Flip", f"{_name}")

# ------------------------------------------------------- story_analyst adds
import story_analyst as sa

good = sa.preflight(
    "The vanishing fishing village on the Kerala coast",
    "the hidden truth nobody tells about the tide",
    sources=["https://example.org/tide-study"])
check("preflight: a good topic passes, not blocked",
      good["verdict"] == "pass" and good["blocked"] is False
      and not good["missing"], f"{good}")
bad = sa.preflight("", "", sources=[])
check("preflight: no hook AND no sources hard-blocks",
      bad["blocked"] is True and bad["verdict"] == "block",
      f"{bad}")
warn = sa.preflight("Some interesting topic", "", sources=[])
check("preflight: gaps without the block condition only warn",
      warn["verdict"] in ("warn", "pass") and warn["blocked"] is False,
      f"{warn}")


def _stub(messages):
    return json.dumps({"scenes": [
        {"emotion": "tense", "subject": "the automatic yes",
         "turning_point": False, "emphasis": ["yes"],
         "visual_opportunity": "scene"},
        {"emotion": "realisation", "subject": "the first honest no",
         "turning_point": True, "emphasis": ["honest", "no"],
         "visual_opportunity": "quote"}]})


sheet = sa.analyse_script(
    [{"vo": "The word yes is out of your mouth.", "label": "A"},
     {"vo": "Then one day you say the honest no.", "label": "B"}],
    _stub, topic="The vanishing fishing village on the Kerala coast",
    angle="the hidden truth nobody tells",
    sources=["https://example.org/tide-study"])
check("analyse_script: existing fields unchanged (back-compat)",
      sheet is not None and sheet["turning_points"] == [2]
      and len(sheet["scenes"]) == 2, f"{sheet and sheet.keys()}")
check("analyse_script: ranked hook variants attached (2-3, named)",
      2 <= len(sheet.get("hook_variants") or []) <= 3
      and all(v.get("formula") for v in sheet["hook_variants"])
      and [v["score"]["total"] for v in sheet["hook_variants"]] ==
      sorted((v["score"]["total"] for v in sheet["hook_variants"]),
             reverse=True),
      f"{sheet.get('hook_variants')}")
check("analyse_script: preflight verdict attached",
      (sheet.get("preflight") or {}).get("verdict") == "pass",
      f"{sheet.get('preflight')}")

# ---------------------------------------------------------------- packaging
import packaging

CHAPTERS = [
    {"title": "The Last Harbour", "start_s": 0, "end_s": 95},
    {"title": "The Hidden Tide Tables", "start_s": 95, "end_s": 210},
    {"title": "The Final Boat", "start_s": 210, "end_s": 300},
]
pkg = packaging.build_packaging(
    "the vanishing fishing village", "The Village the Sea Took Back",
    CHAPTERS, sources=["https://example.org/tide-study",
                       {"url": "https://example.org/harbour-records"}],
    claims=["The harbour closed in 1998"], duration=300)

check("packaging: 10 title candidates", len(pkg["titles"]) == 10,
      f"{len(pkg['titles'])}")
check("packaging: every title < 60 chars",
      all(len(t["title"]) < 60 for t in pkg["titles"]),
      f"{[t['title'] for t in pkg['titles'] if len(t['title']) >= 60]}")
check("packaging: 3 thumbnail concepts, 2-3 words of text each",
      len(pkg["thumbnails"]) == 3
      and all(2 <= len(t["text"].split()) <= 3
              for t in pkg["thumbnails"])
      and all(t.get("visual") for t in pkg["thumbnails"]),
      f"{pkg['thumbnails']}")
check("packaging: pair check PASSES on the chosen pair",
      pkg["pair_check"]["passes"] is True
      and not pkg["pair_check"]["duplicated_words"],
      f"{pkg['pair_check']}")
dup = packaging.pair_check("The Vanishing Village",
                           "VANISHING VILLAGE")
check("packaging: pair check FAILS on a duplicated pair",
      dup["passes"] is False and dup["duplicated_words"],
      f"{dup}")
check("packaging: description contains chapters + timestamps + sources",
      "00:00 The Last Harbour" in pkg["description"]
      and "03:30 The Final Boat" in pkg["description"]
      and "https://example.org/tide-study" in pkg["description"],
      f"{pkg['description'][:200]}")
check("packaging: 3 Shorts cut points, all within the duration",
      len(pkg["shorts"]) == 3
      and all(0 <= s["start_s"] < s["end_s"] <= 300
              for s in pkg["shorts"])
      and all(s.get("rationale") for s in pkg["shorts"]),
      f"{pkg['shorts']}")
check("packaging: first comment is a debate question ending in '?'",
      pkg["first_comment"].strip().endswith("?"),
      f"{pkg['first_comment']}")

print(f"\npackagingtest: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
