from __future__ import annotations

from pathlib import Path

import pytest

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.generation import TaskResult
from ufpy_esp_synth.services.parallel import run_batch
from tests.helpers import artifact_dir


def _cfg(*, workers: int, n_files: int, output_dir: Path) -> AppConfig:
    return AppConfig.from_cli(
        scenario="pump-only",
        esp_id="1006",
        n_files=n_files,
        workers=workers,
        output_dir=output_dir,
        time_step="1H",
        n_points=5,
        esp_db_path=None,
        control_plan_path=None,
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


def test_sequential_generation_creates_all_files() -> None:
    cfg = _cfg(workers=1, n_files=3, output_dir=artifact_dir("parallel_generation"))

    summary = run_batch(cfg)

    assert summary.total == 3
    assert summary.failed_count == 0
    for r in summary.results:
        assert Path(r.output_path).exists()


def test_parallel_falls_back_to_sequential_when_process_pool_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg(workers=2, n_files=2, output_dir=artifact_dir("parallel_fallback"))

    class BrokenExecutor:
        def __init__(self, *args, **kwargs) -> None:
            raise PermissionError("process pool blocked")

    def fake_worker_entry(cfg_dict: dict, run_id: int, total_runs: int) -> TaskResult:
        return TaskResult(
            run_id=run_id,
            ok=True,
            output_path=f"fake_{run_id}.parquet",
            telemetry_output_path=f"fake_{run_id}__telemetry.parquet",
            duration_s=0.01,
        )

    monkeypatch.setattr("ufpy_esp_synth.services.parallel.ProcessPoolExecutor", BrokenExecutor)
    monkeypatch.setattr("ufpy_esp_synth.services.parallel.worker_entry", fake_worker_entry)

    summary = run_batch(cfg)

    assert summary.total == 2
    assert summary.ok_count == 2
    assert summary.failed_count == 0
    assert [r.run_id for r in summary.results] == [0, 1]
