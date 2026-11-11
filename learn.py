"""R45 continuous learning for Divya (divya-edit-worker).

Daily loop (see DIVYA_LONG_VIDEOS_BOOKS_TUTORIALS.md, "Daily learning loop"):
take ONE tutorial/book from the lists in that doc, distil 5 rules from it
in Divya's own words, and write ONE new ``fx_`` helper function that uses
the idea, sandbox-tested. The best functions feed the few-shot pool
(max 12, oldest drops when a 13th is added) that the codegen prompts see.

This module is research + storage only: it never schedules a cron and never
sends anything. The daily loop that calls :func:`learn_one` is a separate
decision (a cron / Worker job owned elsewhere).

Store: ``~/workspace/divya-learn.json`` (override with ``DIVYA_LEARN_STORE``),
``{"learned": [ {"source", "title", "rules", "function",
"function_name", "date", "sandbox_ok"}, ... ]}`` — capped at 12 items,
oldest first out.
"""

import ast
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DOC_NAME = "DIVYA_LONG_VIDEOS_BOOKS_TUTORIALS.md"
MAX_POOL = 12

STORE_PATH = Path(os.environ.get(
    "DIVYA_LEARN_STORE", str(Path.home() / "workspace" / "divya-learn.json")))

_DOC_CANDIDATES = [
    Path(os.environ["DIVYA_LEARN_DOC"]) if os.environ.get("DIVYA_LEARN_DOC") else None,
    Path(__file__).resolve().parent / DOC_NAME,
    Path(__file__).resolve().parent / "hark-kit" / DOC_NAME,
    Path.home() / "workspace" / "hark-v30" / DOC_NAME,
    Path.home() / "workspace" / "divya-v32-modules" / DOC_NAME,
]
_DOC_CANDIDATES = [p for p in _DOC_CANDIDATES if p is not None]

# Learned helpers are layer effects in the video_fx.py convention:
# fn(L, t, st, dur) -> L, L an RGBA layer, t seconds into the effect.
# They must stay inside the 720x1280 safe box (8% x-margins, 10% y-margins)
# and return a layer the same size they were given.
W, H = 720, 1280
SAFE = (int(W * 0.08), int(H * 0.10), int(W * 0.92), int(H * 0.90))


# ---------------------------------------------------------------- doc parsing
def _doc_path():
    for p in _DOC_CANDIDATES:
        if p.is_file():
            return p
    tried = "\n  ".join(str(p) for p in _DOC_CANDIDATES)
    raise FileNotFoundError(
        f"{DOC_NAME} not found. Tried:\n  {tried}\n"
        "Set DIVYA_LEARN_DOC to its path.")


def _read_doc():
    return _doc_path().read_text(encoding="utf-8")


def _section(text, start_marker, end_marker=None):
    """Text between a '## N. ...' heading and the next '## ' heading."""
    i = text.find(start_marker)
    if i < 0:
        raise ValueError(f"section not found: {start_marker!r}")
    j = text.find("\n## ", i + 1)
    if end_marker:
        k = text.find(end_marker, i + 1)
        if 0 < k < (j if j > 0 else len(text)):
            j = k
    return text[i:j if j > 0 else len(text)]


def _split_title_tail(rest):
    """Split 'Title - author/detail (note)' or 'Title (note)' into parts.

    Returns (title, tail, note): tail is everything after the title,
    note is the trailing '(...)' if present, else ''.
    """
    note = ""
    m = re.search(r"\(([^()]*)\)\s*$", rest)
    if m:
        note = m.group(1).strip()
    # Title ends at the first " - " or " (" — whichever comes first, so a
    # URL in parens before the dash (e.g. 'edge-tts project page (https://…) -
    # word timing') does not leak into the title.
    cuts = [i for i in (rest.find(" - "), rest.find(" (")) if i >= 0]
    cut = min(cuts) if cuts else len(rest)
    title = rest[:cut].strip()
    tail = rest[cut:].strip()
    if tail.startswith("("):  # leading parenthetical (usually a URL): drop it
        tail = re.sub(r"^\([^)]*\)\s*(-\s*)?", "", tail).strip()
    elif tail.startswith("-"):
        tail = tail[1:].strip()
    if note and tail.endswith(f"({note})"):  # trailing "(note)": keep separate
        tail = tail[: -len(note) - 2].strip()
    return title, tail, note


