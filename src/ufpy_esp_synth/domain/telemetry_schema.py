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

ATMA_TO_MPA = 0.101325
FIELD_NOMINAL_VOLTAGE_V = 400.0


def _series_or_nan(df: pd.DataFrame, column: str) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series([float("nan")] * len(df), index=df.index, dtype="float64")


def _telemetry_voltage(df: pd.DataFrame) -> pd.Series:
    if "u_surf_v" in df.columns and "motor_u_nom_lin_v" in df.columns:
        nominal = pd.to_numeric(df["motor_u_nom_lin_v"], errors="coerce")
        surface = pd.to_numeric(df["u_surf_v"], errors="coerce")
        safe_nominal = nominal.where(nominal > 0.0)
        return FIELD_NOMINAL_VOLTAGE_V * surface / safe_nominal

    if "motor_u_lin_v" in df.columns and "motor_u_nom_lin_v" in df.columns:
        nominal = pd.to_numeric(df["motor_u_nom_lin_v"], errors="coerce")
        motor_voltage = pd.to_numeric(df["motor_u_lin_v"], errors="coerce")
        safe_nominal = nominal.where(nominal > 0.0)
        return FIELD_NOMINAL_VOLTAGE_V * motor_voltage / safe_nominal

    return pd.to_numeric(_series_or_nan(df, "motor_u_lin_v"), errors="coerce")


def _telemetry_intake_pressure(df: pd.DataFrame) -> pd.Series:
    p_int_atma = pd.to_numeric(_series_or_nan(df, "p_int_atma"), errors="coerce")
    return p_int_atma * ATMA_TO_MPA


def _telemetry_load(df: pd.DataFrame) -> pd.Series:
    load_fraction = pd.to_numeric(_series_or_nan(df, "motor_load_d"), errors="coerce")
    return load_fraction * 100.0

def make_telemetry_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    telemetry = pd.DataFrame(
        {
            TELEMETRY_RUN_ID: _series_or_nan(df, "run_id").astype("Int64"),
            TELEMETRY_VALUE_DATE: pd.to_datetime(_series_or_nan(df, "value_date")),
            TELEMETRY_ACTIVE_POWER: pd.to_numeric(_series_or_nan(df, "motor_p_electr_kw"), errors="coerce"),
            TELEMETRY_VOLTAGE_IMBALANCE: _series_or_nan(df, "__missing_voltage_imbalance__"),
            TELEMETRY_CURRENT_IMBALANCE: _series_or_nan(df, "__missing_current_imbalance__"),
            TELEMETRY_LOAD: _telemetry_load(df),
            TELEMETRY_POWER_FACTOR: pd.to_numeric(_series_or_nan(df, "motor_cosphi"), errors="coerce"),
            TELEMETRY_VOLTAGE: _telemetry_voltage(df),
            TELEMETRY_INTAKE_PRESSURE: _telemetry_intake_pressure(df),
            TELEMETRY_INSULATION_RESISTANCE: _series_or_nan(df, "__missing_insulation_resistance__"),
            TELEMETRY_MOTOR_TEMPERATURE: _series_or_nan(df, "__missing_motor_temperature__"),
            TELEMETRY_CURRENT: pd.to_numeric(_series_or_nan(df, "motor_i_lin_a"), errors="coerce"),
        },
        columns=TELEMETRY_COLUMNS,
    )
    return telemetry
