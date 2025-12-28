from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Tuple
from uuid import UUID
import math

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.models import Assignment, Event, Experiment, Variant


@dataclass(frozen=True)
class ResultsQuery:
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    event_type: Optional[str] = None
    group_by: str = "variant"  # variant|day|hour
    attribution: str = "unique_users"  # unique_users|event_count
    control_key: Optional[str] = None


def _ensure_tz(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _norm_cdf(x: float) -> float:
    # Normal CDF via error function, no scipy dependency
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _two_proportion_ztest(success_a: int, n_a: int, success_b: int, n_b: int) -> Tuple[Optional[float], Optional[float]]:
    """
    Two-sided two-proportion z-test.
    Returns (z, p_value). If invalid, returns (None, None).
    """
    if n_a <= 0 or n_b <= 0:
        return (None, None)

    p_pool = (success_a + success_b) / (n_a + n_b)
    denom = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n_a + 1.0 / n_b))
    if denom == 0.0:
        return (None, None)

    p_a = success_a / n_a
    p_b = success_b / n_b
    z = (p_b - p_a) / denom
    p = 2.0 * (1.0 - _norm_cdf(abs(z)))
    return (float(z), float(p))


def get_experiment_results(
    db: Session,
    experiment_id: UUID,
    q: Optional[ResultsQuery] = None,
    *,
    # compatibility with older calling style
    event_type: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict:
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

    variant_by_id: Dict[UUID, Variant] = {v.id: v for v in variants}
    variant_id_by_key: Dict[str, UUID] = {v.key: v.id for v in variants}

    # Determine control key
    if q.control_key and q.control_key in variant_id_by_key:
        control_key = q.control_key
    else:
        control_key = variants[0].key if variants else None

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

    # Attribution choice
    # - unique_users: count distinct users with >=1 event
    # - event_count: count total events
    if q.attribution == "event_count":
        conversions_expr = func.count(Event.id)
        conversions_label = "events"
    else:
        conversions_expr = func.count(func.distinct(Event.user_id))
        conversions_label = "unique_users"

    # Totals by variant
    rows = db.execute(
        select(
            Assignment.variant_id.label("variant_id"),
            func.count(Event.id).label("events"),
            func.count(func.distinct(Event.user_id)).label("unique_users"),
            conversions_expr.label("conversions"),
        )
        .select_from(Assignment)
        .join(Event, join_cond)
        .where(Assignment.experiment_id == experiment_id)
        .where(*event_filters)
        .group_by(Assignment.variant_id)
    ).all()

    events_by_variant: Dict[UUID, int] = {r.variant_id: int(r.events) for r in rows}
    unique_users_by_variant: Dict[UUID, int] = {r.variant_id: int(r.unique_users) for r in rows}
    conversions_by_variant: Dict[UUID, int] = {r.variant_id: int(r.conversions) for r in rows}

    totals: Dict[str, dict] = {}
    for v in variants:
        assignments = int(assignments_by_variant.get(v.id, 0))
        events = int(events_by_variant.get(v.id, 0))
        unique_users = int(unique_users_by_variant.get(v.id, 0))
        conversions = int(conversions_by_variant.get(v.id, 0))
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

    # overall
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

    # Exec summary: lift + significance vs control
    exec_summary: Dict[str, Any] = {}
    if control_key and control_key in totals:
        control = totals[control_key]
        c_conv = int(control["conversions"])
        c_n = int(control["assignments"])
        c_rate = float(control["conversion_rate"])

        for key, row in totals.items():
            if key in ("__overall__", control_key):
                continue

            t_conv = int(row["conversions"])
            t_n = int(row["assignments"])
            t_rate = float(row["conversion_rate"])

            abs_lift = t_rate - c_rate
            rel_lift = (t_rate / c_rate - 1.0) if c_rate > 0 else None

            z, p = _two_proportion_ztest(c_conv, c_n, t_conv, t_n)

            exec_summary[key] = {
                "control_key": control_key,
                "absolute_lift": float(abs_lift),
                "relative_lift": float(rel_lift) if rel_lift is not None else None,
                "z_score": z,
                "p_value": p,
                "significant_0_05": (p is not None and p < 0.05),
            }

    # Optional time series
    time_series = None
    if q.group_by in ("day", "hour"):
        # date_trunc buckets in Postgres
        bucket = q.group_by
        bucket_col = func.date_trunc(bucket, Event.timestamp).label("bucket_start")

        ts_rows = db.execute(
            select(
                bucket_col,
                Assignment.variant_id.label("variant_id"),
                func.count(Event.id).label("events"),
                func.count(func.distinct(Event.user_id)).label("unique_users"),
                conversions_expr.label("conversions"),
            )
            .select_from(Assignment)
            .join(Event, join_cond)
            .where(Assignment.experiment_id == experiment_id)
            .where(*event_filters)
            .group_by(bucket_col, Assignment.variant_id)
            .order_by(bucket_col.asc())
        ).all()

        # shape: list of buckets with per-variant metrics
        buckets: Dict[datetime, Dict[str, Any]] = {}
        for r in ts_rows:
            b: datetime = r.bucket_start
            v_id: UUID = r.variant_id
            v_key = variant_by_id[v_id].key if v_id in variant_by_id else str(v_id)

            bucket_obj = buckets.setdefault(
                b,
                {
                    "bucket_start": b,
                    "group_by": bucket,
                    "totals": {},
                },
            )

            # use assignments from global denominators (simple for take-home)
            assignments = int(assignments_by_variant.get(v_id, 0))
            conversions = int(r.conversions)
            rate = float(conversions / assignments) if assignments > 0 else 0.0

            bucket_obj["totals"][v_key] = {
                "variant_id": v_id,
                "variant_key": v_key,
                "assignments": assignments,
                "events": int(r.events),
                "unique_users": int(r.unique_users),
                "conversions": conversions,
                "conversion_rate": rate,
            }

        time_series = list(buckets.values())

    return {
        "experiment_id": experiment_id,
        "generated_at": datetime.now(timezone.utc),
        "query": {
            "start": q.start,
            "end": q.end,
            "event_type": q.event_type,
            "group_by": q.group_by,
            "metric": "conversions",
            "attribution": q.attribution,
            "control_key": control_key,
        },
        "totals": totals,
        "exec_summary": exec_summary,
        "time_series": time_series,
        "diagnostics": {"variants": [v.key for v in variants]},
        "definitions": {
            "assignments": "Count of users assigned to the variant.",
            "events": "Count of matching events that occurred after assignment time.",
            "unique_users": "Distinct users with >=1 matching event after assignment.",
            "conversions": f"Defined by attribution={q.attribution} (unique_users or event_count).",
            "conversion_rate": "conversions / assignments.",
            "absolute_lift": "treatment_rate - control_rate.",
            "relative_lift": "(treatment_rate / control_rate) - 1, if control_rate > 0.",
            "p_value": "Two-sided two-proportion z-test p-value (simplified).",
        },
    }


def get_results(db: Session, experiment_id: UUID, q: ResultsQuery) -> dict:
    return get_experiment_results(db, experiment_id, q=q)
