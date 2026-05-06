# ufpy-esp-synth

English version: [README.md](./README.md)

Детерминированный генератор синтетических датасетов ЭЦН, построенный поверх `ufpy`.

Этот проект не является самостоятельным физическим движком. Основные инженерные расчёты выполняет `ufpy`, а данный репозиторий отвечает за:
- оркестрацию сценариев
- JSON `control plan`
- детерминированную генерацию окон
- экспорт в parquet
- сокращённый telemetry export
- построение графиков

Сейчас основной рекомендуемый сценарий: `well-esp-system`, где модель решает цепочку:

`IPR -> забойное давление -> приток -> состояние на приёме насоса -> рабочая точка ЭЦН -> моторная телеметрия`

## Что Делает Проект

На каждом timestamp программа:
1. читает текущее состояние из CLI-параметров и активного сегмента `control plan`
2. строит модель `WellESP`
3. решает скважину для заданного эксплуатационного ограничения, обычно фиксированного устьевого давления
4. вычисляет приток, забойное давление, давление на приёме, напор насоса, мощность, ток, загрузку и связанные выходы
5. сохраняет полный инженерный state в основной parquet
6. сохраняет сокращённый набор операторских сигналов в отдельный telemetry parquet

Генератор детерминированный:
- фиксированное начало временной оси
- отсутствие случайного шума внутри расчётов
- стабильная сортировка по `run_id`

## Сценарии

Поддерживаемые сценарии:
- `pump-only`
- `pump-dp`
- `esp-system`
- `well-esp-system`

Рекомендуемый сценарий для реалистичного поведения скважины:
- `well-esp-system`

Краткое описание:
- `pump-only`: прямой расчёт насосных кривых
- `pump-dp`: гидравлический расчёт насоса
- `esp-system`: насос + двигатель при прямых входах на приёме
- `well-esp-system`: скважина + IPR + гидравлика приёма + ЭЦН + двигатель

## Установка

Требования:
- Python `3.11+`
- установленный `ufpy`

Сначала установите `ufpy`:

```bash
git clone https://gitverse.ru/shars/ufpy
python -m pip install -U pip
python -m pip install -e ./ufpy
```

Потом установите этот проект:

```bash
git clone https://github.com/avysik/esp-shutdown-predict
cd esp-shutdown-predict
python -m pip install -e .
```

## CLI Entry Points

Генератор:

```bash
ufpy-esp-synth --help
```

Plotting:

```bash
ufpy-esp-plot-windows --help
```

Эквивалентные Python entry points:

```bash
python -m ufpy_esp_synth.cli.main --help
python -m ufpy_esp_synth.plot_windows --help
```

Важно:
- в текущей раскладке CLI используйте `ufpy-esp-synth --scenario ...`
- не нужно добавлять `generate`

## Основные Входы Для `well-esp-system`

### Inflow / IPR

- `--ipr-mode linear-pi | vogel-test-point`
- `--p-res-atma`
- `--productivity-index`
- `--q-test-sm3day`
- `--p-test-atma`

Рекомендуемый режим:
- `linear-pi`

Используйте `productivity_index`, если хотите строить сценарии напрямую от продуктивности скважины.

### Геометрия Скважины

- `--p-wh-atma`
- `--p-cas-atma`
- `--t-wf-c`
- `--t-surface-c`
- `--h-perf-m`
- `--h-esp-m`
- `--d-tub-mm`
- `--d-cas-mm`

### Насос / Двигатель / Флюид

- `--esp-id`
- `--stage-num`
- `--pump-freq-hz`
- `--u-surf-v`
- PVT-входы: `gamma_*`, `rsb`, `rp`, `pb`, `t_res`, `bob`, `muob`, `fw`, `q_gas_free`

## Выходные Файлы

На каждый `run_id` создаются:
- основной parquet:
  `{scenario}__esp_{esp_id}__run_{run_id:05d}.parquet`
- telemetry parquet:
  `{scenario}__esp_{esp_id}__run_{run_id:05d}__telemetry.parquet`

Основной parquet содержит полный инженерный state.

