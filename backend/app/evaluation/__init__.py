"""
Evaluation package for SentinelChain - W&B Weave integration
"""
from app.evaluation.golden_set import (
    EvaluationCase, 
    ExpectedOutput, 
    ExpectedRiskFactor,
    ExpectedMitigation,
    ExpectedAlternative,
    golden_cases,
    get_cases_by_category,
    get_cases_by_tier
)
from app.evaluation.runner import (
    EvaluationRunner,
    EvaluationResult,
    run_evaluation
)

__all__ = [
    "EvaluationCase",
    "ExpectedOutput", 
    "ExpectedRiskFactor",
    "ExpectedMitigation",
    "ExpectedAlternative",
    "golden_cases",
    "get_cases_by_category",
    "get_cases_by_tier",
    "EvaluationRunner",
    "EvaluationResult",
    "run_evaluation",
]