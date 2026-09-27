"""
pipeline/llm/client.py
LLMClient - wraps the Anthropic API for all pipeline Claude calls.

Features:
  - Prompt loading from DB (cached in Redis TTL 300s)
  - SHA-256 prompt hash for cache invalidation
  - Redis result cache (same hash → same result, skip API call)
  - Context window guard (guard.py)
  - Exponential backoff retry (3 attempts)
  - Langfuse tracing (optional - never blocks)
  - Saves result to pipeline_llm_outputs table
  - Saves .txt file to R2
  - Writes result to Redis for immediate UI display
"""
import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# ── Retry config ──────────────────────────────────────────────────────────────
MAX_RETRIES = 3
INITIAL_DELAY = 2.0
BACKOFF_FACTOR = 2.0
JITTER = 0.5

# ── Redis TTLs ────────────────────────────────────────────────────────────────
PROMPT_CACHE_TTL = 300        # 5 minutes
RESULT_CACHE_TTL = 60 * 60 * 25  # 25 hours - same as pipeline state keys

# ── Model routing ─────────────────────────────────────────────────────────────
# claude-sonnet-4-6 was the current Sonnet when this table was first written;
# claude-sonnet-5 is now the current release (claude-sonnet-4-6 still works,
# not retired, just no longer the recommended choice - see
# https://platform.claude.com/docs/en/about-claude/models/overview).
DEFAULT_MODELS = {
    "MODULE_UNIFIED": "claude-haiku-4-5",
    "GENERAL_RISK":   "claude-sonnet-5",
    "SPC_RPN":        "claude-sonnet-5",
}

# Haiku auto-upgrade threshold (per architecture decisions doc D4/R2)
HAIKU_UPGRADE_TOKEN_THRESHOLD = 150_000

# Max output tokens per Claude call. The risk reports are long, structured
# markdown; 4096 then 8192 were each tried and both still hit the ceiling on
# real Apex data - confirmed 2026-09-11 via a live run whose General Risk
# report cut off mid-word ("...Scen") at exactly 8192 output tokens. 16000
# is the documented safe ceiling for a *non-streaming* Anthropic request
# (stays under the SDK's HTTP timeout); going higher would require switching
# _call_with_retry to streaming. Env-overridable for tuning.
MAX_OUTPUT_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "16000"))


@dataclass
class LLMResult:
    response_text: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    model_used: str
    prompt_hash: str
    r2_path: Optional[str]
    prompt_id: Optional[int] = None
    from_cache: bool = False


