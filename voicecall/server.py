"""Divya WhatsApp voice-call media server (Hugging Face Docker Space).
The Cloudflare Worker forwards Meta "calls" webhooks to POST /calls with header x-divya-key.
Env (Space secrets): WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, GROQ_KEY, FORWARD_SECRET,
optional CF_TURN_KEY_ID + CF_TURN_KEY_TOKEN (Cloudflare Realtime TURN), ALLOWED_CALLERS (comma list).
"""
import asyncio
import collections
import json
import os
import sys
import time

import aiohttp
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from loguru import logger
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.whatsapp.api import WhatsAppWebhookRequest
from pipecat.transports.whatsapp.client import WhatsAppClient

from bot import run_bot

LOG = collections.deque(maxlen=400)
logger.remove()
logger.add(sys.stderr, level="DEBUG")
logger.add(lambda m: LOG.append(m.strip()), level="DEBUG", format="{time:HH:mm:ss} {level} {message}")

TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "1404587642739329")
SECRET = os.getenv("FORWARD_SECRET", "")
ALLOWED = [x.strip() for x in os.getenv("ALLOWED_CALLERS", "919951950173,917993610173").split(",") if x.strip()]
STUN = [IceServer(urls="stun:stun.cloudflare.com:3478"), IceServer(urls="stun:stun.l.google.com:19302")]

app = FastAPI()
state = {"client": None, "session": None, "calls": [], "started": time.time()}
tasks = set()


async def ice_servers():
    kid, ktok = os.getenv("CF_TURN_KEY_ID"), os.getenv("CF_TURN_KEY_TOKEN")
    if not (kid and ktok):
        return STUN
    try:
        async with state["session"].post(
            f"https://rtc.live.cloudflare.com/v1/turn/keys/{kid}/credentials/generate-ice-servers",
            headers={"Authorization": f"Bearer {ktok}"}, json={"ttl": 3600},
        ) as r:
            d = await r.json()
        out = list(STUN)
        for s in d.get("iceServers", []):
            urls = [u for u in (s["urls"] if isinstance(s["urls"], list) else [s["urls"]]) if u.startswith("turn")]
            # aiortc cannot use :53 ports reliably; keep 3478/443 variants
            urls = [u for u in urls if ":53?" not in u and not u.endswith(":53")]
            if urls:
                out.append(IceServer(urls=urls, username=s.get("username"), credential=s.get("credential")))
        return out
    except Exception as e:
        logger.error(f"TURN creds failed: {e}")
        return STUN


WORKER = os.getenv("WORKER_URL", "https://divya.n8n00101.workers.dev")


async def load_creds():
    """WA token + Groq key come from the Worker's secrets (POST /callcreds), unless set as Space secrets."""
    global TOKEN, ALLOWED
    if TOKEN and os.getenv("GROQ_KEY"):
        return True
    try:
        async with state["session"].post(f"{WORKER}/callcreds", headers={"x-divya-key": SECRET}) as r:
            if r.status != 200:
                logger.error(f"callcreds {r.status}")
                return False
            d = await r.json()
        TOKEN = TOKEN or d.get("WA_TOKEN", "")
        if d.get("GROQ_KEY") and not os.getenv("GROQ_KEY"):
            os.environ["GROQ_KEY"] = d["GROQ_KEY"]
        if not os.getenv("ALLOWED_CALLERS"):
            ALLOWED = [x.strip() for x in f"{d.get('OWNERS','')},{d.get('FRIENDS','')}".split(",") if x.strip()] or ALLOWED
        if state["client"]:
            state["client"].update_whatsapp_token(TOKEN)
        logger.info("creds loaded from worker")
        return bool(TOKEN)
    except Exception as e:
        logger.error(f"callcreds failed: {e}")
        return False


@app.on_event("startup")
async def _start():
    state["session"] = aiohttp.ClientSession()
    state["client"] = WhatsAppClient(whatsapp_token=TOKEN or "pending", phone_number_id=PHONE_ID, session=state["session"], ice_servers=STUN)
    await load_creds()
    logger.info("Divya call server up")


def spawn(coro):
    t = asyncio.create_task(coro)
    tasks.add(t)
    t.add_done_callback(tasks.discard)


def auth(req: Request):
    if not SECRET or req.headers.get("x-divya-key") != SECRET:
        raise HTTPException(403, "no")


@app.get("/")
@app.get("/health")
async def health():
    return {"ok": True, "name": "divya-call", "up_s": int(time.time() - state["started"]),
            "turn": bool(os.getenv("CF_TURN_KEY_ID")), "wa_token": bool(TOKEN), "groq": bool(os.getenv("GROQ_KEY")), "allowed": len(ALLOWED),
            "active": len(tasks), "recent_calls": state["calls"][-5:]}


