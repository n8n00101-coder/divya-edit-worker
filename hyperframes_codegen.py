"""hyperframes_codegen.py — Julie v89: HyperFrames Director codegen.

The Visual Director must EMIT HyperFrames compositions from a scene
script automatically — no hand-authored HTML per scene. This module
is that codegen step (the integration shape the v89 spike README
promised): a scene script goes in, a complete HyperFrames project
(index.html + compositions/ + assets/ + hyperframes.json, structured
exactly like hyperframes_spike/) comes out, and render_project()
invokes the same render path the spike used:

    TMPDIR=<big-disk dir> npx --yes hyperframes@0.9.55 render

Scene script shape (plain data — dicts/lists/str/float only):

    script = [
      {"footage": "path/to/real_clip.webm",      # video or image, REQUIRED
       "duration": 5.0,                          # seconds, REQUIRED-ish
       "media_start": 0.0,                       # optional offset into
                                                 # the footage file
       "layers": [ <layer>, ... ]},              # graphics OVER footage
      ...
    ]

Layer types (all text/data comes from the script, never hand-written
HTML; templates below only supply layout + motion):

  title           {"type": "title", "kicker": "...", "headline": "...",
                   "accent": "<word in headline to colour>",
                   "sub": "...", "lines": ["...", "..."]  # optional}
  data_chart      {"type": "data_chart", "title": "...",
                   "subtitle": "...",
                   "bars": [{"label": "1993", "value": 2.1,
                             "unit": "mm / yr", "display": "2.1"}],
                   "note": "...", "source": "NASA ..."}
  map_card        {"type": "map_card", "title": "...", "label": "...",
                   "description": "..."}
  kinetic_caption {"type": "kinetic_caption",
                   "phrase": "But how fast?", "accent": "fast?",
                   "start": 0.6, "interval": 0.55}
                  # or explicit timings:
                  # "words": [{"text": "But", "at": 0.6}, ...]
  lower_third     {"type": "lower_third", "name": "...", "role": "..."}
  source_card     {"type": "source_card", "kicker": "...",
                   "headline": "...", "stat": "46", "unit": "%",
                   "quote": "...", "source": "Gilovich et al. (2000)"}
  diagram         {"type": "diagram", "kind": "wave|growth|checks|arrow",
                   "title": "...", "items": ["...", "..."]}

Honesty rules, baked into the templates (not left to the caller):
  * Every scene REQUIRES a real footage/image asset — graphics are
    overlays OVER footage, never a replacement frame. A scene with
    no existing footage file is a hard error.
  * A data_chart REQUIRES a source string. Without one the chart is
    still generated (so the defect is visible, not silent) but the
    source line renders as an explicit "Source: NOT PROVIDED —
    unverified" placeholder AND the omission is flagged in the
    generate report.
  * A map_card ALWAYS carries the line "Illustrative map — not to
    scale" — it is hardcoded in the template; the script cannot
    remove or override it. The SVG is a generic stylised coastline,
    never presented as real geography.

No audio: voice/music remain Julie's existing pipeline stages, as in
the spike. Fonts Oswald + Inter resolve from the HyperFrames bundle
by name, as in the spike.
"""

import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

HF_VERSION = "0.9.55"
GSAP_CDN = "https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"
MAP_HONESTY_LABEL = "Illustrative map \u2014 not to scale"
MISSING_SOURCE_LINE = "Source: NOT PROVIDED \u2014 unverified"

