from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class Contract(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", allow_inf_nan=False)


class Candidate(Contract):
    artifact_id: int = Field(gt=0)
    content_version_id: int = Field(gt=0)
    museum_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=300)
    title: str = Field(max_length=300)
    description: str = Field(max_length=2000)
    topics: list[str] = Field(max_length=30)
    gallery_id: int | None = None
    gallery_name: str = Field(default="", max_length=300)
    floor_id: int | None = None
    visit_minutes: float = Field(ge=1, le=30)


class PlanRequest(Contract):
    museum_id: int = Field(gt=0)
    available_minutes: int = Field(ge=5, le=240)
    interests: list[Term] = Field(min_length=1, max_length=8)
    max_stops: int = Field(default=12, ge=1, le=30)
    candidates: list[Candidate] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_candidates(self):
        ids = [c.artifact_id for c in self.candidates]
        if len(set(ids)) != len(ids) or any(c.museum_id != self.museum_id for c in self.candidates):
            raise ValueError("Candidates must be unique and belong to the requested museum")
        return self


class Stop(Contract):
    artifact_id: int
    content_version_id: int
    visit_minutes: float
    walk_minutes: float
    score: float
    matched_interests: list[str]
    reason: str


class PlanResult(Contract):
    engine_version: str = "content-tfidf-v1"
    estimated_minutes: float
    used_fallback: bool
    notice: str
    stops: list[Stop]
