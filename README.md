# ufpy-esp-synth

Deterministic synthetic ESP dataset generator built on top of `ufpy`.

Русская версия: [README.ru.md](./README.ru.md)

The project is not a standalone physics engine. Core engineering calculations are delegated to `ufpy`, while this repository provides:
- scenario orchestration
- JSON control plans
- deterministic window generation
- parquet export
- reduced telemetry export
- plotting utilities

The current recommended scenario is `well-esp-system`, where the model solves:

`IPR -> bottomhole pressure -> inflow -> pump intake state -> ESP operating point -> motor telemetry`

## What The Project Does

At each timestamp the program:
1. reads the current operating state from CLI defaults and the active `control plan` segment
2. builds a `WellESP` model
3. solves the well for the requested operating target, typically fixed wellhead pressure
4. computes inflow, bottomhole pressure, intake pressure, pump head, power, current, load, and related outputs
5. stores the full engineering state in the main parquet
6. stores a reduced operator-style signal set in a separate telemetry parquet

The generator is deterministic:
- fixed time origin
- no random noise inside calculations
- stable ordering by `run_id`

## Scenarios

Supported scenarios:
- `pump-only`
- `pump-dp`
- `esp-system`
- `well-esp-system`

Recommended for realistic well behavior:
- `well-esp-system`

Scenario summary:
- `pump-only`: direct pump curve evaluation
- `pump-dp`: pump hydraulic calculation
- `esp-system`: pump + motor calculation with direct intake inputs
- `well-esp-system`: well + IPR + intake hydraulics + ESP + motor

## Installation

Requirements:
- Python `3.11+`
- installed `ufpy`

Install `ufpy` first:

```bash
git clone https://gitverse.ru/shars/ufpy
python -m pip install -U pip
python -m pip install -e ./ufpy
```

Install this project:

```bash
git clone https://github.com/your-org/esp-shutdown-predict.git
cd esp-shutdown-predict
python -m pip install -e .
```

## CLI Entry Points

Generator:

```bash
ufpy-esp-synth --help
```

Plotting:

```bash
ufpy-esp-plot-windows --help
```

Equivalent Python module entry points:

```bash
python -m ufpy_esp_synth.cli.main --help
python -m ufpy_esp_synth.plot_windows --help
```

Important:
- in the current CLI layout, use `ufpy-esp-synth --scenario ...`
- do not prepend `generate`

## Main Inputs For `well-esp-system`

### Inflow / IPR

- `--ipr-mode linear-pi | vogel-test-point`
- `--p-res-atma`
- `--productivity-index`
- `--q-test-sm3day`
- `--p-test-atma`

Recommended mode:
- `linear-pi`

Use `productivity_index` when you want to drive scenarios by well productivity directly.

### Well Geometry

- `--p-wh-atma`
- `--p-cas-atma`
- `--t-wf-c`
- `--t-surface-c`
- `--h-perf-m`
- `--h-esp-m`
- `--d-tub-mm`
- `--d-cas-mm`

### Pump / Motor / Fluid

- `--esp-id`
- `--stage-num`
- `--pump-freq-hz`
- `--u-surf-v`
- PVT inputs: `gamma_*`, `rsb`, `rp`, `pb`, `t_res`, `bob`, `muob`, `fw`, `q_gas_free`

## Output Files

Each `run_id` produces:
- main parquet:
  `{scenario}__esp_{esp_id}__run_{run_id:05d}.parquet`
- telemetry parquet:
  `{scenario}__esp_{esp_id}__run_{run_id:05d}__telemetry.parquet`

The main parquet contains full engineering state.

The telemetry parquet contains a reduced operational schema intended for diagnostics and ML-style signal workflows.

## Telemetry Schema

Telemetry column order:

```text
run_id
ValueDate
Активная мощность
Дисбаланс напряжений
Дисбаланс токов
Загрузка
Коэффиц.мощности
Напряжение
Р на приеме насоса
Сопротив.изоляции
Температура двигателя
Ток
```

