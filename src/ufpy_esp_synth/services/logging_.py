from __future__ import annotations

import logging
import sys
from typing import Optional


def configure_logging(level: str = "INFO", stream: Optional[object] = None) -> None:
    """
    Configure root logger for CLI runs.
    Deterministic: no timestamps are injected into data artifacts (only console logs).
    """
    root = logging.getLogger()
    root.handlers.clear()

    lvl = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(lvl)

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setLevel(lvl)

    fmt = logging.Formatter(
        fmt="%(levelname)s %(processName)s %(name)s - %(message)s"
    )
    handler.setFormatter(fmt)

    root.addHandler(handler)
