"""Checker 2e — evaluates debt-to-income ratio as a loan default risk signal."""

from __future__ import annotations

from typing import Any

from src.agents.base_checker import BaseChecker


class DebtToIncomeChecker(BaseChecker):

    @property
    def checker_name(self) -> str:
        return "debt_to_income"

    def build_prompt(self, borrower: dict[str, Any]) -> str:
        monthly_income = borrower.get("monthly_income", 0)
        monthly_debt = borrower.get("monthly_debt_payments", 0)
        loan_amount = borrower.get("loan_amount", 0)

        # Calculate DTI here so the LLM gets a pre-computed number, not raw arithmetic
        dti = (monthly_debt / monthly_income * 100) if monthly_income > 0 else 100.0

        return f"""Assess debt-to-income risk for this borrower.

Monthly income: ${monthly_income:,.2f}
Monthly debt payments: ${monthly_debt:,.2f}
Total loan amount: ${loan_amount:,.2f}
Debt-to-income (DTI) ratio: {dti:.1f}%

The DTI ratio is the share of monthly income already committed to debt payments.
Higher DTI means less room to absorb financial shocks before defaulting.

Scoring guide:
- 1–3 (low risk): DTI below 36% — healthy buffer
- 4–6 (medium risk): DTI 36–50% — stretched but manageable
- 7–10 (high risk): DTI above 50% — very little room before default

Return JSON: score (1–10), label (low/medium/high), reason (one sentence).
"""