Currently mapped from the physical model:
- `Активная мощность`
- `Загрузка`
- `Коэффиц.мощности`
- `Напряжение`
- `Р на приеме насоса`
- `Ток`

Currently unavailable and exported as `NaN`:
- `Дисбаланс напряжений`
- `Дисбаланс токов`
- `Сопротив.изоляции`
- `Температура двигателя`

## Control Plans

The generator supports JSON control plans through `--control-plan-path`.

Available sections:
- `base`
- `segments`
- `events`
- `rules`

Typical override fields:
- `productivity_index`
- `p_res_atma`
- `p_wh_atma`
- `pump_freq_hz`
- `u_surf_v`
- `q_test_sm3day`
- `p_test_atma`
- `running`
- `label`
- `reason`

Use `segments` for piecewise-steady windows.

## Ready-to-Run Demo Scenarios

Prepared examples in `examples/`:
- `control_plan_well_productivity_decline_2h.json`
- `control_plan_well_pwh_growth_2h.json`
- `control_plan_well_freq_stepup_2h.json`
- `control_plan_well_qtest_demo_2h.json`
- legacy pump/system demos and shutdown examples

### 1. Productivity Decline Over 2 Hours

Meaning:
- `productivity_index` decreases across 9 points
- inflow falls
- intake pressure falls
- pump operating point shifts accordingly

Generate:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.cli.main --scenario well-esp-system --esp-id 1006 --n-files 1 --workers 1 --output-dir .\out_well_productivity_2h --time-step 15min --n-points 9 --control-plan-path .\examples\control_plan_well_productivity_decline_2h.json --stage-num 250 --pump-freq-hz 50 --gamma-g 0.7 --gamma-o 0.86 --gamma-w 1.0 --rsb-m3m3 100 --rp-m3m3 100 --pb-atma 130 --t-res-c 80 --bob-m3m3 1.2 --muob-cp 1.5 --fw-perc 30 --q-gas-free-sm3day 0 --ipr-mode linear-pi --p-res-atma 250 --productivity-index 0.55 --p-test-atma 200 --p-wh-atma 20 --p-cas-atma 10 --t-wf-c 80 --t-surface-c 20 --h-perf-m 1500 --h-esp-m 1200 --d-tub-mm 62 --d-cas-mm 150 --u-surf-v 1000 --motor-u-nom-lin-v 1000 --motor-p-nom-kw 45 --motor-f-nom-hz 50 --motor-eff-nom-fr 0.85 --motor-cosphi-nom-fr 0.9 --motor-slip-nom-fr 0.04 --motor-id 2
```

### 2. Wellhead Pressure Growth Over 2 Hours

Meaning:
- `p_wh_atma` increases
- well hydraulics rebuild to maintain the new target
- inflow and intake conditions respond

Generate:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.cli.main --scenario well-esp-system --esp-id 1006 --n-files 1 --workers 1 --output-dir .\out_well_pwh_growth_2h --time-step 15min --n-points 9 --control-plan-path .\examples\control_plan_well_pwh_growth_2h.json --stage-num 250 --pump-freq-hz 50 --gamma-g 0.7 --gamma-o 0.86 --gamma-w 1.0 --rsb-m3m3 100 --rp-m3m3 100 --pb-atma 130 --t-res-c 80 --bob-m3m3 1.2 --muob-cp 1.5 --fw-perc 30 --q-gas-free-sm3day 0 --ipr-mode linear-pi --p-res-atma 250 --productivity-index 0.55 --p-test-atma 200 --p-wh-atma 12 --p-cas-atma 10 --t-wf-c 80 --t-surface-c 20 --h-perf-m 1500 --h-esp-m 1200 --d-tub-mm 62 --d-cas-mm 150 --u-surf-v 1000 --motor-u-nom-lin-v 1000 --motor-p-nom-kw 45 --motor-f-nom-hz 50 --motor-eff-nom-fr 0.85 --motor-cosphi-nom-fr 0.9 --motor-slip-nom-fr 0.04 --motor-id 2
```

### 3. Pump Frequency Increase From 50 To 52 Hz

Meaning:
- operator increases pump frequency
- flow rises
- intake pressure drops
- current and power increase

