"""Stock B-roll fetching for Divya's create engine (v69).

Hark's videos mix real stock footage (B-roll) with code-drawn graphics;
Divya's create path (doc.py) used ONLY code-drawn backgrounds. This module
fetches one short stock clip for a scene so doc.py can use it as the
scene's full-frame background.

Providers (first hit wins):
  1. Pexels Video API  — key from env PEXELS_KEY
  2. Pixabay Video API — key from env PIXABAY_KEY
  3. Wikimedia Commons — KEYLESS, v88; only when JULIE_COMMONS_FOOTAGE=1
     (title-gated candidates, WebM transcoded to MP4 on download)
Both are free-tier APIs with free licences (Pexels Licence / Pixabay
Content Licence — no attribution required, commercial use allowed). The
source page URL of every clip is returned so the caller can record it in
the video's plan/result (licence trail).

Contract: fetch_broll() returns {"path", "provider", "source_url",
"query"} on success and None on ANY failure — no key set, network down,
no match, bad download. It NEVER raises: with no keys configured the
create engine behaves exactly as before (code-drawn backgrounds only).
"""

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request

_SEARCH_TIMEOUT = 20
_DOWNLOAD_TIMEOUT = 120
# Transport = stdlib urllib (v69c, 2026-11-13): httpx broke in the agent's
# sandbox — it chokes parsing this machine's proxy env (InvalidURL) and a
# proxy-free direct connect is TLS-intercepted here — while urllib (which
# honours the same proxy env in its own lenient parser) reaches the APIs
# fine, and on the GitHub runner (no proxy env) both behave the same.
# Pexels also 403s default python user agents (verified live 2026-11-13:
# same key, browser UA -> 200, default UA -> 403), so always send a
# browser UA on API + download requests.
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126 Safari/537.36"}
_MAX_BYTES = 60 * 1024 * 1024  # a B-roll clip never needs to be huge


def _get_json(url, params=None, headers=None):
    """GET url -> parsed JSON dict, or None on ANY failure. Never raises.
    This is the module's single network seam (tests stub this)."""
    try:
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={**_UA, **(headers or {})})
        with urllib.request.build_opener().open(req,
                                                timeout=_SEARCH_TIMEOUT) as r:
            if r.status != 200:
                return None
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _cache_paths(workdir, query, orientation):
    h = hashlib.md5(f"{query}|{orientation}".encode("utf-8")).hexdigest()[:16]
    return (os.path.join(workdir, f"broll_{h}.mp4"),
            os.path.join(workdir, f"broll_{h}.json"))


def _download(url, dest):
    """Stream url -> dest (via a .part file). True on success."""
    tmp = dest + ".part"
    try:
        req = urllib.request.Request(url, headers=dict(_UA))
        with urllib.request.build_opener().open(req,
                                                timeout=_DOWNLOAD_TIMEOUT) as r:
            if r.status != 200:
                return False
            n = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    n += len(chunk)
                    if n > _MAX_BYTES:
                        return False
                    f.write(chunk)
        if n < 50_000:  # too small to be a real clip
            return False
        os.replace(tmp, dest)
        return True
    except Exception:
        return False
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _download_transcoded(url, dest):
    """v88: download a non-MP4 clip (Commons WebM) and transcode it to
    a muted MP4 at dest, so every downstream consumer (frame extract,
    active-window, the renderer) sees the one format it expects.
    Height is capped at 1920 — a beat never needs more. False on any
    failure, exactly like _download."""
    import subprocess
    raw = dest + ".src"
    try:
        if not _download(url, raw):
            return False
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", raw, "-an",
             "-vf", "scale=-2:min(1920\\,ih)", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "20", dest],
            capture_output=True, timeout=300)
        return (r.returncode == 0 and os.path.exists(dest)
                and os.path.getsize(dest) > 50_000)
    except Exception:
        return False
    finally:
        try:
            if os.path.exists(raw):
                os.remove(raw)
        except OSError:
            pass


def _best_file(files, orientation):
    """Prefer a file near 1080 wide (enough for the crop, small to
    download); never a giant 4K original."""
    files = list(files)
    if orientation == "portrait":
        files = [f for f in files if f["height"] >= f["width"]] or files
    files.sort(key=lambda f: (abs(f["width"] - 1080), f["width"]))
    return files[0] if files else None


