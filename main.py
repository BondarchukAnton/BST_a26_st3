#!/usr/bin/env python3
"""
Основная точка входа — Пульт Управления Наземным Ровером и БПЛА «Сверх»
Соревнования: Архипелаг 2026, «Воздушный дозор» | Команда: БВС Стресс-тест | Организаторы: Сверх

Запуск в терминале:
    python3 main.py
    python3 main.py --start D1 --target F3

Работает с реальным оборудованием:
 - БПЛА «Сверх» через SSH/ROS 2 (192.168.1.37)
 - Ровер «Сверх» через HTTP API / SSH (192.168.1.33:8767)
"""

import sys
import time
import signal
import logging
import argparse
import config
from grid_map import GridMap
from rover_client import RoverController
from drone_client import DroneSverkController
from dodge_algorithm import EnemyDodgeSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MissionControl")

def print_banner():
    banner = r"""
    ========================================================================
    |   ПУЛЬТ УПРАВЛЕНИЯ БПЛА «СВЕРХ» И НАЗЕМНЫМ РОВЕРОМ — «СТРЕСС-ТЕСТ»   |
    |   Соревнования Архипелаг 2026 — «Воздушный дозор» (Орг.: Сверх)      |
    |   Сетка ArUco: A1 до F6 | Старт: D1                                  |
    |   БПЛА Сверх SSH: 192.168.1.37 (sverk/sverk)                         |
    |   Ровер Сверх REST/SSH: 192.168.1.33:8767 (pi/raspberry)             |
    ========================================================================
    """
    print(banner)

def render_ascii_grid(our_cell: str, enemy_cell: str, drone_cell: str, path: list):
    """Вывод 6x6 ASCII-карты полигона с отображением безопасных и опасных зон."""
    print("\n--- ОПЕРАТИВНАЯ КАРТА ПОЛИГОНА СВЕРХ (A1 - F6) ---")
    print("     1   2   3   4   5   6")
    print("   +---+---+---+---+---+---+")
    
    grid = GridMap()
    for r_idx, r_char in enumerate(config.GRID_ROWS):
        line = f" {r_char} |"
        for c_idx, c_num in enumerate(config.GRID_COLS):
            cell = f"{r_char}{c_num}"
            marker = " "
            
            if cell == our_cell and cell == enemy_cell:
                marker = "X"  # Столкновение / Угроза
            elif cell == our_cell:
                marker = "R"  # Наш Ровер
            elif cell == enemy_cell:
                marker = "E"  # Ровер Противника
            elif cell == drone_cell:
                marker = "D"  # БПЛА Сверх сверху
            elif cell in path:
                marker = "*"  # Маршрут
            elif grid.is_safe(cell):
                marker = "."  # Безопасная зона
            else:
                marker = "#"  # Опасная территория
                
            line += f" {marker} |"
        print(line)
        print("   +---+---+---+---+---+---+")
    print("Легенда: [R] Ровер | [D] БПЛА Сверх | [E] Противник | [*] Маршрут | [.] Безопасно | [#] Опасно\n")

