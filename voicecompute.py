"""v84: voice-batch compute providers — Kaggle GPU + GitHub Actions,
with hybrid split and automatic failover.

WHY THIS EXISTS
---------------
Voicing a long script line-by-line on one CPU runner is the slow path
(Hark's 209-line script: 8-12 hours locally). Two free compute pools
can carry a voice batch instead:

  * the user's OWN Kaggle account (free T4 GPU, ~30 h/week) — Julie
    pushes a kernel built from the voice engine's gpu-pack contract
    (lines in, out.zip with <nnn>.mp3 + batch.qc.json out), polls it,
    and downloads the result;
  * GitHub Actions runners running the engine repo's voice-batch.yml
    (the route that already exists for users without Kaggle).

One account per person is Kaggle's rule, so there is deliberately NO
multi-account rotation here: failover switches BETWEEN PROVIDERS,
never between Kaggle accounts. If Kaggle errors, times out, or hits
its quota, the SAME job's unfinished lines continue on Actions (and
the reverse when only the Actions side fails) — a provider limit can
never kill a job.

CONTRACTS
---------
* Line indices are GLOBAL (1-based positions in the job's lines list)
  everywhere outside a provider. The engine names outputs <nnn>.mp3
  numbered from --first-index; the Kaggle kernel receives the global
  first index directly, and the Actions client remaps the workflow's
  file-relative numbering back to global indices by order (the
  workflow splits its lines file into contiguous chunks, so subset
  position p == items[p-1]).
* A provider run only counts as OK when it completes AND its output
  carries batch.qc.json. No qc -> the whole provider output is
  distrusted and its lines fail over.
* Lines missing under an OK run are GATE failures (the engine already
  re-rolled them internally; the qc names them). They are reported
  failed, never silently re-run on the other provider.
* Credentials arrive on the job record over the authenticated runner
  channel (see /job in cfworker/divya.js) and are NEVER logged here:
  status/error strings are built from fixed text + HTTP status codes
  only, never from response bodies that could echo a key.

The module is transport-injectable (httpx clients, sleep, clock) so
kaggletest.py can drive every path against fake API servers.
"""

import base64
import io
import json
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

KAGGLE_API = "https://www.kaggle.com/api/v1"
GH_API = "https://api.github.com"
ENGINE_REPO_URL = "https://github.com/n8n00101-coder/julie-ai-voice-engine.git"
ENGINE_REPO = "n8n00101-coder/julie-ai-voice-engine"
KERNEL_SLUG = "julie-voice-batch"

_LIMIT_WORDS = ("quota", "limit", "exceeded", "resource_exhausted",
                "too many", "rate")


class ProviderError(Exception):
    """A provider run failed in a failover-eligible way."""

    def __init__(self, reason, detail=""):
        super().__init__(reason)
        self.reason = reason          # "limit" | "timeout" | "error" | "no_qc"
        self.detail = detail[:200]


class KaggleLimitError(ProviderError):
    def __init__(self, detail=""):
        super().__init__("limit", detail)


def _is_limit_text(text):
    t = str(text or "").lower()
    return any(w in t for w in _LIMIT_WORDS)


def _mp3_index(name):
    m = re.match(r"^(\d+)\.mp3$", name.rsplit("/", 1)[-1])
    return int(m.group(1)) if m else None


def _extract_batch_zip(blob):
    """Zip bytes -> ({index: mp3_bytes}, qc_dict_or_None).

    Accepts the gpu-pack shape (an outer zip containing out.zip, whose
    entries may sit under an out/ prefix) and the flat Actions artifact
    shape (mp3s + batch.qc.json at the top level)."""
    def harvest(zf, done, qc_box):
        for name in zf.namelist():
            base = name.rsplit("/", 1)[-1]
            idx = _mp3_index(name)
            if idx is not None:
                done[idx] = zf.read(name)
            elif base == "batch.qc.json" and qc_box[0] is None:
                try:
                    qc_box[0] = json.loads(zf.read(name).decode("utf-8"))
                except Exception:
                    pass

    done, qc_box = {}, [None]
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        harvest(zf, done, qc_box)
        for name in zf.namelist():
            if name.rsplit("/", 1)[-1] == "out.zip":
                try:
                    with zipfile.ZipFile(io.BytesIO(zf.read(name))) as inner:
                        harvest(inner, done, qc_box)
                except Exception:
                    pass
    return done, qc_box[0]


