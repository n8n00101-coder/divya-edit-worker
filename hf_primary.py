"""RENDERER PIVOT (Phase 5): HyperFrames as the PRIMARY renderer
for documentary longs.

Until now the picture layer was the widget/template renderer:
drawn counters, donuts and cards composed in PIL, with footage —
when it landed at all — pasted behind them. The v89 HyperFrames
Director codegen (HTML/CSS typography + motion graphics over real
footage, honesty rules baked into its templates) sat behind a
default-off emit flag that nothing in production ever turned on.

This module makes it the default visual layer for documentary
long beats:

- For every beat that HAS real footage, a one-scene HyperFrames
  project is generated from the directed plan (title / data_chart
  / map_card / lower_third layers chosen from the beat's own
  content) and rendered; the rendered span REPLACES that beat's
  span in the assembled raw video, before captions burn. The
  voice/music/caption stages are untouched.
- The widget renderer is DEMOTED, not deleted: it remains the
  fallback for beats codegen declines — pure-data beats with no
  footage (codegen hard-requires a footage asset), document beats
  (a document visual shows a REAL retrieved source through the
  compliance path — HyperFrames has no document layer, so the
  fake-document class cannot reappear here), and any beat whose
  project fails to generate or render.
- Guardrails ride along: an unsourced number renders through
  data_chart WITHOUT a source, which the template stamps
  "Source: NOT PROVIDED — unverified" on screen; map cards carry
  the hardcoded "Illustrative map — not to scale"; no placeholder
  avatars are ever composed as content.

Enablement: documentary longs (cfg kind == "long") unless the
spec excludes graphics, or JULIE_HYPERFRAMES_PRIMARY=0.

ROUND 5 (motion, effects, transitions): film 3's HF spans were
static cards joined by hard cuts — the templates animated their
text, but the FOOTAGE never moved and no beat ever transitioned.
Now, per beat: (1) a MOTION TREATMENT — still images and
measured-static clips get a keyframed push-in on the media
element; accent beats (a spoken number, an effect hit, the
chapter open) get a speedramp accent rendered by speedramp.py;
every treatment is logged in the report and any beat measured
static that received none is counted as untreated_static.
(2) a TRANSITION into the beat — the editing plan's own
transition field when it names one, else a rule default (dip
from black to open, dissolve into data, fade into maps, a
rotating slide/fade otherwise) — applied as real xfades in
swap_spans, duration-compensated so the chapter's timing (and
its voice sync) does not drift. (3) a MOTION AUDIT of the
swapped chapter (motion_audit.audit_video): beats whose sampled
frames do not change are named in the report as static — the
chapter's MOTION-STATIC compliance check (long_video) reads it.
JULIE_HF_TRANSITIONS=0 restores hard-cut concat.
"""

import os
import re
import subprocess

import anti_boring
import compliance
import hyperframes_codegen
import motion_audit
import speedramp

_PLACE_VISUALS = {"india_map", "world_dots", "map"}

# NEXT-ROUND (Fix 3 — HF TEXT WHITELIST): the second film's
# lower-thirds printed the plan's INTERNAL text — the Visual
# Director's line-descriptions ("the line is about time
# passing...") as microcopy, an internal emotion score as a data
# card ("EMOTION 0.1"), and the structural marker "NEXT" as an
# on-screen title. A composition may now only render
# VIEWER-FACING text: the scene's spoken line, its (sanitised)
# label, a number the line actually speaks together with its
# resolved source, or packaging/topic fields. Internal fields —
# the director's `why` rationale, analyst scores, structural
# markers — are structurally unrenderable: beat_layers never
# reads them, and a label that IS one is rejected, not printed.
_STRUCTURAL_LABELS = {
    "NEXT", "CHAPTER", "INTRO", "OUTRO", "TITLE", "END", "ENDING",
    "HOOK", "CTA", "TEASE", "TRANSITION", "EMOTION", "SCORE",
    "BEAT", "SCENE", "OPENING", "CLOSING", "INTERLUDE", "MONTAGE",
    "TITLE CARD", "CHAPTER CARD", "END CARD",
}
_INTERNAL_MARKERS = (
    "the line", "line is about", "line itself", "emotion",
    "score", "stage direction", "writer's", "writer’s",
    "description", "internal", "placeholder", "lorem",
    "visual opportunity", "turning point",
)


