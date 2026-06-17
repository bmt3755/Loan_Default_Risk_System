"""
Explanation Generator — sequential LangGraph node.
Asks gpt-4o-mini to return structured JSON (one sentence per checker + conclusion),
validates all 6 fields with Pydantic, then assembles into a plain-English explanation.
Falls back to a template built from checker reasons in state if anything fails.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langsmith import traceable
from openai import OpenAI
from pydantic import BaseModel, field_validator

from src.state.schema import LoanDefaultState

logger = logging.getLogger(__name__)
_openai = OpenAI()

_TIMEOUT_SECONDS = 30.0
_MAX_TOKENS = 600
_TEMPERATURE = 0.2  # slightly higher than checkers — natural language benefits from slight variation

_CHECKER_LABELS: dict[str, str] = {
    "credit_score":        "Credit Score",
    "transaction_pattern": "Transaction Patterns",
    "payment_history":     "Payment History",
    "external_signals":    "External Signals",
    "debt_to_income":      "Debt-to-Income Ratio",
}

_SLOT_TO_CHECKER: dict[str, str] = {
    "credit_score_result":        "credit_score",
    "transaction_pattern_result": "transaction_pattern",
    "payment_history_result":     "payment_history",
    "external_signals_result":    "external_signals",
    "debt_to_income_result":      "debt_to_income",
}

_RATING_DESCRIPTIONS: dict[str, str] = {
    "STABLE":   "the borrower appears financially stable with low default risk",
    "WATCH":    "the borrower shows early warning signs that warrant monitoring",
    "AT_RISK":  "the borrower is at elevated risk and may struggle to meet obligations",
    "CRITICAL": "the borrower is at critical risk of defaulting and requires immediate attention",
}


# ---------------------------------------------------------------------------
# Pydantic model — all 6 fields required, none optional
# ---------------------------------------------------------------------------

class _LLMOutput(BaseModel):
    """Validates the structured JSON from gpt-4o-mini. Every field must be present and non-empty."""

    credit_score_summary: str
    transaction_pattern_summary: str
    payment_history_summary: str
    external_signals_summary: str
    debt_to_income_summary: str
    overall_conclusion: str

    @field_validator(
        "credit_score_summary",
        "transaction_pattern_summary",
        "payment_history_summary",
        "external_signals_summary",
        "debt_to_income_summary",
        "overall_conclusion",
    )
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("explanation field must not be empty")
        return v.strip()


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

@traceable
def run(state: LoanDefaultState) -> dict:
    """
    Reads risk_rating + all 5 checker results; writes plain-English explanation to final_decision.
    Never raises — falls back to a template explanation built from checker reasons in state.
    """
    final_decision = state.get("final_decision", {})
    risk_rating = final_decision.get("risk_rating", "UNKNOWN")
    borrower_id = state.get("borrower", {}).get("borrower_id", "unknown")

    logger.info(
        "[explanation_generator] Starting — borrower_id=%s rating=%s",
        borrower_id, risk_rating,
    )

    try:
        checker_data = _extract_checker_data(state)
        prompt = _build_prompt(risk_rating, checker_data)
        raw = _call_llm(prompt)
        validated = _parse_and_validate(raw)
        explanation = _assemble_explanation(risk_rating, validated)
        logger.info("[explanation_generator] Done — explanation assembled from structured LLM output")

    except Exception as exc:
        logger.error(
            "[explanation_generator] Failed (%s) — using fallback explanation",
            exc, exc_info=True,
        )
        explanation = _fallback_explanation(risk_rating, state)

    return {
        # Preserve risk_rating already written by the risk calculator
        "final_decision": {
            **state.get("final_decision", {}),
            "explanation": explanation,
        }
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_checker_data(state: LoanDefaultState) -> dict[str, dict[str, Any]]:
    """Pull score, label, reason, and status from each checker slot in state."""
    data: dict[str, dict[str, Any]] = {}
    for slot_key, checker_name in _SLOT_TO_CHECKER.items():
        result = state.get(slot_key, {})
        data[checker_name] = {
            "score":  result.get("score", "N/A"),
            "label":  result.get("label", "unknown"),
            "reason": result.get("reason", "no details available"),
            "status": result.get("status", "unknown"),
        }
    return data


def _build_prompt(risk_rating: str, checker_data: dict[str, dict[str, Any]]) -> str:
    checker_lines = "\n".join(
        f"- {_CHECKER_LABELS.get(name, name)}: "
        f"score={d['score']}, label={d['label']}, status={d['status']}, reason={d['reason']}"
        for name, d in checker_data.items()
    )

    return f"""You are writing a risk explanation for a bank's loan review team.

