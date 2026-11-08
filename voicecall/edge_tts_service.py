"""Free TTS for Pipecat via Microsoft Edge neural voices (edge-tts). MP3 -> PCM with PyAV."""
import io
import re
from collections.abc import AsyncGenerator

import av
import edge_tts
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService


def mp3_to_pcm(mp3: bytes, rate: int) -> bytes:
    out = bytearray()
    with av.open(io.BytesIO(mp3), format="mp3") as c:
        rs = av.AudioResampler(format="s16", layout="mono", rate=rate)
        for fr in c.decode(audio=0):
            for r in rs.resample(fr):
                out += bytes(r.planes[0])[: r.samples * 2]
        for r in rs.resample(None):
            out += bytes(r.planes[0])[: r.samples * 2]
    return bytes(out)


class EdgeTTSService(TTSService):
    Settings = TTSSettings

    def __init__(self, *, voice: str = "te-IN-ShrutiNeural", rate: str = "+0%", pitch: str = "+0Hz", **kwargs):
        super().__init__(
            pause_frame_processing=True,
            push_start_frame=True,
            push_stop_frames=True,
            settings=TTSSettings(model="edge-tts", voice=voice, language=None),
            **kwargs,
        )
        self._voice, self._rate, self._pitch = voice, rate, pitch

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F*_#`~>\[\]]", "", text or "").strip()
        if not text:
            return
        try:
            buf = bytearray()
            comm = edge_tts.Communicate(text, self._voice, rate=self._rate, pitch=self._pitch)
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    buf += ch["data"]
            await self.stop_ttfb_metrics()
            if not buf:
                return
            pcm = mp3_to_pcm(bytes(buf), self.sample_rate)
            step = self.sample_rate * 2 // 5  # 200 ms chunks
            for i in range(0, len(pcm), step):
                yield TTSAudioRawFrame(pcm[i : i + step], self.sample_rate, 1, context_id=context_id)
        except Exception as e:
            logger.error(f"edge-tts failed: {e}")
            yield ErrorFrame(error=f"edge-tts error: {e}")
