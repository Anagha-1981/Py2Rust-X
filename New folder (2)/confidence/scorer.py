"""Confidence Assessment Module for Py2SafeRust-X.

Computes a deterministic, transparent 0-100 confidence score based on
compilation success, repair iteration penalty, KB vs LLM provenance,
semantic verification pass rate, and unresolved type-inference warnings.
"""
from dataclasses import dataclass, field
from typing import Dict, List
from repair.adaptive_repair import RepairLog
from verifier.comparator import VerificationResult


@dataclass
class ConfidenceDeduction:
    category: str
    amount: float
    reason: str


@dataclass
class ConfidenceResult:
    score: int
    breakdown: List[ConfidenceDeduction] = field(default_factory=list)
    formula: str = ""

    def to_dict(self) -> Dict:
        return {
            "score": self.score,
            "formula": self.formula,
            "breakdown": [
                {
                    "category": d.category,
                    "deduction": d.amount,
                    "reason": d.reason
                }
                for d in self.breakdown
            ]
        }


class ConfidenceScorer:
    def calculate(
        self,
        repair_log: RepairLog,
        verification_result: VerificationResult,
        warnings: List[str]
    ) -> ConfidenceResult:
        deductions: List[ConfidenceDeduction] = []
        base = 100.0

        # 1. Total compilation failure
        if not repair_log.succeeded:
            deductions.append(
                ConfidenceDeduction(
                    category="Compilation Failure",
                    amount=100.0,
                    reason="Rust code failed to compile after all repair iterations"
                )
            )
            return ConfidenceResult(
                score=0,
                breakdown=deductions,
                formula="Score = 0 (Compilation failure)"
            )

        # 2. Repair iteration penalty (if iterations > 1)
        if repair_log.total_iterations > 1:
            penalty = 10.0 * (repair_log.total_iterations - 1)
            deductions.append(
                ConfidenceDeduction(
                    category="Repair Iterations",
                    amount=penalty,
                    reason=f"{repair_log.total_iterations - 1} extra repair iterations required (-10 per extra iteration)"
                )
            )
            base -= penalty

        # 3. Provenance of repairs: KB costs 5, LLM costs 15
        if repair_log.kb_fixes_count > 0:
            cost_kb = 5.0 * repair_log.kb_fixes_count
            deductions.append(
                ConfidenceDeduction(
                    category="KB-Sourced Repairs",
                    amount=cost_kb,
                    reason=f"{repair_log.kb_fixes_count} deterministic KB fixes applied (-5 each)"
                )
            )
            base -= cost_kb

        if repair_log.llm_fixes_count > 0:
            cost_llm = 15.0 * repair_log.llm_fixes_count
            deductions.append(
                ConfidenceDeduction(
                    category="LLM-Sourced Repairs",
                    amount=cost_llm,
                    reason=f"{repair_log.llm_fixes_count} heuristic LLM fixes applied (-15 each)"
                )
            )
            base -= cost_llm

        # 4. Semantic verification penalty: base -= 30 * (1 - pass_rate)
        if verification_result.total_cases > 0:
            fail_rate = 1.0 - verification_result.pass_rate
            if fail_rate > 0:
                penalty_verif = round(30.0 * fail_rate, 2)
                deductions.append(
                    ConfidenceDeduction(
                        category="Semantic Divergence",
                        amount=penalty_verif,
                        reason=f"Failed {verification_result.total_cases - verification_result.passed_cases} of {verification_result.total_cases} test cases (-30 * fail_rate)"
                    )
                )
                base -= penalty_verif

        # 5. Type inference warnings penalty: base -= 20 if unresolved unknown types
        has_unknown_type_warning = any("type unknown" in w.lower() or "/* type: unknown */" in w for w in warnings)
        if has_unknown_type_warning:
            deductions.append(
                ConfidenceDeduction(
                    category="Unresolved Types",
                    amount=20.0,
                    reason="One or more variables or parameters defaulted to /* type: unknown */"
                )
            )
            base -= 20.0

        clamped_score = max(0, min(100, int(round(base))))

        formula_desc = (
            "Score = clamp(100 - (10 * extra_iterations) - (5 * kb_fixes) - "
            "(15 * llm_fixes) - (30 * (1 - pass_rate)) - (20 if unknown_types else 0), 0, 100)"
        )

        return ConfidenceResult(
            score=clamped_score,
            breakdown=deductions,
            formula=formula_desc
        )