def _pexels_candidates(query, key, orientation, per_page=30):
    """Mail 1 Part 2: search Pexels with per_page=15, size=medium.
    Returns candidate dicts (id/provider/url/page/width/height/
    duration/uploader/slug) — filtering + scoring happen in the pool."""
    data = _get_json("https://api.pexels.com/videos/search",
                     params={"query": query, "orientation": orientation,
                             "size": "medium", "per_page": per_page},
                     headers={"Authorization": key})
    if not data:
        return []
    out = []
    for v in data.get("videos") or []:
        files = [f for f in (v.get("video_files") or [])
                 if f.get("link") and f.get("width") and f.get("height")
                 and (not f.get("file_type") or f["file_type"] == "video/mp4")]
        if not files:
            continue
        best = _best_file(files, orientation)
        if not best:
            continue
        out.append({"id": f"pexels:{v.get('id')}", "provider": "pexels",
                    "url": best["link"], "page": v.get("url") or "",
                    "width": best["width"], "height": best["height"],
                    "duration": float(v.get("duration") or 0),
                    "uploader": str((v.get("user") or {}).get("name") or ""),
                    "slug": str(v.get("url") or "")})
    return out


def _pexels_search(query, key, orientation):
    """Best Pexels video file for query -> {url, page} or None.
    (Legacy single-hit shape — fetch_broll and its tests use this.)"""
    cands = _pexels_candidates(query, key, orientation, per_page=5)
    if not cands:
        return None
    c = cands[0]
    return {"url": c["url"], "page": c["page"]}


def _pixabay_candidates(query, key, orientation, per_page=30):
    """Mail 1 Part 2: Pixabay search, per_page=20. Candidate dicts,
    same shape as _pexels_candidates (tags come from the hit)."""
    data = _get_json("https://pixabay.com/api/videos/",
                     params={"key": key, "q": query, "per_page": per_page})
    if not data:
        return []
    out = []
    for h in data.get("hits") or []:
        variants = [v for v in (h.get("videos") or {}).values()
                    if isinstance(v, dict) and v.get("url")
                    and v.get("width") and v.get("height")]
        if not variants:
            continue
        best = _best_file(variants, orientation)
        if not best:
            continue
        out.append({"id": f"pixabay:{h.get('id')}", "provider": "pixabay",
                    "url": best["url"], "page": h.get("pageURL") or "",
                    "width": best["width"], "height": best["height"],
                    "duration": float(h.get("duration") or 0),
                    "uploader": str(h.get("user") or ""),
                    "slug": str(h.get("tags") or "")})
    return out


def _pixabay_search(query, key, orientation):
    """Best Pixabay video file for query -> {url, page} or None.
    (Legacy single-hit shape — fetch_broll and its tests use this.)"""
    cands = _pixabay_candidates(query, key, orientation, per_page=5)
    if not cands:
        return None
    c = cands[0]
    return {"url": c["url"], "page": c["page"]}


# ------------------------------------------------------------------
# v88: Wikimedia Commons — the KEYLESS provider. Pexels/Pixabay need
# API keys; Commons needs none (free licences, mostly CC-BY / public
# domain), so it is the fallback that lets a keyless environment —
# a local test rig, a BYOC instance whose owner sealed no stock key —
# still cut REAL footage instead of drawn graphics. It is OFF unless
# JULIE_COMMONS_FOOTAGE=1: production keeps the Pexels-first behaviour
# byte-identical, and Commons' catalogue (documentary / newsreel /
# lecture material) is topically weaker than Pexels', so candidates
# are STRICTLY gated: the file title must share at least 2 content
# words with the query (or 1 when the query has a single content
# word), and a >=640px-wide transcoded derivative must exist. Files
# arrive as WebM and are transcoded to MP4 at download time (the
# candidate carries transcode=True; FootagePool.assign honours it).
# ------------------------------------------------------------------

_COMMONS_STOP = {"the", "and", "for", "with", "video", "file", "webm",
                 "ogv", "clip", "footage"}