Telemetry parquet содержит сокращённую operational schema для диагностики и signal-oriented задач.

## Telemetry Schema

Порядок колонок telemetry parquet:

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

Сейчас реально заполняются из модели:
- `Активная мощность`
- `Загрузка`
- `Коэффиц.мощности`
- `Напряжение`
- `Р на приеме насоса`
- `Ток`

Сейчас отсутствуют в физической модели и экспортируются как `NaN`:
- `Дисбаланс напряжений`
- `Дисбаланс токов`
- `Сопротив.изоляции`
- `Температура двигателя`

## Control Plans

Генератор поддерживает JSON `control plan` через `--control-plan-path`.

Доступные секции:
- `base`
- `segments`
- `events`
- `rules`

Типичные override-поля:
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

Для кусочно-стационарных окон используйте `segments`.

## Готовые Demo-Сценарии

Подготовленные примеры в `examples/`:
- `control_plan_well_productivity_decline_2h.json`
- `control_plan_well_pwh_growth_2h.json`
- `control_plan_well_freq_stepup_2h.json`
- `control_plan_well_qtest_demo_2h.json`
- legacy pump/system demos и shutdown examples

### 1. Падение Продуктивности За 2 Часа

Смысл:
- `productivity_index` снижается на 9 точках
- приток падает
- давление на приёме падает
- рабочая точка насоса перестраивается

Запуск:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.cli.main --scenario well-esp-system --esp-id 1006 --n-files 1 --workers 1 --output-dir .\out_well_productivity_2h --time-step 15min --n-points 9 --control-plan-path .\examples\control_plan_well_productivity_decline_2h.json --stage-num 250 --pump-freq-hz 50 --gamma-g 0.7 --gamma-o 0.86 --gamma-w 1.0 --rsb-m3m3 100 --rp-m3m3 100 --pb-atma 130 --t-res-c 80 --bob-m3m3 1.2 --muob-cp 1.5 --fw-perc 30 --q-gas-free-sm3day 0 --ipr-mode linear-pi --p-res-atma 250 --productivity-index 0.55 --p-test-atma 200 --p-wh-atma 20 --p-cas-atma 10 --t-wf-c 80 --t-surface-c 20 --h-perf-m 1500 --h-esp-m 1200 --d-tub-mm 62 --d-cas-mm 150 --u-surf-v 1000 --motor-u-nom-lin-v 1000 --motor-p-nom-kw 45 --motor-f-nom-hz 50 --motor-eff-nom-fr 0.85 --motor-cosphi-nom-fr 0.9 --motor-slip-nom-fr 0.04 --motor-id 2
```

### 2. Рост Устьевого Давления За 2 Часа

Смысл:
- `p_wh_atma` растёт
- гидравлика скважины перестраивается под новый target
- приток и условия на приёме меняются как следствие

Запуск:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.cli.main --scenario well-esp-system --esp-id 1006 --n-files 1 --workers 1 --output-dir .\out_well_pwh_growth_2h --time-step 15min --n-points 9 --control-plan-path .\examples\control_plan_well_pwh_growth_2h.json --stage-num 250 --pump-freq-hz 50 --gamma-g 0.7 --gamma-o 0.86 --gamma-w 1.0 --rsb-m3m3 100 --rp-m3m3 100 --pb-atma 130 --t-res-c 80 --bob-m3m3 1.2 --muob-cp 1.5 --fw-perc 30 --q-gas-free-sm3day 0 --ipr-mode linear-pi --p-res-atma 250 --productivity-index 0.55 --p-test-atma 200 --p-wh-atma 12 --p-cas-atma 10 --t-wf-c 80 --t-surface-c 20 --h-perf-m 1500 --h-esp-m 1200 --d-tub-mm 62 --d-cas-mm 150 --u-surf-v 1000 --motor-u-nom-lin-v 1000 --motor-p-nom-kw 45 --motor-f-nom-hz 50 --motor-eff-nom-fr 0.85 --motor-cosphi-nom-fr 0.9 --motor-slip-nom-fr 0.04 --motor-id 2
```

