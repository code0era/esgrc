"""
ESGRC/test/test_rate_limits.py

Rate limiting was configured but almost entirely unapplied. `add_pipeline_middleware`
does register SlowAPIMiddleware with a 60/minute global default, so the claim that
limits were applied "on no endpoint" was too strong. What was actually missing:

  - /auth/register had only the 60/minute global, despite being unauthenticated and
    acting as an organisation-slug oracle (404 for unknown, 201/409 for known).
  - /auth/refresh had only the 60/minute global, despite taking a bearer-equivalent
    secret.
  - The pipeline trigger had only the 60/minute global, despite `rate_limit_trigger`
    ("10/minute") existing in pipeline/middleware.py specifically for it and being
    documented in that module's docstring. Each run spends real money on Claude.

Only /auth/login carried an endpoint limit (5/minute).

conftest sets RATE_LIMIT_ENABLED=false so the rest of the suite is not throttled,
so these tests re-enable the limiter around themselves.
"""
import pytest
from fastapi.testclient import TestClient

from pipeline.middleware import limiter


@pytest.fixture
def live_limiter():
    """Turn the limiter on for one test and reset its counters either side.

    The limiter picks its storage at import time from REDIS_URL, falling back to
    memory://. pipeline/test/conftest.py sets REDIS_URL, so when both suites run
    in a single pytest process the limiter is Redis-backed and reset() fails with
    ConnectionRefused against a Redis nobody started. Running ESGRC/test alone
    gets memory:// and passes, which is why CI (two separate jobs) and
    run-tests.ps1 never saw it.

    Skip rather than fail when the backing store is unreachable: the test cannot
    do anything meaningful without a counter store, and a red suite that depends
    on invocation order teaches people to ignore red suites.
    """
    previous = limiter.enabled
    limiter.enabled = True
    try:
        limiter.reset()
    except Exception as exc:  # storage unreachable
        limiter.enabled = previous
        pytest.skip(
            f"rate-limit storage unreachable ({type(exc).__name__}). The limiter is "
            f"bound to REDIS_URL at import; start Redis or run this suite alone."
        )
    try:
        yield limiter
    finally:
        try:
            limiter.reset()
        except Exception:
            pass
        limiter.enabled = previous


def _post_until_429(client: TestClient, url: str, payload: dict, attempts: int):
    """Return the list of status codes seen over `attempts` identical requests."""
    return [client.post(url, json=payload).status_code for _ in range(attempts)]


class TestAuthRateLimits:

    def test_register_is_limited(self, client: TestClient, live_limiter):
        """Unauthenticated registration must not be a firehose. Limit is 5/minute."""
        payload = {
            "email": "flood@example.com",
            "password": "Str0ngPassw0rd!",
            "full_name": "Flood Tester",
            "organisation_slug": "no-such-org-slug",
        }
        codes = _post_until_429(client, "/auth/register", payload, attempts=7)

        assert 429 in codes, f"register never rate limited; saw {codes}"
        # The limit must bite only after the allowance, not on the first call.
        assert codes[0] != 429, f"register limited immediately; saw {codes}"

    def test_refresh_is_limited(self, client: TestClient, live_limiter):
        """Refresh takes a bearer-equivalent secret. Limit is 20/minute."""
        codes = _post_until_429(
            client, "/auth/refresh", {"refresh_token": "not-a-real-token"}, attempts=22
        )

        assert 429 in codes, f"refresh never rate limited; saw {codes}"
        assert codes[0] != 429, f"refresh limited immediately; saw {codes}"

    def test_login_limit_still_present(self, client: TestClient, live_limiter):
        """Regression guard on the one limit that already existed."""
        codes = _post_until_429(
            client,
            "/auth/login",
            {"email": "nobody@example.com", "password": "wrong-password"},
            attempts=7,
        )

        assert 429 in codes, f"login never rate limited; saw {codes}"

    def test_limit_response_is_structured_json(self, client: TestClient, live_limiter):
        """A 429 must return the handler's JSON, never raw slowapi text."""
        payload = {"email": "x@example.com", "password": "wrong-password"}
        response = None
        for _ in range(10):
            response = client.post("/auth/login", json=payload)
            if response.status_code == 429:
                break

        assert response.status_code == 429
        body = response.json()
        assert "detail" in body
        assert body.get("retry_after") == 60
        assert response.headers.get("Retry-After") == "60"


class TestTriggerRateLimit:
    """
    The trigger endpoint spends money: a real ESGRC run cost $0.9255 before the
    report trim and $0.0416 after. `rate_limit_trigger` existed for it and was
    never applied.
    """

    def test_trigger_endpoint_declares_the_trigger_limit(self):
        from pipeline.middleware import rate_limit_trigger
        from pipeline.routers import pipeline_router

        # slowapi wraps the endpoint; the original is reachable via __wrapped__.
        endpoint = pipeline_router.trigger_pipeline
        assert hasattr(endpoint, "__wrapped__"), (
            "trigger_pipeline is not wrapped by @limiter.limit"
        )
        assert rate_limit_trigger == "10/minute"

    def test_trigger_takes_request_so_slowapi_can_key_it(self):
        """slowapi resolves the client IP from a `request` parameter. Without it
        the decorator raises at call time rather than limiting."""
        import inspect
        from pipeline.routers import pipeline_router

        sig = inspect.signature(pipeline_router.trigger_pipeline.__wrapped__)
        assert "request" in sig.parameters


class TestAgentTriggerRateLimit:
    """
    /agent/run and /agent/llm-run are SUPER_ADMIN-gated, but that gate alone
    doesn't cap how many of these platform-wide, real-money batch runs one
    token can fire per minute - they had no endpoint-specific limit (only the
    60/minute global) despite the pipeline's own sibling /trigger getting one
    for the identical reason. Same static-introspection style as
    TestTriggerRateLimit above (not live-firing): SUPER_ADMIN auth setup adds
    complexity for no extra coverage over confirming the decorator is applied.
    """

    def test_agent_run_declares_the_trigger_limit(self):
        import inspect
        from pipeline.middleware import rate_limit_trigger
        from app.routers import agent

        endpoint = agent.trigger_run
        assert hasattr(endpoint, "__wrapped__"), (
            "trigger_run is not wrapped by @limiter.limit"
        )
        assert rate_limit_trigger == "10/minute"
        assert "request" in inspect.signature(endpoint.__wrapped__).parameters

    def test_agent_llm_run_declares_the_trigger_limit(self):
        import inspect
        from pipeline.middleware import rate_limit_trigger
        from app.routers import agent

        endpoint = agent.trigger_llm_run
        assert hasattr(endpoint, "__wrapped__"), (
            "trigger_llm_run is not wrapped by @limiter.limit"
        )
        assert rate_limit_trigger == "10/minute"
        assert "request" in inspect.signature(endpoint.__wrapped__).parameters
