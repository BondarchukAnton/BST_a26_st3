# Все константы и настройки миссии.
# Содержит: IP-адреса, координаты, ID маркеров, параметры VLM/YOLO, пороги и т.д.

# === Подключение к дрону ===
DRONE_IP = "192.168.1.37"
DRONE_USER = "sverk"
DRONE_PASSWORD = "sverk"

# === Подключение к роверу ===
ROVER_IP = "192.168.1.201"
ROVER_USER = "pi"
ROVER_PASSWORD = "raspberry"
ROVER_API_URL = "http://192.168.1.201:8767"

# === ID ArUco-маркеров ===
ROVER_ARUCO_ID = None   # ID маркера на ровере (будет задан)
ENEMY_ARUCO_ID = None   # ID маркера врага (будет задан)

# === YOLO ===
YOLO_MODEL_PATH = "models/bear.pt"
YOLO_CLASS_NAME = "bear"
YOLO_CONFIDENCE = 0.5

# === VLM ===
VLM_API_KEY = None      # будет задан
VLM_API_BASE = "https://ai.sverk.tech/v1"
VLM_MODEL = "gemma4-vlm"