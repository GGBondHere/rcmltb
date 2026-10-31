"""Load bot definitions without starting clients or Linux-only services."""

import ast
from functools import lru_cache, partial
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def get_i18n():
    spec = spec_from_file_location("rcmltb_i18n", ROOT / "bot/i18n/__init__.py",
                                  submodule_search_locations=[str(ROOT / "bot/i18n")])
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def translation_namespace():
    i18n = get_i18n()
    return {
        "tr": partial(i18n.tr, _language="en"), "raw": i18n.raw,
        "ui_error": lambda detail: i18n.tr("common.technical_error", detail=str(detail), _language="en"),
        "display_status": i18n.display_status, "status_locale": i18n.status_locale,
        "locale_context": i18n.locale_context, "get_language": i18n.get_language,
        "task_locale": i18n.task_locale,
        "error_detail": i18n.error_detail,
    }


def load_source(relative_path, names, namespace=None):
    module = ModuleType(relative_path)
    module.__dict__.update(translation_namespace())
    module.__dict__.update(namespace or {})
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    definitions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name in names
    ]
    exec(compile(ast.Module(body=definitions, type_ignores=[]), relative_path, "exec"), module.__dict__)
    return module
