# ufpy-esp-synth

Deterministic synthetic ESP dataset generator built on top of `ufpy`.

The project generates analysis-ready parquet files for three calculation modes:
- `pump-only`
- `pump-dp`
- `esp-system`

All numerical outputs are produced by `ufpy`. The generator does not inject random noise or fabricate derived telemetry.

## Key Capabilities

- Deterministic time-series generation with stable `run_id` reproducibility
- Optional JSON control plans for scenario-driven operating changes
- Telemetry parquet export with a reduced operational schema
- Window-based plotting for demo and analysis workflows
- Safe batch execution with a sequential fallback when process spawning is restricted

## Requirements

- Python 3.11+
- Installed `ufpy`

## Installation

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

## CLI

Main generator entry point:

```bash
ufpy-esp-synth --help
```

Plot export entry point:

```bash
ufpy-esp-plot-windows --help
```

## Scenarios

- `pump-only`: pump performance curves via `ESPPump.get_*`
- `pump-dp`: pump hydraulic calculation via `ESPPump.calc_ESP`
- `esp-system`: full ESP system calculation via `ESPSystem.calc_esp_system`

## Output Files

Each `run_id` produces:

- Primary parquet:
  `{scenario}__esp_{esp_id}__run_{run_id:05d}.parquet`
- Telemetry parquet:
  `{scenario}__esp_{esp_id}__run_{run_id:05d}__telemetry.parquet`

## Control Plans

Pass `--control-plan-path` to replace the built-in deterministic `q_liq_sm3day` profile with a JSON-driven operating plan.

Supported control-plan sections:

- `base`: default operating point
- `segments`: interval overrides
- `events`: point or interval actions such as `override` and `shutdown`
- `rules`: automatic protection rules evaluated before or after each calculation step

Supported override fields:

- `q_liq_sm3day`
- `p_int_atma`
- `t_int_C`
- `pump_freq_hz`
- `u_surf_v`
- `running`
- `label`
- `reason`

## Demo Workflow: 2-Hour Windows

Prepared demo plan:

- `examples/control_plan_q_liq_windows_demo_2h.json`

Demo characteristics:

- `4` logical windows
- `9` points per window
- `15min` step
- `36` total calculations

Generate the demo dataset:

```bash
ufpy-esp-synth \
  --scenario esp-system \
  --esp-id 1006 \
  --n-files 1 \
  --workers 1 \
  --output-dir ./out_demo_2h \
  --time-step 15min \
  --n-points 36 \
  --control-plan-path ./examples/control_plan_q_liq_windows_demo_2h.json \
  --stage-num 250 \
  --pump-freq-hz 50 \
  --p-int-atma 120 \
  --t-int-c 60 \
  --gamma-g 0.7 --gamma-o 0.86 --gamma-w 1.0 \
  --rsb-m3m3 100 --rp-m3m3 100 \
  --pb-atma 130 \
  --t-res-c 80 \
  --bob-m3m3 1.2 \
  --muob-cp 1.5 \
  --fw-perc 30 \
  --q-gas-free-sm3day 0 \
  --u-surf-v 1000 \
  --motor-u-nom-lin-v 1000 \
  --motor-p-nom-kw 45 \
  --motor-f-nom-hz 50 \
  --motor-eff-nom-fr 0.85 \
  --motor-cosphi-nom-fr 0.9 \
  --motor-slip-nom-fr 0.04 \
  --motor-id 2
```

## Telemetry Export

The telemetry parquet follows this column order:

- `run_id`
- `ValueDate`
- `Активная мощность`
- `Дисбаланс напряжений`
- `Дисбаланс токов`
- `Загрузка`
- `Коэффиц.мощности`
- `Напряжение`
- `Р на приеме насоса`
- `Сопротив.изоляции`
- `Температура двигателя`
- `Ток`

Currently available model outputs are mapped into:

- `Активная мощность`
- `Загрузка`
- `Коэффиц.мощности`
- `Напряжение`
- `Р на приеме насоса`
- `Ток`

Fields that are not yet produced by the current physical model remain present in the schema and are exported as empty values:

- `Дисбаланс напряжений`
- `Дисбаланс токов`
- `Сопротив.изоляции`
- `Температура двигателя`

## Plotting

Build a combined multi-metric window plot:

```bash
ufpy-esp-plot-windows \
  --input-parquet ./out_demo_2h/esp-system__esp_1006__run_00000.parquet \
  --output-png ./out_demo_2h/window_analysis.png \
  --points-per-window 9
```

Build one chart per varying metric over the full selected series and also keep the combined overview:

```bash
ufpy-esp-plot-windows \
  --input-parquet ./out_demo_2h/esp-system__esp_1006__run_00000__telemetry.parquet \
  --output-png ./out_demo_2h/telemetry_full_series.png \
  --metrics \
  --varying-only \
  --full-series \
  --split-metrics \
  --keep-combined
```

## Testing

Run the test suite:

```bash
pytest -q
```
