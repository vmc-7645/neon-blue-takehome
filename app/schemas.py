from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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


class VariantOut(BaseModel):
    id: UUID
    key: str
    allocation_percent: int
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
