"""Explainable Compilation Module for Py2SafeRust-X.

Consolidates transpiler warnings, repair logs, and semantic verification results
into a structured dictionary and human-readable Markdown report explaining
borrow-checker adjustments, repair justifications, and equivalence evidence.
"""
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from repair.adaptive_repair import RepairLog
from verifier.comparator import VerificationResult


@dataclass
class ExplanationReport:
    summary: Dict[str, Any]
    repair_details: List[Dict[str, Any]]
    verification_details: Dict[str, Any]
    warnings: List[str]
    markdown: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "repair_details": self.repair_details,
            "verification_details": self.verification_details,
            "warnings": self.warnings,
            "markdown": self.markdown,
        }


class ReportGenerator:
    def generate(
        self,
        python_source: str,
        rust_source: str,
        warnings: List[str],
        repair_log: RepairLog,
        verification_result: VerificationResult
    ) -> ExplanationReport:
        py_lines = len(python_source.strip().splitlines())
        rs_lines = len(rust_source.strip().splitlines())

        summary = {
            "python_lines": py_lines,
            "rust_lines": rs_lines,
            "compilation_succeeded": repair_log.succeeded,
            "total_repair_iterations": repair_log.total_iterations,
            "kb_fixes_applied": repair_log.kb_fixes_count,
            "llm_fixes_applied": repair_log.llm_fixes_count,
            "learned_rule_id": repair_log.learned_rule_id,
            "semantic_equivalence": verification_result.semantic_match if repair_log.succeeded else "N/A (Compilation Failed)",
            "verification_pass_rate": f"{verification_result.pass_rate * 100:.1f}%" if repair_log.succeeded else "N/A",
        }

        repair_details = []
        for entry in repair_log.entries:
            rationale = self._derive_explanation_rationale(entry.error_code, entry.rule_type, entry.explanation)
            repair_details.append({
                "iteration": entry.iteration,
                "error_code": entry.error_code,
                "error_message": entry.error_message,
                "source": entry.fix_source,
                "rule_type": entry.rule_type,
                "rule_id": entry.rule_id,
                "action": entry.explanation,
                "rationale": rationale
            })

        verif_details = {
            "semantic_match": verification_result.semantic_match,
            "total_cases": verification_result.total_cases,
            "passed_cases": verification_result.passed_cases,
            "pass_rate": verification_result.pass_rate,
            "mismatch_feedback": verification_result.mismatch_feedback,
            "cases": [
                {
                    "input": tc.input_desc,
                    "python_output": tc.python_stdout,
                    "rust_output": tc.rust_stdout,
                    "passed": tc.passed,
                    "error": tc.error,
                    "diff": getattr(tc, "diff", "") or "",
                    "formatted_input": getattr(tc, "formatted_input", "") or tc.input_desc,
                    "formatted_output": getattr(tc, "formatted_output", "") or tc.python_stdout,
                    "rust_formatted_output": getattr(tc, "rust_formatted_output", "") or tc.rust_stdout or (f"Error: {tc.error}" if tc.error else ""),
                    "session_transcript": getattr(tc, "session_transcript", "") or f"{tc.input_desc}\n{tc.python_stdout}",
                    "rust_session_transcript": getattr(tc, "rust_session_transcript", "") or (f"{tc.input_desc}\n{tc.rust_stdout}" if tc.rust_stdout else (f"Error: {tc.error}" if tc.error else ""))
                }
                for tc in verification_result.test_cases
            ]
        }

        markdown_doc = self._render_markdown(
            summary=summary,
            repair_details=repair_details,
            verif_details=verif_details,
            warnings=warnings,
            rust_source=rust_source
        )

        return ExplanationReport(
            summary=summary,
            repair_details=repair_details,
            verification_details=verif_details,
            warnings=warnings,
            markdown=markdown_doc
        )

    def _derive_explanation_rationale(
        self,
        error_code: Optional[str],
        rule_type: str,
        base_explanation: str
    ) -> str:
        if error_code == "E0382":
            return (
                "Rust's affine type system moves ownership on variable assignment for heap-allocated types "
                "(such as Vec or String). Reading the source variable after the assignment violates Rust's "
                "single-ownership guarantee. Inserting an explicit `.clone()` allocates an independent copy, "
                "preserving semantic equivalence with Python's reference semantics while satisfying the borrow checker."
            )
        elif error_code == "E0384":
            return (
                "In Rust, variables are immutable by default (`let`). Python allows rebinding and mutating variables at will. "
                "To accommodate subsequent assignments or mutations detected in the control flow, the declaration was promoted to `let mut`."
            )
        elif error_code in ("E0502", "E0499"):
            return (
                "Rust prohibits simultaneous mutable and immutable borrows to prevent data races and iterator invalidation. "
                "Restructuring borrow scopes or cloning the target data allows safe isolated mutation."
            )
        elif error_code == "unused_mut":
            return "Rust produces a compiler warning when a variable declared `mut` is never mutated. Stripping `mut` restores idiomatic purity."
        elif error_code == "E0308":
            return "Rust enforces strict numeric type safety without automatic widening. Explicit casting between integer and floating-point was injected."

        return f"Resolved via {rule_type} repair: {base_explanation}"

    def _render_markdown(
        self,
        summary: Dict[str, Any],
        repair_details: List[Dict[str, Any]],
        verif_details: Dict[str, Any],
        warnings: List[str],
        rust_source: str
    ) -> str:
        if not summary["compilation_succeeded"]:
            status_badge = "❌ COMPILATION FAILED"
        elif summary["semantic_equivalence"] is True:
            status_badge = "✅ PASSED"
        else:
            status_badge = "⚠️ ATTENTION NEEDED"

        md = []
        md.append(f"# Py2SafeRust-X Transpilation & Verification Report\n")
        md.append(f"**Overall Status:** {status_badge}\n")
        md.append("## 1. Transpilation Summary")
        md.append(f"- **Input Python Lines:** {summary['python_lines']}")
        md.append(f"- **Output Rust Lines:** {summary['rust_lines']}")
        md.append(f"- **Compilation Status:** {'Succeeded' if summary['compilation_succeeded'] else 'Failed'}")
        md.append(f"- **Repair Iterations:** {summary['total_repair_iterations']}")
        md.append(f"- **Repairs Applied:** {summary['kb_fixes_applied']} (Knowledge Base) / {summary['llm_fixes_applied']} (LLM)")
        if summary.get("learned_rule_id"):
            md.append(f"- **New Learned KB Rule:** `{summary['learned_rule_id']}`")
        if not summary["compilation_succeeded"]:
            md.append("- **Semantic Equivalence:** N/A (Compilation Failed)")
            md.append("- **Verification Pass Rate:** N/A\n")
        else:
            md.append(f"- **Semantic Equivalence:** {'Verified' if summary['semantic_equivalence'] else 'Mismatch / Unverified'}")
            md.append(f"- **Verification Pass Rate:** {summary['verification_pass_rate']}\n")

        md.append("## 2. Adaptive Repair & Borrow Checker Analysis")
        if not repair_details:
            md.append("Clean compilation achieved on the first pass. No secondary repair passes required.\n")
        else:
            for i, rd in enumerate(repair_details, 1):
                md.append(f"### Attempt {rd['iteration']}: {rd['error_code'] or 'Diagnostic'}")
                md.append(f"- **Error:** `{rd['error_message']}`")
                md.append(f"- **Fix Source:** {rd['source'].upper()} (Rule: `{rd['rule_id']}`, Type: `{rd['rule_type']}`)")
                md.append(f"- **Plain-English Rationale:** {rd['rationale']}\n")

        md.append("## 3. Semantic Verification Results")
        if not summary["compilation_succeeded"]:
            md.append("⏸️ **Semantic Verification Skipped**: Generated Rust code failed compilation, so semantic verification was not performed.\n")
        else:
            md.append(f"**Test Cases:** {verif_details['passed_cases']}/{verif_details['total_cases']} passed\n")
            md.append("| Case | Input | Expected Output (Python) | Actual Output (Rust) | Result |")
            md.append("|---|---|---|---|---|")
            for idx, tc in enumerate(verif_details["cases"], 1):
                res_str = "✅ Pass" if tc["passed"] else f"❌ Fail: {tc['error'] or ''}"
                inp_flat = tc.get("formatted_input", tc["input"]).replace("\n", " <br> ")
                py_flat = tc.get("formatted_output", tc["python_output"]).replace("\n", " <br> ")
                rs_flat = tc.get("rust_formatted_output", tc["rust_output"]).replace("\n", " <br> ")
                md.append(f"| Case #{idx} | `{inp_flat}` | `{py_flat}` | `{rs_flat}` | {res_str} |")
            md.append("")

            if verif_details["cases"]:
                md.append("### Interactive Test Case Executions (Input & Output)\n")
            for idx, tc in enumerate(verif_details["cases"], 1):
                status_icon = "✅ Pass" if tc["passed"] else "❌ Fail"
                md.append(f"#### Case #{idx} ({status_icon})")
                md.append("```text")
                md.append(tc.get("session_transcript") or f"{tc['input']}\n{tc['python_output']}")
                md.append("```\n")

        if warnings:
            md.append("## 4. Unresolved Warnings & Inferences")
            for w in warnings:
                md.append(f"- ⚠️ {w}")
            md.append("")

        md.append("## 5. Generated Safe Rust Code")
        md.append("```rust")
        md.append(rust_source.strip())
        md.append("```\n")

        return "\n".join(md)
