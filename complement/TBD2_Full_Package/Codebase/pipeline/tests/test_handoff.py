"""
pipeline/test/test_handoff.py
Unit tests for the module-handoff auto-copy + provenance layer (pipeline/tasks/r2.py).

A module pipeline (ESGRC today) copies its data_for_risk_assessment_{module}.csv to
the stable Apex handoff path and writes a provenance manifest (source run + timestamp)
beside it. Apex Step 1 consumes the CSV and can read the manifest for data freshness.
"""
import json
import os
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest

import pipeline.tasks.r2 as r2


@pytest.fixture
def fake_r2():
    """In-memory R2: patches the write/read/exists seam with a dict-backed store."""
    store = {}

    def up_file(local, key):
        with open(local, encoding="utf-8") as f:
            store[key] = f.read()
        return key

    def dl_text(key):
        if key not in store:
            raise r2.R2Error(f"missing {key}")
        return store[key]

    def exists(key):
        return key in store

    with patch.object(r2, "upload_file", side_effect=up_file), \
         patch.object(r2, "download_text", side_effect=dl_text), \
         patch.object(r2, "file_exists", side_effect=exists):
        yield store


def _make_csv() -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
    f.write("metric,value\nESU10102,72\n")
    f.close()
    return f.name


# ── Key helpers ──────────────────────────────────────────────────────────────

def test_key_helpers():
    assert r2.module_handoff_csv_key("9", "esgrc") == \
        "org/9/module_outputs/data_for_risk_assessment_esgrc.csv"
    assert r2.module_manifest_key("9", "esgrc") == \
        "org/9/module_outputs/data_for_risk_assessment_esgrc.manifest.json"


# ── write_module_handoff ─────────────────────────────────────────────────────

def test_write_handoff_uploads_csv_and_manifest(fake_r2):
    csv = _make_csv()
    try:
        res = r2.write_module_handoff(csv, "7", "esgrc", "run-abc",
                                      produced_at="2026-07-15T12:00:00+00:00")
    finally:
        os.unlink(csv)

    assert res["csv_key"] in fake_r2
    assert res["manifest_key"] in fake_r2
    manifest = json.loads(fake_r2[res["manifest_key"]])
    assert manifest["module"] == "esgrc"
    assert manifest["source_run_id"] == "run-abc"
    assert manifest["produced_at"] == "2026-07-15T12:00:00+00:00"
    assert manifest["schema_version"] == r2.HANDOFF_SCHEMA_VERSION
    # the CSV content is copied verbatim
    assert "ESU10102,72" in fake_r2[res["csv_key"]]


def test_write_handoff_default_timestamp_is_iso(fake_r2):
    csv = _make_csv()
    try:
        res = r2.write_module_handoff(csv, "7", "esgrc", "run-xyz")
    finally:
        os.unlink(csv)
    # default produced_at parses as an ISO-8601 timestamp
    parsed = datetime.fromisoformat(res["produced_at"])
    assert parsed.tzinfo is not None  # timezone-aware (UTC)


def test_write_handoff_cleans_up_temp_manifest_file(fake_r2):
    csv = _make_csv()
    before = set(os.listdir(tempfile.gettempdir()))
    try:
        r2.write_module_handoff(csv, "7", "esgrc", "run-abc")
    finally:
        os.unlink(csv)
    after = set(os.listdir(tempfile.gettempdir()))
    leaked = [f for f in (after - before) if f.endswith(".manifest.json")]
    assert leaked == []


# ── read_module_handoff_manifest ─────────────────────────────────────────────

def test_read_manifest_roundtrip(fake_r2):
    csv = _make_csv()
    try:
        r2.write_module_handoff(csv, "7", "esgrc", "run-abc",
                                produced_at="2026-07-15T12:00:00+00:00")
    finally:
        os.unlink(csv)
    m = r2.read_module_handoff_manifest("7", "esgrc")
    assert m is not None
    assert m["source_run_id"] == "run-abc"


def test_read_manifest_absent_returns_none(fake_r2):
    assert r2.read_module_handoff_manifest("7", "esgrc") is None


