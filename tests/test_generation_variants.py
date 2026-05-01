from __future__ import annotations

import pytest

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.generation import generate_dataframe
from tests.helpers import artifact_dir


def _base_kwargs() -> dict:
    return {
        "esp_id": "1006",
        "n_files": 1,
        "workers": 1,
        "output_dir": artifact_dir("generation_variants"),
        "time_step": "30min",
        "n_points": 3,
        "esp_db_path": None,
        "control_plan_path": None,
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


def _cfg(scenario: str) -> AppConfig:
    kwargs = _base_kwargs()
    kwargs["scenario"] = scenario
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
def test_each_scenario_produces_expected_nonzero_outputs(scenario: str) -> None:
    df = generate_dataframe(_cfg(scenario), run_id=0, total_runs=1)

    assert len(df) == 3
    assert df["q_liq_sm3day"].iloc[0] == df["q_liq_sm3day"].iloc[2]
    assert df["q_liq_sm3day"].iloc[1] > df["q_liq_sm3day"].iloc[0]

    if scenario == "pump-only":
        assert (df["head_m"] > 0).all()
        assert (df["power_w"] > 0).all()
        assert ((df["eff_d"] > 0) & (df["eff_d"] < 1)).all()
    elif scenario == "pump-dp":
        assert (df["p_dis_atma"] > df["p_int_atma"]).all()
        assert (df["head_m"] > 0).all()
        assert (df["power_esp_w"] >= df["power_fluid_w"]).all()
        assert ((df["eff_esp_d"] > 0) & (df["eff_esp_d"] < 1)).all()
    else:
        assert (df["p_dis_atma"] > df["p_int_atma"]).all()
        assert (df["head_m"] > 0).all()
        assert (df["motor_i_lin_a"] > 0).all()
        assert ((df["motor_eff_d"] > 0) & (df["motor_eff_d"] < 1)).all()
        assert ((df["system_eff_d"] > 0) & (df["system_eff_d"] < 1)).all()
