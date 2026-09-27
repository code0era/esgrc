"""
Tests for organisation data isolation.

Verifies that users from Organisation A cannot read, modify, or delete
data that belongs to Organisation B - for every domain: ESG, Risk, Compliance.

Every test creates two orgs and confirms that records created under org A
are invisible to org B, and cross-org write/delete attempts return 404
(not 403 - we deliberately do not reveal existence to the caller).
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies.auth import get_current_org, get_current_user
from app.models.models import Organisation, User, UserRole
from main import app


def _make_client(db_session, org: Organisation) -> TestClient:
    """
    Return a TestClient with the given org injected as the current org, plus a
    super_admin user in that org so write endpoints (now role-gated) succeed.
    Cross-org isolation is still enforced by the org-scoped queries, so org B's
    caller cannot reach org A's rows. Caller clears dependency_overrides after use.
    """
    def override_db():
        yield db_session

    def override_org():
        return org

    def override_user():
        return User(
            id=1, email="iso@test", full_name="Iso Tester",
            role=UserRole.SUPER_ADMIN, is_active=True, organisation_id=org.id,
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_org] = override_org
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def orgs(db_session):
    """Create two organisations and yield (org_a, org_b)."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    org_a = Organisation(name=f"Alpha {uid}", slug=f"alpha-{uid}")
    org_b = Organisation(name=f"Beta {uid}",  slug=f"beta-{uid}")
    db_session.add(org_a)
    db_session.add(org_b)
    db_session.flush()
    yield org_a, org_b
    app.dependency_overrides.clear()


# ── ESG isolation ──────────────────────────────────────────────────────────────

def test_esg_category_not_visible_to_other_org(db_session, orgs):
    org_a, org_b = orgs

    ca = _make_client(db_session, org_a)
    r = ca.post("/esg/categories", json={"name": "Carbon", "pillar": "environmental"})
    assert r.status_code == 201
    cat_id = r.json()["id"]

    cb = _make_client(db_session, org_b)
    r_list = cb.get("/esg/categories")
    assert r_list.status_code == 200
    assert cat_id not in [c["id"] for c in r_list.json()]

    r_get = cb.get(f"/esg/categories/{cat_id}")
    assert r_get.status_code == 404


def test_metric_code_reusable_across_orgs(db_session, orgs):
    """The same pipeline metric_code must be usable by every org.

    metric_code was globally unique until migration 20260817_metric_code_per_org:
    every org imports the same fixed set of pipeline codes (e.g. "ESU10102") via
    the standard CSV, so only the first org to ever create a category with a
    given code could use it - every other org's import 409'd on every standard
    code. This is the regression test for that fix; the same-org duplicate
    case is covered separately by test_phase7.py::test_metric_code_unique_within_org.
    """
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    r = ca.post("/esg/categories", json={
        "name": "Carbon Emissions", "pillar": "environmental", "metric_code": "ESU10102",
    })
    assert r.status_code == 201, r.text

    cb = _make_client(db_session, org_b)
    r2 = cb.post("/esg/categories", json={
        "name": "Carbon Emissions", "pillar": "environmental", "metric_code": "ESU10102",
    })
    assert r2.status_code == 201, r2.text


def test_esg_category_update_blocked_cross_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    r = ca.post("/esg/categories", json={"name": "Water", "pillar": "environmental"})
    cat_id = r.json()["id"]

    cb = _make_client(db_session, org_b)
    assert cb.patch(f"/esg/categories/{cat_id}", json={"description": "hacked"}).status_code == 404


def test_esg_category_delete_blocked_cross_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    r = ca.post("/esg/categories", json={"name": "Energy", "pillar": "environmental"})
    cat_id = r.json()["id"]

    cb = _make_client(db_session, org_b)
    assert cb.delete(f"/esg/categories/{cat_id}").status_code == 404


def test_esg_metric_not_visible_to_other_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    r = ca.post("/esg/categories", json={"name": "Scope1", "pillar": "environmental"})
    cat_id = r.json()["id"]
    r2 = ca.post("/esg/metrics", json={
        "category_id": cat_id, "organisation": "AcmeCorp",
        "value": 120.5, "period": "2024-Q1",
    })
    assert r2.status_code == 201
    metric_id = r2.json()["id"]

    cb = _make_client(db_session, org_b)
    r_list = cb.get("/esg/metrics")
    assert metric_id not in [m["id"] for m in r_list.json()]
    assert cb.get(f"/esg/metrics/{metric_id}").status_code == 404


