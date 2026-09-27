"""
pipeline/test/test_modules_registry.py

Guards the module registry (pipeline/modules.py) against the things it cannot
enforce for itself.

Most per-module wiring is now derived from MODULES by a loop. Four things still
have to be written by hand for each new module, because they cannot be generated:

  1. the PipelineTypeEnum member (Python enum members are class attributes and
     SQLAlchemy resolves them statically)
  2. an alembic migration adding the value to the PostgreSQL enum type (DDL)
  3. the frontend PipelineType union (compile-time TypeScript)
  4. a Dockerfile COPY line for the module's analytics scripts (the build context
     cannot iterate a Python list)

Each of those is a silent failure if forgotten: the module simply never runs, or
runs and cannot be stored, or renders with the wrong labels. These tests turn
every one of them into a failing test instead.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipeline.models import PipelineTypeEnum
from pipeline.modules import (
    APEX_PIPELINE_TYPE,
    MODULES,
    factory_built_modules,
    module_for_pipeline_type,
    module_scope_map,
    perf_json_filenames,
    step_counts,
)

REPO = Path(__file__).resolve().parents[2]


# ── 1. Enum parity (hand-written, must not drift) ────────────────────────────

@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_every_module_has_a_pipeline_type_enum_member(spec):
    assert spec.pipeline_type in PipelineTypeEnum.__members__, (
        f"{spec.token}: add {spec.pipeline_type} to PipelineTypeEnum in pipeline/models.py"
    )
    assert PipelineTypeEnum(spec.pipeline_type).value == spec.pipeline_type


def test_every_module_enum_member_has_a_module_spec():
    """The reverse direction - an enum value with no spec is dead wiring."""
    module_values = {
        v for v in PipelineTypeEnum.__members__ if v != APEX_PIPELINE_TYPE
    }
    registered = {m.pipeline_type for m in MODULES}
    assert module_values == registered, (
        f"enum and registry disagree: only-in-enum={module_values - registered}, "
        f"only-in-registry={registered - module_values}"
    )


def test_apex_is_a_pipeline_type_but_not_a_module():
    assert APEX_PIPELINE_TYPE in PipelineTypeEnum.__members__
    assert module_for_pipeline_type(APEX_PIPELINE_TYPE) is None


# ── 2. Alembic migration for the Postgres enum type ─────────────────────────

def test_every_pipeline_type_is_added_by_some_migration():
    """
    On PostgreSQL the enum type only gains values via ALTER TYPE ... ADD VALUE.
    A module whose value was never migrated works on SQLite and fails in prod.
    ESGRC_MODULE and APEX_ENTERPRISE came with the original CREATE TYPE.
    """
    versions = REPO / "ESGRC" / "alembic" / "versions"
    migrated = set()
    for path in versions.glob("*.py"):
        # Match the value in either quote style, and whether it is inlined into
        # the ALTER TYPE string or (as the 2026-08-04 migration does) iterated as
        # an f-string over a tuple of names. Anchoring on the ALTER TYPE text only
        # would silently miss the loop form and report a false failure.
        text = path.read_text(encoding="utf-8")
        if "ALTER TYPE pipelinetypeenum" not in text:
            continue
        migrated.update(re.findall(r"[\"']([A-Z][A-Z_]*_MODULE)[\"']", text))

    original = {"ESGRC_MODULE", APEX_PIPELINE_TYPE}
    for spec in MODULES:
        if spec.pipeline_type in original:
            continue
        assert spec.pipeline_type in migrated, (
            f"{spec.token}: no alembic migration adds {spec.pipeline_type} to "
            f"pipelinetypeenum - it will fail on PostgreSQL"
        )


# ── 3. Frontend parity ───────────────────────────────────────────────────────

def test_frontend_pipeline_type_union_matches_the_registry():
    src = (REPO / "frontend" / "src" / "store" / "pipeline.ts").read_text(encoding="utf-8")
    lines = src.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("export type PipelineType")),
        None,
    )
    assert start is not None, "could not find the PipelineType union in frontend/src/store/pipeline.ts"

    # The union spans multiple lines once there are enough members to wrap, so
    # consume the declaration plus any following continuation lines beginning
    # with '|'. Matching a single line silently under-read the union and passed
    # while five module types were missing from it.
    body = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip().startswith("|"):
            body.append(line)
        else:
            break
    declared = set(re.findall(r"'([A-Z_]+)'", "\n".join(body)))

    expected = {m.pipeline_type for m in MODULES} | {APEX_PIPELINE_TYPE}
    assert declared == expected, (
        f"frontend PipelineType union is out of sync: missing={expected - declared}, "
        f"extra={declared - expected}"
    )


def test_frontend_has_step_labels_for_every_pipeline_type():
    src = (REPO / "frontend" / "src" / "pages" / "PipelinePage.tsx").read_text(encoding="utf-8")
    match = re.search(r"STEP_NAMES_BY_TYPE[^{]*\{(.*?)\n\}", src, re.DOTALL)
    assert match, "could not find STEP_NAMES_BY_TYPE in PipelinePage.tsx"
    declared = set(re.findall(r"^\s*([A-Z_]+):", match.group(1), re.MULTILINE))

    expected = {m.pipeline_type for m in MODULES} | {APEX_PIPELINE_TYPE}
    assert declared == expected, (
        f"frontend step labels out of sync: missing={expected - declared}, "
        f"extra={declared - expected}"
    )


# ── 4. Dockerfile COPY per module ────────────────────────────────────────────

@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_dockerfile_copies_the_modules_analytics_scripts(spec):
    dockerfile = (REPO / "pipeline" / "Dockerfile").read_text(encoding="utf-8")
    copies = re.findall(r"^COPY\s+(\S+)/analytics_scripts/\*\.py", dockerfile, re.MULTILINE)
    # Compare the module directory name only, not the path to it. The modules
    # moved under modules/ on 2026-08-08, which made the captured value
    # "modules/ESGRC" rather than "ESGRC" and failed every case here.
    dirs = {c.rsplit("/", 1)[-1].lower() for c in copies}
    assert spec.token in dirs, (
        f"{spec.token}: pipeline/Dockerfile has no COPY for its analytics_scripts - "
        f"the worker image will not contain its scripts. Found: {sorted(dirs)}"
    )


def test_dockerfile_copies_apex_analytics_scripts():
    """Apex L0 scripts live in modules/apex/analytics_scripts/; the pipeline
    Dockerfile must have a COPY line for them or the worker image will be missing
    all_module_low_perf, correlation_CHAID_L0, SPC_RPN_L0, and regression_L0."""
    dockerfile = (REPO / "pipeline" / "Dockerfile").read_text(encoding="utf-8")
    copies = re.findall(r"^COPY\s+(\S+)/analytics_scripts/\*\.py", dockerfile, re.MULTILINE)
    dirs = {c.rsplit("/", 1)[-1].lower() for c in copies}
    assert "apex" in dirs, (
        "pipeline/Dockerfile is missing COPY modules/apex/analytics_scripts/*.py - "
        "the worker image will not contain the Apex L0 scripts."
    )


# ── Registry-derived wiring is internally consistent ─────────────────────────

@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_every_module_has_its_five_registry_keys(spec):
    registry = json.loads(
        (REPO / "pipeline" / "scripts" / "scripts_registry.json").read_text(encoding="utf-8")
    )["scripts"]
    # ESGRC's keys are the original unprefixed ones (data_prep_1, SPC_RPN, ...);
    # every module added since is {token}_{step}.
    if spec.token == "esgrc":
        pytest.skip("ESGRC uses the original unprefixed registry keys")
    for step in ("data_prep_1", "data_prep_2", "correlation", "spc_rpn", "regression"):
        assert spec.script_key(step) in registry, (
            f"missing scripts_registry.json key {spec.script_key(step)}"
        )


@pytest.mark.parametrize("spec", MODULES, ids=lambda s: s.token)
def test_every_module_has_its_perf_json_bundled(spec):
    assert (REPO / "pipeline" / "llm" / "data" / spec.perf_json).exists()
    assert spec.perf_json in perf_json_filenames()


@pytest.mark.parametrize("spec", factory_built_modules(), ids=lambda s: s.token)
def test_factory_built_chain_exposes_the_conventional_names(spec):
    """
    pipeline_router resolves build_{token}_chain / {token}_step7_claude /
    {TOKEN}_STEP_TASKS by convention, so a chain that drops one breaks triggering
    at runtime rather than at import.
    """
    import importlib

    mod = importlib.import_module(spec.chain_module)
    assert mod.MODULE == spec.token
    assert callable(getattr(mod, f"build_{spec.token}_chain"))
    assert getattr(mod, f"{spec.token}_step7_claude") is not None
    step_tasks = getattr(mod, f"{spec.token.upper()}_STEP_TASKS")
    assert sorted(step_tasks) == [1, 2, 3, 4, 5, 6, 7]


@pytest.mark.parametrize("spec", factory_built_modules(), ids=lambda s: s.token)
def test_factory_built_tasks_keep_their_celery_names(spec):
    """
    Task names are the wire format. Renaming one silently orphans queued work and
    breaks the worker's routing, so they are pinned here.
    """
    import importlib

    from pipeline.celery_app import app

    importlib.import_module(spec.chain_module)
    for n in range(1, 8):
        assert f"pipeline.{spec.token}.step{n}" in app.tasks
    assert f"pipeline.{spec.token}.chord_error_handler" in app.tasks


def test_derived_wiring_covers_every_module_plus_apex():
    expected = {m.pipeline_type for m in MODULES} | {APEX_PIPELINE_TYPE}
    assert set(step_counts()) == expected
    assert set(module_scope_map()) == {m.token for m in MODULES} | {"apex"}
    assert all(count == 7 for m, count in step_counts().items() if m != APEX_PIPELINE_TYPE)
    assert step_counts()[APEX_PIPELINE_TYPE] == 8


def test_module_tokens_are_unique_and_lowercase():
    tokens = [m.token for m in MODULES]
    assert len(tokens) == len(set(tokens))
    assert all(t.islower() and t.isalnum() for t in tokens)


# ── Registry integrity ───────────────────────────────────────────────────────
# These guard the scripts registry itself, not the module wiring. Every failure
# here is a runtime error on a real run, and none of them is visible by reading
# the JSON casually.

def _registry():
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "scripts_registry.json"
    return json.loads(path.read_text(encoding="utf-8"))["scripts"]


def test_output_file_pattern_keys_exist_in_output_files():
    """A pattern key must name a declared output, or the glob is never consulted.

    script_runner does glob_patterns.get(stable_name). If the key does not match
    a name in output_files/optional_output_files the lookup misses silently,
    script_runner falls back to looking for the UNDATED filename, the script
    never wrote that, and the step dies with ScriptOutputMissingError.

    This is not hypothetical. All seven modules added on 6-7 Aug shipped with
    keys still naming 'shared', because the registry entries were cloned from
    Shared and the retokeniser rewrote dict VALUES but not dict KEYS. Every one
    of them would have failed at step 4 on its first real run.
    """
    broken = []
    for key, cfg in _registry().items():
        declared = set(cfg.get("output_files", [])) | set(
            cfg.get("optional_output_files", [])
        )
        for pattern_key in (cfg.get("output_file_patterns") or {}):
            if pattern_key not in declared:
                broken.append(f"{key}: pattern key {pattern_key!r} is not a declared output")
    assert not broken, "orphaned output_file_patterns keys:\n  " + "\n  ".join(broken)


def test_no_registry_entry_references_another_module():
    """Cloning a module's entries must not leave the source module's token behind.

    Catches the same copy-paste failure in the other direction: an entry whose
    script_filename or output names still say 'shared' after being cloned for a
    different module. That already happened once with the SPC scripts, where
    every *_spc_rpn pointed at x_bar_r_chart_fmea_shared_5_0.py.
    """
    from pipeline.modules import MODULES

    tokens = {m.token for m in MODULES}
    offenders = []
    for key, cfg in _registry().items():
        token = key.split("_")[0]
        if token not in tokens:
            continue  # apex / L0 / shared-helper entries use their own naming
        blob = " ".join(
            [cfg.get("script_filename", "")]
            + list(cfg.get("output_files", []))
            + list(cfg.get("optional_output_files", []))
            + list((cfg.get("output_file_patterns") or {}).keys())
            + list((cfg.get("output_file_patterns") or {}).values())
        ).lower()
        for other in tokens - {token}:
            # Word-ish boundary: '_other.' / '_other_' / '_other' at the end.
            import re
            if re.search(rf"_{re.escape(other)}(?![a-z])", blob):
                offenders.append(f"{key} references module {other!r}")
    assert not offenders, "cross-module registry references:\n  " + "\n  ".join(offenders)


def test_every_registry_script_file_exists():
    """A registry entry pointing at a missing file fails with FileNotFoundError
    only when that step runs, which on a 7-step chain can be minutes in."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    missing = []
    for key, cfg in _registry().items():
        fn = cfg.get("script_filename")
        if not fn:
            continue
        if not list(repo.glob(f"modules/*/analytics_scripts/{fn}")) and not list(
            repo.glob(f"pipeline/scripts/{fn}")
        ):
            missing.append(f"{key}: {fn}")
    assert not missing, "registry points at missing scripts:\n  " + "\n  ".join(missing)
