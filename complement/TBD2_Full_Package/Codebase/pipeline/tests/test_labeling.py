"""
pipeline/test/test_labeling.py
Unit tests for the contextual-labeling layer (pipeline/llm/labeling.py).

Verifies the locked design (docs/analytics/DRIFT_TEST_RESULTS.md):
  - deterministic code->name substitution applied at display time,
  - a validation gate that guarantees numeric integrity and complete substitution,
  - fail-safe fallback to the code text when the gate trips.
"""
from collections import Counter

from pipeline.llm.labeling import (
    CODE_RE,
    label_output,
    load_label_map,
    validate_labeling,
)

# The exact response_text the seed script stores for the demo ESGRC run
# (pipeline/scripts/seed_demo.py) - a realistic served-report fixture.
SEED_REPORT = """## Module Risk Assessment

**Overall Risk Score:** 6/10
**Confidence:** Medium - 4 periods of data, 2 SPC violations detected
**Trend:** Improving - scores increased 12% from Q1 to Q4 2024

### Top Risk Areas

**Risk 1: GRC Framework Coverage Gap**
- Description: GRC10101 scored 72/100 in Q4 - below the 90% target benchmark.
- Evidence: Correlation analysis shows GRC coverage strongly predicts overall ESG score (r=0.78).
- Recommended Action: Commission a GRC gap analysis within 30 days. Target 80% coverage by Q2 2025.

**Risk 2: GHG Indirect Emissions Non-Compliance**
- Description: Scope 2 emissions tracking (GRI 305-2) is non-compliant per latest assessment.

**Risk 3: ERM Baseline Incomplete**
- Description: ERM10101 at 70/100 - enterprise risk management framework partially implemented.
- Evidence: Regression model shows ERM completeness drives 34% of overall risk score variance.

### Low-Performing Sub-Modules
- GRC10101: 72/100 (target: 90)
- ERM10101: 70/100 (target: 85)
"""


# ── Resolver map ─────────────────────────────────────────────────────────────

def test_map_has_full_product_coverage():
    m = load_label_map()
    levels = Counter(e.level for e in m.values())
    # Granular group/metric names come from the bundled per-module perf JSONs,
    # one module at a time (see _PERF_JSONS in labeling.py):
    #   ESGRC             41 groups /  84 metrics
    #   Customer          19 groups / 348 metrics
    #   Shared            96 groups / 288 metrics
    #   Business Partner 124 groups / 336 metrics
    # These are lower bounds, not equalities - adding the next module's perf JSON
    # should not break this test, only the per-module assertions below.
    assert levels["group"] >= 41 + 19 + 96 + 124
    assert levels["metric"] >= 84 + 348 + 288 + 336
    # Apex modules from module_mapping.csv - all 12 are already bundled:
    assert levels["module"] == 12
    # sub-modules span the whole product (ESGRC 14 + Customer 19 + Shared 14 +
    # Business Partner 17 + the rest of the Apex 12 from module_mapping.csv)
    assert levels["sub_module"] >= 14 + 19 + 14 + 17


def test_customer_codes_resolve():
    """Customer perf JSON is bundled and loaded alongside ESGRC's."""
    m = load_label_map()
    assert m["CUST_001"].name == "Customer"
    assert m["CUST_001"].level == "module"
    assert m["CSR10000"].name == "Customer Support and Readiness"
    assert m["CSR10000"].level == "sub_module"
    assert m["CSR10101"].level == "metric"
    # ESGRC must be unaffected by the second JSON (no namespace collision).
    assert m["ESU10102"].name == "Emissions Compliance Rate"


def test_shared_codes_resolve():
    """Shared perf JSON is bundled and loaded alongside ESGRC's and Customer's."""
    m = load_label_map()
    assert m["SHRD_001"].name == "Shared"
    assert m["SHRD_001"].level == "module"
    assert m["PVD10000"].name == "Privacy Development"
    assert m["PVD10000"].level == "sub_module"
    assert m["PVD10102"].level == "metric"


