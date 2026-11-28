"""toolroutingtest.py — rig for the tool-routing layer +
Antigravity-equivalent setup (brand / research / style).

  (a) selector: packaging task -> core + hook/packaging tools only;
      transcript task -> video_word_transcript only; footage task
      -> video_scene_list only; research task -> research tools;
      unrelated task -> matched=False, core only, stubs never picked.
  (b) brand: missing fields exact; questions only for missing;
      invalid hex refused; set/get round-trip in a temp workspace.
  (c) research: hook scored from cues, outlier multiple exact,
      no-signal data answered honestly.
  (d) style: pacing stats exact; palette ranked; script_check
      measures words/hook/AI-tells/outro exactly; audio_loudness
      on a generated tone returns a measured LUFS (skipped honestly
      when ffmpeg is absent).
  (e) registry + ENGINE_CORE wiring.
"""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brand_tools
import engine_instructions
import research_tools
import style_tools
import tool_routing
import tools_registry

PASS = 0


def check(cond, label, detail=""):
    global PASS
    if not cond:
        print(f"FAIL: {label} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"ok {PASS}: {label}")


CORE = tool_routing.CORE_TOOLS

# (a) selector -------------------------------------------------------
r = tool_routing.select_tools(
    "score these hooks and lint the title and thumbnail packaging")
check(r["matched"] and r["caps"] == ["packaging", "hook-scoring"],
      "packaging task caps exact", str(r))
check(r["tools"] == CORE + ["yt_hook_score", "yt_title_lint",
                            "yt_package_rank"],
      "packaging task picks only hook/packaging tools", str(r["tools"]))

r = tool_routing.select_tools("transcribe this voiceover and make captions")
check(r["tools"] == CORE + ["video_word_transcript"],
      "transcript task picks only video_word_transcript", str(r["tools"]))

r = tool_routing.select_tools(
    "find shot boundaries in this footage for b-roll")
check(r["tools"] == CORE + ["video_scene_list"],
      "footage task picks only video_scene_list", str(r["tools"]))

r = tool_routing.select_tools("research this niche outlier video")
check(r["tools"] == CORE + ["yt_viral_rank", "yt_research_analyze"],
      "research task picks only research tools", str(r["tools"]))

r = tool_routing.select_tools("write a poem about the moon")
check(r["matched"] is False and r["tools"] == CORE,
      "unrelated task: matched=False, core only", str(r))
check("noop" not in r["tools"] and "echo" not in r["tools"],
      "stubs never selected", str(r["tools"]))

r = tool_routing.select_tools("set up the brand design system",
                              available=["brand_profile_get",
                                         "brand_questions",
                                         "yt_hook_score"])
check(r["tools"] == ["brand_profile_get", "brand_questions"],
      "selector respects the available set", str(r["tools"]))

# (b) brand ----------------------------------------------------------
check(brand_tools.missing_fields({}) ==
      [d for d, _q, _k in brand_tools.PROFILE_FIELDS],
      "empty profile: every field missing", "")
qs = brand_tools.brand_questions({"channel": "WTU",
                                  "colors": {"primary": "#F5C518"}})
check([q["field"] for q in qs] ==
      [d for d, _q, _k in brand_tools.PROFILE_FIELDS
       if d not in ("channel", "colors.primary")],
      "questions only for missing fields, in order", str(qs))
ok, problems = brand_tools.validate_profile(
    {"colors": {"primary": "yellow"}})
check(not ok and problems and "colors.primary" in problems[0],
      "invalid hex refused by name", str(problems))

tmp = tempfile.mkdtemp()
try:
    reg = tools_registry.Registry()
    tools_registry.register_brand_tools(reg, tmp)
    tools = {t["name"]: t for t in reg.as_tools()}
    ok, res = tools["brand_profile_get"]["run"]({"channel": "WTU EN"})
    check(ok and res["exists"] is False and res["questions"],
          "brand get on empty workspace: exists=False + questions", str(res))
    prof = {"channel": "WTU EN", "audience": "young adults",
            "colors": {"primary": "#F5C518", "accent": "#FFFFFF",
                       "background": "#0A0A0A", "text": "#FFFFFF"},
            "fonts": {"title": "Oswald", "caption": "Inter"},
            "caption_style": {"position": "bottom",
                              "highlight": "yellow word"},
            "pacing": {"avg_shot_s": 3.5},
            "zoom_rules": "punch in on turns",
            "sfx_rules": "whoosh on cuts",
            "outro_line": "Follow for more"}
    ok, res = tools["brand_profile_set"]["run"](
        {"channel": "WTU EN", "profile": prof})
    check(ok and res["complete"] is True and res["missing"] == [],
          "brand set: complete profile saved", str(res))
    ok, res = tools["brand_profile_get"]["run"]({"channel": "WTU EN"})
    check(ok and res["exists"] and res["profile"]["colors"]["primary"] == "#F5C518",
          "brand get round-trips the saved profile", str(res)[:120])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# (c) research -------------------------------------------------------
cues = [{"start": 0, "end": 3, "text": "Stop checking everyone else's life"},
        {"start": 3, "end": 6, "text": "your feed is lying to you"},
        {"start": 20, "end": 24, "text": "here is the comparison trap"},
        {"start": 40, "end": 44, "text": "and how to leave it"}]
a = research_tools.analyze_video({
    "title": "Why Your Feed Makes You Feel Behind",
    "thumb": "YOU ARE NOT BEHIND", "cues": cues,
    "views": 50000, "channel_median_views": 10000})
check(a["hook"] and a["hook"]["score"]["formula"],
      "research: hook scored with a named formula", str(a["hook"]))
check(a["outlier"]["multiple"] == 5.0 and a["outlier"]["is_outlier"],
      "research: outlier multiple exact (5.0x)", str(a["outlier"]))
check(a["structure"]["cues"] == 4,
      "research: structure counts cues", str(a["structure"]))
a2 = research_tools.analyze_video({"title": "Plain title"})
check(a2["hook"] is None and a2["outlier"] is None and a2["ideas"],
      "research: no-signal data answered honestly", str(a2))

# (d) style ----------------------------------------------------------
scenes = [{"start": 0, "end": 2}, {"start": 2, "end": 6},
          {"start": 6, "end": 9}, {"start": 9, "end": 15}]
sp = style_tools.style_profile(scenes, ["#F5C518", "#F5C518", "#0A0A0A"])
check(sp["pacing"] == {"shots": 4, "avg_shot_s": 3.75,
                       "median_shot_s": 3.5, "min_shot_s": 2.0,
                       "max_shot_s": 6.0, "cuts_per_min": 16.0},
      "style: pacing stats exact", str(sp["pacing"]))
check(sp["palette"][0] == {"color": "#f5c518", "samples": 2}
      and sp["brand_patch"]["colors"]["primary"] == "#f5c518"
      and sp["brand_patch"]["pacing"]["avg_shot_s"] == 3.75,
      "style: palette ranked + brand_patch exact", str(sp))

sc = style_tools.script_check(
    "Stop scrolling now. This seamless journey will delve deep. "
    "Follow for more", wpm=150, short=True, outro="Follow for more")
check(sc["hook_words"] == 3 and sc["outro_ok"] is True
      and "seamless" in sc["ai_tells"] and "delve" in sc["ai_tells"]
      and sc["ok"] is False,
      "script_check: hook/outro/AI-tells measured exactly", str(sc))
sc2 = style_tools.script_check("One two three four five six seven eight nine.",
                               short=True)
check(sc2["hook_words"] == 9 and sc2["ok"] is False,
      "script_check: 9-word short hook flagged", str(sc2))

if shutil.which("ffmpeg"):
    tmp = tempfile.mkdtemp()
    try:
        wav = os.path.join(tmp, "tone.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "sine=frequency=1000:duration=3",
                        wav], check=True)
        ok, res = style_tools.audio_loudness(wav)
        check(ok and isinstance(res["integrated_lufs"], float),
              "audio_loudness: measured LUFS on a generated tone", str(res))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
