"""
Карта сетки ArUco и система поиска путей (Алгоритм A* с ограничением по БЕЗОПАСНЫМ ЗОНАМ)
Вычисляет расстояния, сопоставляет координаты и находит оптимальные безопасные маршруты.
"""

import math
from typing import List, Tuple, Optional, Dict, Set
import config

class GridMap:
    def __init__(self):
        self.rows = config.GRID_ROWS
        self.cols = config.GRID_COLS
        self.safe_zones: Set[str] = set(config.SAFE_ZONES)
        self.enemy_zones: Set[str] = set(config.ENEMY_ZONES)

    @staticmethod
    def cell_to_coords(cell: str) -> Tuple[float, float]:
        """Преобразует строковое имя ячейки ('D1') в координаты (x, y) в метрах."""
        if not cell or len(cell) < 2:
            return (0.0, 0.0)
        row_char = cell[0].upper()
        col_num = int(cell[1:])
        
        row_idx = ord(row_char) - ord('A')
        col_idx = col_num - 1
        
        x = col_idx * config.CELL_SIZE_METERS
        y = row_idx * config.CELL_SIZE_METERS
        return (x, y)

    @staticmethod
    def coords_to_cell(x: float, y: float) -> str:
        """Преобразует координаты (x, y) в метрах в имя ближайшей ячейки ('D1')."""
        col_idx = max(0, min(5, int(round(x / config.CELL_SIZE_METERS))))
        row_idx = max(0, min(5, int(round(y / config.CELL_SIZE_METERS))))
        
        row_char = chr(ord('A') + row_idx)
        col_num = col_idx + 1
        return f"{row_char}{col_num}"

    def is_safe(self, cell: str) -> bool:
        """Проверяет, принадлежит ли ячейка к нашей безопасной зоне."""
        return cell in self.safe_zones

    def distance(self, cell1: str, cell2: str) -> float:
        """Евклидово расстояние между двумя ячейками в метрах."""
        x1, y1 = self.cell_to_coords(cell1)
        x2, y2 = self.cell_to_coords(cell2)
        return math.hypot(x2 - x1, y2 - y1)

    def get_adjacent_safe_cells(self, cell: str) -> List[str]:
        """Получает 4 смежные ячейки, находящиеся в БЕЗОПАСНЫХ ЗОНАХ."""
        x, y = self.cell_to_coords(cell)
        row_idx = int(y / config.CELL_SIZE_METERS)
        col_idx = int(x / config.CELL_SIZE_METERS)
        
        neighbors = []
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        
        for dr, dc in directions:
            r = row_idx + dr
            c = col_idx + dc
            if 0 <= r < 6 and 0 <= c < 6:
                neighbor_cell = f"{chr(ord('A') + r)}{c + 1}"
                if self.is_safe(neighbor_cell):
                    neighbors.append(neighbor_cell)
                    
        return neighbors

    def find_safe_path(self, start: str, target: str) -> Optional[List[str]]:
        """
        Алгоритм поиска пути A*, ограниченный ИСКЛЮЧИТЕЛЬНО безопасными зонами.
        Возвращает список ячеек от старта до цели.
        """
        if not self.is_safe(start):
            print(f"[GridMap] Предупреждение: Стартовая ячейка {start} не в безопасной зоне!")
        if not self.is_safe(target):
            print(f"[GridMap] Ошибка: Целевая ячейка {target} не в безопасной зоне!")
            return None

        open_set = {start}
        came_from: Dict[str, str] = {}
        
        g_score: Dict[str, float] = {start: 0.0}
        f_score: Dict[str, float] = {start: self.distance(start, target)}
        
        while open_set:
            current = min(open_set, key=lambda c: f_score.get(c, float('inf')))
            
            if current == target:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path
                
            open_set.remove(current)
            
            for neighbor in self.get_adjacent_safe_cells(current):
                tentative_g = g_score[current] + 1.0
                
                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self.distance(neighbor, target)
                    open_set.add(neighbor)
                    
        return None
