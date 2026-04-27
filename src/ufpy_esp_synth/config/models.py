from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator, field_validator


class ScenarioName(str, Enum):
    PUMP_ONLY = "pump-only"
    PUMP_DP = "pump-dp"
    ESP_SYSTEM = "esp-system"
    WELL_ESP_SYSTEM = "well-esp-system"

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
            "well-esp-system": "well-esp-system",
            "well-system": "well-esp-system",
            "well": "well-esp-system",
            "nodal": "well-esp-system",
        }
        if v in aliases:
            v = aliases[v]
        return ScenarioName(v)


class IPRMode(str, Enum):
    LINEAR_PI = "linear-pi"
    VOGEL_TEST_POINT = "vogel-test-point"

    @staticmethod
    def normalize(value: str) -> "IPRMode":
        v = (value or "").strip().lower().replace("_", "-")
        aliases = {
            "linear": "linear-pi",
            "linear-pi": "linear-pi",
            "pi": "linear-pi",
            "vogel": "vogel-test-point",
            "vogel-test-point": "vogel-test-point",
            "test-point": "vogel-test-point",
        }
        if v in aliases:
            v = aliases[v]
        return IPRMode(v)


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


class InflowConfig(BaseModel):
    ipr_mode: IPRMode = Field(IPRMode.LINEAR_PI)
    p_res_atma: float = Field(..., gt=0)
    productivity_index: Optional[float] = Field(None, gt=0)
    q_test_sm3day: Optional[float] = Field(None, ge=0)
    p_test_atma: float = Field(..., ge=0)

    @model_validator(mode="after")
    def _validate_ipr_inputs(self) -> "InflowConfig":
        if self.p_test_atma >= self.p_res_atma:
            raise ValueError("p_test_atma must be lower than p_res_atma for IPR calculations.")
        if self.ipr_mode == IPRMode.LINEAR_PI:
            if self.productivity_index is None:
                raise ValueError("productivity_index is required for linear-pi inflow mode.")
        elif self.ipr_mode == IPRMode.VOGEL_TEST_POINT:
            if self.q_test_sm3day is None:
                raise ValueError("q_test_sm3day is required for vogel-test-point inflow mode.")
        return self

    @property
    def effective_productivity_index(self) -> float:
        if self.productivity_index is not None:
            return float(self.productivity_index)
        if self.q_test_sm3day is None:
            return 0.0
        dp = self.p_res_atma - self.p_test_atma
        return 0.0 if dp <= 0 else float(self.q_test_sm3day) / float(dp)

    @property
    def effective_q_test_sm3day(self) -> float:
        if self.q_test_sm3day is not None:
            return float(self.q_test_sm3day)
        dp = self.p_res_atma - self.p_test_atma
        return max(0.0, float(self.effective_productivity_index) * float(dp))


class WellConfig(BaseModel):
    p_wh_atma: float = Field(..., ge=0)
    p_cas_atma: float = Field(10.0, ge=0)
    t_wf_C: float = Field(...)
    t_surface_C: float = Field(...)
    h_perf_m: float = Field(..., gt=0)
    h_esp_m: float = Field(..., gt=0)
    d_tub_mm: float = Field(..., gt=0)
    d_cas_mm: float = Field(..., gt=0)

    @model_validator(mode="after")
    def _validate_depths(self) -> "WellConfig":
        if self.h_perf_m < self.h_esp_m:
            raise ValueError("h_perf_m must be greater than or equal to h_esp_m.")
        return self


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
    hydraulic: Optional[HydraulicConfig]
    pvt: PVTConfig
    time_axis: TimeAxisConfig
    generation: GenerationConfig

    # optional
    esp_db_path: Optional[Path] = None
    motor: Optional[MotorConfig] = None
    control_plan_path: Optional[Path] = None
    inflow: Optional[InflowConfig] = None
    well: Optional[WellConfig] = None

    @model_validator(mode="after")
    def _validate_scenario_requirements(self) -> "AppConfig":
        if self.scenario == ScenarioName.ESP_SYSTEM:
            if self.motor is None:
                raise ValueError("motor config is required for esp-system scenario.")
            if self.hydraulic is None:
                raise ValueError("hydraulic config is required for esp-system scenario.")
            if self.inflow is not None or self.well is not None:
                raise ValueError("inflow and well config must not be provided for esp-system scenario.")
        elif self.scenario == ScenarioName.WELL_ESP_SYSTEM:
            if self.motor is None:
                raise ValueError("motor config is required for well-esp-system scenario.")
            if self.inflow is None:
                raise ValueError("inflow config is required for well-esp-system scenario.")
            if self.well is None:
                raise ValueError("well config is required for well-esp-system scenario.")
            if self.hydraulic is not None:
                raise ValueError("hydraulic config must not be provided for well-esp-system scenario.")
        else:
            if self.motor is not None:
                raise ValueError("motor config must not be provided for non-system scenarios.")
            if self.hydraulic is None:
                raise ValueError("hydraulic config is required for pump-only and pump-dp scenarios.")
            if self.inflow is not None or self.well is not None:
                raise ValueError("inflow and well config must not be provided for pump-only and pump-dp scenarios.")
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

        hydraulic = None
        if kwargs.get("p_int_atma") is not None and kwargs.get("t_int_C") is not None:
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
        if scenario in (ScenarioName.ESP_SYSTEM, ScenarioName.WELL_ESP_SYSTEM):
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

        inflow = None
        if scenario == ScenarioName.WELL_ESP_SYSTEM:
            inflow = InflowConfig(
                ipr_mode=IPRMode.normalize(kwargs["ipr_mode"]),
                p_res_atma=kwargs["p_res_atma"],
                productivity_index=kwargs.get("productivity_index"),
                q_test_sm3day=kwargs["q_test_sm3day"],
                p_test_atma=kwargs["p_test_atma"],
            )

        well = None
        if scenario == ScenarioName.WELL_ESP_SYSTEM:
            well = WellConfig(
                p_wh_atma=kwargs["p_wh_atma"],
                p_cas_atma=kwargs.get("p_cas_atma", 10.0),
                t_wf_C=kwargs["t_wf_C"],
                t_surface_C=kwargs["t_surface_C"],
                h_perf_m=kwargs["h_perf_m"],
                h_esp_m=kwargs["h_esp_m"],
                d_tub_mm=kwargs["d_tub_mm"],
                d_cas_mm=kwargs["d_cas_mm"],
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
            control_plan_path=kwargs.get("control_plan_path"),
            inflow=inflow,
            well=well,
        )
    
