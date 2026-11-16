"""hooks_lib.py — Julie: the 21 hook formulas + deterministic hook scoring.

Knowledge source (VERIFIED 2026-11-16): skills/yt-script/hooks.json v1.0
from the MIT-licensed repo Jakeschincariol/youtube-agent-skill
(https://github.com/Jakeschincariol/youtube-agent-skill), fetched verbatim
from raw.githubusercontent.com/.../main. Licence: MIT, Copyright (c) 2026
Jake Schincariol — see ~/workspace/JULIE_BRAIN_KNOWLEDGE_HOOK_FORMULAS.md
for the full library (name + pattern + when to use + licence note).

The FORMULAS data below (id / name / shape / example / fails_when /
match patterns) is that file's content. The scoring panel is Julie's
own deterministic implementation of the five criteria the pipeline
asks for — curiosity_gap, specificity, timeframe, contrarian_stakes,
clarity — with the upstream hookscore.py weakest-link idea for the
total (0.6 * mean + 0.4 * weakest). No LLM, no network, no deps.
"""

import re

FORMULAS = [{'id': 'the-statistic', 'name': 'The Statistic', 'shape': 'A number the viewer did not know, stated flat, then the consequence.', 'example': '97% of the people who start a channel quit before video 30. Here is what the other 3% do differently.', 'fails_when': 'Dies if the number is vague or unverifiable. Say the source out loud.', 'match': ['\\b\\d+(\\.\\d+)?\\s?%', '\\b\\d+ (out of|in) \\d+\\b', '\\b\\d{2,}(,\\d{3})+\\b']}, {'id': 'someone-elses-result', 'name': "Someone Else's Result", 'shape': "A named person's outcome, then the mechanism.", 'example': 'This channel went from 400 subscribers to 200,000 in seven months on one format. I mapped it.', 'fails_when': 'Do not invent the number. If you cannot name the channel, use a different formula.', 'match': ['\\bthis (channel|guy|creator|account)\\b', '\\bwent from .* to\\b', '\\bin (a|one|two|three|\\d+) (week|month|year)s?\\b']}, {'id': 'the-mistake', 'name': 'The Mistake', 'shape': 'Name the error the viewer is probably making right now.', 'example': 'Your first 30 seconds are why nobody finishes your videos. It is not the topic.', 'fails_when': 'Only works if the mistake is common and the viewer can check it in one second.', 'match': ["\\byou('re| are) (probably |still )?(doing|making)\\b", '\\bthe (mistake|reason) (everyone|most people|nobody)\\b', '\\bstop (doing )?\\b']}, {'id': 'contrarian-flip', 'name': 'Contrarian Flip', 'shape': 'State the accepted advice, then reject it.', 'example': 'Everyone says post daily. I posted once a week for a year and tripled the channel.', 'fails_when': 'Needs evidence in the next 15 seconds or it reads as contrarian for its own sake.', 'match': ['\\beveryone (says|thinks|tells you)\\b', '\\bis (actually )?wrong\\b', '\\bnobody (tells|talks about)\\b']}, {'id': 'the-reveal', 'name': 'The Reveal', 'shape': 'Promise a specific thing will be shown, then show it.', 'example': 'I am going to show you the exact prompt, on screen, that wrote this video.', 'fails_when': 'You have to actually show it, early. A reveal at 8:00 is a retention cliff at 1:00.', 'match': ["\\bI('m| am) going to show you\\b", "\\bhere('s| is) (the|exactly)\\b", '\\bon screen\\b']}, {'id': 'the-superlative', 'name': 'The Superlative', 'shape': 'The single best/worst/fastest of a category.', 'example': 'This is the fastest way to turn one long video into thirty Shorts.', 'fails_when': 'Superlatives are cheap. Earn it by naming what it beat.', 'match': ['\\bthe (best|worst|fastest|easiest|only)\\b', '\\bnumber one\\b']}, {'id': 'the-clock', 'name': 'The Clock', 'shape': 'Bound the payoff in time.', 'example': 'In the next six minutes you will have a working title, thumbnail and script for your next video.', 'fails_when': "The clock has to be true. Overrun it and the next video's hook is not believed.", 'match': ['\\bin (the next )?\\d+ (seconds|minutes|hours)\\b', '\\bby the end of this video\\b', '\\bunder \\d+\\b']}, {'id': 'i-tried-it', 'name': 'I Tried It', 'shape': 'First-person experiment with a stated cost.', 'example': 'I let an AI run my channel for 30 days. I did not touch the uploads.', 'fails_when': 'Needs a real cost - time, money, risk - or there is no stake.', 'match': ['\\bI (tried|spent|tested|let|gave)\\b', '\\bfor \\d+ (days|weeks|months)\\b', "\\bso you don'?t have to\\b"]}, {'id': 'the-question', 'name': 'The Question', 'shape': 'Ask the exact question the viewer typed into search.', 'example': 'Why do your videos die at 30 seconds when the topic is fine?', 'fails_when': "Must be the viewer's question, not yours. Pull it from your own comments.", 'match': ['^(why|how|what|when|should|can|do|does|is)\\b', '\\?\\s*$']}, {'id': 'the-before-after', 'name': 'Before and After', 'shape': 'Two states, one cut between them.', 'example': 'This was my thumbnail. This is my thumbnail now. Same video, four times the click-through.', 'fails_when': 'Only works with a visual. Do not use it on a talking-head-only video.', 'match': ['\\bbefore\\b.*\\bafter\\b', '\\bthis was\\b.*\\bthis is\\b', '\\bused to\\b']}, {'id': 'the-teardown', 'name': 'The Teardown', 'shape': 'Take a real thing apart in public.', 'example': 'I pulled the nine most-viewed AI videos of the month and broke down what the titles share.', 'fails_when': 'Name what you pulled and how many. A teardown of one example is an anecdote.', 'match': ['\\b(broke|break|breaking) (it )?down\\b', '\\bteardown\\b', '\\banalys(ed|ed|is|e)\\b', '\\bI pulled\\b']}, {'id': 'the-stack', 'name': 'The Stack', 'shape': 'Two named tools combined into one outcome.', 'example': "Claude plus your YouTube Studio export gives you next week's upload schedule in one prompt.", 'fails_when': 'Both tools must be nameable and the outcome must need both.', 'match': ['\\b\\w+ (plus|\\+) \\w+\\b', '\\bcombine\\b', '\\btogether\\b']}, {'id': 'the-warning', 'name': 'The Warning', 'shape': 'A cost the viewer is about to pay.', 'example': 'Do not upload another video until you check this one setting.', 'fails_when': 'If the cost is small the hook is a lie. Reserve it.', 'match': ['\\bdo not\\b', "\\bdon'?t (upload|post|publish|start)\\b", '\\bbefore you\\b', '\\bstop\\b']}, {'id': 'the-list', 'name': 'The List', 'shape': 'A counted set, with the count in the first line.', 'example': 'Seven things I would do differently if I started a channel in 2026.', 'fails_when': 'The count must be exact and every item must be different in kind.', 'match': ['^\\d+ \\w+', '\\b(here are|these are) \\d+\\b']}, {'id': 'the-receipt', 'name': 'The Receipt', 'shape': 'Show the artifact first, explain second.', 'example': "This is the analytics page. This video did 40% of the channel's watch time. Here is why.", 'fails_when': 'Requires a real screenshot. A described receipt is not a receipt.', 'match': ['\\bthis is (the|my)\\b', '\\bscreenshot\\b', '\\bproof\\b', '\\breceipts?\\b']}, {'id': 'the-insider', 'name': 'The Insider', 'shape': 'Information from inside a system.', 'example': 'YouTube tells you which videos are underperforming. Almost nobody opens the report.', 'fails_when': 'Do not claim insider access you do not have.', 'match': ['\\b(nobody|almost nobody|most people) (knows?|opens?|uses?)\\b', '\\bhidden\\b', '\\bburied\\b']}, {'id': 'the-impossible', 'name': 'The Impossible Claim', 'shape': 'State something that sounds untrue, then prove it.', 'example': 'You can write, title, thumbnail and schedule a week of videos without opening a single editor.', 'fails_when': 'The proof has to start within 20 seconds or it reads as clickbait.', 'match': ['\\bwithout\\b', '\\bnever\\b', '\\bin one\\b', '\\bzero\\b']}, {'id': 'the-comparison', 'name': 'The Comparison', 'shape': 'Two named options, one winner.', 'example': 'I wrote the same video three ways. One of them held 62% and the other two did not.', 'fails_when': 'Say the losing option out loud. A comparison with no loser is an advert.', 'match': ['\\bvs\\.?\\b', '\\bversus\\b', '\\bwhich (one )?(is|wins)\\b', '\\bsame .* (three|two) ways\\b']}, {'id': 'the-origin', 'name': 'The Origin', 'shape': 'Where a result actually came from.', 'example': 'Every video on this channel starts in the same 12-line file. Here it is.', 'fails_when': 'Works once per channel. It is a reveal about you, and you only have one.', 'match': ['\\bevery (video|post) .* starts\\b', '\\bit all (starts|started)\\b', '\\bthe (real )?reason\\b']}, {'id': 'the-deadline', 'name': 'The Deadline', 'shape': 'Something is changing on a date.', 'example': 'The old description format stops mattering this month. Here is what replaces it.', 'fails_when': 'Only use with a real, checkable date. This is the fastest formula to lose trust with.', 'match': ['\\b(this|next) (week|month|year)\\b', '\\bis changing\\b', '\\bno longer\\b', '\\bas of\\b']}, {'id': 'the-direct-address', 'name': 'The Direct Address', 'shape': 'Name the exact viewer in the first six words.', 'example': 'If you have under a thousand subscribers, this is the only video you need this week.', 'fails_when': "Narrow beats broad. 'If you make videos' addresses nobody.", 'match': ['^if you\\b', '\\bfor (anyone|everyone|people) who\\b', '\\byou specifically\\b']}]

