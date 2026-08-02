"""
Модуль ровера: движение к коробу, VLM-поиск финишной координаты, движение к финишу.
Адаптирован из modules/mission5_chushka_1.py.

Использование:
    result = run_rover_mission(target_x, target_y, logger)
"""

import json
import os
import sys
import time
import paramiko
from urllib.request import Request, urlopen

from config.settings import (
    ROVER_IP, ROVER_USER, ROVER_PASSWORD,
    ROVER_CONTROL_PORT, ROVER_WEB_PORT,
    ROVER_CLIENT_PATH, ROVER_CD_PATH,
)


def _rover_api_url() -> str:
    return f"http://{ROVER_IP}:{ROVER_CONTROL_PORT}"


def _rover_web_url() -> str:
    return f"http://{ROVER_IP}:{ROVER_WEB_PORT}"


COLS = "ABCDEF"
GEMMA_IMAGE = "gemm_rover_photo.jpg"

GEMMA_PROMPT = (
    "Проанализируй изображение. Найди белый лист бумаги с надписью. "
    "На листе должна быть указана координата финишной клетки полигона "
    "(буква от A до F и цифра от 1 до 6, например A6, B6, F3). "
    "Если координата видна на белом листе, верни СТРОГО JSON вида: "
    '{"finish_point": true, "coordinate": "B6"}. '
    "Если белого листа или координаты на нем нет, верни: "
    '{"finish_point": false, "coordinate": null}.'
)


def _take_photo(filename: str, log=None) -> dict:
    """Снимает фото с камеры ровера через HTTP API."""
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    req = Request(
        f"{_rover_web_url()}/api/camera/frame?topic=/image_raw&type=sensor_msgs/msg/Image",
        headers={"Accept": "image/jpeg"},
    )
    with urlopen(req, timeout=10) as resp:
        data = resp.read()
        with open(filename, "wb") as f:
            f.write(data)
    if log:
        log.info("ровер", f"фото сохранено: {filename} ({len(data)} байт)")
    else:
        print(f"[PHOTO] {filename} ({len(data)} bytes)")
    return {"ok": True, "file": filename, "size_bytes": len(data)}