def commons_enabled():
    return (os.environ.get("JULIE_COMMONS_FOOTAGE") or "").strip() == "1"


def _commons_candidates(query, orientation, per_page=20):
    """Commons video search -> candidate dicts (same shape as the
    Pexels/Pixabay candidates, plus transcode=True). Title-gated:
    an ungated Commons search returns lectures and newsreels whose
    titles merely brush the query — those must never reach a beat."""
    qt = {t for t in _tokens(query) if t not in _COMMONS_STOP}
    if not qt:
        return []
    data = _get_json("https://commons.wikimedia.org/w/api.php",
                     params={"action": "query", "format": "json",
                             "generator": "search",
                             "gsrsearch": f"filetype:video {query}",
                             "gsrnamespace": 6, "gsrlimit": per_page,
                             "prop": "videoinfo",
                             "viprop": "derivatives|size|url",
                             "viderivatives": 30})
    if not data:
        return []
    pages = ((data.get("query") or {}).get("pages") or {})
    out = []
    for p in pages.values():
        title = str(p.get("title") or "")
        tt = {t for t in _tokens(title) if t not in _COMMONS_STOP}
        need = 1 if len(qt) <= 1 else 2
        if len(qt & tt) < need:
            continue  # relevance gate: title must really be about it
        vi = (p.get("videoinfo") or [{}])[0]
        ders = [d for d in (vi.get("derivatives") or [])
                if d.get("src") and (d.get("width") or 0) >= 640]
        if not ders:
            continue
        if orientation == "portrait":
            ders.sort(key=lambda d: abs((d.get("height") or 1) /
                                        max(1, d.get("width") or 1) - 1.78))
        else:
            ders.sort(key=lambda d: -min(d.get("width") or 0, 1920))
        best = ders[0]
        out.append({"id": f"commons:{p.get('pageid')}",
                    "provider": "commons",
                    "url": best["src"],
                    "page": vi.get("descriptionurl") or "",
                    "width": int(best.get("width") or 0),
                    "height": int(best.get("height") or 0),
                    "duration": float(vi.get("duration") or 0),
                    "uploader": "",
                    "slug": title,
                    "transcode": True})
    return out


def providers_available():
    """True when ANY footage route can serve: a stock key is set, or
    the keyless Commons provider is enabled. Callers use this to
    decide whether building a FootagePool is worthwhile at all."""
    return bool((os.environ.get("PEXELS_KEY") or "").strip()
                or (os.environ.get("PIXABAY_KEY") or "").strip()
                or commons_enabled())


def fetch_broll(query, workdir, orientation="portrait", verify=None):
    """Fetch one stock clip matching query into workdir (cached per
    query+orientation). Returns {"path", "provider", "source_url",
    "query"} or None on any failure. Never raises.

    v87: `verify` — an optional callable (clip_path, query) -> truthy
    verdict. When given, a downloaded clip enters the plan ONLY if
    the verifier accepts it (vision verification is mandatory before
    a clip is used — the long pipeline's FootagePool verifier has
    enforced this since v84; this is the same gate for the direct
    fetch path). A rejected clip is deleted and reported as no-fetch.
    Queries themselves now originate from the Visual Director's
    per-beat decisions (director v87 writes beat["queries"])."""
    try:
        query = " ".join(str(query or "").split()).strip()
        if not query or not workdir:
            return None
        pexels_key = (os.environ.get("PEXELS_KEY") or "").strip()
        pixabay_key = (os.environ.get("PIXABAY_KEY") or "").strip()
        if not pexels_key and not pixabay_key:
            return None  # no keys configured -> engine stays code-drawn
        os.makedirs(workdir, exist_ok=True)
        dest, meta_path = _cache_paths(workdir, query, orientation)
        if os.path.exists(dest) and os.path.getsize(dest) > 50_000 \
                and os.path.exists(meta_path):
            try:
                meta = json.loads(open(meta_path, encoding="utf-8").read())
                return {"path": dest, "provider": meta.get("provider", ""),
                        "source_url": meta.get("source_url", ""),
                        "query": query}
            except Exception:
                pass  # corrupt meta -> refetch below
        hit = None
        provider = ""
        if pexels_key:
            hit = _pexels_search(query, pexels_key, orientation)
            provider = "pexels"
        if hit is None and pixabay_key:
            hit = _pixabay_search(query, pixabay_key, orientation)
            provider = "pixabay"
        if hit is None:
            return None
        if not _download(hit["url"], dest):
            return None
        if verify is not None:
            try:
                _ok = verify(dest, query)
            except Exception:
                _ok = None
            if not _ok:
                try:
                    os.remove(dest)
                except OSError:
                    pass
                print(f"broll: clip for '{query}' rejected by "
                      f"verification — not used")
                return None
        meta = {"provider": provider, "source_url": hit["page"],
                "query": query}
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f)
        except OSError:
            pass
        return {"path": dest, "provider": provider,
                "source_url": hit["page"], "query": query}
    except Exception:
        return None


