from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ufpy_esp_synth.domain.labels import display_label, metric_slug


DEFAULT_METRICS = [
    "q_liq_sm3day",
    "head_m",
    "p_dis_atma",
    "motor_i_lin_a",
]
EXCLUDED_AUTO_METRICS = {
    "run_id",
    "window_numb",
}

DEFAULT_TIME_COLUMNS = ["value_date", "ValueDate"]


def _available_metrics(
    df: pd.DataFrame,
    metrics: Sequence[str] | None,
    *,
    varying_only: bool,
) -> list[str]:
    if metrics is None:
        requested = list(DEFAULT_METRICS)
    elif len(metrics) == 0:
        requested = [
            column
            for column in df.columns
            if column not in EXCLUDED_AUTO_METRICS and pd.api.types.is_numeric_dtype(df[column])
        ]
    else:
        requested = list(metrics)

    available = [metric for metric in requested if metric in df.columns]
    if varying_only:
        available = [metric for metric in available if df[metric].nunique(dropna=False) > 1]
    return available


def _window_groups(
    df: pd.DataFrame,
    *,
    points_per_window: int,
    window_column: str,
) -> list[tuple[str, pd.DataFrame]]:
    if window_column in df.columns and df[window_column].astype(str).str.len().gt(0).any():
        groups: list[tuple[str, pd.DataFrame]] = []
        for label, group in df.groupby(window_column, sort=False):
            groups.append((str(label), group.reset_index(drop=True)))
    else:
        groups = []
        for i in range(0, len(df), points_per_window):
            chunk = df.iloc[i : i + points_per_window].reset_index(drop=True)
            if not chunk.empty:
                groups.append((f"window_{i // points_per_window:04d}", chunk))

    bad = [label for label, group in groups if len(group) != points_per_window]
    if bad:
        raise ValueError(
            f"Expected exactly {points_per_window} points in each window, got mismatches for: {', '.join(bad)}"
        )
    return groups


def _resolve_time_column(df: pd.DataFrame, time_column: str | None) -> str:
    if time_column is not None:
        if time_column not in df.columns:
            raise ValueError(f"Time column {time_column!r} is not present in the DataFrame.")
        return time_column

    for candidate in DEFAULT_TIME_COLUMNS:
        if candidate in df.columns:
            return candidate
    raise ValueError(f"Could not find a time column. Tried: {', '.join(DEFAULT_TIME_COLUMNS)}")


def _metric_output_path(output_png: Path, metric: str, metric_index: int) -> Path:
    stem = output_png.stem
    suffix = output_png.suffix or ".png"
    safe_metric = re.sub(r"\W+", "_", metric_slug(metric), flags=re.UNICODE).strip("_")
    if not safe_metric:
        safe_metric = f"metric_{metric_index:02d}"
    return output_png.with_name(f"{stem}__{metric_index:02d}__{safe_metric}{suffix}")


def _plot_full_series(ax, data: pd.DataFrame, metric: str, time_column: str) -> None:
    axis_label = display_label(metric)
    ax.plot(
        data["_plot_time"],
        data[metric],
        marker="o",
        linewidth=1.8,
        markersize=5.5,
    )
    ax.set_xlabel(display_label(time_column))
    ax.set_title(axis_label)


def _plot_windowed_series(ax, groups: list[tuple[str, pd.DataFrame]], metric: str) -> None:
    axis_label = display_label(metric)
    for label, group in groups:
        minutes = (group["_plot_time"] - group["_plot_time"].iloc[0]).dt.total_seconds() / 60.0
        ax.plot(
            minutes,
            group[metric],
            marker="o",
            linewidth=1.8,
            markersize=5.5,
            label=label,
        )
    ax.set_xlabel("Minutes Since Window Start")
    ax.set_title(axis_label)


def _save_metric_plot(
    data: pd.DataFrame,
    *,
    metric: str,
    output_png: Path,
    full_series: bool,
    time_column: str,
    groups: list[tuple[str, pd.DataFrame]] | None,
) -> Path:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    if full_series:
        _plot_full_series(ax, data, metric, time_column)
    else:
        if groups is None:
            raise ValueError("Window groups are required for windowed plotting.")
        _plot_windowed_series(ax, groups, metric)
        ax.legend(loc="best", fontsize=8, title="Window")
    ax.set_ylabel(display_label(metric))
    ax.grid(True, alpha=0.35)
    fig.tight_layout()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=160)
    plt.close(fig)
    return output_png


