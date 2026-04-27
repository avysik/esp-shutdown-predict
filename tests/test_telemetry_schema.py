from __future__ import annotations

from pathlib import Path

import pandas as pd

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.domain.labels import (
    TELEMETRY_ACTIVE_POWER,
    TELEMETRY_COLUMNS,
    TELEMETRY_CURRENT,
    TELEMETRY_CURRENT_IMBALANCE,
    TELEMETRY_INTAKE_PRESSURE,
    TELEMETRY_INSULATION_RESISTANCE,
    TELEMETRY_LOAD,
    TELEMETRY_MOTOR_TEMPERATURE,
    TELEMETRY_POWER_FACTOR,
    TELEMETRY_RUN_ID,
    TELEMETRY_VALUE_DATE,
    TELEMETRY_VOLTAGE,
    TELEMETRY_VOLTAGE_IMBALANCE,
)
from ufpy_esp_synth.domain.telemetry_schema import make_telemetry_dataframe
from ufpy_esp_synth.services.generation import generate_dataframe, generate_one_file
from tests.helpers import artifact_dir


DEMO_PLAN = Path(__file__).resolve().parents[1] / "examples" / "control_plan_q_liq_windows_demo_2h.json"


def _cfg(output_dir: Path) -> AppConfig:
    return AppConfig.from_cli(
        scenario="esp-system",
        esp_id="1006",
        n_files=1,
        workers=1,
        output_dir=output_dir,
        time_step="15min",
        n_points=36,
        esp_db_path=None,
        control_plan_path=DEMO_PLAN,
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


def test_telemetry_dataframe_maps_expected_columns() -> None:
    df = generate_dataframe(_cfg(artifact_dir("telemetry_schema")), run_id=0, total_runs=1)
    telemetry = make_telemetry_dataframe(df)

    assert list(telemetry.columns) == TELEMETRY_COLUMNS
    assert telemetry[TELEMETRY_RUN_ID].iloc[0] == df["run_id"].iloc[0]
    assert telemetry[TELEMETRY_VALUE_DATE].iloc[0] == df["value_date"].iloc[0]
    assert telemetry[TELEMETRY_ACTIVE_POWER].iloc[0] == df["motor_p_electr_kw"].iloc[0]
    assert telemetry[TELEMETRY_VOLTAGE_IMBALANCE].isna().all()
    assert telemetry[TELEMETRY_CURRENT_IMBALANCE].isna().all()
    assert telemetry[TELEMETRY_LOAD].iloc[0] == df["motor_load_d"].iloc[0]
    assert telemetry[TELEMETRY_POWER_FACTOR].iloc[0] == df["motor_cosphi"].iloc[0]
    assert telemetry[TELEMETRY_VOLTAGE].iloc[0] == df["motor_u_lin_v"].iloc[0]
    assert telemetry[TELEMETRY_INTAKE_PRESSURE].iloc[0] == df["p_int_atma"].iloc[0]
    assert telemetry[TELEMETRY_INSULATION_RESISTANCE].isna().all()
    assert telemetry[TELEMETRY_MOTOR_TEMPERATURE].isna().all()
    assert telemetry[TELEMETRY_CURRENT].iloc[0] == df["motor_i_lin_a"].iloc[0]


def test_generate_one_file_writes_telemetry_parquet() -> None:
    out_dir = artifact_dir("telemetry_export")
    result = generate_one_file(_cfg(out_dir), run_id=0, total_runs=1)

    assert result.ok is True
    assert Path(result.output_path).exists()
    assert Path(result.telemetry_output_path).exists()

    telemetry_df = pd.read_parquet(result.telemetry_output_path)
    assert list(telemetry_df.columns) == TELEMETRY_COLUMNS
