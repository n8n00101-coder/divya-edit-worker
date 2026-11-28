"""Julie agent engine: YOUTUBE RESEARCH (Antigravity-equivalent).

The Antigravity setup researches a video and saves ideas/analysis.
Julie's equivalent works ONLY on data the job supplies (title,
thumbnail text, transcript cues, view stats) — it never fetches,
scrapes, or logs into anything. The upstream research repo's
collection paths (yt-dlp downloads, API-key fetching) are held;
the analysis structure is what ports.

yt_research_analyze returns a structured record:
  hook        first-cue hook text + yt_hook_score verdict
  packaging   yt_title_lint pairing verdict
  structure   cue-based chapter draft (validated) + cue stats
  outlier     views / channel-median multiple when stats supplied
  ideas       deterministic takeaways drawn from the findings
"""
import yt_tools


def _first_hook(cues):
    """Hook text = cues starting within the first 8 seconds."""
    rows = yt_tools._norm_cues(cues or [])
    hook = " ".join(text for start, _end, text in rows
                    if start < 8.0).strip()
    return hook


def analyze_video(data):
    data = data if isinstance(data, dict) else {}
    title = str(data.get("title") or "").strip()
    thumb = data.get("thumb")
    cues = data.get("cues") or []
    out = {"title": title, "ideas": []}

    hook = _first_hook(cues)
    if hook:
        scored = yt_tools.score_hooks([hook])["ranked"]
        out["hook"] = {"text": hook, "score": scored[0] if scored else None}
        if scored:
            top = scored[0]
            out["ideas"].append(
                f"hook formula: {top.get('formula')} "
                f"(score {top.get('total')}, {top.get('band')})")
    else:
        out["hook"] = None

    if title:
        lint = yt_tools.lint_title_pair(title, thumb)
        out["packaging"] = lint
        for issue in lint.get("issues") or []:
            out["ideas"].append(f"packaging: {issue}")

    rows = yt_tools._norm_cues(cues)
    if rows:
        dur = data.get("duration") or rows[-1][1]
        out["structure"] = {
            "cues": len(rows),
            "duration_s": dur,
            "chapters": yt_tools.chapters_from_cues(cues),
        }

    views = data.get("views")
    median = data.get("channel_median_views")
    if isinstance(views, (int, float)) and isinstance(median, (int, float)) \
            and median > 0:
        mult = round(views / median, 2)
        out["outlier"] = {"views": views, "channel_median_views": median,
                          "multiple": mult, "is_outlier": mult >= 1.5}
        if mult >= 1.5:
            out["ideas"].append(
                f"outlier: {mult}x the channel median — study its "
                f"hook and packaging, not just its topic")
    else:
        out["outlier"] = None

    if not out["ideas"]:
        out["ideas"].append(
            "no measurable signal in the supplied data — supply "
            "cues/stats for a deeper read")
    return out


def register_research_tools(reg):
    reg.register(
        "yt_research_analyze",
        "Structured analysis of PROVIDED YouTube video data "
        "(hook score, title/thumbnail lint, chapter structure, "
        "outlier multiple, ideas). Args: {data: {title, thumb?, "
        "cues?, views?, channel_median_views?, duration?}}. "
        "Never fetches or scrapes. Read-only.",
        {"data": {"type": "object", "required": True,
                  "desc": "supplied video data"}},
        lambda a: (True, analyze_video(a.get("data"))),
        mutating=False, needs_allow=False, timeout=30)
    return reg
