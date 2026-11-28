"""Julie agent engine: TOOL ROUTING — capability registry + selector.

Julie now carries many agent tools (YouTube packaging, video
analysis, compute/verify, workspace files, brand, research, style).
Offered flat, the whole set can disturb the brain: unrelated tools
invite unrelated calls. This module is the routing layer Ajju
ordered (2026-11-28): every tool declares its capabilities, and a
deterministic selector picks the MINIMAL tool set a task needs.

Contract:
  - TOOL_META: one entry per agent tool — capability tags, cost
    class, one-line when-to-use / when-NOT-to-use.
  - CORE_TOOLS: the engine bookkeeping tools every job keeps
    (director layer, plan, job record, the selector itself).
  - select_tools(task_text, available): keyword-classifies the
    task into capabilities and returns CORE + the tools whose
    capabilities match, in registry order. No capability match is
    an honest answer (matched=False, core only) — never a forced
    tool. Stubs (noop/echo) are never selected.
  - register_routing_tool(reg): exposes tool_select to the brain
    so it classifies first and works with the minimal set.
"""
import re

# name -> {caps, cost, use, avoid}
TOOL_META = {
    "job_state": {"caps": ["core"], "cost": "fast",
                  "use": "read this job's own record",
                  "avoid": "never for facts about the outside world"},
    "get_history": {"caps": ["core"], "cost": "fast",
                    "use": "recover earlier steps of this job",
                    "avoid": "not a substitute for re-verifying"},
    "set_plan": {"caps": ["core"], "cost": "fast",
                 "use": "declare/maintain the job plan",
                 "avoid": "bookkeeping only, does no work"},
    "director_plan": {"caps": ["core"], "cost": "fast",
                      "use": "record vision + steps + risks first",
                      "avoid": "—"},
    "director_check": {"caps": ["core"], "cost": "fast",
                       "use": "check one plan step with evidence",
                       "avoid": "never without real tool results"},
    "director_review": {"caps": ["core"], "cost": "fast",
                        "use": "final deliver/rework/fail verdict",
                        "avoid": "never before verifying the deliverable"},
    "tool_select": {"caps": ["core"], "cost": "fast",
                    "use": "classify the task, get the minimal tool set",
                    "avoid": "—"},
    "file_list": {"caps": ["file-read"], "cost": "fast",
                  "use": "see what files the workspace holds",
                  "avoid": "not for file contents"},
    "file_read": {"caps": ["file-read"], "cost": "fast",
                  "use": "read a workspace text file",
                  "avoid": "never guess contents instead"},
    "search_text": {"caps": ["file-read"], "cost": "fast",
                    "use": "grep the workspace before guessing locations",
                    "avoid": "—"},
    "list_files": {"caps": ["file-read"], "cost": "fast",
                   "use": "glob the workspace",
                   "avoid": "—"},
    "file_write": {"caps": ["file-write"], "cost": "fast",
                   "use": "create/replace a workspace text file",
                   "avoid": "small changes belong in edit_file"},
    "file_append": {"caps": ["file-write"], "cost": "fast",
                    "use": "append to a workspace text file",
                    "avoid": "—"},
    "edit_file": {"caps": ["file-write"], "cost": "fast",
                  "use": "surgical exact-match edit after file_read",
                  "avoid": "never without reading the file first"},
    "run_command": {"caps": ["run"], "cost": "medium",
                    "use": "run tests/scripts inside the workspace",
                    "avoid": "never to escape the workspace"},
    "compute_csv": {"caps": ["compute"], "cost": "fast",
                    "use": "exact CSV facts by code",
                    "avoid": "never compute figures in your head instead"},
    "filter_csv": {"caps": ["compute", "file-write"], "cost": "fast",
                   "use": "filtered/sorted CSV subset copied by code",
                   "avoid": "never hand-copy rows"},
    "verify_file_contains": {"caps": ["verify"], "cost": "fast",
                             "use": "prove a file contains required strings",
                             "avoid": "—"},
    "verify_csv_rows": {"caps": ["verify"], "cost": "fast",
                        "use": "prove a CSV matches expectations",
                        "avoid": "—"},
    "verify_csv_subset": {"caps": ["verify"], "cost": "fast",
                          "use": "prove an output CSV is the source subset",
                          "avoid": "—"},
    "fetch_url": {"caps": ["verify-web"], "cost": "medium",
                  "use": "verify a published page by reading it back",
                  "avoid": "not a research crawler"},
    "publish_app": {"caps": ["publish"], "cost": "medium",
                    "use": "publish this job's HTML page",
                    "avoid": "only when the deliverable is a web page"},
    "yt_hook_score": {"caps": ["hook-scoring"], "cost": "fast",
                      "use": "score hook candidates, keep the top two",
                      "avoid": "the score is a heuristic, not a promise"},
    "yt_title_lint": {"caps": ["packaging"], "cost": "fast",
                      "use": "judge one title+thumbnail pairing",
                      "avoid": "not for ranking many pairings"},
    "yt_package_rank": {"caps": ["packaging"], "cost": "fast",
                        "use": "rank title x thumbnail pairings",
                        "avoid": "never invents titles"},
    "yt_chapters_validate": {"caps": ["chapters"], "cost": "fast",
                             "use": "validate a chapter list",
                             "avoid": "—"},
    "yt_chapters_from_cues": {"caps": ["chapters"], "cost": "fast",
                              "use": "draft chapters from cues",
                              "avoid": "titles are drafts to retitle"},
    "yt_viral_rank": {"caps": ["research"], "cost": "fast",
                      "use": "rank PROVIDED videos by median multiple",
                      "avoid": "never collects or scrapes data"},
    "yt_retention_read": {"caps": ["retention"], "cost": "fast",
                          "use": "name the biggest retention leak",
                          "avoid": "needs real retention rows"},
    "video_scene_list": {"caps": ["scene-analysis"], "cost": "slow",
                         "use": "shot boundaries before cut/B-roll planning",
                         "avoid": "crossfades merge shots — a floor, not gospel"},
    "video_word_transcript": {"caps": ["transcription"], "cost": "slow",
                              "use": "word timings, caption cues, pause cuts",
                              "avoid": "never invent a transcript on FAILED"},
    "brand_profile_get": {"caps": ["brand"], "cost": "fast",
                          "use": "read a channel brand profile + gaps",
                          "avoid": "—"},
    "brand_questions": {"caps": ["brand"], "cost": "fast",
                        "use": "questions for missing brand fields only",
                        "avoid": "never guess brand answers"},
    "brand_profile_set": {"caps": ["brand"], "cost": "fast",
                          "use": "save a validated brand profile",
                          "avoid": "only answers the user actually gave"},
    "yt_research_analyze": {"caps": ["research"], "cost": "fast",
                            "use": "structured analysis of PROVIDED video data",
                            "avoid": "never fetches or scrapes listings"},
    "style_profile_extract": {"caps": ["style"], "cost": "fast",
                              "use": "pacing/palette profile from measured data",
                              "avoid": "measures only what it is given"},
    "script_check": {"caps": ["script"], "cost": "fast",
                     "use": "measure a script: WPM, hook, AI-tells, outro",
                     "avoid": "measures, does not judge taste"},
    "audio_loudness": {"caps": ["audio-qc"], "cost": "medium",
                       "use": "measure LUFS + true peak of a workspace file",
                       "avoid": "—"},
}

