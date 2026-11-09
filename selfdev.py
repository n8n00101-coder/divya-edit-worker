"""Divya self-development (OWNER ONLY).
The owner asks for a change on WhatsApp ("divya change: ..."). The Worker checks the owner number and
starts this job. Actions:
  plan  -> AI reads Divya's code (repo + live Worker script), writes the change on branch selfdev/<id>,
           runs checks, then tells the owner: "ok <id>" to deploy, "cancel <id>" to drop.
  apply -> merges selfdev/<id> into main and, if the Worker changed, deploys it to Cloudflare (backup kept).
  undo  -> redeploys the Worker backup and reverts the last selfdev merge.
Never prints or commits secrets."""
import base64, json, os, re, subprocess, sys, textwrap, time
import httpx

WORKER = os.environ["WORKER_URL"].rstrip("/")
KEY = os.environ["RUNNER_KEY"]
JOB = sys.argv[1]
CF_ACC = "ba39b7fb8bae4e32999a8a77c8e04039"
CF_SCRIPT = os.getenv("CF_SCRIPT", "divya")
LIVE = "cfworker/live_divya.js"
CODE_EXT = (".py", ".js", ".yml", ".yaml", ".md", ".html", ".css", ".json", ".txt", ".sh")
SKIP_DIRS = (".git", "fonts", "voices", "docs/app", "node_modules")


def sh(*a, check=True):
    r = subprocess.run(a, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(a[:3])} failed: {(r.stderr or r.stdout)[-400:]}")
    return r.stdout


def load_job():
    r = httpx.post(f"{WORKER}/job", json={"job": JOB}, headers={"x-runner-key": KEY}, timeout=30)
    r.raise_for_status()
    j = r.json()
    for k in ("WA_TOKEN", "GROQ_KEY"):
        for v in str(j.get(k, "")).split(","):
            if v.strip():
                print(f"::add-mask::{v.strip()}")
    return j


J = load_job()
OWNER = J["to"]
WA_TOKEN, PHONE_ID = J["WA_TOKEN"], J["PHONE_ID"]
GROQ_KEYS = [k.strip() for k in str(J.get("GROQ_KEY", "")).split(",") if k.strip()]
GEMINI = os.getenv("GEMINI_KEY", "").strip()
OWNERS = [s.strip() for s in str(J.get("OWNERS", "")).split(",") if s.strip()]


def say(text):
    httpx.post(f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages", headers={"Authorization": f"Bearer {WA_TOKEN}"},
               json={"messaging_product": "whatsapp", "to": OWNER, "type": "text", "text": {"body": text[:4000]}}, timeout=60)


def state(st, note=""):
    try:
        httpx.post(f"{WORKER}/selfdev/state", json={"id": J["id"], "state": st, "note": note[:500], "to": OWNER},
                   headers={"x-runner-key": KEY}, timeout=20)
    except Exception as e:
        print("state post failed", type(e).__name__)


# ---------------------------------------------------------------- LLM
GROQ_MODELS = ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905", "qwen/qwen3-32b", "llama-3.3-70b-versatile"]


