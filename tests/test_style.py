"""House rules from CLAUDE.md that a machine can check."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKED = [ROOT / "src", ROOT / "scripts", ROOT / "spike"]


def python_files():
    for base in CHECKED:
        yield from (p for p in base.rglob("*.py") if "_build" not in p.parts)


def is_stub(fn: ast.FunctionDef) -> bool:
    body = fn.body[0]
    return len(fn.body) == 1 and isinstance(body, ast.Expr) and isinstance(body.value, ast.Constant) \
        and body.value.value is ...


def test_every_function_has_a_purpose_tag():
    missing = []
    for path in python_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for node in ast.walk(ast.parse("\n".join(lines))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or is_stub(node):
                continue
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            if not lines[first - 2].strip().startswith("# PURPOSE:"):
                missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}")
    assert missing == []


def test_purpose_tags_are_capitalized():
    lowercase = [
        f"{path.relative_to(ROOT)}:{n}"
        for path in python_files()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for tag in ("# PURPOSE:", "# RENAME:")
        if tag in line and line.split(tag, 1)[1] != line.split(tag, 1)[1].upper()
    ]
    assert lowercase == []