CORE_TOOLS = ["director_plan", "director_check", "director_review",
              "set_plan", "job_state", "get_history", "tool_select"]

STUBS = {"noop", "echo"}

# capability -> task keywords (word-boundary matched, lowercased)
CAPABILITY_KEYWORDS = [
    ("packaging", ["title", "thumbnail", "thumb", "packaging",
                   "package rank", "title lint"]),
    ("hook-scoring", ["hook", "hooks"]),
    ("chapters", ["chapter", "chapters"]),
    ("retention", ["retention", "drop-off", "dropoff", "audience drop"]),
    ("research", ["research", "niche", "outlier", "viral",
                  "competitor", "analyze this video",
                  "analyse this video", "video analysis"]),
    ("transcription", ["transcript", "transcribe", "captions",
                       "caption", "subtitles", "subtitle",
                       "word timestamps", "pause cuts"]),
    ("scene-analysis", ["scene", "scenes", "shot", "shots",
                        "footage", "b-roll", "broll", "cut points",
                        "shot boundaries"]),
    ("brand", ["brand", "design system", "brand profile",
               "channel style", "style guide"]),
    ("style", ["style profile", "copy the style", "copy style",
               "pacing", "reference video", "editing style"]),
    ("script", ["script check", "voiceover script", "wpm",
                "check the script", "script length"]),
    ("audio-qc", ["loudness", "lufs", "audio level", "volume level",
                  "true peak"]),
    ("compute", ["csv", "compute", "sum", "total", "average",
                 "count rows", "filter rows"]),
    ("verify", ["verify", "check the file", "must contain"]),
    ("verify-web", ["fetch the page", "verify the page",
                    "published page", "check the url"]),
    ("publish", ["publish", "web app", "web page", "landing page"]),
    ("run", ["run the tests", "run tests", "execute", "run the script"]),
    ("file-write", ["write a file", "create a file", "save the file",
                    "edit the file", "update the file"]),
    ("file-read", ["read the file", "list files", "search the workspace",
                   "find in the workspace"]),
]


