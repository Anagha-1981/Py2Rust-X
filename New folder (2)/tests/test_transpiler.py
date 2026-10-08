"""Unit tests for Py2SafeRust-X Transpiler Module."""
import pytest
from transpiler import transpile


def test_transpile_basic_arithmetic():
    code = """
a = 10
b = 20
c = a + b
print(c)
"""
    res = transpile(code)
    assert "let a = 10;" in res.rust_code
    assert "let b = 20;" in res.rust_code
    assert "let c = (a + b);" in res.rust_code
    assert 'println!("{}", c);' in res.rust_code


def test_transpile_ownership_cloning_core_slide_example():
    """Slide Example:
    x = [1, 2, 3]
    y = x
    print(x)
    Because x is accessed after assignment to y, y = x must become y = x.clone()!
    """
    code = """
x = [1, 2, 3]
y = x
print(x)
"""
    res = transpile(code)
    assert "let x = vec![1, 2, 3];" in res.rust_code
    assert "let y = x.clone();" in res.rust_code
    assert 'println!("{:?}", x);' in res.rust_code


def test_transpile_mutability_detection():
    code = """
count = 0
count = count + 1
items = [1]
items.append(2)
"""
    res = transpile(code)
    assert "let mut count = 0;" in res.rust_code
    assert "count = (count + 1);" in res.rust_code
    assert "let mut items = vec![1];" in res.rust_code
    assert "items.push(2);" in res.rust_code


def test_transpile_loops_and_conditionals():
    code = """
total = 0
for i in range(5):
    if i % 2 == 0:
        total = total + i
print(total)
"""
    res = transpile(code)
    assert "let mut total = 0;" in res.rust_code
    assert "for i in (0..5)" in res.rust_code
    assert "if ((i % 2) == 0)" in res.rust_code


def test_transpile_function_definition():
    code = """
def add(a: int, b: int) -> int:
    return a + b

res = add(5, 7)
print(res)
"""
    res = transpile(code)
    assert "fn add(a: i64, b: i64) -> i64" in res.rust_code
    assert "return (a + b);" in res.rust_code
    assert "let res = add(5, 7);" in res.rust_code


def test_transpile_hashmap_dict():
    code = """
scores = {"alice": 95, "bob": 80}
print(scores)
"""
    res = transpile(code)
    assert "use std::collections::HashMap;" in res.rust_code
    assert "HashMap::from(" in res.rust_code