### 3. Рост Частоты Насоса С 50 До 52 Гц

Смысл:
- оператор поднимает частоту насоса
- расход растёт
- давление на приёме падает
- ток и мощность растут

Запуск:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.cli.main --scenario well-esp-system --esp-id 1006 --n-files 1 --workers 1 --output-dir .\out_well_freq_stepup_2h --time-step 15min --n-points 9 --control-plan-path .\examples\control_plan_well_freq_stepup_2h.json --stage-num 250 --pump-freq-hz 50 --gamma-g 0.7 --gamma-o 0.86 --gamma-w 1.0 --rsb-m3m3 100 --rp-m3m3 100 --pb-atma 130 --t-res-c 80 --bob-m3m3 1.2 --muob-cp 1.5 --fw-perc 30 --q-gas-free-sm3day 0 --ipr-mode linear-pi --p-res-atma 250 --productivity-index 0.55 --p-test-atma 200 --p-wh-atma 20 --p-cas-atma 10 --t-wf-c 80 --t-surface-c 20 --h-perf-m 1500 --h-esp-m 1200 --d-tub-mm 62 --d-cas-mm 150 --u-surf-v 1000 --motor-u-nom-lin-v 1000 --motor-p-nom-kw 45 --motor-f-nom-hz 50 --motor-eff-nom-fr 0.85 --motor-cosphi-nom-fr 0.9 --motor-slip-nom-fr 0.04 --motor-id 2
```

## Построение Графиков

### Графики по всем меняющимся метрикам из основного parquet

Пример:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.plot_windows --input-parquet .\out_well_productivity_2h\well-esp-system__esp_1006__run_00000.parquet --output-png .\out_well_productivity_2h\well_productivity_full_series.png --metrics --varying-only --full-series --split-metrics --keep-combined
```

На выходе:
- один общий PNG
- один PNG на каждую меняющуюся метрику

### Графики по telemetry parquet

