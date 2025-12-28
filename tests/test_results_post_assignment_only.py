from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app


def _auth_headers() -> dict:
    return {"Authorization": "Bearer dev-token-1"}


def test_results_only_count_events_after_assignment():
    client = TestClient(app)

    # Create experiment
    payload = {
        "name": "Post Assignment Only",
        "description": "test",
        "variants": [
            {"key": "control", "allocation_percent": 100, "metadata": {}},
        ],
    }
    r = client.post("/experiments", json=payload, headers=_auth_headers())
    assert r.status_code in (200, 201), r.text
    exp_id = r.json()["id"]

    user_id = "user_time"

    # Assign user first (required by your API before posting events)
    ra = client.get(f"/experiments/{exp_id}/assignment/{user_id}", headers=_auth_headers())
    assert ra.status_code == 200, ra.text
    assigned_at = datetime.fromisoformat(ra.json()["assigned_at"].replace("Z", "+00:00"))

    # Create an event with timestamp BEFORE assignment timestamp (user is assigned, so API should accept)
    t_before = assigned_at - timedelta(seconds=10)
    ev_before = {
        "experiment_id": exp_id,
        "user_id": user_id,
        "type": "click",
        "timestamp": t_before.isoformat(),
        "properties": {"when": "before_assigned_at"},
    }
    r0 = client.post("/events", json=ev_before, headers=_auth_headers())
    assert r0.status_code in (200, 201), r0.text

    # Create an event AFTER assignment
    t_after = assigned_at + timedelta(seconds=10)
    ev_after = {
        "experiment_id": exp_id,
        "user_id": user_id,
        "type": "click",
        "timestamp": t_after.isoformat(),
        "properties": {"when": "after_assigned_at"},
    }
    r1 = client.post("/events", json=ev_after, headers=_auth_headers())
    assert r1.status_code in (200, 201), r1.text

    # Fetch results filtered to click
    rr = client.get(f"/experiments/{exp_id}/results?event_type=click", headers=_auth_headers())
    assert rr.status_code == 200, rr.text
    data = rr.json()

    overall = data["totals"]["__overall__"]

    # Only the post-assignment event should be counted (results logic enforces timestamp >= assigned_at)
    assert overall["events"] == 1
    assert overall["unique_users"] == 1
    assert overall["conversions"] == 1
