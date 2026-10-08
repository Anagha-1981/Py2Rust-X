"""End-to-End (E2E) Pipeline Tests for Py2SafeRust-X."""
import pytest
from pipeline import run_pipeline, PipelineConfig


def test_e2e_slide_example_vector_aliasing():
    """Benchmark test from slides:
    input:
        x = [1, 2, 3]
        y = x
        print(x)
    expect:
        Generated Rust clones x into y (`let y = x.clone();`), compiles cleanly with rustc,
        and achieves semantic_match == True with high confidence score.
    """
    python_source = """
x = [1, 2, 3]
y = x
print(x)
"""
    result = run_pipeline(python_source)

    # 1. Structural check on emitted code
    assert "let x = vec![1, 2, 3];" in result.rust_code
    assert "let y = x.clone();" in result.rust_code
    assert 'println!("{:?}", x);' in result.rust_code

    # 2. Rustc compilation check
    assert result.compiled is True, f"Rust compilation failed:\n{result.rust_code}"

    # 3. Semantic verification check
    assert result.semantic_match is True, f"Semantic equivalence mismatch:\n{result.verification_details}"

    # 4. Confidence assessment check
    assert result.confidence_score >= 90
    assert result.confidence_score == 100

    # 5. Report check
    assert "# Py2SafeRust-X Transpilation & Verification Report" in result.explanation_report_markdown
    assert "PASSED" in result.explanation_report_markdown


def test_e2e_loop_and_computation():
    python_source = """
total = 0
for i in range(10):
    if i % 2 == 0:
        total = total + i
print(total)
"""
    result = run_pipeline(python_source)
    assert result.compiled is True
    assert result.semantic_match is True
    assert result.confidence_score == 100


def test_e2e_function_call_and_recursion():
    python_source = """
def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)

res = factorial(5)
print(res)
"""
    result = run_pipeline(python_source)
    assert result.compiled is True
    assert result.semantic_match is True
    assert result.confidence_score == 100
