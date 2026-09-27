"""
Tests for the ESG Scoring Engine - benchmarks and metric scoring.

Covers:
- Benchmark CRUD
- Scoring algorithm (lower_is_better, higher_is_better)
- Edge cases: at-target (100), at-baseline (0), beyond range (clamped)
- Degenerate benchmark rejected at schema level
- Missing benchmark raises 422 (not 500)
- Unit tests for the pure scoring function (no DB, no HTTP)
"""

import uuid
import pytest
from app.models.models import ESGScoreBenchmark, ScoringDirection
from app.services.scoring import compute_score


# ── Pure algorithm unit tests (no DB, no HTTP) ────────────────────────────────

def _make_benchmark(target, baseline, direction):
    """Build a benchmark object without a DB session."""
    b = ESGScoreBenchmark()
    b.id = 1
    b.target_value = target
    b.baseline_value = baseline
    b.direction = direction
    return b


def test_lower_is_better_at_target():
    b = _make_benchmark(target=0.0, baseline=500.0, direction=ScoringDirection.LOWER_IS_BETTER)
    assert compute_score(0.0, b) == 100.0


def test_lower_is_better_at_baseline():
    b = _make_benchmark(target=0.0, baseline=500.0, direction=ScoringDirection.LOWER_IS_BETTER)
    assert compute_score(500.0, b) == 0.0


def test_lower_is_better_midpoint():
    b = _make_benchmark(target=0.0, baseline=500.0, direction=ScoringDirection.LOWER_IS_BETTER)
    assert compute_score(250.0, b) == 50.0


def test_lower_is_better_clamped_above_baseline():
    b = _make_benchmark(target=0.0, baseline=500.0, direction=ScoringDirection.LOWER_IS_BETTER)
    assert compute_score(1000.0, b) == 0.0   # beyond worst case → 0


def test_lower_is_better_clamped_below_target():
    b = _make_benchmark(target=0.0, baseline=500.0, direction=ScoringDirection.LOWER_IS_BETTER)
    assert compute_score(-100.0, b) == 100.0  # beyond best case → 100


def test_higher_is_better_at_target():
    b = _make_benchmark(target=100.0, baseline=0.0, direction=ScoringDirection.HIGHER_IS_BETTER)
    assert compute_score(100.0, b) == 100.0


def test_higher_is_better_at_baseline():
    b = _make_benchmark(target=100.0, baseline=0.0, direction=ScoringDirection.HIGHER_IS_BETTER)
    assert compute_score(0.0, b) == 0.0


def test_higher_is_better_midpoint():
    b = _make_benchmark(target=100.0, baseline=0.0, direction=ScoringDirection.HIGHER_IS_BETTER)
    assert compute_score(75.0, b) == 75.0


def test_higher_is_better_clamped_above_target():
    b = _make_benchmark(target=100.0, baseline=0.0, direction=ScoringDirection.HIGHER_IS_BETTER)
    assert compute_score(150.0, b) == 100.0


def test_degenerate_benchmark_returns_zero():
    b = _make_benchmark(target=50.0, baseline=50.0, direction=ScoringDirection.LOWER_IS_BETTER)
    assert compute_score(50.0, b) == 0.0


# ── HTTP integration tests ─────────────────────────────────────────────────────

@pytest.fixture
def category_id(client):
    name = f"Carbon Emissions {uuid.uuid4().hex[:8]}"
    r = client.post("/esg/categories", json={"name": name, "pillar": "environmental", "unit": "tonnes CO2"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def metric_id(client, category_id):
    r = client.post("/esg/metrics", json={
        "category_id": category_id,
        "organisation": "AcmeCorp",
        "value": 250.0,
        "period": "2024-Q1",
    })
    return r.json()["id"]


@pytest.fixture
def benchmark_id(client, category_id):
    r = client.post("/esg/benchmarks", json={
        "category_id": category_id,
        "target_value": 0.0,
        "baseline_value": 500.0,
        "direction": "lower_is_better",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_benchmark(client, category_id):
    r = client.post("/esg/benchmarks", json={
        "category_id": category_id,
        "target_value": 0.0,
        "baseline_value": 500.0,
        "direction": "lower_is_better",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["target_value"] == 0.0
    assert data["baseline_value"] == 500.0
    assert data["direction"] == "lower_is_better"
    assert "updated_at" in data


def test_create_benchmark_unknown_category(client):
    r = client.post("/esg/benchmarks", json={
        "category_id": 9999,
        "target_value": 0.0,
        "baseline_value": 500.0,
        "direction": "lower_is_better",
    })
    assert r.status_code == 404


def test_degenerate_benchmark_rejected(client, category_id):
    r = client.post("/esg/benchmarks", json={
        "category_id": category_id,
        "target_value": 100.0,
        "baseline_value": 100.0,
        "direction": "higher_is_better",
    })
    assert r.status_code == 422


def test_get_benchmark_for_category(client, category_id, benchmark_id):
    r = client.get(f"/esg/categories/{category_id}/benchmark")
    assert r.status_code == 200
    assert r.json()["id"] == benchmark_id


def test_get_benchmark_by_id(client, benchmark_id):
    r = client.get(f"/esg/benchmarks/{benchmark_id}")
    assert r.status_code == 200
    assert r.json()["id"] == benchmark_id


def test_patch_benchmark(client, benchmark_id):
    r = client.patch(f"/esg/benchmarks/{benchmark_id}", json={"target_value": 10.0})
    assert r.status_code == 200
    assert r.json()["target_value"] == 10.0


def test_replace_benchmark_upsert(client, category_id, benchmark_id):
    """Second POST to same category_id should update, not error."""
    r = client.post("/esg/benchmarks", json={
        "category_id": category_id,
        "target_value": 50.0,
        "baseline_value": 1000.0,
        "direction": "lower_is_better",
    })
    assert r.status_code == 201
    assert r.json()["target_value"] == 50.0
    assert r.json()["id"] == benchmark_id   # same record, updated in place


def test_score_metric_lower_is_better(client, metric_id, benchmark_id):
    """value=250, target=0, baseline=500 → score=50"""
    r = client.post(f"/esg/metrics/{metric_id}/score")
    assert r.status_code == 200
    data = r.json()
    assert data["score"] == 50.0
    assert data["metric_id"] == metric_id
    assert data["direction"] == "lower_is_better"


def test_score_metric_higher_is_better(client, category_id):
    """value=75, target=100, baseline=0 → score=75"""
    client.post("/esg/benchmarks", json={
        "category_id": category_id,
        "target_value": 100.0,
        "baseline_value": 0.0,
        "direction": "higher_is_better",
    })
    r = client.post("/esg/metrics", json={
        "category_id": category_id, "organisation": "X",
        "value": 75.0, "period": "2024-Q2",
    })
    mid = r.json()["id"]
    r2 = client.post(f"/esg/metrics/{mid}/score")
    assert r2.status_code == 200
    assert r2.json()["score"] == 75.0


def test_score_metric_clamped_to_100(client, category_id):
    """value beyond target → clamped to 100"""
    client.post("/esg/benchmarks", json={
        "category_id": category_id,
        "target_value": 0.0,
        "baseline_value": 500.0,
        "direction": "lower_is_better",
    })
    r = client.post("/esg/metrics", json={
        "category_id": category_id, "organisation": "X",
        "value": -50.0, "period": "2024",
    })
    mid = r.json()["id"]
    r2 = client.post(f"/esg/metrics/{mid}/score")
    assert r2.json()["score"] == 100.0


def test_score_metric_no_benchmark_returns_422(client, category_id):
    """Scoring without a benchmark should return 422, not 500."""
    r = client.post("/esg/metrics", json={
        "category_id": category_id, "organisation": "X",
        "value": 100.0, "period": "2024",
    })
    mid = r.json()["id"]
    r2 = client.post(f"/esg/metrics/{mid}/score")
    assert r2.status_code == 422


def test_score_unknown_metric(client):
    r = client.post("/esg/metrics/9999/score")
    assert r.status_code == 404


def test_patch_metric_cannot_set_score_directly(client, category_id):
    """
    Regression: ESGMetricUpdate used to accept an arbitrary 0-100 `score`,
    so PATCH /esg/metrics/{id} could set it directly - bypassing
    compute_score()/the benchmark formula that POST .../score and the
    batch/LLM agents both go through. `score` must now be silently ignored
    on this endpoint; it can only be set via the real scoring path.
    """
    client.post("/esg/benchmarks", json={
        "category_id": category_id,
        "target_value": 100.0,
        "baseline_value": 0.0,
        "direction": "higher_is_better",
    })
    r = client.post("/esg/metrics", json={
        "category_id": category_id, "organisation": "X",
        "value": 75.0, "period": "2024-Q3",
    })
    mid = r.json()["id"]
    assert r.json()["score"] is None

    patched = client.patch(f"/esg/metrics/{mid}", json={"score": 99.0})
    assert patched.status_code == 200
    assert patched.json()["score"] is None  # ignored, not set to 99

    scored = client.post(f"/esg/metrics/{mid}/score")
    assert scored.json()["score"] == 75.0  # the real, computed value


def test_score_persisted_on_metric(client, metric_id, benchmark_id):
    """After scoring, GET /esg/metrics/{id} should reflect the score."""
    client.post(f"/esg/metrics/{metric_id}/score")
    r = client.get(f"/esg/metrics/{metric_id}")
    assert r.json()["score"] == 50.0
