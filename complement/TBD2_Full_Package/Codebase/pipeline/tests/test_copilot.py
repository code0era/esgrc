"""
pipeline/test/test_copilot.py
Tests for the Co-Pilot backend endpoints.
"""
import json
import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_copilot.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")

from pipeline.models import PipelineBase
from pipeline.routers.copilot_router import (
    router,
    _sanitise,
    _session_key,
    _stream_key,
)

copilot_engine = create_engine(
    "sqlite:///./.local/test_databases/test_copilot.db", connect_args={"check_same_thread": False}
)
PipelineBase.metadata.create_all(bind=copilot_engine)


class FakeRedis:
    def __init__(self):
        self._store = {}
        self._lists = {}

    def get(self, key): return self._store.get(key)
    def set(self, key, value, ex=None): self._store[key] = value
    def delete(self, key): self._store.pop(key, None)
    def keys(self, pattern="*"): return list(self._store.keys())
    def rpush(self, key, value):
        self._lists.setdefault(key, []).append(value)
    def lrange(self, key, start, end):
        lst = self._lists.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start:end + 1]
    def expire(self, key, ttl): pass
    def ping(self): return True


def _make_client():
    app = FastAPI()
    app.include_router(router, prefix="/copilot")

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.organisation_id = 42
    mock_user.role = MagicMock()
    mock_user.role.value = "analyst"
    # Co-Pilot is gated by require_any_module - a real caller must hold at least
    # one module. Give the mock concrete module access (not a MagicMock, which
    # user_modules() cannot turn into a set).
    mock_user.module_access = ["esgrc", "apex"]

    from app.dependencies.auth import get_current_user, get_current_user_sse
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_current_user_sse] = lambda: mock_user

    return TestClient(app), mock_user


class TestSanitise:
    def test_strips_html_tags(self):
        assert _sanitise("<script>alert('xss')</script>Hello") == "Hello"

    def test_strips_control_characters(self):
        assert "\x00" not in _sanitise("Hello\x00World")

    def test_decodes_html_entities(self):
        result = _sanitise("&lt;b&gt;bold&lt;/b&gt;")
        assert "<" not in result

    def test_truncates_to_max_length(self):
        long_text = "A" * 3000
        result = _sanitise(long_text)
        assert len(result) <= 2000

    def test_normal_text_passes_through(self):
        text = "What are the top risks this quarter?"
        assert _sanitise(text) == text


