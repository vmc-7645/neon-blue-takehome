from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.db import get_db
from app.models import Experiment, Variant, Assignment
from app.schemas import ExperimentCreate, ExperimentOut, AssignmentOut
from app.services.assignment import get_or_create_assignment

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
def create_experiment(payload: ExperimentCreate, db: Session = Depends(get_db)) -> Experiment:
    exp = Experiment(
        name=payload.name,
        description=payload.description,
        status="running",
    )
    db.add(exp)
    db.flush()  # exp.id is available

    for v in payload.variants:
        db.add(
            Variant(
                experiment_id=exp.id,
                key=v.key,
                traffic_allocation=v.allocation_percent,
                meta=v.metadata,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Experiment creation conflict")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Failed to create experiment")

    # reload with variants
    exp = db.scalar(
        select(Experiment)
        .where(Experiment.id == exp.id)
        .options(selectinload(Experiment.variants))
    )
    return exp


@router.get("/{experiment_id}", response_model=ExperimentOut)
def get_experiment(experiment_id: UUID, db: Session = Depends(get_db)) -> Experiment:
    exp = db.scalar(
        select(Experiment)
        .where(Experiment.id == experiment_id)
        .options(selectinload(Experiment.variants))
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp

@router.get("/{experiment_id}/assignment/{user_id}", response_model=AssignmentOut)
def get_assignment(experiment_id: UUID, user_id: str, db: Session = Depends(get_db)) -> AssignmentOut:
    exp = db.scalar(select(Experiment.id).where(Experiment.id == experiment_id))
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    a = get_or_create_assignment(db, experiment_id=experiment_id, user_id=user_id)

    # fetch variant key
    v = db.scalar(select(Variant).where(Variant.id == a.variant_id))
    return AssignmentOut(
        experiment_id=a.experiment_id,
        user_id=a.user_id,
        variant_id=a.variant_id,
        variant_key=v.key if v else "unknown",
        assigned_at=a.assigned_at,
    )