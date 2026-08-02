#!/usr/bin/env python3
"""
Тест: взлёт, YOLO-поиск + VLM-анализ.
ЛЕТИМ → ИЩЕМ → нашли → VLM → вывод точки и результата VLM.
Использование: python3 test_yolo_search_vlm.py <drone_ip> <password>
"""

import paramiko
import sys
import os
import random
import json

# ═══════════════════════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════════════════════

DRONE_USER = "sverk"

ALTITUDE = 2.0
SPEED = 0.5
SEARCH_DURATION = 8.0

FINISH_X = 0.0
FINISH_Y = 0.0

WAYPOINTS = [
    (0.4, 4.425),
    (1.205, 1.205),
]

RANDOM_OFFSET_RANGE = 0.3

LOCAL_MODEL_PATH = r"C:\Users\slava\Desktop\code_new_top\BST_a26_st3-master\BST_a26_st3-master\best.pt"
DRONE_MODEL_DIR = "/home/sverk/yolo_models"
DRONE_MODEL_NAME = "yolo_model.pt"

YOLO_MODEL_NAME = "yolo11n.pt"
YOLO_CLASS_NAME = None
YOLO_CONFIDENCE = 0.5

VLM_API_KEY = "sk-jkx31e2PLKxCpjOynEwyxA"
VLM_API_BASE = "https://ai.sverk.tech/v1"
VLM_MODEL = "gemma4-vlm"

# ═══════════════════════════════════════════════════════════════════════════════
# БОРТОВОЙ СКРИПТ
# ═══════════════════════════════════════════════════════════════════════════════

