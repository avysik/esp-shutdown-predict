from __future__ import annotations

import re


TELEMETRY_RUN_ID = "run_id"
TELEMETRY_VALUE_DATE = "ValueDate"
TELEMETRY_ACTIVE_POWER = "Активная мощность"
TELEMETRY_VOLTAGE_IMBALANCE = "Дисбаланс напряжений"
TELEMETRY_CURRENT_IMBALANCE = "Дисбаланс токов"
TELEMETRY_LOAD = "Загрузка"
TELEMETRY_POWER_FACTOR = "Коэффиц.мощности"
TELEMETRY_VOLTAGE = "Напряжение"
TELEMETRY_INTAKE_PRESSURE = "Р на приеме насоса"
TELEMETRY_INSULATION_RESISTANCE = "Сопротив.изоляции"
TELEMETRY_MOTOR_TEMPERATURE = "Температура двигателя"
TELEMETRY_CURRENT = "Ток"


TELEMETRY_COLUMNS = [
    TELEMETRY_RUN_ID,
    TELEMETRY_VALUE_DATE,
    TELEMETRY_ACTIVE_POWER,
    TELEMETRY_VOLTAGE_IMBALANCE,
    TELEMETRY_CURRENT_IMBALANCE,
    TELEMETRY_LOAD,
    TELEMETRY_POWER_FACTOR,
    TELEMETRY_VOLTAGE,
    TELEMETRY_INTAKE_PRESSURE,
    TELEMETRY_INSULATION_RESISTANCE,
    TELEMETRY_MOTOR_TEMPERATURE,
    TELEMETRY_CURRENT,
]


DISPLAY_LABELS = {
    "run_id": "Run ID",
    "value_date": "Timestamp",
    "ValueDate": "Timestamp",
    "control_label": "Window Label",
    "q_liq_sm3day": "Liquid Rate, sm3/day",
    "head_m": "Pump Head, m",
    "p_dis_atma": "Pump Discharge Pressure, atma",
    "p_int_atma": "Pump Intake Pressure, atma",
    "motor_i_lin_a": "Motor Line Current, A",
    "motor_u_lin_v": "Motor Line Voltage, V",
    "motor_p_electr_kw": "Motor Active Power, kW",
    "motor_load_d": "Motor Load, fraction",
    "motor_cosphi": "Motor Power Factor",
    TELEMETRY_ACTIVE_POWER: "Motor Active Power, kW",
    TELEMETRY_VOLTAGE_IMBALANCE: "Voltage Imbalance",
    TELEMETRY_CURRENT_IMBALANCE: "Current Imbalance",
    TELEMETRY_LOAD: "Motor Load, fraction",
    TELEMETRY_POWER_FACTOR: "Motor Power Factor",
    TELEMETRY_VOLTAGE: "Voltage, V",
    TELEMETRY_INTAKE_PRESSURE: "Pump Intake Pressure, atma",
    TELEMETRY_INSULATION_RESISTANCE: "Insulation Resistance",
    TELEMETRY_MOTOR_TEMPERATURE: "Motor Temperature",
    TELEMETRY_CURRENT: "Current, A",
}


SLUG_LABELS = {
    "q_liq_sm3day": "liquid_rate_sm3day",
    "head_m": "pump_head_m",
    "p_dis_atma": "pump_discharge_pressure_atma",
    "p_int_atma": "pump_intake_pressure_atma",
    "motor_i_lin_a": "motor_line_current_a",
    "motor_u_lin_v": "motor_line_voltage_v",
    "motor_p_electr_kw": "motor_active_power_kw",
    "motor_load_d": "motor_load_fraction",
    "motor_cosphi": "motor_power_factor",
    TELEMETRY_ACTIVE_POWER: "motor_active_power_kw",
    TELEMETRY_VOLTAGE_IMBALANCE: "voltage_imbalance",
    TELEMETRY_CURRENT_IMBALANCE: "current_imbalance",
    TELEMETRY_LOAD: "motor_load_fraction",
    TELEMETRY_POWER_FACTOR: "motor_power_factor",
    TELEMETRY_VOLTAGE: "voltage_v",
    TELEMETRY_INTAKE_PRESSURE: "pump_intake_pressure_atma",
    TELEMETRY_INSULATION_RESISTANCE: "insulation_resistance",
    TELEMETRY_MOTOR_TEMPERATURE: "motor_temperature",
    TELEMETRY_CURRENT: "current_a",
}


def display_label(column: str) -> str:
    if column in DISPLAY_LABELS:
        return DISPLAY_LABELS[column]
    return column.replace("_", " ").strip().title()


def metric_slug(column: str) -> str:
    if column in SLUG_LABELS:
        return SLUG_LABELS[column]
    label = display_label(column).lower()
    safe = re.sub(r"[^a-z0-9]+", "_", label)
    safe = safe.strip("_")
    return safe or "metric"
