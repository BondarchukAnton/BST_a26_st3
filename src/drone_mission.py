"""
Модуль дрона: сборка и запуск бортового скрипта.
Объединяет:
  - YOLO-поиск объекта + VLM-верификацию (из yolo_search_vlm_best.py)
  - Полёт к роверу
  - Посадку на ArUco-метку (из aruco_land.py)

Бортовой скрипт формируется как строка Python-кода, загружается
на дрон по SSH и выполняется. Вывод парсится для извлечения результата.
"""

import os
import json
import time
import datetime
import paramiko


from config.settings import (
    ALTITUDE, SPEED, SEARCH_DURATION, RANDOM_OFFSET_RANGE,
    WAYPOINT_A1, WAYPOINT_E2, WAYPOINTS, WAYPOINT_NAMES,
    ROVER_POSITION, ROVER_ARUCO_ID,
    YOLO_MODEL_NAME, YOLO_CLASS_NAME, YOLO_CONFIDENCE,
    LOCAL_MODEL_PATH, DRONE_MODEL_DIR, DRONE_MODEL_NAME,
    VLM_API_KEY, VLM_API_BASE, VLM_MODEL,
    SEARCH_ALTITUDE, MIN_LAND_ALTITUDE, FOV_DEG, ARUCO_KP,
    CENTER_TOLERANCE_PX, LOST_MARKER_TIMEOUT, ARUCO_SEARCH_TIMEOUT,
    ARUCO_STEP_DOWN,
    FLY_TO_ROVER_SPEED, LED_DURATION,
    TAKEOFF_SETTLE_TIME, FLY_SETTLE_TIME,
    POST_TAKEOFF_SLEEP,
    DRONE_IP, DRONE_USER, DRONE_PASSWORD,
)

# ═══════════════════════════════════════════════════════════════════════════════
# БОРТОВОЙ СКРИПТ ДРОНА
# ═══════════════════════════════════════════════════════════════════════════════


