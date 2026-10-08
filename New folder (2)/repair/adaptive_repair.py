"""Adaptive Repair Module for Py2SafeRust-X.

Coordinates the repair loop:
    Compile -> if error: try Knowledge Base -> if no match: try LLM ->
    Apply fix -> Recompile -> if semantic verification is active: verify test cases ->
    if success & fix was LLM: self-learn rule into KB ->
    Repeat up to max_iterations.
Produces a detailed RepairLog for the Explainable Compilation Module.
"""
import html as _html
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional
from .compiler import compile_rust_string, CompilationResult, RustDiagnostic
from .knowledge_base import RepairKnowledgeBase
from .llm_repair import LLMRepairClient


def _unescape_rust(code: str) -> str:
    """Strip residual HTML entities that may appear in LLM-generated or KB-repaired Rust code."""
    if not code:
        return code
    prev = None
    result = code
    # Loop to handle double-encoded entities (e.g. &amp;#039; -> &#039; -> ')
    while result != prev:
        prev = result
        result = _html.unescape(result)
    return result


@dataclass
class RepairLogEntry:
    iteration: int
    error_code: Optional[str]
    error_message: str
    fix_source: str  # "kb" or "llm"
    rule_type: str   # "pre_seeded", "learned", or "llm"
    rule_id: str
    explanation: str
    diff_summary: str = ""


@dataclass
class RepairLog:
    entries: List[RepairLogEntry] = field(default_factory=list)
    total_iterations: int = 0
    succeeded: bool = False
    kb_fixes_count: int = 0
    llm_fixes_count: int = 0
    learned_rule_id: Optional[str] = None


@dataclass
class AdaptiveRepairResult:
    success: bool
    final_rust_code: str
    iterations: int
    repair_log: RepairLog
    compilation_result: CompilationResult


