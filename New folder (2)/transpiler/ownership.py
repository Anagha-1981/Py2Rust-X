"""Ownership and Borrowing Analysis for Py2SafeRust-X.

Implements static ownership tracking, alias detection, and mutability analysis.
Identifies move operations on non-Copy types (Vec, HashMap, String) and transforms
aliases into explicit `.clone()` calls whenever the source variable is accessed later
in the scope, preventing E0382 'borrow of moved value' errors.
Also infers whether variables require `let mut` declarations (preventing E0384).
"""
from typing import Dict, List, Set, Tuple, Optional
from .ir import (
    Program, FunctionDef, IRStmt, AssignStmt, ExprStmt, ReturnStmt,
    IfStmt, WhileStmt, ForRangeStmt, ForInStmt, TupleAssignStmt,
    IRExpr, Literal, Variable, BinaryOp, UnaryOp, Call, MethodCall,
    Subscript, ListExpr, DictExpr, TupleExpr, CloneExpr, ListComp, RustType
)


class OwnershipAnalyzer:
    def __init__(self):
        self.clones_inserted: List[Tuple[str, int]] = []  # (var_name, line)
        self.mutables_marked: Set[str] = set()

    def run(self, program: Program) -> None:
        self.clones_inserted.clear()
        self.mutables_marked.clear()

        # Analyze each function body
        for func in program.functions:
            self._analyze_scope(func.body)

        # Analyze top-level program statements
        self._analyze_scope(program.statements)

    def _analyze_scope(self, statements: List[IRStmt]) -> None:
        # Step 1: Detect mutability (reassignments or mutating calls like .append)
        assigned_counts: Dict[str, int] = {}
        mutated_vars: Set[str] = set()

        for stmt in statements:
            self._find_mutations(stmt, assigned_counts, mutated_vars)

        # Mark AssignStmt declarations as is_mut if reassigned or mutated
        for stmt in statements:
            if isinstance(stmt, AssignStmt):
                if assigned_counts.get(stmt.target, 0) > 1 or stmt.target in mutated_vars:
                    stmt.is_mut = True
                    self.mutables_marked.add(stmt.target)

        # Step 2: Liveness & Alias analysis for Move vs Clone
        # Scan forward: if stmt is `y = x` where x is a non-Copy variable,
        # inspect if `x` is read in any subsequent statements.
        for i, stmt in enumerate(statements):
            if isinstance(stmt, AssignStmt):
                rhs = stmt.value
                # Direct aliasing: y = x
                if isinstance(rhs, Variable):
                    source_var = rhs.name
                    # Check if source_var type is non-Copy (or assumed non-Copy if unknown/Vec/HashMap/String)
                    is_non_copy = True
                    if rhs.inferred_type and rhs.inferred_type.is_copy_type:
                        is_non_copy = False

                    if is_non_copy:
                        # Check if source_var is read anywhere in statements[i+1:]
                        if self._is_var_read_in_subsequent(source_var, statements[i+1:]):
                            # Replace rhs with CloneExpr
                            stmt.value = CloneExpr(inner=Variable(name=source_var, line=rhs.line, col=rhs.col))
                            self.clones_inserted.append((source_var, stmt.line))

            # Recurse into nested blocks (if, while, for)
            if isinstance(stmt, IfStmt):
                self._analyze_scope(stmt.then_body)
                self._analyze_scope(stmt.else_body)
            elif isinstance(stmt, WhileStmt):
                self._analyze_scope(stmt.body)
            elif isinstance(stmt, ForRangeStmt):
                self._analyze_scope(stmt.body)
            elif isinstance(stmt, ForInStmt):
                self._analyze_scope(stmt.body)

    def _find_mutations(self, stmt: IRStmt, assigned_counts: Dict[str, int], mutated_vars: Set[str]) -> None:
        if isinstance(stmt, AssignStmt):
            assigned_counts[stmt.target] = assigned_counts.get(stmt.target, 0) + 1
        elif isinstance(stmt, TupleAssignStmt):
            for t in stmt.targets:
                assigned_counts[t] = assigned_counts.get(t, 0) + 1
        elif isinstance(stmt, ExprStmt):
            if isinstance(stmt.expr, MethodCall):
                # Mutating methods like append, insert, remove, clear, push
                if stmt.expr.method in ("append", "push", "insert", "remove", "clear", "_set_subscript"):
                    if isinstance(stmt.expr.obj, Variable):
                        mutated_vars.add(stmt.expr.obj.name)
        elif isinstance(stmt, IfStmt):
            for s in stmt.then_body:
                self._find_mutations(s, assigned_counts, mutated_vars)
            for s in stmt.else_body:
                self._find_mutations(s, assigned_counts, mutated_vars)
        elif isinstance(stmt, WhileStmt):
            for s in stmt.body:
                self._find_mutations(s, assigned_counts, mutated_vars)
        elif isinstance(stmt, ForRangeStmt):
            for s in stmt.body:
                self._find_mutations(s, assigned_counts, mutated_vars)
        elif isinstance(stmt, ForInStmt):
            for s in stmt.body:
                self._find_mutations(s, assigned_counts, mutated_vars)

    def _is_var_read_in_subsequent(self, var_name: str, stmts: List[IRStmt]) -> bool:
        for stmt in stmts:
            if self._is_var_read_in_stmt(var_name, stmt):
                return True
        return False

    def _is_var_read_in_stmt(self, var_name: str, stmt: IRStmt) -> bool:
        if isinstance(stmt, AssignStmt):
            # Target is being written, but rhs is being read
            if self._is_var_read_in_expr(var_name, stmt.value):
                return True
            return False
        elif isinstance(stmt, ExprStmt):
            return self._is_var_read_in_expr(var_name, stmt.expr)
        elif isinstance(stmt, ReturnStmt):
            return self._is_var_read_in_expr(var_name, stmt.value) if stmt.value else False
        elif isinstance(stmt, IfStmt):
            if self._is_var_read_in_expr(var_name, stmt.condition):
                return True
            if any(self._is_var_read_in_stmt(var_name, s) for s in stmt.then_body):
                return True
            if any(self._is_var_read_in_stmt(var_name, s) for s in stmt.else_body):
                return True
        elif isinstance(stmt, WhileStmt):
            if self._is_var_read_in_expr(var_name, stmt.condition):
                return True
            if any(self._is_var_read_in_stmt(var_name, s) for s in stmt.body):
                return True
        elif isinstance(stmt, ForRangeStmt):
            if (self._is_var_read_in_expr(var_name, stmt.start) or
                    self._is_var_read_in_expr(var_name, stmt.end) or
                    (stmt.step and self._is_var_read_in_expr(var_name, stmt.step))):
                return True
            if any(self._is_var_read_in_stmt(var_name, s) for s in stmt.body):
                return True
        elif isinstance(stmt, ForInStmt):
            if self._is_var_read_in_expr(var_name, stmt.iter_expr):
                return True
            if any(self._is_var_read_in_stmt(var_name, s) for s in stmt.body):
                return True
        elif isinstance(stmt, TupleAssignStmt):
            return any(self._is_var_read_in_expr(var_name, val) for val in stmt.values)
        return False

    def _is_var_read_in_expr(self, var_name: str, expr: Optional[IRExpr]) -> bool:
        if expr is None:
            return False
        if isinstance(expr, Variable):
            return expr.name == var_name
        elif isinstance(expr, CloneExpr):
            return self._is_var_read_in_expr(var_name, expr.inner)
        elif isinstance(expr, BinaryOp):
            return self._is_var_read_in_expr(var_name, expr.left) or self._is_var_read_in_expr(var_name, expr.right)
        elif isinstance(expr, UnaryOp):
            return self._is_var_read_in_expr(var_name, expr.operand)
        elif isinstance(expr, Call):
            return any(self._is_var_read_in_expr(var_name, arg) for arg in expr.args)
        elif isinstance(expr, MethodCall):
            if self._is_var_read_in_expr(var_name, expr.obj):
                return True
            return any(self._is_var_read_in_expr(var_name, arg) for arg in expr.args)
        elif isinstance(expr, Subscript):
            return self._is_var_read_in_expr(var_name, expr.target) or self._is_var_read_in_expr(var_name, expr.index)
        elif isinstance(expr, ListExpr):
            return any(self._is_var_read_in_expr(var_name, elem) for elem in expr.elements)
        elif isinstance(expr, DictExpr):
            return any(self._is_var_read_in_expr(var_name, k) for k in expr.keys) or any(self._is_var_read_in_expr(var_name, v) for v in expr.values)
        elif isinstance(expr, TupleExpr):
            return any(self._is_var_read_in_expr(var_name, elem) for elem in expr.elements)
        elif isinstance(expr, ListComp):
            return self._is_var_read_in_expr(var_name, expr.iter_expr) or \
                   (expr.var != var_name and self._is_var_read_in_expr(var_name, expr.elt))
        return False