def build_onboard_script() -> str:
    """
    Формирует полный бортовой скрипт дрона (Python-код для выполнения на дроне).
    Скрипт включает: взлёт, циклический облёт точек с YOLO-поиском,
    VLM-верификацию, полёт к роверу и ArUco-посадку.

    Возвращает строку с Python-кодом.
    """

    # Проверка наличия локальной модели
    has_local_model = (
        LOCAL_MODEL_PATH is not None
        and os.path.exists(LOCAL_MODEL_PATH or "")
    )

    rvx, rvy = ROVER_POSITION

    script = f'''# -*- coding: utf-8 -*-
import time
import sys
import os
import signal
import random
import json
import math
import base64
import urllib.request
from math import tan, radians

import sverk_interfaces
import cv2
from ultralytics import YOLO

try:
    from aruco_det_loc.msg import MarkerArray
    HAS_ARUCO_MSG = True
except ImportError:
    HAS_ARUCO_MSG = False

from rclpy.qos import qos_profile_sensor_data

# ═══════════════════════════════════════════════════════════════════════════
# ПАРАМЕТРЫ МИССИИ (подставлены с хоста)
# ═══════════════════════════════════════════════════════════════════════════
ALTITUDE = {ALTITUDE}
SPEED = {SPEED}
SEARCH_DURATION = {SEARCH_DURATION}
RANDOM_OFFSET_RANGE = {RANDOM_OFFSET_RANGE}
WAYPOINTS = {json.dumps(WAYPOINTS)}
DRONE_MODEL_DIR = "{DRONE_MODEL_DIR}"
DRONE_MODEL_NAME = "{DRONE_MODEL_NAME}"
YOLO_CLASS_NAME = {repr(YOLO_CLASS_NAME)}
YOLO_CONFIDENCE = {YOLO_CONFIDENCE}
MODEL_UPLOADED = {has_local_model}
VLM_API_KEY = "{VLM_API_KEY}"
VLM_API_BASE = "{VLM_API_BASE}"
VLM_MODEL = "{VLM_MODEL}"

ROVER_X = {rvx}
ROVER_Y = {rvy}
FLY_TO_ROVER_SPEED = {FLY_TO_ROVER_SPEED}
LED_DURATION = {LED_DURATION}
TAKEOFF_SETTLE_TIME = {TAKEOFF_SETTLE_TIME}
POST_TAKEOFF_SLEEP = {POST_TAKEOFF_SLEEP}
FLY_SETTLE_TIME = {FLY_SETTLE_TIME}

# Параметры ArUco-посадки
ROVER_ARUCO_ID = {ROVER_ARUCO_ID}
SEARCH_ALTITUDE = {SEARCH_ALTITUDE}
MIN_LAND_ALTITUDE = {MIN_LAND_ALTITUDE}
FOV_DEG = {FOV_DEG}
ARUCO_KP = {ARUCO_KP}
CENTER_TOLERANCE_PX = {CENTER_TOLERANCE_PX}
LOST_MARKER_TIMEOUT = {LOST_MARKER_TIMEOUT}
ARUCO_SEARCH_TIMEOUT = {ARUCO_SEARCH_TIMEOUT}
ARUCO_STEP_DOWN = {ARUCO_STEP_DOWN}

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

# ═══════════════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ═══════════════════════════════════════════════════════════════════════════
drone = None
yolo_model = None
should_stop = False
target_found = False
found_point = None
vlm_result_cache = None
frame_counter = 0

# ArUco-переменные
last_marker_pose = None
last_detection_time = 0.0
marker_found_once = False


def _signal_handler(sig, frame):
    global should_stop
    should_stop = True
    print("SIGNAL: прерывание")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ═══════════════════════════════════════════════════════════════════════════
# YOLO-ПОИСК + VLM
# ═══════════════════════════════════════════════════════════════════════════

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
        result = json.loads(raw)
        print(f"[VLM] raw result: {{json.dumps(result, ensure_ascii=False)}}")
        return result

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
    last_aruco_log = 0
    while time.time() - t0 < SEARCH_DURATION and not target_found and not should_stop:
        if time.time() - last_aruco_log > 3.0:
            try:
                t = drone.control.get_telemetry(frame_id="aruco_map")
                if t.x == t.x:
                    print(f"  [ARUCO] map OK  pos=({{t.x:.1f}},{{t.y:.1f}})  z={{t.z:.2f}}m")
                else:
                    print(f"  [ARUCO] map LOST")
            except Exception:
                print(f"  [ARUCO] error")
            last_aruco_log = time.time()
        frame = drone.image.take_picture(timeout=1.0)
        if frame is not None:
            frames_ok += 1
            if run_yolo_on_frame(frame):
                target_found = True
                found_point = current_point
                cv2.imwrite("/tmp/cheburashka_found.jpg", frame)
                print(f"[DETECT_PHOTO]/tmp/cheburashka_found.jpg")
                print(f"[DETECT] синий LED {{LED_DURATION:.0f}} сек...")
                led_error = None
                try:
                    import rclpy as _rclpy_led
                    from led_interfaces.srv import SetLEDEffect
                    client = drone.node.create_client(SetLEDEffect, '/led_control/set_effect')
                    if client.wait_for_service(timeout_sec=1.0):
                        req = SetLEDEffect.Request()
                        req.effect = "fill"; req.r = 0; req.g = 0; req.b = 255
                        future = client.call_async(req)
                        _rclpy_led.spin_until_future_complete(drone.node, future, timeout_sec=2.0)
                        time.sleep(LED_DURATION)
                        req.r = 0; req.g = 0; req.b = 0
                        future = client.call_async(req)
                        _rclpy_led.spin_until_future_complete(drone.node, future, timeout_sec=2.0)
                except Exception as e:
                    led_error = str(e)
                if led_error:
                    print(f"[DETECT] LED error: {{led_error}}")
                elapsed = time.time() - t0
                print(f"\\n[DETECT] *** ОБЪЕКТ НАЙДЕН ***")
                print(f"[DETECT] точка: ({{wx:.3f}}, {{wy:.3f}})")
                print(f"[DETECT] время: {{elapsed:.1f}} сек, кадров: {{frames_ok}}")

                print(f"\\n[VLM] запуск анализа...")
                vlm_result_cache = vlm_analyze(frame)
                if vlm_result_cache:
                    vlm_json_str = json.dumps(vlm_result_cache, ensure_ascii=False)
                    try:
                        with open("/tmp/vlm_result.json", "w") as vf:
                            json.dump(vlm_result_cache, vf, ensure_ascii=False, indent=2)
                        print(f"[VLM_JSON_FILE]/tmp/vlm_result.json")
                    except Exception:
                        pass
                    print(f"[VLM_JSON]{{vlm_json_str}}")
                    print(f"[VLM] cheburashka={{vlm_result_cache.get('cheburashka')}} "
                          f"conf={{vlm_result_cache.get('confidence')}} "
                          f"dir={{vlm_result_cache.get('direction')}}")
                    print(f"[VLM] summary: {{vlm_result_cache.get('summary')}}")
                else:
                    print("[VLM_JSON]{{}}")
                    print(f"[VLM] ошибка: ответ не получен")

                print(f"[FOUND_POINT]({{wx:.3f}}, {{wy:.3f}})")
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


# ═══════════════════════════════════════════════════════════════════════════
# ARUCO ПОСАДКА НА РОВЕР
# ═══════════════════════════════════════════════════════════════════════════

def aruco_callback(msg):
    global last_marker_pose, last_detection_time, marker_found_once
    for marker in msg.markers:
        if marker.id == ROVER_ARUCO_ID:
            if not marker_found_once:
                print(f"[ARUCO_DET] 🎯 Целевая метка ROVER_ARUCO_ID={ROVER_ARUCO_ID} ЗАФИКСИРОВАНА!")
            last_marker_pose = (marker.center_x, marker.center_y)
            last_detection_time = time.time()
            marker_found_once = True
            break


def aruco_land_on_rover():
    global last_marker_pose, last_detection_time, marker_found_once

    if not HAS_ARUCO_MSG:
        print("[ARUCO] модуль aruco_det_loc.msg не найден, аварийная посадка")
        safe_land()
        return False

    print("[ARUCO] подписка на /aruco/det/markers (BEST_EFFORT QoS) ...")
    try:
        drone.topic.subscribe(MarkerArray, '/aruco/det/markers', aruco_callback, qos_profile=qos_profile_sensor_data)
    except Exception:
        drone.node.create_subscription(MarkerArray, '/aruco/det/markers', aruco_callback, qos_profile_sensor_data)
    time.sleep(1.0)

    print("[ARUCO] определение разрешения камеры...")
    frame_w = 640
    frame_h = 480
    try:
        cam_img = drone.camera.read_numpy()
        frame_h, frame_w = cam_img.shape[:2]
    except Exception:
        try:
            cam_img = drone.image.take_picture(timeout=2.0)
            if cam_img is not None:
                frame_h, frame_w = cam_img.shape[:2]
        except Exception:
            pass
    print(f"[ARUCO] разрешение кадра: {{frame_w}}x{{frame_h}}")

    print(f"[ARUCO] поиск метки ID {{ROVER_ARUCO_ID}}...")
    current_z = SEARCH_ALTITUDE
    start_search_time = time.time()

    try:
        import rclpy
    except ImportError:
        rclpy = None

    while rclpy and rclpy.ok():
        time_since_last_det = time.time() - last_detection_time

        if time_since_last_det > LOST_MARKER_TIMEOUT or last_marker_pose is None:
            if marker_found_once:
                print(f"\\n[ARUCO] метка была найдена, но пропала (> {{LOST_MARKER_TIMEOUT}} сек).")
                print("[ARUCO] считаем, что дрон над меткой — посадка!")
                break
            else:
                if time.time() - start_search_time > ARUCO_SEARCH_TIMEOUT:
                    print(f"[ARUCO] ОШИБКА: метка не обнаружена за {{ARUCO_SEARCH_TIMEOUT}} сек!")
                    safe_land()
                    return False
                print("[ARUCO] ожидание первого обнаружения метки...")
                time.sleep(0.2)
                continue

        cx_px, cy_px = last_marker_pose
        dx_px = cx_px - (frame_w / 2.0)
        dy_px = cy_px - (frame_h / 2.0)

        view_width_m = 2.0 * current_z * tan(radians(FOV_DEG / 2.0))
        m_per_px = view_width_m / frame_w

        shift_x = -dy_px * m_per_px * ARUCO_KP
        shift_y = -dx_px * m_per_px * ARUCO_KP

        print(f"[ARUCO_TRACK] Метка ID={{ROVER_ARUCO_ID}} в кадре (cx={{cx_px:.0f}}, cy={{cy_px:.0f}}) | "
            f"Высота: {{current_z:.2f}}м | Ошибка PX: ({{dx_px:.1f}}, {{dy_px:.1f}}) | "
            f"Коррекция body (м): X={{shift_x:.2f}}, Y={{shift_y:.2f}}")

        if abs(dx_px) < CENTER_TOLERANCE_PX and abs(dy_px) < CENTER_TOLERANCE_PX:
            print(f"[ARUCO] центрирование достигнуто (ошибка < {{CENTER_TOLERANCE_PX}}px). снижение...")
            current_z -= ARUCO_STEP_DOWN

        if current_z >= MIN_LAND_ALTITUDE:
            drone.navigate(x=shift_x, y=shift_y, z=current_z, frame_id='body', wait=True)
        else:
            print(f"[ARUCO] минимальная высота {{MIN_LAND_ALTITUDE}} м достигнута. посадка!")
            break

        time.sleep(0.1)

    if not marker_found_once:
        print("[ARUCO] метка так и не была обнаружена — аварийная посадка")
        safe_land()
        return False

    print("[ARUCO] команда land()...")
    drone.control.land()
    time.sleep(3)
    print("[ARUCO] посадка успешно завершена")
    return True


# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ЦИКЛ МИССИИ
# ═══════════════════════════════════════════════════════════════════════════

def run():
    global drone, yolo_model, should_stop, target_found, found_point, vlm_result_cache

    print("=" * 50)
    print("[INIT] подключение sverk_interfaces...")
    t0 = time.time()
    drone = sverk_interfaces.init(Nodename="mission_drone")
    print(f"[INIT] готово ({{time.time() - t0:.1f}} сек)")

    print("[INIT] загрузка YOLO...")
    t0 = time.time()
    yolo_model = load_model()
    print(f"[INIT] готово ({{time.time() - t0:.1f}} сек)")

    try:
        print(f"[TAKEOFF] взлёт на {{ALTITUDE}} м...")
        t0 = time.time()
        drone.control.navigate(
            x=0.0, y=0.0, z=1.7,
            yaw=0.0, speed=0.7,
            frame_id="body", auto_arm=True,
        )
        print(f"[TAKEOFF] команда отправлена ({{time.time() - t0:.1f}} сек), "
              f"ожидание {{TAKEOFF_SETTLE_TIME:.0f}} сек...")
        time.sleep(TAKEOFF_SETTLE_TIME)
        t = drone.control.get_telemetry(frame_id="body")
        print(f"[TAKEOFF] взлёт выполнен, высота: z={{t.z:.2f}} м")
        time.sleep(POST_TAKEOFF_SLEEP)

        if should_stop:
            safe_land()
            return

        # ── Цикл поиска ──
        cycle = 0
        while not target_found and not should_stop:
            cycle += 1
            print(f"\\n{{'=' * 50}}")
            print(f"[CYCLE {{cycle}}] облёт точек")
            random.seed(int(time.time() * 1000) + cycle)

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
                print(f"[FLY] отправлено ({{time.time() - t0:.1f}} сек), "
                      f"ожидание {{FLY_SETTLE_TIME:.0f}} сек...")
                time.sleep(FLY_SETTLE_TIME)

                if should_stop:
                    break

                search_at_point((tx, ty))

        # ── Результат поиска ──
        if should_stop and not target_found:
            print("\\n[ABORT] прерывание — посадка")
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
            print(f"[RESULT] всего кадров: {{frame_counter}}")
        else:
            print("\\n[RESULT] цель не найдена, аварийная посадка")
            safe_land()
            return

        # ── Полёт к роверу ──
        print(f"\\n[FLY_TO_ROVER] полёт к позиции ровера ({{ROVER_X}}, {{ROVER_Y}})...")
        drone.control.navigate(
            x=ROVER_X, y=ROVER_Y, z=ALTITUDE,
            yaw=0.0, speed=FLY_TO_ROVER_SPEED,
            frame_id="aruco_map", auto_arm=False,
        )
        print(f"[FLY_TO_ROVER] команда отправлена, ожидание {{FLY_SETTLE_TIME:.0f}} сек...")
        time.sleep(FLY_SETTLE_TIME)
        print("[FLY_TO_ROVER] прибытие к роверу")

        # ── ArUco посадка ──
        print("\\n[ARUCO] ===== НАЧАЛО ПОСАДКИ НА ARUCO-МЕТКУ =====")
        landed = aruco_land_on_rover()
        if landed:
            print("[LANDING_OK]")
        else:
            print("[LANDING_FAIL]")

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

    return script


# ═══════════════════════════════════════════════════════════════════════════════
# РАБОТА С SSH И ПАРСИНГ РЕЗУЛЬТАТА
# ═══════════════════════════════════════════════════════════════════════════════

DroneResult = dict  # {"found": bool, "point": tuple|None, "vlm": dict|None}


def _parse_output_line(line: str, result: dict) -> None:
    """Разбирает строку вывода дрона и заполняет result."""
    line = line.strip()
    if line.startswith("[FOUND_POINT]("):
        coords = line[len("[FOUND_POINT]("):].rstrip(")")
        try:
            x_str, y_str = coords.split(",")
            result["point"] = (float(x_str.strip()), float(y_str.strip()))
            result["found"] = True
        except (ValueError, IndexError):
            pass
    elif line.startswith("[VLM_JSON_FILE]"):
        result["vlm_file_remote"] = line[len("[VLM_JSON_FILE]"):].strip()
    elif line.startswith("[VLM_JSON]"):
        json_str = line[len("[VLM_JSON]"):].strip()
        try:
            result["vlm"] = json.loads(json_str) if json_str else None
        except json.JSONDecodeError:
            result["vlm"] = {"raw": json_str}
    elif line.startswith("[DETECT_PHOTO]"):
        result["photo_remote"] = line[len("[DETECT_PHOTO]"):].strip()
    elif line.startswith("[LANDING_OK]"):
        result["landing_ok"] = True
    elif line.startswith("[LANDING_FAIL]"):
        result["landing_ok"] = False


def run_drone_mission(logger=None) -> DroneResult:
    """
    Подключается к дрону, загружает и запускает бортовой скрипт.
    Парсит вывод для получения результатов обнаружения.

    Возвращает словарь:
        {
            "found": bool,
            "point": (float, float) | None,
            "vlm": dict | None,
            "landing_ok": bool,
            "elapsed_sec": float,
            "raw_output": str,
        }
    """
    result: DroneResult = {
        "found": False,
        "point": None,
        "vlm": None,
        "landing_ok": False,
        "elapsed_sec": 0.0,
        "raw_output": "",
        "photo_remote": None,
        "vlm_file_remote": None,
    }

    t_start = datetime.datetime.now()

    script = build_onboard_script()
    log = logger

    if log:
        log.info("координатор",
                 f"подключение к дрону {DRONE_IP}...")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=DRONE_IP,
            username=DRONE_USER,
            password=DRONE_PASSWORD,
            timeout=30,
        )
        if log:
            log.info("координатор", "SSH-соединение с дроном установлено")

        # Загрузка YOLO-модели (если есть локально)
        model_uploaded = False
        if LOCAL_MODEL_PATH and os.path.exists(LOCAL_MODEL_PATH or ""):
            size_mb = os.path.getsize(LOCAL_MODEL_PATH) / (1024 * 1024)
            if log:
                log.info("координатор",
                         f"загрузка модели {size_mb:.1f} МБ → дрон...")
            sftp = ssh.open_sftp()
            sftp.put(LOCAL_MODEL_PATH, "/tmp/yolo_upload.pt")
            sftp.close()
            model_uploaded = True
            if log:
                log.info("координатор", "модель загружена на дрон")
        else:
            if log:
                log.info("координатор",
                         "используется встроенная/авто-загружаемая модель YOLO")

        # Загрузка бортового скрипта
        if log:
            log.info("координатор",
                     f"загрузка скрипта ({len(script)} байт) на дрон...")
        sftp = ssh.open_sftp()
        remote_script = "/tmp/_mission_drone.py"
        with sftp.open(remote_script, "w") as f:
            f.write(script)
        sftp.close()
        if log:
            log.info("координатор", "скрипт загружен")

        # Запуск
        # Установка параметров ArUco (не блокирует запуск при ошибке)
        if log:
            log.info("координатор", "установка параметров ArUco на дроне...")
        ssh.exec_command(
            "bash -c 'source ~/sverk_ws/install/setup.bash && "
            "ros2 param set /aruco_detect pnp_non_map_markers true; "
            "ros2 param set /aruco_detect estimate_marker_pose true'",
            get_pty=True,
        )
        time.sleep(1.0)

        # Запуск бортового скрипта
        if log:
            log.info("координатор", "ЗАПУСК БОРТОВОГО СКРИПТА ДРОНА")
            log.start_phase(1, "ПОИСК ОБЪЕКТА + ПОСАДКА НА РОВЕР")

        stdin, stdout, stderr = ssh.exec_command(
            f"bash -c 'source ~/sverk_ws/install/setup.bash && "
            f"python3 {remote_script}'",
            get_pty=True,
        )

        output_lines = []
        for line in iter(stdout.readline, ""):
            print(line, end="")  # вывод в консоль хоста
            output_lines.append(line)
            _parse_output_line(line, result)

        err = stderr.read().decode()
        if err:
            print(f"\n[STDERR]\n{err.strip()}")

        result["raw_output"] = "".join(output_lines)

        if log:
            log.end_phase(1)

        # Скачивание результатов с дрона
        sftp = ssh.open_sftp()
        for remote_key, local_name in [
            ("photo_remote", "cheburashka_detected.jpg"),
            ("vlm_file_remote", "vlm_result.json"),
        ]:
            remote_path = result.get(remote_key)
            if remote_path:
                local_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", local_name,
                )
                try:
                    sftp.get(remote_path, local_path)
                    result[remote_key.replace("_remote", "_local")] = local_path
                    if log:
                        log.info("координатор",
                                 f"файл скачан: {local_name}")
                except Exception as e:
                    if log:
                        log.info("координатор",
                                 f"не удалось скачать {local_name}: {e}")
                try:
                    sftp.remove(remote_path)
                except Exception:
                    pass

        # Очистка
        try:
            sftp.remove(remote_script)
        except Exception:
            pass
        sftp.close()

        if log:
            point_str = (f"({result['point'][0]:.3f}, {result['point'][1]:.3f})"
                         if result["point"] else "не найдена")
            log.info("координатор",
                     f"результат дрона: найдено={result['found']}, "
                     f"точка={point_str}, "
                     f"посадка={'OK' if result['landing_ok'] else 'FAIL'}")

    except Exception as e:
        if log:
            log.info("координатор", f"ОШИБКА дрона: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()
        result["elapsed_sec"] = (
            datetime.datetime.now() - t_start
        ).total_seconds()
        if log:
            log.info("координатор",
                     f"миссия дрона завершена, время: {result['elapsed_sec']:.0f} сек")

    return result