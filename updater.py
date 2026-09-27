import json
import os
from bs4 import BeautifulSoup
from openai import OpenAI
import requests

# Ключ API передаётся безопасно через настройки GitHub Secrets
client = OpenAI(
    api_key=os.environ.get("AI_API_KEY"),
    base_url=os.environ.get(
        "AI_BASE_URL", "https://api.openai.com/v1"
    ),  # можно использовать OpenRouter или DeepSeek
)


def scrape_site_text(url):
    """Скачивает текст сайта, обрезая лишний мусор"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        # Удаляем скрипты и стили
        for s in soup(["script", "style", "noscript"]):
            s.decompose()
        text = " ".join(soup.stripped_strings)
        return text[:10000]  # берем первые 10 000 символов страницы
    except Exception as e:
        print(f"Ошибка при скачивании {url}: {e}")
        return None


def analyze_with_ai(url, page_text):
    """Нейросеть анализирует сайт, сама определяет категорию и проверяет лимиты"""
    prompt = f"""
Ты — аналитик ИИ-сервисов. Проанализируй текст официального сайта {url}:
{page_text}

Верни строго JSON со следующей структурой:
{{
  "name": "Название сервиса (например, Kling AI)",
  "cat": "Строго одно из: 'chat' (текст), 'image' (картинки), 'video' (видео), 'code' (код), 'audio' (звук/голос)",
  "freeVerdict": "Кратко на русском языке (1-2 предложения): сколько именно дают бесплатно (картинок, секунд видео, запросов), есть ли водяной знак, есть ли бесплатный тариф вообще",
  "card": true или false (требуется ли ввод банковской карты для бесплатного использования),
  "watermark": true или false (ставится ли логотип/водяной знак на бесплатные генерации),
  "reset": "Строго одно из: 'Ежедневно', 'Ежемесячно', 'Разово', 'Безлимит', 'Нет'",
  "hasFree": true или false (есть ли бесплатный тариф в принципе),
  "search": "Ключевые слова на русском и английском для поиска через пробел"
}}
"""
    try:
        response = client.chat.completions.create(
            model="google/gemini-2.5-flash",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Ошибка нейросети для {url}: {e}")
        return None


def main():
    if not os.path.exists("targets.txt"):
        print("Файл targets.txt не найден!")
        return

    with open("targets.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    catalog = []
    for url in urls:
        print(f"Проверяю: {url}...")
        text = scrape_site_text(url)
        if text:
            ai_data = analyze_with_ai(url, text)
            if ai_data:
                ai_data["url"] = url
                catalog.append(ai_data)
                print(
                    f"-> Успешно: {ai_data['name']} (Категория: {ai_data['cat']})"
                )

    # Сохраняем свежую базу в data.json
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"Готово! Сохранено {len(catalog)} сервисов в data.json.")


if __name__ == "__main__":
    main()
