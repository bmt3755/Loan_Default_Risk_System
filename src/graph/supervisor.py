"""
Supervisor node — entry point of the graph.
Validates borrower input, initializes all state fields, then hands off to the parallel checkers.
Fails immediately if required borrower fields are missing — before any LLM calls are made.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from src.state.schema import (
    BorrowerInput,
    LoanDefaultState,
    make_audit_entry,
    pending_checker_result,
)

logger = logging.getLogger(__name__)


def run(state: LoanDefaultState) -> dict:
    """
    Validates the borrower dict in state, then initializes all fields the graph depends on.
    Raises ValueError on invalid input — stops the graph before wasting any LLM calls.
    """
    raw_borrower = state.get("borrower", {})
    bid = raw_borrower.get("borrower_id", "unknown")
    logger.info("[supervisor] Starting — borrower_id=%s", bid)

    # Fail fast — validate before anything else runs
    try:
        validated = BorrowerInput.model_validate(raw_borrower)
    except ValidationError as exc:
        logger.error("[supervisor] Invalid borrower input: %s", exc)
        raise ValueError(f"Invalid borrower input — {exc}") from exc

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("[supervisor] Validated — run_id=%s borrower_id=%s", run_id, validated.borrower_id)

    return {
        # Clean, validated borrower data
        "borrower": validated.model_dump(),

        # Initialize all 5 checker slots as pending — state is never empty downstream
        "credit_score_result":        pending_checker_result(),
        "transaction_pattern_result": pending_checker_result(),
        "payment_history_result":     pending_checker_result(),
        "external_signals_result":    pending_checker_result(),
        "debt_to_income_result":      pending_checker_result(),

        # Initialize metadata
        "metadata": {
            "run_id":                run_id,
            "started_at":            started_at,
            "checkers_succeeded":    [],
            "checkers_failed":       [],
            "errors":                {},
            "human_review_required": False,
        },

        # First audit entry
        "audit_trail": [
            make_audit_entry(
                step="supervisor",
                event=f"Evaluation started for borrower {validated.borrower_id}",
            )
        ],
    }