def _viewer_label(scene):
    """The scene's label, when it is fit to print — else ''.
    A label is viewer-facing only when it is short, is not a
    structural marker (NEXT / CHAPTER / EMOTION ...) and does
    not read as plan prose (a sentence describing the line)."""
    label = str((scene or {}).get("label") or "").strip()
    if not label:
        return ""
    if label.upper() in _STRUCTURAL_LABELS:
        return ""
    low = label.lower()
    if any(m in low for m in _INTERNAL_MARKERS):
        return ""
    if re.match(r"^(chapter|scene|beat|part)\s*\d*$", low):
        return ""
    if len(label) > 44 or len(label.split()) > 6:
        return ""
    return label


def _spoken_value(scene, num):
    """True when the scene's spoken line actually speaks this
    number. A plan-side value the narration never says (an
    analyst's emotion score, a counter nobody voices) is
    internal data, not a claim — it may not become a chart."""
    vo = str((scene or {}).get("vo") or "")
    if not vo:
        return False
    try:
        vals = {round(float(v), 4)
                for v, _u in compliance.spoken_numbers(vo)}
    except Exception:
        vals = set()
    return round(float(num), 4) in vals


def _vo_excerpt(scene, limit=70):
    """The scene's spoken line, trimmed — the one sub-line a
    lower-third may always carry (it is the caption text)."""
    vo = " ".join(str((scene or {}).get("vo") or "").split())
    if len(vo) <= limit:
        return vo
    cut = vo[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def enabled_for(cfg):
    if os.environ.get("JULIE_HYPERFRAMES_PRIMARY", "1") == "0":
        return False
    if not cfg or cfg.get("kind") != "long":
        return False
    excludes = cfg.get("excludes") or []
    return "graphics" not in excludes and "hyperframes" not in excludes


# ------------------------------------------------- ROUND 5: motion
# xfade names this ffmpeg generation supports (verified against
# the render host's `ffmpeg -h filter=xfade`).
_XFADE_OK = {"fade", "fadeblack", "fadewhite", "dissolve",
             "slideleft", "slideright", "slideup", "slidedown",
             "wipeleft", "wiperight", "circleopen", "circleclose",
             "zoomin", "pixelize", "radial", "hblur"}
_RULE_ROTATION = ("fade", "slideleft", "dissolve", "slideright")


def _xfade_for(plan_name, idx, layer_types, taste=False):
    """The xfade transition INTO beat `idx`: the editing plan's
    own transition name when it maps to a real xfade, else a
    rule default. A hard cut is never the default — film 3 cut
    every boundary because nothing ever chose otherwise."""
    n = str(plan_name or "").lower().replace("-", "_").replace(" ", "_")
    if n and n not in ("cut", "none", "hard_cut"):
        if "black" in n or "dip" in n:
            return "fadeblack"
        if "slide" in n and "right" in n:
            return "slideright"
        if "slide" in n:
            return "slideleft"
        if "wipe" in n:
            return "wipeleft"
        if "zoom" in n:
            return "zoomin"
        if "circle" in n:
            return "circleopen"
        if "dissolve" in n:
            return "dissolve"
        if "fade" in n:
            return "fade"
        if "match" in n:
            # a match cut is an editorial alignment, not an
            # ffmpeg blend — dissolve is the closest honest
            # rendering of the intent at a beat boundary.
            return "dissolve"
    if idx == 0:
        # Taste films open on content, never a black dip (the sheet
        # hook is footage from the first frame).
        return "fade" if taste else "fadeblack"
    if "data_chart" in (layer_types or []):
        return "dissolve"
    if "map_card" in (layer_types or []):
        return "fade"
    return _RULE_ROTATION[idx % len(_RULE_ROTATION)]


def _speed_accent(path, start, dur, proj_dir):
    """Render a speedramp accent of the beat's footage window:
    ease to 0.8x over the first 45%, back through 1.15x — the
    output is >= the window length (the composition trims), so
    the beat's timing is preserved. Returns the treated path or
    None (the caller falls back and logs the failure)."""
    try:
        os.makedirs(proj_dir, exist_ok=True)
        window = os.path.join(proj_dir, "accent_src.mp4")
        span = float(dur) + 0.6
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss",
             f"{float(start):.3f}", "-i", str(path), "-t",
             f"{span:.3f}", "-c:v", "libx264", "-pix_fmt",
             "yuv420p", "-an", window],
            check=True, capture_output=True, timeout=300)
        spec = [{"type": "speed", "factor": 0.8,
                 "duration": round(0.45 * span, 3)},
                {"type": "speed", "factor": 1.15,
                 "duration": round(0.55 * span, 3)}]
        out = os.path.join(proj_dir, "accent.mp4")
        speedramp.render(window, out, spec)
        return out
    except Exception:
        return None