# ==================================================================
# v79 — the footage METHOD (Blind/Hark mail 1 Part 2 + mail 3 R10).
# The LLM writes a shot list first: per scene, 2 search queries that
# show the MEANING of the line, not the topic word. Both APIs are
# searched (10-15 results per query), filtered (duration >= scene
# length + 1 s, height >= 1080, croppable), scored (query match from
# tags/slug + duration fit), and assigned under the NO-REPEAT rule: a
# used_ids set for the WHOLE video (shared across chapters of a long
# video through the state file), and never two clips from the same
# uploader back-to-back. Every assignment + rejection is recorded for
# footage.json. The trim picks the most ACTIVE window of the clip
# (frame-difference score), not always the first seconds.
# ==================================================================

def _tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(t) > 2}


def score_candidate(cand, query):
    """Query match (from tags/slug) dominates; a clip that comfortably
    covers the needed length beats a barely-long-enough one.
    RENDERER PIVOT (Phase 2b): among matches, HD sources win —
    a 1080p+ clip outranks a 540p one, 720p sits between, and
    Pexels edges out other providers at equal quality (its
    renditions are the most reliable downloads)."""
    qt = _tokens(query)
    ct = _tokens(cand.get("slug", "")) | _tokens(cand.get("page", ""))
    match = len(qt & ct) / max(1, len(qt)) if qt else 0.0
    score = match * 10.0 + min(2.0, (cand.get("duration") or 0) / 30.0)
    h = cand.get("height") or 0
    if h >= 1080:
        score += 1.5
    elif h >= 720:
        score += 0.75
    if cand.get("provider") == "pexels":
        score += 0.25
    return score


def _min_height_for_canvas(canvas):
    """The footage height floor, RELATIVE to the delivery canvas.
    History: the old absolute floor (1080) rejected 92% of
    landscape stock for 16:9 longs; PROOF-FIX 2 relaxed landscape
    to 2/3 of canvas height (720p for 1080) — and the first film
    STILL lost 789 of 849 candidates under it (540p/506p/464p
    stock reality).

    RENDERER PIVOT (Phase 2b): landscape canvases now accept
    >= 540p landscape footage, upscaled to the canvas under
    GRADE_LOCK at render (footage beats only — generated/data
    beats are unaffected). Portrait canvas / no canvas: the
    historical 1080 floor — vertical stock is natively tall,
    portrait shorts unaffected.
    """
    if not canvas:
        return 1080
    w, h = int(canvas[0]), int(canvas[1])
    if w >= h:
        return min(540, h)
    return 1080


