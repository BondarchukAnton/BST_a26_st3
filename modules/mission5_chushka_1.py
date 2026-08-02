"""Миссия: доехать до чепух, крутиться и фоткать, искать координату через VLM.
   python3 mission5_chushka_1.py <x> <y>   — координаты чепух."""

import json
import os
import sys
import time
from urllib.request import Request, urlopen

import paramiko

from gemma_vlm import analyze_image as gemma_analyze

ROBOT_IP = "192.168.1.185"
USERNAME = "pi"
PASSWORD = "raspberry"
V1_URL = "http://192.168.1.185:8767"
WEB_URL = "http://192.168.1.185:8765"
CLIENT = "/home/pi/sverk_rover/tools/rover_control_client.py"
CD = "/home/pi/sverk_rover"
GEMMA_IMAGE = r"D:\arhipelag\gemochka\gemm.jpg"

GEMMA_PROMPT = (
    "Проанализируй изображение. Найди белый лист бумаги с надписью. "
    "На листе должна быть указана координата финишной клетки полигона "
    "(буква от A до F и цифра от 1 до 6, например A6, B6, F3). "
    "Если координата видна на белом листе, верни СТРОГО JSON вида: "
    '{"finish_point": true, "coordinate": "B6"}. '
    "Если белого листа или координаты на нем нет, верни: "
    '{"finish_point": false, "coordinate": null}.'
)

COLS = "ABCDEF"


def ssh_run(ssh: paramiko.SSHClient, commands: list[str]) -> str:
    full = " && ".join(commands)
    print(f"[SSH] {full}")
    stdin, stdout, stderr = ssh.exec_command(full)
    out = stdout.read().decode("utf-8")
    err = stderr.read().decode("utf-8")
    if out:
        print(out.strip())
    if err:
        print(err.strip())
    return out


def initial_cell(col: int, row: int, yaw: int = 0) -> str:
    return f'python3 "{CLIENT}" --url "{V1_URL}" initial-cell {col} {row} --yaw {yaw}'


def goal_cell(col: int, row: int, yaw: int = 0, replace: bool = True) -> str:
    cmd = f'python3 "{CLIENT}" --url "{V1_URL}" goal-cell {col} {row} --yaw {yaw}'
    if replace:
        cmd += " --replace"
    return cmd


def convert_coord(coord: str) -> tuple[int, int]:
    """A6 -> (1, 6), B1 -> (2, 1), F4 -> (6, 4) и т.д."""
    letter = coord[0].upper()
    number = int(coord[1])
    col = COLS.index(letter) + 1
    return col, number