def _treat_beat(scene, path, media_start, dur, proj_dir, idx,
                layers, failures):
    """Decide + apply the beat's motion treatment. Returns
    (treatment|None, media_motion|None, footage_path,
    media_start, measured_static|None). A still image is static
    by nature; a video clip is MEASURED (motion_audit) — an
    unmeasurable clip is treated as unknown, never as moving."""
    ext = os.path.splitext(str(path))[1].lower()
    if ext in hyperframes_codegen._IMAGE_EXTS:
        return ({"kind": "push_in", "source": "still"},
                "push_in", path, media_start, True)
    motion = motion_audit.clip_motion(path, media_start, dur)
    measured_static = motion.get("static")
    accent = bool(scene.get("_effect_choice")) or idx == 0 or any(
        l.get("type") == "data_chart" for l in layers or [])
    if accent:
        treated = _speed_accent(path, media_start, dur, proj_dir)
        if treated:
            return ({"kind": "speed_accent", "source": "accent",
                     "clip_max_diff": motion.get("max_diff")},
                    None, treated, 0.0, measured_static)
        failures.append({"scene": idx + 1,
                         "kind": "speed_accent",
                         "fallback": "punch_in"})
        return ({"kind": "punch_in", "source": "accent_fallback"},
                "punch_in", path, media_start, measured_static)
    if measured_static:
        return ({"kind": "push_in", "source": "static_clip",
                 "clip_max_diff": motion.get("max_diff")},
                "push_in", path, media_start, True)
    return (None, None, path, media_start, measured_static)


def _resolved_source(scene, plan):
    research = plan.get("research")
    if research is not None:
        return anti_boring.resolved_source_title(scene, research)
    return str(scene.get("source") or "").strip()


def _number(value):
    try:
        return float(str(value).replace(",", "").rstrip("%x"))
    except (TypeError, ValueError):
        return None