def run_mission(start_cell: str = config.START_CELL, target_cell: str = "F3"):
    print_banner()
    logger.info(f"Инициализация миссии: Старт Ровера={start_cell} | Целевая ячейка={target_cell}")
    
    grid = GridMap()
    rover = RoverController()
    drone = DroneSverkController()
    dodge_sys = EnemyDodgeSystem(grid=grid)
    
    def handle_exit(sig, frame):
        logger.warning("\n⚠️ СИГНАЛ ПРЕРЫВАНИЯ! Выполнение экстренной остановки оборудования...")
        try:
            rover.emergency_stop()
            drone.land()
        except Exception as e:
            logger.error(f"Ошибка экстренного останова: {e}")
        sys.exit(1)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # 1. Подключение оборудования
    logger.info("Подключение к оборудованию Ровера и БПЛА...")
    rover_connected = rover.connect()
    drone_connected = drone.connect()
    
    if not rover_connected:
        logger.error(f"Невозможно продолжить: Ровер недоступен по адресу {config.ROVER_IP}:{config.ROVER_CLIENT_PORT}")
        sys.exit(1)
        
    if not drone_connected:
        logger.error(f"Невозможно продолжить: БПЛА «Сверх» недоступен по SSH ({config.DRONE_IP})")
        sys.exit(1)

    our_pos = start_cell
    enemy_pos = "НЕИЗВЕСТНО"
    drone_pos = start_cell

    # 2. Взлет БПЛА Сверх
    logger.info("Выполнение процедуры взлета БПЛА «Сверх»...")
    takeoff_ok = drone.takeoff(altitude=config.TAKEOFF_ALTITUDE, frame_id=config.TAKEOFF_FRAME)
    if not takeoff_ok:
        logger.error("Ошибка взлета БПЛА. Миссия отменена для обеспечения безопасности.")
        rover.emergency_stop()
        sys.exit(1)

    # 3. Расчет безопасного траекторного пути
    logger.info(f"Расчет безопасного маршрута из {start_cell} в {target_cell} по безопасным зонам...")
    path = grid.find_safe_path(start=start_cell, target=target_cell)
    if not path:
        logger.error(f"Не найден безопасный путь между {start_cell} и {target_cell}!")
        drone.land()
        sys.exit(1)

    logger.info(f"Безопасный маршрут построен ({len(path)} ячеек): {' -> '.join(path)}")
    render_ascii_grid(our_pos, enemy_pos, drone_pos, path)

    # 4. Прохождение маршрута и мониторинг противника
    logger.info("Старт движения техники и сканирования ArUco маркеров...")
    current_path = list(path)
    step_idx = 0

    while step_idx < len(current_path):
        next_cell = current_path[step_idx]
        logger.info(f"Движение -> Следующая ячейка: {next_cell} | Позиция Ровера: {our_pos}")

        # Сканирование ArUco маркеров
        aruco_res = drone.scan_aruco_markers()
        if aruco_res.get("success"):
            markers = aruco_res.get("markers", {})
            enemy_id = config.ENEMY_ARUCO_ID
            if enemy_id in markers or str(enemy_id) in markers:
                e_data = markers.get(enemy_id) or markers.get(str(enemy_id))
                sector = e_data.get("sector", "center")
                logger.warning(f"🚨 ОБНАРУЖЕН МАРКЕР ПРОТИВНИКА в секторе кадра '{sector}'!")
                
                dodge_sys.execute_sector_evasion(rover, sector)
                our_pos = rover.current_cell
                
                new_path = grid.find_safe_path(our_pos, target_cell)
                if new_path:
                    logger.info(f"Пересчитанный маршрут: {' -> '.join(new_path)}")
                    current_path = new_path
                    step_idx = 0
                    render_ascii_grid(our_pos, enemy_pos, drone_pos, current_path)
                    continue

        rover_success = rover.move_to_cell(next_cell)
        drone_success = drone.navigate_to_cell(next_cell)

        if not rover_success:
            logger.error(f"Ошибка движения Ровера в ячейку {next_cell}. Остановка.")
            break

        our_pos = rover.current_cell
        drone_pos = drone.current_cell
        step_idx += 1

        render_ascii_grid(our_pos, enemy_pos, drone_pos, current_path)

    # 5. VLM Снимок в целевой точке
    logger.info("Целевая ячейка достигнута. Выполнение VLM снимка и анализа местности...")
    vlm_result = drone.capture_photo_and_analyze_vlm("Описать целевую зону и определить присутствующие объекты.")
    if vlm_result.get("success"):
        logger.info(f"Результат VLM анализа: {vlm_result.get('vlm_response', {}).get('description')}")

    # 6. Посадка и финализация
    logger.info("Посадка БПЛА «Сверх» и перевод Ровера в режим ожидания...")
    drone.land()
    
    logger.info("========================================================================")
    logger.info(" 🎉 МИССИЯ НА РЕАЛЬНОМ ОБОРУДОВАНИИ УСПЕШНО ЗАВЕРШЕНА!")
    logger.info(f" - Финальная ячейка Ровера: {our_pos}")
    logger.info(f" - Выполнено маневров уклонения: {dodge_sys.evasion_count}")
    logger.info("========================================================================\n")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Пульт управления БПЛА «Сверх» и Ровером (Архипелаг 2026)")
    parser.add_argument("--start", default=config.START_CELL, help=f"Стартовая ячейка (По умолчанию: {config.START_CELL})")
    parser.add_argument("--target", default="F3", help="Целевая ячейка (По умолчанию: F3)")
    
    args = parser.parse_args()
    run_mission(start_cell=args.start, target_cell=args.target)