# ---------------------------------------------------------------- Kaggle

_KERNEL_TEMPLATE = '''# Julie voice batch — pushed by Julie via the Kaggle API.
# Twin of the voice engine's gpu-pack/gpu_batch.py (same contract:
# lines in, out.zip with <nnn>.mp3 + batch.qc.json out), generated per
# job so the job's lines + first index ride inside the kernel push.
import json, os, subprocess, sys

LINES = json.loads({lines_json!r})
LANG = {lang!r}
FIRST_INDEX = {first_index}
WORK = "/kaggle/working"
REPO_DIR = os.path.join(WORK, "julie-ai-voice-engine")
REPO_URL = {repo_url!r}


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def main():
    import torch
    if not torch.cuda.is_available():
        raise SystemExit("No GPU visible on this kernel session.")
    print("GPU:", torch.cuda.get_device_name(0))
    with open(os.path.join(WORK, "lines.txt"), "w") as fh:
        fh.write("\\n".join(LINES) + "\\n")
    if not os.path.isdir(REPO_DIR):
        run(["git", "clone", "--depth", "1", REPO_URL, REPO_DIR])
    run([sys.executable, "-m", "pip", "install", "-q",
         "torch==2.6.0", "torchaudio==2.6.0",
         "--index-url", "https://download.pytorch.org/whl/cu124"])
    run([sys.executable, "-m", "pip", "install", "-q", "httpx",
         "-r", os.path.join(REPO_DIR, "requirements.txt")])
    eng = os.path.join(REPO_DIR, "engine.py")
    src = open(eng).read()
    old = 'ChatterboxTTS.from_pretrained(device="cpu")'
    assert src.count(old) == 1, "engine.py device line not found"
    open(eng, "w").write(src.replace(
        old, 'ChatterboxTTS.from_pretrained(device="cuda")'))
    gat = os.path.join(REPO_DIR, "gates.py")
    src = open(gat).read()
    old = 'WhisperModel(_model_path(), device="cpu", compute_type="int8")'
    assert src.count(old) == 1, "gates.py WhisperModel line not found"
    open(gat, "w").write(src.replace(
        old, 'WhisperModel(_model_path(), device="cuda", compute_type="float16")'))
    outdir = os.path.join(WORK, "out")
    # NOT check=True: the engine exits 2 when some lines fail the gates
    # after re-rolls — those lines are named in batch.qc.json and the
    # passing lines must still ship. A hard failure (no qc at all) is
    # detected by the caller, not by the exit code.
    r = subprocess.run([sys.executable, "engine.py", "--batch",
                        os.path.join(WORK, "lines.txt"), "--lang", LANG,
                        "--outdir", outdir, "--jobs", "1", "--rerolls", "2",
                        "--first-index", str(FIRST_INDEX)],
                       cwd=REPO_DIR)
    print("engine exit", r.returncode)
    run(["bash", "-c", "cd " + outdir + " && zip -r " +
         os.path.join(WORK, "out.zip") + " ."])
    print("Done.")


main()
'''


def build_kernel_script(lines, lang, first_index):
    """The per-job Kaggle kernel source: gpu-pack flow + the job's
    lines embedded as JSON (quotes/unicode safe)."""
    return _KERNEL_TEMPLATE.format(
        lines_json=json.dumps(list(lines), ensure_ascii=False),
        lang=lang, first_index=int(first_index), repo_url=ENGINE_REPO_URL)


