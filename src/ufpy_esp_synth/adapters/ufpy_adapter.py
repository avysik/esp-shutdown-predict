from __future__ import annotations

from pathlib import Path
from typing import Optional

from ufpy.esp.database import EquipmentRepository
from ufpy.esp.motor import ESPMotor
from ufpy.esp.pump import ESPPump
from ufpy.esp.system import ESPSystem
from ufpy.pvt.pvt import PVT
from ufpy.well.well_esp import WellESP

from ufpy_esp_synth.config.models import InflowConfig, MotorConfig, PumpConfig, PVTConfig, WellConfig


def resolve_default_esp_db_path() -> Path:
    """
    Try to locate ufpy/data/esp_db.json inside installed ufpy package.
    Falls back to <ufpy_package_dir>/data/esp_db.json.
    """
    import ufpy  # noqa: WPS433 (runtime import is intentional here)

    pkg_dir = Path(ufpy.__file__).resolve().parent
    candidate = pkg_dir / "data" / "esp_db.json"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        "Could not locate ufpy/data/esp_db.json inside ufpy installation. "
        "Provide --esp-db-path explicitly."
    )


def load_repository(db_path: Optional[Path]) -> EquipmentRepository:
    path = db_path if db_path is not None else resolve_default_esp_db_path()
    repo = EquipmentRepository(str(path))
    return repo


def build_pvt(pvt_cfg: PVTConfig, q_liq_sm3day: float) -> PVT:
    pvt = PVT()
    pvt.gamma_g = pvt_cfg.gamma_g
    pvt.gamma_o = pvt_cfg.gamma_o
    pvt.gamma_w = pvt_cfg.gamma_w
    pvt.rsb_m3m3 = pvt_cfg.rsb_m3m3
    pvt.rp_m3m3 = pvt_cfg.rp_m3m3
    pvt.pb_atma = pvt_cfg.pb_atma
    pvt.t_res_C = pvt_cfg.t_res_C
    pvt.bob_m3m3 = pvt_cfg.bob_m3m3
    pvt.muob_cP = pvt_cfg.muob_cP

    pvt.q_liq_sm3day = q_liq_sm3day
    pvt.fw_fr = pvt_cfg.fw_fr
    pvt.q_gas_free_sm3day = pvt_cfg.q_gas_free_sm3day
    return pvt


def build_pump(repo: EquipmentRepository, pump_cfg: PumpConfig) -> ESPPump:
    pump = ESPPump()
    pump.load_from_repository(repo, pump_cfg.esp_id)

    # Resolve stage_num and freq from DB if not provided
    if pump_cfg.stage_num is not None:
        pump.stage_num = int(pump_cfg.stage_num)
    elif pump.db.stages_max > 0:
        pump.stage_num = int(pump.db.stages_max)
    else:
        raise ValueError("stage_num is not provided and stages_max is not available in DB.")

    if pump_cfg.freq_hz is not None:
        pump.freq_hz = float(pump_cfg.freq_hz)
    elif pump.db.freq_hz > 0:
        pump.freq_hz = float(pump.db.freq_hz)
    else:
        raise ValueError("pump_freq_hz is not provided and freq_hz is not available in DB.")

    # Keep ufpy defaults; explicitly enable gas correction model=1 (same as examples).
    pump.gas_correct_model = 1
    return pump


def build_motor(motor_cfg: MotorConfig) -> ESPMotor:
    motor = ESPMotor()
    motor.set_motor(
        u_nom_lin_v=motor_cfg.u_nom_lin_v,
        p_nom_kw=motor_cfg.p_nom_kw,
        f_nom_hz=motor_cfg.f_nom_hz,
        eff_nom_fr=motor_cfg.eff_nom_fr,
        cosphi_nom_fr=motor_cfg.cosphi_nom_fr,
        slip_nom_fr=motor_cfg.slip_nom_fr,
        motor_id=motor_cfg.motor_id,
    )
    return motor