def plot_windows(
    df: pd.DataFrame,
    *,
    output_png: Path,
    points_per_window: int = 9,
    metrics: Sequence[str] | None = None,
    window_column: str = "control_label",
    window_label: str | None = None,
    varying_only: bool = False,
    time_column: str | None = None,
    full_series: bool = False,
    split_metrics: bool = False,
    keep_combined: bool = False,
) -> Path:
    data = df.copy()
    resolved_time_column = _resolve_time_column(data, time_column)
    data["_plot_time"] = pd.to_datetime(data[resolved_time_column])
    data = data.sort_values("_plot_time").reset_index(drop=True)
    if window_label is not None:
        data = data[data[window_column].astype(str) == window_label].reset_index(drop=True)
        if data.empty:
            raise ValueError(f"No rows found for {window_column}={window_label!r}.")
    metrics_to_plot = _available_metrics(data, metrics, varying_only=varying_only)
    if not metrics_to_plot:
        raise ValueError("No requested varying metrics are present in the DataFrame.")
    groups = None if full_series else _window_groups(data, points_per_window=points_per_window, window_column=window_column)

    if split_metrics:
        for metric_index, metric in enumerate(metrics_to_plot, start=1):
            metric_output = output_png if len(metrics_to_plot) == 1 else _metric_output_path(output_png, metric, metric_index)
            _save_metric_plot(
                data,
                metric=metric,
                output_png=metric_output,
                full_series=full_series,
                time_column=resolved_time_column,
                groups=groups,
            )
        if not keep_combined:
            return output_png

    fig, axes = plt.subplots(len(metrics_to_plot), 1, figsize=(10, 3.2 * len(metrics_to_plot)), sharex=not full_series)
    if len(metrics_to_plot) == 1:
        axes = [axes]

    for ax, metric in zip(axes, metrics_to_plot):
        if full_series:
            _plot_full_series(ax, data, metric, resolved_time_column)
        else:
            if groups is None:
                raise ValueError("Window groups are required for windowed plotting.")
            _plot_windowed_series(ax, groups, metric)
        ax.set_ylabel(display_label(metric))
        ax.grid(True, alpha=0.35)

    if full_series:
        axes[-1].set_xlabel(display_label(resolved_time_column))
        fig.suptitle("ESP Performance Overview", fontsize=12)
    else:
        axes[-1].set_xlabel("Minutes Since Window Start")
        axes[0].legend(loc="best", fontsize=8, title="Window")
        fig.suptitle(f"ESP Window Analysis: {points_per_window} samples per window", fontsize=12)
    fig.tight_layout()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=160)
    plt.close(fig)
    return output_png


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export ESP performance charts from parquet datasets.")
    parser.add_argument("--input-parquet", required=True, type=Path, help="Input parquet path.")
    parser.add_argument("--output-png", required=True, type=Path, help="Output PNG path.")
    parser.add_argument("--points-per-window", type=int, default=9, help="Expected points in each logical window.")
    parser.add_argument(
        "--time-column",
        type=str,
        default=None,
        help="Optional time column. If omitted, auto-detects value_date or ValueDate.",
    )
    parser.add_argument(
        "--window-column",
        type=str,
        default="control_label",
        help="Column used to identify logical windows. Falls back to fixed-size row chunks.",
    )
    parser.add_argument(
        "--window-label",
        type=str,
        default=None,
        help="Optional single window identifier to plot.",
    )
    parser.add_argument(
        "--metrics",
        nargs="*",
        default=None,
        help="Optional metric list. Omit to use default demo metrics. Pass without values to auto-pick all numeric metrics.",
    )
    parser.add_argument(
        "--varying-only",
        action="store_true",
        help="Plot only metrics that change within the selected data slice.",
    )
    parser.add_argument(
        "--full-series",
        action="store_true",
        help="Plot one continuous series instead of overlaying separate window traces.",
    )
    parser.add_argument(
        "--split-metrics",
        action="store_true",
        help="Save one PNG per metric instead of a single multi-panel figure.",
    )
    parser.add_argument(
        "--keep-combined",
        action="store_true",
        help="When used with --split-metrics, also keep the combined multi-panel PNG.",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    df = pd.read_parquet(args.input_parquet)
    output = plot_windows(
        df,
        output_png=args.output_png,
        points_per_window=args.points_per_window,
        metrics=args.metrics,
        window_column=args.window_column,
        window_label=args.window_label,
        varying_only=args.varying_only,
        time_column=args.time_column,
        full_series=args.full_series,
        split_metrics=args.split_metrics,
        keep_combined=args.keep_combined,
    )
    print(output)


if __name__ == "__main__":
    main()
