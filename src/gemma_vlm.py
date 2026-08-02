"""
VLM-анализ изображений через API (Gemma4-VLM).
Используется ровером для поиска финишной координаты на листе A4.

Адаптирован из modules/gemma_vlm.py.
"""

import base64
import os
import json
from openai import OpenAI


def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_mime(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return mime_map.get(ext, "image/jpeg")


def analyze_image(image_path: str, prompt: str,
                  api_key: str = None,
                  base_url: str = None,
                  model: str = None) -> str:
    """
    Отправляет изображение на VLM и возвращает текстовый ответ.

    Параметры:
        image_path: путь к файлу изображения
        prompt: текстовый промпт для VLM
        api_key: API-ключ (если None — из конфига)
        base_url: базовый URL API (если None — из конфига)
        model: имя модели (если None — из конфига)
    """
    from config.settings import VLM_API_KEY, VLM_API_BASE, VLM_MODEL

    client = OpenAI(
        api_key=api_key or VLM_API_KEY,
        base_url=base_url or VLM_API_BASE,
    )

    mime = get_image_mime(image_path)
    b64 = encode_image(image_path)

    response = client.chat.completions.create(
        model=model or VLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64}",
                            "detail": "auto",
                        },
                    },
                ],
            }
        ],
    )

    return response.choices[0].message.content


def try_parse_json_vlm_response(raw: str) -> dict:
    """
    Пытается извлечь JSON из ответа VLM (с очисткой markdown-обёртки).
    Возвращает dict или None при ошибке парсинга.
    """
    clean = raw.strip()
    if clean.startswith("```"):
        parts = clean.split("\n", 1)
        clean = parts[1] if len(parts) > 1 else clean
        if clean.endswith("```"):
            clean = clean[:-3].strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return None