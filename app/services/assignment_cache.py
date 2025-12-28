from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from uuid import UUID

@dataclass(frozen=True)
class CachedAssignment:
    experiment_id: UUID
    user_id: str
    variant_id: UUID
    variant_key: str
    assigned_at: datetime

_TTL = timedelta(minutes=5)
_cache: Dict[Tuple[UUID, str], Tuple[CachedAssignment, datetime]] = {}

def get_cached(experiment_id: UUID, user_id: str) -> Optional[CachedAssignment]:
    key = (experiment_id, user_id)
    item = _cache.get(key)
    if not item:
        return None
    value, expires_at = item
    now = datetime.now(timezone.utc)
    if now >= expires_at:
        _cache.pop(key, None)
        return None
    return value

def set_cached(value: CachedAssignment) -> None:
    key = (value.experiment_id, value.user_id)
    expires_at = datetime.now(timezone.utc) + _TTL
    _cache[key] = (value, expires_at)

def invalidate_experiment(experiment_id: UUID) -> None:
    keys = [k for k in _cache.keys() if k[0] == experiment_id]
    for k in keys:
        _cache.pop(k, None)
