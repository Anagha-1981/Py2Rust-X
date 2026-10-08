"""Program Behavior Analyzer and Test Case Generator for Py2SafeRust-X.

Analyzes Python AST to determine program characteristics (functions, parameter
types, recursion, mathematical vs string operations, stdin usage, control flow)
and automatically generates 5-8 diverse semantic test cases (boundary values,
typical inputs, zero/empty states, negatives, and structural variations).
"""
import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ParamInfo:
    name: str
    inferred_type: str  # "int", "float", "str", "bool", "list", "dict", "unknown"
    default_value: Optional[Any] = None


@dataclass
class FunctionSignature:
    name: str
    params: List[ParamInfo] = field(default_factory=list)
    return_type: str = "unknown"
    is_recursive: bool = False
    has_division: bool = False
    operation_hints: Set[str] = field(default_factory=set)


@dataclass
class ProgramBehavior:
    has_functions: bool
    functions: List[FunctionSignature] = field(default_factory=list)
    primary_function: Optional[str] = None
    uses_stdin: bool = False
    stdin_count: int = 0
    uses_loops: bool = False
    uses_recursion: bool = False
    uses_math: bool = False
    uses_strings: bool = False
    uses_lists: bool = False
    uses_dicts: bool = False
    top_level_vars: Dict[str, Any] = field(default_factory=dict)
    has_print_stmts: bool = False
    has_top_level_calls: bool = False
    has_self_contained_execution: bool = False


