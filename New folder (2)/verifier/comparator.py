"""Output Comparator and Semantic Verification Module for Py2SafeRust-X.

Analyzes program behavior to automatically generate 5-8 diverse test cases,
constructs unified dual-language test harnesses, executes Python and Rust in isolated
subprocesses, normalizes and compares outputs, and produces detailed diagnostic
mismatch feedback for the LLM adaptive repair loop.
"""
import ast
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from repair.compiler import compile_rust_string
from .executor import run_python_code, run_rust_code, run_rust_binary, ExecutionResult
from .analyzer import ProgramBehaviorAnalyzer, TestCaseGenerator, ProgramBehavior, FunctionSignature

DELIM = "---PY2SAFERUST_CASE_DELIM---"


@dataclass
class TestCaseResult:
    __test__ = False
    input_desc: str
    python_stdout: str
    rust_stdout: str
    passed: bool
    error: Optional[str] = None
    diff: Optional[str] = None
    formatted_input: str = ""
    formatted_output: str = ""
    rust_formatted_output: str = ""
    session_transcript: str = ""
    rust_session_transcript: str = ""


@dataclass
class VerificationResult:
    semantic_match: bool
    total_cases: int
    passed_cases: int
    pass_rate: float
    test_cases: List[TestCaseResult] = field(default_factory=list)
    mismatch_feedback: Optional[str] = None


def normalize_output(text: str) -> str:
    """Normalizes whitespace and representation variations between Python and Rust."""
    text = text.replace("\r\n", "\n").strip()
    # Normalize booleans: True/False vs true/false
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)

    lines = []
    for line in text.split("\n"):
        line_clean = line.strip()
        # Normalize quotes in list/array/dict representations e.g. ['a', 'b'] vs ["a", "b"]
        if (line_clean.startswith("[") and line_clean.endswith("]")) or (line_clean.startswith("{") and line_clean.endswith("}")):
            line_clean = line_clean.replace("'", '"')
        lines.append(line_clean)

    return "\n".join(lines).strip()


def compute_output_diff(
    py_norm: str,
    rs_norm: str,
    py_success: bool,
    rs_success: bool,
    py_error: Optional[str] = None,
    rs_error: Optional[str] = None
) -> str:
    """Computes an itemized, human-readable divergence diff between Python and Rust."""
    if not py_success:
        return f"Python Error: {py_error or 'Execution Failed'}"
    if not rs_success:
        return f"Rust Error: {rs_error or 'Execution Failed'}"
    if py_norm == rs_norm:
        return ""

    py_lines = py_norm.splitlines()
    rs_lines = rs_norm.splitlines()
    if len(py_lines) <= 1 and len(rs_lines) <= 1:
        return f"- Python: \"{py_norm}\"\n+ Rust:   \"{rs_norm}\""

    import difflib
    diff = list(difflib.unified_diff(
        py_lines,
        rs_lines,
        fromfile="Python (Expected)",
        tofile="Rust (Actual)",
        lineterm=""
    ))
    return "\n".join(diff) if diff else f"- Python: {py_norm}\n+ Rust:   {rs_norm}"


def format_direct_execution_io(
    py_raw: str,
    rs_raw: str,
    rs_success: bool = True,
    rs_error: Optional[str] = None
) -> Tuple[str, str, str, str, str]:
    """Formats direct execution where inputs are provided directly in code."""
    formatted_input = "Direct Execution (inputs in code)"

    py_clean = py_raw.strip()
    py_out = py_clean if py_clean else "(no output)"

    if not rs_success:
        rs_out = f"Rust Error: {rs_error or 'Execution Failed'}"
    else:
        rs_clean = rs_raw.strip()
        rs_out = rs_clean if rs_clean else "(no output)"

    py_session = f"Python Output:\n{py_out}"
    rs_session = f"Rust Output:\n{rs_out}"
    return formatted_input, py_out, rs_out, py_session, rs_session


