"""v87test.py — unit tests for the Editing Brain (v87).

Covers: taste pack integrity, Story Analyst schema + degradation,
Visual Director choice parsing, the veto gates around LLM choices
(an LLM choice that repeats the previous beat is rejected and the
deterministic candidate wins), Taste-QC exclusion re-planning (the
failed template cannot come back), the applied Editing Director pass
(diff log integrity, sanctioned silences only, transition authority),
analyst-validated arc roles, executed music dynamics (the per-beat
intensity curve changes the rendered loudness contour), and the
brain.py taste wiring. All model calls are stubs — deterministic.
"""

import asyncio
import copy
import json
import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------- taste
import visual_director as VD

pack = VD.taste_pack()
check("taste pack loads in full (v88: bound follows the merged pack — "
      "Premiere-course + pro-editor rules took it to ~17.8k chars)",
      15000 <= len(pack) <= 60000,
      f"{len(pack)} chars")
check("taste pack carries the core laws",
      all(w in pack for w in ("Blind R2", "LRA", "sanctioned",
                              "UNVERIFIED", "re-PLANNED")))

# ---------------------------------------------------------------- analyst
import story_analyst as SA

SCENES = [
    {"vo": "Someone asks for one small favour, and the word yes is "
           "already out of your mouth.", "label": "THE REFLEX"},
    {"vo": "Psychologists call this the compliance reflex, and it "
           "costs you your evenings.", "label": "THE NAME"},
    {"vo": "Then one evening you say it like this: I can't take this "
           "on, and the world does not end.", "label": "THE TURN"},
]


def analyst_stub(messages):
    return json.dumps({"scenes": [
        {"emotion": "tense", "subject": "the automatic yes",
         "turning_point": False, "emphasis": ["yes"],
         "visual_opportunity": "scene"},
        {"emotion": "dry", "subject": "the compliance reflex",
         "turning_point": False, "emphasis": ["compliance reflex"],
         "visual_opportunity": "document"},
        {"emotion": "relief", "subject": "the first honest no",
         "turning_point": True, "emphasis": ["can't"],
         "visual_opportunity": "quote"}]})


sheet = SA.analyse_script(SCENES, analyst_stub, taste=pack, topic="yes")
check("analyst: sheet schema", bool(sheet) and len(sheet["scenes"]) == 3)
check("analyst: turning point read from the script",
      sheet and sheet["turning_points"] == [3])
check("analyst: bad JSON degrades to None (no fake sheet)",
      SA.analyse_script(SCENES, lambda m: "no json here") is None)
check("analyst: markdown renders",
      "TURNING POINT" in SA.beat_sheet_markdown(sheet))

# ---------------------------------------------------------------- VD parse
menus = [{"beat": 1, "line": "Psychologists call this the compliance "
          "reflex.", "role": "evidence",
          "analyst": {"emotion": "dry", "visual_opportunity": "document"},
          "candidates": [{"template": "primary", "asset_type": "g",
                          "why": ""},
                         {"template": "evidence_document",
                          "asset_type": "d", "why": ""}]}]
got = VD.choose_visuals(menus, lambda m: json.dumps({"choices": [
    {"beat": 1, "template": "evidence_document",
     "why": "psychologists' claim as the document it is"}]}))
check("visual director: choice parsed + validated against the menu",
      got.get(1, {}).get("template") == "evidence_document")
got = VD.choose_visuals(menus, lambda m: json.dumps({"choices": [
    {"beat": 1, "template": "not_on_the_menu", "why": "x"}]}))
check("visual director: off-menu choice dropped", got == {})
got = VD.choose_visuals(menus, lambda m: json.dumps({"choices": [
    {"beat": 1, "template": "evidence_document [document visual]",
     "why": "the menu display form, copied verbatim (live 2026-11-15)"}]}))
check("visual director: bracket-suffixed menu echo normalised",
      got.get(1, {}).get("template") == "evidence_document")

# ------------------------------------------------- directing with a brain
import director as D

PLAN = {"topic": "psychology of saying yes", "look": "A", "seed": 7,
        "scenes": [
            {"vo": s["vo"], "label": s["label"], "mood": "tense",
             "visual": "chat", "value": "", "why": "writer",
             "queries": ["people talking"]} for s in SCENES]}