def beat_layers(scene, plan, first=False):
    """The HyperFrames layers for one beat, chosen from the beat's
    own directed content — or None when codegen declines the beat
    (document beats: the compliance path renders the REAL
    retrieved source; avatar/placeholder content: never composed).
    """
    vis = compliance.effective_visual(scene)
    if vis == "document":
        return None
    # NEXT-ROUND Fix 3: every string below comes from the
    # whitelist — sanitised label, spoken number + resolved
    # source, topic/title packaging fields, or the spoken line
    # itself. scene["why"] (the director's rationale) and any
    # unspoken plan value are never read here again.
    label = _viewer_label(scene)
    value = str(scene.get("value") or "").strip()
    layers = []
    num = _number(value) if value else None
    taste_profile = str((plan or {}).get("taste_profile") or "")
    graphic_type = str(scene.get("graphic_type") or "")
    if graphic_type == "diagram":
        graphic_type = str(scene.get("diagram_kind") or "wave")
    if taste_profile and scene.get("graphic_locked"):
        # Variety repair demoted this beat to footage: no card/chart
        # may reappear at render; a viewer-safe label may ride only.
        if label:
            return [{"type": "lower_third", "name": label.title(),
                     "role": ""}]
        return None
    if taste_profile and graphic_type in ("wave", "growth", "checks", "arrow"):
        layers.append({
            "type": "diagram",
            "kind": graphic_type,
            "title": label.title(),
            "items": [str(x)[:48] for x in (scene.get("diagram_items") or [])
                      if str(x).strip()][:4],
        })
        return layers
    if taste_profile == "wtu_long_sheet" and num is not None \
            and _spoken_value(scene, num):
        src = _resolved_source(scene, plan)
        if src:
            layers.append({
                "type": "source_card",
                "kicker": "THE RESEARCH",
                "headline": label.title() or "What the study found",
                "stat": value,
                "unit": str(scene.get("unit") or ""),
                "quote": _vo_excerpt(scene, 110),
                "source": src,
            })
            return layers
    if num is not None and _spoken_value(scene, num):
        src = _resolved_source(scene, plan)
        layers.append({
            "type": "data_chart",
            "title": label.title() or "In numbers",
            "subtitle": "",
            "bars": [{"label": label.title() or "Value",
                      "value": num, "unit": "",
                      "display": value}],
            "note": "",
            # an empty source is deliberate: the template renders
            # the visible "NOT PROVIDED — unverified" placeholder
            "source": src,
        })
    elif str(scene.get("lib_visual") or "") in _PLACE_VISUALS:
        layers.append({
            "type": "map_card",
            "title": label.title() or str(plan.get("topic") or ""),
            "label": label.title(),
            "description": "",
        })
    elif first and taste_profile == "wtu_long_sheet":
        # Sheet style: the first beat is footage + captions, never a
        # title card. A viewer-safe label may ride as a lower-third.
        if label:
            layers.append({
                "type": "lower_third",
                "name": label.title(),
                "role": "",
            })
    elif first:
        layers.append({
            "type": "title",
            "kicker": str(plan.get("topic") or "").upper()[:60],
            "headline": (label.title()
                         or str(plan.get("title") or "")).upper(),
            "accent": "",
            "sub": "",
        })
    elif label:
        src = _resolved_source(scene, plan)
        layers.append({
            "type": "lower_third",
            "name": label.title(),
            "role": (f"Source: {src}" if src
                     else ("" if taste_profile else _vo_excerpt(scene))),
        })
    return layers or None


