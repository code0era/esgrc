"""
ESGRC/test/test_frontend_api_contract.py

Checks the frontend against the API it actually talks to.

WHY THIS EXISTS
---------------
The frontend's dev and test environment is Mock Service Worker. MSW answers
whatever the frontend asks for, so a handler encodes the FRONTEND's assumption,
not the API's contract. When the two disagree, everything works in dev and fails
against the real backend, and no existing test catches it.

That is not hypothetical. RiskPage called `PUT /risks/{id}` while the API serves
`PATCH /risks/{risk_id}`, and `handlers.ts` mocked `http.put('/api/risks/:id')`.
Editing a risk therefore worked perfectly in development and returned 405 in
production. Nothing failed: the frontend unit tests do not cover RiskPage, and
Playwright is not run in CI.

These tests compare both the real calls and the mocks against the live OpenAPI
schema, so the mock can no longer agree with the caller instead of the server.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend" / "src"

CALL_RE = re.compile(r"api\.(get|post|put|patch|delete)\(\s*[`'\"]([^`'\"]+)")
MSW_RE = re.compile(r"http\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]")


def _served():
    """(methods, compiled path regex, raw path) for every route the API serves."""
    from main import app

    out = []
    for path, ops in app.openapi()["paths"].items():
        rx = re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$")
        out.append(({m.upper() for m in ops}, rx, path))
    return out


def _source_files():
    for pattern in ("*.ts", "*.tsx"):
        for p in FRONTEND.rglob(pattern):
            if "mocks" in p.parts or ".test." in p.name:
                continue
            yield p


def _normalise(path: str) -> str:
    """`/pipelines/${id}/runs` -> `/pipelines/abc/runs`, `:id` -> `abc`."""
    path = path.split("?")[0]
    path = re.sub(r"\$\{[^}]+\}", "abc", path)
    path = re.sub(r":[A-Za-z_]+", "abc", path)
    return re.sub(r"\*", "abc", path)


def _matches(method: str, path: str, served) -> bool:
    probe = _normalise(path)
    return any(method in ms and rx.match(probe) for ms, rx, _ in served)


def test_every_frontend_api_call_hits_a_real_endpoint():
    served = _served()
    broken = []
    for p in _source_files():
        for m in CALL_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
            method, raw = m.group(1).upper(), m.group(2)
            if not _matches(method, raw, served):
                offered = next(
                    (sorted(ms) for ms, rx, _ in served if rx.match(_normalise(raw))),
                    "no such path",
                )
                broken.append(
                    f"{method} {raw} ({p.relative_to(REPO)}) - API offers: {offered}"
                )
    assert not broken, "frontend calls with no matching API route:\n  " + "\n  ".join(broken)


def test_every_msw_handler_matches_a_real_endpoint():
    """A mock for an endpoint that does not exist is worse than no mock.

    It makes the frontend appear to work against a backend that would reject it.
    """
    served = _served()
    handlers_file = FRONTEND / "mocks" / "handlers.ts"
    if not handlers_file.exists():
        pytest.skip("no MSW handlers file")

    broken = []
    for m in MSW_RE.finditer(handlers_file.read_text(encoding="utf-8", errors="replace")):
        method, raw = m.group(1).upper(), m.group(2)
        path = raw[len("/api"):] if raw.startswith("/api") else raw
        if not _matches(method, path, served):
            offered = next(
                (sorted(ms) for ms, rx, _ in served if rx.match(_normalise(path))),
                "no such path",
            )
            broken.append(f"{method} {raw} - API offers: {offered}")
    assert not broken, (
        "MSW handlers that do not match the real API:\n  " + "\n  ".join(broken)
    )


def test_msw_covers_every_endpoint_the_frontend_calls():
    """The reverse gap: a call with no mock silently hits the network in dev."""
    served = _served()
    handlers_file = FRONTEND / "mocks" / "handlers.ts"
    if not handlers_file.exists():
        pytest.skip("no MSW handlers file")

    mocked = []
    for m in MSW_RE.finditer(handlers_file.read_text(encoding="utf-8", errors="replace")):
        raw = m.group(2)
        path = raw[len("/api"):] if raw.startswith("/api") else raw
        mocked.append((m.group(1).upper(), re.compile("^" + _normalise(path).replace("abc", "[^/]+") + "$")))

    unmocked = []
    for p in _source_files():
        for m in CALL_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
            method, raw = m.group(1).upper(), m.group(2)
            probe = _normalise(raw)
            if not any(method == mm and rx.match(probe) for mm, rx in mocked):
                # Only report calls that ARE real endpoints; a bogus call is the
                # other test's job to flag.
                if _matches(method, raw, served):
                    unmocked.append(f"{method} {raw} ({p.relative_to(REPO)})")

    assert not unmocked, (
        "frontend calls with no MSW handler - these hit the network in dev:\n  "
        + "\n  ".join(sorted(set(unmocked)))
    )