def test_read_manifest_corrupt_returns_none(fake_r2):
    fake_r2[r2.module_manifest_key("7", "esgrc")] = "{not valid json"
    assert r2.read_module_handoff_manifest("7", "esgrc") is None


# ── get_apex_handoff_provenance ──────────────────────────────────────────────

def test_provenance_lists_all_modules_with_present_flags(fake_r2):
    csv = _make_csv()
    try:
        r2.write_module_handoff(csv, "7", "esgrc", "run-abc",
                                produced_at="2026-07-15T12:00:00+00:00")
    finally:
        os.unlink(csv)

    prov = r2.get_apex_handoff_provenance("7")
    assert len(prov) == len(r2.APEX_MODULE_NAMES)  # one entry per known module

    by_module = {p["module"]: p for p in prov}
    assert by_module["esgrc"]["present"] is True
    assert by_module["esgrc"]["produced_at"] == "2026-07-15T12:00:00+00:00"
    assert by_module["esgrc"]["source_run_id"] == "run-abc"
    # a module that never produced a handoff
    assert by_module["brand"]["present"] is False
    assert by_module["brand"]["produced_at"] is None


def test_provenance_present_without_manifest(fake_r2):
    # CSV exists but no manifest (e.g. a pre-existing handoff from before this feature)
    fake_r2[r2.module_handoff_csv_key("7", "customer")] = "data"
    prov = {p["module"]: p for p in r2.get_apex_handoff_provenance("7")}
    assert prov["customer"]["present"] is True
    assert prov["customer"]["produced_at"] is None


# ── Per-module handoff coverage ──────────────────────────────────────────────
# Definition-of-done item 5 in docs/analytics/MODULE_REPLICATION_TEMPLATE.md: every module
# that comes online gets handoff coverage here, not just a chain e2e. The handoff
# is the ONLY thing that makes a module visible to the Apex roll-up, so a module
# whose token drifts from APEX_MODULE_NAMES would still pass its own e2e while
# silently never reaching Apex. Parameterised so the next module is one string.

@pytest.mark.parametrize("module", ["esgrc", "customer", "shared", "bspt"])
def test_handoff_roundtrip_per_module(fake_r2, module):
    """Write -> manifest -> provenance, for every module built so far."""
    csv = _make_csv()
    try:
        r2.write_module_handoff(csv, "7", module, f"run-{module}",
                                produced_at="2026-08-04T09:00:00+00:00")
    finally:
        os.unlink(csv)

    # The CSV landed at the stable path Apex step 1 globs.
    assert r2.module_handoff_csv_key("7", module) in fake_r2

    manifest = r2.read_module_handoff_manifest("7", module)
    assert manifest is not None
    assert manifest["module"] == module
    assert manifest["source_run_id"] == f"run-{module}"

    prov = {p["module"]: p for p in r2.get_apex_handoff_provenance("7")}
    assert prov[module]["present"] is True
    assert prov[module]["produced_at"] == "2026-08-04T09:00:00+00:00"
    assert prov[module]["source_run_id"] == f"run-{module}"


@pytest.mark.parametrize("module", ["shared", "bspt"])
def test_new_module_tokens_are_known_to_apex(module):
    """
    The chain's MODULE constant, APEX_MODULE_NAMES and apex_chord's
    MODULE_CSV_NAMES must agree, or the handoff is written somewhere Apex never
    looks. Verified live on 2026-08-04, pinned here so a rename cannot break it
    without failing a test.
    """
    from pipeline.tasks import apex_chord

    assert module in r2.APEX_MODULE_NAMES
    assert f"data_for_risk_assessment_{module}.csv" in apex_chord.MODULE_CSV_NAMES


@pytest.mark.parametrize(
    "module,chain_module",
    [("shared", "pipeline.tasks.shared_chain"), ("bspt", "pipeline.tasks.bspt_chain")],
)
def test_new_module_chain_declares_matching_token(module, chain_module):
    """The chain's own MODULE constant is what gets passed to write_module_handoff."""
    import importlib

    assert importlib.import_module(chain_module).MODULE == module
