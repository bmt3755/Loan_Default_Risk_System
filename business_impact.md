# Business Impact — Architecture Decisions

This document maps the **real engineering decisions in the codebase** to their business consequences and risk/cost impact. Every decision below points to actual code; nothing here is hypothetical.

> **A note on numbers:** this is a demonstration project run on synthetic borrowers, so it carries no measured production metrics. Impacts below are stated as **directional risk and cost categories** (the kind and direction of impact each decision controls), not invented dollar figures. In lending, the relevant cost categories are well understood: **charge-off losses** on defaulted loans, **per-evaluation API spend**, **regulatory/compliance exposure** (fair-lending and explainability rules), and **operational availability**.

---

## 1. The risk number is computed in plain Python, not by an LLM

- **Code:** `src/calculator/risk_calculator.py` averages the valid checker scores and maps the average to a rating with fixed thresholds (`> 6.5 → CRITICAL`, `≥ 5.0 → AT_RISK`, `≥ 3.0 → WATCH`, else `STABLE`). No LLM, no network call.
- **Technical reason:** LLM outputs vary run-to-run; arithmetic and threshold logic must be deterministic and inspectable.
- **Business consequence:** The same borrower always produces the same rating, and an auditor can trace exactly why. The LLMs advise; they do not decide.
- **Risk / cost impact:** Directly addresses **regulatory explainability and consistency** requirements — the decision boundary is a reviewable rule, not a black box. Removes the fair-lending risk of a non-reproducible decision.

## 2. Fail-fast input validation before any LLM call

- **Code:** `BorrowerInput` (Pydantic) in `src/state/schema.py` enforces `credit_score` ∈ 300–850, positive income/loan, and a sanity check rejecting `monthly_debt_payments > 2× monthly_income`. The supervisor (`src/graph/supervisor.py`) validates and raises `ValueError` **before** the graph fans out.
- **Technical reason:** Catch malformed data at the boundary instead of letting it propagate into seven LLM calls.
- **Business consequence:** Garbage input is rejected immediately with a clear error, never turned into a confident-looking but meaningless risk rating.
- **Risk / cost impact:** Eliminates **wasted API spend** on doomed runs and prevents **bad decisions on corrupt data** — a data-entry error can't silently become a lending action.

## 3. Conservative worst-case fallback when a checker fails

- **Code:** `failed_checker_result()` returns `score = 10.0`, `label = "high"`, `status = "failed"`. The base checker's `run()` catches **all** exceptions and returns this (`src/agents/base_checker.py`).
- **Technical reason:** A failed signal has unknown risk; the safe assumption in lending is the worst case, not the best.
- **Business consequence:** A crashed or malformed checker can never make a borrower look *safer* than they are.
- **Risk / cost impact:** Biases errors toward **false positives (extra caution) over false negatives (missed defaults)** — the cheaper error type in lending, since a missed default is a charge-off loss while an over-cautious flag costs only a review.

## 4. Every LLM step degrades gracefully — the run never crashes

- **Code:** Checkers never raise (`base_checker.py`); `explanation_generator.py` falls back to a template built from checker reasons in state; `action_recommender.py` falls back to its rule-based default. All three wrap the LLM call in try/except.
- **Technical reason:** External LLM calls are the least reliable part of the system (timeouts, rate limits, malformed JSON).
- **Business consequence:** One flaky API call doesn't abort the evaluation — the run completes using the remaining signals and still emits a rating, explanation, and action.
- **Risk / cost impact:** Protects **operational availability**; a transient provider issue degrades quality slightly instead of producing zero output.

## 5. Human-review escalation when too many signals are missing

- **Code:** `risk_calculator.py` sets `human_review_required = true` when `len(failed) >= 3` (`_HUMAN_REVIEW_THRESHOLD`).
- **Technical reason:** A rating built from only one or two surviving signals is statistically thin and shouldn't be trusted automatically.
- **Business consequence:** Low-confidence cases are routed to a person instead of being auto-decided.
- **Risk / cost impact:** Mitigates **compliance and model-risk exposure** — the system declines to make automated decisions when it lacks sufficient evidence, which is exactly what model-governance reviewers look for.

## 6. Total signal failure defaults to CRITICAL, not "unknown"

- **Code:** `_map_to_rating()` returns `CRITICAL` when there are no valid scores.
- **Technical reason:** "No data" must not be silently treated as "no risk."
- **Business consequence:** A complete failure surfaces as maximum risk (and, per decision 5, also trips human review).
- **Risk / cost impact:** Closes a dangerous failure mode where an all-systems-down run could otherwise look benign and let a high-risk borrower through.

## 7. Per-checker dedicated state slots + parallel fan-out

