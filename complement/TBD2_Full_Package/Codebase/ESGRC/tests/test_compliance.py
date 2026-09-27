"""Tests for compliance framework and requirement endpoints."""

def test_create_framework(client):
    r = client.post("/compliance/frameworks", json={"name": "GRI Standards", "version": "2021"})
    assert r.status_code == 201
    assert "updated_at" in r.json()

def test_duplicate_framework_returns_409(client):
    client.post("/compliance/frameworks", json={"name": "ISO 14001"})
    r = client.post("/compliance/frameworks", json={"name": "ISO 14001"})
    assert r.status_code == 409

def test_requirement_default_status(client):
    r = client.post("/compliance/frameworks", json={"name": "TCFD"})
    fid = r.json()["id"]
    r2 = client.post("/compliance/requirements", json={"framework_id": fid, "title": "Governance"})
    assert r2.json()["status"] == "not_assessed"

def test_cascade_delete_framework(client):
    r = client.post("/compliance/frameworks", json={"name": "SOC2"})
    fid = r.json()["id"]
    r2 = client.post("/compliance/requirements", json={"framework_id": fid, "title": "Access control"})
    rid = r2.json()["id"]
    client.delete(f"/compliance/frameworks/{fid}")
    assert client.get(f"/compliance/requirements/{rid}").status_code == 404

def test_patch_null_evidence_clears_it(client):
    r = client.post("/compliance/frameworks", json={"name": "GRI2"})
    fid = r.json()["id"]
    r2 = client.post("/compliance/requirements", json={"framework_id": fid, "title": "Req1"})
    rid = r2.json()["id"]
    client.patch(f"/compliance/requirements/{rid}", json={"evidence": "Audit doc"})
    r3 = client.patch(f"/compliance/requirements/{rid}", json={"evidence": None})
    assert r3.json()["evidence"] is None
