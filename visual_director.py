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


def _clean_tpl(tpl, valid_set):
    """Normalise a model's template reply to a bare menu name.
    Models copy the menu's display form — "primary [motion graphic]"
    — bracket suffix and all (observed live 2026-11-15: every choice
    was silently discarded by exact-match validation and directing
    degraded to the v86 order). Strip the decoration; also accept a
    reply that begins with a valid name. "" when nothing matches."""
    tpl = str(tpl or "").strip()
    if tpl in valid_set:
        return tpl
    base = re.sub(r"\s*\[.*\]\s*$", "", tpl).strip()
    if base in valid_set:
        return base
    for v in valid_set:
        if tpl.startswith(v):
            return v
    return ""


def choose_visuals(menus, chat, taste="", beat_sheet=None):
    """menus: [{beat, line, role, analyst (dict|None), candidates:
    [{template, asset_type, why}]}] — one entry per beat, candidates in
    the deterministic preference order. Returns {beat_no: {template,
    why, footage_query}} for the beats the model decided; {} on any
    failure. Choices are ADVISORY: director.direct_plan still vetoes.
    """
    if not menus or chat is None:
        return {}
    # PROOF-FIX 1: the Visual Director reads the VISUAL slice of
    # the taste pack, never the whole 56K pack (the full pack 413'd
    # on the free channel and directing silently degraded to the
    # v86 deterministic order). A caller that still hands a full
    # pack gets the slice instead.
    if len(taste or "") > 12000:
        try:
            import pack_slicer as _ps
            taste = _ps.slice_for("visual")
        except Exception:
            pass
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
    except Exception as _e:
        _note_stage(False, f"LLM failed: {str(_e)[:80]}")
        return {}
    data = _parse(raw)
    rows = (data or {}).get("choices")
    if not isinstance(rows, list):
        _note_stage(False, "LLM reply unusable (no choices)")
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
        tpl = _clean_tpl(r.get("template"),
                         valid.get(beat) or set())
        if beat in valid and tpl:
            out[beat] = {"template": tpl,
                         "why": str(r.get("why") or "")[:220],
                         "footage_query": str(
                             r.get("footage_query") or "")[:80]}
    if out:
        _note_stage(True, f"LLM chose {len(out)}/{len(menus)} beat visuals")
    else:
        _note_stage(False, "LLM choices all failed validation — "
                           "deterministic order kept")
    return out


def _note_stage(ok, detail=""):
    """PROOF-FIX 1: ledger entry for the Visual Director — see
    story_analyst._note_stage."""
    try:
        import brain_status as _bs
        _bs.record("visual-director", ok, detail)
    except Exception:
        pass


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
    tpl = _clean_tpl((data or {}).get("template"),
                     set(menu_templates))
    if tpl and tpl != failed_template:
        return {"template": tpl,
                "why": str((data or {}).get("why") or "")[:220]}
    return None


def emit_hyperframes_compositions(plan, outdir, enabled=False, **kw):
    """v89 guarded wiring: convert a directed plan's graphics-carrying
    scenes into a HyperFrames scene script and emit the project via
    hyperframes_codegen. OFF by default — returns None and writes
    nothing unless enabled=True or JULIE_HYPERFRAMES_CODEGEN=1, so
    existing behaviour is unchanged.

    A plan scene participates only when it carries an explicit
    graphics spec — scene["graphics"] (one layer dict or a list of
    layer dicts; see hyperframes_codegen for the layer types) — plus
    a footage path in scene["footage_path"] / ["footage_file"] /
    ["asset"] (a string path; the plan-level footage pool dict is
    deliberately NOT read as a path) and a duration in
    scene["duration"] / ["duration_est_s"] / ["d"] (default 5.0).
    Scenes without a spec are skipped silently; scenes with a spec
    but no usable footage path are skipped and named in the returned
    report's flags. Returns the codegen report dict, or None when
    disabled or when no scene carried a graphics spec."""
    if not enabled and \
            os.environ.get("JULIE_HYPERFRAMES_CODEGEN", "") != "1":
        return None
    scenes = plan.get("scenes") if isinstance(plan, dict) else plan
    script, skipped = [], []
    for sc in scenes or []:
        if not isinstance(sc, dict):
            continue
        gfx = sc.get("graphics") or sc.get("hf_graphics")
        if not gfx:
            continue
        footage = None
        for key in ("footage_path", "footage_file", "asset"):
            if isinstance(sc.get(key), str) and sc.get(key):
                footage = sc[key]
                break
        if not footage:
            skipped.append(
                f"plan scene {sc.get('no', '?')}: graphics spec but "
                f"no footage path — skipped (graphics never replace "
                f"footage)")
            continue
        entry = {
            "footage": footage,
            "duration": float(sc.get("duration")
                              or sc.get("duration_est_s")
                              or sc.get("d") or 5.0),
            "layers": gfx if isinstance(gfx, list) else [gfx],
        }
        if sc.get("media_start") is not None:
            entry["media_start"] = float(sc["media_start"])
        script.append(entry)
    if not script:
        return None
    import hyperframes_codegen as _hfc
    report = _hfc.generate_project(script, outdir, **kw)
    if skipped:
        report["flags"] = list(report.get("flags") or []) + skipped
    return report


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