The borrower has been rated: {risk_rating}

The 5 risk signals that produced this rating:
{checker_lines}

Return a JSON object with exactly these 6 fields — one plain-English sentence each:
- credit_score_summary: what the credit score signal means for this borrower
- transaction_pattern_summary: what the transaction pattern signal means
- payment_history_summary: what the payment history signal means
- external_signals_summary: what the external signals mean
- debt_to_income_summary: what the debt-to-income signal means
- overall_conclusion: one sentence tying all signals together and explaining the {risk_rating} rating

Rules:
- Every field must be exactly one clear sentence
- Write for a bank risk officer — factual, direct, no jargon
- Do NOT invent information not present in the signals above
- If a checker has status=failed, note that it was unavailable
"""


def _call_llm(prompt: str) -> str:
    response = _openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a financial risk analyst. "
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
    logger.debug("[explanation_generator] Raw LLM output: %s", raw)
    return raw


def _parse_and_validate(raw: str) -> _LLMOutput:
    data = json.loads(raw)
    validated = _LLMOutput.model_validate(data)
    logger.info(
        "[explanation_generator] Validated 6 fields — "
        "credit=%r transaction=%r payment=%r external=%r dti=%r conclusion=%r",
        validated.credit_score_summary,
        validated.transaction_pattern_summary,
        validated.payment_history_summary,
        validated.external_signals_summary,
        validated.debt_to_income_summary,
        validated.overall_conclusion,
    )
    return validated


def _assemble_explanation(risk_rating: str, validated: _LLMOutput) -> str:
    """Stitch the 6 validated sentences into a readable explanation paragraph."""
    rating_desc = _RATING_DESCRIPTIONS.get(
        risk_rating, "the borrower's risk level has been assessed"
    )
    lines = [
        f"This borrower has been rated {risk_rating}, meaning {rating_desc}.",
        "",
        f"Credit Score: {validated.credit_score_summary}",
        f"Transaction Patterns: {validated.transaction_pattern_summary}",
        f"Payment History: {validated.payment_history_summary}",
        f"External Signals: {validated.external_signals_summary}",
        f"Debt-to-Income: {validated.debt_to_income_summary}",
        "",
        validated.overall_conclusion,
    ]
    return "\n".join(lines)


def _fallback_explanation(risk_rating: str, state: LoanDefaultState) -> str:
    """
    Template-based fallback — pulls checker reasons directly from state.
    No LLM call. Used when the primary path fails.
    """
    logger.warning(
        "[explanation_generator] Building fallback explanation from checker reasons in state"
    )
    rating_desc = _RATING_DESCRIPTIONS.get(
        risk_rating, "the borrower's risk level has been assessed"
    )
    lines = [
        f"This borrower has been rated {risk_rating}, meaning {rating_desc}.",
        "",
        "(Note: explanation generated from raw checker data due to a processing error.)",
        "",
    ]
    for slot_key, checker_name in _SLOT_TO_CHECKER.items():
        result = state.get(slot_key, {})
        label = _CHECKER_LABELS.get(checker_name, checker_name)
        reason = result.get("reason", "no details available")
        status = result.get("status", "unknown")
        if status == "failed":
            lines.append(f"{label}: Checker was unavailable during this assessment.")
        else:
            lines.append(f"{label}: {reason}")

    return "\n".join(lines)
