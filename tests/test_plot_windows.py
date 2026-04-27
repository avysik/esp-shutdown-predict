from __future__ import annotations

import pandas as pd

from ufpy_esp_synth.domain.labels import (
    TELEMETRY_ACTIVE_POWER,
    TELEMETRY_CURRENT,
    TELEMETRY_CURRENT_IMBALANCE,
    TELEMETRY_INTAKE_PRESSURE,
    TELEMETRY_INSULATION_RESISTANCE,
    TELEMETRY_LOAD,
    TELEMETRY_MOTOR_TEMPERATURE,
    TELEMETRY_POWER_FACTOR,
    TELEMETRY_RUN_ID,
    TELEMETRY_VALUE_DATE,
    TELEMETRY_VOLTAGE,
    TELEMETRY_VOLTAGE_IMBALANCE,
)
from ufpy_esp_synth.plot_windows import _available_metrics, plot_windows
from tests.helpers import artifact_dir


def _clear_pngs(out_dir, pattern: str) -> None:
    for path in out_dir.glob(pattern):
        path.unlink()


def _telemetry_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            TELEMETRY_VALUE_DATE: pd.date_range("2020-01-01", periods=18, freq="15min"),
            TELEMETRY_RUN_ID: [0] * 18,
            TELEMETRY_ACTIVE_POWER: [20, 21, 22, 23, 24, 25, 26, 27, 28, 18, 19, 20, 21, 22, 23, 24, 25, 26],
            TELEMETRY_VOLTAGE_IMBALANCE: [float("nan")] * 18,
            TELEMETRY_CURRENT_IMBALANCE: [float("nan")] * 18,
            TELEMETRY_LOAD: [0.50, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58, 0.45, 0.46, 0.47, 0.48, 0.49, 0.50, 0.51, 0.52, 0.53],
            TELEMETRY_POWER_FACTOR: [0.80, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86, 0.87, 0.88, 0.75, 0.76, 0.77, 0.78, 0.79, 0.80, 0.81, 0.82, 0.83],
            TELEMETRY_VOLTAGE: [1000] * 18,
            TELEMETRY_INTAKE_PRESSURE: [120] * 18,
            TELEMETRY_INSULATION_RESISTANCE: [float("nan")] * 18,
            TELEMETRY_MOTOR_TEMPERATURE: [float("nan")] * 18,
            TELEMETRY_CURRENT: [10, 10.2, 10.4, 10.6, 10.8, 11.0, 11.2, 11.4, 11.6, 9.5, 9.7, 9.9, 10.1, 10.3, 10.5, 10.7, 10.9, 11.1],
        }
    )


def test_plot_windows_exports_png() -> None:
    out_dir = artifact_dir("plot_windows")
    output_png = out_dir / "demo.png"

    df = pd.DataFrame(
        {
            "value_date": pd.date_range("2020-01-01", periods=18, freq="15min"),
            "control_label": ["window_0000"] * 9 + ["window_0001"] * 9,
            "q_liq_sm3day": [80, 81, 82, 83, 84, 85, 86, 87, 88, 70, 71, 72, 73, 74, 75, 76, 77, 78],
            "head_m": [300, 301, 303, 305, 306, 307, 308, 309, 310, 250, 252, 253, 255, 257, 258, 260, 262, 264],
            "p_dis_atma": [140, 141, 141.5, 142, 143, 143.5, 144, 144.5, 145, 130, 131, 131.5, 132, 133, 133.5, 134, 134.5, 135],
            "motor_i_lin_a": [10, 10.1, 10.2, 10.4, 10.5, 10.6, 10.8, 10.9, 11.0, 9.5, 9.6, 9.7, 9.8, 10.0, 10.1, 10.2, 10.3, 10.4],
        }
    )

    result = plot_windows(df, output_png=output_png, points_per_window=9)

    assert result.exists()
    assert result.stat().st_size > 0


def test_available_metrics_can_auto_pick_only_varying_numeric_columns() -> None:
    df = pd.DataFrame(
        {
            "value_date": pd.date_range("2020-01-01", periods=9, freq="15min"),
            "control_label": ["window_0000"] * 9,
            "run_id": [0] * 9,
            "q_liq_sm3day": [80, 81, 82, 83, 84, 85, 86, 87, 88],
            "head_m": [300] * 9,
            "p_dis_atma": [140, 141, 141.5, 142, 143, 143.5, 144, 144.5, 145],
            "mode": ["a"] * 9,
        }
    )

    metrics = _available_metrics(df, [], varying_only=True)

    assert metrics == ["q_liq_sm3day", "p_dis_atma"]


def test_plot_windows_supports_telemetry_dataframe_shape() -> None:
    out_dir = artifact_dir("plot_windows_telemetry")
    output_png = out_dir / "telemetry.png"

    result = plot_windows(
        _telemetry_df(),
        output_png=output_png,
        points_per_window=9,
        metrics=[],
        varying_only=True,
    )

    assert result.exists()
    assert result.stat().st_size > 0


def test_plot_windows_can_export_full_series_one_metric_per_png() -> None:
    out_dir = artifact_dir("plot_windows_full_series")
    output_png = out_dir / "telemetry_full_series.png"
    _clear_pngs(out_dir, "telemetry_full_series__*.png")

    result = plot_windows(
        _telemetry_df(),
        output_png=output_png,
        metrics=[],
        varying_only=True,
        full_series=True,
        split_metrics=True,
    )

    created = sorted(out_dir.glob("telemetry_full_series__*.png"))
    assert result == output_png
    assert len(created) == 4
    assert all(path.stat().st_size > 0 for path in created)


def test_plot_windows_can_keep_combined_and_split_outputs() -> None:
    out_dir = artifact_dir("plot_windows_full_series_combined")
    output_png = out_dir / "telemetry_full_series_combined.png"
    _clear_pngs(out_dir, "telemetry_full_series_combined__*.png")
    if output_png.exists():
        output_png.unlink()

    result = plot_windows(
        _telemetry_df(),
        output_png=output_png,
        metrics=[],
        varying_only=True,
        full_series=True,
        split_metrics=True,
        keep_combined=True,
    )

    created = sorted(out_dir.glob("telemetry_full_series_combined__*.png"))
    assert result == output_png
    assert output_png.exists()
    assert output_png.stat().st_size > 0
    assert len(created) == 4
    assert all(path.stat().st_size > 0 for path in created)