def plan_beats(p, wd, cfg):
    """Decide the HyperFrames beats for a directed plan. Returns
    (beats, report): beats = [{scene, start, duration, footage,
    media_start, layers, project_dir}] for every beat with real
    footage AND a layer decision; the report counts the declines
    (no footage / codegen declined) honestly."""
    W = int(cfg.get("width") or 1920)
    H = int(cfg.get("height") or 1080)
    pool = p.get("_footage_pool")
    by_scene = {}
    if pool is not None:
        for a in getattr(pool, "assignments", []) or []:
            if a.get("path"):
                by_scene[int(a.get("scene") or 0)] = a
    starts = p.get("starts") or []
    plan_trs = p.get("transitions") or []
    beats, declined = [], {"no_footage": 0, "declined": 0,
                           "no_timing": 0}
    treatments, treat_failed, untreated_static = [], [], 0
    for i, sc in enumerate(p.get("scenes") or []):
        a = by_scene.get(i + 1)
        if not a or not os.path.isfile(str(a["path"])):
            declined["no_footage"] += 1
            continue
        if i >= len(starts):
            declined["no_timing"] += 1
            continue
        layers = beat_layers(sc, p, first=(i == 0))
        if not layers:
            declined["declined"] += 1
            continue
        dur = float(sc.get("d") or 6)
        proj = os.path.join(wd, "hf_primary", f"beat{i + 1}")
        # ROUND 5: motion treatment first — it can replace the
        # beat's footage (speedramp accent) or mark the media
        # element for a keyframed push (still / static clip).
        treatment, media_motion, fpath, mstart, mstatic = \
            _treat_beat(sc, str(a["path"]),
                        float(a.get("start") or 0), dur, proj, i,
                        layers, treat_failed)
        if treatment:
            treatments.append({"scene": i + 1, **treatment})
        elif mstatic:
            untreated_static += 1
        script = [{"footage": str(fpath), "duration": dur,
                   "media_start": mstart, "layers": layers}]
        if media_motion:
            script[0]["media_motion"] = media_motion
        rep = hyperframes_codegen.generate_project(
            script, proj, width=W, height=H)
        # the transition INTO this beat: doc.plan stamps each
        # scene with the transition that brings the viewer into
        # it (scene["transition"]); the plan's per-boundary list
        # is the fallback source. Else a rule default.
        plan_name = sc.get("transition") or (
            plan_trs[i - 1] if 0 < i <= len(plan_trs) else None)
        beats.append({"scene": i + 1, "start": float(starts[i]),
                      "duration": dur, "project_dir": proj,
                      "flags": rep.get("flags") or [],
                      "transition": _xfade_for(
                          plan_name, i,
                          [l.get("type") for l in layers],
                          taste=bool(p.get("taste_profile"))),
                      "treatment": treatment})
    report = {"beats_considered": len(p.get("scenes") or []),
              "beats_ready": len(beats), "declined": declined,
              "motion_treatments": treatments,
              "motion_treatment_failed": treat_failed,
              "untreated_static": untreated_static}
    return beats, report


def _probe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30)
    return float(r.stdout.strip())


def swap_spans(raw_path, spans, out_path, width, height, fps=30,
               transitions=None):
    """Replace [start, start+duration) spans of raw_path with the
    rendered beat clips (spans = [(start, duration, clip_path)],
    sorted, non-overlapping), normalising every segment to the
    canvas. Video only — the pipeline mixes audio afterwards.

    ROUND 5: segments are fitted CROP-TO-FILL (never stretched —
    scale-to-cover + centre crop), and beat boundaries carry
    real transitions: `transitions` (parallel to spans) names
    the xfade INTO each span; raw segments default to a fade.
    The xfade chain is duration-compensated — every segment but
    the last is clone-padded by the transition length and each
    offset is the cumulative REAL duration, so the output keeps
    the input's total length and the voice stays in sync. If
    the xfade graph fails, the swap retries as a plain concat
    (the failure is printed, never silent)."""
    total = _probe_duration(raw_path)
    spans = sorted(s for s in spans if s[0] < total)
    if not spans:
        return False
    trs = list(transitions or [])
    # segments: (input_index, trim_filter, duration, transition_in)
    segs, cursor = [], 0.0
    norm = (f"fps={fps},scale={width}:{height}:"
            f"force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,format=yuv420p")
    for k, (s, d, _clip) in enumerate(spans):
        if s > cursor + 0.01:
            segs.append((0, f"trim=start={cursor:.3f}:end={s:.3f}",
                         s - cursor, "fade"))
        segs.append((k + 1, f"trim=duration={d:.3f}", d,
                     trs[k] if k < len(trs) and trs[k] else "fade"))
        cursor = s + d
    if total > cursor + 0.01:
        segs.append((0, f"trim=start={cursor:.3f}:end={total:.3f}",
                     total - cursor, "fade"))

    def build(use_xfade, td):
        filters = []
        for j, (inp, trim, d, _t) in enumerate(segs):
            f = (f"[{inp}:v]{trim},setpts=PTS-STARTPTS,{norm},"
                 f"settb=AVTB")
            if use_xfade and j < len(segs) - 1:
                f += f",tpad=stop_mode=clone:stop_duration={td:.3f}"
            filters.append(f + f"[v{j}]")
        if not use_xfade:
            filters.append(
                "".join(f"[v{j}]" for j in range(len(segs)))
                + f"concat=n={len(segs)}:v=1:a=0[out]")
            return ";".join(filters)
        acc, offset = "v0", 0.0
        for j in range(1, len(segs)):
            offset += segs[j - 1][2]
            name = segs[j][3] if segs[j][3] in _XFADE_OK else "fade"
            filters.append(
                f"[{acc}][v{j}]xfade=transition={name}:"
                f"duration={td:.3f}:offset={offset:.3f}[x{j}]")
            acc = f"x{j}"
        filters.append(f"[{acc}]null[out]")
        return ";".join(filters)

    base = ["ffmpeg", "-y", "-loglevel", "error", "-i", raw_path]
    for _, _, clip in spans:
        base += ["-i", clip]
    tail = ["-map", "[out]", "-c:v", "libx264", "-preset", "medium",
            "-crf", "18", out_path]
    want_xfade = (len(segs) > 1
                  and os.environ.get("JULIE_HF_TRANSITIONS", "1") != "0")
    if want_xfade:
        shortest = min(d for _i, _t, d, _n in segs)
        td = 0.35 if shortest >= 0.8 else max(0.12, shortest * 0.3)
        if shortest >= 0.3:
            r = subprocess.run(
                base + ["-filter_complex", build(True, td)] + tail,
                capture_output=True, text=True, timeout=1800)
            if r.returncode == 0:
                return True
            print("hf swap: xfade graph failed — retrying as "
                  f"concat ({(r.stderr or '')[-200:]})")
    subprocess.run(base + ["-filter_complex", build(False, 0.0)]
                   + tail, check=True, timeout=1800,
                   capture_output=True, text=True)
    return True


