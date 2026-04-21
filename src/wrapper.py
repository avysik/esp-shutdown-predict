import json
import subprocess
import os
import sys


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(CURRENT_DIR, 'data', 'esp_db.json')
# Результаты будут складываться в корень проекта в папку out_wrapper
OUTPUT_BASE_DIR = os.path.join(CURRENT_DIR, '..', 'out_wrapper')

def load_db(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл базы данных не найден по пути: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_batch():
    try:
        db = load_db(DB_PATH)
    except Exception as e:
        print(f"Ошибка загрузки БД: {e}")
        return

    # Берем список доступных ID насосов
    # db.keys(X) x = сколько насосов (при отсутствии - все)
    target_esp_ids = list(db.keys())

    for esp_id in target_esp_ids:
        esp = db[esp_id]
        
        # 1. Ступени
        stages = int(esp.get('stages_max', 100) * 0.75)
        
        # 2. Мощность двигателя
        # Находим макс. мощность на ступень и умножаем на кол-во ступеней + N% запас
        p_stage_max = max(esp.get('power_points', [0.1]))
        calc_power = p_stage_max * stages * 1.2
        
        # 3. Дебит номинальный из базы
        q_nom = esp.get('rate_nom_sm3day', 50)
        
        run_dir = os.path.join(OUTPUT_BASE_DIR, f"esp_{esp_id}")

        # Полный список аргументов
        cmd = [
            sys.executable, "-m", "ufpy_esp_synth.cli.main",
            "--scenario", "esp-system",
            "--esp-id", str(esp_id),
            "--n-files", "1",
            "--workers", "1",
            "--output-dir", run_dir,
            "--time-step", "1min",
            "--n-points", "1440",
            "--esp-db-path", DB_PATH,
            "--stage-num", str(stages),
            "--pump-freq-hz", "50",
            "--motor-p-nom-kw", str(round(calc_power, 2)),
            "--q-gas-free-sm3day", str(q_nom),
            "--p-int-atma", "120",
            "--t-int-c", "60",
            "--gamma-g", "0.7",
            "--gamma-o", "0.86",
            "--gamma-w", "1.0",
            "--rsb-m3m3", "100",
            "--rp-m3m3", "100",
            "--pb-atma", "130",
            "--t-res-c", "80",
            "--bob-m3m3", "1.2",
            "--muob-cp", "1.5",
            "--fw-perc", "30",
            "--u-surf-v", "1000",
            "--motor-u-nom-lin-v", "1000",
            "--motor-f-nom-hz", "50",
            "--motor-eff-nom-fr", "0.85",
            "--motor-cosphi-nom-fr", "0.9",
            "--motor-slip-nom-fr", "0.04",
            "--motor-id", "2"
        ]

        print(f"--- Генерация: {esp['name']} (ID: {esp_id}) ---")
        
        try:
            subprocess.run(cmd, check=True, cwd=CURRENT_DIR)
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при работе с насосом {esp_id}: {e}")
        except Exception as e:
            print(f"Непредвиденная ошибка: {e}")

if __name__ == "__main__":
    run_batch()