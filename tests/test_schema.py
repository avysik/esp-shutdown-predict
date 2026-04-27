from __future__ import annotations

from pathlib import Path

from ufpy_esp_synth.config.models import AppConfig, ScenarioName
from ufpy_esp_synth.domain.schema import columns_for
from ufpy_esp_synth.services.generation import generate_dataframe
from tests.helpers import artifact_dir


def test_schema_columns_match_domain_schema() -> None:
    cfg = AppConfig.from_cli(
        scenario="esp-system",
        esp_id="1006",
        n_files=1,
        workers=1,
        output_dir=artifact_dir("schema"),
        time_step="30min",
        n_points=4,
        esp_db_path=None,
        stage_num=10,
        pump_freq_hz=50.0,
        p_int_atma=100.0,
        t_int_C=50.0,
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
        u_surf_v=1000.0,
        motor_u_nom_lin_v=1000.0,
        motor_p_nom_kw=30.0,
        motor_f_nom_hz=50.0,
        motor_eff_nom_fr=0.82,
        motor_cosphi_nom_fr=0.88,
        motor_slip_nom_fr=0.053,
        motor_id=2,
    )

    df = generate_dataframe(cfg, run_id=0, total_runs=1)

    expected = columns_for(ScenarioName.ESP_SYSTEM)
    assert list(df.columns) == expected
    assert len(df) == cfg.time_axis.n_points
