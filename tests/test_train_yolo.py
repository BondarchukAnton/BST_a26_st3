#!/usr/bin/env python3
"""
Обучение и оптимизация YOLO для быстрого инференса.
Запуск: раскомментируй нужную функцию в блоке if __name__ == "__main__" внизу файла.

Требования:
    pip install ultralytics onnx onnxruntime

Структура датасета (формат YOLO):
    datasets/my_dataset/
    ├── data.yaml          # paths, nc, names
    ├── train/
    │   ├── images/        # .jpg / .png
    │   └── labels/        # .txt (одноимённые с images)
    └── val/
        ├── images/
        └── labels/
"""

import os
from ultralytics import YOLO

# ═══════════════════════════════════════════════════════════════════════════════
# НАСТРОЙКИ — меняй здесь
# ═══════════════════════════════════════════════════════════════════════════════

# Путь к data.yaml твоего датасета
DATASET_YAML = "/home/workerfit/PycharmProjects/datasett3/data.yaml"

# Папка куда сохраняются обученные и экспортированные модели
OUTPUT_DIR = "/home/workerfit/PycharmProjects/datasett3/models"

# Базовая модель. Варианты:
#   yolo11n  — nano   (2.6M параметров, самая быстрая)         ← рекомендую
#   yolo11s  — small  (9.4M)
#   yolo11m  — medium (20M)
#   yolo11l  — large  (25M)
#   yolo11x  — xlarge (57M)
BASE_MODEL = "yolo11n"

# Целевой размер изображения в пикселях.
# Изображение будет сжато так, чтобы бо́льшая сторона стала = IMGSZ,
# а меньшая — пропорционально. Потом дополняется padding до кратного 32.
# Для 360×30 картинки ставь 360.
IMGSZ = 320

# Число эпох обучения. 50–100 обычно хватает.
# Если на валидации метрики перестали расти — early stopping остановит раньше.
EPOCHS = 100

# Размер батча. Уменьши если не хватает видеопамяти (batch=8 или 4).
BATCH = 256

# Устройство: 0 = первая GPU, "cpu" = процессор
DEVICE = 0

# Число потоков загрузки данных (обычно = числу ядер CPU)
WORKERS = 4

# ═══════════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ — раскомментируй нужную в __main__ внизу
# ═══════════════════════════════════════════════════════════════════════════════


