#!/usr/bin/env python3
"""
Тест: взлёт дрона и следование за ArUco-маркером с заданным ID.
Дрон непрерывно сканирует камеру, ищет маркер и корректирует позицию,
чтобы всегда находиться точно над ним.

Использование: python3 test_aruco_track.py <drone_ip> <password>
"""

import paramiko
import sys
import os
import json

# ═══════════════════════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════════════════════

DRONE_USER = "sverk"

ALTITUDE = 1.2          # рабочая высота (м)

TARGET_ARUCO_ID = 10    # ID маркера, за которым следим

TRACK_SPEED = 0.3       # скорость корректирующих движений (м/с)

# Kp — пропорциональный коэффициент перевода пиксельного смещения в метры.
# Чем больше Kp, тем агрессивнее дрон реагирует на смещение маркера.
# Маленькое значение = плавное, медленное следование.
# Большое значение = резкое, но может перелететь.
# Подбирается экспериментально. Начни с 0.003 и увеличивай при необходимости.
Kp_XY = 0.003

# Порог «центрирования» в пикселях: если маркер смещён меньше этого —
# дрон не двигается (считаем что мы над ним).
CENTER_DEADZONE_PX = 30

# ═══════════════════════════════════════════════════════════════════════════════
# БОРТОВОЙ СКРИПТ (исполняется на дроне)
# ═══════════════════════════════════════════════════════════════════════════════

ONBOARD_SCRIPT = f'''
import time
import sys
import signal
import cv2
import numpy as np
import sverk_interfaces

ALTITUDE = {ALTITUDE}
TARGET_ARUCO_ID = {TARGET_ARUCO_ID}
TRACK_SPEED = {TRACK_SPEED}
Kp_XY = {Kp_XY}
CENTER_DEADZONE_PX = {CENTER_DEADZONE_PX}

drone = None
should_stop = False


def _signal_handler(sig, frame):
    global should_stop
    should_stop = True
    print("\\nSIGNAL: прерывание, готовлюсь к посадке")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def safe_land():
    try:
        print("LANDING: посадка...")
        drone.control.land()
        time.sleep(3)
        print("LANDING: посадка выполнена")
    except Exception as e:
        print(f"LANDING ERROR: {{e}}")


def detect_aruco(frame):
    """Ищет ArUco-маркер TARGET_ARUCO_ID на кадре.
    Возвращает (center_x, center_y) в пикселях или None если не найден."""
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    corners, ids, _ = cv2.aruco.detectMarkers(frame, aruco_dict, parameters=parameters)

    if ids is None:
        return None

    for i, marker_id in enumerate(ids.flatten()):
        if int(marker_id) == TARGET_ARUCO_ID:
            cx = int(np.mean(corners[i][0][:, 0]))
            cy = int(np.mean(corners[i][0][:, 1]))
            return cx, cy
    return None


def draw_debug(frame, marker_center, dx, dy, state):
    """Рисует отладочную информацию на кадре."""
    h, w = frame.shape[:2]
    cv2.line(frame, (w // 2, 0), (w // 2, h), (255, 255, 255), 1)
    cv2.line(frame, (0, h // 2), (w, h // 2), (255, 255, 255), 1)

    if marker_center is not None:
        mx, my = marker_center
        cv2.circle(frame, (mx, my), 8, (0, 255, 0), -1)
        cv2.line(frame, (w // 2, h // 2), (mx, my), (0, 255, 255), 1)
        cv2.putText(frame, f"dx={{dx:+d}} dy={{dy:+d}}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    cv2.putText(frame, state, (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    try:
        drone.image.publish(frame)
    except Exception:
        pass


def run():
    global drone, should_stop

    print("INIT: подключение sverk_interfaces...")
    drone = sverk_interfaces.init(Nodename="aruco_track_test")

    try:
        print(f"TAKEOFF: взлёт на {{ALTITUDE}} м...")
        drone.control.navigate(
            x=0.0, y=0.0, z=ALTITUDE,
            yaw=0.0, speed=0.5,
            frame_id="body",
            auto_arm=True,
        )
        time.sleep(3)
        print("TAKEOFF: взлёт выполнен, начинаю слежение\\n")

        lost_count = 0
        while not should_stop:
            frame = drone.image.take_picture(timeout=2.0)
            if frame is None:
                print("  -> кадр не получен")
                time.sleep(0.1)
                continue

            center = detect_aruco(frame)

            if center is None:
                lost_count += 1
                state = f"SEARCHING (lost {{lost_count}})"
                draw_debug(frame, None, 0, 0, state)
                if lost_count % 10 == 0:
                    print(f"  -> маркер не найден ({{lost_count}} кадров)")
                time.sleep(0.1)
                continue

            lost_count = 0
            mx, my = center
            h, w = frame.shape[:2]
            dx = mx - w // 2
            dy = my - h // 2

            if abs(dx) < CENTER_DEADZONE_PX and abs(dy) < CENTER_DEADZONE_PX:
                state = f"ON TARGET dx={{dx:+d}} dy={{dy:+d}}"
                draw_debug(frame, (mx, my), dx, dy, state)
                time.sleep(0.05)
                continue

            move_x = dx * Kp_XY
            move_y = -dy * Kp_XY

            state = f"TRACKING dx={{dx:+d}} dy={{dy:+d}} | move x={{move_x:+.2f}} y={{move_y:+.2f}}"
            print(state)
            draw_debug(frame, (mx, my), dx, dy, state)

            drone.control.navigate(
                x=move_x, y=move_y, z=0.0,
                yaw=0.0, speed=TRACK_SPEED,
                frame_id="body",
                auto_arm=False,
            )
            time.sleep(0.2)

        print("\\nОстановка слежения, посадка...")
        safe_land()

    except Exception as e:
        print(f"FATAL ERROR: {{e}}")
        import traceback
        traceback.print_exc()
        safe_land()
    finally:
        try:
            drone.close()
        except Exception:
            pass
        print("CLEANUP: завершено")


if __name__ == "__main__":
    run()
'''


# ═══════════════════════════════════════════════════════════════════════════════
# ХОСТ-СКРИПТ (запускается с ноутбука)
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print("Использование: python3 test_aruco_track.py <drone_ip> <password>")
        sys.exit(1)

    drone_ip = sys.argv[1]
    password = sys.argv[2]

    print(f"[{drone_ip}] Подключение к дрону...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(hostname=drone_ip, username=DRONE_USER,
                    password=password, timeout=30)
        print(f"[{drone_ip}] Подключено. Загрузка программы...")

        sftp = ssh.open_sftp()
        remote_script = "/tmp/_aruco_track.py"
        with sftp.open(remote_script, "w") as f:
            f.write(ONBOARD_SCRIPT)
        sftp.close()

        print(f"[{drone_ip}] Запуск программы слежения...")
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