def extract_fn_bounds(source: str, func_name: str = "main") -> Optional[Tuple[int, int, str]]:
    """Returns (start_idx, end_idx, body_text) for the specified Rust function using brace counting."""
    m = re.search(rf"fn\s+{re.escape(func_name)}\s*\([^)]*\)\s*(?:->[^{{]+)?\{{", source)
    if not m:
        return None
    start_open = m.end() - 1
    depth = 1
    idx = start_open + 1
    while idx < len(source) and depth > 0:
        if source[idx] == '{':
            depth += 1
        elif source[idx] == '}':
            depth -= 1
        idx += 1
    if depth == 0:
        return m.start(), idx, source[start_open + 1 : idx - 1]
    return None


def format_function_io(
    func_name: str,
    params: List[str],
    args: Tuple[Any, ...],
    py_raw: str,
    rs_raw: str
) -> Tuple[str, str, str, str, str]:
    """Formats function test cases into structured input prompts and outputs."""
    ordinals = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"]
    input_lines = []
    for i, a in enumerate(args):
        p_name = params[i] if i < len(params) else None
        if p_name and p_name.lower() in ("a", "first", "num1", "n1", "x"):
            label = "Enter first number:"
        elif p_name and p_name.lower() in ("b", "second", "num2", "n2", "y"):
            label = "Enter second number:"
        elif p_name and p_name.lower() in ("c", "third", "num3", "n3", "z"):
            label = "Enter third number:"
        elif len(args) == 1:
            label = f"Enter {p_name}:" if p_name else "Enter number:"
        else:
            ord_name = ordinals[i] if i < len(ordinals) else f"#{i+1}"
            label = f"Enter {ord_name} number ({p_name}):" if p_name else f"Enter {ord_name} number:"
        input_lines.append(f"{label} {a}")

    formatted_input = "\n".join(input_lines) if input_lines else f"{func_name}()"

    py_clean = py_raw.strip()
    rs_clean = rs_raw.strip()

    py_out = py_clean if (":" in py_clean or not py_clean) else f"result: {py_clean}"
    rs_out = rs_clean if (":" in rs_clean or not rs_clean) else f"result: {rs_clean}"

    py_session = f"{formatted_input}\n{py_out}"
    rs_session = f"{formatted_input}\n{rs_out}"
    return formatted_input, py_out, rs_out, py_session, rs_session


def format_top_level_vars_io(
    behavior: ProgramBehavior,
    var_dict: Optional[Dict[str, Any]],
    py_raw: str,
    rs_raw: str
) -> Tuple[str, str, str, str, str]:
    """Formats top-level script variable permutations into structured input prompts and outputs."""
    target_dict = var_dict if var_dict is not None else behavior.top_level_vars
    ordinals = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"]
    input_lines = []

    if target_dict:
        for idx, (k, v) in enumerate(target_dict.items()):
            if k.lower() in ("a", "first", "num1", "n1", "x"):
                label = "Enter first number:"
            elif k.lower() in ("b", "second", "num2", "n2", "y"):
                label = "Enter second number:"
            elif k.lower() in ("c", "third", "num3", "n3", "z"):
                label = "Enter third number:"
            else:
                ord_name = ordinals[idx] if idx < len(ordinals) else f"#{idx+1}"
                label = f"Enter {ord_name} variable ({k}):"
            input_lines.append(f"{label} {v}")

    formatted_input = "\n".join(input_lines) if input_lines else "default variables"

    py_clean = py_raw.strip()
    rs_clean = rs_raw.strip()

    py_out = py_clean if (":" in py_clean or not py_clean) else f"result: {py_clean}"
    rs_out = rs_clean if (":" in rs_clean or not rs_clean) else f"result: {rs_clean}"

    py_session = f"{formatted_input}\n{py_out}"
    rs_session = f"{formatted_input}\n{rs_out}"
    return formatted_input, py_out, rs_out, py_session, rs_session