class AdaptiveRepairOrchestrator:
    def __init__(
        self,
        kb: Optional[RepairKnowledgeBase] = None,
        llm_client: Optional[LLMRepairClient] = None,
        max_iterations: int = 5
    ):
        self.kb = kb or RepairKnowledgeBase()
        self.llm_client = llm_client or LLMRepairClient()
        self.max_iterations = max_iterations

    def run(
        self,
        python_source: str,
        initial_rust_code: str,
        semantic_mismatch: Optional[str] = None,
        verifier: Optional[Any] = None,
        test_inputs: Optional[List[Any]] = None
    ) -> AdaptiveRepairResult:
        current_code = initial_rust_code
        repair_log = RepairLog()

        # Step 1: Initial compilation check
        comp_res = compile_rust_string(current_code)
        if comp_res.success and not semantic_mismatch:
            repair_log.total_iterations = 1
            repair_log.succeeded = True
            return AdaptiveRepairResult(
                success=True,
                final_rust_code=current_code,
                iterations=1,
                repair_log=repair_log,
                compilation_result=comp_res
            )

        iteration = 1
        last_fix_was_llm = False
        last_error_code: Optional[str] = None
        last_error_msg: str = ""

        while iteration <= self.max_iterations:
            repair_log.total_iterations = iteration

            # Determine primary diagnostic to address
            primary_diag: Optional[RustDiagnostic] = None
            if comp_res.errors:
                primary_diag = comp_res.errors[0]
                last_error_code = primary_diag.code
                last_error_msg = primary_diag.message
            elif semantic_mismatch:
                primary_diag = RustDiagnostic(
                    code="SEMANTIC_MISMATCH",
                    message=f"Output mismatch across test cases:\n{semantic_mismatch}",
                    level="error"
                )
                last_error_code = "SEMANTIC_MISMATCH"
                last_error_msg = semantic_mismatch

            if not primary_diag:
                # No errors detected
                break

            # Phase A: Try Knowledge Base first (deterministic & fast)
            kb_match = self.kb.match_and_repair(current_code, primary_diag)
            new_code = None

            if kb_match:
                new_code = kb_match.repaired_code
                last_fix_was_llm = False
                repair_log.kb_fixes_count += 1
                repair_log.entries.append(
                    RepairLogEntry(
                        iteration=iteration,
                        error_code=primary_diag.code,
                        error_message=primary_diag.message,
                        fix_source="kb",
                        rule_type=kb_match.rule_origin,  # "pre_seeded" or "learned"
                        rule_id=kb_match.rule_id,
                        explanation=kb_match.explanation,
                        diff_summary=f"Repaired via {kb_match.rule_id} ({kb_match.rule_origin})"
                    )
                )
            else:
                # Phase B: Fall back to LLM repair
                llm_res = self.llm_client.repair(
                    python_source=python_source,
                    current_rust_code=current_code,
                    diagnostics=comp_res.errors,
                    semantic_mismatch=semantic_mismatch
                )
                if llm_res.success and llm_res.repaired_code:
                    new_code = llm_res.repaired_code
                    last_fix_was_llm = True
                    repair_log.llm_fixes_count += 1
                    explanation_msg = f"Repaired via LLM ({llm_res.model_name})"
                    if semantic_mismatch:
                        explanation_msg += " to resolve semantic test mismatch"
                    repair_log.entries.append(
                        RepairLogEntry(
                            iteration=iteration,
                            error_code=primary_diag.code,
                            error_message=primary_diag.message,
                            fix_source="llm",
                            rule_type="llm",
                            rule_id="LLM_SEMANTIC_FIX" if semantic_mismatch else "LLM_GENERATED_FIX",
                            explanation=explanation_msg,
                            diff_summary="Synthesized new repair candidate via LLM"
                        )
                    )
                else:
                    # Both KB and LLM failed to produce a candidate
                    repair_log.entries.append(
                        RepairLogEntry(
                            iteration=iteration,
                            error_code=primary_diag.code,
                            error_message=primary_diag.message,
                            fix_source="failed",
                            rule_type="none",
                            rule_id="REPAIR_FAILED",
                            explanation=f"LLM fallback failed: {llm_res.error_message}",
                            diff_summary="No candidate fix produced"
                        )
                    )
                    break

            # Phase C: Recompile new candidate
            if new_code:
                current_code = _unescape_rust(new_code)
                comp_res = compile_rust_string(current_code)

                if comp_res.success:
                    # If this repair was addressing semantic mismatch, verify semantics
                    if verifier and semantic_mismatch:
                        verif = verifier.verify(python_source, current_code, test_inputs)
                        if verif.semantic_match:
                            repair_log.succeeded = True
                            if last_fix_was_llm and last_error_code:
                                learned_id = self.kb.learn_rule(
                                    error_code=last_error_code,
                                    pattern=rf"error.*{re.escape(last_error_code)}" if last_error_code else ".*",
                                    replace_pattern=r"/\* placeholder \*/",
                                    replacement="// learned fix",
                                    description=f"Auto-learned rule for {last_error_code} from successful LLM repair"
                                )
                                repair_log.learned_rule_id = learned_id

                            return AdaptiveRepairResult(
                                success=True,
                                final_rust_code=current_code,
                                iterations=iteration,
                                repair_log=repair_log,
                                compilation_result=comp_res
                            )
                        else:
                            # Code compiled but failed semantic tests; update mismatch for next loop
                            semantic_mismatch = verif.mismatch_feedback
                    else:
                        repair_log.succeeded = True
                        if last_fix_was_llm and last_error_code:
                            learned_id = self.kb.learn_rule(
                                error_code=last_error_code,
                                pattern=rf"error.*{re.escape(last_error_code)}" if last_error_code else ".*",
                                replace_pattern=r"/\* placeholder \*/",
                                replacement="// learned fix",
                                description=f"Auto-learned rule for {last_error_code} from successful LLM repair"
                            )
                            repair_log.learned_rule_id = learned_id

                        return AdaptiveRepairResult(
                            success=True,
                            final_rust_code=current_code,
                            iterations=iteration,
                            repair_log=repair_log,
                            compilation_result=comp_res
                        )

            iteration += 1

        repair_log.succeeded = False
        return AdaptiveRepairResult(
            success=False,
            final_rust_code=current_code,
            iterations=min(iteration, self.max_iterations),
            repair_log=repair_log,
            compilation_result=comp_res
        )
