"""
Evaluation package for SentinelChain - W&B Weave integration.

The golden set is import-safe without weave installed; the Weave-backed
runner/harness are imported lazily via `get_runner_exports()` or direct
module imports (`app.evaluation.runner`).
"""
from app.evaluation.golden_set import (
    EvaluationCase,
    ExpectedOutput,
    ExpectedRiskFactor,
    ExpectedMitigation,
    ExpectedAlternative,
    golden_cases,
    get_cases_by_category,
    get_cases_by_tier,
)


def get_runner_exports():
    """Import the Weave-dependent runner lazily."""
    from app.evaluation.runner import EvaluationRunner, EvaluationResult, run_evaluation

    return {"EvaluationRunner": EvaluationRunner, "EvaluationResult": EvaluationResult, "run_evaluation": run_evaluation}


__all__ = [
    "EvaluationCase",
    "ExpectedOutput",
    "ExpectedRiskFactor",
    "ExpectedMitigation",
    "ExpectedAlternative",
    "golden_cases",
    "get_cases_by_category",
    "get_cases_by_tier",
    "get_runner_exports",
]
