from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceCreate(BaseModel):
    chapter_id: str | None = None
    chunk_id: str | None = None
    quote: str = Field(min_length=1, max_length=10000)
    source_type: str = Field(default="explicit_fact", max_length=40)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: list[str] | None = None
    state: Literal["active", "rejected"] | None = None
    reason: str = Field(default="", max_length=1000)


class FactCreate(BaseModel):
    character_id: str
    fact_type: str = Field(min_length=1, max_length=80)
    value: Any
    evidence: EvidenceCreate | None = None
    source_type: Literal["agent", "user", "import"] = "user"
    locked_by_user: bool = False


class FactUpdate(BaseModel):
    value: Any
    evidence: EvidenceCreate | None = None
    reason: str = Field(default="", max_length=1000)
    locked_by_user: bool | None = None


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10000)
    story_time_start: str | None = None
    story_time_end: str | None = None
    chapter_no: int | None = Field(default=None, ge=1)
    sequence_no: int | None = Field(default=None, ge=0)
    evidence: EvidenceCreate | None = None


class EventUpdate(EventCreate):
    reason: str = Field(default="", max_length=1000)


class ClueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    original_text: str = Field(min_length=1, max_length=10000)
    possible_meaning: str = Field(default="", max_length=10000)
    first_chapter_no: int | None = Field(default=None, ge=1)
    state: Literal["candidate", "open", "hypothesis"] = "candidate"
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: EvidenceCreate | None = None


class ClueUpdate(ClueCreate):
    reason: str = Field(default="", max_length=1000)


class RelationCreate(BaseModel):
    subject_type: str = Field(min_length=1, max_length=40)
    subject_id: str = Field(min_length=1, max_length=200)
    relation_type: str = Field(min_length=1, max_length=80)
    object_type: str = Field(min_length=1, max_length=40)
    object_id: str = Field(min_length=1, max_length=200)
    value: dict[str, Any] = Field(default_factory=dict)
    evidence: EvidenceCreate | None = None


class RelationUpdate(RelationCreate):
    reason: str = Field(default="", max_length=1000)


class ReviewResolution(BaseModel):
    action: Literal["approve", "reject", "merge", "verify", "dismiss"]
    target_id: str | None = None
    reason: str = Field(default="", max_length=1000)


class SynthesisRequest(BaseModel):
    profile_id: str | None = None