FORMULA_BY_ID = {f['id']: f for f in FORMULAS}
FORMULA_BY_NAME = {f['name']: f for f in FORMULAS}

# ------------------------------------------------------------ classify
def classify_hook(text):
    """Name the formula a hook text matches (upstream `match` patterns,
    most pattern hits wins). Returns (formula_name, hits); name is None
    when nothing matches — usually a summary, not a hook."""
    best, hits = None, 0
    for f in FORMULAS:
        n = sum(1 for p in f["match"] if re.search(p, text or "", re.I))
        if n > hits:
            best, hits = f, n
    return (best["name"] if best else None), hits


# ------------------------------------------------------------ scoring
_VAGUE = {"amazing", "incredible", "insane", "crazy", "huge", "massive",
          "game", "changer", "powerful", "ultimate", "best",
          "revolutionary", "unbelievable", "awesome", "great", "good",
          "stuff", "things", "very", "really"}
_FILLER = {"basically", "actually", "literally", "just", "so", "kind",
           "sort", "like", "guys", "hey", "welcome", "subscribe",
           "channel", "today", "video"}
_NUMBER = re.compile(
    r"\b\d[\d,.]*\s?(%|k|m|x)?\b|\$\s?\d|\b\d+\s?(second|minute|hour|"
    r"day|week|month|year)s?\b", re.I)