def brain_chat_factory(vd_template):
    def chat(messages):
        user = messages[-1]["content"]
        if "Story Analyst" in messages[0]["content"] or \
                "beat sheet" in user[:2000].lower() and "SCRIPT:" in user:
            return analyst_stub(messages)
        if "Visual Director" in messages[0]["content"]:
            rows = []
            for part in user.split("Beat ")[1:]:
                n = int(part.split(" ")[0])
                rows.append({"beat": n, "template": vd_template,
                             "why": "the line itself, shown plainly"})
            return json.dumps({"choices": rows})
        if "Editing Director" in messages[0]["content"]:
            return json.dumps({"adjustments": []})
        return analyst_stub(messages)
    return chat


brain = {"chat": brain_chat_factory("typewriter_dev"), "taste": pack,
         "beat_sheet": sheet}
directed, records = D.direct_plan(copy.deepcopy(PLAN),
                                  brief="chapter 1 of 1", brain=brain)
check("directing: beats produced", len(directed["scenes"]) >= 5,
      f"{len(directed['scenes'])} beats")
check("directing: analyst rode onto beats",
      any(b.get("analyst") for b in directed["scenes"]))
check("directing: turning-point role from the analyst",
      any(b.get("arc_role") == "turning_point"
          for b in directed["scenes"]))
effs = []
import compliance as COMP
for b in directed["scenes"]:
    effs.append(COMP.effective_visual(b))
check("directing: no back-to-back effective visual repeat",
      all(effs[i] != effs[i - 1] for i in range(1, len(effs))),
      str(effs))

# the veto: VD demands the SAME template for every beat — repetition
# gates must refuse it after the first use and fall back.
brain2 = {"chat": brain_chat_factory("typewriter_dev"), "taste": pack,
          "beat_sheet": sheet}
d2, r2 = D.direct_plan(copy.deepcopy(PLAN), brief="chapter 1 of 1",
                       brain=brain2)
tpls = [b["dir"]["template"] for b in d2["scenes"]]
check("veto: LLM may not repeat one template back-to-back",
      all(tpls[i] != tpls[i - 1] or tpls[i] == "primary_fallback"
          for i in range(1, len(tpls))), str(tpls))

# exclusion re-plan: exclude the winning template of beat 1 — the
# re-plan must choose something else for that beat.
first_tpl = records[0]["visual_concept"]
brain3 = {"chat": brain["chat"], "taste": pack, "beat_sheet": sheet,
          "exclude": {1: [first_tpl]}}
d3, r3 = D.direct_plan(copy.deepcopy(PLAN), brief="chapter 1 of 1",
                       brain=brain3)
check("re-plan: excluded template cannot return on its beat",
      r3[0]["visual_concept"] != first_tpl,
      f"{first_tpl} -> {r3[0]['visual_concept']}")

# ------------------------------------------------------- editing director
diffs = directed.get("editing_director_diff")
check("editing director: diff log present on the plan",
      isinstance(diffs, list))
sil = [b for b in directed["scenes"] if b.get("silence_after_s")]
check("editing director: silences only at sanctioned spots "
      "(after turning point / before payoff / before ending)",
      all(0.8 <= float(b["silence_after_s"]) <= 1.5 for b in sil) and
      len(sil) <= 3, f"{len(sil)} silence(s)")
roles = [b.get("arc_role") for b in directed["scenes"]]
if "turning_point" in roles:
    tp_last = max(i for i, r in enumerate(roles) if r == "turning_point")
    check("editing director: silence lands after the turning point",
          bool(directed["scenes"][tp_last].get("silence_after_s")))
same_parent = [i for i in range(1, len(directed["scenes"]))
               if directed["scenes"][i].get("parent_label")
               and directed["scenes"][i].get("parent_label")
               == directed["scenes"][i - 1].get("parent_label")]
check("editing director: same-idea boundaries are hard cuts",
      all(not directed["scenes"][i].get("transition")
          for i in same_parent), f"{len(same_parent)} internal cuts")
check("editing director: music intensity on every beat",
      all(isinstance(b.get("music_intensity"), (int, float))
          for b in directed["scenes"]))

