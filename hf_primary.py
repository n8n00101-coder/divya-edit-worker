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
"""

import os
import subprocess

import anti_boring
import compliance
import hyperframes_codegen

_PLACE_VISUALS = {"india_map", "world_dots", "map"}


def enabled_for(cfg):
    if os.environ.get("JULIE_HYPERFRAMES_PRIMARY", "1") == "0":
        return False
    if not cfg or cfg.get("kind") != "long":
        return False
    excludes = cfg.get("excludes") or []
    return "graphics" not in excludes and "hyperframes" not in excludes


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
    label = str(scene.get("label") or "").strip()
    value = str(scene.get("value") or "").strip()
    layers = []
    num = _number(value) if value else None
    if num is not None:
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
        layers.append({
            "type": "lower_third",
            "name": label.title(),
            "role": str(scene.get("why") or "")[:70],
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
    beats, declined = [], {"no_footage": 0, "declined": 0,
                           "no_timing": 0}
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
        script = [{"footage": str(a["path"]), "duration": dur,
                   "media_start": float(a.get("start") or 0),
                   "layers": layers}]
        rep = hyperframes_codegen.generate_project(
            script, proj, width=W, height=H)
        beats.append({"scene": i + 1, "start": float(starts[i]),
                      "duration": dur, "project_dir": proj,
                      "flags": rep.get("flags") or []})
    report = {"beats_considered": len(p.get("scenes") or []),
              "beats_ready": len(beats), "declined": declined}
    return beats, report


def _probe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30)
    return float(r.stdout.strip())


def swap_spans(raw_path, spans, out_path, width, height, fps=30):
    """Replace [start, start+duration) spans of raw_path with the
    rendered beat clips (spans = [(start, duration, clip_path)],
    sorted, non-overlapping), normalising every segment to the
    canvas. Video only — the pipeline mixes audio afterwards."""
    total = _probe_duration(raw_path)
    spans = sorted(s for s in spans if s[0] < total)
    if not spans:
        return False
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", raw_path]
    for _, _, clip in spans:
        cmd += ["-i", clip]
    filters, labels, cursor = [], [], 0.0
    norm = f"fps={fps},scale={width}:{height},setsar=1,format=yuv420p"

    def raw_seg(a, b, tag):
        filters.append(
            f"[0:v]trim=start={a:.3f}:end={b:.3f},"
            f"setpts=PTS-STARTPTS,{norm}[{tag}]")
        labels.append(tag)

    for k, (s, d, _clip) in enumerate(spans):
        if s > cursor + 0.01:
            raw_seg(cursor, s, f"s{len(labels)}")
        filters.append(
            f"[{k + 1}:v]trim=duration={d:.3f},"
            f"setpts=PTS-STARTPTS,{norm}[s{len(labels)}]")
        labels.append(f"s{len(labels)}")
        cursor = s + d
    if total > cursor + 0.01:
        raw_seg(cursor, total, f"s{len(labels)}")
    filters.append(
        "".join(f"[{t}]" for t in labels)
        + f"concat=n={len(labels)}:v=1:a=0[out]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            out_path]
    subprocess.run(cmd, check=True, timeout=1800,
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
    spans = []
    for b in beats:
        out = os.path.join(b["project_dir"], "hf_beat.mp4")
        try:
            hyperframes_codegen.render_project(
                b["project_dir"], output=out,
                tmpdir=os.path.join(wd, ".hyperframes-tmp"),
                timeout=600)
            spans.append((b["start"], b["duration"], out))
            report["beats_rendered"] += 1
        except Exception as e:
            report["render_failed"].append(
                {"scene": b["scene"], "error": str(e)[:140]})
    if spans:
        swapped = os.path.join(wd, "raw_hf.mp4")
        if swap_spans(raw_path, spans, swapped, W, H):
            os.replace(swapped, raw_path)
            report["swapped"] = True
    return report
