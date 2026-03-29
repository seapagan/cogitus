"""Guardrails around the small set of allowed raw-SQL modules."""

from __future__ import annotations

import ast
from pathlib import Path

ALLOWED_RAW_SQL_PATHS = {
    Path("src/cogitus/db/__init__.py"),
    Path("src/cogitus/search/backend.py"),
    Path("tests/test_db.py"),
    Path("tests/test_search_index.py"),
}


def test_raw_sql_usage_stays_within_allowlist() -> None:
    """Raw execute/executemany calls should stay in approved modules only."""
    repo_root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []

    for pattern in ("src/**/*.py", "tests/**/*.py"):
        for path in sorted(repo_root.glob(pattern)):
            relative_path = path.relative_to(repo_root)
            if relative_path in ALLOWED_RAW_SQL_PATHS:
                continue

            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in {"execute", "executemany"}:
                    continue
                offenders.append(
                    f"{relative_path}:{node.lineno}:{node.col_offset + 1}"
                )

    assert offenders == []
