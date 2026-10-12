"""Static pre-flight checks for generated Python. Defense in depth: the container is the real boundary.

Rejects imports outside an allowlist, dynamic code execution, dunder attribute access (the usual
route to escaping restricted namespaces), and pandas/numpy/matplotlib methods that touch files or URLs.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

ALLOWED_MODULES = {
    "pandas", "numpy", "scipy", "sklearn", "matplotlib", "statsmodels", "math", "statistics", "datetime",
    "json", "re", "collections", "itertools", "functools", "decimal", "fractions", "random", "typing",
    "dataclasses", "string", "textwrap", "operator", "calendar", "warnings", "heapq", "bisect",
}
FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "__import__", "open", "input", "breakpoint", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "exit", "quit", "help", "memoryview", "license", "credits",
}
FORBIDDEN_ATTRIBUTES = {
    "system", "popen", "spawn", "fork", "environ", "getenv", "load", "loads", "save", "savez", "savez_compressed",
    "loadtxt", "savetxt", "genfromtxt", "fromfile", "tofile", "memmap", "savefig", "imread", "imsave",
    "read_sql", "read_sql_query", "read_sql_table", "read_html", "read_clipboard", "to_clipboard", "read_pickle",
    "to_pickle", "read_csv", "read_excel", "read_json", "read_parquet", "read_feather", "read_orc", "read_xml",
    "read_hdf", "read_stata", "read_sas", "read_spss", "read_fwf", "read_table", "read_gbq", "to_csv", "to_excel",
    "to_json", "to_parquet", "to_feather", "to_hdf", "to_sql", "to_stata", "to_orc", "to_xml", "to_gbq",
    "to_latex", "to_html", "dump", "dumps_to_file", "urlopen",
}


@dataclass
class StaticCheckResult:
    ok: bool
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "violations": self.violations}


class _Checker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    def _flag(self, node: ast.AST, message: str) -> None:
        self.violations.append(f"line {getattr(node, 'lineno', '?')}: {message}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in ALLOWED_MODULES:
                self._flag(node, f"import of '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").split(".")[0]
        if node.level or root not in ALLOWED_MODULES:
            self._flag(node, f"import from '{node.module}' is not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            self._flag(node, f"call to '{node.func.id}()' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__") and node.id not in {"__name__"}:
            self._flag(node, f"use of '{node.id}' is not allowed")
        if node.id in {"__builtins__", "builtins"}:
            self._flag(node, "access to builtins is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__") or node.attr.startswith("_abc") or node.attr in {"f_globals", "f_locals",
                                                                                        "gi_frame", "tb_frame",
                                                                                        "co_code", "func_globals"}:
            self._flag(node, f"access to attribute '{node.attr}' is not allowed")
        elif node.attr in FORBIDDEN_ATTRIBUTES:
            self._flag(node, f"'.{node.attr}' (file, network or process access) is not allowed; "
                             "use the provided dataframes and assign the answer to `result`")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and ("__" in node.value and any(
                k in node.value for k in ("__class__", "__subclasses__", "__globals__", "__builtins__",
                                          "__import__", "__mro__", "__bases__"))):
            self._flag(node, "suspicious dunder string literal")
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self._flag(node, "'global' statements are not allowed")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._flag(node, "async code is not allowed")


def check_code(code: str, max_chars: int = 20_000) -> StaticCheckResult:
    if not code or not code.strip():
        return StaticCheckResult(False, ["code is empty"])
    if len(code) > max_chars:
        return StaticCheckResult(False, [f"code exceeds {max_chars} characters"])
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return StaticCheckResult(False, [f"line {exc.lineno}: syntax error: {exc.msg}"])
    checker = _Checker()
    checker.visit(tree)
    assigns_result = any(
        isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign)
        and any(isinstance(t, ast.Name) and t.id == "result"
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]))
        for node in ast.walk(tree)
    )
    if not assigns_result:
        checker.violations.append("the code must assign its final answer to a variable named `result`")
    return StaticCheckResult(not checker.violations, checker.violations)
