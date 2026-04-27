from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
from tqdm import tqdm

from ufpy_esp_synth.adapters.ufpy_adapter import (
    build_pump,
    build_pvt,
    build_system,
    build_well_esp,
    load_repository,
    solve_well_from_pwh,
)
from ufpy_esp_synth.config.models import AppConfig, ScenarioName
from ufpy_esp_synth.domain.control_plan import (
    apply_post_rules,
    apply_pre_rules,
    build_time_controls,
    load_control_plan,
)
from ufpy_esp_synth.domain.schema import columns_for
from ufpy_esp_synth.domain.telemetry_schema import make_telemetry_dataframe
from ufpy_esp_synth.utils.deterministic import make_q_profile
from ufpy_esp_synth.utils.paths import make_output_path, make_telemetry_output_path
from ufpy_esp_synth.utils.time import normalize_pandas_freq


START_TS = pd.Timestamp("2020-01-01 00:00:00")


@dataclass(frozen=True)
class TaskResult:
    run_id: int
    ok: bool
    output_path: str
    telemetry_output_path: str
    duration_s: float
    error: str = ""


def _make_time_index(time_step: str, n_points: int) -> pd.DatetimeIndex:
    # Strict determinism: fixed start time.
    freq = normalize_pandas_freq(time_step)
    return pd.date_range(start=START_TS, periods=n_points, freq=freq)


def _pump_q_range_from_db(pump) -> tuple[float, float]:
    """
    Determine a deterministic operating range for q_liq_sm3day.
    Priority:
      1) rate_opt_min/max (scaled by freq)
      2) rate_nom vs rate_max (scaled by freq)
      3) fallback: rate_max vs rate_max (constant series)
    """
    db = pump.db
    freq_ratio = (pump.freq_hz / db.freq_hz) if db.freq_hz and db.freq_hz > 0 else 1.0

    opt_min = float(db.rate_opt_min_sm3day or 0.0) * freq_ratio
    opt_max = float(db.rate_opt_max_sm3day or 0.0) * freq_ratio
    if opt_min > 0 and opt_max > opt_min:
        return opt_min, opt_max

    rate_nom = float(db.rate_nom_sm3day or 0.0) * freq_ratio
    rate_max = float(db.rate_max_sm3day or 0.0) * freq_ratio

    if rate_nom > 0 and rate_max > 0:
        q_lo = min(rate_nom, rate_max)
        q_hi = max(rate_nom, rate_max)
        return q_lo, q_hi

    if rate_max > 0:
        return rate_max, rate_max

    raise ValueError("Cannot determine q range: DB has no usable rate_* fields for this pump.")


