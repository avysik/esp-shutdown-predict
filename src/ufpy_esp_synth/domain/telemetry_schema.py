from __future__ import annotations

import pandas as pd

from ufpy_esp_synth.domain.labels import (
    TELEMETRY_ACTIVE_POWER,
    TELEMETRY_COLUMNS,
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


def _series_or_nan(df: pd.DataFrame, column: str) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series([float("nan")] * len(df), index=df.index, dtype="float64")

def make_telemetry_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    telemetry = pd.DataFrame(
        {
            TELEMETRY_RUN_ID: _series_or_nan(df, "run_id").astype("Int64"),
            TELEMETRY_VALUE_DATE: pd.to_datetime(_series_or_nan(df, "value_date")),
            TELEMETRY_ACTIVE_POWER: pd.to_numeric(_series_or_nan(df, "motor_p_electr_kw"), errors="coerce"),
            TELEMETRY_VOLTAGE_IMBALANCE: _series_or_nan(df, "__missing_voltage_imbalance__"),
            TELEMETRY_CURRENT_IMBALANCE: _series_or_nan(df, "__missing_current_imbalance__"),
            TELEMETRY_LOAD: pd.to_numeric(_series_or_nan(df, "motor_load_d"), errors="coerce"),
            TELEMETRY_POWER_FACTOR: pd.to_numeric(_series_or_nan(df, "motor_cosphi"), errors="coerce"),
            TELEMETRY_VOLTAGE: pd.to_numeric(_series_or_nan(df, "motor_u_lin_v"), errors="coerce"),
            TELEMETRY_INTAKE_PRESSURE: pd.to_numeric(_series_or_nan(df, "p_int_atma"), errors="coerce"),
            TELEMETRY_INSULATION_RESISTANCE: _series_or_nan(df, "__missing_insulation_resistance__"),
            TELEMETRY_MOTOR_TEMPERATURE: _series_or_nan(df, "__missing_motor_temperature__"),
            TELEMETRY_CURRENT: pd.to_numeric(_series_or_nan(df, "motor_i_lin_a"), errors="coerce"),
        },
        columns=TELEMETRY_COLUMNS,
    )
    return telemetry