def tutorial_list():
    """All tutorials from section 3 of the doc, in study order.

    The doc lists them as numbered lines (1-32) grouped under
    '### Stage N: ...' headings. Section 0 has its own 1-7 numbered list,
    so parsing is scoped to section 3 only — never the whole file.
    Each item: {"n", "title", "detail", "url", "source", "stage"}.
    """
    text = _read_doc()
    sec = _section(text, "## 3. TUTORIALS", "### Daily learning loop")
    out, stage = [], ""
    for line in sec.splitlines():
        if line.startswith("### Stage"):
            stage = line.lstrip("#").strip()
            continue
        m = re.match(r"^(\d+)\.\s+(.+)$", line)
        if not m:
            continue
        num, rest = int(m.group(1)), m.group(2).strip()
        url_m = re.search(r"https?://[^\s)]+", rest)
        url = url_m.group(0) if url_m else ""
        title, tail, note = _split_title_tail(rest)
        detail = tail
        if note and note not in detail:
            detail = f"{detail} ({note})" if detail else note
        if "YouTube" in rest:
            source = "YouTube"
        elif url:
            source = re.sub(r"^www\.", "", url.split("/")[2])
        else:
            source = ""
        out.append({"n": num, "title": title, "detail": detail,
                    "url": url or None, "source": source, "stage": stage})
    out.sort(key=lambda d: d["n"])
    return out


def book_list():
    """All books from section 2 of the doc, in priority order.

    The doc gives the core 6 as prose ('Core 6 (already in handbook): A;
    B; ...') and books 7-22 as numbered lines ('7. Title - Author
    (note)'). Both shapes are parsed; each item is
    {"n", "title", "author", "note"}.
    """
    text = _read_doc()
    sec = _section(text, "## 2. BOOKS", "## 3. TUTORIALS")
    books = []
    # --- core 6: prose paragraph, items separated by ';', 'Title (Author)'.
    m = re.search(r"Core 6.*?:\s*(.*?)\s*More, in priority order", sec, re.S)
    if not m:
        raise ValueError("core-6 paragraph not found in books section")
    core = " ".join(m.group(1).split())
    for chunk in core.split(";"):
        chunk = chunk.strip().rstrip(".")
        if not chunk:
            continue
        mm = re.match(r"(.+?)\s*\(([^)]+)\)$", chunk)
        if not mm:
            raise ValueError(f"cannot parse core book: {chunk!r}")
        books.append({"n": len(books) + 1, "title": mm.group(1).strip(),
                      "author": mm.group(2).strip(),
                      "note": "core 6, notes in DIVYA_EDITING_HANDBOOK"})
    # --- books 7-22: numbered lines.
    for num_s, rest in re.findall(r"^(\d+)\.\s+(.+)$", sec, re.M):
        num = int(num_s)
        if num < 7:
            continue
        title, tail, note = _split_title_tail(rest)
        author = re.split(r"\s*\(", tail, 1)[0].strip() if tail else ""
        books.append({"n": num, "title": title, "author": author,
                      "note": note})
    books.sort(key=lambda d: d["n"])
    return books


