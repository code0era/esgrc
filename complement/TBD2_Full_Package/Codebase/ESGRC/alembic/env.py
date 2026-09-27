"""
Alembic migration environment.

Key wiring decisions
─────────────────────
1. DATABASE_URL is read from app.config.settings - never from alembic.ini -
   so secrets are not stored in version-controlled config files.

2. target_metadata is set to Base.metadata so autogenerate can compare the
   current ORM models against the live database schema.

3. All model modules are imported explicitly before Base.metadata is used.
   Alembic autogenerate only sees tables that have been imported into the
   Python process; forgetting an import silently skips those tables.

4. run_migrations_online() uses NullPool so Alembic never holds an open
   connection between migration steps, which matters for transactional DDL
   databases (PostgreSQL) and for CI pipelines that run against fresh DBs.

5. compare_type=True tells autogenerate to detect column type changes, not
   just table/column additions and removals.

6. render_as_batch=True enables SQLite batch migration support (SQLite does
   not support ALTER COLUMN, so Alembic needs to recreate the table).
   This has no effect on PostgreSQL but allows the same migration files to
   run on both SQLite (dev/test) and PostgreSQL (production).
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Make the project root importable ──────────────────────────────────────────
# Alembic runs from the project root (where alembic.ini lives) but sys.path
# may not include it depending on how the command is invoked.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── App imports ───────────────────────────────────────────────────────────────
# Import settings first, then Base, then ALL model modules.
# The order matters: models depend on Base, Base depends on nothing app-specific.
from app.config import settings  # noqa: E402 - must come after sys.path fix
from app.database import Base    # noqa: E402

# Import every model module so their Table objects are registered on Base.metadata.
# If you add a new models file, add its import here.
import app.models.models  # noqa: F401 - side-effect import registers all tables

# ── Alembic config ────────────────────────────────────────────────────────────
config = context.config

# Wire in Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject DATABASE_URL from settings so alembic.ini never contains credentials.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# The metadata object autogenerate compares against.
target_metadata = Base.metadata


# ── Migration runners ─────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Emit migration SQL to stdout without a live DB connection.
    Useful for generating SQL scripts to review or apply manually.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations against a live database connection.
    NullPool ensures the connection is never held between migration steps.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
