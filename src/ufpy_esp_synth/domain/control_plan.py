from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field, model_validator


class ControlOverride(BaseModel):
    label: Optional[str] = None
    reason: Optional[str] = None
    running: Optional[bool] = None
    q_liq_sm3day: Optional[float] = Field(None, ge=0)
    p_int_atma: Optional[float] = None
    t_int_C: Optional[float] = None
    pump_freq_hz: Optional[float] = Field(None, ge=0)
    u_surf_v: Optional[float] = Field(None, ge=0)
    p_res_atma: Optional[float] = Field(None, ge=0)
    productivity_index: Optional[float] = Field(None, gt=0)
    q_test_sm3day: Optional[float] = Field(None, ge=0)
    p_test_atma: Optional[float] = Field(None, ge=0)
    p_wh_atma: Optional[float] = Field(None, ge=0)
    p_cas_atma: Optional[float] = Field(None, ge=0)
    t_wf_C: Optional[float] = None
    rp_m3m3: Optional[float] = Field(None, ge=0)
    muob_cP: Optional[float] = Field(None, gt=0)
    fw_fr: Optional[float] = Field(None, ge=0, le=1)
    fw_perc: Optional[float] = Field(None, ge=0, le=100)
    q_gas_free_sm3day: Optional[float] = Field(None, ge=0)

    @model_validator(mode="after")
    def _validate_fw_override(self) -> "ControlOverride":
        if self.fw_fr is not None and self.fw_perc is not None:
            raise ValueError("Specify only one of fw_fr or fw_perc in control overrides.")
        return self


class ControlSegment(ControlOverride):
    start: str
    end: str


class ControlEvent(ControlOverride):
    at: str
    duration: str = "0min"
    kind: Literal["override", "shutdown"] = "override"

    def to_override(self) -> ControlOverride:
        data = self.model_dump(exclude={"at", "duration", "kind"}, exclude_none=True)

        if self.kind == "shutdown":
            data.setdefault("label", "shutdown")
            data.setdefault("running", False)
            data.setdefault("q_liq_sm3day", 0.0)
            data.setdefault("pump_freq_hz", 0.0)
            data.setdefault("u_surf_v", 0.0)
        return ControlOverride.model_validate(data)


class ControlPlan(BaseModel):
    base: Optional[ControlOverride] = None
    segments: list[ControlSegment] = Field(default_factory=list)
    events: list[ControlEvent] = Field(default_factory=list)
    rules: list["ControlRule"] = Field(default_factory=list)


class RuleAction(ControlOverride):
    kind: Literal["override", "shutdown"] = "shutdown"
    duration: str = "0min"

    def to_override(self) -> ControlOverride:
        data = self.model_dump(exclude={"kind", "duration"}, exclude_none=True)

        if self.kind == "shutdown":
            data.setdefault("label", "shutdown")
            data.setdefault("running", False)
            data.setdefault("q_liq_sm3day", 0.0)
            data.setdefault("pump_freq_hz", 0.0)
            data.setdefault("u_surf_v", 0.0)
        return ControlOverride.model_validate(data)


class ControlRule(BaseModel):
    name: str
    stage: Literal["pre", "post"] = "pre"
    metric: str
    op: Literal[">", ">=", "<", "<=", "==", "!="]
    value: float | int | str | bool
    max_triggers: Optional[int] = 1
    action: RuleAction


@dataclass(frozen=True)
class TimeStepControl:
    q_liq_sm3day: float
    p_int_atma: float
    t_int_C: float
    pump_freq_hz: float
    u_surf_v: Optional[float]
    is_running: bool
    control_label: str
    control_reason: str
    p_res_atma: Optional[float] = None
    productivity_index: Optional[float] = None
    q_test_sm3day: Optional[float] = None
    p_test_atma: Optional[float] = None
    p_wh_atma: Optional[float] = None
    p_cas_atma: Optional[float] = None
    t_wf_C: Optional[float] = None
    rp_m3m3: Optional[float] = None
    muob_cP: Optional[float] = None
    fw_fr: Optional[float] = None
    q_gas_free_sm3day: Optional[float] = None


@dataclass(frozen=True)
class ActiveRuleAction:
    rule_name: str
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    override: ControlOverride


def load_control_plan(path: Optional[Path]) -> Optional[ControlPlan]:
    if path is None:
        return None

    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return ControlPlan.model_validate(payload)


def _normalize_timedelta_expr(expr: str) -> str:
    # pandas deprecates lowercase "d"; keep JSON syntax user-friendly while
    # converting to the canonical unit before parsing.
    return re.sub(r"(?<=\d)d(?=\d|\b)", "D", expr)


