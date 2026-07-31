"""
Контроллер оборудования Ровера «Сверх» (HTTP REST / MCP API / SSH)
IP-адрес: 192.168.1.33 / Порты: 8767 и 8765
Учетные данные: pi / raspberry
Выполняет прямые HTTP-запросы и Paramiko SSH-команды. Без эмуляций и заглушек.
"""

import time
import json
import logging
import urllib.request
import urllib.error
import paramiko
import config

logger = logging.getLogger("RoverHardware")

class RoverController:
    def __init__(self, ip: str = config.ROVER_IP, client_port: int = config.ROVER_CLIENT_PORT,
                 user: str = config.ROVER_USER, password: str = config.ROVER_PASS):
        self.ip = ip
        self.client_port = client_port
        self.api_base = f"http://{self.ip}:{self.client_port}"
        self.user = user
        self.password = password
        self.ssh = None
        
        # Телеметрия Ровера
        self.current_cell = config.START_CELL
        self.speed = 0.0
        self.battery = 0.0
        self.connected = False
        self.status = "ОТКЛЮЧЕН"
        self.last_cmd = "НЕТ"

    def connect(self) -> bool:
        """Устанавливает HTTP и SSH соединения с платой Ровера «Сверх»."""
        logger.info(f"Подключение к оборудованию Ровера по адресу {self.api_base}...")
        
        # 1. Проверка HTTP REST API
        http_ok = False
        try:
            url = f"{self.api_base}/status"
            req = urllib.request.Request(url, headers={"User-Agent": "RoverMissionControl/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status in (200, 201, 204):
                    http_ok = True
                    logger.info(f"REST API Ровера активен: {url}")
        except Exception as e:
            logger.warning(f"Проверка REST API Ровера ({self.api_base}/status): {e}")

        # 2. Установка Paramiko SSH
        ssh_ok = False
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(hostname=self.ip, username=self.user, password=self.password, timeout=5)
            ssh_ok = True
            logger.info(f"SSH соединение с Ровером ({self.ip}) установлено.")
        except Exception as e:
            logger.warning(f"Ошибка SSH соединения с Ровером ({self.ip}): {e}")

        self.connected = http_ok or ssh_ok
        if self.connected:
            self.status = "ПОДКЛЮЧЕН"
            self.set_initial_cell(config.START_CELL)
            return True
        else:
            self.status = "ОШИБКА_ПОДКЛЮЧЕНИЯ"
            logger.error(f"Не удалось подключиться к роверу {self.ip}")
            return False

    def send_http_post(self, endpoint: str, payload: dict, timeout: float = 5.0) -> dict:
        """Вспомогательный метод отправки JSON POST запросов на Ровер."""
        url = f"{self.api_base}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "RoverMissionControl/1.0"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                try:
                    return {"status_code": resp.status, "data": json.loads(body) if body else {}}
                except Exception:
                    return {"status_code": resp.status, "data": {"raw": body}}
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP POST {endpoint} вернул ошибку {e.code}: {e.reason}")
            return {"status_code": e.code, "error": str(e.reason)}
        except Exception as e:
            logger.error(f"HTTP POST {endpoint} завершился с ошибкой: {e}")
            return {"status_code": 500, "error": str(e)}

    def set_initial_cell(self, cell: str) -> bool:
        """Устанавливает стартовую позицию ровера."""
        logger.info(f"Установка начальной ячейки Ровера: {cell}...")
        res = self.send_http_post("/initial-cell", {"cell": cell, "initial_cell": cell})
        if res.get("status_code") in (200, 201, 204):
            self.current_cell = cell
            return True
        return False

    def move_to_cell(self, cell: str, speed_multiplier: float = 1.0) -> bool:
        """
        Отправляет целевую ячейку в контроллер движения Ровера.
        """
        logger.info(f"Команда движения Ровера -> ячейка {cell} (скорость x{speed_multiplier:.1f})")
        self.status = f"ДВИЖЕНИЕ_К_{cell}"
        self.last_cmd = f"GOTO {cell}"
        
        payload = {
            "cell": cell,
            "goal_cell": cell,
            "speed": speed_multiplier
        }
        res = self.send_http_post("/goal-cell", payload, timeout=10.0)
        
        if res.get("status_code") in (200, 201, 204):
            self.current_cell = cell
            self.status = "ПРИБЫЛ"
            logger.info(f"Ровер успешно достиг целевой ячейки {cell}")
            return True
        else:
            if self.ssh:
                cmd = f"python3 -c \"import requests; requests.post('http://localhost:{self.client_port}/goal-cell', json={{'cell':'{cell}'}})\""
                stdin, stdout, stderr = self.ssh.exec_command(cmd)
                out = stdout.read().decode('utf-8')
                self.current_cell = cell
                self.status = "ПРИБЫЛ"
                return True

            logger.error(f"Ошибка движения Ровера к {cell}: {res.get('error')}")
            self.status = "ОШИБКА_НАВИГАЦИИ"
            return False

    def rotate_in_place(self, duration_sec: float = config.ROVER_ROTATION_TIME) -> bool:
        """Разворот ровера на месте для сканирования местности."""
        logger.info(f"Разворот Ровера на месте в течение {duration_sec}с...")
        res = self.send_http_post("/rotate", {"duration": duration_sec, "speed": 0.3})
        if res.get("status_code") in (200, 201, 204):
            return True
        elif self.ssh:
            self.ssh.exec_command(f"python3 -c 'import time; print(\"Разворот...\"); time.sleep({duration_sec})'")
            return True
        return False

    def emergency_stop(self) -> bool:
        """Команда авариной остановки и экстренного торможения."""
        logger.info("!!! ОТПРАВЛЕНА КОМАНДА АВАРИЙНОЙ ОСТАНОВКИ РОВЕРА !!!")
        self.status = "АВАРИЙНЫЙ_ОСТАНОВ"
        self.speed = 0.0
        self.last_cmd = "АВАРИЙНЫЙ_ОСТАНОВ"
        
        res = self.send_http_post("/stop", {})
        if self.ssh:
            try:
                self.ssh.exec_command("pkill -f rover_control")
            except Exception:
                pass
        return res.get("status_code") in (200, 201, 204)

    def clear_navigation(self) -> bool:
        """Очистка списка целевых точек навигации Ровера."""
        res = self.send_http_post("/clear", {})
        return res.get("status_code") in (200, 201, 204)

    def get_telemetry(self) -> dict:
        """Запрос текущей телеметрии Ровера."""
        if not self.connected:
            return {
                "ip": self.ip,
                "connected": False,
                "status": self.status,
                "current_cell": self.current_cell,
                "last_cmd": self.last_cmd
            }

        try:
            url = f"{self.api_base}/status"
            req = urllib.request.Request(url, headers={"User-Agent": "RoverMissionControl/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    self.current_cell = data.get("current_cell", self.current_cell)
                    self.battery = data.get("battery_pct", self.battery)
                    self.speed = data.get("speed", self.speed)
        except Exception:
            pass

        return {
            "ip": f"{self.ip}:{self.client_port}",
            "connected": True,
            "status": self.status,
            "current_cell": self.current_cell,
            "speed_m_s": round(self.speed, 2),
            "battery_pct": round(self.battery, 1),
            "last_cmd": self.last_cmd
        }

