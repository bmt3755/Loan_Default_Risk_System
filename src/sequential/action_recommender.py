"""
Action Recommender — sequential LangGraph node.
Step 1: maps risk rating to a safe default action (no LLM, pure rule).
Step 2: asks gpt-4o-mini whether the default should be overridden given the full explanation.
Falls back to the rule-based default on any failure — never crashes.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from langsmith import traceable
from openai import OpenAI
from pydantic import BaseModel, field_validator

from src.state.schema import LoanDefaultState, RecommendedAction

logger = logging.getLogger(__name__)
_openai = OpenAI()

_TIMEOUT_SECONDS = 30.0
_MAX_TOKENS = 200
_TEMPERATURE = 0.1

# Step 1 — rule-based default mapping, no LLM involved
_DEFAULT_ACTIONS: dict[str, RecommendedAction] = {
    "STABLE":   "do_nothing",
    "WATCH":    "send_reminder",
    "AT_RISK":  "offer_payment_plan",
    "CRITICAL": "escalate_to_collections",
}

# Conservative fallback for any rating not in the map
_SAFE_FALLBACK: RecommendedAction = "escalate_to_collections"


# ---------------------------------------------------------------------------
# Pydantic model — all 3 fields required, action locked to 4 allowed values
# ---------------------------------------------------------------------------

class _LLMOutput(BaseModel):
    """Validates the LLM's override response."""

    should_override: bool
    action: Literal[
        "do_nothing",
        "send_reminder",
        "offer_payment_plan",
        "escalate_to_collections",
    ]
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be empty")
        return v.strip()


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

@traceable
def run(state: LoanDefaultState) -> dict:
    """
    Determines the recommended action for this borrower.
    Step 1: rule-based default from rating (always runs, never fails).
    Step 2: LLM checks if default should be overridden (falls back to default on any failure).
    """
    final_decision = state.get("final_decision", {})
    risk_rating = final_decision.get("risk_rating", "UNKNOWN")
    explanation = final_decision.get("explanation", "")
    borrower_id = state.get("borrower", {}).get("borrower_id", "unknown")

    logger.info(
        "[action_recommender] Starting — borrower_id=%s rating=%s",
        borrower_id, risk_rating,
    )

    # Step 1: rule-based default — always succeeds
    default_action = _DEFAULT_ACTIONS.get(risk_rating, _SAFE_FALLBACK)
    logger.info(
        "[action_recommender] Rule-based default for %s → %s",
        risk_rating, default_action,
    )

    # Step 2: LLM override check — falls back to default on any failure
    final_action = default_action
    try:
        prompt = _build_prompt(risk_rating, explanation, default_action)
        raw = _call_llm(prompt)
        validated = _parse_and_validate(raw)

        if validated.should_override and validated.action != default_action:
            logger.info(
                "[action_recommender] LLM override accepted: %s → %s | reason: %s",
                default_action, validated.action, validated.reason,
            )
            final_action = validated.action
        else:
            logger.info(
                "[action_recommender] LLM kept default: %s | reason: %s",
                default_action, validated.reason,
            )

    except Exception as exc:
        logger.error(
            "[action_recommender] LLM check failed (%s) — keeping rule-based default: %s",
            exc, default_action, exc_info=True,
        )

    logger.info("[action_recommender] Final action → %s", final_action)

    return {
        # Preserve risk_rating and explanation already written by earlier nodes
        "final_decision": {
            **state.get("final_decision", {}),
            "recommended_action": final_action,
        }
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_prompt(
    risk_rating: str,
    explanation: str,
    default_action: RecommendedAction,
) -> str:
    return f"""A borrower has been rated {risk_rating} by an automated loan risk system.

Default action for this rating: {default_action}

Full explanation of why this rating was given:
{explanation}

The 4 possible actions are:
- do_nothing: borrower is stable, no intervention needed
- send_reminder: send a gentle payment reminder
- offer_payment_plan: proactively offer a restructured payment plan
- escalate_to_collections: immediately escalate to the collections team

Should the default action ({default_action}) be overridden based on the full explanation above?

Return JSON with exactly these 3 fields:
- should_override: true or false
- action: the chosen action (one of the 4 above — return the default if not overriding)
- reason: one sentence explaining your decision

Only override if the explanation contains clear, specific evidence that the default action is inappropriate.
"""


def _call_llm(prompt: str) -> str:
    response = _openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior loan risk officer. "
                    "Respond only with valid JSON matching the requested structure exactly."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        response_format={"type": "json_object"},
        timeout=_TIMEOUT_SECONDS,
    )
    raw = response.choices[0].message.content or ""
    logger.debug("[action_recommender] Raw LLM output: %s", raw)
    return raw


def _parse_and_validate(raw: str) -> _LLMOutput:
    data = json.loads(raw)
    validated = _LLMOutput.model_validate(data)
    logger.info(
        "[action_recommender] Validated — should_override=%s action=%s reason=%r",
        validated.should_override, validated.action, validated.reason,
    )
    return validated
