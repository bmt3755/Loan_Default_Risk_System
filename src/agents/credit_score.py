"""Checker 2a — evaluates current credit score as a loan default risk signal."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base_checker import BaseChecker


class CreditScoreChecker(BaseChecker):

    @property
    def checker_name(self) -> str:
        return "credit_score"

    def build_prompt(self, borrower: dict[str, Any]) -> str:
        credit_score = borrower.get("credit_score", "not available")
        # Cap at 12 records to keep prompt size reasonable
        payment_history = borrower.get("payment_history", [])[-12:]

        return f"""Assess the credit score risk for this borrower.

Credit score: {credit_score} (scale 300–850; higher = better creditworthiness)
Recent payment records (up to last 12): {json.dumps(payment_history)}

Scoring guide:
- 1–3 (low risk): Score above 720, consistent on-time payments
- 4–6 (medium risk): Score 620–719, occasional late payments
- 7–10 (high risk): Score below 620, multiple missed or late payments, or signs of rapid decline

Return JSON: score (1–10), label (low/medium/high), reason (one sentence).
"""
