#!/usr/bin/env python3
"""
Тест: движение ровера к заданной точке с уклонением от противника.
Пока ровер едет, можно в любой момент задать координаты противника —
ровер выполнит манёвр уклонения и перестроит маршрут.

Использование:
    python3 test_rover_dodge.py D1 F3
    python3 test_rover_dodge.py D1 F3 --rover 192.168.1.33

Во время движения вводи в консоли команды:
    enemy A3     — задать позицию противника (ровер начнёт уклоняться)
    stop         — аварийная остановка и выход
"""

import sys
import time
import math
import json
import urllib.request
import urllib.error
import threading
import os

# ═══════════════════════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════════════════════

ROVER_IP = os.environ.get("ROVER_IP", "192.168.1.201")
ROVER_PORT = int(os.environ.get("ROVER_PORT", "8767"))
ROVER_API = f"http://{ROVER_IP}:{ROVER_PORT}"

START_CELL = "D1"           # стартовая ячейка (по умолчанию)
CELL_SIZE = 1.0             # размер клетки в метрах

# Зоны: какие клетки доступны для движения (безопасные)
SAFE_ZONES = {
    "A1", "D1", "E1", "F1",
    "E2", "F2", "F3",
    "A4", "A5", "A6",
    "B4", "B5", "B6",
    "C4", "C5", "C6",
    "D5", "D6",
}

GRID_ROWS = ["A", "B", "C", "D", "E", "F"]
GRID_COLS = [1, 2, 3, 4, 5, 6]

INTERACTIVE = sys.stdout.isatty()  # True если запущено из терминала

# ═══════════════════════════════════════════════════════════════════════════════
# УТИЛИТЫ: HTTP-команды роверу
# ═══════════════════════════════════════════════════════════════════════════════

def rover_post(endpoint: str, payload: dict = None, timeout: float = 5.0) -> dict:
    """Отправляет JSON POST на API ровера."""
    url = f"{ROVER_API}{endpoint}"
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return {"ok": True, "data": json.loads(body) if body else {}}
            except Exception:
                return {"ok": True, "data": body}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def rover_initial_cell(cell: str):
    """Задаёт стартовую позицию ровера."""
    print(f"[ROVER] initial-cell → {cell}")
    return rover_post("/initial-cell", {"cell": cell, "initial_cell": cell})


def rover_goal_cell(cell: str):
    """Отправляет ровер в указанную клетку."""
    print(f"[ROVER] goal-cell → {cell}")
    return rover_post("/goal-cell", {"cell": cell, "goal_cell": cell})


def rover_stop():
    """Аварийная остановка."""
    print("[ROVER] EMERGENCY STOP")
    return rover_post("/stop", {})


def rover_clear():
    """Снятие программного STOP."""
    return rover_post("/clear", {})


# ═══════════════════════════════════════════════════════════════════════════════
# ГРИД
# ═══════════════════════════════════════════════════════════════════════════════

def cell_to_coords(cell: str):
    """Переводит 'D1' → (x, y) в метрах."""
    row_char = cell[0].upper()
    col_num = int(cell[1:])
    x = (col_num - 1) * CELL_SIZE
    y = (ord(row_char) - ord('A')) * CELL_SIZE
    return x, y


def distance(cell1: str, cell2: str) -> float:
    """Евклидово расстояние между клетками (м)."""
    x1, y1 = cell_to_coords(cell1)
    x2, y2 = cell_to_coords(cell2)
    return math.hypot(x2 - x1, y2 - y1)


def get_adjacent(cell: str):
    """Соседние клетки (вверх/вниз/влево/вправо)."""
    row_char = cell[0].upper()
    col = int(cell[1:])
    row_idx = ord(row_char) - ord('A')
    col_idx = col - 1

    neighbors = []
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        r, c = row_idx + dr, col_idx + dc
        if 0 <= r < 6 and 0 <= c < 6:
            nb = f"{chr(ord('A') + r)}{c + 1}"
            if nb in SAFE_ZONES:
                neighbors.append(nb)
    return neighbors


