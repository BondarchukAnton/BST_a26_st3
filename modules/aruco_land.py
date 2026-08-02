#!/usr/bin/env python3
"""
Тест: Автономная посадка на ArUco-метку.
Параметры задаются на хосте, формируются в бортовой скрипт,
передаются по SSH (Paramiko) и выполняются на дроне.

Использование: python3 test_aruco_landing.py <drone_ip> <password>
"""

import paramiko
import sys
import os
import datetime

# ==============================================================================
# НАСТРОЙКИ (НА ХОСТЕ)
# ==============================================================================

DRONE_USER = "sverk"

# Настройки миссии и параметры
TARGET_MARKER_ID = 332          # ID целевой ArUco-метки для посадки
SEARCH_ALTITUDE = 1.8          # Высота первичного поиска метки (в метрах)
MIN_LAND_ALTITUDE = 0.4        # Высота финишного зависания перед посадочным маневром (в метрах)

FOV_DEG = 62.0                 # Горизонтальный угол обзора камеры RPi Cam v2 (в градусах)
KP = 0.6                       # Пропорциональный коэффициент P-регулятора коррекции

# Настраиваемые пороги и таймауты
CENTER_TOLERANCE_PX = 50       # Допустимая погрешность центрирования (в пикселях)
LOST_MARKER_TIMEOUT = 3.0      # Таймаут утери метки (в секундах)
SEARCH_TIMEOUT = 15.0          # Максимальное время первого поиска метки (в секундах)


# ==============================================================================
# БОРТОВОЙ СКРИПТ (ФОРМИРУЕТСЯ ИЗ ПАРАМЕТРОВ ХОСТА)
# ==============================================================================

ONBOARD_SCRIPT = f'''
import time
import math
from math import tan, radians
import rclpy
import sverk_interfaces
from aruco_det_loc.msg import MarkerArray

# ==============================================================================
# НАСТРОЙКИ МИССИИ И ПАРАМЕТРЫ (ПОДСТАВЛЕНЫ С ХОСТА)
# ==============================================================================
TARGET_MARKER_ID = {TARGET_MARKER_ID}
SEARCH_ALTITUDE = {SEARCH_ALTITUDE}
MIN_LAND_ALTITUDE = {MIN_LAND_ALTITUDE}

FOV_DEG = {FOV_DEG}
KP = {KP}

CENTER_TOLERANCE_PX = {CENTER_TOLERANCE_PX}
LOST_MARKER_TIMEOUT = {LOST_MARKER_TIMEOUT}
SEARCH_TIMEOUT = {SEARCH_TIMEOUT}

# ==============================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ СОСТОЯНИЯ
# ==============================================================================
last_marker_pose = None
last_detection_time = 0.0
marker_found_once = False      # Флаг: была ли метка зафиксирована хотя бы 1 раз


def aruco_callback(msg: MarkerArray):
    global last_marker_pose, last_detection_time, marker_found_once
    for marker in msg.markers:
        if marker.id == TARGET_MARKER_ID:
            last_marker_pose = (marker.center_x, marker.center_y)
            last_detection_time = time.time()
            marker_found_once = True
            break


# ==============================================================================
# ОСНОВНОЙ КОД МИССИИ
# ==============================================================================
def run():
    global last_marker_pose, last_detection_time, marker_found_once

    print("1. Инициализация sverk_interfaces...")
    drone = sverk_interfaces.init()
    drone.subscribe('/aruco/det/markers', MarkerArray, aruco_callback)

    try:
        # АВТОМАТИЧЕСКОЕ ВЫЧИСЛЕНИЕ РАЗРЕШЕНИЯ КАДРА
        print("2. Автоматическое определение разрешения камеры...")
        cam_img = drone.camera.read_numpy()
        frame_h, frame_w = cam_img.shape[:2]
        print(f"Зафиксировано разрешение кадра: {{frame_w}}x{{frame_h}} пикселей.")

        print(f"3. Поиск и центрирование над меткой ID {{TARGET_MARKER_ID}}...")
        current_z = SEARCH_ALTITUDE
        start_search_time = time.time()

        while rclpy.ok():
            time_since_last_det = time.time() - last_detection_time

            # --- ОБРАБОТКА ПОТЕРИ МЕТКИ И ТАЙМАУТОВ ---
            if time_since_last_det > LOST_MARKER_TIMEOUT or last_marker_pose is None:
                if marker_found_once:
                    print(f"⚠️ Метка была найдена ранее, но пропала из кадра (> {{LOST_MARKER_TIMEOUT}} сек).")
                    print("Считаем, что дрон находится прямо над меткой. Выполняем посадку!")
                    break
                else:
                    if time.time() - start_search_time > SEARCH_TIMEOUT:
                        raise RuntimeError("❌ Ошибка: Метка так и не была обнаружена за отведённое время!")
                    print("⏳ Ожидание первого обнаружения метки...")
                    time.sleep(0.2)
                    continue

            # --- ВЫЧИСЛЕНИЕ СМЕЩЕНИЯ В ПИКСЕЛЯХ ---
            cx_px, cy_px = last_marker_pose
            dx_px = cx_px - (frame_w / 2.0)
            dy_px = cy_px - (frame_h / 2.0)

            # --- ПЕРЕСЧЕТ ПИКСЕЛЕЙ В МЕТРЫ НА ТЕКУЩЕЙ ВЫСОТЕ ---
            view_width_m = 2.0 * current_z * tan(radians(FOV_DEG / 2.0))
            m_per_px = view_width_m / frame_w

            # Смещение по осям дрона (frame_id='body')
            shift_x = -dy_px * m_per_px * KP
            shift_y = -dx_px * m_per_px * KP

            print(f"Высота: {{current_z:.2f}}м | Ошибка PX: ({{dx_px:.1f}}, {{dy_px:.1f}}) | Коррекция (м): X={{shift_x:.2f}}, Y={{shift_y:.2f}}")

            # --- ПРОВЕРКА ЦЕНТРИРОВАНИЯ ---
            if abs(dx_px) < CENTER_TOLERANCE_PX and abs(dy_px) < CENTER_TOLERANCE_PX:
                print(f"✅ Точность центрирования достигнута (ошибка < {{CENTER_TOLERANCE_PX}}px). Снижение высоты...")
                current_z -= 0.15  # Пошаговое снижение на 15 см

            # Перемещение и контроль высоты
            if current_z >= MIN_LAND_ALTITUDE:
                drone.navigate(x=shift_x, y=shift_y, z=current_z, frame_id='body', wait=True)
            else:
                print(f"🎯 Достигнута минимальная высота перед посадкой ({{MIN_LAND_ALTITUDE}} м). Завершаем центрирование.")
                break

            time.sleep(0.1)

        # --- ФИНИШНАЯ ПОСАДКА ---
        print("4. Отправка команды land()...")
        drone.land()
        print("Посадка успешно завершена.")

    finally:
        drone.close()


if __name__ == "__main__":
    run()
'''


