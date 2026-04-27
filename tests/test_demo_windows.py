from __future__ import annotations

from pathlib import Path

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.generation import generate_dataframe
from tests.helpers import artifact_dir


PLAN_PATH = Path(__file__).resolve().parents[1] / "examples" / "control_plan_q_liq_windows_demo_2h.json"


def test_demo_control_plan_has_four_windows_of_nine_points() -> None:
    cfg = AppConfig.from_cli(
        scenario="esp-system",
        esp_id="1006",
        n_files=1,
        workers=1,
        output_dir=artifact_dir("demo_windows"),
        time_step="15min",
        n_points=36,
        esp_db_path=None,
        control_plan_path=PLAN_PATH,
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
        q_gas_free_sm3day=0.0,
        u_surf_v=1000.0,
        motor_u_nom_lin_v=1000.0,
        motor_p_nom_kw=45.0,
        motor_f_nom_hz=50.0,
        motor_eff_nom_fr=0.85,
        motor_cosphi_nom_fr=0.9,
        motor_slip_nom_fr=0.04,
        motor_id=2,
    )

    df = generate_dataframe(cfg, run_id=0, total_runs=1)

    counts = df.groupby("control_label", sort=False).size().to_dict()
    assert len(df) == 36
    assert len(counts) == 4
    assert set(counts.values()) == {9}
    assert list(counts) == [
        "window_0000_q_decline_demo",
        "window_0001_q_growth_demo",
        "window_0002_q_decline_soft_demo",
        "window_0003_q_growth_soft_demo",
    ]

    first_window = df[df["control_label"] == "window_0000_q_decline_demo"].reset_index(drop=True)
    span_minutes = (first_window["value_date"].iloc[-1] - first_window["value_date"].iloc[0]).total_seconds() / 60.0
    assert span_minutes == 120.0
