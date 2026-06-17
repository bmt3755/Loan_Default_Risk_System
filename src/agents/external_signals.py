"""Checker 2d — assesses employment stability and regional economic risk signals."""

from __future__ import annotations

from typing import Any

from src.agents.base_checker import BaseChecker


class ExternalSignalsChecker(BaseChecker):

    @property
    def checker_name(self) -> str:
        return "external_signals"

    def build_prompt(self, borrower: dict[str, Any]) -> str:
        employment_status = borrower.get("employment_status", "unknown")
        region = borrower.get("region", "unknown")

        return f"""Assess external risk signals for this borrower.

Employment status: {employment_status}
Region: {region}

Look for: job instability (unemployed, recently laid off, contract/gig work),
employment in high-risk sectors (retail, hospitality, construction), and
regions with historically high unemployment or economic stress.

Scoring guide:
- 1–3 (low risk): Full-time stable employment in a resilient sector and stable region
- 4–6 (medium risk): Part-time, contract, or employment in a volatile sector or uncertain region
- 7–10 (high risk): Unemployed, recently laid off, gig-only income, or economically distressed area

Return JSON: score (1–10), label (low/medium/high), reason (one sentence).
"""
