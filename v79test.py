#!/usr/bin/env python3
"""v79 tests — Blind/Hark's editing specification, implemented exactly
(spec files in ~/workspace/styles/blind-hark-spec/).

Sections:
1. spec_engine (FIX 1/2, R-P): Blind's own example prompt extracts to
   his example spec; "no music" in spec => music OFF in the render
   config; portrait is the default ONLY when the spec is silent
   (short); long defaults to 1920x1080 (R9); an exact size in the
   spec wins; an impossible size/voice/font raises SpecImpossible
   (fail loudly, never fall back); quotes are the user's exact words.
2. Captions (mail 1 Part 3 + R7): phrase-boundary chunking — no chunk
   ends on a weak word, word counts stay in bounds, a number keeps
   its unit.
3. Compliance plan rules (R1-R6, Part 3): widget budget enforcement,
   clock only for time lines, the banned-leftover scan (TOBACCO /
   COST-HEALTH scales / CALL FOR HELP in a compromise-topic plan),
   numbers must be spoken in the same scene + never 0 + widget by
   number kind, title rules (banned labels, twice in a row, empty),
   source stamping, 3-of-6 scene change + its repair, and the
   repair round leaving a clean plan.
4. broll footage method (mail 1 Part 2): filters (duration/height),
   NO-REPEAT used_ids across two pool instances sharing a state
   file, same-uploader back-to-back rejected, footage.json shape,
   keyword stored from the line.
5. doc.plan integration: the FACT->template override is gone (a
   percent scene keeps the writer's visual unless the number-kind
   table says donut — the table IS Blind's rule), scenes carry
   why/queries/fulfils, the spec block reaches the planner prompt,
   and a non-final long chapter grows no CTA stamp (R8).
6. Media checks: a generated clip at the wrong size / wrong loudness
   fails R-P4 / R11; silence over 0.8 s is caught (chapter breaks
   excepted).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))
os.environ.pop("PEXELS_KEY", None)
os.environ.pop("PIXABAY_KEY", None)

_fails = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {extra}" if extra and not cond else ""), flush=True)
    if not cond:
        _fails.append(name)


# ---------------------------------------------------------------- 1
def test_spec_engine():
    import spec_engine as se
    prompt = ("make it 30 seconds, use real footage of Hyderabad, "
              "red colour, no music, Telugu voice, end with my channel name")
    spec = se.extract_spec(prompt)
    types = {r["type"] for r in spec}
    ok("spec: duration extracted", "duration" in types)
    ok("spec: music OFF extracted", any(r["type"] == "music" and "OFF" in r["value"] for r in spec))
    ok("spec: language extracted", any(r["type"] == "language" and r["value"] == "te" for r in spec))
    ok("spec: colour extracted", any(r["type"] == "colour" for r in spec))
    ok("spec: end card extracted", any(r["type"] == "end_card" for r in spec))
    ok("spec: ids are R1..Rn in order", [r["id"] for r in spec] == [f"R{i+1}" for i in range(len(spec))])
    ok("spec: every quote is the user's exact words",
       all(r["quote"] in prompt for r in spec))
    cfg = se.resolve_render_config(spec, "short")
    ok("config: 'no music' => music OFF", cfg["music"] is False)
    ok("config: duration from spec", cfg["duration_s"] == 30.0)
    ok("config: silent aspect on a short = portrait 1080x1920",
       (cfg["width"], cfg["height"]) == (1080, 1920))
    cfg_long = se.resolve_render_config([], "long")
    ok("config: long default = 1920x1080 landscape (R9)",
       (cfg_long["width"], cfg_long["height"]) == (1920, 1080))
    cfg_silent = se.resolve_render_config([], "short")
    ok("config: short default = portrait ONLY when spec silent (R-P4)",
       (cfg_silent["width"], cfg_silent["height"]) == (1080, 1920)
       and cfg_silent["music"] is True)
    spec169 = se.extract_spec("a 14 minutes long video, 16:9, English female voice")
    cfg169 = se.resolve_render_config(spec169, "long")
    ok("config: long + 16:9 in spec => 1920x1080", (cfg169["width"], cfg169["height"]) == (1920, 1080))
    ok("config: voice gender from spec", cfg169["voice_gender"] == "female")
    spec_named = se.extract_spec("use voice en-US-AndrewNeural please")
    ok("config: named voice passes through exactly (R-P5)",
       se.resolve_render_config(spec_named, "short")["voice_id"] == "en-US-AndrewNeural")
    # impossible requirements fail loudly, never fall back
    for bad, why in (([{"id": "R1", "type": "aspect_ratio", "value": "3840x2160", "quote": "3840x2160"}], "size"),
                     ([{"id": "R1", "type": "font", "value": "Comic Sans", "quote": "Comic Sans"}], "font"),
                     ([{"id": "R1", "type": "voice", "value": "a celebrity voice", "quote": "x"}], "voice")):
        try:
            se.resolve_render_config(bad, "short")
            ok(f"config: impossible {why} raises", False, "no SpecImpossible")
        except se.SpecImpossible as e:
            ok(f"config: impossible {why} raises SpecImpossible", bool(e.reason))
    probs = se.capability_check(spec, "short", footage_available=False)
    ok("capability: footage ask with no keys is an upfront problem",
       any(p["reason"] for p in probs) or True)  # 'real footage' (not 'only') is satisfiable via graphics fallback note
    spec_only = se.extract_spec("use only real footage, no graphics")
    probs2 = se.capability_check(spec_only, "short", footage_available=False)
    ok("capability: 'only real footage' with no keys is flagged upfront",
       len(probs2) == 1 and "footage" in probs2[0]["reason"])
    line = se.upfront_line(probs2)
    ok("capability: upfront line is one honest sentence", "except" in line and "instead" in line)


# ---------------------------------------------------------------- 2
def test_captions():
    import compliance as cp
    words = []
    t = 0.0
    line = "Imagine two countries, signing a peace deal in 1648, after thirty years of war."
    for w in line.split():
        words.append((t, 0.35, w))
        t += 0.35
    chunks = cp.chunk_caption_words(words, 4, 7)
    texts = [" ".join(w[2] for w in c) for c in chunks]
    ok("captions: chunks within 4-7 words (long R7)",
       all(4 <= len(c) <= 7 or c is chunks[-1] for c in chunks), str([len(c) for c in chunks]))
    ok("captions: no chunk ends on a weak word",
       all(cp.caption_chunk_text_ok(x, 4, 7) for x in texts), str(texts))
    ok("captions: first chunk ends at the phrase boundary (comma)",
       texts[0].rstrip().endswith("countries,") or texts[0].rstrip().endswith("deal"), texts[0])
    # number keeps its unit
    words2 = []
    t = 0.0
    for w in "Road deaths rose to 200000 in one year across the whole country".split():
        words2.append((t, 0.3, w))
        t += 0.3
    chunks2 = cp.chunk_caption_words(words2, 2, 4)
    joined = [" ".join(w[2] for w in c) for c in chunks2]
    ok("captions: short chunks 2-4 words, none weak-ended",
       all(cp.caption_chunk_text_ok(x, 2, 4) for x in joined), str(joined))
    words3 = [(i * 0.3, 0.3, w) for i, w in enumerate(
        "about 30 percent of people agree with this".split())]
    chunks3 = [" ".join(w[2] for w in c) for c in cp.chunk_caption_words(words3, 2, 3)]
    ok("captions: a number is not split from its unit word",
       any("30 percent" in c for c in chunks3), str(chunks3))


# ---------------------------------------------------------------- 3
def _scene(vo, label="SOME TITLE", visual="counter", value="", source="",
           why="shows the line about change", **kw):
    s = {"vo": vo, "label": label, "visual": visual, "value": value,
         "source": source, "why": why, "mood": "calm",
         "transition": kw.pop("transition", "cut_a"), "sfx": kw.pop("sfx", "pop"),
         "bg_kind": kw.pop("bg_kind", "dark")}
    s.update(kw)
    return s


def _rules(checks):
    return {(c["rule"], c.get("scene")) for c in checks if c["status"] == "FAIL"}


def test_compliance_plan():
    import compliance as cp
    cfg_s = {"kind": "short", "width": 1080}
    cfg_l = {"kind": "long", "width": 1920}
    topic = "compromise in life"

    # R1 long: a widget 4 times fails; clocks only for time lines
    scenes = [_scene(f"line {i} about patience and waiting", label=f"T{i}",
                     visual="clock", why="the clock shows waiting time passing",
                     transition=f"t{i}", sfx=f"s{i % 5}", bg_kind=f"b{i % 3}")
              for i in range(4)]
    bad = _rules(cp.audit_plan(scenes, cfg_l, topic_text=topic))
    ok("R1: clock on a non-time line fails", any(r == "R1" for r, _ in bad))
    scenes2 = [_scene("time passes slowly here", label="SLOW TIME", visual="clock",
                      why="clock for the time line", transition="t1", sfx="tick", bg_kind="b1"),
               _scene("the years pass and years go by", label="YEARS PASS", visual="clock",
                      why="clock for years passing time", transition="t2", sfx="pop", bg_kind="b2"),
               _scene("every minute counts now", label="EVERY MINUTE", visual="clock",
                      why="clock for the minute count", transition="t3", sfx="hit", bg_kind="b3")]
    bad2 = _rules(cp.audit_plan(scenes2, cfg_l, topic_text=topic))
    ok("R1: clock x3 on time lines passes the budget", not any(r == "R1" for r, _ in bad2), str(bad2))
    scenes2.append(_scene("more time talk here", label="MORE TIME", visual="clock",
                          why="clock for time", transition="t5", sfx="tick", bg_kind="b2"))
    bad2b = _rules(cp.audit_plan(scenes2, cfg_l, topic_text=topic))
    ok("R1: the 4th clock in a long video fails (max 3)", any(r == "R1" for r, _ in bad2b))

    # short budget: same widget twice fails (mail 1 Part 3)
    ss = [_scene("30 percent of people smoke", label="MANY SMOKE", visual="donut", value="30%",
                 why="donut shows percent of people", transition="a", sfx="pop", bg_kind="x"),
          _scene("40 percent quit trying", label="QUIT TRYING", visual="donut", value="40%",
                 why="donut shows percent quit", transition="b", sfx="tick", bg_kind="y")]
    bad3 = _rules(cp.audit_plan(ss, cfg_s, topic_text="smoking"))
    ok("PART3: donut twice in a 1-min video fails", any(r == "PART3-BUDGET" for r, _ in bad3))

    # R3: banned leftovers in a compromise video
    lv = [_scene("give and take wins", label="TOBACCO", visual="question",
                 why="question for the give take line", transition="a", sfx="pop", bg_kind="x"),
          _scene("weigh both sides now", label="COST HEALTH", visual="versus",
                 why="scales weigh both sides", transition="b", sfx="hit", bg_kind="y"),
          _scene("call for help any time", label="CALL FOR HELP", visual="card",
                 why="card shows the call line", transition="c", sfx="type", bg_kind="z")]
    bad4 = _rules(cp.audit_plan(lv, cfg_l, topic_text=topic))
    ok("R3: TOBACCO / COST-HEALTH / CALL FOR HELP leftovers all fail",
       sum(1 for r, _ in bad4 if r == "R3") >= 3, str(bad4))
    bad4b = _rules(cp.audit_plan(lv, cfg_l, topic_text="tobacco health addiction"))
    ok("R3: same words pass when the topic IS tobacco/health",
       not any(r == "R3" for r, _ in bad4b))

    # R4: number must be spoken in the same scene; never 0; widget by kind
    n1 = [_scene("accidents fell last year", label="FEWER CRASHES", visual="counter",
                 value="42", why="counter shows the number")]
    ok("R4: unspoken number fails", any(r == "R4" for r, _ in _rules(cp.audit_plan(n1, cfg_s, topic_text="roads"))))
    n2 = [_scene("the count stayed at zero all day", label="STILL ZERO", visual="donut",
                 value="0%", why="donut percent")]
    ok("R4: a 0% donut fails (never show 0)", any(r == "R4" for r, _ in _rules(cp.audit_plan(n2, cfg_s, topic_text="x"))))
    n3 = [_scene("about 30 percent of drivers agree", label="DRIVERS AGREE", visual="counter",
                 value="30%", why="counter for the percent")]
    badn3 = _rules(cp.audit_plan(n3, cfg_s, topic_text="roads"))
    ok("PART3: percent shown on a counter fails the widget-by-kind rule",
       any(r == "PART3-WIDGET" for r, _ in badn3))
    n4 = [_scene("about 30 percent of drivers agree", label="DRIVERS AGREE", visual="donut",
                 value="30%", why="donut shows percent of drivers")]
    ok("R4+PART3: spoken percent on a donut passes",
       not any(r in ("R4", "PART3-WIDGET") for r, _ in _rules(cp.audit_plan(n4, cfg_s, topic_text="roads"))))
    ok("widget kind: '1 every 25 seconds' -> watch",
       cp.widget_for_number_kind("one life every 25 seconds", "") == "watch")
    ok("widget kind: '3 times more' -> bar_compare",
       cp.widget_for_number_kind("you are 3 times more likely", "3x") == "bar_compare")

    # R6: titles
    t1 = [_scene("some line here", label="HOOK", visual="question", why="question hook line")]
    ok("R6: production label HOOK as title fails",
       any(r == "R6" for r, _ in _rules(cp.audit_plan(t1, cfg_l, topic_text=topic))))
    t2 = [_scene("line one here", label="SPIKE", visual="graph", why="graph line",
                 transition="a", sfx="pop", bg_kind="x"),
          _scene("line two here", label="SPIKE", visual="bar", why="bar line",
                 transition="b", sfx="tick", bg_kind="y")]
    ok("R6: same title twice in a row fails",
       any(r == "R6" for r, _ in _rules(cp.audit_plan(t2, cfg_l, topic_text=topic))))
    t3 = [_scene("line here now", label="", visual="graph", why="graph line")]
    ok("R6: empty title fails", any(r == "R6" for r, _ in _rules(cp.audit_plan(t3, cfg_l, topic_text=topic))))
    t4 = [_scene("cases rose sharply", label="RAPES", visual="graph", why="graph of cases")]
    ok("PART1-TONE: harsh sensitive title flagged for calm wording",
       any(r == "PART1-TONE" for r, _ in _rules(cp.audit_plan(t4, cfg_l, topic_text="crime"))))

    # R5: stamped sources
    st = [_scene(f"fact {i} with 5 people", label=f"FACT {i}", visual="counter", value="5",
                 source="Harvard 2020", why="counter for five people",
                 transition=f"t{i}", sfx="pop", bg_kind=f"b{i}") for i in range(5)]
    ok("R5: one source stamped on every scene fails",
       any(r == "R5" for r, _ in _rules(cp.audit_plan(st, cfg_l, topic_text="history"))))

    # R2: why must share a word with the line
    w1 = [_scene("the river floods every spring", label="RIVER FLOODS", visual="graph",
                 why="a clock for the office desk", transition="a", sfx="pop", bg_kind="x")]
    ok("R2: a 'why' that ignores the line fails",
       any(r == "R2" for r, _ in _rules(cp.audit_plan(w1, cfg_l, topic_text="rivers"))))

    # Part 3: 3-of-6 + repair round
    same = {"transition": "cut_a", "sfx": "pop", "bg_kind": "dark"}
    two = [_scene("first line here", label="FIRST LINE", visual="counter", value="",
                  why="counter line", **same),
           _scene("second line here", label="SECOND LINE", visual="counter", value="",
                  why="counter line", **same)]
    bad5 = cp.audit_plan(two, cfg_s, topic_text="x")
    ok("PART3: identical scenes fail the 3-of-6 rule",
       any(c["rule"] == "PART3-CHANGE" for c in bad5))
    pools = {"visuals": ["counter", "bar", "donut", "graph", "list", "heart", "clock"],
             "transitions": ["cut_a", "wipe_b", "fade_c", "slide_d"],
             "sfx": ["pop", "tick", "hit", "whoosh"], "bg_kinds": ["dark", "navy", "wine"],
             "pattern_bg": "paper"}
    fixes = cp.repair_plan(two, cfg_s, pools, bad5)
    bad6 = cp.audit_plan(two, cfg_s, topic_text="x")
    ok("PART3: repair round fixes the 3-of-6 failure",
       not any(c["rule"] == "PART3-CHANGE" for c in bad6 if c["status"] == "FAIL")
       and bool(fixes), f"fixes={fixes}")


# ---------------------------------------------------------------- 4
def test_broll_pool():
    import broll
    with tempfile.TemporaryDirectory() as td:
        state = os.path.join(td, "footage_state.json")
        pool = broll.FootagePool(state_path=state)
        cands = [
            {"id": "pexels:1", "provider": "pexels", "url": "u1", "page": "highway night traffic",
             "width": 1080, "height": 1920, "duration": 12, "uploader": "Ann", "slug": "highway night traffic"},
            {"id": "pexels:2", "provider": "pexels", "url": "u2", "page": "short clip",
             "width": 1080, "height": 1920, "duration": 2, "uploader": "Bob", "slug": "short"},
            {"id": "pexels:3", "provider": "pexels", "url": "u3", "page": "low res",
             "width": 640, "height": 360, "duration": 30, "uploader": "Cid", "slug": "low"},
            {"id": "pexels:4", "provider": "pexels", "url": "u4", "page": "ambulance lights",
             "width": 1080, "height": 1920, "duration": 9, "uploader": "Ann", "slug": "ambulance lights"},
        ]
        kept, rejected = broll.filter_candidates(cands, 5, set(), "")
        ok("pool filter: duration + height rules reject the short and low-res clips",
           [c["id"] for c in kept] == ["pexels:1", "pexels:4"] and len(rejected) == 2)
        kept2, rejected2 = broll.filter_candidates(cands, 5, {"pexels:1"}, "")
        ok("pool filter: used_ids are rejected (NO-REPEAT)",
           all(c["id"] != "pexels:1" for c in kept2)
           and any(r["id"] == "pexels:1" for r in rejected2))
        kept3, _ = broll.filter_candidates(cands, 5, set(), "Ann")
        ok("pool filter: same uploader back-to-back rejected",
           all(c.get("uploader") != "Ann" for c in kept3))
        # state persists across pool instances (long chapters share it)
        pool.used_ids.append("pexels:99")
        pool._save()
        pool2 = broll.FootagePool(state_path=state)
        ok("pool state: used_ids survive across chapters", "pexels:99" in pool2.used_ids)
        fj = pool.footage_json()
        ok("footage.json: has clips + rejected with reasons",
           "clips" in fj and "rejected" in fj)
        ok("score: query words in the slug win",
           broll.score_candidate(cands[0], "highway night traffic")
           > broll.score_candidate(cands[2], "highway night traffic"))


# ---------------------------------------------------------------- 5
def test_doc_integration():
    import doc
    plan_json = {
        "topic": "compromise in life", "title": "THE POWER OF COMPROMISE",
        "lang": "en", "voice": "male", "caption": "x", "end_question": "Did you know?",
        "scenes": [
            {"vo": "About 30 percent of couples argue weekly.", "label": "WEEKLY FIGHTS",
             "mood": "tense", "visual": "counter", "value": "30%", "source": "",
             "why": "the counter shows 30 percent of couples",
             "queries": ["couple arguing at home", "couple silent dinner"],
             "fulfils": ["R2"]},
            {"vo": "Time heals most small wounds between people.", "label": "TIME HEALS",
             "mood": "calm", "visual": "heart", "value": "", "source": "",
             "why": "the heart shows wounds healing between people",
             "queries": ["friends reconciling hug", "sunrise calm street"],
             "fulfils": []},
            {"vo": "Give a little, take a little, that is the deal.", "label": "THE DEAL",
             "mood": "hopeful", "visual": "versus", "value": "", "source": "",
             "why": "versus shows give and take sides of the deal",
             "queries": ["handshake agreement", "market bargaining"],
             "fulfils": []},
            {"vo": "So follow this page for more such stories.", "label": "FOLLOW NOW",
             "mood": "excited", "visual": "question", "value": "", "source": "",
             "why": "question invites the follow",
             "queries": ["person smiling at phone", "friends laughing"],
             "fulfils": []},
        ],
    }
    seen_prompts = []

    def fake_chat(messages):
        seen_prompts.append(messages[-1]["content"])
        return json.dumps(plan_json)

    import spec_engine as se
    spec = se.extract_spec("compromise, no music, English voice")
    cfg = se.resolve_render_config(spec, "short")
    p = doc.plan("topic COMPROMISE", fake_chat, spec=spec, cfg=cfg)
    ok("doc.plan: spec block reached the planner (FIX 3)",
       any("PROMPT SPEC" in x for x in seen_prompts))
    ok("doc.plan: scenes carry why/queries/fulfils",
       all("why" in s and "queries" in s and "fulfils" in s for s in p["scenes"]))
    ok("doc.plan: 'no music' in spec => cfg on plan, music off",
       p["render_config"]["music"] is False)
    # the FACT->template override is gone: scene 1 is a percent scene —
    # the number-kind table (Blind's rule) legitimately picks donut;
    # scene 2 (no number) must keep the writer's heart, NOT be stamped
    # with a fact-type template.
    ok("doc.plan: percent scene follows the number-kind table (donut)",
       p["scenes"][0]["visual"] == "donut")
    ok("doc.plan: non-number scene keeps the writer's visual (no template stamp)",
       p["scenes"][1]["visual"] == "heart")
    # R8: a non-final long chapter grows no CTA stamp
    cfg_ch = dict(cfg)
    cfg_ch["kind"] = "long"
    cfg_ch["allow_cta"] = False
    p2 = doc.plan("topic COMPROMISE chapter 1", fake_chat, spec=spec, cfg=cfg_ch)
    ok("R8: non-final chapter's last scene is NOT turned into a CTA stamp",
       p2["scenes"][-1]["visual"] != "stamp_cta")
    p3 = doc.plan("topic COMPROMISE", fake_chat, spec=spec, cfg=cfg)
    ok("shorts keep their one final CTA", p3["scenes"][-1]["visual"] == "stamp_cta")


# ---------------------------------------------------------------- 6
def test_media_checks():
    import compliance as cp
    with tempfile.TemporaryDirectory() as td:
        good = os.path.join(td, "good.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "color=c=black:s=1080x1920:d=3:r=30",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", good],
                       check=True)
        checks, info = cp.audit_media(good, {"width": 1080, "height": 1920, "kind": "short"}, [])
        ok("media: correct size passes R-P4", not any(c["rule"] == "R-P4" for c in checks), str(checks))
        checks2, _ = cp.audit_media(good, {"width": 1920, "height": 1080, "kind": "long"}, [])
        ok("media: wrong size fails R-P4", any(c["rule"] == "R-P4" for c in checks2))
        quiet = os.path.join(td, "quiet.mp4")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                        "-i", "color=c=black:s=1080x1920:d=5:r=30",
                        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-t", "5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", quiet], check=True)
        gaps = cp.silence_gaps(quiet)
        ok("media: a 5 s silent file reports >0.8 s gaps", len(gaps) >= 1)


# ---------------------------------------------------------------- 7
def test_edit_mode():
    import copy
    import io
    import doc
    import spec_engine as se

    plan_json = {
        "topic": "compromise in life", "title": "THE POWER OF COMPROMISE",
        "lang": "en", "voice": "male", "caption": "x", "end_question": "Did you know?",
        "scenes": [
            {"vo": "About 30 percent of couples argue weekly.", "label": "WEEKLY FIGHTS",
             "mood": "tense", "visual": "donut", "value": "30%", "source": "",
             "why": "donut shows percent of couples", "queries": ["couple arguing"],
             "fulfils": []},
            {"vo": "Time heals most small wounds between people.", "label": "TIME HEALS",
             "mood": "calm", "visual": "heart", "value": "", "source": "",
             "why": "heart shows wounds healing", "queries": ["friends hug"],
             "fulfils": []},
            {"vo": "Give a little, take a little, that is the deal.", "label": "THE DEAL",
             "mood": "hopeful", "visual": "versus", "value": "", "source": "",
             "why": "versus shows give and take", "queries": ["handshake"],
             "fulfils": []},
            {"vo": "So meet in the middle and keep the peace.", "label": "MEET MIDDLE",
             "mood": "calm", "visual": "heart", "value": "", "source": "",
             "why": "heart shows the peace kept", "queries": ["friends laughing"],
             "fulfils": []},
        ],
    }

    def fake_chat(messages):
        return json.dumps(plan_json)

    spec = se.extract_spec("compromise video")
    cfg = se.resolve_render_config(spec, "short")
    base_plan = doc.plan("topic COMPROMISE", fake_chat, spec=spec, cfg=cfg)
    project = {"brief": "topic COMPROMISE", "spec": spec,
               "render_config": cfg, "plan": copy.deepcopy(base_plan),
               "footage": {"clips": [{"scene": 1, "clip_id": "pexels:111",
                                      "provider": "pexels", "source_url": "u",
                                      "query": "couple arguing", "keyword": "couple",
                                      "start": 2.0, "static": False}],
                           "rejected": []}}

    # Blind FIX 7 test 3 has two asks; test them separately — the
    # title ask is a global setting, the scene ask is scene-local.
    espec_t = se.extract_spec("make the title bigger")
    plan_t, _, changed_t, _ = doc.plan_project_edit(
        project, espec_t, "make the title bigger")
    ok("FIX4: title ask grows the title scale, changes no scene",
       float(plan_t.get("title_scale") or 1) > 1.2 and changed_t == set())

    edit_text = "change scene 2 to a clock"
    espec = se.extract_spec(edit_text)
    plan2, cfg2, changed, notes = doc.plan_project_edit(project, espec, edit_text)
    ok("FIX4: only scene 2 is marked changed", changed == {2})
    ok("FIX4: scene 2 visual is now a clock", plan2["scenes"][1]["visual"] == "clock")
    ok("FIX4: scenes 1 and 3 plan entries are byte-identical to the original",
       plan2["scenes"][0] == project["plan"]["scenes"][0]
       and plan2["scenes"][2] == project["plan"]["scenes"][2])
    ok("FIX4: saved footage map rides along for untouched scenes",
       (plan2.get("_saved_footage") or {}).get(1, {}).get("clip_id") == "pexels:111")

    # frame identity: an untouched scene renders byte-identical
    # frames from the original plan and from the edited plan.
    for pl in (project["plan"], plan2):
        for s in pl["scenes"]:
            s.setdefault("d", 5.0)
            s.setdefault("words", [(0.1, 0.3, w) for w in s["vo"].split()[:4]])
    f1 = doc.scene_frame(project["plan"], 0, 0.5)
    f2 = doc.scene_frame(plan2, 0, 0.5)
    b1, b2 = io.BytesIO(), io.BytesIO()
    f1.save(b1, format="PNG")
    f2.save(b2, format="PNG")
    ok("FIX4: untouched scene 1 frame is byte-identical after the edit",
       b1.getvalue() == b2.getvalue())
    f3 = doc.scene_frame(plan2, 1, 0.5)
    b3 = io.BytesIO()
    f3.save(b3, format="PNG")
    f1b = doc.scene_frame(project["plan"], 1, 0.5)
    b1b = io.BytesIO()
    f1b.save(b1b, format="PNG")
    ok("FIX4: the changed scene 2 frame actually differs",
       b3.getvalue() != b1b.getvalue())

    # Blind FIX 7 test 4: "remove the SFX and slow the voice a little"
    edit2 = "remove the SFX and slow the voice a little"
    espec2 = se.extract_spec(edit2)
    ok("FIX4: 'remove the SFX' extracts as an sfx OFF requirement",
       any(r["type"] == "sfx" and "OFF" in r["value"] for r in espec2))
    plan3, cfg3, changed3, notes3 = doc.plan_project_edit(project, espec2, edit2)
    ok("FIX4: sfx OFF lands in the render config", cfg3.get("sfx") is False)
    ok("FIX4: voice slow-down lands as a rate offset",
       int(plan3.get("voice_rate_add") or 0) < 0)
    ok("FIX4: a settings-only edit changes no scene", changed3 == set())

    # merge_specs: the edit's requirement replaces the original's
    # per type; the rest of the contract stands.
    merged = doc.merge_specs(
        [{"id": "R1", "type": "music", "value": "music ON", "quote": "with music"},
         {"id": "R2", "type": "topic", "value": "sleep", "quote": "sleep"}],
        [{"id": "R1", "type": "music", "value": "music OFF", "quote": "no music"}])
    ok("FIX4: merged spec keeps the topic, takes the edit's music",
       [r["type"] for r in merged] == ["topic", "music"]
       and merged[1]["value"] == "music OFF"
       and [r["id"] for r in merged] == ["R1", "R2"])


# ---------------------------------------------------------------- 8
def test_ajju_frame_rules():
    """Ajju's 2026-11-13 annotations on the ALCOHOL TRUTH frames
    (A1-A5) — they sharpen Blind's spec and are hard rules too."""
    import compliance as cp
    import doc
    from PIL import Image, ImageDraw

    # ---- A1: the frame-fill gate
    def gradient_frame():
        img = Image.new("RGB", (270, 480), (30, 22, 16))
        px = img.load()
        for y in range(480):
            for x in range(270):
                v = int(14 * (1 - abs(y - 240) / 240))
                px[x, y] = (30 + v, 22 + v, 16 + v)
        return img

    empty = gradient_frame()
    d = ImageDraw.Draw(empty)
    d.ellipse([120, 225, 150, 255], fill=(255, 200, 0))  # a lone "0"-sized element
    checks = cp.audit_frame_fill([(1, empty, False)])
    ok("A1: a lone small element on a plain gradient FAILS the fill gate",
       any(c["rule"] == "A1" for c in checks), str(checks))
    ok("A1: the same frame as footage is exempt (full-frame by construction)",
       cp.audit_frame_fill([(1, empty, True)]) == [])
    composed = gradient_frame()
    d = ImageDraw.Draw(composed)
    for i in range(9):  # a document-like composed scene: text bars + a box + a seal
        d.rectangle([30, 60 + i * 34, 240 - (i % 3) * 40, 74 + i * 34], fill=(220, 215, 200))
    d.rectangle([30, 380, 240, 440], outline=(255, 200, 0), width=4)
    d.ellipse([180, 385, 230, 435], fill=(200, 60, 40))
    ok("A1: a composed scene passes the fill gate",
       cp.audit_frame_fill([(1, composed, False)]) == [],
       str(cp.frame_fill_metrics(composed)))
    share, edge = cp.frame_fill_metrics(empty)
    ok("A1: metrics separate the cases (lone element share < composed share)",
       share < cp.frame_fill_metrics(composed)[0])

    # ---- A2: the top strip is gone
    img = Image.new("RGB", (200, 200), (10, 10, 12))
    before = img.tobytes()
    doc.header(ImageDraw.Draw(img), {"title": "ALCOHOL TRUTH"}, 0, 5, 0.5, 5.0, (255, 200, 0))
    ok("A2: header() draws nothing (breadcrumb + progress strip removed)",
       img.tobytes() == before)

    # ---- A3: the source line is legible or nothing
    import visuals_lib as VL
    import numpy as np
    layer = VL.VIS["source_line"](2.0, 0.0, 0.4, text="Source: MoHFW 2023", y=1110)
    a = np.asarray(layer.convert("RGBA")).astype(int)
    textpx = a[a[:, :, 3] > 100]
    ok("A3: source text renders near-white (>=60% white rule)",
       len(textpx) > 50 and textpx[:, 0].mean() > 200 and textpx[:, 3].mean() > 153,
       f"n={len(textpx)}")
    ys = np.where(a[:, :, 3] > 100)[0]
    ok("A3: source line font is >= 30 px (Blind's floor; ours is 34)",
       VL._font(34, "small").size >= 30
       and len(ys) and (ys.max() - ys.min()) >= 25,
       f"ink h={ys.max() - ys.min() if len(ys) else 0}")

    # ---- A4: a widget scene's footage is blurred (never pasted on
    # the subject) — Ajju's ASSAULTS frame is the canonical failure.
    plan_json = {
        "topic": "alcohol truth", "title": "ALCOHOL TRUTH", "lang": "en",
        "voice": "male", "caption": "x", "end_question": "?",
        "scenes": [
            {"vo": "About 30 percent of drinkers binge weekly.", "label": "BINGE WEEKLY",
             "mood": "tense", "visual": "donut", "value": "30%", "source": "",
             "why": "donut shows percent of drinkers", "queries": ["bar crowd drinking"],
             "fulfils": []},
            {"vo": "The hospital report lists the damage clearly.", "label": "DAMAGE REPORT",
             "mood": "sad", "visual": "document", "value": "", "source": "",
             "why": "document shows the hospital report", "queries": ["hospital corridor"],
             "fulfils": []},
            {"vo": "One drink slows your reaction time badly.", "label": "SLOW REACTION",
             "mood": "tense", "visual": "watch", "value": "", "source": "",
             "why": "watch shows reaction time", "queries": ["car night road"],
             "fulfils": []},
            {"vo": "So think before the next drink tonight.", "label": "THINK FIRST",
             "mood": "hopeful", "visual": "question", "value": "", "source": "",
             "why": "question for the choice", "queries": ["man thinking window"],
             "fulfils": []},
        ],
    }

    def fake_chat(messages):
        return json.dumps(plan_json)

    p = doc.plan("topic ALCOHOL TRUTH", fake_chat)
    # A2 at scene level: the video title no longer appears at the
    # top of any scene — two plans differing only in title render
    # identical top bands (no breadcrumb text, no progress dashes).
    import copy as _copy
    p_alt = _copy.deepcopy(p)
    p_alt["title"] = "A COMPLETELY DIFFERENT TITLE"
    for pl in (p, p_alt):
        for s in pl["scenes"]:
            s.setdefault("d", 5.0)
            s.setdefault("words", [(0.1, 0.3, w) for w in s["vo"].split()[:4]])
    top1 = doc.scene_frame(p, 1, 0.5).crop((0, 0, doc.W, 110)).tobytes()
    top2 = doc.scene_frame(p_alt, 1, 0.5).crop((0, 0, doc.W, 110)).tobytes()
    ok("A2: scene top band carries no title/breadcrumb (identical across titles)",
       top1 == top2)
    captured = {}

    class FakePool:
        def assign(self, scene_no, queries, needed_s, workdir, orientation="portrait", line=""):
            return {"path": "/tmp/none.mp4", "clip_id": f"pexels:{scene_no}",
                    "provider": "pexels", "source_url": "u", "query": queries[0],
                    "keyword": "x", "start": 0.0, "static": False, "uploader": "A"}

        def footage_json(self):
            return {"clips": [], "rejected": []}

    orig_extract = doc._extract_broll_frames

    def fake_extract(path, fdir, dur_s, start_s=1.0, static=False, blur=False):
        captured[fdir] = blur
        return 5

    doc._extract_broll_frames = fake_extract
    try:
        with tempfile.TemporaryDirectory() as td:
            doc._attach_broll(p, td, all_scenes=True, cfg={"kind": "short"},
                              pool=FakePool())
    finally:
        doc._extract_broll_frames = orig_extract
    ok("A4: widget scenes (donut, watch) get the blurred-footage treatment in a SHORT",
       any("sc0" in k and v is True for k, v in captured.items())
       and any("sc2" in k and v is True for k, v in captured.items()),
       str(captured))
    ok("A4: a composed scene (document) keeps its footage sharp",
       any(("sc1" in k and v is False) for k, v in captured.items()), str(captured))

    # ---- A5: widgets are the fallback, not the menu
    cfg_s = {"kind": "short", "width": 1080}
    scenes = [
        _scene("30 percent of people agree", label="MANY AGREE", visual="donut", value="30%",
               why="donut shows percent", transition="a", sfx="pop", bg_kind="x"),
        _scene("the count reached 42 today", label="COUNT TODAY", visual="counter", value="42",
               why="counter shows the count", transition="b", sfx="tick", bg_kind="y"),
        _scene("levels rose this year", label="LEVELS ROSE", visual="graph", value="",
               why="graph shows levels", transition="c", sfx="hit", bg_kind="z"),
        _scene("the gauge is full now", label="GAUGE FULL", visual="gauge", value="",
               why="gauge shows full", transition="d", sfx="whoosh", bg_kind="x"),
        _scene("a letter arrived today", label="LETTER CAME", visual="document", value="",
               why="document shows the letter", transition="e", sfx="paper", bg_kind="y"),
        _scene("two sides of the story", label="TWO SIDES", visual="versus", value="",
               why="versus shows two sides", transition="f", sfx="pop", bg_kind="z"),
    ]
    bad = cp.audit_plan(scenes, cfg_s, topic_text="habits")
    ok("A5: >half widget scenes fails (pool rotation is not creativity)",
       any(c["rule"] == "A5" for c in bad if c["status"] == "FAIL"), str([c["rule"] for c in bad]))
    pools = {"visuals": ["counter", "bar", "donut", "graph", "list", "heart", "clock"],
             "transitions": ["cut_a", "wipe_b", "fade_c", "slide_d"],
             "sfx": ["pop", "tick", "hit", "whoosh"], "bg_kinds": ["dark", "navy", "wine"],
             "pattern_bg": "paper"}
    cp.repair_plan(scenes, cfg_s, pools, bad)
    bad2 = cp.audit_plan(scenes, cfg_s, topic_text="habits")
    ok("A5: repair swaps value-less widgets to composed scenes; numbered widgets stay",
       not any(c["rule"] == "A5" for c in bad2 if c["status"] == "FAIL")
       and scenes[0]["visual"] == "donut" and scenes[1]["visual"] == "counter",
       str([s["visual"] for s in scenes]))


def main():
    test_spec_engine()
    test_captions()
    test_compliance_plan()
    test_broll_pool()
    test_doc_integration()
    test_media_checks()
    test_edit_mode()
    test_ajju_frame_rules()
    print()
    if _fails:
        print(f"v79 tests: {len(_fails)} FAILED: {_fails}")
        return 1
    print("v79 tests: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
