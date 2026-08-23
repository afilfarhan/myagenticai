"""Golden evaluation set integrity (pure module, no weave required)."""
from app.evaluation.golden_set import get_cases_by_category, get_cases_by_tier, golden_cases
from app.models import RiskCategory, RiskLevel


def test_golden_set_loads_with_minimum_coverage():
    assert len(golden_cases) >= 8, "golden set should keep at least 8 cases"


def test_every_case_is_well_formed():
    for case in golden_cases:
        assert case.case_id, "every case needs an id"
        assert case.query.strip(), "every case needs a query"
        assert case.expected.risk_factors, f"case {case.case_id} expects risk factors"
        for rf in case.expected.risk_factors:
            assert isinstance(rf.category, RiskCategory)
            assert isinstance(rf.level, RiskLevel)


def test_filter_by_category_and_tier():
    reputational = get_cases_by_category("reputational")
    assert reputational, "expected at least one reputational case"
    assert all(c.metadata.get("category") == "reputational" for c in reputational)

    tier1 = get_cases_by_tier("TIER_1")
    assert tier1, "expected at least one TIER_1 case"
    assert all(c.metadata.get("tier") == "TIER_1" for c in tier1)
