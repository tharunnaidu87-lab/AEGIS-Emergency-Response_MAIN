"""Local English emergency extraction. No network, persistence or dispatch side effects.

Nullable values mean unstated/ambiguous, not zero or false. An IntakeParser can be
replaced later by a validated provider without changing the report pipeline.
"""
import re
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, model_validator

Channel = Literal["SMS", "CALL"]
Incident = Literal["Fire", "Flood", "Accident", "Landslide"]
UnknownField = Literal["people_affected", "injured", "trapped", "spreading", "structural_damage"]


class ParseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False, extra="forbid")
    source: Channel
    text: str = Field(min_length=1, max_length=5000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    gps_verified: bool = False

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude")
        if self.gps_verified and self.latitude is None:
            raise ValueError("A GPS fix needs coordinates")
        return self


class Extraction(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    source: Channel
    method: Literal["LOCAL_RULE_BASED"] = "LOCAL_RULE_BASED"
    incident_type: Incident | None = None
    location: str | None = Field(default=None, max_length=200)
    people_affected: int | None = Field(default=None, ge=0, le=1000000)
    injured: int | None = Field(default=None, ge=0, le=1000000)
    trapped: int | None = Field(default=None, ge=0, le=1000000)
    vulnerable_groups: list[str] = Field(default_factory=list)
    spreading: bool | None = None
    structural_damage: bool | None = None
    hazard_intensity: float = Field(default=.5, ge=0, le=1)
    hazard_basis: str = "Default scenario intensity; no magnitude stated"
    description: str
    latitude: float | None = None
    longitude: float | None = None
    gps_verified: bool = False
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_factors: dict[str, int] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: dict[str, str] = Field(default_factory=dict)


class IntakeParser(Protocol):
    def parse(self, request: ParseRequest) -> Extraction: ...


UNITS = dict(zip("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20)))
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
NUMBER_WORDS = "|".join([*UNITS, *TENS, "hundred", "thousand", "million"])
NUMBER_PATTERN = re.compile(r"\b(?:" + NUMBER_WORDS + r")(?:[ -]+(?:" + NUMBER_WORDS + r"|and))*\b", re.I)


def normalize_numbers(text):
    def replace(match):
        if match.group().lower() == "one" and re.search(r"\bno\s+$", text[:match.start()], re.I):
            return match.group()
        words = re.split(r"[ -]+", match.group().lower())
        total = current = 0
        for word in words:
            if word in UNITS:
                current += UNITS[word]
            elif word in TENS:
                current += TENS[word]
            elif word == "hundred":
                current = max(1, current) * 100
            elif word in {"thousand", "million"}:
                total += max(1, current) * (1000 if word == "thousand" else 1000000)
                current = 0
        return str(total + current) + (" and" if words[-1] == "and" else "")
    return NUMBER_PATTERN.sub(replace, text)


KEYWORDS = {
    "Fire": r"fire|burning|smoke|flames?|explosion",
    "Flood": r"flood(?:ing)?|water (?:is )?(?:rising|entering)|overflow(?:ing)?|submerged",
    "Accident": r"accident|crash(?:ed)?|collision|vehicle hit",
    "Landslide": r"landslide|mudslide|rocks? falling|soil collapse",
}


def negated(text, start):
    prefix = re.split(r"[.!?;,]|\bbut\b|\band\b", text[:start])[-1][-65:]
    return bool(re.search(r"\b(?:no|not|never|without|isn't|isnt|aren't|arent)\b", prefix, re.I))


def positive_matches(text, pattern):
    return [m for m in re.finditer(r"\b(?:" + pattern + r")\b", text, re.I) if not negated(text, m.start())]


def flag(text, pattern):
    hits = list(re.finditer(r"\b(?:" + pattern + r")\b", text, re.I))
    if not hits:
        return None
    # Conflicting positive/negative observations need review, not an arbitrary choice.
    states = {not negated(text, m.start()) for m in hits}
    return states.pop() if len(states) == 1 else None


PERSON = r"(?:people|persons?|residents?|students?|children|workers?|passengers?|victims?)"
STATE = r"(?:are |were |is |have been |got |reportedly )?"


def count_for(text, kind, warnings):
    patterns = {
        "injured": [r"\b(\d+)\s+(?:" + PERSON + r"\s+)?" + STATE + r"(?:injured|hurt|wounded)\b",
                    r"\b(?:injured|injuries|wounded)\s*[:=]?\s*(\d+)\b"],
        "trapped": [r"\b(\d+)\s+(?:" + PERSON + r"\s+)?" + STATE + r"(?:trapped|stuck|stranded)\b",
                    r"\b(?:trapped|stranded)\s*[:=]?\s*(\d+)\b"],
        "people_affected": [r"\b(\d+)\s+" + PERSON + r"\b", r"\b(?:people affected|affected people|total people)\s*[:=]?\s*(\d+)\b"],
    }
    values = []
    for pattern in patterns[kind]:
        for match in re.finditer(pattern, text, re.I):
            # Do not turn decimals, negatives or ranges into an exact count.
            prefix = text[max(0, match.start()-16):match.start()]
            if re.search(r"[\d.-]$|\d+\s*(?:to|or|-)\s*$", prefix):
                warnings.append("A count is a range or invalid number; check the people details.")
                continue
            if negated(text, match.start()):
                continue
            value = int(match.group(1))
            if value > 1000000:
                warnings.append("A stated count is outside the supported range; please correct it.")
                continue
            # A subgroup is not automatically the overall affected population.
            if kind == "people_affected" and re.match(r"\s+" + STATE + r"(?:injured|hurt|wounded|trapped|stuck|stranded)\b", text[match.end():], re.I):
                continue
            values.append(value)
    if values:
        if len(set(values)) > 1:
            warnings.append("Multiple " + kind.replace("_", " ") + " counts were found; the largest is shown for review.")
        return max(values)
    zero = {"injured": r"(?:no (?:one (?:is |was )?)?(?:injuries|injured|hurt)|nobody (?:is |was )?injured)",
            "trapped": r"(?:no (?:one (?:is |was )?)?(?:trapped|stranded)|nobody (?:is |was )?trapped)",
            "people_affected": r"no (?:people|persons?|residents?) (?:are )?affected"}
    return 0 if re.search(zero[kind], text, re.I) else None


def extract_location(text):
    # Keep original spelling. Stop at sentence boundaries or a new situation clause.
    starts = list(re.finditer(r"\b(near|at|beside|behind|opposite|in|on)\s+", text, re.I))
    starts.sort(key=lambda match: match.group(1).lower() in {"in", "on"})
    for start in starts:
        candidate = text[start.end():]
        candidate = re.split(r"[.!?;\n]|,\s*(?:\d|around|about|water|fire)|\b(?:and|with|where)\b|\b(?:there|around|about|approximately)\s+\d|\b(?:is|are|has|have)\b", candidate, maxsplit=1, flags=re.I)[0]
        candidate = re.sub(r"^(?:the|a|an)\s+", "", candidate.strip(), flags=re.I).strip(" ,:")
        if candidate and not re.fullmatch(r"(?:here|there|inside|danger|trouble|need|\d+(?:\.\d+)?(?:\s*[ap]m)?)", candidate, re.I):
            return candidate[:200]
    landmark = re.search(r"\b([\w'-]+(?:\s+[\w'-]+){0,3}\s+(?:road|bridge|building|village|hospital|school|hostel))\b", text, re.I)
    if landmark:
        candidate = re.sub(r"^(?:there is |fire |flood |at |near |the )+", "", landmark.group(1), flags=re.I)
        return candidate[:200]
    return None


class LocalIntakeParser:
    def parse(self, request: ParseRequest) -> Extraction:
        original = request.text
        text = normalize_numbers(original.lower())
        warnings = []
        evidence = {}
        scores = {kind: positive_matches(text, pattern) for kind, pattern in KEYWORDS.items()}
        ranked = sorted(scores, key=lambda kind: len(scores[kind]), reverse=True)
        incident = ranked[0] if scores[ranked[0]] else None
        if incident and len(scores[ranked[0]]) == len(scores[ranked[1]]) and scores[ranked[1]]:
            incident = None
            warnings.append("More than one emergency type was mentioned. Choose the main incident.")
        if incident:
            evidence["incident_type"] = scores[incident][0].group()
        counts = {key: count_for(text, key, warnings) for key in ("people_affected", "injured", "trapped")}
        # '30 people trapped' explicitly describes a group, and supplies a known minimum.
        if counts["people_affected"] is None and counts["trapped"] is not None and re.search(r"\d+\s+" + PERSON, text):
            counts["people_affected"] = counts["trapped"]
            warnings.append("Affected count uses the stated trapped group; confirm whether others are affected.")
        if counts["people_affected"] is not None and max(counts["injured"] or 0, counts["trapped"] or 0) > counts["people_affected"]:
            warnings.append("Injured/trapped count exceeds the stated total. Correct the counts before sending.")
        location = extract_location(original)
        spreading = flag(text, r"spreading|(?:water (?:is )?)?(?:increasing|rising)(?: quickly| rapidly)?|getting worse|overflowing")
        structural = flag(text, r"(?:structural (?:damage|failure)|(?:building |roof |wall |bridge |hostel )?(?:collapsed|collapsing))")
        groups = [label for label, pattern in {
            "Children": r"children|kids|babies|infants", "Elderly": r"elderly|senior citizens?|old people",
            "Disabled": r"disabled|wheelchair|disabilities", "Pregnant": r"pregnant",
            "Medical dependent": r"medical(?:ly)? dependent|oxygen dependent|dialysis",
        }.items() if positive_matches(text, pattern)]
        urgency = positive_matches(text, r"critical|unconscious|heavy smoke|rapidly|rapid|explosion")
        intense = spreading is True or structural is True or bool(urgency)
        confidence_factors = {"incident": 30 if incident else 0, "location": 20 if location else 0,
                              "gps": 15 if request.gps_verified else 0,
                              "people_count": 15 if counts["people_affected"] is not None else 0,
                              "useful_details": min(15, 5 * (sum(counts[k] is not None for k in ("injured", "trapped")) + bool(groups) + (spreading is not None) + (structural is not None)))}
        missing = [key for key, value in {"incident_type": incident, "location": location, **counts,
                   "spreading": spreading, "structural_damage": structural, "coordinates": request.latitude}.items() if value is None]
        questions = {"incident_type": "What kind of emergency is happening?", "location": "Where is the emergency?",
                     "people_affected": "Approximately how many people are affected? You can leave this unknown.",
                     "coordinates": "Share device GPS or enter the incident coordinates for the map.",
                     "spreading": "Is the situation spreading? Leave it unknown if you are unsure."}
        return Extraction(source=request.source, incident_type=incident, location=location, **counts,
            vulnerable_groups=groups, spreading=spreading, structural_damage=structural,
            hazard_intensity=.8 if intense else .5,
            hazard_basis="Estimated from urgency/spreading words; review this scenario value" if intense else "Default scenario intensity; no magnitude stated",
            description=original, latitude=request.latitude, longitude=request.longitude, gps_verified=request.gps_verified,
            confidence=round(sum(confidence_factors.values())/100, 2), confidence_factors=confidence_factors,
            missing_fields=missing, questions=[question for key, question in questions.items() if key in missing],
            warnings=list(dict.fromkeys(warnings)), evidence=evidence)


local_parser: IntakeParser = LocalIntakeParser()


def parse_intake(request: ParseRequest) -> Extraction:
    return Extraction.model_validate(local_parser.parse(request))


def report_intake_metadata(payload):
    """Recompute extraction on the server; retain reviewed fields separately per report."""
    if payload.get("source") not in {"SMS", "CALL"} or not payload.get("raw_content", "").strip():
        return None
    parsed = parse_intake(ParseRequest(source=payload["source"], text=payload["raw_content"],
                         latitude=payload["latitude"], longitude=payload["longitude"], gps_verified=payload.get("gps_verified", False)))
    unknown = payload.get("intake_unknown_fields", [])
    fields = ["incident_type", "location", "people_affected", "injured", "trapped", "vulnerable_groups", "spreading", "structural_damage", "hazard_intensity"]
    reviewed = {key: None if key in unknown else payload.get(key) for key in fields}
    return {"extraction": parsed.model_dump(), "reviewed": reviewed, "unknown_fields": unknown,
            "corrected_fields": [key for key in fields if reviewed[key] != getattr(parsed, key)],
            "confidence_basis": "Original text extraction completeness; separate from incident evidence and severity"}