def filter_candidates(cands, needed_s, used_ids, last_uploader,
                      canvas=None, relax=False):
    """Mail 1 Part 2 filters + the NO-REPEAT rule. Returns
    (kept, rejected) — every rejection carries its reason for
    footage.json.

    PROOF-FIX 2: with a landscape `canvas`, a PORTRAIT clip is
    rejected outright (cropping it into a landscape frame breaks
    the frame-fill rule) and the height floor is canvas-relative
    (see _min_height_for_canvas).

    Wave 4: `relax=True` is the starvation sweep — floors drop
    to what delivery can still use (a shorter clip loops/slows
    into the beat; 360p landscape upscales under the grade).
    Relaxed keeps are marked `relaxed_floors` so the record
    never hides which floor admitted them. NO-REPEAT and the
    portrait rule never relax."""
    kept, rejected = [], []
    min_h = _min_height_for_canvas(canvas)
    if relax:
        min_h = min(min_h, 360)
    dur_floor = (max(2.5, needed_s * 0.8) if relax
                 else needed_s + 1)
    landscape = bool(canvas) and int(canvas[0]) >= int(canvas[1])
    for c in cands:
        if c["id"] in used_ids:
            rejected.append({**c, "reason": "already used in this video (NO-REPEAT)"})
        elif (c.get("duration") or 0) < dur_floor:
            rejected.append({**c, "reason": f"too short: {c.get('duration')}s < needed {dur_floor}s"})
        elif landscape and (c.get("width") or 0) < (c.get("height") or 0):
            rejected.append({**c, "reason": f"portrait clip {c.get('width')}x{c.get('height')} for a landscape {canvas[0]}x{canvas[1]} frame — would break frame-fill"})
        elif (c.get("height") or 0) < min_h:
            rejected.append({**c, "reason": f"height {c.get('height')} < {min_h}" + (f" (canvas {canvas[0]}x{canvas[1]} floor)" if canvas else "")})
        elif last_uploader and c.get("uploader") and c["uploader"] == last_uploader:
            rejected.append({**c, "reason": "same uploader as the previous clip"})
        else:
            kept.append({**c, "relaxed_floors": True} if relax else c)
    return kept, rejected


def active_window(clip_path, needed_s, fps=2):
    """The most active window of the clip: sample gray frames at
    `fps`, score consecutive frame differences, return
    (start_s, mean_motion). mean_motion under ~1.2 reads as a frozen
    clip to a viewer — the caller marks it static (slow push-in)."""
    import subprocess
    import tempfile
    import numpy as np
    from PIL import Image
    try:
        with tempfile.TemporaryDirectory(prefix="v79act_") as td:
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip_path),
                            "-vf", f"fps={fps},scale=128:-2,format=gray",
                            os.path.join(td, "f%04d.png")],
                           check=True, timeout=120)
            files = sorted(f for f in os.listdir(td) if f.endswith(".png"))
            if len(files) < 2:
                return 0.0, 0.0
            frames = [np.asarray(Image.open(os.path.join(td, f)),
                                 dtype=np.float32) for f in files]
            diffs = [float(np.mean(np.abs(frames[i + 1] - frames[i])))
                     for i in range(len(frames) - 1)]
            win = max(1, int(round(needed_s * fps)))
            if len(diffs) <= win:
                return 0.0, (sum(diffs) / len(diffs) if diffs else 0.0)
            best_i, best_v = 0, -1.0
            for i in range(len(diffs) - win + 1):
                v = sum(diffs[i:i + win])
                if v > best_v:
                    best_i, best_v = i, v
            return best_i / fps, best_v / win
    except Exception:
        return 0.0, 0.0


