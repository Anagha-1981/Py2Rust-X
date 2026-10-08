"""Type Inference Module for Py2SafeRust-X.

Performs static type inference across IR nodes using literals, explicit annotations,
built-in returns, and local data-flow analysis. Surfaces warnings for uninferable types.
"""
from typing import Dict, List, Optional, Set
from .ir import (
    Program, FunctionDef, ClassDef, IRStmt, AssignStmt, ExprStmt, ReturnStmt,
    IfStmt, WhileStmt, ForRangeStmt, ForInStmt, TupleAssignStmt,
    IRExpr, Literal, Variable, BinaryOp, UnaryOp, Call, MethodCall, Subscript,
    ListExpr, DictExpr, TupleExpr, CloneExpr, ListComp, RustType
)


class TypeInferenceEngine:
    def __init__(self):
        self.warnings: List[str] = []
        self.global_env: Dict[str, RustType] = {}
        self.function_signatures: Dict[str, RustType] = {}

    def run(self, program: Program) -> List[str]:
        self.warnings.clear()
        self.global_env.clear()
        self.function_signatures.clear()

        # Pass 1: Infer classes and register constructor types
        for cls in program.classes:
            self._infer_class(cls)

        # Pre-populate known function return types
        for func in program.functions:
            if func.return_type and func.return_type.name != "unknown":
                self.function_signatures[func.name] = func.return_type

        # Pass 2: Infer top-level functions signatures and bodies
        for func in program.functions:
            self._infer_function(func, self.global_env)
            if func.return_type:
                self.function_signatures[func.name] = func.return_type

        # Pass 3: Infer top-level statements
        env: Dict[str, RustType] = dict(self.global_env)
        for stmt in program.statements:
            self._infer_stmt(stmt, env)

        return list(self.warnings)

    def _infer_class(self, cls: ClassDef) -> None:
        for field in cls.fields:
            if field.field_type.name == "unknown":
                self.warnings.append(
                    f"Class '{cls.name}' field '{field.name}' could not be inferred; defaulting to /* type: unknown */"
                )

    def _infer_function(self, func: FunctionDef, parent_env: Dict[str, RustType]) -> None:
        func_env: Dict[str, RustType] = dict(parent_env)

        # Parameter types
        for param in func.params:
            if param.param_type and param.param_type.name != "unknown":
                func_env[param.name] = param.param_type
            else:
                # Check if param type can be inferred from body usage
                inferred = self._guess_param_type_from_body(param.name, func.body)
                if inferred:
                    param.param_type = inferred
                    func_env[param.name] = inferred
                else:
                    param.param_type = RustType("unknown")
                    func_env[param.name] = param.param_type
                    self.warnings.append(
                        f"Function '{func.name}' parameter '{param.name}' type unknown; falling back to /* type: unknown */"
                    )

        # Infer statements in body
        return_types: List[RustType] = []
        for stmt in func.body:
            self._infer_stmt(stmt, func_env, return_types)

        # Infer return type if not explicitly set
        if not func.return_type or func.return_type.name in ("unknown", "()"):
            if return_types:
                # Take first non-unknown return type
                valid_ret = next((r for r in return_types if r.name != "unknown"), return_types[0])
                func.return_type = valid_ret
            else:
                func.return_type = RustType("void")

    def _guess_param_type_from_body(self, param_name: str, body: List[IRStmt]) -> Optional[RustType]:
        for stmt in body:
            if isinstance(stmt, ExprStmt):
                if isinstance(stmt.expr, MethodCall) and isinstance(stmt.expr.obj, Variable) and stmt.expr.obj.name == param_name:
                    if stmt.expr.method == "append":
                        elem_type = self._infer_expr_type(stmt.expr.args[0], {}) if stmt.expr.args else RustType("i64")
                        return RustType("Vec", type_args=[elem_type])
            elif isinstance(stmt, ForInStmt):
                if isinstance(stmt.iter_expr, Variable) and stmt.iter_expr.name == param_name:
                    return RustType("Vec", type_args=[RustType("i64")])
                nested = self._guess_param_type_from_body(param_name, stmt.body)
                if nested: return nested
            elif isinstance(stmt, ForRangeStmt):
                if (isinstance(stmt.end, Variable) and stmt.end.name == param_name) or (isinstance(stmt.start, Variable) and stmt.start.name == param_name):
                    return RustType("i64")
                nested = self._guess_param_type_from_body(param_name, stmt.body)
                if nested: return nested
            elif isinstance(stmt, IfStmt):
                if isinstance(stmt.condition, BinaryOp):
                    if (isinstance(stmt.condition.left, Variable) and stmt.condition.left.name == param_name) or \
                       (isinstance(stmt.condition.right, Variable) and stmt.condition.right.name == param_name):
                        return RustType("i64")
                nested = self._guess_param_type_from_body(param_name, stmt.then_body) or self._guess_param_type_from_body(param_name, stmt.else_body)
                if nested: return nested
            elif isinstance(stmt, WhileStmt):
                if isinstance(stmt.condition, BinaryOp):
                    if (isinstance(stmt.condition.left, Variable) and stmt.condition.left.name == param_name) or \
                       (isinstance(stmt.condition.right, Variable) and stmt.condition.right.name == param_name):
                        return RustType("i64")
                nested = self._guess_param_type_from_body(param_name, stmt.body)
                if nested: return nested
        return None

    def _infer_stmt(self, stmt: IRStmt, env: Dict[str, RustType], return_types: Optional[List[RustType]] = None) -> None:
        if isinstance(stmt, AssignStmt):
            if stmt.inferred_type and stmt.inferred_type.name != "unknown":
                val_type = stmt.inferred_type
            else:
                val_type = self._infer_expr_type(stmt.value, env)
                stmt.inferred_type = val_type

            if val_type.name == "unknown":
                self.warnings.append(
                    f"Line {stmt.line}: Variable '{stmt.target}' type unknown; falling back to /* type: unknown */"
                )

            env[stmt.target] = val_type

        elif isinstance(stmt, TupleAssignStmt):
            for target, val in zip(stmt.targets, stmt.values):
                val_t = self._infer_expr_type(val, env)
                env[target] = val_t

        elif isinstance(stmt, ExprStmt):
            self._infer_expr_type(stmt.expr, env)

        elif isinstance(stmt, ReturnStmt):
            if stmt.value:
                ret_t = self._infer_expr_type(stmt.value, env)
                if return_types is not None:
                    return_types.append(ret_t)
            else:
                if return_types is not None:
                    return_types.append(RustType("void"))

        elif isinstance(stmt, IfStmt):
            self._infer_expr_type(stmt.condition, env)
            then_env = dict(env)
            for s in stmt.then_body:
                self._infer_stmt(s, then_env, return_types)
            else_env = dict(env)
            for s in stmt.else_body:
                self._infer_stmt(s, else_env, return_types)

        elif isinstance(stmt, WhileStmt):
            self._infer_expr_type(stmt.condition, env)
            loop_env = dict(env)
            for s in stmt.body:
                self._infer_stmt(s, loop_env, return_types)

        elif isinstance(stmt, ForRangeStmt):
            env[stmt.var] = RustType("i64")
            self._infer_expr_type(stmt.start, env)
            self._infer_expr_type(stmt.end, env)
            if stmt.step:
                self._infer_expr_type(stmt.step, env)
            loop_env = dict(env)
            for s in stmt.body:
                self._infer_stmt(s, loop_env, return_types)

        elif isinstance(stmt, ForInStmt):
            iter_t = self._infer_expr_type(stmt.iter_expr, env)
            elem_t = iter_t.type_args[0] if (iter_t.name == "Vec" and iter_t.type_args) else RustType("i64")
            env[stmt.var] = elem_t
            loop_env = dict(env)
            for s in stmt.body:
                self._infer_stmt(s, loop_env, return_types)

    def _infer_expr_type(self, expr: Optional[IRExpr], env: Dict[str, RustType]) -> RustType:
        if expr is None:
            return RustType("void")

        if isinstance(expr, Literal):
            if isinstance(expr.value, bool):
                t = RustType("bool")
            elif isinstance(expr.value, int):
                t = RustType("i64")
            elif isinstance(expr.value, float):
                t = RustType("f64")
            elif isinstance(expr.value, str):
                t = RustType("String")
            elif expr.value is None:
                t = RustType("void")
            else:
                t = RustType("unknown")
            expr.inferred_type = t
            return t

        elif isinstance(expr, Variable):
            t = env.get(expr.name, RustType("unknown"))
            expr.inferred_type = t
            return t

        elif isinstance(expr, CloneExpr):
            inner_t = self._infer_expr_type(expr.inner, env)
            expr.inferred_type = inner_t
            return inner_t

        elif isinstance(expr, BinaryOp):
            lt = self._infer_expr_type(expr.left, env)
            rt = self._infer_expr_type(expr.right, env)
            if expr.op in ("==", "!=", "<", "<=", ">", ">=", "&&", "||"):
                t = RustType("bool")
            elif expr.op in ("+", "-", "*", "%"):
                t = lt if lt.name != "unknown" else rt
            elif expr.op == "/":
                t = RustType("f64")
            else:
                t = lt if lt.name != "unknown" else RustType("i64")
            expr.inferred_type = t
            return t

        elif isinstance(expr, UnaryOp):
            if expr.op == "!":
                t = RustType("bool")
            else:
                t = self._infer_expr_type(expr.operand, env)
            expr.inferred_type = t
            return t

        elif isinstance(expr, ListExpr):
            if expr.elements:
                elem_t = self._infer_expr_type(expr.elements[0], env)
                for e in expr.elements[1:]:
                    self._infer_expr_type(e, env)
                t = RustType("Vec", type_args=[elem_t])
            else:
                t = RustType("Vec", type_args=[RustType("i64")])
            expr.inferred_type = t
            return t

        elif isinstance(expr, DictExpr):
            k_t = self._infer_expr_type(expr.keys[0], env) if expr.keys else RustType("String")
            v_t = self._infer_expr_type(expr.values[0], env) if expr.values else RustType("i64")
            for k, v in zip(expr.keys, expr.values):
                self._infer_expr_type(k, env)
                self._infer_expr_type(v, env)
            t = RustType("HashMap", type_args=[k_t, v_t])
            expr.inferred_type = t
            return t

        elif isinstance(expr, TupleExpr):
            inners = [self._infer_expr_type(e, env) for e in expr.elements]
            t = RustType("tuple", type_args=inners)
            expr.inferred_type = t
            return t

        elif isinstance(expr, ListComp):
            local_env = dict(env)
            iter_t = self._infer_expr_type(expr.iter_expr, env)
            elem_t = iter_t.type_args[0] if (iter_t.name == "Vec" and iter_t.type_args) else RustType("i64")
            local_env[expr.var] = elem_t
            elt_t = self._infer_expr_type(expr.elt, local_env)
            t = RustType("Vec", type_args=[elt_t])
            expr.inferred_type = t
            return t

        elif isinstance(expr, Subscript):
            target_t = self._infer_expr_type(expr.target, env)
            self._infer_expr_type(expr.index, env)
            if target_t.name == "Vec" and target_t.type_args:
                t = target_t.type_args[0]
            elif target_t.name == "HashMap" and len(target_t.type_args) > 1:
                t = target_t.type_args[1]
            elif target_t.name == "String":
                t = RustType("char")
            else:
                t = RustType("unknown")
            expr.inferred_type = t
            return t

        elif isinstance(expr, Call):
            for a in expr.args:
                self._infer_expr_type(a, env)
            if expr.func == "len":
                t = RustType("i64")
            elif expr.func in ("print", "println"):
                t = RustType("void")
            elif expr.func == "range":
                t = RustType("Vec", type_args=[RustType("i64")])
            elif expr.func == "int":
                t = RustType("i64")
            elif expr.func == "float":
                t = RustType("f64")
            elif expr.func == "str":
                t = RustType("String")
            elif expr.func in self.function_signatures:
                t = self.function_signatures[expr.func]
            else:
                t = RustType("unknown")
            expr.inferred_type = t
            return t

        elif isinstance(expr, MethodCall):
            obj_t = self._infer_expr_type(expr.obj, env)
            for a in expr.args:
                self._infer_expr_type(a, env)
            if expr.method == "append":
                t = RustType("void")
            elif expr.method == "clone":
                t = obj_t
            else:
                t = RustType("unknown")
            expr.inferred_type = t
            return t

        t = RustType("unknown")
        expr.inferred_type = t
        return t
