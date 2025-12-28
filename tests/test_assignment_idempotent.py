from fastapi.testclient import TestClient
from app.main import app

def _auth_headers() -> dict:
    return {"Authorization": "Bearer dev-token-1"}

def test_assignment_is_idempotent():
    client = TestClient(app)

    # Create experiment
    payload = {
        "name": "Idempotent Assign",
        "description": "test",
        "variants": [
            {"key": "control", "allocation_percent": 50, "metadata": {}},
            {"key": "treatment", "allocation_percent": 50, "metadata": {}},
        ],
    }
    r = client.post("/experiments", json=payload, headers=_auth_headers())
    assert r.status_code in (200, 201), r.text
    exp_id = r.json()["id"]

    # First assignment
    r1 = client.get(f"/experiments/{exp_id}/assignment/user123", headers=_auth_headers())
    assert r1.status_code == 200, r1.text
    a1 = r1.json()

    # Second assignment should match exactly (idempotent)
    r2 = client.get(f"/experiments/{exp_id}/assignment/user123", headers=_auth_headers())
    assert r2.status_code == 200, r2.text
    a2 = r2.json()

    assert a1["experiment_id"] == exp_id
    assert a2["experiment_id"] == exp_id
    assert a1["user_id"] == "user123"
    assert a2["user_id"] == "user123"

    # The essential idempotency guarantees
    assert a1["variant_id"] == a2["variant_id"]
    assert a1["variant_key"] == a2["variant_key"]
    assert a1["assigned_at"] == a2["assigned_at"]
