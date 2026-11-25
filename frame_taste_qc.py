"""frame_taste_qc.py — Julie v87 role 4: Taste QC.

Compliance and media_qc are meters: they measure the file. Nothing in
the pipeline ever looked at a rendered frame and asked whether it
shows what the plan PROMISED. This module does: for every beat it
extracts one frame from the rendered chapter and puts the plan's own
promise next to it for the vision model —

  "the plan promised X because of line Y — does this frame show X,
   does it fill the frame, is any text clipped or wrong?"

Verdicts: PASS / WARN (shows it, but the frame is under-filled) /
FAIL (does not show it, or text is clipped/wrong) / UNVERIFIED (no
vision route answered — stated honestly, never upgraded to PASS).
FAIL beats go back to the Visual Director for RE-PLANNING (a new
visual decision via director's exclude mechanism), never a bare
re-render of the same plan.

The vision callable is injected: async (images, question) ->
(answer, provider), matching vision.describe_images. Sync frame
extraction via ffmpeg; beats are checked one frame each.
"""

import asyncio
import json
import os
import re
import subprocess

_Q = (
    "You are Julie's frame taste checker. The plan for this beat "
    "promised: {promise}\nBecause of the narration line: \"{line}\"\n"
    "Look at this frame from the rendered video and answer ONLY with "
    "strict JSON: {{\"shows\": true|false, \"fills_frame\": "
    "true|false, \"text_ok\": true|false, "
    "\"source_card_ok\": true|false, \"graphic_ok\": true|false, "
    "\"face_ok\": true|false, \"note\": \"<one short "
    "sentence>\"}}\n"
    "shows = the frame visibly presents the promised visual idea. "
    "fills_frame = the visual occupies the frame properly, not a "
    "small island on an empty background. text_ok = no visible text "
    "is clipped, cut off, garbled or wrong (true when there is no "
    "text to judge). source_card_ok = any research/source card is "
    "legible and shows its source (true when no card is present). "
    "graphic_ok = any chart/diagram is justified by the line and "
    "does not replace the footage (true when no graphic). face_ok = "
    "no graphic or card covers a person's face (true when no face).")


def extract_frame(video, t, out_path):
    """One frame at time t (seconds) -> out_path (jpg). True on success."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0.0, t):.2f}",
             "-i", str(video), "-frames:v", "1", "-q:v", "4",
             str(out_path)], capture_output=True, timeout=60)
        return r.returncode == 0 and os.path.exists(out_path) \
            and os.path.getsize(out_path) > 0
    except Exception:
        return False


def _parse(raw):
    if not raw:
        return None
    m = re.search(r"\{[\s\S]*\}", str(raw))
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def audit_beats(video_path, beats, outdir, vision=None):
    """beats: [{beat, line, promise, why, start, duration}].
    Returns {version, vision: provider|'unavailable', beats: [{beat,
    status, note, frame}], counts}. Never raises."""
    os.makedirs(outdir, exist_ok=True)
    results = []
    provider = None
    for b in beats or []:
        entry = {"beat": b.get("beat"), "status": "UNVERIFIED",
                 "note": "", "frame": ""}
        t = float(b.get("start") or 0) + min(
            1.2, float(b.get("duration") or 3) * 0.5)
        fp = os.path.join(outdir, f"taste_beat_{b.get('beat')}.jpg")
        if not extract_frame(video_path, t, fp):
            entry["note"] = "frame extraction failed"
            results.append(entry)
            continue
        entry["frame"] = fp
        if vision is None:
            entry["note"] = "no vision route available"
            results.append(entry)
            continue
        q = _Q.format(promise=str(b.get("promise") or "")[:300],
                      line=str(b.get("line") or "")[:200])
        try:
            ans, prov = await vision([fp], q)
            provider = prov or provider
        except Exception as e:
            entry["note"] = f"vision failed: {str(e)[:100]}"
            results.append(entry)
            continue
        v = _parse(ans)
        if v is None:
            entry["note"] = "vision reply unparseable"
            results.append(entry)
            continue
        entry["note"] = str(v.get("note") or "")[:200]
        entry["sheet"] = {
            "source_card_ok": v.get("source_card_ok", True),
            "graphic_ok": v.get("graphic_ok", True),
            "face_ok": v.get("face_ok", True),
        }
        if not v.get("shows") or not v.get("text_ok") \
                or not v.get("source_card_ok", True) \
                or not v.get("graphic_ok", True) \
                or not v.get("face_ok", True):
            entry["status"] = "FAIL"
        elif not v.get("fills_frame"):
            entry["status"] = "WARN"
        else:
            entry["status"] = "PASS"
        results.append(entry)
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"version": "v87-frame-taste-qc-1",
            "vision": provider or "unavailable",
            "beats": results, "counts": counts}


def audit_chapter_sync(video_path, beats, outdir, vision=None):
    """Sync wrapper for sync callers (tests, scripts)."""
    return asyncio.run(audit_beats(video_path, beats, outdir, vision))


if __name__ == "__main__":
    rep = audit_chapter_sync("/nonexistent.mp4",
                             [{"beat": 1, "line": "x", "promise": "y",
                               "start": 0, "duration": 3}], "/tmp/tq")
    assert rep["beats"][0]["status"] == "UNVERIFIED", rep
    print("frame_taste_qc self-check OK")