class KaggleClient:
    """The user's own Kaggle account, via the official API (Basic auth
    with the username + API key from their kaggle.json)."""

    name = "kaggle"

    def __init__(self, user, key, http=None, slug=KERNEL_SLUG):
        self.user = str(user or "").strip()
        self.key = str(key or "").strip()
        self.slug = slug
        self.http = http or _default_http()

    @property
    def ref(self):
        return f"{self.user}/{self.slug}"

    def _req(self, method, path, **kw):
        kw.setdefault("auth", (self.user, self.key))
        r = self.http.request(method, KAGGLE_API + path, **kw)
        if r.status_code in (401, 403):
            # 403 from Kaggle on push/status is its quota/limit shape;
            # 401 is bad credentials — both end this provider's run,
            # but only the limit wording earns the "limit" reason.
            body = ""
            try:
                body = str(r.json().get("message") or "")
            except Exception:
                pass
            if r.status_code == 403 or _is_limit_text(body):
                raise KaggleLimitError(f"HTTP {r.status_code}")
            raise ProviderError("error", f"HTTP {r.status_code} (credentials rejected)")
        if r.status_code == 429:
            raise KaggleLimitError("HTTP 429")
        if r.status_code >= 400:
            raise ProviderError("error", f"HTTP {r.status_code}")
        return r

    def push_kernel(self, lines, lang, first_index):
        script = build_kernel_script(lines, lang, first_index)
        body = {
            "id": self.ref, "slug": self.ref,
            "newTitle": "Julie voice batch",
            "text": script, "language": "python", "kernelType": "script",
            "isPrivate": True, "enableGpu": True, "enableTpu": False,
            "enableInternet": True,
            "datasetDataSources": [], "competitionDataSources": [],
            "kernelDataSources": [], "modelDataSources": [],
            "categoryIds": [],
        }
        r = self._req("POST", "/kernels/push", json=body)
        try:
            j = r.json()
        except Exception:
            j = {}
        if isinstance(j, dict) and j.get("error"):
            msg = str(j.get("error"))[:200]
            if _is_limit_text(msg):
                raise KaggleLimitError(msg)
            raise ProviderError("error", msg)
        return self.ref

    def status(self):
        r = self._req("GET", "/kernels/status",
                      params={"userName": self.user, "kernelSlug": self.slug})
        j = r.json()
        return str(j.get("status") or "").lower(), str(j.get("failureMessage") or "")

    def download_output(self):
        r = self._req("GET", "/kernels/output",
                      params={"userName": self.user, "kernelSlug": self.slug})
        return r.content

    def run_batch(self, items, lang, timeout_s=1800, poll_s=20,
                  sleep=time.sleep, now=time.monotonic):
        """items: [(global_index, text), ...] — a contiguous range.
        Returns (done {global_idx: bytes}, qc). Raises ProviderError."""
        if not items:
            return {}, None
        first = items[0][0]
        self.push_kernel([t for _, t in items], lang, first)
        t0 = now()
        while True:
            st, fail_msg = self.status()
            if st == "complete":
                break
            if st in ("error", "failed", "cancelacknowledged", "cancelled"):
                if _is_limit_text(fail_msg):
                    raise KaggleLimitError(fail_msg)
                raise ProviderError("error", fail_msg or f"kernel status {st}")
            if now() - t0 > timeout_s:
                raise ProviderError("timeout", f"kernel still {st or 'queued'} after {timeout_s}s")
            sleep(poll_s)
        done, qc = _extract_batch_zip(self.download_output())
        if qc is None:
            raise ProviderError("no_qc", "kernel output has no batch.qc.json")
        return done, qc


# ---------------------------------------------------------------- Actions

