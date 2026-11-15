"""visual_director.py — Julie v87 role 2: the Visual Director (LLM).

The v86 Director chose visuals with keyword heuristics: rules, no
taste (it anchored a balance scale on PSYCHOLOGISTS because a long
word won a regex search). This module is the LLM that now CHOOSES:
for each beat it receives the beat's line, the Story Analyst's read of
the line, and the menu of candidate templates the deterministic code
can honestly render for that beat — and it picks one, with a reason
that must share words with the line (Blind R2).

The split the audit demanded: LLM = decisions, Python = vetoes.
director.direct_plan validates every choice through the same gates as
before (honest composition, no number graphic without a spoken number,
no canned word, no back-to-back repeat); a choice that fails a veto
falls through to the next candidate and the rejection is recorded.

One call per chapter (free-tier friendly). A failed call returns {}
and directing degrades to the v86 deterministic order — reported,
never hidden.
"""

import json
import os
import re

_SYSTEM = (
    "You are Julie's Visual Director. You decide what the audience "
    "SEES on every beat of a documentary. You output strict JSON "
    "only — no prose, no markdown fences.")

_HERE = os.path.dirname(os.path.abspath(__file__))
_pack_cache = {"txt": None}


def taste_pack():
    """skills/taste_pack.md, read in full (never truncated)."""
    if _pack_cache["txt"] is None:
        try:
            with open(os.path.join(_HERE, "skills", "taste_pack.md"),
                      encoding="utf-8") as f:
                _pack_cache["txt"] = f.read()
        except OSError:
            _pack_cache["txt"] = ""
    return _pack_cache["txt"]


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


def choose_visuals(menus, chat, taste="", beat_sheet=None):
    """menus: [{beat, line, role, analyst (dict|None), candidates:
    [{template, asset_type, why}]}] — one entry per beat, candidates in
    the deterministic preference order. Returns {beat_no: {template,
    why, footage_query}} for the beats the model decided; {} on any
    failure. Choices are ADVISORY: director.direct_plan still vetoes.
    """
    if not menus or chat is None:
        return {}
    blocks = []
    for m in menus:
        an = m.get("analyst") or {}
        cands = "; ".join(
            f"{c['template']} [{c['asset_type']}]"
            for c in m.get("candidates") or [])
        blocks.append(
            f"Beat {m['beat']} (role {m.get('role', '')}"
            + (f"; analyst: emotion {an.get('emotion', '')}, "
               f"opportunity {an.get('visual_opportunity', '')}"
               if an else "")
            + f")\n  Line: \"{m['line']}\"\n  Candidates: {cands}")
    prompt = (
        (taste or "") +
        "\n\nFor EACH beat below, choose exactly ONE candidate "
        "template — the visual that best carries THIS line's meaning "
        "(the taste pack's asset priority: footage > document/data > "
        "typography-as-visual > drawn graphic). Your \"why\" must "
        "share actual words with the beat's line. When the line names "
        "something filmable and you would prefer real footage over "
        "every drawn candidate, still pick the best candidate AND add "
        "\"footage_query\": a 3-6 word stock-footage search for the "
        "line's subject. Never pick the same template for two "
        "neighbouring beats unless every alternative is wrong for the "
        "line.\n"
        'Reply with strict JSON: {"choices": [{"beat": <n>, '
        '"template": "<candidate template name>", "why": "<one '
        'sentence, sharing words with the line>", "footage_query": '
        '"<optional>"}]}\n\n' + "\n".join(blocks))
    try:
        raw = chat([{"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt}])
    except Exception:
        return {}
    data = _parse(raw)
    rows = (data or {}).get("choices")
    if not isinstance(rows, list):
        return {}
    valid = {m["beat"]: {c["template"] for c in m.get("candidates") or []}
             for m in menus}
    out = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            beat = int(r.get("beat"))
        except (TypeError, ValueError):
            continue
        tpl = str(r.get("template") or "")
        if beat in valid and tpl in valid[beat]:
            out[beat] = {"template": tpl,
                         "why": str(r.get("why") or "")[:220],
                         "footage_query": str(
                             r.get("footage_query") or "")[:80]}
    return out


def replan_choice(beat_no, line, failed_template, failure_note,
                  menu_templates, chat, taste=""):
    """One failed beat, after Taste QC: choose a DIFFERENT template
    from the menu. Returns {template, why} or None. This is the
    re-PLAN in the correction loop — a new decision, not a re-render
    of the failed one."""
    if chat is None or not menu_templates:
        return None
    prompt = (
        (taste or "") +
        f"\n\nBeat {beat_no} FAILED its frame check.\n"
        f"Line: \"{line}\"\nFailed visual: {failed_template} — "
        f"{failure_note}\nChoose a DIFFERENT template from this menu "
        "that will show the line's meaning clearly and fill the "
        "frame: " + "; ".join(menu_templates) +
        '\nReply with strict JSON: {"template": "<name>", "why": '
        '"<one sentence sharing words with the line>"}')
    try:
        raw = chat([{"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt}])
    except Exception:
        return None
    data = _parse(raw)
    tpl = str((data or {}).get("template") or "")
    if tpl and tpl in menu_templates and tpl != failed_template:
        return {"template": tpl,
                "why": str((data or {}).get("why") or "")[:220]}
    return None


if __name__ == "__main__":
    menus = [{"beat": 1, "line": "Psychologists call this the "
              "compliance reflex.", "role": "evidence",
              "analyst": {"emotion": "dry", "visual_opportunity":
                          "document"},
              "candidates": [{"template": "primary",
                              "asset_type": "motion graphic",
                              "why": "writer's visual"},
                             {"template": "evidence_document",
                              "asset_type": "document visual",
                              "why": "cited finding as a document"}]}]
    def stub(messages):
        return json.dumps({"choices": [
            {"beat": 1, "template": "evidence_document",
             "why": "psychologists' finding shown as the document it is"}]})
    got = choose_visuals(menus, stub)
    assert got[1]["template"] == "evidence_document", got
    assert choose_visuals(menus, lambda m: "junk") == {}
    print("visual_director self-check OK")
