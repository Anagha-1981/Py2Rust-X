"""Python AST Parser for Py2SafeRust-X.

Parses Python source code into the Py2SafeRust-X Intermediate Representation (IR).
NOTE ON FUTURE UPGRADE:
    The project specification notes tree-sitter as a future upgrade path for
    fault-tolerant parsing and richer language support across multiple frontend
    dialects. For v1, Python's built-in `ast` module is utilized.
"""
import ast
from typing import List, Optional, Tuple, Any
from .ir import (
    Program, FunctionDef, Param, ClassDef, ClassField,
    IRStmt, AssignStmt, ExprStmt, ReturnStmt, IfStmt, WhileStmt,
    ForRangeStmt, ForInStmt, TupleAssignStmt,
    IRExpr, Literal, Variable, BinaryOp, UnaryOp, Call, MethodCall,
    Subscript, ListExpr, DictExpr, TupleExpr, ListComp, RustType
)


class ParserError(Exception):
    pass


class PythonASTParser:
    def __init__(self):
        self.warnings: List[str] = []

    def parse(self, source_code: str) -> Program:
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            raise ParserError(f"Syntax error at line {e.lineno}, col {e.offset}: {e.msg}")

        program = Program()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                program.functions.append(self._parse_function(node))
            elif isinstance(node, ast.ClassDef):
                program.classes.append(self._parse_class(node))
            elif isinstance(node, ast.If) and self._is_name_main_guard(node):
                # if __name__ == "__main__": top-level block unwraps directly into fn main() statements
                for inner in node.body:
                    stmt = self._parse_stmt(inner)
                    if stmt:
                        program.statements.append(stmt)
            else:
                stmt = self._parse_stmt(node)
                if stmt:
                    program.statements.append(stmt)
        return program

    def _is_name_main_guard(self, node: ast.If) -> bool:
        """Checks if an If node is `if __name__ == '__main__':`."""
        if isinstance(node.test, ast.Compare):
            left = node.test.left
            if len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.Eq) and len(node.test.comparators) == 1:
                right = node.test.comparators[0]
                if isinstance(left, ast.Name) and left.id == "__name__" and isinstance(right, ast.Constant) and right.value == "__main__":
                    return True
                if isinstance(right, ast.Name) and right.id == "__name__" and isinstance(left, ast.Constant) and left.value == "__main__":
                    return True
        return False

    def _parse_type_annotation(self, node: Optional[ast.AST]) -> Optional[RustType]:
        if node is None:
            return None
        if isinstance(node, ast.Name):
            mapping = {
                "int": "i64",
                "float": "f64",
                "str": "String",
                "bool": "bool",
                "None": "()",
            }
            return RustType(mapping.get(node.id, node.id))
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                container = node.value.id
                if container in ("List", "list"):
                    inner = self._parse_type_annotation(node.slice) or RustType("unknown")
                    return RustType("Vec", type_args=[inner])
                elif container in ("Dict", "dict"):
                    if isinstance(node.slice, ast.Tuple) and len(node.slice.elts) >= 2:
                        k = self._parse_type_annotation(node.slice.elts[0]) or RustType("unknown")
                        v = self._parse_type_annotation(node.slice.elts[1]) or RustType("unknown")
                        return RustType("HashMap", type_args=[k, v])
                elif container in ("Tuple", "tuple"):
                    if isinstance(node.slice, ast.Tuple):
                        inners = [self._parse_type_annotation(elt) or RustType("unknown") for elt in node.slice.elts]
                        return RustType("tuple", type_args=inners)
        return RustType("unknown")

    def _parse_function(self, node: ast.FunctionDef) -> FunctionDef:
        params: List[Param] = []
        for arg in node.args.args:
            if arg.arg == "self":
                continue
            ann = self._parse_type_annotation(arg.annotation)
            params.append(Param(name=arg.arg, param_type=ann, line=arg.lineno, col=arg.col_offset))

        ret_type = self._parse_type_annotation(node.returns)
        body = [self._parse_stmt(s) for s in node.body]
        body = [s for s in body if s is not None]

        return FunctionDef(
            name=node.name,
            params=params,
            return_type=ret_type,
            body=body,
            line=node.lineno,
            col=node.col_offset
        )

    def _parse_class(self, node: ast.ClassDef) -> ClassDef:
        fields: List[ClassField] = []
        methods: List[FunctionDef] = []

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name == "__init__":
                    # Extract self.field assignments
                    for stmt in item.body:
                        if (isinstance(stmt, ast.Assign) and
                                len(stmt.targets) == 1 and
                                isinstance(stmt.targets[0], ast.Attribute) and
                                isinstance(stmt.targets[0].value, ast.Name) and
                                stmt.targets[0].value.id == "self"):
                            f_name = stmt.targets[0].attr
                            # If constructor parameter matches f_name, check if param has annotation
                            f_type = RustType("unknown")
                            for p in item.args.args:
                                if p.arg == f_name and p.annotation:
                                    f_type = self._parse_type_annotation(p.annotation) or RustType("unknown")
                            fields.append(ClassField(name=f_name, field_type=f_type))
                else:
                    methods.append(self._parse_function(item))

        return ClassDef(name=node.name, fields=fields, methods=methods, line=node.lineno, col=node.col_offset)

    def _parse_stmt(self, node: ast.AST) -> Optional[IRStmt]:
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Tuple):
                # Tuple unpacking assignment e.g. a, b = 0, 1 or a, b = b, a + b
                targets = [elt.id for elt in node.targets[0].elts if isinstance(elt, ast.Name)]
                if isinstance(node.value, ast.Tuple):
                    values = [self._parse_expr(v) for v in node.value.elts]
                else:
                    values = [self._parse_expr(node.value)]
                return TupleAssignStmt(targets=targets, values=values, line=node.lineno, col=node.col_offset)

            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                # We also support subscript assignment: x[0] = 5 or target.attr
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript):
                    # Represent as method or expression statement
                    target = self._parse_expr(node.targets[0].value)
                    idx = self._parse_expr(node.targets[0].slice)
                    val = self._parse_expr(node.value)
                    return ExprStmt(
                        expr=MethodCall(obj=target, method="_set_subscript", args=[idx, val]),
                        line=node.lineno,
                        col=node.col_offset
                    )
                self.warnings.append(f"Line {node.lineno}: Multi-assignment or complex target simplified")
                return None
            target_name = node.targets[0].id
            value_expr = self._parse_expr(node.value)
            return AssignStmt(
                target=target_name,
                value=value_expr,
                line=node.lineno,
                col=node.col_offset
            )
        elif isinstance(node, ast.Raise):
            msg = "Exception raised"
            if node.exc:
                if isinstance(node.exc, ast.Call) and node.exc.args:
                    first_arg = node.exc.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        msg = first_arg.value
                elif isinstance(node.exc, ast.Constant) and isinstance(node.exc.value, str):
                    msg = node.exc.value
            return ExprStmt(
                expr=Call(func="panic!", args=[Literal(value=msg, raw_text=f'"{msg}"')]),
                line=node.lineno,
                col=node.col_offset
            )
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                ann = self._parse_type_annotation(node.annotation)
                val = self._parse_expr(node.value) if node.value else None
                return AssignStmt(
                    target=node.target.id,
                    value=val,
                    inferred_type=ann,
                    line=node.lineno,
                    col=node.col_offset
                )
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                target_name = node.target.id
                op_map = {
                    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
                    ast.Mod: "%"
                }
                op = op_map.get(type(node.op), "+")
                rhs = self._parse_expr(node.value)
                return AssignStmt(
                    target=target_name,
                    value=BinaryOp(left=Variable(name=target_name), op=op, right=rhs),
                    is_declaration=False,
                    line=node.lineno,
                    col=node.col_offset
                )
        elif isinstance(node, ast.Expr):
            # Check for standalone string literal (docstring)
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return None
            return ExprStmt(expr=self._parse_expr(node.value), line=node.lineno, col=node.col_offset)
        elif isinstance(node, ast.Return):
            val = self._parse_expr(node.value) if node.value else None
            return ReturnStmt(value=val, line=node.lineno, col=node.col_offset)
        elif isinstance(node, ast.If):
            cond = self._parse_expr(node.test)
            then_body = [self._parse_stmt(s) for s in node.body]
            else_body = [self._parse_stmt(s) for s in node.orelse]
            return IfStmt(
                condition=cond,
                then_body=[s for s in then_body if s is not None],
                else_body=[s for s in else_body if s is not None],
                line=node.lineno,
                col=node.col_offset
            )
        elif isinstance(node, ast.While):
            cond = self._parse_expr(node.test)
            body = [self._parse_stmt(s) for s in node.body]
            return WhileStmt(
                condition=cond,
                body=[s for s in body if s is not None],
                line=node.lineno,
                col=node.col_offset
            )
        elif isinstance(node, ast.For):
            # Check for range(...)
            if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
                args = [self._parse_expr(a) for a in node.iter.args]
                var_name = node.target.id if isinstance(node.target, ast.Name) else "i"
                if len(args) == 1:
                    start_expr = Literal(value=0, raw_text="0")
                    end_expr = args[0]
                    step_expr = None
                elif len(args) == 2:
                    start_expr = args[0]
                    end_expr = args[1]
                    step_expr = None
                else:
                    start_expr = args[0]
                    end_expr = args[1]
                    step_expr = args[2]
                body = [self._parse_stmt(s) for s in node.body]
                return ForRangeStmt(
                    var=var_name,
                    start=start_expr,
                    end=end_expr,
                    step=step_expr,
                    body=[s for s in body if s is not None],
                    line=node.lineno,
                    col=node.col_offset
                )
            else:
                var_name = node.target.id if isinstance(node.target, ast.Name) else "item"
                iter_expr = self._parse_expr(node.iter)
                body = [self._parse_stmt(s) for s in node.body]
                return ForInStmt(
                    var=var_name,
                    iter_expr=iter_expr,
                    body=[s for s in body if s is not None],
                    line=node.lineno,
                    col=node.col_offset
                )
        elif isinstance(node, ast.Pass):
            return None

        self.warnings.append(f"Line {getattr(node, 'lineno', '?')}: Unhandled Python statement {type(node).__name__}")
        return None

    def _parse_expr(self, node: ast.AST) -> IRExpr:
        line = getattr(node, 'lineno', 1)
        col = getattr(node, 'col_offset', 0)

        if isinstance(node, ast.Constant):
            # Python 3.8+ handles int, float, str, bool, None as ast.Constant
            val = node.value
            raw = repr(val)
            if isinstance(val, bool):
                raw = "true" if val else "false"
            return Literal(value=val, raw_text=raw, line=line, col=col)
        elif isinstance(node, ast.Name):
            return Variable(name=node.id, line=line, col=col)
        elif isinstance(node, ast.BinOp):
            op_map = {
                ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
                ast.FloorDiv: "/", ast.Mod: "%", ast.Pow: "**"
            }
            op = op_map.get(type(node.op), "+")
            return BinaryOp(
                left=self._parse_expr(node.left),
                op=op,
                right=self._parse_expr(node.right),
                line=line,
                col=col
            )
        elif isinstance(node, ast.UnaryOp):
            op_map = {ast.USub: "-", ast.Not: "!"}
            op = op_map.get(type(node.op), "-")
            return UnaryOp(op=op, operand=self._parse_expr(node.operand), line=line, col=col)
        elif isinstance(node, ast.BoolOp):
            op = "&&" if isinstance(node.op, ast.And) else "||"
            # Chain binary ops for values
            res = self._parse_expr(node.values[0])
            for val in node.values[1:]:
                res = BinaryOp(left=res, op=op, right=self._parse_expr(val), line=line, col=col)
            return res
        elif isinstance(node, ast.Compare):
            op_map = {
                ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
                ast.Gt: ">", ast.GtE: ">="
            }
            # Simple single comparison
            op = op_map.get(type(node.ops[0]), "==")
            return BinaryOp(
                left=self._parse_expr(node.left),
                op=op,
                right=self._parse_expr(node.comparators[0]),
                line=line,
                col=col
            )
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                args = [self._parse_expr(a) for a in node.args]
                return Call(func=node.func.id, args=args, line=line, col=col)
            elif isinstance(node.func, ast.Attribute):
                obj = self._parse_expr(node.func.value)
                method_name = node.func.attr
                args = [self._parse_expr(a) for a in node.args]
                return MethodCall(obj=obj, method=method_name, args=args, line=line, col=col)
        elif isinstance(node, ast.Attribute):
            obj = self._parse_expr(node.value)
            return MethodCall(obj=obj, method=node.attr, args=[], line=line, col=col)
        elif isinstance(node, ast.Subscript):
            target = self._parse_expr(node.value)
            index = self._parse_expr(node.slice)
            return Subscript(target=target, index=index, line=line, col=col)
        elif isinstance(node, ast.List):
            elems = [self._parse_expr(e) for e in node.elts]
            return ListExpr(elements=elems, line=line, col=col)
        elif isinstance(node, ast.Dict):
            keys = [self._parse_expr(k) for k in node.keys if k is not None]
            values = [self._parse_expr(v) for v in node.values]
            return DictExpr(keys=keys, values=values, line=line, col=col)
        elif isinstance(node, ast.Tuple):
            elems = [self._parse_expr(e) for e in node.elts]
            return TupleExpr(elements=elems, line=line, col=col)
        elif isinstance(node, ast.ListComp):
            elt_expr = self._parse_expr(node.elt)
            if node.generators:
                gen = node.generators[0]
                var_name = gen.target.id if isinstance(gen.target, ast.Name) else "item"
                iter_expr = self._parse_expr(gen.iter)
                cond_expr = self._parse_expr(gen.ifs[0]) if gen.ifs else None
                return ListComp(elt=elt_expr, var=var_name, iter_expr=iter_expr, condition=cond_expr, line=line, col=col)
            return ListExpr(elements=[], line=line, col=col)

        self.warnings.append(f"Line {line}: Unhandled expression type {type(node).__name__}")
        return Literal(value=None, raw_text="/* unsupported expression */", line=line, col=col)
