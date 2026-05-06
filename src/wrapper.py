from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.fleet import SEVERITY_LEVELS, run_fleet_generation
from ufpy_esp_synth.services.parallel import BatchSummary, run_batch


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = Path(__file__).resolve().parent
DB_PATH = SRC_DIR / "data" / "esp_db.json"
SCENARIO_LIBRARY_DIR = ROOT_DIR / "examples" / "scenario_library"
OUTPUT_BASE_DIR = ROOT_DIR / "out_scenario_library"
CATALOG_PATH = SCENARIO_LIBRARY_DIR / "catalog.json"
ARCHETYPE_LIBRARY_PATH = ROOT_DIR / "examples" / "fleet_archetypes" / "well_esp_archetypes_v1.json"
FLEET_OUTPUT_BASE_DIR = ROOT_DIR / "out_fleet_dataset"


@dataclass(frozen=True)
class LibraryRunResult:
    scenario_file: str
    output_dir: str
    ok_count: int
    failed_count: int
    duration_s: float


def _load_catalog_order() -> list[str]:
    if not CATALOG_PATH.exists():
        return []

    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    ordered: list[str] = []
    for family in payload.get("families", []):
        ordered.extend(str(name) for name in family.get("files", []))
    return ordered


def _iter_scenario_files(scenario_dir: Path) -> list[Path]:
    catalog_names = _load_catalog_order()
    if not catalog_names:
        return sorted(p for p in scenario_dir.glob("*.json") if p.name != "catalog.json")

    paths: list[Path] = []
    seen: set[str] = set()
    for name in catalog_names:
        path = scenario_dir / name
        if path.exists():
            paths.append(path)
            seen.add(path.name)

    for path in sorted(p for p in scenario_dir.glob("*.json") if p.name not in seen and p.name != "catalog.json"):
        paths.append(path)
    return paths


def _base_cli_kwargs(*, output_dir: Path, control_plan_path: Path, n_files: int, workers: int) -> dict[str, Any]:
    return {
        "scenario": "well-esp-system",
        "esp_id": "1006",
        "n_files": n_files,
        "workers": workers,
        "output_dir": output_dir,
        "time_step": "15min",
        "n_points": 9,
        "esp_db_path": DB_PATH,
        "control_plan_path": control_plan_path,
        "stage_num": 250,
        "pump_freq_hz": 50.0,
        "p_int_atma": None,
        "t_int_C": None,
        "gamma_g": 0.7,
        "gamma_o": 0.86,
        "gamma_w": 1.0,
        "rsb_m3m3": 100.0,
        "rp_m3m3": 100.0,
        "pb_atma": 130.0,
        "t_res_C": 80.0,
        "bob_m3m3": 1.2,
        "muob_cP": 1.5,
        "fw_fr": None,
        "fw_perc": 30.0,
        "q_gas_free_sm3day": 0.0,
        "ipr_mode": "linear-pi",
        "p_res_atma": 250.0,
        "productivity_index": 0.55,
        "q_test_sm3day": None,
        "p_test_atma": 200.0,
        "p_wh_atma": 20.0,
        "p_cas_atma": 10.0,
        "t_wf_C": 80.0,
        "t_surface_C": 20.0,
        "h_perf_m": 1500.0,
        "h_esp_m": 1200.0,
        "d_tub_mm": 62.0,
        "d_cas_mm": 150.0,
        "u_surf_v": 1000.0,
        "motor_u_nom_lin_v": 1000.0,
        "motor_p_nom_kw": 45.0,
        "motor_f_nom_hz": 50.0,
        "motor_eff_nom_fr": 0.85,
        "motor_cosphi_nom_fr": 0.9,
        "motor_slip_nom_fr": 0.04,
        "motor_id": 2,
    }


def _summary_to_payload(summary: BatchSummary) -> dict[str, Any]:
    return summary.to_dict()