def test_esg_metric_submit_to_other_org_category_blocked(db_session, orgs):
    """Org B cannot submit metrics into Org A's category."""
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    r = ca.post("/esg/categories", json={"name": "Bio", "pillar": "environmental"})
    cat_id = r.json()["id"]

    cb = _make_client(db_session, org_b)
    r = cb.post("/esg/metrics", json={
        "category_id": cat_id, "organisation": "OrgB", "value": 1.0, "period": "2024",
    })
    assert r.status_code == 404


# ── Risk isolation ─────────────────────────────────────────────────────────────

def test_risk_not_visible_to_other_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    r = ca.post("/risks", json={"title": "Supply Chain Risk", "level": "high"})
    assert r.status_code == 201
    risk_id = r.json()["id"]

    cb = _make_client(db_session, org_b)
    assert risk_id not in [x["id"] for x in cb.get("/risks").json()]
    assert cb.get(f"/risks/{risk_id}").status_code == 404


def test_risk_update_blocked_cross_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    risk_id = ca.post("/risks", json={"title": "Flood Risk", "level": "medium"}).json()["id"]

    cb = _make_client(db_session, org_b)
    assert cb.patch(f"/risks/{risk_id}", json={"status": "closed"}).status_code == 404


def test_risk_delete_blocked_cross_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    risk_id = ca.post("/risks", json={"title": "Fire Risk", "level": "critical"}).json()["id"]

    cb = _make_client(db_session, org_b)
    assert cb.delete(f"/risks/{risk_id}").status_code == 404


def test_heatmap_scoped_to_org(db_session, orgs):
    """Heatmap must only count the caller org's risks."""
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    ca.post("/risks", json={"title": "R", "likelihood": 5, "impact": 5})

    cb = _make_client(db_session, org_b)
    r = cb.get("/risks/heatmap")
    high_cell = next(c for c in r.json()["cells"] if c["likelihood"] == 5 and c["impact"] == 5)
    assert high_cell["count"] == 0


# ── Compliance isolation ───────────────────────────────────────────────────────

def test_compliance_framework_not_visible_to_other_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    r = ca.post("/compliance/frameworks", json={"name": "GRI Standards", "version": "2021"})
    assert r.status_code == 201
    fw_id = r.json()["id"]

    cb = _make_client(db_session, org_b)
    assert fw_id not in [f["id"] for f in cb.get("/compliance/frameworks").json()]
    assert cb.get(f"/compliance/frameworks/{fw_id}").status_code == 404


def test_compliance_requirement_blocked_cross_org(db_session, orgs):
    """Org B cannot add requirements to Org A's framework."""
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    fw_id = ca.post("/compliance/frameworks", json={"name": "ISO 14001"}).json()["id"]

    cb = _make_client(db_session, org_b)
    r = cb.post("/compliance/requirements", json={"framework_id": fw_id, "title": "Injected"})
    assert r.status_code == 404


def test_compliance_summary_scoped_to_org(db_session, orgs):
    """Compliance summary must only count the caller org's frameworks."""
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    fw_id = ca.post("/compliance/frameworks", json={"name": "TCFD"}).json()["id"]
    ca.post("/compliance/requirements", json={"framework_id": fw_id, "title": "Governance"})

    cb = _make_client(db_session, org_b)
    r = cb.get("/compliance/summary")
    assert fw_id not in [f["framework_id"] for f in r.json()["frameworks"]]


