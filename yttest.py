"""yttest.py — rig for yt_tools.py (deterministic YouTube packaging
tools ported from the MIT youtube-agent-skill pack) + registry wiring
+ the ENGINE_CORE YouTube-packaging rule.

  (a) title/thumbnail lint: exact scores and issue keys on a clean
      pair and a broken pair (length/mobile/vague/duplicate).
  (b) chapters validation: valid list passes; late first chapter,
      too-few chapters, and a sub-10s chapter each fail by name.
  (c) chapters from cues: boundaries land on the section pauses,
      list validates.
  (d) viral ranking: median multiples exact, thin channels skipped
      and reported, formulas named from hooks_lib.
  (e) retention read: hook leak / first cliff / slide exact on a
      fixture; under-8-points input refused honestly.
  (f) hook scoring + package ranking: known formula named, ranking
      order exact, best pair is the clean pair at lint 100.
  (g) registry contract: yt tools registered read-only, bad args
      refused before the handler, agent_runner.build_tools offers
      them.
  (h) ENGINE_CORE carries the YouTube-packaging tool rule.
"""

import os

import yt_tools
import tools_registry
import engine_instructions

PASS = 0


def check(cond, label, extra=""):
    global PASS
    assert cond, f"FAIL: {label} {extra}"
    PASS += 1
    print(f"  ok {label}")


# (a) title lint ------------------------------------------------------
good = yt_tools.lint_title_pair("Why You Feel Alone at 3 AM", "NOT BROKEN")
check(good["score"] == 100, "clean pair scores 100", good)
check(good["issues"] == [], "clean pair has no issues", good)
check(good["chars"] == 26, "clean pair char count exact", good)

bad = yt_tools.lint_title_pair(
    "How to became YouTuber in 2026 with this amazing secret trick "
    "that changes everything forever", "AMAZING SECRET TRICK")
check(bad["chars"] == 93, "bad pair char count exact", bad)
check([i[0] for i in bad["issues"]] ==
      ["length", "mobile", "vague", "duplicate"],
      "bad pair issue keys exact", bad)
check(bad["score"] == 48, "bad pair score exact (100-56+4)", bad)

# (b) chapters validation ---------------------------------------------
ok = yt_tools.validate_chapters(
    [{"start": 0}, {"start": 12}, {"start": 24}, {"start": 36},
     {"start": 48}], duration=64)
check(ok["valid"] is True, "valid chapter list passes", ok)
check([c["seconds"] for c in ok["chapters"]] == [12, 12, 12, 12, 16],
      "chapter seconds exact", ok)

late = yt_tools.validate_chapters([{"start": 5}, {"start": 20}], duration=40)
check(late["valid"] is False and len(late["issues"]) == 2,
      "late start + too few chapters fail with 2 issues", late)

short = yt_tools.validate_chapters(
    [{"start": 0}, {"start": 5}, {"start": 30}], duration=60)
check(short["valid"] is False and
      any("10s minimum" in i for i in short["issues"]),
      "sub-10s chapter fails by name", short)

nodur = yt_tools.validate_chapters(
    [{"start": 0}, {"start": 12}, {"start": 24}])
check(nodur["last_chapter_checked"] is False and
      nodur["chapters"][-1]["seconds"] is None,
      "last chapter unchecked without duration, never assumed", nodur)

# (c) chapters from cues ----------------------------------------------
CUES = [
    {"start": 0.0, "end": 4.0, "text": "Why do you feel alone even when your phone is full of people?"},
    {"start": 4.5, "end": 8.5, "text": "At night, the room is quiet and the mind starts comparing."},
    {"start": 12.0, "end": 16.0, "text": "A friend posts a new job, another friend posts a trip."},
    {"start": 16.5, "end": 20.5, "text": "Your brain reads their success as proof that you are behind."},
    {"start": 24.0, "end": 28.0, "text": "Social pain uses some of the same alarm signals as physical pain."},
    {"start": 28.5, "end": 32.5, "text": "That is why rejection can feel heavy in the body, not only in thoughts."},
    {"start": 36.0, "end": 40.0, "text": "The fix is not one big motivation speech."},
    {"start": 40.5, "end": 44.5, "text": "Small contact, sleep, and fewer late night comparisons lower the alarm."},
    {"start": 48.0, "end": 52.0, "text": "You are not broken because you feel alone sometimes."},
    {"start": 52.5, "end": 56.5, "text": "The feeling is a signal, and signals can be answered slowly."},
    {"start": 57.0, "end": 61.0, "text": "Start with one honest message to one safe person."},
    {"start": 61.5, "end": 64.0, "text": "Tonight, put the phone away before the comparison starts."},
]
draft = yt_tools.chapters_from_cues(CUES, target=5)
check(draft["valid"] is True, "drafted chapters validate", draft)
check([c["start"] for c in draft["chapters"]] == [0.0, 12.0, 24.0, 36.0, 48.0],
      "boundaries land on section pauses", draft)