ONBOARD_SCRIPT = f'''
import time
import sys
import os
import signal
import random
import json
import math
import base64
import urllib.request

import sverk_interfaces
import cv2
from ultralytics import YOLO

ALTITUDE = {ALTITUDE}
SPEED = {SPEED}
SEARCH_DURATION = {SEARCH_DURATION}
FINISH_X = {FINISH_X}
FINISH_Y = {FINISH_Y}
WAYPOINTS = {json.dumps(WAYPOINTS)}
RANDOM_OFFSET_RANGE = {RANDOM_OFFSET_RANGE}
DRONE_MODEL_DIR = "{DRONE_MODEL_DIR}"
DRONE_MODEL_NAME = "{DRONE_MODEL_NAME}"
YOLO_CLASS_NAME = {repr(YOLO_CLASS_NAME)}
YOLO_CONFIDENCE = {YOLO_CONFIDENCE}
MODEL_UPLOADED = {LOCAL_MODEL_PATH is not None}
VLM_API_KEY = "{VLM_API_KEY}"
VLM_API_BASE = "{VLM_API_BASE}"
VLM_MODEL = "{VLM_MODEL}"

VLM_PROMPT = \"\"\"Ты — специализированный детектор целевого объекта (плюшевая игрушка Чебурашка) на бортовом компьютере дрона.
Перед тобой кадр с камеры дрона, направленной строго вниз на игровое поле, разделенное на квадратные клетки.
Дрон висит над центром одной клетки (Центральная клетка под дроном = область в центре кадра).
По краям кадра могут быть частично видны соседние клетки.
Твоя задача — проанализировать аэроснимок игрового поля сверху и найти целевые объекты — мягкие/плюшевые игрушки Чебурашки.


### 1. ВИЗУАЛЬНЫЕ ПРИЗНАКИ И ИСКЛЮЧЕНИЯ:
- ЦЕЛЕВОЙ ОБЪЕКТ "ЧЕБУРАШКА": Плюшевая игрушка в оттенках коричневого.
  Ключевые признаки сверху: огромные округлые уши, плюшевая фактура, светлая зона мордочки/грудки.
- ИСКЛЮЧЕНИЯ: плоские коричневые элементы, кубики, тени — НЕ Чебурашка.

### 2. ПРАВИЛА ЛОКАЛИЗАЦИИ:
- "center" — объект прямо под дроном.
- "left", "right", "up", "down", "up-left", "up-right", "down-left", "down-right" — в соседней клетке.
- "none" — объект не обнаружен.

### 3. ФОРМАТ ОТВЕТА (строго JSON):
{{
  "cheburashka": true,
  "confidence": 0.95,
  "direction": "center",
  "summary": "краткое резюме"
}}\"\"\"

drone = None
yolo_model = None
should_stop = False
target_found = False
found_point = None
vlm_result_cache = None
frame_counter = 0


def _signal_handler(sig, frame):
    global should_stop
    should_stop = True
    print("SIGNAL: прерывание")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def safe_land():
    try:
        print("[LAND] начинаю посадку...")
        drone.control.land()
        time.sleep(3)
        print("[LAND] посадка выполнена")
    except Exception as e:
        print(f"[LAND] ОШИБКА: {{e}}")


def vlm_analyze(frame):
    try:
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        b64 = base64.b64encode(buf).decode()
        print(f"[VLM] отправка кадра ({{len(b64)}} символов b64)...")
        t0 = time.time()

        payload = {{
            "model": VLM_MODEL,
            "max_tokens": 200,
            "messages": [
                {{"role": "system", "content": VLM_PROMPT}},
                {{"role": "user", "content": [
                    {{"type": "text", "text": "Проанализируй этот кадр и найди Чебурашку."}},
                    {{"type": "image_url", "image_url": {{"url": f"data:image/jpeg;base64,{{b64}}"}}}}
                ]}}
            ]
        }}

        req = urllib.request.Request(
            f"{{VLM_API_BASE}}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={{"Content-Type": "application/json", "Authorization": f"Bearer {{VLM_API_KEY}}"}},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"].get("content", "")

        elapsed = (time.time() - t0) * 1000
        print(f"[VLM] ответ за {{elapsed:.0f}} мс")

        raw = content.strip()
        if raw.startswith("```"):
            raw = raw.split("\\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)

    except Exception as e:
        print(f"[VLM] ошибка: {{type(e).__name__}}: {{e}}")
        return None


def run_yolo_on_frame(frame):
    global target_found, found_point, vlm_result_cache, frame_counter
    frame_counter += 1
    annotated = frame.copy()
    results = yolo_model(frame, verbose=False)

    detected_anything = False
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = yolo_model.names[cls_id]
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            if YOLO_CLASS_NAME is not None and cls_name != YOLO_CLASS_NAME:
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 1)
                continue

            if conf >= YOLO_CONFIDENCE:
                detected_anything = True
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(annotated, f"{{cls_name}} {{conf:.2f}}",
                            (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            else:
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 1)

    try:
        drone.image.publish(annotated)
    except Exception:
        pass

    return detected_anything


def search_at_point(current_point):
    global target_found, found_point, vlm_result_cache, should_stop
    wx, wy = current_point
    print(f"[SEARCH] поиск у точки ({{wx:.3f}}, {{wy:.3f}}), {{SEARCH_DURATION:.0f}} сек...")
    t0 = time.time()
    frames_ok = 0
    last_report = 0
    while time.time() - t0 < SEARCH_DURATION and not target_found and not should_stop:
        frame = drone.image.take_picture(timeout=1.0)
        if frame is not None:
            frames_ok += 1
            if run_yolo_on_frame(frame):
                target_found = True
                found_point = current_point
                cv2.imwrite("/tmp/cheburashka_found.jpg", frame)
                print(f"[DETECT] фото: /tmp/cheburashka_found.jpg")
                print(f"[DETECT] синий LED 5 сек...")
                try:
                    drone.led.set_effect("fill", r=0, g=0, b=255)
                    time.sleep(5)
                    drone.led.set_effect("fill", r=0, g=0, b=0) if drone.led else None
                except Exception as e:
                    print(f"[DETECT] LED error: {{e}}")
                elapsed = time.time() - t0
                print(f"\\n[DETECT] *** ОБЪЕКТ НАЙДЕН ***")
                print(f"[DETECT] точка: ({{wx:.3f}}, {{wy:.3f}})")
                print(f"[DETECT] время: {{elapsed:.1f}} сек, кадров: {{frames_ok}}")

                print(f"\\n[VLM] запуск анализа...")
                vlm_result_cache = vlm_analyze(frame)
                if vlm_result_cache:
                    print(f"[VLM] cheburashka={{vlm_result_cache.get('cheburashka')}} "
                          f"conf={{vlm_result_cache.get('confidence')}} "
                          f"dir={{vlm_result_cache.get('direction')}}")
                    print(f"[VLM] summary: {{vlm_result_cache.get('summary')}}")
                else:
                    print(f"[VLM] ошибка: ответ не получен")
                return
        time.sleep(0.1)

        elapsed = time.time() - t0
        if elapsed - last_report >= 2.0:
            print(f"[SEARCH] ... {{elapsed:.0f}} сек, кадров: {{frames_ok}}, всего: {{frame_counter}}")
            last_report = elapsed

    if not target_found:
        print(f"[SEARCH] завершён, кадров: {{frames_ok}}, цель не найдена")


def load_model():
    model_path = os.path.join(DRONE_MODEL_DIR, DRONE_MODEL_NAME)
    print(f"[MODEL] путь: {{model_path}}")
    if MODEL_UPLOADED and os.path.exists("/tmp/yolo_upload.pt"):
        print("[MODEL] установка загруженной модели...")
        os.makedirs(DRONE_MODEL_DIR, exist_ok=True)
        if os.path.exists(model_path):
            os.remove(model_path)
        import shutil
        shutil.move("/tmp/yolo_upload.pt", model_path)

    if os.path.exists(model_path):
        print(f"[MODEL] загрузка из {{model_path}}...")
        m = YOLO(model_path)
    else:
        print(f"[MODEL] авто-скачивание {YOLO_MODEL_NAME}...")
        m = YOLO("{YOLO_MODEL_NAME}")
    print(f"[MODEL] загружена, классов: {{len(m.names)}}")
    return m


def run():
    global drone, yolo_model, should_stop

    print("=" * 50)
    print("[INIT] подключение sverk_interfaces...")
    t0 = time.time()
    drone = sverk_interfaces.init(Nodename="yolo_search_vlm")
    print(f"[INIT] готово ({{time.time() - t0:.1f}} сек)")

    print("[INIT] загрузка YOLO...")
    t0 = time.time()
    yolo_model = load_model()
    print(f"[INIT] готово ({{time.time() - t0:.1f}} сек)")

    try:
        print(f"[TAKEOFF] взлёт на {{ALTITUDE}} м...")
        t0 = time.time()
        drone.control.navigate(
            x=0.0, y=0.0, z=ALTITUDE,
            yaw=0.0, speed=0.7,
            frame_id="body", auto_arm=True,
        )
        print(f"[TAKEOFF] команда отправлена ({{time.time() - t0:.1f}} сек), ожидание 5 сек...")
        time.sleep(5)
        print("[TAKEOFF] взлёт выполнен")

        if should_stop:
            safe_land()
            return

        cycle = 0
        while not target_found and not should_stop:
            cycle += 1
            print(f"\\n{{'=' * 50}}")
            print(f"[CYCLE {{cycle}}] облёт точек")
            random.seed(time.time() + cycle)

            for idx, (wx, wy) in enumerate(WAYPOINTS):
                if should_stop or target_found:
                    break

                offset_x = 0.0
                offset_y = 0.0
                if cycle > 1:
                    offset_x = random.uniform(-RANDOM_OFFSET_RANGE, RANDOM_OFFSET_RANGE)
                    offset_y = random.uniform(-RANDOM_OFFSET_RANGE, RANDOM_OFFSET_RANGE)

                tx = wx + offset_x
                ty = wy + offset_y

                print(f"[FLY {{idx + 1}}/{{len(WAYPOINTS)}}] полёт к ({{tx:.3f}}, {{ty:.3f}})"
                      f"{{'  смещение: +' + format(offset_x, '.2f') + ', +' + format(offset_y, '.2f') if cycle > 1 else ''}}")
                t0 = time.time()
                drone.control.navigate(
                    x=tx, y=ty, z=ALTITUDE,
                    yaw=0.0, speed=SPEED,
                    frame_id="aruco_map", auto_arm=False,
                )
                print(f"[FLY] отправлено ({{time.time() - t0:.1f}} сек), ожидание 4 сек...")
                time.sleep(4)

                if should_stop:
                    break

                search_at_point((tx, ty))

            if should_stop and not target_found:
                print("\\n[ABORT] прерывание")
                print(f"[FINISH] полёт к ({{FINISH_X}}, {{FINISH_Y}})...")
                drone.control.navigate(
                    x=FINISH_X, y=FINISH_Y, z=ALTITUDE,
                    yaw=0.0, speed=SPEED,
                    frame_id="aruco_map", auto_arm=False,
                )
                time.sleep(3)
                safe_land()
                return

        if target_found:
            print(f"\\n{{'=' * 50}}")
            print(f"[RESULT] *** ОБЪЕКТ НАЙДЕН ***")
            print(f"[RESULT] точка: ({{found_point[0]:.3f}}, {{found_point[1]:.3f}})")
            if vlm_result_cache:
                print(f"[RESULT] VLM: cheburashka={{vlm_result_cache.get('cheburashka')}} "
                      f"conf={{vlm_result_cache.get('confidence')}} "
                      f"dir={{vlm_result_cache.get('direction')}}")
                print(f"[RESULT] VLM summary: {{vlm_result_cache.get('summary')}}")
            print(f"[RESULT] кадров: {{frame_counter}}")
            print(f"[FINISH] полёт к ({{FINISH_X}}, {{FINISH_Y}})...")
            drone.control.navigate(
                x=FINISH_X, y=FINISH_Y, z=ALTITUDE,
                yaw=0.0, speed=SPEED,
                frame_id="aruco_map", auto_arm=False,
            )
            time.sleep(3)
            safe_land()

    except Exception as e:
        print(f"[FATAL] {{type(e).__name__}}: {{e}}")
        import traceback
        traceback.print_exc()
        try:
            safe_land()
        except Exception:
            pass
    finally:
        print("[CLEANUP] закрытие ресурсов...")
        try:
            yolo_model = None
            drone.close()
            print("[CLEANUP] завершено")
        except Exception as e:
            print(f"[CLEANUP] ошибка: {{e}}")


if __name__ == "__main__":
    run()
'''