def generate_dataframe(cfg: AppConfig, run_id: int, total_runs: int) -> pd.DataFrame:
    idx = _make_time_index(cfg.time_axis.time_step, cfg.time_axis.n_points)

    repo = load_repository(cfg.esp_db_path)

    # Build a temporary object only to read pump DB bounds for deterministic q profile.
    if cfg.scenario == ScenarioName.ESP_SYSTEM:
        pump_for_bounds = build_system(repo, cfg.pump, cfg.motor).pump  # type: ignore[arg-type]
    elif cfg.scenario == ScenarioName.WELL_ESP_SYSTEM:
        pump_for_bounds = build_pump(repo, cfg.pump)
    else:
        pump_for_bounds = build_pump(repo, cfg.pump)

    q_min, q_max = _pump_q_range_from_db(pump_for_bounds)
    q_series = make_q_profile(
        n_points=cfg.time_axis.n_points,
        q_min=q_min,
        q_max=q_max,
        run_id=run_id,
        total_runs=total_runs,
    )
    q_base_value = cfg.inflow.q_test_sm3day if cfg.scenario == ScenarioName.WELL_ESP_SYSTEM else (q_min + q_max) / 2.0
    control_plan = load_control_plan(cfg.control_plan_path)
    rules = [] if control_plan is None else list(control_plan.rules)
    controls = build_time_controls(
        idx=idx,
        q_default_series=q_series,
        q_base_value=q_base_value,
        p_int_atma=1.0 if cfg.hydraulic is None else cfg.hydraulic.p_int_atma,
        t_int_C=cfg.well.t_wf_C if cfg.well is not None else cfg.hydraulic.t_int_C,
        pump_freq_hz=float(pump_for_bounds.freq_hz),
        u_surf_v=None if cfg.motor is None else cfg.motor.u_surf_v,
        p_res_atma=None if cfg.inflow is None else cfg.inflow.p_res_atma,
        q_test_sm3day=None if cfg.inflow is None else cfg.inflow.q_test_sm3day,
        p_test_atma=None if cfg.inflow is None else cfg.inflow.p_test_atma,
        p_wh_atma=None if cfg.well is None else cfg.well.p_wh_atma,
        p_cas_atma=None if cfg.well is None else cfg.well.p_cas_atma,
        t_wf_C=None if cfg.well is None else cfg.well.t_wf_C,
        control_plan=control_plan,
    )
    sample_step = idx[1] - idx[0] if len(idx) > 1 else pd.Timedelta(seconds=0)
    active_rule_actions = []
    rule_trigger_counts: dict[str, int] = {}

    cols = columns_for(cfg.scenario)
    data: dict[str, list[Any]] = {c: [] for c in cols}

    for i, ts in enumerate(tqdm(idx, desc=f"run {run_id}", leave=False)):
        planned_control = controls[i]
        control, active_rule_actions, rule_trigger_counts = apply_pre_rules(
            planned_control=planned_control,
            ts=ts,
            rules=rules,
            active_actions=active_rule_actions,
            trigger_counts=rule_trigger_counts,
            sample_step=sample_step,
        )
        q_liq = float(control.q_liq_sm3day)
        is_running = bool(control.is_running and control.pump_freq_hz > 0.0)

        if cfg.scenario == ScenarioName.WELL_ESP_SYSTEM:
            assert cfg.inflow is not None
            assert cfg.well is not None
            assert cfg.motor is not None

            inflow_cfg = cfg.inflow.model_copy(
                update={
                    "p_res_atma": cfg.inflow.p_res_atma if control.p_res_atma is None else float(control.p_res_atma),
                    "q_test_sm3day": cfg.inflow.q_test_sm3day if control.q_test_sm3day is None else float(control.q_test_sm3day),
                    "p_test_atma": cfg.inflow.p_test_atma if control.p_test_atma is None else float(control.p_test_atma),
                }
            )
            well_cfg = cfg.well.model_copy(
                update={
                    "p_wh_atma": cfg.well.p_wh_atma if control.p_wh_atma is None else float(control.p_wh_atma),
                    "p_cas_atma": cfg.well.p_cas_atma if control.p_cas_atma is None else float(control.p_cas_atma),
                    "t_wf_C": cfg.well.t_wf_C if control.t_wf_C is None else float(control.t_wf_C),
                }
            )

            well = build_well_esp(repo, cfg.pump, cfg.pvt, inflow_cfg, well_cfg)
            p_wf_atma = solve_well_from_pwh(
                well,
                p_wh_atma=well_cfg.p_wh_atma,
                t_wf_C=well_cfg.t_wf_C,
                p_cas_atma=well_cfg.p_cas_atma,
                esp_freq_hz=float(control.pump_freq_hz),
            )

            q_liq = float(well.q_liq_sm3day)
            intake_fluid = well.fluid.clone()
            intake_fluid.q_liq_sm3day = q_liq
            intake_fluid.mod_after_separation(well.separ.p_ksep_atma, well.separ.t_ksep_C, well.ksep_total_d)
            intake_fluid.calc_pvt(well.p_intake_atma, well.t_intake_C)

            mu_mix_cst = float(intake_fluid.mu_mix_cSt)
            gas_frac = float(intake_fluid.gas_fraction_d)
            q_mix_rc = float(intake_fluid.q_mix_rc_m3day)

            if is_running:
                sys = build_system(repo, cfg.pump, cfg.motor)
                sys.fluid = intake_fluid
                sys.calc_esp_system(
                    well.p_intake_atma,
                    well.t_intake_C,
                    t_dis_C=-1.0,
                    u_surf_v=float(control.u_surf_v if control.u_surf_v is not None else cfg.motor.u_surf_v),
                    f_surf_hz=float(control.pump_freq_hz),
                    calc_along_flow=True,
                )
                motor_data = sys.motor.data
                system_eff_d = float(sys.eff_d)
                motor_speed_rpm = 60.0 * float(motor_data.f_hz) * (1.0 - float(motor_data.s_d))
                motor_row = {
                    "motor_u_lin_v": float(motor_data.u_lin_v),
                    "motor_i_lin_a": float(motor_data.i_lin_a),
                    "motor_cosphi": float(motor_data.cosphi),
                    "motor_slip": float(motor_data.s_d),
                    "motor_eff_d": float(motor_data.eff_d),
                    "motor_p_shaft_kw": float(motor_data.p_shaft_kw),
                    "motor_p_electr_kw": float(motor_data.p_electr_kw),
                    "motor_power_cs_kw": float(motor_data.power_cs_calc_w) / 1000.0,
                    "motor_eff_full_d": float(motor_data.eff_full_d),
                    "motor_load_d": float(motor_data.load_d),
                    "motor_speed_rpm": motor_speed_rpm,
                }
            else:
                system_eff_d = 0.0
                motor_row = {
                    "motor_u_lin_v": 0.0,
                    "motor_i_lin_a": 0.0,
                    "motor_cosphi": 0.0,
                    "motor_slip": 0.0,
                    "motor_eff_d": 0.0,
                    "motor_p_shaft_kw": 0.0,
                    "motor_p_electr_kw": 0.0,
                    "motor_power_cs_kw": 0.0,
                    "motor_eff_full_d": 0.0,
                    "motor_load_d": 0.0,
                    "motor_speed_rpm": 0.0,
                }

            row = {
                "value_date": ts.to_pydatetime(),
                "esp_id": cfg.pump.esp_id,
                "run_id": int(run_id),
                "is_running": is_running,
                "control_label": control.control_label,
                "control_reason": control.control_reason,
                "stage_num": int(well.esp.stage_num),
                "pump_freq_hz": float(control.pump_freq_hz),
                "p_wf_atma": float(p_wf_atma),
                "p_int_atma": float(well.p_intake_atma),
                "p_dis_atma": float(well.p_dis_atma),
                "p_buf_atma": float(well.p_buf_atma),
                "p_cas_atma": float(well_cfg.p_cas_atma),
                "p_res_atma": float(inflow_cfg.p_res_atma),
                "q_test_sm3day": float(inflow_cfg.q_test_sm3day),
                "p_test_atma": float(inflow_cfg.p_test_atma),
                "t_wf_c": float(well_cfg.t_wf_C),
                "t_int_c": float(well.t_intake_C),
                "t_dis_c": float(well.t_dis_C),
                "t_buf_c": float(well.t_buf_C),
                "t_surface_c": float(well_cfg.t_surface_C),
                "h_perf_m": float(well_cfg.h_perf_m),
                "h_esp_m": float(well_cfg.h_esp_m),
                "d_tub_mm": float(well_cfg.d_tub_mm),
                "d_cas_mm": float(well_cfg.d_cas_mm),
                "gamma_g": float(cfg.pvt.gamma_g),
                "gamma_o": float(cfg.pvt.gamma_o),
                "gamma_w": float(cfg.pvt.gamma_w),
                "rsb_m3m3": float(cfg.pvt.rsb_m3m3),
                "rp_m3m3": float(cfg.pvt.rp_m3m3),
                "pb_atma": float(cfg.pvt.pb_atma),
                "t_res_c": float(cfg.pvt.t_res_C),
                "bob_m3m3": float(cfg.pvt.bob_m3m3),
                "muob_cp": float(cfg.pvt.muob_cP),
                "fw_fr": float(cfg.pvt.fw_fr),
                "q_gas_free_sm3day": float(cfg.pvt.q_gas_free_sm3day),
                "q_liq_sm3day": q_liq,
                "mu_mix_cst": mu_mix_cst,
                "gas_fraction_d": gas_frac,
                "q_mix_rc_m3day": q_mix_rc,
                "ksep_total_d": float(well.ksep_total_d),
                "gas_fraction_pump_d": float(well.gas_fraction_pump_d),
                "head_m": float(well.esp.head_m),
                "eff_esp_d": float(well.esp.eff_ESP_d),
                "power_fluid_w": float(well.esp.power_fluid_W),
                "power_esp_w": float(well.esp.power_ESP_W),
                "system_eff_d": system_eff_d,
                "u_surf_v": float(control.u_surf_v if control.u_surf_v is not None else cfg.motor.u_surf_v),
                "motor_u_nom_lin_v": float(cfg.motor.u_nom_lin_v),
                "motor_p_nom_kw": float(cfg.motor.p_nom_kw),
                "motor_f_nom_hz": float(cfg.motor.f_nom_hz),
                "motor_eff_nom_fr": float(cfg.motor.eff_nom_fr),
                "motor_cosphi_nom_fr": float(cfg.motor.cosphi_nom_fr),
                "motor_slip_nom_fr": float(cfg.motor.slip_nom_fr),
                "motor_id": int(cfg.motor.motor_id),
                **motor_row,
            }

            active_rule_actions, rule_trigger_counts = apply_post_rules(
                control=control,
                row=row,
                ts=ts,
                rules=rules,
                active_actions=active_rule_actions,
                trigger_counts=rule_trigger_counts,
                sample_step=sample_step,
            )
            for c in cols:
                data[c].append(row[c])
            continue

        # IMPORTANT:
        # Rebuild ufpy objects on every timestamp to avoid hidden state carry-over
        # between time points.
        if cfg.scenario == ScenarioName.ESP_SYSTEM:
            sys = build_system(repo, cfg.pump, cfg.motor)  # type: ignore[arg-type]
            pump = sys.pump
        else:
            pump = build_pump(repo, cfg.pump)
            sys = None  # type: ignore[assignment]
        pump.freq_hz = float(control.pump_freq_hz)

        pvt = build_pvt(cfg.pvt, q_liq_sm3day=q_liq)
        # Compute intake PVT state (used by pump.calc_ESP internally; also recorded as honest intermediate outputs)
        pvt.calc_pvt(control.p_int_atma, control.t_int_C)

        mu_mix_cst = float(pvt.mu_mix_cSt)
        gas_frac = float(pvt.gas_fraction_d)
        q_mix_rc = float(pvt.q_mix_rc_m3day)

        # Common inputs
        common = {
            "value_date": ts.to_pydatetime(),
            "esp_id": cfg.pump.esp_id,
            "run_id": int(run_id),
            "is_running": is_running,
            "control_label": control.control_label,
            "control_reason": control.control_reason,
            "stage_num": int(pump.stage_num),
            "pump_freq_hz": float(control.pump_freq_hz),
            "p_int_atma": float(control.p_int_atma),
            "t_int_c": float(control.t_int_C),
            "gamma_g": float(cfg.pvt.gamma_g),
            "gamma_o": float(cfg.pvt.gamma_o),
            "gamma_w": float(cfg.pvt.gamma_w),
            "rsb_m3m3": float(cfg.pvt.rsb_m3m3),
            "rp_m3m3": float(cfg.pvt.rp_m3m3),
            "pb_atma": float(cfg.pvt.pb_atma),
            "t_res_c": float(cfg.pvt.t_res_C),
            "bob_m3m3": float(cfg.pvt.bob_m3m3),
            "muob_cp": float(cfg.pvt.muob_cP),
            "fw_fr": float(cfg.pvt.fw_fr),
            "q_gas_free_sm3day": float(cfg.pvt.q_gas_free_sm3day),
            "q_liq_sm3day": q_liq,
            "mu_mix_cst": mu_mix_cst,
            "gas_fraction_d": gas_frac,
            "q_mix_rc_m3day": q_mix_rc,
        }

        if cfg.scenario == ScenarioName.PUMP_ONLY:
            if is_running:
                head_m = float(pump.get_head_m(q_liq, pump.stage_num, mu_mix_cst))
                power_w = float(pump.get_power_W(q_liq, pump.stage_num, mu_mix_cst))
                eff_d = float(pump.get_efficiency(q_liq, mu_mix_cst))
            else:
                head_m = 0.0
                power_w = 0.0
                eff_d = 0.0

            row = {
                **common,
                "head_m": head_m,
                "power_w": power_w,
                "eff_d": eff_d,
            }

        elif cfg.scenario == ScenarioName.PUMP_DP:
            if is_running:
                pump.fluid = pvt
                pump.calc_ESP(
                    control.p_int_atma,
                    control.t_int_C,
                    t_dis_C=-1.0,
                    calc_from_dis=False,
                )

                row = {
                    **common,
                    "p_dis_atma": float(pump.p_dis_atma),
                    "t_dis_c": float(pump.t_dis_C),
                    "head_m": float(pump.head_m),
                    "eff_esp_d": float(pump.eff_ESP_d),
                    "power_fluid_w": float(pump.power_fluid_W),
                    "power_esp_w": float(pump.power_ESP_W),
                }
            else:
                row = {
                    **common,
                    "p_dis_atma": float(control.p_int_atma),
                    "t_dis_c": float(control.t_int_C),
                    "head_m": 0.0,
                    "eff_esp_d": 0.0,
                    "power_fluid_w": 0.0,
                    "power_esp_w": 0.0,
                }

        elif cfg.scenario == ScenarioName.ESP_SYSTEM:
            assert sys is not None
            assert cfg.motor is not None

            if is_running:
                sys.fluid = pvt
                sys.calc_esp_system(
                    control.p_int_atma,
                    control.t_int_C,
                    t_dis_C=-1.0,
                    u_surf_v=float(control.u_surf_v if control.u_surf_v is not None else cfg.motor.u_surf_v),
                    f_surf_hz=float(pump.freq_hz),
                    calc_along_flow=True,
                )

                m = sys.motor
                md = m.data

                motor_speed_rpm = 60.0 * float(md.f_hz) * (1.0 - float(md.s_d))

                row = {
                    **common,
                    "p_dis_atma": float(sys.p_dis_atma),
                    "t_dis_c": float(sys.t_dis_C),
                    "head_m": float(sys.pump.head_m),
                    "eff_esp_d": float(sys.pump.eff_ESP_d),
                    "power_fluid_w": float(sys.pump.power_fluid_W),
                    "power_esp_w": float(sys.pump.power_ESP_W),
                    "system_eff_d": float(sys.eff_d),
                    "u_surf_v": float(control.u_surf_v if control.u_surf_v is not None else cfg.motor.u_surf_v),
                    "motor_u_nom_lin_v": float(cfg.motor.u_nom_lin_v),
                    "motor_p_nom_kw": float(cfg.motor.p_nom_kw),
                    "motor_f_nom_hz": float(cfg.motor.f_nom_hz),
                    "motor_eff_nom_fr": float(cfg.motor.eff_nom_fr),
                    "motor_cosphi_nom_fr": float(cfg.motor.cosphi_nom_fr),
                    "motor_slip_nom_fr": float(cfg.motor.slip_nom_fr),
                    "motor_id": int(cfg.motor.motor_id),
                    "motor_u_lin_v": float(md.u_lin_v),
                    "motor_i_lin_a": float(md.i_lin_a),
                    "motor_cosphi": float(md.cosphi),
                    "motor_slip": float(md.s_d),
                    "motor_eff_d": float(md.eff_d),
                    "motor_p_shaft_kw": float(md.p_shaft_kw),
                    "motor_p_electr_kw": float(md.p_electr_kw),
                    "motor_power_cs_kw": float(md.power_cs_calc_w) / 1000.0,
                    "motor_eff_full_d": float(md.eff_full_d),
                    "motor_load_d": float(md.load_d),
                    "motor_speed_rpm": motor_speed_rpm,
                }
            else:
                row = {
                    **common,
                    "p_dis_atma": float(control.p_int_atma),
                    "t_dis_c": float(control.t_int_C),
                    "head_m": 0.0,
                    "eff_esp_d": 0.0,
                    "power_fluid_w": 0.0,
                    "power_esp_w": 0.0,
                    "system_eff_d": 0.0,
                    "u_surf_v": float(control.u_surf_v if control.u_surf_v is not None else 0.0),
                    "motor_u_nom_lin_v": float(cfg.motor.u_nom_lin_v),
                    "motor_p_nom_kw": float(cfg.motor.p_nom_kw),
                    "motor_f_nom_hz": float(cfg.motor.f_nom_hz),
                    "motor_eff_nom_fr": float(cfg.motor.eff_nom_fr),
                    "motor_cosphi_nom_fr": float(cfg.motor.cosphi_nom_fr),
                    "motor_slip_nom_fr": float(cfg.motor.slip_nom_fr),
                    "motor_id": int(cfg.motor.motor_id),
                    "motor_u_lin_v": 0.0,
                    "motor_i_lin_a": 0.0,
                    "motor_cosphi": 0.0,
                    "motor_slip": 0.0,
                    "motor_eff_d": 0.0,
                    "motor_p_shaft_kw": 0.0,
                    "motor_p_electr_kw": 0.0,
                    "motor_power_cs_kw": 0.0,
                    "motor_eff_full_d": 0.0,
                    "motor_load_d": 0.0,
                    "motor_speed_rpm": 0.0,
                }
        else:
            raise ValueError(f"Unsupported scenario: {cfg.scenario}")

        active_rule_actions, rule_trigger_counts = apply_post_rules(
            control=control,
            row=row,
            ts=ts,
            rules=rules,
            active_actions=active_rule_actions,
            trigger_counts=rule_trigger_counts,
            sample_step=sample_step,
        )

        # Append in schema order
        for c in cols:
            data[c].append(row[c])

    df = pd.DataFrame(data, columns=cols)
    df["value_date"] = pd.to_datetime(df["value_date"])
    return df