# ------------------------------------------------------------- rule distilling
# Heuristic fallback (no LLM): keyword -> rules grounded in that topic.
# Used only when no chat function is passed; with a chat function the LLM
# distils real rules from the source (see _llm_distill).
_KEYWORD_RULES = [
    (("eas", "bezier", "penner", "curve"), [
        "Ease every move — never move anything linearly; ease-out on entries, ease-in-out on travels.",
        "One easing family per video; changing the curve mid-video reads as a mistake.",
        "Fast-in reads as a snap, slow-out reads as a settle — pick by what the word means.",
        "Keep the moving thing inside the safe box at every frame of the ease.",
        "If two things move at once, give them the same duration so they land together."]),
    (("typograph", "type", "font"), [
        "One font family per video; a second font is a second voice.",
        "Captions 2-4 words per line, big enough to read at a glance on a phone.",
        "Emphasis goes on ONE word per line — highlight it, never the whole sentence.",
        "Never set text across a face or the moving visual; put it in empty space.",
        "Line spacing matters as much as size — cramped lines read as noise."]),
    (("color", "colour", "palette"), [
        "One accent colour at a time; a second accent must earn its scene.",
        "Change the background colour only on a section change, not every sentence.",
        "Text must contrast with what is behind it at every frame, not just the first.",
        "Warm vs cool is a mood choice — pick it from the sentence, not the last scene.",
        "Keep the palette the same across chapters of one video so it reads as one piece."]),
    (("sound", "sfx", "audio", "music"), [
        "One sound effect per hit word, landing exactly on the word — never a bed of pops.",
        "Duck the music under the voice; silence just before a big reveal beats a sting.",
        "Voice stays at one constant loud level from start to finish — no quiet ramp-up.",
        "A sound must mean something (stamp = rule, whoosh = move); decoration noise is a defect.",
        "Check the mix on a phone speaker, not just headphones."]),
    (("retention", "pacing", "edit", "cut"), [
        "Hook in the first 2 seconds: the strongest visual plus the question.",
        "A visual change every 3-6 seconds in long form; never 20 seconds without movement.",
        "Every chapter answers one question and raises the next — an open loop per chapter.",
        "Re-hook at 30s, 1 minute, and the middle: 'but here is the strange part'.",
        "Cut on the idea, not on the clock — a scene ends when its point lands."]),
    (("animat", "motion"), [
        "One effect at a time per scene — an entry, then an emphasis, never both at once.",
        "The visual lands 80ms before its hit word; ears lag eyes.",
        "Anticipation before a big move, follow-through after — nothing starts or stops dead.",
        "Squash and stretch sell weight; a rigid move reads as a slideshow.",
        "If a move does not change what the viewer understands, cut it."]),
    (("ffmpeg", "pillow", "numpy", "code", "manim", "shader"), [
        "Draw it in code before reaching for footage — code-drawn beats stock for abstract ideas.",
        "One function, one visual; test it in the sandbox before it touches a render.",
        "Keep every drawn element inside the safe box at every frame.",
        "Vary the camera (push / drift / whip) between scenes, never inside one take.",
        "If a frame looks wrong, fix the code — never patch it with a caption."]),
]


def _heuristic_rules(source):
    low = source.lower()
    for keywords, rules in _KEYWORD_RULES:
        if any(k in low for k in keywords):
            return list(rules)
    return [
        "One idea per scene, one visual per idea — the visual must literally show the line.",
        "Hook first, then context, then a twist, then the payoff — in that order.",
        "One effect at a time; the visual lands 80ms before its hit word.",
        "Keep everything inside the safe box and the voice at one constant level.",
        "Self-check one frame per scene; re-render only the bad scene."]


def _slug(title):
    words = re.findall(r"[a-z0-9]+", title.lower())
    words = [w for w in words if w not in ("the", "a", "an", "of", "and", "for")]
    slug = "_".join(words[:3])[:24].strip("_") or "general"
    return slug


