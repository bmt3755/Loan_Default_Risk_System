"""
Three sample borrowers for end-to-end testing.
    LOW_RISK  — stable employment, good credit, clean payments, low DTI
    HIGH_RISK — unemployed, poor credit, missed payments, extreme DTI
    EDGE_CASE — mixed signals: good credit but high DTI and recent job change
"""

from typing import Any

LOW_RISK: dict[str, Any] = {
    "borrower_id": "B-001",
    "loan_id": "L-001",
    "loan_amount": 15000.0,
    "credit_score": 760,
    "employment_status": "Full-time Software Engineer at established tech company, 4 years tenure",
    "monthly_income": 6500.0,
    "monthly_debt_payments": 950.0,  # DTI ~14.6%
    "region": "Austin, TX — stable economy, low unemployment rate",
    "recent_transactions": [
        {"date": "2024-03-01", "type": "income",   "amount": 6500, "description": "Salary deposit"},
        {"date": "2024-03-05", "type": "expense",  "amount": 800,  "description": "Rent"},
        {"date": "2024-03-10", "type": "expense",  "amount": 150,  "description": "Groceries"},
        {"date": "2024-03-15", "type": "expense",  "amount": 60,   "description": "Utilities"},
        {"date": "2024-03-20", "type": "expense",  "amount": 200,  "description": "Dining"},
        {"date": "2024-04-01", "type": "income",   "amount": 6500, "description": "Salary deposit"},
        {"date": "2024-04-05", "type": "expense",  "amount": 800,  "description": "Rent"},
        {"date": "2024-04-10", "type": "expense",  "amount": 140,  "description": "Groceries"},
    ],
    "payment_history": [
        {"month": "2023-11", "status": "on_time", "amount": 320},
        {"month": "2023-12", "status": "on_time", "amount": 320},
        {"month": "2024-01", "status": "on_time", "amount": 320},
        {"month": "2024-02", "status": "on_time", "amount": 320},
        {"month": "2024-03", "status": "on_time", "amount": 320},
        {"month": "2024-04", "status": "on_time", "amount": 320},
    ],
}

HIGH_RISK: dict[str, Any] = {
    "borrower_id": "B-002",
    "loan_id": "L-002",
    "loan_amount": 22000.0,
    "credit_score": 540,
    "employment_status": "Unemployed — laid off 3 months ago, no new employment secured",
    "monthly_income": 1800.0,  # unemployment benefits only
    "monthly_debt_payments": 1600.0,  # DTI ~88.9%
    "region": "Detroit, MI — economically distressed area, high unemployment",
    "recent_transactions": [
        {"date": "2024-02-01", "type": "income",      "amount": 3200, "description": "Final paycheck"},
        {"date": "2024-02-10", "type": "expense",     "amount": 900,  "description": "Rent"},
        {"date": "2024-03-01", "type": "income",      "amount": 1800, "description": "Unemployment benefits"},
        {"date": "2024-03-05", "type": "expense",     "amount": 900,  "description": "Rent"},
        {"date": "2024-03-15", "type": "expense",     "amount": 500,  "description": "Credit card minimum payment"},
        {"date": "2024-04-01", "type": "income",      "amount": 1800, "description": "Unemployment benefits"},
        {"date": "2024-04-05", "type": "expense",     "amount": 900,  "description": "Rent"},
        {"date": "2024-04-12", "type": "withdrawal",  "amount": 400,  "description": "ATM cash withdrawal"},
    ],
    "payment_history": [
        {"month": "2023-11", "status": "on_time", "amount": 450},
        {"month": "2023-12", "status": "late_30", "amount": 450},
        {"month": "2024-01", "status": "late_60", "amount": 450},
        {"month": "2024-02", "status": "missed",  "amount": 0},
        {"month": "2024-03", "status": "missed",  "amount": 0},
        {"month": "2024-04", "status": "missed",  "amount": 0},
    ],
}

EDGE_CASE: dict[str, Any] = {
    "borrower_id": "B-003",
    "loan_id": "L-003",
    "loan_amount": 18000.0,
    "credit_score": 715,
    "employment_status": "Recently switched from full-time to 6-month contract role, income dropped",
    "monthly_income": 4200.0,
    "monthly_debt_payments": 2100.0,  # DTI exactly 50% — sits right at the AT_RISK threshold
    "region": "Chicago, IL — mixed economy, moderate employment stability",
    "recent_transactions": [
        {"date": "2024-02-01", "type": "income",  "amount": 5500, "description": "Final full-time salary"},
        {"date": "2024-02-05", "type": "expense", "amount": 1200, "description": "Rent"},
        {"date": "2024-03-01", "type": "income",  "amount": 4200, "description": "Contract payment"},
        {"date": "2024-03-05", "type": "expense", "amount": 1200, "description": "Rent"},
        {"date": "2024-03-20", "type": "expense", "amount": 800,  "description": "Car payment and insurance"},
        {"date": "2024-04-01", "type": "income",  "amount": 4200, "description": "Contract payment"},
        {"date": "2024-04-05", "type": "expense", "amount": 1200, "description": "Rent"},
        {"date": "2024-04-18", "type": "expense", "amount": 350,  "description": "Unexpected medical bill"},
    ],
    "payment_history": [
        {"month": "2023-11", "status": "on_time", "amount": 380},
        {"month": "2023-12", "status": "on_time", "amount": 380},
        {"month": "2024-01", "status": "on_time", "amount": 380},
        {"month": "2024-02", "status": "late_30", "amount": 380},
        {"month": "2024-03", "status": "on_time", "amount": 380},
        {"month": "2024-04", "status": "on_time", "amount": 380},
    ],
}

SCENARIOS: dict[str, dict[str, Any]] = {
    "LOW_RISK":  LOW_RISK,
    "HIGH_RISK": HIGH_RISK,
    "EDGE_CASE": EDGE_CASE,
}
