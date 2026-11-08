"""Divya voice-call pipeline: SmallWebRTC (WhatsApp) -> Silero VAD -> Groq Whisper -> Groq LLM -> edge-tts."""
import os

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.groq.stt import GroqSTTService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from edge_tts_service import EdgeTTSService

SCRIPT = os.getenv("VOICE_SCRIPT", "telugu")  # telugu = Telugu script (correct TTS pronunciation); roman = romanized
SYSTEM = f"""Nuvvu "Divya", owner ki close friend laanti personal AI agent. Ippudu WhatsApp VOICE CALL lo matladutunnav.
Rules:
- Prathi reply 1-2 chinna sentences matrame. Phone call laaga natural ga, friendly ga.
- Telugu + English mix (Tenglish). {"Telugu maatalu TELUGU LIPI lo rayi (ex: 'నేను బాగున్నా, nuvvu?' kaadu 'నేను బాగున్నా, నువ్వు ఎలా ఉన్నావ్?'); English words English lo ne unchu." if SCRIPT == "telugu" else "Romanized Telugu + English lo rayi."}
- Emojis, markdown, bullets, special characters vaddu (idi voice ga maaruthundi).
- Videos create/edit WhatsApp chat lo jarugutayi; call lo adigithe 'chat lo message pettu, akkada start chestha' ani cheppu.
- Nijayithi: leni pani aipoyindi anaku. Keys/secrets eppudu cheppaku."""


async def run_bot(webrtc_connection, caller: str = ""):
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=2),
    )
    key = os.environ["GROQ_KEY"].split(",")[0].strip()
    stt = GroqSTTService(
        api_key=key,
        settings=GroqSTTService.Settings(model="whisper-large-v3", language=Language(os.getenv("STT_LANG", "te"))),
    )
    llm = GroqLLMService(
        api_key=key,
        settings=GroqLLMService.Settings(
            model=os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
            temperature=0.7,
            max_completion_tokens=300,
            extra={"reasoning_effort": "low"},
        ),
    )
    tts = EdgeTTSService(voice=os.getenv("TTS_VOICE", "te-IN-ShrutiNeural"), rate=os.getenv("TTS_RATE", "+5%"))

    context = LLMContext([{"role": "system", "content": SYSTEM}])
    user_agg, asst_agg = LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()))

    pipeline = Pipeline([transport.input(), stt, user_agg, llm, tts, transport.output(), asst_agg])
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True))
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def _on_conn(t, c):
        logger.info(f"call connected {caller[-4:]}")
        context.add_message({"role": "user", "content": "(Call ippude connect ayyindi. Owner ni chinna ga greet chesi, em kavali ani adugu.)"})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def _on_disc(t, c):
        logger.info("call disconnected")
        await runner.cancel()

    await runner.run()
