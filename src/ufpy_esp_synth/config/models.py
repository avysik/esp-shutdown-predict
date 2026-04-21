from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator, field_validator


class ScenarioName(str, Enum):
    PUMP_ONLY = "pump-only"
    PUMP_DP = "pump-dp"
    ESP_SYSTEM = "esp-system"

    @staticmethod
    def normalize(value: str) -> "ScenarioName":
        v = (value or "").strip().lower().replace("_", "-")
        aliases = {
            "pumponly": "pump-only",
            "pump-only": "pump-only",
            "pump": "pump-only",
            "pump-dp": "pump-dp",
            "dp": "pump-dp",
            "esp-system": "esp-system",
            "electric-chain": "esp-system",
            "system": "esp-system",
        }
        if v in aliases:
            v = aliases[v]
        return ScenarioName(v)


class PumpConfig(BaseModel):
    esp_id: str = Field(..., min_length=1)
    stage_num: Optional[int] = Field(None, ge=1)
    freq_hz: Optional[float] = Field(None, gt=0)

    @model_validator(mode="after")
    def _stage_freq_optional(self) -> "PumpConfig":
        # stage_num and freq_hz may be None -> resolved from DB at runtime
        return self


class HydraulicConfig(BaseModel):
    p_int_atma: float = Field(..., gt=0)
    t_int_C: float = Field(...)


class PVTConfig(BaseModel):
    gamma_g: float = Field(..., gt=0)
    gamma_o: float = Field(..., gt=0)
    gamma_w: float = Field(..., gt=0)
    rsb_m3m3: float = Field(..., ge=0)
    rp_m3m3: float = Field(..., ge=0)
    pb_atma: float = Field(...)

    t_res_C: float = Field(...)

    bob_m3m3: float = Field(...)
    muob_cP: float = Field(...)

    fw_fr: float = Field(..., ge=0, le=1)
    q_gas_free_sm3day: float = Field(..., ge=0)

    @staticmethod
    def resolve_fw(fw_fr: Optional[float], fw_perc: Optional[float]) -> float:
        if fw_fr is None and fw_perc is None:
            raise ValueError("Exactly one of fw_fr or fw_perc must be provided.")
        if fw_fr is not None and fw_perc is not None:
            raise ValueError("Exactly one of fw_fr or fw_perc must be provided (not both).")
        if fw_fr is not None:
            if not (0.0 <= fw_fr <= 1.0):
                raise ValueError("fw_fr must be in [0..1].")
            return float(fw_fr)
        # fw_perc is not None
        if not (0.0 <= fw_perc <= 100.0):
            raise ValueError("fw_perc must be in [0..100].")
        return float(fw_perc) / 100.0


class MotorConfig(BaseModel):
    # Required only for esp-system
    u_surf_v: float = Field(..., gt=0)

    u_nom_lin_v: float = Field(..., gt=0)
    p_nom_kw: float = Field(..., gt=0)
    f_nom_hz: float = Field(..., gt=0)

    eff_nom_fr: float = Field(..., gt=0, le=1)
    cosphi_nom_fr: float = Field(..., gt=0, le=1)
    slip_nom_fr: float = Field(..., ge=0, lt=1)

    motor_id: int = Field(...)

    @model_validator(mode="after")
    def _validate_motor_id(self) -> "MotorConfig":
        if self.motor_id not in (0, 2):
            raise ValueError("motor_id must be 0 (simple) or 2 (Gridin) for this utility.")
        return self


class TimeAxisConfig(BaseModel):
    time_step: str = Field(..., min_length=1)
    n_points: int = Field(..., ge=1)


class TimeAxisConfig(BaseModel):
    time_step: str
    n_points: int

    @field_validator("time_step")
    @classmethod
    def normalize_freq(cls, v: str) -> str:
        return v.lower()


class GenerationConfig(BaseModel):
    output_dir: Path
    n_files: int = Field(..., ge=1)
    workers: int = Field(..., ge=1)


class AppConfig(BaseModel):
    scenario: ScenarioName
    pump: PumpConfig
    hydraulic: HydraulicConfig
    pvt: PVTConfig
    time_axis: TimeAxisConfig
    generation: GenerationConfig

    # optional
    esp_db_path: Optional[Path] = None
    motor: Optional[MotorConfig] = None

    @model_validator(mode="after")
    def _validate_scenario_requirements(self) -> "AppConfig":
        if self.scenario == ScenarioName.ESP_SYSTEM and self.motor is None:
            raise ValueError("motor config is required for esp-system scenario.")
        if self.scenario != ScenarioName.ESP_SYSTEM and self.motor is not None:
            # Keep strict: do not accept unused inputs (honesty / no extra fields)
            raise ValueError("motor config must not be provided for non esp-system scenarios.")
        return self

    @classmethod
    def from_cli(cls, **kwargs: Any) -> "AppConfig":
        scenario = ScenarioName.normalize(kwargs["scenario"])

        fw_fr = PVTConfig.resolve_fw(kwargs.get("fw_fr"), kwargs.get("fw_perc"))

        pump = PumpConfig(
            esp_id=kwargs["esp_id"],
            stage_num=kwargs.get("stage_num"),
            freq_hz=kwargs.get("pump_freq_hz"),
        )

        hydraulic = HydraulicConfig(
            p_int_atma=kwargs["p_int_atma"],
            t_int_C=kwargs["t_int_C"],
        )

        pvt = PVTConfig(
            gamma_g=kwargs["gamma_g"],
            gamma_o=kwargs["gamma_o"],
            gamma_w=kwargs["gamma_w"],
            rsb_m3m3=kwargs["rsb_m3m3"],
            rp_m3m3=kwargs["rp_m3m3"],
            pb_atma=kwargs["pb_atma"],
            t_res_C=kwargs["t_res_C"],
            bob_m3m3=kwargs["bob_m3m3"],
            muob_cP=kwargs["muob_cP"],
            fw_fr=fw_fr,
            q_gas_free_sm3day=kwargs["q_gas_free_sm3day"],
        )

        time_axis = TimeAxisConfig(
            time_step=kwargs["time_step"],
            n_points=kwargs["n_points"],
        )

        generation = GenerationConfig(
            output_dir=kwargs["output_dir"],
            n_files=kwargs["n_files"],
            workers=kwargs["workers"],
        )

        motor = None
        if scenario == ScenarioName.ESP_SYSTEM:
            motor = MotorConfig(
                u_surf_v=kwargs["u_surf_v"],
                u_nom_lin_v=kwargs["motor_u_nom_lin_v"],
                p_nom_kw=kwargs["motor_p_nom_kw"],
                f_nom_hz=kwargs["motor_f_nom_hz"],
                eff_nom_fr=kwargs["motor_eff_nom_fr"],
                cosphi_nom_fr=kwargs["motor_cosphi_nom_fr"],
                slip_nom_fr=kwargs["motor_slip_nom_fr"],
                motor_id=kwargs["motor_id"],
            )

        return cls(
            scenario=scenario,
            pump=pump,
            hydraulic=hydraulic,
            pvt=pvt,
            time_axis=time_axis,
            generation=generation,
            esp_db_path=kwargs.get("esp_db_path"),
            motor=motor,
        )
    