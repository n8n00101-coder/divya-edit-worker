"""Julie edits on her own, end to end:
  plan_edit  -> looks at sampled frames (vision) + transcript (local whisper if installed) and asks the LLM,
                with the editing playbook as context, for a JSON plan of real editor.py / pro.py ops
  run_plan   -> executes the plan step by step
  auto_edit  -> plan -> run -> review_render (vision QA) -> one retry with the issues fed back if needed."""
import asyncio
import json
import os

import editor
import pro
import providers
import vision

PLAYBOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills", "editing_playbook.md")

# op -> (module, allowed params). Only functions that really exist in editor.py / pro.py.
_SPEC = {
    "trim": (editor, {"start", "end"}),
    "vertical": (editor, set()),
    "remove_silence": (editor, set()),
    "speed": (editor, {"factor"}),
    "zoom": (editor, {"factor"}),
    "color": (editor, {"preset"}),
    "text": (editor, {"text", "position", "start", "end"}),
    "captions": (editor, {"lang"}),
    "music": (editor, {"volume"}),
    "mute": (editor, set()),
    "compress": (editor, {"target_mb"}),
    "punch_ins": (pro, {"every", "factor"}),
    "sharpen": (pro, set()),
    "clean_audio": (pro, set()),
    "animated_captions": (pro, {"lang", "style", "words_per_line", "position"}),
    "music_ducked": (pro, {"volume"}),
}
OPS = {op: (mod, params) for op, (mod, params) in _SPEC.items() if callable(getattr(mod, op, None))}
NEEDS_MUSIC = {"music", "music_ducked"}

OP_DOC = """Allowed ops (applied in order to the current video):
- {"op":"trim","start":"00:00:02","end":"00:00:30"}
- {"op":"remove_silence"}                       jump-cut silent gaps
- {"op":"vertical"}                             centre-crop to 1080x1920
- {"op":"punch_ins","every":4,"factor":1.12}    alternate zoom framing every N s
- {"op":"zoom","factor":1.1}                    slow push-in over the whole clip
- {"op":"speed","factor":1.1}
- {"op":"color","preset":"warm|cool|bw|vivid"}
- {"op":"sharpen"}                              light sharpen + contrast/saturation
- {"op":"clean_audio"}                          denoise, voice EQ, -14 LUFS
- {"op":"music_ducked","volume":0.35}           needs a music file; ducks under speech
- {"op":"music","volume":0.25}                  needs a music file; no ducking
- {"op":"animated_captions","lang":"te|en|hi","style":"bold|neon|green|minimal","words_per_line":3,"position":"lower|middle"}
- {"op":"captions","lang":"te"}                 plain subtitles (prefer animated_captions)
- {"op":"text","text":"HOOK TEXT","position":"top|center|bottom","start":0,"end":2.5}
- {"op":"mute"}
- {"op":"compress","target_mb":15}"""

PLANNER = """You are Julie, a top Shorts/Reels editor. Plan an edit for the owner's video using ONLY the ops below.
Follow the playbook: hook in the first 1-2 s, no dead air, 9:16 for Shorts/Reels, clean audio at -14 LUFS,
readable captions in safe zones, don't over-edit. Order matters: cut/trim first, then framing (vertical,
punch_ins/zoom), then colour/sharpen, then audio, then captions/text LAST (so text is not cropped or zoomed).
Use music ops only if has_music is true. Never use an op that is not listed.

{ops}

Reply ONLY JSON: {{"summary":"one line in romanized Telugu + English","steps":[{{"op":"...", ...}}]}}

PLAYBOOK (excerpt):
{playbook}"""


def _playbook(limit=6000):
    try:
        return open(PLAYBOOK, encoding="utf-8").read()[:limit]
    except OSError:
        return ""


def parse_plan(text: str, has_music: bool = False) -> dict:
    """LLM reply -> validated plan. Unknown ops and unknown params are dropped, never executed."""
    raw = vision.parse_json(text)
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else raw.get("actions", [])
    clean, dropped = [], []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        op = s.get("op")
        if op not in OPS or (op in NEEDS_MUSIC and not has_music):
            dropped.append(str(op))
            continue
        allowed = OPS[op][1]
        clean.append({"op": op, **{k: v for k, v in s.items() if k in allowed}})
    return {"summary": str(raw.get("summary", "")), "steps": clean, "dropped": dropped}


