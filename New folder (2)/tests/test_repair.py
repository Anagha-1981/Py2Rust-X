"""Unit tests for Py2SafeRust-X Adaptive Repair Module."""
import tempfile
import pytest
from repair.compiler import compile_rust_string, find_rustc, RustDiagnostic
from repair.knowledge_base import RepairKnowledgeBase
from repair.llm_repair import LLMRepairClient, LLMRepairResult
from repair.adaptive_repair import AdaptiveRepairOrchestrator


def test_find_rustc():
    path = find_rustc()
    assert path is not None
    assert "rustc" in path.lower()


def test_compile_valid_rust():
    code = """
fn main() {
    let msg = "Hello from Py2SafeRust!";
    println!("{}", msg);
}
"""
    res = compile_rust_string(code)
    assert res.success is True
    assert res.returncode == 0
    assert len(res.errors) == 0


def test_compile_error_json_diagnostics():
    # Intentionally reassign immutable variable to trigger E0384
    bad_code = """
fn main() {
    let x = 10;
    x = 20;
    println!("{}", x);
}
"""
    res = compile_rust_string(bad_code)
    assert res.success is False
    assert len(res.errors) > 0
    e0384 = [e for e in res.errors if e.code == "E0384"]
    assert len(e0384) > 0
    assert "cannot assign twice to immutable variable `x`" in e0384[0].message


def test_kb_repair_e0384_mutability():
    bad_code = """
fn main() {
    let x = 10;
    x = 20;
    println!("{}", x);
}
"""
    kb = RepairKnowledgeBase()
    diag = RustDiagnostic(
        code="E0384",
        message="cannot assign twice to immutable variable `x`",
        level="error"
    )
    match = kb.match_and_repair(bad_code, diag)
    assert match is not None
    assert match.rule_origin == "pre_seeded"
    assert "let mut x = 10;" in match.repaired_code

    # Verify that the repaired code now actually compiles with rustc!
    res = compile_rust_string(match.repaired_code)
    assert res.success is True


def test_kb_self_learning():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tf.write(b"[]")
        tf_path = tf.name

    kb = RepairKnowledgeBase(rules_file_path=tf_path)
    assert len(kb.rules) == 0

    # Learn a new rule
    rule_id = kb.learn_rule(
        error_code="E9999",
        pattern=r"cannot find value `foo`",
        replace_pattern=r"foo",
        replacement="bar",
        description="Custom learned rule"
    )
    assert rule_id.startswith("LEARNED_E9999")

    # Match with new learned rule
    diag = RustDiagnostic(code="E9999", message="cannot find value `foo` in this scope", level="error")
    match = kb.match_and_repair("let x = foo;", diag)
    assert match is not None
    assert match.rule_origin == "learned"
    assert match.repaired_code == "let x = bar;"


def test_adaptive_repair_loop_with_kb_fix():
    # Start with code missing mut
    code = """
fn main() {
    let val = 5;
    val = 10;
    println!("{}", val);
}
"""
    orchestrator = AdaptiveRepairOrchestrator()
    res = orchestrator.run(
        python_source="val = 5\nval = 10\nprint(val)",
        initial_rust_code=code
    )
    assert res.success is True
    assert "let mut val = 5;" in res.final_rust_code
    assert res.repair_log.succeeded is True
    assert res.repair_log.kb_fixes_count >= 1
    assert len(res.repair_log.entries) >= 1
    assert res.repair_log.entries[0].rule_type == "pre_seeded"


def test_llm_repair_graceful_timeout_handling():
    client = LLMRepairClient(timeout=1, gemini_api_key="invalid_test_key", groq_api_key="invalid_test_key", openai_api_key="invalid_test_key")
    res = client.repair("x = 1", "fn main() {}", [])
    assert res.success is False
    assert res.error_message is not None
