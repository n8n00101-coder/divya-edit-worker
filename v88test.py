"""v88test.py — unit tests for the v88 picture build (Hark-like:
real footage routes + full-frame aesthetic renderer + honest QC).

Covers: the keyless Commons provider's relevance gate (stubbed API:
a topical file survives, a lecture with a brushing title and a
small-derivative file do not), providers_available() env logic, the
_ff_fill full-frame composition rule (a small centred island grows
to fill the visual band; an already-full visual is untouched), the
media_qc designed-silence distinction (a sanctioned gap reports
DESIGNED, an unsanctioned one still FAILs), and the taste-pack load
(cap raised, full pack, logged). Model/network calls are stubbed —
deterministic.
"""

import os
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


# ---------------------------------------------------------------- broll
import broll

_fake_commons = {
    "query": {"pages": {
        "1": {"pageid": 101, "title": "File:Office workers typing on laptops.webm",
              "videoinfo": [{"duration": 42.0, "descriptionurl": "https://commons.wikimedia.org/wiki/File:Office_workers",
                             "derivatives": [
                                 {"src": "https://upload.wikimedia.org/office_720.webm", "width": 1280, "height": 720},
                                 {"src": "https://upload.wikimedia.org/office_1080.webm", "width": 1920, "height": 1080}]}]},
        "2": {"pageid": 102, "title": "File:August 2024 Future Audiences office hours.webm",
              "videoinfo": [{"duration": 3600.0, "descriptionurl": "https://commons.wikimedia.org/wiki/File:Lecture",
                             "derivatives": [
                                 {"src": "https://upload.wikimedia.org/lec_720.webm", "width": 1280, "height": 720}]}]},
        "3": {"pageid": 103, "title": "File:Office typing closeup.webm",
              "videoinfo": [{"duration": 20.0, "descriptionurl": "https://commons.wikimedia.org/wiki/File:Small",
                             "derivatives": [
                                 {"src": "https://upload.wikimedia.org/small_320.webm", "width": 320, "height": 240}]}]},
    }}}

_orig_get_json = broll._get_json
broll._get_json = lambda url, params=None, headers=None: _fake_commons
try:
    cands = broll._commons_candidates("office workers typing", "landscape")
finally:
    broll._get_json = _orig_get_json
check("commons: topical file survives the title gate",
      len(cands) == 1 and cands[0]["id"] == "commons:101",
      f"got {[c['id'] for c in cands]}")
check("commons: candidate is transcoded + honestly labelled",
      bool(cands) and cands[0].get("transcode") is True
      and cands[0]["provider"] == "commons")
check("commons: lecture (1 shared word) + small file are gated out",
      all(c["id"] not in ("commons:102", "commons:103") for c in cands))

os.environ.pop("PEXELS_KEY", None)
os.environ.pop("PIXABAY_KEY", None)
os.environ.pop("JULIE_COMMONS_FOOTAGE", None)
check("providers_available: nothing configured -> False",
      broll.providers_available() is False)
os.environ["JULIE_COMMONS_FOOTAGE"] = "1"
check("providers_available: keyless Commons on -> True",
      broll.providers_available() is True)
os.environ.pop("JULIE_COMMONS_FOOTAGE", None)

# ---------------------------------------------------------------- _ff_fill
import doc
from PIL import Image, ImageDraw

import compliance as _comp88

doc._FF_ACTIVE = True
lay = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
d = ImageDraw.Draw(lay)
# a clock-sized island, like the v87 beats: ~430px across, centred
d.ellipse([325, 730, 755, 1160], fill=(255, 255, 255, 255))
bb0 = lay.getchannel("A").getbbox()
check("ff_fill: the unfilled visual IS an island (v87 baseline)",
      _comp88.island_metrics(bb0, width=1080, height=1920)[0] is True,
      f"bbox {bb0}")
filled = doc._ff_fill(lay, 480, 1410)
bb = filled.getchannel("A").getbbox()
check("ff_fill: after the fill it is NOT an island (pipeline's own A1)",
      _comp88.island_metrics(bb, width=1080, height=1920)[0] is False,
      f"bbox {bb}")
check("ff_fill: filled content stays inside the band",
      bb[1] >= 470 and bb[3] <= 1420, f"bbox {bb}")

big = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
d2 = ImageDraw.Draw(big)
d2.rectangle([60, 500, 1020, 1390], fill=(255, 255, 255, 255))
bb2 = doc._ff_fill(big, 480, 1410).getchannel("A").getbbox()
check("ff_fill: an already-full visual is left alone",
      bb2 == (60, 500, 1021, 1391), f"bbox {bb2}")
doc._FF_ACTIVE = False

# ---------------------------------------------------------------- media_qc
import media_qc

with tempfile.TemporaryDirectory() as td:
    mp4 = os.path.join(td, "gap.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=navy:s=320x240:d=4",
         "-f", "lavfi", "-i",
         "sine=frequency=440:duration=1,apad,atrim=0:4",
         "-af", "volume=0:enable='between(t,1.2,2.7)'",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", mp4],
        check=True, capture_output=True)
    plain, _ = media_qc.inspect_file(mp4)
    sil_plain = [c for c in plain if c["rule"] == "MQ-SILENCE"]
    check("media_qc: unsanctioned gap FAILs",
          any(c["status"] == "FAIL" for c in sil_plain),
          f"{sil_plain}")
    with_des, _ = media_qc.inspect_file(
        mp4, designed_silences=[(1.2, 2.7)])
    sil_des = [c for c in with_des if c["rule"] == "MQ-SILENCE"]
    check("media_qc: sanctioned gap reports DESIGNED, not FAIL",
          any(c["status"] == "DESIGNED" for c in sil_des)
          and not any(c["status"] == "FAIL" for c in sil_des),
          f"{sil_des}")

# ---------------------------------------------------------------- taste
import brain
import visual_director as VD

pack = VD.taste_pack()
check("taste pack: full pack loads (>15k chars after the merges)",
      len(pack) > 15000, f"{len(pack)} chars")
pb = brain.playbooks()
check("brain.playbooks: pack present in the system prompt in full",
      len(pb) > len(pack), f"playbooks {len(pb)} chars")

print(f"\nv88test: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
