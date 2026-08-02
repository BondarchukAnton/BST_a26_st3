#!/usr/bin/env python3
"""
main.py — Оркестратор автономной миссии «Дрон + Ровер».

Порядок выполнения:
  1. Дрон: взлёт → облёт точек A1/E2 → YOLO-поиск → VLM-верификация
  2. Дрон: полёт к роверу → ArUco-посадка на метку 332
  3. Пауза 15 сек после посадки
  4. Ровер: старт миссии с координатами цели (определяются по точке находки)

Все результаты сохраняются в директорию запуска:
  - logs/mission_YYYYMMDD_HHMMSS.log  — лог миссии
  - cheburashka_detected.jpg          — фото находки
  - vlm_result.json                   — вывод VLM

Использование:
  python3 main.py [--drone-ip IP] [--rover-ip IP] [--altitude M]

Параметры по умолчанию — в config/settings.py.
"""

import os
import sys
import time
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import (
    WAYPOINTS, WAYPOINT_NAMES, ROVER_TARGETS,
    LANDING_DELAY, LOGS_DIR, MISSION_LOG_NAME,
    DRONE_IP, ROVER_IP,
)
from src.logger import MissionLogger
from src.drone_mission import run_drone_mission
from src.rover_mission import run_rover_mission


def _closest_waypoint(point, waypoints):
    """Возвращает ближайшую точку из списка waypoints."""
    if point is None:
        return None
    px, py = point
    best = None
    best_dist = float("inf")
    for wp in waypoints:
        wx, wy = wp
        dist = ((px - wx) ** 2 + (py - wy) ** 2) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best = wp
    return best


def main():
    parser = argparse.ArgumentParser(
        description="Автономная миссия «Дрон + Ровер» — поиск Чебурашки",
    )
    parser.add_argument("--drone-ip", default=DRONE_IP,
                        help="IP-адрес дрона")
    parser.add_argument("--rover-ip", default=ROVER_IP,
                        help="IP-адрес ровера")
    parser.add_argument("--altitude", type=float, default=None,
                        help="Рабочая высота дрона (м)")
    args = parser.parse_args()

    # Переопределяем IP через переменные окружения (если заданы в командной строке)
    if args.drone_ip != DRONE_IP:
        os.environ["DRONE_IP"] = args.drone_ip
    if args.rover_ip != ROVER_IP:
        os.environ["ROVER_IP"] = args.rover_ip

    # Создаём директорию логов
    os.makedirs(LOGS_DIR, exist_ok=True)

    # Имя файла лога с меткой времени
    log_filename = datetime.now().strftime(
        f"mission_%Y%m%d_%H%M%S.log"
    )
    log_path = os.path.join(LOGS_DIR, log_filename)

    log = MissionLogger(log_path)

    sep = "=" * 60
    print(f"\n{sep}")
    log.info("координатор", "МИССИЯ ЗАПУЩЕНА")
    print(sep)

    log.info("координатор",
             f"дрон: {args.drone_ip}, ровер: {args.rover_ip}")
    wp_labels = [f"{WAYPOINT_NAMES.get(wp, str(wp))}={wp}" for wp in WAYPOINTS]
    log.info("координатор", f"точки поиска: {', '.join(wp_labels)}")
    log.info("координатор",
             f"файл лога: {log_path}")

    # ═════════════════════════════════════════════════════════════════════
    # ФАЗА 1: ДРОН — ПОИСК + ПОСАДКА
    # ═════════════════════════════════════════════════════════════════════
    log.start_phase(1, "ДРОН: ПОИСК ОБЪЕКТА + ПОСАДКА НА РОВЕР")

    drone_result = run_drone_mission(logger=log)

    log.end_phase(1)

    # ═════════════════════════════════════════════════════════════════════
    # АНАЛИЗ РЕЗУЛЬТАТА ДРОНА
    # ═════════════════════════════════════════════════════════════════════
    found_point = drone_result.get("point")
    found = drone_result.get("found", False)
    landing_ok = drone_result.get("landing_ok", False)

    if not found or found_point is None:
        log.info("координатор",
                 "ОБЪЕКТ НЕ НАЙДЕН. Миссия ровера отменена.")
        log.info("координатор",
                 "Проверьте точки поиска и конфигурацию YOLO/VLM.")
        log.finish()
        print(f"\nЛог сохранён: {log_path}")
        return 1

    # Определяем, к какой из точек поиска ближе находка
    closest_wp = _closest_waypoint(found_point, WAYPOINTS)
    if closest_wp is None:
        log.info("координатор",
                 "Не удалось сопоставить точку находки с точками поиска.")
        log.finish()
        print(f"\nЛог сохранён: {log_path}")
        return 1

    wp_name = WAYPOINT_NAMES.get(closest_wp, str(closest_wp))
    rover_target = ROVER_TARGETS.get(closest_wp)

    log.info("координатор",
             f"объект найден у точки {wp_name} "
             f"({found_point[0]:.3f}, {found_point[1]:.3f})")

    if rover_target is None:
        log.info("координатор",
                 f"Нет сопоставления для точки {wp_name}. "
                 f"Доступны: {list(ROVER_TARGETS.keys())}")
        log.finish()
        print(f"\nЛог сохранён: {log_path}")
        return 1

    log.info("координатор",
             f"цель ровера: клетка ({rover_target[0]}, {rover_target[1]})")
    log.info("координатор",
             f"посадка дрона: {'OK' if landing_ok else 'FAIL'}")

    # Логируем события для рекордов
    log.drone_detect_stable(
        confidence=drone_result.get("vlm", {}).get("confidence", 0.0),
        frames=1,
        point_name=wp_name,
    )
    log.drone_send_coords(
        target_point=f"{wp_name}={closest_wp}",
    )

    # ═════════════════════════════════════════════════════════════════════
    # ФАЗА 2: ОЖИДАНИЕ ПОСЛЕ ПОСАДКИ
    # ═════════════════════════════════════════════════════════════════════
    log.start_phase(2, "ОЖИДАНИЕ ПОСЛЕ ПОСАДКИ ДРОНА")
    log.info("координатор",
             f"пауза {LANDING_DELAY:.0f} сек после посадки...")
    time.sleep(LANDING_DELAY)
    log.info("координатор", "пауза завершена")
    log.end_phase(2)

    # ═════════════════════════════════════════════════════════════════════
    # ФАЗА 3: РОВЕР — МИССИЯ
    # ═════════════════════════════════════════════════════════════════════
    log.start_phase(3, "РОВЕР: ДВИЖЕНИЕ К ЦЕЛИ + ПОИСК ФИНИША")

    rx, ry = rover_target
    log.rover_recv_coords(target_cell=f"({rx}, {ry})")
    log.rover_cmd_move(cell=f"({rx}, {ry})")

    rover_result = run_rover_mission(target_x=rx, target_y=ry, log=log)

    log.end_phase(3)

    # ═════════════════════════════════════════════════════════════════════
    # ФИНАЛ
    # ═════════════════════════════════════════════════════════════════════
    log.info("координатор",
             f"ровер: финиш={'найден' if rover_result.get('finish_found') else 'не найден'}")
    if rover_result.get("finish_cell"):
        fc = rover_result["finish_cell"]
        log.info("координатор", f"финишная клетка: ({fc[0]}, {fc[1]})")

    print(f"\n{sep}")
    log.finish()
    print(sep)

    print(f"\nЛог сохранён: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())