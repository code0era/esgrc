"""
Phase 7 tests - bulk import, CSV export, org snapshot, and LLM output format.

Covers:
  POST /esg/import         - bulk metric import
  GET  /esg/export         - CSV export (pipeline-compatible format)
  GET  /org/snapshot       - org dashboard snapshot
  prompts.py               - Golden Response JSON structure alignment
  llm_agent.py             - write_findings stores structured JSON
"""

import csv
import io
import json
import uuid

import pytest


def _unique_code(prefix: str = "TST") -> str:
    """Generate a globally unique metric code for test isolation."""
    return f"{prefix}{str(uuid.uuid4().int)[:5]}"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def category_with_code(client):
    """ESG category with a unique metric_code - required for bulk import."""
    code = _unique_code("ESU")
    r = client.post("/esg/categories", json={
        "name": f"Carbon Emissions {code}",
        "pillar": "environmental",
        "unit": "tonnes CO2",
        "metric_code": code,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    data["_code"] = code   # expose generated code to tests
    return data


@pytest.fixture
def category_no_code(client):
    """ESG category WITHOUT a metric_code - for testing skip logic."""
    r = client.post("/esg/categories", json={
        "name": "Energy Use No Code",
        "pillar": "environmental",
    })
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def two_coded_categories(client):
    """Two categories each with distinct unique metric codes."""
    cats = []
    codes = [_unique_code("ESU"), _unique_code("SSU")]
    names = ["Water Usage", "Employee Safety"]
    pillars = ["environmental", "social"]
    for code, name, pillar in zip(codes, names, pillars):
        r = client.post("/esg/categories", json={
            "name": f"{name} {code}", "pillar": pillar, "metric_code": code
        })
        assert r.status_code == 201, r.text
        data = r.json()
        data["_code"] = code
        cats.append(data)
    return cats


# ─── metric_code on ESGCategory ───────────────────────────────────────────────

class TestMetricCode:
    def test_create_category_with_metric_code(self, client):
        code = _unique_code("ESU")
        r = client.post("/esg/categories", json={
            "name": f"Test With Code {code}",
            "pillar": "environmental",
            "metric_code": code,
        })
        assert r.status_code == 201
        assert r.json()["metric_code"] == code

    def test_create_category_without_metric_code(self, client):
        r = client.post("/esg/categories", json={
            "name": "Test Without Code",
            "pillar": "social",
        })
        assert r.status_code == 201
        assert r.json()["metric_code"] is None

    def test_metric_code_returned_in_get(self, client, category_with_code):
        cat_id = category_with_code["id"]
        r = client.get(f"/esg/categories/{cat_id}")
        assert r.status_code == 200
        assert r.json()["metric_code"] == category_with_code["_code"]

    def test_metric_code_unique_within_org(self, client, category_with_code):
        """Same metric_code in the same org should be rejected.

        metric_code is unique per (org_id, metric_code), not globally - see
        test_org_isolation.py::test_metric_code_reusable_across_orgs for the
        cross-org half of this contract.
        """
        r = client.post("/esg/categories", json={
            "name": "Duplicate Code Category",
            "pillar": "environmental",
            "metric_code": category_with_code["_code"],   # already used
        })
        assert r.status_code == 409

    def test_update_category_with_metric_code(self, client):
        r = client.post("/esg/categories", json={
            "name": "Updatable Cat",
            "pillar": "governance",
        })
        cat_id = r.json()["id"]
        new_code = _unique_code("GRC")
        r2 = client.patch(f"/esg/categories/{cat_id}", json={"metric_code": new_code})
        assert r2.status_code == 200
        assert r2.json()["metric_code"] == new_code


# ─── Bulk Import ──────────────────────────────────────────────────────────────

class TestBulkImport:
    def test_import_single_row(self, client, category_with_code):
        r = client.post("/esg/import", json=[{
            "metric_code": category_with_code["_code"],
            "value": 342.5,
            "period": "2024-Q1",
            "organisation": "Acme Corp",
        }])
        assert r.status_code == 200
        data = r.json()
        assert data["imported"] == 1
        assert data["skipped"] == 0
        assert data["errors"] == []

    def test_import_multiple_rows(self, client, two_coded_categories):
        r = client.post("/esg/import", json=[
            {"metric_code": two_coded_categories[0]["_code"], "value": 1500.0, "period": "2024-Q1", "organisation": "Corp A"},
            {"metric_code": two_coded_categories[1]["_code"], "value": 0.02, "period": "2024-Q1", "organisation": "Corp A"},
        ])
        assert r.status_code == 200
        data = r.json()
        assert data["imported"] == 2
        assert data["skipped"] == 0

    def test_import_unknown_metric_code_is_skipped(self, client):
        r = client.post("/esg/import", json=[{
            "metric_code": "UNKNOWN99",
            "value": 100.0,
            "period": "2024-Q1",
            "organisation": "Test Org",
        }])
        assert r.status_code == 200
        data = r.json()
        assert data["imported"] == 0
        assert data["skipped"] == 1
        assert len(data["errors"]) == 1
        assert "UNKNOWN99" in data["errors"][0]

    def test_import_mixed_known_and_unknown(self, client, category_with_code):
        r = client.post("/esg/import", json=[
            {"metric_code": category_with_code["_code"], "value": 200.0, "period": "2024-Q2", "organisation": "Org X"},
            {"metric_code": "BAD_CODE", "value": 999.0, "period": "2024-Q2", "organisation": "Org X"},
        ])
        assert r.status_code == 200
        data = r.json()
        assert data["imported"] == 1
        assert data["skipped"] == 1

    def test_import_empty_list_returns_zero(self, client):
        r = client.post("/esg/import", json=[])
        assert r.status_code == 200
        data = r.json()
        assert data["imported"] == 0
        assert data["skipped"] == 0

    def test_import_creates_retrievable_metrics(self, client, category_with_code):
        """Imported metrics should be readable via GET /esg/metrics."""
        client.post("/esg/import", json=[{
            "metric_code": category_with_code["_code"],
            "value": 888.0,
            "period": "2024-Q3",
            "organisation": "Readable Org",
        }])
        r = client.get("/esg/metrics")
        assert r.status_code == 200
        values = [m["value"] for m in r.json()]
        assert 888.0 in values

    def test_import_requires_auth(self, raw_client):
        r = raw_client.post("/esg/import", json=[])
        assert r.status_code == 401

    def test_import_invalid_period_returns_422(self, client, category_with_code):
        r = client.post("/esg/import", json=[{
            "metric_code": category_with_code["_code"],
            "value": 100.0,
            "period": "not-a-period",
            "organisation": "Org",
        }])
        assert r.status_code == 422


# ─── CSV Export ───────────────────────────────────────────────────────────────

class TestCSVExport:
    def test_export_returns_csv_content_type(self, client, category_with_code):
        r = client.get("/esg/export")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

    def test_export_empty_when_no_coded_categories(self, client, category_no_code):
        r = client.get("/esg/export")
        assert r.status_code == 200
        assert r.text == ""

    def test_export_contains_metric_code_columns(self, client, two_coded_categories):
        # Add some data via import
        client.post("/esg/import", json=[
            {"metric_code": two_coded_categories[0]["_code"], "value": 100.0, "period": "2024-Q1", "organisation": "Org A"},
            {"metric_code": two_coded_categories[1]["_code"], "value": 0.05, "period": "2024-Q1", "organisation": "Org A"},
        ])
        r = client.get("/esg/export")
        assert r.status_code == 200
        reader = csv.DictReader(io.StringIO(r.text))
        cols = reader.fieldnames
        assert two_coded_categories[0]["_code"] in cols
        assert two_coded_categories[1]["_code"] in cols
        assert "period" in cols
        assert "organisation" in cols

    def test_export_values_correct(self, client, two_coded_categories):
        client.post("/esg/import", json=[
            {"metric_code": two_coded_categories[0]["_code"], "value": 250.0, "period": "2024-Q1", "organisation": "Test Co"},
        ])
        r = client.get("/esg/export")
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        esu_code = two_coded_categories[0]["_code"]
        # Bulk import now stamps the caller's real org name (tenant integrity),
        # ignoring the client-supplied "Test Co" - so match on period + value.
        matching = [r for r in rows if r["period"] == "2024-Q1" and r.get(esu_code)]
        assert len(matching) == 1
        assert float(matching[0][esu_code]) == 250.0
        assert matching[0]["organisation"] != "Test Co"  # client value not trusted

    def test_export_period_filter(self, client, category_with_code):
        # Import two periods
        client.post("/esg/import", json=[
            {"metric_code": category_with_code["_code"], "value": 100.0, "period": "2024-Q1", "organisation": "Org"},
            {"metric_code": category_with_code["_code"], "value": 200.0, "period": "2024-Q2", "organisation": "Org"},
        ])
        r = client.get("/esg/export?period=2024-Q1")
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        periods = [row["period"] for row in rows]
        assert all(p == "2024-Q1" for p in periods)
        assert "2024-Q2" not in periods

    def test_export_requires_auth(self, raw_client):
        r = raw_client.get("/esg/export")
        assert r.status_code == 401


# ─── Org Snapshot ─────────────────────────────────────────────────────────────

class TestOrgSnapshot:
    def test_snapshot_returns_200(self, client):
        r = client.get("/org/snapshot")
        assert r.status_code == 200

    def test_snapshot_has_all_required_fields(self, client):
        r = client.get("/org/snapshot")
        data = r.json()
        assert "org_id" in data
        assert "org_name" in data
        assert "esg" in data
        assert "risk" in data
        assert "compliance" in data
        assert "sub_module_averages" in data
        assert "generated_at" in data

    def test_snapshot_esg_fields(self, client):
        r = client.get("/org/snapshot")
        esg = r.json()["esg"]
        assert "total_metrics" in esg
        assert "scored_metrics" in esg
        assert "unscored_metrics" in esg
        assert "avg_score" in esg

    def test_snapshot_risk_fields(self, client):
        r = client.get("/org/snapshot")
        risk = r.json()["risk"]
        assert "total_open" in risk
        assert "critical_zone_count" in risk
        assert "highest_risk_score" in risk

    def test_snapshot_compliance_fields(self, client):
        r = client.get("/org/snapshot")
        compliance = r.json()["compliance"]
        assert "overall_rate" in compliance
        assert "total_requirements" in compliance
        assert "compliant" in compliance

    def test_snapshot_sub_module_averages_is_list(self, client):
        r = client.get("/org/snapshot")
        subs = r.json()["sub_module_averages"]
        assert isinstance(subs, list)

    def test_snapshot_sub_module_has_correct_fields(self, client):
        r = client.get("/org/snapshot")
        subs = r.json()["sub_module_averages"]
        if subs:
            sub = subs[0]
            assert "sub_module_id" in sub
            assert "sub_module_name" in sub
            assert "average_score" in sub
            assert "metric_count" in sub
            assert "scored_count" in sub

    def test_snapshot_counts_match_data(self, client, category_with_code):
        """After importing metrics, snapshot totals should update."""
        client.post("/esg/import", json=[
            {"metric_code": category_with_code["_code"], "value": 300.0, "period": "2024-Q1", "organisation": "Snap Org"},
            {"metric_code": category_with_code["_code"], "value": 400.0, "period": "2024-Q2", "organisation": "Snap Org"},
        ])
        r = client.get("/org/snapshot")
        esg = r.json()["esg"]
        assert esg["total_metrics"] >= 2

    def test_snapshot_requires_auth(self, raw_client):
        r = raw_client.get("/org/snapshot")
        assert r.status_code == 401

    def test_snapshot_with_coded_categories_shows_sub_modules(self, client, two_coded_categories):
        """Categories with metric codes should map to sub-module averages."""
        client.post("/esg/import", json=[
            {"metric_code": two_coded_categories[0]["_code"], "value": 100.0, "period": "2024-Q1", "organisation": "SubMod Org"},
        ])
        r = client.get("/org/snapshot")
        subs = r.json()["sub_module_averages"]
        esu_code = two_coded_categories[0]["_code"]
        prefix = esu_code[:3]
        esu_sub = next((s for s in subs if s["sub_module_id"] == f"{prefix}10000"), None)
        assert esu_sub is not None
        assert esu_sub["metric_count"] >= 1


# ─── Prompts alignment with Golden Response ───────────────────────────────────

class TestPromptsGoldenResponseAlignment:
    """Verify prompts.py produces output aligned to Golden Response spec."""

    def test_orchestrator_system_contains_l1_structure(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        assert "L1_ESRC_Risk_Assessment" in ORCHESTRATOR_SYSTEM

    def test_orchestrator_system_has_required_top_level_fields(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        for field in [
            "Module_Name", "Report_Date", "Org_Name",
            "L1_Risk_Assessment", "Time_Series_Reporting",
            "Statistical_Analysis", "Actionable_Insights"
        ]:
            assert field in ORCHESTRATOR_SYSTEM, f"Missing field: {field}"

    def test_orchestrator_system_has_sub_module_average_performance(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        assert "Sub_Module_Average_Performance" in ORCHESTRATOR_SYSTEM

    def test_orchestrator_system_has_low_performing_entities(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        assert "Low_Performing_Entities" in ORCHESTRATOR_SYSTEM

    def test_orchestrator_system_has_confidence_score(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        assert "Confidence_Score" in ORCHESTRATOR_SYSTEM

    def test_orchestrator_system_has_trend_direction(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        assert "Trend_Direction" in ORCHESTRATOR_SYSTEM

    def test_orchestrator_system_has_recommendations(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        assert "Recommendations" in ORCHESTRATOR_SYSTEM

    def test_orchestrator_system_has_primary_risk_drivers(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        assert "Primary_Risk_Drivers" in ORCHESTRATOR_SYSTEM

    def test_orchestrator_system_has_write_findings_format_instruction(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        assert "write_findings" in ORCHESTRATOR_SYSTEM

    def test_orchestrator_system_uses_org_name_placeholder(self):
        from app.agent.prompts import ORCHESTRATOR_SYSTEM
        # The prompt contains {org_name} and {today_date} as real placeholders.
        # JSON-style braces in the template use single braces - escape manually for this test.
        import re
        # Escape all { and } that are not our two known placeholders
        escaped = ORCHESTRATOR_SYSTEM.replace("{", "{{").replace("}", "}}")
        escaped = escaped.replace("{{org_name}}", "{org_name}").replace("{{today_date}}", "{today_date}")
        filled = escaped.format(org_name="Test Org", today_date="2025-01-01")
        assert "Test Org" in filled
        assert "{org_name}" not in filled

    def test_specialist_esg_scorer_returns_score_field(self):
        from app.agent.prompts import SPECIALIST_ESG_SCORER
        assert '"score"' in SPECIALIST_ESG_SCORER

    def test_specialist_compliance_returns_status_and_confidence(self):
        from app.agent.prompts import SPECIALIST_COMPLIANCE_CLASSIFIER
        assert '"status"' in SPECIALIST_COMPLIANCE_CLASSIFIER
        assert '"confidence"' in SPECIALIST_COMPLIANCE_CLASSIFIER

    def test_specialist_risk_assessor_returns_recommended_level(self):
        from app.agent.prompts import SPECIALIST_RISK_ASSESSOR
        assert '"recommended_level"' in SPECIALIST_RISK_ASSESSOR
        assert '"urgent"' in SPECIALIST_RISK_ASSESSOR

    def test_write_findings_tool_schema_requires_findings_json(self):
        from app.agent.llm_agent import ORCHESTRATOR_TOOLS
        wf_tool = next(t for t in ORCHESTRATOR_TOOLS if t["name"] == "write_findings")
        required = wf_tool["input_schema"].get("required", [])
        assert "findings_json" in required

    def test_write_findings_tool_schema_has_object_type(self):
        from app.agent.llm_agent import ORCHESTRATOR_TOOLS
        wf_tool = next(t for t in ORCHESTRATOR_TOOLS if t["name"] == "write_findings")
        props = wf_tool["input_schema"]["properties"]
        assert "findings_json" in props
        assert props["findings_json"]["type"] == "object"


# ─── GET /esg/dashboard ───────────────────────────────────────────────────────

class TestESGDashboard:
    def test_dashboard_returns_200(self, client):
        r = client.get("/esg/dashboard")
        assert r.status_code == 200

    def test_dashboard_has_required_fields(self, client):
        r = client.get("/esg/dashboard")
        data = r.json()
        assert "org_id" in data
        assert "org_name" in data
        assert "categories" in data
        assert "total_categories" in data
        assert "categories_with_data" in data
        assert "categories_scored" in data
        assert "overall_avg_score" in data
        assert "generated_at" in data

    def test_dashboard_empty_when_no_categories(self, client):
        r = client.get("/esg/dashboard")
        data = r.json()
        assert data["total_categories"] == 0
        assert data["categories"] == []
        assert data["overall_avg_score"] is None

    def test_dashboard_counts_categories(self, client, two_coded_categories):
        r = client.get("/esg/dashboard")
        data = r.json()
        assert data["total_categories"] == 2

    def test_dashboard_shows_latest_metric(self, client, category_with_code):
        client.post("/esg/import", json=[{
            "metric_code": category_with_code["_code"],
            "value": 500.0, "period": "2024-Q1", "organisation": "Dash Org"
        }])
        r = client.get("/esg/dashboard")
        cats = r.json()["categories"]
        assert len(cats) == 1
        assert cats[0]["latest_value"] == 500.0
        assert cats[0]["latest_period"] == "2024-Q1"
        assert cats[0]["metric_count"] == 1

    def test_dashboard_category_has_correct_fields(self, client, category_with_code):
        r = client.get("/esg/dashboard")
        cats = r.json()["categories"]
        assert len(cats) == 1
        cat = cats[0]
        assert "category_id" in cat
        assert "category_name" in cat
        assert "pillar" in cat
        assert "metric_code" in cat
        assert "latest_period" in cat
        assert "latest_value" in cat
        assert "latest_score" in cat
        assert "metric_count" in cat

    def test_dashboard_requires_auth(self, raw_client):
        r = raw_client.get("/esg/dashboard")
        assert r.status_code == 401


# ─── PATCH /compliance/requirements/bulk ─────────────────────────────────────

class TestBulkRequirementUpdate:
    @pytest.fixture
    def framework_and_requirements(self, client):
        fw = client.post("/compliance/frameworks", json={
            "name": "Bulk Update Framework"
        }).json()
        reqs = []
        for i in range(3):
            r = client.post("/compliance/requirements", json={
                "framework_id": fw["id"],
                "code": f"BLK-{i+1}",
                "title": f"Bulk Requirement {i+1}",
            }).json()
            reqs.append(r)
        return fw, reqs

    def test_bulk_update_returns_200(self, client, framework_and_requirements):
        _, reqs = framework_and_requirements
        r = client.patch("/compliance/requirements/bulk", json=[
            {"id": reqs[0]["id"], "status": "compliant"},
            {"id": reqs[1]["id"], "status": "non_compliant"},
        ])
        assert r.status_code == 200

    def test_bulk_update_correct_counts(self, client, framework_and_requirements):
        _, reqs = framework_and_requirements
        r = client.patch("/compliance/requirements/bulk", json=[
            {"id": reqs[0]["id"], "status": "compliant"},
            {"id": reqs[1]["id"], "status": "partial"},
        ])
        data = r.json()
        assert data["updated"] == 2
        assert data["skipped"] == 0
        assert data["errors"] == []

    def test_bulk_update_persists_status(self, client, framework_and_requirements):
        fw, reqs = framework_and_requirements
        client.patch("/compliance/requirements/bulk", json=[
            {"id": reqs[0]["id"], "status": "compliant"},
        ])
        r = client.get(f"/compliance/requirements/{reqs[0]['id']}")
        assert r.json()["status"] == "compliant"

    def test_bulk_update_skips_unknown_ids(self, client, framework_and_requirements):
        _, reqs = framework_and_requirements
        r = client.patch("/compliance/requirements/bulk", json=[
            {"id": reqs[0]["id"], "status": "compliant"},
            {"id": 999999, "status": "compliant"},
        ])
        data = r.json()
        assert data["updated"] == 1
        assert data["skipped"] == 1
        assert len(data["errors"]) == 1

    def test_bulk_update_with_evidence(self, client, framework_and_requirements):
        _, reqs = framework_and_requirements
        client.patch("/compliance/requirements/bulk", json=[
            {"id": reqs[0]["id"], "status": "compliant",
             "evidence": "Annual report 2024 p.42"},
        ])
        r = client.get(f"/compliance/requirements/{reqs[0]['id']}")
        assert r.json()["evidence"] == "Annual report 2024 p.42"

    def test_bulk_update_empty_list_returns_zero(self, client):
        r = client.patch("/compliance/requirements/bulk", json=[])
        assert r.status_code == 200
        data = r.json()
        assert data["updated"] == 0
        assert data["skipped"] == 0

    def test_bulk_update_requires_auth(self, raw_client):
        r = raw_client.patch("/compliance/requirements/bulk", json=[])
        assert r.status_code == 401
