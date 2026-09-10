import asyncio
import httpx
from pydantic import ValidationError
from provider_config import SARVAM_MODEL, STT_TIMEOUT, api_key
from speech.provider import SpeechUnavailable, Transcription


class SarvamSpeechProvider:
    def __init__(self, transport=None):
        self.transport = transport

    async def transcribe(self, audio, content_type):
        key = api_key("SARVAM_API_KEY")
        if not key:
            raise SpeechUnavailable("Advanced multilingual transcription is unavailable.")
        try:
            async with asyncio.timeout(STT_TIMEOUT), httpx.AsyncClient(
                timeout=httpx.Timeout(STT_TIMEOUT, connect=10), transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.post("https://api.sarvam.ai/speech-to-text",
                    headers={"api-subscription-key": key},
                    data={"model": SARVAM_MODEL, "language_code": "unknown", "mode": "codemix"},
                    files={"file": ("recording.webm", audio, content_type)})
                response.raise_for_status()
                data = response.json()
                return Transcription(model=SARVAM_MODEL, transcript=data["transcript"],
                                     language_code=data.get("language_code"), confidence=None)
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, ValidationError):
            raise SpeechUnavailable("Advanced multilingual transcription is unavailable. Retry or use browser speech/manual text.") from None
