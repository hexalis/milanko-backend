"""Enforce the package boundaries: api -> core, processor -> core, never api <-> processor."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def python_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)


class BoundaryTest(unittest.TestCase):
    def test_api_does_not_import_processor(self) -> None:
        for path in python_files(ROOT / "api"):
            modules = imported_modules(path)
            offenders = {name for name in modules if name == "processor" or name.startswith("processor.")}
            self.assertFalse(offenders, f"{path} imports {offenders}")

    def test_processor_does_not_import_api(self) -> None:
        for path in python_files(ROOT / "processor"):
            modules = imported_modules(path)
            offenders = {name for name in modules if name == "api" or name.startswith("api.")}
            self.assertFalse(offenders, f"{path} imports {offenders}")

    def test_core_does_not_import_api_or_processor(self) -> None:
        for path in python_files(ROOT / "core"):
            modules = imported_modules(path)
            offenders = {
                name
                for name in modules
                if name in {"api", "processor"}
                or name.startswith("api.")
                or name.startswith("processor.")
            }
            self.assertFalse(offenders, f"{path} imports {offenders}")


if __name__ == "__main__":
    unittest.main()
