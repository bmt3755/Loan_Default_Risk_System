"""
Graph assembly — wires all nodes into a single compiled LangGraph runnable.

Flow:
    supervisor
        ↓ (fan-out — all 5 run in parallel)
    [credit_score, transaction_pattern, payment_history, external_signals, debt_to_income]
        ↓ (fan-in — LangGraph waits for all 5 before proceeding)
    risk_calculator → explanation_generator → action_recommender → END
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from src.agents.credit_score import CreditScoreChecker
from src.agents.debt_to_income import DebtToIncomeChecker
from src.agents.external_signals import ExternalSignalsChecker
from src.agents.payment_history import PaymentHistoryChecker
from src.agents.transaction_pattern import TransactionPatternChecker
from src.calculator import risk_calculator
from src.graph import supervisor
from src.sequential import action_recommender, explanation_generator
from src.state.schema import CheckerResult, LoanDefaultState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Checker instances — one per checker class, shared across all graph runs
# ---------------------------------------------------------------------------

_credit_score_checker        = CreditScoreChecker()
_transaction_pattern_checker = TransactionPatternChecker()
_payment_history_checker     = PaymentHistoryChecker()
_external_signals_checker    = ExternalSignalsChecker()
_debt_to_income_checker      = DebtToIncomeChecker()


# ---------------------------------------------------------------------------
# Checker node wrappers — each calls its checker and writes to its own state slot
# ---------------------------------------------------------------------------

def _credit_score_node(state: LoanDefaultState) -> dict:
    result: CheckerResult = _credit_score_checker.run(state)
    return {"credit_score_result": result}


def _transaction_pattern_node(state: LoanDefaultState) -> dict:
    result: CheckerResult = _transaction_pattern_checker.run(state)
    return {"transaction_pattern_result": result}


def _payment_history_node(state: LoanDefaultState) -> dict:
    result: CheckerResult = _payment_history_checker.run(state)
    return {"payment_history_result": result}


def _external_signals_node(state: LoanDefaultState) -> dict:
    result: CheckerResult = _external_signals_checker.run(state)
    return {"external_signals_result": result}


def _debt_to_income_node(state: LoanDefaultState) -> dict:
    result: CheckerResult = _debt_to_income_checker.run(state)
    return {"debt_to_income_result": result}


# ---------------------------------------------------------------------------
# Parallel checker node names — used for fan-out and fan-in edges
# ---------------------------------------------------------------------------

_CHECKER_NODES = [
    "credit_score_node",
    "transaction_pattern_node",
    "payment_history_node",
    "external_signals_node",
    "debt_to_income_node",
]


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    builder = StateGraph(LoanDefaultState)

    # Register all nodes
    builder.add_node("supervisor",             supervisor.run)
    builder.add_node("credit_score_node",        _credit_score_node)
    builder.add_node("transaction_pattern_node", _transaction_pattern_node)
    builder.add_node("payment_history_node",     _payment_history_node)
    builder.add_node("external_signals_node",    _external_signals_node)
    builder.add_node("debt_to_income_node",      _debt_to_income_node)
    builder.add_node("risk_calculator",          risk_calculator.run)
    builder.add_node("explanation_generator",    explanation_generator.run)
    builder.add_node("action_recommender",       action_recommender.run)

    # Entry point
    builder.set_entry_point("supervisor")

    # Fan-out: supervisor → all 5 checkers in parallel
    for node in _CHECKER_NODES:
        builder.add_edge("supervisor", node)

    # Fan-in: all 5 checkers → risk_calculator
    # LangGraph waits for every incoming edge before running the target node
    for node in _CHECKER_NODES:
        builder.add_edge(node, "risk_calculator")

    # Sequential pipeline
    builder.add_edge("risk_calculator",       "explanation_generator")
    builder.add_edge("explanation_generator", "action_recommender")
    builder.add_edge("action_recommender",    END)

    return builder


# Compile once at import time — wiring errors surface immediately, not at runtime
graph = _build_graph().compile()
logger.info("[graph] Compiled successfully — nodes=%s", list(_CHECKER_NODES))