# (d) viral ranking -----------------------------------------------------
VIDEOS = [
    {"channel": "Calm Mind Lab", "title": "Why You Feel Alone at 3 AM", "views": 120000, "url": "u1"},
    {"channel": "Calm Mind Lab", "title": "The Comparison Trap Nobody Talks About", "views": 20000, "url": "u2"},
    {"channel": "Calm Mind Lab", "title": "5 Signs Your Brain Is Tired", "views": 25000, "url": "u3"},
    {"channel": "Calm Mind Lab", "title": "How to Stop Feeling Behind", "views": 30000, "url": "u4"},
    {"channel": "Study Focus", "title": "I Studied 30 Days Without My Phone", "views": 90000, "url": "u5"},
    {"channel": "Study Focus", "title": "Morning Routine for Students", "views": 10000, "url": "u6"},
    {"channel": "Study Focus", "title": "Memory Tips That Actually Work", "views": 15000, "url": "u7"},
    {"channel": "Study Focus", "title": "Stop Wasting Your Evenings", "views": 20000, "url": "u8"},
    {"channel": "Tiny Channel", "title": "First Video", "views": 999999, "url": "u9"},
]
ranked = yt_tools.rank_viral(VIDEOS, min_multiple=2.0)
check([o["multiple"] for o in ranked["outliers"]] == [5.14, 4.36],
      "median multiples exact and ranked", ranked)
check(ranked["outliers"][0]["formula"] == "The Impossible Claim",
      "outlier formula named", ranked)
check(ranked["outliers"][1]["formula"] == "The Question",
      "question formula named", ranked)
check(ranked["skipped_thin_channels"] == [["Tiny Channel", 1]],
      "thin channel skipped and reported", ranked)

# (e) retention ---------------------------------------------------------
ROWS = [[0, 100], [5, 88], [10, 82], [15, 79], [20, 76], [25, 70],
        [30, 69], [40, 66], [50, 64], [60, 61], [70, 55], [80, 54],
        [90, 52], [100, 50]]
ret = yt_tools.read_retention(ROWS, duration=64, cues=CUES)
check(ret["ok"] is True and ret["hook_leak"] == 34.0,
      "hook leak exact", ret)
check(ret["cliffs"][0]["from"] == 0.0 and ret["cliffs"][0]["lost"] == 12.0,
      "first cliff exact", ret)
check(ret["slide_per_unit"] == 0.28, "slide exact", ret)
check("feel alone" in ret["said"].get("0.0", ""),
      "cliff names what was said", ret)
check(yt_tools.read_retention([[0, 100], [50, 60]])["ok"] is False,
      "under-8-points retention refused", "")

# (f) hooks + package ---------------------------------------------------
scored = yt_tools.score_hooks([
    "97% of channels quit before video 30 — here is what the other 3% do",
    "Welcome to my channel, today we talk about videos"])
check(scored["ranked"][0]["formula"] == "The Statistic",
      "statistic formula named", scored)
check(scored["ranked"][0]["total"] > scored["ranked"][1]["total"],
      "strong hook outranks weak hook", scored)

pkg = yt_tools.package_rank(
    ["Why You Feel Alone at 3 AM",
     "How to became YouTuber in 2026 with this amazing secret trick "
     "that changes everything forever"],
    ["NOT BROKEN", "AMAZING SECRET TRICK"])
# Both thumbnails lint 100 against the clean title (neither repeats
# its words); the curiosity tie-break decides between them. What the
# ranking must guarantee: the clean title wins, and the duplicating
# pair ranks last at its exact lint score.
check(pkg["best"]["title"] == "Why You Feel Alone at 3 AM" and
      pkg["best"]["lint_score"] == 100,
      "best pair carries the clean title at lint 100", pkg)
check(pkg["pairs"][-1]["lint_score"] == 48 and
      pkg["pairs"][-1]["thumbnail_text"] == "AMAZING SECRET TRICK",
      "duplicating pair ranks last at lint 48", pkg)

# (g) registry contract ---------------------------------------------------
reg = tools_registry.default_registry()
tools_registry.register_yt_tools(reg)
names = reg.names()
for n in ("yt_hook_score", "yt_title_lint", "yt_chapters_validate",
          "yt_chapters_from_cues", "yt_viral_rank", "yt_retention_read",
          "yt_package_rank"):
    check(n in names, f"{n} registered", names)
    e = reg.get(n)
    check(e["mutating"] is False and e["needs_allow"] is False
          and e["stub"] is False, f"{n} read-only non-stub", e)

tools = {t["name"]: t for t in reg.as_tools()}
ok_run, res = tools["yt_title_lint"]["run"](
    {"title": "Why You Feel Alone at 3 AM", "thumb": "NOT BROKEN"})
check(ok_run is True and res["score"] == 100,
      "yt_title_lint runs through the registry runner", res)
bad_run, reason = tools["yt_title_lint"]["run"]({})
check(bad_run is False and "missing required arg" in reason,
      "bad args refused before the handler", reason)

# agent_runner imports setup.py -> playwright, absent in this VM
# (pre-existing env gap; integrationtest.py fails the same way), so
# the build_tools wiring is asserted statically against its source.
_runner_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "agent_runner.py"), encoding="utf-8").read()
check("tools_registry.register_yt_tools(reg)" in _runner_src,
      "agent_runner.build_tools wires register_yt_tools", "")

# (h) engine rule ---------------------------------------------------------
check("yt_hook_score" in engine_instructions.ENGINE_CORE and
      "yt_chapters_validate" in engine_instructions.ENGINE_CORE,
      "ENGINE_CORE carries the YouTube-packaging tool rule", "")
text, _manifest = engine_instructions.load_instructions(job={})
check("YouTube packaging:" in text,
      "rule reaches the loaded instruction text", "")

print(f"\nALL {PASS} CHECKS PASS")
