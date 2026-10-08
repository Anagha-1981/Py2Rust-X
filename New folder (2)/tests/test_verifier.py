"""Unit tests for Py2SafeRust-X Semantic Verifier and Adaptive Repair Module."""
import pytest
from verifier import (
    run_python_code,
    run_rust_code,
    SemanticVerifier,
    ProgramBehaviorAnalyzer,
    TestCaseGenerator,
)
from repair.adaptive_repair import AdaptiveRepairOrchestrator
from repair.llm_repair import LLMRepairClient, LLMRepairResult


def test_run_python_code():
    res = run_python_code('print("Hello Python")')
    assert res.success is True
    assert res.stdout.strip() == "Hello Python"


def test_run_rust_code():
    rust_code = """
fn main() {
    println!("Hello Rust");
}
"""
    res = run_rust_code(rust_code)
    assert res.success is True
    assert res.stdout.strip() == "Hello Rust"


def test_program_behavior_analyzer():
    py_code = """
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""
    analyzer = ProgramBehaviorAnalyzer()
    behavior = analyzer.analyze(py_code)

    assert behavior.has_functions is True
    assert behavior.primary_function == "factorial"
    assert len(behavior.functions) == 1
    assert behavior.functions[0].is_recursive is True
    assert behavior.functions[0].params[0].name == "n"
    assert behavior.functions[0].params[0].inferred_type == "int"


def test_testcase_generator_generates_5_to_8_cases():
    analyzer = ProgramBehaviorAnalyzer()
    generator = TestCaseGenerator(target_count=6)

    # Test arithmetic multi-param function
    code_add = "def add(a: int, b: int) -> int:\n    return a + b\n"
    behavior_add = analyzer.analyze(code_add)
    cases_add = generator.generate(behavior_add)
    assert 5 <= len(cases_add) <= 8
    assert all(isinstance(c, tuple) and len(c) == 2 for c in cases_add)

    # Test recursive single-param function
    code_fact = "def fact(n: int) -> int:\n    return 1 if n <= 1 else n * fact(n - 1)\n"
    behavior_fact = analyzer.analyze(code_fact)
    cases_fact = generator.generate(behavior_fact)
    assert 5 <= len(cases_fact) <= 8
    assert all(isinstance(c, tuple) and len(c) == 1 for c in cases_fact)

    # Test string function
    code_str = "def is_palindrome(s: str) -> bool:\n    return s == s[::-1]\n"
    behavior_str = analyzer.analyze(code_str)
    cases_str = generator.generate(behavior_str)
    assert 5 <= len(cases_str) <= 8

    # Test list function
    code_list = "def rev_list(items: list) -> list:\n    return items[::-1]\n"
    behavior_list = analyzer.analyze(code_list)
    cases_list = generator.generate(behavior_list)
    assert 5 <= len(cases_list) <= 8

    # Test stdin program
    code_stdin = "x = int(input())\nprint(x * 2)\n"
    behavior_stdin = analyzer.analyze(code_stdin)
    cases_stdin = generator.generate(behavior_stdin)
    assert 5 <= len(cases_stdin) <= 8
    assert all(isinstance(c, str) and c.endswith("\n") for c in cases_stdin)


def test_semantic_verifier_match():
    py_code = """
a = 15
b = 25
print(a + b)
"""
    rs_code = """
fn main() {
    let a = 15;
    let b = 25;
    println!("{}", a + b);
}
"""
    verifier = SemanticVerifier()
    res = verifier.verify(py_code, rs_code)
    assert res.semantic_match is True
    assert res.total_cases == 1
    assert res.passed_cases == 1
    assert res.pass_rate == 1.0
    assert res.mismatch_feedback is None


def test_semantic_verifier_function_match():
    py_code = """
def add(a: int, b: int) -> int:
    return a + b
"""
    rs_code = """
fn add(a: i64, b: i64) -> i64 {
    return a + b;
}

fn main() {
}
"""
    verifier = SemanticVerifier()
    res = verifier.verify(py_code, rs_code)
    assert res.semantic_match is True
    assert 5 <= res.total_cases <= 8
    assert res.passed_cases == res.total_cases
    assert res.pass_rate == 1.0


def test_semantic_verifier_mismatch():
    py_code = 'print(100)'
    rs_code = 'fn main() { println!("{}", 200); }'

    verifier = SemanticVerifier()
    res = verifier.verify(py_code, rs_code)
    assert res.semantic_match is False
    assert res.passed_cases == 0
    assert res.mismatch_feedback is not None
    assert "Output mismatch" in res.mismatch_feedback


def test_adaptive_repair_on_semantic_mismatch():
    """Validates that adaptive repair feeds semantic mismatch details to LLM and verifies correction."""
    py_code = """
def double(n: int) -> int:
    return n * 2
"""
    # Flawed Rust implementation (adds 2 instead of multiplying by 2)
    flawed_rs = """
fn double(n: i64) -> i64 {
    return n + 2;
}

fn main() {}
"""
    correct_rs = """
fn double(n: i64) -> i64 {
    return n * 2;
}

fn main() {}
"""
    verifier = SemanticVerifier()
    initial_verif = verifier.verify(py_code, flawed_rs)
    assert initial_verif.semantic_match is False
    assert initial_verif.mismatch_feedback is not None

    # Mock LLM that receives mismatch feedback and produces the corrected Rust code
    class MockLLMClient:
        def __init__(self):
            self.repair_called = False
            self.received_mismatch = None

        def repair(self, python_source, current_rust_code, diagnostics, semantic_mismatch=None):
            self.repair_called = True
            self.received_mismatch = semantic_mismatch
            return LLMRepairResult(
                success=True,
                repaired_code=correct_rs,
                model_name="mock-llm"
            )

    mock_llm = MockLLMClient()
    orchestrator = AdaptiveRepairOrchestrator(llm_client=mock_llm, max_iterations=3)

    repair_res = orchestrator.run(
        python_source=py_code,
        initial_rust_code=flawed_rs,
        semantic_mismatch=initial_verif.mismatch_feedback,
        verifier=verifier
    )

    assert mock_llm.repair_called is True
    assert mock_llm.received_mismatch is not None
    assert "Output mismatch" in mock_llm.received_mismatch
    assert repair_res.success is True
    assert "n * 2" in repair_res.final_rust_code
    assert repair_res.repair_log.succeeded is True
    assert repair_res.repair_log.llm_fixes_count == 1

    # Verify the repaired code now passes all test cases
    final_verif = verifier.verify(py_code, repair_res.final_rust_code)
    assert final_verif.semantic_match is True
    assert 5 <= final_verif.total_cases <= 8
    assert final_verif.passed_cases == final_verif.total_cases