class ProgramBehaviorAnalyzer:
    """Analyzes Python code AST to discover behavioral semantics and signatures."""

    def analyze(self, python_source: str) -> ProgramBehavior:
        try:
            tree = ast.parse(python_source)
        except Exception:
            # Fallback for unparseable snippet
            return ProgramBehavior(has_functions=False)

        functions: List[FunctionSignature] = []
        uses_stdin = False
        uses_loops = False
        uses_recursion = False
        uses_math = False
        uses_strings = False
        uses_lists = False
        uses_dicts = False
        has_print = False
        top_level_vars: Dict[str, Any] = {}

        # Scan top-level statements
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        val = self._extract_constant(stmt.value)
                        if val is not None:
                            top_level_vars[target.id] = val
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                func_id = getattr(stmt.value.func, "id", None)
                if func_id == "print":
                    has_print = True

        stdin_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_id = getattr(node.func, "id", None)
                if func_id == "input":
                    uses_stdin = True
                elif func_id == "print":
                    has_print = True
            elif isinstance(node, (ast.For, ast.While)):
                uses_loops = True
            elif isinstance(node, (ast.List, ast.ListComp)):
                uses_lists = True
            elif isinstance(node, (ast.Dict, ast.DictComp)):
                uses_dicts = True
            elif isinstance(node, ast.BinOp):
                if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)):
                    uses_math = True
            elif isinstance(node, ast.Constant):
                if isinstance(node.value, str):
                    uses_strings = True

        if uses_stdin:
            class StdinCounter(ast.NodeVisitor):
                def __init__(self):
                    self.loop_stack = []
                    self.direct = 0
                    self.loop_inputs = 0

                def visit_For(self, node):
                    iters = 3
                    if isinstance(node.iter, ast.Call) and getattr(node.iter.func, "id", None) == "range":
                        if node.iter.args:
                            arg = node.iter.args[0] if len(node.iter.args) == 1 else (node.iter.args[1] if len(node.iter.args) >= 2 else None)
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                                iters = min(10, max(1, arg.value))
                    self.loop_stack.append(iters)
                    self.generic_visit(node)
                    self.loop_stack.pop()

                def visit_While(self, node):
                    self.loop_stack.append(3)
                    self.generic_visit(node)
                    self.loop_stack.pop()

                def visit_Call(self, node):
                    if getattr(node.func, "id", None) == "input":
                        if self.loop_stack:
                            self.loop_inputs += self.loop_stack[-1]
                        else:
                            self.direct += 1
                    self.generic_visit(node)

            counter = StdinCounter()
            counter.visit(tree)
            stdin_count = max(1, counter.direct + counter.loop_inputs)

        # Analyze functions
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                sig = self._analyze_function(node)
                functions.append(sig)
                if sig.is_recursive:
                    uses_recursion = True

        primary_func = functions[0].name if functions else None

        # Check if the code has inputs given directly in the code (self-contained script)
        has_call_to_main = False
        has_top_level_calls = False
        has_classes = any(isinstance(s, ast.ClassDef) for s in tree.body)

        top_level_executable_stmts = [
            s for s in tree.body
            if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom))
        ]

        if top_level_executable_stmts:
            for stmt in top_level_executable_stmts:
                for subnode in ast.walk(stmt):
                    if isinstance(subnode, ast.Call):
                        has_top_level_calls = True
                        func_id = getattr(subnode.func, "id", None)
                        if func_id == "main":
                            has_call_to_main = True
                        elif func_id == "print":
                            has_print = True

        has_self_contained_execution = False
        if not uses_stdin:
            if top_level_executable_stmts:
                has_self_contained_execution = True
            elif has_call_to_main or primary_func == "main":
                has_self_contained_execution = True
            elif functions and all(len(f.params) == 0 for f in functions):
                has_self_contained_execution = True
            elif has_classes and has_top_level_calls:
                has_self_contained_execution = True
            elif has_top_level_calls or has_print or top_level_vars:
                has_self_contained_execution = True

        return ProgramBehavior(
            has_functions=len(functions) > 0,
            functions=functions,
            primary_function=primary_func,
            uses_stdin=uses_stdin,
            stdin_count=stdin_count,
            uses_loops=uses_loops,
            uses_recursion=uses_recursion,
            uses_math=uses_math,
            uses_strings=uses_strings,
            uses_lists=uses_lists,
            uses_dicts=uses_dicts,
            top_level_vars=top_level_vars,
            has_print_stmts=has_print,
            has_top_level_calls=has_top_level_calls,
            has_self_contained_execution=has_self_contained_execution
        )

    def _extract_constant(self, node: ast.AST) -> Optional[Any]:
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            return -node.operand.value
        elif isinstance(node, ast.List):
            elems = [self._extract_constant(e) for e in node.elts]
            if all(e is not None for e in elems):
                return elems
        return None

    def _analyze_function(self, func_node: ast.FunctionDef) -> FunctionSignature:
        name = func_node.name
        is_rec = False
        has_div = False
        hints: Set[str] = set()

        for subnode in ast.walk(func_node):
            if isinstance(subnode, ast.Call):
                call_id = getattr(subnode.func, "id", None)
                if call_id == name:
                    is_rec = True
            elif isinstance(subnode, ast.BinOp):
                if isinstance(subnode.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                    has_div = True
                hints.add("arithmetic")
            elif isinstance(subnode, ast.Subscript):
                hints.add("subscript")
            elif isinstance(subnode, ast.For):
                hints.add("loop")

        params: List[ParamInfo] = []
        for arg in func_node.args.args:
            p_name = arg.arg
            inferred = self._infer_param_type(arg, func_node)
            params.append(ParamInfo(name=p_name, inferred_type=inferred))

        ret_type = "unknown"
        if func_node.returns:
            ret_type = self._annotation_to_type(func_node.returns)

        return FunctionSignature(
            name=name,
            params=params,
            return_type=ret_type,
            is_recursive=is_rec,
            has_division=has_div,
            operation_hints=hints
        )

    def _annotation_to_type(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            mapping = {
                "int": "int",
                "float": "float",
                "str": "str",
                "bool": "bool",
                "list": "list",
                "dict": "dict",
            }
            return mapping.get(node.id, node.id)
        elif isinstance(node, ast.Subscript):
            val_id = getattr(node.value, "id", "")
            if val_id in ("List", "list"):
                return "list"
            elif val_id in ("Dict", "dict"):
                return "dict"
        return "unknown"

    def _infer_param_type(self, arg_node: ast.arg, func_node: ast.FunctionDef) -> str:
        if arg_node.annotation:
            t = self._annotation_to_type(arg_node.annotation)
            if t != "unknown":
                return t

        name = arg_node.arg.lower()
        # Heuristics based on name
        if name in ("s", "text", "str_val", "word", "sentence", "name", "prefix", "suffix", "line"):
            return "str"
        if name in ("lst", "arr", "items", "nums", "elements", "vector", "values", "data"):
            return "list"
        if name in ("d", "dict_val", "mapping", "lookup", "table"):
            return "dict"
        if name.startswith("is_") or name.startswith("has_") or name in ("flag", "cond"):
            return "bool"
        if name in ("n", "x", "y", "z", "a", "b", "c", "i", "j", "k", "num", "count", "idx", "size", "len", "limit", "val", "value"):
            return "int"

        # Look for usages in AST
        for subnode in ast.walk(func_node):
            if isinstance(subnode, ast.For) and isinstance(subnode.iter, ast.Name) and subnode.iter.id == arg_node.arg:
                return "list"
            if isinstance(subnode, ast.Subscript) and isinstance(subnode.value, ast.Name) and subnode.value.id == arg_node.arg:
                return "list"

        return "int"


class TestCaseGenerator:
    """Generates 5-8 diverse, targeted test cases based on program behavior."""
    __test__ = False

    def __init__(self, target_count: int = 6):
        # Bound target count strictly between 5 and 8
        self.target_count = max(5, min(8, target_count))

    def generate(self, behavior: ProgramBehavior) -> List[Any]:
        """Generates 5-6 test cases ONLY for programs where input has to be accepted from user (via input()).
        If input is already specified in the program itself, just check only that (single direct execution)."""
        # 1. Programs accepting user inputs via input() -> test 5-6 diverse test cases
        if behavior.uses_stdin:
            return self._generate_stdin_cases(behavior)

        # 2. Codes where inputs are given directly in code
        #    (self-contained script, print statements, top-level function calls, top-level variables)
        if (
            behavior.has_self_contained_execution
            or behavior.has_print_stmts
            or behavior.has_top_level_calls
            or behavior.top_level_vars
        ):
            return [None]

        # 3. Parameterized functions without any caller or inputs in the code -> generate diverse test cases
        if behavior.has_functions and behavior.functions:
            primary = behavior.functions[0]
            for f in behavior.functions:
                if f.name == behavior.primary_function:
                    primary = f
                    break
            if primary.params:
                return self._generate_function_cases(primary)
            return [None]

        # Baseline execution for static scripts
        return [None]

    def _generate_stdin_cases(self, behavior: ProgramBehavior) -> List[str]:
        """Generates 5-8 distinct stdin input streams matching the number of expected inputs."""
        n = max(1, behavior.stdin_count)
        if n == 1:
            if behavior.uses_math:
                candidates = ["5\n", "2\n", "7\n", "1\n", "0\n", "10\n", "13\n", "-3\n"]
            elif behavior.uses_strings:
                candidates = ["hello\n", "\n", "world\n", "racecar\n", "Python 3\n", "test 123\n", "a\n", "madam\n"]
            else:
                candidates = ["10\n", "0\n", "1\n", "5\n", "-1\n", "25\n", "100\n", "2\n"]
            return candidates[:self.target_count]

        # Multi-input programs (e.g., 2 or more input() calls)
        if behavior.uses_math:
            base_tuples = [
                [5, 10, 15, 20],
                [0, 0, 0, 0],
                [1, 2, 3, 4],
                [-3, 7, -2, 5],
                [10, 20, 30, 40],
                [42, 8, 12, 16],
                [100, -50, 25, 75],
                [2, 3, 5, 7],
            ]
            cases = []
            for row in base_tuples[:self.target_count]:
                vals = [str(row[i % len(row)]) for i in range(n)]
                cases.append("\n".join(vals) + "\n")
            return cases
        elif behavior.uses_strings:
            base_tuples = [
                ["hello", "world", "foo", "bar"],
                ["alpha", "beta", "gamma", "delta"],
                ["test", "case", "input", "data"],
                ["first", "second", "third", "fourth"],
                ["apple", "banana", "orange", "grape"],
                ["rust", "python", "code", "safe"],
                ["quick", "brown", "fox", "jumps"],
                ["one", "two", "three", "four"]
            ]
            cases = []
            for row in base_tuples[:self.target_count]:
                vals = [row[i % len(row)] for i in range(n)]
                cases.append("\n".join(vals) + "\n")
            return cases
        else:
            base_tuples = [
                [10, 20, 30],
                [0, 1, 2],
                [5, 15, 25],
                [-1, 1, 0],
                [42, 100, 200],
                [7, 14, 21],
                [3, 6, 9],
                [8, 16, 24]
            ]
            cases = []
            for row in base_tuples[:self.target_count]:
                vals = [str(row[i % len(row)]) for i in range(n)]
                cases.append("\n".join(vals) + "\n")
            return cases

    def _generate_function_cases(self, func: FunctionSignature) -> List[Any]:
        """Generates 5-8 diverse argument tuples for the target function."""
        params = func.params
        if not params:
            return [()] * self.target_count

        # Generate candidates for each parameter
        param_candidates: List[List[Any]] = []
        for p in params:
            vals = self._candidates_for_type(p.inferred_type, func)
            param_candidates.append(vals)

        # Combine into tuples of length equal to param count
        num_cases = self.target_count
        cases: List[Tuple[Any, ...]] = []
        for i in range(num_cases):
            case_args = []
            for p_idx, vals in enumerate(param_candidates):
                case_args.append(vals[(i + p_idx) % len(vals)])
            cases.append(tuple(case_args))

        return cases

    def _candidates_for_type(self, type_name: str, func: FunctionSignature) -> List[Any]:
        """Generates a rich spectrum of 8 values for the given type."""
        is_rec = func.is_recursive
        has_div = func.has_division

        if type_name == "int":
            if is_rec or func.name.lower() in ("factorial", "fibonacci", "fib", "fact"):
                # Strict non-negative small inputs to prevent recursion overflow
                return [5, 0, 1, 2, 3, 4, 6, 7]
            if has_div:
                # Avoid zero in general divisor positions
                return [10, 1, 2, -5, 20, 4, -2, 8]
            # Standard rich int spectrum: typical, zero, unit, negative, larger, edge
            return [15, 0, 1, -5, 42, -10, 100, 7]

        elif type_name == "float":
            if has_div:
                return [10.5, 1.0, 2.5, -4.0, 20.25, 0.5, -2.5, 8.0]
            return [12.5, 0.0, 1.0, -3.5, 42.0, -10.25, 100.0, 0.1]

        elif type_name == "str":
            # Typical, empty, unit, palindrome, phrases, special chars, uppercase
            return [
                "hello",
                "",
                "a",
                "racecar",
                "Python 3.11",
                "madam",
                "safe_rust",
                "WORLD!"
            ]

        elif type_name == "list":
            # Typical, empty, unit, negative, larger, duplicates, sorted, mixed
            return [
                [1, 2, 3],
                [],
                [42],
                [-5, 0, 5],
                [10, 20, 30, 40, 50],
                [1, 1, 2, 2, 3],
                [9, 8, 7, 6],
                [0, 0, 0]
            ]

        elif type_name == "bool":
            return [True, False, True, False, True, False, True, False]

        elif type_name == "dict":
            return [
                {"a": 1, "b": 2},
                {},
                {"key": 42},
                {"x": 10, "y": 20, "z": 30},
                {"item": 0},
                {"first": 100, "second": 200},
                {"k": -5},
                {"num": 7}
            ]

        # Default fallback
        return [10, 0, 1, -1, 5, 20, 100, 42]

    def _generate_top_level_cases(self, behavior: ProgramBehavior) -> List[Any]:
        """Generates 5-8 variations of top-level variable values."""
        vars_dict = behavior.top_level_vars
        cases: List[Any] = [None]  # Case 1 is always baseline default

        # Pick up to 2 numeric/string variables to perturb
        perturbers = [(k, v) for k, v in vars_dict.items() if isinstance(v, (int, float, str, list))][:2]
        if not perturbers:
            return [None] * self.target_count

        permutations = [
            # Variant 1: zero/minimal
            {k: 0 if isinstance(v, (int, float)) else ("" if isinstance(v, str) else ([v[0]] if v else [0])) for k, v in perturbers},
            # Variant 2: unit
            {k: 1 if isinstance(v, (int, float)) else ("a" if isinstance(v, str) else [1]) for k, v in perturbers},
            # Variant 3: negative / alt
            {k: -5 if isinstance(v, (int, float)) else ("world" if isinstance(v, str) else [-1, 0]) for k, v in perturbers},
            # Variant 4: larger
            {k: 100 if isinstance(v, (int, float)) else ("test" if isinstance(v, str) else [10, 20, 30]) for k, v in perturbers},
            # Variant 5: distinct values
            {k: 42 if isinstance(v, (int, float)) else ("Rust" if isinstance(v, str) else [5, 4, 3]) for k, v in perturbers},
            # Variant 6: edge
            {k: -10 if isinstance(v, (int, float)) else ("Python" if isinstance(v, str) else [0]) for k, v in perturbers},
            # Variant 7: double
            {k: 50 if isinstance(v, (int, float)) else ("abc" if isinstance(v, str) else [1, 2]) for k, v in perturbers},
        ]

        for p in permutations:
            if len(cases) >= self.target_count:
                break
            cases.append(p)

        return cases[:self.target_count]
