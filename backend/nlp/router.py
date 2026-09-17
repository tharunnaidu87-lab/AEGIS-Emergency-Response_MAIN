import re
from intake_nlp import Extraction, parse_intake
from nlp.nvidia import NvidiaNLPProvider
from nlp.provider import NLPUnavailable
from provider_config import NVIDIA_MODEL, api_key

QUESTIONS = {
    "incident_type": "What kind of emergency is happening?",
    "location": "Where is the emergency? Please confirm the landmark or street.",
    "people_affected": "Approximately how many people are affected?",
    "injured": "How many people are injured, if known?",
    "trapped": "How many people cannot get out, if known?",
    "spreading": "Is the situation spreading? Leave unknown if unsure.",
}
FACTS = [*QUESTIONS, "structural_damage", "vulnerable_groups", "hazard_intensity_estimate"]


async def extract(request, provider=None):
    if api_key("NVIDIA_API_KEY") or provider is not None:
        try:
            facts = await (provider or NvidiaNLPProvider()).parse(request)
            values = facts.model_dump()
            warnings = list(facts.warnings)
            for key in FACTS:
                evidence = facts.field_evidence.get(key)
                if evidence:
                    match = re.search(re.escape(evidence), request.text, re.IGNORECASE)
                    if match:
                        evidence = match.group(0)
                        facts.field_evidence[key] = evidence
                if values[key] is not None and values[key] != [] and (not evidence or evidence not in request.text):
                    values[key] = [] if key == "vulnerable_groups" else None
                    warnings.append(key.replace("_", " ") + " lacked supporting text; left unknown.")
            if values["incident_type"] is None:
                basic = parse_intake(request)
                if basic.incident_type is not None:
                    values["incident_type"] = basic.incident_type
                    warnings.append("Basic rules identified the incident type. Please verify it.")
            if values["people_affected"] is not None and max(values["injured"] or 0, values["trapped"] or 0) > values["people_affected"]:
                values["people_affected"] = None
                warnings.append("Conflicting counts: confirm the affected total.")
            missing = [k for k in FACTS if values[k] is None]
            scores = {k: facts.field_confidence.get(k) if values[k] is not None else None for k in FACTS}
            questions = [q for k, q in QUESTIONS.items() if k in missing or (scores[k] is not None and scores[k] < .7)]
            if request.latitude is None:
                missing.append("coordinates")
                questions.append("Share GPS or enter incident coordinates for the map.")
            estimate = values["hazard_intensity_estimate"]
            return Extraction(source=request.source, method="ADVANCED_NLP", nlp_provider="NVIDIA_NIM",
                nlp_model=NVIDIA_MODEL, language=facts.language, confidence=facts.confidence,
                confidence_basis="Model self-assessment, uncalibrated; not a probability or severity score",
                field_confidence=scores, hazard_intensity_estimate=estimate,
                hazard_intensity=estimate if estimate is not None else .5,
                hazard_basis="Uncalibrated model estimate; review before sending" if estimate is not None else "Default scenario intensity; magnitude unknown",
                **{k: values[k] for k in FACTS if k != "hazard_intensity_estimate"},
                description=request.text, latitude=request.latitude, longitude=request.longitude,
                gps_verified=request.gps_verified, missing_fields=missing, questions=questions,
                warnings=warnings, evidence=facts.field_evidence)
        except NLPUnavailable:
            pass
    result = parse_intake(request)
    result.field_confidence = {key: None for key in FACTS}
    result.questions = list(dict.fromkeys([*result.questions, *[q for k, q in QUESTIONS.items() if getattr(result, k) is None]]))
    result.warnings.append("Using basic emergency analysis. Check the details, especially multilingual text, before submitting.")
    return result