class LLMClient:
    """
    Wraps Anthropic API calls for the TBD2 pipeline.

    Usage:
        client = LLMClient()
        result = client.analyze(
            analysis_type="MODULE_UNIFIED",
            consolidated_report_r2_path="org/42/runs/.../MASTER.txt",
            run_id="...",
            step_result_id="...",
        )
    """

    def __init__(self):
        self._anthropic = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        self._redis = self._init_redis()
        self._langfuse = self._init_langfuse()

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(
        self,
        analysis_type: str,
        consolidated_report_r2_path: str,
        run_id: str,
        step_result_id: str,
        model_override: Optional[str] = None,
        report_text: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> LLMResult:
        """
        Run a Claude analysis on a consolidated report.

        Steps:
        1. Load prompt template from DB (cached in Redis)
        2. Download report from R2
        3. Render full prompt
        4. Compute prompt_hash - check Redis result cache
        5. Run context window guard (auto-upgrade to Sonnet if needed)
        6. Call Anthropic API with retry
        7. Save to DB, R2, Redis
        8. Trace in Langfuse (non-blocking)

        Returns LLMResult.

        org_id: caller's organisation (claude_tasks.py always has it - every step
        task takes org_id as a positional arg). Falls back to a DB lookup by
        run_id when omitted, e.g. from older/direct callers. Used ONLY to scope
        the Redis result cache key below - never trusted for R2/DB reads.

        FIX: the result cache key used to be bare prompt_hash = sha256(full_prompt),
        with no org in it at all. full_prompt is template + report_text, and two
        different orgs CAN produce byte-identical report_text - most plausibly a
        near-empty "skeleton" report before either org has uploaded real data
        (exactly the case preflight.py's floor-guard warns about), where every
        org's MASTER_CONSOLIDATED_REPORT.txt is just the same static headers with
        no populated numbers. Without an org-scoped key, org B's run would silently
        serve org A's cached Claude response on a cache hit - it still lands under
        org B's own R2/DB rows (never a raw cross-org read), but the content itself
        was never generated from org B's own call. Scoping the key by org_id closes
        that even for the coincidental-collision case.
        """
        # 1. Load prompt template
        prompt_id, prompt_template = self._load_prompt_template(analysis_type)

        if org_id is None:
            org_id = self._get_org_id(run_id)

        # 2. Download report from R2 (skip if caller already has it)
        if report_text is None:
            report_text = self._download_report(consolidated_report_r2_path)

        # 3. Render prompt
        full_prompt = prompt_template.replace("{report_text}", report_text)

        # 4. Hash - check cache
        prompt_hash = hashlib.sha256(full_prompt.encode()).hexdigest()
        cached = self._check_result_cache(prompt_hash, org_id)
        if cached:
            logger.info("LLM result cache hit for hash %s", prompt_hash[:12])

            r2_path = self._save_to_r2(
                response_text=cached.response_text,
                run_id=run_id,
                step_result_id=step_result_id,
                analysis_type=analysis_type,
            )
            self._save_to_db(
                run_id=run_id,
                step_result_id=step_result_id,
                analysis_type=analysis_type,
                prompt_id=cached.prompt_id,
                prompt_hash=prompt_hash,
                model_used=cached.model_used,
                input_tokens=cached.input_tokens,
                output_tokens=cached.output_tokens,
                response_text=cached.response_text,
                r2_path=r2_path,
            )
            self._cache_result_for_ui(run_id, step_result_id, cached.response_text)

            cached.r2_path = r2_path
            return cached

        # 5. Context window guard + model selection
        model = model_override or DEFAULT_MODELS.get(analysis_type, "claude-haiku-4-5")
        from pipeline.llm.guard import check_token_count

        check_result = check_token_count(full_prompt, model)

        # Auto-upgrade Haiku → Sonnet if token count is high.
        #
        # Decide on original_token_count, NOT token_count: check_token_count
        # already truncated, and token_count is the count AFTER that truncation.
        # _truncate_to_tokens aims at a char target derived from an assumed
        # chars-per-token ratio, so on content lighter than that assumption the
        # cut lands well under the threshold - a 180K-token report could come
        # back measuring ~125K, the upgrade would not fire, and Haiku would
        # silently receive a middle-truncated report that Sonnet 5 (950K)
        # could have taken whole. The size that matters is the size we were
        # handed, before any trimming.
        if (
            model == "claude-haiku-4-5"
            and check_result.original_token_count > HAIKU_UPGRADE_TOKEN_THRESHOLD
        ):
            logger.warning(
                "Token count %d > %d - upgrading Haiku → Sonnet for run %s",
                check_result.original_token_count,
                HAIKU_UPGRADE_TOKEN_THRESHOLD,
                run_id,
            )
            model = "claude-sonnet-5"
            # Re-check against the ORIGINAL untruncated prompt, not the
            # already-Haiku-truncated check_result.text - Sonnet's limit
            # is much higher and may not need truncation at all.
            check_result = check_token_count(full_prompt, model)

        # 6. Call API with retry
        response = self._call_with_retry(model, check_result.text)

        # claude-sonnet-5 (unlike claude-haiku-4-5) returns a ThinkingBlock
        # ahead of the TextBlock by default, so content[0] is not reliably
        # the text - find the text block(s) instead of assuming position.
        text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        if not text_blocks:
            block_types = [getattr(b, "type", type(b).__name__) for b in response.content]
            raise ValueError(f"Anthropic response for model {model} had no text block (got: {block_types})")
        response_text = "".join(text_blocks)
        input_tokens = getattr(response.usage, "input_tokens", None)
        output_tokens = getattr(response.usage, "output_tokens", None)

        # 7. Persist results
        r2_path = self._save_to_r2(
            response_text=response_text,
            run_id=run_id,
            step_result_id=step_result_id,
            analysis_type=analysis_type,
        )

        self._save_to_db(
            run_id=run_id,
            step_result_id=step_result_id,
            analysis_type=analysis_type,
            prompt_id=prompt_id,
            prompt_hash=prompt_hash,
            model_used=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_text=response_text,
            r2_path=r2_path,
        )

        # Write to Redis immediately for UI display before DB write propagates
        self._cache_result_for_ui(run_id, step_result_id, response_text)

        result = LLMResult(
            response_text=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_used=model,
            prompt_hash=prompt_hash,
            r2_path=r2_path,
            prompt_id=prompt_id,
            from_cache=False,
        )

        # Cache for future identical prompts
        self._store_result_cache(prompt_hash, result, org_id)

        # 8. Langfuse trace (non-blocking)
        self._trace_langfuse(
            analysis_type=analysis_type,
            run_id=run_id,
            step_result_id=step_result_id,
            prompt_text=check_result.text,
            response_text=response_text,
            model_used=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            prompt_hash=prompt_hash,
        )

        return result

    # ── Prompt loading ────────────────────────────────────────────────────────

    def _load_prompt_template(self, analysis_type: str) -> tuple[Optional[int], str]:
        """Load (prompt_id, template) from DB (via Redis cache). Falls back to hardcoded."""
        cache_key = f"pipeline:prompt:{analysis_type}"

        if self._redis:
            cached = self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return data["prompt_id"], data["content"]

        # Try DB
        prompt_id, template = self._load_prompt_from_db(analysis_type)

        if template and self._redis:
            self._redis.set(
                cache_key,
                json.dumps({"prompt_id": prompt_id, "content": template}),
                ex=PROMPT_CACHE_TTL,
            )

        return prompt_id, template

    def _load_prompt_from_db(self, analysis_type: str) -> tuple[Optional[int], str]:
        """
        Load active prompt from pipeline_prompts table using shared session factory.
        Returns (prompt_id, content). prompt_id is None for hardcoded fallbacks -
        there's no real PipelinePrompt row backing those, so no FK value exists.
        """
        try:
            from sqlalchemy import text
            from pipeline.database import session_ctx

            with session_ctx() as s:
                row = s.execute(
                    text("""
                        SELECT id, content FROM pipeline_prompts
                        WHERE name = :name AND is_active = TRUE
                        LIMIT 1
                    """),
                    {"name": analysis_type},
                ).fetchone()
                if row:
                    return int(row[0]), str(row[1])

        except Exception as exc:
            logger.warning("Could not load prompt from DB (%s) - using hardcoded fallback", exc)

        from pipeline.llm.prompts import ESGRC_MODULE_UNIFIED, APEX_GENERAL_RISK, APEX_SPC_RPN
        fallbacks = {
            "MODULE_UNIFIED": ESGRC_MODULE_UNIFIED,
            "GENERAL_RISK":   APEX_GENERAL_RISK,
            "SPC_RPN":        APEX_SPC_RPN,
        }
        template = fallbacks.get(analysis_type)
        if not template:
            raise ValueError(f"Unknown analysis_type: {analysis_type}")
        return None, template

    # ── Report download ───────────────────────────────────────────────────────

    def _download_report(self, r2_path: str) -> str:
        """Download report text from R2 directly into memory (no disk I/O)."""
        from pipeline.tasks.r2 import download_text
        return download_text(r2_path)

    # ── API call with retry ───────────────────────────────────────────────────

    def _call_with_retry(self, model: str, prompt: str):
        """Call Anthropic API with exponential backoff retry."""
        last_exc = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._anthropic.messages.create(
                    model=model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response

            except anthropic.AuthenticationError as exc:
                # Don't retry - bad API key
                logger.error("Anthropic authentication error - check ANTHROPIC_API_KEY")
                raise

            except anthropic.BadRequestError as exc:
                # Don't retry - malformed prompt
                logger.error("Anthropic bad request: %s", exc)
                raise

            except (
                anthropic.RateLimitError,
                anthropic.APITimeoutError,
                anthropic.APIConnectionError,
            ) as exc:
                last_exc = exc
                if attempt == MAX_RETRIES:
                    break

                delay = INITIAL_DELAY * (BACKOFF_FACTOR ** (attempt - 1))
                jitter = random.uniform(-JITTER, JITTER)
                sleep_time = max(0.1, delay + jitter)

                logger.warning(
                    "Anthropic API error (attempt %d/%d): %s - retrying in %.1fs",
                    attempt, MAX_RETRIES, type(exc).__name__, sleep_time,
                )
                time.sleep(sleep_time)

            except anthropic.APIStatusError as exc:
                if exc.status_code == 529:  # Overloaded
                    last_exc = exc
                    if attempt == MAX_RETRIES:
                        break

                    delay = INITIAL_DELAY * (BACKOFF_FACTOR ** (attempt - 1))
                    jitter = random.uniform(-JITTER, JITTER)
                    sleep_time = max(0.1, delay + jitter)

                    logger.warning(
                        "Anthropic overloaded (attempt %d/%d) - retrying in %.1fs",
                        attempt, MAX_RETRIES, sleep_time,
                    )
                    time.sleep(sleep_time)
                else:
                    raise

        raise last_exc

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_to_r2(
        self,
        response_text: str,
        run_id: str,
        step_result_id: str,
        analysis_type: str,
    ) -> Optional[str]:
        """Save recommendation text to R2 directly from memory (no disk I/O)."""
        try:
            from pipeline.tasks.r2 import upload_text, run_key

            org_id = self._get_org_id(run_id)
            if not org_id:
                return None

            step_num = self._get_step_number(step_result_id)
            filename = f"recommendation_{analysis_type.lower()}_{step_result_id[:8]}.txt"
            r2_key = run_key(str(org_id), run_id, step_num, filename)
            upload_text(response_text, r2_key)
            return r2_key

        except Exception as exc:
            logger.warning("Failed to save recommendation to R2: %s", exc)
            return None

    def _save_to_db(
        self,
        run_id: str,
        step_result_id: str,
        analysis_type: str,
        prompt_id: Optional[int],
        prompt_hash: str,
        model_used: str,
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        response_text: str,
        r2_path: Optional[str],
    ) -> None:
        """Persist LLM output to pipeline_llm_outputs using shared session factory."""
        import uuid as _uuid
        from datetime import datetime, timezone
        from sqlalchemy import text
        from pipeline.database import session_ctx

        try:
            with session_ctx() as s:
                s.execute(
                    text("""
                        INSERT INTO pipeline_llm_outputs
                            (id, run_id, step_result_id, analysis_type, prompt_id,
                             prompt_hash, model_used, input_tokens, output_tokens,
                             response_text, output_file_r2_path, created_at)
                        VALUES
                            (:id, :run_id, :step_id, :atype, :prompt_id,
                             :phash, :model, :itok, :otok,
                             :rtext, :r2path, :created_at)
                    """),
                    {
                        "id": str(_uuid.uuid4()),
                        "run_id": run_id,
                        "step_id": step_result_id,
                        "atype": analysis_type,
                        # Was accepted as an argument and then dropped on the
                        # floor: neither the column list nor the parameters
                        # mentioned it, so every row written since
                        # 20260622_add_prompt_id had a NULL prompt_id and no way
                        # to tell which prompt version produced the output.
                        "prompt_id": prompt_id,
                        "phash": prompt_hash,
                        "model": model_used,
                        "itok": input_tokens,
                        "otok": output_tokens,
                        "rtext": response_text,
                        "r2path": r2_path,
                        # Bound parameter rather than NOW(): NOW() is a
                        # PostgreSQL function and raises "no such function" on
                        # SQLite, which is what the single-container demo runs
                        # on - every Claude step there failed at persistence.
                        # Every other raw-SQL write in the codebase already
                        # passes a Python datetime for this reason.
                        "created_at": datetime.now(timezone.utc),
                    },
                )
        except Exception as exc:
            logger.error("Failed to save LLM output to DB: %s", exc)
            raise

    def _cache_result_for_ui(
        self, run_id: str, step_result_id: str, response_text: str
    ) -> None:
        """Write recommendation to Redis so UI can display it immediately."""
        if not self._redis:
            return
        try:
            key = f"pipeline:{run_id}:llm:{step_result_id}"
            self._redis.set(key, response_text, ex=RESULT_CACHE_TTL)
        except Exception as exc:
            logger.warning("Failed to cache LLM result in Redis: %s", exc)

    # ── Result cache ──────────────────────────────────────────────────────────

    @staticmethod
    def _result_cache_key(prompt_hash: str, org_id: Optional[str]) -> str:
        """Org-scoped cache key. org_id defaults to 'unscoped' only when it could
        not be resolved at all (e.g. a run row that vanished) - never silently
        drops the scope for a real org."""
        return f"pipeline:llm:cache:{org_id if org_id is not None else 'unscoped'}:{prompt_hash}"

    def _check_result_cache(
        self, prompt_hash: str, org_id: Optional[str] = None
    ) -> Optional[LLMResult]:
        if not self._redis:
            return None
        try:
            raw = self._redis.get(self._result_cache_key(prompt_hash, org_id))
            if raw:
                data = json.loads(raw)
                return LLMResult(**data, from_cache=True)
        except Exception:
            pass
        return None

    def _store_result_cache(
        self, prompt_hash: str, result: LLMResult, org_id: Optional[str] = None
    ) -> None:
        if not self._redis:
            return
        try:
            data = {
                "response_text": result.response_text,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "model_used": result.model_used,
                "prompt_hash": result.prompt_hash,
                "r2_path": result.r2_path,
                "prompt_id": result.prompt_id,
            }
            self._redis.set(
                self._result_cache_key(prompt_hash, org_id),
                json.dumps(data),
                ex=RESULT_CACHE_TTL,
            )
        except Exception:
            pass

    # ── Langfuse tracing ──────────────────────────────────────────────────────

    def _trace_langfuse(self, **kwargs) -> None:
        """Non-blocking Langfuse trace. Never raises - tracing must not block pipeline."""
        if not self._langfuse:
            return
        try:
            trace = self._langfuse.trace(
                name=kwargs.get("analysis_type", "unknown"),
                metadata={
                    "run_id":          kwargs.get("run_id"),
                    "step_result_id":  kwargs.get("step_result_id"),
                    "model_used":      kwargs.get("model_used"),
                    "prompt_hash":     kwargs.get("prompt_hash"),
                    "input_tokens":    kwargs.get("input_tokens"),
                    "output_tokens":   kwargs.get("output_tokens"),
                },
            )
            trace.generation(
                name="claude_api_call",
                model=kwargs.get("model_used"),
                input=kwargs.get("prompt_text", "")[:500],
                output=kwargs.get("response_text", "")[:500],
                usage={
                    "input": kwargs.get("input_tokens", 0),
                    "output": kwargs.get("output_tokens", 0),
                },
            )
        except Exception as exc:
            logger.warning("Langfuse trace failed (non-blocking): %s", exc)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _init_redis():
        try:
            import redis as redis_lib
            r = redis_lib.Redis.from_url(
                os.environ.get("REDIS_URL", "redis://redis:6379/0"),
                decode_responses=True,
                socket_connect_timeout=2,
            )
            r.ping()
            return r
        except Exception as exc:
            logger.warning("Redis unavailable for LLMClient (%s) - caching disabled", exc)
            return None

    @staticmethod
    def _init_langfuse():
        pub_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        sec_key = os.environ.get("LANGFUSE_SECRET_KEY")
        if not pub_key or not sec_key:
            return None
        try:
            from langfuse import Langfuse
            return Langfuse(public_key=pub_key, secret_key=sec_key)
        except Exception as exc:
            logger.warning("Langfuse init failed (%s) - tracing disabled", exc)
            return None

    def _get_org_id(self, run_id: str) -> Optional[int]:
        try:
            from sqlalchemy import text
            from pipeline.database import session_ctx
            with session_ctx() as s:
                row = s.execute(
                    text("SELECT org_id FROM pipeline_runs WHERE id = :r"),
                    {"r": run_id},
                ).fetchone()
                return int(row[0]) if row else None
        except Exception:
            return None

    def _get_step_number(self, step_result_id: str) -> int:
        try:
            from sqlalchemy import text
            from pipeline.database import session_ctx
            with session_ctx() as s:
                row = s.execute(
                    text("SELECT step_number FROM pipeline_step_results WHERE id = :id"),
                    {"id": step_result_id},
                ).fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0