def test_bspt_codes_resolve():
    """Business Partner perf JSON is bundled and loaded."""
    m = load_label_map()
    assert m["BSPT_001"].name == "Business Partner"
    assert m["BSPT_001"].level == "module"
    assert m["BSP10000"].name == "Business Partner Strategy & Planning"
    assert m["BSP10000"].level == "sub_module"
    assert m["BSP10102"].level == "metric"


def test_group_name_ordinal_prefix_is_stripped():
    """
    Shared and Business Partner prefix every group name with a display ordinal
    ("1. Partner Recruitment"); ESGRC and Customer prefix none. The digit would
    break the numeric-integrity gate - substituting the code injects a number the
    code text never had, so gate B fails and the labelled report is thrown away.
    load_label_map strips the prefix; this pins that behaviour, and
    test_no_business_name_contains_a_digit is the backstop across all modules.
    """
    m = load_label_map()
    assert m["BSP10101"].name == "Partner Recruitment"     # was "1. Partner Recruitment"
    assert m["PVD10101"].name == "Privacy Policy Development"  # was "1. Privacy Policy Development"
    assert m["BSP10101"].level == "group"


def test_no_business_name_contains_a_digit():
    """
    The numeric-integrity gate in validate_labeling assumes business names are
    digit-free, so stripping codes leaves only data numbers. If a future module's
    perf JSON breaks that assumption, the gate silently starts comparing name
    digits against data digits - catch it here instead.
    """
    import re
    offenders = {c: e.name for c, e in load_label_map().items() if re.search(r"\d", e.name)}
    assert offenders == {}


def test_known_codes_resolve_to_expected_names():
    m = load_label_map()
    assert m["ESU10102"].name == "Emissions Compliance Rate"
    assert m["ESU10102"].level == "metric"
    assert m["GRC10101"].name == "Risk Identification Group"
    assert m["GRC10101"].level == "group"
    assert m["GRC10000"].level == "sub_module"
    assert m["ESRC_001"].level == "module"


# ── Substitution ─────────────────────────────────────────────────────────────

def test_codes_replaced_with_names():
    res = label_output("ESU10102 scored 72/100 and correlates with CSU10102 (r=0.83).")
    assert res.status == "ok"
    assert "ESU10102" not in res.labeled_text
    assert "Emissions Compliance Rate" in res.labeled_text
    assert "Average Patching Time" in res.labeled_text


def test_legend_lists_codes_in_first_appearance_order():
    res = label_output("GRC10101 then ERM10101 then GRC10101 again.")
    codes = [item["code"] for item in res.labels]
    assert codes == ["GRC10101", "ERM10101"]  # deduped, ordered, no repeat
    assert {item["name"] for item in res.labels} == {
        "Risk Identification Group",
        "Risk Strategy Group",
    }


def test_numbers_are_preserved_by_substitution():
    text = "ESU10102 scored 72/100, r=0.83, p<0.01, 8 points."
    res = label_output(text)
    for token in ("72", "100", "0.83", "0.01", "8"):
        assert token in res.labeled_text


# ── Validation gate ──────────────────────────────────────────────────────────

def test_gate_fails_on_changed_number():
    m = load_label_map()
    ok, issues = validate_labeling("ESU10102 r=0.83", "Emissions Compliance Rate r=0.99", m)
    assert ok is False
    assert any("numeric integrity" in i for i in issues)


def test_gate_fails_on_leftover_known_code():
    m = load_label_map()
    ok, issues = validate_labeling(
        "ESU10102 and CSU10102", "Emissions Compliance Rate and CSU10102", m
    )
    assert ok is False
    assert any("unsubstituted" in i for i in issues)


def test_unmapped_code_warns_but_does_not_fail():
    res = label_output("Value ZZZ99999 and ESU10102 here.")
    assert res.status == "ok"                 # unmapped is a warning, not a failure
    assert res.unmapped_codes == ["ZZZ99999"]
    assert "ZZZ99999" in res.labeled_text     # left as-is


