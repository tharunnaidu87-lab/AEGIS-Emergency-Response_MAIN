"""Validated API inputs shared by intake and scenario calculations."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from intake_nlp import UnknownField


class Coordinates(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Scenario(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    unavailable_resource_ids: list[str] = Field(default_factory=list, max_length=100)
    closed_shelter_ids: list[str] = Field(default_factory=list, max_length=100)
    hospital_capacity_factor: float = Field(default=1, ge=0, le=1)
    shelter_capacity_factor: float = Field(default=1, ge=0, le=1)
    road_blocked: bool = False
    response_delay_minutes: int = Field(default=0, ge=0, le=120)
    forecast_minutes: int = Field(default=30, ge=0, le=120)


class AnalysisRequest(Coordinates):
    report_id: str | None = Field(default=None, max_length=100)
    incident_type: Literal["Flood", "Landslide", "Fire", "Accident"]
    location: str = Field(min_length=1, max_length=200)
    people_affected: int = Field(ge=0, le=1000000)
    hazard_intensity: float = Field(default=.5, ge=0, le=1)
    description: str = Field(default="", max_length=5000)
    injured: int = Field(default=0, ge=0, le=1000000)
    trapped: int = Field(default=0, ge=0, le=1000000)
    vulnerable_groups: list[str] = Field(default_factory=list, max_length=20)
    gps_verified: bool = False
    spreading: bool = False
    structural_damage: bool = False
    scenario: Scenario = Field(default_factory=Scenario)

    @model_validator(mode="after")
    def validate_people(self):
        # Injured and trapped can overlap, but neither may exceed the report total.
        if max(self.injured, self.trapped) > self.people_affected:
            raise ValueError("Injured/trapped counts cannot exceed people affected")
        return self


class ReportCreateRequest(AnalysisRequest):
    client_request_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{16,80}$")
    photos: list[str] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def media_limits(self):
        if any(len(p) > 950000 for p in self.photos):
            raise ValueError("Compress photos before submitting")
        return self

    intake_result_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    intake_unknown_fields: list[UnknownField] = Field(default_factory=list, max_length=5)
    source: Literal["APP", "SMS", "CALL"] = "APP"
    raw_content: str = Field(default="", max_length=10000)
    phone: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def intake_is_baseline(self):
        if self.source in {"SMS", "CALL"} and len(self.raw_content) > 5000:
            raise ValueError("Keep the intake message within 5000 characters")
        if self.scenario != Scenario():
            raise ValueError("What-if overrides belong to /aegis-analyse, not citizen intake")
        return self
