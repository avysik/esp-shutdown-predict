from __future__ import annotations

from pathlib import Path

import pytest

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.generation import generate_dataframe
from tests.helpers import artifact_dir


PLAN_PATH = Path(__file__).resolve().parent / "data" / "control_plan_small_shutdown.json"


def _cfg(scenario: str) -> AppConfig:
    kwargs = {
        "scenario": scenario,
        "esp_id": "1006",
        "n_files": 1,
        "workers": 1,
        "output_dir": artifact_dir("shutdown_variants"),
        "time_step": "1min",
        "n_points": 6,
        "esp_db_path": None,
        "control_plan_path": PLAN_PATH,
        "stage_num": 50,
        "pump_freq_hz": 50.0,
        "p_int_atma": 120.0,
        "t_int_C": 60.0,
        "gamma_g": 0.7,
        "gamma_o": 0.86,
        "gamma_w": 1.0,
        "rsb_m3m3": 100.0,
        "rp_m3m3": 100.0,
        "pb_atma": 130.0,
        "t_res_C": 80.0,
        "bob_m3m3": 1.2,
        "muob_cP": 1.5,
        "fw_fr": None,
        "fw_perc": 30.0,
        "q_gas_free_sm3day": 0.0,
    }
    if scenario == "esp-system":
        kwargs.update(
            {
                "u_surf_v": 1000.0,
                "motor_u_nom_lin_v": 1000.0,
                "motor_p_nom_kw": 45.0,
                "motor_f_nom_hz": 50.0,
                "motor_eff_nom_fr": 0.85,
                "motor_cosphi_nom_fr": 0.9,
                "motor_slip_nom_fr": 0.04,
                "motor_id": 2,
            }
        )
    else:
        kwargs.update(
            {
                "u_surf_v": None,
                "motor_u_nom_lin_v": None,
                "motor_p_nom_kw": None,
                "motor_f_nom_hz": None,
                "motor_eff_nom_fr": None,
                "motor_cosphi_nom_fr": None,
                "motor_slip_nom_fr": None,
                "motor_id": None,
            }
        )
    return AppConfig.from_cli(**kwargs)


@pytest.mark.parametrize("scenario", ["pump-only", "pump-dp", "esp-system"])
def test_shutdown_and_restart_are_reflected_in_each_scenario(scenario: str) -> None:
    df = generate_dataframe(_cfg(scenario), run_id=0, total_runs=1)

    shutdown = df.iloc[2]
    restart = df.iloc[4]

    assert bool(shutdown["is_running"]) is False
    assert shutdown["control_label"] == "shutdown"
    assert shutdown["control_reason"] == "protection_trip"
    assert shutdown["q_liq_sm3day"] == 0.0
    assert shutdown["pump_freq_hz"] == 0.0

    if scenario == "pump-only":
        assert shutdown["head_m"] == 0.0
        assert shutdown["power_w"] == 0.0
        assert shutdown["eff_d"] == 0.0
    elif scenario == "pump-dp":
        assert shutdown["p_dis_atma"] == shutdown["p_int_atma"]
        assert shutdown["t_dis_c"] == shutdown["t_int_c"]
        assert shutdown["head_m"] == 0.0
        assert shutdown["power_fluid_w"] == 0.0
        assert shutdown["power_esp_w"] == 0.0
    else:
        assert shutdown["u_surf_v"] == 0.0
        assert shutdown["p_dis_atma"] == shutdown["p_int_atma"]
        assert shutdown["t_dis_c"] == shutdown["t_int_c"]
        assert shutdown["head_m"] == 0.0
        assert shutdown["motor_i_lin_a"] == 0.0
        assert shutdown["motor_speed_rpm"] == 0.0

    assert bool(restart["is_running"]) is True
    assert restart["control_label"] == "restart"
    assert restart["control_reason"] == "recovered"
    assert restart["q_liq_sm3day"] == 76.0
    assert restart["pump_freq_hz"] == 50.0
    assert restart["p_int_atma"] == 118.0