_TIMEFRAME = re.compile(
    r"\b(in (the next )?\d+ (second|minute|hour|day|week|month|year)s?|"
    r"by the end|before|until|deadline|this (week|month|year)|"
    r"next (week|month|year)|\d+ (days|weeks|months|years)|"
    r"in \d+ (days|weeks|months|years)|under \d+|as of|no longer|"
    r"stops|ends? (this|next))\b", re.I)
_CURIOSITY = re.compile(
    r"\b(why|how|what|which|who|nobody|almost nobody|hidden|secret|"
    r"until|but|except|reason|never told|no one)\b", re.I)
_STAKES = re.compile(
    r"\b(everyone (says|thinks|tells you)|is (actually )?wrong|"
    r"nobody (tells|talks about)|stop|do not|don'?t|mistake|wrong|"
    r"lose|lost|wasting|waste|quit|fail|broke|cost|risk|never|die|"
    r"dying|dead|warning|before you)\b", re.I)


def _words(t):
    return re.findall(r"[a-z0-9'%$.]+", (t or "").lower())


def _score_curiosity_gap(t):
    n = len(_CURIOSITY.findall(t))
    s = 22 + n * 18
    if t.strip().endswith("?"):
        s += 16
    if re.search(r"\b(but|yet|except|until)\b", t, re.I):
        s += 10  # an open contrast leaves the loop open
    if re.search(r"\b(because|so that|which means|the answer is)\b",
                 t, re.I):
        s -= 20  # a hook that answers itself has no gap left
    return max(0, min(100, s))


