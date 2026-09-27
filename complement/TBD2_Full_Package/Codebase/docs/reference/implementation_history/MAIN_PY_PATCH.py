"""
pipeline/MAIN_PY_PATCH.py
─────────────────────────────────────────────────────────────
EXACT CHANGES TO APPLY TO ESGRC/main.py  (3 locations)
─────────────────────────────────────────────────────────────

LOCATION 1 - top of file, after existing router imports
────────────────────────────────────────────────────────
ADD after the existing `from app.routers import ...` block:

    from pipeline.routers.pipeline_router import router as pipeline_router
    from pipeline.routers.copilot_router import router as copilot_router
    from pipeline.db import create_pipeline_tables
    from pipeline.middleware import add_pipeline_middleware


LOCATION 2 - inside lifespan(), after Base.metadata.create_all(bind=engine)
─────────────────────────────────────────────────────────────────────────────
ADD immediately after `Base.metadata.create_all(bind=engine)`:

    # Create pipeline tables (does not touch existing ESGRC tables)
    create_pipeline_tables()


LOCATION 3 - after existing app.include_router() calls
────────────────────────────────────────────────────────────────────────────────
ADD after the last existing app.include_router():

    app.include_router(pipeline_router, prefix="/pipelines", tags=["Pipeline"])
    app.include_router(copilot_router,  prefix="/copilot",   tags=["Co-Pilot"])
    add_pipeline_middleware(app)


─────────────────────────────────────────────────────────────
VERIFICATION (run after applying the patch)
─────────────────────────────────────────────────────────────

    # All 207 existing tests must still pass
    pytest test/ -q
    # Expected: 207 passed

    # Pipeline endpoints
    curl http://localhost:8000/pipelines
    # Expected: []

    # Co-Pilot endpoint
    curl -X POST http://localhost:8000/copilot/message \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"message":"What are my top risks?"}'
    # Expected: {"run_id":"...","session_id":"...","status":"streaming"}

    # Swagger shows Pipeline + Co-Pilot sections
    open http://localhost:8000/docs

    # Rate limiting active
    for i in $(seq 1 65); do
      curl -s -o /dev/null -w "%{http_code}\\n" http://localhost:8000/pipelines
    done
    # Expected: first 60 return 200, request 61+ returns 429
─────────────────────────────────────────────────────────────
"""