def llm(system, user, max_tokens=8000):
    last = ""
    if GEMINI:
        for m in ("gemini-2.5-pro", "gemini-2.5-flash"):
            try:
                r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI}",
                               json={"systemInstruction": {"parts": [{"text": system}]},
                                     "contents": [{"parts": [{"text": user}]}],
                                     "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": max_tokens}},
                               timeout=240)
                if r.status_code == 200:
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
                last = f"gemini {r.status_code}"
            except Exception as e:
                last = f"gemini {type(e).__name__}"
    for key in GROQ_KEYS:
        for m in GROQ_MODELS:
            try:
                r = httpx.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                               json={"model": m, "temperature": 0.2, "max_tokens": max_tokens,
                                     "response_format": {"type": "json_object"},
                                     "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                               timeout=240)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
                last = f"groq {m} {r.status_code}"
                if r.status_code == 429:
                    time.sleep(8)
            except Exception as e:
                last = f"groq {m} {type(e).__name__}"
    raise RuntimeError("AI brain ready ledu: " + last)


def ask_json(system, user, max_tokens=8000):
    for _ in range(2):
        t = llm(system, user, max_tokens)
        t = re.sub(r"^```(json)?|```$", "", t.strip(), flags=re.M).strip()
        try:
            return json.loads(t)
        except Exception:
            m = re.search(r"\{.*\}", t, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
    raise RuntimeError("AI JSON reply ardham kaaledu")


# ---------------------------------------------------------------- Cloudflare
def cf_headers():
    tok = os.getenv("CF_API_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("CF_API_TOKEN GitHub secret ledu, Worker deploy cheyalenu")
    return {"Authorization": f"Bearer {tok}"}


def cf_download():
    r = httpx.get(f"https://api.cloudflare.com/client/v4/accounts/{CF_ACC}/workers/scripts/{CF_SCRIPT}/content/v2",
                  headers=cf_headers(), timeout=60)
    r.raise_for_status()
    return r.text


def cf_deploy(code):
    meta = {"main_module": "divya.js", "compatibility_date": "2024-11-01",
            "keep_bindings": ["secret_text", "plain_text", "kv_namespace"]}
    files = {"metadata": (None, json.dumps(meta), "application/json"),
             "divya.js": ("divya.js", code, "application/javascript+module")}
    r = httpx.put(f"https://api.cloudflare.com/client/v4/accounts/{CF_ACC}/workers/scripts/{CF_SCRIPT}",
                  headers=cf_headers(), files=files, timeout=120)
    j = r.json()
    if not j.get("success"):
        raise RuntimeError(f"Cloudflare deploy fail: {str(j.get('errors'))[:300]}")
    # health check
    time.sleep(4)
    h = httpx.get(f"{WORKER}/health", timeout=30)
    if h.status_code != 200 or not h.json().get("ok"):
        raise RuntimeError(f"health check fail ({h.status_code})")


# ---------------------------------------------------------------- repo helpers
def repo_files():
    out = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if not any(os.path.join(root, d).lstrip("./").startswith(s) for s in SKIP_DIRS)]
        for f in files:
            p = os.path.join(root, f)[2:]
            if p.endswith(CODE_EXT) and os.path.getsize(p) < 400_000:
                out.append(p)
    return sorted(out)


def outline(path):
    """Compact map of a file: top-level defs/functions with line numbers."""
    pat = re.compile(r"^\s*(async\s+)?(def|class|function|const\s+\w+\s*=\s*(async\s*)?\(|export default|name:|on:|jobs:)")
    lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    marks = [f"{i+1}: {l.strip()[:110]}" for i, l in enumerate(lines) if pat.match(l)]
    return f"## {path} ({len(lines)} lines)\n" + "\n".join(marks[:80])


def window(path, start, end):
    lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    start, end = max(1, int(start)), min(len(lines), int(end))
    return f"### {path} lines {start}-{end}\n" + "\n".join(lines[start - 1:end])


SYS_PICK = """You are Divya's self-development engineer. Divya is a WhatsApp + PWA AI agent (Cloudflare Worker brain in
cfworker/live_divya.js = the LIVE production script, Python video engine run on GitHub Actions: runner.py, doc3.py, autoedit.py,
editor.py, workflows in .github/workflows). The OWNER asked for a change. From the file outlines, choose the code regions you
must read to make the change. Reply JSON {"read":[{"path":"...","start":N,"end":M}], "new_files_maybe":["..."]}.
Max 8 regions, max 300 lines each. Prefer the live Worker file for chat/WhatsApp/app behaviour."""

SYS_EDIT = """You are Divya's self-development engineer. Make the OWNER's change with minimal, safe edits.
Rules: keep existing features working; never print, log, hardcode or send secrets; never weaken the owner-only checks
(OWNERS var) or the RUNNER_KEY / FORWARD_SECRET checks; never give friends or app users self-development power;
no paid services; Worker code is a Cloudflare module (no Node APIs); Python 3.11 on ubuntu-latest.
Each edit replaces an EXACT existing snippet ("find", copied byte-for-byte from the code shown, unique in the file, 1-40 lines)
with "replace". For a new file give "path" and full "content" and no "find".
Reply JSON {"summary_te":"2-4 short Tenglish lines for the owner on what changed",
 "edits":[{"path":"...","find":"...","replace":"..."} | {"path":"...","content":"..."}],
 "needs_owner":"empty, or what only the owner can do (e.g. sign up somewhere, add a key)"}"""


def apply_edits(edits):
    changed = []
    for e in edits:
        p = e["path"].lstrip("./")
        if p.startswith(".git/") or ".." in p:
            raise RuntimeError(f"bad path {p}")
        if "find" in e and e.get("find"):
            src = open(p, encoding="utf-8").read()
            n = src.count(e["find"])
            if n != 1:
                raise RuntimeError(f"{p}: find snippet matched {n} times")
            src = src.replace(e["find"], e["replace"])
            open(p, "w", encoding="utf-8").write(src)
        else:
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            open(p, "w", encoding="utf-8").write(e["content"])
        changed.append(p)
    return sorted(set(changed))


SECRET_PAT = re.compile(r"(gsk_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|EAA[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_\-]{30,})")


def checks(changed):
    for p in changed:
        txt = open(p, encoding="utf-8", errors="ignore").read()
        if SECRET_PAT.search(txt):
            raise RuntimeError(f"{p}: secret-like value found, stopped")
        if p.endswith(".py"):
            sh("python", "-m", "py_compile", p)
        elif p.endswith(".js"):
            tmp = "/tmp/check.mjs"
            open(tmp, "w").write(txt)
            sh("node", "--check", tmp)
        elif p.endswith((".yml", ".yaml")):
            import yaml
            yaml.safe_load(txt)
        elif p.endswith(".json"):
            json.loads(txt)
    if LIVE in changed:
        src = open(LIVE, encoding="utf-8").read()
        for must in ("export default", "env.OWNERS", "x-runner-key", "async function handle("):
            if must not in src:
                raise RuntimeError(f"Worker check fail: '{must}' missing")


def git_setup():
    sh("git", "config", "user.name", "Divya selfdev")
    sh("git", "config", "user.email", "divya-selfdev@users.noreply.github.com")
    sh("git", "fetch", "origin", "--prune")


# ---------------------------------------------------------------- actions
def do_plan():
    sid = J["id"]
    req = J["request"].strip()
    say(f"🛠️ Change {sid} start chesa: \"{req[:200]}\". Code chadivi plan chesthunna (2-6 min).")
    state("planning")
    git_setup()
    sh("git", "checkout", "-B", f"selfdev/{sid}", "origin/main")
    have_cf = bool(os.getenv("CF_API_TOKEN", "").strip())
    if have_cf:
        os.makedirs("cfworker", exist_ok=True)
        open(LIVE, "w", encoding="utf-8").write(cf_download())
    files = [f for f in repo_files() if not f.startswith("cfworker/backup/")]
    outl = "\n\n".join(outline(f) for f in files if f.endswith((".py", ".js", ".yml")) and (have_cf or f != LIVE))
    outl += "\n\nOther files: " + ", ".join(f for f in files if not f.endswith((".py", ".js", ".yml")))
    pick = ask_json(SYS_PICK, f"OWNER CHANGE REQUEST:\n{req}\n\nFILE OUTLINES:\n{outl[:60000]}", 2000)
    ctx = []
    for r in (pick.get("read") or [])[:8]:
        if os.path.exists(r.get("path", "")):
            ctx.append(window(r["path"], r.get("start", 1), min(int(r.get("end", 300)), int(r.get("start", 1)) + 300)))
    plan = ask_json(SYS_EDIT, f"OWNER CHANGE REQUEST:\n{req}\n\nCODE:\n" + "\n\n".join(ctx)[:90000], 12000)
    edits = plan.get("edits") or []
    if not edits:
        state("failed", "no edits")
        return say(f"⚠️ {sid}: ee change ki code edit ardham kaaledu. Konchem detail ga cheppu. {plan.get('needs_owner','')}")
    changed = apply_edits(edits)
    checks(changed)
    if LIVE in changed and not have_cf:
        raise RuntimeError("Worker change ki CF_API_TOKEN avasaram")
    sh("git", "add", "-A")
    sh("git", "commit", "-m", f"selfdev {sid}: {req[:60]}")
    sh("git", "push", "-f", "origin", f"selfdev/{sid}")
    stat = sh("git", "diff", "--shortstat", "origin/main", "HEAD").strip()
    state("ready", plan.get("summary_te", ""))
    need = plan.get("needs_owner") or ""
    say(f"✅ Change {sid} ready (test pass):\n{plan.get('summary_te','')}\nFiles: {', '.join(changed)} ({stat})"
        + (f"\nNee nundi kavali: {need}" if need else "")
        + f"\n\nDeploy cheyalante: ok {sid}\nVaddu ante: cancel {sid}")


def do_apply():
    sid = J["id"]
    state("deploying")
    git_setup()
    sh("git", "checkout", "-B", "main", "origin/main")
    changed = sh("git", "diff", "--name-only", "origin/main", f"origin/selfdev/{sid}").split()
    if LIVE in changed:
        os.makedirs("cfworker/backup", exist_ok=True)
        open(f"cfworker/backup/{sid}.js", "w", encoding="utf-8").write(cf_download())
    sh("git", "merge", "--no-ff", "-m", f"selfdev {sid} merged (owner ok)", f"origin/selfdev/{sid}")
    if LIVE in changed:
        try:
            cf_deploy(open(LIVE, encoding="utf-8").read())
        except Exception:
            cf_deploy(open(f"cfworker/backup/{sid}.js", encoding="utf-8").read())
            raise
    sh("git", "add", "-A")
    sh("git", "commit", "--allow-empty", "-m", f"selfdev {sid}: backup + deploy record")
    sh("git", "push", "origin", "main")
    sh("git", "push", "origin", "--delete", f"selfdev/{sid}", check=False)
    state("live")
    say(f"🚀 Change {sid} live ayyindi." + (" Worker deploy + health check OK." if LIVE in changed else "")
        + " Emaina tedaga unte: undo")


def do_undo():
    git_setup()
    sh("git", "checkout", "-B", "main", "origin/main")
    log = sh("git", "log", "--merges", "--format=%H %s", "-n", "20").splitlines()
    last = next((l for l in log if re.search(r"selfdev (\w+) merged", l)), None)
    if not last:
        return say("Undo cheyadaniki selfdev change emi ledu.")
    sha, sid = last.split()[0], re.search(r"selfdev (\w+) merged", last).group(1)
    bk = f"cfworker/backup/{sid}.js"
    if os.path.exists(bk):
        cf_deploy(open(bk, encoding="utf-8").read())
    sh("git", "revert", "--no-edit", "-m", "1", sha)
    sh("git", "push", "origin", "main")
    say(f"↩️ Change {sid} undo chesa. Mundu version malli live lo undi.")


def main():
    if OWNER not in OWNERS:
        raise SystemExit("not owner")  # defence in depth: the Worker already checks
    act = J.get("action", "plan")
    try:
        {"plan": do_plan, "apply": do_apply, "undo": do_undo}[act]()
    except Exception as e:
        state("failed", str(e))
        say(f"⚠️ Self-change {J.get('id','')} ({act}) fail: {str(e)[:300]}. Emi marchaledu / live safe ga undi.")
        raise


main()