Generate:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.cli.main --scenario well-esp-system --esp-id 1006 --n-files 1 --workers 1 --output-dir .\out_well_freq_stepup_2h --time-step 15min --n-points 9 --control-plan-path .\examples\control_plan_well_freq_stepup_2h.json --stage-num 250 --pump-freq-hz 50 --gamma-g 0.7 --gamma-o 0.86 --gamma-w 1.0 --rsb-m3m3 100 --rp-m3m3 100 --pb-atma 130 --t-res-c 80 --bob-m3m3 1.2 --muob-cp 1.5 --fw-perc 30 --q-gas-free-sm3day 0 --ipr-mode linear-pi --p-res-atma 250 --productivity-index 0.55 --p-test-atma 200 --p-wh-atma 20 --p-cas-atma 10 --t-wf-c 80 --t-surface-c 20 --h-perf-m 1500 --h-esp-m 1200 --d-tub-mm 62 --d-cas-mm 150 --u-surf-v 1000 --motor-u-nom-lin-v 1000 --motor-p-nom-kw 45 --motor-f-nom-hz 50 --motor-eff-nom-fr 0.85 --motor-cosphi-nom-fr 0.9 --motor-slip-nom-fr 0.04 --motor-id 2
```

## Plotting

### Plot all varying metrics from the main parquet

Example:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.plot_windows --input-parquet .\out_well_productivity_2h\well-esp-system__esp_1006__run_00000.parquet --output-png .\out_well_productivity_2h\well_productivity_full_series.png --metrics --varying-only --full-series --split-metrics --keep-combined
```

This produces:
- one combined PNG
- one PNG per varying metric

### Plot all varying telemetry signals

Example:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.plot_windows --input-parquet .\out_well_productivity_2h\well-esp-system__esp_1006__run_00000__telemetry.parquet --output-png .\out_well_productivity_2h\well_productivity_telemetry.png --metrics --varying-only --full-series --split-metrics --keep-combined
```

### Plot one logical window with overlaid window traces

If the parquet contains multiple windows, use:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.plot_windows --input-parquet .\out_demo_2h\esp-system__esp_1006__run_00000.parquet --output-png .\out_demo_2h\window_analysis.png --points-per-window 9
```

## Main Parquet: Important `well-esp-system` Fields

Useful engineering columns:
- `productivity_index`
- `p_res_atma`
- `p_wf_atma`
- `drawdown_atma`
- `p_int_atma`
- `p_dis_atma`
- `p_buf_atma`
- `p_wh_target_atma`
- `wellhead_target_error_atma`
- `well_solver_ok`
- `q_liq_sm3day`
- `q_ipr_sm3day`
- `gas_fraction_d`
- `gas_fraction_pump_d`
- `head_m`
- `power_esp_w`
- `motor_p_electr_kw`
- `motor_i_lin_a`
- `motor_load_d`

These columns are intended for engineering validation, not only ML export.

## Solver Quality

For `well-esp-system` the code now stores explicit solver quality fields:
- `well_solver_ok`
- `wellhead_target_error_atma`

Use them to filter invalid points if you experiment with aggressive scenarios.

## Known Limitations

- The model is piecewise-steady, not transient.
- The repository does not simulate motor insulation resistance, phase imbalance, or motor temperature directly.
- Gas behavior depends heavily on the separation stage inside `WellESP`; low intake pressure does not automatically mean large gas fraction at the pump if separation removes the free gas.
- The telemetry parquet is intentionally reduced and does not contain full well state.

## Testing

Run the test suite:

```bash
python -m pytest -q
```

Useful focused regression run:

```bash
python -m pytest tests/test_well_esp_system.py -q
```

## Project Positioning

This repository should be understood as:
- a deterministic scenario generator
- a dataset/export layer
- a control-plan wrapper around `ufpy`

It should not be understood as:
- an independent replacement for `ufpy`
- a full transient multiphase simulator

The physics live in `ufpy`.
The orchestration, scenario logic, dataset structure, telemetry export, and plotting live here.
