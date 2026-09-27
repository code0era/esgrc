"""
Tests for the batch agent - tasks, runner, and API endpoints.

Unit tests run tasks directly against the in-memory DB (no scheduler needed).
Integration tests hit the HTTP endpoints via the admin-role client.

Covers:
- score_unscored_metrics: scores metrics with benchmarks, skips those without
- flag_overdue_requirements: flags past review_date, skips future ones
- escalate_critical_risks: escalates overdue critical risks, ignores safe ones
- run_batch(): creates AgentRunLog, correct totals, status=SUCCESS
- GET /agent/runs - returns run history
- GET /agent/runs/{id} - returns single run with details
- GET /agent/status - returns scheduler info
- POST /agent/run - 202 Accepted
- Non-admin cannot access agent endpoints (403)
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.agent.runner import run_batch
from app.agent.tasks import (
    escalate_critical_risks,
    flag_overdue_requirements,
    score_unscored_metrics,
)
from app.database import get_db
from app.dependencies.auth import get_current_org, get_current_user
from app.models.models import (
    AgentRunStatus,
    ComplianceFramework,
    ComplianceRequirement,
    ComplianceStatus,
    ESGCategory,
    ESGMetric,
    ESGPillar,
    ESGScoreBenchmark,
    Organisation,
    Risk,
    RiskLevel,
    RiskStatus,
    ScoringDirection,
    User,
    UserRole,
)
from app.services.auth import create_access_token
from main import app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_org(db_session) -> Organisation:
    uid = uuid.uuid4().hex[:8]
    org = Organisation(name=f"AgentTestOrg {uid}", slug=f"agent-{uid}")
    db_session.add(org)
    db_session.flush()
    return org


def _make_category(db_session, org_id: int) -> ESGCategory:
    uid = uuid.uuid4().hex[:6]
    cat = ESGCategory(
        org_id=org_id,
        name=f"Carbon {uid}",
        pillar=ESGPillar.ENVIRONMENTAL,
        unit="tonnes CO2",
    )
    db_session.add(cat)
    db_session.flush()
    return cat


def _make_benchmark(db_session, category_id: int) -> ESGScoreBenchmark:
    b = ESGScoreBenchmark(
        category_id=category_id,
        target_value=0.0,
        baseline_value=500.0,
        direction=ScoringDirection.LOWER_IS_BETTER,
    )
    db_session.add(b)
    db_session.flush()
    return b


def _make_metric(db_session, category_id: int, value: float = 250.0, period: str = "2024-Q1") -> ESGMetric:
    m = ESGMetric(
        category_id=category_id,
        organisation="TestOrg",
        value=value,
        period=period,
    )
    db_session.add(m)
    db_session.flush()
    return m


def _make_framework(db_session, org_id: int) -> ComplianceFramework:
    uid = uuid.uuid4().hex[:6]
    fw = ComplianceFramework(org_id=org_id, name=f"GRI {uid}", active=True)
    db_session.add(fw)
    db_session.flush()
    return fw


def _make_requirement(
    db_session,
    framework_id: int,
    status: ComplianceStatus = ComplianceStatus.NOT_ASSESSED,
    review_date: datetime | None = None,
) -> ComplianceRequirement:
    req = ComplianceRequirement(
        framework_id=framework_id,
        title="Test Requirement",
        status=status,
        review_date=review_date,
    )
    db_session.add(req)
    db_session.flush()
    return req


def _make_risk(
    db_session,
    org_id: int,
    likelihood: int = 4,
    impact: int = 5,
    status: RiskStatus = RiskStatus.OPEN,
    due_date: datetime | None = None,
    level: RiskLevel = RiskLevel.HIGH,
) -> Risk:
    r = Risk(
        org_id=org_id,
        title="Test Risk",
        level=level,
        status=status,
        likelihood=likelihood,
        impact=impact,
        due_date=due_date,
    )
    db_session.add(r)
    db_session.flush()
    return r


# ── Task unit tests ───────────────────────────────────────────────────────────

def test_score_unscored_metrics_with_benchmark(db_session):
    org = _make_org(db_session)
    cat = _make_category(db_session, org.id)
    _make_benchmark(db_session, cat.id)
    metric = _make_metric(db_session, cat.id, value=250.0)
    assert metric.score is None

    result = score_unscored_metrics(db_session, org.id)

    assert result["scored"] == 1
    assert result["skipped_no_benchmark"] == 0
    db_session.refresh(metric)
    assert metric.score == 50.0  # (500-250)/(500-0)*100


def test_score_unscored_metrics_no_benchmark(db_session):
    org = _make_org(db_session)
    cat = _make_category(db_session, org.id)
    # No benchmark created
    _make_metric(db_session, cat.id)

    result = score_unscored_metrics(db_session, org.id)

    assert result["scored"] == 0
    assert result["skipped_no_benchmark"] == 1


def test_score_unscored_metrics_skips_already_scored(db_session):
    org = _make_org(db_session)
    cat = _make_category(db_session, org.id)
    _make_benchmark(db_session, cat.id)
    metric = _make_metric(db_session, cat.id)
    metric.score = 75.0  # already scored
    db_session.flush()

    result = score_unscored_metrics(db_session, org.id)

    assert result["scored"] == 0  # was already scored, not re-scored


def test_score_unscored_metrics_caches_benchmark_per_category(db_session, monkeypatch):
    """
    Regression: score_unscored_metrics previously called get_benchmark_by_category
    once per metric, so N metrics sharing one category issued N identical
    benchmark queries. It must now issue at most one lookup per distinct
    category regardless of how many metrics share it.
    """
    import app.agent.tasks as tasks_module

    org = _make_org(db_session)
    cat = _make_category(db_session, org.id)
    _make_benchmark(db_session, cat.id)
    for _ in range(5):
        _make_metric(db_session, cat.id, value=250.0)

    calls = []
    real_lookup = tasks_module.get_benchmark_by_category

    def _counting_lookup(db, category_id):
        calls.append(category_id)
        return real_lookup(db, category_id)

    monkeypatch.setattr(tasks_module, "get_benchmark_by_category", _counting_lookup)

    result = score_unscored_metrics(db_session, org.id)

    assert result["scored"] == 5
    assert len(calls) == 1  # one lookup for the one distinct category, not 5


def test_score_metrics_org_isolation(db_session):
    """Scoring task must not touch another org's metrics."""
    org_a = _make_org(db_session)
    org_b = _make_org(db_session)
    cat_a = _make_category(db_session, org_a.id)
    cat_b = _make_category(db_session, org_b.id)
    _make_benchmark(db_session, cat_a.id)
    _make_metric(db_session, cat_b.id)  # belongs to org_b

    result = score_unscored_metrics(db_session, org_a.id)  # run for org_a only
    assert result["scored"] == 0  # org_b's metric should not be touched