def reconstruct_stdin_io_session(
    python_source: str,
    case_input: Any,
    py_stdout: str,
    rs_stdout: str
) -> Tuple[str, str, str, str, str]:
    """Reconstructs prompt/input pairings and output from stdin execution."""
    prompts: List[str] = []
    try:
        tree = ast.parse(python_source)
        input_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "input":
                input_calls.append(node)
        input_calls.sort(key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))

        for c in input_calls:
            p = ""
            if c.args and isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str):
                p = c.args[0].value
            prompts.append(p)

        if any(not p for p in prompts):
            print_prompts = []
            for stmt in tree.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and getattr(stmt.value.func, "id", None) == "print":
                    if stmt.value.args and isinstance(stmt.value.args[0], ast.Constant) and isinstance(stmt.value.args[0].value, str):
                        print_prompts.append(stmt.value.args[0].value)
            if len(print_prompts) == len(prompts):
                for i in range(len(prompts)):
                    if not prompts[i]:
                        prompts[i] = print_prompts[i]
        target_vars = []
        for stmt in ast.walk(tree):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    t_name = getattr(target, "id", None)
                    for sub in ast.walk(stmt.value):
                        if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == "input":
                            target_vars.append(t_name)
    except Exception:
        pass

    input_str = str(case_input) if case_input is not None else ""
    input_lines = [l for l in input_str.splitlines() if l.strip()]
    if not input_lines and input_str.strip():
        input_lines = [input_str.strip()]

    ordinals = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"]
    formatted_input_lines = []

    py_rem = py_stdout.strip()
    rs_rem = rs_stdout.strip()

    for idx, inp in enumerate(input_lines):
        prompt_str = prompts[idx] if idx < len(prompts) and prompts[idx] else None
        if not prompt_str:
            t_name = target_vars[idx] if idx < len(target_vars) and target_vars[idx] else None
            if len(input_lines) == 1:
                prompt_str = f"Enter number ({t_name}):" if t_name else "Enter number:"
            else:
                ord_name = ordinals[idx] if idx < len(ordinals) else f"#{idx+1}"
                prompt_str = f"Enter {ord_name} number ({t_name}):" if t_name else f"Enter {ord_name} number:"

        # Strip prompt from remaining output
        for p_cand in (prompt_str, prompt_str.strip(), prompt_str.rstrip() + " "):
            if p_cand and p_cand in py_rem:
                py_rem = py_rem.replace(p_cand, "", 1).strip()
                break
        for p_cand in (prompt_str, prompt_str.strip(), prompt_str.rstrip() + " "):
            if p_cand and p_cand in rs_rem:
                rs_rem = rs_rem.replace(p_cand, "", 1).strip()
                break

        p_clean = prompt_str.strip()
        if not p_clean.endswith(":"):
            p_clean += ":"
        formatted_input_lines.append(f"{p_clean} {inp.strip()}")

    formatted_input = "\n".join(formatted_input_lines) if formatted_input_lines else "default input"

    def clean_output_val(rem_val: str, raw_val: str) -> str:
        target = rem_val.strip() if rem_val.strip() else raw_val.strip()
        if not target:
            return "result: none"
        lines = [l.strip() for l in target.splitlines() if l.strip()]
        if len(lines) == 1 and not (":" in lines[0]):
            return f"result: {lines[0]}"
        return "\n".join(lines)

    py_out = clean_output_val(py_rem, py_stdout)
    rs_out = clean_output_val(rs_rem, rs_stdout)

    py_session = f"{formatted_input}\n{py_out}"
    rs_session = f"{formatted_input}\n{rs_out}"
    return formatted_input, py_out, rs_out, py_session, rs_session


