from __future__ import annotations

import hashlib
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.domain.fleet import (
    FleetArchetype,
    FleetArchetypeLibrary,
    FloatRange,
    GlobalGuidance,
    load_fleet_archetype_library,
    scale_range_value,
)
from ufpy_esp_synth.services.generation import generate_dataframe, generate_one_file


FAST_SCENARIO_FAMILIES = ("stable_normal", "inflow_deterioration", "wellhead_backpressure_growth", "voltage_sag")
SLOW_SCENARIO_FAMILIES = ("watercut_growth", "viscosity_growth")
SEVERITY_LEVELS = ("mild", "medium", "severe")
CHANGE_PROGRESS = (0.0, 0.0, 0.18, 0.38, 0.58, 0.78, 1.0, 1.0, 1.0)


@dataclass(frozen=True)
class SampledBaseState:
    archetype_id: str
    sample_index: int
    q_liq_target_sm3day: float
    p_int_target_atma: float
    p_wh_atma: float
    h_esp_m: float
    h_perf_m: float
    d_tub_mm: float
    d_cas_mm: float
    p_res_atma: float
    productivity_index: float
    fw_perc: float
    muob_cP: float
    u_surf_v: float
    pump_nominal_rate_target_sm3day: float
    pump_nominal_head_target_m: float
    motor_nominal_power_target_kw: float


@dataclass(frozen=True)
class PumpSelection:
    esp_id: str
    stage_num: int
    pump_freq_hz: float
    rate_nom_sm3day: float
    total_head_target_m: float
    total_power_target_kw: float
    motor_nominal_power_kw: float
    motor_nominal_voltage_v: float


@dataclass(frozen=True)
class BaseStateCandidate:
    sample: SampledBaseState
    pump: PumpSelection
    stable_row: dict[str, Any]


@dataclass(frozen=True)
class WindowDefinition:
    window_id: str
    archetype_id: str
    archetype_name: str
    sample_index: int
    scenario_family: str
    severity: str
    duration: str
    points: int
    time_step: str
    output_dir: Path
    control_plan_path: Path
    config: AppConfig
    base_state: BaseStateCandidate


@dataclass(frozen=True)
class FleetWindowResult:
    window_id: str
    archetype_id: str
    scenario_family: str
    severity: str
    ok: bool
    output_path: str
    telemetry_output_path: str
    duration_s: float
    error: str


@dataclass(frozen=True)
class FleetSummary:
    total_windows: int
    ok_count: int
    failed_count: int
    duration_s: float
    manifest_path: str
    summary_path: str
    archetype_stats: list[dict[str, Any]]
    results: list[FleetWindowResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_windows": self.total_windows,
            "ok_count": self.ok_count,
            "failed_count": self.failed_count,
            "duration_s": self.duration_s,
            "manifest_path": self.manifest_path,
            "summary_path": self.summary_path,
            "archetype_stats": self.archetype_stats,
            "results": [asdict(item) for item in self.results],
        }


@dataclass(frozen=True)
class PumpCatalogEntry:
    esp_id: str
    rate_nom_sm3day: float
    rate_opt_min_sm3day: float
    rate_opt_max_sm3day: float
    rate_max_sm3day: float
    stages_max: int
    freq_hz: float
    d_cas_min_mm: float
    head_per_stage_nom_m: float
    power_per_stage_nom_kw: float
    power_limit_shaft_max_kw: float