def test_flag_overdue_requirements(db_session):
    org = _make_org(db_session)
    fw = _make_framework(db_session, org.id)
    past = datetime.now(timezone.utc) - timedelta(days=7)
    req = _make_requirement(db_session, fw.id, status=ComplianceStatus.PARTIAL, review_date=past)

    result = flag_overdue_requirements(db_session, org.id)

    assert result["flagged"] == 1
    db_session.refresh(req)
    assert req.status == ComplianceStatus.NOT_ASSESSED


def test_flag_overdue_skips_future_review_date(db_session):
    org = _make_org(db_session)
    fw = _make_framework(db_session, org.id)
    future = datetime.now(timezone.utc) + timedelta(days=30)
    _make_requirement(db_session, fw.id, status=ComplianceStatus.PARTIAL, review_date=future)

    result = flag_overdue_requirements(db_session, org.id)
    assert result["flagged"] == 0


def test_flag_overdue_skips_compliant(db_session):
    """Compliant requirements should not be reset even if overdue."""
    org = _make_org(db_session)
    fw = _make_framework(db_session, org.id)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    req = _make_requirement(db_session, fw.id, status=ComplianceStatus.COMPLIANT, review_date=past)

    result = flag_overdue_requirements(db_session, org.id)
    assert result["flagged"] == 0
    db_session.refresh(req)
    assert req.status == ComplianceStatus.COMPLIANT  # untouched


