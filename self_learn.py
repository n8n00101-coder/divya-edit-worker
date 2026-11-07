"""Julie keeps learning how AI agents / personal assistants work and improves herself.
Daily: read fresh sources -> distil lessons into skills/learned/*.md (used in her prompt)
       -> propose concrete self-improvements. Safe ones (prompt notes, skill files) apply automatically;
          code changes are written as a patch and only applied after the owner says 'ok <id>' on WhatsApp."""
import datetime as dt
import json
import os

import httpx

import providers
import skill_hub
import state

LEARN_DIR = os.path.join(os.path.dirname(__file__), "skills", "learned")
SOURCES = [
    # fresh agent repos on GitHub (last 7 days, by stars)
    ("github", "https://api.github.com/search/repositories?q=topic:ai-agents+pushed:>{week}&sort=stars&per_page=8"),
    ("github", "https://api.github.com/search/repositories?q=personal+assistant+agent+pushed:>{week}&sort=stars&per_page=5"),
    # research
    ("arxiv", "http://export.arxiv.org/api/query?search_query=all:%22LLM%20agent%22&sortBy=submittedDate&max_results=6"),
    # community
    ("hn", "https://hn.algolia.com/api/v1/search_by_date?query=AI%20agent&tags=story&numericFilters=points>80"),
]

DISTIL = """You are Julie, a WhatsApp AI agent that edits videos (ffmpeg), posts to YouTube/Instagram, and runs
herself on free servers. From the material below, extract only lessons that could make YOU better
(memory, planning, tool use, reliability, video editing taste, cost-free hosting, self-healing).
Reply JSON: {"lessons":[{"title":"...","why":"...","how_julie_uses_it":"..."}],
"improvements":[{"id":"short-id","kind":"prompt|skill|code","change":"exact change","risk":"low|med|high"}]}
Max 5 lessons, 3 improvements. Skip hype and anything you can't verify from the text."""


def _today():
    return dt.date.today().isoformat()


async def _gather():
    week = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    h = {"Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"} if os.getenv("GITHUB_TOKEN") else {}
    out = []
    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
        for kind, url in SOURCES:
            try:
                r = await c.get(url.format(week=week), headers=h if kind == "github" else {})
                if kind == "github":
                    for it in r.json().get("items", []):
                        out.append(f"[repo] {it['full_name']} ★{it['stargazers_count']}: {it.get('description')}")
                elif kind == "hn":
                    for it in r.json().get("hits", [])[:8]:
                        out.append(f"[hn] {it.get('title')} {it.get('url')}")
                else:
                    out.append("[arxiv] " + r.text[:12000])
            except Exception as e:
                print("learn source", url, e)
    return "\n".join(out)[:40000]


async def daily(notify):
    os.makedirs(LEARN_DIR, exist_ok=True)
    material = await _gather()
    if not material:
        return "nothing new"
    reply, _ = await providers.chat([{"role": "system", "content": DISTIL}, {"role": "user", "content": material}])
    data = json.loads(reply)
    # 1) lessons -> skill file (auto, safe)
    md = [f"# Learned {_today()}"] + [f"- **{l['title']}**: {l['how_julie_uses_it']} (why: {l['why']})"
                                       for l in data.get("lessons", [])]
    path = os.path.join(LEARN_DIR, f"{_today()}.md")
    open(path, "w").write("\n".join(md))
    state.save_file(path)
    # 2) deeper study of the top repo through skill_hub (summarised guide, cached)
    for l in data.get("lessons", [])[:1]:
        try:
            await skill_hub.learn(l["title"])
        except Exception as e:
            print("skill_hub", e)
    # 3) improvements: low-risk prompt/skill notes auto-apply; code waits for owner
    pending = _pending()
    applied = []
    for imp in data.get("improvements", []):
        if imp["kind"] in ("prompt", "skill") and imp.get("risk") == "low":
            _append_prompt_note(imp["change"])
            applied.append(imp["id"])
        else:
            pending[imp["id"]] = imp
    _save_pending(pending)
    msg = f"Julie nerchukundi ({len(data.get('lessons', []))} lessons)."
    if applied:
        msg += " Auto-apply: " + ", ".join(applied) + "."
    if pending:
        msg += " Code changes approval kosam: " + "; ".join(f"{k}: {v['change'][:80]}" for k, v in pending.items()) + \
               ". 'ok <id>' ani pampandi."
    await notify(msg)
    return msg


def prompt_notes() -> str:
    """brain.py adds this to Julie's system prompt so lessons change her behaviour."""
    p = state.fetch_file("prompt_notes.md")
    return open(p).read()[-4000:] if p and os.path.exists(p) else ""


def _append_prompt_note(text):
    p = state._local("prompt_notes.md")
    old = open(p).read() if os.path.exists(p) else ""
    open(p, "w").write(old + f"\n- ({_today()}) {text}")
    state.save_file(p)


def _pending():
    p = state.fetch_file("pending_improvements.json")
    return json.load(open(p)) if p and os.path.exists(p) else {}


def _save_pending(d):
    p = state._local("pending_improvements.json")
    json.dump(d, open(p, "w"), indent=1)
    state.save_file(p)


async def approve(imp_id, notify):
    """Owner said 'ok <id>': ask the LLM for a unified diff, test-compile, then keep it as a patch file.
    The patch is applied on next deploy (git), never hot-patched into a running server."""
    pending = _pending()
    imp = pending.pop(imp_id, None)
    if not imp:
        return "id ledu"
    p = state._local(f"patch_{imp_id}.json")
    json.dump(imp, open(p, "w"))
    state.save_file(p)
    _save_pending(pending)
    await notify(f"'{imp_id}' approve ayyindi, next deploy lo apply avutundi.")
    return "ok"