def render_and_swap(p, wd, cfg, raw_path):
    """The pipeline entry: generate + render the HyperFrames beats
    for this chapter and swap them into the assembled raw video.
    Returns the report (also stored on the plan by the caller).
    Any beat whose render fails keeps the widget renderer's span —
    counted in the report, never silent."""
    W = int(cfg.get("width") or 1920)
    H = int(cfg.get("height") or 1080)
    beats, report = plan_beats(p, wd, cfg)
    report["beats_rendered"] = 0
    report["render_failed"] = []
    spans, span_trs, rendered = [], [], []
    for b in beats:
        out = os.path.join(b["project_dir"], "hf_beat.mp4")
        try:
            hyperframes_codegen.render_project(
                b["project_dir"], output=out,
                tmpdir=os.path.join(wd, ".hyperframes-tmp"),
                timeout=600)
            spans.append((b["start"], b["duration"], out))
            span_trs.append(b.get("transition"))
            rendered.append(b)
            report["beats_rendered"] += 1
        except Exception as e:
            report["render_failed"].append(
                {"scene": b["scene"], "error": str(e)[:140]})
    report["transitions"] = [b.get("transition") for b in rendered]
    if spans:
        swapped = os.path.join(wd, "raw_hf.mp4")
        if swap_spans(raw_path, spans, swapped, W, H,
                      transitions=span_trs):
            os.replace(swapped, raw_path)
            report["swapped"] = True
            # ROUND 5 (Fix 2): the motion audit — sample the
            # swapped chapter inside every rendered beat and
            # measure pixel change. A beat that does not move
            # is named here; long_video turns an over-budget
            # static share into a MOTION-STATIC fix-round FAIL.
            try:
                report["motion_audit"] = motion_audit.audit_video(
                    raw_path,
                    [{"scene": b["scene"], "start": b["start"],
                      "duration": b["duration"]} for b in rendered])
            except Exception as e:
                report["motion_audit"] = {"error": str(e)[:140]}
    return report
