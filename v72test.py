"""v72 tests: mid-flight amendments — the mapping is PURE, the
checkpoint consumption is HONEST.

1. doc.classify_amendment — Ajju's exact live message maps to B-roll
   on + SFX on + transitions change + a style note; negations map to
   off; a bare content point maps to content only.
2. doc._AmendBox + doc._amend_checkpoint with a fake provider + fake
   plan: an amendment present before assembly is consumed AT the
   assembly checkpoint (transitions really re-picked, captions flag
   set); footage/audio checkpoints consume theirs; a multi-effect
   amendment is marked only when its last effect lands.
3. An amendment that arrives AFTER the final checkpoint is reported
   missed — not applied, not marked.
4. Content at the script checkpoint folds into the narration (stub
   chat writes the line); content at assembly stays missed.
5. long_video._fold_chapter_amendments: a content amendment folds
   into the NEXT chapter's brief and is marked for that chapter;
   toggles are left for the chapter's own checkpoints.
6. runner.Amendments (extracted from source — runner.py runs main()
   at import) against a stubbed httpx: fetch/pending/mark semantics.
7. runner.parse_requested_seconds: "5 mints" (Ajju's spelling) = 300.

No network, no TTS, no render. Run: python v72test.py
"""

import inspect
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import doc
import long_video

fails = []