class ActionsClient:
    """The engine repo's voice-batch.yml route (GitHub Actions).

    The workflow reads its lines from a file inside the engine repo,
    so the job's lines are written there via the Contents API under
    jobs/<job>.txt, the workflow is dispatched on that path, and the
    file is deleted when the run ends (success or failure). The merged
    artifact's numbering is file-relative; this client remaps it to
    the job's global line indices by order."""

    name = "actions"

    def __init__(self, token, repo=ENGINE_REPO, http=None, job_tag="job"):
        self.token = str(token or "").strip()
        self.repo = repo
        self.job_tag = re.sub(r"[^a-zA-Z0-9_-]", "", str(job_tag))[:40] or "job"
        self.http = http or _default_http()

    def _req(self, method, path, ok=(200,), **kw):
        headers = {"Authorization": f"token {self.token}",
                   "Accept": "application/vnd.github+json",
                   "User-Agent": "julie-runner"}
        r = self.http.request(method, GH_API + path, headers=headers, **kw)
        if r.status_code == 429 or (r.status_code == 403 and _is_limit_text(_body_msg(r))):
            raise ProviderError("limit", f"HTTP {r.status_code}")
        if r.status_code not in ok:
            raise ProviderError("error", f"HTTP {r.status_code} on {method} {path.split('?')[0]}")
        return r

    def _put_lines_file(self, texts):
        path = f"jobs/{self.job_tag}.txt"
        content = base64.b64encode(("\n".join(texts) + "\n").encode("utf-8")).decode()
        r = self._req("PUT", f"/repos/{self.repo}/contents/{path}", ok=(200, 201),
                      json={"message": f"voice batch lines ({self.job_tag})",
                            "content": content})
        return path, (r.json().get("content") or {}).get("sha", "")

    def _delete_lines_file(self, path, sha):
        try:
            self._req("DELETE", f"/repos/{self.repo}/contents/{path}", ok=(200,),
                      json={"message": f"voice batch lines done ({self.job_tag})",
                            "sha": sha})
        except Exception:
            pass  # cleanup is best-effort; a stale jobs/ file is litter, not a failure

    def _latest_run_id(self):
        r = self._req("GET", f"/repos/{self.repo}/actions/workflows/voice-batch.yml/runs",
                      ok=(200,), params={"event": "workflow_dispatch", "per_page": "1"})
        runs = (r.json() or {}).get("workflow_runs") or []
        return runs[0]["id"] if runs else 0

    def _wait_run(self, after_id, timeout_s, poll_s, sleep, now):
        t0 = now()
        while True:
            r = self._req("GET", f"/repos/{self.repo}/actions/workflows/voice-batch.yml/runs",
                          ok=(200,), params={"event": "workflow_dispatch", "per_page": "10"})
            runs = (r.json() or {}).get("workflow_runs") or []
            run = next((x for x in runs if x.get("id", 0) > after_id), None)
            if run and run.get("status") == "completed":
                if run.get("conclusion") in ("success", "failure"):
                    # "failure" still uploads chunk artifacts (if: always)
                    # with every passing line — judge by the artifact + qc,
                    # exactly like the Kaggle path.
                    return run["id"]
                raise ProviderError("error", f"run conclusion {run.get('conclusion')}")
            if now() - t0 > timeout_s:
                raise ProviderError("timeout", f"no completed run after {timeout_s}s")
            sleep(poll_s)

    def _download_artifact(self, run_id):
        r = self._req("GET", f"/repos/{self.repo}/actions/runs/{run_id}/artifacts",
                      ok=(200,), params={"per_page": "100"})
        arts = (r.json() or {}).get("artifacts") or []
        art = next((a for a in arts if a.get("name") == "julie-voice-batch-all"), None)
        if not art:
            raise ProviderError("error", "merged artifact julie-voice-batch-all missing")
        dl = self._req("GET", f"/repos/{self.repo}/actions/artifacts/{art['id']}/zip",
                       ok=(200,))
        return dl.content

    def run_batch(self, items, lang, timeout_s=3600, poll_s=20,
                  sleep=time.sleep, now=time.monotonic, chunks=10):
        """items: [(global_index, text), ...] — a contiguous range.
        Returns (done {global_idx: bytes}, qc). Raises ProviderError."""
        if not items:
            return {}, None
        texts = [t for _, t in items]
        path, sha = self._put_lines_file(texts)
        try:
            after = self._latest_run_id()
            self._req("POST", f"/repos/{self.repo}/actions/workflows/voice-batch.yml/dispatches",
                      ok=(204,), json={"ref": "main", "inputs": {
                          "lines_path": path, "lang": lang,
                          "chunks": str(max(1, min(10, int(chunks)))),
                          "rerolls": "2"}})
            run_id = self._wait_run(after, timeout_s, poll_s, sleep, now)
            blob = self._download_artifact(run_id)
        finally:
            self._delete_lines_file(path, sha)
        sub_done, qc = _extract_batch_zip(blob)
        if qc is None:
            raise ProviderError("no_qc", "artifact has no batch.qc.json")
        # File-relative numbering -> global indices, by order.
        done = {}
        for sub_idx, blob_bytes in sub_done.items():
            pos = sub_idx - 1
            if 0 <= pos < len(items):
                done[items[pos][0]] = blob_bytes
        return done, qc