def train():
    """
    Обучает YOLO с нуля на твоём датасете.

    Что происходит:
      1. Скачивается предобученная модель (yolo11n.pt)
      2. Запускается дообучение (fine-tuning) на твоих данных
      3. Лучшая модель сохраняется в models/yolo_custom/weights/best.pt

    Пример вывода в конце:
      results:  mAP50=0.95, mAP50-95=0.72, precision=0.93, recall=0.91
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    model = YOLO(f"{BASE_MODEL}.pt")
    print(f"Базовая модель: {BASE_MODEL}")

    model.train(
        data=DATASET_YAML,       # путь к data.yaml
        imgsz=IMGSZ,             # целевой размер (360 → картинка сжимается до 360 по большей стороне)
        epochs=EPOCHS,           # сколько эпох
        batch=BATCH,             # размер батча
        device=DEVICE,           # GPU или CPU
        workers=WORKERS,         # потоки загрузки
        project=OUTPUT_DIR,      # папка для результатов
        name="yolo_custom",      # имя эксперимента
        exist_ok=True,           # перезаписывать если уже есть
        patience=20,             # остановить если 20 эпох без улучшения
        lr0=0.01,                # стартовый learning rate
        lrf=0.01,                # конечный = lr0 * lrf
        cos_lr=True,             # косинусное затухание (плавнее)
        augment=True,            # аугментация (повороты, отражения, яркость)
        rect=True,
        freeze=10,
        # verbose=False,         # раскомментируй чтобы убрать подробный лог
    )

    trained = os.path.join(OUTPUT_DIR, "yolo_custom", "weights", "best.pt")
    print(f"\nГотово! Модель сохранена: {trained}")
    print(f"Проверь скорость: model = YOLO('{trained}')")


def val():
    """
    Валидация — проверяет качество обученной модели на val-выборке.

    Выводит:
      mAP50      — точность при IoU=0.5 (основная метрика)
      mAP50-95   — средняя точность при IoU от 0.5 до 0.95
      precision  — сколько найденных объектов действительно правильные
      recall     — сколько реальных объектов найдено
      speed      — мс на кадр (preprocess + inference + postprocess)
    """
    model_path = _best_pt()
    model = YOLO(model_path)
    metrics = model.val(data=DATASET_YAML, imgsz=IMGSZ, device=DEVICE)
    print(f"\nmAP50={metrics.box.map50:.3f}  mAP50-95={metrics.box.map:.3f}  "
          f"speed={metrics.speed['inference']:.1f}ms")


def export_onnx():
    """
    Экспорт в ONNX (Open Neural Network Exchange).
    Самый универсальный формат — работает на x86, ARM, Raspberry Pi.

    После экспорта использовать ТОЧНО так же:
        model = YOLO("models/yolo_custom/weights/best.onnx")
        results = model(frame)        # ultralytics сам подхватит ONNX Runtime

    Что такое half=True:
      Веса модели хранятся в FP16 (половинная точность) вместо FP32.
      Это даёт: ×1.5–2 прирост скорости на CPU, ×2 меньше памяти.
      Потеря точности: < 0.5% mAP — незаметно.
    """
    model_path = _best_pt()
    model = YOLO(model_path)
    out = model.export(
        format="onnx",
        half=True,           # FP16 — быстрее, меньше памяти
        imgsz=IMGSZ,
        simplify=True,       # упростить граф вычислений (быстрее)
        opset=17,            # версия ONNX (17 = современная, широкая поддержка)
        dynamic=False,       # фиксированный размер входа (быстрее, чем dynamic)
    )
    print(f"\nONNX сохранён: {out}")
    print('Использование: model = YOLO("' + out + '")')


def export_openvino():
    """
    Экспорт в OpenVINO (Intel).
    Лучший выбор если инференс на ноутбуке с Intel CPU.

    Использование:
        model = YOLO("models/yolo_custom/weights/best_openvino_model/")
        results = model(frame)
    """
    model_path = _best_pt()
    model = YOLO(model_path)
    out = model.export(format="openvino", half=True, imgsz=IMGSZ)
    print(f"\nOpenVINO сохранён: {out}")


def export_ncnn():
    """
    Экспорт в NCNN.
    Оптимален для ARM-процессоров (Raspberry Pi, дрон).

    Использование:
        model = YOLO("models/yolo_custom/weights/best_ncnn_model/")
        results = model(frame)

    Требуется: pip install ncnn  (может потребоваться сборка из исходников)
    """
    model_path = _best_pt()
    model = YOLO(model_path)
    out = model.export(format="ncnn", imgsz=IMGSZ, half=True)
    print(f"\nNCNN сохранён: {out}")


def export_tflite_int8():
    """
    Экспорт в TFLite с INT8-квантизацией.
    Максимальная скорость на NPU / Edge TPU.

    INT8: веса и активации сжимаются до 8 бит.
    Прирост скорости: ×3–4 на поддерживаемом железе.
    Потеря точности: 1–3% mAP (нужна калибровка на датасете).

    Использование:
        model = YOLO("models/yolo_custom/weights/best_int8.tflite")
        results = model(frame)
    """
    model_path = _best_pt()
    model = YOLO(model_path)
    out = model.export(
        format="tflite",
        int8=True,               # квантизация в INT8
        data=DATASET_YAML,       # датасет для калибровки квантизации
        imgsz=IMGSZ,
        nms=True,                # встроенный NMS (не нужен отдельно)
    )
    print(f"\nTFLite INT8 сохранён: {out}")


def export_engine_fp16():
    """
    Экспорт в TensorRT FP16 (только для NVIDIA GPU / Jetson).

    Самый быстрый вариант на GPU NVIDIA.
    ВАЖНО: экспортировать нужно НА ЦЕЛЕВОМ УСТРОЙСТВЕ
    (TensorRT-движок привязан к конкретной видеокарте).

    Использование:
        model = YOLO("models/yolo_custom/weights/best_fp16.engine")
        results = model(frame)
    """
    model_path = _best_pt()
    model = YOLO(model_path)
    out = model.export(
        format="engine",
        half=True,               # FP16
        imgsz=IMGSZ,
        device=DEVICE,
        dynamic=False,           # фиксированный вход → быстрее
        batch=1,                 # по 1 кадру
        workspace=4,             # ГБ памяти под сборку
    )
    print(f"\nTensorRT FP16 сохранён: {out}")


def export_onnx_int8():
    model = YOLO(_best_pt())
    out = model.export(
        format="onnx",
        imgsz=IMGSZ,
        int8=True,
        data=DATASET_YAML,  # нужно для калибровки весов
        simplify=True,
        nms=True,           # встроенный NMS экономит время CPU на пост-обработке
    )
    print(f"\nONNX INT8 сохранён: {out}")

def benchmark():
    """
    Сравнивает скорость оригинальной .pt модели и экспортированной .onnx.

    Выводит время инференса в миллисекундах для каждого формата.
    Чем меньше — тем быстрее.
    """
    model_path = _best_pt()
    print("Сравнение скорости инференса:\n")

    # Оригинал
    m = YOLO(model_path)
    metrics = m.val(data=DATASET_YAML, imgsz=IMGSZ, device=DEVICE, verbose=False)
    pt_time = metrics.speed["inference"]
    print(f"  PyTorch (.pt):  {pt_time:.1f} мс/кадр")

    # ONNX
    onnx_path = model_path.replace(".pt", ".onnx")
    if os.path.exists(onnx_path):
        m = YOLO(onnx_path)
        metrics = m.val(data=DATASET_YAML, imgsz=IMGSZ, device=DEVICE, verbose=False)
        onnx_time = metrics.speed["inference"]
        speedup = pt_time / onnx_time if onnx_time > 0 else 0
        print(f"  ONNX    (.onnx): {onnx_time:.1f} мс/кадр  (×{speedup:.1f} быстрее)")
    else:
        print("  ONNX не найден — сначала запусти export_onnx()")


def predict_image():
    """
    Быстрая проверка: прогоняет одно тестовое изображение через модель
    и сохраняет результат с нарисованными рамками в models/prediction.jpg.
    """
    model = YOLO(_best_pt())
    test_img = "test.jpg"  # ← положи тестовую картинку в корень проекта
    results = model(test_img, imgsz=IMGSZ, conf=0.5)
    for r in results:
        r.save(os.path.join(OUTPUT_DIR, "prediction.jpg"))
        print(f"Результат сохранён: {OUTPUT_DIR}/prediction.jpg")
        print(f"Найдено объектов: {len(r.boxes)}")
        for box in r.boxes:
            cls = model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            print(f"  {cls}: {conf:.2f}")


# ── Вспомогательная ──────────────────────────────────────────────────────────

def _best_pt():
    """Возвращает путь к лучшей обученной модели."""
    path = os.path.join(OUTPUT_DIR, "yolo_custom", "weights", "best.pt")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Модель не найдена: {path}\n"
            f"Сначала запусти train()"
        )
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАПУСК — раскомментируй нужную строку и нажми Run
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Шаг 1: обучить модель
    # train()

    # Шаг 2: проверить качество
    # val()

    # Шаг 3: экспортировать в быстрый формат
    # export_onnx()       # универсальный, для любого CPU
    # export_openvino()   # для Intel CPU
    # export_ncnn()       # для ARM / Raspberry Pi
    # export_tflite_int8()# для NPU / Edge TPU
    # export_engine_fp16()# для NVIDIA GPU / Jetson
    export_onnx_int8()

    # Шаг 4: сравнить скорость .pt vs .onnx
    # benchmark()

    # Тест: прогнать одну картинку
    # predict_image()