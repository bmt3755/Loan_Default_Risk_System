"""Checker 2b — detects income drops and unusual spending in recent transactions."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base_checker import BaseChecker


class TransactionPatternChecker(BaseChecker):

    @property
    def checker_name(self) -> str:
        return "transaction_pattern"

    def build_prompt(self, borrower: dict[str, Any]) -> str:
        monthly_income = borrower.get("monthly_income", 0)
        # Cap at 10 most recent transactions to keep prompt focused
        recent_transactions = borrower.get("recent_transactions", [])[-10:]

        return f"""Assess transaction pattern risk for this borrower.

Monthly income: ${monthly_income:,.2f}
Recent transactions (up to last 10): {json.dumps(recent_transactions)}

Look for: sudden income drops, spending consistently exceeding income,
large unexpected withdrawals, or erratic transaction patterns that signal financial stress.

Scoring guide:
- 1–3 (low risk): Stable income, spending comfortably within income, no unusual patterns
- 4–6 (medium risk): Minor income variability or occasional overspending
- 7–10 (high risk): Significant income drops, spending exceeds income, or erratic/alarming patterns

Return JSON: score (1–10), label (low/medium/high), reason (one sentence).
"""
