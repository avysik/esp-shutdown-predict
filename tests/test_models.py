from __future__ import annotations

import pytest
from pydantic import ValidationError

from ufpy_esp_synth.config.models import TimeAxisConfig


def test_time_axis_normalizes_frequency_to_lowercase() -> None:
    cfg = TimeAxisConfig(time_step="1H", n_points=10)

    assert cfg.time_step == "1h"
    assert cfg.n_points == 10


@pytest.mark.parametrize(
    ("time_step", "n_points"),
    [
        ("", 10),
        ("1h", 0),
    ],
)
def test_time_axis_keeps_field_validation(time_step: str, n_points: int) -> None:
    with pytest.raises(ValidationError):
        TimeAxisConfig(time_step=time_step, n_points=n_points)
