"""
Base class for all 5 parallel risk checkers.
Subclasses only define checker_name and build_prompt().
All LLM calling, parsing, validation, and fallback logic lives here.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Literal

from langsmith import traceable
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from src.state.schema import CheckerResult, LoanDefaultState, failed_checker_result

logger = logging.getLogger(__name__)

# Single shared client — thread-safe, reads OPENAI_API_KEY from environment
_openai = OpenAI()

_SYSTEM_PROMPT = (
    "You are a financial risk analyst. "
    "Respond only with valid JSON containing exactly three fields: "
    "score (number 1–10; 1 = lowest risk, 10 = highest risk), "
    "label (exactly one of: low, medium, high), "
    "reason (one plain-English sentence explaining the score)."
)

_MAX_TOKENS = 300
_TEMPERATURE = 0.1  # low temperature for consistent, repeatable scoring
_TIMEOUT_SECONDS = 30.0


class _LLMOutput(BaseModel):
    """Validates the raw JSON returned by gpt-4o-mini before it touches state."""

    score: float = Field(ge=1.0, le=10.0)
    label: Literal["low", "medium", "high"]
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be empty")
        return v.strip()


class BaseChecker(ABC):
    """
    Abstract base class for all parallel risk checkers.
    Subclasses implement checker_name and build_prompt(); nothing else.
    """

    @property
    @abstractmethod
    def checker_name(self) -> str:
        """Unique identifier used in logs, audit trail, and LangSmith traces."""
        ...

    @abstractmethod
    def build_prompt(self, borrower: dict[str, Any]) -> str:
        """Build the domain-specific prompt with relevant borrower fields."""
        ...

    @traceable
    def run(self, state: LoanDefaultState) -> CheckerResult:
        """
        Full execution: build prompt → call LLM → parse → validate → return result.
        Never raises — always returns a CheckerResult (fallback on any failure).
        """
        borrower = state.get("borrower", {})
        bid = borrower.get("borrower_id", "unknown")
        logger.info("[%s] Starting — borrower_id=%s", self.checker_name, bid)

        try:
            prompt = self.build_prompt(borrower)
            raw = self._call_llm(prompt)
            result = self._parse_and_validate(raw)
            logger.info(
                "[%s] Done — score=%.1f label=%s",
                self.checker_name,
                result["score"],
                result["label"],
            )
            return result

        except Exception as exc:
            logger.error("[%s] Failed — %s", self.checker_name, exc, exc_info=True)
            return failed_checker_result(f"{self.checker_name} error: {exc}")

    # ------------------------------------------------------------------
    # Private helpers — not overridden by subclasses
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str) -> str:
        """Call gpt-4o-mini with a 30-second timeout; return the raw JSON string."""
        response = _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            response_format={"type": "json_object"},
            timeout=_TIMEOUT_SECONDS,
        )
        raw = response.choices[0].message.content or ""
        logger.debug("[%s] Raw LLM output: %s", self.checker_name, raw)
        return raw

    def _parse_and_validate(self, raw: str) -> CheckerResult:
        """Parse LLM JSON with Pydantic; reject any out-of-range or missing values."""
        data = json.loads(raw)
        validated = _LLMOutput.model_validate(data)
        return CheckerResult(
            score=round(validated.score, 2),
            label=validated.label,
            reason=validated.reason,
            status="success",
            ran_at=datetime.now(timezone.utc).isoformat(),
        )
