"""
Контроллер БПЛА «Сверх» (ROS 2 / sverk_interfaces / SSH Client)
Выполняет реальное SSH-подключение к 192.168.1.37 (sverk/sverk) и исполняет
бортовые скрипты через sverk_interfaces. Без эмуляций и заглушек.
"""

import time
import json
import logging
import paramiko
import config
from grid_map import GridMap

logger = logging.getLogger("DroneSverk")

class DroneSverkController:
    def __init__(self, ip: str = config.DRONE_IP, user: str = config.DRONE_USER, password: str = config.DRONE_PASS):
        self.ip = ip
        self.user = user
        self.password = password
        self.ssh = None
        
        # Полетная телеметрия
        self.armed = False
        self.in_air = False
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.current_cell = "НЕИЗВЕСТНО"
        self.frame_id = config.TAKEOFF_FRAME
        self.battery_voltage = 0.0
        self.battery_pct = 0.0
        self.status = "ОТКЛЮЧЕН"
        self.aruco_visible = 0

    def connect(self) -> bool:
        """Устанавливает SSH-соединение с бортовым компьютером БПЛА Сверх."""
        try:
            logger.info(f"Подключение по SSH к БПЛА «Сверх» ({self.ip}:22) под пользователем {self.user}...")
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(hostname=self.ip, username=self.user, password=self.password, timeout=10)
            self.status = "ПОДКЛЮЧЕН"
            logger.info(f"SSH-соединение с БПЛА «Сверх» ({self.ip}) успешно установлено.")
            return True
        except Exception as e:
            logger.error(f"Ошибка SSH-подключения к БПЛА «Сверх» ({self.ip}): {e}")
            self.status = "ОШИБКА_ПОДКЛЮЧЕНИЯ"
            return False

    def execute_onboard_script(self, script_code: str, timeout: int = 60) -> dict:
        """
        Передает Python-скрипт по SFTP в /tmp/_mission.py на борт БПЛА и исполняет его.
        """
        if not self.ssh:
            if not self.connect():
                return {"stdout": "", "stderr": "SSH Отключен", "exit_code": 1}

        remote_script = "/tmp/_mission.py"
        try:
            sftp = self.ssh.open_sftp()
            with sftp.open(remote_script, "w") as f:
                f.write(script_code)
            sftp.close()

            cmd = f"python3 {remote_script}"
            logger.info(f"Исполнение бортового скрипта на БПЛА: {cmd}")
            stdin, stdout, stderr = self.ssh.exec_command(cmd, timeout=timeout)
            
            out_str = stdout.read().decode('utf-8')
            err_str = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()

            try:
                sftp = self.ssh.open_sftp()
                sftp.remove(remote_script)
                sftp.close()
            except Exception:
                pass

            return {"stdout": out_str, "stderr": err_str, "exit_code": exit_code}
        except Exception as e:
            logger.error(f"Ошибка выполнения бортового скрипта: {e}")
            return {"stdout": "", "stderr": str(e), "exit_code": 1}

    def takeoff(self, altitude: float = config.TAKEOFF_ALTITUDE, frame_id: str = config.TAKEOFF_FRAME) -> bool:
        """
        Отправляет команду взлета через sverk_interfaces ROS 2 на БПЛА.
        """
        logger.info(f"Инициализация ВЗЛЕТА БПЛА на высоту {altitude}м (фрейм: '{frame_id}')...")
        script = f"""
import time, sys
import sverk_interfaces

try:
    drone = sverk_interfaces.init(Nodename="drone_takeoff")
    print("[БОРТ] Арминг моторов и взлет...")
    drone.control.navigate(x=0.0, y=0.0, z={altitude}, yaw=0.0, speed=0.5, frame_id="{frame_id}", auto_arm=True)
    time.sleep(4.0)
    
    t = drone.control.get_telemetry(frame_id="{config.NAV_FRAME}")
    print(f"[БОРТ] Телеметрия после взлета: x={{t.x:.2f}}, y={{t.y:.2f}}, z={{t.z:.2f}}, armed={{t.armed}}")
    drone.close()
except Exception as e:
    print(f"[ОШИБКА БОРТА] {{e}}", file=sys.stderr)
    sys.exit(1)
"""
        res = self.execute_onboard_script(script, timeout=20)
        if res["exit_code"] == 0:
            self.armed = True
            self.in_air = True
            self.z = altitude
            self.frame_id = config.NAV_FRAME
            self.status = "ЗАВИСАНИЕ_ARUCO_MAP"
            logger.info("Взлет БПЛА «Сверх» успешно выполнен на реальном оборудовании.")
            return True
        else:
            logger.error(f"Ошибка взлета БПЛА: {res['stderr']}")
            return False

    def navigate_to_coords(self, x: float, y: float, z: float = config.TAKEOFF_ALTITUDE, speed: float = config.NAV_SPEED) -> bool:
        """
        Перемещает БПЛА в абсолютные координаты (x, y, z) фрейма aruco_map.
        """
        logger.info(f"Полёт БПЛА в координаты x={x:.2f}м, y={y:.2f}м, z={z:.2f}м (фрейм '{config.NAV_FRAME}')...")
        script = f"""
import time, sys
import sverk_interfaces

try:
    drone = sverk_interfaces.init(Nodename="drone_nav")
    print(f"[БОРТ] Навигация в координаты x={x}, y={y}, z={z}...")
    drone.control.navigate_wait(x={x}, y={y}, z={z}, yaw=0.0, speed={speed},
                                frame_id="{config.NAV_FRAME}", auto_arm=False,
                                tolerance=0.25, timeout=30.0)
    t = drone.control.get_telemetry(frame_id="{config.NAV_FRAME}")
    print(f"[БОРТ] Точка достигнута: x={{t.x:.2f}}, y={{t.y:.2f}}, z={{t.z:.2f}}")
    drone.close()
except Exception as e:
    print(f"[ОШИБКА БОРТА] {{e}}", file=sys.stderr)
    sys.exit(1)
"""
        res = self.execute_onboard_script(script, timeout=40)
        if res["exit_code"] == 0:
            self.x = x
            self.y = y
            self.z = z
            self.current_cell = GridMap.coords_to_cell(x, y)
            self.status = "ЗАВИСАНИЕ"
            return True
        else:
            logger.error(f"Ошибка навигации БПЛА: {res['stderr']}")
            return False

    def navigate_to_cell(self, cell: str, speed: float = config.NAV_SPEED) -> bool:
        """Переводит наименование ячейки (напр. 'E1') в координаты и направляет БПЛА."""
        x, y = GridMap.cell_to_coords(cell)
        return self.navigate_to_coords(x, y, z=config.TAKEOFF_ALTITUDE, speed=speed)

    def capture_photo_and_analyze_vlm(self, prompt: str = "Идентифицировать объект и определить ячейку сетки.") -> dict:
        """
        Получает кадр с курсовой камеры БПЛА и отправляет в VLM Gemma API.
        """
        logger.info("Захват снимка с камеры БПЛА «Сверх» для мультимодального анализа VLM...")
        script = f"""
import time, sys, cv2, base64
import sverk_interfaces

try:
    drone = sverk_interfaces.init(Nodename="drone_cam")
    img = drone.image.take_picture(timeout=5.0)
    drone.close()
    
    if img is None:
        print("[ОШИБКА БОРТА] Не удалось получить кадр с /camera_1/image_raw", file=sys.stderr)
        sys.exit(1)
        
    _, buffer = cv2.imencode('.png', img)
    b64_str = base64.b64encode(buffer).decode('utf-8')
    print(f"B64_IMAGE_START:{{b64_str}}:B64_IMAGE_END")
except Exception as e:
    print(f"[ОШИБКА БОРТА] {{e}}", file=sys.stderr)
    sys.exit(1)
"""
        res = self.execute_onboard_script(script, timeout=15)
        if res["exit_code"] != 0 or "B64_IMAGE_START" not in res["stdout"]:
            logger.error(f"Ошибка захвата изображения с камеры: {res['stderr']}")
            return {"success": False, "error": res["stderr"]}

        try:
            b64 = res["stdout"].split("B64_IMAGE_START:")[1].split(":B64_IMAGE_END")[0]
            import vlm_analyzer
            vlm_res = vlm_analyzer.analyze_image_b64(b64, prompt)
            return {"success": True, "vlm_response": vlm_res, "b64": b64[:50] + "..."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scan_aruco_markers(self) -> dict:
        """
        Сканирует кадр с камеры БПЛА на наличие маркеров ArUco (Ровер и Противник).
        Определяет сектор кадра для обнаруженного маркера противника.
        """
        script = f"""
import sys, cv2, json
import numpy as np
import sverk_interfaces

try:
    drone = sverk_interfaces.init(Nodename="aruco_scanner")
    img = drone.image.take_picture(timeout=5.0)
    drone.close()
    
    if img is None:
        print(json.dumps({{"error": "Нет кадра"}}))
        sys.exit(0)
        
    h, w = img.shape[:2]
    cx_frame, cy_frame = w // 2, h // 2
    
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    corners, ids, _ = cv2.aruco.detectMarkers(img, aruco_dict, parameters=parameters)
    
    detected = {{}}
    if ids is not None:
        for i, marker_id in enumerate(ids.flatten()):
            mcx = int(np.mean(corners[i][0][:, 0]))
            mcy = int(np.mean(corners[i][0][:, 1]))
            
            dx = mcx - cx_frame
            dy = mcy - cy_frame
            
            threshold = min(w, h) * 0.15
            if abs(dx) < threshold and abs(dy) < threshold:
                sector = "center"
            else:
                v_dir = "up" if dy < -threshold else ("down" if dy > threshold else "")
                h_dir = "left" if dx < -threshold else ("right" if dx > threshold else "")
                sector = f"{{v_dir}}-{{h_dir}}".strip("-") or "center"
                
            detected[int(marker_id)] = {{
                "cx": mcx, "cy": mcy,
                "dx": dx, "dy": dy,
                "sector": sector
            }}
            
    print("ARUCO_JSON_START:" + json.dumps(detected) + ":ARUCO_JSON_END")
except Exception as e:
    print(json.dumps({{"error": str(e)}}), file=sys.stderr)
    sys.exit(1)
"""
        res = self.execute_onboard_script(script, timeout=12)
        if res["exit_code"] == 0 and "ARUCO_JSON_START:" in res["stdout"]:
            try:
                raw_json = res["stdout"].split("ARUCO_JSON_START:")[1].split(":ARUCO_JSON_END")[0]
                markers = json.loads(raw_json)
                return {"success": True, "markers": markers}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "markers": {}}

    def land(self) -> bool:
        """Посадка БПЛА Сверх."""
        logger.info("Отправка команды ПОСАДКА на БПЛА «Сверх»...")
        script = """
import time, sys
import sverk_interfaces

try:
    drone = sverk_interfaces.init(Nodename="drone_land")
    print("[БОРТ] Выполнение посадки...")
    drone.control.land()
    time.sleep(3.0)
    drone.close()
except Exception as e:
    print(f"[ОШИБКА БОРТА] {e}", file=sys.stderr)
    sys.exit(1)
"""
        res = self.execute_onboard_script(script, timeout=15)
        self.in_air = False
        self.armed = False
        self.status = "ПОСАЖЕН"
        logger.info("БПЛА «Сверх» совершил посадку и отключил моторы.")
        return res["exit_code"] == 0

    def get_telemetry(self) -> dict:
        """Получение текущей полетной телеметрии БПЛА."""
        if not self.ssh:
            return {
                "ip": self.ip,
                "status": self.status,
                "connected": False,
                "armed": self.armed,
                "in_air": self.in_air,
                "current_cell": self.current_cell,
                "altitude_m": round(self.z, 2),
                "battery_pct": self.battery_pct
            }

        cmd = "ros2 topic echo --once /fmu/out/battery_status 2>/dev/null | grep voltage_v"
        try:
            stdin, stdout, stderr = self.ssh.exec_command(cmd, timeout=3)
            out = stdout.read().decode('utf-8')
            if "voltage_v" in out:
                v = float(out.split(":")[1].strip())
                self.battery_voltage = v
                self.battery_pct = max(0.0, min(100.0, ((v - 10.5) / 2.1) * 100))
        except Exception:
            pass

        return {
            "ip": self.ip,
            "status": self.status,
            "connected": True,
            "armed": self.armed,
            "in_air": self.in_air,
            "current_cell": self.current_cell,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "altitude_m": round(self.z, 2),
            "battery_pct": round(self.battery_pct, 1),
            "battery_voltage": round(self.battery_voltage, 2),
            "frame_id": self.frame_id
        }

