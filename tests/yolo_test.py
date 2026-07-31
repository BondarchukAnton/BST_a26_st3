#!/usr/bin/env python3
"""
Тестовый скрипт: только работа с камерой и YOLO в реальном времени.
ДРОН НЕ ВЗЛЕТАЕТ И НЕ СОВЕРШАЕТ ДВИЖЕНИЙ.

Запуск:
python3 yolo_camera_test.py
"""

import time
import signal
import sys
import cv2
from ultralytics import YOLO
import sverk_interfaces

# ================= Настройки =================
# Путь к вашей модели (если нет файла bear.pt, можно заменить на "yolov8n.pt" для теста)
YOLO_MODEL_PATH = "/home/sverk/yolo_models/bear.pt"
YOLO_CONFIDENCE = 0.5  # Порог уверенности (0.0 - 1.0)

# Попытаться показать окно с видео (True — окно OpenCV, False — только консоль)
SHOW_WINDOW = True
# =============================================

should_stop = False


def signal_handler(sig, frame):
    global should_stop
    print("\n[SIGNAL] Получен сигнал прерывания (Ctrl+C). Остановка...")
    should_stop = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main():
    global should_stop, SHOW_WINDOW

    print("[INIT] Подключение к sverk_interfaces...")
    drone = sverk_interfaces.init(Nodename="yolo_camera_test")

    print(f"[INIT] Загрузка YOLO-модели из {YOLO_MODEL_PATH}...")
    try:
        yolo_model = YOLO(YOLO_MODEL_PATH)
        print("[INIT] Модель успешно загружена.")
    except Exception as e:
        print(f"[ERROR] Ошибка загрузки модели: {e}")
        print("[HINT] Проверьте путь к файлу весов или укажите 'yolov8n.pt' для проверки.")
        sys.exit(1)

    print("\n--- ЗАПУСК ОБРАБОТКИ КАМЕРЫ ---")
    print("Навигация и моторы отключены. Работаем только с кадрами.")
    print("Для завершения нажмите Ctrl+C (или 'q' в окне видео).\n")

    fps_counter = 0
    fps_timer = time.time()
    current_fps = 0.0

    try:
        while not should_stop:
            loop_start = time.time()

            # 1. Запрос кадра с камеры дрона
            frame = drone.image.take_picture(timeout=1.0)
            if frame is None:
                print("[WARN] Кадр не получен от камеры, повтор...")
                time.sleep(0.05)
                continue

            # 2. Запуск детекции YOLO
            results = yolo_model(frame, conf=YOLO_CONFIDENCE, verbose=False)

            # 3. Сбор информации о найденных объектах для консоли
            detections_info = []
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = yolo_model.names[cls_id]
                    conf = float(box.conf[0])
                    detections_info.append(f"{cls_name} ({conf:.2f})")

            # 4. Расчёт текущего FPS
            fps_counter += 1
            if time.time() - fps_timer >= 1.0:
                current_fps = fps_counter / (time.time() - fps_timer)
                fps_counter = 0
                fps_timer = time.time()

            # 5. Вывод лога в консоль
            det_str = ", ".join(detections_info) if detections_info else "Ничего не найдено"
            print(f"[FPS: {current_fps:4.1f}] Детекции: {det_str}")

            # 6. Отрисовка результатов на видео
            if SHOW_WINDOW:
                # Отрисовываем рамки (bounding boxes), классы и уверенность поверх кадра
                annotated_frame = results[0].plot()

                # Добавляем плашку с текущим FPS
                cv2.putText(
                    annotated_frame,
                    f"FPS: {current_fps:.1f}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 0),
                    2
                )

                try:
                    cv2.imshow("Drone Camera - YOLO Detection", annotated_frame)
                    # waitKey(1) необходим для обновления графического окна OpenCV
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                except Exception:
                    # Если работаем по SSH без GUI/X11, мягко переключаемся в режим консоли
                    print("[INFO] Графический интерфейс недоступен (Headless режим). Вывод продолжается в консоль.")
                    SHOW_WINDOW = False

    except Exception as e:
        print(f"[FATAL ERROR] {e}")
    finally:
        print("\n[CLEANUP] Завершение работы...")
        if SHOW_WINDOW:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        try:
            drone.close()
        except Exception:
            pass
        print("[FINISHED] Скрипт остановлен.")


if __name__ == "__main__":
    main()