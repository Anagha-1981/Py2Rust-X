"""Adaptive Repair package for Py2SafeRust-X."""
from .compiler import compile_rust_string, CompilationResult, RustDiagnostic, find_rustc, find_cargo
from .knowledge_base import RepairKnowledgeBase, RepairMatch
from .llm_repair import LLMRepairClient, LLMRepairResult
from .adaptive_repair import (
    AdaptiveRepairOrchestrator,
    AdaptiveRepairResult,
    RepairLog,
    RepairLogEntry
)
