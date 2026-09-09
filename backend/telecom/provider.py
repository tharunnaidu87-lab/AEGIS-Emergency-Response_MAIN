"""Future telecom boundary. No configured provider, number, webhook or outbound calls.

A real adapter must verify signatures on raw requests, enforce replay protection,
and normalize a provider event. Calling this interface never saves or dispatches
an incident: a future operator review screen must confirm it through /reports.
"""
from typing import Mapping, Protocol
from pydantic import BaseModel, Field
from intake_nlp import Channel, Extraction, ParseRequest, parse_intake


class InboundMessage(BaseModel):
    provider_message_id: str = Field(min_length=1, max_length=200)
    source: Channel
    sender: str = Field(max_length=100)
    text: str = Field(min_length=1, max_length=5000)


class TelecomProvider(Protocol):
    def verify_and_normalize(self, headers: Mapping[str, str], raw_body: bytes) -> InboundMessage: ...


def prepare_for_review(message: InboundMessage) -> Extraction:
    # Phone identity is not GPS. Coordinates stay unknown until obtained separately.
    return parse_intake(ParseRequest(source=message.source, text=message.text))