def _stable_hash_int(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _coprime_stride(n_samples: int, seed: int) -> int:
    if n_samples <= 1:
        return 1
    stride = max(1, seed % n_samples)
    while math.gcd(stride, n_samples) != 1:
        stride += 1
    return stride


def deterministic_latin_hypercube(*, n_samples: int, dimensions: int, salt: str) -> list[list[float]]:
    if n_samples <= 0:
        raise ValueError("n_samples must be positive.")
    if dimensions <= 0:
        raise ValueError("dimensions must be positive.")
    if n_samples == 1:
        return [[0.5] * dimensions]

    rows = [[0.0] * dimensions for _ in range(n_samples)]
    for dim in range(dimensions):
        seed = _stable_hash_int(f"{salt}:{dim}")
        offset = seed % n_samples
        stride = _coprime_stride(n_samples, seed // max(1, n_samples))
        for sample_idx in range(n_samples):
            stratum = (offset + stride * sample_idx) % n_samples
            rows[sample_idx][dim] = (float(stratum) + 0.5) / float(n_samples)
    return rows


def _linear_interpolate(xs: list[float], ys: list[float], x_value: float) -> float:
    if not xs or not ys or len(xs) != len(ys):
        raise ValueError("Interpolation points are inconsistent.")
    if len(xs) == 1:
        return float(ys[0])

    if x_value <= xs[0]:
        return float(ys[0])
    if x_value >= xs[-1]:
        return float(ys[-1])

    for idx in range(1, len(xs)):
        x_lo = float(xs[idx - 1])
        x_hi = float(xs[idx])
        if x_value <= x_hi:
            y_lo = float(ys[idx - 1])
            y_hi = float(ys[idx])
            if x_hi == x_lo:
                return y_hi
            ratio = (float(x_value) - x_lo) / (x_hi - x_lo)
            return y_lo + (y_hi - y_lo) * ratio

    return float(ys[-1])


@lru_cache(maxsize=8)
def load_pump_catalog(db_path: str) -> tuple[PumpCatalogEntry, ...]:
    payload = json.loads(Path(db_path).read_text(encoding="utf-8"))
    entries: list[PumpCatalogEntry] = []

    for esp_id, raw in payload.items():
        rate_points = [float(value) for value in raw.get("rate_points", [])]
        head_points = [float(value) for value in raw.get("head_points", [])]
        power_points = [float(value) for value in raw.get("power_points", [])]
        rate_nom = float(raw.get("rate_nom_sm3day") or 0.0)
        stages_max = int(raw.get("stages_max") or 0)
        if rate_nom <= 0.0 or stages_max <= 0 or not rate_points or not head_points or not power_points:
            continue

        head_per_stage_nom = _linear_interpolate(rate_points, head_points, rate_nom)
        power_per_stage_nom = _linear_interpolate(rate_points, power_points, rate_nom)
        if head_per_stage_nom <= 0.0 or power_per_stage_nom <= 0.0:
            continue

        entries.append(
            PumpCatalogEntry(
                esp_id=str(esp_id),
                rate_nom_sm3day=rate_nom,
                rate_opt_min_sm3day=float(raw.get("rate_opt_min_sm3day") or rate_nom),
                rate_opt_max_sm3day=float(raw.get("rate_opt_max_sm3day") or rate_nom),
                rate_max_sm3day=float(raw.get("rate_max_sm3day") or rate_nom),
                stages_max=stages_max,
                freq_hz=float(raw.get("freq_Hz") or 50.0),
                d_cas_min_mm=float(raw.get("d_cas_min_mm") or 0.0),
                head_per_stage_nom_m=head_per_stage_nom,
                power_per_stage_nom_kw=power_per_stage_nom,
                power_limit_shaft_max_kw=float(raw.get("power_limit_shaft_max_kW") or raw.get("power_limit_shaft_high_kW") or raw.get("power_limit_shaft_kW") or 0.0),
            )
        )

    if not entries:
        raise ValueError(f"No usable pump entries found in DB: {db_path}")
    return tuple(entries)


def select_pump_for_sample(
    *,
    catalog: tuple[PumpCatalogEntry, ...],
    d_cas_mm: float,
    target_rate_nom_sm3day: float,
    target_head_nom_m: float,
    target_motor_power_kw: float,
    u_surf_v: float,
) -> PumpSelection:
    compatible = [entry for entry in catalog if entry.d_cas_min_mm <= d_cas_mm + 1e-9]
    candidates = compatible if compatible else list(catalog)

    best_selection: PumpSelection | None = None
    best_score: float | None = None

    for entry in candidates:
        stage_num = int(round(target_head_nom_m / entry.head_per_stage_nom_m))
        stage_num = max(1, min(stage_num, entry.stages_max))
        total_head = entry.head_per_stage_nom_m * stage_num
        total_power = entry.power_per_stage_nom_kw * stage_num
        if entry.power_limit_shaft_max_kw > 0.0 and total_power > entry.power_limit_shaft_max_kw * 1.02:
            continue

        rate_score = abs(entry.rate_nom_sm3day - target_rate_nom_sm3day) / max(target_rate_nom_sm3day, 1.0)
        head_score = abs(total_head - target_head_nom_m) / max(target_head_nom_m, 1.0)
        power_score = abs(total_power - target_motor_power_kw) / max(target_motor_power_kw, 1.0)
        oversize_penalty = 0.0 if total_power <= target_motor_power_kw * 1.35 else 0.25
        score = rate_score + head_score + 0.5 * power_score + oversize_penalty

        motor_nominal_power_kw = max(target_motor_power_kw, total_power / 0.82)
        motor_nominal_voltage_v = max(400.0, round(float(u_surf_v) / 50.0) * 50.0)
        selection = PumpSelection(
            esp_id=entry.esp_id,
            stage_num=stage_num,
            pump_freq_hz=entry.freq_hz if entry.freq_hz > 0.0 else 50.0,
            rate_nom_sm3day=entry.rate_nom_sm3day,
            total_head_target_m=total_head,
            total_power_target_kw=total_power,
            motor_nominal_power_kw=float(motor_nominal_power_kw),
            motor_nominal_voltage_v=float(motor_nominal_voltage_v),
        )
        if best_score is None or score < best_score:
            best_score = score
            best_selection = selection

    if best_selection is None:
        raise ValueError("Could not select a compatible ESP pump for sampled archetype state.")
    return best_selection


def _window_spec_for_family(guidance: GlobalGuidance, family: str) -> tuple[str, int, str]:
    if family in guidance.fast_window_default.use_for:
        spec = guidance.fast_window_default
    elif family in guidance.slow_window_default.use_for:
        spec = guidance.slow_window_default
    elif family in FAST_SCENARIO_FAMILIES:
        spec = guidance.fast_window_default
    else:
        spec = guidance.slow_window_default
    return spec.duration, spec.points, spec.time_step


def _family_end_value(
    *,
    family: str,
    severity: str,
    base_state: BaseStateCandidate,
) -> float:
    sample = base_state.sample
    severity_index = {"mild": 0, "medium": 1, "severe": 2}[severity]

    if family == "inflow_deterioration":
        factors = (0.93, 0.82, 0.68)
        return sample.productivity_index * factors[severity_index]
    if family == "wellhead_backpressure_growth":
        deltas = (2.0, 4.5, 7.0)
        return sample.p_wh_atma + deltas[severity_index]
    if family == "watercut_growth":
        deltas = (6.0, 12.0, 20.0)
        return min(97.0, sample.fw_perc + deltas[severity_index])
    if family == "viscosity_growth":
        deltas = (0.4, 0.9, 1.5)
        return min(8.0, sample.muob_cP + deltas[severity_index])
    if family == "voltage_sag":
        factors = (0.975, 0.95, 0.90)
        return sample.u_surf_v * factors[severity_index]
    raise ValueError(f"Unsupported scenario family: {family}")


def _value_for_progress(base_value: float, end_value: float, progress: float) -> float:
    return float(base_value) + (float(end_value) - float(base_value)) * float(progress)


def _phase_reason(family: str, point_index: int) -> str:
    if point_index < 2:
        return "baseline_stable_regime"
    if point_index < 6:
        return f"progressive_{family}"
    return f"new_{family}_plateau"


def build_control_plan_payload(
    *,
    base_state: BaseStateCandidate,
    family: str,
    severity: str,
    duration: str,
    points: int,
    time_step: str,
    label: str,
) -> dict[str, Any]:
    sample = base_state.sample
    base_payload: dict[str, Any] = {
        "label": label,
        "reason": family,
        "p_res_atma": sample.p_res_atma,
        "productivity_index": sample.productivity_index,
        "p_test_atma": max(sample.p_res_atma - max(35.0, min(60.0, sample.p_res_atma * 0.2)), 1.0),
        "p_wh_atma": sample.p_wh_atma,
        "p_cas_atma": 10.0,
        "t_wf_C": 80.0,
        "pump_freq_hz": base_state.pump.pump_freq_hz,
        "u_surf_v": sample.u_surf_v,
        "rp_m3m3": 100.0,
        "muob_cP": sample.muob_cP,
        "fw_perc": sample.fw_perc,
        "q_gas_free_sm3day": 0.0,
    }

    if family == "stable_normal":
        return {"base": base_payload, "segments": []}

    step = pd.to_timedelta(time_step)
    if points != len(CHANGE_PROGRESS):
        raise ValueError("Scenario builder expects nine points per window.")

    end_value = _family_end_value(family=family, severity=severity, base_state=base_state)
    family_to_key = {
        "inflow_deterioration": "productivity_index",
        "wellhead_backpressure_growth": "p_wh_atma",
        "watercut_growth": "fw_perc",
        "viscosity_growth": "muob_cP",
        "voltage_sag": "u_surf_v",
    }
    metric_key = family_to_key[family]
    base_value = float(base_payload[metric_key])
    segments: list[dict[str, Any]] = []

    for point_index, progress in enumerate(CHANGE_PROGRESS):
        start = step * point_index
        end = start + step
        value = _value_for_progress(base_value, end_value, progress)
        segment = {
            "start": _format_timedelta(start),
            "end": _format_timedelta(end),
            "label": label,
            "reason": _phase_reason(family, point_index),
            metric_key: value,
        }
        segments.append(segment)

    return {"base": base_payload, "segments": segments}


def _format_timedelta(delta: pd.Timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)
    return f"{total_minutes}min"


def _sampled_input_dimensions(archetype: FleetArchetype) -> list[tuple[str, FloatRange]]:
    base = archetype.base_input_ranges
    pump = archetype.pump_selection_targets
    return [
        ("q_liq_target_sm3day", base.q_liq_target_sm3day),
        ("p_int_atma", base.p_int_atma),
        ("p_wh_atma", base.p_wh_atma),
        ("h_esp_m", base.h_esp_m),
        ("h_perf_minus_h_esp_m", base.h_perf_minus_h_esp_m),
        ("d_tub_mm", base.d_tub_mm),
        ("d_cas_mm", base.d_cas_mm),
        ("p_res_atma", base.p_res_atma),
        ("productivity_index", base.productivity_index),
        ("fw_perc", base.fw_perc),
        ("muob_cP", base.muob_cP),
        ("u_surf_v", base.u_surf_v),
        ("pump_nominal_rate_target_sm3day", pump.pump_nominal_rate_sm3day),
        ("pump_nominal_head_target_m", pump.pump_nominal_head_m),
        ("motor_nominal_power_target_kw", pump.motor_nominal_power_kw),
    ]


def sample_archetype_states(*, archetype: FleetArchetype, n_samples: int) -> list[SampledBaseState]:
    dims = _sampled_input_dimensions(archetype)
    unit_rows = deterministic_latin_hypercube(
        n_samples=n_samples,
        dimensions=len(dims),
        salt=f"fleet:{archetype.id}",
    )
    sampled_states: list[SampledBaseState] = []
    for sample_index, unit_values in enumerate(unit_rows):
        values = {
            name: scale_range_value(bounds, unit_values[idx])
            for idx, (name, bounds) in enumerate(dims)
        }
        h_esp = values["h_esp_m"]
        h_perf = h_esp + values["h_perf_minus_h_esp_m"]
        sampled_states.append(
            SampledBaseState(
                archetype_id=archetype.id,
                sample_index=sample_index,
                q_liq_target_sm3day=values["q_liq_target_sm3day"],
                p_int_target_atma=values["p_int_atma"],
                p_wh_atma=values["p_wh_atma"],
                h_esp_m=h_esp,
                h_perf_m=h_perf,
                d_tub_mm=values["d_tub_mm"],
                d_cas_mm=values["d_cas_mm"],
                p_res_atma=values["p_res_atma"],
                productivity_index=values["productivity_index"],
                fw_perc=values["fw_perc"],
                muob_cP=values["muob_cP"],
                u_surf_v=values["u_surf_v"],
                pump_nominal_rate_target_sm3day=values["pump_nominal_rate_target_sm3day"],
                pump_nominal_head_target_m=values["pump_nominal_head_target_m"],
                motor_nominal_power_target_kw=values["motor_nominal_power_target_kw"],
            )
        )
    return sampled_states


def _build_stable_cfg(
    *,
    sample: SampledBaseState,
    pump: PumpSelection,
    esp_db_path: Path,
    output_dir: Path,
) -> AppConfig:
    return AppConfig.from_cli(
        scenario="well-esp-system",
        esp_id=pump.esp_id,
        n_files=1,
        workers=1,
        output_dir=output_dir,
        time_step="15min",
        n_points=1,
        esp_db_path=esp_db_path,
        control_plan_path=None,
        stage_num=pump.stage_num,
        pump_freq_hz=pump.pump_freq_hz,
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
        muob_cP=sample.muob_cP,
        fw_fr=None,
        fw_perc=sample.fw_perc,
        q_gas_free_sm3day=0.0,
        ipr_mode="linear-pi",
        p_res_atma=sample.p_res_atma,
        productivity_index=sample.productivity_index,
        q_test_sm3day=None,
        p_test_atma=max(sample.p_res_atma - max(35.0, min(60.0, sample.p_res_atma * 0.2)), 1.0),
        p_wh_atma=sample.p_wh_atma,
        p_cas_atma=10.0,
        t_wf_C=80.0,
        t_surface_C=20.0,
        h_perf_m=sample.h_perf_m,
        h_esp_m=sample.h_esp_m,
        d_tub_mm=sample.d_tub_mm,
        d_cas_mm=sample.d_cas_mm,
        u_surf_v=sample.u_surf_v,
        motor_u_nom_lin_v=pump.motor_nominal_voltage_v,
        motor_p_nom_kw=pump.motor_nominal_power_kw,
        motor_f_nom_hz=50.0,
        motor_eff_nom_fr=0.85,
        motor_cosphi_nom_fr=0.9,
        motor_slip_nom_fr=0.04,
        motor_id=2,
    )


def evaluate_base_state(
    *,
    sample: SampledBaseState,
    pump: PumpSelection,
    esp_db_path: Path,
    temp_output_dir: Path,
) -> dict[str, Any]:
    cfg = _build_stable_cfg(sample=sample, pump=pump, esp_db_path=esp_db_path, output_dir=temp_output_dir)
    df = generate_dataframe(cfg, run_id=0, total_runs=1, show_progress=False)
    return df.iloc[0].to_dict()


def _within(bounds: FloatRange, value: float) -> bool:
    lo, hi = bounds
    return float(lo) <= float(value) <= float(hi)


def calibrate_archetype_sample(
    *,
    sample: SampledBaseState,
    archetype: FleetArchetype,
    esp_db_path: Path,
    temp_output_dir: Path,
    catalog: tuple[PumpCatalogEntry, ...],
) -> BaseStateCandidate | None:
    pump = select_pump_for_sample(
        catalog=catalog,
        d_cas_mm=sample.d_cas_mm,
        target_rate_nom_sm3day=sample.pump_nominal_rate_target_sm3day,
        target_head_nom_m=sample.pump_nominal_head_target_m,
        target_motor_power_kw=sample.motor_nominal_power_target_kw,
        u_surf_v=sample.u_surf_v,
    )

    current_sample = sample
    stable_row = evaluate_base_state(
        sample=current_sample,
        pump=pump,
        esp_db_path=esp_db_path,
        temp_output_dir=temp_output_dir,
    )
    current_q = float(stable_row["q_liq_sm3day"])
    if current_q > 0.0:
        adjusted_pi = current_sample.productivity_index * current_sample.q_liq_target_sm3day / current_q
        pi_lo, pi_hi = archetype.base_input_ranges.productivity_index
        adjusted_pi = max(float(pi_lo), min(float(pi_hi), adjusted_pi))
        current_sample = SampledBaseState(
            **{**asdict(current_sample), "productivity_index": adjusted_pi}
        )
        stable_row = evaluate_base_state(
            sample=current_sample,
            pump=pump,
            esp_db_path=esp_db_path,
            temp_output_dir=temp_output_dir,
        )

    if not bool(stable_row.get("well_solver_ok", False)):
        return None
    if not _within(archetype.base_input_ranges.q_liq_target_sm3day, float(stable_row["q_liq_sm3day"])):
        return None
    if not _within(archetype.base_input_ranges.p_int_atma, float(stable_row["p_int_atma"])):
        return None
    if float(stable_row.get("head_m", 0.0)) <= 0.0:
        return None
    if float(stable_row.get("motor_p_electr_kw", 0.0)) <= 0.0:
        return None

    return BaseStateCandidate(sample=current_sample, pump=pump, stable_row=stable_row)


def build_archetype_base_states(
    *,
    archetype: FleetArchetype,
    esp_db_path: Path,
    accepted_samples: int,
    candidate_multiplier: int,
    temp_output_dir: Path,
) -> list[BaseStateCandidate]:
    candidate_count = max(accepted_samples, accepted_samples * candidate_multiplier)
    raw_samples = sample_archetype_states(archetype=archetype, n_samples=candidate_count)
    catalog = load_pump_catalog(str(esp_db_path.resolve()))

    accepted: list[BaseStateCandidate] = []
    for sample in raw_samples:
        candidate = calibrate_archetype_sample(
            sample=sample,
            archetype=archetype,
            esp_db_path=esp_db_path,
            temp_output_dir=temp_output_dir,
            catalog=catalog,
        )
        if candidate is not None:
            accepted.append(candidate)
        if len(accepted) >= accepted_samples:
            break
    return accepted


def _families_for_archetype(
    *,
    archetype: FleetArchetype,
    recommended_only: bool,
    scenario_filter: str | None,
) -> list[str]:
    if recommended_only:
        families = list(archetype.recommended_scenarios)
    else:
        families = [
            "stable_normal",
            "inflow_deterioration",
            "wellhead_backpressure_growth",
            "watercut_growth",
            "viscosity_growth",
            "voltage_sag",
        ]
    if "stable_normal" not in families:
        families = ["stable_normal", *families]
    if scenario_filter:
        token = scenario_filter.lower()
        families = [family for family in families if token in family.lower()]
    return families


def _window_dir(base_dir: Path, window_id: str) -> Path:
    return base_dir / window_id


def build_window_definitions(
    *,
    archetype_library: FleetArchetypeLibrary,
    archetypes: list[FleetArchetype],
    esp_db_path: Path,
    output_base_dir: Path,
    samples_per_archetype: int,
    candidate_multiplier: int,
    recommended_only: bool,
    scenario_filter: str | None,
    include_severities: tuple[str, ...],
) -> tuple[list[WindowDefinition], list[dict[str, Any]]]:
    temp_output_dir = output_base_dir / "_calibration"
    temp_output_dir.mkdir(parents=True, exist_ok=True)

    windows: list[WindowDefinition] = []
    archetype_stats: list[dict[str, Any]] = []
    for archetype in archetypes:
        base_states = build_archetype_base_states(
            archetype=archetype,
            esp_db_path=esp_db_path,
            accepted_samples=samples_per_archetype,
            candidate_multiplier=candidate_multiplier,
            temp_output_dir=temp_output_dir,
        )
        families = _families_for_archetype(
            archetype=archetype,
            recommended_only=recommended_only,
            scenario_filter=scenario_filter,
        )
        archetype_window_count = 0
        for base_state in base_states:
            for family in families:
                severities = ("baseline",) if family == "stable_normal" else include_severities
                duration, points, time_step = _window_spec_for_family(archetype_library.global_guidance, family)
                for severity in severities:
                    sample_index = base_state.sample.sample_index
                    window_id = (
                        f"{archetype.id}__sample_{sample_index:04d}__{family}__{severity}"
                    )
                    window_output_dir = _window_dir(output_base_dir, window_id)
                    window_output_dir.mkdir(parents=True, exist_ok=True)
                    control_plan_path = window_output_dir / "control_plan.json"

                    payload = build_control_plan_payload(
                        base_state=base_state,
                        family=family,
                        severity="medium" if severity == "baseline" else severity,
                        duration=duration,
                        points=points,
                        time_step=time_step,
                        label=window_id,
                    )
                    control_plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

                    sample = base_state.sample
                    pump = base_state.pump
                    cfg = AppConfig.from_cli(
                        scenario="well-esp-system",
                        esp_id=pump.esp_id,
                        n_files=1,
                        workers=1,
                        output_dir=window_output_dir,
                        time_step=time_step,
                        n_points=points,
                        esp_db_path=esp_db_path,
                        control_plan_path=control_plan_path,
                        stage_num=pump.stage_num,
                        pump_freq_hz=pump.pump_freq_hz,
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
                        muob_cP=sample.muob_cP,
                        fw_fr=None,
                        fw_perc=sample.fw_perc,
                        q_gas_free_sm3day=0.0,
                        ipr_mode="linear-pi",
                        p_res_atma=sample.p_res_atma,
                        productivity_index=sample.productivity_index,
                        q_test_sm3day=None,
                        p_test_atma=max(sample.p_res_atma - max(35.0, min(60.0, sample.p_res_atma * 0.2)), 1.0),
                        p_wh_atma=sample.p_wh_atma,
                        p_cas_atma=10.0,
                        t_wf_C=80.0,
                        t_surface_C=20.0,
                        h_perf_m=sample.h_perf_m,
                        h_esp_m=sample.h_esp_m,
                        d_tub_mm=sample.d_tub_mm,
                        d_cas_mm=sample.d_cas_mm,
                        u_surf_v=sample.u_surf_v,
                        motor_u_nom_lin_v=pump.motor_nominal_voltage_v,
                        motor_p_nom_kw=pump.motor_nominal_power_kw,
                        motor_f_nom_hz=50.0,
                        motor_eff_nom_fr=0.85,
                        motor_cosphi_nom_fr=0.9,
                        motor_slip_nom_fr=0.04,
                        motor_id=2,
                    )
                    windows.append(
                        WindowDefinition(
                            window_id=window_id,
                            archetype_id=archetype.id,
                            archetype_name=archetype.name,
                            sample_index=sample_index,
                            scenario_family=family,
                            severity=severity,
                            duration=duration,
                            points=points,
                            time_step=time_step,
                            output_dir=window_output_dir,
                            control_plan_path=control_plan_path,
                            config=cfg,
                            base_state=base_state,
                        )
                    )
                    archetype_window_count += 1
        archetype_stats.append(
            {
                "archetype_id": archetype.id,
                "archetype_name": archetype.name,
                "requested_samples": samples_per_archetype,
                "accepted_samples": len(base_states),
                "window_count": archetype_window_count,
                "recommended_only": recommended_only,
                "scenario_families": families,
            }
        )
    return windows, archetype_stats


def _window_manifest_row(window: WindowDefinition) -> dict[str, Any]:
    sample = window.base_state.sample
    stable_row = window.base_state.stable_row
    return {
        "window_id": window.window_id,
        "archetype_id": window.archetype_id,
        "archetype_name": window.archetype_name,
        "sample_index": window.sample_index,
        "scenario_family": window.scenario_family,
        "severity": window.severity,
        "duration": window.duration,
        "points": window.points,
        "time_step": window.time_step,
        "control_plan_path": str(window.control_plan_path),
        "output_dir": str(window.output_dir),
        "esp_id": window.base_state.pump.esp_id,
        "stage_num": window.base_state.pump.stage_num,
        "base_q_liq_target_sm3day": sample.q_liq_target_sm3day,
        "base_q_liq_sm3day": float(stable_row["q_liq_sm3day"]),
        "base_p_int_target_atma": sample.p_int_target_atma,
        "base_p_int_atma": float(stable_row["p_int_atma"]),
        "base_p_wh_atma": sample.p_wh_atma,
        "base_p_res_atma": sample.p_res_atma,
        "base_productivity_index": sample.productivity_index,
        "base_fw_perc": sample.fw_perc,
        "base_muob_cP": sample.muob_cP,
        "base_u_surf_v": sample.u_surf_v,
        "base_motor_nominal_power_kw": window.base_state.pump.motor_nominal_power_kw,
        "base_motor_nominal_voltage_v": window.base_state.pump.motor_nominal_voltage_v,
    }


def _fleet_worker_entry(payload: dict[str, Any]) -> FleetWindowResult:
    cfg = AppConfig.model_validate(payload["config"])
    result = generate_one_file(cfg, run_id=0, total_runs=1)
    return FleetWindowResult(
        window_id=payload["window_id"],
        archetype_id=payload["archetype_id"],
        scenario_family=payload["scenario_family"],
        severity=payload["severity"],
        ok=result.ok,
        output_path=result.output_path,
        telemetry_output_path=result.telemetry_output_path,
        duration_s=result.duration_s,
        error=result.error,
    )


def run_fleet_generation(
    *,
    archetype_library_path: Path,
    esp_db_path: Path,
    output_base_dir: Path,
    samples_per_archetype: int,
    workers: int,
    candidate_multiplier: int = 4,
    archetype_filter: str | None = None,
    scenario_filter: str | None = None,
    include_severities: tuple[str, ...] = SEVERITY_LEVELS,
    recommended_only: bool = True,
    dry_run: bool = False,
    max_windows: int | None = None,
) -> FleetSummary:
    t0 = time.perf_counter()
    output_base_dir.mkdir(parents=True, exist_ok=True)
    archetype_library = load_fleet_archetype_library(archetype_library_path)
    archetypes = list(archetype_library.archetypes)

    if archetype_filter:
        token = archetype_filter.lower()
        archetypes = [
            archetype
            for archetype in archetypes
            if token in archetype.id.lower() or token in archetype.name.lower()
        ]

    windows, archetype_stats = build_window_definitions(
        archetype_library=archetype_library,
        archetypes=archetypes,
        esp_db_path=esp_db_path,
        output_base_dir=output_base_dir,
        samples_per_archetype=samples_per_archetype,
        candidate_multiplier=candidate_multiplier,
        recommended_only=recommended_only,
        scenario_filter=scenario_filter,
        include_severities=include_severities,
    )
    if max_windows is not None:
        windows = windows[:max_windows]

    manifest_rows = [_window_manifest_row(window) for window in windows]
    manifest_df = pd.DataFrame(manifest_rows)
    manifest_path = output_base_dir / "fleet_manifest.parquet"

    results: list[FleetWindowResult] = []
    if not dry_run:
        tasks = [
            {
                "window_id": window.window_id,
                "archetype_id": window.archetype_id,
                "scenario_family": window.scenario_family,
                "severity": window.severity,
                "config": window.config.model_dump(mode="json"),
            }
            for window in windows
        ]

        if workers <= 1 or len(tasks) <= 1:
            for task in tqdm(tasks, desc="Fleet generation"):
                results.append(_fleet_worker_entry(task))
        else:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_fleet_worker_entry, task): task for task in tasks}
                for future in tqdm(as_completed(futures), total=len(futures), desc="Fleet generation"):
                    task = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:  # pragma: no cover - defensive
                        results.append(
                            FleetWindowResult(
                                window_id=task["window_id"],
                                archetype_id=task["archetype_id"],
                                scenario_family=task["scenario_family"],
                                severity=task["severity"],
                                ok=False,
                                output_path="",
                                telemetry_output_path="",
                                duration_s=0.0,
                                error=repr(exc),
                            )
                        )

    result_by_window = {item.window_id: item for item in results}
    if not manifest_df.empty:
        manifest_df["ok"] = manifest_df["window_id"].map(lambda key: result_by_window.get(key).ok if key in result_by_window else pd.NA)
        manifest_df["output_path"] = manifest_df["window_id"].map(lambda key: result_by_window.get(key).output_path if key in result_by_window else "")
        manifest_df["telemetry_output_path"] = manifest_df["window_id"].map(lambda key: result_by_window.get(key).telemetry_output_path if key in result_by_window else "")
        manifest_df["task_duration_s"] = manifest_df["window_id"].map(lambda key: result_by_window.get(key).duration_s if key in result_by_window else pd.NA)
        manifest_df["task_error"] = manifest_df["window_id"].map(lambda key: result_by_window.get(key).error if key in result_by_window else "")
    manifest_df.to_parquet(manifest_path, index=False, engine="pyarrow")

    ok_count = sum(1 for item in results if item.ok)
    failed_count = sum(1 for item in results if not item.ok)
    duration_s = time.perf_counter() - t0

    summary = FleetSummary(
        total_windows=len(windows),
        ok_count=ok_count,
        failed_count=failed_count,
        duration_s=duration_s,
        manifest_path=str(manifest_path),
        summary_path=str(output_base_dir / "fleet_summary.json"),
        archetype_stats=archetype_stats,
        results=sorted(results, key=lambda item: item.window_id),
    )
    summary_path = Path(summary.summary_path)
    summary_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
