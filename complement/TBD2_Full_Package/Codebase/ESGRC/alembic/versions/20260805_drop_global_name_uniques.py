"""drop stale global UNIQUE(name) on esg_categories and compliance_frameworks

The initial schema (1b087c059d7e) created these tables single-tenant, with a
bare sa.UniqueConstraint('name'). Tenancy came later: e2a54ef84063 added org_id
and 07256f6eed55 added the composite uq_*_org_name - but nothing ever dropped
the original global constraint, and batch mode faithfully reproduced it on every
subsequent SQLite rebuild.

Effect on a migrated database: two organisations cannot both have a category or
framework of the same name. Org B creating "GRI Standards" after Org A gets an
IntegrityError, which crud.py catches and reports as "already exists in your
organisation" - a message that is actively misleading, since it exists in a
different tenant the caller cannot see. It also leaks the existence of another
tenant's data and lets the first org squat common framework names.

The model (app/models/models.py) only ever declared the composite constraint, so
this migration brings the database in line with the ORM. The test suite never
caught the drift because conftest builds its schema with create_all from the
models rather than by running this chain.

Not touched here: esg_categories.metric_code stays globally unique on purpose -
pipeline codes are fixed and stable across all orgs (see models.py).

Revision ID: 20260805_drop_global_uniques
Revises: 20260804_shared_bspt_types
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import MetaData, Table, UniqueConstraint

revision = "20260805_drop_global_uniques"
down_revision = "20260804_shared_bspt_types"
branch_labels = None
depends_on = None

TABLES = ("esg_categories", "compliance_frameworks")
COLUMN = "name"


def _global_name_uniques(table: Table) -> list[UniqueConstraint]:
    """Unique constraints covering exactly (name,).

    Matching on the exact column list is what keeps the per-org composite
    (org_id, name) and any other unique constraint out of the result.
    """
    return [
        c
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
        and [col.name for col in c.columns] == [COLUMN]
    ]


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # PostgreSQL auto-named the constraint at CREATE TABLE time (normally
        # "<table>_name_key"). Discover it instead of hardcoding, so a database
        # restored under a different name is still cleaned up.
        for table in TABLES:
            rows = bind.execute(
                sa.text(
                    """
                    SELECT con.conname
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_attribute att
                      ON att.attrelid = rel.oid AND att.attnum = con.conkey[1]
                    WHERE rel.relname = :table
                      AND con.contype = 'u'
                      AND array_length(con.conkey, 1) = 1
                      AND att.attname = :column
                    """
                ),
                {"table": table, "column": COLUMN},
            ).fetchall()
            for (constraint_name,) in rows:
                op.drop_constraint(constraint_name, table, type_="unique")
        return

    # SQLite and anything else without ALTER TABLE ... DROP CONSTRAINT.
    # The constraint is unnamed, so it cannot be dropped by name at all; the
    # table has to be rebuilt without it. copy_from is what makes that possible:
    # without it, batch mode re-reflects the live table and faithfully recreates
    # the very constraint we are trying to remove.
    for table in TABLES:
        reflected = Table(table, MetaData(), autoload_with=bind)
        offenders = _global_name_uniques(reflected)
        if not offenders:
            # Schema built from the ORM (create_all) never had the constraint.
            continue
        for constraint in offenders:
            reflected.constraints.discard(constraint)
        with op.batch_alter_table(table, copy_from=reflected, recreate="always"):
            pass


def downgrade() -> None:
    # Intentionally not reversed. Restoring a global UNIQUE(name) fails outright
    # once two tenants legitimately share a category or framework name, which is
    # the exact state this migration exists to permit. Reversing it is therefore
    # a manual, data-dependent operation: deduplicate across orgs first, then
    # recreate the constraint by hand if it is genuinely wanted.
    pass