def run_scenario_library(
    *,
    scenario_dir: Path = SCENARIO_LIBRARY_DIR,
    output_base_dir: Path = OUTPUT_BASE_DIR,
    n_files: int = 1,
    workers: int = 1,
    limit: int | None = None,
    scenario_name_contains: str | None = None,
) -> list[LibraryRunResult]:
    scenario_files = _iter_scenario_files(scenario_dir)

    if scenario_name_contains:
        token = scenario_name_contains.lower()
        scenario_files = [path for path in scenario_files if token in path.stem.lower()]

    if limit is not None:
        scenario_files = scenario_files[:limit]

    output_base_dir.mkdir(parents=True, exist_ok=True)
    results: list[LibraryRunResult] = []
    summary_payload: dict[str, Any] = {
        "scenario_dir": str(scenario_dir),
        "output_base_dir": str(output_base_dir),
        "total_scenarios": len(scenario_files),
        "scenarios": [],
    }

    for scenario_path in scenario_files:
        scenario_output_dir = output_base_dir / scenario_path.stem
        scenario_output_dir.mkdir(parents=True, exist_ok=True)

        print(f"[RUN] {scenario_path.name} -> {scenario_output_dir}")

        cfg = AppConfig.from_cli(
            **_base_cli_kwargs(
                output_dir=scenario_output_dir,
                control_plan_path=scenario_path,
                n_files=n_files,
                workers=workers,
            )
        )
        summary = run_batch(cfg)

        results.append(
            LibraryRunResult(
                scenario_file=scenario_path.name,
                output_dir=str(scenario_output_dir),
                ok_count=summary.ok_count,
                failed_count=summary.failed_count,
                duration_s=summary.duration_s,
            )
        )
        summary_payload["scenarios"].append(
            {
                "scenario_file": scenario_path.name,
                "output_dir": str(scenario_output_dir),
                "batch_summary": _summary_to_payload(summary),
            }
        )

    summary_path = output_base_dir / "_scenario_library_summary.json"
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] Summary written to {summary_path}")
    return results


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run either the curated ESP scenario-library JSON files or the fleet-scale archetype generator."
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=("scenario-library", "fleet"),
        default="scenario-library",
        help="Execution mode.",
    )
    parser.add_argument(
        "--scenario-dir",
        type=Path,
        default=SCENARIO_LIBRARY_DIR,
        help="Directory containing scenario JSON files for scenario-library mode.",
    )
    parser.add_argument(
        "--output-base-dir",
        type=Path,
        default=OUTPUT_BASE_DIR,
        help="Base output directory. In scenario-library mode each scenario gets its own subdirectory.",
    )
    parser.add_argument(
        "--n-files",
        type=int,
        default=1,
        help="Number of parquet files to generate per scenario.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Worker count for each scenario batch.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for quick smoke runs.",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Optional case-insensitive substring filter by scenario filename.",
    )
    parser.add_argument(
        "--archetype-library-path",
        type=Path,
        default=ARCHETYPE_LIBRARY_PATH,
        help="Fleet archetype-library JSON for fleet mode.",
    )
    parser.add_argument(
        "--samples-per-archetype",
        type=int,
        default=2,
        help="Accepted base samples to generate per archetype in fleet mode.",
    )
    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=4,
        help="How many deterministic LHS candidates to try per accepted fleet base sample.",
    )
    parser.add_argument(
        "--archetype-filter",
        type=str,
        default=None,
        help="Optional case-insensitive substring filter by archetype id or name in fleet mode.",
    )
    parser.add_argument(
        "--severities",
        type=str,
        default=",".join(SEVERITY_LEVELS),
        help="Comma-separated severity list for fleet mode.",
    )
    parser.add_argument(
        "--recommended-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use only the recommended scenario families for each archetype in fleet mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build fleet manifests and control plans without running ufpy generation.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.mode == "scenario-library":
        results = run_scenario_library(
            scenario_dir=args.scenario_dir,
            output_base_dir=args.output_base_dir,
            n_files=args.n_files,
            workers=args.workers,
            limit=args.limit,
            scenario_name_contains=args.filter,
        )

        total = len(results)
        ok = sum(1 for item in results if item.failed_count == 0)
        failed = total - ok
        print(f"[SUMMARY] scenarios={total} fully_ok={ok} failed={failed}")
        for item in results:
            print(
                f"  - {item.scenario_file}: ok_count={item.ok_count} "
                f"failed_count={item.failed_count} duration_s={item.duration_s:.2f}"
            )
        return 0 if failed == 0 else 1

    severity_values = tuple(
        token.strip().lower()
        for token in args.severities.split(",")
        if token.strip()
    )
    unknown = [value for value in severity_values if value not in SEVERITY_LEVELS]
    if unknown:
        parser.error(f"Unknown severity values: {', '.join(unknown)}")

    fleet_output_dir = args.output_base_dir if args.output_base_dir != OUTPUT_BASE_DIR else FLEET_OUTPUT_BASE_DIR
    summary = run_fleet_generation(
        archetype_library_path=args.archetype_library_path,
        esp_db_path=DB_PATH,
        output_base_dir=fleet_output_dir,
        samples_per_archetype=args.samples_per_archetype,
        workers=args.workers,
        candidate_multiplier=args.candidate_multiplier,
        archetype_filter=args.archetype_filter,
        scenario_filter=args.filter,
        include_severities=severity_values,
        recommended_only=bool(args.recommended_only),
        dry_run=bool(args.dry_run),
        max_windows=args.limit,
    )
    print(
        f"[SUMMARY] windows={summary.total_windows} ok={summary.ok_count} "
        f"failed={summary.failed_count} duration_s={summary.duration_s:.2f}"
    )
    print(f"[SUMMARY] manifest={summary.manifest_path}")
    print(f"[SUMMARY] summary={summary.summary_path}")
    return 0 if summary.failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
