from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from ufpy_esp_synth.config.models import AppConfig
from ufpy_esp_synth.services.logging_ import configure_logging
from ufpy_esp_synth.services.parallel import run_batch

import logging
logging.basicConfig(level=logging.INFO)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Generate deterministic ESP datasets and analysis-ready parquet exports.",
)


@app.command("generate")
def generate(
    scenario: str = typer.Option(
        ...,
        help="Scenario name: pump-only | pump-dp | esp-system | well-esp-system",
    ),
    esp_id: str = typer.Option(..., help="Pump ESP_ID from ufpy esp_db.json"),
    n_files: int = typer.Option(1, min=1, help="How many parquet files to generate"),
    workers: int = typer.Option(1, min=1, help="How many processes to run in parallel"),
    output_dir: Path = typer.Option(..., help="Output directory for parquet files"),
    time_step: str = typer.Option(..., help="Pandas offset alias, e.g. 1min, 5min, 1H"),
    n_points: int = typer.Option(..., min=1, help="Number of time points in each series"),
    esp_db_path: Optional[Path] = typer.Option(
        None,
        help="Path to ufpy ESP equipment DB JSON. If omitted, tries ufpy package data (ufpy/data/esp_db.json).",
    ),
    control_plan_path: Optional[Path] = typer.Option(
        None,
        help="Path to JSON control plan with time intervals and events (shutdown, overrides, recovery).",
    ),
    stage_num: Optional[int] = typer.Option(
        None,
        help="Pump stage_num. If omitted, uses pump.stages_max from DB (if available).",
    ),
    pump_freq_hz: Optional[float] = typer.Option(
        None,
        help="Pump operating frequency (Hz). If omitted, uses pump.freq_hz from DB.",
    ),
    p_int_atma: Optional[float] = typer.Option(None, help="Pump intake pressure (atma)"),
    t_int_C: Optional[float] = typer.Option(None, help="Pump intake temperature (C)"),
    # PVT required inputs
    gamma_g: float = typer.Option(..., help="Gas specific gravity (air=1)"),
    gamma_o: float = typer.Option(..., help="Oil specific gravity (water=1)"),
    gamma_w: float = typer.Option(..., help="Water specific gravity (water=1)"),
    rsb_m3m3: float = typer.Option(..., help="Solution GOR at bubble point (m3/m3)"),
    rp_m3m3: float = typer.Option(..., help="Producing GOR (m3/m3)"),
    pb_atma: float = typer.Option(..., help="Bubble point pressure (atma, -1 for auto)"),
    t_res_C: float = typer.Option(..., help="Reservoir temperature (C)"),
    bob_m3m3: float = typer.Option(..., help="Oil FVF at bubble point (-1 for auto)"),
    muob_cP: float = typer.Option(..., help="Oil viscosity at bubble point (cP, -1 for auto)"),
    fw_fr: Optional[float] = typer.Option(
        None,
        help="Watercut fraction [0..1]. Exactly one of fw_fr or fw_perc must be provided.",
    ),
    fw_perc: Optional[float] = typer.Option(
        None,
        help="Watercut in percent [0..100]. Exactly one of fw_fr or fw_perc must be provided.",
    ),
    q_gas_free_sm3day: float = typer.Option(..., help="Free gas rate at standard conditions (sm3/day)"),
    # Inflow / well model (required for well-esp-system)
    p_res_atma: Optional[float] = typer.Option(None, help="Reservoir pressure for IPR, atma"),
    q_test_sm3day: Optional[float] = typer.Option(None, help="IPR test liquid rate, sm3/day"),
    p_test_atma: Optional[float] = typer.Option(None, help="IPR test bottomhole pressure, atma"),
    p_wh_atma: Optional[float] = typer.Option(None, help="Target wellhead pressure, atma"),
    p_cas_atma: float = typer.Option(10.0, help="Casing head pressure, atma"),
    t_wf_C: Optional[float] = typer.Option(None, help="Bottomhole flowing temperature, C"),
    t_surface_C: Optional[float] = typer.Option(None, help="Surface temperature, C"),
    h_perf_m: Optional[float] = typer.Option(None, help="Perforation depth, m"),
    h_esp_m: Optional[float] = typer.Option(None, help="ESP setting depth, m"),
    d_tub_mm: Optional[float] = typer.Option(None, help="Tubing inner diameter, mm"),
    d_cas_mm: Optional[float] = typer.Option(None, help="Casing inner diameter, mm"),
    # Motor (required for esp-system)
    u_surf_v: Optional[float] = typer.Option(None, help="Surface line voltage (V); required for esp-system"),
    motor_u_nom_lin_v: Optional[float] = typer.Option(None, help="Motor nominal line voltage (V)"),
    motor_p_nom_kw: Optional[float] = typer.Option(None, help="Motor nominal shaft power (kW)"),
    motor_f_nom_hz: Optional[float] = typer.Option(None, help="Motor nominal frequency (Hz)"),
    motor_eff_nom_fr: Optional[float] = typer.Option(None, help="Motor nominal efficiency [0..1]"),
    motor_cosphi_nom_fr: Optional[float] = typer.Option(None, help="Motor nominal cosphi [0..1]"),
    motor_slip_nom_fr: Optional[float] = typer.Option(None, help="Motor nominal slip [0..1)"),
    motor_id: Optional[int] = typer.Option(None, help="Motor model id (0=simple, 2=Gridin)."),
    log_level: str = typer.Option("INFO", help="Logging level: DEBUG|INFO|WARNING|ERROR"),
) -> None:
    """
    Generate deterministic ESP time-series datasets.

    Output:
      - One parquet per run_id (0..n_files-1).
      - One telemetry parquet per run_id.
      - No randomness or synthetic noise; all computed values come from ufpy models.
    """
    configure_logging(level=log_level)

    cfg = AppConfig.from_cli(
        scenario=scenario,
        esp_id=esp_id,
        n_files=n_files,
        workers=workers,
        output_dir=output_dir,
        time_step=time_step,
        n_points=n_points,
        esp_db_path=esp_db_path,
        control_plan_path=control_plan_path,
        stage_num=stage_num,
        pump_freq_hz=pump_freq_hz,
        p_int_atma=p_int_atma,
        t_int_C=t_int_C,
        gamma_g=gamma_g,
        gamma_o=gamma_o,
        gamma_w=gamma_w,
        rsb_m3m3=rsb_m3m3,
        rp_m3m3=rp_m3m3,
        pb_atma=pb_atma,
        t_res_C=t_res_C,
        bob_m3m3=bob_m3m3,
        muob_cP=muob_cP,
        fw_fr=fw_fr,
        fw_perc=fw_perc,
        q_gas_free_sm3day=q_gas_free_sm3day,
        p_res_atma=p_res_atma,
        q_test_sm3day=q_test_sm3day,
        p_test_atma=p_test_atma,
        p_wh_atma=p_wh_atma,
        p_cas_atma=p_cas_atma,
        t_wf_C=t_wf_C,
        t_surface_C=t_surface_C,
        h_perf_m=h_perf_m,
        h_esp_m=h_esp_m,
        d_tub_mm=d_tub_mm,
        d_cas_mm=d_cas_mm,
        u_surf_v=u_surf_v,
        motor_u_nom_lin_v=motor_u_nom_lin_v,
        motor_p_nom_kw=motor_p_nom_kw,
        motor_f_nom_hz=motor_f_nom_hz,
        motor_eff_nom_fr=motor_eff_nom_fr,
        motor_cosphi_nom_fr=motor_cosphi_nom_fr,
        motor_slip_nom_fr=motor_slip_nom_fr,
        motor_id=motor_id,
    )

    # Log config in a stable JSON form (no timestamps, no random ids).
    typer.echo("=== Generation Started ===")
    typer.echo(json.dumps(cfg.model_dump(mode="json"), ensure_ascii=False, indent=2))

    summary = run_batch(cfg)

    typer.echo("=== Generation Summary ===")
    typer.echo(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))

    # Non-zero exit code on any failures
    if summary.failed_count > 0:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
