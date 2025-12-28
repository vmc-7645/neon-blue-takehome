from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


ExperimentStatus = Literal["running", "stopped"]


class ExperimentStatusUpdate(BaseModel):
    status: ExperimentStatus = Field(..., description="Experiment status: running|stopped")


class VariantCreate(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    allocation_percent: int = Field(ge=0, le=100)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    variants: List[VariantCreate] = Field(min_length=1)

    @field_validator("variants")
    @classmethod
    def validate_variants(cls, v: List[VariantCreate]) -> List[VariantCreate]:
        keys = [vv.key for vv in v]
        if len(set(keys)) != len(keys):
            raise ValueError("Variant keys must be unique within an experiment")

        total = sum(vv.allocation_percent for vv in v)
        if total != 100:
            raise ValueError(f"Variant allocation_percent must sum to 100 (got {total})")

        if all(vv.allocation_percent == 0 for vv in v):
            raise ValueError("At least one variant must have allocation_percent > 0")

        return v

class EventCreate(BaseModel):
    experiment_id: UUID
    user_id: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=64)
    timestamp: datetime
    properties: Dict[str, Any] = Field(default_factory=dict)

class VariantOut(BaseModel):
    id: UUID
    key: str

    # ORM field is traffic_allocation
    allocation_percent: int = Field(alias="traffic_allocation")

    # ORM field is meta (DB column name "metadata")
    metadata: Dict[str, Any] = Field(alias="meta")

    class Config:
        from_attributes = True
        populate_by_name = True


class ExperimentOut(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    status: str
    created_at: datetime
    variants: List[VariantOut]

    class Config:
        from_attributes = True

class AssignmentOut(BaseModel):
    experiment_id: UUID
    user_id: str
    variant_id: UUID
    variant_key: str
    assigned_at: datetime


class ResultsQueryOut(BaseModel):
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    event_type: Optional[str] = None
    group_by: str = "variant"  # "variant" or "day"
    metric: str = "conversions"  # "conversions" | "events" | "unique_users"


class VariantResultsRow(BaseModel):
    variant_id: UUID
    variant_key: str
    assignments: int
    unique_users: int
    events: int
    conversions: int
    conversion_rate: float


class TimeBucketRow(BaseModel):
    bucket_start: datetime
    bucket_end: datetime
    per_variant: Dict[str, VariantResultsRow]


class ExperimentResultsOut(BaseModel):
    experiment_id: UUID
    generated_at: datetime
    query: ResultsQueryOut
    totals: Dict[str, VariantResultsRow]  # key -> variant_key, plus "__overall__"
    time_series: Optional[List[TimeBucketRow]] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    definitions: Dict[str, str] = Field(default_factory=dict)

class EventOut(BaseModel):
    id: UUID
    experiment_id: UUID
    user_id: str
    type: str
    timestamp: datetime
    properties: Dict[str, Any]

    class Config:
        from_attributes = True

