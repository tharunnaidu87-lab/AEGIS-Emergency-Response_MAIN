import asyncio

import httpx
from pydantic import ValidationError

from provider_config import SARVAM_MODEL, STT_TIMEOUT, api_key
from speech.provider import SpeechUnavailable, Transcription


SARVAM_URL = "https://api.sarvam.ai/speech-to-text"


class SarvamSpeechProvider:
    def __init__(self, transport=None):
        self.transport = transport

    async def _request(
        self,
        client: httpx.AsyncClient,
        key: str,
        audio: bytes,
        language_code: str,
        mode: str,
    ) -> dict:
        """
        Send one STT request to Sarvam.

        Important:
        Browser records audio/webm;codecs=opus, but Sarvam expects
        the upload MIME type as audio/webm.
        """

        response = await client.post(
            SARVAM_URL,
            headers={
                "api-subscription-key": key,
            },
            data={
                "model": SARVAM_MODEL,
                "language_code": language_code,
                "mode": mode,
            },
            files={
                "file": (
                    "recording.webm",
                    audio,
                    "audio/webm",
                )
            },
        )

        response.raise_for_status()

        data = response.json()

        transcript = str(data.get("transcript") or "").strip()

        if not transcript:
            raise ValueError("Sarvam returned an empty transcript")

        return data

    async def transcribe(self, audio, content_type):
        key = api_key("SARVAM_API_KEY")

        if not key:
            raise SpeechUnavailable(
                "Advanced multilingual transcription is unavailable."
            )

        if not audio:
            raise SpeechUnavailable(
                "No audio was recorded."
            )

        try:
            async with asyncio.timeout(STT_TIMEOUT), httpx.AsyncClient(
                timeout=httpx.Timeout(
                    STT_TIMEOUT,
                    connect=10,
                ),
                transport=self.transport,
                follow_redirects=False,
            ) as client:

                # -------------------------------------------------
                # PASS 1
                # Detect the language automatically.
                # Keep code-mixed English words recognizable.
                # -------------------------------------------------

                first = await self._request(
                    client=client,
                    key=key,
                    audio=audio,
                    language_code="unknown",
                    mode="codemix",
                )

                first_transcript = str(
                    first.get("transcript") or ""
                ).strip()

                detected_language = (
                    first.get("language_code")
                    or "unknown"
                )

                print(
                    "[SARVAM] detected language:",
                    detected_language,
                )

                print(
                    "[SARVAM] first pass:",
                    first_transcript[:300],
                )

                # -------------------------------------------------
                # PASS 2
                #
                # Once Sarvam tells us the language, send the SAME
                # audio again with the explicit language code.
                #
                # For Indian-language speech we ask Sarvam to translate
                # it into English. This gives the NLP engine a much
                # cleaner and more reliable input.
                #
                # English simply gets transcribed again.
                # -------------------------------------------------

                if (
                    detected_language
                    and detected_language != "unknown"
                ):
                    try:
                        if detected_language.startswith("en"):
                            second_mode = "transcribe"
                        else:
                            second_mode = "translate"

                        second = await self._request(
                            client=client,
                            key=key,
                            audio=audio,
                            language_code=detected_language,
                            mode=second_mode,
                        )

                        final_transcript = str(
                            second.get("transcript") or ""
                        ).strip()

                        if final_transcript:
                            print(
                                "[SARVAM] second pass:",
                                final_transcript[:300],
                            )

                            return Transcription(
                                model=SARVAM_MODEL,
                                transcript=final_transcript,
                                language_code=detected_language,
                                confidence=None,
                            )

                    except Exception as second_error:
                        # Do NOT lose a valid first transcription just
                        # because the accuracy-improvement pass failed.
                        print(
                            "[SARVAM] second pass failed:",
                            type(second_error).__name__,
                        )

                # First-pass fallback.
                return Transcription(
                    model=SARVAM_MODEL,
                    transcript=first_transcript,
                    language_code=detected_language,
                    confidence=None,
                )

        except httpx.HTTPStatusError as error:
            print(
                f"[SARVAM ERROR] HTTP "
                f"{error.response.status_code}: "
                f"{error.response.text[:1000]}"
            )

            raise SpeechUnavailable(
                "Advanced multilingual transcription is unavailable. "
                "Retry or use browser speech/manual text."
            ) from None

        except httpx.TimeoutException as error:
            print(
                "[SARVAM ERROR] HTTP TIMEOUT:",
                type(error).__name__,
            )

            raise SpeechUnavailable(
                "Advanced multilingual transcription timed out."
            ) from None

        except TimeoutError:
            print(
                "[SARVAM ERROR] OVERALL TIMEOUT"
            )

            raise SpeechUnavailable(
                "Advanced multilingual transcription timed out."
            ) from None

        except (
            httpx.RequestError,
            ValueError,
            KeyError,
            TypeError,
            ValidationError,
        ) as error:
            print(
                "[SARVAM ERROR]",
                type(error).__name__,
                str(error)[:500],
            )

            raise SpeechUnavailable(
                "Advanced multilingual transcription is unavailable. "
                "Retry or use browser speech/manual text."
            ) from None