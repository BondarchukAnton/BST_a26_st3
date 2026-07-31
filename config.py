"""
Конфигурационный файл Пульта Управления Автономным Ровером и БПЛА «Сверх»
Соревнования: Архипелаг 2026, «Воздушный дозор»
Команда: БВС Стресс-тест | Организаторы: Сверх
"""

import os

# Hardware Credentials & Endpoints
DRONE_IP = os.getenv("DRONE_IP", "192.168.1.37")
DRONE_USER = os.getenv("DRONE_USER", "sverk")
DRONE_PASS = os.getenv("DRONE_PASS", "sverk")

ROVER_IP = os.getenv("ROVER_IP", "192.168.1.33")  # IP without http:// prefix for SSH/Ping
ROVER_API_URL = os.getenv("ROVER_API_URL", "http://192.168.1.33:8767")
ROVER_USER = os.getenv("ROVER_USER", "pi")
ROVER_PASS = os.getenv("ROVER_PASS", "raspberry")

ROVER_CLIENT_PORT = int(os.getenv("ROVER_CLIENT_PORT", 8767))
ROVER_MCP_PORT = int(os.getenv("ROVER_MCP_PORT", 8766))
ROVER_WEB_API_PORT = int(os.getenv("ROVER_WEB_API_PORT", 8765))

# Starting Cell for Rover
START_CELL = os.getenv("START_CELL", "D1")

# Grid Dimensions
GRID_ROWS = ["A", "B", "C", "D", "E", "F"]
GRID_COLS = [1, 2, 3, 4, 5, 6]
GRID_SIZE_X = 6
GRID_SIZE_Y = 6
CELL_SIZE_METERS = 1.0  # 1 meter per AruCo grid tile

# Territory Boundaries
SAFE_ZONES = [
    "A1", "D1", "E1", "F1", 
    "E2", "F2", "F3", 
    "A4", "A5", "A6", 
    "B4", "B5", "B6", 
    "C4", "C5", "C6", 
    "D5", "D6"
]

ENEMY_ZONES = [
    "A2", "A3", 
    "B1", "B2", "B3", 
    "C1", "C2", "C3", 
    "D2", "D3", "D4", 
    "E3", "E4", "E5", "E6", 
    "F4", "F5", "F6"
]

# Drone Flight Parameters
TAKEOFF_ALTITUDE = float(os.getenv("TAKEOFF_ALTITUDE", "1.2"))  # Meters
TAKEOFF_FRAME = os.getenv("TAKEOFF_FRAME", "body")              # 'body' or 'rangefinder'
NAV_FRAME = os.getenv("NAV_FRAME", "aruco_map")
NAV_SPEED = float(os.getenv("NAV_SPEED", "0.5"))                # m/s

# Patrol Waypoints & Search Parameters
WAYPOINTS = ["E1", "A5"]
WAYPOINT_PROXIMITY_THRESHOLD = 0.5  # meters threshold to filter false positive YOLO detections
RANDOM_OFFSET_RANGE = 0.3          # random displacement range on repeated passes

# ArUco Marker IDs
ROVER_ARUCO_ID = int(os.getenv("ROVER_ARUCO_ID", "10"))
ENEMY_ARUCO_ID = int(os.getenv("ENEMY_ARUCO_ID", "99"))

# YOLO & VLM Analysis Parameters
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "/tmp/model.pt")
YOLO_TARGET_CLASS = os.getenv("YOLO_TARGET_CLASS", "bear")
YOLO_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.5"))

VLM_API_KEY = os.getenv("SVERK_API_KEY", "sk-sverk-vlm-key")
VLM_API_BASE = os.getenv("SVERK_API_BASE", "https://ai.sverk.tech/v1")
VLM_MODEL = os.getenv("VLM_MODEL", "gemma4-vlm")

# Dodge System Parameters
SAFE_DISTANCE_THRESHOLD = 1.5  # Tiles / meters
EVASION_SPEED_MULTIPLIER = 1.2
ROVER_ROTATION_TIME = 2.0      # seconds for rotation step during ground search

