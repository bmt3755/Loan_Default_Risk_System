from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Literal, TypedDict

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Allowed values
# ---------------------------------------------------------------------------

RiskLabel = Literal["low", "medium", "high"]
RiskRating = Literal["STABLE", "WATCH", "AT_RISK", "CRITICAL"]
CheckerStatus = Literal["success", "failed", "pending"]
RecommendedAction = Literal[
    "do_nothing",
    "send_reminder",
    "offer_payment_plan",
    "escalate_to_collections",
]


# ---------------------------------------------------------------------------
# Borrower Input — validated at entry, fails fast if required fields are missing
# ---------------------------------------------------------------------------

class BorrowerInput(BaseModel):
    borrower_id: str
    loan_id: str
    loan_amount: float = Field(gt=0)
    credit_score: int = Field(ge=300, le=850)
    employment_status: str
    monthly_income: float = Field(gt=0)
    monthly_debt_payments: float = Field(ge=0)
    recent_transactions: List[dict[str, Any]] = Field(default_factory=list)
    payment_history: List[dict[str, Any]] = Field(default_factory=list)
    region: str

    @field_validator("borrower_id", "loan_id", "employment_status", "region")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("monthly_debt_payments")
    @classmethod
    def debt_sanity_check(cls, v: float, info: Any) -> float:
        # Debt payments more than 2x income is almost certainly a data error
        income = info.data.get("monthly_income")
        if income is not None and v > income * 2:
            raise ValueError("monthly_debt_payments is more than 2x monthly_income — likely a data error")
        return v


# ---------------------------------------------------------------------------
# Checker Result — one dedicated slot per checker (no shared fields, no collision)
# ---------------------------------------------------------------------------

class CheckerResult(TypedDict, total=False):
    score: float          # 1.0–10.0  (higher = more risk)
    label: RiskLabel      # low / medium / high
    reason: str           # plain-English explanation for auditors
    status: CheckerStatus # success / failed / pending
    ran_at: str           # ISO 8601 timestamp


def failed_checker_result(reason: str) -> CheckerResult:
    """Used when a checker crashes — defaults to worst-case score (conservative for a financial system)."""
    return CheckerResult(
        score=10.0,
        label="high",
        reason=reason,
        status="failed",
        ran_at=_now(),
    )


def pending_checker_result() -> CheckerResult:
    """Initial state before a checker runs."""
    return CheckerResult(status="pending", ran_at=_now())


# ---------------------------------------------------------------------------
# Audit Entry — timestamped record; written only by the supervisor
# ---------------------------------------------------------------------------

class AuditEntry(TypedDict):
    step: str       # which stage produced this entry
    event: str      # what happened (plain English)
    timestamp: str  # ISO 8601


def make_audit_entry(step: str, event: str) -> AuditEntry:
    return AuditEntry(step=step, event=event, timestamp=_now())


# ---------------------------------------------------------------------------
# Final Decision — populated by the 3 sequential agents after the parallel phase
# ---------------------------------------------------------------------------

class FinalDecision(TypedDict, total=False):
    risk_rating: RiskRating
    explanation: str
    recommended_action: RecommendedAction


# ---------------------------------------------------------------------------
# Run Metadata — tracks which checkers succeeded/failed for debugging
# ---------------------------------------------------------------------------

class RunMetadata(TypedDict, total=False):
    run_id: str
    started_at: str
    completed_at: str
    checkers_succeeded: List[str]
    checkers_failed: List[str]
    errors: dict[str, str]       # checker_name → error message
    human_review_required: bool  # set to True when all checkers fail


# ---------------------------------------------------------------------------
# Main LangGraph State — the single structure flowing through the entire graph
# ---------------------------------------------------------------------------

class LoanDefaultState(TypedDict, total=False):

    # Stage 1: Input
    borrower: dict[str, Any]                   # serialized BorrowerInput

    # Stage 2: 5 dedicated checker slots — each checker writes only its own slot
    credit_score_result: CheckerResult
    transaction_pattern_result: CheckerResult
    payment_history_result: CheckerResult
    external_signals_result: CheckerResult
    debt_to_income_result: CheckerResult

    # Stage 3: Final decision (sequential)
    final_decision: FinalDecision

    # Supervisor-managed
    metadata: RunMetadata
    audit_trail: List[AuditEntry]              # supervisor always writes the full updated list


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
