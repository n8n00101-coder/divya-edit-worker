"""Julie agent engine: BRAND DESIGN SYSTEM (Antigravity-equivalent).

The Antigravity setup builds a brand design system by grilling the
creator with questions, then edits under it. Julie's equivalent:
a structured per-channel brand profile stored in the job workspace
(brand/<channel>.json), created by asking ONLY for the fields that
are missing (never guessing), and read by packaging/editing work.

Tools:
  brand_profile_get   read a channel profile + list missing fields
  brand_questions     missing fields -> ordered questions (pure)
  brand_profile_set   validate + save a profile (mutating, Allow)

The questioning flow is deterministic: brand_questions returns one
question per missing field, in field order, so the brain asks the
user exactly what it cannot see — the grill-me discipline without
invented answers.
"""
import json
import os
import re

import workspace_tools

# (dotted field, question, validator kind)
PROFILE_FIELDS = [
    ("channel", "Which channel is this brand profile for?", "text"),
    ("audience", "Who is the audience for this channel?", "text"),
    ("colors.primary", "What is the primary brand color (hex, e.g. #F5C518)?", "hex"),
    ("colors.accent", "What is the accent color (hex)?", "hex"),
    ("colors.background", "What is the background color (hex)?", "hex"),
    ("colors.text", "What is the main text color (hex)?", "hex"),
    ("fonts.title", "Which font do titles/headlines use?", "text"),
    ("fonts.caption", "Which font do captions use?", "text"),
    ("caption_style.position", "Where do captions sit (bottom/center/top)?", "text"),
    ("caption_style.highlight", "How are caption keywords highlighted (color/weight/none)?", "text"),
    ("pacing.avg_shot_s", "What is the target average shot length in seconds?", "posnum"),
    ("zoom_rules", "What are the zoom rules (when to punch in, how fast)?", "text"),
    ("sfx_rules", "What are the sound-effect rules (which moments get SFX)?", "text"),
    ("outro_line", "What is the locked outro/CTA line, if any?", "text"),
]

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _get(profile, dotted):
    cur = profile if isinstance(profile, dict) else {}
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _valid(kind, v):
    if kind == "hex":
        return isinstance(v, str) and bool(_HEX.match(v.strip()))
    if kind == "posnum":
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
    return isinstance(v, str) and bool(v.strip())


def missing_fields(profile):
    """Dotted fields that are absent or invalid, in field order."""
    out = []
    for dotted, _q, kind in PROFILE_FIELDS:
        if not _valid(kind, _get(profile, dotted)):
            out.append(dotted)
    return out


def brand_questions(profile):
    """One question per missing field — ask only what is missing."""
    miss = set(missing_fields(profile))
    return [{"field": d, "question": q}
            for d, q, _k in PROFILE_FIELDS if d in miss]


def validate_profile(profile):
    """Returns (ok, problems). A profile may be partial — problems
    name invalid PRESENT fields; missing fields are reported
    separately by missing_fields."""
    if not isinstance(profile, dict):
        return False, ["profile must be an object"]
    problems = []
    for dotted, _q, kind in PROFILE_FIELDS:
        v = _get(profile, dotted)
        if v is not None and not _valid(kind, v):
            problems.append(f"{dotted}: invalid {kind} value {v!r}")
    return (not problems), problems


def _brand_path(root_real, channel):
    name = re.sub(r"[^a-z0-9_-]+", "-", str(channel or "").lower()).strip("-")
    if not name:
        return None
    return workspace_tools._confined(root_real, f"brand/{name}.json")


def register_brand_tools(reg, root):
    root_real = os.path.realpath(root)

    def _get_tool(args):
        target = _brand_path(root_real, args.get("channel"))
        if target is None:
            return False, "brand_profile_get needs a channel name"
        if not os.path.isfile(target):
            return True, {"exists": False, "profile": {},
                          "missing": missing_fields({}),
                          "questions": brand_questions({})}
        try:
            with open(target, encoding="utf-8") as f:
                profile = json.load(f)
        except Exception as e:
            return False, f"brand profile unreadable: {str(e)[:120]}"
        return True, {"exists": True, "profile": profile,
                      "missing": missing_fields(profile),
                      "questions": brand_questions(profile)}

    def _questions(args):
        return True, {"questions": brand_questions(args.get("profile") or {}),
                      "missing": missing_fields(args.get("profile") or {})}

    def _set_tool(args):
        profile = args.get("profile") or {}
        ok, problems = validate_profile(profile)
        if not ok:
            return False, "invalid brand profile: " + "; ".join(problems)
        target = _brand_path(root_real, args.get("channel")
                             or _get(profile, "channel"))
        if target is None:
            return False, "brand_profile_set needs a channel name"
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, sort_keys=True)
        return True, {"saved": os.path.relpath(target, root_real),
                      "missing": missing_fields(profile),
                      "complete": not missing_fields(profile)}

    reg.register(
        "brand_profile_get",
        "Read a channel's brand design profile from the workspace "
        "(brand/<channel>.json). Args: {channel}. Returns the "
        "profile, missing fields, and the questions to ask. "
        "Read-only.",
        {"channel": {"type": "string", "required": True,
                     "desc": "channel name"}},
        _get_tool, mutating=False, needs_allow=False, timeout=15)
    reg.register(
        "brand_questions",
        "Given a (partial) brand profile, return one question per "
        "missing/invalid field, in order. Args: {profile}. Ask the "
        "user only these — never guess brand answers. Read-only.",
        {"profile": {"type": "object", "required": False,
                     "desc": "partial brand profile (default {})"}},
        _questions, mutating=False, needs_allow=False, timeout=15)
    reg.register(
        "brand_profile_set",
        "Validate and save a channel brand profile to the "
        "workspace. Args: {channel, profile}. Only save answers "
        "the user actually gave. Mutating — needs Allow.",
        {"channel": {"type": "string", "required": True,
                     "desc": "channel name"},
         "profile": {"type": "object", "required": True,
                     "desc": "brand profile object"}},
        _set_tool, mutating=True, needs_allow=True, timeout=15)
    return reg
