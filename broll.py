"""Stock B-roll fetching for Divya's create engine (v69).

Hark's videos mix real stock footage (B-roll) with code-drawn graphics;
Divya's create path (doc.py) used ONLY code-drawn backgrounds. This module
fetches one short stock clip for a scene so doc.py can use it as the
scene's full-frame background.

Providers (first hit wins):
  1. Pexels Video API  — key from env PEXELS_KEY
  2. Pixabay Video API — key from env PIXABAY_KEY
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

import httpx

_SEARCH_TIMEOUT = 20
_DOWNLOAD_TIMEOUT = 120
# Pexels 403s the default httpx/python user agents (verified live
# 2026-11-13: same key, browser UA -> 200, default UA -> 403). Always
# send a browser UA on API + download requests.
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126 Safari/537.36"}
_MAX_BYTES = 60 * 1024 * 1024  # a B-roll clip never needs to be huge


def _cache_paths(workdir, query, orientation):
    h = hashlib.md5(f"{query}|{orientation}".encode("utf-8")).hexdigest()[:16]
    return (os.path.join(workdir, f"broll_{h}.mp4"),
            os.path.join(workdir, f"broll_{h}.json"))


def _download(url, dest):
    """Stream url -> dest (via a .part file). True on success."""
    tmp = dest + ".part"
    try:
        with httpx.stream("GET", url, follow_redirects=True, headers=_UA,
                          timeout=_DOWNLOAD_TIMEOUT) as r:
            if r.status_code != 200:
                return False
            n = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
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


def _pexels_search(query, key, orientation):
    """Best Pexels video file for query -> {url, page} or None."""
    try:
        r = httpx.get("https://api.pexels.com/videos/search",
                      params={"query": query, "orientation": orientation,
                              "per_page": 5},
                      headers={"Authorization": key, **_UA},
                      timeout=_SEARCH_TIMEOUT)
        if r.status_code != 200:
            return None
        videos = r.json().get("videos") or []
    except Exception:
        return None
    for v in videos:
        files = [f for f in (v.get("video_files") or [])
                 if f.get("link") and f.get("width") and f.get("height")
                 and (not f.get("file_type") or f["file_type"] == "video/mp4")]
        if not files:
            continue
        if orientation == "portrait":
            files = [f for f in files if f["height"] >= f["width"]] or files
        # Prefer a file near 1080 wide (enough for the 1080x1920 crop,
        # small to download); never a giant 4K original.
        files.sort(key=lambda f: (abs(f["width"] - 1080), f["width"]))
        best = files[0]
        return {"url": best["link"], "page": v.get("url") or ""}
    return None


def _pixabay_search(query, key, orientation):
    """Best Pixabay video file for query -> {url, page} or None."""
    try:
        r = httpx.get("https://pixabay.com/api/videos/",
                      params={"key": key, "q": query, "per_page": 5},
                      headers=_UA,
                      timeout=_SEARCH_TIMEOUT)
        if r.status_code != 200:
            return None
        hits = r.json().get("hits") or []
    except Exception:
        return None
    for h in hits:
        variants = [v for v in (h.get("videos") or {}).values()
                    if isinstance(v, dict) and v.get("url")
                    and v.get("width") and v.get("height")]
        if not variants:
            continue
        if orientation == "portrait":
            variants = [v for v in variants if v["height"] >= v["width"]] \
                or variants
        variants.sort(key=lambda v: (abs(v["width"] - 1080), v["width"]))
        best = variants[0]
        return {"url": best["url"], "page": h.get("pageURL") or ""}
    return None


def fetch_broll(query, workdir, orientation="portrait"):
    """Fetch one stock clip matching query into workdir (cached per
    query+orientation). Returns {"path", "provider", "source_url",
    "query"} or None on any failure. Never raises."""
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
