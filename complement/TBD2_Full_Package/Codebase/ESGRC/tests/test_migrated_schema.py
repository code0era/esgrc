"""Guard: assert the schema produced by the Alembic chain, not by create_all.

conftest builds its schema with Base.metadata.create_all, so every other test in
this suite validates the ORM's idea of the schema. Production runs the migration
chain instead (main.py lifespan). Anything the migrations do that the models do
not describe is therefore invisible to the rest of the suite - which is exactly
how a global UNIQUE(name) survived on esg_categories and compliance_frameworks
from the initial single-tenant schema through two tenancy migrations, silently
preventing two organisations from sharing a category or framework name.

These tests run the real chain into a throwaway SQLite database and assert on the
result, so that class of drift fails in CI instead of in a customer's tenant.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

ESGRC_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = ESGRC_DIR.parent

# Tables that were created single-tenant and later had org scoping bolted on.
ORG_SCOPED_BY_NAME = {
    "esg_categories": "uq_esg_categories_org_name",
    "compliance_frameworks": "uq_compliance_frameworks_org_name",
}


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory):
    """A SQLite database built by running `alembic upgrade head` for real.

    Run in a subprocess rather than via alembic's Python API because
    alembic/env.py injects settings.DATABASE_URL over whatever the caller
    configures, and app.config caches that value at import time. A subprocess
    with its own environment is both simpler and closer to how this actually
    runs in production.
    """
    db_path = tmp_path_factory.mktemp("migrated") / "schema.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        # Migrations import pipeline.llm.prompts to seed prompt rows.
        "PYTHONPATH": str(REPO_ROOT),
        # main.py refuses the placeholder key, and config requires one to load.
        "SECRET_KEY": "migration-test-only-secret-key-32-chars",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ESGRC_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic upgrade head failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    yield engine
    engine.dispose()


@pytest.mark.parametrize("table", sorted(ORG_SCOPED_BY_NAME))
def test_no_global_unique_on_name(migrated_db, table):
    """`name` must only ever be unique together with org_id, never on its own."""
    constraints = inspect(migrated_db).get_unique_constraints(table)
    offenders = [c for c in constraints if c["column_names"] == ["name"]]
    assert not offenders, (
        f"{table} has a unique constraint on `name` alone: {offenders}. "
        "That makes category/framework names globally unique across tenants, so "
        "one organisation can block or squat another's names."
    )


@pytest.mark.parametrize("table,expected", sorted(ORG_SCOPED_BY_NAME.items()))
def test_per_org_unique_still_present(migrated_db, table, expected):
    """Dropping the global constraint must not take the per-org one with it."""
    constraints = inspect(migrated_db).get_unique_constraints(table)
    composites = [c for c in constraints if set(c["column_names"]) == {"org_id", "name"}]
    assert composites, (
        f"{table} lost its per-org unique constraint ({expected}); duplicate "
        f"names within a single organisation would now be allowed. "
        f"Found: {constraints}"
    )


def test_metric_code_is_unique_per_org_not_globally(migrated_db):
    """metric_code is unique WITHIN an org, not across all orgs.

    Every org imports the same fixed set of pipeline codes (e.g. "ESU10102")
    via the standard CSV, so a global unique constraint let only the first
    org ever use each code - every other org's import 409'd on every
    standard code (see migration 20260817_metric_code_per_org). Pinned so a
    future change does not silently reintroduce the global constraint.
    """
    inspector = inspect(migrated_db)
    unique_cols = {
        tuple(sorted(c["column_names"])) for c in inspector.get_unique_constraints("esg_categories")
    } | {
        tuple(sorted(i["column_names"]))
        for i in inspector.get_indexes("esg_categories")
        if i.get("unique")
    }
    assert ("metric_code", "org_id") in unique_cols, (
        "esg_categories.metric_code is no longer unique per-org. "
        f"Found unique column sets: {sorted(unique_cols)}"
    )
    assert ("metric_code",) not in unique_cols, (
        "esg_categories.metric_code is globally unique again - this blocks "
        "every org after the first from using any standard pipeline code."
    )


def test_migrated_schema_matches_orm_tables(migrated_db):
    """The migration chain and the ORM must agree on which tables exist."""
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(ESGRC_DIR))
    from app.database import Base
    import app.models.models  # noqa: F401 - registers tables on Base.metadata

    migrated = set(inspect(migrated_db).get_table_names())
    orm = set(Base.metadata.tables)
    missing = orm - migrated
    assert not missing, (
        f"tables defined in the ORM but never created by a migration: {sorted(missing)}"
    )


def test_migrated_schema_matches_orm_columns(migrated_db):
    """Tables agreeing is not enough; the COLUMNS must agree too.

    The table-level check above passes even when a model gains a column that no
    migration adds. That gap is not theoretical, it has produced two production
    bugs already:

      - `prompt_id` was in the ORM and accepted by the API but silently dropped
        from the INSERT, so every row since 20260622 had NULL.
      - `REFRESH_TOKEN_EXPIRE_DAYS` was configured while the column that would
        enforce it did not exist, so refresh tokens never expired.

    Both work under SQLite `create_all`, which builds from the models, and fail
    or silently misbehave against a Postgres database built by the migration
    chain. conftest uses create_all, so only this file sees the real schema.
    """
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(ESGRC_DIR))
    from app.database import Base
    import app.models.models  # noqa: F401
    from pipeline.models import PipelineBase

    inspector = inspect(migrated_db)
    migrated_tables = set(inspector.get_table_names())

    drift = []
    for base, label in ((Base, "ESGRC"), (PipelineBase, "pipeline")):
        for name, table in base.metadata.tables.items():
            if name not in migrated_tables:
                continue  # covered by the table-level test above
            migrated_cols = {c["name"] for c in inspector.get_columns(name)}
            orm_cols = {c.name for c in table.columns}
            only_orm = orm_cols - migrated_cols
            only_migrated = migrated_cols - orm_cols
            if only_orm:
                drift.append(
                    f"{label}.{name}: in the ORM but no migration adds it: {sorted(only_orm)}"
                )
            if only_migrated:
                drift.append(
                    f"{label}.{name}: migrated but absent from the ORM: {sorted(only_migrated)}"
                )

    assert not drift, "ORM and migration chain disagree on columns:\n  " + "\n  ".join(drift)