def _make_function(slug, title, rule):
    """Deterministic eased accent-bar helper, in the video_fx.py convention.

    ``fx_learned_<slug>(L, t, st, dur)`` — needs ``math`` and ``ImageDraw``
    in scope (as in effects.py / video_fx.py). Draws one accent bar that
    eases in plus one dot; everything stays inside the 720x1280 safe box.
    """
    return (
        f"def fx_learned_{slug}(L, t, st=0.0, dur=0.6):\n"
        f"    \"\"\"Learned from {title}: {rule}\"\"\"\n"
        "    p = min(1.0, max(0.0, (t - st) / max(dur, 0.01)))\n"
        "    e = 1 - (1 - p) ** 3  # ease-out cubic: fast in, soft landing\n"
        "    d = ImageDraw.Draw(L)\n"
        "    x0, x1 = 90, 90 + int(540 * e)\n"
        "    d.rounded_rectangle([x0, 1090, max(x1, x0 + 8), 1112], radius=11,\n"
        "                        fill=(255, 210, 0, 255))\n"
        "    r = int(34 * e)\n"
        "    if r > 0:\n"
        "        d.ellipse([360 - r, 640 - r, 360 + r, 640 + r],\n"
        "                  fill=(255, 255, 255, 255))\n"
        "    return L\n"
    )


def _sandbox_test(code, fn_name, timeout=60):
    """Sandbox-test a helper: import it in a subprocess, call it on a dummy
    720x1280 RGBA layer at several times, check size + safe box.

    Returns (ok, error-or-""). Mirrors fx_sandbox.py's fx_ contract
    (fn(L, t, st, dur)) but at the 720x1280 size the task specifies.
    """
    harness = (
        "import importlib.util, sys\n"
        "from PIL import Image\n"
        "spec = importlib.util.spec_from_file_location('learned_fn', sys.argv[1])\n"
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
        f"fn = getattr(mod, {fn_name!r})\n"
        "SAFE = (57, 128, 662, 1152)\n"
        "for t in (0.0, 0.15, 0.3, 0.45, 0.6, 1.0):\n"
        "    L = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))\n"
        "    out = fn(L, t, 0.0, 0.6)\n"
        "    assert out.size == (720, 1280), f'wrong size {out.size}'\n"
        "    bb = out.getbbox()\n"
        "    if bb:\n"
        "        assert bb[0] >= SAFE[0] - 2 and bb[1] >= SAFE[1] - 2, f'outside safe box {bb}'\n"
        "        assert bb[2] <= SAFE[2] + 2 and bb[3] <= SAFE[3] + 2, f'outside safe box {bb}'\n"
        "print('sandbox ok')\n"
    )
    with tempfile.TemporaryDirectory(prefix="learn_fn_") as td:
        mod_path = os.path.join(td, "learned_fn.py")
        with open(mod_path, "w") as f:
            f.write("import math\nfrom PIL import Image, ImageDraw\n\n" + code)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as hf:
            hf.write(harness)
            harness_path = hf.name
        try:
            r = subprocess.run([sys.executable, harness_path, mod_path],
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, "sandbox timed out"
        finally:
            os.unlink(harness_path)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "sandbox failed").strip().splitlines()
        return False, err[-1][:300] if err else "sandbox failed"
    return True, ""


def _llm_distill(source, chat):
    """Ask the LLM (same [{"role": ...}] format as doc.plan) for 5 rules
    + one fx_ function. Returns (rules, code, fn_name) or None on any failure.
    """
    prompt = (
        "You are Divya's learning step (R45). From the source below, distil "
        "exactly 5 short, concrete video-editing rules in Divya's own words "
        "(each one sentence, about easing / visuals / pacing / sound / "
        "typography as the source dictates), and write ONE small Python "
        "helper function that uses the idea. The function must be named "
        "fx_learned_<slug>, take (L, t, st=0.0, dur=0.6), draw on the RGBA "
        "720x1280 layer L with PIL ImageDraw only (math allowed), stay "
        "inside x 57-662, y 128-1152, and return L. Return ONLY JSON: "
        '{"rules": ["...", x5], "function": "def fx_learned_...\\n ...", '
        '"function_name": "fx_learned_..."}. Source: ' + source[:4000])
    try:
        raw = chat([{"role": "system", "content": "You output strict JSON only."},
                    {"role": "user", "content": prompt}])
        data = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))
        rules = [str(r).strip() for r in data.get("rules", []) if str(r).strip()]
        code, name = str(data.get("function", "")), str(data.get("function_name", ""))
        if len(rules) != 5 or not code or not name.startswith("fx_"):
            return None
        tree = ast.parse(code)
        if not any(isinstance(n, ast.FunctionDef) and n.name == name
                   for n in tree.body):
            return None
        return rules, code, name
    except Exception:
        return None


