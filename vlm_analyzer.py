"""
Модуль VLM-анализатора кадров БПЛА «Сверх»
Выполняет визуально-языковой анализ (Vision Language Model Gemma) снимков
с курсовой камеры БПЛА через REST API.
"""

import json
import logging
import urllib.request
import urllib.error
import config

logger = logging.getLogger("VLMAnalyzer")

def analyze_image_b64(image_b64: str, prompt: str = "Идентифицировать целевой объект и вернуть его координаты ячейки.") -> dict:
    """
    Отправляет изображение в формате Base64 PNG/JPEG на VLM эндпоинт.
    Возвращает разобранный результат анализа.
    """
    api_url = f"{config.VLM_API_BASE.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.VLM_API_KEY}"
    }

    payload = {
        "model": config.VLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        }
                    }
                ]
            }
        ],
        "temperature": 0.1,
        "max_tokens": 300
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(api_url, data=data_bytes, headers=headers, method="POST")
        logger.info(f"Запрос к VLM API ({api_url}) модель: {config.VLM_MODEL}...")
        
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8")
                res_json = json.loads(body)
                content = res_json["choices"][0]["message"]["content"]
                logger.info(f"Ответ VLM анализатора: {content}")
                
                target_found = config.YOLO_TARGET_CLASS.lower() in content.lower() or "bear" in content.lower() or "цель" in content.lower() or "медведь" in content.lower()
                return {
                    "success": True,
                    "target_detected": target_found,
                    "description": content,
                    "raw_response": res_json
                }
            else:
                logger.error(f"VLM API вернул HTTP статус {resp.status}")
                return {"success": False, "error": f"HTTP {resp.status}"}
    except Exception as e:
        logger.error(f"Ошибка вызова VLM API: {e}")
        return {"success": False, "error": str(e)}
