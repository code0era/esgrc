"""
LLM Agent - the intelligence layer of the ESGRC agent.

Architecture: Orchestrator-Worker pattern
  - Orchestrator (Claude Sonnet): reads all data, plans, delegates
  - Specialist (Claude Haiku):    fast, cheap, focused on one task

Both use Anthropic's native tool_use feature. The orchestrator calls
tools to read data and to delegate to the specialist. The specialist
calls tools to write results back to the database.

Key production design decisions (from Anthropic best practices):
1. Separate models for separate concerns: Sonnet for reasoning,
   Haiku for classification. This reduces cost by ~80% on batch work.
2. coalesce=True on the scheduler so if two runs overlap, only one fires.
3. max_iterations guard: prevents infinite loops if the LLM misbehaves.
4. All writes are ownership-verified in tools.py before touching the DB.
5. A findings dict is written at the end of every run - always an audit trail.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
import time

import anthropic

from app.config import settings
from app.services.risk_thresholds import RISK_LLM_ASSESSMENT_SCORE

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 20  # hard stop - prevents runaway agent loops

# ─── Tool schemas (what the LLM sees) ─────────────────────────────────────────

ORCHESTRATOR_TOOLS = [
    {
        "name": "read_org_snapshot",
        "description": (
            "Read the full current state of this organisation: ESG metric counts and "
            "average score, risk heatmap summary, and overall compliance rate. "
            "ALWAYS call this first before any other tool."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_unscored_metrics",
        "description": (
            "Read all ESG metrics that have no score yet. Returns metric_id, value, "
            "category name, and benchmark info. Use this to decide which metrics to score."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_open_risks",
        "description": (
            "Read all open risks with their likelihood, impact, risk_score, "
            "due_date, and days_overdue. Use to identify risks needing escalation."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_overdue_requirements",
        "description": (
            "Read compliance requirements that are past their review date and not compliant. "
            "Returns req_id, title, evidence, and days_overdue."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "delegate_scoring",
        "description": (
            "Ask the specialist agent to compute a score for one ESG metric. "
            "Only call this if the metric has a benchmark (has_benchmark=true). "
            "Returns the computed score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_id": {"type": "integer", "description": "The metric ID to score"},
                "value": {"type": "number", "description": "The raw metric value"},
                "category_name": {"type": "string"},
                "target_value": {"type": "number"},
                "baseline_value": {"type": "number"},
                "direction": {"type": "string", "enum": ["lower_is_better", "higher_is_better"]},
            },
            "required": ["metric_id", "value", "category_name", "target_value", "baseline_value", "direction"],
        },
    },
    {
        "name": "delegate_classification",
        "description": (
            "Ask the specialist agent to classify a compliance requirement as "
            "compliant/partial/non_compliant/not_assessed based on the evidence. "
            "Only call this for requirements that HAVE evidence text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "req_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "evidence": {"type": "string"},
            },
            "required": ["req_id", "title", "evidence"],
        },
    },
    {
        "name": "delegate_risk_assessment",
        "description": (
            "Ask the specialist agent to assess whether a risk should be escalated. "
            f"Only call for risks with risk_score >= {RISK_LLM_ASSESSMENT_SCORE}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "current_level": {"type": "string"},
                "risk_score": {"type": "integer"},
                "days_overdue": {"type": "integer"},
            },
            "required": ["risk_id", "title", "risk_score", "days_overdue", "current_level"],
        },
    },
    {
        "name": "write_findings",
        "description": (
            "Record the final structured L1_ESRC_Risk_Assessment. "
            "MUST be called at the end of every run - this is the audit trail and the report. "
            "Pass the complete findings_json as specified in the system prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "findings_json": {
                    "type": "object",
                    "description": "The complete L1_ESRC_Risk_Assessment JSON object.",
                },
            },
            "required": ["findings_json"],
        },
    },
]


# ─── Specialist agent call ─────────────────────────────────────────────────────

def _call_specialist(
    client: anthropic.Anthropic,
    system_prompt: str,
    user_message: str,
) -> dict:
    """
    Call the specialist agent (Claude Haiku) for a focused classification task.
    Returns parsed JSON from the specialist's response.
    Raises ValueError if the response cannot be parsed.
    """
    response = client.messages.create(
        model=settings.SPECIALIST_MODEL,
        max_tokens=256,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract JSON from response if wrapped in text
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Specialist returned non-JSON: {raw[:200]}")


# ─── Orchestrator agent loop ───────────────────────────────────────────────────

def run_llm_batch_for_org(
    db,
    org_id: int,
    org_name: str,
) -> dict:
    """
    Run one full LLM-powered analysis cycle for a single organisation.

    Returns a dict with counts and findings summary.
    """
    from app.agent.tools import (
        read_org_snapshot,
        read_unscored_metrics,
        read_open_risks,
        read_overdue_requirements,
        apply_metric_score,
        apply_requirement_status,
        apply_risk_level,
    )
    from app.agent.prompts import (
        ORCHESTRATOR_SYSTEM,
        SPECIALIST_ESG_SCORER,
        SPECIALIST_COMPLIANCE_CLASSIFIER,
        SPECIALIST_RISK_ASSESSOR,
    )

    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not configured.")

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # NOTE: use .replace(), not .format(). ORCHESTRATOR_SYSTEM embeds a large
    # literal JSON example full of "{"/"}" - str.format() parses those braces as
    # format fields and raises KeyError('\n  "L1_ESRC_Risk_Assessment"'). Explicit
    # replacement substitutes only the two real placeholders and leaves the JSON
    # braces untouched.
    system = (
        ORCHESTRATOR_SYSTEM
        .replace("{org_name}", org_name)
        .replace("{today_date}", today)
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Begin the analysis cycle for organisation: {org_name} (id={org_id}). "
                "Start by reading the org snapshot, then work through what needs attention."
            ),
        }
    ]

    # Counters
    metrics_scored = 0
    requirements_classified = 0
    risks_escalated = 0
    findings = {}
    iterations = 0

    while iterations < MAX_ITERATIONS:
        iterations += 1

        response = client.messages.create(
            model=settings.ORCHESTRATOR_MODEL,
            max_tokens=settings.ORCHESTRATOR_MAX_TOKENS,
            system=system,
            tools=ORCHESTRATOR_TOOLS,
            messages=messages,
        )

        # Add assistant response to message history.
        # Convert ContentBlock Pydantic objects to plain dicts for serialisation
        # (required for multi-turn: SDK accepts both, but plain dicts are safer
        # across SDK versions and avoid any Pydantic model validation on re-use).
        messages.append({
            "role": "assistant",
            "content": [block.model_dump() for block in response.content],
        })

        # Check if done
        if response.stop_reason == "end_turn":
            logger.info(
                "Orchestrator finished for org_id=%s after %s iterations",
                org_id, iterations,
            )
            break

        if response.stop_reason != "tool_use":
            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            result: Any = None

            try:
                # ── Read tools ────────────────────────────────────────────────
                if tool_name == "read_org_snapshot":
                    result = read_org_snapshot(db, org_id)

                elif tool_name == "read_unscored_metrics":
                    result = read_unscored_metrics(db, org_id)

                elif tool_name == "read_open_risks":
                    result = read_open_risks(db, org_id)

                elif tool_name == "read_overdue_requirements":
                    result = read_overdue_requirements(db, org_id)

                # ── Delegation to specialist ──────────────────────────────────
                elif tool_name == "delegate_scoring":
                    specialist_result = _call_specialist(
                        client,
                        SPECIALIST_ESG_SCORER,
                        json.dumps(tool_input),
                    )
                    score = specialist_result.get("score", 0)
                    write_result = apply_metric_score(
                        db, org_id, tool_input["metric_id"], score
                    )
                    if write_result["success"]:
                        metrics_scored += 1
                    result = {**specialist_result, **write_result}

                elif tool_name == "delegate_classification":
                    specialist_result = _call_specialist(
                        client,
                        SPECIALIST_COMPLIANCE_CLASSIFIER,
                        json.dumps(tool_input),
                    )
                    status = specialist_result.get("status", "not_assessed")
                    reasoning = specialist_result.get("reasoning", "")
                    write_result = apply_requirement_status(
                        db, org_id, tool_input["req_id"], status, reasoning
                    )
                    if write_result["success"]:
                        requirements_classified += 1
                    result = {**specialist_result, **write_result}

                elif tool_name == "delegate_risk_assessment":
                    specialist_result = _call_specialist(
                        client,
                        SPECIALIST_RISK_ASSESSOR,
                        json.dumps(tool_input),
                    )
                    recommended_level = specialist_result.get(
                        "recommended_level", tool_input.get("current_level", "medium")
                    )
                    action = specialist_result.get("action", "")
                    write_result = apply_risk_level(
                        db, org_id, tool_input["risk_id"], recommended_level, action
                    )
                    if write_result["success"]:
                        risks_escalated += 1
                    result = {**specialist_result, **write_result}

                # ── Findings ──────────────────────────────────────────────────
                elif tool_name == "write_findings":
                    # Extract the structured L1_ESRC_Risk_Assessment JSON
                    findings = tool_input.get("findings_json", tool_input)
                    logger.info(
                        "Findings written for org_id=%s - L1_ESRC_Risk_Assessment recorded",
                        org_id,
                    )
                    result = {"recorded": True}

                else:
                    result = {"error": f"Unknown tool: {tool_name}"}

            except Exception as exc:
                logger.exception("Tool %s failed for org_id=%s: %s", tool_name, org_id, exc)
                result = {"error": str(exc)}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        # Feed tool results back to the orchestrator
        messages.append({"role": "user", "content": tool_results})

    else:
        logger.warning(
            "Orchestrator hit MAX_ITERATIONS (%s) for org_id=%s",
            MAX_ITERATIONS, org_id,
        )

    return {
        "metrics_scored": metrics_scored,
        "requirements_classified": requirements_classified,
        "risks_escalated": risks_escalated,
        "findings": findings,
        "iterations": iterations,
    }
