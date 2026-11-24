"""videogen: free AI video generation on the user's own Kaggle GPU.

WHY THIS EXISTS
---------------
Ajju's 2026-11-24 order: implement the free AI video models from the
"Stop Paying for Higgsfield" video (Wan 2.2, Seedance 2.0 Fast,
Seedream, MiniMax H3, Nano Banana) into Julie. Verification first
(~/workspace/claude-code-setup/FREE_VIDEO_MODELS.md):

  * Wan 2.2 (Alibaba, Apache 2.0 open weights) — TI2V-5B is the only
    variant that fits a 16 GB GPU, so it is the only one that can run
    on Kaggle's free T4/P100. THIS module is that route.
  * Seedance 2.0 Fast + Seedream (ByteDance) — hosted only; the free
    route is Dreamina daily credits behind an account login
    (login-gated, NOT connected per the no-card rule); the API is paid.
  * MiniMax H3 — open weights exist (~134 GB, Blackwell-class
    community routes); they do NOT fit Kaggle's free GPUs.
  * Nano Banana (Gemini image) — Google lists no free API tier for it;
    no Gemini key is held in the router pool. Not wired.

CONTRACT
--------
* A videogen job record carries {mode: "videogen", prompt, to}.
  The runner channel (/job in cfworker/divya.js) hands the owner's
  sealed Kaggle creds to the runner as j["KAGGLE"] — the same
  hand-off voicebatch uses. Credentials are NEVER logged here:
  status/error strings are fixed text + HTTP status codes only.
* run_videogen pushes ONE private Kaggle kernel (kernelType "script",
  like voicecompute.py) whose source embeds the render config, polls
  it, and downloads /kernels/output. A run counts as OK only when the
  output zip carries videogen_out.mp4 AND render_info.json — no info
  record, no trust (same discipline as voicecompute's batch.qc rule).
* There is deliberately NO second provider and NO multi-account
  rotation: if Kaggle limits/errors, the job reports that honestly
  (reason "limit" | "timeout" | "error") instead of silently moving.

The module is transport-injectable (httpx client, sleep, clock) so
videogentest.py can drive every path against fake API servers.
"""

import io
import json
import time
import zipfile

KAGGLE_API = "https://www.kaggle.com/api/v1"
KERNEL_SLUG = "julie-videogen"
MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"

_LIMIT_WORDS = ("quota", "limit", "exceeded", "resource_exhausted",
                "too many", "rate", "maximum batch")


class VideogenError(Exception):
    """A videogen run failed; reason is limit | timeout | error."""

    def __init__(self, reason, detail=""):
        super().__init__(reason)
        self.reason = reason
        self.detail = str(detail)[:200]


def _is_limit_text(text):
    t = str(text or "").lower()
    return any(w in t for w in _LIMIT_WORDS)


# ---------------------------------------------------------------- kernel

_KERNEL_TEMPLATE = '''# Wan 2.2 TI2V-5B render — pushed by Julie (videogen.py) via the
# Kaggle API. Config rides inside the push; output contract:
# /kaggle/working/videogen_out.mp4 + render_info.json.
import json, os, subprocess, sys, time

CFG = json.loads({cfg_json!r})
WORK = "/kaggle/working"


def main():
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "diffusers>=0.36.0", "transformers>=4.57.0",
                    "accelerate>=1.0", "imageio", "imageio-ffmpeg",
                    "sentencepiece"], check=False)
    import torch
    if not torch.cuda.is_available():
        raise SystemExit("No GPU visible on this kernel session.")
    from diffusers import WanPipeline, AutoencoderKLWan
    from diffusers.utils import export_to_video

    info = {{"model": CFG["model"], "width": CFG["width"],
            "height": CFG["height"], "frames": CFG["frames"],
            "steps": CFG["steps"], "fps": CFG["fps"],
            "prompt": CFG["prompt"], "gpu": torch.cuda.get_device_name(0)}}
    t0 = time.time()
    vae = AutoencoderKLWan.from_pretrained(
        CFG["model"], subfolder="vae", torch_dtype=torch.float32)
    pipe = WanPipeline.from_pretrained(
        CFG["model"], vae=vae, torch_dtype=torch.float16,
        low_cpu_mem_usage=True)
    # PROVEN recipe (Kaggle proof kernel v2, 2026-11-24): sequential
    # offload rendered end-to-end on a T4 (peak VRAM 11.93 GB). The
    # earlier model-offload variant died on Kaggle (DeadKernelError).
    pipe.enable_sequential_cpu_offload()
    info["load_s"] = round(time.time() - t0, 1)

    gen = torch.Generator(device="cpu").manual_seed(CFG["seed"])
    t1 = time.time()
    out = pipe(prompt=CFG["prompt"], negative_prompt=CFG["negative"],
               height=CFG["height"], width=CFG["width"],
               num_frames=CFG["frames"], guidance_scale=5.0,
               num_inference_steps=CFG["steps"], generator=gen).frames[0]
    info["render_s"] = round(time.time() - t1, 1)
    export_to_video(out, os.path.join(WORK, "videogen_out.mp4"),
                    fps=CFG["fps"])
    info["total_s"] = round(time.time() - t0, 1)
    info["peak_vram_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
    with open(os.path.join(WORK, "render_info.json"), "w") as fh:
        json.dump(info, fh, indent=2)
    print(json.dumps(info, indent=2))
    print("VIDEOGEN_DONE")


main()
'''