def find_path(start: str, target: str):
    """A* только по безопасным клеткам. Возвращает список клеток или None."""
    if start not in SAFE_ZONES:
        print(f"[GRID] WARNING: start {start} not safe")
    if target not in SAFE_ZONES:
        print(f"[GRID] ERROR: target {target} not safe")
        return None

    open_set = {start}
    came_from = {}
    g_score = {start: 0.0}
    f_score = {start: distance(start, target)}

    while open_set:
        cur = min(open_set, key=lambda c: f_score.get(c, float('inf')))
        if cur == target:
            path = [cur]
            while cur in came_from:
                cur = came_from[cur]
                path.append(cur)
            path.reverse()
            return path

        open_set.remove(cur)
        for nb in get_adjacent(cur):
            g = g_score[cur] + 1.0
            if g < g_score.get(nb, float('inf')):
                came_from[nb] = cur
                g_score[nb] = g
                f_score[nb] = g + distance(nb, target)
                open_set.add(nb)
    return None


def find_retreat_cell(our: str, enemy: str):
    """Находит смежную безопасную клетку, макс. удалённую от врага."""
    candidates = get_adjacent(our)
    best = our
    max_dist = distance(our, enemy)
    for nb in candidates:
        d = distance(nb, enemy)
        if d > max_dist:
            max_dist = d
            best = nb
    return best


# ═══════════════════════════════════════════════════════════════════════════════
# ФОН: чтение команд пользователя
# ═══════════════════════════════════════════════════════════════════════════════

_user_command = None
_cmd_lock = threading.Lock()


def input_reader():
    """Фоновый поток: читает stdin и сохраняет последнюю команду."""
    global _user_command
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip()
            if cmd:
                with _cmd_lock:
                    _user_command = cmd
        except Exception:
            break


def get_user_command():
    """Потокобезопасное получение последней команды (None если нет)."""
    with _cmd_lock:
        cmd = _user_command
        _user_command = None
        return cmd


def process_user_command(our_cell: str, target_cell: str):
    """Обрабатывает команду пользователя.
    'enemy A3' → возвращает (True, A3) — нужно уклониться.
    'stop'     → возвращает (False, None) — выход.
    Иначе      → возвращает (None, None) — продолжать движение.
    """
    cmd = get_user_command()
    if cmd is None:
        return None, None

    parts = cmd.split()
    if not parts:
        return None, None

    if parts[0] == "stop":
        print("\n[CMD] ПОЛУЧЕНА КОМАНДА 'stop' — завершение.")
        return False, None

    if parts[0] == "enemy" and len(parts) >= 2:
        ec = parts[1].upper()
        if len(ec) >= 2 and ec[0] in "ABCDEF" and ec[1:].isdigit():
            print(f"\n[CMD] Противник обнаружен в клетке {ec}")
            return True, ec
        else:
            print(f"[CMD] Неверный формат клетки: {parts[1]}")
            return None, None

    if parts[0] == "status":
        print(f"\n[STATUS] Ровер: {our_cell}  |  Цель: {target_cell}")
        return None, None

    if parts[0] == "help":
        print("\nДоступные команды:")
        print("  enemy A3  — задать клетку противника")
        print("  status    — текущая позиция и цель")
        print("  stop      — аварийный останов и выход")
        return None, None

    print(f"[CMD] Неизвестная команда: {cmd}")
    return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ЛОГИКА
# ═══════════════════════════════════════════════════════════════════════════════

def print_header():
    print("=" * 60)
    print("  ТЕСТ: ДВИЖЕНИЕ РОВЕРА С УКЛОНЕНИЕМ ОТ ПРОТИВНИКА")
    print(f"  Ровер: {ROVER_API}")
    print("=" * 60)
    if INTERACTIVE:
        print("  Команды: enemy A3 | status | stop | help")
        print("=" * 60)


def print_grid(our: str, enemy: str, path: list):
    """ASCII-карта 6×6."""
    path_set = set(path) if path else set()
    print("\n    1   2   3   4   5   6")
    print("  +---+---+---+---+---+---+")
    for r_char in GRID_ROWS:
        line = f" {r_char} |"
        for c_num in GRID_COLS:
            cell = f"{r_char}{c_num}"
            if cell == our and cell == enemy:
                m = "X"
            elif cell == our:
                m = "R"
            elif cell == enemy:
                m = "E"
            elif cell in path_set:
                m = "*"
            elif cell in SAFE_ZONES:
                m = "."
            else:
                m = "#"
            line += f" {m} |"
        print(line)
        print("  +---+---+---+---+---+---+")
    print("  R=Ровер  E=Противник  *=Маршрут  .=Безопасно  #=Опасно\n")