def transcript(path: str, max_chars=2500) -> str:
    """Local speech-to-text only (faster-whisper or openai-whisper if installed). No API calls; '' if unavailable."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
        model = WhisperModel(os.getenv("LOCAL_WHISPER", "small"), device="cpu", compute_type="int8")
        segs, _ = model.transcribe(path, vad_filter=True)
        txt = "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.text.strip()}" for s in segs)
        return txt[:max_chars]
    except ImportError:
        pass
    except Exception:  # noqa
        return ""
    try:
        import whisper  # type: ignore
        r = whisper.load_model(os.getenv("LOCAL_WHISPER", "small")).transcribe(path)
        return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()}" for s in r.get("segments", []))[:max_chars]
    except Exception:  # noqa  (ImportError included)
        return ""


async def _look(path: str, n=6) -> str:
    """What the video looks like, via sampled frames + a vision model ('' if no vision available)."""
    if not vision.available():
        return ""
    frames = await vision.frames_for_video(path, n)
    try:
        if not frames:
            return ""
        ans, _ = await vision.describe_images(
            [f["path"] for f in frames],
            "These are frames in order from one video (timestamps " + ", ".join(f"{f['t']}s" for f in frames) +
            "). Describe briefly for a video editor: subject, framing/orientation, talking head or B-roll, "
            "existing on-screen text, lighting/colour problems, best-looking moment for a hook.")
        return ans[:1500]
    except Exception:  # noqa
        return ""
    finally:
        for f in frames:
            try:
                os.remove(f["path"])
            except OSError:
                pass


async def plan_edit(video_path: str, instruction: str, has_music: bool = False, feedback: str = "") -> dict:
    info = await pro.probe(video_path)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    ctx = {
        "instruction": instruction,
        "video": {"width": v.get("width"), "height": v.get("height"),
                  "duration_s": round(float(info.get("format", {}).get("duration", 0) or 0), 1),
                  "has_audio": any(s.get("codec_type") == "audio" for s in info.get("streams", []))},
        "has_music": has_music,
        "what_frames_show": await _look(video_path),
        "transcript": await asyncio.to_thread(transcript, video_path),
    }
    if feedback:
        ctx["previous_render_problems"] = feedback
    sysmsg = PLANNER.format(ops=OP_DOC, playbook=_playbook())
    content, _ = await providers.chat([{"role": "system", "content": sysmsg},
                                       {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)}])
    return parse_plan(content, has_music)


async def run_plan(plan: dict, src: str, music_path: str | None = None, notify=None) -> tuple[str, list[str]]:
    cur, done = src, []
    for s in plan.get("steps", []):
        op = s["op"]
        mod, _ = OPS[op]
        kw = {k: v for k, v in s.items() if k != "op"}
        if op in NEEDS_MUSIC:
            kw["music_path"] = music_path
        if notify:
            await notify(f"\u23f3 {op.replace('_', ' ')}...")
        cur = await getattr(mod, op)(cur, **kw)
        done.append(op)
    return cur, done


async def auto_edit(src: str, instruction: str, music_path: str | None = None, notify=None) -> dict:
    """Plan -> run -> QA review -> at most one retry. Returns {"path","steps","summary","review"}."""
    plan = await plan_edit(src, instruction, has_music=bool(music_path))
    if not plan["steps"]:
        raise RuntimeError("Edit plan empty ayyindi — inka clear ga emi cheyyalo cheppandi.")
    out, steps = await run_plan(plan, src, music_path, notify)
    review = await vision.review_render(out)
    if not review["ok"]:
        if notify:
            await notify("\U0001f50d Quality check lo issues: " + "; ".join(review["issues"][:3]) + ". Okasari fix chestunna...")
        plan2 = await plan_edit(src, instruction, has_music=bool(music_path),
                                feedback="; ".join(review["issues"]) + " | hint: " + review.get("fix_hint", ""))
        if plan2["steps"]:
            out2, steps2 = await run_plan(plan2, src, music_path, notify)
            review2 = await vision.review_render(out2)
            if review2["ok"] or len(review2["issues"]) < len(review["issues"]):
                out, steps, plan, review = out2, steps2, plan2, review2
    return {"path": out, "steps": steps, "summary": plan.get("summary", ""), "review": review}