@app.get("/logs")
async def logs(req: Request):
    auth(req)
    return {"log": list(LOG)[-200:]}


async def reject(call_id):
    async with state["session"].post(f"https://graph.facebook.com/v23.0/{PHONE_ID}/calls",
                                     headers={"Authorization": f"Bearer {TOKEN}"},
                                     json={"messaging_product": "whatsapp", "call_id": call_id, "action": "reject"}) as r:
        logger.info(f"reject {call_id}: {r.status} {await r.text()}")


async def process(body: dict):
    try:
        if not TOKEN or not os.getenv("GROQ_KEY"):
            await load_creds()
        events = [(c.get("id"), c.get("event"), c.get("from")) for e in body.get("entry", []) for ch in e.get("changes", [])
                  for c in (ch.get("value") or {}).get("calls", [])]
        for cid, ev, frm in events:
            state["calls"].append({"t": time.strftime("%H:%M:%S"), "event": ev, "from": (frm or "")[-4:]})
            if ev == "connect" and frm and ALLOWED and frm not in ALLOWED:
                logger.warning(f"caller {frm[-4:]} not allowed -> reject")
                await reject(cid)
                return
        if not any(ev in ("connect", "terminate") for _, ev, _ in events):
            logger.info(f"calls webhook without connect/terminate: {json.dumps(body)[:600]}")
            return
        client = state["client"]
        if any(ev == "connect" for _, ev, _ in events):
            client.update_ice_servers(await ice_servers())
        req = WhatsAppWebhookRequest.model_validate(body)

        async def on_conn(connection: SmallWebRTCConnection, call):
            logger.info(f"WebRTC answered, starting bot for {call.from_[-4:]}")
            spawn(run_bot(connection, call.from_))

        await client.handle_webhook_request(req, on_conn)
    except Exception as e:
        logger.exception(f"process failed: {e}")


@app.post("/calls")
async def calls(req: Request):
    auth(req)
    body = await req.json()
    logger.info(f"calls webhook: {json.dumps(body)[:1500]}")
    spawn(process(body))
    return {"ok": True}


@app.post("/selftest")
async def selftest(req: Request):
    """Loopback test inside the container: a local aiortc peer calls the bot; counts audio it gets back."""
    auth(req)
    await load_creds()
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.mediastreams import AudioStreamTrack

    secs = float((await req.json()).get("secs", 20)) if (await req.body()) else 20.0
    pc = RTCPeerConnection()
    pc.addTrack(AudioStreamTrack())  # silence
    got = {"frames": 0, "loud": 0}

    @pc.on("track")
    def on_track(track):
        async def reader():
            import numpy as np
            while True:
                try:
                    f = await track.recv()
                except Exception:
                    break
                got["frames"] += 1
                a = f.to_ndarray()
                if np.abs(a).max() > 500:
                    got["loud"] += 1
        spawn(reader())

    await pc.setLocalDescription(await pc.createOffer())
    conn = SmallWebRTCConnection(await ice_servers())
    await conn.initialize(sdp=pc.localDescription.sdp, type="offer")
    ans = conn.get_answer()
    cand = sorted({l.split()[7] for l in ans["sdp"].splitlines() if l.startswith("a=candidate")})
    await pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type="answer"))
    spawn(run_bot(conn, "selftest"))
    await asyncio.sleep(secs)
    await pc.close()
    return {"answer_candidate_types": cand, "audio_frames_received": got["frames"], "frames_with_voice": got["loud"],
            "log_tail": [l for l in list(LOG)[-60:] if "ERROR" in l or "TTS" in l or "LLM" in l or "edge" in l][-20:]}


@app.get("/icetest")
async def icetest(req: Request):
    """Gather ICE candidates from this host to see which kinds (host/srflx/relay) are reachable."""
    auth(req)
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection
    srv = await ice_servers()
    cfg = RTCConfiguration([RTCIceServer(urls=s.urls, username=s.username, credential=s.credential) for s in srv])
    pc = RTCPeerConnection(cfg)
    pc.createDataChannel("x")
    await pc.setLocalDescription(await pc.createOffer())
    lines = [l for l in pc.localDescription.sdp.splitlines() if l.startswith("a=candidate")]
    await pc.close()
    return {"servers": [s.urls for s in srv], "candidates": [" ".join(l.split()[2:8]) for l in lines]}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")), log_config=None)
