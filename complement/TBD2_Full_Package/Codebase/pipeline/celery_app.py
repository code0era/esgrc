"""
pipeline/celery_app.py
Celery application factory for TBD2 pipeline workers.
"""
import os

# Load .env before reading any os.environ default (broker, DATABASE_URL, model
# ids). The worker process has no other entry point that would do this, so
# without it a local worker can diverge from the API's .env config.
# override=False so Docker/prod env vars still win.
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

from celery import Celery

from pipeline.modules import chain_module_paths

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")

# Eager mode: run tasks synchronously in the calling process instead of handing
# them to a separate worker. Used by the single-container demo deploy (HF Spaces)
# where there is no standalone Celery worker - the API triggers a pipeline and it
# executes inline. Never enable this in the real multi-service deployment.
EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"

app = Celery("tbd2_pipeline")

app.conf.update(
    broker_url=BROKER_URL,
    result_backend=RESULT_BACKEND,

    # Synchronous inline execution when no worker is available (demo container).
    task_always_eager=EAGER,

    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behaviour
    task_track_started=True,
    task_acks_late=True,           # Re-queue if worker dies mid-task
    worker_prefetch_multiplier=1,  # One task at a time per worker slot - important for long tasks

    # Result TTL - keep results 24 hours
    result_expires=86400,

    # Chord / group error propagation
    task_eager_propagates=True,

    # Auto-discover tasks in the tasks/ package
    imports=[
        # One entry per module, derived from pipeline/modules.py so a new module's
        # tasks register without editing this list.
        *chain_module_paths(),
        "pipeline.tasks.apex_chord",
        # Registers pipeline.copilot.stream_response on the worker. The Co-Pilot
        # endpoint enqueues this task; without the import the worker cannot execute
        # it (the pipeline image ships FastAPI, so importing the router is safe).
        "pipeline.routers.copilot_router",
    ],
)

# Beat schedule - add scheduled pipelines here
app.conf.beat_schedule = {}