def _set_led(enabled: bool, brightness: float, effect: str, color: str,
             speed: float = 1.0):
    """Управление LED-лентой ровера."""
    body = json.dumps({
        "enabled": enabled,
        "brightness": brightness,
        "effect": effect,
        "primary_color": color,
        "effect_speed_hz": speed,
    }).encode("utf-8")
    req = Request(
        f"{_rover_web_url()}/api/led_strip/command",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _flash_green_led(log=None):
    """Зелёная LED-индикация 3 сек (распознавание финишной клетки)."""
    if log:
        log.info("ровер", "LED зелёный (распознавание финиша)")
    print("[LED] зелёный 0.35")
    _set_led(enabled=True, brightness=0.35, effect="fill", color="#00FF00")
    time.sleep(3.0)
    print("[LED] голубой #16B8F3 0.15")
    _set_led(enabled=True, brightness=0.15, effect="fill", color="#16B8F3")


def _convert_coord(coord: str) -> tuple[int, int]:
    """Преобразует координату A6 -> (1, 6), B1 -> (2, 1), F4 -> (6, 4)."""
    letter = coord[0].upper()
    number = int(coord[1])
    col = COLS.index(letter) + 1
    return col, number


def _ssh_run(ssh: paramiko.SSHClient, commands: list[str],
             log=None) -> str:
    """Выполняет цепочку команд на ровере через SSH."""
    full = " && ".join(commands)
    if log:
        log.info("ровер", f"SSH: {full[:120]}{'...' if len(full) > 120 else ''}")
    else:
        print(f"[SSH] {full[:200]}")
    stdin, stdout, stderr = ssh.exec_command(full)
    out = stdout.read().decode("utf-8")
    err = stderr.read().decode("utf-8")
    if out and not log:
        print(out.strip())
    if err:
        print(err.strip())
    return out


def _initial_cell(col: int, row: int, yaw: int = 0) -> str:
    return (f'python3 "{ROVER_CLIENT_PATH}" '
            f'--url "{_rover_api_url()}" '
            f'initial-cell {col} {row} --yaw {yaw}')


def _goal_cell(col: int, row: int, yaw: int = 0,
               replace: bool = True) -> str:
    cmd = (f'python3 "{ROVER_CLIENT_PATH}" '
           f'--url "{_rover_api_url()}" '
           f'goal-cell {col} {row} --yaw {yaw}')
    if replace:
        cmd += " --replace"
    return cmd


def _spin_and_shoot(ssh: paramiko.SSHClient, col: int, row: int,
                    log=None) -> tuple[int, int] | None:
    """
    Крутится в клетке и фоткает, ищет лист с координатой через VLM.
    Возвращает (col, row) или None.
    """
    from src.gemma_vlm import analyze_image, try_parse_json_vlm_response

    yaws = [0, 315, 270, 225, 180]

    for attempt in range(2):
        if log:
            log.info("ровер", f"цикл фотографирования {attempt + 1}/2")
        else:
            print(f"\n=== Цикл фотографирования {attempt + 1}/2 ===")

        for i, yaw in enumerate(yaws):
            if log:
                log.info("ровер",
                         f"разворот {i+1}/{len(yaws)}: "
                         f"клетка=({col},{row}) yaw={yaw}°")
            else:
                print(f"\n>>> Разворот {i+1}/{len(yaws)}: "
                      f"cell=({col},{row}) yaw={yaw}°")

            _ssh_run(ssh, [
                f'source "{ROVER_CD_PATH}/install/setup.zsh"',
                _goal_cell(col, row, yaw=yaw),
            ], log=log)
            time.sleep(2.0)

            _take_photo(GEMMA_IMAGE, log=log)

            if log:
                log.info("ровер", f"VLM-анализ {GEMMA_IMAGE}...")
            else:
                print(f"[VLM] анализирую {GEMMA_IMAGE} ...")

            try:
                result = analyze_image(GEMMA_IMAGE, GEMMA_PROMPT)
                if log:
                    log.info("ровер", f"VLM ответ: {result}")
                else:
                    print(f"[VLM] ответ: {result}")

                data = try_parse_json_vlm_response(result)
                if data is None:
                    if log:
                        log.info("ровер", "VLM: не удалось разобрать JSON")
                    continue

                if data.get("finish_point") and data.get("coordinate"):
                    gemma_coord = data["coordinate"]
                    r_col, r_row = _convert_coord(gemma_coord)
                    if log:
                        log.rover_vlm_found(
                            gemma_coord,
                            f"({r_col}, {r_row})",
                        )
                    else:
                        print(f"[VLM] НАЙДЕНА координата: {gemma_coord} "
                              f"→ ровер ({r_col}, {r_row})")
                    _flash_green_led(log=log)
                    return (r_col, r_row)

            except Exception as e:
                if log:
                    log.info("ровер", f"VLM ошибка: {e}")
                else:
                    print(f"[VLM] ошибка анализа: {e}")

    return None


def run_rover_mission(target_x: int, target_y: int, log=None) -> dict:
    """
    Запускает миссию ровера.

    Параметры:
        target_x, target_y: координаты цели (клетка с объектом интереса)
        log: логгер (опционально)

    Возвращает:
        {"finish_found": bool, "finish_cell": (int, int) | None,
         "elapsed_sec": float}
    """
    import datetime
    t_start = datetime.datetime.now()

    if log:
        log.rover_start_mission(target_x, target_y)
    print(f"Цель ровера: чепуха в клетке ({target_x}, {target_y})")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=ROVER_IP,
            username=ROVER_USER,
            password=ROVER_PASSWORD,
            timeout=30,
        )
        if log:
            log.info("ровер", f"SSH подключено: {ROVER_USER}@{ROVER_IP}")
        print(f"SSH подключено: {ROVER_USER}@{ROVER_IP}\n")

        target_coord = None  # финишная клетка от VLM

        # ── Стартовый маршрут ──
        if log:
            log.info("ровер", "стартовый маршрут: initial-cell (6,1)")
        print("=== Стартовый маршрут ===")
        _ssh_run(ssh, [
            f'source "{ROVER_CD_PATH}/install/setup.zsh"',
            _initial_cell(6, 1, yaw=0),
            _goal_cell(6, 1, yaw=0),
            _goal_cell(6, 2, yaw=0),
        ], log=log)

        # ── Сценарий по координатам цели ──
        if target_x == 5 and target_y == 2:
            if log:
                log.info("ровер", "СЦЕНАРИЙ А: чепуха (5, 2)")
            print("\n=== Сценарий А: чепуха (5, 2) ===")
            _ssh_run(ssh, [
                f'source "{ROVER_CD_PATH}/install/setup.zsh"',
                _goal_cell(6, 2, yaw=270),
                _goal_cell(5, 2, yaw=270),
            ], log=log)
            target_coord = _spin_and_shoot(ssh, 5, 2, log=log)
            _ssh_run(ssh, [
                f'source "{ROVER_CD_PATH}/install/setup.zsh"',
                _goal_cell(5, 2, yaw=90),
                _goal_cell(6, 2, yaw=0),
                _goal_cell(6, 4, yaw=0),
                _goal_cell(1, 4, yaw=0),
            ], log=log)

        elif target_x == 1 and target_y == 1:
            if log:
                log.info("ровер", "СЦЕНАРИЙ Б: чепуха (1, 1)")
            print("\n=== Сценарий Б: чепуха (1, 1) ===")
            _ssh_run(ssh, [
                f'source "{ROVER_CD_PATH}/install/setup.zsh"',
                _goal_cell(6, 4, yaw=0),
                _goal_cell(1, 1, yaw=270),
            ], log=log)
            target_coord = _spin_and_shoot(ssh, 1, 1, log=log)
            _ssh_run(ssh, [
                f'source "{ROVER_CD_PATH}/install/setup.zsh"',
                _goal_cell(1, 1, yaw=90),
                _goal_cell(2, 1, yaw=0),
                _goal_cell(1, 4, yaw=0),
            ], log=log)

        else:
            msg = (f"Нет сценария для координат ({target_x}, {target_y}). "
                   f"Доступны: (5, 2) или (1, 1)")
            if log:
                log.info("ровер", msg)
            print(msg)

        # ── Движение к финишной клетке ──
        if target_coord:
            t_col, t_row = target_coord
            if log:
                log.rover_arrived(f"({t_col}, {t_row})")
            print(f"\n=== Едем на финишную клетку ({t_col}, {t_row}) ===")
            _ssh_run(ssh, [
                f'source "{ROVER_CD_PATH}/install/setup.zsh"',
                _goal_cell(t_col, t_row, yaw=0),
            ], log=log)
        else:
            print("\n=== Координата не найдена, финишная клетка пропущена ===")
            if log:
                log.info("ровер",
                         "координата финиша не найдена, миссия завершена без финиша")

    except Exception as e:
        msg = f"ОШИБКА ровера: {type(e).__name__}: {e}"
        if log:
            log.info("ровер", msg)
        print(msg)
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()
        if log:
            log.info("ровер", "SSH закрыто")
        print("\nSSH закрыто. Готово.")

    elapsed = (datetime.datetime.now() - t_start).total_seconds()
    return {
        "finish_found": target_coord is not None,
        "finish_cell": target_coord,
        "elapsed_sec": elapsed,
    }