def _body_msg(r):
    try:
        return str(r.json().get("message") or "")
    except Exception:
        return ""


def _default_http():
    import httpx
    return httpx.Client(follow_redirects=True, timeout=120)


# ---------------------------------------------------------------- orchestration

_SWITCH_LINE = {
    ("kaggle", "limit"): "Kaggle GPU limit ayyindhi — migitha lines GitHub runners meedha continue chesthunna.",
    ("kaggle", "timeout"): "Kaggle slow ga undhi (time ayipoyindhi) — migitha lines GitHub runners meedha continue chesthunna.",
    ("kaggle", "error"): "Kaggle pani cheyyaledhu — migitha lines GitHub runners meedha continue chesthunna.",
    ("kaggle", "no_qc"): "Kaggle result sarigga raledhu — migitha lines GitHub runners meedha continue chesthunna.",
    ("actions", "limit"): "GitHub runners limit ayyindhi — migitha lines Kaggle GPU meedha continue chesthunna.",
    ("actions", "timeout"): "GitHub runners slow ga unnayi — migitha lines Kaggle GPU meedha continue chesthunna.",
    ("actions", "error"): "GitHub runners pani cheyyaledhu — migitha lines Kaggle GPU meedha continue chesthunna.",
    ("actions", "no_qc"): "GitHub runners result sarigga raledhu — migitha lines Kaggle GPU meedha continue chesthunna.",
}


def split_ranges(n, kaggle_share=0.6):
    """Contiguous (kaggle_range, actions_range) over 1..n. Kaggle (the
    GPU) takes the head share; Actions takes the tail."""
    if n <= 0:
        return range(0), range(0)
    k = int(n * kaggle_share)
    if 0 < n <= 2:
        k = n  # tiny batches: one provider, no split overhead
    k = max(0, min(n, k))
    return range(1, k + 1), range(k + 1, n + 1)


