"""Top-level Pipeline Orchestrator for Py2SafeRust-X.

Coordinates all 5 stages in sequence:
    1. Python-to-Rust Transpilation (AST -> IR -> Type Inference -> Ownership Analysis -> Codegen)
    2. Adaptive Repair (rustc diagnostic analysis -> KB match -> LLM fallback -> Recompile)
    3. Semantic Verification (Python vs Rust dual execution & output diff)
       [Feedback loop: on semantic mismatch, feeds back to Adaptive Repair once]
    4. Explainable Compilation (Detailed JSON & rendered Markdown report)
    5. Confidence Assessment (Transparent 0-100 metric with itemized breakdown)
"""
import html as _html
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from transpiler import transpile, TranspileResult
from repair import AdaptiveRepairOrchestrator, AdaptiveRepairResult, RepairKnowledgeBase, LLMRepairClient
from verifier import SemanticVerifier, VerificationResult
from explain import ReportGenerator, ExplanationReport
from confidence import ConfidenceScorer, ConfidenceResult


def _sanitize_rust_code(code: str) -> str:
    """Strip any residual HTML entities from Rust code (e.g. from LLM responses).
    Loops until stable to handle double-encoded entities like &amp;#039; -> &#039; -> '.
    """
    if not code:
        return code
    prev = None
    result = code
    while result != prev:
        prev = result
        result = _html.unescape(result)
    return result


@dataclass
class PipelineConfig:
    max_repair_iterations: int = 5
    execution_timeout_secs: int = 5
    llm_timeout_secs: int = 30
    rules_file_path: Optional[str] = None
    enable_semantic_repair_loop: bool = True


@dataclass
class PipelineResult:
    rust_code: str
    compiled: bool
    semantic_match: bool
    confidence_score: int
    confidence_breakdown: List[Dict[str, Any]]
    explanation_report_markdown: str
    explanation_report_dict: Dict[str, Any]
    repair_log: List[Dict[str, Any]]
    warnings: List[str]
    verification_details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rust_code": self.rust_code,
            "compiled": self.compiled,
            "semantic_match": self.semantic_match,
            "confidence_score": self.confidence_score,
            "confidence_breakdown": self.confidence_breakdown,
            "explanation_report_markdown": self.explanation_report_markdown,
            "explanation_report_dict": self.explanation_report_dict,
            "repair_log": self.repair_log,
            "warnings": self.warnings,
            "verification_details": self.verification_details,
        }


def run_pipeline(
    python_source: str,
    test_inputs: Optional[List[Any]] = None,
    config: Optional[PipelineConfig] = None
) -> PipelineResult:
    """Executes the full 5-stage Py2SafeRust-X transpilation and verification pipeline."""
    cfg = config or PipelineConfig()

    # Stage 1: Transpilation
    transpile_res = transpile(python_source)
    initial_rust = _sanitize_rust_code(transpile_res.rust_code)
    warnings = list(transpile_res.warnings)

    # Stage 2: Adaptive Repair
    kb = RepairKnowledgeBase(rules_file_path=cfg.rules_file_path)
    llm = LLMRepairClient(timeout=cfg.llm_timeout_secs)
    orchestrator = AdaptiveRepairOrchestrator(kb=kb, llm_client=llm, max_iterations=cfg.max_repair_iterations)

    repair_res = orchestrator.run(
        python_source=python_source,
        initial_rust_code=initial_rust
    )
    current_rust = _sanitize_rust_code(repair_res.final_rust_code)

    # Stage 3: Semantic Verification
    verifier = SemanticVerifier(timeout=cfg.execution_timeout_secs)
    if repair_res.success:
        verif_res = verifier.verify(python_source, current_rust, test_inputs)

        # Feedback loop: If semantic mismatch occurred and loop is enabled, attempt secondary repair
        if not verif_res.semantic_match and cfg.enable_semantic_repair_loop and verif_res.mismatch_feedback:
            secondary_repair = orchestrator.run(
                python_source=python_source,
                initial_rust_code=current_rust,
                semantic_mismatch=verif_res.mismatch_feedback,
                verifier=verifier,
                test_inputs=test_inputs
            )
            # Accumulate secondary repair iterations and log entries
            repair_res.repair_log.entries.extend(secondary_repair.repair_log.entries)
            repair_res.repair_log.llm_fixes_count += secondary_repair.repair_log.llm_fixes_count
            repair_res.repair_log.total_iterations += secondary_repair.repair_log.total_iterations

            if secondary_repair.success:
                current_rust = _sanitize_rust_code(secondary_repair.final_rust_code)
                repair_res.final_rust_code = current_rust
                repair_res.success = True
                verif_res = verifier.verify(python_source, current_rust, test_inputs)
    else:
        # If initial repair compilation failed, verification cannot run
        verif_res = VerificationResult(
            semantic_match=False,
            total_cases=0,
            passed_cases=0,
            pass_rate=0.0,
            test_cases=[],
            mismatch_feedback="Verification skipped: Rust source failed to compile"
        )

    # Final Ground-Truth Compilation Check: Authoritative test of current_rust against rustc
    from repair.compiler import compile_rust_string
    final_comp_check = compile_rust_string(current_rust)
    truly_compiled = final_comp_check.success

    if not truly_compiled:
        repair_res.success = False
        repair_res.repair_log.succeeded = False
        verif_res = VerificationResult(
            semantic_match=False,
            total_cases=0,
            passed_cases=0,
            pass_rate=0.0,
            test_cases=[],
            mismatch_feedback="Verification skipped: Rust source failed to compile"
        )

    # Stage 4: Explainable Compilation Report
    report_gen = ReportGenerator()
    explanation = report_gen.generate(
        python_source=python_source,
        rust_source=current_rust,
        warnings=warnings,
        repair_log=repair_res.repair_log,
        verification_result=verif_res
    )

    # Stage 5: Confidence Assessment
    scorer = ConfidenceScorer()
    confidence = scorer.calculate(
        repair_log=repair_res.repair_log,
        verification_result=verif_res,
        warnings=warnings
    )

    # Format repair log entries
    formatted_repair_log = [
        {
            "iteration": entry.iteration,
            "error_code": entry.error_code,
            "error_message": entry.error_message,
            "fix_source": entry.fix_source,
            "rule_type": entry.rule_type,
            "rule_id": entry.rule_id,
            "explanation": entry.explanation
        }
        for entry in repair_res.repair_log.entries
    ]

    return PipelineResult(
        rust_code=current_rust,
        compiled=truly_compiled,
        semantic_match=bool(truly_compiled and verif_res.semantic_match),
        confidence_score=confidence.score,
        confidence_breakdown=confidence.to_dict()["breakdown"],
        explanation_report_markdown=explanation.markdown,
        explanation_report_dict=explanation.to_dict(),
        repair_log=formatted_repair_log,
        warnings=warnings,
        verification_details=explanation.verification_details
    )
