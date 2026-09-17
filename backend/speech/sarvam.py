"""One bounded auto-language transcription; never discard or log citizen audio/text."""
import asyncio
import logging
import httpx
import provider_health
from provider_config import SARVAM_MODEL, STT_TIMEOUT, api_key
from speech.provider import SpeechUnavailable, Transcription

SARVAM_URL = "https://api.sarvam.ai/speech-to-text"
log = logging.getLogger(__name__)

class SarvamSpeechProvider:
    def __init__(self, transport=None):
        self.transport = transport

    async def transcribe(self, audio, content_type):
        key = api_key("SARVAM_API_KEY")
        if not key or not audio or (self.transport is None and provider_health.paused("speech")):
            raise SpeechUnavailable("Keep the recording for later processing, or type your message.")
        try:
            async with asyncio.timeout(min(STT_TIMEOUT, 45)), httpx.AsyncClient(
                timeout=httpx.Timeout(min(STT_TIMEOUT, 45), connect=8), transport=self.transport,
                follow_redirects=False) as client:
                response = await client.post(SARVAM_URL, headers={"api-subscription-key": key},
                    data={"model": SARVAM_MODEL, "language_code": "unknown", "mode": "codemix"},
                    files={"file": ("recording.webm", audio, "audio/webm")})
                response.raise_for_status()
                value = response.json()
                if not isinstance(value, dict) or not isinstance(value.get("transcript"), str):
                    raise ValueError("shape")
                result = Transcription(model=SARVAM_MODEL, transcript=value["transcript"].strip(),
                    language_code=value.get("language_code"), confidence=None)
                if self.transport is None: provider_health.record("speech", True)
                return result
        except (httpx.HTTPError, ValueError, TypeError, TimeoutError) as error:
            status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            if self.transport is None: provider_health.record("speech", False, type(error).__name__, status)
            log.warning("speech_degraded reason=%s status=%s", type(error).__name__, status)
            raise SpeechUnavailable("Keep the recording for later processing, or type your message.") from None
