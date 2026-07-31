"""
Алгоритм обнаружения и уклонения от техники противника
Анализирует приближение противника по секторам камеры и ArUco-маркерам.
Вычисляет маршрут экстренного отхода, находящийся исключительно в БЕЗОПАСНЫХ ЗОНАХ (SAFE_ZONES).
"""

import logging
from typing import Tuple, List, Optional
import config
from grid_map import GridMap

logger = logging.getLogger("EnemyDodgeSystem")

class EnemyDodgeSystem:
    def __init__(self, grid: GridMap):
        self.grid = grid
        self.threshold = config.SAFE_DISTANCE_THRESHOLD
        self.last_threat_level = "SAFE"  # SAFE, WARNING, EVADING
        self.evasion_count = 0

    def evaluate_threat(self, our_cell: str, enemy_cell: str) -> Tuple[str, float]:
        """
        Вычисляет дистанцию и уровень угрозы.
        Возвращает (threat_level, distance).
        """
        dist = self.grid.distance(our_cell, enemy_cell)
        
        if dist < 1.1:
            threat_level = "EVADING"  # Критическая опасность! Прямое соседство
        elif dist <= self.threshold:
            threat_level = "WARNING"  # Приближение противника
        else:
            threat_level = "SAFE"
            
        self.last_threat_level = threat_level
        return threat_level, dist

    def find_best_retreat_cell(self, our_cell: str, enemy_cell: str) -> str:
        """
        Находит смежную безопасную ячейку, максимально удаленную от ровера противника.
        """
        candidates = self.grid.get_adjacent_safe_cells(our_cell)
        
        best_cell = our_cell
        max_dist = self.grid.distance(our_cell, enemy_cell)
        
        for neighbor in candidates:
            dist_to_enemy = self.grid.distance(neighbor, enemy_cell)
            if dist_to_enemy > max_dist:
                max_dist = dist_to_enemy
                best_cell = neighbor
                
        return best_cell

    def execute_sector_evasion(self, rover_ctrl, sector: str) -> bool:
        """
        Выполняет немедленный уход на основе визульного сектора камеры ('up', 'down', 'left', 'right').
        """
        self.evasion_count += 1
        logger.warning(f"🚨 АКТИВИРОВАНО УБЕЖИЩЕ ПО СЕКТОРУ! Противник обнаружен в секторе '{sector}'")
        
        rover_ctrl.emergency_stop()
        
        current_cell = rover_ctrl.current_cell
        adjacent_safe = self.grid.get_adjacent_safe_cells(current_cell)
        
        if not adjacent_safe:
            logger.error("Нет доступных смежных безопасных ячеек для уклонения!")
            return False

        target_cell = adjacent_safe[0]
        
        logger.info(f"Перемещение Ровера из {current_cell} в Безопасную Ячейку {target_cell} на повышенной скорости...")
        success = rover_ctrl.move_to_cell(target_cell, speed_multiplier=config.EVASION_SPEED_MULTIPLIER)
        return success

    def execute_dodge_maneuver(self, rover_ctrl, drone_ctrl, our_cell: str, enemy_cell: str) -> str:
        """
        Выполняет маневр экстренного уклонения:
        1. Экстренный останов движения
        2. Определение безопасной ячейки для отступления
        3. Маневр отхода ровера на повышенной скорости
        4. Зависание БПЛА «Сверх» сверху для наблюдения
        """
        self.evasion_count += 1
        retreat_cell = self.find_best_retreat_cell(our_cell, enemy_cell)
        
        logger.warning(f"🚨 ОБНАРУЖЕНА УГРОЗА! Противник в {enemy_cell} (Дистанция: {self.grid.distance(our_cell, enemy_cell):.2f}м)")
        logger.info(f"Выполнение экстренного отступления из {our_cell} -> {retreat_cell} (БЕЗОПАСНАЯ ЗОНА)")
        
        # 1. Экстренный останов
        rover_ctrl.emergency_stop()
        
        # 2. Перемещение БПЛА для слежения
        drone_ctrl.navigate_to_cell(enemy_cell)
        
        # 3. Отход Ровера
        rover_ctrl.move_to_cell(retreat_cell, speed_multiplier=config.EVASION_SPEED_MULTIPLIER)
        
        logger.info(f"✅ Маневр уклонения завершен. Ровер защищен в ячейке {retreat_cell}.")
        return retreat_cell

