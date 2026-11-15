"""story_analyst.py — Julie v87 role 1: the Story Analyst.

Reads the writer's FINISHED chapter script (doc.plan output scenes,
before directing) and emits a BEAT SHEET: per scene — emotion, subject,
turning-point flag, spoken emphasis words, and the visual opportunity
the line itself offers (footage / document / number / quote / contrast /
term / scene). This is the structure the Visual Director plans from and
the structure doc_structure validates arc roles against — replacing
chapter-position arithmetic with reading the script.

Contract:
- One LLM call per chapter, through the pipeline's injected `chat`
  callable (the same sync callable doc.plan receives; in production it
  is providers.py rotation via the runner's chat).
- Output is data only. A failed/unparseable call returns None and the
  pipeline degrades to v86 deterministic behaviour — the report says
  so; the analyst never invents a sheet it did not produce.
- The beat sheet is a human-readable artifact (BEAT_SHEET.md) as well
  as JSON: Ajju/Blind can read it before a single frame renders.
"""

import json
import re

OPPORTUNITIES = ("footage", "document", "number", "quote", "contrast",
                 "term", "scene")

_SYSTEM = (
    "You are Julie's Story Analyst. You read a finished narration "
    "script and produce a beat sheet for the editing team. You output "
    "strict JSON only — no prose, no markdown fences.")


def _prompt(scenes, topic, taste):
    lines = []
    for i, s in enumerate(scenes):
        lines.append(f"{i + 1}. {str(s.get('vo', '')).strip()}")
    return (
        (taste or "") +
        "\n\nAnalyse this narration script"
        + (f" (topic: {topic})" if topic else "") +
        ". For EACH numbered line return one object:\n"
        '{"emotion": "<one or two words>", "subject": "<what the line '
        'is about, in the line\'s own words>", "turning_point": '
        'true|false (true only where the story itself turns — a '
        'realisation, a reversal, the first honest act), "emphasis": '
        '["<up to 3 spoken words that carry the line>"], '
        '"visual_opportunity": one of footage|document|number|quote|'
        'contrast|term|scene — footage: the line names a filmable '
        'thing/action; document: it cites evidence or a finding; '
        'number: it speaks a number that matters; quote: it quotes '
        'exact words; contrast: it weighs two opposing ideas; term: '
        'it names a concept; scene: none of these, a plain scene.}\n'
        'Reply with strict JSON: {"scenes": [ ... one object per '
        'line, in order ... ]}\n\nSCRIPT:\n' + "\n".join(lines))


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


def analyse_script(scenes, chat, taste="", topic=""):
    """Return the beat sheet dict {version, scenes: [...]} aligned to
    `scenes` by index, or None when the model call fails or returns
    nothing usable. Never raises."""
    scenes = [s for s in (scenes or []) if str(s.get("vo", "")).strip()]
    if not scenes or chat is None:
        return None
    try:
        raw = chat([{"role": "system", "content": _SYSTEM},
                    {"role": "user",
                     "content": _prompt(scenes, topic, taste)}])
    except Exception:
        return None
    data = _parse(raw)
    rows = (data or {}).get("scenes")
    if not isinstance(rows, list) or not rows:
        return None
    out = []
    for i, s in enumerate(scenes):
        r = rows[i] if i < len(rows) and isinstance(rows[i], dict) else {}
        opp = str(r.get("visual_opportunity") or "scene").lower()
        if opp not in OPPORTUNITIES:
            opp = "scene"
        emph = [str(w)[:24] for w in (r.get("emphasis") or [])
                if str(w).strip()][:3]
        out.append({
            "scene": i + 1,
            "label": str(s.get("label", "")),
            "line": str(s.get("vo", "")).strip(),
            "emotion": str(r.get("emotion") or "")[:40],
            "subject": str(r.get("subject") or "")[:80],
            "turning_point": bool(r.get("turning_point")),
            "emphasis": emph,
            "visual_opportunity": opp,
            "analysed": bool(r),
        })
    if not any(r["analysed"] for r in out):
        return None
    return {"version": "v87-story-analyst-1", "topic": topic,
            "scenes": out,
            "turning_points": [r["scene"] for r in out
                               if r["turning_point"]]}


def scene_for(sheet, scene_index0):
    """The sheet row for a 0-based writer-scene index, or {}."""
    if not sheet:
        return {}
    rows = sheet.get("scenes") or []
    return rows[scene_index0] if 0 <= scene_index0 < len(rows) else {}


def beat_sheet_markdown(sheet, title=""):
    """BEAT_SHEET.md — the readable form of the analyst's sheet."""
    if not sheet:
        return "# Beat Sheet\n\n(Story Analyst unavailable — sheet not produced.)\n"
    lines = [f"# Beat Sheet — {title or sheet.get('topic') or 'documentary'}",
             "",
             "Produced by the v87 Story Analyst from the finished "
             "script, BEFORE any visual planning or rendering.", ""]
    for r in sheet.get("scenes") or []:
        tp = " ★ TURNING POINT" if r.get("turning_point") else ""
        lines.append(
            f"- **Scene {r['scene']}** ({r.get('emotion') or '—'}){tp}\n"
            f"  - Line: {r['line']}\n"
            f"  - Subject: {r.get('subject') or '—'} · "
            f"Emphasis: {', '.join(r.get('emphasis') or []) or '—'} · "
            f"Visual opportunity: {r.get('visual_opportunity')}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    def stub(messages):
        return json.dumps({"scenes": [
            {"emotion": "tense", "subject": "the automatic yes",
             "turning_point": False, "emphasis": ["yes"],
             "visual_opportunity": "scene"},
            {"emotion": "realisation", "subject": "the first honest no",
             "turning_point": True, "emphasis": ["honest", "no"],
             "visual_opportunity": "quote"}]})
    sheet = analyse_script(
        [{"vo": "The word yes is out of your mouth.", "label": "A"},
         {"vo": "Then one day you say the honest no.", "label": "B"}],
        stub, topic="saying yes")
    assert sheet and sheet["turning_points"] == [2], sheet
    assert analyse_script([{"vo": "x"}], lambda m: "not json") is None
    print("story_analyst self-check OK")
