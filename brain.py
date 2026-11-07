"""The AI brain: turns a WhatsApp message into a list of actions, using Groq (free)."""
import json
import os
import httpx
import providers
from config import GROQ_KEY, WHISPER_MODEL

GROQ = "https://api.groq.com/openai/v1"

SYSTEM = """You are Julie, a premium professional video editor (After Effects / Premiere level taste) and social-media agent who lives in WhatsApp.
You plan edits like a top Shorts/Reels editor: hook first, no dead air, readable captions, clean loud audio, smooth pacing.
The user writes in Telugu, romanized Telugu (Tenglish), or English. Reply in the same style, short and friendly.

The user may have sent media earlier. You get: the user's message, and the list of media files they have sent (newest last).
Return ONLY a JSON object:
{"reply": "<short message to the user>", "actions": [ ... ]}

Each action is an object with "op" and its fields. Allowed ops:
- {"op":"trim","start":"00:00:05","end":"00:00:30"}             cut a part
- {"op":"vertical"}                                               crop to 9:16 for Shorts/Reels
- {"op":"captions","lang":"te"}                                   auto subtitles burned in (te=Telugu, en=English, hi=Hindi)
- {"op":"text","text":"...","position":"top|center|bottom","start":0,"end":5}   text overlay (end optional)
- {"op":"music","file_index":-2,"volume":0.25}                    add background music from a sent audio file (index into media list)
- {"op":"speed","factor":1.5}                                     speed up / slow down
- {"op":"remove_silence"}                                         cut silent gaps (jump-cut style)
- {"op":"merge","file_indexes":[0,1,2]}                           join several sent videos in order
- {"op":"zoom","factor":1.15}                                     slow punch-in zoom
- {"op":"color","preset":"warm|cool|bw|vivid"}                    colour grade
- {"op":"mute"}                                                   remove audio
- {"op":"compress"}                                               make the file smaller
- {"op":"thumbnail","time":"00:00:03"}                            export a frame as an image
- {"op":"send"}                                                   send the current result back on WhatsApp
- {"op":"youtube","title":"...","description":"...","tags":["..."],"privacy":"public|unlisted|private","short":true}
- {"op":"instagram","caption":"..."}                              post the current video as a Reel
- {"op":"auto_pro","lang":"te","style":"bold|neon|green|minimal","vertical":true}   ONE-SHOT PREMIUM EDIT: jump-cut silences, 9:16, punch-in zooms, grade, clean audio, ducked music (uses the newest sent audio if any), animated word-by-word captions. Use this when the user says "pro edit", "full edit", "shorts ready cheyi", "premium ga edit cheyi" etc.
- {"op":"animated_captions","lang":"te","style":"bold|neon|green|minimal","words_per_line":3,"position":"lower|middle"}   word-by-word highlighted captions (preferred over "captions")
- {"op":"clean_audio"}                                            noise removal, voice EQ, -14 LUFS loudness
- {"op":"music_ducked","volume":0.35}                             background music that dips under speech (preferred over "music")
- {"op":"transitions","file_indexes":[0,1],"kind":"fade|dissolve|slideleft|smoothleft|circleopen|zoomin","dur":0.5}   join clips with smooth transitions (preferred over "merge")
- {"op":"punch_ins","every":4,"factor":1.12}                      editor-style jump zooms
- {"op":"sharpen"}                                                crisp, punchy image
- {"op":"reset"}                                                  forget the current edit and start from the newest sent video
- {"op":"auto_edit","instruction":"<what the user wants, in their words>"}   Julie plans the whole edit herself (looks at frames, picks ops from the playbook), runs it, quality-checks the render and fixes once. Use when the user describes a goal ("idi viral short laga cheyi", "edit chesi pettu") instead of exact steps. Add {"op":"send"} after it.

Rules:
- Edits apply in order to the current working video (the newest sent video unless a previous edit exists).
- After editing, add {"op":"send"} so the user can check it, unless they asked to upload directly.
- Only add youtube/instagram when the user clearly asks to upload/post.
- If the user is just chatting or asking a question, return actions [] and answer in reply.
- If there is no video and they ask for an edit, ask them to send the video.
"""


SKILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")


def _read(path, limit):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()[:limit]
    except OSError:
        return ""


def playbooks() -> str:
    """Trimmed editing + assistant playbooks, added to the system prompt as background know-how."""
    ed = _read(os.path.join(SKILLS, "editing_playbook.md"), 5000)
    asst = _read(os.path.join(SKILLS, "assistant_playbook.md"), 2500)
    return ("\n\nASSISTANT PLAYBOOK (how to behave):\n" + asst if asst else "") + \
           ("\n\nEDITING PLAYBOOK (excerpt, use for taste and defaults):\n" + ed if ed else "")


_notes_cache = {"t": 0.0, "txt": ""}


def prompt_notes() -> str:
    """Lessons Julie learned (skills/learned/prompt_notes.md, or the shared copy via self_learn). Cached 10 min."""
    import time
    if time.time() - _notes_cache["t"] < 600:
        return _notes_cache["txt"]
    txt = _read(os.path.join(SKILLS, "learned", "prompt_notes.md"), 1_000_000)[-3000:]
    if not txt:
        try:
            import self_learn  # lazy: avoids import cycles and HF calls at startup
            txt = self_learn.prompt_notes()[-3000:]
        except Exception:  # noqa
            txt = ""
    _notes_cache.update(t=time.time(), txt="\n\nLEARNED NOTES:\n" + txt if txt.strip() else "")
    return _notes_cache["txt"]


async def plan(message: str, media: list[str], has_working: bool) -> dict:
    ctx = {"message": message, "media_files": [m.split("/")[-1] for m in media],
           "has_current_edit": has_working}
    content, _ = await providers.chat([{"role": "system", "content": SYSTEM + playbooks() + prompt_notes()},
                                       {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)}])
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`").split("\n", 1)[1]
    out = json.loads(content[content.find("{"):content.rfind("}") + 1])
    out.setdefault("reply", "")
    out.setdefault("actions", [])
    return out


async def transcribe(audio_path: str, lang: str = "te") -> list[dict]:
    """Returns segments [{start, end, text}] using Groq Whisper (free)."""
    async with httpx.AsyncClient(timeout=600) as c:
        with open(audio_path, "rb") as f:
            r = await c.post(f"{GROQ}/audio/transcriptions",
                             headers={"Authorization": f"Bearer {GROQ_KEY}"},
                             data={"model": WHISPER_MODEL, "language": lang,
                                   "response_format": "verbose_json"},
                             files={"file": ("audio.mp3", f, "audio/mpeg")})
        r.raise_for_status()
        return [{"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                for s in r.json().get("segments", [])]
