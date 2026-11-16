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

try:
    import hooks_lib as _hooks
except Exception:  # hooks are additive — the analyst must still run
    _hooks = None


def _note_stage(ok, detail=""):
    """PROOF-FIX 1: the stage's outcome goes on the brain ledger —
    a fallback is labelled FALLBACK in the job report, never passed
    off as brain work. Guarded: the ledger must never break a stage."""
    try:
        import brain_status as _bs
        _bs.record("story-analyst", ok, detail)
    except Exception:
        pass

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


# ------------------------------------------------------- topic pre-flight
_PLACE_WORDS = ("village", "town", "city", "coast", "river", "island",
                "desert", "forest", "mountain", "valley", "harbour",
                "harbor", "port", "lake", "ocean", "sea", "street",
                "market", "temple", "fort", "bridge", "india", "kerala",
                "goa", "assam", "rajasthan", "himalaya", "ganges",
                "village", "district", "state", "country", "region")
_TWIST_WORDS = ("but", "yet", "actually", "hidden", "secret", "twist",
                "reveal", "despite", "paradox", "forgot", "vanish",
                "disappear", "nobody", "no one", "never", "truth",
                "behind", "real reason", "turns out", "ironically")


def preflight(topic, angle="", sources=None):
    """Topic pre-flight checklist (additive; deterministic, no LLM).

    Checks: a one-line hook is possible (a generated hook variant
    scores WORKABLE or better), a mappable place exists in the
    topic/angle, real sources are available, and a twist/payoff
    exists. Returns a structured verdict dict. `blocked` is True
    ONLY when there is no viable hook AND no sources — every other
    gap is a warning (`missing`), never a hard block."""
    topic = str(topic or "").strip()
    angle = str(angle or "").strip()
    text = f"{topic} {angle}".lower()
    srcs = [s for s in (sources or [])
            if (isinstance(s, dict) and (s.get("url") or s.get("title")
                                         or s.get("source")))
            or (isinstance(s, str) and s.strip())]
    variants = []
    hook_ok = False
    if _hooks is not None and topic:
        try:
            variants = _hooks.generate_hook_variants(topic, angle)
            hook_ok = bool(variants) and \
                variants[0]["score"]["total"] >= 30
        except Exception:
            variants, hook_ok = [], False
    place_ok = any(w in text for w in _PLACE_WORDS) or bool(
        re.search(r"\b[A-Z][a-z]{2,}\b", f"{topic} {angle}"))
    twist_ok = any(w in text for w in _TWIST_WORDS)
    checks = {"hook_possible": bool(hook_ok),
              "mappable_place": bool(place_ok),
              "sources_available": bool(srcs),
              "twist_or_payoff": bool(twist_ok)}
    missing = [k for k, v in checks.items() if not v]
    blocked = not checks["hook_possible"] and not checks[
        "sources_available"]
    verdict = "block" if blocked else ("warn" if missing else "pass")
    if missing:
        print(f"preflight [{verdict}]: topic {topic[:60]!r} — "
              f"missing: {', '.join(missing)}")
    return {"version": "v89-preflight-1", "topic": topic,
            "checks": checks, "missing": missing,
            "verdict": verdict, "blocked": blocked,
            "hook_variants": variants}


def hook_variants(topic, angle=""):
    """Ranked hook variants (2-3 named formulas) for a topic/angle,
    scored by hooks_lib. [] when the library is unavailable."""
    if _hooks is None or not str(topic or "").strip():
        return []
    try:
        return _hooks.generate_hook_variants(str(topic), str(angle or ""))
    except Exception:
        return []


def analyse_script(scenes, chat, taste="", topic="", angle="",
                   sources=None):
    """Return the beat sheet dict {version, scenes: [...]} aligned to
    `scenes` by index, or None when the model call fails or returns
    nothing usable. Never raises."""
    scenes = [s for s in (scenes or []) if str(s.get("vo", "")).strip()]
    if not scenes or chat is None:
        return None
    # PROOF-FIX 1: the analyst reads the STORY slice of the taste
    # pack, never the whole 56K pack (the full pack 413'd on the
    # free channel and the analyst silently never ran). A caller
    # that still hands a full pack gets the slice instead.
    if len(taste or "") > 12000:
        try:
            import pack_slicer as _ps
            taste = _ps.slice_for("story")
        except Exception:
            pass
    try:
        raw = chat([{"role": "system", "content": _SYSTEM},
                    {"role": "user",
                     "content": _prompt(scenes, topic, taste)}])
    except Exception as _e:
        _note_stage(False, f"LLM failed: {str(_e)[:80]}")
        return None
    data = _parse(raw)
    rows = (data or {}).get("scenes")
    if not isinstance(rows, list) or not rows:
        _note_stage(False, "LLM reply unusable (no scene rows)")
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
        _note_stage(False, "LLM reply carried no usable scene analysis")
        return None
    sheet = {"version": "v87-story-analyst-1", "topic": topic,
             "scenes": out,
             "turning_points": [r["scene"] for r in out
                                if r["turning_point"]]}
    # v89 (additive): before script lock — ranked hook variants in
    # named formulas + the topic pre-flight verdict ride on the sheet.
    # Existing callers read scenes/turning_points and are unaffected.
    try:
        sheet["hook_variants"] = hook_variants(topic, angle)
        sheet["preflight"] = preflight(topic, angle, sources)
    except Exception as e:
        print(f"story_analyst v89 hooks/preflight failed: "
              f"{str(e)[:120]}")
    _note_stage(True, f"{len(out)} scenes, preflight "
                      f"{(sheet.get('preflight') or {}).get('verdict', '?')}, "
                      f"{len(sheet.get('hook_variants') or [])} hook variants")
    return sheet


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