def set_led(enabled: bool, brightness: float, effect: str, color: str, speed: float = 1.0):
    body = json.dumps({
        "enabled": enabled,
        "brightness": brightness,
        "effect": effect,
        "primary_color": color,
        "effect_speed_hz": speed,
    }).encode("utf-8")
    req = Request(
        f"{WEB_URL}/api/led_strip/command",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def flash_led():
    """Зелёный 3 секунды, затем голубой #16B8F3."""
    print("[LED] зелёный 0.35")
    set_led(enabled=True, brightness=0.35, effect="fill", color="#00FF00")
    time.sleep(3.0)
    print("[LED] голубой #16B8F3 0.15")
    set_led(enabled=True, brightness=0.15, effect="fill", color="#16B8F3")


def take_photo(filename: str) -> dict:
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    req = Request(
        f"{WEB_URL}/api/camera/frame?topic=/image_raw&type=sensor_msgs/msg/Image",
        headers={"Accept": "image/jpeg"},
    )
    with urlopen(req, timeout=10) as resp:
        data = resp.read()
        with open(filename, "wb") as f:
            f.write(data)
    print(f"[PHOTO] {filename} ({len(data)} bytes)")
    return {"ok": True, "file": filename, "size_bytes": len(data)}


def spin_and_shoot(ssh: paramiko.SSHClient, col: int, row: int, prefix: str) -> tuple[int, int] | None:
    """Крутиться и искать лист с координатой. Возвращает (col, row) или None."""
    yaws = [0, 315, 270, 225, 180]
    found = None

    for attempt in range(2):  # два полных цикла если не нашли
        print(f"\n=== Цикл фотографирования {attempt + 1}/2 ===")
        for i, yaw in enumerate(yaws):
            print(f"\n>>> Разворот {i+1}/{len(yaws)}: cell=({col},{row}) yaw={yaw}°")
            ssh_run(ssh, [
                f'source "{CD}/install/setup.zsh"',
                goal_cell(col, row, yaw=yaw),
            ])
            time.sleep(2.0)

            take_photo(GEMMA_IMAGE)

            # --- анализ через gemma_vlm ---
            print(f"[VLM] анализирую {GEMMA_IMAGE} ...")
            try:
                result = gemma_analyze(GEMMA_IMAGE, GEMMA_PROMPT)
                print(f"[VLM] ответ: {result}")
                # убрать markdown-обёртку ```json ... ```
                clean = result.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[-1] if "\n" in clean else clean
                    if clean.endswith("```"):
                        clean = clean[:-3].strip()
                data = json.loads(clean)
                if data.get("finish_point") and data.get("coordinate"):
                    gemma_coord = data["coordinate"]
                    r_col, r_row = convert_coord(gemma_coord)
                    print(f"[VLM] НАЙДЕНА координата: {gemma_coord} → ровер ({r_col}, {r_row})")
                    flash_led()
                    found = (r_col, r_row)
                    break
            except Exception as e:
                print(f"[VLM] ошибка анализа: {e}")

        if found:
            break

    return found


def mission(ch_x: int, ch_y: int):
    print(f"Цель: чепуха в клетке ({ch_x}, {ch_y})")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=ROBOT_IP, username=USERNAME, password=PASSWORD, timeout=30)
    print(f"SSH подключено: {USERNAME}@{ROBOT_IP}\n")

    target_coord = None  # координата ровера, найденная VLM

    try:
        print("=== Стартовый маршрут ===")
        ssh_run(ssh, [
            f'source "{CD}/install/setup.zsh"',
            initial_cell(6, 1, yaw=0),
            goal_cell(6, 1, yaw=0),
            goal_cell(6, 2, yaw=0),
        ])

        if ch_x == 5 and ch_y == 2:
            print("\n=== Сценарий А: чепуха (5, 2) ===")
            ssh_run(ssh, [
                f'source "{CD}/install/setup.zsh"',
                goal_cell(6, 2, yaw=270),
                goal_cell(5, 2, yaw=270),
            ])
            target_coord = spin_and_shoot(ssh, 5, 2, "chushka_A")
            ssh_run(ssh, [
                f'source "{CD}/install/setup.zsh"',
                goal_cell(5, 2, yaw=90),
                goal_cell(6, 2, yaw=0),
                goal_cell(6, 4, yaw=0),
                goal_cell(1, 4, yaw=0),
            ])

        elif ch_x == 1 and ch_y == 1:
            print("\n=== Сценарий Б: чепуха (1, 1) ===")
            ssh_run(ssh, [
                f'source "{CD}/install/setup.zsh"',
                goal_cell(6, 4, yaw=0),
                goal_cell(1, 1, yaw=270),
            ])
            target_coord = spin_and_shoot(ssh, 1, 1, "chushka_B")
            ssh_run(ssh, [
                f'source "{CD}/install/setup.zsh"',
                goal_cell(1, 1, yaw=90),
                goal_cell(2, 1, yaw=0),
                goal_cell(1, 4, yaw=0),
            ])

        else:
            print(f"Нет сценария для координат ({ch_x}, {ch_y})")
            print("Доступны: (5, 2) или (1, 1)")

        # ── Едем на найденную координату ──
        if target_coord:
            t_col, t_row = target_coord
            print(f"\n=== Едем на финишную клетку ({t_col}, {t_row}) ===")
            ssh_run(ssh, [
                f'source "{CD}/install/setup.zsh"',
                goal_cell(t_col, t_row, yaw=0),
            ])
        else:
            print("\n=== Координата не найдена, финишная клетка пропущена ===")

    finally:
        ssh.close()
        print("\nSSH закрыто. Готово.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python3 mission5_chushka_1.py <x> <y>")
        sys.exit(1)

    cx = int(sys.argv[1])
    cy = int(sys.argv[2])
    mission(cx, cy)