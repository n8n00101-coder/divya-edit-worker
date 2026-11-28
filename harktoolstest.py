"""harktoolstest.py — rig for the Hark gates + variant/competitor
tools (Waves 1-2 of the Hark-parity mission).

  (a) gates: clip reuse caught; repeat_ok honoured; spoken vs
      on-screen number mismatch caught; weak/non-footage opening
      fails HARK-HOOK-3S; pacing bounds exact; two endings fail;
      clipping peak + long gap fail HARK-AUDIO; unmeasured peak
      fails honestly; a clean plan passes all gates.
  (b) variants: ranked best-first, fits_3s flags exact, provided
      hooks merged and deduped, no invented numbers in output.
  (c) competitor: outlier multiple exact, formula distribution
      counted, gaps = competitor formulas missing from ours.
  (d) routing: variant task picks yt_hook_variants; competitor
      task picks yt_competitor_analyze; taste-gate task picks
      hark_gate_check; poem task still matched=False.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hark_gates
import tool_routing
import yt_tools

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


def status(checks, rule):
    rows = [c["status"] for c in checks if c["rule"] == rule]
    return rows


STRONG_HOOK = ("97% of channels quit before video 30 — here is what "
               "the other 3% do in the next 7 days, and why nobody "
               "tells you")

# ------------------------------------------------------------- (a) gates
print("(a) hark gates")
scenes = [
    {"kind": "footage", "clip": "a.mp4", "vo": STRONG_HOOK,
     "duration": 4.0, "overlay": "97% quit"},
    {"kind": "footage", "clip": "b.mp4", "vo": "Then the pattern flips.",
     "duration": 3.0},
    {"kind": "footage", "clip": "a.mp4", "vo": "Same shot again.",
     "duration": 3.0},
]
checks = hark_gates.hark_checks(
    {"scenes": scenes, "loudness": {"true_peak_db": -3.0},
     "silence_gaps": [0.4]})
check("clip reuse fails", status(checks, "HARK-CLIP-REUSE") == ["FAIL"],
      str(checks))
scenes[2]["repeat_ok"] = True
checks = hark_gates.hark_checks(
    {"scenes": scenes, "loudness": {"true_peak_db": -3.0},
     "silence_gaps": [0.4]})
check("repeat_ok honoured",
      status(checks, "HARK-CLIP-REUSE") == ["PASS"], str(checks))
check("clean plan passes all gates",
      hark_gates.hark_critical_fails(checks) == [], str(checks))

bad_num = [{"kind": "footage", "clip": "x.mp4",
            "vo": "Almost 40 percent of people feel this.",
            "overlay": "65%", "duration": 3.0}]
checks = hark_gates.hark_checks({"scenes": bad_num})
check("number mismatch fails",
      status(checks, "HARK-NUMBER-MATCH") == ["FAIL"], str(checks))

promise = [{"kind": "footage", "clip": "x.mp4",
            "vo": "Nobody checks on you.",
            "overlay": "In the next 30 seconds: exactly why",
            "runtime_promise_s": 30, "duration": 3.0}]
checks = hark_gates.hark_checks({"scenes": promise})
check("declared runtime promise exempt",
      status(checks, "HARK-NUMBER-MATCH") == ["PASS"], str(checks))

weak = [{"kind": "titlecard", "vo": "Welcome to my channel.",
         "duration": 3.0}]
checks = hark_gates.hark_checks({"scenes": weak})
check("weak non-footage opening fails",
      status(checks, "HARK-HOOK-3S") == ["FAIL"], str(checks))

slow = [{"kind": "footage", "clip": "x.mp4", "vo": STRONG_HOOK,
         "duration": 12.0}]
checks = hark_gates.hark_checks({"scenes": slow})
check("12s shot fails pacing",
      status(checks, "HARK-PACING") == ["FAIL"], str(checks))

two_ends = [
    {"kind": "footage", "clip": "x.mp4", "vo": STRONG_HOOK,
     "duration": 3.0},
    {"kind": "cta", "vo": "Subscribe for more.", "duration": 2.0},
    {"kind": "endcard", "vo": "Stay tuned.", "duration": 2.0},
]
checks = hark_gates.hark_checks({"scenes": two_ends})
check("two endings fail",
      status(checks, "HARK-ENDINGS") == ["FAIL"], str(checks))

checks = hark_gates.check_audio({"true_peak_db": -0.2}, [2.0])
check("clipping peak + long gap fail audio",
      status(checks, "HARK-AUDIO") == ["FAIL", "FAIL"], str(checks))
checks = hark_gates.check_audio(None, [])
check("unmeasured peak fails honestly",
      status(checks, "HARK-AUDIO")[0] == "FAIL", str(checks))

# ---------------------------------------------------------- (b) variants
print("(b) hook variants")
out = yt_tools.hook_variants(
    "loneliness in a crowded city",
    extra_hooks=["Nobody checks on you. That silence is the loudest "
                 "sound in your life"])
variants = out["variants"]
check("variants ranked best-first",
      all(variants[i]["total"] >= variants[i + 1]["total"]
          for i in range(len(variants) - 1)), str(variants))
check("fits_3s flags exact",
      all(v["fits_3s"] == (v["words"] <= 12) for v in variants),
      str(variants))
check("provided hook merged",
      any(v["source"] == "provided" for v in variants), str(variants))
check("no invented statistics in formula variants",
      all("%" not in v["hook"]
          for v in variants if v["source"] == "formula"),
      str(variants))

# -------------------------------------------------------- (c) competitor
print("(c) competitor analysis")
rows = [
    {"channel": "rival", "title": "Why nobody talks about burnout",
     "views": 1000},
    {"channel": "rival", "title": "Burnout is not laziness",
     "views": 1200},
    {"channel": "rival", "title": "In the next 2 minutes: focus",
     "views": 1100},
    {"channel": "rival", "title": "The mistake everyone makes daily",
     "views": 900},
    {"channel": "rival", "title": "Why rest feels like guilt",
     "views": 5000},
]
out = yt_tools.competitor_analyze(
    rows, ours=["Why nobody talks about rest"])
check("competitor videos counted", out["videos"] == 5, str(out))
check("formula distribution counted",
      sum(out["formula_distribution"].values()) >= 3, str(out))
check("gaps exclude our formulas",
      all(g not in out["our_formulas"] for g in out["formula_gaps"]),
      str(out))
check("avg title words exact",
      out["avg_title_words"] == 5.0, str(out))

# ------------------------------------------------------------ (d) routing
print("(d) routing")
sel = tool_routing.select_tools(
    "give me first 3 seconds hook variants for this topic")
check("variant task picks yt_hook_variants",
      "yt_hook_variants" in sel["tools"], str(sel))
sel = tool_routing.select_tools("competitor analysis on these rows")
check("competitor task picks yt_competitor_analyze",
      "yt_competitor_analyze" in sel["tools"], str(sel))
sel = tool_routing.select_tools("run the taste gate final check")
check("taste-gate task picks hark_gate_check",
      "hark_gate_check" in sel["tools"], str(sel))
sel = tool_routing.select_tools("write a poem about rain")
check("poem still unmatched", sel["matched"] is False, str(sel))

print(f"\nharktoolstest: {PASS} pass, {FAIL} fail")
sys.exit(1 if FAIL else 0)
