"""Cross-process file locks, used to make worker-duplicated startup work safe.

The API is served with `uvicorn --workers 2` (ESGRC/Dockerfile and the compose
api service). Uvicorn workers are independent OS processes and each one runs the
FastAPI lifespan in full, so anything done there happens twice:

  * `alembic upgrade head` ran concurrently in both workers, which races on
    PostgreSQL DDL locks.
  * `start_scheduler()` built a second APScheduler against the shared
    SQLAlchemyJobStore. APScheduler's `max_instances=1` is per-scheduler, not
    global, so both schedulers fired the daily batch and the compliance batch,
    producing duplicate AgentRunLog rows and double writes.

An OS file lock is the smallest thing that fixes both: workers in a container
share a filesystem, and the kernel releases the lock automatically if a worker
crashes, so there is no stale-lock cleanup to get wrong.

Scope: this coordinates processes on one host. It does NOT coordinate several
API containers. If the API is ever scaled past one replica, the scheduler needs
to move to its own single-replica service (or a Postgres advisory lock) - see
the note in app/agent/scheduler.py.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator, Optional

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"


def _lock_file(handle: IO, *, blocking: bool) -> bool:
    """Take an exclusive lock on an open file. False if held elsewhere."""
    try:
        if _IS_WINDOWS:
            import msvcrt

            mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
            msvcrt.locking(handle.fileno(), mode, 1)
        else:
            import fcntl

            flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
            fcntl.flock(handle.fileno(), flags)
        return True
    except OSError:
        # POSIX raises BlockingIOError, Windows raises OSError(EDEADLOCK) after
        # exhausting its retries. Both mean: someone else holds it.
        return False


def _unlock_file(handle: IO) -> None:
    try:
        if _IS_WINDOWS:
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:  # pragma: no cover - already gone, nothing to release
        pass


def acquire_forever(path: str | Path) -> Optional[IO]:
    """Claim `path` for the lifetime of this process.

    Returns the open handle on success (keep a reference: closing it releases
    the lock) or None if another process already holds it.

    Returns the handle if the lock file itself cannot be created. That is
    deliberately fail-open: an unwritable lock directory should degrade to the
    old duplicate-work behaviour, not silently disable scheduled jobs entirely.
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a+b")
    except OSError as exc:
        logger.warning(
            "Could not open scheduler lock file %s (%s); proceeding without "
            "single-instance protection",
            path,
            exc,
        )
        return _NullHandle()

    if not _lock_file(handle, blocking=False):
        handle.close()
        return None
    return handle


@contextmanager
def exclusive(path: str | Path) -> Iterator[None]:
    """Block until `path` is ours, run the body, then release.

    Used to serialise startup migrations: the first worker migrates while the
    others wait, then each of them runs an upgrade that is already a no-op.
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, "a+b")
    except OSError as exc:
        logger.warning(
            "Could not open lock file %s (%s); continuing unserialised", path, exc
        )
        yield
        return

    _lock_file(handle, blocking=True)
    try:
        yield
    finally:
        _unlock_file(handle)
        handle.close()


class _NullHandle:
    """Stand-in returned when locking is unavailable, so callers proceed."""

    def close(self) -> None:
        pass


def default_lock_path(name: str) -> Path:
    """Lock location, overridable so a container can point at a shared volume."""
    base = os.environ.get("ESGRC_LOCK_DIR")
    if base:
        return Path(base) / name
    import tempfile

    return Path(tempfile.gettempdir()) / name
