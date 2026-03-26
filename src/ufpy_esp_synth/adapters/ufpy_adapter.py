from __future__ import annotations

from pathlib import Path
from typing import Optional

from ufpy.esp.database import EquipmentRepository
from ufpy.esp.motor import ESPMotor
from ufpy.esp.pump import ESPPump
from ufpy.esp.system import ESPSystem
from ufpy.pvt.pvt import PVT

from ufpy_esp_synth.config.models import MotorConfig, PumpConfig, PVTConfig


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
    return sys
