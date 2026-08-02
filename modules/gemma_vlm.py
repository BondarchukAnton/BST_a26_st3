import base64
import os
import sys
from openai import OpenAI

API_KEY = "sk-jkx31e2PLKxCpjOynEwyxA"
BASE_URL = "https://ai.sverk.tech/v1"
MODEL = "gemma4-vlm"


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


def analyze_image(image_path: str, prompt: str) -> str:
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    mime = get_image_mime(image_path)
    b64 = encode_image(image_path)

    response = client.chat.completions.create(
        model=MODEL,
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


def main():
    # if len(sys.argv) < 1:
    #     print("Usage: python gemma_vlm.py <image_path> [prompt]")
    #     print("Example: python gemma_vlm.py photo.jpg \"Что на этом фото?\"")
    #     sys.exit(1)

    # image_path = sys.argv[1]
    # prompt = sys.argv[2] if len(sys.argv) > 2 else "Опиши, что изображено на этой картинке."
    image_path = r"D:\arhipelag\gemochka\gemm.jpg"
    prompt = (
        "Проанализируй изображение. Найди белый лист бумаги с надписью. "
        "На листе должна быть указана координата финишной клетки полигона (буква от A до F и цифра от 1 до 6, например A6, B6, F3). "
        "Если координата видна на белом листе, верни СТРОГО JSON вида: {\"finish_point\": true, \"coordinate\": \"B6\"}. "
        "Если белого листа или координаты на нем нет, верни: {\"finish_point\": false, \"coordinate\": null}."
    )

    if not os.path.exists(image_path):
        print(f"Ошибка: файл '{image_path}' не найден.")
        sys.exit(1)

    print(f"Анализирую: {image_path}")
    print(f"Промпт: {prompt}")
    print("-" * 50)

    try:
        result = analyze_image(image_path, prompt)
        print(result)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()