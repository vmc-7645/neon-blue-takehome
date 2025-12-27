from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Assignment, Event, Experiment, Variant


@dataclass(frozen=True)
class ResultsQuery:
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    event_type: Optional[str] = None


def _ensure_tz(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_experiment_results(
    db: Session,
    experiment_id: UUID,
    q: Optional[ResultsQuery] = None,
    *,
    # Support router calling style: get_experiment_results(..., event_type=..., start=..., end=...)
    event_type: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict:
    """
    Flexible results entrypoint.
    Accepts either:
      - q=ResultsQuery(...)
      - event_type/start/end keyword args
    """

    if q is None:
        q = ResultsQuery(start=start, end=end, event_type=event_type)

    # experiment exists
    exp_id = db.scalar(select(Experiment.id).where(Experiment.id == experiment_id))
    if not exp_id:
        raise ValueError("Experiment not found")

    q_start = _ensure_tz(q.start)
    q_end = _ensure_tz(q.end)

    variants = db.scalars(
        select(Variant).where(Variant.experiment_id == experiment_id).order_by(Variant.key.asc())
    ).all()

    # denominator: assignments per variant
    assignments_rows = db.execute(
        select(Assignment.variant_id, func.count().label("assignments"))
        .where(Assignment.experiment_id == experiment_id)
        .group_by(Assignment.variant_id)
    ).all()
    assignments_by_variant: Dict[UUID, int] = {r.variant_id: int(r.assignments) for r in assignments_rows}

    # join events to assignments, enforce "after assignment"
    join_cond = and_(
        Event.experiment_id == Assignment.experiment_id,
        Event.user_id == Assignment.user_id,
        Event.timestamp >= Assignment.assigned_at,
    )

    event_filters = [Event.experiment_id == experiment_id]
    if q.event_type:
        event_filters.append(Event.type == q.event_type)
    if q_start:
        event_filters.append(Event.timestamp >= q_start)
    if q_end:
        event_filters.append(Event.timestamp < q_end)

    rows = db.execute(
        select(
            Assignment.variant_id.label("variant_id"),
            func.count(Event.id).label("events"),
            func.count(func.distinct(Event.user_id)).label("unique_users"),
        )
        .select_from(Assignment)
        .join(Event, join_cond)
        .where(Assignment.experiment_id == experiment_id)
        .where(*event_filters)
        .group_by(Assignment.variant_id)
    ).all()

    events_by_variant: Dict[UUID, int] = {r.variant_id: int(r.events) for r in rows}
    unique_users_by_variant: Dict[UUID, int] = {r.variant_id: int(r.unique_users) for r in rows}

    totals: Dict[str, dict] = {}
    for v in variants:
        assignments = int(assignments_by_variant.get(v.id, 0))
        events = int(events_by_variant.get(v.id, 0))
        unique_users = int(unique_users_by_variant.get(v.id, 0))
        conversions = int(unique_users)  # simple definition for take-home
        rate = float(conversions / assignments) if assignments > 0 else 0.0

        totals[v.key] = {
            "variant_id": v.id,
            "variant_key": v.key,
            "assignments": assignments,
            "events": events,
            "unique_users": unique_users,
            "conversions": conversions,
            "conversion_rate": rate,
        }

    overall_assignments = sum(x["assignments"] for x in totals.values())
    overall_events = sum(x["events"] for x in totals.values())
    overall_unique_users = sum(x["unique_users"] for x in totals.values())
    overall_conversions = sum(x["conversions"] for x in totals.values())
    overall_rate = float(overall_conversions / overall_assignments) if overall_assignments > 0 else 0.0

    totals["__overall__"] = {
        "variant_id": variants[0].id if variants else UUID(int=0),
        "variant_key": "__overall__",
        "assignments": int(overall_assignments),
        "events": int(overall_events),
        "unique_users": int(overall_unique_users),
        "conversions": int(overall_conversions),
        "conversion_rate": overall_rate,
    }

    return {
        "experiment_id": experiment_id,
        "generated_at": datetime.now(timezone.utc),
        "query": {
            "start": q.start,
            "end": q.end,
            "event_type": q.event_type,
            "group_by": "variant",
            "metric": "conversions",
        },
        "totals": totals,
        "time_series": None,
        "diagnostics": {"variants": [v.key for v in variants]},
        "definitions": {
            "assignments": "Count of users assigned to the variant.",
            "events": "Count of matching events that occurred after assignment time.",
            "unique_users": "Distinct users with >=1 matching event after assignment.",
            "conversions": "Currently defined as unique_users.",
            "conversion_rate": "conversions / assignments.",
        },
    }


# Backward compatible alias if some code imports get_results
def get_results(db: Session, experiment_id: UUID, q: ResultsQuery) -> dict:
    return get_experiment_results(db, experiment_id, q=q)
