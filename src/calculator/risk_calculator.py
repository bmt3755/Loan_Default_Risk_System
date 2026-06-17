"""
Risk Calculator — math-only LangGraph node.
Reads the 5 checker scores, averages valid ones, maps to a risk rating.
No LLM. No external calls. Pure logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.state.schema import LoanDefaultState, RiskRating

logger = logging.getLogger(__name__)

# Maps checker name → state slot key
_CHECKER_SLOTS: dict[str, str] = {
    "credit_score":        "credit_score_result",
    "transaction_pattern": "transaction_pattern_result",
    "payment_history":     "payment_history_result",
    "external_signals":    "external_signals_result",
    "debt_to_income":      "debt_to_income_result",
}

_MIN_SCORE = 1.0
_MAX_SCORE = 10.0

# Flag for human review when this many checkers fail
_HUMAN_REVIEW_THRESHOLD = 3


def run(state: LoanDefaultState) -> dict:
    """
    LangGraph node — reads 5 checker slots, returns risk rating + updated metadata.
    Never raises. Defaults to CRITICAL when no valid scores are available.
    """
    succeeded: list[str] = []
    failed: list[str] = []
    valid_scores: list[float] = []

    for checker_name, slot_key in _CHECKER_SLOTS.items():
        result = state.get(slot_key, {})
        status = result.get("status")
        score = result.get("score")

        if status == "success" and _is_valid_score(score):
            valid_scores.append(float(score))
            succeeded.append(checker_name)
            logger.info("[risk_calculator] ✓ %s — score=%.1f included", checker_name, score)
        else:
            failed.append(checker_name)
            logger.warning(
                "[risk_calculator] ✗ %s — excluded (status=%s, score=%s)",
                checker_name, status, score,
            )

    avg = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
    risk_rating = _map_to_rating(valid_scores)
    human_review = len(failed) >= _HUMAN_REVIEW_THRESHOLD

    logger.info(
        "[risk_calculator] avg=%.2f → %s | succeeded=%s failed=%s human_review=%s",
        avg, risk_rating, succeeded, failed, human_review,
    )

    return {
        # Only set risk_rating here — explanation and action are filled by later nodes
        "final_decision": {
            "risk_rating": risk_rating,
        },
        "metadata": {
            # Preserve fields already set by the supervisor (e.g. run_id, started_at)
            **state.get("metadata", {}),
            "checkers_succeeded": succeeded,
            "checkers_failed": failed,
            "human_review_required": human_review,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _map_to_rating(valid_scores: list[float]) -> RiskRating:
    """Map average score to a risk rating. Defaults to CRITICAL when no data."""
    if not valid_scores:
        logger.error("[risk_calculator] No valid scores — all checkers failed. Forcing CRITICAL.")
        return "CRITICAL"

    avg = sum(valid_scores) / len(valid_scores)

    if avg > 6.5:
        return "CRITICAL"
    if avg >= 5.0:
        return "AT_RISK"
    if avg >= 3.0:
        return "WATCH"
    return "STABLE"


def _is_valid_score(score: object) -> bool:
    """Reject scores outside 1–10 or of the wrong type — never silently include garbage."""
    if not isinstance(score, (int, float)):
        return False
    return _MIN_SCORE <= float(score) <= _MAX_SCORE
