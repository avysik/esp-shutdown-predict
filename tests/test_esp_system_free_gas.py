from __future__ import annotations

from pathlib import Path

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.generation import generate_dataframe


def _cfg(q_gas_free_sm3day: float) -> AppConfig:
    return AppConfig.from_cli(
        scenario="esp-system",
        esp_id="1006",
        n_files=1,
        workers=1,
        output_dir=Path("."),
        time_step="30min",
        n_points=1,
        esp_db_path=None,
        control_plan_path=None,
        stage_num=250,
        pump_freq_hz=50.0,
        p_int_atma=120.0,
        t_int_C=60.0,
        gamma_g=0.7,
        gamma_o=0.86,
        gamma_w=1.0,
        rsb_m3m3=100.0,
        rp_m3m3=100.0,
        pb_atma=130.0,
        t_res_C=80.0,
        bob_m3m3=1.2,
        muob_cP=1.5,
        fw_fr=None,
        fw_perc=30.0,
        q_gas_free_sm3day=q_gas_free_sm3day,
        u_surf_v=1000.0,
        motor_u_nom_lin_v=1000.0,
        motor_p_nom_kw=45.0,
        motor_f_nom_hz=50.0,
        motor_eff_nom_fr=0.85,
        motor_cosphi_nom_fr=0.9,
        motor_slip_nom_fr=0.04,
        motor_id=2,
    )


def test_esp_system_outputs_change_when_free_gas_changes() -> None:
    df_no_free = generate_dataframe(_cfg(0.0), run_id=0, total_runs=1)
    df_with_free = generate_dataframe(_cfg(2000.0), run_id=0, total_runs=1)

    row0 = df_no_free.iloc[0]
    row1 = df_with_free.iloc[0]

    assert row0["gas_fraction_d"] != row1["gas_fraction_d"]
    assert row0["head_m"] != row1["head_m"]
    assert row0["p_dis_atma"] != row1["p_dis_atma"]
    assert row0["motor_i_lin_a"] != row1["motor_i_lin_a"]
