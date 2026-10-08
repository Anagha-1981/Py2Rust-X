"""Unit tests for Py2SafeRust-X Confidence Assessment Module."""
import pytest
from confidence import ConfidenceScorer
from repair.adaptive_repair import RepairLog
from verifier.comparator import VerificationResult


def test_confidence_perfect_score():
    scorer = ConfidenceScorer()
    repair_log = RepairLog(total_iterations=1, succeeded=True, kb_fixes_count=0, llm_fixes_count=0)
    verif_res = VerificationResult(semantic_match=True, total_cases=1, passed_cases=1, pass_rate=1.0)
    warnings = []

    res = scorer.calculate(repair_log, verif_res, warnings)
    assert res.score == 100
    assert len(res.breakdown) == 0


def test_confidence_failed_compilation():
    scorer = ConfidenceScorer()
    repair_log = RepairLog(total_iterations=5, succeeded=False)
    verif_res = VerificationResult(semantic_match=False, total_cases=0, passed_cases=0, pass_rate=0.0)

    res = scorer.calculate(repair_log, verif_res, [])
    assert res.score == 0
    assert any("Compilation Failure" in d.category for d in res.breakdown)


def test_confidence_penalties_breakdown():
    scorer = ConfidenceScorer()
    # 2 iterations (1 extra = -10), 1 KB fix (-5), 50% semantic pass (-15), unknown type (-20)
    # Expected score = 100 - 10 - 5 - 15 - 20 = 50
    repair_log = RepairLog(total_iterations=2, succeeded=True, kb_fixes_count=1, llm_fixes_count=0)
    verif_res = VerificationResult(semantic_match=False, total_cases=2, passed_cases=1, pass_rate=0.5)
    warnings = ["Variable 'x' type unknown; falling back to /* type: unknown */"]

    res = scorer.calculate(repair_log, verif_res, warnings)
    assert res.score == 50
    assert len(res.breakdown) == 4
