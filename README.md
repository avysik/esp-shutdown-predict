Production-grade deterministic synthetic ESP time-series generator based on `ufpy`.

Key principles:
- No randomness, no noise, no Monte Carlo.
- No invented columns: only inputs used by `ufpy` ESP/PVT calculations and direct (or strictly derivable) outputs.
- One run_id -> one parquet file (DataFrame saved via pyarrow).
- Safe parallel execution: ProcessPoolExecutor with isolated calculation context per worker.

## Requirements
- Python >= 3.11
- Installed `ufpy` (from https://gitverse.ru/shars/ufpy)

## Install

### 1) Install ufpy
Clone and install `ufpy` (editable install recommended):

```bash
git clone https://gitverse.ru/shars/ufpy
python -m pip install -U pip
python -m pip install -e ./ufpy
```

### 2) Install this utility

```bash
git clone esp-shutdown-predict
python -m pip install -e
```

## Run

The CLI entrypoint is:

```bash
ufpy-esp-synth generate --help
```

### Scenarios
- `pump-only`   : H/Q, P/Q, eta/Q via ESPPump.get_* (curve-like)
- `pump-dp`     : ESPPump.calc_ESP => pressures, power, efficiency
- `esp-system`  : ESPSystem.calc_esp_system => pump outputs + motor electrical outputs

## Output
- Parquet files in output directory:
  `{scenario}__esp_{esp_id}__run_{run_id}.parquet`

## Tests

```bash
pytest
```
```

## Примеры CLI

Ниже — примеры, которые соответствуют реализованным сценариям и требуют только те входы, которые реально используются `ufpy`‑моделями.

### Сценарий pump-only (кривые насоса во времени)

```bash
ufpy-esp-synth generate \
  --scenario pump-only \
  --esp-id 1006 \
  --n-files 2 \
  --workers 2 \
  --output-dir ./out \
  --time-step 5min \
  --n-points 200 \
  --stage-num 250 \
  --pump-freq-hz 50 \
  --p-int-atma 100 \
  --t-int-c 50 \
  --gamma-g 0.6 --gamma-o 0.86 --gamma-w 1.1 \
  --rsb-m3m3 120 --rp-m3m3 120 \
  --pb-atma 130 \
  --t-res-c 80 \
  --bob-m3m3 1.2 \
  --muob-cp 0.6 \
  --fw-perc 10 \
  --q-gas-free-sm3day 0
```

### Сценарий pump-dp (давления/КПД/мощности через calc_ESP)

```bash
ufpy-esp-synth generate \
  --scenario pump-dp \
  --esp-id 1006 \
  --n-files 3 \
  --workers 3 \
  --output-dir ./out \
  --time-step 10min \
  --n-points 144 \
  --stage-num 250 \
  --pump-freq-hz 50 \
  --p-int-atma 100 \
  --t-int-c 30 \
  --gamma-g 0.6 --gamma-o 0.86 --gamma-w 1.1 \
  --rsb-m3m3 120 --rp-m3m3 120 \
  --pb-atma 130 \
  --t-res-c 80 \
  --bob-m3m3 1.2 \
  --muob-cp 0.6 \
  --fw-perc 10 \
  --q-gas-free-sm3day 0
```

### Сценарий esp-system (насос + мотор через ESPSystem.calc_esp_system)

```bash
ufpy-esp-synth generate \
  --scenario esp-system \
  --esp-id 1006 \
  --n-files 4 \
  --workers 2 \
  --output-dir ./out \
  --time-step 15min \
  --n-points 96 \
  --stage-num 250 \
  --pump-freq-hz 50 \
  --p-int-atma 100 \
  --t-int-c 50 \
  --gamma-g 0.6 --gamma-o 0.86 --gamma-w 1.1 \
  --rsb-m3m3 120 --rp-m3m3 120 \
  --pb-atma 130 \
  --t-res-c 80 \
  --bob-m3m3 1.2 \
  --muob-cp 0.6 \
  --fw-perc 10 \
  --q-gas-free-sm3day 0 \
  --u-surf-v 1000 \
  --motor-u-nom-lin-v 1000 \
  --motor-p-nom-kw 30 \
  --motor-f-nom-hz 50 \
  --motor-eff-nom-fr 0.82 \
  --motor-cosphi-nom-fr 0.88 \
  --motor-slip-nom-fr 0.053 \
  --motor-id 2
```

## Пример структуры parquet

Ниже приведён пример схемы (колонки и смысл) для сценария `esp-system`. Прочие сценарии — подмножества (см. `domain/schema.py` в коде).

- `value_date`: datetime64[ns]
- `esp_id`: id насоса из `esp_db.json`
- `run_id`: номер прогона (0..n_files-1)

Параметры насоса и условия:
- `stage_num`, `pump_freq_hz`
- `p_int_atma`, `t_int_c`

PVT входы:
- `gamma_g`, `gamma_o`, `gamma_w`, `rsb_m3m3`, `rp_m3m3`, `pb_atma`, `t_res_c`, `bob_m3m3`, `muob_cp`, `fw_fr`, `q_gas_free_sm3day`
- `q_liq_sm3day` (временной профиль расхода)

PVT промежуточные (на приёме, честные «результаты расчёта PVT»):
- `mu_mix_cst`, `gas_fraction_d`, `q_mix_rc_m3day`

Выходы насоса:
- `p_dis_atma`, `t_dis_c`, `head_m`, `eff_esp_d`, `power_fluid_w`, `power_esp_w`
- `system_eff_d` (выход `ESPSystem.eff_d`)

Входы мотора:
- `u_surf_v`, `motor_u_nom_lin_v`, `motor_p_nom_kw`, `motor_f_nom_hz`, `motor_eff_nom_fr`, `motor_cosphi_nom_fr`, `motor_slip_nom_fr`, `motor_id`

Выходы мотора:
- `motor_u_lin_v`, `motor_i_lin_a`, `motor_cosphi`, `motor_slip`, `motor_eff_d`
- `motor_p_shaft_kw`, `motor_p_electr_kw`
- `motor_power_cs_kw`, `motor_eff_full_d`, `motor_load_d`
- `motor_speed_rpm` (строго выводится из `f_hz` и `slip` по формуле модели)

# ПРИМЕР

```
python -m ufpy_esp_synth.cli.main --scenario esp-system --esp-id 1006 --n-files 1 --workers 1 --output-dir ./out_system_day --time-step 1min --n-points 1440 --esp-db-path ./initial-data/esp_db.json --stage-num 250 --pump-freq-hz 50 --p-int-atma 120 --t-int-c 60 --gamma-g 0.7 --gamma-o 0.86 --gamma-w 1.0 --rsb-m3m3 100 --rp-m3m3 100 --pb-atma 130 --t-res-c 80 --bob-m3m3 1.2 --muob-cp 1.5 --fw-perc 30 --q-gas-free-sm3day 0 --u-surf-v 1000 --motor-u-nom-lin-v 1000 --motor-p-nom-kw 45 --motor-f-nom-hz 50 --motor-eff-nom-fr 0.85 --motor-cosphi-nom-fr 0.9 --motor-slip-nom-fr 0.04 --motor-id 2
```
# Входные параметры

## 2.1. Общие параметры генерации

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--scenario` | scenario | Тип расчёта: `pump-only`, `pump-dp`, `esp-system` |
| `--n-files` | n_files | Количество генерируемых parquet-файлов |
| `--workers` | workers | Количество параллельных процессов |
| `--output-dir` | output_dir | Директория для сохранения |
| `--time-step` | time_step | Шаг времени (`1min`, `1h`, `30min`) |
| `--n-points` | n_points | Количество точек (строк) |

---

## 2.2. Параметры насоса

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--esp-id` | esp_id | ID насоса из базы ufpy |
| `--stage-num` | stage_num | Количество ступеней |
| `--pump-freq-hz` | pump_freq_hz | Частота вращения насоса (Гц) |

---

## 2.3. Условия на входе

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--p-int-atma` | p_int_atma | Давление на приёме насоса (атм) |
| `--t-int-c` | t_int_c | Температура на приёме (°C) |

---

## 2.4. PVT (состав флюида)

### Плотности

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--gamma-g` | gamma_g | Относительная плотность газа |
| `--gamma-o` | gamma_o | Относительная плотность нефти |
| `--gamma-w` | gamma_w | Относительная плотность воды |

---

### Газовые параметры

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--rsb-m3m3` | rsb_m3m3 | Газосодержание при насыщении |
| `--rp-m3m3` | rp_m3m3 | Текущий газовый фактор |
| `--pb-atma` | pb_atma | Давление насыщения |

---

### Температура пласта

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--t-res-c` | t_res_c | Температура пласта |

---

### Свойства нефти

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--bob-m3m3` | bob_m3m3 | Объёмный коэффициент нефти |
| `--muob-cp` | muob_cp | Вязкость нефти (сП) |

---

### Обводнённость

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--fw-perc` | fw_fr | Обводнённость (доля) |

---

### Свободный газ

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--q-gas-free-sm3day` | q_gas_free_sm3day | Свободный газ (м³/сут) |

---

## 2.5. Параметры мотора (только esp-system)

| CLI аргумент | Поле | Описание |
|-------------|------|----------|
| `--u-surf-v` | u_surf_v | Напряжение на поверхности |
| `--motor-u-nom-lin-v` | motor_u_nom_lin_v | Номинальное напряжение |
| `--motor-p-nom-kw` | motor_p_nom_kw | Номинальная мощность |
| `--motor-f-nom-hz` | motor_f_nom_hz | Номинальная частота |
| `--motor-eff-nom-fr` | motor_eff_nom_fr | Номинальный КПД |
| `--motor-cosphi-nom-fr` | motor_cosphi_nom_fr | cos φ |
| `--motor-slip-nom-fr` | motor_slip_nom_fr | Скольжение |
| `--motor-id` | motor_id | Тип модели мотора |

---

# 3. Выходные данные (parquet)

## 3.1. Общие

| Поле | Описание |
|------|----------|
| `value_date` | Временная метка |
| `esp_id` | ID насоса |
| `run_id` | Номер запуска |

---

## 3.2. Конфигурация

| Поле | Описание |
|------|----------|
| `stage_num` | Число ступеней |
| `pump_freq_hz` | Частота насоса |

---

## 3.3. Входные условия

| Поле | Описание |
|------|----------|
| `p_int_atma` | Давление на приёме |
| `t_int_c` | Температура на приёме |

---

## 3.4. PVT

| Поле | Описание |
|------|----------|
| `gamma_g` | Плотность газа |
| `gamma_o` | Плотность нефти |
| `gamma_w` | Плотность воды |
| `rsb_m3m3` | Газосодержание |
| `rp_m3m3` | Газовый фактор |
| `pb_atma` | Давление насыщения |
| `t_res_c` | Температура пласта |
| `bob_m3m3` | Коэффициент объёма |
| `muob_cp` | Вязкость нефти |
| `fw_fr` | Обводнённость |
| `q_gas_free_sm3day` | Свободный газ |

---

## 3.5. Управляющий параметр

| Поле | Описание |
|------|----------|
| `q_liq_sm3day` | Расход жидкости |

---

## 3.6. Расчёт PVT

| Поле | Описание |
|------|----------|
| `mu_mix_cst` | Вязкость смеси |
| `gas_fraction_d` | Доля газа |
| `q_mix_rc_m3day` | Смесь в рабочих условиях |

---

## 3.7. Насос

| Поле | Описание |
|------|----------|
| `p_dis_atma` | Давление на выходе |
| `t_dis_c` | Температура на выходе |
| `head_m` | Напор |
| `eff_esp_d` | КПД насоса |
| `power_fluid_w` | Мощность жидкости |
| `power_esp_w` | Мощность насоса |

---

## 3.8. Система (esp-system)

| Поле | Описание |
|------|----------|
| `system_eff_d` | КПД системы |
| `motor_u_lin_v` | Линейное напряжение |
| `motor_i_lin_a` | Линейный ток |
| `motor_cosphi` | cos φ |
| `motor_slip` | Скольжение |
| `motor_eff_d` | КПД мотора |
| `motor_p_shaft_kw` | Мощность на валу |
| `motor_p_electr_kw` | Электрическая мощность |
| `motor_power_cs_kw` | Полная мощность |
| `motor_eff_full_d` | Полный КПД |
| `motor_load_d` | Загрузка |
| `motor_speed_rpm` | Обороты двигателя |