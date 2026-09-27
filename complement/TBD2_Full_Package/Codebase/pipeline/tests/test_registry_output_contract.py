"""
pipeline/test/test_registry_output_contract.py

Exercises the contract between the scripts registry and the analytics scripts,
for every module, using the REAL ScriptRunner._collect_outputs.

WHY THIS FILE EXISTS
--------------------
The per-module e2e tests (test_shared_e2e.py and friends) mock
script_runner.get_runner entirely and assert against a hardcoded dict of
expected filenames. That validates the Celery chain, but it means
_collect_outputs and its glob resolution are never executed, and the registry is
never compared to the scripts.

That gap let a real bug reach main: every module added 6-7 Aug had
output_file_patterns whose KEYS still said "shared", because the entries were
cloned from Shared by a script that rewrote dict values but not dict keys. The
lookup missed, _collect_outputs fell back to the undated filename that the SPC
scripts never write, and all seven modules would have died at step 4 with
ScriptOutputMissingError on their first real run. Standalone script runs passed,
the registry was valid JSON, and every other test was green.

These tests close that specific hole. They are fast: no analytics run, no Claude.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from pipeline.modules import MODULES

REPO = Path(__file__).resolve().parents[2]
REGISTRY = json.loads(
    (REPO / "pipeline" / "scripts" / "scripts_registry.json").read_text(encoding="utf-8")
)["scripts"]

STEPS = ("data_prep_1", "data_prep_2", "correlation", "spc_rpn", "regression")


def _registry_key(spec, step):
    """ESGRC predates the {token}_{step} convention and uses bare keys."""
    if spec.token == "esgrc":
        legacy = {
            "data_prep_1": "data_prep_1",
            "data_prep_2": "data_prep_2",
            "correlation": "correlation_CHAID",
            "spc_rpn": "SPC_RPN",
            "regression": "regression_esgrc",
        }
        return legacy[step]
    return f"{spec.token}_{step}"


def _script_path(filename):
    hits = list(REPO.glob(f"modules/*/analytics_scripts/{filename}"))
    return hits[0] if hits else None


def _filenames_written_by(script_src: str) -> set[str]:
    """Every literal filename the script writes.

    Deliberately derived from the SCRIPT, not from the registry, so the two are
    independent sources. Resolves the one f-string placeholder the analytics
    scripts use for dated outputs.
    """
    date = re.search(r'ANALYSIS_DATE\s*=\s*"([^"]+)"', script_src)
    date = date.group(1) if date else "2026-01-07"

    names = set()
    # Both quote styles. The analytics scripts assign most output names with
    # single quotes (source_file = 'module_values_shared.csv') and use double
    # quotes for the dated f-strings, so matching only one style finds nothing.
    for quote in ('"', "'"):
        pattern = rf"f?{quote}([^{quote}\n]*\.(?:txt|csv|pdf)){quote}"
        for m in re.finditer(pattern, script_src):
            raw = m.group(1)
            if "{" in raw:
                raw = raw.replace("{ANALYSIS_DATE}", date)
                if "{" in raw:      # some other placeholder we cannot resolve
                    continue
            # Comments and docstrings carry placeholders such as
            # data_for_risk_assessment_<module>.csv, which are not filenames and
            # cannot even be created on Windows.
            if any(ch in raw for ch in '<>*?:|"'):
                continue
            names.add(raw)
    return names


def _cases():
    out = []
    for spec in MODULES:
        for step in STEPS:
            key = _registry_key(spec, step)
            if key in REGISTRY:
                out.append(pytest.param(spec, step, key, id=f"{spec.token}-{step}"))
    return out


CASES = _cases()


@pytest.mark.parametrize("spec,step,key", CASES)
def test_declared_outputs_resolve_through_the_real_collector(spec, step, key, tmp_path):
    """Create exactly the files the script writes, then run the REAL collector.

    This is the test that would have caught the orphaned-pattern-key bug: with a
    wrong key the glob is never consulted, the collector looks for the undated
    name, and resolution fails.
    """
    from pipeline.tasks.script_runner import ScriptRunner, ScriptOutputMissingError

    cfg = REGISTRY[key]
    script = _script_path(cfg["script_filename"])
    assert script is not None, f"{key}: script {cfg['script_filename']} not found"

    written = _filenames_written_by(script.read_text(encoding="utf-8", errors="replace"))
    work = tmp_path / "work"
    work.mkdir()
    for name in written:
        (work / name).write_text("stub", encoding="utf-8")

    runner = ScriptRunner.__new__(ScriptRunner)  # no registry load needed
    try:
        resolved = runner._collect_outputs(key, cfg, str(work))
    except ScriptOutputMissingError as exc:
        pytest.fail(
            f"{key}: declared outputs did not resolve from what the script writes.\n"
            f"  script writes : {sorted(written)}\n"
            f"  registry wants: {cfg.get('output_files')}\n"
            f"  patterns      : {cfg.get('output_file_patterns')}\n"
            f"  error         : {exc}"
        )

    for declared in cfg.get("output_files", []):
        assert declared in resolved, f"{key}: {declared} missing from collector output"
        assert os.path.exists(resolved[declared])


@pytest.mark.parametrize("spec,step,key", CASES)
def test_every_glob_pattern_matches_something_the_script_writes(spec, step, key):
    """A pattern whose value no longer matches the script is dead.

    Complements the key check: a correct key with a stale value fails just as
    hard, and only at runtime.
    """
    import fnmatch

    cfg = REGISTRY[key]
    script = _script_path(cfg["script_filename"])
    written = _filenames_written_by(script.read_text(encoding="utf-8", errors="replace"))

    for stable, pattern in (cfg.get("output_file_patterns") or {}).items():
        assert any(fnmatch.fnmatch(n, pattern) for n in written), (
            f"{key}: pattern {pattern!r} (for {stable!r}) matches nothing the script "
            f"writes. Script writes: {sorted(written)}"
        )


@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_module_reference_data_is_present_and_loadable(spec):
    """The two files a module cannot run without, in the shape the contract needs.

    Guards the three data defects already seen: a module_id that is not
    [A-Z]{4}_001 (brand shipped "EBM"), a filename whose case only works on
    Windows (mkts shipped a capital I), and a BOM that makes json.load fail on
    character 0 (introduced by a PowerShell edit).
    """
    import csv

    # ESGRC predates the {Module}/reference_data/ convention: its two files sit
    # at the repo root. Every module added since keeps them in its own folder.
    candidates = list(REPO.glob(f"modules/*/reference_data/{spec.perf_json}"))
    if not candidates and (REPO / spec.perf_json).exists():
        candidates = [REPO / spec.perf_json]
    assert candidates, (
        f"{spec.token}: {spec.perf_json} is not in the repo. Every module needs its "
        f"reference data committed, or the module cannot be seeded on a fresh clone."
    )
    perf = candidates[0]

    raw = perf.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), (
        f"{spec.token}: {perf.name} has a UTF-8 BOM. The analytics scripts call "
        f"open(path) with no encoding, so json.load dies on character 0."
    )
    doc = json.loads(raw.decode("utf-8"))
    assert re.fullmatch(r"[A-Z]{4}_001", str(doc.get("module_id"))), (
        f"{spec.token}: module_id {doc.get('module_id')!r} is not [A-Z]{{4}}_001, so it "
        f"matches neither the L0 roll-up regex nor labeling's CODE_RE"
    )

    csv_path = perf.parent / spec.metrics_csv
    assert csv_path.exists(), f"{spec.token}: {spec.metrics_csv} missing"
    # Case-sensitivity: the on-disk name must match exactly, not just on Windows.
    assert csv_path.name in {p.name for p in perf.parent.iterdir()}, (
        f"{spec.token}: {spec.metrics_csv} case mismatch; fails on Linux"
    )

    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        header = next(csv.reader(fh))
    metrics = {
        m["metric_id"]
        for sm in doc.get("sub_modules", [])
        for g in sm.get("groups", [])
        for m in (g.get("value") or [])
    }
    undeclared = {c.strip() for c in header if c.strip()} - metrics
    assert not undeclared, (
        f"{spec.token}: {len(undeclared)} CSV columns are not declared in the JSON, "
        f"e.g. {sorted(undeclared)[:3]}. The analysis would carry columns with no "
        f"definition, which is how Integration was found to be incomplete."
    )


def _module_matrix_columns() -> dict:
    """{sub_module_id: owning module_id}, from modules/apex/reference_data/module_matrix.csv.

    Two parallel rows, not two columns: row 0 is every sub_module_id across all
    modules, row 1 is the module_id that owns the column at the same position.
    """
    import csv

    path = REPO / "modules" / "apex" / "reference_data" / "module_matrix.csv"
    with path.open(newline="", encoding="utf-8") as fh:
        header, owners = list(csv.reader(fh))
    return dict(zip(header, owners))


@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_module_is_present_in_apex_module_matrix(spec):
    """
    Every module's sub-modules must appear in module_matrix.csv, owned by its
    own module_id. ICTM was onboarded everywhere else (module_mapping.csv, the
    pipeline registry, all 11 other modules' analytics scripts) but was never
    added here - a silent gap, since nothing currently consumes this file's
    contents (AI_ready_Multiple_Regression_Model_implementation_L0_19_0.py
    loads it and never reads it again), so it wouldn't fail loudly until
    something finally does.
    """
    import json

    candidates = list(REPO.glob(f"modules/*/reference_data/{spec.perf_json}"))
    assert candidates, f"{spec.token}: {spec.perf_json} not found (see test above)"
    doc = json.loads(candidates[0].read_bytes().decode("utf-8"))
    module_id = doc.get("module_id")
    sub_module_ids = {sm["sub_module_id"] for sm in doc.get("sub_modules", [])}

    matrix = _module_matrix_columns()
    missing = sub_module_ids - matrix.keys()
    assert not missing, (
        f"{spec.token}: sub-module(s) {sorted(missing)} missing from "
        f"modules/apex/reference_data/module_matrix.csv entirely."
    )
    wrong_owner = {
        sm: matrix[sm] for sm in sub_module_ids if matrix[sm] != module_id
    }
    assert not wrong_owner, (
        f"{spec.token}: module_matrix.csv attributes {wrong_owner} to the wrong "
        f"module_id (expected {module_id})."
    )