class SemanticVerifier:
    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.analyzer = ProgramBehaviorAnalyzer()
        self.generator = TestCaseGenerator(target_count=6)

    def analyze_program(self, python_source: str) -> ProgramBehavior:
        """Analyzes behavioral semantics of the input Python program."""
        return self.analyzer.analyze(python_source)

    def generate_test_cases(self, python_source: str, count: int = 6) -> List[Any]:
        """Generates 5-8 diverse semantic test cases analyzing program behavior."""
        behavior = self.analyzer.analyze(python_source)
        gen = TestCaseGenerator(target_count=count)
        return gen.generate(behavior)

    def verify(
        self,
        python_source: str,
        rust_source: str,
        test_inputs: Optional[List[Any]] = None
    ) -> VerificationResult:
        """Analyzes behavior, generates 5-8 test cases, and executes Python and Rust to verify semantics."""
        behavior = self.analyzer.analyze(python_source)
        test_cases_to_run = self._prepare_test_cases(behavior, test_inputs)

        # Check if we can run function harness in unified batch (compile once!)
        if (
            not behavior.has_self_contained_execution
            and behavior.has_functions
            and behavior.functions
            and all(isinstance(c, (list, tuple)) and len(c) > 0 for c in test_cases_to_run)
        ):
            return self._verify_functions_unified(python_source, rust_source, behavior, test_cases_to_run)

        # Check if we can run top-level var harness in unified batch (compile once!)
        if (
            not behavior.has_self_contained_execution
            and behavior.top_level_vars
            and all(isinstance(c, dict) for c in test_cases_to_run)
        ):
            return self._verify_top_level_vars_unified(python_source, rust_source, behavior, test_cases_to_run)

        # Individual case execution (e.g. direct execution [None], stdin, or mixed)
        return self._verify_individual_cases(python_source, rust_source, behavior, test_cases_to_run)

    def _prepare_test_cases(
        self,
        behavior: ProgramBehavior,
        user_inputs: Optional[List[Any]]
    ) -> List[Any]:
        if user_inputs is not None and len(user_inputs) > 0:
            return user_inputs
        return self.generator.generate(behavior)

    def _verify_functions_unified(
        self,
        python_source: str,
        rust_source: str,
        behavior: ProgramBehavior,
        test_cases: List[Any]
    ) -> VerificationResult:
        """Compiles and executes all function test cases in a single unified run for maximum speed."""
        func = behavior.functions[0]
        for f in behavior.functions:
            if f.name == behavior.primary_function:
                func = f
                break

        func_name = func.name
        ret_type_match = re.search(
            rf"fn\s+{re.escape(func_name)}\s*\([^)]*\)\s*(?:->\s*([^{{]+))?\{{",
            rust_source
        )
        is_debug_format = False
        if ret_type_match and ret_type_match.group(1):
            ret_t = ret_type_match.group(1).strip()
            if "Vec" in ret_t or "HashMap" in ret_t or "[" in ret_t or "(" in ret_t:
                is_debug_format = True

        fmt_spec = "{:?}" if is_debug_format else "{}"

        # Build Python unified harness
        cases_repr = repr([list(c) if isinstance(c, (list, tuple)) else [c] for c in test_cases])
        py_harness = (
            f"\n\n# --- Py2SafeRust Unified Function Verification Harness ---\n"
            f"import sys\n"
            f"_cases = {cases_repr}\n"
            f"for _i, _args in enumerate(_cases):\n"
            f"    if _i > 0:\n"
            f"        print('{DELIM}')\n"
            f"    try:\n"
            f"        _ret = {func_name}(*_args)\n"
            f"        print(_ret)\n"
            f"    except Exception as _e:\n"
            f"        print(f'Runtime Error: {{_e}}')\n"
        )
        # Filter python source to avoid top-level prints polluting harness output
        try:
            py_tree = ast.parse(python_source)
            filtered_body = [
                n for n in py_tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom))
            ]
            if filtered_body:
                py_tree.body = filtered_body
                base_py = ast.unparse(py_tree)
            else:
                base_py = python_source
        except Exception:
            base_py = python_source

        py_code = base_py + py_harness

        # Build Rust unified harness
        rs_blocks = []
        for i, case_args in enumerate(test_cases):
            args_tuple = tuple(case_args) if isinstance(case_args, list) else case_args
            rs_args = [self._to_rust_literal(a) for a in args_tuple]
            rs_call = f"{func_name}({', '.join(rs_args)})"
            if i > 0:
                rs_blocks.append(f'    println!("{DELIM}");')
            rs_blocks.append(f'    println!("{fmt_spec}", {rs_call});')

        new_main = "fn main() {\n" + "\n".join(rs_blocks) + "\n}"
        bounds = extract_fn_bounds(rust_source, "main")
        if bounds:
            rs_code = rust_source[:bounds[0]] + new_main + rust_source[bounds[1]:]
        else:
            rs_code = rust_source + "\n\n" + new_main

        # Execute unified scripts
        py_exec = run_python_code(py_code, timeout=self.timeout)
        rs_exec = run_rust_code(rs_code, timeout=self.timeout)

        # Split results by delimiter
        py_chunks = py_exec.stdout.split(DELIM) if py_exec.success else [""] * len(test_cases)
        rs_chunks = rs_exec.stdout.split(DELIM) if rs_exec.success else [""] * len(test_cases)

        results: List[TestCaseResult] = []
        passed_count = 0

        for idx, case_args in enumerate(test_cases):
            args_tuple = tuple(case_args) if isinstance(case_args, list) else case_args
            desc = f"{func_name}({', '.join(repr(a) for a in args_tuple)})"
            py_raw = py_chunks[idx].strip() if idx < len(py_chunks) else ""
            rs_raw = rs_chunks[idx].strip() if idx < len(rs_chunks) else ""

            py_norm = normalize_output(py_raw)
            rs_norm = normalize_output(rs_raw)

            passed = (py_exec.success and rs_exec.success and (py_norm == rs_norm))

            err = None
            diff_str = None
            if not py_exec.success:
                err = f"Python execution error: {py_exec.stderr.strip() or py_exec.error or 'Failed'}"
            elif not rs_exec.success:
                err = f"Rust execution error: {rs_exec.stderr.strip() or rs_exec.error or 'Failed'}"
            elif py_norm != rs_norm:
                err = f"Output mismatch: expected '{py_norm}', got '{rs_norm}'"

            if not passed:
                diff_str = compute_output_diff(
                    py_norm, rs_norm, py_exec.success, rs_exec.success,
                    py_exec.stderr.strip() or py_exec.error,
                    rs_exec.stderr.strip() or rs_exec.error
                )

            if passed:
                passed_count += 1

            fmt_in, fmt_out, rs_fmt_out, session_py, session_rs = format_function_io(
                func_name, [p.name for p in func.params], args_tuple, py_raw, rs_raw
            )

            results.append(
                TestCaseResult(
                    input_desc=desc,
                    python_stdout=py_raw,
                    rust_stdout=rs_raw,
                    passed=passed,
                    error=err,
                    diff=diff_str,
                    formatted_input=fmt_in,
                    formatted_output=fmt_out,
                    rust_formatted_output=rs_fmt_out,
                    session_transcript=session_py,
                    rust_session_transcript=session_rs
                )
            )

        return self._format_verification_result(results, passed_count)

    def _verify_top_level_vars_unified(
        self,
        python_source: str,
        rust_source: str,
        behavior: ProgramBehavior,
        test_cases: List[Any]
    ) -> VerificationResult:
        """Executes top-level script variable permutations in unified batch."""
        bounds = extract_fn_bounds(rust_source, "main")
        main_inner = bounds[2] if bounds else ""

        rs_blocks = []
        results: List[TestCaseResult] = []
        passed_count = 0

        # Construct single Rust binary with multiple scoped blocks
        for i, var_dict in enumerate(test_cases):
            block_code = main_inner
            if var_dict is not None and isinstance(var_dict, dict):
                for k, v in var_dict.items():
                    rs_val = self._to_rust_literal(v)
                    pattern = rf"(let\s+(?:mut\s+)?{re.escape(k)}\s*=\s*)([^;]+);"
                    if re.search(pattern, block_code):
                        block_code = re.sub(pattern, rf"\g<1>{rs_val};", block_code, count=1)

            if i > 0:
                rs_blocks.append(f'    println!("{DELIM}");')
            rs_blocks.append("    {")
            for line in block_code.strip().splitlines():
                rs_blocks.append(f"        {line.strip()}")
            rs_blocks.append("    }")

        new_main = "fn main() {\n" + "\n".join(rs_blocks) + "\n}"
        if bounds:
            rs_code = rust_source[:bounds[0]] + new_main + rust_source[bounds[1]:]
        else:
            rs_code = rust_source + "\n\n" + new_main

        # Compile and execute Rust once
        rs_exec = run_rust_code(rs_code, timeout=self.timeout)
        rs_chunks = rs_exec.stdout.split(DELIM) if rs_exec.success else [""] * len(test_cases)

        # Run Python for each variable permutation
        for idx, var_dict in enumerate(test_cases):
            if var_dict is None:
                py_code = python_source
                desc = "default"
            else:
                desc = f"vars=({', '.join(f'{k}={v}' for k, v in var_dict.items())})"
                py_code = python_source
                for k, v in var_dict.items():
                    pattern = rf"^(\s*{re.escape(k)}\s*=\s*)([^\n]+)"
                    if re.search(pattern, py_code, flags=re.MULTILINE):
                        py_code = re.sub(pattern, rf"\g<1>{repr(v)}", py_code, count=1, flags=re.MULTILINE)
                    else:
                        py_code = f"{k} = {repr(v)}\n" + py_code

            py_exec = run_python_code(py_code, timeout=self.timeout)
            rs_raw = rs_chunks[idx].strip() if idx < len(rs_chunks) else ""

            py_norm = normalize_output(py_exec.stdout)
            rs_norm = normalize_output(rs_raw)

            passed = (py_exec.success and rs_exec.success and (py_norm == rs_norm))

            err = None
            diff_str = None
            if not py_exec.success:
                err = f"Python execution error: {py_exec.stderr.strip() or py_exec.error or 'Failed'}"
            elif not rs_exec.success:
                err = f"Rust execution error: {rs_exec.stderr.strip() or rs_exec.error or 'Failed'}"
            elif py_norm != rs_norm:
                err = f"Output mismatch: expected '{py_norm}', got '{rs_norm}'"

            if not passed:
                diff_str = compute_output_diff(
                    py_norm, rs_norm, py_exec.success, rs_exec.success,
                    py_exec.stderr.strip() or py_exec.error,
                    rs_exec.stderr.strip() or rs_exec.error
                )

            if passed:
                passed_count += 1

            fmt_in, fmt_out, rs_fmt_out, session_py, session_rs = format_top_level_vars_io(
                behavior, var_dict, py_exec.stdout, rs_raw
            )

            results.append(
                TestCaseResult(
                    input_desc=desc,
                    python_stdout=py_exec.stdout.strip(),
                    rust_stdout=rs_raw,
                    passed=passed,
                    error=err,
                    diff=diff_str,
                    formatted_input=fmt_in,
                    formatted_output=fmt_out,
                    rust_formatted_output=rs_fmt_out,
                    session_transcript=session_py,
                    rust_session_transcript=session_rs
                )
            )

        return self._format_verification_result(results, passed_count)

    def _verify_individual_cases(
        self,
        python_source: str,
        rust_source: str,
        behavior: ProgramBehavior,
        test_cases_to_run: List[Any]
    ) -> VerificationResult:
        results: List[TestCaseResult] = []
        passed_count = 0

        # For stdin-based programs, rust_source does not change across testcases.
        # Compile Rust ONCE upfront rather than N times, speeding up verification by 10x!
        compiled_bin = None
        temp_bin_dir = None
        if behavior.uses_stdin:
            temp_bin_dir = tempfile.mkdtemp(prefix="py2saferust_stdin_")
            comp_res = compile_rust_string(rust_source, output_bin_dir=temp_bin_dir, timeout=30)
            if comp_res.success and comp_res.binary_path:
                compiled_bin = comp_res.binary_path

        try:
            for case_input in test_cases_to_run:
                py_code, rs_code, stdin_val, desc = self._build_case_payload(
                    python_source, rust_source, behavior, case_input
                )

                py_exec = run_python_code(py_code, stdin_input=stdin_val, timeout=self.timeout)
                if compiled_bin:
                    rs_exec = run_rust_binary(compiled_bin, stdin_input=stdin_val, timeout=self.timeout)
                else:
                    rs_exec = run_rust_code(rs_code, stdin_input=stdin_val, timeout=self.timeout)

                py_norm = normalize_output(py_exec.stdout)
                rs_norm = normalize_output(rs_exec.stdout)

                passed = (py_exec.success and rs_exec.success and (py_norm == rs_norm))

                err = None
                diff_str = None
                if not py_exec.success:
                    err = f"Python execution error: {py_exec.stderr.strip() or py_exec.error or 'Failed'}"
                elif not rs_exec.success:
                    err = f"Rust execution error: {rs_exec.stderr.strip() or rs_exec.error or 'Failed'}"
                elif py_norm != rs_norm:
                    err = f"Output mismatch: expected '{py_norm}', got '{rs_norm}'"

                if not passed:
                    diff_str = compute_output_diff(
                        py_norm, rs_norm, py_exec.success, rs_exec.success,
                        py_exec.stderr.strip() or py_exec.error,
                        rs_exec.stderr.strip() or rs_exec.error
                    )

                if passed:
                    passed_count += 1

                if case_input is None:
                    fmt_in, fmt_out, rs_fmt_out, session_py, session_rs = format_direct_execution_io(
                        py_exec.stdout, rs_exec.stdout, rs_success=rs_exec.success, rs_error=rs_exec.stderr.strip() or rs_exec.error
                    )
                else:
                    fmt_in, fmt_out, rs_fmt_out, session_py, session_rs = reconstruct_stdin_io_session(
                        python_source, case_input, py_exec.stdout, rs_exec.stdout
                    )

                results.append(
                    TestCaseResult(
                        input_desc=desc,
                        python_stdout=py_exec.stdout.strip(),
                        rust_stdout=rs_exec.stdout.strip(),
                        passed=passed,
                        error=err,
                        diff=diff_str,
                        formatted_input=fmt_in,
                        formatted_output=fmt_out,
                        rust_formatted_output=rs_fmt_out,
                        session_transcript=session_py,
                        rust_session_transcript=session_rs
                    )
                )

            return self._format_verification_result(results, passed_count)
        finally:
            if temp_bin_dir:
                try:
                    shutil.rmtree(temp_bin_dir, ignore_errors=True)
                except Exception:
                    pass

    def _format_verification_result(
        self,
        results: List[TestCaseResult],
        passed_count: int
    ) -> VerificationResult:
        total = len(results)
        pass_rate = (passed_count / total) if total > 0 else 0.0
        all_passed = (passed_count == total and total > 0)

        feedback = None
        if not all_passed:
            failed_cases = [r for r in results if not r.passed]
            feedback_lines = [f"Semantic Verification Failed ({passed_count}/{total} passed):"]
            for fc in failed_cases:
                feedback_lines.append(f"- Case [{fc.input_desc}]: {fc.error}")
                if fc.diff:
                    feedback_lines.append(f"  Difference Details:\n  {fc.diff}")
                elif fc.python_stdout:
                    feedback_lines.append(f"  Python stdout: {fc.python_stdout}")
                if not fc.diff and fc.rust_stdout:
                    feedback_lines.append(f"  Rust stdout:   {fc.rust_stdout}")
            feedback = "\n".join(feedback_lines)

        return VerificationResult(
            semantic_match=all_passed,
            total_cases=total,
            passed_cases=passed_count,
            pass_rate=pass_rate,
            test_cases=results,
            mismatch_feedback=feedback
        )

    def _build_case_payload(
        self,
        python_source: str,
        rust_source: str,
        behavior: ProgramBehavior,
        case_input: Any
    ) -> Tuple[str, str, Optional[str], str]:
        if case_input is None:
            return python_source, rust_source, None, "default"

        # Stdin input
        if isinstance(case_input, str):
            desc = f"stdin='{case_input.strip()}'"
            return python_source, rust_source, case_input, desc

        return python_source, rust_source, str(case_input), str(case_input)

    def _to_rust_literal(self, val: Any) -> str:
        """Converts a Python literal value into equivalent Rust source syntax."""
        if isinstance(val, bool):
            return "true" if val else "false"
        elif isinstance(val, int):
            return str(val)
        elif isinstance(val, float):
            return f"{val}f64" if not str(val).endswith(".0") else str(val)
        elif isinstance(val, str):
            escaped = val.replace('"', '\\"')
            return f'String::from("{escaped}")'
        elif isinstance(val, (list, tuple)):
            elems = ", ".join(self._to_rust_literal(e) for e in val)
            return f"vec![{elems}]"
        elif isinstance(val, dict):
            entries = []
            for k, v in val.items():
                entries.append(f'map.insert({self._to_rust_literal(k)}, {self._to_rust_literal(v)});')
            body = " ".join(entries)
            return f"{{ let mut map = std::collections::HashMap::new(); {body} map }}"
        return repr(val)
