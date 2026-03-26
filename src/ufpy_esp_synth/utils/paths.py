from __future__ import annotations

from pathlib import Path


def make_output_path(output_dir: Path, scenario: str, esp_id: str, run_id: int) -> Path:
    # Deterministic file naming
    name = f"{scenario}__esp_{esp_id}__run_{run_id:05d}.parquet"
    return Path(output_dir) / name