def ok(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- 1. pure
fx = doc.classify_amendment(
    "Real footage kuda include cheyu, and sfx use cheyu, animations "
    "transitions, anni use cheyu, ok na")
ok("classify Ajju: broll on", fx.get("broll") == "on")
ok("classify Ajju: sfx on", fx.get("sfx") == "on")
ok("classify Ajju: transitions change", fx.get("transitions") == "change")
ok("classify Ajju: style note kept", bool(fx.get("style_note")))
ok("classify Ajju: no phantom content", "content" not in fx)
ok("classify: music vaddu -> off",
   doc.classify_amendment("music vaddu, voice matrame") .get("music") == "off")
ok("classify: sfx off -> off",
   doc.classify_amendment("sfx off cheyu").get("sfx") == "off")
ok("classify: no footage -> broll off",
   doc.classify_amendment("no footage, animations use cheyu").get("broll") == "off")
ok("classify: captions off -> off",
   doc.classify_amendment("captions off cheyu").get("captions") == "off")
ok("classify: transitions vaddu -> off",
   doc.classify_amendment("transitions vaddu, simple ga pettu").get("transitions") == "off")
ok("classify: bare point -> content only",
   doc.classify_amendment("add a point about road safety") == {"content": "add a point about road safety"})
ok("classify: sound effects on",
   doc.classify_amendment("sound effects use cheyu").get("sfx") == "on")


# ---------------------------------------------------------------- 2. box
class FakeProvider:
    def __init__(self, items=()):
        self.items = [dict(id=i + 1, text=t, at=0, stage=None)
                      for i, t in enumerate(items)]
        self.marks = []

    def pending(self):
        return [it for it in self.items if not it["stage"]]

    def mark(self, ids, stage):
        for it in self.items:
            if it["id"] in ids and not it["stage"]:
                it["stage"] = stage
        self.marks.append((list(ids), stage))

    def add(self, text):
        self.items.append(dict(id=len(self.items) + 1, text=text,
                               at=0, stage=None))


def fake_plan():
    return {"title": "Test Title", "look": "A", "seed": 3,
            "lang": "en",
            "scenes": [{"vo": "First point.", "visual": "chart", "mood": "calm"},
                       {"vo": "Second point.", "visual": "icons", "mood": "calm"},
                       {"vo": "Follow us.", "visual": "stamp_cta", "mood": "calm"}],
            "transitions": ["placeholder_old_1", "placeholder_old_2"],
            "transition_families": ["placeholder", "placeholder"]}


# -- footage + audio checkpoints consume theirs; assembly waits.
pv = FakeProvider(["real footage include cheyu, sfx use cheyu, music vaddu"])
box = doc._AmendBox(pv)
p = fake_plan()
f = doc._amend_checkpoint(box, p, "script")
ok("cp script: toggles untouched", f == {} and pv.marks == [])
f = doc._amend_checkpoint(box, p, "footage")
ok("cp footage: broll flag on", f.get("broll") == "on")
ok("cp footage: item not fully marked yet", pv.marks == [])
f = doc._amend_checkpoint(box, p, "audio")
ok("cp audio: sfx on + music off", f.get("sfx") == "on" and f.get("music") == "off")
ok("cp audio: fully consumed -> marked audio",
   pv.marks == [([1], "audio")] and pv.items[0]["stage"] == "audio")
ok("cp: applied record carries desc",
   len(box.applied) == 1 and "B-roll" in box.applied[0]["desc"]
   and "Music off" in box.applied[0]["desc"])
ok("cp: nothing missed", box.missed() == [])

# -- assembly checkpoint: transitions re-picked, captions flag set.
pv = FakeProvider(["transitions marchu, captions off cheyu"])
box = doc._AmendBox(pv)
p = fake_plan()
for st in ("script", "footage", "audio"):
    f = doc._amend_checkpoint(box, p, st)
    ok(f"cp {st}: assembly item untouched", f == {} and pv.marks == [])
f = doc._amend_checkpoint(box, p, "assembly")
ok("cp assembly: captions flag off", f.get("captions") == "off")
ok("cp assembly: transitions really re-picked",
   len(p["transitions"]) == 2
   and all(t not in ("placeholder_old_1", "placeholder_old_2")
           for t in p["transitions"])
   and p["scenes"][1]["transition"] == p["transitions"][0])
ok("cp assembly: marked at assembly", pv.items[0]["stage"] == "assembly")

# -- transitions off -> plain crossfade cuts.
pv = FakeProvider(["transitions vaddu"])
box = doc._AmendBox(pv)
p = fake_plan()
doc._amend_checkpoint(box, p, "assembly")
ok("cp assembly: transitions off = crossfade cuts",
   p["transitions"] == ["crossfade", "crossfade"])

# -- broll off at the footage checkpoint.
pv = FakeProvider(["footage vaddu, drawn backgrounds chaalu"])
box = doc._AmendBox(pv)
f = doc._amend_checkpoint(box, fake_plan(), "footage")
ok("cp footage: broll flag off", f.get("broll") == "off")


# ---------------------------------------------------------------- 3. late
pv = FakeProvider()
box = doc._AmendBox(pv)
p = fake_plan()
for st in ("script", "footage", "audio", "assembly"):
    doc._amend_checkpoint(box, p, st, chat=lambda msgs: "A woven line.")
pv.add("add a point about helmets")
box.finish()
ok("late: post-checkpoint amendment reported missed",
   box.missed() == ["add a point about helmets"] and box.applied == [])
ok("late: never marked", pv.items[0]["stage"] is None)


# ---------------------------------------------------------------- 4. fold
pv = FakeProvider(["add a point about helmets"])
box = doc._AmendBox(pv)
p = fake_plan()
doc._amend_checkpoint(box, p, "script",
                      chat=lambda msgs: "Helmets save lives every day.")
ok("fold: content line woven into the last non-CTA scene",
   p["scenes"][1]["vo"] == "Second point. Helmets save lives every day.")
ok("fold: CTA scene untouched", p["scenes"][2]["vo"] == "Follow us.")
ok("fold: marked at script", pv.items[0]["stage"] == "script")

pv = FakeProvider(["add a point about helmets"])
box = doc._AmendBox(pv)
p = fake_plan()
for st in ("footage", "audio", "assembly"):
    doc._amend_checkpoint(box, p, st, chat=lambda msgs: "Too late line.")
ok("fold: content at assembly stays missed (no fake fold)",
   box.missed() == ["add a point about helmets"]
   and all("Too late" not in s["vo"] for s in p["scenes"]))


# ---------------------------------------------------------------- 5. long
pv = FakeProvider(["add a point about helmets", "sfx use cheyu"])
brief = long_video._fold_chapter_amendments(pv, "Chapter brief.", 2)
ok("long fold: content lands in the chapter brief",
   "Viewer-requested additions" in brief and "helmets" in brief)
ok("long fold: content marked for chapter 2",
   pv.items[0]["stage"] == "chapter 2")
ok("long fold: toggle left pending for doc checkpoints",
   pv.items[1]["stage"] is None)


# ---------------------------------------------------------------- 6. runner
src = (HERE / "runner.py").read_text(encoding="utf-8")
body = src.split("class Amendments:", 1)[1].split("\nasync def create_job", 1)[0]


class _Resp:
    def __init__(self, code, payload=None):
        self.status_code = code
        self._p = payload or {}

    def json(self):
        return self._p


class FakeHttpx:
    def __init__(self):
        self.items = [{"id": 1, "text": "sfx use cheyu", "at": 0, "stage": None}]
        self.posts = []

    def get(self, url, params=None, headers=None, timeout=None):
        assert url.endswith("/api/runner/amendments"), url
        assert params == {"job": "JOBX"} and headers.get("x-runner-key") == "rk"
        return _Resp(200, {"amendments": [dict(it) for it in self.items]})

    def post(self, url, params=None, json=None, headers=None, timeout=None):
        self.posts.append(json)
        for it in self.items:
            if it["id"] in json["ids"] and not it["stage"]:
                it["stage"] = json["stage"]
        return _Resp(200, {})


fh = FakeHttpx()
ns = {"httpx": fh, "WORKER": "https://w.example", "KEY": "rk", "JOB": "JOBX"}
exec("class Amendments:" + body, ns)
am = ns["Amendments"]()
ok("runner provider: pending lists unmarked", [i["id"] for i in am.pending()] == [1])
am.mark([1], "audio")
ok("runner provider: mark posts ids+stage", fh.posts == [{"ids": [1], "stage": "audio"}])
ok("runner provider: nothing pending after mark", am.pending() == [])
ok("runner provider: fetch shows the stage", am.fetch()[0]["stage"] == "audio")


# ---------------------------------------------------------------- 7. route
def _load_parse_fn():
    body = src.split("def parse_requested_seconds", 1)[1]
    body = body.split("\nasync def create_job", 1)[0]
    ns2 = {"re": re}
    exec("def parse_requested_seconds" + body, ns2)
    return ns2["parse_requested_seconds"]


parse = _load_parse_fn()
ok("route: '5 mints' = 300 s", parse("topic x, 5 mints") == 300)
ok("route: '5 minutes' = 300 s", parse("topic x, 5 minutes") == 300)
ok("route: bare short stays None", parse("topic x, short 30s 9:16") is None)

# signatures: the engines accept amendments; doc3-style gate intact.
ok("sig: doc.make_video takes amendments",
   "amendments" in inspect.signature(doc.make_video).parameters)
ok("sig: doc advertises AMENDMENTS", getattr(doc, "AMENDMENTS", False) is True)
ok("sig: long pipeline takes amendments",
   "amendments" in inspect.signature(long_video.make_long_video).parameters
   and "amendments" in inspect.signature(long_video.render_chapters).parameters)
ok("sig: _attach_broll takes all_scenes",
   "all_scenes" in inspect.signature(doc._attach_broll).parameters)

print()
if fails:
    print(f"v72test: {len(fails)} FAILED: {fails}")
    sys.exit(1)
print("v72test: ALL PASS")
