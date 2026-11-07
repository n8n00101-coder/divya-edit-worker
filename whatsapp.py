import os
import httpx
from config import WA_TOKEN, WA_PHONE_ID, DATA

API = "https://graph.facebook.com/v21.0"
H = lambda: {"Authorization": f"Bearer {WA_TOKEN}"}


async def send_text(to: str, text: str):
    async with httpx.AsyncClient(timeout=60) as c:
        for i in range(0, len(text), 4000):
            await c.post(f"{API}/{WA_PHONE_ID}/messages", headers=H(), json={
                "messaging_product": "whatsapp", "to": to, "type": "text",
                "text": {"body": text[i:i + 4000]}})


async def download_media(media_id: str, ext: str) -> str:
    async with httpx.AsyncClient(timeout=300) as c:
        meta = (await c.get(f"{API}/{media_id}", headers=H())).json()
        r = await c.get(meta["url"], headers=H())
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
        mid = up.json().get("id")
        if not mid:
            raise RuntimeError(f"WhatsApp upload failed: {up.text[:300]}")
        body = {"id": mid}
        if caption and kind != "audio":
            body["caption"] = caption
        await c.post(f"{API}/{WA_PHONE_ID}/messages", headers=H(), json={
            "messaging_product": "whatsapp", "to": to, "type": kind, kind: body})