def test_escalate_critical_risks(db_session):
    org = _make_org(db_session)
    past = datetime.now(timezone.utc) - timedelta(days=3)
    risk = _make_risk(db_session, org.id, likelihood=4, impact=5, due_date=past, level=RiskLevel.HIGH)
    # risk_score = 20 >= 20, overdue, open, not already CRITICAL

    result = escalate_critical_risks(db_session, org.id)

    assert result["escalated"] == 1
    db_session.refresh(risk)
    assert risk.level == RiskLevel.CRITICAL


def test_escalate_skips_low_score_risks(db_session):
    org = _make_org(db_session)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    _make_risk(db_session, org.id, likelihood=2, impact=3, due_date=past)
    # score = 6, below threshold of 20

    result = escalate_critical_risks(db_session, org.id)
    assert result["escalated"] == 0


def test_escalate_skips_future_due_date(db_session):
    org = _make_org(db_session)
    future = datetime.now(timezone.utc) + timedelta(days=10)
    _make_risk(db_session, org.id, likelihood=5, impact=5, due_date=future)

    result = escalate_critical_risks(db_session, org.id)
    assert result["escalated"] == 0


def test_escalate_skips_already_critical(db_session):
    org = _make_org(db_session)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    _make_risk(db_session, org.id, likelihood=5, impact=5, due_date=past, level=RiskLevel.CRITICAL)

    result = escalate_critical_risks(db_session, org.id)
    assert result["escalated"] == 0  # already CRITICAL, no-op


def test_escalate_org_isolation(db_session):
    org_a = _make_org(db_session)
    org_b = _make_org(db_session)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    _make_risk(db_session, org_b.id, likelihood=5, impact=5, due_date=past)

    result = escalate_critical_risks(db_session, org_a.id)
    assert result["escalated"] == 0  # org_b's risk not touched


# ── Runner integration test ───────────────────────────────────────────────────

def test_run_batch_creates_log(db_session):
    """run_batch() must create an AgentRunLog with status SUCCESS."""
    # Seed data: one org with scorable metric
    org = _make_org(db_session)
    cat = _make_category(db_session, org.id)
    _make_benchmark(db_session, cat.id)
    _make_metric(db_session, cat.id, value=100.0)
    db_session.commit()

    # Inject a session factory that returns the test session
    # so run_batch uses the same in-memory DB as the test
    def test_session_factory():
        return db_session

    run_log = run_batch(session_factory=test_session_factory)

    assert run_log.status == AgentRunStatus.SUCCESS
    assert run_log.orgs_processed >= 1
    assert run_log.metrics_scored >= 1
    assert run_log.finished_at is not None
    assert run_log.details is not None
    details = json.loads(run_log.details)
    assert isinstance(details, list)
    assert len(details) >= 1


# ── HTTP endpoint tests ───────────────────────────────────────────────────────