- **Code:** `LoanDefaultState` gives each checker its own result key; `graph.py` fans out to all five in parallel and fans back in.
- **Technical reason:** Five concurrent writers to a shared field would race and overwrite each other; separate slots make concurrent writes safe.
- **Business consequence:** The five independent risk signals run **at the same time** rather than in sequence, and results never corrupt one another.
- **Risk / cost impact:** Cuts **per-evaluation latency** (roughly one LLM round-trip for all five checkers instead of five sequential ones) while removing a class of **state-corruption bugs**.

## 8. Low temperature + structured-output validation on every LLM response

- **Code:** All checkers call at `temperature = 0.1` in JSON mode; responses are validated by Pydantic (`score` ∈ 1–10, `label` enum, non-empty `reason`) before touching state.
- **Technical reason:** Scoring needs repeatability, and the system must never ingest an out-of-range or malformed score.
- **Business consequence:** Repeat evaluations of the same borrower stay consistent, and the LLM cannot inject an invalid rating into the pipeline.
- **Risk / cost impact:** Supports **fairness/consistency** (similar borrowers scored similarly) and protects **data integrity** at the model boundary.

## 9. DTI is computed in Python, then interpreted by the LLM

- **Code:** `debt_to_income.py` computes `dti = monthly_debt / monthly_income * 100` and passes the pre-computed number into the prompt.
- **Technical reason:** LLMs are unreliable at arithmetic; the math should be exact and the model should only judge it.
- **Business consequence:** The debt-to-income ratio that influences the decision is always arithmetically correct.
- **Risk / cost impact:** Removes a subtle **correctness risk** (an LLM mis-dividing) from a number that maps to real lending exposure.

## 10. Actions are bounded: rule-based default + constrained LLM override

- **Code:** `action_recommender.py` maps each rating to a safe default action, then lets the LLM override **only** within the four allowed actions and **only** "if the explanation contains clear, specific evidence." Any failure keeps the default; unknown ratings fall back to `escalate_to_collections`.
- **Technical reason:** Automated actions must be enumerable and safe; the LLM should refine, not invent.
- **Business consequence:** The system can never recommend an action outside the approved set, and a stable borrower can't be accidentally escalated (or a critical one ignored) on an LLM whim.
- **Risk / cost impact:** Caps **operational and reputational risk** of automated borrower-facing actions (reminders, payment-plan offers, collections) by keeping them inside a governed action space.

## 11. Cost and latency are bounded by construction

- **Code:** Prompts cap history (`[-12:]` payments, `[-10:]` transactions); every LLM call sets `max_tokens` (200–600) and a 30 s `timeout`.
- **Technical reason:** Token usage and wall-clock time per evaluation must be predictable.
- **Business consequence:** Per-evaluation cost and runtime stay within a known envelope regardless of how much history a borrower has.
- **Risk / cost impact:** Makes **per-evaluation API spend** predictable and bounds the **latency** a reviewer waits on — both required to forecast cost at scale.

## 12. Built-in observability

- **Code:** `@traceable` on every LLM node; structured logging throughout; an audit entry and per-checker success/failure metadata recorded in state.
- **Technical reason:** Production financial systems must be debuggable and after-the-fact reviewable.
- **Business consequence:** Any individual decision can be traced end-to-end — which signals fired, what they said, and why the rating and action followed.
- **Risk / cost impact:** Reduces **incident-resolution time** and supports **audit/compliance** evidence requirements.

---

## Summary

| # | Decision (in code) | Technical reason | Business consequence | Primary risk/cost lever |
|---|---|---|---|---|
| 1 | Deterministic calculator, no LLM in scoring | LLMs vary; math must be inspectable | Reproducible, auditable ratings | Regulatory explainability |
| 2 | Pydantic fail-fast at entry | Reject bad data at the boundary | Errors instead of fake confidence | Wasted API spend; bad decisions |
| 3 | Worst-case fallback on checker failure | Unknown risk = worst case | Failures never understate risk | Missed-default (charge-off) loss |
| 4 | Graceful degradation, never crash | LLM calls are the weak link | Run completes despite a failure | Operational availability |
| 5 | Human review when ≥3 checkers fail | Thin evidence ≠ trustworthy | Low-confidence cases go to a human | Model-risk / compliance |
| 6 | No valid scores → CRITICAL | "No data" ≠ "no risk" | Total failure surfaces as max risk | Dangerous false-benign runs |
| 7 | Dedicated slots + parallel fan-out | Avoid concurrent-write races | Faster runs, no state corruption | Latency; correctness |
| 8 | Low temp + validated outputs | Repeatable, in-range scores | Consistent, tamper-proof scoring | Fairness; data integrity |
| 9 | DTI computed in Python | LLMs miscalculate | Always-correct ratio | Arithmetic correctness |
| 10 | Bounded actions + constrained override | Actions must be enumerable | No out-of-policy actions | Operational/reputational risk |
| 11 | Capped history, tokens, timeouts | Predictable usage | Known cost & latency envelope | Per-evaluation spend |
| 12 | Tracing, logging, audit metadata | Must be debuggable & reviewable | Any decision is traceable | Incident time; audit evidence |
