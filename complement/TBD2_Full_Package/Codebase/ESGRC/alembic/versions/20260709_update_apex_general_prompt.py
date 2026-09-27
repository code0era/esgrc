"""Update APEX_GENERAL_RISK prompt: regression drill-down (Module->Sub-Module->Group->Metric)

Revision ID: 20260709_apex_prompt_v2
Revises: 20260708_add_user_module_access
Create Date: 2026-07-09

Publishes a new active version of the GENERAL_RISK prompt (Apex Step 6). The new
prompt drives the Parent Module -> Sub-Module -> Group -> Metric drill-down with
correlation/impact traceability, now that the regression report is combined into
the general master (apex_chord.py step5 = [1, 2, 4]).

Version-safe: the previous active version is deactivated and the new content is
inserted as the next version, made active. On a FRESH DB the seed migration
(20260621) already inserts the current prompts.py text as v1, so this migration
detects the active content already matches and is a no-op (no duplicate version).
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# NOTE: revision id MUST be <= 32 chars - Alembic's alembic_version.version_num
# is VARCHAR(32) and Postgres enforces it (SQLite does not, so tests won't catch
# an over-long id). "20260709_apex_prompt_v2" is 23 chars.
revision = "20260709_apex_prompt_v2"
down_revision = "20260708_add_user_module_access"
branch_labels = None
depends_on = None

NAME = "GENERAL_RISK"


def _new_content() -> str:
    # Fail loudly if the import breaks - never seed placeholder text a client
    # could see as real prompt instructions.
    from pipeline.llm.prompts import APEX_GENERAL_RISK
    return APEX_GENERAL_RISK


def upgrade() -> None:
    conn = op.get_bind()
    new_content = _new_content()

    active = conn.execute(
        sa.text("SELECT content FROM pipeline_prompts WHERE name = :n AND is_active = :t LIMIT 1"),
        {"n": NAME, "t": True},
    ).fetchone()
    if active and active[0] == new_content:
        # Fresh DB (seed already inserted current text) - nothing to do.
        return

    maxv = conn.execute(
        sa.text("SELECT COALESCE(MAX(version), 0) FROM pipeline_prompts WHERE name = :n"),
        {"n": NAME},
    ).scalar() or 0

    conn.execute(
        sa.text("UPDATE pipeline_prompts SET is_active = :f WHERE name = :n AND is_active = :t"),
        {"f": False, "t": True, "n": NAME},
    )
    conn.execute(
        sa.text(
            "INSERT INTO pipeline_prompts (name, version, content, is_active, created_at) "
            "VALUES (:n, :v, :c, :t, :ts)"
        ),
        {"n": NAME, "v": maxv + 1, "c": new_content, "t": True,
         "ts": datetime.now(timezone.utc)},
    )


def downgrade() -> None:
    conn = op.get_bind()
    maxv = conn.execute(
        sa.text("SELECT COALESCE(MAX(version), 0) FROM pipeline_prompts WHERE name = :n"),
        {"n": NAME},
    ).scalar() or 0
    if maxv <= 1:
        return  # nothing this migration added
    conn.execute(
        sa.text("DELETE FROM pipeline_prompts WHERE name = :n AND version = :v"),
        {"n": NAME, "v": maxv},
    )
    conn.execute(
        sa.text("UPDATE pipeline_prompts SET is_active = :t WHERE name = :n AND version = :v"),
        {"t": True, "n": NAME, "v": maxv - 1},
    )