def test_compliance_framework_summary_cross_org_returns_404(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    fw_id = ca.post("/compliance/frameworks", json={"name": "SOC 2"}).json()["id"]

    cb = _make_client(db_session, org_b)
    assert cb.get(f"/compliance/frameworks/{fw_id}/summary").status_code == 404


def test_compliance_requirement_get_blocked_cross_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    fw_id = ca.post("/compliance/frameworks", json={"name": "ISO 27001"}).json()["id"]
    req_id = ca.post(
        "/compliance/requirements",
        json={"framework_id": fw_id, "title": "Access reviews"},
    ).json()["id"]

    cb = _make_client(db_session, org_b)
    assert cb.get(f"/compliance/requirements/{req_id}").status_code == 404


def test_compliance_requirement_update_blocked_cross_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    fw_id = ca.post("/compliance/frameworks", json={"name": "PCI DSS"}).json()["id"]
    req_id = ca.post(
        "/compliance/requirements",
        json={"framework_id": fw_id, "title": "Encrypt cardholder data"},
    ).json()["id"]

    cb = _make_client(db_session, org_b)
    r = cb.patch(f"/compliance/requirements/{req_id}", json={"status": "compliant"})
    assert r.status_code == 404

    # Org A's own view must be unaffected by the blocked cross-org attempt.
    # _make_client mutates the shared app.dependency_overrides, so re-point it
    # back at org_a before checking - `cb`'s override is still active otherwise.
    ca = _make_client(db_session, org_a)
    still = ca.get(f"/compliance/requirements/{req_id}")
    assert still.json()["status"] == "not_assessed"


def test_compliance_requirement_bulk_update_skips_other_org(db_session, orgs):
    """Bulk update must silently skip requirement IDs from another org rather
    than leaking their existence or applying the write."""
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    fw_id = ca.post("/compliance/frameworks", json={"name": "NIST CSF"}).json()["id"]
    req_id = ca.post(
        "/compliance/requirements",
        json={"framework_id": fw_id, "title": "Identify assets"},
    ).json()["id"]

    cb = _make_client(db_session, org_b)
    r = cb.patch(
        "/compliance/requirements/bulk",
        json=[{"id": req_id, "status": "compliant"}],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 0
    assert body["skipped"] == 1

    # Re-point the shared dependency overrides back at org_a - see the
    # matching comment in test_compliance_requirement_update_blocked_cross_org.
    ca = _make_client(db_session, org_a)
    still = ca.get(f"/compliance/requirements/{req_id}")
    assert still.json()["status"] == "not_assessed"


# ── ESG Scoring benchmark isolation ────────────────────────────────────────────

def test_benchmark_get_blocked_cross_org(db_session, orgs):
    """A benchmark has no org_id of its own - it must be tenant-scoped purely
    via its category, exercised here through GET /esg/benchmarks/{id}."""
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    cat_id = ca.post(
        "/esg/categories", json={"name": "Emissions", "pillar": "environmental"}
    ).json()["id"]
    bench_id = ca.post(
        "/esg/benchmarks",
        json={"category_id": cat_id, "target_value": 0.0, "baseline_value": 100.0},
    ).json()["id"]

    cb = _make_client(db_session, org_b)
    assert cb.get(f"/esg/benchmarks/{bench_id}").status_code == 404
    assert cb.get(f"/esg/categories/{cat_id}/benchmark").status_code == 404


def test_benchmark_update_blocked_cross_org(db_session, orgs):
    org_a, org_b = orgs
    ca = _make_client(db_session, org_a)
    cat_id = ca.post(
        "/esg/categories", json={"name": "Water Use", "pillar": "environmental"}
    ).json()["id"]
    bench_id = ca.post(
        "/esg/benchmarks",
        json={"category_id": cat_id, "target_value": 0.0, "baseline_value": 50.0},
    ).json()["id"]

    cb = _make_client(db_session, org_b)
    r = cb.patch(f"/esg/benchmarks/{bench_id}", json={"target_value": 999.0})
    assert r.status_code == 404

    # Org A's benchmark must be unchanged by the blocked cross-org attempt.
    # Re-point the shared dependency overrides back at org_a - see the
    # matching comment in test_compliance_requirement_update_blocked_cross_org.
    ca = _make_client(db_session, org_a)
    still = ca.get(f"/esg/benchmarks/{bench_id}")
    assert still.json()["target_value"] == 0.0


# ── Same-org data is fully accessible ─────────────────────────────────────────

def test_same_org_data_fully_accessible(db_session, orgs):
    """Sanity check: Org A can read its own data."""
    org_a, _ = orgs
    ca = _make_client(db_session, org_a)

    r1 = ca.post("/esg/categories", json={"name": "Renewables", "pillar": "environmental"})
    assert r1.status_code == 201
    cat_id = r1.json()["id"]
    assert ca.get(f"/esg/categories/{cat_id}").status_code == 200

    r3 = ca.post("/risks", json={"title": "My Risk"})
    assert r3.status_code == 201
    assert any(x["id"] == r3.json()["id"] for x in ca.get("/risks").json())

    r5 = ca.post("/compliance/frameworks", json={"name": "My Framework"})
    assert r5.status_code == 201
    assert any(f["id"] == r5.json()["id"] for f in ca.get("/compliance/frameworks").json())
