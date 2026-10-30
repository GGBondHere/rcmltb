"""Load bot definitions without starting clients or Linux-only services."""

import ast
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]


def load_source(relative_path, names, namespace=None):
    module = ModuleType(relative_path)
    module.__dict__.update(namespace or {})
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    definitions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in names
    ]
    exec(compile(ast.Module(body=definitions, type_ignores=[]), relative_path, "exec"), module.__dict__)
    return module