def run_voice_batch(lines, lang, kaggle=None, actions=None,
                    on_status=None, on_switch=None,
                    kaggle_share=0.6, kaggle_timeout=1800,
                    actions_timeout=3600, poll_s=20,
                    sleep=time.sleep, now=time.monotonic):
    """Voice every line on the available providers.

    lines: list[str] (global index = position + 1).
    kaggle/actions: client objects or None. At least one is required.
    on_status(text): live progress lines for the chat.
    on_switch(text): called AT MOST once per failed provider, with the
        single user-facing line explaining the switch.

    Returns a dict:
      done        {global_idx: mp3_bytes}
      gate_failed {global_idx: reason}   (engine gates, after re-rolls)
      switches    [{from, to, reason}]
      qc          {provider: raw batch.qc.json}
      errors      {provider: "reason: detail"} for providers that
                  produced nothing usable
    """
    lines = [str(x) for x in lines]
    n = len(lines)
    out = {"done": {}, "gate_failed": {}, "switches": [], "qc": {}, "errors": {}}
    if n == 0:
        return out
    providers = {}
    if kaggle is not None:
        providers["kaggle"] = kaggle
    if actions is not None:
        providers["actions"] = actions
    if not providers:
        raise ValueError("no compute provider available")

    items = {i + 1: t for i, t in enumerate(lines)}
    if len(providers) == 2:
        kr, ar = split_ranges(n, kaggle_share)
        assign = {"kaggle": [i for i in kr], "actions": [i for i in ar]}
    else:
        only = next(iter(providers))
        assign = {only: list(range(1, n + 1))}

    def run_one(name, idxs):
        if not idxs:
            return ("ok", {}, None)
        client = providers[name]
        sub = [(i, items[i]) for i in idxs]
        kw = {"timeout_s": kaggle_timeout if name == "kaggle" else actions_timeout,
              "poll_s": poll_s, "sleep": sleep, "now": now}
        try:
            done, qc = client.run_batch(sub, lang, **kw)
            return ("ok", done, qc)
        except ProviderError as e:
            return ("fail", {}, e)
        except Exception as e:  # transport trouble etc. — still failover-eligible
            return ("fail", {}, ProviderError("error", str(e)[:200]))

    if on_status:
        if "kaggle" in assign and assign["kaggle"]:
            on_status("Kaggle GPU lo voice avthundhi…")
        if "actions" in assign and assign["actions"]:
            on_status("GitHub runners lo voice avthundhi…")

    results = {}
    todo = [(name, idxs) for name, idxs in assign.items() if idxs]
    if len(todo) == 2:
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {ex.submit(run_one, name, idxs): name for name, idxs in todo}
            for fut, name in [(f, futs[f]) for f in futs]:
                results[name] = fut.result()
    elif todo:
        results[todo[0][0]] = run_one(*todo[0])

    failed_providers = {}
    for name, (state, done, payload) in results.items():
        if state == "ok":
            out["done"].update(done)
            out["qc"][name] = payload
            # Lines this provider owned but produced no mp3 for, under
            # an OK run with qc present = gate failures (named in qc).
            for i in assign.get(name, []):
                if i not in done:
                    out["gate_failed"][i] = "gates"
        else:
            failed_providers[name] = payload

    # Failover: a failed provider's lines continue on the survivor.
    for name, err in failed_providers.items():
        idxs = [i for i in assign.get(name, []) if i not in out["done"]]
        out["errors"][name] = f"{err.reason}: {err.detail}".strip()
        survivor = next((p for p in providers if p != name), None)
        if survivor is None or not idxs:
            for i in idxs:
                out["gate_failed"][i] = f"provider failed ({err.reason})"
            continue
        out["switches"].append({"from": name, "to": survivor, "reason": err.reason})
        if on_switch:
            on_switch(_SWITCH_LINE.get((name, err.reason),
                                       _SWITCH_LINE[(name, "error")]))
        if on_status:
            on_status("GitHub runners lo voice avthundhi…" if survivor == "actions"
                      else "Kaggle GPU lo voice avthundhi…")
        state, done, payload = run_one(survivor, idxs)
        if state == "ok":
            out["done"].update(done)
            out["qc"][survivor] = payload
            for i in idxs:
                if i not in done:
                    out["gate_failed"].setdefault(i, "gates")
        else:
            out["errors"][survivor] = f"{payload.reason}: {payload.detail}".strip()
            for i in idxs:
                if i not in out["done"]:
                    out["gate_failed"][i] = f"provider failed ({payload.reason})"
    return out
