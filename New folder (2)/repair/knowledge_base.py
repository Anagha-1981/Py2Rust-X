"""Repair Knowledge Base for Py2SafeRust-X.

Provides data-driven rule matching against rustc compiler errors and suggestions.
Supports self-learning: persists new error-to-repair patterns discovered by LLM
so future runs bypass the LLM and apply the deterministic rule directly.
"""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .compiler import RustDiagnostic


@dataclass
class RepairMatch:
    repaired_code: str
    rule_id: str
    rule_origin: str  # "pre_seeded" or "learned"
    explanation: str


class RepairKnowledgeBase:
    def __init__(self, rules_file_path: Optional[str] = None):
        if rules_file_path:
            self.rules_path = Path(rules_file_path)
        else:
            self.rules_path = Path(__file__).parent / "rules.json"

        self.rules: List[Dict] = []
        self.load_rules()

    def load_rules(self) -> None:
        """Loads repair rules from JSON store."""
        if not self.rules_path.exists():
            self.rules = []
            return
        with open(self.rules_path, "r", encoding="utf-8") as f:
            self.rules = json.load(f)

    def save_rules(self) -> None:
        """Persists repair rules to JSON store."""
        with open(self.rules_path, "w", encoding="utf-8") as f:
            json.dump(self.rules, f, indent=2)

    def match_and_repair(self, rust_code: str, diagnostic: RustDiagnostic) -> Optional[RepairMatch]:
        """Attempts to match a compiler diagnostic against the rule base and apply a fix."""
        # 1. First priority: Check if rustc provided a direct suggestion with span replacement
        if diagnostic.suggestion and diagnostic.spans:
            fixed_code = self._apply_span_suggestion(rust_code, diagnostic)
            if fixed_code and fixed_code != rust_code:
                return RepairMatch(
                    repaired_code=fixed_code,
                    rule_id="RUSTC_DIRECT_SUGGESTION",
                    rule_origin="pre_seeded",
                    explanation=f"Applied direct rustc suggestion: '{diagnostic.suggestion}'"
                )

        # 2. Match against stored rules (both pre_seeded and learned)
        for rule in self.rules:
            if rule.get("error_code") == diagnostic.code or rule.get("error_code") is None:
                pattern = rule.get("pattern", "")
                m = re.search(pattern, diagnostic.message, re.IGNORECASE)
                if m:
                    fixed_code = self._apply_rule_action(rust_code, rule, m.groupdict(), diagnostic)
                    if fixed_code and fixed_code != rust_code:
                        origin = rule.get("source", "pre_seeded")
                        return RepairMatch(
                            repaired_code=fixed_code,
                            rule_id=rule.get("id", "UNKNOWN_RULE"),
                            rule_origin=origin,
                            explanation=rule.get("description", "Rule applied")
                        )

        return None

    def _apply_span_suggestion(self, rust_code: str, diagnostic: RustDiagnostic) -> Optional[str]:
        # Sort spans in reverse order so line modifications don't disrupt offsets
        spans = sorted(diagnostic.spans, key=lambda s: (s.line_start, s.column_start), reverse=True)
        lines = rust_code.splitlines()

        for sp in spans:
            if not sp.suggested_replacement:
                continue
            line_idx = sp.line_start - 1
            if 0 <= line_idx < len(lines):
                orig_line = lines[line_idx]
                col_start = max(0, sp.column_start - 1)
                col_end = min(len(orig_line), sp.column_end - 1)
                new_line = orig_line[:col_start] + sp.suggested_replacement + orig_line[col_end:]
                lines[line_idx] = new_line

        return "\n".join(lines) + ("\n" if rust_code.endswith("\n") else "")

    def _apply_rule_action(
        self,
        rust_code: str,
        rule: Dict,
        matches: Dict[str, str],
        diagnostic: RustDiagnostic
    ) -> Optional[str]:
        action = rule.get("action")
        var_name = matches.get("var")

        if action == "add_mut_to_declaration" and var_name:
            # Replace `let {var_name}` with `let mut {var_name}`
            pattern = rf"\blet\s+{re.escape(var_name)}\b"
            if re.search(pattern, rust_code):
                return re.sub(pattern, f"let mut {var_name}", rust_code, count=1)

        elif action == "insert_clone_for_var" and var_name:
            # Replace assignment `let {other} = {var_name};` with `let {other} = {var_name}.clone();`
            pat = rf"(let\s+\w+\s*=\s*){re.escape(var_name)}(\s*;)"
            if re.search(pat, rust_code):
                return re.sub(pat, rf"\g<1>{var_name}.clone()\g<2>", rust_code, count=1)

            # Or replace bare variable move in function argument
            pat_arg = rf"(\(\s*){re.escape(var_name)}(\s*[,)])"
            if re.search(pat_arg, rust_code):
                return re.sub(pat_arg, rf"\g<1>{var_name}.clone()\g<2>", rust_code, count=1)

        elif action == "remove_mut" and var_name:
            pattern = rf"\blet\s+mut\s+{re.escape(var_name)}\b"
            if re.search(pattern, rust_code):
                return re.sub(pattern, f"let {var_name}", rust_code, count=1)

        elif action == "cast_int_to_f64":
            # Coerce literals like `0` to `0.0` or add `as f64`
            return re.sub(r"(\b\d+)(\s*;)|\b(\d+)(\s*[\),])", r"\1\3 as f64\2\4", rust_code, count=1)

        elif action == "cast_float_to_i64_add":
            # Coerce expressions like `n + 0.5` or `(n + 0.5)` to `((n as f64) + 0.5)`
            pattern = r"\(([\w\.\(\)]+)\s*\+\s*(\d+\.\d+)\)"
            if re.search(pattern, rust_code):
                return re.sub(pattern, r"((\1 as f64) + \2)", rust_code, count=1)
            pattern2 = r"(\b\w+)\s*\+\s*(\d+\.\d+)"
            if re.search(pattern2, rust_code):
                return re.sub(pattern2, r"((\1 as f64) + \2)", rust_code, count=1)

        elif action == "replace_display_with_debug":
            # Replace `println!("{}", ...)` with `println!("{:?}", ...)`
            pattern = r'(println!\s*\(\s*)"\{\}"'
            if re.search(pattern, rust_code):
                return re.sub(pattern, r'\1"{:?}"', rust_code, count=1)
            pattern2 = r'(format!\s*\(\s*)"\{\}"'
            if re.search(pattern2, rust_code):
                return re.sub(pattern2, r'\1"{:?}"', rust_code, count=1)
            # More general: replace first `{}` in format string
            pattern3 = r'(".*?)\{\}(.*?")'
            if re.search(pattern3, rust_code):
                return re.sub(pattern3, r'\1{:?}\2', rust_code, count=1)

        elif action == "regex_replace" and "replace_pattern" in rule and "replacement" in rule:
            return re.sub(rule["replace_pattern"], rule["replacement"], rust_code)

        return None

    def learn_rule(
        self,
        error_code: Optional[str],
        pattern: str,
        replace_pattern: str,
        replacement: str,
        description: str = ""
    ) -> str:
        """Self-learning: persists a newly discovered repair pattern from an LLM fix."""
        new_id = f"LEARNED_{error_code or 'CUSTOM'}_{len(self.rules) + 1}"
        rule = {
            "id": new_id,
            "error_code": error_code,
            "description": description or f"Auto-learned rule for {error_code}",
            "pattern": pattern,
            "action": "regex_replace",
            "replace_pattern": replace_pattern,
            "replacement": replacement,
            "source": "learned"
        }
        self.rules.append(rule)
        self.save_rules()
        return new_id