# ---------------------------------------------------------------- store
def _load_store():
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        learned = data.get("learned", [])
        return learned if isinstance(learned, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_store(learned):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps({"learned": learned}, indent=2),
                          encoding="utf-8")


def _resolve_title(source):
    """If the source names a listed tutorial/book, use its canonical title."""
    low = source.lower()
    for item in tutorial_list() + book_list():
        title = item["title"].lower()
        if title and (title in low or low.strip() in title):
            return item["title"]
    return " ".join(source.split())[:80]


def learn_one(source, chat=None):
    """Distil ONE learning item into the store.

    source: a tutorial title/link or book notes text. chat: optional LLM
    chat function (same [{"role": ...}] format as doc.plan); without it,
    rules come from the topic-keyword heuristic and the helper is the
    deterministic eased-bar function. The helper is always sandbox-tested;
    a failing LLM function falls back to the deterministic one.
    Returns the learned item dict.
    """
    title = _resolve_title(source)
    rules = code = name = None
    if chat is not None:
        got = _llm_distill(source, chat)
        if got:
            rules, code, name = got
            ok, _err = _sandbox_test(code, name)
            if not ok:
                rules = code = name = None  # fall through to deterministic
    if rules is None:
        rules = _heuristic_rules(source)
        slug = _slug(title)
        name = f"fx_learned_{slug}"
        code = _make_function(slug, title, rules[0])
        ok, err = _sandbox_test(code, name)
        if not ok:
            raise RuntimeError(f"learned helper failed sandbox: {err}")
    else:
        ok, err = _sandbox_test(code, name)
        if not ok:  # LLM code passed the first test but not the re-test: be safe
            slug = _slug(title)
            name = f"fx_learned_{slug}"
            code = _make_function(slug, title, rules[0])
            ok, err = _sandbox_test(code, name)
            if not ok:
                raise RuntimeError(f"learned helper failed sandbox: {err}")
    item = {"source": source, "title": title, "rules": rules[:5],
            "function": code, "function_name": name,
            "date": _dt.date.today().isoformat(), "sandbox_ok": bool(ok)}
    learned = _load_store()
    learned.append(item)
    learned = learned[-MAX_POOL:]  # rotation: adding a 13th drops the oldest
    _save_store(learned)
    return item


def fewshot_pool():
    """Current few-shot pool: up to 12 learned helper function strings,
    oldest first (the store already rotates, so this is just the list)."""
    return [it["function"] for it in _load_store()
            if it.get("function")][-MAX_POOL:]


if __name__ == "__main__":
    tuts, books = tutorial_list(), book_list()
    print(f"tutorials: {len(tuts)}")
    print(f"books: {len(books)}")
    assert len(tuts) == 32, f"expected 32 tutorials, got {len(tuts)}"
    assert len(books) == 22, f"expected 22 books, got {len(books)}"
    sample = tuts[0]
    item = learn_one(f"{sample['title']} - {sample['detail']} "
                     f"({sample['url']})")
    print(f"learn_one: {item['title']!r} -> {len(item['rules'])} rules, "
          f"{item['function_name']}, sandbox_ok={item['sandbox_ok']}")
    print(f"few-shot pool: {len(fewshot_pool())} function(s)")
    print(f"store: {STORE_PATH}")
