from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Assignment, Variant


def _bucket_0_99(experiment_id: UUID, user_id: str) -> int:
    # stable deterministic bucket
    key = f"{experiment_id}:{user_id}".encode("utf-8")
    digest = hashlib.sha256(key).digest()
    # use first 4 bytes for an int
    n = int.from_bytes(digest[:4], byteorder="big", signed=False)
    return n % 100


def choose_variant(db: Session, experiment_id: UUID, user_id: str) -> Variant:
    variants = db.scalars(
        select(Variant).where(Variant.experiment_id == experiment_id).order_by(Variant.key.asc())
    ).all()
    if not variants:
        raise ValueError("Experiment has no variants")

    # Build cumulative ranges using traffic_allocation
    bucket = _bucket_0_99(experiment_id, user_id)
    cum = 0
    for v in variants:
        cum += int(v.traffic_allocation)
        if bucket < cum:
            return v

    # If allocations are slightly off, fall back to last variant
    return variants[-1]


def get_or_create_assignment(db: Session, experiment_id: UUID, user_id: str) -> Assignment:
    existing = db.scalar(
        select(Assignment).where(
            Assignment.experiment_id == experiment_id,
            Assignment.user_id == user_id,
        )
    )
    if existing:
        return existing

    variant = choose_variant(db, experiment_id, user_id)
    a = Assignment(
        experiment_id=experiment_id,
        user_id=user_id,
        variant_id=variant.id,
    )
    db.add(a)

    try:
        db.commit()
        db.refresh(a)
        return a
    except IntegrityError:
        # race: someone else inserted, fetch and return
        db.rollback()
        existing = db.scalar(
            select(Assignment).where(
                Assignment.experiment_id == experiment_id,
                Assignment.user_id == user_id,
            )
        )
        if existing:
            return existing
        raise
