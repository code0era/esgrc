"""Guard: every Alembic revision id must fit alembic_version.version_num (VARCHAR(32)).

Postgres enforces the 32-char limit; SQLite ignores it - so an over-long revision
id passes the SQLite-backed test suite but rolls back the migration on the real
Postgres DB (as happened with 20260709). This test scans the actual migration
files so the mismatch is caught in CI, not in production.
"""
import glob
import os
import re

VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
MAX_LEN = 32  # Alembic default alembic_version.version_num length


def test_all_revision_ids_within_varchar32():
    files = glob.glob(os.path.join(VERSIONS_DIR, "*.py"))
    assert files, f"no migration files found under {VERSIONS_DIR}"
    offenders = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for m in re.finditer(r'^revision\s*=\s*["\']([^"\']+)["\']', text, re.M):
            rid = m.group(1)
            if len(rid) > MAX_LEN:
                offenders.append((os.path.basename(path), rid, len(rid)))
    assert not offenders, (
        "revision ids exceed Alembic's VARCHAR(32) (they roll back on Postgres): "
        + "; ".join(f"{f}: {rid!r} ({n} chars)" for f, rid, n in offenders)
    )
