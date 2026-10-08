"""Unit tests for Py2SafeRust-X Explainable Compilation Module."""
import pytest
from explain import ReportGenerator
from repair.adaptive_repair import RepairLog, RepairLogEntry
from verifier.comparator import VerificationResult, TestCaseResult


def test_explain_report_generation():
    generator = ReportGenerator()

    repair_log = RepairLog(
        entries=[
            RepairLogEntry(
                iteration=1,
                error_code="E0382",
                error_message="borrow of moved value: `x`",
                fix_source="kb",
                rule_type="pre_seeded",
                rule_id="RULE_E0382_CLONE_MOVE",
                explanation="Inserted .clone() on moved value"
            )
        ],
        total_iterations=2,
        succeeded=True,
        kb_fixes_count=1,
        llm_fixes_count=0
    )

    verif_res = VerificationResult(
        semantic_match=True,
        total_cases=1,
        passed_cases=1,
        pass_rate=1.0,
        test_cases=[
            TestCaseResult(
                input_desc="default",
                python_stdout="[1, 2, 3]",
                rust_stdout="[1, 2, 3]",
                passed=True
            )
        ]
    )

    py_code = "x = [1, 2, 3]\ny = x\nprint(x)"
    rs_code = "fn main() {\n    let x = vec![1, 2, 3];\n    let y = x.clone();\n    println!(\"{:?}\", x);\n}"

    report = generator.generate(
        python_source=py_code,
        rust_source=rs_code,
        warnings=["Test warning"],
        repair_log=repair_log,
        verification_result=verif_res
    )

    data = report.to_dict()
    assert data["summary"]["compilation_succeeded"] is True
    assert data["summary"]["semantic_equivalence"] is True
    assert len(data["repair_details"]) == 1
    assert "single-ownership guarantee" in data["repair_details"][0]["rationale"]
    assert "# Py2SafeRust-X Transpilation & Verification Report" in data["markdown"]
    assert "RULE_E0382_CLONE_MOVE" in data["markdown"]
