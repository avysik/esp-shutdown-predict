from __future__ import annotations

from pathlib import Path


def artifact_dir(name: str) -> Path:
    path = Path(__file__).resolve().parents[1] / ".test_runs" / name
    path.mkdir(parents=True, exist_ok=True)
    return path