def run(target: str):
    """Основной цикл: движение к цели с отслеживанием противника."""
    print_header()

    our = START_CELL
    enemy = None

    # Построить начальный маршрут
    path = find_path(START_CELL, target)
    if path is None:
        print(f"[ERROR] Нет безопасного пути из {START_CELL} в {target}!")
        return
    print(f"Маршрут ({len(path)} шагов): {' → '.join(path)}")
    print_grid(our, "—", path)

    # Установить начальную позицию
    rover_initial_cell(START_CELL)
    rover_clear()

    # Запустить поток чтения команд
    if INTERACTIVE:
        reader = threading.Thread(target=input_reader, daemon=True)
        reader.start()

    evasion_count = 0
    step = 0
    current_path = list(path)

    while step < len(current_path):
        next_cell = current_path[step]
        enemy_cell = None

        # Проверить есть ли команда от пользователя
        action, enemy_cell = process_user_command(our, target)

        if action is False:  # stop
            rover_stop()
            return

        if action is True and enemy_cell is not None:  # enemy задан
            enemy = enemy_cell
            dist_to_rover = distance(our, enemy)
            print(f"\n{'!' * 50}")
            print(f"  ПРОТИВНИК В {enemy} (дистанция: {dist_to_rover:.1f} м)")
            print(f"{'!' * 50}")

            # Оценить угрозу
            if dist_to_rover < 1.1:
                print("  УРОВЕНЬ: КРИТИЧЕСКИЙ — прямое соседство!")
            elif dist_to_rover <= 1.5:
                print("  УРОВЕНЬ: ПРЕДУПРЕЖДЕНИЕ — противник приближается")
            else:
                print("  УРОВЕНЬ: низкий — просто фиксируем позицию")

            # Манёвр уклонения
            evasion_count += 1
            retreat = find_retreat_cell(our, enemy)
            print(f"  Отход из {our} → {retreat}")

            rover_stop()
            time.sleep(0.5)
            rover_goal_cell(retreat)
            our = retreat

            # Перестроить маршрут от новой позиции
            new_path = find_path(retreat, target)
            if new_path:
                print(f"  Новый маршрут: {' → '.join(new_path)}")
                current_path = new_path
                step = 0
                print_grid(our, enemy, current_path)
                continue
            else:
                print(f"  [ERROR] Не удалось перестроить маршрут из {retreat} в {target}")
                break

        # Двигаемся к следующей клетке
        rover_goal_cell(next_cell)
        our = next_cell
        step += 1
        print_grid(our, enemy or "—", current_path)

    print("\n" + "=" * 60)
    if our == target:
        print(f"  ЦЕЛЬ ДОСТИГНУТА: {target}")
    else:
        print(f"  МИССИЯ ПРЕРВАНА. Ровер в {our}")
    print(f"  Манёвров уклонения: {evasion_count}")
    print("=" * 60)


# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python3 test_rover_dodge.py <target_cell>")
        print("  python3 test_rover_dodge.py <target_cell> --rover <ip>")
        print("Пример:")
        print("  python3 test_rover_dodge.py F3")
        print("  python3 test_rover_dodge.py F3 --rover 192.168.1.33")
        sys.exit(1)

    target_cell = sys.argv[1].upper()

    for i, arg in enumerate(sys.argv):
        if arg == "--rover" and i + 1 < len(sys.argv):
            ROVER_IP = sys.argv[i + 1]
            ROVER_API = f"http://{ROVER_IP}:{ROVER_PORT}"

    if target_cell not in SAFE_ZONES:
        print(f"[ERROR] Целевая клетка {target_cell} не в безопасной зоне!")
        print(f"  Доступные: {sorted(SAFE_ZONES)}")
        sys.exit(1)

    run(target_cell)