Пример:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.plot_windows --input-parquet .\out_well_productivity_2h\well-esp-system__esp_1006__run_00000__telemetry.parquet --output-png .\out_well_productivity_2h\well_productivity_telemetry.png --metrics --varying-only --full-series --split-metrics --keep-combined
```

### График окна с наложением нескольких window traces

Если parquet содержит несколько окон, используйте:

```powershell
.\.venv\Scripts\python.exe -m ufpy_esp_synth.plot_windows --input-parquet .\out_demo_2h\esp-system__esp_1006__run_00000.parquet --output-png .\out_demo_2h\window_analysis.png --points-per-window 9
```

## Генератор Фонда

Для массовой генерации датасета по фонду используйте `src/wrapper.py` в режиме `fleet`.

Генератор фонда:
- загружает архетипы из `examples/fleet_archetypes/well_esp_archetypes_v1.json`
- строит детерминированные базовые состояния внутри каждого архетипа через Latin hypercube sampling
- подбирает совместимые `esp_id` и `stage_num`
- калибрует устойчивую базовую рабочую точку
- накладывает поверх неё рекомендованные семейства сценариев
- пишет по одному основному parquet, одному telemetry parquet и одному `control_plan.json` на каждое окно

### Пилотный Запуск

Сначала используйте этот запуск, чтобы убедиться, что end-to-end генерация работает на вашем компьютере:

```powershell
.\.venv\Scripts\python.exe .\src\wrapper.py --mode fleet --archetype-filter A03 --samples-per-archetype 1 --candidate-multiplier 12 --workers 1 --limit 4 --output-base-dir .\out_fleet_pilot_v1
```

Эта команда создаёт маленький реальный batch:
- один архетип: `A03`
- один принятый базовый sample
- до четырёх scenario windows
- полный вывод parquet и telemetry

### Большой Batch-Запуск

После успешного пилота используйте на более мощной машине:

```powershell
.\.venv\Scripts\python.exe .\src\wrapper.py --mode fleet --samples-per-archetype 100 --candidate-multiplier 12 --workers 16 --output-base-dir .\out_fleet_batch_v1
```

### Опциональный Dry Run

Если хотите сначала оценить покрытие без полного вычислительного прогона, используйте:

```powershell
.\.venv\Scripts\python.exe .\src\wrapper.py --mode fleet --samples-per-archetype 100 --candidate-multiplier 12 --workers 1 --dry-run --output-base-dir .\out_fleet_batch_v1_dry
```

Dry run строит fleet-план, калибрует candidate base states, подбирает насосы и пишет `fleet_manifest.parquet` и `fleet_summary.json`, но не выполняет полную генерацию parquet-окон для каждого сценария.

### Что Получится После Big Batch

Для текущей библиотеки архетипов `v1`, при `recommended_only=true`, включённых трёх уровнях тяжести и предположении, что все `10` архетипов примут по `100` базовых sample, объём будет таким:

- принятые базовые состояния: до `1000`
- семейства сценариев:
  - `stable_normal`
  - `inflow_deterioration`
  - `wellhead_backpressure_growth`
  - `watercut_growth`
  - `viscosity_growth`
  - `voltage_sag`
- быстрые окна:
  - `stable_normal`
  - `inflow_deterioration`
  - `wellhead_backpressure_growth`
  - `voltage_sag`
  - спецификация: `2h`, `9` точек, `15min`
- медленные окна:
  - `watercut_growth`
  - `viscosity_growth`
  - спецификация: `4h`, `9` точек, `30min`

В текущей матрице рекомендаций это даёт `85` окон на один полный проход по архетипам, поэтому для batch с `100` sample на архетип целевой объём такой:

- всего окон: до `8500`
- всего строк в основных parquet: `76 500`
- всего строк в telemetry parquet: `76 500`

Ожидаемое распределение окон по семействам:

- `stable_normal`: `1000`
- `inflow_deterioration`: `600`
- `wellhead_backpressure_growth`: `2400`
- `watercut_growth`: `1200`
- `viscosity_growth`: `900`
- `voltage_sag`: `2400`

В каталоге каждого окна будут:
- `control_plan.json`
- один основной parquet
- один telemetry parquet

В корне датасета дополнительно будут:
- `fleet_manifest.parquet`
- `fleet_summary.json`

Важно:
- фактический объём может быть меньше, если часть candidate base states не пройдёт калибровку
- сначала прогоняйте pilot
- перед многосуточным production batch лучше делать `dry-run`
- текущая telemetry-семантика уже выровнена ближе к полевым данным:
  - `Напряжение` экспортируется как линейное напряжение в эквиваленте `400 V`
  - `Р на приеме насоса` экспортируется в `MPa`
  - `Загрузка` экспортируется в `%`

## Важные Поля Основного Parquet Для `well-esp-system`

Полезные инженерные колонки:
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

Эти колонки нужны именно для инженерной проверки модели, а не только для ML-export.

## Качество Solver-а

Для `well-esp-system` код теперь сохраняет явные поля качества решения:
- `well_solver_ok`
- `wellhead_target_error_atma`

Используйте их, чтобы отфильтровывать невалидные точки при агрессивных сценариях.

## Ограничения

- Модель кусочно-стационарная, не переходная.
- Репозиторий не моделирует напрямую сопротивление изоляции двигателя, фазные дисбалансы и температуру двигателя.
- Газовое поведение сильно зависит от стадии separation внутри `WellESP`; низкое давление на приёме не означает автоматически большую газовую долю у насоса, если свободный газ удаляется до насоса.
- Telemetry parquet специально сокращён и не содержит полный well state.

## Тестирование

Полный запуск тестов:

```bash
python -m pytest -q
```

Полезный focused regression run:

```bash
python -m pytest tests/test_well_esp_system.py -q
```

## Позиционирование Проекта

Этот репозиторий следует понимать как:
- детерминированный генератор сценариев
- слой dataset/export
- control-plan wrapper над `ufpy`

И не следует понимать как:
- независимую замену `ufpy`
- полноценный transient multiphase simulator

Физика живёт в `ufpy`.
Оркестрация, сценарная логика, структура датасета, telemetry export и plotting живут здесь.
