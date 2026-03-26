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

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command("generate")
def generate(
    scenario: str = typer.Option(
        ...,
        help="Scenario name: pump-only | pump-dp | esp-system",
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
    stage_num: Optional[int] = typer.Option(
        None,
        help="Pump stage_num. If omitted, uses pump.stages_max from DB (if available).",
    ),
    pump_freq_hz: Optional[float] = typer.Option(
        None,
        help="Pump operating frequency (Hz). If omitted, uses pump.freq_hz from DB.",
    ),
    p_int_atma: float = typer.Option(..., help="Pump intake pressure (atma)"),
    t_int_C: float = typer.Option(..., help="Pump intake temperature (C)"),
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
    # Motor (required for esp-system)
    u_surf_v: Optional[float] = typer.Option(None, help="Surface line voltage (V) — required for esp-system"),
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
    Deterministic synthetic ESP time-series generator.

    Output:
      - One parquet per run_id (0..n_files-1).
      - No randomness, no noise. All computed values come from ufpy models.
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
    typer.echo("=== ufpy-esp-synth: start ===")
    typer.echo(json.dumps(cfg.model_dump(mode="json"), ensure_ascii=False, indent=2))

    summary = run_batch(cfg)

    typer.echo("=== summary ===")
    typer.echo(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))

    # Non-zero exit code on any failures
    if summary.failed_count > 0:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()