# ==============================================================================
# ХОСТ-СКРИПТ (ОТПРАВКА И ЗАПУСК НА ДРОНЕ)
# ==============================================================================

def main():
    if len(sys.argv) < 3:
        print("Использование: python3 test_aruco_landing.py <drone_ip> <password>")
        sys.exit(1)

    drone_ip = sys.argv[1]
    password = sys.argv[2]
    t_start = datetime.datetime.now()

    print(f"[HOST {t_start.strftime('%H:%M:%S')}] === ТЕСТ ПОСАДКИ НА ARUCO-МЕТКУ ===")
    print(f"[HOST] Дрон IP: {drone_ip} | Target ID: {TARGET_MARKER_ID} | Высота поиска: {SEARCH_ALTITUDE} м")

    print(f"\n[HOST] [1/3] SSH-подключение к {drone_ip}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=drone_ip,
            username=DRONE_USER,
            password=password,
            timeout=30
        )
        print(f"[HOST] [1/3] SSH-соединение установлено: OK")

        print(f"[HOST] [2/3] Загрузка скрипта посадки ({len(ONBOARD_SCRIPT)} байт)...")
        sftp = ssh.open_sftp()
        remote_script = "/tmp/_aruco_landing.py"
        with sftp.open(remote_script, "w") as f:
            f.write(ONBOARD_SCRIPT)
        sftp.close()
        print(f"[HOST] [2/3] Скрипт передан на дрон: OK")

        print(f"[HOST] [3/3] Запуск программы на дроне...")
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

        print(f"[HOST] Очистка временного файла {remote_script} на дроне...")
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
        print(f"[HOST] Завершено, общее время выполнения: {elapsed:.0f} сек")


if __name__ == "__main__":
    main()