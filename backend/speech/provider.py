from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field


class Transcription(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    provider: Literal["SARVAM"] = "SARVAM"
    model: str
    language_code: str | None = Field(default=None, max_length=40)
    transcript: str = Field(min_length=1, max_length=5000)
    # Sarvam language_probability is NOT transcript confidence.
    confidence: float | None = Field(default=None, ge=0, le=1)
    result_id: str | None = None


class SpeechProvider(Protocol):
    async def transcribe(self, audio: bytes, content_type: str) -> Transcription: ...


class SpeechUnavailable(Exception):
    """Safe public exception; never contains provider response bodies/headers."""
