"""Checker 2c — evaluates on-time vs late/missed loan payment history."""

from __future__ import annotations

import json
from typing import Any

from src.agents.base_checker import BaseChecker


class PaymentHistoryChecker(BaseChecker):

    @property
    def checker_name(self) -> str:
        return "payment_history"

    def build_prompt(self, borrower: dict[str, Any]) -> str:
        loan_amount = borrower.get("loan_amount", 0)
        # Full payment history — every missed payment matters for this checker
        payment_history = borrower.get("payment_history", [])

        return f"""Assess payment history risk for this borrower.

Loan amount: ${loan_amount:,.2f}
Full payment history ({len(payment_history)} records): {json.dumps(payment_history)}

Look for: frequency of late payments, any missed payments, whether issues
are isolated or form a worsening pattern over time.

Scoring guide:
- 1–3 (low risk): All or nearly all payments on time, no missed payments
- 4–6 (medium risk): A few isolated late payments, no misses, no worsening trend
- 7–10 (high risk): Multiple late payments, one or more missed payments, or a clearly worsening pattern

Return JSON: score (1–10), label (low/medium/high), reason (one sentence).
"""