_VIDEO_EXTS = {".webm", ".mp4", ".mov", ".m4v", ".ogv"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ---------------------------------------------------------------- util

def _esc(text):
    return html.escape(str(text if text is not None else ""), quote=True)


def _t(v):
    """Format a seconds value the way the spike writes it (15, 0.5)."""
    s = f"{float(v):.3f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "julie-hyperframes").lower())
    return s.strip("-") or "julie-hyperframes"


def _decimals(value):
    s = repr(float(value))
    if "." in s and "e" not in s and "E" not in s:
        frac = s.split(".")[1].rstrip("0")
        return min(3, len(frac))
    return 0


def _display_decimals(display, value):
    """Decimals for the count-up: the DISPLAY string's precision wins
    (a spoken '46%' must count 0..46, never flash '46.0' because the
    float repr carried a trailing zero)."""
    m = re.search(r"\d[\d,]*(?:\.(\d+))?", str(display or ""))
    if m:
        return min(3, len(m.group(1) or ""))
    return _decimals(value)


# ------------------------------------------------------- layer templates
# Each returns (css, body_html, js_lines). All element ids/classes are
# prefixed per scene+layer so layers compose inside one scene file.

def _safe_px(scale):
    """Text safe margin: no text container may sit closer than this
    to a frame edge (120 px at 1920 wide — the taste caption margin
    is 115 px; text layers keep the same discipline)."""
    return int(120 * scale)


def text_edge_violations(content, width=1920):
    """Deterministic text-edge audit over one composition's CSS:
    every absolutely-positioned text container must keep the safe
    margin on both sides. Full-bleed media/scrim/vignette layers
    are exempt (they carry no text). Returns violation strings."""
    safe = max(80, int(0.06 * width))
    out = []
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", str(content)):
        sel = sel.strip()
        if "position: absolute" not in body:
            continue
        if any(x in sel for x in ("-media", "-scrim", "-vig", "#root")):
            continue

        def _px(name):
            m = re.search(rf"{name}:\s*(\d+)px", body)
            return int(m.group(1)) if m else None

        left, right = _px("left"), _px("right")
        w = _px("width") or _px("max-width")
        if left is not None and left < safe:
            out.append(f"{sel}: left {left}px < safe {safe}px")
        if right is not None and right < safe:
            out.append(f"{sel}: right {right}px < safe {safe}px")
        if left is not None and w is not None \
                and left + w > width - safe:
            out.append(f"{sel}: left+width {left + w}px crosses "
                       f"safe right edge {width - safe}px")
    return out


def _layer_title(spec, p, dur, track, scale):
    kicker = str(spec.get("kicker") or "")
    headline = str(spec.get("headline") or "")
    accent = str(spec.get("accent") or "")
    sub = str(spec.get("sub") or "")
    lines = spec.get("lines")
    if not lines:
        words = headline.split()
        if len(words) <= 1:
            lines = [headline] if headline else []
        else:
            cut = (len(words) + 1) // 2
            lines = [" ".join(words[:cut]), " ".join(words[cut:])]
    longest = max((len(str(ln)) for ln in lines), default=1)
    fs = 158 if longest <= 15 else max(84, int(158 * 15 / longest))
    fs = int(fs * scale)

    def _line_html(ln):
        out = []
        for w in str(ln).split():
            if accent and w.strip(".,!?'\"").lower() == \
                    accent.strip(".,!?'\"").lower():
                out.append(f'<span class="accent">{_esc(w)}</span>')
            else:
                out.append(_esc(w))
        return " ".join(out)

    css = f"""
    #{p}-ttl-block {{ position: absolute; left: {_safe_px(scale)}px;
      bottom: {int(190*scale)}px; width: {int(1680*scale)}px; }}
    #{p}-ttl-krow {{ display: flex; align-items: center;
      gap: {int(26*scale)}px; }}
    #{p}-ttl-rule {{ width: {int(120*scale)}px; height: 5px;
      background: #ffb340; transform-origin: left center; flex: 0 0 auto; }}
    #{p}-ttl-kicker {{ font-family: Inter, sans-serif;
      font-size: {int(30*scale)}px; font-weight: 700;
      letter-spacing: {int(12*scale)}px; color: #ffb340;
      text-shadow: 0 2px 14px rgba(0,0,0,0.8);
      min-width: 0; overflow-wrap: anywhere; }}
    .{p}-ttl-mask {{ overflow: hidden; }}
    .{p}-ttl-line {{ font-family: Oswald, sans-serif; font-weight: 700;
      font-size: {fs}px; line-height: 1.04; letter-spacing: 1px;
      color: #ffffff; text-transform: uppercase;
      overflow-wrap: anywhere; }}
    .{p}-ttl-line .accent {{ color: #ffb340; }}
    #{p}-ttl-sub {{ margin-top: {int(26*scale)}px;
      font-family: Inter, sans-serif; font-size: {int(41*scale)}px;
      color: rgba(255,255,255,0.92);
      text-shadow: 0 2px 14px rgba(0,0,0,0.8);
      overflow-wrap: anywhere; }}"""
    parts = [f'<div id="{p}-ttl-block" class="clip" data-start="0" '
             f'data-duration="{_t(dur)}" data-track-index="{track}">']
    if kicker:
        parts.append(
            f'<div id="{p}-ttl-krow"><div id="{p}-ttl-rule"></div>'
            f'<div id="{p}-ttl-kicker">{_esc(kicker)}</div></div>')
    for i, ln in enumerate(lines):
        parts.append(f'<div class="{p}-ttl-mask"><div class="{p}-ttl-line" '
                     f'id="{p}-ttl-line{i}">{_line_html(ln)}</div></div>')
    if sub:
        parts.append(f'<div id="{p}-ttl-sub">{_esc(sub)}</div>')
    parts.append("</div>")
    js = []
    if kicker:
        js.append(f'tl.fromTo("#{p}-ttl-rule", {{scaleX: 0}}, '
                  f'{{scaleX: 1, duration: 0.7, ease: "power3.out"}}, 0.5);')
        js.append(f'tl.fromTo("#{p}-ttl-kicker", {{opacity: 0, x: -24}}, '
                  f'{{opacity: 1, x: 0, duration: 0.6, ease: "power3.out"}}, 0.65);')
    for i in range(len(lines)):
        js.append(f'tl.fromTo("#{p}-ttl-line{i}", {{yPercent: 110}}, '
                  f'{{yPercent: 0, duration: 0.85, ease: "power4.out"}}, '
                  f'{_t(0.8 + 0.18 * i)});')
    if sub:
        js.append(f'tl.fromTo("#{p}-ttl-sub", {{opacity: 0, y: 26}}, '
                  f'{{opacity: 1, y: 0, duration: 0.7, ease: "power3.out"}}, 1.9);')
    return css, "".join(parts), js


def _layer_data_chart(spec, p, dur, track, scale, flags, scene_no):
    title = str(spec.get("title") or "")
    subtitle = str(spec.get("subtitle") or "")
    bars = [b for b in (spec.get("bars") or []) if isinstance(b, dict)]
    note = str(spec.get("note") or "")
    source = str(spec.get("source") or "").strip()
    source_missing = not source
    if source_missing:
        flags.append(
            f"scene {scene_no}: data_chart has NO source — rendered "
            f"with the explicit placeholder '{MISSING_SOURCE_LINE}'")
        source_line = MISSING_SOURCE_LINE
    else:
        source_line = source if source.lower().startswith("source") \
            else "Source: " + source
    maxv = max((abs(float(b.get("value") or 0)) for b in bars),
               default=0) or 1.0
    maxw = 560 * scale
    colours = ["#7fb2d9", "#ffb340", "#8fd18b", "#e58fb1"]

    css = f"""
    #{p}-dat-panel {{ position: absolute; right: {_safe_px(scale)}px;
      top: {int(120*scale)}px; width: {int(700*scale)}px;
      padding: {int(52*scale)}px {int(56*scale)}px {int(44*scale)}px;
      background: rgba(8,14,20,0.78);
      border: 1px solid rgba(255,255,255,0.16); border-radius: 18px; }}
    #{p}-dat-title {{ font-family: Oswald, sans-serif; font-weight: 600;
      font-size: {int(44*scale)}px; letter-spacing: 2px; color: #ffffff;
      text-transform: uppercase; overflow-wrap: anywhere; }}
    #{p}-dat-sub {{ margin-top: 8px; font-family: Inter, sans-serif;
      font-size: {int(28*scale)}px; color: rgba(255,255,255,0.75);
      overflow-wrap: anywhere; }}
    .{p}-dat-row {{ margin-top: {int(40*scale)}px; }}
    .{p}-dat-rowhead {{ display: flex; justify-content: space-between;
      align-items: baseline; font-family: Inter, sans-serif;
      gap: {int(16*scale)}px; }}
    .{p}-dat-label {{ font-size: {int(30*scale)}px; font-weight: 700;
      color: #ffffff; letter-spacing: 2px; min-width: 0;
      overflow-wrap: anywhere; }}
    .{p}-dat-val {{ font-family: Oswald, sans-serif;
      font-size: {int(46*scale)}px; font-weight: 600; color: #ffffff;
      min-width: 0; overflow-wrap: anywhere; }}
    .{p}-dat-val small {{ font-size: {int(28*scale)}px;
      color: rgba(255,255,255,0.7); }}
    .{p}-dat-barbg {{ margin-top: 12px; height: {int(34*scale)}px;
      background: rgba(255,255,255,0.13); border-radius: 6px;
      overflow: hidden; }}
    .{p}-dat-bar {{ height: 100%; border-radius: 6px;
      transform-origin: left center; }}
    #{p}-dat-note {{ margin-top: {int(42*scale)}px;
      font-family: Inter, sans-serif; font-size: {int(29*scale)}px;
      font-weight: 700; color: #ffb340; }}
    #{p}-dat-src {{ margin-top: {int(22*scale)}px;
      font-family: Inter, sans-serif; font-size: {int(24*scale)}px;
      color: rgba(255,255,255,0.5); }}
    #{p}-dat-src.missing {{ color: #ff8a75; font-weight: 700; }}"""
    parts = [f'<div id="{p}-dat-panel" class="clip" data-start="0" '
             f'data-duration="{_t(dur)}" data-track-index="{track}">']
    if title:
        parts.append(f'<div id="{p}-dat-title">{_esc(title)}</div>')
    if subtitle:
        parts.append(f'<div id="{p}-dat-sub">{_esc(subtitle)}</div>')
    for i, b in enumerate(bars):
        w = int(maxw * abs(float(b.get("value") or 0)) / maxv)
        unit = str(b.get("unit") or "")
        parts.append(
            f'<div class="{p}-dat-row"><div class="{p}-dat-rowhead">'
            f'<div class="{p}-dat-label">{_esc(b.get("label"))}</div>'
            f'<div class="{p}-dat-val"><span id="{p}-dat-v{i}">0</span>'
            + (f' <small>{_esc(unit)}</small>' if unit else "")
            + f'</div></div><div class="{p}-dat-barbg">'
              f'<div class="{p}-dat-bar" id="{p}-dat-bar{i}" '
              f'style="width: {w}px; background: '
              f'{colours[i % len(colours)]};"></div></div></div>')
    if note:
        parts.append(f'<div id="{p}-dat-note">{_esc(note)}</div>')
    parts.append(
        f'<div id="{p}-dat-src"'
        + (' class="missing" data-source-missing="true"'
           if source_missing else "")
        + f'>{_esc(source_line)}</div>')
    parts.append("</div>")

    js = [f'tl.fromTo("#{p}-dat-panel", {{opacity: 0, x: 60}}, '
          f'{{opacity: 1, x: 0, duration: 0.7, ease: "power3.out"}}, 0.4);']
    t = 0.9
    for i, b in enumerate(bars):
        v = float(b.get("value") or 0)
        disp = str(b.get("display") or "")
        dec = _display_decimals(disp, b.get("value") or 0)
        js.append(f'tl.fromTo("#{p}-dat-bar{i}", {{scaleX: 0}}, '
                  f'{{scaleX: 1, duration: 0.85, ease: "power3.inOut"}}, '
                  f'{_t(t)});')
        js.append(f'const c{p}{i} = {{v: 0}};')
        js.append(
            f'tl.to(c{p}{i}, {{v: {v!r}, duration: 0.85, '
            f'ease: "power3.inOut", onUpdate: function () {{ '
            f'document.querySelector("#{p}-dat-v{i}").textContent = '
            f'c{p}{i}.v.toFixed({dec}); }}}}, {_t(t)});')
        if disp:
            js.append(
                f'tl.call(function () {{ document.querySelector('
                f'"#{p}-dat-v{i}").textContent = {_esc_js(disp)}; }}, '
                f'null, {_t(t + 0.9)});')
        t += 0.8
    if note:
        js.append(f'tl.fromTo("#{p}-dat-note", {{opacity: 0, y: 18}}, '
                  f'{{opacity: 1, y: 0, duration: 0.6, '
                  f'ease: "power3.out"}}, {_t(t + 0.2)});')
    js.append(f'tl.fromTo("#{p}-dat-src", {{opacity: 0}}, '
              f'{{opacity: 1, duration: 0.5, ease: "power2.out"}}, '
              f'{_t(t + 0.75)});')
    return css, "".join(parts), js


def _esc_js(s):
    return json.dumps(str(s))


def _layer_map_card(spec, p, dur, track, scale):
    title = str(spec.get("title") or "")
    label = str(spec.get("label") or "")
    desc = str(spec.get("description") or "")
    # NOTE: the honesty label is NOT read from the spec — it is baked
    # into this template and cannot be overridden or removed.
    css = f"""
    #{p}-map-panel {{ position: absolute; left: {_safe_px(scale)}px;
      top: {int(96*scale)}px; width: {int(520*scale)}px;
      padding: {int(40*scale)}px {int(44*scale)}px {int(34*scale)}px;
      background: rgba(8,14,20,0.78);
      border: 1px solid rgba(255,255,255,0.16); border-radius: 18px; }}
    #{p}-map-title {{ font-family: Oswald, sans-serif; font-weight: 600;
      font-size: {int(38*scale)}px; letter-spacing: 2px; color: #ffffff;
      text-transform: uppercase; }}
    #{p}-map-wrap {{ margin-top: 18px; display: flex;
      gap: {int(24*scale)}px; align-items: flex-start; }}
    #{p}-map-side {{ padding-top: {int(130*scale)}px; }}
    #{p}-map-place {{ font-family: Inter, sans-serif;
      font-size: {int(29*scale)}px; font-weight: 700;
      letter-spacing: 3px; color: #ffb340; }}
    #{p}-map-desc {{ margin-top: 10px; font-family: Inter, sans-serif;
      font-size: {int(28*scale)}px; line-height: 1.35;
      color: rgba(255,255,255,0.85); width: {int(190*scale)}px; }}
    #{p}-map-micro {{ margin-top: 16px; font-family: Inter, sans-serif;
      font-size: {int(24*scale)}px; color: rgba(255,255,255,0.5); }}"""
    svg = f"""
        <svg width="{int(230*scale)}" height="{int(330*scale)}"
             viewBox="0 0 460 640" fill="none">
          <path d="M150,30 L330,55 L430,150 L425,610 L60,610
                   C52,470 82,330 66,190 C60,120 90,60 150,30 Z"
                fill="rgba(255,255,255,0.07)"
                stroke="rgba(255,255,255,0.45)" stroke-width="3" />
          <path id="{p}-map-coast"
                d="M96,52 C66,190 88,330 70,470 C64,530 60,575 60,608"
                stroke="#ffb340" stroke-width="7" stroke-linecap="round"
                pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"
                opacity="0" />
          <g stroke="#ff5d47" stroke-width="6" stroke-linecap="round">
            <line x1="52" y1="200" x2="76" y2="206" />
            <line x1="56" y1="330" x2="80" y2="336" />
            <line x1="44" y1="470" x2="68" y2="476" />
          </g>
          <circle id="{p}-map-ring" cx="74" cy="318" r="16" fill="none"
                  stroke="#ffb340" stroke-width="4" />
          <circle id="{p}-map-dot" cx="74" cy="318" r="10"
                  fill="#ffb340" />
        </svg>"""
    body = (
        f'<div id="{p}-map-panel" class="clip" data-start="0" '
        f'data-duration="{_t(dur)}" data-track-index="{track}" '
        f'data-honesty="illustrative-map-not-to-scale">'
        + (f'<div id="{p}-map-title">{_esc(title)}</div>' if title else "")
        + f'<div id="{p}-map-wrap">{svg}<div id="{p}-map-side">'
        + (f'<div id="{p}-map-place">{_esc(label)}</div>' if label else "")
        + (f'<div id="{p}-map-desc">{_esc(desc)}</div>' if desc else "")
        + f'</div></div>'
          f'<div id="{p}-map-micro">{_esc(MAP_HONESTY_LABEL)}</div></div>')
    js = [
        f'tl.fromTo("#{p}-map-panel", {{opacity: 0, x: -60}}, '
        f'{{opacity: 1, x: 0, duration: 0.7, ease: "power3.out"}}, 0.4);',
        f'tl.to("#{p}-map-coast", {{opacity: 1, duration: 0.05, '
        f'ease: "none"}}, 1.2);',
        f'tl.to("#{p}-map-coast", {{strokeDashoffset: 0, duration: 2.0, '
        f'ease: "power2.inOut"}}, 1.2);',
        f'tl.fromTo("#{p}-map-dot", {{scale: 0, '
        f'transformOrigin: "74px 318px"}}, {{scale: 1, duration: 0.45, '
        f'ease: "back.out(2.2)"}}, 3.3);',
        f'tl.fromTo("#{p}-map-ring", {{scale: 0.4, opacity: 0.95, '
        f'transformOrigin: "74px 318px"}}, {{scale: 2.6, opacity: 0, '
        f'duration: 1.1, ease: "power2.out"}}, 3.45);',
    ]
    if label:
        js.append(f'tl.fromTo("#{p}-map-place", {{opacity: 0, y: 16}}, '
                  f'{{opacity: 1, y: 0, duration: 0.55, '
                  f'ease: "power3.out"}}, 3.8);')
    if desc:
        js.append(f'tl.fromTo("#{p}-map-desc", {{opacity: 0, y: 16}}, '
                  f'{{opacity: 1, y: 0, duration: 0.55, '
                  f'ease: "power3.out"}}, 4.05);')
    js.append(f'tl.fromTo("#{p}-map-micro", {{opacity: 0}}, '
              f'{{opacity: 1, duration: 0.5, ease: "power2.out"}}, 4.4);')
    return css, body, js


def _layer_kinetic_caption(spec, p, dur, track, scale):
    words = spec.get("words")
    timed = []
    if isinstance(words, list) and words and isinstance(words[0], dict):
        for w in words:
            timed.append((str(w.get("text") or ""),
                          float(w.get("at") or 0.0),
                          bool(w.get("accent"))))
    else:
        phrase = str(spec.get("phrase") or "")
        accent = str(spec.get("accent") or "")
        start = float(spec.get("start") or 0.4)
        interval = float(spec.get("interval") or 0.55)
        for i, w in enumerate(phrase.split()):
            timed.append((w, start + i * interval,
                          bool(accent) and
                          w.strip(".,!?'\"").lower() ==
                          accent.strip(".,!?'\"").lower()))
    fs = int(118 * scale)
    css = f"""
    #{p}-kin {{ position: absolute; left: {_safe_px(scale)}px;
      bottom: {int(205*scale)}px; display: flex;
      gap: {int(34*scale)}px; flex-wrap: wrap;
      max-width: {int(1680*scale)}px;
      font-family: Oswald, sans-serif; font-weight: 700;
      font-size: {fs}px; letter-spacing: 1px; color: #ffffff;
      text-transform: uppercase;
      text-shadow: 0 3px 18px rgba(0,0,0,0.75); }}
    #{p}-kin span {{ min-width: 0; overflow-wrap: anywhere; }}
    #{p}-kin .accent {{ color: #ffb340; }}"""
    spans = "".join(
        f'<span id="{p}-kin-w{i}"'
        + (' class="accent"' if acc else "") + f'>{_esc(w)}</span>'
        for i, (w, _at, acc) in enumerate(timed))
    body = (f'<div id="{p}-kin" class="clip" data-start="0" '
            f'data-duration="{_t(dur)}" data-track-index="{track}">'
            f'{spans}</div>')
    js = [f'tl.fromTo("#{p}-kin-w{i}", {{opacity: 0, y: 44}}, '
          f'{{opacity: 1, y: 0, duration: 0.5, ease: "power4.out"}}, '
          f'{_t(at)});'
          for i, (_w, at, _acc) in enumerate(timed)]
    return css, body, js


def _layer_lower_third(spec, p, dur, track, scale):
    name = str(spec.get("name") or "")
    role = str(spec.get("role") or "")
    css = f"""
    #{p}-lt {{ position: absolute; left: {_safe_px(scale)}px;
      bottom: {int(120*scale)}px; display: flex;
      gap: {int(24*scale)}px; align-items: stretch;
      max-width: {int(1680*scale)}px; }}
    #{p}-lt > div {{ min-width: 0; }}
    #{p}-lt-bar {{ width: 8px; background: #ffb340; flex: 0 0 auto;
      transform-origin: center bottom; }}
    #{p}-lt-name {{ font-family: Oswald, sans-serif; font-weight: 600;
      font-size: {int(54*scale)}px; letter-spacing: 1px; color: #ffffff;
      text-transform: uppercase;
      text-shadow: 0 2px 14px rgba(0,0,0,0.8);
      min-width: 0; overflow-wrap: anywhere; }}
    #{p}-lt-role {{ margin-top: 4px; font-family: Inter, sans-serif;
      font-size: {int(30*scale)}px; color: rgba(255,255,255,0.88);
      text-shadow: 0 2px 14px rgba(0,0,0,0.8);
      min-width: 0; overflow-wrap: anywhere; }}"""
    body = (f'<div id="{p}-lt" class="clip" data-start="0" '
            f'data-duration="{_t(dur)}" data-track-index="{track}">'
            f'<div id="{p}-lt-bar"></div><div>'
            f'<div id="{p}-lt-name">{_esc(name)}</div>'
            + (f'<div id="{p}-lt-role">{_esc(role)}</div>' if role else "")
            + '</div></div>')
    js = [
        f'tl.fromTo("#{p}-lt-bar", {{scaleY: 0}}, {{scaleY: 1, '
        f'duration: 0.5, ease: "power3.out"}}, 0.5);',
        f'tl.fromTo("#{p}-lt-name", {{opacity: 0, x: -30}}, '
        f'{{opacity: 1, x: 0, duration: 0.6, ease: "power3.out"}}, 0.6);',
    ]
    if role:
        js.append(f'tl.fromTo("#{p}-lt-role", {{opacity: 0, x: -30}}, '
                  f'{{opacity: 1, x: 0, duration: 0.6, '
                  f'ease: "power3.out"}}, 0.75);')
    return css, body, js


def _layer_source_card(spec, p, dur, track, scale, flags, scene_no):
    """Sheet-style research card: paper card, big stat, visible source.

    The taste gate blocks sourceless facts before render; if one still
    reaches codegen, the missing source is rendered explicitly and
    flagged, never hidden."""
    kicker = str(spec.get("kicker") or "THE RESEARCH")
    headline = str(spec.get("headline") or spec.get("title") or "")
    stat = str(spec.get("stat") or spec.get("display") or spec.get("value") or "")
    unit = str(spec.get("unit") or "")
    quote = str(spec.get("quote") or spec.get("note") or "")
    source = str(spec.get("source") or "").strip()
    source_missing = not source
    if source_missing:
        flags.append(
            f"scene {scene_no}: source_card has NO source — rendered "
            f"with the explicit placeholder '{MISSING_SOURCE_LINE}'")
        source_line = MISSING_SOURCE_LINE
    else:
        source_line = source if source.lower().startswith("source") \
            else "Source: " + source
    css = f"""
    #{p}-src-card {{ position: absolute; right: {_safe_px(scale)}px;
      top: {int(110*scale)}px; width: {int(620*scale)}px;
      padding: {int(44*scale)}px {int(48*scale)}px {int(40*scale)}px;
      background: rgba(248,246,240,0.96); color: #161616;
      border-radius: 14px; box-shadow: 0 18px 50px rgba(0,0,0,0.35); }}
    #{p}-src-kicker {{ font-family: Inter, sans-serif; font-weight: 800;
      font-size: {int(22*scale)}px; letter-spacing: 3px; color: #8a5a12;
      text-transform: uppercase; }}
    #{p}-src-head {{ margin-top: 10px; font-family: Inter, sans-serif;
      font-weight: 800; font-size: {int(36*scale)}px; line-height: 1.18;
      overflow-wrap: anywhere; }}
    #{p}-src-stat {{ margin-top: {int(26*scale)}px; display: flex;
      align-items: baseline; gap: {int(14*scale)}px; flex-wrap: wrap; }}
    #{p}-src-num {{ font-family: Oswald, sans-serif; font-weight: 700;
      font-size: {int(92*scale)}px; color: #d97706; line-height: 1;
      min-width: 0; overflow-wrap: anywhere; }}
    #{p}-src-unit {{ font-family: Inter, sans-serif; font-weight: 700;
      font-size: {int(28*scale)}px; color: #444;
      min-width: 0; overflow-wrap: anywhere; }}
    #{p}-src-quote {{ margin-top: {int(22*scale)}px; font-family: Inter, sans-serif;
      font-size: {int(27*scale)}px; line-height: 1.35; color: #333;
      border-left: 5px solid #d97706; padding-left: {int(18*scale)}px;
      overflow-wrap: anywhere; }}
    #{p}-src-line {{ margin-top: {int(24*scale)}px; font-family: Inter, sans-serif;
      font-size: {int(23*scale)}px; color: #555;
      overflow-wrap: anywhere; }}
    #{p}-src-line.missing {{ color: #b3261e; font-weight: 800; }}"""
    parts = [f'<div id="{p}-src-card" class="clip" data-start="0" '
             f'data-duration="{_t(dur)}" data-track-index="{track}">',
             f'<div id="{p}-src-kicker">{_esc(kicker)}</div>']
    if headline:
        parts.append(f'<div id="{p}-src-head">{_esc(headline)}</div>')
    if stat:
        parts.append(
            f'<div id="{p}-src-stat"><div id="{p}-src-num">{_esc(stat)}</div>'
            + (f'<div id="{p}-src-unit">{_esc(unit)}</div>' if unit else "")
            + '</div>')
    if quote:
        parts.append(f'<div id="{p}-src-quote">{_esc(quote)}</div>')
    parts.append(
        f'<div id="{p}-src-line"'
        + (' class="missing" data-source-missing="true"' if source_missing else "")
        + f'>{_esc(source_line)}</div></div>')
    js = [f'tl.fromTo("#{p}-src-card", {{opacity: 0, x: 60}}, '
          f'{{opacity: 1, x: 0, duration: 0.7, ease: "power3.out"}}, 0.4);']
    return css, "".join(parts), js


def _layer_diagram(spec, p, dur, track, scale):
    """Minimal sheet diagrams: wave / growth / checks / arrow.

    Deliberately small and caption-safe: the diagram supports the
    footage; it never replaces it or enters the caption band."""
    kind = str(spec.get("kind") or "wave").lower()
    if kind not in ("wave", "growth", "checks", "arrow"):
        kind = "wave"
    title = str(spec.get("title") or "")
    items = [str(x)[:48] for x in (spec.get("items") or []) if str(x).strip()][:4]
    css = f"""
    #{p}-dia {{ position: absolute; right: {_safe_px(scale)}px;
      top: {int(150*scale)}px; width: {int(560*scale)}px;
      padding: {int(36*scale)}px; background: rgba(8,14,20,0.72);
      border: 1px solid rgba(255,255,255,0.16); border-radius: 18px;
      color: #fff; font-family: Inter, sans-serif; }}
    #{p}-dia-title {{ font-size: {int(25*scale)}px; font-weight: 800;
      letter-spacing: 2px; text-transform: uppercase;
      overflow-wrap: anywhere; }}
    .{p}-dia-row {{ display: flex; align-items: center; gap: {int(16*scale)}px;
      margin-top: {int(24*scale)}px; font-size: {int(27*scale)}px; }}
    .{p}-dia-row > div {{ min-width: 0; overflow-wrap: anywhere; }}
    .{p}-dia-dot {{ width: {int(22*scale)}px; height: {int(22*scale)}px;
      border-radius: 50%; background: #ffb340; flex: 0 0 auto; }}
    .{p}-dia-bar {{ height: {int(18*scale)}px; border-radius: 999px;
      background: #ffb340; flex: 0 1 auto; }}
    .{p}-dia-check {{ width: {int(34*scale)}px; height: {int(34*scale)}px;
      border-radius: 50%; border: 3px solid #8fd18b; color: #8fd18b;
      display: flex; align-items: center; justify-content: center;
      font-weight: 900; flex: 0 0 auto; }}"""
    rows = []
    if kind == "growth":
        vals = [35, 55, 78, 100]
        for i, v in enumerate(vals):
            rows.append(
                f'<div class="{p}-dia-row"><div class="{p}-dia-bar" '
                f'style="width:{int(v * 4 * scale)}px"></div>'
                f'<div>{_esc(items[i] if i < len(items) else "")}</div></div>')
    elif kind == "checks":
        for i, it in enumerate(items or ["A starting point", "A sentence"]):
            rows.append(
                f'<div class="{p}-dia-row"><div class="{p}-dia-check">✓</div>'
                f'<div>{_esc(it)}</div></div>')
    elif kind == "arrow":
        rows.append(
            f'<div class="{p}-dia-row"><div class="{p}-dia-dot"></div>'
            f'<div class="{p}-dia-bar" style="width:{int(300*scale)}px"></div>'
            f'<div class="{p}-dia-dot"></div></div>')
        for it in items:
            rows.append(f'<div class="{p}-dia-row"><div>{_esc(it)}</div></div>')
    else:  # wave
        rows.append(
            f'<div class="{p}-dia-row"><div class="{p}-dia-dot"></div>'
            f'<div class="{p}-dia-bar" style="width:{int(180*scale)}px"></div>'
            f'<div class="{p}-dia-dot"></div>'
            f'<div class="{p}-dia-bar" style="width:{int(120*scale)}px"></div></div>')
        for it in items:
            rows.append(f'<div class="{p}-dia-row"><div>{_esc(it)}</div></div>')
    body = (f'<div id="{p}-dia" class="clip" data-start="0" '
            f'data-duration="{_t(dur)}" data-track-index="{track}">'
            + (f'<div id="{p}-dia-title">{_esc(title)}</div>' if title else "")
            + "".join(rows) + '</div>')
    js = [f'tl.fromTo("#{p}-dia", {{opacity: 0, y: 24}}, '
          f'{{opacity: 1, y: 0, duration: 0.6, ease: "power3.out"}}, 0.5);']
    return css, body, js


_LAYER_BUILDERS = {
    "title": _layer_title,
    "data_chart": None,          # special-cased (needs flags)
    "source_card": None,         # special-cased (needs flags)
    "diagram": _layer_diagram,
    "map_card": _layer_map_card,
    "kinetic_caption": _layer_kinetic_caption,
    "lower_third": _layer_lower_third,
}
LAYER_TYPES = ("title", "data_chart", "source_card", "diagram", "map_card",
               "kinetic_caption", "lower_third")


# ------------------------------------------------------------- scenes

def _scene_composition(idx, scene, asset_name, media_start, width,
                       height, flags):
    """One scene -> one compositions/sceneN_<type>.html file body."""
    cid = f"scene{idx}"
    p = f"s{idx}"
    dur = float(scene["duration"])
    scale = width / 1920.0
    ext = os.path.splitext(asset_name)[1].lower()
    if ext in _IMAGE_EXTS:
        media = (f'<img id="{p}-media" class="clip" data-start="0" '
                 f'data-duration="{_t(dur)}" data-track-index="0" '
                 f'src="assets/{_esc(asset_name)}" />')
    else:
        media = (f'<video id="{p}-media" class="clip" data-start="0" '
                 f'data-duration="{_t(dur)}" '
                 f'data-media-start="{_t(media_start)}" '
                 f'data-track-index="0" src="assets/{_esc(asset_name)}" '
                 f'muted playsinline></video>')
    css = f"""
    #root {{ position: absolute; inset: 0; overflow: hidden;
      background: #000; }}
    #{p}-media {{ position: absolute; left: 0; top: 0;
      width: {width}px; height: {height}px; object-fit: cover; }}
    #{p}-scrim {{ position: absolute; left: 0; right: 0; bottom: 0;
      height: {int(620 * scale)}px;
      background: linear-gradient(to top, rgba(0,0,0,0.72),
        rgba(0,0,0,0)); }}
    #{p}-vig {{ position: absolute; inset: 0;
      background: radial-gradient(ellipse at center, rgba(0,0,0,0) 58%,
        rgba(0,0,0,0.38) 100%); }}"""
    body_parts = [
        media,
        f'<div id="{p}-scrim" class="clip" data-start="0" '
        f'data-duration="{_t(dur)}" data-track-index="1"></div>',
        f'<div id="{p}-vig" class="clip" data-start="0" '
        f'data-duration="{_t(dur)}" data-track-index="1"></div>',
    ]
    js = []
    # ROUND 5 (Fix 3 — FOOTAGE MOTION): the footage itself moves.
    # hf_primary marks beats whose source is a still image or a
    # measured-static clip with media_motion; the media element
    # gets a real keyframed zoom (slow push-in over the whole
    # beat, or a punch-in at the beat's accent) instead of sitting
    # frozen under animated text — film 3's "static card" feel.
    _mm = str(scene.get("media_motion") or "")
    if _mm == "push_in":
        js.append(f'tl.fromTo("#{p}-media", {{scale: 1.03}}, '
                  f'{{scale: 1.14, duration: {_t(dur)}, '
                  f'ease: "none", transformOrigin: "50% 50%"}}, 0);')
    elif _mm == "punch_in":
        js.append(f'tl.fromTo("#{p}-media", {{scale: 1.0}}, '
                  f'{{scale: 1.16, duration: 0.9, '
                  f'ease: "power3.out", transformOrigin: "50% 50%"}}, 0);')
    track = 2
    for layer in scene.get("layers") or []:
        if not isinstance(layer, dict):
            flags.append(f"scene {idx}: non-dict layer skipped")
            continue
        ltype = str(layer.get("type") or "")
        if ltype == "data_chart":
            c, b, j = _layer_data_chart(layer, p, dur, track, scale,
                                        flags, idx)
        elif ltype == "source_card":
            c, b, j = _layer_source_card(layer, p, dur, track, scale,
                                         flags, idx)
        elif ltype in _LAYER_BUILDERS and _LAYER_BUILDERS[ltype]:
            c, b, j = _LAYER_BUILDERS[ltype](layer, p, dur, track, scale)
        else:
            flags.append(f"scene {idx}: unknown layer type "
                         f"'{ltype}' skipped")
            continue
        css += c
        body_parts.append(b)
        js.extend(j)
        track += 1
    first_type = "plain"
    for layer in scene.get("layers") or []:
        if isinstance(layer, dict) and layer.get("type"):
            first_type = str(layer["type"])
            break
    for _tv in text_edge_violations(css, width):
        flags.append(f"scene {idx}: TEXT-EDGE {_tv}")
    fname = f"scene{idx}_{first_type}.html"
    content = (
        "<template>\n  <style>" + css + "\n  </style>\n"
        f'  <div id="root" data-composition-id="{cid}" '
        f'data-width="{width}" data-height="{height}">\n    '
        + "\n    ".join(body_parts)
        + "\n  </div>\n  <script>\n    const tl = gsap.timeline("
          "{ paused: true });\n"
        + "".join(f"    {line}\n" for line in js)
        + f'    window.__timelines["{cid}"] = tl;\n  </script>\n'
          "</template>\n")
    return fname, content


def _index_html(scenes_meta, total, width, height, name):
    children = []
    for m in scenes_meta:
        children.append(
            f'      <div\n        id="{m["cid"]}"\n'
            f'        data-composition-id="{m["cid"]}"\n'
            f'        data-composition-src="compositions/{m["file"]}"\n'
            f'        data-start="{_t(m["start"])}"\n'
            f'        data-duration="{_t(m["duration"])}"\n'
            f'        data-track-index="0"\n'
            f'        data-track-kind="graphics"\n'
            f'        data-width="{width}"\n'
            f'        data-height="{height}"\n      ></div>')
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <script src="{GSAP_CDN}"></script>
    <style>
      :root {{
        --ink: #ffffff;
        --accent: #ffb340;
        --font-display: Oswald, sans-serif;
        --font-body: Inter, sans-serif;
      }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: {width}px; height: {height}px;
        overflow: hidden; background: #000; }}
      #root {{ position: absolute; inset: 0; }}
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-start="0"
      data-duration="{_t(total)}"
      data-width="{width}"
      data-height="{height}"
    >
{chr(10).join(children)}
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""


# ------------------------------------------------------------- public

def generate_project(script, outdir, *, width=1920, height=1080,
                     name="julie-hyperframes"):
    """Scene script (list of scene dicts, see module docstring) ->
    a complete HyperFrames project in outdir, structured like the
    spike. Returns a report dict: {project_dir, index, compositions,
    assets, total_duration, scenes, flags}. Raises ValueError on a
    scene with missing/unusable footage or a non-positive duration —
    graphics never substitute for footage."""
    if not script:
        raise ValueError("empty scene script — nothing to generate")
    outdir = os.path.abspath(str(outdir))
    comp_dir = os.path.join(outdir, "compositions")
    asset_dir = os.path.join(outdir, "assets")
    os.makedirs(comp_dir, exist_ok=True)
    os.makedirs(asset_dir, exist_ok=True)
    os.makedirs(os.path.join(outdir, "renders"), exist_ok=True)

    flags = []
    asset_map = {}          # abspath -> asset file name in project
    media_cursor = {}       # asset name -> next default media_start
    scenes_meta = []
    start = 0.0
    for idx, scene in enumerate(script, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"scene {idx}: not a dict")
        footage = str(scene.get("footage") or "")
        if not footage or not os.path.isfile(footage):
            raise ValueError(
                f"scene {idx}: footage file not found: {footage!r} "
                f"— HyperFrames layers are overlays OVER real "
                f"footage, never a replacement frame")
        dur = float(scene.get("duration") or 0)
        if dur <= 0:
            raise ValueError(f"scene {idx}: duration must be > 0, "
                             f"got {scene.get('duration')!r}")
        src_abs = os.path.abspath(footage)
        if src_abs not in asset_map:
            base = os.path.basename(src_abs)
            stem, ext = os.path.splitext(base)
            cand, n = base, 2
            while cand in asset_map.values():
                cand = f"{stem}_{n}{ext}"
                n += 1
            shutil.copy2(src_abs, os.path.join(asset_dir, cand))
            asset_map[src_abs] = cand
        asset_name = asset_map[src_abs]
        if scene.get("media_start") is not None:
            media_start = float(scene["media_start"])
        else:
            media_start = media_cursor.get(asset_name, 0.0)
        media_cursor[asset_name] = media_start + dur

        sc = dict(scene)
        sc["duration"] = dur
        fname, content = _scene_composition(
            idx, sc, asset_name, media_start, width, height, flags)
        with open(os.path.join(comp_dir, fname), "w",
                  encoding="utf-8") as f:
            f.write(content)
        scenes_meta.append({"cid": f"scene{idx}", "file": fname,
                            "start": start, "duration": dur})
        start += dur

    total = start
    slug = _slug(name)
    with open(os.path.join(outdir, "index.html"), "w",
              encoding="utf-8") as f:
        f.write(_index_html(scenes_meta, total, width, height, slug))
    with open(os.path.join(outdir, "hyperframes.json"), "w",
              encoding="utf-8") as f:
        json.dump({
            "$schema": "https://hyperframes.heygen.com/schema/"
                       "hyperframes.json",
            "registry": "https://raw.githubusercontent.com/"
                        "heygen-com/hyperframes/main/registry",
            "paths": {"blocks": "compositions",
                      "components": "compositions/components",
                      "assets": "assets"},
            "media": {"autoProxy": True},
        }, f, indent=2)
    with open(os.path.join(outdir, "package.json"), "w",
              encoding="utf-8") as f:
        json.dump({"name": slug, "private": True, "type": "module",
                   "scripts": {
                       "check": f"npx --yes hyperframes@{HF_VERSION} check",
                       "render": f"npx --yes hyperframes@{HF_VERSION} render"}},
                  f, indent=2)
    with open(os.path.join(outdir, "meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"id": slug, "name": slug,
                   "createdAt": datetime.now(timezone.utc).strftime(
                       "%Y-%m-%dT%H:%M:%S.000Z")}, f, indent=2)
    return {"project_dir": outdir,
            "index": os.path.join(outdir, "index.html"),
            "compositions": [os.path.join(comp_dir, m["file"])
                              for m in scenes_meta],
            "assets": sorted(asset_map.values()),
            "total_duration": round(total, 3),
            "scenes": len(scenes_meta),
            "flags": flags}


def check_project(project_dir, *, tmpdir=None, timeout=300):
    """Run the spike's lint step: hyperframes check --json.
    Returns the parsed JSON dict (or {"raw": ...} if unparsable)."""
    env = dict(os.environ)
    if tmpdir:
        os.makedirs(tmpdir, exist_ok=True)
        env["TMPDIR"] = tmpdir
    r = subprocess.run(
        ["npx", "--yes", f"hyperframes@{HF_VERSION}", "check", "--json"],
        cwd=str(project_dir), env=env, capture_output=True, text=True,
        timeout=timeout)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"raw": (r.stdout or "")[-2000:],
                "stderr": (r.stderr or "")[-1000:],
                "returncode": r.returncode}


def render_project(project_dir, output=None, *, tmpdir=None,
                   timeout=None, quality=None, extra_args=()):
    """Render a generated project with the SAME command the spike
    used: npx --yes hyperframes@0.9.55 render (optionally -o output).
    TMPDIR is pointed at a big-disk dir (this VM's /tmp is a 512 MB
    tmpfs and the renderer refuses to start under ~1 GB free — the
    spike README's warning). Returns the MP4 path. Raises
    RuntimeError with the CLI tail on failure."""
    project_dir = os.path.abspath(str(project_dir))
    env = dict(os.environ)
    tmp = tmpdir or os.path.join(os.path.dirname(project_dir),
                                 ".hyperframes-tmp")
    os.makedirs(tmp, exist_ok=True)
    env["TMPDIR"] = tmp
    cmd = ["npx", "--yes", f"hyperframes@{HF_VERSION}", "render"]
    if quality:
        cmd += ["--quality", str(quality)]
    if output:
        cmd += ["-o", str(output)]
    cmd += [str(a) for a in extra_args]
    r = subprocess.run(cmd, cwd=project_dir, env=env,
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(
            "hyperframes render failed (rc=%s):\n%s\n%s" % (
                r.returncode, (r.stdout or "")[-3000:],
                (r.stderr or "")[-3000:]))
    if output:
        out = str(output)
        if not os.path.isabs(out):
            out = os.path.join(project_dir, out)
        if os.path.isfile(out):
            return out
    renders = os.path.join(project_dir, "renders")
    mp4s = [os.path.join(renders, f) for f in
            (os.listdir(renders) if os.path.isdir(renders) else [])
            if f.endswith(".mp4")]
    if not mp4s:
        raise RuntimeError("hyperframes render reported success but "
                           "no MP4 found in renders/")
    return max(mp4s, key=os.path.getmtime)
