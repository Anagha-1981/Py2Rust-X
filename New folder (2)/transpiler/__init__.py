"""Transpiler package for Py2SafeRust-X.

Provides the primary public interface:
    transpile(python_source: str) -> TranspileResult
    transpile_file(file_path: str) -> TranspileResult
"""
from dataclasses import dataclass, field
from typing import List, Optional
import os
from .parser import PythonASTParser
from .type_inference import TypeInferenceEngine
from .ownership import OwnershipAnalyzer
from .codegen import RustCodeGenerator
from .ir import Program


@dataclass
class TranspileResult:
    rust_code: str
    warnings: List[str] = field(default_factory=list)
    ir: Optional[Program] = None


def transpile(python_source: str) -> TranspileResult:
    """Transpiles a Python code snippet or script content into idiomatic Rust code."""
    parser = PythonASTParser()
    ir = parser.parse(python_source)
    warnings = list(parser.warnings)

    type_engine = TypeInferenceEngine()
    type_warnings = type_engine.run(ir)
    warnings.extend(type_warnings)

    ownership_analyzer = OwnershipAnalyzer()
    ownership_analyzer.run(ir)

    codegen = RustCodeGenerator()
    rust_code = codegen.generate(ir)

    return TranspileResult(
        rust_code=rust_code,
        warnings=warnings,
        ir=ir
    )


def transpile_file(file_path: str) -> TranspileResult:
    """Reads a Python source file and transpiles it."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return transpile(content)
