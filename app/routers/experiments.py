from __future__ import annotations

from uuid import UUID
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.db import get_db
from app.models import Experiment, Variant, Assignment
from app.schemas import ExperimentCreate, ExperimentOut, AssignmentOut, ExperimentResultsOut, ExperimentStatusUpdate
from app.services.assignment import get_or_create_assignment
from app.services.assignment_cache import get_cached, set_cached, invalidate_experiment, CachedAssignment
from app.services.results import ResultsQuery, get_experiment_results

router = APIRouter(
    prefix="/experiments",
    tags=["Experiments", "A/B Testing"],
    responses={404: {"description": "Not found"}},
)


@router.post(
    "",
    response_model=ExperimentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new experiment",
    description="""
    Create a new A/B test experiment with the specified variants and traffic allocations.
    
    - Creates experiment record in the database
    - Sets up variants with their respective traffic allocations
    - Initial experiment status is set to 'running'
    - Returns the created experiment with its variants
    """
)
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


@router.get(
    "/{experiment_id}",
    response_model=ExperimentOut,
    summary="Get experiment details",
    description="""
    Retrieve detailed information about a specific experiment.
    
    - Returns experiment metadata including name, description, and status
    - Includes list of variants with their traffic allocations
    - Returns 404 if experiment is not found
    """
)
def get_experiment(experiment_id: UUID, db: Session = Depends(get_db)) -> Experiment:
    exp = db.scalar(
        select(Experiment)
        .where(Experiment.id == experiment_id)
        .options(selectinload(Experiment.variants))
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


@router.get(
    "/{experiment_id}/assignment/{user_id}",
    response_model=Dict[str, Any],
    summary="Get or create user assignment",
    description="""
    Get or create a user's variant assignment for an experiment.
    
    - Returns cached assignment if available (fast path)
    - Creates new assignment if user doesn't have one
    - Enforces experiment status (no new assignments for stopped experiments)
    - Returns assignment details including variant information
    - Includes cache_hit flag to indicate if response was served from cache
    """
)
def get_assignment(experiment_id: UUID, user_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    # Check cache first
    cached = get_cached(experiment_id, user_id)
    if cached:
        return {
            "experiment_id": str(cached.experiment_id),
            "user_id": cached.user_id,
            "variant_id": str(cached.variant_id),
            "variant_key": cached.variant_key,
            "assigned_at": cached.assigned_at,
            "cache_hit": True,
        }

    # 1) Check existing assignment first (idempotent)
    existing = db.scalar(
        select(Assignment).where(
            Assignment.experiment_id == experiment_id,
            Assignment.user_id == user_id,
        )
    )
    if existing:
        v = db.scalar(select(Variant).where(Variant.id == existing.variant_id))
        variant_key = v.key if v else "unknown"
        
        # Cache the existing assignment
        set_cached(
            CachedAssignment(
                experiment_id=existing.experiment_id,
                user_id=existing.user_id,
                variant_id=existing.variant_id,
                variant_key=variant_key,
                assigned_at=existing.assigned_at,
            )
        )
        
        return {
            "experiment_id": str(existing.experiment_id),
            "user_id": existing.user_id,
            "variant_id": str(existing.variant_id),
            "variant_key": variant_key,
            "assigned_at": existing.assigned_at,
            "cache_hit": False,
        }

    # 2) If no existing assignment, check experiment status
    exp = db.scalar(select(Experiment).where(Experiment.id == experiment_id))
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    if exp.status != "running":
        raise HTTPException(
            status_code=409,
            detail=f"Experiment is {exp.status}; no new assignments allowed",
        )

    # 3) Create new assignment
    a = get_or_create_assignment(db, experiment_id=experiment_id, user_id=user_id)

    # fetch variant key
    v = db.scalar(select(Variant).where(Variant.id == a.variant_id))
    variant_key = v.key if v else "unknown"
    
    # Cache the new assignment
    set_cached(
        CachedAssignment(
            experiment_id=a.experiment_id,
            user_id=a.user_id,
            variant_id=a.variant_id,
            variant_key=variant_key,
            assigned_at=a.assigned_at,
        )
    )
    
    return {
        "experiment_id": str(a.experiment_id),
        "user_id": a.user_id,
        "variant_id": str(a.variant_id),
        "variant_key": variant_key,
        "assigned_at": a.assigned_at,
        "cache_hit": False,
    }


@router.patch(
    "/{experiment_id}/status",
    response_model=ExperimentOut,
    summary="Update experiment status",
    description="""
    Update the status of an experiment (e.g., 'running' to 'stopped').
    
    - Valid status transitions are enforced
    - Automatically invalidates cache when stopping an experiment
    - Returns the updated experiment
    - Returns 404 if experiment is not found
    - Returns 400 for invalid status transitions
    """
)
def update_experiment_status(
    experiment_id: UUID,
    status_update: ExperimentStatusUpdate,
    db: Session = Depends(get_db)
) -> Experiment:
    # Get the experiment
    exp = db.scalar(select(Experiment).where(Experiment.id == experiment_id))
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    # Update status
    old_status = exp.status
    exp.status = status_update.status
    
    # Invalidate cache if experiment is being stopped
    if old_status == "running" and status_update.status == "stopped":
        invalidate_experiment(experiment_id)
    
    try:
        db.commit()
        db.refresh(exp)
        return exp
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to update experiment status: {str(e)}")


@router.get(
    "/{experiment_id}/results",
    response_model=ExperimentResultsOut,
    summary="Get experiment results",
    description="""
    Retrieve aggregated metrics and statistical analysis for an experiment.
    
    - Supports filtering by event type and time range
    - Group results by variant, day, or hour
    - Choose between unique users or event count attribution
    - Optionally specify a control variant for comparison
    - Returns statistical significance calculations
    - Only includes events that occurred after user assignment
    """
)
def experiment_results(
    experiment_id: UUID,
    event_type: Optional[str] = Query(
        default=None,
        description="Filter results by specific event type"
    ),
    start: Optional[datetime] = Query(
        default=None,
        description="Start of time range for results (inclusive)"
    ),
    end: Optional[datetime] = Query(
        default=None,
        description="End of time range for results (inclusive)"
    ),
    group_by: str = Query(
        default="variant",
        pattern="^(variant|day|hour)$",
        description="Group results by variant, day, or hour"
    ),
    attribution: str = Query(
        default="unique_users",
        pattern="^(unique_users|event_count)$",
        description="Attribution model: count unique users or total events"
    ),
    control_key: Optional[str] = Query(
        default=None,
        description="Variant key to use as control for lift calculations"
    ),
    db: Session = Depends(get_db),
):
    try:
        q = ResultsQuery(
            start=start,
            end=end,
            event_type=event_type,
            group_by=group_by,
            attribution=attribution,
            control_key=control_key,
        )
        return get_experiment_results(db=db, experiment_id=experiment_id, q=q)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))