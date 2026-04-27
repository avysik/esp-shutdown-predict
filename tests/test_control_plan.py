from __future__ import annotations

from pathlib import Path

import pandas as pd

from ufpy_esp_synth.domain.control_plan import (
    ControlRule,
    RuleAction,
    TimeStepControl,
    apply_post_rules,
    apply_pre_rules,
    build_time_controls,
    load_control_plan,
)


def test_control_plan_applies_overrides_shutdown_and_restart() -> None:
    plan_path = Path(__file__).resolve().parents[1] / "examples" / "control_plan_shutdown.json"
    plan = load_control_plan(plan_path)

    idx = pd.DatetimeIndex(
        [
            pd.Timestamp("2020-01-01 00:00:00"),
            pd.Timestamp("2020-01-04 14:46:00"),
            pd.Timestamp("2020-01-04 14:47:00"),
            pd.Timestamp("2020-01-04 15:00:00"),
            pd.Timestamp("2020-01-04 23:59:00"),
            pd.Timestamp("2020-01-05 00:00:00"),
        ]
    )

    controls = build_time_controls(
        idx=idx,
        q_default_series=[60.0] * len(idx),
        q_base_value=82.0,
        p_int_atma=120.0,
        t_int_C=60.0,
        pump_freq_hz=50.0,
        u_surf_v=1000.0,
        control_plan=plan,
    )

    assert controls[0].is_running is True
    assert controls[0].q_liq_sm3day == 82.0
    assert controls[0].control_label == "stable"

    assert controls[2].is_running is True
    assert controls[2].p_int_atma == 240.0
    assert controls[2].control_label == "overpressure"

    assert controls[3].is_running is False
    assert controls[3].q_liq_sm3day == 0.0
    assert controls[3].pump_freq_hz == 0.0
    assert controls[3].control_reason == "protection_trip"

    assert controls[5].is_running is True
    assert controls[5].q_liq_sm3day == 76.0
    assert controls[5].p_int_atma == 118.0
    assert controls[5].control_label == "restart"


def test_pre_rule_triggers_immediate_shutdown() -> None:
    rule = ControlRule(
        name="trip_on_high_intake_pressure",
        stage="pre",
        metric="p_int_atma",
        op=">=",
        value=200.0,
        action=RuleAction(kind="shutdown", duration="10min", reason="auto_trip"),
    )
    control = TimeStepControl(
        q_liq_sm3day=82.0,
        p_int_atma=240.0,
        t_int_C=60.0,
        pump_freq_hz=50.0,
        u_surf_v=1000.0,
        is_running=True,
        control_label="overpressure",
        control_reason="intake_overpressure",
    )

    effective, active_actions, trigger_counts = apply_pre_rules(
        planned_control=control,
        ts=pd.Timestamp("2020-01-01 14:47:00"),
        rules=[rule],
        active_actions=[],
        trigger_counts={},
        sample_step=pd.Timedelta(minutes=1),
    )

    assert effective.is_running is False
    assert effective.q_liq_sm3day == 0.0
    assert effective.pump_freq_hz == 0.0
    assert effective.control_reason == "auto_trip"
    assert len(active_actions) == 1
    assert trigger_counts["trip_on_high_intake_pressure"] == 1


def test_post_rule_schedules_shutdown_from_next_point() -> None:
    rule = ControlRule(
        name="trip_on_motor_overcurrent",
        stage="post",
        metric="motor_i_lin_a",
        op=">=",
        value=25.0,
        action=RuleAction(kind="shutdown", duration="5min", reason="auto_trip_overcurrent"),
    )
    control = TimeStepControl(
        q_liq_sm3day=82.0,
        p_int_atma=120.0,
        t_int_C=60.0,
        pump_freq_hz=50.0,
        u_surf_v=1000.0,
        is_running=True,
        control_label="stable",
        control_reason="normal_operation",
    )
    row = {"motor_i_lin_a": 30.0}

    active_actions, trigger_counts = apply_post_rules(
        control=control,
        row=row,
        ts=pd.Timestamp("2020-01-01 10:00:00"),
        rules=[rule],
        active_actions=[],
        trigger_counts={},
        sample_step=pd.Timedelta(minutes=1),
    )

    assert len(active_actions) == 1
    assert active_actions[0].start_ts == pd.Timestamp("2020-01-01 10:01:00")
    assert trigger_counts["trip_on_motor_overcurrent"] == 1

    next_control, _, _ = apply_pre_rules(
        planned_control=control,
        ts=pd.Timestamp("2020-01-01 10:01:00"),
        rules=[],
        active_actions=active_actions,
        trigger_counts=trigger_counts,
        sample_step=pd.Timedelta(minutes=1),
    )

    assert next_control.is_running is False
    assert next_control.control_reason == "auto_trip_overcurrent"
