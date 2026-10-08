"""Rust Code Generator for Py2SafeRust-X.

Emits idiomatic, clean, and compilable Rust code from the analyzed IR tree.
Automatically handles imports, type annotations, vec!/HashMap conversions,
println! format string deduction, and fn main() wrapper generation.
"""
from typing import List, Set, Optional
from .ir import (
    Program, FunctionDef, ClassDef, IRStmt, AssignStmt, ExprStmt, ReturnStmt,
    IfStmt, WhileStmt, ForRangeStmt, ForInStmt, TupleAssignStmt,
    IRExpr, Literal, Variable, BinaryOp, UnaryOp, Call, MethodCall,
    Subscript, ListExpr, DictExpr, TupleExpr, CloneExpr, ListComp, RustType
)


class RustCodeGenerator:
    def __init__(self):
        self.indent_level: int = 0
        self.declared_vars: Set[str] = set()
        self.uses_hashmap: bool = False
        self.uses_stdin: bool = False

    def _indent(self) -> str:
        return "    " * self.indent_level

    def generate(self, program: Program) -> str:
        self.indent_level = 0
        self.declared_vars.clear()
        self.uses_hashmap = False
        self.uses_stdin = False

        # First pass to check if HashMap is used anywhere
        self._check_hashmap_usage(program)

        # Generate structs & impl blocks
        class_lines: List[str] = []
        for cls in program.classes:
            class_lines.append(self._generate_class(cls))
            class_lines.append("")

        # Generate standalone functions
        func_lines: List[str] = []
        for func in program.functions:
            func_lines.append(self._generate_function(func))
            func_lines.append("")

        # If there are top-level statements, wrap them in fn main()
        # Even if there are no top-level statements, generate an empty fn main() if not present
        main_lines: List[str] = []
        has_user_main = any(f.name == "main" for f in program.functions)
        if not has_user_main:
            main_lines.append("fn main() {")
            self.indent_level += 1
            for stmt in program.statements:
                main_lines.append(self._generate_stmt(stmt))
            self.indent_level -= 1
            main_lines.append("}")

        header_lines: List[str] = []
        if self.uses_stdin:
            header_lines.append("use std::io::{self, Write};")
        if self.uses_hashmap:
            header_lines.append("use std::collections::HashMap;")
        if header_lines:
            header_lines.append("")

        if self.uses_stdin:
            header_lines.append("fn __py2saferust_input(prompt: &str) -> String {")
            header_lines.append('    print!("{}", prompt);')
            header_lines.append("    let _ = io::stdout().flush();")
            header_lines.append("    let mut line = String::new();")
            header_lines.append("    let _ = io::stdin().read_line(&mut line);")
            header_lines.append("    line.trim_end_matches(&['\\r', '\\n'][..]).to_string()")
            header_lines.append("}")
            header_lines.append("")

        lines = header_lines + class_lines + func_lines + main_lines
        result = "\n".join(lines).strip() + "\n"
        return result

    def _check_hashmap_usage(self, program: Program) -> None:
        def check_t(t: Optional[RustType]):
            if t:
                if t.name == "HashMap":
                    self.uses_hashmap = True
                for arg in t.type_args:
                    check_t(arg)

        def check_expr(e: Optional[IRExpr]):
            if e is None:
                return
            if isinstance(e, DictExpr):
                self.uses_hashmap = True
            check_t(e.inferred_type)
            if isinstance(e, BinaryOp):
                check_expr(e.left)
                check_expr(e.right)
            elif isinstance(e, UnaryOp):
                check_expr(e.operand)
            elif isinstance(e, Call):
                for a in e.args:
                    check_expr(a)
            elif isinstance(e, MethodCall):
                check_expr(e.obj)
                for a in e.args:
                    check_expr(a)
            elif isinstance(e, ListExpr):
                for el in e.elements:
                    check_expr(el)
            elif isinstance(e, TupleExpr):
                for el in e.elements:
                    check_expr(el)
            elif isinstance(e, CloneExpr):
                check_expr(e.inner)
            elif isinstance(e, ListComp):
                check_expr(e.elt)
                check_expr(e.iter_expr)

        def check_stmt(s: IRStmt):
            if isinstance(s, AssignStmt):
                check_t(s.inferred_type)
                check_expr(s.value)
            elif isinstance(s, TupleAssignStmt):
                for v in s.values:
                    check_expr(v)
            elif isinstance(s, ExprStmt):
                check_expr(s.expr)
            elif isinstance(s, ReturnStmt):
                check_expr(s.value)
            elif isinstance(s, IfStmt):
                check_expr(s.condition)
                for st in s.then_body:
                    check_stmt(st)
                for st in s.else_body:
                    check_stmt(st)
            elif isinstance(s, WhileStmt):
                check_expr(s.condition)
                for st in s.body:
                    check_stmt(st)
            elif isinstance(s, ForRangeStmt):
                check_expr(s.start)
                check_expr(s.end)
                if s.step:
                    check_expr(s.step)
                for st in s.body:
                    check_stmt(st)
            elif isinstance(s, ForInStmt):
                check_expr(s.iter_expr)
                for st in s.body:
                    check_stmt(st)

        for cls in program.classes:
            for f in cls.fields:
                check_t(f.field_type)
            for m in cls.methods:
                check_t(m.return_type)
                for p in m.params:
                    check_t(p.param_type)
                for st in m.body:
                    check_stmt(st)
        for func in program.functions:
            check_t(func.return_type)
            for p in func.params:
                check_t(p.param_type)
            for st in func.body:
                check_stmt(st)
        for stmt in program.statements:
            check_stmt(stmt)

    def _generate_class(self, cls: ClassDef) -> str:
        lines: List[str] = []
        lines.append(f"#[derive(Debug, Clone)]")
        lines.append(f"struct {cls.name} {{")
        self.indent_level += 1
        for field in cls.fields:
            ft = field.field_type.to_rust_str()
            lines.append(f"{self._indent()}pub {field.name}: {ft},")
        self.indent_level -= 1
        lines.append("}")

        if cls.methods:
            lines.append("")
            lines.append(f"impl {cls.name} {{")
            self.indent_level += 1
            for method in cls.methods:
                lines.append(self._generate_function(method, is_method=True))
            self.indent_level -= 1
            lines.append("}")

        return "\n".join(lines)

    def _generate_function(self, func: FunctionDef, is_method: bool = False) -> str:
        params_str_list: List[str] = []
        if is_method:
            params_str_list.append("&mut self")

        for p in func.params:
            p_type = p.param_type.to_rust_str() if p.param_type else "/* type: unknown */"
            mut_prefix = "mut " if p.is_mut else ""
            params_str_list.append(f"{mut_prefix}{p.name}: {p_type}")

        ret_str = ""
        if func.return_type and func.return_type.name not in ("void", "None", "()"):
            ret_str = f" -> {func.return_type.to_rust_str()}"

        head = f"{self._indent()}fn {func.name}({', '.join(params_str_list)}){ret_str} {{"
        lines = [head]
        self.indent_level += 1

        local_declared = set(self.declared_vars)
        for stmt in func.body:
            lines.append(self._generate_stmt(stmt))
        self.declared_vars = local_declared

        self.indent_level -= 1
        lines.append(f"{self._indent()}}}")
        return "\n".join(lines)

    def _strip_outer_parens(self, s: str) -> str:
        """Remove a single layer of wrapping parentheses if they wrap the entire expression."""
        s = s.strip()
        if s.startswith('(') and s.endswith(')'):
            # Make sure the opening paren actually closes at the end (not mid-expression)
            depth = 0
            for i, ch in enumerate(s):
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                if depth == 0 and i < len(s) - 1:
                    return s  # paren closes before end — don't strip
            return s[1:-1].strip()
        return s

    def _prompt_str(self, expr: Optional['IRExpr']) -> str:
        """Return a Rust &str literal for a prompt expression (used by input() calls).

        Emits a bare string literal e.g. "Enter value: " rather than
        "...".to_string() because __py2saferust_input takes &str.
        """
        if expr is None:
            return '""'
        if isinstance(expr, Literal) and isinstance(expr.value, str):
            # Escape backslashes and double-quotes in the prompt text
            escaped = expr.value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        # Fallback: generate the expression and hope it is &str compatible
        return self._generate_expr(expr)

    def _generate_stmt(self, stmt: IRStmt) -> str:
        ind = self._indent()
        if isinstance(stmt, AssignStmt):
            is_new = stmt.target not in self.declared_vars
            mut_kw = "mut " if stmt.is_mut else ""
            val_str = self._generate_expr(stmt.value) if stmt.value else "Default::default()"
            # Strip unnecessary outer parens to avoid rustc warning on assignment RHS
            val_str = self._strip_outer_parens(val_str)

            if is_new:
                self.declared_vars.add(stmt.target)
                type_annot = ""
                if stmt.inferred_type and stmt.inferred_type.name == "HashMap":
                    type_annot = f": {stmt.inferred_type.to_rust_str()}"
                return f"{ind}let {mut_kw}{stmt.target}{type_annot} = {val_str};"
            else:
                return f"{ind}{stmt.target} = {val_str};"

        elif isinstance(stmt, TupleAssignStmt):
            lines = []
            all_new = all(t not in self.declared_vars for t in stmt.targets)
            if all_new:
                for target, val in zip(stmt.targets, stmt.values):
                    self.declared_vars.add(target)
                    val_str = self._generate_expr(val)
                    lines.append(f"{ind}let mut {target} = {val_str};")
                return "\n".join(lines)
            else:
                temps = [f"__temp_{i}" for i in range(len(stmt.values))]
                val_strs = [self._generate_expr(val) for val in stmt.values]
                lines.append(f"{ind}let ({', '.join(temps)}) = ({', '.join(val_strs)});")
                for target, temp in zip(stmt.targets, temps):
                    if target not in self.declared_vars:
                        self.declared_vars.add(target)
                        lines.append(f"{ind}let mut {target} = {temp};")
                    else:
                        lines.append(f"{ind}{target} = {temp};")
                return "\n".join(lines)

        elif isinstance(stmt, ExprStmt):
            # Special handling for subscript set
            if isinstance(stmt.expr, MethodCall) and stmt.expr.method == "_set_subscript":
                target_str = self._generate_expr(stmt.expr.obj)
                idx_str = self._generate_expr(stmt.expr.args[0])
                val_str = self._generate_expr(stmt.expr.args[1])
                return f"{ind}{target_str}[{idx_str} as usize] = {val_str};"
            return f"{ind}{self._generate_expr(stmt.expr)};"

        elif isinstance(stmt, ReturnStmt):
            if stmt.value:
                return f"{ind}return {self._generate_expr(stmt.value)};"
            return f"{ind}return;"

        elif isinstance(stmt, IfStmt):
            lines = [f"{ind}if {self._generate_expr(stmt.condition)} {{"]
            self.indent_level += 1
            for s in stmt.then_body:
                lines.append(self._generate_stmt(s))
            self.indent_level -= 1

            if stmt.else_body:
                lines.append(f"{ind}}} else {{")
                self.indent_level += 1
                for s in stmt.else_body:
                    lines.append(self._generate_stmt(s))
                self.indent_level -= 1
            lines.append(f"{ind}}}")
            return "\n".join(lines)

        elif isinstance(stmt, WhileStmt):
            lines = [f"{ind}while {self._generate_expr(stmt.condition)} {{"]
            self.indent_level += 1
            for s in stmt.body:
                lines.append(self._generate_stmt(s))
            self.indent_level -= 1
            lines.append(f"{ind}}}")
            return "\n".join(lines)

        elif isinstance(stmt, ForRangeStmt):
            start = self._generate_expr(stmt.start)
            end = self._generate_expr(stmt.end)
            range_expr = f"({start}..{end})"
            if stmt.step:
                step_val = self._generate_expr(stmt.step)
                range_expr = f"({start}..{end}).step_by({step_val} as usize)"

            lines = [f"{ind}for {stmt.var} in {range_expr} {{"]
            self.indent_level += 1
            for s in stmt.body:
                lines.append(self._generate_stmt(s))
            self.indent_level -= 1
            lines.append(f"{ind}}}")
            return "\n".join(lines)

        elif isinstance(stmt, ForInStmt):
            iter_s = self._generate_expr(stmt.iter_expr)
            lines = [f"{ind}for {stmt.var} in &{iter_s} {{"]
            self.indent_level += 1
            for s in stmt.body:
                lines.append(self._generate_stmt(s))
            self.indent_level -= 1
            lines.append(f"{ind}}}")
            return "\n".join(lines)

        return f"{ind}/* unhandled statement */"

    def _generate_expr(self, expr: Optional[IRExpr]) -> str:
        if expr is None:
            return "()"

        if isinstance(expr, Literal):
            if isinstance(expr.value, str):
                return f'"{expr.value}".to_string()'
            return expr.raw_text

        elif isinstance(expr, Variable):
            return expr.name

        elif isinstance(expr, CloneExpr):
            inner_str = self._generate_expr(expr.inner)
            return f"{inner_str}.clone()"

        elif isinstance(expr, BinaryOp):
            l_str = self._generate_expr(expr.left)
            r_str = self._generate_expr(expr.right)
            if expr.op == "**":
                return f"({l_str} as f64).powf({r_str} as f64)"
            # Emit without outer parens; caller (_generate_stmt) strips them
            # when used on the RHS of a let/assign to avoid rustc warnings.
            return f"{l_str} {expr.op} {r_str}"

        elif isinstance(expr, UnaryOp):
            op_str = expr.op
            operand_str = self._generate_expr(expr.operand)
            return f"{op_str}{operand_str}"

        elif isinstance(expr, ListExpr):
            elems = ", ".join(self._generate_expr(e) for e in expr.elements)
            return f"vec![{elems}]"

        elif isinstance(expr, DictExpr):
            self.uses_hashmap = True
            pairs = ", ".join(
                f"({self._generate_expr(k)}, {self._generate_expr(v)})"
                for k, v in zip(expr.keys, expr.values)
            )
            return f"std::collections::HashMap::from([{pairs}])"

        elif isinstance(expr, TupleExpr):
            elems = ", ".join(self._generate_expr(e) for e in expr.elements)
            return f"({elems})"

        elif isinstance(expr, ListComp):
            elt_str = self._generate_expr(expr.elt)
            if isinstance(expr.iter_expr, Call) and expr.iter_expr.func == "range":
                if len(expr.iter_expr.args) == 1:
                    iter_str = f"(0..{self._generate_expr(expr.iter_expr.args[0])})"
                elif len(expr.iter_expr.args) == 2:
                    iter_str = f"({self._generate_expr(expr.iter_expr.args[0])}..{self._generate_expr(expr.iter_expr.args[1])})"
                else:
                    iter_str = self._generate_expr(expr.iter_expr)
            else:
                iter_str = self._generate_expr(expr.iter_expr)
            if expr.condition:
                cond_str = self._generate_expr(expr.condition)
                return f"{{ let mut __vec = Vec::new(); for {expr.var} in {iter_str} {{ if {cond_str} {{ __vec.push({elt_str}); }} }} __vec }}"
            return f"{{ let mut __vec = Vec::new(); for {expr.var} in {iter_str} {{ __vec.push({elt_str}); }} __vec }}"

        elif isinstance(expr, Subscript):
            target_str = self._generate_expr(expr.target)
            idx_str = self._generate_expr(expr.index)
            # Check if index is integer or string
            return f"{target_str}[{idx_str} as usize]"

        elif isinstance(expr, Call):
            if expr.func == "print":
                return self._generate_print(expr.args)
            elif expr.func == "input":
                self.uses_stdin = True
                prompt_arg = self._prompt_str(expr.args[0]) if expr.args else '""'
                return f"__py2saferust_input({prompt_arg})"
            elif expr.func == "len":
                arg_str = self._generate_expr(expr.args[0])
                return f"({arg_str}.len() as i64)"
            elif expr.func == "int":
                if expr.args and isinstance(expr.args[0], Call) and expr.args[0].func == "input":
                    self.uses_stdin = True
                    prompt_arg = self._prompt_str(expr.args[0].args[0]) if expr.args[0].args else '""'
                    return f"__py2saferust_input({prompt_arg}).parse::<i64>().unwrap_or(0)"
                arg_str = self._generate_expr(expr.args[0])
                return f"({arg_str} as i64)"
            elif expr.func == "float":
                if expr.args and isinstance(expr.args[0], Call) and expr.args[0].func == "input":
                    self.uses_stdin = True
                    prompt_arg = self._prompt_str(expr.args[0].args[0]) if expr.args[0].args else '""'
                    return f"__py2saferust_input({prompt_arg}).parse::<f64>().unwrap_or(0.0)"
                arg_str = self._generate_expr(expr.args[0])
                return f"({arg_str} as f64)"
            elif expr.func == "str":
                arg_str = self._generate_expr(expr.args[0])
                return f"format!(\"{{}}\", {arg_str})"

            args_str = ", ".join(self._generate_expr(a) for a in expr.args)
            return f"{expr.func}({args_str})"

        elif isinstance(expr, MethodCall):
            obj_str = self._generate_expr(expr.obj)
            if expr.method == "append":
                val = self._generate_expr(expr.args[0])
                return f"{obj_str}.push({val})"
            elif expr.method == "clone":
                return f"{obj_str}.clone()"
            args_str = ", ".join(self._generate_expr(a) for a in expr.args)
            return f"{obj_str}.{expr.method}({args_str})"

        return "/* unsupported expr */"

    def _generate_print(self, args: List[IRExpr]) -> str:
        if not args:
            return 'println!()'

        # Separate literal string parts from runtime values so we can build
        # a single format string instead of multiple {}
        format_parts: List[str] = []
        arg_strings: List[str] = []

        for arg in args:
            if isinstance(arg, Literal) and isinstance(arg.value, str):
                # Embed the string directly into the format string
                escaped = arg.value.replace('\\', '\\\\').replace('"', '\\"').replace('{', '{{').replace('}', '}}')
                format_parts.append(escaped)
            else:
                # Complex types like Vec, HashMap, Tuple use {:?} in Rust
                is_debug = False
                if isinstance(arg, (ListExpr, DictExpr, TupleExpr, ListComp)):
                    is_debug = True
                elif isinstance(arg, Variable) and arg.inferred_type and arg.inferred_type.name in ("Vec", "HashMap", "tuple"):
                    is_debug = True
                elif isinstance(arg, CloneExpr) and arg.inferred_type and arg.inferred_type.name in ("Vec", "HashMap", "tuple"):
                    is_debug = True

                format_parts.append("{:?}" if is_debug else "{}")
                arg_strings.append(self._generate_expr(arg))

        fmt_str = " ".join(format_parts)
        if arg_strings:
            rendered_args = ", ".join(arg_strings)
            return f'println!("{fmt_str}", {rendered_args})'
        else:
            return f'println!("{fmt_str}")'
