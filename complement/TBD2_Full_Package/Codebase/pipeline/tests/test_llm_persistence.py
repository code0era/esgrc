"""Tests for LLMClient persistence and the Haiku->Sonnet upgrade decision.

Both areas were previously uncovered because every test mocked LLMClient
wholesale, which is how two bugs survived:

  * _save_to_db built its INSERT with NOW(). That is a PostgreSQL function, so
    on SQLite - what the single-container demo actually runs - every Claude step
    failed at the persistence step with "no such function: NOW".
  * The same INSERT accepted prompt_id and then never wrote it, leaving the
    column added by 20260622_add_prompt_id NULL on every row, so no output could
    be traced back to the prompt version that produced it.

  * The upgrade decision read check_result.token_count, which is the count AFTER
    the guard already truncated, instead of original_token_count.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import pipeline.database as pdb
from pipeline.llm.client import HAIKU_UPGRADE_TOKEN_THRESHOLD, LLMClient
from pipeline.llm.guard import TokenCheckResult


@pytest.fixture
def sqlite_session(db_engine, monkeypatch):
    """Point pipeline.database's session factory at the SQLite test engine.

    session_ctx() reads the module-level _SessionFactory, so patching that is
    enough to make _save_to_db write somewhere observable - and, crucially, to
    exercise it against SQLite rather than PostgreSQL.
    """
    monkeypatch.setattr(pdb, "_engine", db_engine)
    monkeypatch.setattr(
        pdb, "_SessionFactory", sessionmaker(bind=db_engine, expire_on_commit=False)
    )
    return db_engine


def _client() -> LLMClient:
    """An LLMClient without __init__ side effects (no Anthropic/Redis/Langfuse)."""
    return object.__new__(LLMClient)


# ── Persistence ───────────────────────────────────────────────────────────────

def test_save_to_db_succeeds_on_sqlite(sqlite_session):
    """The NOW() regression: this raised 'no such function: NOW' on SQLite."""
    run_id = str(uuid.uuid4())
    _client()._save_to_db(
        run_id=run_id,
        step_result_id=str(uuid.uuid4()),
        analysis_type="MODULE_UNIFIED",
        prompt_id=None,
        prompt_hash="deadbeef",
        model_used="claude-haiku-4-5",
        input_tokens=100,
        output_tokens=200,
        response_text="analysis body",
        r2_path="org/1/runs/x/llm.txt",
    )

    with sqlite_session.begin() as conn:
        row = conn.execute(
            text(
                "SELECT response_text, created_at FROM pipeline_llm_outputs "
                "WHERE run_id = :r"
            ),
            {"r": run_id},
        ).one()
    assert row.response_text == "analysis body"
    assert row.created_at is not None, "created_at was not populated"


def test_save_to_db_persists_prompt_id(sqlite_session):
    """prompt_id was accepted and silently dropped from the INSERT."""
    run_id = str(uuid.uuid4())
    _client()._save_to_db(
        run_id=run_id,
        step_result_id=str(uuid.uuid4()),
        analysis_type="MODULE_UNIFIED",
        prompt_id=77,
        prompt_hash="cafebabe",
        model_used="claude-haiku-4-5",
        input_tokens=1,
        output_tokens=2,
        response_text="body",
        r2_path=None,
    )

    with sqlite_session.begin() as conn:
        stored = conn.execute(
            text("SELECT prompt_id FROM pipeline_llm_outputs WHERE run_id = :r"),
            {"r": run_id},
        ).scalar_one()
    assert stored == 77, (
        "prompt_id was not persisted, so outputs cannot be traced to a prompt version"
    )


# ── Model upgrade decision ────────────────────────────────────────────────────

def _run_analyze_capturing_model(check_result: TokenCheckResult) -> str:
    """Drive analyze() with everything stubbed except the model choice.

    Returns the model handed to _call_with_retry.
    """
    response = MagicMock()
    response.content = [MagicMock(type="text", text="result")]
    response.usage = MagicMock(input_tokens=1, output_tokens=1)

    client = _client()
    client._redis = None
    client._langfuse = None

    with (
        patch.object(LLMClient, "_load_prompt_template", return_value=(1, "{report_text}")),
        patch.object(LLMClient, "_download_report", return_value="report body"),
        patch.object(LLMClient, "_check_result_cache", return_value=None),
        patch("pipeline.llm.guard.check_token_count", return_value=check_result),
        patch.object(LLMClient, "_call_with_retry", return_value=response) as call,
        patch.object(LLMClient, "_save_to_r2", return_value="r2/path"),
        patch.object(LLMClient, "_save_to_db"),
        patch.object(LLMClient, "_cache_result_for_ui"),
        patch.object(LLMClient, "_store_result_cache"),
        patch.object(LLMClient, "_trace_langfuse"),
    ):
        client.analyze(
            analysis_type="MODULE_UNIFIED",
            consolidated_report_r2_path="org/1/runs/x/MASTER.txt",
            run_id=str(uuid.uuid4()),
            step_result_id=str(uuid.uuid4()),
        )
    return call.call_args[0][0]


def test_upgrades_when_original_prompt_was_oversized_even_if_truncated_below():
    """The core regression.

    A report that arrives well over Haiku's threshold but whose truncated form
    measures under it must still go to Sonnet. Reading the post-truncation count
    sent it to Haiku with a middle-cut report instead.
    """
    over = HAIKU_UPGRADE_TOKEN_THRESHOLD + 30_000
    under = HAIKU_UPGRADE_TOKEN_THRESHOLD - 25_000
    model = _run_analyze_capturing_model(
        TokenCheckResult(
            token_count=under,          # what it measured after truncation
            was_truncated=True,
            original_token_count=over,  # what we were actually handed
            text="truncated report",
        )
    )
    assert model == "claude-sonnet-5", (
        f"stayed on {model}: a {over}-token report was truncated to {under} and "
        "the upgrade check read the truncated figure"
    )


def test_stays_on_haiku_for_genuinely_small_prompts():
    """The upgrade must not fire for everything - Haiku is the cost default."""
    small = HAIKU_UPGRADE_TOKEN_THRESHOLD - 50_000
    model = _run_analyze_capturing_model(
        TokenCheckResult(
            token_count=small,
            was_truncated=False,
            original_token_count=small,
            text="small report",
        )
    )
    assert model == "claude-haiku-4-5"


# ── Response content-block extraction ─────────────────────────────────────────
#
# Live regression, 2026-09-11: claude-sonnet-5 runs adaptive thinking by
# default even with no `thinking` param set, so response.content[0] is a
# ThinkingBlock (a pydantic model with no .text attribute), not the TextBlock.
# analyze() used to index content[0] directly and crashed every real Apex/
# ESGRC Claude step on that model with AttributeError: 'ThinkingBlock' object
# has no attribute 'text'. Reproduced here with a mock shaped like the real
# SDK response (thinking block first, spec'd so .text raises like the real
# pydantic model does) rather than assuming position.

_SMALL_CHECK_RESULT = TokenCheckResult(
    token_count=100,
    was_truncated=False,
    original_token_count=100,
    text="small report",
)


def _run_analyze_with_content(content_blocks) -> str:
    """Drive analyze() with a stubbed response.content; returns response_text."""
    response = MagicMock()
    response.content = content_blocks
    response.usage = MagicMock(input_tokens=1, output_tokens=1)

    client = _client()
    client._redis = None
    client._langfuse = None

    captured = {}

    def fake_save_to_db(**kw):
        captured["response_text"] = kw["response_text"]

    with (
        patch.object(LLMClient, "_load_prompt_template", return_value=(1, "{report_text}")),
        patch.object(LLMClient, "_download_report", return_value="report body"),
        patch.object(LLMClient, "_check_result_cache", return_value=None),
        patch("pipeline.llm.guard.check_token_count", return_value=_SMALL_CHECK_RESULT),
        patch.object(LLMClient, "_call_with_retry", return_value=response),
        patch.object(LLMClient, "_save_to_r2", return_value="r2/path"),
        patch.object(LLMClient, "_save_to_db", side_effect=fake_save_to_db),
        patch.object(LLMClient, "_cache_result_for_ui"),
        patch.object(LLMClient, "_store_result_cache"),
        patch.object(LLMClient, "_trace_langfuse"),
    ):
        client.analyze(
            analysis_type="MODULE_UNIFIED",
            consolidated_report_r2_path="org/1/runs/x/MASTER.txt",
            run_id=str(uuid.uuid4()),
            step_result_id=str(uuid.uuid4()),
        )
    return captured["response_text"]


def test_analyze_finds_text_block_when_thinking_block_precedes_it():
    """The exact live failure shape: [ThinkingBlock, TextBlock]."""
    thinking_block = MagicMock(spec=["type"], type="thinking")
    text_block = MagicMock(type="text", text="the real analysis")

    response_text = _run_analyze_with_content([thinking_block, text_block])

    assert response_text == "the real analysis"


def test_analyze_joins_multiple_text_blocks():
    """Claude can also split its answer across more than one text block."""
    thinking_block = MagicMock(spec=["type"], type="thinking")
    first = MagicMock(type="text", text="part one. ")
    second = MagicMock(type="text", text="part two.")

    response_text = _run_analyze_with_content([thinking_block, first, second])

    assert response_text == "part one. part two."


def test_analyze_raises_clear_error_when_response_has_no_text_block():
    """A response of only thinking blocks must fail loudly, not silently."""
    thinking_block = MagicMock(spec=["type"], type="thinking")

    with pytest.raises(ValueError, match="no text block"):
        _run_analyze_with_content([thinking_block])
