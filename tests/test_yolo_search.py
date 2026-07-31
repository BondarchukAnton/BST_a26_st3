#!/usr/bin/env python3
"""
Тест: взлёт дрона, циклический облёт 3 точек с YOLO-поиском объекта класса 'bear'.
При нахождении — зависание, вывод координат на ArUco-карте, посадка на финиш.
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
    (3.0, 3.0),
]

RANDOM_OFFSET_RANGE = 0.3

YOLO_MODEL_PATH = "/home/pi/yolo_models/bear.pt"
YOLO_CLASS_NAME = "bear"
YOLO_CONFIDENCE = 0.5

ONBOARD_SCRIPT = f'''
import time
import sys
import os
import signal
import random
import json

import sverk_interfaces
from ultralytics import YOLO

ALTITUDE = {ALTITUDE}
FINISH_X = {FINISH_X}
FINISH_Y = {FINISH_Y}
WAYPOINTS = {json.dumps(WAYPOINTS)}
RANDOM_OFFSET_RANGE = {RANDOM_OFFSET_RANGE}
YOLO_MODEL_PATH = "{YOLO_MODEL_PATH}"
YOLO_CLASS_NAME = "{YOLO_CLASS_NAME}"
YOLO_CONFIDENCE = {YOLO_CONFIDENCE}

drone = None
yolo_model = None
should_stop = False
target_found = False


def _signal_handler(sig, frame):
    global should_stop
    should_stop = True
    print("SIGNAL: получен сигнал прерывания, готовлюсь к посадке")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def safe_land():
    """Безопасная посадка с обработкой ошибок."""
    try:
        print("LANDING: начинаю посадку...")
        drone.control.land()
        time.sleep(3)
        print("LANDING: посадка выполнена")
    except Exception as e:
        print(f"LANDING ERROR: {{e}}")


def get_aruco_position():
    """Возвращает текущие координаты дрона в системе ArUco-карты."""
    try:
        t = drone.control.get_telemetry(frame_id="aruco_map")
        if t.x is not None and t.y is not None:
            return t.x, t.y, t.z
    except Exception as e:
        print(f"TELEMETRY ERROR: {{e}}")
    return None, None, None


def detect_bear(frame):
    """Запускает YOLO на кадре, возвращает (найден_ли_медведь, список_боксов)."""
    results = yolo_model(frame, verbose=False)
    bears = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = yolo_model.names[cls_id]
            conf = float(box.conf[0])
            if cls_name == YOLO_CLASS_NAME and conf >= YOLO_CONFIDENCE:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                bears.append({{
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "confidence": conf,
                }})
    return len(bears) > 0, bears


def center_over_object():
    """Центрирует дрон над обнаруженным объектом (если объект не в центре кадра)."""
    pass


def run():
    global drone, yolo_model, should_stop, target_found

    print("INIT: подключение sverk_interfaces...")
    drone = sverk_interfaces.init(Nodename="yolo_search_test")

    print(f"INIT: загрузка YOLO-модели из {{YOLO_MODEL_PATH}}...")
    yolo_model = YOLO(YOLO_MODEL_PATH)
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
                time.sleep(3)

                if should_stop:
                    break

                print("  -> съёмка кадра и YOLO-поиск...")
                frame = drone.image.take_picture(timeout=5.0)
                if frame is None:
                    print("  -> КАДР НЕ ПОЛУЧЕН, пропуск точки")
                    continue

                found, bears = detect_bear(frame)
                print(f"  -> медведей найдено: {{len(bears)}}")

                if found:
                    target_found = True
                    print(f"\\n*** ОБЪЕКТ НАЙДЕН! ***")
                    for b in bears:
                        print(f"    confidence: {{b['confidence']:.3f}}, "
                              f"bbox: ({{b['x1']:.0f}}, {{b['y1']:.0f}}, {{b['x2']:.0f}}, {{b['y2']:.0f}})")

                    center_over_object()
                    time.sleep(2)

                    x, y, z = get_aruco_position()
                    if x is not None:
                        print(f"\\nКООРДИНАТЫ ОБЪЕКТА (ArUco map):")
                        print(f"  x = {{x:.2f}}")
                        print(f"  y = {{y:.2f}}")
                        print(f"  z = {{z:.2f}}")
                    else:
                        print("\\nНЕ УДАЛОСЬ ПОЛУЧИТЬ КООРДИНАТЫ ArUco")

                    print(f"\\nFINISH: посадка в точку финиша ({{FINISH_X}}, {{FINISH_Y}})...")
                    drone.control.navigate(
                        x=FINISH_X, y=FINISH_Y, z=ALTITUDE,
                        yaw=0.0, speed=0.5,
                        frame_id="map",
                        auto_arm=False,
                    )
                    time.sleep(3)
                    safe_land()
                    return

            if should_stop and not target_found:
                print("\\nINTERRUPTED: прерывание, объект не найден")
                safe_land()
                return

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
        stdin, stdout, stderr = ssh.exec_command(f"python3 {remote_script}")
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