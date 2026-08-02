"""
Модуль логирования миссии.

Формат лога соответствует рекомендациям Task.md:
    время, агент, событие, идентификатор, значение

Все логи пишутся на русском языке (где это уместно).
Одновременно выводятся в консоль и сохраняются в файл.
"""

import os
import time
from datetime import datetime, timezone


def _iso_now() -> str:
    """ISO-метка времени с миллисекундами (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
           f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def _now_float() -> float:
    """Время в секундах (Unix timestamp) для вычисления задержек."""
    return time.time()


class MissionLogger:
    """
    Логгер миссии. Поддерживает сквозную нумерацию событий (id).

    Использование:
        log = MissionLogger("logs/mission.log")
        log.info("дрон", "взлёт выполнен", скорость=0.7)
        log.event("дрон", "устойчивая детекция", id=17, доверие=0.94)
    """

    def __init__(self, log_path: str):
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        self._path = log_path
        self._counter = 0           # сквозной идентификатор событий
        self._msg_id_counter = 0    # счётчик сообщений (для рекорда 2)
        self._start_time = _now_float()

    # ── генерация идентификаторов ──────────────────────────────────────────

    def next_id(self) -> int:
        """Следующий сквозной идентификатор события."""
        self._counter += 1
        return self._counter

    def next_msg_id(self) -> int:
        """Следующий идентификатор сообщения (для канала связи)."""
        self._msg_id_counter += 1
        return self._msg_id_counter

    # ── запись строки ───────────────────────────────────────────────────────

    def _write(self, agent: str, event: str, event_id: int | None = None,
               **values) -> None:
        ts = _iso_now()
        id_part = f"id={event_id}" if event_id is not None else "id=-"
        val_parts = " ".join(f"{k}={v}" for k, v in values.items())
        line = f"{ts} {agent} {event} {id_part} {val_parts}".rstrip()
        print(line)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ── общие методы ────────────────────────────────────────────────────────

    def info(self, agent: str, msg: str, **values) -> None:
        """Информационное сообщение (без id)."""
        ts = _iso_now()
        val_parts = " ".join(f"{k}={v}" for k, v in values.items())
        line = f"{ts} {agent} {msg} {val_parts}".rstrip()
        print(line)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def event(self, agent: str, event: str, **values) -> None:
        """Событие с авто-id."""
        eid = self.next_id()
        self._write(agent, event, event_id=eid, **values)

    def start_phase(self, phase_num: int, phase_name: str) -> None:
        """Начало фазы миссии."""
        sep = "=" * 60
        print(f"\n{sep}")
        self.info("координатор", f"ФАЗА {phase_num}: {phase_name}")
        print(sep)

    def end_phase(self, phase_num: int) -> None:
        """Конец фазы миссии."""
        self.info("координатор", f"ФАЗА {phase_num} ЗАВЕРШЕНА")

    # ── события для Рекорда 1: самое быстрое целеуказание ──────────────────

    def drone_detect_stable(self, confidence: float, frames: int,
                            point_name: str) -> int:
        """
        Момент устойчивой детекции на дроне.
        Возвращает id события.
        """
        eid = self.next_id()
        self._write("дрон", "устойчивая_детекция", event_id=eid,
                    доверие=f"{confidence:.2f}", кадров=frames,
                    точка=point_name)
        return eid

    def drone_send_coords(self, target_point: str) -> int:
        """
        Момент отправки координат цели с дрона.
        Возвращает id события.
        """
        eid = self.next_id()
        self._write("дрон", "отправка_координат", event_id=eid,
                    точка_цели=target_point)
        return eid

    def rover_recv_coords(self, target_cell: str) -> int:
        """
        Момент приёма координат на ровере.
        Возвращает id события.
        """
        eid = self.next_id()
        self._write("ровер", "приём_координат", event_id=eid,
                    целевая_клетка=target_cell)
        return eid

    def rover_cmd_move(self, cell: str) -> int:
        """
        Первая команда движения ровера.
        Возвращает id события.
        """
        eid = self.next_id()
        self._write("ровер", "команда_движения", event_id=eid,
                    клетка=cell)
        return eid

    # ── события для Рекорда 2: плотный канал связи ─────────────────────────

    def msg_sent(self, msg_type: str, payload: str = "") -> int:
        """Отправка сообщения. Возвращает id сообщения."""
        mid = self.next_msg_id()
        self._write("канал", "отправка", event_id=mid,
                    тип=msg_type, данные=payload)
        return mid

    def msg_recv(self, msg_type: str, payload: str = "",
                 sent_msg_id: int | None = None) -> int:
        """Приём сообщения. Возвращает id сообщения."""
        if sent_msg_id is not None:
            mid = sent_msg_id
        else:
            mid = self.next_msg_id()
        self._write("канал", "приём", event_id=mid,
                    тип=msg_type, данные=payload)
        return mid

    # ── события для Рекорда 3: быстрый бортовой VLM ────────────────────────

    def drone_vlm_frame_received(self, cycle_num: int) -> int:
        """
        Метка получения кадра для VLM-инференса.
        Возвращает id события.
        """
        eid = self.next_id()
        self._write("дрон", "vlm_получен_кадр", event_id=eid,
                    цикл=cycle_num)
        return eid

    def drone_vlm_result_ready(self, cycle_num: int, latency_ms: float,
                               result: str) -> int:
        """
        Метка готовности результата VLM-инференса.
        Возвращает id события.
        """
        eid = self.next_id()
        self._write("дрон", "vlm_результат_готов", event_id=eid,
                    цикл=cycle_num, задержка_мс=f"{latency_ms:.0f}",
                    результат=result)
        return eid

    # ── события LED-индикации ───────────────────────────────────────────────

    def drone_led_on(self, color: str, duration: float) -> None:
        """Включение LED-индикации."""
        self.event("дрон", f"led_{color}", цвет=color,
                   длительность_сек=f"{duration:.1f}")

    # ── события посадки / ArUco ─────────────────────────────────────────────

    def drone_landing_start(self, marker_id: int) -> None:
        """Начало процедуры посадки на ArUco-метку."""
        self.event("дрон", "начало_посадки_aruco", marker_id=marker_id)

    def drone_landing_ok(self, marker_id: int) -> None:
        """Успешная посадка на ArUco-метку."""
        self.event("дрон", "посадка_успешно", marker_id=marker_id)

    # ── события ровера ──────────────────────────────────────────────────────

    def rover_start_mission(self, target_x: int, target_y: int) -> None:
        """Запуск миссии ровера."""
        self.event("ровер", "старт_миссии",
                   цель=f"({target_x},{target_y})")

    def rover_arrived(self, cell: str) -> None:
        """Ровер прибыл в клетку."""
        self.event("ровер", "прибытие", клетка=cell)

    def rover_vlm_found(self, coordinate: str, cell: str) -> None:
        """Ровер нашёл финишную координату через VLM."""
        self.event("ровер", "vlm_нашёл_координату",
                   координата=coordinate, клетка=cell)

    # ── прочее ──────────────────────────────────────────────────────────────

    def finish(self) -> None:
        """Финал миссии."""
        elapsed = _now_float() - self._start_time
        self.info("координатор", "МИССИЯ ЗАВЕРШЕНА",
                  общее_время_сек=f"{elapsed:.1f}",
                  всего_событий=self._counter)