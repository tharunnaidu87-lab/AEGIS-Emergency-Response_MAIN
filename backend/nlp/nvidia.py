import asyncio
import json
import re

import httpx
from pydantic import ValidationError

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


def _int_or_none(value):
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        if 0 <= value <= 1_000_000:
            return value

        return None

    if isinstance(value, float) and value.is_integer():
        value = int(value)

        if 0 <= value <= 1_000_000:
            return value

        return None

    if isinstance(value, str):
        value = value.strip()

        if value.isdigit():
            number = int(value)

            if 0 <= number <= 1_000_000:
                return number

    return None


def _score_or_none(value):
    if value is None or isinstance(value, bool):
        return None

    try:
        score = float(value)

    except (TypeError, ValueError):
        return None

    if 0 <= score <= 1:
        return score

    return None


def _text_or_none(value, max_length):
    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    return value[:max_length]


def _incident_or_none(value):
    if not isinstance(value, str):
        return None

    mapping = {
        "fire": "Fire",
        "flood": "Flood",
        "accident": "Accident",
        "landslide": "Landslide",
    }

    return mapping.get(
        value.strip().lower()
    )


def _exact_substring(candidate, source):
    if not isinstance(candidate, str):
        return None

    candidate = candidate.strip()

    if not candidate:
        return None

    match = re.search(
        re.escape(candidate),
        source,
        flags=re.I,
    )

    if not match:
        return None

    return source[
        match.start():
        match.end()
    ]


def _normalize(raw, citizen_text):
    values = {
        "incident_type":
            _incident_or_none(
                raw.get("incident_type")
            ),

        "location":
            _text_or_none(
                raw.get("location"),
                200,
            ),

        "people_affected":
            _int_or_none(
                raw.get("people_affected")
            ),

        "injured":
            _int_or_none(
                raw.get("injured")
            ),

        "trapped":
            _int_or_none(
                raw.get("trapped")
            ),

        "vulnerable_groups":
            [],

        "spreading":
            (
                raw.get("spreading")
                if isinstance(
                    raw.get("spreading"),
                    bool,
                )
                else None
            ),

        "structural_damage":
            (
                raw.get("structural_damage")
                if isinstance(
                    raw.get("structural_damage"),
                    bool,
                )
                else None
            ),

        "hazard_intensity_estimate":
            _score_or_none(
                raw.get(
                    "hazard_intensity_estimate"
                )
            ),
    }

    groups = raw.get(
        "vulnerable_groups"
    )

    if isinstance(groups, list):
        values["vulnerable_groups"] = [
            item
            for item in groups
            if item in ALLOWED_GROUPS
        ][:5]

    raw_evidence = raw.get(
        "field_evidence"
    )

    if not isinstance(
        raw_evidence,
        dict,
    ):
        raw_evidence = {}

    evidence = {}

    for key in FACTS:
        exact = _exact_substring(
            raw_evidence.get(key),
            citizen_text,
        )

        if exact:
            evidence[key] = exact

    # AEGIS only accepts model facts that have
    # exact supporting text.
    for key in FACTS:
        value = values[key]

        populated = (
            value is not None
            and value != []
        )

        if (
            populated
            and key not in evidence
        ):
            if key == "vulnerable_groups":
                values[key] = []
            else:
                values[key] = None

    raw_confidence = raw.get(
        "field_confidence"
    )

    if not isinstance(
        raw_confidence,
        dict,
    ):
        raw_confidence = {}

    field_confidence = {
        key: _score_or_none(
            raw_confidence.get(key)
        )
        for key in FACTS
    }

    missing_fields = [
        key
        for key, value
        in values.items()
        if value is None
        or value == []
    ]

    def clean_list(value):
        if not isinstance(value, list):
            return []

        return [
            item.strip()[:300]
            for item in value
            if isinstance(item, str)
            and item.strip()
        ][:10]

    return {
        **values,

        "description":
            citizen_text,

        "language":
            _text_or_none(
                raw.get("language"),
                80,
            )
            or "English",

        "confidence":
            _score_or_none(
                raw.get("confidence")
            ),

        "field_confidence":
            field_confidence,

        "missing_fields":
            missing_fields,

        "questions":
            clean_list(
                raw.get("questions")
            ),

        "warnings":
            clean_list(
                raw.get("warnings")
            ),

        "field_evidence":
            evidence,
    }


class NvidiaNLPProvider:
    def __init__(self, transport=None):
        self.transport = transport

    async def parse(self, request):
        key = api_key(
            "NVIDIA_API_KEY"
        )

        if not key:
            print(
                "[NVIDIA NLP ERROR] "
                "NVIDIA_API_KEY is missing"
            )

            raise NLPUnavailable()

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "citizen_text":
                            request.text
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        try:
            async with asyncio.timeout(
                NLP_TIMEOUT
            ), httpx.AsyncClient(
                timeout=httpx.Timeout(
                    45,
                    connect=10,
                ),
                transport=self.transport,
                follow_redirects=False,
            ) as client:

                response = await client.post(
                    NVIDIA_URL,
                    headers={
                        "Authorization":
                            "Bearer " + key,

                        "Content-Type":
                            "application/json",

                        "Accept":
                            "application/json",
                    },
                    json={
                        "model":
                            NVIDIA_MODEL,

                        "messages":
                            messages,

                        "temperature":
                            0.1,

                        "max_tokens":
                            1400,

                        "stream":
                            False,

                        # Disable Nemotron thinking so
                        # final JSON appears in content.
                        "chat_template_kwargs": {
                            "enable_thinking":
                                False
                        },
                    },
                )

                response.raise_for_status()

                payload = response.json()

                choice = (
                    payload["choices"][0]
                )

                message = (
                    choice["message"]
                )

                content = (
                    message.get("content")
                )

                print(
                    "[NVIDIA NLP] model:",
                    NVIDIA_MODEL,
                )

                print(
                    "[NVIDIA NLP] "
                    "response received"
                )

                if (
                    not isinstance(
                        content,
                        str,
                    )
                    or not content.strip()
                ):
                    print(
                        "[NVIDIA NLP ERROR] "
                        "Empty content; "
                        "finish_reason=",
                        choice.get(
                            "finish_reason"
                        ),
                    )

                    raise NLPUnavailable()

                raw = _extract_json(
                    content
                )

                normalized = _normalize(
                    raw,
                    request.text,
                )

                facts = (
                    EmergencyFacts
                    .model_validate(
                        normalized
                    )
                )

                print(
                    "[NVIDIA NLP] "
                    "extraction successful"
                )

                return facts

        except NLPUnavailable:
            raise

        except httpx.HTTPStatusError as error:
            print(
                f"[NVIDIA NLP ERROR] "
                f"HTTP "
                f"{error.response.status_code}: "
                f"{error.response.text[:1200]}"
            )

            raise NLPUnavailable() from None

        except httpx.TimeoutException as error:
            print(
                "[NVIDIA NLP ERROR] "
                "HTTP TIMEOUT:",
                type(error).__name__,
            )

            raise NLPUnavailable() from None

        except TimeoutError:
            print(
                "[NVIDIA NLP ERROR] "
                "OVERALL TIMEOUT"
            )

            raise NLPUnavailable() from None

        except ValidationError as error:
            print(
                "[NVIDIA NLP ERROR] "
                "VALIDATION:",
                str(error)[:1200],
            )

            raise NLPUnavailable() from None

        except (
            httpx.RequestError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as error:

            print(
                "[NVIDIA NLP ERROR]",
                type(error).__name__,
                str(error)[:1200],
            )

            raise NLPUnavailable() from None