else:
    print("skip: ffmpeg absent — loudness untested here")

# (e) registry + engine wiring ---------------------------------------
reg = tools_registry.default_registry()
tools_registry.register_routing_tool(reg)
tools_registry.register_research_tools(reg)
tmp = tempfile.mkdtemp()
try:
    tools_registry.register_brand_tools(reg, tmp)
    tools_registry.register_style_tools(reg, tmp)
    names = reg.names()
    for n in ("tool_select", "brand_profile_get", "brand_questions",
              "brand_profile_set", "yt_research_analyze",
              "style_profile_extract", "script_check", "audio_loudness"):
        check(n in names, f"registry offers {n}", str(names))
    check(reg.get("brand_profile_set")["needs_allow"] is True
          and reg.get("tool_select")["mutating"] is False,
          "registry flags: brand set needs Allow, selector read-only", "")
    tools = {t["name"]: t for t in reg.as_tools()}
    ok, res = tools["tool_select"]["run"](
        {"task": "transcribe this and make captions"})
    check(ok and res["tools"][-1] == "video_word_transcript"
          or ok and "video_word_transcript" not in res["tools"],
          "tool_select runs over the live registry", str(res)[:160])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "agent_runner.py"), encoding="utf-8").read()
for fn in ("register_routing_tool", "register_brand_tools",
           "register_research_tools", "register_style_tools"):
    check(f"tools_registry.{fn}(reg" in src,
          f"agent_runner.build_tools wires {fn}", "")
check("Tool routing:" in engine_instructions.ENGINE_CORE
      and "tool_select" in engine_instructions.ENGINE_CORE
      and "Brand design system:" in engine_instructions.ENGINE_CORE,
      "ENGINE_CORE carries routing + brand rules", "")

print(f"\nALL {PASS} CHECKS PASS")
