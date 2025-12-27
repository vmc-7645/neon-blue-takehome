from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Assignment, Event, Experiment
from app.schemas import EventCreate, EventOut

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def record_event(payload: EventCreate, db: Session = Depends(get_db)) -> Event:
    # Ensure experiment exists
    exp_id = db.scalar(select(Experiment.id).where(Experiment.id == payload.experiment_id))
    if not exp_id:
        raise HTTPException(status_code=404, detail="Experiment not found")

    # Enforce that the user must have been assigned (otherwise results rule is ambiguous)
    a = db.scalar(
        select(Assignment).where(
            Assignment.experiment_id == payload.experiment_id,
            Assignment.user_id == payload.user_id,
        )
    )
    if not a:
        raise HTTPException(status_code=409, detail="User has no assignment for this experiment yet")

    ev = Event(
        experiment_id=payload.experiment_id,
        user_id=payload.user_id,
        type=payload.type,
        timestamp=payload.timestamp,
        properties=payload.properties,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev
