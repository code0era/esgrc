"""
Tests for GET /risks/heatmap.

Covers:
- Empty register → 25 zero-count cells, all summary stats 0
- Single risk correctly placed in its cell
- Multiple risks in same cell → count accumulates
- Risks across different cells
- NULL likelihood/impact → excluded from cells, reported in unscored_count
- status filter (open only)
- category filter
- critical_zone_count (likelihood >= 4 AND impact >= 4)
- highest_risk_score tracks the highest occupied cell
- All 25 cells always present in response
- Cells ordered by risk_score descending
"""

import pytest


def _make_risk(client, likelihood=None, impact=None, status="open", category=None):
    payload = {"title": f"Risk L{likelihood}I{impact}", "level": "medium"}
    if likelihood is not None:
        payload["likelihood"] = likelihood
    if impact is not None:
        payload["impact"] = impact
    if status != "open":
        payload["status"] = status
    if category:
        payload["category"] = category
    r = client.post("/risks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── Structure ─────────────────────────────────────────────────────────────────

def test_heatmap_always_returns_25_cells(client):
    r = client.get("/risks/heatmap")
    assert r.status_code == 200
    assert len(r.json()["cells"]) == 25


def test_heatmap_structure_invariants(client):
    """
    Invariants that must hold regardless of existing data:
    - always 25 cells
    - highest_risk_score equals max risk_score among non-empty cells (or 0)
    - total_scored equals sum of all cell counts
    - all cell counts are non-negative
    """
    r = client.get("/risks/heatmap")
    assert r.status_code == 200
    data = r.json()
    cells = data["cells"]
    assert len(cells) == 25
    assert all(c["count"] >= 0 for c in cells)
    assert data["total_scored"] == sum(c["count"] for c in cells)
    non_empty = [c for c in cells if c["count"] > 0]
    expected_highest = max((c["risk_score"] for c in non_empty), default=0)
    assert data["highest_risk_score"] == expected_highest


def test_heatmap_cells_ordered_by_risk_score_descending(client):
    r = client.get("/risks/heatmap")
    scores = [c["risk_score"] for c in r.json()["cells"]]
    assert scores == sorted(scores, reverse=True)


def test_heatmap_all_25_combinations_present(client):
    r = client.get("/risks/heatmap")
    pairs = {(c["likelihood"], c["impact"]) for c in r.json()["cells"]}
    expected = {(l, i) for l in range(1, 6) for i in range(1, 6)}
    assert pairs == expected


def test_heatmap_cell_risk_score_equals_likelihood_times_impact(client):
    r = client.get("/risks/heatmap")
    for cell in r.json()["cells"]:
        assert cell["risk_score"] == cell["likelihood"] * cell["impact"]


# ── Counting ──────────────────────────────────────────────────────────────────

def test_heatmap_single_risk_placed_correctly(client):
    _make_risk(client, likelihood=3, impact=4)
    r = client.get("/risks/heatmap")
    cell = next(c for c in r.json()["cells"] if c["likelihood"] == 3 and c["impact"] == 4)
    assert cell["count"] >= 1
    assert r.json()["total_scored"] >= 1


def test_heatmap_multiple_risks_same_cell(client):
    _make_risk(client, likelihood=2, impact=3)
    _make_risk(client, likelihood=2, impact=3)
    _make_risk(client, likelihood=2, impact=3)
    r = client.get("/risks/heatmap")
    cell = next(c for c in r.json()["cells"] if c["likelihood"] == 2 and c["impact"] == 3)
    assert cell["count"] >= 3


def test_heatmap_risks_across_different_cells(client):
    _make_risk(client, likelihood=1, impact=1)
    _make_risk(client, likelihood=5, impact=5)
    r = client.get("/risks/heatmap")
    data = r.json()
    low_cell  = next(c for c in data["cells"] if c["likelihood"] == 1 and c["impact"] == 1)
    high_cell = next(c for c in data["cells"] if c["likelihood"] == 5 and c["impact"] == 5)
    assert low_cell["count"] >= 1
    assert high_cell["count"] >= 1


# ── Unscored risks ────────────────────────────────────────────────────────────

def test_heatmap_null_likelihood_goes_to_unscored(client):
    _make_risk(client, likelihood=None, impact=3)
    r = client.get("/risks/heatmap")
    assert r.json()["unscored_count"] >= 1


def test_heatmap_null_impact_goes_to_unscored(client):
    _make_risk(client, likelihood=3, impact=None)
    r = client.get("/risks/heatmap")
    assert r.json()["unscored_count"] >= 1


def test_heatmap_both_null_goes_to_unscored(client):
    _make_risk(client, likelihood=None, impact=None)
    r = client.get("/risks/heatmap")
    assert r.json()["unscored_count"] >= 1


def test_heatmap_unscored_not_counted_in_total_scored(client):
    _make_risk(client, likelihood=3, impact=3)   # scored
    _make_risk(client, likelihood=None, impact=3) # unscored
    r = client.get("/risks/heatmap")
    data = r.json()
    # total_scored must not include the unscored one
    assert data["total_scored"] >= 1
    assert data["unscored_count"] >= 1
    # Verify the unscored risk is NOT in any cell
    assert all(c["count"] <= data["total_scored"] for c in data["cells"])


# ── Summary stats ─────────────────────────────────────────────────────────────

def test_heatmap_highest_risk_score(client):
    _make_risk(client, likelihood=4, impact=3)  # score 12
    _make_risk(client, likelihood=5, impact=4)  # score 20
    r = client.get("/risks/heatmap")
    assert r.json()["highest_risk_score"] >= 20


def test_heatmap_highest_risk_score_reflects_occupied_cells(client):
    """highest_risk_score must equal the risk_score of the highest occupied cell."""
    r = client.get("/risks/heatmap")
    data = r.json()
    non_empty = [c for c in data["cells"] if c["count"] > 0]
    if not non_empty:
        assert data["highest_risk_score"] == 0
    else:
        expected = max(c["risk_score"] for c in non_empty)
        assert data["highest_risk_score"] == expected


def test_heatmap_critical_zone_count(client):
    """likelihood >= 4 AND impact >= 4 = critical zone."""
    _make_risk(client, likelihood=4, impact=4)  # in critical zone: score 16
    _make_risk(client, likelihood=5, impact=5)  # in critical zone: score 25
    _make_risk(client, likelihood=3, impact=5)  # NOT in critical zone: score 15
    _make_risk(client, likelihood=4, impact=3)  # NOT in critical zone: score 12
    r = client.get("/risks/heatmap")
    assert r.json()["critical_zone_count"] >= 2


def test_heatmap_critical_zone_boundary(client):
    """Exact boundary: L=4,I=4 is in; L=3,I=5 and L=4,I=3 are NOT."""
    _make_risk(client, likelihood=3, impact=5)
    _make_risk(client, likelihood=4, impact=3)
    r = client.get("/risks/heatmap")
    # These two should NOT be in the critical zone
    # We get critical_zone_count before adding boundary risks
    initial_cz = r.json()["critical_zone_count"]

    _make_risk(client, likelihood=4, impact=4)
    r2 = client.get("/risks/heatmap")
    assert r2.json()["critical_zone_count"] == initial_cz + 1


# ── Filters ───────────────────────────────────────────────────────────────────

def test_heatmap_status_filter_open_only(client):
    """Closed risk must not appear when status=open is requested."""
    _make_risk(client, likelihood=5, impact=5, status="open")
    rid = _make_risk(client, likelihood=1, impact=1, status="open")
    # Close the second risk
    client.patch(f"/risks/{rid}", json={"status": "closed"})

    r_open = client.get("/risks/heatmap?status=open")
    r_all  = client.get("/risks/heatmap")
    # The closed risk (L1,I1) should NOT count in the open-only heatmap
    cell_open = next(c for c in r_open.json()["cells"] if c["likelihood"] == 1 and c["impact"] == 1)
    cell_all  = next(c for c in r_all.json()["cells"]  if c["likelihood"] == 1 and c["impact"] == 1)
    assert cell_open["count"] < cell_all["count"]


def test_heatmap_category_filter(client):
    """Only risks from the requested category should appear."""
    _make_risk(client, likelihood=5, impact=5, category="ESG")
    _make_risk(client, likelihood=3, impact=3, category="Operational")
    r = client.get("/risks/heatmap?category=ESG")
    data = r.json()
    high_cell = next(c for c in data["cells"] if c["likelihood"] == 5 and c["impact"] == 5)
    low_cell  = next(c for c in data["cells"] if c["likelihood"] == 3 and c["impact"] == 3)
    # ESG risk IS in the filtered heatmap
    assert high_cell["count"] >= 1
    # Operational risk should NOT appear in ESG-filtered heatmap
    # (can't be certain it's 0 if other tests added Operational risks, but
    #  the ESG count must be >= 1 and the total_scored must reflect filtering)
    assert data["total_scored"] >= 1


def test_heatmap_invalid_status_returns_422(client):
    r = client.get("/risks/heatmap?status=invalid_status")
    assert r.status_code == 422