class FootagePool:
    """One pool per VIDEO (a long video shares one pool across all
    chapters via state_path). assign() returns the scene's clip
    record for footage.json, or None with the rejections logged."""

    def __init__(self, state_path=None):
        self.state_path = state_path
        self.used_ids = []
        self.last_uploader = ""
        self.assignments = []
        self.rejected = []
        # v84 (Stage 3): optional vision verifier (a
        # broll_verify.BrollVerifier). Attached by the long pipeline;
        # None = verification off (previous behaviour, byte-identical).
        self.verifier = None
        if state_path and os.path.exists(state_path):
            try:
                st = json.loads(open(state_path, encoding="utf-8").read())
                self.used_ids = list(st.get("used_ids") or [])
                self.last_uploader = st.get("last_uploader") or ""
                self.assignments = list(st.get("assignments") or [])
                self.rejected = list(st.get("rejected") or [])
            except Exception:
                pass

    def _save(self):
        if not self.state_path:
            return
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"used_ids": self.used_ids,
                           "last_uploader": self.last_uploader,
                           "assignments": self.assignments,
                           "rejected": self.rejected}, f)
        except OSError:
            pass

    def available(self):
        return providers_available()

    def fetch_by_id(self, clip_id, workdir):
        """v79 (FIX 4): re-download the EXACT clip a saved project
        used — Pexels' by-id endpoint, Pixabay's id search — so an
        edit-mode render keeps untouched scenes' footage identical
        instead of picking a fresh clip. Returns a rec dict or None
        (the caller then falls back to a normal assign and the edit
        notes say the scene was re-footaged)."""
        try:
            prov, pid = str(clip_id).split(":", 1)
        except ValueError:
            return None
        meta = None
        try:
            if prov == "pexels" and os.environ.get("PEXELS_KEY"):
                d = _get_json(f"https://api.pexels.com/videos/videos/{pid}",
                              {"Authorization": os.environ["PEXELS_KEY"]})
                if d and d.get("video_files"):
                    f = _best_file(d["video_files"])
                    if f:
                        meta = {"url": f["link"], "page": d.get("url") or "",
                                "uploader": (d.get("user") or {}).get("name", "")}
            elif prov == "pixabay" and os.environ.get("PIXABAY_KEY"):
                q = urllib.parse.urlencode({"key": os.environ["PIXABAY_KEY"], "id": pid})
                d = _get_json("https://pixabay.com/api/videos/?" + q, {})
                hits = (d or {}).get("hits") or []
                if hits:
                    h = hits[0]
                    vids = h.get("videos") or {}
                    f = vids.get("large") or vids.get("medium") or vids.get("small") or {}
                    if f.get("url"):
                        meta = {"url": f["url"], "page": h.get("pageURL") or "",
                                "uploader": h.get("user") or ""}
        except Exception:
            return None
        if not meta:
            return None
        os.makedirs(workdir, exist_ok=True)
        dest = os.path.join(workdir, f"pool_{prov}_{pid}.mp4")
        if not _download(meta["url"], dest):
            return None
        return {"path": dest, "provider": prov,
                "source_url": meta["page"], "uploader": meta["uploader"],
                "clip_id": clip_id}

    def assign(self, scene_no, queries, needed_s, workdir,
               orientation="portrait", line="", canvas=None,
               strict_verify=False):
        """queries: the scene's shot-list queries (meaning, not the
        topic word). Returns {path, clip_id, provider, source_url,
        query, keyword, start, static} or None. `canvas` (w, h) is
        the delivery frame — PROOF-FIX 2: the candidate gate is
        canvas-relative, not an absolute 1080 floor."""
        if not self.available():
            self.rejected.append({"scene": scene_no,
                                  "reason": "no stock-footage provider configured"})
            return None
        os.makedirs(workdir, exist_ok=True)
        used = set(self.used_ids)
        _verified_count = 0  # v84: max 2 candidates verified per scene
        _all_cands = []  # Wave 4: every candidate seen, for the relaxed sweep
        for query in [q for q in (queries or []) if str(q).strip()]:
            cands = []
            pk = (os.environ.get("PEXELS_KEY") or "").strip()
            xk = (os.environ.get("PIXABAY_KEY") or "").strip()
            if pk:
                cands += _pexels_candidates(query, pk, orientation)
            if xk:
                cands += _pixabay_candidates(query, xk, orientation)
            if commons_enabled():
                cands += _commons_candidates(query, orientation)
            _all_cands.extend({**c, "_q": query} for c in cands)
            kept, rejected = filter_candidates(cands, needed_s, used,
                                               self.last_uploader,
                                               canvas=canvas)
            self.rejected.extend({**r, "scene": scene_no, "query": query}
                                 for r in rejected)
            kept.sort(key=lambda c: -score_candidate(c, query))

            def _finish(cand, dest, _verify):
                start, motion = active_window(dest, needed_s)
                keyword = ""
                line_toks = _tokens(line)
                for tok in _tokens(query):
                    if tok in line_toks:
                        keyword = tok
                        break
                rec = {"scene": scene_no, "clip_id": cand["id"],
                       "provider": cand["provider"],
                       "source_url": cand["page"], "query": query,
                       "keyword": keyword, "start": round(start, 2),
                       "path": dest, "static": motion < 1.2,
                       "uploader": cand.get("uploader", ""),
                       **({"verify": _verify} if _verify else {})}
                self.used_ids.append(cand["id"])
                self.last_uploader = cand.get("uploader", "")
                self.assignments.append(rec)
                self._save()
                return rec

            # ROUND 4 (Fix 3): a verifier-UNDECIDED candidate is
            # only a fallback — the next candidate gets its chance
            # first; the undecided one is used only when nothing
            # better verifies, and its record says keyword_only.
            _pending_undecided = None
            for cand in kept:
                dest = os.path.join(
                    workdir, f"pool_{cand['provider']}_{str(cand['id']).split(':')[-1]}.mp4")
                if not (os.path.exists(dest) and os.path.getsize(dest) > 50_000):
                    _dl_ok = (_download_transcoded(cand["url"], dest)
                              if cand.get("transcode")
                              else _download(cand["url"], dest))
                    if not _dl_ok:
                        self.rejected.append({**cand, "scene": scene_no,
                                              "query": query,
                                              "reason": "download failed"})
                        continue
                # v84 (Stage 3 / P1): vision verification of the
                # ACTUAL frames against the narration line + the
                # query (the scene's why). FAIL rejects the clip with
                # the reason recorded (and feeds editing memory via
                # the verifier); UNVERIFIED keeps the clip but is
                # reported as unverified — never as a pass.
                _verify = None
                # Strict (taste) mode verifies EVERY candidate: the
                # old 2-candidate cap let a third, never-checked
                # clip into a taste film (ta57e022 step 5 showed a
                # mask/Scrabble tiles instead of the promised
                # subject). Non-strict mode keeps the budget cap.
                if self.verifier is not None and (
                        strict_verify or _verified_count < 2):
                    _verified_count += 1
                    try:
                        _v, _reason, _cached = self.verifier.verify_candidate(
                            {"id": cand["id"], "path": dest}, line, query,
                            workdir=workdir)
                        _verify = {"verdict": _v, "reason": _reason,
                                   "cached": _cached}
                        # NEXT-ROUND (Fix 2): a clip kept while the
                        # verifier ERRORED (this call, or an outage
                        # across the job) was picked by keyword
                        # score alone — the record must say so, so
                        # the report never reads it as verified.
                        if _v == "unverified" and (
                                str(_reason).startswith(
                                    "vision unavailable")
                                or (hasattr(self.verifier, "outage")
                                    and self.verifier.outage())):
                            _verify["keyword_only"] = True
                        # ROUND 4 (Fix 3): UNDECIDED means the
                        # verifier looked and would not decide —
                        # the clip is NOT vision-verified (flag it
                        # keyword_only) and the next candidate is
                        # tried first; this one is only the
                        # fallback when nothing better verifies.
                        if _v == "undecided":
                            _verify["keyword_only"] = True
                            if _pending_undecided is None and \
                                    cand is not kept[-1]:
                                _pending_undecided = (cand, dest,
                                                      _verify)
                                continue
                        if _v == "fail":
                            self.rejected.append(
                                {**cand, "scene": scene_no, "query": query,
                                 "reason": f"vision verification failed: {_reason}"})
                            used.add(cand["id"])
                            continue
                        # Taste-guarantee strict mode: only a PASS
                        # verdict may enter a taste film. Unverified
                        # and undecided candidates are rejected and
                        # the search re-plans; they are never kept
                        # as a silent fallback.
                        if strict_verify and _v != "pass":
                            self.rejected.append(
                                {**cand, "scene": scene_no, "query": query,
                                 "reason": f"taste strict verify rejected ({_v}): {_reason}"})
                            used.add(cand["id"])
                            continue
                    except Exception as _e:
                        _verify = {"verdict": "unverified",
                                   "reason": str(_e)[:100]}
                        if strict_verify:
                            self.rejected.append(
                                {**cand, "scene": scene_no, "query": query,
                                 "reason": f"taste strict verify error: {str(_e)[:80]}"})
                            used.add(cand["id"])
                            continue
                if strict_verify and self.verifier is None:
                    self.rejected.append(
                        {**cand, "scene": scene_no, "query": query,
                         "reason": "taste strict verify: no verifier attached"})
                    used.add(cand["id"])
                    continue
                if strict_verify and _verify is None:
                    # No verdict was produced for this candidate
                    # (budget/cap path) — a taste film never takes
                    # an unchecked clip; re-plan instead.
                    self.rejected.append(
                        {**cand, "scene": scene_no, "query": query,
                         "reason": "taste strict verify: no verdict for candidate"})
                    used.add(cand["id"])
                    continue
                return _finish(cand, dest, _verify)
            if _pending_undecided is not None and not strict_verify:
                _pc, _pd, _pv = _pending_undecided
                return _finish(_pc, _pd, _pv)
        # Wave 4 starvation sweep: every query failed under the
        # strict floors (ta57e024: 0/10 beats got footage). One
        # relaxed-floor pass over ALL candidates seen — strict
        # vision verification still applies; only the height /
        # duration floors drop to what delivery can use.
        if _all_cands:
            _kept_r, _rej_r = filter_candidates(
                _all_cands, needed_s, used, self.last_uploader,
                canvas=canvas, relax=True)
            _kept_r.sort(key=lambda c: -score_candidate(
                c, c.get("_q") or ""))
            for cand in _kept_r:
                _q_r = cand.get("_q") or ""
                dest = os.path.join(
                    workdir, f"pool_{cand['provider']}_{str(cand['id']).split(':')[-1]}.mp4")
                if not (os.path.exists(dest) and os.path.getsize(dest) > 50_000):
                    _dl_ok = (_download_transcoded(cand["url"], dest)
                              if cand.get("transcode")
                              else _download(cand["url"], dest))
                    if not _dl_ok:
                        continue
                _verify = None
                if self.verifier is not None:
                    try:
                        _v, _reason, _cached = self.verifier.verify_candidate(
                            {"id": cand["id"], "path": dest}, line, _q_r,
                            workdir=workdir)
                        _verify = {"verdict": _v, "reason": _reason,
                                   "cached": _cached}
                        if _v == "fail":
                            used.add(cand["id"])
                            continue
                        if strict_verify and _v != "pass":
                            self.rejected.append(
                                {**cand, "scene": scene_no, "query": _q_r,
                                 "reason": f"taste strict verify rejected ({_v}): {_reason}"})
                            used.add(cand["id"])
                            continue
                    except Exception as _e:
                        if strict_verify:
                            used.add(cand["id"])
                            continue
                        _verify = {"verdict": "unverified",
                                   "reason": str(_e)[:100]}
                elif strict_verify:
                    continue
                start, motion = active_window(dest, needed_s)
                rec = {"scene": scene_no, "clip_id": cand["id"],
                       "provider": cand["provider"],
                       "source_url": cand["page"], "query": _q_r,
                       "keyword": "", "start": round(start, 2),
                       "path": dest, "static": motion < 1.2,
                       "uploader": cand.get("uploader", ""),
                       "relaxed_floors": True,
                       **({"verify": _verify} if _verify else {})}
                self.used_ids.append(cand["id"])
                self.last_uploader = cand.get("uploader", "")
                self.assignments.append(rec)
                self._save()
                return rec
        self.rejected.append({"scene": scene_no,
                              "reason": "no unused clip matched any query"})
        self._save()
        return None

    def footage_json(self):
        """footage.json: scene -> clip id, source, url, query, the
        keyword that matched the line (R10), start time — plus the
        rejected clips with their reasons (mail 1 Part 2 point 6)."""
        return {
            "clips": [{**{k: r[k] for k in ("scene", "clip_id", "provider",
                                            "source_url", "query", "keyword",
                                            "start", "static")},
                       **({"verify": r["verify"]} if r.get("verify") else {})}
                      for r in self.assignments],
            "rejected": [{k: r.get(k) for k in ("scene", "clip_id",
                                                "provider", "query",
                                                "reason") if k in r}
                         for r in self.rejected],
            # NEXT-ROUND (Fix 2): the job-level vision summary —
            # present only when a verifier was attached. An outage
            # is declared HERE, in the artifact, not left as 33
            # identical per-clip "unverified" lines.
            **({"vision": self.verifier.report()}
               if self.verifier is not None
               and hasattr(self.verifier, "report") else {}),
        }
