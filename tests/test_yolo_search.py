#!/usr/bin/env python3
"""
Тест: взлёт дрона, циклический облёт 2 точек с YOLO-поиском в реальном времени.
YOLO работает непрерывно во время полёта.
При нахождении объекта рядом с точкой — вывод координат точки, посадка на финиш.
При Ctrl+C — безопасная посадка.

Использование: python3 test_yolo_search.py <drone_ip> <password>
"""

import paramiko
import sys
import os
import random
import json

DRONE_USER = "sverk"

ALTITUDE = 1.7

FINISH_X = 0.0
FINISH_Y = 0.0

WAYPOINTS = [
    (2.0, 0.0),
    (0.0, 2.0),
]

RANDOM_OFFSET_RANGE = 0.3
WAYPOINT_PROXIMITY_THRESHOLD = 0.5

YOLO_MODEL_NAME = "yolo11n.pt"
YOLO_CLASS_NAME = "bear"
YOLO_CONFIDENCE = 0.5

ONBOARD_SCRIPT = f'''
import time
import sys
import os
import signal
import random
import json
import math

import sverk_interfaces
import cv2
from ultralytics import YOLO

ALTITUDE = {ALTITUDE}
FINISH_X = {FINISH_X}
FINISH_Y = {FINISH_Y}
WAYPOINTS = {json.dumps(WAYPOINTS)}
RANDOM_OFFSET_RANGE = {RANDOM_OFFSET_RANGE}
WAYPOINT_PROXIMITY_THRESHOLD = {WAYPOINT_PROXIMITY_THRESHOLD}
YOLO_MODEL_NAME = "{YOLO_MODEL_NAME}"
YOLO_CLASS_NAME = "{YOLO_CLASS_NAME}"
YOLO_CONFIDENCE = {YOLO_CONFIDENCE}

drone = None
yolo_model = None
should_stop = False
target_found = False
found_waypoint_coords = None


def _signal_handler(sig, frame):
    global should_stop
    should_stop = True
    print("SIGNAL: получен сигнал прерывания, готовлюсь к посадке")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def safe_land():
    try:
        print("LANDING: начинаю посадку...")
        drone.control.land()
        time.sleep(3)
        print("LANDING: посадка выполнена")
    except Exception as e:
        print(f"LANDING ERROR: {{e}}")


def get_aruco_position():
    try:
        t = drone.control.get_telemetry(frame_id="aruco_map")
        if t.x is not None and t.y is not None:
            return t.x, t.y, t.z
    except Exception as e:
        print(f"TELEMETRY ERROR: {{e}}")
    return None, None, None


def distance_to_waypoint(x, y, wx, wy):
    return math.sqrt((x - wx) ** 2 + (y - wy) ** 2)


def check_proximity(x, y):
    min_dist = float('inf')
    nearest_coords = None
    for idx, (wx, wy) in enumerate(WAYPOINTS):
        dist = distance_to_waypoint(x, y, wx, wy)
        print(f"    расстояние до точки {{idx + 1}} ({{wx:.2f}}, {{wy:.2f}}): {{dist:.2f}} м")
        if dist < min_dist:
            min_dist = dist
            nearest_coords = (wx, wy)
    if min_dist < WAYPOINT_PROXIMITY_THRESHOLD:
        return min_dist, nearest_coords
    return None


frame_counter = 0


def detect_and_check():
    """Один цикл: кадр → YOLO → проверка близости → публикация.
    Возвращает True если найдена валидная цель."""
    global target_found, found_waypoint_coords, frame_counter

    frame = drone.image.take_picture(timeout=1.0)
    if frame is None:
        return False

    frame_counter += 1
    annotated = frame.copy()
    results = yolo_model(frame, verbose=False)

    bears_found = False
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = yolo_model.names[cls_id]
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            if cls_name == YOLO_CLASS_NAME and conf >= YOLO_CONFIDENCE:
                bears_found = True
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{{cls_name}} {{conf:.2f}}"
                cv2.putText(annotated, label, (x1, y1 - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            else:
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 1)

    if bears_found:
        print(f"\\n[DETECT] ОБЪЕКТ НАЙДЕН! (кадр #{{frame_counter}})")
        x, y, z = get_aruco_position()
        if x is not None:
            print(f"  позиция дрона: ({{x:.2f}}, {{y:.2f}})")
            proximity = check_proximity(x, y)
            if proximity is not None:
                wp_dist, wp_coords = proximity
                target_found = True
                found_waypoint_coords = wp_coords
                print(f"  >>> ВАЛИДНАЯ НАХОДКА: {{wp_dist:.2f}} м < {{WAYPOINT_PROXIMITY_THRESHOLD}} м")
                print(f"  >>> Объект на точке с координатами ({{wp_coords[0]:.2f}}, {{wp_coords[1]:.2f}})")
                cv2.putText(annotated, "FOUND at WP!",
                            (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                print(f"  >>> ИГНОРИРУЕМ: далеко от точек (>{{WAYPOINT_PROXIMITY_THRESHOLD}} м)")
                cv2.putText(annotated, "IGNORED (far from WP)",
                            (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            print("  позиция не получена")

    try:
        drone.image.publish(annotated)
    except Exception:
        pass

    return target_found


def run():
    global drone, yolo_model, should_stop

    print("INIT: подключение sverk_interfaces...")
    drone = sverk_interfaces.init(Nodename="yolo_search_test")

    print(f"INIT: загрузка YOLO-модели ({{YOLO_MODEL_NAME}})...")
    yolo_model = YOLO(YOLO_MODEL_NAME)
    print("INIT: модель загружена")

    try:
        print(f"TAKEOFF: взлёт на {{ALTITUDE}} м...")
        drone.control.navigate(
            x=0.0, y=0.0, z=ALTITUDE,
            yaw=0.0, speed=0.5,
            frame_id="body",
            auto_arm=True,
        )
        time.sleep(3)
        print("TAKEOFF: взлёт выполнен")

        if should_stop:
            safe_land()
            return

        cycle = 0
        while not target_found and not should_stop:
            cycle += 1
            print(f"\\nCYCLE {{cycle}}: облёт точек")
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

                print(f"  -> точка {{idx + 1}}/{{len(WAYPOINTS)}}: "
                      f"базовая ({{wx:.2f}}, {{wy:.2f}}) + смещение ({{offset_x:+.2f}}, {{offset_y:+.2f}}) "
                      f"= ({{tx:.2f}}, {{ty:.2f}})")

                drone.control.navigate(
                    x=tx, y=ty, z=ALTITUDE,
                    yaw=0.0, speed=0.5,
                    frame_id="map",
                    auto_arm=False,
                )

                t0 = time.time()
                while time.time() - t0 < 3.0 and not target_found and not should_stop:
                    if detect_and_check():
                        break
                    time.sleep(0.15)

            if should_stop and not target_found:
                print("\\nINTERRUPTED: прерывание, объект не найден")
                print(f"FINISH: посадка в точку финиша ({{FINISH_X}}, {{FINISH_Y}})...")
                drone.control.navigate(
                    x=FINISH_X, y=FINISH_Y, z=ALTITUDE,
                    yaw=0.0, speed=0.5,
                    frame_id="map",
                    auto_arm=False,
                )
                time.sleep(3)
                safe_land()
                return

        if target_found:
            wp_coords = found_waypoint_coords
            print(f"\\n*** ВАЛИДНАЯ НАХОДКА ПОДТВЕРЖДЕНА ***")
            print(f"Объект на точке с координатами ({{wp_coords[0]:.2f}}, {{wp_coords[1]:.2f}})")
            print(f"\\nFINISH: посадка в точку финиша ({{FINISH_X}}, {{FINISH_Y}})...")
            drone.control.navigate(
                x=FINISH_X, y=FINISH_Y, z=ALTITUDE,
                yaw=0.0, speed=0.5,
                frame_id="map",
                auto_arm=False,
            )
            time.sleep(3)
            safe_land()

    except Exception as e:
        print(f"FATAL ERROR: {{e}}")
        import traceback
        traceback.print_exc()
        safe_land()
    finally:
        print("CLEANUP: завершение работы")
        try:
            yolo_model = None
            drone.close()
        except Exception:
            pass


if __name__ == "__main__":
    run()
'''


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) < 3:
        print("Использование: python3 test_yolo_search.py <drone_ip> <password>")
        sys.exit(1)

    drone_ip = sys.argv[1]
    password = sys.argv[2]

    print(f"[{drone_ip}] Подключение к дрону...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(hostname=drone_ip, username=DRONE_USER,
                    password=password, timeout=30)
        print(f"[{drone_ip}] Подключено. Загрузка полётной программы...")

        sftp = ssh.open_sftp()
        remote_script = "/tmp/_yolo_search_test.py"
        with sftp.open(remote_script, "w") as f:
            f.write(ONBOARD_SCRIPT)
        sftp.close()

        print(f"[{drone_ip}] Запуск полётной программы...")
        stdin, stdout, stderr = ssh.exec_command(f"source ~/sverk_ws/install/setup.bash && python3 {remote_script}")
        out = stdout.read().decode()
        err = stderr.read().decode()
        print(out.strip())
        if err:
            print(f"STDERR:\n{err.strip()}", file=sys.stderr)

        sftp = ssh.open_sftp()
        try:
            sftp.remove(remote_script)
        except Exception:
            pass
        sftp.close()

    finally:
        ssh.close()

    print(f"[{drone_ip}] Завершено.")


if __name__ == "__main__":
    main()