def _resolve_time_expr(expr: str, start_ts: pd.Timestamp) -> pd.Timestamp:
    try:
        return start_ts + pd.to_timedelta(_normalize_timedelta_expr(expr))
    except (TypeError, ValueError):
        return pd.Timestamp(expr)


def _resolve_duration(expr: str) -> pd.Timedelta:
    try:
        duration = pd.to_timedelta(_normalize_timedelta_expr(expr))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid control duration: {expr!r}") from exc

    if duration < pd.Timedelta(0):
        raise ValueError(f"Control duration must be non-negative: {expr!r}")
    return duration


def _apply_override(state: TimeStepControl, override: ControlOverride) -> TimeStepControl:
    if override.fw_fr is not None:
        fw_fr = float(override.fw_fr)
    elif override.fw_perc is not None:
        fw_fr = float(override.fw_perc) / 100.0
    else:
        fw_fr = state.fw_fr

    return TimeStepControl(
        q_liq_sm3day=state.q_liq_sm3day if override.q_liq_sm3day is None else float(override.q_liq_sm3day),
        p_int_atma=state.p_int_atma if override.p_int_atma is None else float(override.p_int_atma),
        t_int_C=state.t_int_C if override.t_int_C is None else float(override.t_int_C),
        pump_freq_hz=state.pump_freq_hz if override.pump_freq_hz is None else float(override.pump_freq_hz),
        u_surf_v=state.u_surf_v if override.u_surf_v is None else float(override.u_surf_v),
        p_res_atma=state.p_res_atma if override.p_res_atma is None else float(override.p_res_atma),
        productivity_index=state.productivity_index if override.productivity_index is None else float(override.productivity_index),
        q_test_sm3day=state.q_test_sm3day if override.q_test_sm3day is None else float(override.q_test_sm3day),
        p_test_atma=state.p_test_atma if override.p_test_atma is None else float(override.p_test_atma),
        p_wh_atma=state.p_wh_atma if override.p_wh_atma is None else float(override.p_wh_atma),
        p_cas_atma=state.p_cas_atma if override.p_cas_atma is None else float(override.p_cas_atma),
        t_wf_C=state.t_wf_C if override.t_wf_C is None else float(override.t_wf_C),
        rp_m3m3=state.rp_m3m3 if override.rp_m3m3 is None else float(override.rp_m3m3),
        muob_cP=state.muob_cP if override.muob_cP is None else float(override.muob_cP),
        fw_fr=fw_fr,
        q_gas_free_sm3day=state.q_gas_free_sm3day if override.q_gas_free_sm3day is None else float(override.q_gas_free_sm3day),
        is_running=state.is_running if override.running is None else bool(override.running),
        control_label=state.control_label if override.label is None else str(override.label),
        control_reason=state.control_reason if override.reason is None else str(override.reason),
    )


def _compare_rule_values(lhs: Any, op: str, rhs: Any) -> bool:
    if op == ">":
        return lhs > rhs
    if op == ">=":
        return lhs >= rhs
    if op == "<":
        return lhs < rhs
    if op == "<=":
        return lhs <= rhs
    if op == "==":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    raise ValueError(f"Unsupported rule operator: {op}")


def _apply_active_rule_actions(
    control: TimeStepControl,
    ts: pd.Timestamp,
    active_actions: list[ActiveRuleAction],
) -> TimeStepControl:
    effective = control
    for action in active_actions:
        if action.start_ts <= ts < action.end_ts:
            effective = _apply_override(effective, action.override)
    return effective