def generate_one_file(cfg: AppConfig, run_id: int, total_runs: int) -> TaskResult:
    t0 = time.perf_counter()
    out_path = make_output_path(
        output_dir=cfg.generation.output_dir,
        scenario=cfg.scenario.value,
        esp_id=cfg.pump.esp_id,
        run_id=run_id,
    )
    telemetry_out_path = make_telemetry_output_path(
        output_dir=cfg.generation.output_dir,
        scenario=cfg.scenario.value,
        esp_id=cfg.pump.esp_id,
        run_id=run_id,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        df = generate_dataframe(cfg, run_id=run_id, total_runs=total_runs)
        telemetry_df = make_telemetry_dataframe(df)
        df.to_parquet(out_path, index=False, engine="pyarrow")
        telemetry_df.to_parquet(telemetry_out_path, index=False, engine="pyarrow")
        dt = time.perf_counter() - t0
        return TaskResult(
            run_id=run_id,
            ok=True,
            output_path=str(out_path),
            telemetry_output_path=str(telemetry_out_path),
            duration_s=dt,
        )
    except Exception as e:
        dt = time.perf_counter() - t0
        return TaskResult(
            run_id=run_id,
            ok=False,
            output_path=str(out_path),
            telemetry_output_path=str(telemetry_out_path),
            duration_s=dt,
            error=repr(e),
        )


def worker_entry(cfg_dict: dict[str, Any], run_id: int, total_runs: int) -> TaskResult:
    """
    ProcessPoolExecutor entrypoint.
    Must be top-level for pickling (esp. on Windows spawn).
    """
    cfg = AppConfig.model_validate(cfg_dict)
    return generate_one_file(cfg, run_id=run_id, total_runs=total_runs)
