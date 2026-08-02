# Agent_Guide: Программирование дрона и ровера «Сверх»

## Оглавление
1. [Общая архитектура](#1-общая-архитектура)
2. [Программирование дрона](#2-программирование-дрона)
3. [Программирование ровера](#3-программирование-ровера)
4. [Компьютерное зрение](#4-компьютерное-зрение)
5. [VLM-анализ](#5-vlm-анализ)
6. [Шаблоны кода из рабочих примеров](#6-шаблоны-кода-из-рабочих-примеров)
7. [Отладка](#7-отладка)

---
## 1. Общая архитектура

```
Ноутбук управления (Python 3)
    │
    ├── SSH (paramiko) ──────► Дрон (Raspberry Pi, ROS 2 Humble)
    │   Загрузка Python-скрипта → выполнение на борту
    │   Библиотека: sverk_interfaces
    │
    └── SSH (paramiko) ──────► Ровер (Raspberry Pi 5, ROS 2 Jazzy)
        Выполнение команд в терминале ровера
        HTTP API: rover_control_client.py (порт 8767)
        MCP API: JSON-RPC (порт 8766)
```

**Ключевой принцип:** дрон программируется через отправку Python-скрипта по SSH, ровер — через выполнение shell-команд по SSH (с использованием `rover_control_client.py` или прямых ROS 2 команд).

---

## 2. Программирование дрона

### 2.1. Подключение к дрону

Дрон «Сверх» работает на ROS 2 Humble, PX4, с бортовым компьютером на Raspberry Pi.

```python
import paramiko

DRONE_IP = "192.168.1.37"
DRONE_USER = "sverk"
DRONE_PASSWORD = "sverk"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=DRONE_IP, username=DRONE_USER, password=DRONE_PASSWORD, timeout=30)
```

### 2.2. Отправка скрипта на дрон

Рабочий паттерн из примеров (`fly_photo_land_pw.py`):

```python
# 1. Загружаем скрипт на дрон через SFTP
sftp = ssh.open_sftp()
remote_script = "/tmp/_mission.py"
with sftp.open(remote_script, "w") as f:
    f.write(onboard_script_code)   # строка с Python-кодом
sftp.close()

# 2. Запускаем скрипт на дроне
stdin, stdout, stderr = ssh.exec_command(f"python3 {remote_script}")
out = stdout.read().decode()
err = stderr.read().decode()

# 3. После выполнения — удаляем скрипт
sftp = ssh.open_sftp()
sftp.remove(remote_script)
sftp.close()
```

### 2.3. Библиотека sverk_interfaces (основные команды)

На дроне код использует библиотеку `sverk_interfaces`. Инициализация:

```python
import sverk_interfaces
drone = sverk_interfaces.init(Nodename="my_program")
```

#### Полёт

```python
# Взлёт на 1.7 м вверх относительно корпуса (auto_arm=True — сам заармит)
drone.control.navigate(x=0.0, y=0.0, z=1.7, yaw=0.0, speed=0.5,
                       frame_id="body", auto_arm=True)

# Полёт в точку в мировой системе координат (ArUco map)
drone.control.navigate(x=2.0, y=1.0, z=1.7, yaw=0.0, speed=0.5,
                       frame_id="map", auto_arm=False)

# Полёт с ожиданием прибытия (допуск 0.25 м, таймаут 30 с)
drone.control.navigate_wait(x=2.0, y=1.0, z=1.7, yaw=0.0, speed=0.5,
                            frame_id="map", auto_arm=False,
                            tolerance=0.25, timeout=30.0)

# Посадка
drone.control.land()

# Изменить только высоту
drone.control.set_altitude(z=2.0, frame_id="terrain")
```

**Системы координат (frame_id):**
| frame_id | Описание |
|---|---|
| `body` | Относительно корпуса (x — вперёд, y — влево, z — вверх) |
| `map` | Мировая система координат |
| `aruco_map` | Система координат ArUco-карты |
| `terrain` | Высота над поверхностью |

#### Телеметрия

```python
t = drone.control.get_telemetry(frame_id="aruco_map")
# t.x, t.y, t.z — координаты (метры)
# t.yaw — курс (радианы)
# t.vx, t.vy, t.vz — скорости (м/с)
# t.armed — запущены ли моторы
# t.mode — режим полёта (OFFBOARD, POSITION, LAND...)
# t.voltage — напряжение аккумулятора
# t.connected — связь с PX4
```

#### LED-лента

```python
if drone.led:
    drone.led.set_effect("fill", r=255, g=0, b=0)     # красный
    drone.led.set_effect("blink", r=0, g=255, b=0)     # зелёный мигающий
    drone.led.set_effect("rainbow")                     # радуга
    drone.led.set_leds([(0, 255, 0, 0), (1, 0, 255, 0)])  # отдельные LED
```

#### Завершение работы

```python
drone.close()  # всегда в finally
```

### 2.4. Безопасность и аварийные команды

```python
drone.fcu.disarm()          # штатное выключение моторов (только на земле)
drone.fcu.force_disarm()    # принудительное (можно в воздухе)
drone.fcu.kill_switch()     # мгновенная остановка всех моторов
```

---

## 3. Программирование ровера

### 3.1. Подключение к роверу

Ровер «Сверх» — mecanum-платформа на Raspberry Pi 5, ROS 2 Jazzy.

```python
import paramiko

ROVER_IP = "192.168.1.201"
ROVER_USER = "pi"
ROVER_PASSWORD = "raspberry"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=ROVER_IP, username=ROVER_USER, password=ROVER_PASSWORD, timeout=30)
```

### 3.2. Управление через rover_control_client.py (рабочий метод из примеров)

Примеры (`mission3_zachet.py`) используют утилиту `rover_control_client.py` через SSH:

```python
URL = "http://192.168.1.201:8767"
CLIENT = "tools/rover_control_client.py"

commands = [
    "cd sverk_rover",
    "source install/setup.zsh",

    # Проверить статус поля
    f'python3 "{CLIENT}" --url "{URL}" field-status',

    # Узнать координаты клетки (x, y)
    f'python3 "{CLIENT}" --url "{URL}" cell {x} {y}',

    # Задать начальную позицию (ровер физически стоит в этой клетке)
    f'python3 "{CLIENT}" --url "{URL}" initial-cell {x} {y} --yaw 0',

    # Снять программный STOP
    f'python3 "{CLIENT}" --url "{URL}" clear',

    # Движение в клетку (с заменой предыдущей цели)
    f'python3 "{CLIENT}" --url "{URL}" goal-cell {x} {y} --replace',

    # Аварийная остановка
    f'python3 "{CLIENT}" --url "{URL}" stop --reason emergency',
]

full_command = " && ".join(commands)
stdin, stdout, stderr = ssh.exec_command(full_command)
```

**Доступные команды rover_control_client.py:**
| Команда | Назначение |
|---|---|
| `field-status` | Статус поля и сетки |
| `cell X Y` | Координаты центра клетки |
| `initial-cell X Y --yaw ANGLE` | Задать начальную позицию |
| `goal-cell X Y --replace` | Движение в клетку |
| `clear` | Снять STOP |
| `stop --reason TEXT` | Аварийная остановка |
| `state` | Текущее состояние ровера |

**Система координат ровера:**
- Поле 6×6 клеток
- Столбцы слева направо по +X: 1..6
- Строки снизу вверх по +Y: 1..6
- Клетка (1,1) — нижняя левая
- Клетка (6,6) — верхняя правая
- `yaw`: 0 — вдоль +Y, 90 — вдоль +X, 180 — вдоль −Y, −90 — вдоль −X

### 3.3. Управление через MCP API (порт 8766)

Ровер также имеет MCP JSON-RPC сервер на порту 8766:

```bash
# Проверка статуса
curl -s http://ROVER_IP:8766/mcp -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

# Список инструментов
curl -s http://ROVER_IP:8766/mcp -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

# Вызов инструмента
curl -s http://ROVER_IP:8766/mcp -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"TOOL_NAME","arguments":{...}}}'
```

**Основные MCP-инструменты:**

| Инструмент | Параметры | Описание |
|---|---|---|
| `navigate_to_pose` | `x, y, yaw_deg, frame_id, wait_until_done, timeout_s` | Движение к абсолютной точке через Nav2 |
| `drive_relative` | `forward_m, left_m, speed_mps, timeout_s` | Относительное mecanum-движение |
| `turn_relative` | `angle_deg, angular_speed_degps, timeout_s` | Поворот на месте |
| `cancel_navigation` | — | Отмена текущей Nav2-цели |
| `get_robot_pose` | — | Текущие координаты (AMCL или odom) |
| `get_navigation_status` | — | Статус Nav2 |
| `is_navigation_ready` | — | Готовность навигации |
| `get_laser_summary` | — | Данные лидара (спереди/слева/справа/сзади) |
| `set_led_preset` | `preset` | LED-пресет (success, error, warning, navigation...) |
| `set_led_strip` | `enabled, effect, brightness, color` | Управление LED-лентой |
| `blink_led_strip` | `color, times, interval_s` | Мигание лентой |
| `wait` | `duration_s` | Пауза |
| `run_motion_sequence` | `steps[], stop_on_error` | Последовательность действий |
| `get_system_status` | — | Статус всех систем |

### 3.4. Камера ровера и детектор объектов

- **Топик камеры:** `/image_raw` (USB-камера, 1280×720 @ 30 FPS, MJPEG)
- **Детектор:** встроенная фиксированная модель, топики:
  - `/image_processed` — кадр с bounding boxes
  - `/detections` — JSON: `[{"class": "...", "confidence": 0.95, "bbox": [x1,y1,x2,y2]}]`

### 3.5. Веб-интерфейс ровера

- **Порт 8765** — веб-интерфейс (визуализация, управление, карты, терминал)
- Интерфейс позволяет: строить карты, накладывать сетку 6×6, управлять ровером вручную

---

## 4. Компьютерное зрение

### 4.1. Камера дрона

Топик: `/camera_1/image_raw`

```python
# Один кадр
img = drone.image.take_picture(timeout=5.0)  # numpy BGR (OpenCV) или None

# Поток кадров
def on_frame(img):  # img — numpy BGR
    # обработка...
    pass

drone.image.stream(on_frame, duration=10.0)
drone.image.stop_stream()
```

### 4.2. ArUco-навигация дрона

Дрон определяет позицию по ArUco-маркерам на полу:

```python
# Через телеметрию
t = drone.control.get_telemetry(frame_id="aruco_map")
print(f"ArUco позиция: x={t.x:.2f}, y={t.y:.2f}, z={t.z:.2f}")

# Через ROS-топик (сырые данные)
drone.topic.subscribe(PoseWithCovarianceStamped, "/aruco_map/pose_cov", callback)
```

**Детекция ArUco-маркеров на кадре (OpenCV):**

```python
import cv2
import numpy as np

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
parameters = cv2.aruco.DetectorParameters()

corners, ids, rejected = cv2.aruco.detectMarkers(img, aruco_dict, parameters=parameters)
if ids is not None:
    for i, marker_id in enumerate(ids.flatten()):
        if marker_id == ROVER_ARUCO_ID:  # искомый маркер
            # corners[i] — углы маркера на кадре
            center_x = int(np.mean(corners[i][0][:, 0]))
            center_y = int(np.mean(corners[i][0][:, 1]))
            # определяем сектор кадра...
```

**Определение сектора кадра для маркера:**

```python
h, w = img.shape[:2]
cx_frame, cy_frame = w // 2, h // 2  # центр кадра
marker_cx, marker_cy = center_x, center_y

dx = marker_cx - cx_frame
dy = marker_cy - cy_frame

# Сектор определяется по знакам dx, dy и величине смещения
threshold = min(w, h) * 0.15  # порог для "center"

if abs(dx) < threshold and abs(dy) < threshold:
    sector = "center"
else:
    h_dir = ""
    v_dir = ""
    if dy < -threshold: v_dir = "up"
    elif dy > threshold: v_dir = "down"
    if dx < -threshold: h_dir = "left"
    elif dx > threshold: h_dir = "right"
    sector = f"{v_dir}-{h_dir}".strip("-")
```

### 4.3. YOLO-детекция на дроне

```python
from ultralytics import YOLO

model = YOLO("/path/to/model.pt")

frame = drone.image.take_picture(timeout=5.0)
results = model(frame, verbose=False)

for r in results:
    for box in r.boxes:
        cls_id = int(box.cls[0])
        cls_name = model.names[cls_id]
        conf = float(box.conf[0])
        if cls_name == "bear" and conf >= 0.5:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            # объект найден! координаты bbox: (x1, y1, x2, y2)
```

### 4.4. Детекция QR-кодов

```python
codes = drone.image.detect_qr()
for code in codes:
    print(code.data)     # текст
    print(code.center)   # (x, y) в пикселях
```

---

## 5. VLM-анализ

### 5.1. Отправка изображения на VLM

Паттерн из `scan_fire_kletki.py`:

```python
import json, base64, urllib.request

with open(image_path, "rb") as f:
    image_bytes = f.read()
b64 = base64.b64encode(image_bytes).decode()

key = os.environ.get("SVERK_API_KEY") or "sk-..."
base_url = os.environ.get("SVERK_API_BASE") or "https://ai.sverk.tech/v1"

payload = {
    "model": "gemma4-vlm",
    "max_tokens": 200,
    "messages": [
        {"role": "system", "content": "Ты — анализатор изображений..."},
        {"role": "user", "content": [
            {"type": "text", "text": "Проанализируй этот кадр."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]}
    ]
}

req = urllib.request.Request(
    f"{base_url}/chat/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    method="POST"
)

with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read().decode())
    content = data["choices"][0]["message"]["content"]
    result = json.loads(content)  # парсим JSON-ответ VLM
```

### 5.2. Очистка Markdown-разметки из ответа VLM

VLM иногда оборачивает JSON в markdown-блоки:

```python
raw = content.strip()
if raw.startswith("```"):
    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
result = json.loads(raw)
```

---

## 6. Шаблоны кода из рабочих примеров

### 6.1. Структура программы для дрона (запуск по SSH)

```python
# === Ноутбук: host-скрипт ===
import paramiko, sys, os

ONBOARD_SCRIPT = f'''
import time, signal, sys
import sverk_interfaces

def safe_land():
    try:
        drone.control.land()
    except:
        pass

def signal_handler(sig, frame):
    safe_land()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

drone = sverk_interfaces.init(Nodename="mission")
try:
    # ... код миссии ...
finally:
    drone.close()
'''

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=sys.argv[1], username="sverk", password=sys.argv[2], timeout=30)

sftp = ssh.open_sftp()
remote = "/tmp/_mission.py"
with sftp.open(remote, "w") as f:
    f.write(ONBOARD_SCRIPT)
sftp.close()

stdin, stdout, stderr = ssh.exec_command(f"python3 {remote}")
print(stdout.read().decode())

sftp = ssh.open_sftp()
sftp.remove(remote)
sftp.close()
ssh.close()
```

### 6.2. Структура программы для ровера (команды по SSH)

```python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname="192.168.1.201", username="pi", password="raspberry", timeout=30)

commands = [
    "cd sverk_rover",
    "source install/setup.zsh",
    'python3 "tools/rover_control_client.py" --url "http://192.168.1.201:8767" goal-cell 3 4 --replace',
]
full_command = " && ".join(commands)
stdin, stdout, stderr = ssh.exec_command(full_command)
print(stdout.read().decode())
ssh.close()
```

### 6.3. Скачивание файлов с дрона по SFTP

```python
sftp = ssh.open_sftp()
remote_path = "/tmp/photo.jpg"
local_path = "logs/photo.jpg"
sftp.get(remote_path, local_path)
sftp.remove(remote_path)  # удалить после скачивания
sftp.close()
```

### 6.4. Логирование с временными метками

```python
from datetime import datetime, timezone

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line)
    with open("mission.log", "a") as f:
        f.write(line + "\n")
```

---

## 7. Отладка

### 7.1. Проверка дрона

```bash
# Внутри контейнера sverk_ros2 (через SSH):
# Заряд батареи
ros2 topic echo --once /fmu/out/battery_status

# EKF сошёлся? (xy_valid: true, z_valid: true)
ros2 topic echo /fmu/out/vehicle_local_position --qos-reliability best_effort

# ArUco позиция
ros2 topic echo --once /aruco_map/pose_cov

# Частота камеры
ros2 topic hz /camera_1/image_raw

# Список всех топиков
ros2 topic list
```

### 7.2. Проверка ровера

```bash
# Внутри ровера (через SSH):
cd ~/sverk_rover
source install/setup.zsh

# Готовность навигации
python3 tools/rover_control_client.py --url http://192.168.1.201:8767 field-status

# Текущее состояние
python3 tools/rover_control_client.py --url http://192.168.1.201:8767 state

# MCP API
curl -s http://192.168.1.201:8766/mcp -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_system_status","arguments":{}}}'
```

### 7.3. Типовые проблемы

| Проблема | Решение |
|---|---|
| Дрон не армится | EKF не сошёлся — подождать 2-3 мин, проверить `xy_valid`, дождаться `GPS-to-ArUco handoff complete` |
| Ровер не едет | `stop_latched` → `clear`, `nav_not_ready` → `initial-cell` |
| Кадр не получен | Проверить `ros2 topic hz /camera_1/image_raw` |
| VLM возвращает мусор | Очистить markdown-разметку (```json ... ```) |
| SSH connection refused | Проверить IP, ждать загрузки дрона/ровера |

---

## Приложение: Расположение ключевых файлов

| Что | Где |
|---|---|
| Документация дрона | `docs/documentation`, `docs/guide.md` |
| Регламент соревнования | `docs/Vozdushny_dozor.pdf` |
| Документация ровера | `docs/sverk_rover-main/`, `docs/README (1).md` |
| Рабочие примеры (НЕ ИЗМЕНЯТЬ) | `examples/` |
| Конфигурация проекта | `config/settings.py` |
| Скрипты тестов | `tests/` |
| Логи миссии | `logs/` |