def _build_rule_context(control: TimeStepControl, row: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    context = {
        "q_liq_sm3day": control.q_liq_sm3day,
        "p_int_atma": control.p_int_atma,
        "t_int_C": control.t_int_C,
        "t_int_c": control.t_int_C,
        "pump_freq_hz": control.pump_freq_hz,
        "u_surf_v": control.u_surf_v,
        "p_res_atma": control.p_res_atma,
        "productivity_index": control.productivity_index,
        "q_test_sm3day": control.q_test_sm3day,
        "p_test_atma": control.p_test_atma,
        "p_wh_atma": control.p_wh_atma,
        "p_cas_atma": control.p_cas_atma,
        "t_wf_C": control.t_wf_C,
        "rp_m3m3": control.rp_m3m3,
        "muob_cP": control.muob_cP,
        "muob_cp": control.muob_cP,
        "fw_fr": control.fw_fr,
        "fw_perc": None if control.fw_fr is None else control.fw_fr * 100.0,
        "q_gas_free_sm3day": control.q_gas_free_sm3day,
        "is_running": control.is_running,
        "control_label": control.control_label,
        "control_reason": control.control_reason,
    }
    if row is not None:
        context.update(row)
    return context


def evaluate_rule(rule: ControlRule, context: dict[str, Any]) -> bool:
    if rule.metric not in context:
        raise ValueError(f"Rule {rule.name!r} references unknown metric: {rule.metric!r}")

    lhs = context[rule.metric]
    rhs = rule.value
    return _compare_rule_values(lhs, rule.op, rhs)


def apply_pre_rules(
    planned_control: TimeStepControl,
    ts: pd.Timestamp,
    rules: list[ControlRule],
    active_actions: list[ActiveRuleAction],
    trigger_counts: dict[str, int],
    sample_step: pd.Timedelta,
) -> tuple[TimeStepControl, list[ActiveRuleAction], dict[str, int]]:
    effective = _apply_active_rule_actions(planned_control, ts, active_actions)

    for rule in rules:
        if rule.stage != "pre":
            continue
        if rule.max_triggers is not None and trigger_counts.get(rule.name, 0) >= rule.max_triggers:
            continue
        if not evaluate_rule(rule, _build_rule_context(effective)):
            continue

        duration = _resolve_duration(rule.action.duration)
        if duration == pd.Timedelta(0):
            duration = sample_step

        action = ActiveRuleAction(
            rule_name=rule.name,
            start_ts=ts,
            end_ts=ts + duration,
            override=rule.action.to_override(),
        )
        active_actions.append(action)
        trigger_counts[rule.name] = trigger_counts.get(rule.name, 0) + 1
        effective = _apply_override(effective, action.override)

    return effective, active_actions, trigger_counts


def apply_post_rules(
    control: TimeStepControl,
    row: dict[str, Any],
    ts: pd.Timestamp,
    rules: list[ControlRule],
    active_actions: list[ActiveRuleAction],
    trigger_counts: dict[str, int],
    sample_step: pd.Timedelta,
) -> tuple[list[ActiveRuleAction], dict[str, int]]:
    for rule in rules:
        if rule.stage != "post":
            continue
        if rule.max_triggers is not None and trigger_counts.get(rule.name, 0) >= rule.max_triggers:
            continue
        if not evaluate_rule(rule, _build_rule_context(control, row=row)):
            continue

        duration = _resolve_duration(rule.action.duration)
        if duration == pd.Timedelta(0):
            duration = sample_step

        start_ts = ts + sample_step
        end_ts = start_ts + duration
        active_actions.append(
            ActiveRuleAction(
                rule_name=rule.name,
                start_ts=start_ts,
                end_ts=end_ts,
                override=rule.action.to_override(),
            )
        )
        trigger_counts[rule.name] = trigger_counts.get(rule.name, 0) + 1

    return active_actions, trigger_counts


def build_time_controls(
    idx: pd.DatetimeIndex,
    q_default_series: list[float],
    q_base_value: float,
    p_int_atma: float,
    t_int_C: float,
    pump_freq_hz: float,
    u_surf_v: Optional[float],
    p_res_atma: Optional[float] = None,
    productivity_index: Optional[float] = None,
    q_test_sm3day: Optional[float] = None,
    p_test_atma: Optional[float] = None,
    p_wh_atma: Optional[float] = None,
    p_cas_atma: Optional[float] = None,
    t_wf_C: Optional[float] = None,
    rp_m3m3: Optional[float] = None,
    muob_cP: Optional[float] = None,
    fw_fr: Optional[float] = None,
    q_gas_free_sm3day: Optional[float] = None,
    control_plan: Optional[ControlPlan] = None,
) -> list[TimeStepControl]:
    if not idx.empty:
        start_ts = pd.Timestamp(idx[0])
    else:
        start_ts = pd.Timestamp("2020-01-01 00:00:00")

    if control_plan is None:
        return [
            TimeStepControl(
                q_liq_sm3day=float(q_default_series[i]),
                p_int_atma=float(p_int_atma),
                t_int_C=float(t_int_C),
                pump_freq_hz=float(pump_freq_hz),
                u_surf_v=None if u_surf_v is None else float(u_surf_v),
                p_res_atma=None if p_res_atma is None else float(p_res_atma),
                productivity_index=None if productivity_index is None else float(productivity_index),
                q_test_sm3day=None if q_test_sm3day is None else float(q_test_sm3day),
                p_test_atma=None if p_test_atma is None else float(p_test_atma),
                p_wh_atma=None if p_wh_atma is None else float(p_wh_atma),
                p_cas_atma=None if p_cas_atma is None else float(p_cas_atma),
                t_wf_C=None if t_wf_C is None else float(t_wf_C),
                rp_m3m3=None if rp_m3m3 is None else float(rp_m3m3),
                muob_cP=None if muob_cP is None else float(muob_cP),
                fw_fr=None if fw_fr is None else float(fw_fr),
                q_gas_free_sm3day=None if q_gas_free_sm3day is None else float(q_gas_free_sm3day),
                is_running=True,
                control_label="",
                control_reason="",
            )
            for i in range(len(idx))
        ]

    base = control_plan.base or ControlOverride()
    base_state = TimeStepControl(
        q_liq_sm3day=float(q_base_value if base.q_liq_sm3day is None else base.q_liq_sm3day),
        p_int_atma=float(p_int_atma if base.p_int_atma is None else base.p_int_atma),
        t_int_C=float(t_int_C if base.t_int_C is None else base.t_int_C),
        pump_freq_hz=float(pump_freq_hz if base.pump_freq_hz is None else base.pump_freq_hz),
        u_surf_v=(None if u_surf_v is None and base.u_surf_v is None else float(u_surf_v if base.u_surf_v is None else base.u_surf_v)),
        p_res_atma=(None if p_res_atma is None and base.p_res_atma is None else float(p_res_atma if base.p_res_atma is None else base.p_res_atma)),
        productivity_index=(None if productivity_index is None and base.productivity_index is None else float(productivity_index if base.productivity_index is None else base.productivity_index)),
        q_test_sm3day=(None if q_test_sm3day is None and base.q_test_sm3day is None else float(q_test_sm3day if base.q_test_sm3day is None else base.q_test_sm3day)),
        p_test_atma=(None if p_test_atma is None and base.p_test_atma is None else float(p_test_atma if base.p_test_atma is None else base.p_test_atma)),
        p_wh_atma=(None if p_wh_atma is None and base.p_wh_atma is None else float(p_wh_atma if base.p_wh_atma is None else base.p_wh_atma)),
        p_cas_atma=(None if p_cas_atma is None and base.p_cas_atma is None else float(p_cas_atma if base.p_cas_atma is None else base.p_cas_atma)),
        t_wf_C=(None if t_wf_C is None and base.t_wf_C is None else float(t_wf_C if base.t_wf_C is None else base.t_wf_C)),
        rp_m3m3=(None if rp_m3m3 is None and base.rp_m3m3 is None else float(rp_m3m3 if base.rp_m3m3 is None else base.rp_m3m3)),
        muob_cP=(None if muob_cP is None and base.muob_cP is None else float(muob_cP if base.muob_cP is None else base.muob_cP)),
        fw_fr=(
            None
            if fw_fr is None and base.fw_fr is None and base.fw_perc is None
            else float(
                fw_fr
                if base.fw_fr is None and base.fw_perc is None
                else (base.fw_fr if base.fw_fr is not None else base.fw_perc / 100.0)
            )
        ),
        q_gas_free_sm3day=(
            None
            if q_gas_free_sm3day is None and base.q_gas_free_sm3day is None
            else float(q_gas_free_sm3day if base.q_gas_free_sm3day is None else base.q_gas_free_sm3day)
        ),
        is_running=True if base.running is None else bool(base.running),
        control_label="" if base.label is None else str(base.label),
        control_reason="" if base.reason is None else str(base.reason),
    )
    controls = [base_state for _ in idx]

    def apply_interval(start_expr: str, end_expr: str, override: ControlOverride) -> None:
        start = _resolve_time_expr(start_expr, start_ts)
        end = _resolve_time_expr(end_expr, start_ts)
        if end < start:
            raise ValueError(f"Control interval end precedes start: {start_expr!r} -> {end_expr!r}")

        for pos, ts in enumerate(idx):
            if start <= ts < end:
                controls[pos] = _apply_override(controls[pos], override)

    for segment in control_plan.segments:
        override = ControlOverride.model_validate(segment.model_dump(exclude={"start", "end"}, exclude_none=True))
        apply_interval(segment.start, segment.end, override)

    if len(idx) > 1:
        default_event_duration = idx[1] - idx[0]
    else:
        default_event_duration = pd.Timedelta(seconds=0)

    for event in control_plan.events:
        start = _resolve_time_expr(event.at, start_ts)
        duration = _resolve_duration(event.duration)
        if duration == pd.Timedelta(0):
            duration = default_event_duration
        end = start + duration
        override = event.to_override()

        for pos, ts in enumerate(idx):
            if duration == pd.Timedelta(0):
                if ts == start:
                    controls[pos] = _apply_override(controls[pos], override)
            elif start <= ts < end:
                controls[pos] = _apply_override(controls[pos], override)

    return controls


ControlPlan.model_rebuild()
