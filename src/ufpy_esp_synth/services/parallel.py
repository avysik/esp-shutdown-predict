from __future__ import annotations

import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from tqdm import tqdm

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.generation import TaskResult, worker_entry


@dataclass(frozen=True)
class BatchSummary:
    total: int
    ok_count: int
    failed_count: int
    duration_s: float
    results: list[TaskResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "ok_count": self.ok_count,
            "failed_count": self.failed_count,
            "duration_s": self.duration_s,
            "results": [
                {
                    "run_id": r.run_id,
                    "ok": r.ok,
                    "output_path": r.output_path,
                    "duration_s": r.duration_s,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def run_batch(cfg: AppConfig) -> BatchSummary:
    """
    Run generation in multiple isolated processes.
    One failed task does not crash the batch.
    """
    log = logging.getLogger("ufpy_esp_synth")
    t0 = time.perf_counter()

    cfg_dict = cfg.model_dump(mode="json")

    results: list[TaskResult] = []
    ok = 0
    fail = 0

    log.info(
        "Start batch: scenario=%s esp_id=%s files=%s workers=%s out=%s",
        cfg.scenario.value,
        cfg.pump.esp_id,
        cfg.generation.n_files,
        cfg.generation.workers,
        str(cfg.generation.output_dir),
    )

    with ProcessPoolExecutor(max_workers=cfg.generation.workers) as ex:
        futs = {
            ex.submit(worker_entry, cfg_dict, run_id, cfg.generation.n_files): run_id
            for run_id in range(cfg.generation.n_files)
        }

        for fut in tqdm(as_completed(futs), total=len(futs), desc="Generating files"):
            run_id = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                # This should be rare because worker_entry returns TaskResult on exceptions, but keep it safe.
                res = TaskResult(run_id=run_id, ok=False, output_path="", duration_s=0.0, error=repr(e))

            results.append(res)
            if res.ok:
                ok += 1
                log.info("OK run_id=%s path=%s duration=%.3fs", res.run_id, res.output_path, res.duration_s)
            else:
                fail += 1
                log.error("FAIL run_id=%s path=%s duration=%.3fs error=%s", res.run_id, res.output_path, res.duration_s, res.error)

    dt = time.perf_counter() - t0
    log.info("Batch finished: ok=%s failed=%s duration=%.3fs", ok, fail, dt)

    # deterministic ordering in summary
    results_sorted = sorted(results, key=lambda r: r.run_id)
    return BatchSummary(
        total=cfg.generation.n_files,
        ok_count=ok,
        failed_count=fail,
        duration_s=dt,
        results=results_sorted,
    )