def classify(task_text):
    """Task text -> matched capability list (rule order)."""
    text = " " + re.sub(r"\s+", " ", str(task_text or "").lower()) + " "
    caps = []
    for cap, kws in CAPABILITY_KEYWORDS:
        for kw in kws:
            if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])",
                         text):
                caps.append(cap)
                break
    return caps


def select_tools(task_text, available=None):
    """Deterministic minimal selection. Returns {matched, caps,
    tools, note}. tools = CORE (that are available) + tools whose
    capabilities intersect the matched caps, in TOOL_META order.
    Stubs are never selected. No capability match -> matched False
    and core only: the honest answer, never a forced tool."""
    avail = None if available is None else set(available)
    caps = classify(task_text)
    capset = set(caps)
    tools = []
    for name in CORE_TOOLS:
        if avail is None or name in avail:
            tools.append(name)
    for name, meta in TOOL_META.items():
        if name in CORE_TOOLS or name in STUBS:
            continue
        if avail is not None and name not in avail:
            continue
        if capset.intersection(meta["caps"]):
            tools.append(name)
    matched = bool(caps)
    note = ("minimal set for capabilities: " + ", ".join(caps)
            if matched else
            "no capability matched this task — core tools only; "
            "do not force an unrelated tool")
    return {"matched": matched, "caps": caps, "tools": tools,
            "note": note}


def routing_table(available=None):
    """Compact capability -> tools table for the brain's context."""
    avail = None if available is None else set(available)
    by_cap = {}
    for name, meta in TOOL_META.items():
        if avail is not None and name not in avail:
            continue
        for cap in meta["caps"]:
            by_cap.setdefault(cap, []).append(name)
    lines = []
    for cap in sorted(by_cap):
        lines.append(f"{cap}: {', '.join(by_cap[cap])}")
    return "\n".join(lines)


def register_routing_tool(reg):
    """Expose tool_select: classify first, then work minimal."""
    def _select(args):
        return True, select_tools(args.get("task"), reg.names())

    reg.register(
        "tool_select",
        "Classify the task and return the MINIMAL tool set it needs "
        "(capabilities matched by rule). Args: {task}. Call this "
        "first; work only with the returned tools. matched=false "
        "means no tool fits — say so honestly. Read-only.",
        {"task": {"type": "string", "required": True,
                  "desc": "the task in plain words"}},
        _select, mutating=False, needs_allow=False, timeout=15)
    return reg
