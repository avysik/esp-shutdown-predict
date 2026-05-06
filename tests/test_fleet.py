from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from ufpy_esp_synth.domain.fleet import load_fleet_archetype_library
from ufpy_esp_synth.services.fleet import (
    BaseStateCandidate,
    PumpSelection,
    SampledBaseState,
    build_archetype_base_states,
    build_control_plan_payload,
    deterministic_latin_hypercube,
    load_pump_catalog,
    run_fleet_generation,
    select_pump_for_sample,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
ARCHETYPE_LIBRARY_PATH = ROOT_DIR / "examples" / "fleet_archetypes" / "well_esp_archetypes_v1.json"
ESP_DB_PATH = ROOT_DIR / "src" / "data" / "esp_db.json"
ARTIFACT_ROOT = ROOT_DIR / "tests" / "data" / "fleet_artifacts"


def fleet_artifact_dir(name: str) -> Path:
    path = ARTIFACT_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _base_state_candidate() -> BaseStateCandidate:
    sample = SampledBaseState(
        archetype_id="A03",
        sample_index=0,
        q_liq_target_sm3day=70.0,
        p_int_target_atma=34.0,
        p_wh_atma=20.0,
        h_esp_m=2500.0,
        h_perf_m=2750.0,
        d_tub_mm=62.0,
        d_cas_mm=150.0,
        p_res_atma=250.0,
        productivity_index=0.55,
        fw_perc=30.0,
        muob_cP=1.5,
        u_surf_v=1000.0,
        pump_nominal_rate_target_sm3day=90.0,
        pump_nominal_head_target_m=2200.0,
        motor_nominal_power_target_kw=63.0,
    )
    pump = PumpSelection(
        esp_id="1006",
        stage_num=250,
        pump_freq_hz=50.0,
        rate_nom_sm3day=100.0,
        total_head_target_m=2200.0,
        total_power_target_kw=30.0,
        motor_nominal_power_kw=45.0,
        motor_nominal_voltage_v=1000.0,
    )
    return BaseStateCandidate(
        sample=sample,
        pump=pump,
        stable_row={
            "q_liq_sm3day": 68.0,
            "p_int_atma": 32.0,
            "well_solver_ok": True,
            "head_m": 1200.0,
            "motor_p_electr_kw": 29.0,
        },
    )


def test_load_fleet_archetype_library_reads_expected_archetypes() -> None:
    library = load_fleet_archetype_library(ARCHETYPE_LIBRARY_PATH)

    assert library.library_name == "well_esp_fleet_archetypes_v1"
    assert len(library.archetypes) >= 10
    assert library.get_archetype("A03").name == "balanced_medium_rate"
    assert library.global_guidance.fast_window_default.points == 9
    assert library.global_guidance.slow_window_default.points == 9


def test_deterministic_latin_hypercube_is_repeatable_and_stratified() -> None:
    lhs = deterministic_latin_hypercube(n_samples=5, dimensions=3, salt="fleet-test")
    lhs_again = deterministic_latin_hypercube(n_samples=5, dimensions=3, salt="fleet-test")

    assert lhs == lhs_again
    for dim in range(3):
        strata = sorted(int(math.floor(row[dim] * 5)) for row in lhs)
        assert strata == [0, 1, 2, 3, 4]


def test_select_pump_for_sample_returns_valid_selection() -> None:
    catalog = load_pump_catalog(str(ESP_DB_PATH.resolve()))

    selection = select_pump_for_sample(
        catalog=catalog,
        d_cas_mm=160.0,
        target_rate_nom_sm3day=90.0,
        target_head_nom_m=2200.0,
        target_motor_power_kw=63.0,
        u_surf_v=1000.0,
    )

    assert selection.esp_id
    assert selection.stage_num >= 1
    assert selection.pump_freq_hz > 0.0
    assert selection.motor_nominal_power_kw >= selection.total_power_target_kw


def test_build_control_plan_payload_for_backpressure_has_nine_segments() -> None:
    payload = build_control_plan_payload(
        base_state=_base_state_candidate(),
        family="wellhead_backpressure_growth",
        severity="medium",
        duration="2h",
        points=9,
        time_step="15min",
        label="A03__sample_0000__wellhead_backpressure_growth__medium",
    )

    segments = payload["segments"]
    values = [segment["p_wh_atma"] for segment in segments]

    assert len(segments) == 9
    assert values[0] == 20.0
    assert values[1] == 20.0
    assert values[-1] > values[0]


def test_run_fleet_generation_dry_run_creates_manifest_and_control_plan() -> None:
    output_dir = fleet_artifact_dir("fleet_dry_run")

    summary = run_fleet_generation(
        archetype_library_path=ARCHETYPE_LIBRARY_PATH,
        esp_db_path=ESP_DB_PATH,
        output_base_dir=output_dir,
        samples_per_archetype=1,
        workers=1,
        candidate_multiplier=12,
        archetype_filter="A03",
        scenario_filter="stable",
        recommended_only=True,
        dry_run=True,
        max_windows=1,
    )

    manifest_path = Path(summary.manifest_path)
    assert summary.total_windows == 1
    assert manifest_path.exists()

    manifest = pd.read_parquet(manifest_path)
    assert len(manifest) == 1
    control_plan_path = Path(manifest.loc[0, "control_plan_path"])
    assert control_plan_path.exists()
    payload = json.loads(control_plan_path.read_text(encoding="utf-8"))
    assert "base" in payload


def test_a06_accepts_at_least_one_base_state_after_restriction() -> None:
    library = load_fleet_archetype_library(ARCHETYPE_LIBRARY_PATH)
    archetype = library.get_archetype("A06")

    accepted = build_archetype_base_states(
        archetype=archetype,
        esp_db_path=ESP_DB_PATH,
        accepted_samples=1,
        candidate_multiplier=12,
        temp_output_dir=fleet_artifact_dir("fleet_a06_calibration"),
    )

    assert len(accepted) == 1


def test_run_fleet_generation_single_window_creates_outputs() -> None:
    output_dir = fleet_artifact_dir("fleet_single_window")

    summary = run_fleet_generation(
        archetype_library_path=ARCHETYPE_LIBRARY_PATH,
        esp_db_path=ESP_DB_PATH,
        output_base_dir=output_dir,
        samples_per_archetype=1,
        workers=1,
        candidate_multiplier=12,
        archetype_filter="A03",
        scenario_filter="stable",
        recommended_only=True,
        dry_run=False,
        max_windows=1,
    )

    assert summary.total_windows == 1
    assert summary.ok_count == 1
    assert summary.failed_count == 0
    assert Path(summary.manifest_path).exists()
    assert Path(summary.summary_path).exists()
    assert Path(summary.results[0].output_path).exists()
    assert Path(summary.results[0].telemetry_output_path).exists()
