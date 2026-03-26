from __future__ import annotations

from pathlib import Path

import pandas as pd

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.generation import generate_dataframe


def _base_cfg(tmp_path: Path) -> AppConfig:
    # Minimal small config for fast tests (small stage_num).
    return AppConfig.from_cli(
        scenario="pump-dp",
        esp_id="1006",
        n_files=1,
        workers=1,
        output_dir=tmp_path,
        time_step="1H",
        n_points=6,
        esp_db_path=None,
        stage_num=10,
        pump_freq_hz=50.0,
        p_int_atma=100.0,
        t_int_C=30.0,
        gamma_g=0.6,
        gamma_o=0.86,
        gamma_w=1.1,
        rsb_m3m3=120.0,
        rp_m3m3=120.0,
        pb_atma=130.0,
        t_res_C=80.0,
        bob_m3m3=1.2,
        muob_cP=0.6,
        fw_fr=None,
        fw_perc=10.0,
        q_gas_free_sm3day=0.0,
        u_surf_v=None,
        motor_u_nom_lin_v=None,
        motor_p_nom_kw=None,
        motor_f_nom_hz=None,
        motor_eff_nom_fr=None,
        motor_cosphi_nom_fr=None,
        motor_slip_nom_fr=None,
        motor_id=None,
    )


def test_determinism_same_config_same_output(tmp_path: Path) -> None:
    cfg = _base_cfg(tmp_path)
    df1 = generate_dataframe(cfg, run_id=0, total_runs=1)
    df2 = generate_dataframe(cfg, run_id=0, total_runs=1)

    pd.testing.assert_frame_equal(df1, df2, check_exact=True)
