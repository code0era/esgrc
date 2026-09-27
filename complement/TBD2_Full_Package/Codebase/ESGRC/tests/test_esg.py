"""Tests for ESG categories and metrics endpoints."""

def test_create_category(client):
    r = client.post("/esg/categories", json={"name": "Carbon Emissions", "pillar": "environmental", "unit": "tonnes CO2"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Carbon Emissions"
    assert data["pillar"] == "environmental"
    assert "updated_at" in data

def test_duplicate_category_returns_409(client):
    client.post("/esg/categories", json={"name": "Water", "pillar": "environmental"})
    r = client.post("/esg/categories", json={"name": "Water", "pillar": "social"})
    assert r.status_code == 409

def test_invalid_period_returns_422(client):
    client.post("/esg/categories", json={"name": "Cat1", "pillar": "social"})
    r = client.post("/esg/metrics", json={"category_id": 1, "organisation": "X", "value": 1.0, "period": "INVALID"})
    assert r.status_code == 422

def test_valid_period_formats(client):
    r = client.post("/esg/categories", json={"name": "Energy", "pillar": "environmental"})
    cid = r.json()["id"]
    for period in ["2024", "2024-Q1", "2024-Q4"]:
        r = client.post("/esg/metrics", json={"category_id": cid, "organisation": "Acme", "value": 1.0, "period": period})
        assert r.status_code == 201, f"Period {period} should be valid"

def test_cascade_delete(client):
    r = client.post("/esg/categories", json={"name": "Waste", "pillar": "environmental"})
    cid = r.json()["id"]
    r2 = client.post("/esg/metrics", json={"category_id": cid, "organisation": "X", "value": 5.0, "period": "2024-Q2"})
    mid = r2.json()["id"]
    client.delete(f"/esg/categories/{cid}")
    assert client.get(f"/esg/metrics/{mid}").status_code == 404

def test_patch_null_clears_field(client):
    r = client.post("/esg/categories", json={"name": "Biodiversity", "pillar": "environmental", "unit": "hectares"})
    cid = r.json()["id"]
    r2 = client.patch(f"/esg/categories/{cid}", json={"unit": None})
    assert r2.json()["unit"] is None