class TestSendMessage:
    def test_returns_202_with_run_id_and_session_id(self):
        client, _ = _make_client()
        fake_redis = FakeRedis()

        with (
            patch("pipeline.routers.copilot_router._get_redis", return_value=fake_redis),
            patch("pipeline.routers.copilot_router.stream_copilot_response.apply_async"),
        ):
            resp = client.post(
                "/copilot/message",
                json={"message": "What are the top ESG risks?"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        assert "session_id" in data
        assert data["status"] == "streaming"

    def test_empty_message_returns_400(self):
        client, _ = _make_client()
        fake_redis = FakeRedis()

        with patch("pipeline.routers.copilot_router._get_redis", return_value=fake_redis):
            resp = client.post(
                "/copilot/message",
                json={"message": "   "},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code in (400, 422)

    def test_session_id_preserved_when_provided(self):
        client, _ = _make_client()
        fake_redis = FakeRedis()
        session_id = str(uuid.uuid4())

        with (
            patch("pipeline.routers.copilot_router._get_redis", return_value=fake_redis),
            patch("pipeline.routers.copilot_router.stream_copilot_response.apply_async"),
        ):
            resp = client.post(
                "/copilot/message",
                json={"message": "Follow-up question?", "session_id": session_id},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 202
        assert resp.json()["session_id"] == session_id

    def test_html_injection_sanitised_before_llm(self):
        """Verify malicious HTML in message is stripped before task is queued."""
        client, _ = _make_client()
        fake_redis = FakeRedis()
        captured_args = {}

        def capture_apply_async(args=None, **kwargs):
            captured_args["message"] = args[4] if args else None

        with (
            patch("pipeline.routers.copilot_router._get_redis", return_value=fake_redis),
            patch(
                "pipeline.routers.copilot_router.stream_copilot_response.apply_async",
                side_effect=capture_apply_async,
            ),
        ):
            resp = client.post(
                "/copilot/message",
                json={"message": "<script>steal()</script>What is my risk score?"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 202
        # The sanitised message passed to the task must not contain HTML
        assert "<script>" not in (captured_args.get("message") or "")


class TestStreamEndpoint:
    def test_stream_returns_connected_event(self):
        """SSE stream must yield a 'connected' event immediately."""
        client, user = _make_client()
        fake_redis = FakeRedis()
        run_id = str(uuid.uuid4())

        # Pre-populate stream with done signal (key is namespaced by user id)
        done_chunk = json.dumps({"type": "done", "text": ""})
        fake_redis.rpush(_stream_key(user.id, run_id), done_chunk)

        with patch("pipeline.routers.copilot_router._get_redis", return_value=fake_redis):
            resp = client.get(
                f"/copilot/stream/{run_id}",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    def test_stream_nonexistent_run_id_still_responds(self):
        """Even unknown run IDs should get a connected event (Celery may not have started yet)."""
        client, user = _make_client()
        fake_redis = FakeRedis()
        run_id = str(uuid.uuid4())
        fake_redis.rpush(_stream_key(user.id, run_id), json.dumps({"type": "done", "text": ""}))

        with patch("pipeline.routers.copilot_router._get_redis", return_value=fake_redis):
            resp = client.get(
                f"/copilot/stream/{run_id}",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200


class TestSessionManagement:
    def test_list_sessions_returns_empty_for_new_user(self):
        client, _ = _make_client()
        fake_redis = FakeRedis()

        with patch("pipeline.routers.copilot_router._get_redis", return_value=fake_redis):
            resp = client.get(
                "/copilot/sessions",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_clear_session_returns_204(self):
        client, _ = _make_client()
        fake_redis = FakeRedis()
        session_id = str(uuid.uuid4())

        # Pre-populate session
        fake_redis.set(_session_key(1, session_id), json.dumps([]))

        with patch("pipeline.routers.copilot_router._get_redis", return_value=fake_redis):
            resp = client.delete(
                f"/copilot/sessions/{session_id}",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 204


class TestSessionHistoryTTL:
    """
    copilot:{user}:session:{id} holds the user's questions and Claude's full
    answers about the org's data. GDPR erasure cannot reach it, because the key
    is scoped by session and the erasure endpoint is scoped by run (see #12), so
    until an org-scoped endpoint exists the TTL is the only control over how
    long that content survives.
    """

    def test_ttl_is_24h_not_7_days(self):
        from pipeline.routers.copilot_router import SESSION_HISTORY_TTL

        assert SESSION_HISTORY_TTL == 60 * 60 * 24, (
            "Co-Pilot conversation history TTL changed; it is the only control "
            "over erasure exposure until issue #12 lands"
        )

    def test_save_uses_the_constant_rather_than_a_literal(self):
        """A literal here is how it drifted to 7 days unnoticed in the first place."""
        from unittest.mock import MagicMock, patch
        from pipeline.routers.copilot_router import (
            _save_session_history, SESSION_HISTORY_TTL,
        )

        fake = MagicMock()
        with patch("pipeline.routers.copilot_router._get_redis", return_value=fake):
            _save_session_history(7, "sess-1", [{"role": "user", "content": "hi"}])

        assert fake.set.call_args.kwargs["ex"] == SESSION_HISTORY_TTL


class ErasureRedis(FakeRedis):
    """FakeRedis with the operations the erasure endpoints actually use.

    The base fake predates them: it has no scan_iter, and its delete takes a
    single key rather than *keys.
    """

    def scan_iter(self, match="*", count=100):
        import fnmatch
        return iter([k for k in list(self._store) if fnmatch.fnmatch(k, match)])

    def delete(self, *keys):
        n = 0
        for k in keys:
            if self._store.pop(k, None) is not None:
                n += 1
        return n

    def seed_user(self, user_id, sessions=2, runs=1):
        for i in range(sessions):
            self._store[f"copilot:{user_id}:session:s{i}"] = "[]"
        for i in range(runs):
            self._store[f"copilot:{user_id}:r{i}:stream"] = "[]"
            self._store[f"copilot:{user_id}:r{i}:done"] = "1"


def _erasure_client(role="admin", org_id=42, users=((1, 42), (2, 42), (3, 99))):
    """Client whose DB knows `users` as (id, organisation_id) pairs."""
    app = FastAPI()
    app.include_router(router, prefix="/copilot")

    from app.models.models import UserRole

    caller = MagicMock()
    caller.id, caller.organisation_id = 1, org_id
    # A real UserRole, not a MagicMock: require_role does
    # _ROLE_HIERARCHY.index(user.role), which needs the actual enum member.
    caller.role = UserRole(role)
    caller.module_access = ["esgrc"]

    rows = {uid: org for uid, org in users}

    class FakeResult:
        def __init__(self, v): self._v = v
        def scalar_one_or_none(self): return self._v
        def scalars(self): return self._v

    class FakeDB:
        def execute(self, stmt):
            # Discriminate on bound parameters, not SQL text: both statements
            # select from `users`, so a substring match on the text picked the
            # wrong branch and returned a list where a User was expected.
            params = stmt.compile().params
            if "organisation_id_1" in params:
                org = params["organisation_id_1"]
                return FakeResult([u for u, o in rows.items() if o == org])
            uid = params.get("id_1")
            if uid in rows:
                u = MagicMock(); u.id = uid; u.organisation_id = rows[uid]
                return FakeResult(u)
            return FakeResult(None)

    from app.dependencies.auth import get_current_user
    from app.database import get_db
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_db] = lambda: FakeDB()
    return TestClient(app), caller


class TestCopilotErasure:
    """Issue #12. The per-run erasure endpoint cannot reach Co-Pilot history,
    because its keys are scoped by session while that endpoint is scoped by run."""

    def test_self_erasure_clears_sessions_and_streams(self):
        client, _ = _erasure_client(role="analyst")
        r = ErasureRedis(); r.seed_user(1, sessions=3, runs=2); r.seed_user(2)
        with patch("pipeline.routers.copilot_router._get_redis", return_value=r):
            resp = client.delete("/copilot/sessions")
        assert resp.status_code == 204
        assert not [k for k in r._store if k.startswith("copilot:1:")]
        # another user's data must be untouched
        assert [k for k in r._store if k.startswith("copilot:2:")]

    def test_erasure_covers_stream_keys_not_just_history(self):
        """The stream list holds every token of the model's response."""
        client, _ = _erasure_client(role="analyst")
        r = ErasureRedis(); r.seed_user(1, sessions=1, runs=1)
        with patch("pipeline.routers.copilot_router._get_redis", return_value=r):
            client.delete("/copilot/sessions")
        assert "copilot:1:r0:stream" not in r._store
        assert "copilot:1:r0:done" not in r._store

    def test_admin_can_erase_a_user_in_their_own_org(self):
        client, _ = _erasure_client(role="admin")
        r = ErasureRedis(); r.seed_user(2)
        with patch("pipeline.routers.copilot_router._get_redis", return_value=r):
            resp = client.delete("/copilot/erasure/users/2")
        assert resp.status_code == 204
        assert not [k for k in r._store if k.startswith("copilot:2:")]

    def test_admin_cannot_erase_a_user_in_another_org(self):
        """Cross-tenant target is a 404, matching the rest of the app."""
        client, _ = _erasure_client(role="admin")
        r = ErasureRedis(); r.seed_user(3)
        with patch("pipeline.routers.copilot_router._get_redis", return_value=r):
            resp = client.delete("/copilot/erasure/users/3")
        assert resp.status_code == 404
        assert [k for k in r._store if k.startswith("copilot:3:")], "data was deleted anyway"

    def test_admin_cannot_erase_another_org(self):
        client, _ = _erasure_client(role="admin", org_id=42)
        r = ErasureRedis(); r.seed_user(3)
        with patch("pipeline.routers.copilot_router._get_redis", return_value=r):
            resp = client.delete("/copilot/erasure/organisations/99")
        assert resp.status_code == 404
        assert [k for k in r._store if k.startswith("copilot:3:")]

    def test_super_admin_can_erase_any_org(self):
        client, _ = _erasure_client(role="super_admin", org_id=42)
        r = ErasureRedis(); r.seed_user(3)
        with patch("pipeline.routers.copilot_router._get_redis", return_value=r):
            resp = client.delete("/copilot/erasure/organisations/99")
        assert resp.status_code == 204

    def test_redis_failure_surfaces_rather_than_reporting_success(self):
        """The regression that matters: a failed deletion must not look deleted."""
        client, _ = _erasure_client(role="analyst")
        with patch("pipeline.routers.copilot_router._get_redis",
                   side_effect=OSError("redis down")):
            resp = client.delete("/copilot/sessions")
        assert resp.status_code == 502
        assert "nothing was deleted" in resp.json()["detail"].lower()

    def test_single_session_clear_no_longer_swallows_failures(self):
        client, _ = _erasure_client(role="analyst")
        with patch("pipeline.routers.copilot_router._get_redis",
                   side_effect=OSError("redis down")):
            resp = client.delete("/copilot/sessions/abc")
        assert resp.status_code == 502, "a failed delete used to return 204"

    def test_listing_uses_scan_not_keys(self):
        """KEYS blocks the whole Redis server."""
        client, _ = _erasure_client(role="analyst")
        r = ErasureRedis(); r.seed_user(1, sessions=2, runs=0)
        r.keys = MagicMock(side_effect=AssertionError("KEYS must not be used"))
        with patch("pipeline.routers.copilot_router._get_redis", return_value=r):
            resp = client.get("/copilot/sessions")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2
        r.keys.assert_not_called()


class TestOrgContextInjection:
    """FIX: the module docstring and SYSTEM_PROMPT both claim Co-Pilot answers
    are grounded in "the organisation's pipeline outputs and analytical
    reports" with "org context injected automatically from current_user" -
    but stream_copilot_response accepted org_id as a parameter and never
    referenced it again. No org data ever reached the Claude call."""

    @staticmethod
    def _fake_ctx(runs_rows, outputs_rows):
        class FakeResult:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        class FakeSession:
            def execute(self, stmt, params=None):
                # pipeline_runs is queried first, pipeline_llm_outputs second.
                if "pipeline_runs" in str(stmt):
                    return FakeResult(runs_rows)
                return FakeResult(outputs_rows)

        class FakeCtx:
            def __enter__(self):
                return FakeSession()

            def __exit__(self, *a):
                return False

        return FakeCtx()

    def test_includes_confidence_score_and_recommendation_text(self):
        from pipeline.routers.copilot_router import _load_org_context

        ctx = self._fake_ctx(
            runs_rows=[("run-1", "pipe-1", 0.81, "2026-09-01T00:00:00Z")],
            outputs_rows=[("run-1", "GENERAL_RISK", "Top risk: Scope 2 emissions gap.")],
        )
        with patch("pipeline.database.session_ctx", return_value=ctx):
            context = _load_org_context(42)

        assert "0.81" in context
        assert "Scope 2 emissions gap" in context

    def test_empty_string_when_org_has_no_completed_runs(self):
        from pipeline.routers.copilot_router import _load_org_context

        ctx = self._fake_ctx(runs_rows=[], outputs_rows=[])
        with patch("pipeline.database.session_ctx", return_value=ctx):
            assert _load_org_context(42) == ""

    def test_never_raises_on_db_error(self):
        """A data-layer hiccup must degrade to a generic answer, not a 500."""
        from pipeline.routers.copilot_router import _load_org_context

        with patch("pipeline.database.session_ctx", side_effect=RuntimeError("db down")):
            assert _load_org_context(42) == ""

    def test_stream_task_actually_passes_org_context_to_the_claude_call(self):
        """The regression this guards against: a helper that CAN build org
        context is not the same as the Celery task actually using it."""
        from pipeline.routers import copilot_router as cr

        fake_redis = FakeRedis()
        captured = {}

        class FakeStreamCtx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            @property
            def text_stream(self):
                return iter(["ok"])

        class FakeMessages:
            def stream(self, **kwargs):
                captured.update(kwargs)
                return FakeStreamCtx()

        fake_client = MagicMock()
        fake_client.messages = FakeMessages()

        with (
            patch("pipeline.routers.copilot_router._get_redis", return_value=fake_redis),
            patch(
                "pipeline.routers.copilot_router._load_org_context",
                return_value="## org data\nconfidence 0.81",
            ),
            patch("pipeline.routers.copilot_router.anthropic.Anthropic", return_value=fake_client),
        ):
            cr.stream_copilot_response(
                run_id="r1", user_id=1, org_id=42, session_id="s1",
                message="What are my top risks?", history=[],
            )

        assert "confidence 0.81" in captured["system"]
        assert cr.SYSTEM_PROMPT in captured["system"]
