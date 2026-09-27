"""Tests for risk register endpoints."""

def test_create_risk(client):
    r = client.post("/risks", json={"title": "Climate Risk", "level": "high", "likelihood": 4, "impact": 5})
    assert r.status_code == 201
    data = r.json()
    assert data["risk_score"] == 20
    assert data["status"] == "open"
    assert "updated_at" in data

def test_likelihood_zero_rejected(client):
    r = client.post("/risks", json={"title": "Bad", "likelihood": 0, "impact": 3})
    assert r.status_code == 422

def test_invalid_status_enum_rejected(client):
    assert client.get("/risks?status=banana").status_code == 422

def test_patch_null_clears_mitigation_plan(client):
    r = client.post("/risks", json={"title": "R1", "mitigation_plan": "Some plan"})
    rid = r.json()["id"]
    r2 = client.patch(f"/risks/{rid}", json={"mitigation_plan": None})
    assert r2.json()["mitigation_plan"] is None

def test_delete_risk(client):
    r = client.post("/risks", json={"title": "Temp"})
    rid = r.json()["id"]
    assert client.delete(f"/risks/{rid}").status_code == 204
    assert client.get(f"/risks/{rid}").status_code == 404