# analyse_plan stays pure (the v84 contract is untouched)
probe = [{"no": 1, "visual": "clock", "vo": "Time passes.", "d": 4}]
before = copy.deepcopy(probe)
D.analyse_plan(probe)
check("v84 analyse_plan still log-only/pure", probe == before)

# ------------------------------------------------------------- arc roles
import doc_structure as DS

roles, notes = DS.validate_arc_with_analyst(
    ["hook", "context", "conclusion"],
    [None, {"turning_points": [2]}, None])
check("arc: analyst turning point promotes the chapter role",
      roles[1] == "turning_points" and bool(notes), str(roles))
roles2, _ = DS.validate_arc_with_analyst(["hook", "conclusion"],
                                         [None, None])
check("arc: no sheet -> roles unchanged", roles2 == ["hook", "conclusion"])

# ------------------------------------------------------- taste QC module
import frame_taste_qc as TQ


async def _fake_vision_fail(images, q):
    return (json.dumps({"shows": False, "fills_frame": False,
                        "text_ok": True, "note": "shows a blank card"}),
            "stub")


async def _fake_vision_pass(images, q):
    return (json.dumps({"shows": True, "fills_frame": True,
                        "text_ok": True, "note": "matches"}), "stub")


import subprocess
import tempfile
tmp = tempfile.mkdtemp()
vid = os.path.join(tmp, "t.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                "-i", "color=c=navy:s=270x480:d=4", "-pix_fmt", "yuv420p",
                vid], check=True)
beats = [{"beat": 1, "line": "line one", "promise": "a scale",
          "why": "", "start": 0.0, "duration": 4.0}]
rep = asyncio.run(TQ.audit_beats(vid, beats, tmp, vision=_fake_vision_fail))
check("taste QC: vision FAIL is a FAIL (never upgraded)",
      rep["beats"][0]["status"] == "FAIL")
rep = asyncio.run(TQ.audit_beats(vid, beats, tmp, vision=_fake_vision_pass))
check("taste QC: matching frame passes",
      rep["beats"][0]["status"] == "PASS")
rep = asyncio.run(TQ.audit_beats(vid, beats, tmp, vision=None))
check("taste QC: no vision -> UNVERIFIED (honest)",
      rep["beats"][0]["status"] == "UNVERIFIED")

# ---------------------------------------------------- music curve executes
import numpy as np
import doc as DOC


def _seg_rms(path, t0, t1, sr):
    w = wave.open(path)
    w.rewind()
    w.readframes(int(t0 * sr))
    data = np.frombuffer(w.readframes(int((t1 - t0) * sr)), dtype=np.int16)
    w.close()
    return float(np.sqrt(np.mean(data.astype(np.float64) ** 2))) if len(data) else 0.0


mp3 = os.path.join(tmp, "m.wav")
starts = [0.4, 3.4, 6.4]
DOC.music(9.4, starts, ["calm", "calm", "calm"], mp3,
          intensity=[0.2, 0.95, 0.2])
sr = DOC.SR
quiet = _seg_rms(mp3, 0.6, 3.2, sr)
loud = _seg_rms(mp3, 3.6, 6.2, sr)
check("music: per-beat intensity curve is EXECUTED (loud beat >> quiet)",
      loud > quiet * 1.5, f"quiet {quiet:.0f} vs loud {loud:.0f}")
mp4 = os.path.join(tmp, "m2.wav")
DOC.music(9.4, starts, ["calm", "calm", "calm"], mp4,
          silences=[(3.4, 1.0)])
sil_rms = _seg_rms(mp4, 3.6, 4.2, sr)
norm_rms = _seg_rms(mp4, 0.6, 3.2, sr)
check("music: sanctioned silence window is actually silent",
      sil_rms < norm_rms * 0.05, f"sil {sil_rms:.1f} vs {norm_rms:.0f}")

# ------------------------------------------------------------- brain wiring
import brain as BRAIN

pb = BRAIN.playbooks()
check("brain.py: shorts path reads the taste pack in full",
      "TASTE PACK" in pb and len(pb) > 6000)

print(f"\nv87test: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
print("v87test: ALL PASS")
