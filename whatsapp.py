import asyncio
import os
import httpx
from config import WA_TOKEN, WA_PHONE_ID, DATA

API = "https://graph.facebook.com/v21.0"
H = lambda: {"Authorization": f"Bearer {WA_TOKEN}"}

# v74: WhatsApp sends used to be fire-and-forget — no status check, no
# retry — so a transient Meta 429/5xx or a network blip silently ate
# progress notes, failure notices and even finished videos. Transient
# failures now retry with backoff; the outcome is reported to the
# caller (send_text returns bool; send_media raises, as its callers
# already treat exceptions as job failures).
_TRANSIENT = {429, 500, 502, 503, 504}


async def _post_with_retry(c, url, **kw):
    last = None
    for attempt in range(3):
        try:
            r = await c.post(url, **kw)
            if r.status_code not in _TRANSIENT:
                return r
            last = r
        except Exception as e:
            last = e
        if attempt < 2:
            await asyncio.sleep(2 * (attempt + 1))
    return last


async def send_text(to: str, text: str) -> bool:
    ok = True
    async with httpx.AsyncClient(timeout=60) as c:
        for i in range(0, len(text), 4000):
            r = await _post_with_retry(c, f"{API}/{WA_PHONE_ID}/messages", headers=H(), json={
                "messaging_product": "whatsapp", "to": to, "type": "text",
                "text": {"body": text[i:i + 4000]}})
            if isinstance(r, Exception) or r.status_code >= 400:
                ok = False
                print("wa send_text failed:", getattr(r, "status_code", type(r).__name__),
                      (getattr(r, "text", "") or "")[:200])
    return ok


async def download_media(media_id: str, ext: str) -> str:
    async with httpx.AsyncClient(timeout=300) as c:
        meta_r = await c.get(f"{API}/{media_id}", headers=H())
        if meta_r.status_code != 200:
            raise RuntimeError(f"WhatsApp media info failed: HTTP {meta_r.status_code}")
        url = meta_r.json().get("url")
        if not url:
            raise RuntimeError("WhatsApp media info lo URL ledu")
        r = await c.get(url, headers=H())
        if r.status_code != 200:
            raise RuntimeError(f"WhatsApp media download failed: HTTP {r.status_code}")
        path = os.path.join(DATA, f"in_{media_id}.{ext}")
        with open(path, "wb") as f:
            f.write(r.content)
        return path


async def send_media(to: str, path: str, kind: str = "video", caption: str = ""):
    """Uploads a file and sends it. WhatsApp allows videos up to 16 MB."""
    mime = {"video": "video/mp4", "image": "image/jpeg", "audio": "audio/mpeg"}[kind]
    async with httpx.AsyncClient(timeout=600) as c:
        with open(path, "rb") as f:
            up = await c.post(f"{API}/{WA_PHONE_ID}/media", headers=H(),
                              data={"messaging_product": "whatsapp", "type": mime},
                              files={"file": (os.path.basename(path), f, mime)})
        mid = up.json().get("id") if up.status_code == 200 else None
        if not mid:
            raise RuntimeError(f"WhatsApp upload failed: HTTP {up.status_code} {up.text[:300]}")
        body = {"id": mid}
        if caption and kind != "audio":
            body["caption"] = caption
        # v74: the send itself was unchecked — media could upload and
        # never be delivered while the job reported success.
        r = await _post_with_retry(c, f"{API}/{WA_PHONE_ID}/messages", headers=H(), json={
            "messaging_product": "whatsapp", "to": to, "type": kind, kind: body})
        if isinstance(r, Exception) or r.status_code >= 400:
            raise RuntimeError(f"WhatsApp send failed: {getattr(r, 'status_code', type(r).__name__)} {(getattr(r, 'text', '') or '')[:200]}")
