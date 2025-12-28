from fastapi.testclient import TestClient
from app.main import app

def _auth_headers() -> dict:
    return {"Authorization": "Bearer dev-token-1"}

def test_stop_experiment_freezes_new_assignments():
    client = TestClient(app)

    # Create experiment
    payload = {
        "name": "Stop Freeze",
        "description": "test",
        "variants": [
            {"key": "control", "allocation_percent": 50, "metadata": {}},
            {"key": "treatment", "allocation_percent": 50, "metadata": {}},
        ],
    }
    r = client.post("/experiments", json=payload, headers=_auth_headers())
    assert r.status_code in (200, 201), r.text
    exp_id = r.json()["id"]

    # Existing user gets assignment
    r1 = client.get(f"/experiments/{exp_id}/assignment/userA", headers=_auth_headers())
    assert r1.status_code == 200, r1.text
    a1 = r1.json()

    # Stop the experiment
    rstop = client.patch(
        f"/experiments/{exp_id}/status",
        json={"status": "stopped"},
        headers=_auth_headers(),
    )
    assert rstop.status_code in (200, 204), rstop.text

    # Existing user should still be idempotent
    r2 = client.get(f"/experiments/{exp_id}/assignment/userA", headers=_auth_headers())
    assert r2.status_code == 200, r2.text
    a2 = r2.json()
    assert a1["variant_id"] == a2["variant_id"]
    assert a1["assigned_at"] == a2["assigned_at"]

    # New user should NOT receive an assignment
    r3 = client.get(f"/experiments/{exp_id}/assignment/userNEW", headers=_auth_headers())

    # Choose one expected behavior and enforce it:
    # - 409 Conflict is a great choice for "can't assign because experiment stopped"
    # - 400 is acceptable too, but less semantically crisp
    assert r3.status_code in (409, 400), r3.text