@pytest.fixture
def admin_client(db_session):
    """Client with admin JWT injected."""
    uid = uuid.uuid4().hex[:8]
    org = Organisation(name=f"AdminOrg {uid}", slug=f"admin-{uid}")
    user = User(
        organisation_id=1,  # will be updated after flush
        email=f"admin-{uid}@test.com",
        full_name="Admin",
        hashed_password="x",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(org)
    db_session.flush()
    user.organisation_id = org.id
    db_session.add(user)
    db_session.flush()

    token = create_access_token(user_id=user.id, org_id=org.id, role="admin")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_org] = lambda: org

    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def analyst_client(db_session):
    """Client with analyst JWT - should be denied agent endpoints."""
    uid = uuid.uuid4().hex[:8]
    org = Organisation(name=f"AnalystOrg {uid}", slug=f"analyst-{uid}")
    user = User(
        organisation_id=1,
        email=f"analyst-{uid}@test.com",
        full_name="Analyst",
        hashed_password="x",
        role=UserRole.ANALYST,
        is_active=True,
    )
    db_session.add(org)
    db_session.flush()
    user.organisation_id = org.id
    db_session.add(user)
    db_session.flush()

    token = create_access_token(user_id=user.id, org_id=org.id, role="analyst")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_org] = lambda: org

    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def super_admin_client(db_session):
    """Client with super_admin JWT - required to view platform-wide agent run logs."""
    uid = uuid.uuid4().hex[:8]
    org = Organisation(name=f"SuperOrg {uid}", slug=f"super-{uid}")
    user = User(
        organisation_id=1,
        email=f"super-{uid}@test.com",
        full_name="Super",
        hashed_password="x",
        role=UserRole.SUPER_ADMIN,
        is_active=True,
    )
    db_session.add(org)
    db_session.flush()
    user.organisation_id = org.id
    db_session.add(user)
    db_session.flush()

    token = create_access_token(user_id=user.id, org_id=org.id, role="super_admin")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_org] = lambda: org

    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c

    app.dependency_overrides.clear()


def test_list_runs_super_admin(super_admin_client):
    # AgentRunLog is a platform-wide, cross-org log → SUPER_ADMIN only.
    r = super_admin_client.get("/agent/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_runs_admin_forbidden(admin_client):
    # Org admins must NOT read cross-org agent run logs (tenant-isolation).
    r = admin_client.get("/agent/runs")
    assert r.status_code == 403


def test_list_runs_analyst_forbidden(analyst_client):
    r = analyst_client.get("/agent/runs")
    assert r.status_code == 403


def test_get_run_not_found(super_admin_client):
    r = super_admin_client.get("/agent/runs/9999")
    assert r.status_code == 404


def test_agent_status(admin_client):
    r = admin_client.get("/agent/status")
    assert r.status_code == 200
    data = r.json()
    assert "agent_enabled" in data
    assert "scheduler_running" in data
    assert "daily_esg_risk" in data
    assert "compliance_check" in data
    assert "schedule" in data["daily_esg_risk"]
    assert "schedule" in data["compliance_check"]


def test_trigger_run_accepted(super_admin_client):
    # SUPER_ADMIN can trigger the cross-org batch.
    r = super_admin_client.post("/agent/run")
    assert r.status_code == 202
    assert "queued_at" in r.json()

    # Wait for the fire-and-forget one-shot job to actually finish before this
    # fixture's `with TestClient(app)` block exits. Exiting fires app shutdown
    # (stop_scheduler -> scheduler.shutdown()), which - if it lands while the
    # scheduler's own background thread is still mid-`_process_jobs()` for the
    # job this test just queued - can race APScheduler's post-run cleanup and
    # surface as an unhandled JobLookupError in that thread. That race is an
    # artifact of this test opening/closing a fresh TestClient (and thus the
    # whole scheduler) around a single call; a real deployment starts the
    # scheduler once and shuts it down once, hours or days apart, never right
    # on the heels of a manual trigger.
    from app.agent.scheduler import get_scheduler
    import time

    deadline = time.monotonic() + 5
    while get_scheduler().get_job("esgrc_manual_run") is not None:
        if time.monotonic() > deadline:
            break
        time.sleep(0.02)


def test_trigger_run_admin_forbidden(admin_client):
    # A per-org ADMIN must NOT be able to trigger a batch that writes across ALL
    # organisations + spends the platform LLM budget (security fix).
    r = admin_client.post("/agent/run")
    assert r.status_code == 403


def test_trigger_run_analyst_forbidden(analyst_client):
    r = analyst_client.post("/agent/run")
    assert r.status_code == 403
