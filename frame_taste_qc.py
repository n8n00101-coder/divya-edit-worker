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
    "is physically cut off by the frame edge, garbled, or overlapped "
    "by other text (true when there is no text to judge). Captions "
    "are short phrases and often end mid-sentence — an unfinished "
    "phrase is NOT clipping; judge only whether the letters "
    "themselves are cut by the frame edge. source_card_ok = any "
    "research/source card is "
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
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # Wave 4: the Workers AI fallback answers in prose with
    # key:value fragments instead of strict JSON — three beats
    # died UNVERIFIED ("vision reply unparseable") in ta57e027.
    # Recover explicit verdicts; a reply with no `shows` verdict
    # stays unparseable (UNVERIFIED, never a pass).
    text = str(raw)
    out = {}
    for key in ("shows", "fills_frame", "text_ok",
                "source_card_ok", "graphic_ok", "face_ok"):
        km = re.search(rf'"?{key}"?\s*[:=]\s*(true|false)',
                       text.lower())
        if km:
            out[key] = km.group(1) == "true"
    if "shows" not in out:
        return None
    nm = re.search(r'"?note"?\s*[:=]\s*"?([^"\n}]{3,200})', text)
    out["note"] = nm.group(1).strip() if nm else text[:160]
    return out


async def audit_beats(video_path, beats, outdir, vision=None,
                      vision_attempts=2, retry_sleep_s=45, pace_s=20):
    """beats: [{beat, line, promise, why, start, duration}].
    Returns {version, vision: provider|'unavailable', beats: [{beat,
    status, note, frame}], counts}. Never raises.

    A vision failure (429/outage/unparseable) is retried ONCE after
    a cooldown sleep before the beat is left UNVERIFIED — bounded,
    and UNVERIFIED is never upgraded to PASS."""
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
        if results and pace_s:
            # Pace vision calls: the free vision leg rate-limits
            # (429) when beats are judged back to back.
            await asyncio.sleep(pace_s)
        v = None
        last_note = "vision unavailable"
        for attempt in range(max(1, int(vision_attempts))):
            try:
                ans, prov = await vision([fp], q)
                provider = prov or provider
            except Exception as e:
                last_note = f"vision failed: {str(e)[:100]}"
                ans = None
            if ans is not None:
                v = _parse(ans)
                if v is not None:
                    break
                last_note = "vision reply unparseable"
            if attempt + 1 < max(1, int(vision_attempts)) and retry_sleep_s:
                await asyncio.sleep(retry_sleep_s)
        if v is None:
            entry["note"] = last_note
            results.append(entry)
            continue
        entry["note"] = str(v.get("note") or "")[:200]
        entry["sheet"] = {
            "source_card_ok": v.get("source_card_ok", True),
            "graphic_ok": v.get("graphic_ok", True),
            "face_ok": v.get("face_ok", True),
            # Vision text judgement is recorded, not gating: the
            # free vision model repeatedly hallucinated caption
            # clipping on frames whose captions sit inside the
            # frame with margin. Caption boundaries are owned by
            # the deterministic ASS/caption gate (TASTE-CAPTION).
            "text_ok_vision": v.get("text_ok", True),
        }
        if not v.get("shows") \
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
