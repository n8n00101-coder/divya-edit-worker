"""codegen.py — Divya's adapter for Blind's divya_codegen.py (v32).

Bridges Divya's plan (doc.plan) and chat (runner.groq_chat) into Blind's
codegen engine: plan.json -> ideas (objects + per-scene fx/transitions/
visuals) -> video_fx.py (sandbox-tested, max 2 fixes) -> codegen_result.json
(passed_custom + fallback_from_library + fingerprint). Sets p["codegen"].

Raises on a hard failure — the caller (doc.make_video) falls back to the
library, so one bad codegen never kills the video.
"""
import json, os, re, pathlib
import divya_codegen as DC

_STOP = {"a", "an", "the", "is", "are", "was", "were", "it", "its", "this", "that",
         "and", "or", "but", "so", "to", "of", "in", "on", "for", "with", "you", "your",
         "we", "our", "i", "me", "my", "he", "she", "they", "do", "does", "did", "can",
         "will", "would", "not", "no", "yes", "if", "when", "why", "how", "what"}
_SHOCK = {"but", "never", "only", "not", "no", "stop", "secret", "shocking", "surprise",
          "hidden", "truth", "lie", "fake", "real", "actually", "exactly", "nobody", "everyone"}
_NUMWORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
             "eleven", "twelve", "twenty", "thirty", "fifty", "hundred", "thousand", "million",
             "billion", "percent", "half", "double", "triple", "zero"}


def hit_word_of(s, title):
    """The ONE hit word for a scene (the word the visual/effect lands on).
    Same priority as doc.make_video's pop_t, but returns the WORD (not the
    time): number > label word > topic noun > shock word > first content
    word. Searches only the first 60% of the words (a hit word at the end
    would hide the visual and the label for most of the scene)."""
    words = [w.strip().lower().strip(".,!?\"'") for w in str(s.get("vo", "")).split()]
    if not words:
        return ""
    early = words[:max(1, int(len(words) * 0.6) + 1)]
    label = {w.strip().lower() for w in str(s.get("label", "")).split() if len(w.strip()) > 1}
    topic = {w.strip().lower().strip(".,!?\"'") for w in str(title or "").split()
             if len(w.strip().strip(".,!?\"'")) > 3}
    for ww in early:  # 1. a number (digit, or a spelled-out number word)
        if any(c.isdigit() for c in ww) or ww in _NUMWORDS:
            return ww
    for ww in early:  # 2. a word from the scene's label
        if ww in label:
            return ww
    for ww in early:  # 3. a topic noun (a word from the title)
        if ww in topic and ww not in _STOP:
            return ww
    for ww in early:  # 4. a contrast/shock word
        if ww in _SHOCK:
            return ww
    for ww in words:  # fallback: first content word
        if len(ww) > 3 and ww not in _STOP:
            return ww
    return words[0]


def _chat_llm(chat):
    """Wrap Divya's chat(messages) -> str into divya_codegen.llm's signature."""
    def call(messages, temperature=0.8, max_tokens=3500):
        return chat([{"role": m["role"], "content": m["content"]} for m in messages])
    return call


def run(p, chat, wd, recent_families=()):
    """Run Blind's codegen engine on Divya's plan p. Writes plan.json,
    ideas.json, video_fx.py, codegen_result.json into wd. Returns the
    codegen_result dict (passed_custom, fallback_from_library, fingerprint).
    Sets p['codegen'] to the same dict. Raises on a hard failure (the caller
    falls back to the library)."""
    os.environ["FX_MAX_MS"] = "200"  # Divya offline render (1080x1920)
    DC.CHAT = _chat_llm(chat)
    title = p.get("title", "WATCH THIS")
    acc = p.get("accent") or [255, 210, 0]
    accent = list(acc) if isinstance(acc, (list, tuple)) else [255, 210, 0]
    plan = {
        "topic": title,
        "mood": p.get("look", ""),
        "accent": accent,
        "recent_families": list(recent_families or []),
        "tags": sorted({w.lower() for w in re.split(r"[^A-Z0-9]+", title.upper()) if len(w) > 3}),
        "scenes": [
            {"text": s.get("vo", ""), "hit_word": hit_word_of(s, title),
             "tags": [s.get("visual", ""), s.get("mood", "")]}
            for s in p["scenes"]
        ],
    }
    plan_path = os.path.join(wd, "plan.json")
    with open(plan_path, "w") as f:
        json.dump(plan, f, indent=1)
    DC.main(plan_path, wd)
    result = json.loads(pathlib.Path(wd, "codegen_result.json").read_text())
    p["codegen"] = result
    return result
