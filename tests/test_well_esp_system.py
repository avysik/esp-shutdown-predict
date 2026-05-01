from __future__ import annotations

from pathlib import Path

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.generation import generate_dataframe
from tests.helpers import artifact_dir


def _cfg(
    *,
    output_name: str,
    n_points: int = 4,
    ipr_mode: str = "linear-pi",
    productivity_index: float | None = 0.55,
    q_test_sm3day: float | None = None,
    p_res_atma: float = 250.0,
    control_plan_path: str | None = None,
) -> AppConfig:
    return AppConfig.from_cli(
        scenario="well-esp-system",
        esp_id="1006",
        n_files=1,
        workers=1,
        output_dir=artifact_dir(output_name),
        time_step="15min",
        n_points=n_points,
        esp_db_path=None,
        control_plan_path=None if control_plan_path is None else Path(control_plan_path),
        stage_num=250,
        pump_freq_hz=50.0,
        p_int_atma=None,
        t_int_C=None,
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
        ipr_mode=ipr_mode,
        p_res_atma=p_res_atma,
        productivity_index=productivity_index,
        q_test_sm3day=q_test_sm3day,
        p_test_atma=200.0,
        p_wh_atma=20.0,
        p_cas_atma=10.0,
        t_wf_C=80.0,
        t_surface_C=20.0,
        h_perf_m=1500.0,
        h_esp_m=1200.0,
        d_tub_mm=62.0,
        d_cas_mm=150.0,
        u_surf_v=1000.0,
        motor_u_nom_lin_v=1000.0,
        motor_p_nom_kw=45.0,
        motor_f_nom_hz=50.0,
        motor_eff_nom_fr=0.85,
        motor_cosphi_nom_fr=0.9,
        motor_slip_nom_fr=0.04,
        motor_id=2,
    )


def test_well_esp_system_generates_coupled_well_and_motor_outputs() -> None:
    df = generate_dataframe(_cfg(output_name="well_esp_static"), run_id=0, total_runs=1)

    assert {
        "ipr_mode",
        "productivity_index",
        "p_wf_atma",
        "drawdown_atma",
        "j_calc_sm3day_atma",
        "q_ipr_sm3day",
        "p_buf_atma",
        "ksep_total_d",
        "gas_fraction_pump_d",
        "motor_i_lin_a",
    }.issubset(df.columns)
    assert df["q_liq_sm3day"].iloc[0] > 0
    assert abs(df["p_buf_atma"].iloc[0] - 20.0) < 0.2
    assert df["p_int_atma"].iloc[0] > 0
    assert df["head_m"].iloc[0] > 0
    assert df["power_esp_w"].iloc[0] > 0
    assert df["motor_i_lin_a"].iloc[0] > 0
    assert df["ipr_mode"].iloc[0] == "linear-pi"
    assert abs(df["j_calc_sm3day_atma"].iloc[0] - df["productivity_index"].iloc[0]) < 1e-6
    assert abs(df["q_ipr_sm3day"].iloc[0] - df["q_liq_sm3day"].iloc[0]) < 1e-6


def test_well_esp_system_responds_to_productivity_index() -> None:
    df_low = generate_dataframe(_cfg(output_name="well_esp_low", productivity_index=0.40), run_id=0, total_runs=1)
    df_high = generate_dataframe(_cfg(output_name="well_esp_high", productivity_index=0.90), run_id=0, total_runs=1)

    assert df_high["q_liq_sm3day"].iloc[0] > df_low["q_liq_sm3day"].iloc[0]
    assert df_high["p_int_atma"].iloc[0] > df_low["p_int_atma"].iloc[0]
    assert df_high["motor_i_lin_a"].iloc[0] > df_low["motor_i_lin_a"].iloc[0]


def test_well_esp_system_keeps_legacy_vogel_test_point_mode() -> None:
    df_low = generate_dataframe(
        _cfg(
            output_name="well_esp_vogel_low",
            ipr_mode="vogel-test-point",
            productivity_index=None,
            q_test_sm3day=25.0,
        ),
        run_id=0,
        total_runs=1,
    )
    df_high = generate_dataframe(
        _cfg(
            output_name="well_esp_vogel_high",
            ipr_mode="vogel-test-point",
            productivity_index=None,
            q_test_sm3day=45.0,
        ),
        run_id=0,
        total_runs=1,
    )

    assert df_low["ipr_mode"].iloc[0] == "vogel-test-point"
    assert df_high["q_liq_sm3day"].iloc[0] > df_low["q_liq_sm3day"].iloc[0]


def test_well_esp_system_tracks_target_wellhead_pressure_across_demo_window() -> None:
    df = generate_dataframe(
        _cfg(
            output_name="well_esp_static",
            n_points=9,
            control_plan_path="examples/control_plan_well_productivity_decline_2h.json",
            productivity_index=0.55,
        ),
        run_id=0,
        total_runs=1,
    )

    assert len(df) == 9
    assert df["well_solver_ok"].all()
    assert df["wellhead_target_error_atma"].max() < 0.05
    assert (df["p_buf_atma"] - df["p_wh_target_atma"]).abs().max() < 0.05
