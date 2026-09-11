from typing import Annotated, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field
from intake_nlp import Incident, ParseRequest

Score = Annotated[float, Field(ge=0, le=1)]
Count = Annotated[int, Field(ge=0, le=1000000)]
ShortText = Annotated[str, Field(min_length=1, max_length=300)]
Fact = Literal["incident_type", "location", "people_affected", "injured", "trapped",
               "vulnerable_groups", "spreading", "structural_damage", "hazard_intensity_estimate"]


class EmergencyFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    incident_type: Incident | None
    location: Annotated[str, Field(min_length=1, max_length=200)] | None
    people_affected: Count | None
    injured: Count | None
    trapped: Count | None
    vulnerable_groups: list[Literal["Children", "Elderly", "Disabled", "Pregnant", "Medical dependent"]] = Field(max_length=5)
    spreading: bool | None
    structural_damage: bool | None
    hazard_intensity_estimate: Score | None
    description: str = Field(max_length=5000)
    language: Annotated[str, Field(max_length=80)] | None
    confidence: Score | None
    field_confidence: dict[Fact, Score | None]
    missing_fields: list[Fact] = Field(max_length=9)
    questions: list[ShortText] = Field(max_length=10)
    warnings: list[ShortText] = Field(max_length=10)
    # Verbatim support is required for every non-null fact; unsupported facts become unknown.
    field_evidence: dict[Fact, ShortText]


class NLPProvider(Protocol):
    async def parse(self, request: ParseRequest) -> EmergencyFacts: ...


class NLPUnavailable(Exception):
    pass
