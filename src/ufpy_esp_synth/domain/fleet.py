from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias

from pydantic import BaseModel, Field, model_validator


FloatRange: TypeAlias = tuple[float, float]


def _validate_range(name: str, bounds: FloatRange) -> None:
    if len(bounds) != 2:
        raise ValueError(f"{name} must contain exactly two bounds.")
    lo, hi = bounds
    if hi < lo:
        raise ValueError(f"{name} upper bound must be greater than or equal to lower bound.")


def range_mid(bounds: FloatRange) -> float:
    lo, hi = bounds
    return (float(lo) + float(hi)) / 2.0


def scale_range_value(bounds: FloatRange, unit_value: float) -> float:
    lo, hi = bounds
    return float(lo) + (float(hi) - float(lo)) * float(unit_value)


class WindowGuidance(BaseModel):
    duration: str
    points: int = Field(..., ge=1)
    time_step: str
    use_for: list[str] = Field(default_factory=list)


class GlobalGuidance(BaseModel):
    fast_window_default: WindowGuidance
    slow_window_default: WindowGuidance
    notes: list[str] = Field(default_factory=list)


class PumpSelectionTargets(BaseModel):
    pump_nominal_rate_sm3day: FloatRange
    pump_nominal_head_m: FloatRange
    motor_nominal_power_kw: FloatRange

    @model_validator(mode="after")
    def _validate_ranges(self) -> "PumpSelectionTargets":
        _validate_range("pump_nominal_rate_sm3day", self.pump_nominal_rate_sm3day)
        _validate_range("pump_nominal_head_m", self.pump_nominal_head_m)
        _validate_range("motor_nominal_power_kw", self.motor_nominal_power_kw)
        return self


class ArchetypeBaseInputRanges(BaseModel):
    q_liq_target_sm3day: FloatRange
    p_int_atma: FloatRange
    p_wh_atma: FloatRange
    h_esp_m: FloatRange
    h_perf_minus_h_esp_m: FloatRange
    d_tub_mm: FloatRange
    d_cas_mm: FloatRange
    p_res_atma: FloatRange
    productivity_index: FloatRange
    fw_perc: FloatRange
    muob_cP: FloatRange
    u_surf_v: FloatRange

    @model_validator(mode="after")
    def _validate_ranges(self) -> "ArchetypeBaseInputRanges":
        for name, value in self.model_dump().items():
            _validate_range(name, value)
        return self


class FleetArchetype(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    intent: str = Field(..., min_length=1)
    pump_selection_targets: PumpSelectionTargets
    base_input_ranges: ArchetypeBaseInputRanges
    recommended_scenarios: list[str] = Field(default_factory=list)


class FleetArchetypeLibrary(BaseModel):
    library_name: str = Field(..., min_length=1)
    source_basis: dict[str, str] = Field(default_factory=dict)
    global_guidance: GlobalGuidance
    archetypes: list[FleetArchetype] = Field(default_factory=list)

    def get_archetype(self, archetype_id: str) -> FleetArchetype:
        for archetype in self.archetypes:
            if archetype.id == archetype_id:
                return archetype
        raise KeyError(f"Unknown archetype id: {archetype_id}")


def load_fleet_archetype_library(path: Path) -> FleetArchetypeLibrary:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return FleetArchetypeLibrary.model_validate(payload)
