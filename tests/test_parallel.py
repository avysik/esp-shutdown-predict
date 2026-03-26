from __future__ import annotations

from pathlib import Path

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.parallel import run_batch


def test_parallel_generation_creates_all_files(tmp_path: Path) -> None:
    cfg = AppConfig.from_cli(
        scenario="pump-only",
        esp_id="1006",
        n_files=3,
        workers=2,
        output_dir=tmp_path,
        time_step="1H",
        n_points=5,
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
        u_surf_v=None,
        motor_u_nom_lin_v=None,
        motor_p_nom_kw=None,
        motor_f_nom_hz=None,
        motor_eff_nom_fr=None,
        motor_cosphi_nom_fr=None,
        motor_slip_nom_fr=None,
        motor_id=None,
    )

    summary = run_batch(cfg)
    assert summary.total == 3
    assert summary.failed_count == 0

    # Check files exist
    for r in summary.results:
        assert Path(r.output_path).exists()
