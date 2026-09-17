import asyncio
import json
import re

import httpx
import provider_health

from provider_config import NVIDIA_MODEL, NLP_TIMEOUT, api_key
from nlp.provider import EmergencyFacts, NLPUnavailable


NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


SYSTEM_PROMPT = """
You are the emergency-information extraction component of AEGIS.

Extract ONLY emergency facts explicitly supported by citizen_text.

You must NOT:
- dispatch resources
- decide severity
- invent missing information
- assume injuries, trapped people, spreading or damage

The speech layer may already translate Telugu, Tamil, Hindi or another
Indian language into English.

Understand natural emergency language and minor transcription mistakes
when the intended meaning is clear.

Allowed incident_type values are exactly:
Fire
Flood
Accident
Landslide

RULES:

1. Unknown or ambiguous facts must be null.
2. Unstated boolean values must be null, not false.
3. "20 students are inside" may mean people_affected = 20.
4. People inside are NOT automatically trapped.
5. "2 people are injured" means injured = 2.
6. Never invent a location.
7. Never invent counts.
8. Never invent structural damage.
9. Never invent spreading.
10. vulnerable_groups may contain only:
    Children
    Elderly
    Disabled
    Pregnant
    Medical dependent

VERY IMPORTANT:

For every non-null extracted fact, field_evidence must contain an
EXACT substring copied from citizen_text.

If there is no exact supporting substring, leave that fact null.

Return ONLY one JSON object.

Do NOT return markdown.
Do NOT return explanation.
Do NOT return reasoning.

Return these keys:

{
  "incident_type": null,
  "location": null,
  "people_affected": null,
  "injured": null,
  "trapped": null,
  "vulnerable_groups": [],
  "spreading": null,
  "structural_damage": null,
  "hazard_intensity_estimate": null,
  "description": "",
  "language": "English",
  "confidence": null,
  "field_confidence": {},
  "missing_fields": [],
  "questions": [],
  "warnings": [],
  "field_evidence": {}
}
""".strip()


FACTS = {
    "incident_type",
    "location",
    "people_affected",
    "injured",
    "trapped",
    "vulnerable_groups",
    "spreading",
    "structural_damage",
    "hazard_intensity_estimate",
}


ALLOWED_GROUPS = {
    "Children",
    "Elderly",
    "Disabled",
    "Pregnant",
    "Medical dependent",
}


def _extract_json(text):
    cleaned = (text or "").strip()

    if not cleaned:
        raise ValueError("Model returned empty content")

    # Remove accidental Markdown JSON fences.
    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
            flags=re.I,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

    try:
        value = json.loads(cleaned)

    except json.JSONDecodeError:
        # Defensive recovery if model surrounds JSON with text.
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start < 0 or end <= start:
            raise

        value = json.loads(
            cleaned[start:end + 1]
        )

    if not isinstance(value, dict):
        raise ValueError(
            "Model response was not a JSON object"
        )

    return value


class NvidiaNLPProvider:
    def __init__(self, transport=None):
        self.transport = transport

    async def parse(self, request):
        import logging
        key = api_key("NVIDIA_API_KEY")
        if not key or (self.transport is None and provider_health.paused("nlp")):
            raise NLPUnavailable()
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"citizen_text": request.text}, ensure_ascii=False)}]
        try:
            async with asyncio.timeout(min(NLP_TIMEOUT, 50)), httpx.AsyncClient(
                timeout=httpx.Timeout(min(NLP_TIMEOUT, 50), connect=8), transport=self.transport,
                follow_redirects=False) as client:
                for attempt in range(2):
                    response = await client.post(NVIDIA_URL, headers={"Authorization": "Bearer " + key},
                        json={"model": NVIDIA_MODEL, "messages": messages, "temperature": 0.1,
                              "max_tokens": 1800, "stream": False,
                              "chat_template_kwargs": {"enable_thinking": False}})
                    response.raise_for_status()
                    try:
                        choice = response.json()["choices"][0]
                        if choice.get("finish_reason") != "stop":
                            raise ValueError("incomplete")
                        raw = _extract_json(choice["message"]["content"])
                        # Validate BEFORE any normalization: no coercion or silent loss of unknown fields.
                        result = EmergencyFacts.model_validate(raw)
                        if self.transport is None: provider_health.record("nlp", True)
                        return result
                    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as invalid:
                        logging.getLogger(__name__).warning("nlp_invalid_output reason=%s attempt=%s", type(invalid).__name__, attempt + 1)
                        if attempt:
                            raise NLPUnavailable() from None
                        messages.append({"role": "user", "content": "Return one complete JSON object matching every required field in the schema. Use null for unknown facts. No additional keys."})
        except (httpx.HTTPError, ValueError, TypeError, TimeoutError, NLPUnavailable) as error:
            status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            if self.transport is None: provider_health.record("nlp", False, type(error).__name__, status)
            logging.getLogger(__name__).warning("nlp_degraded reason=%s status=%s", type(error).__name__, status)
            raise NLPUnavailable() from None