def build_system(repo: EquipmentRepository, pump_cfg: PumpConfig, motor_cfg: MotorConfig) -> ESPSystem:
    sys = ESPSystem()
    sys.pump.load_from_repository(repo, pump_cfg.esp_id)

    # stage_num and freq resolution mirrors build_pump
    if pump_cfg.stage_num is not None:
        sys.pump.stage_num = int(pump_cfg.stage_num)
    elif sys.pump.db.stages_max > 0:
        sys.pump.stage_num = int(sys.pump.db.stages_max)
    else:
        raise ValueError("stage_num is not provided and stages_max is not available in DB.")

    if pump_cfg.freq_hz is not None:
        sys.pump.freq_hz = float(pump_cfg.freq_hz)
    elif sys.pump.db.freq_hz > 0:
        sys.pump.freq_hz = float(sys.pump.db.freq_hz)
    else:
        raise ValueError("pump_freq_hz is not provided and freq_hz is not available in DB.")

    sys.pump.gas_correct_model = 1
    sys.motor = build_motor(motor_cfg)

    # This utility does not expose separator configuration.
    # Disable the implicit intake separation in ufpy's ESPSystem so free-gas
    # inputs (q_gas_free_sm3day) actually propagate into pump/system results.
    sys.separ.natsep_type = -1
    sys.separ.gassep_type = -1
    return sys


def build_well_esp(
    repo: EquipmentRepository,
    pump_cfg: PumpConfig,
    pvt_cfg: PVTConfig,
    inflow_cfg: InflowConfig,
    well_cfg: WellConfig,
) -> WellESP:
    well = WellESP()
    well.fluid = build_pvt(pvt_cfg, q_liq_sm3day=max(inflow_cfg.q_test_sm3day, 0.0))

    well.ipr.p_res_atma = inflow_cfg.p_res_atma
    well.ipr.q_test_sm3day = inflow_cfg.q_test_sm3day
    well.ipr.p_test_atma = inflow_cfg.p_test_atma
    well.ipr.fw_perc = pvt_cfg.fw_fr * 100.0
    well.ipr.pb_atma = pvt_cfg.pb_atma

    well.esp.load_from_repository(repo, pump_cfg.esp_id)
    if pump_cfg.stage_num is not None:
        well.esp.stage_num = int(pump_cfg.stage_num)
    elif well.esp.db.stages_max > 0:
        well.esp.stage_num = int(well.esp.db.stages_max)
    else:
        raise ValueError("stage_num is not provided and stages_max is not available in DB.")

    if pump_cfg.freq_hz is not None:
        well.esp.freq_hz = float(pump_cfg.freq_hz)
    elif well.esp.db.freq_hz > 0:
        well.esp.freq_hz = float(well.esp.db.freq_hz)
    else:
        raise ValueError("pump_freq_hz is not provided and freq_hz is not available in DB.")

    well.esp.gas_correct_model = 1
    well.init_well(
        well_cfg.h_perf_m,
        well_cfg.h_esp_m,
        well_cfg.d_tub_mm,
        well_cfg.d_cas_mm,
        well_cfg.t_surface_C,
        well_cfg.t_wf_C,
    )
    return well


def solve_well_from_pwh(
    well: WellESP,
    *,
    p_wh_atma: float,
    t_wf_C: float,
    p_cas_atma: float,
    esp_freq_hz: float,
    tol_atma: float = 0.05,
    max_iter: int = 60,
) -> float:
    p_wf_max = well.ipr.p_res_atma if well.ipr.p_res_atma > 0 else 500.0
    p_lo, p_hi = p_wh_atma, p_wf_max
    last_p_mid = p_hi

    for _ in range(max_iter):
        p_mid = (p_lo + p_hi) / 2.0
        last_p_mid = p_mid
        well.calc_from_pwf(p_mid, t_wf_C, p_cas_atma=p_cas_atma, esp_freq_hz=esp_freq_hz)
        diff = well.p_buf_atma - p_wh_atma
        if abs(diff) < tol_atma:
            return p_mid
        if diff > 0:
            p_hi = p_mid
        else:
            p_lo = p_mid

    well.calc_from_pwf(last_p_mid, t_wf_C, p_cas_atma=p_cas_atma, esp_freq_hz=esp_freq_hz)
    return last_p_mid
