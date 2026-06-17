"""
Loan Default Risk Monitor — entry point.

Usage (from the load_default/ directory):
    python run.py               # runs LOW_RISK scenario
    python run.py HIGH_RISK     # runs HIGH_RISK scenario
    python run.py EDGE_CASE     # runs EDGE_CASE scenario
"""

from __future__ import annotations

import logging
import os
import sys
import time


def _load_dotenv() -> None:
    """Load .env from the project directory — no extra packages needed."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

# Configure logging before any module imports that may log at import time
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _check_env() -> None:
    """Fail fast and clearly if required environment variables are missing."""
    missing = []
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if missing:
        print("\n  ERROR: The following environment variables are not set:")
        for var in missing:
            print(f"    - {var}")
        print("\n  Set them before running:")
        print("    $env:OPENAI_API_KEY = 'your_key'   (PowerShell)")
        print("    export OPENAI_API_KEY='your_key'   (bash)\n")
        sys.exit(1)


def _print_result(result: dict, elapsed: float) -> None:
    """Print the final state in a clean, readable format."""
    metadata    = result.get("metadata", {})
    final       = result.get("final_decision", {})
    borrower    = result.get("borrower", {})
    audit_trail = result.get("audit_trail", [])

    sep = "=" * 70

    print(f"\n{sep}")
    print("  LOAN DEFAULT RISK MONITOR — RESULT")
    print(sep)
    print(f"  Borrower ID : {borrower.get('borrower_id', 'unknown')}")
    print(f"  Loan ID     : {borrower.get('loan_id', 'unknown')}")
    print(f"  Run ID      : {metadata.get('run_id', 'unknown')}")
    print(f"  Duration    : {elapsed:.1f}s")

    # --- Checker results ---
    print(f"\n  CHECKER RESULTS")
    print(f"  {'-' * 60}")
    checker_slots = [
        ("Credit Score",        "credit_score_result"),
        ("Transaction Pattern", "transaction_pattern_result"),
        ("Payment History",     "payment_history_result"),
        ("External Signals",    "external_signals_result"),
        ("Debt-to-Income",      "debt_to_income_result"),
    ]
    for label, slot in checker_slots:
        r      = result.get(slot, {})
        status = r.get("status", "unknown")
        score  = r.get("score", "N/A")
        lbl    = r.get("label", "N/A")
        reason = r.get("reason", "N/A")
        print(f"  {label:<22} [{status:^9}]  score={score}  label={lbl}")
        print(f"  {'':22}   {reason}")
        print()

    succeeded      = metadata.get("checkers_succeeded", [])
    failed         = metadata.get("checkers_failed", [])
    human_review   = metadata.get("human_review_required", False)
    print(f"  Succeeded : {succeeded}")
    print(f"  Failed    : {failed}")
    print(f"  Human review required: {human_review}")

    # --- Final decision ---
    rating      = final.get("risk_rating", "UNKNOWN")
    action      = final.get("recommended_action", "UNKNOWN")
    explanation = final.get("explanation", "No explanation generated.")

    print(f"\n  FINAL DECISION")
    print(f"  {'-' * 60}")
    print(f"  Risk Rating : {rating}")
    print(f"  Action      : {action}")

    print(f"\n  EXPLANATION")
    print(f"  {'-' * 60}")
    for line in explanation.split("\n"):
        print(f"  {line}")

    # --- Audit trail ---
    print(f"\n  AUDIT TRAIL")
    print(f"  {'-' * 60}")
    for entry in audit_trail:
        ts    = entry.get("timestamp", "")[:19].replace("T", " ")  # trim microseconds
        step  = entry.get("step", "")
        event = entry.get("event", "")
        print(f"  {ts}  [{step}]  {event}")

    print(f"\n{sep}\n")


def main() -> None:
    _check_env()

    # Imports here so env check happens before any OpenAI client is created
    from src.graph import graph
    from src.runner.sample_data import SCENARIOS

    scenario_name = sys.argv[1].upper() if len(sys.argv) > 1 else "LOW_RISK"

    if scenario_name not in SCENARIOS:
        print(f"\n  ERROR: Unknown scenario '{scenario_name}'")
        print(f"  Available scenarios: {list(SCENARIOS.keys())}\n")
        sys.exit(1)

    borrower = SCENARIOS[scenario_name]
    logger.info("Starting scenario=%s borrower_id=%s", scenario_name, borrower["borrower_id"])

    start = time.time()
    try:
        result = graph.invoke({"borrower": borrower})
    except ValueError as exc:
        # Supervisor validation failure — bad borrower data
        logger.error("Input validation failed: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Graph run failed: %s", exc, exc_info=True)
        sys.exit(1)

    elapsed = time.time() - start
    _print_result(result, elapsed)


if __name__ == "__main__":
    main()