# ── Markdown-escaped module ids ──────────────────────────────────────────────
# Claude writes module ids as "BSPT\_001", escaping the underscore so markdown
# does not start an italic run. Before CODE_RE tolerated the backslash these
# matched nothing: not substituted, and not reported as unmapped either, so a
# report came back status="ok" with unmapped=0 while raw codes stayed visible.
# Seen on a real Apex run 2026-08-04.

def test_escaped_module_id_is_matched_and_labelled():
    res = label_output(r"Modules Analysed: 3 (BSPT\_001, SHRD\_001, ESRC\_001).")
    assert res.status == "ok"
    # Legend reports the plain form, never the escaped one.
    assert [item["code"] for item in res.labels] == ["BSPT_001", "SHRD_001", "ESRC_001"]
    assert res.unmapped_codes == []
    assert "Business Partner" in res.labeled_text
    assert "Shared" in res.labeled_text
    assert "\\_001" not in res.labeled_text     # nothing escaped left behind


def test_escaped_and_plain_module_ids_resolve_identically():
    plain = label_output("Module BSPT_001 review.")
    escaped = label_output(r"Module BSPT\_001 review.")
    assert plain.labeled_text == escaped.labeled_text
    assert [i["code"] for i in plain.labels] == [i["code"] for i in escaped.labels]


# ── Source-of-truth invariant ─────────────────────────────────────────────────

def test_module_mapping_single_source_of_truth():
    """pipeline/llm/data/module_mapping.csv is the only local copy.
    modules/apex/reference_data/module_mapping.csv must not exist; if it
    drifts from pipeline/llm/data/ the regression script gets stale data."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent.parent
    duplicate = repo_root / "modules" / "apex" / "reference_data" / "module_mapping.csv"
    assert not duplicate.exists(), (
        "modules/apex/reference_data/module_mapping.csv must not exist. "
        "pipeline/llm/data/module_mapping.csv is the single source of truth; "
        "upload that file when seeding R2."
    )


def test_escaped_unmapped_code_reported_in_canonical_form():
    res = label_output(r"Unknown ZZZ\_999 stays put.")
    assert res.status == "ok"
    assert res.unmapped_codes == ["ZZZ_999"]   # canonical, not "ZZZ\\_999"
    assert r"ZZZ\_999" in res.labeled_text     # original span untouched


def test_escaped_leftover_code_trips_gate_a():
    """A known code left behind still fails gate A even when markdown-escaped."""
    m = load_label_map()
    ok, issues = validate_labeling(
        "BSPT_001 and ESU10102", r"BSPT\_001 and Emissions Compliance Rate", m
    )
    assert ok is False
    assert any("unsubstituted" in i for i in issues)


def test_escaped_module_id_preserves_numeric_integrity():
    """Gate B must still pass: the 001 is stripped from both sides consistently."""
    res = label_output(r"BSPT\_001 scored 72/100 with r=0.83 across 8 points.")
    assert res.status == "ok"
    assert res.issues == []
    for token in ("72", "100", "0.83", "8"):
        assert token in res.labeled_text


def test_empty_and_none_are_skipped():
    assert label_output("").status == "skipped"
    assert label_output(None).status == "skipped"
    assert label_output("   ").status == "skipped"


# ── Realistic seeded report ──────────────────────────────────────────────────

def test_seed_report_labels_cleanly():
    res = label_output(SEED_REPORT)
    assert res.status == "ok"
    # our codes are substituted
    assert "GRC10101" not in res.labeled_text
    assert "ERM10101" not in res.labeled_text
    assert "Risk Identification Group" in res.labeled_text
    assert "Risk Strategy Group" in res.labeled_text
    # legend captured both
    assert {i["code"] for i in res.labels} == {"GRC10101", "ERM10101"}


def test_seed_report_leaves_non_codes_untouched():
    res = label_output(SEED_REPORT)
    # "GRI 305-2" is a regulatory standard, not one of our codes: CODE_RE must not
    # match it, and it must survive substitution verbatim.
    assert not CODE_RE.findall("GRI 305-2")
    assert "GRI 305-2" in res.labeled_text
    # key data numbers survive verbatim
    for token in ("6/10", "72/100", "0.78", "34%", "90"):
        assert token in res.labeled_text