# ═══════════════════════════════════════════════════════════════════════════════
# ХОСТ-СКРИПТ
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import datetime
    if len(sys.argv) < 3:
        print("Использование: python3 test_yolo_search_vlm.py <drone_ip> <password>")
        sys.exit(1)

    drone_ip = sys.argv[1]
    password = sys.argv[2]
    t_start = datetime.datetime.now()
    print(f"[HOST {t_start.strftime('%H:%M:%S')}] === ТЕСТ YOLO-ПОИСКА + VLM ===")
    print(f"[HOST] дрон: {drone_ip}  высота: {ALTITUDE} м  скорость: {SPEED} м/с")
    print(f"[HOST] точек: {len(WAYPOINTS)}  поиск у точки: {SEARCH_DURATION} сек")

    print(f"\n[HOST] [1/4] SSH-подключение к {drone_ip}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(hostname=drone_ip, username=DRONE_USER,
                    password=password, timeout=30)
        print(f"[HOST] [1/4] SSH: OK")

        if LOCAL_MODEL_PATH and os.path.exists(LOCAL_MODEL_PATH):
            size_mb = os.path.getsize(LOCAL_MODEL_PATH) / 1024 / 1024
            print(f"[HOST] [2/4] Загрузка модели {LOCAL_MODEL_PATH} ({size_mb:.1f} МБ) → дрон...")
            sftp = ssh.open_sftp()
            sftp.put(LOCAL_MODEL_PATH, "/tmp/yolo_upload.pt")
            sftp.close()
            print(f"[HOST] [2/4] Модель загружена: OK")
        elif LOCAL_MODEL_PATH:
            print(f"[HOST] [2/4] ПРОПУСК: модель {LOCAL_MODEL_PATH} не найдена локально")
        else:
            print(f"[HOST] [2/4] ПРОПУСК: используется модель на дроне")

        print(f"[HOST] [3/4] Загрузка программы ({len(ONBOARD_SCRIPT)} байт)...")
        sftp = ssh.open_sftp()
        remote_script = "/tmp/_yolo_search_vlm.py"
        with sftp.open(remote_script, "w") as f:
            f.write(ONBOARD_SCRIPT)
        sftp.close()
        print(f"[HOST] [3/4] Программа загружена: OK")

        print(f"[HOST] [4/4] Запуск...")
        print("=" * 60)
        stdin, stdout, stderr = ssh.exec_command(
            f"bash -c 'source ~/sverk_ws/install/setup.bash && python3 {remote_script}'",
            get_pty=True
        )
        for line in iter(stdout.readline, ""):
            print(line, end="")
        err = stderr.read().decode()
        if err:
            print(f"\n[HOST] STDERR:\n{err.strip()}")
        print("=" * 60)

        print(f"[HOST] очистка...")
        sftp = ssh.open_sftp()
        try:
            sftp.remove(remote_script)
        except Exception:
            pass
        sftp.close()

    except Exception as e:
        print(f"[HOST] ОШИБКА: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()
        elapsed = (datetime.datetime.now() - t_start).total_seconds()
        print(f"[HOST] завершено, общее время: {elapsed:.0f} сек")


if __name__ == "__main__":
    main()