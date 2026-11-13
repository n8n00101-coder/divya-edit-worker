#!/usr/bin/env python3
"""v79.2 tests — the three defects from the frame-level QC of the
first live FIX-7 test-1 render (job 6afb4da0, "30 second video on
sleep, blue colour, no music, Telugu voice") + the topic-fidelity
guard + Ajju's five standing rules from watching test 1
(2026-11-13 17:22-17:23 IST): Romanized captions by default for
Telugu/Hindi, ring discipline, no source lines unless asked,
full-screen effects, music default ON topic-matched:

1. Canned content: a sleep video's document scene rendered a past
   project's gutka-ban notification verbatim. The canned bodies are
   gone from every visual builder (document / receipt / card /
   packet / newspaper / typewriter / scale / timeline / bars /
   stamp CTA / source line), a document scene about sleep composes
   SLEEP content from the scene's own queries/source, and a
   repo-wide assertion fails if any canned string reappears in a
   renderer source.
2. Audit the delivered file: the compliance audit measured the
   pre-trim master (37.2 s FAIL) while the delivered file was
   exactly 30.000 s. refresh_report_for_final_file re-measures the
   final file, and the trim is recorded in fixes_applied.
3. Exclude merge: "no music" produced a music PASS *and* an
   exclude UNVERIFIED. One ask now yields one verdict; genuinely
   uncheckable excludes stay UNVERIFIED.
4. Topic fidelity: a content-bearing visual's composed text must
   overlap the scene's line/topic; on failure one plan-level fix
   round swaps the visual to an abstract one and records the swap;
   a visual that cannot compose from the scene fails honestly.
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

_fails = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {extra}" if extra and not cond else ""), flush=True)
    if not cond:
        _fails.append(name)


# The canned bodies of past projects. If any of these strings ever
# reappears in a renderer source, a visual default has been
# re-armed with somebody else's video text.
BANNED_CANNED = [
    "Sale of gutka and pan masala is prohibited",
    "Ban applies to all states from 2012",
    "Violators face fines and jail",
    "Gutka x30", "Rs 13,800", "1800-11-2356",
    "NATIONAL TOBACCO QUITLINE", "Free counselling in 16 languages",
    "WARNING: TOBACCO KILLS", "PAN MASALA",
    "Study finds men look first",
    "CLASSIFIED: subjects did not notice the swap",
    "Ministry of Health & Family Welfare",
    "NOT TOMORROW", "NOV 11, 2026", "Source: WHO, 2023",
]


def test_no_canned_strings_in_renderer():
    offenders = []
    for f in sorted(HERE.glob("*.py")):
        if f.name == Path(__file__).name:
            continue  # this test carries the list itself
        text = f.read_text(encoding="utf-8", errors="ignore")
        for b in BANNED_CANNED:
            if b in text:
                offenders.append(f"{f.name}: {b!r}")
    ok("canned: no past-topic canned string in any renderer source",
       not offenders, "; ".join(offenders[:4]))


def _sleep_scene():
    # scene 1 of the live test-1 render (project.json): the line is
    # about the brain cleaning itself in sleep; the planner's why
    # asked for "a document showing a brain scan" and got a gutka ban.
    return {"vo": "మీకు తెలుసా, మన మెదడు 90% నిద్రలో శుభ్రం అవుతుంది?",
            "label": "CLEANSE", "mood": "mystery", "visual": "document",
            "value": "", "source": "NIH 2022",
            "why": "The word 'clean' calls for a document showing a brain scan.",
            "queries": ["brain cleaning during sleep MRI",
                        "neuroscience article brain waste removal"],
            "fulfils": ["R3"], "hit_type": "percent",
            "fact_type": "percent", "transition": "", "sfx": "pop",
            "bg_kind": "dark", "d": 5.0}


def test_document_composes_from_scene():
    import compliance as cp
    import visuals_lib as VL

    sc = _sleep_scene()
    args, text = cp.compose_visual(sc, "document", "sleep")
    ok("compose: document composes from the sleep scene", args is not None)
    joined = " ".join(args["lines"]).lower() if args else ""
    ok("compose: document lines are about sleep/brain (the scene's queries)",
       "brain" in joined and "sleep" in joined, joined[:90])
    ok("compose: document carries the scene's own source",
       any("NIH 2022" in ln for ln in args["lines"]))
    ok("compose: no banned canned word in the composed document",
       not any(b.lower() in (text + joined).lower() for b in BANNED_CANNED))
    ok("fidelity: the sleep document passes the topic-fidelity check",
       cp.topic_fidelity(sc, "sleep")[0])
    # the visual renders with the composed args (and with bare
    # defaults it draws a blank report, never the old notification)
    lay = VL.VIS["document"](1.0, 0.0, 2.0, **{k: v for k, v in args.items()
                                               if k in ("title", "lines", "stamp")})
    ok("render: composed document draws a layer", lay.getbbox() is not None)
    bare = VL.VIS["document"](1.0, 0.0, 2.0)
    ok("render: bare document defaults still draw the paper (blank, not canned)",
       bare.getbbox() is not None)
    # other builders survive their bare (content-free) defaults
    for name, kw in (("receipt", {}), ("bracket_bars", {}),
                     ("timeline_cards", {}), ("typewriter_page", {}),
                     ("card", {}), ("speech_bubble", {})):
        try:
            VL.VIS[name](0.5, 0.0, 1.0, **kw)
            ok(f"render: bare {name} defaults do not crash", True)
        except Exception as e:
            ok(f"render: bare {name} defaults do not crash", False, str(e)[:80])


def test_draw_path_uses_scene_composition():
    import doc
    from PIL import Image, ImageDraw
    sc = _sleep_scene()
    sc["words"] = []
    p = {"topic": "sleep", "scenes": [sc]}
    vlay = Image.new("RGBA", (doc.W, doc.H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vlay)
    doc.draw_scene_visual(vd, vlay, p, 0, sc, 1.0, 640, (80, 140, 255))
    cached = (sc.get("_vis_args_cache") or {}).get("document") or {}
    ok("draw path: the document's args were composed from the scene",
       "brain" in " ".join(cached.get("lines") or []).lower(),
       str(cached)[:120])
    ok("draw path: the composed document landed on the frame",
       vlay.getbbox() is not None)


def test_fidelity_guard_and_swap():
    import compliance as cp
    cfg_s = {"kind": "short", "width": 1080}
    base = {"mood": "calm", "value": "", "source": "",
            "why": "shows the line", "transition": "a", "sfx": "pop",
            "bg_kind": "x", "queries": []}

    # a versus scene with no named sides cannot compose -> FAIL,
    # one repair round swaps it to an abstract visual, re-audit clean
    sc = dict(base, vo="give a little, take a little, that is the deal",
              label="THE DEAL", visual="versus")
    checks = cp.audit_plan([sc], cfg_s, topic_text="compromise")
    ok("fidelity: uncomposable versus FAILs the audit",
       any(c["rule"] == "FIDELITY" and c["status"] == "FAIL" for c in checks),
       str(checks)[:200])
    pools = {"visuals": ["counter", "bar", "donut", "graph", "list",
                         "heart", "clock"],
             "transitions": ["cut_a", "wipe_b"],
             "sfx": ["pop", "tick"], "bg_kinds": ["dark", "navy"],
             "pattern_bg": "paper"}
    fixes = cp.repair_plan([sc], cfg_s, pools, checks)
    ok("fidelity: the fix round records the swap",
       any("topic-fidelity swap" in f for f in fixes), str(fixes))
    ok("fidelity: the scene's visual was swapped to the abstract filmstrip",
       sc.get("lib_visual") == "filmstrip")
    checks2 = cp.audit_plan([sc], cfg_s, topic_text="compromise")
    ok("fidelity: after the swap the scene passes",
       not any(c["rule"] == "FIDELITY" and c["status"] == "FAIL"
               for c in checks2))

    # a receipt whose items belong to ANOTHER topic fails on overlap
    sc2 = dict(base, vo="deep sleep repairs your memory and mood",
               label="DEEP SLEEP", visual="receipt",
               items=[("Gutka x30", "Rs 300"), ("Doctor", "Rs 4,000")],
               total="Rs 13,800", queries=["deep sleep memory repair"])
    ok("fidelity: another topic's receipt items fail the overlap check",
       not cp.topic_fidelity(sc2, "sleep")[0])
    # ...while a receipt the line is actually about passes
    sc3 = dict(base, vo="the hospital bill for the tests shocked him",
               label="THE BILL", visual="receipt",
               items=[("Doctor", "Rs 4,000"), ("Tests", "Rs 9,500")],
               total="Rs 13,500", queries=["hospital bill tests cost"])
    ok("fidelity: an on-topic receipt passes",
       cp.topic_fidelity(sc3, "hospital bill")[0])


def test_audit_measures_final_file():
    import compliance as cp
    cfg = {"width": 1080, "height": 1920, "kind": "short",
           "duration_s": 4.0}
    spec = [{"id": "R1", "type": "duration", "value": "4s",
             "quote": "4 seconds"}]
    with tempfile.TemporaryDirectory() as td:
        def make(name, secs):
            path = os.path.join(td, name)
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                 "-i", f"color=c=black:s=1080x1920:d={secs}:r=30",
                 "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}",
                 "-af", "loudnorm=I=-14:TP=-1.0:LRA=11", "-c:v", "libx264",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path],
                check=True)
            return path
        pre = make("pre.mp4", 7)      # the pre-trim master
        final = make("final.mp4", 4)  # the delivered file
        # the report as make_video built it: measured the MASTER
        mchecks, minfo = cp.audit_media(pre, cfg, spec)
        verdicts = cp.requirement_verdicts(spec, cfg, {}, minfo)
        report = cp.build_report(spec, cfg, mchecks, verdicts, 0, [])
        dv = [v for v in report["requirements"] if v["type"] == "duration"][0]
        ok("audit-final: the pre-trim report FAILs duration (the old bug)",
           dv["status"] == "FAIL" and "7.0s" in dv["evidence"], dv["evidence"])
        # the runner trims to target, then refreshes the report
        report2 = cp.refresh_report_for_final_file(
            report, cfg, final,
            extra_fixes=["duration trimmed 7.0s → 4.0s to meet R1"])
        dv2 = [v for v in report2["requirements"]
               if v["type"] == "duration"][0]
        ok("audit-final: the refreshed verdict measures the DELIVERED file",
           dv2["status"] == "PASS" and "4.0s" in dv2["evidence"]
           and "final delivered file" in dv2["evidence"], dv2["evidence"])
        ok("audit-final: the trim is recorded in fixes_applied",
           any("duration trimmed 7.0s" in f and "4.0s" in f
               for f in report2["fixes_applied"]),
           str(report2["fixes_applied"]))
        ok("audit-final: no stale pre-trim duration check remains",
           not any(c["rule"] == "FIX5-DURATION" and c["status"] == "FAIL"
                   for c in report2["checks"]))
        ok("audit-final: the refreshed report passes",
           report2["passed"] is True,
           str([c for c in report2["checks"] if c["status"] == "FAIL"])[:160])


def test_exclude_merge():
    import compliance as cp
    import spec_engine as se

    # unit: the merge itself
    merged = se._merge_excludes(
        [{"type": "exclude", "value": "music", "quote": "no music"}])
    ok("exclude: a lone exclude-of-music becomes the music OFF requirement",
       len(merged) == 1 and merged[0]["type"] == "music"
       and "OFF" in merged[0]["value"], str(merged))
    merged2 = se._merge_excludes(
        [{"type": "music", "value": "music OFF", "quote": "no music"},
         {"type": "exclude", "value": "music", "quote": "no music"}])
    ok("exclude: exclude + typed OFF merge into ONE requirement",
       len(merged2) == 1 and merged2[0]["type"] == "music", str(merged2))
    kept = se._merge_excludes(
        [{"type": "exclude", "value": "no cartoon dogs",
          "quote": "no cartoon dogs"},
         {"type": "exclude", "value": "no zoom", "quote": "no zoom"}])
    ok("exclude: uncheckable / own-check excludes stay excludes",
       len(kept) == 2 and all(k["type"] == "exclude" for k in kept),
       str(kept))

    # end to end: the LLM pass emits the duplicate exclude (as it did
    # on the live job) — the spec must carry ONE music ask.
    def fake_chat(messages):
        return json.dumps([
            {"type": "exclude", "value": "music", "quote": "no music"},
            {"type": "topic", "value": "sleep", "quote": "on sleep"}])

    spec = se.extract_spec(
        "30 second video on sleep, blue colour, no music, Telugu voice",
        chat=fake_chat)
    music_reqs = [r for r in spec if r["type"] == "music"]
    excl_music = [r for r in spec if r["type"] == "exclude"
                  and "music" in r["value"].lower()]
    ok("exclude: the test-1 prompt yields ONE music requirement",
       len(music_reqs) == 1 and not excl_music,
       str([(r["type"], r["value"]) for r in spec]))
    cfg = se.resolve_render_config(spec, "short")
    ok("exclude: the merged spec still switches music OFF",
       cfg["music"] is False)
    verdicts = cp.requirement_verdicts(
        spec, cfg, {"music_applied": False, "lang": "te",
                    "voice_used": cfg.get("voice_id"),
                    "topic": "sleep"},
        {"duration": 30.0, "width": 1080, "height": 1920})
    mv = [v for v in verdicts if v["type"] == "music"]
    ok("exclude: one ask yields one verdict (music PASS, no UNVERIFIED twin)",
       len(mv) == 1 and mv[0]["status"] == "PASS"
       and not any(v["type"] == "exclude" and v["status"] == "UNVERIFIED"
                   for v in verdicts), str(verdicts)[:220])



def _spec_of(prompt):
    """Deterministic-only spec with ids assigned (the LLM pass
    contributes nothing)."""
    import spec_engine as se
    return se.extract_spec(prompt, chat=lambda messages: "[]")

def test_caption_script_rule():
    # Item 5 (Ajju, 2026-11-13): "Telugu captions ivvalsina avasaram
    # ledhu — Romanized Telugu lo ichina ok, English lo kuda ok."
    import compliance as cp
    import spec_engine as se
    import translit

    ok("translit: Telugu words romanize readably",
       translit.transliterate("నిద్ర") == "nidra"
       and translit.transliterate("శుభ్రం") == "shubhram"
       and translit.transliterate("తెలుసా") == "telusaa"
       and translit.transliterate("మెదడు") == "medadu")
    ok("translit: Hindi romanizes too",
       translit.transliterate("नींद") == "neenda")
    ok("translit: Latin words and digits pass through untouched",
       translit.transliterate("90% sleep") == "90% sleep")
    ok("translit: a mixed line keeps its English words and numbers",
       translit.transliterate("మీకు తెలుసా 90%") == "meeku telusaa 90%")

    spec = _spec_of("30 second video on sleep in Telugu")
    cfg = se.resolve_render_config(spec, "short")
    ok("captions: Telugu narration defaults to ROMANIZED captions",
       cfg.get("caption_script") == "roman", str(cfg.get("caption_script")))
    spec2 = _spec_of("video on sleep in Telugu with Telugu script captions")
    cfg2 = se.resolve_render_config(spec2, "short")
    ok("captions: an explicit Telugu-script ask switches to native",
       cfg2.get("caption_script") == "native"
       and cfg2.get("caption_script_explicit") is True,
       str(cfg2.get("caption_script")))
    spec3 = _spec_of("video on sleep in English")
    cfg3 = se.resolve_render_config(spec3, "short")
    ok("captions: English narration stays latin",
       cfg3.get("caption_script") == "latin")

    import doc
    plan = {"lang": "te", "render_config": cfg,
            "scenes": [{"vo": "నిద్ర మంచిది",
                        "words": [(0.0, 0.5, "నిద్ర"), (0.5, 0.6, "మంచిది")],
                        "adur": 1.1}],
            "starts": [0.0]}
    ass = Path(tempfile.mkdtemp()) / "c.ass"
    doc.write_ass(plan, str(ass))
    txt = ass.read_text(encoding="utf-8")
    ok("captions: the roman render burns Romanized text (no Telugu glyphs)",
       "nidra" in txt and "నిద్ర" not in txt, txt[-200:])
    plan2 = dict(plan, render_config=cfg2)
    ass2 = Path(tempfile.mkdtemp()) / "c2.ass"
    doc.write_ass(plan2, str(ass2))
    txt2 = ass2.read_text(encoding="utf-8")
    ok("captions: the native render (explicit ask) burns Telugu script",
       "నిద్ర" in txt2)

    req = [{"id": "r1", "type": "captions",
            "value": "native script captions",
            "quote": "Telugu script captions"}]
    v = cp.requirement_verdicts(req, cfg2, {"caption_script": "native"}, {})
    ok("captions: native ask + native render PASSes",
       bool(v) and v[0]["status"] == "PASS", str(v)[:160])
    v2 = cp.requirement_verdicts(req, cfg, {"caption_script": "roman"}, {})
    ok("captions: native ask + roman render FAILs honestly",
       bool(v2) and v2[0]["status"] == "FAIL", str(v2)[:160])


def test_ring_discipline():
    # Item 6 (Ajju, 2026-11-13): the big round ring over the
    # sleeper's face AGAIN on a plain percent — demoted to a rare
    # special; plain percents default to the counter/bar.
    import compliance as cp

    ok("ring: a plain percent defaults to the counter, not the ring",
       cp.widget_for_number_kind("heart risk drops by 30 percent", "30%")
       == "counter")
    ok("ring: a cycle line may use the ring",
       cp.widget_for_number_kind(
           "one sleep cycle completes 100 percent of its loop", "100%")
       == "donut")
    ok("ring: a share-of-a-whole percent keeps the donut",
       cp.widget_for_number_kind("30 percent of drivers agree", "30%")
       == "donut")
    ok("ring: the plain-percent acceptable set excludes the ring",
       cp.acceptable_widgets_for_number("risk drops 30 percent", "30%")
       == {"counter", "bar"})
    ok("ring: the share-percent acceptable set is the ring family",
       cp.acceptable_widgets_for_number("30 percent of drivers agree", "30%")
       == {"donut", "dot_grid"})

    cfg_s = {"kind": "short", "width": 1080}
    base = {"mood": "calm", "source": "", "why": "shows the line",
            "transition": "a", "sfx": "pop", "bg_kind": "x", "queries": []}

    # a plain-percent scene wearing the ring fails the widget rule
    sc = dict(base, vo="heart risk drops by 30 percent at night",
              label="LOWER RISK", visual="donut", value="30%")
    checks = cp.audit_plan([sc], cfg_s, topic_text="sleep heart health")
    ok("ring: a plain percent on a donut FAILs PART3-WIDGET",
       any(c["rule"] == "PART3-WIDGET" and c["status"] == "FAIL"
           for c in checks), str(checks)[:240])

    # two ring-family visuals in one short break the ring budget
    rings = [dict(base, vo="deep sleep covers 40 percent of the night",
                  label="DEEP SLEEP", visual="donut", value="40%",
                  queries=["deep sleep night"]),
             dict(base, vo="the gauge reads 60 percent by morning",
                  label="BY MORNING", visual="gauge", value="60%",
                  transition="b", sfx="tick", bg_kind="y",
                  queries=["sleep morning"])]
    checks = cp.audit_plan(rings, cfg_s, topic_text="sleep")
    ok("ring: a second ring-family visual FAILs the ring budget",
       any(c["rule"] == "PART3-RING" and c["status"] == "FAIL"
           for c in checks), str(checks)[:240])
    pools = {"visuals": ["counter", "bar", "donut", "graph", "list",
                         "heart", "clock"],
             "transitions": ["cut_a", "wipe_b"],
             "sfx": ["pop", "tick"], "bg_kinds": ["dark", "navy"],
             "pattern_bg": "paper"}
    fixes = cp.repair_plan(rings, cfg_s, pools, checks)
    ok("ring: the repair records the ring-budget swap",
       any("ring-budget swap" in f for f in fixes), str(fixes))
    checks2 = cp.audit_plan(rings, cfg_s, topic_text="sleep")
    ok("ring: after the repair the budget holds (one ring max)",
       not any(c["rule"] == "PART3-RING" and c["status"] == "FAIL"
               for c in checks2), str(checks2)[:240])


def test_sources_gate():
    # Item 7 (Ajju, 2026-11-13): no source lines in the video unless
    # asked; sources are metadata only.
    import compliance as cp
    import spec_engine as se

    spec = _spec_of("video on sleep, show sources")
    cfg = se.resolve_render_config(spec, "short")
    ok("sources: an explicit ask switches show_sources ON",
       cfg.get("show_sources") is True)
    spec2 = _spec_of("video on sleep")
    cfg2 = se.resolve_render_config(spec2, "short")
    ok("sources: by default sources are NOT drawn (metadata only)",
       cfg2.get("show_sources") is False)
    req = [{"id": "r1", "type": "sources", "value": "show sources",
            "quote": "show sources"}]
    v = cp.requirement_verdicts(req, cfg, {"sources_shown": True}, {})
    ok("sources: asked + drawn PASSes",
       bool(v) and v[0]["status"] == "PASS", str(v)[:160])
    v2 = cp.requirement_verdicts(req, cfg, {"sources_shown": False}, {})
    ok("sources: asked + not drawn FAILs honestly",
       bool(v2) and v2[0]["status"] == "FAIL", str(v2)[:160])

    # render level: the source line's bbox exists only when allowed
    import doc
    plan_json = {
        "title": "SLEEP", "lang": "en",
        "scenes": [
            {"vo": "Deep sleep cleans the brain at night.",
             "label": "BRAIN CLEANSE", "mood": "mystery",
             "visual": "document", "value": "", "source": "NIH 2022",
             "why": "document shows the finding",
             "queries": ["brain cleaning sleep"], "fulfils": []},
            {"vo": "Your body repairs itself while you rest.",
             "label": "BODY REPAIR", "mood": "calm",
             "visual": "heart", "value": "", "source": "",
             "why": "heart for the repair line",
             "queries": ["body repair sleep"], "fulfils": []},
            {"vo": "Dreams sort the memories of the day.",
             "label": "DREAM WORK", "mood": "mystery",
             "visual": "brain", "value": "", "source": "",
             "why": "brain for the memory line",
             "queries": ["brain dreams memory"], "fulfils": []},
            {"vo": "So guard your sleep every single night.",
             "label": "GUARD SLEEP", "mood": "hopeful",
             "visual": "question", "value": "", "source": "",
             "why": "question for the closing choice",
             "queries": ["sleeping peacefully"], "fulfils": []},
        ],
    }

    def fake_chat(messages):
        return json.dumps(plan_json)

    p_off = doc.plan("video on sleep", fake_chat)
    p_on = doc.plan("video on sleep", fake_chat, cfg={"show_sources": True})
    for pl in (p_off, p_on):
        for s in pl["scenes"]:
            s.setdefault("d", 5.0)
            s.setdefault("words", [(0.1, 0.3, w)
                                   for w in s["vo"].split()[:4]])
    sb_off = doc.scene_frame(p_off, 0, 1.0, return_layers=True)[4]
    sb_on = doc.scene_frame(p_on, 0, 1.0, return_layers=True)[4]
    ok("sources: without the ask, no source line is drawn",
       sb_off is None, str(sb_off))
    ok("sources: with the ask, the source line is drawn",
       sb_on is not None, str(sb_on))


def test_fullscreen_island():
    # Item 8 (Ajju, 2026-11-13): "screen motham kuda effects use
    # cheyamani chepu" — a main visual must use the full frame.
    import compliance as cp

    m = cp.island_metrics((340, 900, 740, 1150))
    ok("island: a small centred visual is flagged as an island",
       bool(m) and m[0] is True, str(m))
    m2 = cp.island_metrics((40, 500, 1040, 1390))
    ok("island: a near-full-frame visual is not flagged",
       bool(m2) and m2[0] is False, str(m2))
    ok("island: no bbox cannot be judged (None, not a pass)",
       cp.island_metrics(None) is None)
    checks = cp.audit_central_island(
        [(1, (340, 900, 740, 1150), False),
         (2, (40, 500, 1040, 1390), False),
         (3, None, False),
         (4, (340, 900, 740, 1150), True)])
    ok("island: the audit FAILs the island scene only (footage skipped)",
       [c["scene"] for c in checks if c["status"] == "FAIL"] == [1],
       str(checks))
    ok("island: an unjudgeable frame reports UNVERIFIED, never PASS",
       any(c["scene"] == 3 and c["status"] == "UNVERIFIED" for c in checks))

    # the render-side enlarge round: the band fit grows a scaled-up
    # composition instead of only ever shrinking it
    import doc
    from PIL import Image, ImageDraw
    lay = Image.new("RGBA", (doc.W, doc.H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rectangle([440, 900, 640, 1100], fill=(255, 0, 0, 255))
    out = doc._fit_above_label(lay, 1.3)
    b0, b1 = lay.getbbox(), out.getbbox()
    ok("island: the enlarge round grows the composition",
       (b1[2] - b1[0]) > (b0[2] - b0[0]), f"{b0} -> {b1}")


def test_music_default():
    # Item 9 (Ajju, 2026-11-13): "topic ki thagga background music
    # kuda undali" — music defaults ON when the prompt is silent.
    import compliance as cp

    ok("music: silent prompt + no track FAILs MUSIC-DEFAULT",
       any(c["rule"] == "MUSIC-DEFAULT" and c["status"] == "FAIL"
           for c in cp.audit_music_default([], {}, {"music_applied": False})))
    ok("music: silent prompt + track applied is clean",
       cp.audit_music_default([], {}, {"music_applied": True}) == [])
    ok("music: an explicit music ask defers to its own verdict",
       cp.audit_music_default([{"type": "music", "value": "music OFF"}],
                              {}, {"music_applied": False}) == [])

    import wave
    import numpy as np
    import doc
    td = Path(tempfile.mkdtemp())
    tone = (td / "tone.wav")
    w = wave.open(str(tone), "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(doc.SR)
    t = np.arange(doc.SR) / doc.SR
    w.writeframes((np.sin(2 * np.pi * 220 * t) * 12000).astype(np.int16).tobytes())
    w.close()
    sil = (td / "sil.wav")
    w = wave.open(str(sil), "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(doc.SR)
    w.writeframes(np.zeros(doc.SR, dtype=np.int16).tobytes())
    w.close()
    ok("music: _wav_rms hears a tone and hears silence",
       doc._wav_rms(str(tone)) > 0.1 and doc._wav_rms(str(sil)) < 0.005,
       f"{doc._wav_rms(str(tone)):.3f} / {doc._wav_rms(str(sil)):.4f}")


def main():
    test_no_canned_strings_in_renderer()
    test_document_composes_from_scene()
    test_draw_path_uses_scene_composition()
    test_fidelity_guard_and_swap()
    test_audit_measures_final_file()
    test_exclude_merge()
    test_caption_script_rule()
    test_ring_discipline()
    test_sources_gate()
    test_fullscreen_island()
    test_music_default()
    print()
    if _fails:
        print(f"v79.2 tests: {len(_fails)} FAILED: {_fails}")
        return 1
    print("v79.2 tests: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
