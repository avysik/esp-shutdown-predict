from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ufpy_esp_synth.adapters.ufpy_adapter import build_pump, build_pvt, build_system, load_repository
from ufpy_esp_synth.config.models import AppConfig, ScenarioName
from ufpy_esp_synth.domain.schema import columns_for
from ufpy_esp_synth.utils.deterministic import make_q_profile
from ufpy_esp_synth.utils.paths import make_output_path
from ufpy_esp_synth.utils.time import normalize_pandas_freq


START_TS = pd.Timestamp("2020-01-01 00:00:00")


@dataclass(frozen=True)
class TaskResult:
    run_id: int
    ok: bool
    output_path: str
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

    if cfg.scenario == ScenarioName.ESP_SYSTEM:
        sys = build_system(repo, cfg.pump, cfg.motor)  # type: ignore[arg-type]
        pump = sys.pump
    else:
        pump = build_pump(repo, cfg.pump)
        sys = None  # type: ignore[assignment]

    q_min, q_max = _pump_q_range_from_db(pump)
    q_series = make_q_profile(
        n_points=cfg.time_axis.n_points,
        q_min=q_min,
        q_max=q_max,
        run_id=run_id,
        total_runs=total_runs,
    )

    cols = columns_for(cfg.scenario)
    data: dict[str, list[Any]] = {c: [] for c in cols}

    for i, ts in enumerate(idx):
        q_liq = float(q_series[i])

        pvt = build_pvt(cfg.pvt, q_liq_sm3day=q_liq)
        # Compute intake PVT state (used by pump.calc_ESP internally; also recorded as honest intermediate outputs)
        pvt.calc_pvt(cfg.hydraulic.p_int_atma, cfg.hydraulic.t_int_C)

        mu_mix_cst = float(pvt.mu_mix_cSt)
        gas_frac = float(pvt.gas_fraction_d)
        q_mix_rc = float(pvt.q_mix_rc_m3day)

        # Common inputs
        common = {
            "value_date": ts.to_pydatetime(),
            "esp_id": cfg.pump.esp_id,
            "run_id": int(run_id),
            "stage_num": int(pump.stage_num),
            "pump_freq_hz": float(pump.freq_hz),
            "p_int_atma": float(cfg.hydraulic.p_int_atma),
            "t_int_c": float(cfg.hydraulic.t_int_C),
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
            head_m = float(pump.get_head_m(q_liq, pump.stage_num, mu_mix_cst))
            power_w = float(pump.get_power_W(q_liq, pump.stage_num, mu_mix_cst))
            eff_d = float(pump.get_efficiency(q_liq, mu_mix_cst))

            row = {
                **common,
                "head_m": head_m,
                "power_w": power_w,
                "eff_d": eff_d,
            }

        elif cfg.scenario == ScenarioName.PUMP_DP:
            pump.fluid = pvt
            pump.calc_ESP(cfg.hydraulic.p_int_atma, cfg.hydraulic.t_int_C, t_dis_C=-1.0, calc_from_dis=False)

            row = {
                **common,
                "p_dis_atma": float(pump.p_dis_atma),
                "t_dis_c": float(pump.t_dis_C),
                "head_m": float(pump.head_m),
                "eff_esp_d": float(pump.eff_ESP_d),
                "power_fluid_w": float(pump.power_fluid_W),
                "power_esp_w": float(pump.power_ESP_W),
            }

        elif cfg.scenario == ScenarioName.ESP_SYSTEM:
            assert sys is not None
            sys.fluid = pvt
            sys.calc_esp_system(
                cfg.hydraulic.p_int_atma,
                cfg.hydraulic.t_int_C,
                t_dis_C=-1.0,
                u_surf_v=cfg.motor.u_surf_v,  # type: ignore[union-attr]
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
                "u_surf_v": float(cfg.motor.u_surf_v),  # type: ignore[union-attr]
                "motor_u_nom_lin_v": float(cfg.motor.u_nom_lin_v),  # type: ignore[union-attr]
                "motor_p_nom_kw": float(cfg.motor.p_nom_kw),  # type: ignore[union-attr]
                "motor_f_nom_hz": float(cfg.motor.f_nom_hz),  # type: ignore[union-attr]
                "motor_eff_nom_fr": float(cfg.motor.eff_nom_fr),  # type: ignore[union-attr]
                "motor_cosphi_nom_fr": float(cfg.motor.cosphi_nom_fr),  # type: ignore[union-attr]
                "motor_slip_nom_fr": float(cfg.motor.slip_nom_fr),  # type: ignore[union-attr]
                "motor_id": int(cfg.motor.motor_id),  # type: ignore[union-attr]
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
            raise ValueError(f"Unsupported scenario: {cfg.scenario}")

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
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        df = generate_dataframe(cfg, run_id=run_id, total_runs=total_runs)
        df.to_parquet(out_path, index=False, engine="pyarrow")
        dt = time.perf_counter() - t0
        return TaskResult(run_id=run_id, ok=True, output_path=str(out_path), duration_s=dt)
    except Exception as e:
        dt = time.perf_counter() - t0
        return TaskResult(run_id=run_id, ok=False, output_path=str(out_path), duration_s=dt, error=repr(e))


def worker_entry(cfg_dict: dict[str, Any], run_id: int, total_runs: int) -> TaskResult:
    """
    ProcessPoolExecutor entrypoint.
    Must be top-level for pickling (esp. on Windows spawn).
    """
    cfg = AppConfig.model_validate(cfg_dict)
    return generate_one_file(cfg, run_id=run_id, total_runs=total_runs)