def _score_specificity(t):
    w = _words(t)
    if not w:
        return 0
    nums = len(_NUMBER.findall(t))
    vague = sum(1 for x in w if x in _VAGUE)
    s = 30 + nums * 24 - vague * 14
    # capitalised non-initial words read as named things
    s += min(18, 6 * sum(1 for x in t.split()[1:] if x[:1].isupper()))
    return max(0, min(100, s))


def _score_timeframe(t):
    n = len(_TIMEFRAME.findall(t))
    return max(0, min(100, 12 + n * 44))


def _score_contrarian_stakes(t):
    n = len(_STAKES.findall(t))
    s = 16 + n * 28
    if _NUMBER.search(t):
        s += 10  # a cost with a number attached lands harder
    return max(0, min(100, s))


def _score_clarity(t):
    w = _words(t)
    if not w:
        return 0
    n = len(w)
    if 7 <= n <= 26:
        s = 100
    elif n < 7:
        s = max(35, 100 - (7 - n) * 13)
    else:
        s = max(10, 100 - (n - 26) * 6)
    filler = sum(1 for x in w if x in _FILLER)
    s -= filler * 6
    if len([x for x in w if len(x) > 11]) > 2:
        s -= 10  # stacked long words read slowly
    return max(0, min(100, s))


_CRITERIA = (("curiosity_gap", _score_curiosity_gap),
             ("specificity", _score_specificity),
             ("timeframe", _score_timeframe),
             ("contrarian_stakes", _score_contrarian_stakes),
             ("clarity", _score_clarity))


def score_hook(text):
    """Deterministic hook score. Returns {criteria: {name: 0-100},
    total: 0-100 (0.6*mean + 0.4*weakest — a hook leaks at its weakest
    criterion), formula: matched formula name or None, band}."""
    text = str(text or "")
    crit = {name: fn(text) for name, fn in _CRITERIA}
    vals = list(crit.values())
    total = round(0.6 * (sum(vals) / len(vals)) + 0.4 * min(vals))
    name, _hits = classify_hook(text)
    return {"criteria": crit, "total": total, "formula": name,
            "band": ("STRONG" if total >= 70 else
                     "WORKABLE" if total >= 50 else "WEAK")}


# ------------------------------------------------- hook variant maker
def _clean_topic(topic, angle=""):
    t = " ".join(str(angle or topic or "").split()).strip(" .")
    return t[:1].upper() + t[1:] if t else ""


def generate_hook_variants(topic, angle="", count=3):
    """Deterministic hook variants in named formulas, built ONLY from
    the topic/angle words given — no invented statistics or results.
    Uses the three formulas fillable without fabricating facts (The
    Question, Contrarian Flip, The Clock), plus The Mistake / The
    Reveal when the caller wants more. Returns ranked dicts:
    {text, formula, formula_id, score} best first."""
    subj = _clean_topic(topic) or "This story"
    low = subj.lower()
    templates = [
        ("the-question",
         f"Why does {low} — and why does nobody talk about it?"),
        ("contrarian-flip",
         f"Everyone thinks they understand {low}. Everyone is wrong."),
        ("the-clock",
         f"In the next 2 minutes, {low} will change how you see it."),
        ("the-mistake",
         f"The mistake everyone makes about {low} — stop doing it."),
        ("the-reveal",
         f"Here is exactly what {low} really hides. On screen."),
    ]
    out = []
    for fid, text in templates[:max(1, min(count, len(templates)))]:
        sc = score_hook(text)
        out.append({"text": text,
                    "formula": FORMULA_BY_ID[fid]["name"],
                    "formula_id": fid, "score": sc})
    out.sort(key=lambda v: -v["score"]["total"])
    return out


if __name__ == "__main__":
    strong = score_hook(
        "97% of channels quit before video 30 — here is what the "
        "other 3% do in the next 7 days, and why nobody tells you")
    weak = score_hook("Welcome to my channel, today we talk about videos")
    assert strong["total"] > weak["total"], (strong, weak)
    assert strong["formula"] == "The Statistic", strong
    assert len(FORMULAS) == 21
    print("hooks_lib self-check OK", strong["total"], weak["total"])
