"""Intermediate Representation (IR) for Py2SafeRust-X.

Defines a clean dataclass-based AST representing Python semantics
mapped toward Rust constructs prior to code emission.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict


@dataclass
class RustType:
    name: str  # e.g. "i64", "f64", "String", "bool", "Vec", "HashMap", "void", "unknown"
    type_args: List['RustType'] = field(default_factory=list)
    is_ref: bool = False
    is_mut: bool = False

    def to_rust_str(self) -> str:
        prefix = ""
        if self.is_ref:
            prefix = "&mut " if self.is_mut else "&"

        if self.name == "unknown":
            return f"{prefix}/* type: unknown */"
        if self.name in ("void", "None", "()"):
            return "()"
        if self.name == "Vec":
            inner = self.type_args[0].to_rust_str() if self.type_args else "/* type: unknown */"
            return f"{prefix}Vec<{inner}>"
        if self.name == "HashMap":
            k = self.type_args[0].to_rust_str() if len(self.type_args) > 0 else "/* type: unknown */"
            v = self.type_args[1].to_rust_str() if len(self.type_args) > 1 else "/* type: unknown */"
            return f"{prefix}std::collections::HashMap<{k}, {v}>"
        if self.name == "tuple":
            inners = ", ".join(t.to_rust_str() for t in self.type_args)
            return f"{prefix}({inners})"

        return f"{prefix}{self.name}"

    @property
    def is_copy_type(self) -> bool:
        """Primitive integer, float, and bool types implement Copy in Rust."""
        return self.name in {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64", "bool"}


# Base AST Node
@dataclass
class IRNode:
    line: int = 1
    col: int = 0


# Expressions
@dataclass
class IRExpr(IRNode):
    inferred_type: Optional[RustType] = None


@dataclass
class Literal(IRExpr):
    value: Any = None
    raw_text: str = ""


@dataclass
class Variable(IRExpr):
    name: str = ""


@dataclass
class BinaryOp(IRExpr):
    left: IRExpr = field(default_factory=IRExpr)
    op: str = "+"  # +, -, *, /, %, ==, !=, <, <=, >, >=, and, or
    right: IRExpr = field(default_factory=IRExpr)


@dataclass
class UnaryOp(IRExpr):
    op: str = "-"  # -, not
    operand: IRExpr = field(default_factory=IRExpr)


@dataclass
class Call(IRExpr):
    func: str = ""  # e.g., "print", "len", "range", or custom function name
    args: List[IRExpr] = field(default_factory=list)


@dataclass
class MethodCall(IRExpr):
    obj: IRExpr = field(default_factory=IRExpr)
    method: str = ""
    args: List[IRExpr] = field(default_factory=list)


@dataclass
class Subscript(IRExpr):
    target: IRExpr = field(default_factory=IRExpr)
    index: IRExpr = field(default_factory=IRExpr)


@dataclass
class ListExpr(IRExpr):
    elements: List[IRExpr] = field(default_factory=list)


@dataclass
class DictExpr(IRExpr):
    keys: List[IRExpr] = field(default_factory=list)
    values: List[IRExpr] = field(default_factory=list)


@dataclass
class TupleExpr(IRExpr):
    elements: List[IRExpr] = field(default_factory=list)


@dataclass
class CloneExpr(IRExpr):
    inner: IRExpr = field(default_factory=IRExpr)


@dataclass
class ListComp(IRExpr):
    elt: IRExpr = field(default_factory=IRExpr)
    var: str = "i"
    iter_expr: IRExpr = field(default_factory=IRExpr)
    condition: Optional[IRExpr] = None


# Statements
@dataclass
class IRStmt(IRNode):
    pass


@dataclass
class TupleAssignStmt(IRStmt):
    targets: List[str] = field(default_factory=list)
    values: List[IRExpr] = field(default_factory=list)
    is_declaration: bool = True


@dataclass
class AssignStmt(IRStmt):
    target: str = ""
    value: IRExpr = field(default_factory=IRExpr)
    is_declaration: bool = True
    is_mut: bool = False
    inferred_type: Optional[RustType] = None


@dataclass
class ExprStmt(IRStmt):
    expr: IRExpr = field(default_factory=IRExpr)


@dataclass
class ReturnStmt(IRStmt):
    value: Optional[IRExpr] = None


@dataclass
class IfStmt(IRStmt):
    condition: IRExpr = field(default_factory=IRExpr)
    then_body: List[IRStmt] = field(default_factory=list)
    else_body: List[IRStmt] = field(default_factory=list)


@dataclass
class WhileStmt(IRStmt):
    condition: IRExpr = field(default_factory=IRExpr)
    body: List[IRStmt] = field(default_factory=list)


@dataclass
class ForRangeStmt(IRStmt):
    var: str = "i"
    start: IRExpr = field(default_factory=IRExpr)
    end: IRExpr = field(default_factory=IRExpr)
    step: Optional[IRExpr] = None
    body: List[IRStmt] = field(default_factory=list)


@dataclass
class ForInStmt(IRStmt):
    var: str = "item"
    iter_expr: IRExpr = field(default_factory=IRExpr)
    body: List[IRStmt] = field(default_factory=list)


@dataclass
class Param(IRNode):
    name: str = ""
    param_type: Optional[RustType] = None
    is_mut: bool = False


@dataclass
class FunctionDef(IRStmt):
    name: str = ""
    params: List[Param] = field(default_factory=list)
    return_type: Optional[RustType] = None
    body: List[IRStmt] = field(default_factory=list)


@dataclass
class ClassField:
    name: str
    field_type: RustType


@dataclass
class ClassDef(IRStmt):
    name: str = ""
    fields: List[ClassField] = field(default_factory=list)
    methods: List[FunctionDef] = field(default_factory=list)


@dataclass
class Program(IRNode):
    statements: List[IRStmt] = field(default_factory=list)
    functions: List[FunctionDef] = field(default_factory=list)
    classes: List[ClassDef] = field(default_factory=list)