_NEGATIVE = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，"
             "画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，"
             "残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，"
             "毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，"
             "三条腿，背景人很多，倒着走")

DEFAULT_CFG = {"width": 832, "height": 480, "frames": 81, "steps": 20,
               "fps": 24, "seed": 42}


def build_kernel_script(cfg):
    """The per-job Kaggle kernel source: render config embedded as
    JSON (quotes/unicode safe)."""
    full = {"model": MODEL_ID, "negative": _NEGATIVE, **cfg}
    return _KERNEL_TEMPLATE.format(
        cfg_json=json.dumps(full, ensure_ascii=False))


# ---------------------------------------------------------------- client

class KaggleVideogenClient:
    """The user's own Kaggle account, via the official API (Basic auth
    with the username + API key from their kaggle.json). Mirrors
    voicecompute.KaggleClient's error discipline."""

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
            body = ""
            try:
                body = str(r.json().get("message") or "")
            except Exception:
                pass
            if r.status_code == 403 or _is_limit_text(body):
                raise VideogenError("limit", f"HTTP {r.status_code}")
            raise VideogenError("error", f"HTTP {r.status_code} (credentials rejected)")
        if r.status_code == 429:
            raise VideogenError("limit", "HTTP 429")
        if r.status_code >= 400:
            raise VideogenError("error", f"HTTP {r.status_code}")
        return r

    def push_kernel(self, cfg):
        body = {
            "id": self.ref, "slug": self.ref,
            "newTitle": "Julie videogen (Wan 2.2)",
            "text": build_kernel_script(cfg),
            "language": "python", "kernelType": "script",
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
                raise VideogenError("limit", msg)
            raise VideogenError("error", msg)
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

    def run_render(self, cfg, timeout_s=5400, poll_s=30,
                   sleep=time.sleep, now=time.monotonic, on_status=None):
        """Push, poll, download. Returns (mp4_bytes, info_dict).
        Raises VideogenError (limit | timeout | error)."""
        self.push_kernel(cfg)
        t0 = now()
        while True:
            st, fail_msg = self.status()
            if on_status:
                on_status(st)
            if st == "complete":
                break
            if st in ("error", "failed", "cancelacknowledged", "cancelled"):
                if _is_limit_text(fail_msg):
                    raise VideogenError("limit", fail_msg)
                raise VideogenError("error", fail_msg or f"kernel status {st}")
            if now() - t0 > timeout_s:
                raise VideogenError("timeout", f"kernel still {st or 'queued'} after {timeout_s}s")
            sleep(poll_s)
        mp4, info = _extract_output(self.download_output())
        if mp4 is None:
            raise VideogenError("error", "kernel output has no videogen_out.mp4")
        if info is None:
            raise VideogenError("error", "kernel output has no render_info.json")
        return mp4, info


def _extract_output(blob):
    """Output zip bytes -> (mp4_bytes_or_None, info_dict_or_None)."""
    mp4, info = None, None
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for name in zf.namelist():
            base = name.rsplit("/", 1)[-1]
            if base == "videogen_out.mp4":
                mp4 = zf.read(name)
            elif base == "render_info.json" and info is None:
                try:
                    info = json.loads(zf.read(name).decode("utf-8"))
                except Exception:
                    pass
    return mp4, info


def _default_http():
    import httpx
    return httpx.Client(follow_redirects=True, timeout=300)


# ---------------------------------------------------------------- entry

def run_videogen(prompt, kaggle=None, cfg_overrides=None, timeout_s=5400,
                 poll_s=30, sleep=time.sleep, now=time.monotonic,
                 on_status=None):
    """Render one clip for a videogen job.

    Returns {"ok": True, "mp4": bytes, "info": {...}} or
    {"ok": False, "reason": ..., "detail": ...}. Never raises for a
    provider failure — the caller reports the reason honestly."""
    prompt = str(prompt or "").strip()
    if not prompt:
        return {"ok": False, "reason": "error", "detail": "empty prompt"}
    if kaggle is None:
        return {"ok": False, "reason": "error",
                "detail": "no Kaggle compute provider connected"}
    cfg = {**DEFAULT_CFG, **(cfg_overrides or {}), "prompt": prompt}
    try:
        mp4, info = kaggle.run_render(cfg, timeout_s=timeout_s,
                                      poll_s=poll_s, sleep=sleep, now=now,
                                      on_status=on_status)
    except VideogenError as e:
        return {"ok": False, "reason": e.reason, "detail": e.detail}
    except Exception as e:
        return {"ok": False, "reason": "error", "detail": str(e)[:200]}
    return {"ok": True, "mp4": mp4, "info": info}
