#!/usr/bin/env python3
"""
Тест: взлёт дрона и автоматическое следование за ArUco-маркером через frame_id.
Использование: python3 test_aruco_track.py <drone_ip> <password>
"""

import paramiko
import sys
import os

# ═══════════════════════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════════════════════

DRONE_USER = "sverk"

ALTITUDE = 1.2          # Высота удержания над маркером (м)
TARGET_ARUCO_ID = 10    # ID целевого ArUco-маркера
TRACK_SPEED = 0.3       # Скорость следования (м/с)

# ═══════════════════════════════════════════════════════════════════════════════
# БОРТОВОЙ СКРИПТ (исполняется на дроне)
# ═══════════════════════════════════════════════════════════════════════════════

ONBOARD_SCRIPT = f'''
import time
import sys
import signal
import sverk_interfaces

ALTITUDE = {ALTITUDE}
TARGET_ARUCO_ID = {TARGET_ARUCO_ID}
TRACK_SPEED = {TRACK_SPEED}

drone = None
should_stop = False


def _signal_handler(sig, frame):
    global should_stop
    should_stop = True
    print("\\nSIGNAL: получен сигнал прерывания, выполняю посадку...")


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


def run():
    global drone, should_stop

    print("INIT: подключение sverk_interfaces...")
    drone = sverk_interfaces.init(Nodename="aruco_track_test")

    # Имя TF-фрейма целевого маркера
    marker_frame = f"aruco_{{TARGET_ARUCO_ID}}"

    try:
        # 1. Взлёт на базовую высоту относительно корпуса дрона
        print(f"TAKEOFF: взлёт на {{ALTITUDE}} м...")
        drone.control.navigate(
            x=0.0, y=0.0, z=ALTITUDE,
            yaw=0.0, speed=0.5,
            frame_id="body",
            auto_arm=True,
        )
        time.sleep(3)
        print(f"TAKEOFF: взлёт выполнен. Переход в режим слежения за {{marker_frame}}...\\n")

        # 2. Перевод навигации в фрейм маркерa
        # x=0, y=0 означает удерживать центр точно над меткой
        drone.control.navigate(
            x=0.0, y=0.0, z=ALTITUDE,
            yaw=0.0, speed=TRACK_SPEED,
            frame_id=marker_frame,
            auto_arm=False,
        )

        while not should_stop:
            # Получаем телеметрию относительно маркера для контроля видимости
            telemetry = drone.control.get_telemetry(frame_id=marker_frame)

            if telemetry is not None and telemetry.x is not None:
                print(f"TRACKING: маркер {{TARGET_ARUCO_ID}} виден | "
                      f"Смещение: dx={{telemetry.x:+.2f}}m, dy={{telemetry.y:+.2f}}m, dz={{telemetry.z:+.2f}}m")
            else:
                print(f"WARN: маркер {{TARGET_ARUCO_ID}} не виден в камере (поиск...)")

            # Периодически подтверждаем целевую точку для контроллера
            drone.control.navigate(
                x=0.0, y=0.0, z=ALTITUDE,
                yaw=0.0, speed=TRACK_SPEED,
                frame_id=marker_frame,
                auto_arm=False,
            )

            time.sleep(0.5)

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