from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_IMPORTS = {
    "random",
    "faker",
}
FORBIDDEN_PREFIXES = {
    "numpy.random",
}


def _iter_py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if p.is_file()]


def test_no_forbidden_imports_in_source() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src" / "ufpy_esp_synth"
    py_files = _iter_py_files(src_root)

    offenders: list[str] = []

    for f in py_files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    name = a.name
                    if name in FORBIDDEN_IMPORTS:
                        offenders.append(f"{f}: import {name}")
                    for pref in FORBIDDEN_PREFIXES:
                        if name.startswith(pref):
                            offenders.append(f"{f}: import {name}")
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in FORBIDDEN_IMPORTS:
                    offenders.append(f"{f}: from {mod} import ...")
                for pref in FORBIDDEN_PREFIXES:
                    if mod.startswith(pref):
                        offenders.append(f"{f}: from {mod} import ...")

    assert offenders == []
