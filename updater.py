import json
import os
import requests
from openai import OpenAI

# Подключаемся к нейросети (OpenRouter или OpenAI)
client = OpenAI(
    api_key=os.environ.get("AI_API_KEY"),
    base_url=os.environ.get("AI_BASE_URL", "https://api.openai.com/v1"),
)

def scrape_site_text(url):
    """Обходим защиту от ботов через Jina AI Reader"""
    print(f"🔍 Сканирую: {url} ...")
    try:
        # Секретное оружие: r.jina.ai обходит Cloudflare и возвращает чистый текст
        jina_url = f"https://r.jina.ai/{url}"
        res = requests.get(jina_url, timeout=25)
        
        if res.status_code == 200 and len(res.text) > 50:
            return res.text[:8000] # Берем 8000 символов, чтобы сэкономить токены
        else:
            print(f"⚠️ Защита не пустила на {url}. Пробуем запасной метод...")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res2 = requests.get(url, headers=headers, timeout=15)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res2.text, "html.parser")
            text = " ".join(soup.stripped_strings)
            return text[:8000]
    except Exception as e:
        print(f"❌ Ошибка доступа к {url}: {e}")
        return None

def analyze_with_ai(url, page_text):
    """Скармливаем текст нейросети для извлечения лимитов"""
    prompt = f"""
Проанализируй текст сайта {url}:
{page_text}

Верни строго JSON со следующей структурой:
{{
  "name": "Название сервиса",
  "cat": "Строго одно из: chat, image, video, code, audio",
  "freeVerdict": "На русском языке, 1-2 предложения: сколько точно дают бесплатных попыток, кредитов или минут.",
  "card": false,
  "watermark": false,
  "reset": "Строго одно из: Ежедневно, Ежемесячно, Разово, Безлимит, Нет",
  "hasFree": true,
  "search": "ключевые слова для поиска на английском и русском"
}}
"""
    try:
        response = client.chat.completions.create(
            # ВАЖНО: Если используешь OpenRouter, оставь "openai/gpt-4o-mini" или "google/gemini-2.5-flash"
            model="openai/gpt-4o-mini", 
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ Ошибка нейросети для {url}: {e}")
        return None

def main():
    if not os.path.exists("targets.txt"):
        print("Файл targets.txt не найден!")
        return

    with open("targets.txt", "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    # 1. Загружаем СТАРЫЕ данные, чтобы не удалять то, что работает
    catalog_dict = {}
    if os.path.exists("data.json"):
        try:
            with open("data.json", "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    old_data = json.loads(content)
                    # Собираем в словарь по URL
                    for item in old_data:
                        if isinstance(item, dict) and "url" in item:
                            catalog_dict[item["url"]] = item
        except Exception:
            pass

    successful_updates = 0

    # 2. Обходим сайты и обновляем данные
    for url in urls:
        text = scrape_site_text(url)
        if text and len(text) > 50:
            ai_data = analyze_with_ai(url, text)
            if ai_data and "name" in ai_data:
                ai_data["url"] = url
                catalog_dict[url] = ai_data # Записываем или обновляем сервис
                successful_updates += 1
                print(f"✅ Успех: {ai_data['name']}")
            else:
                print(f"⚠️ Нейросеть не смогла вытащить лимиты для {url}")
        else:
            print(f"⚠️ Сайт {url} заблокировал парсер, оставляем старые данные.")

    final_catalog = list(catalog_dict.values())

    # 3. Сохраняем ТОЛЬКО если есть данные (защита от пустого файла)
    if len(final_catalog) > 0:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(final_catalog, f, ensure_ascii=False, indent=2)
        print(f"🎉 Готово! Всего сервисов: {len(final_catalog)}. Обновлено сейчас: {successful_updates}.")
    else:
        print("❌ Не удалось собрать данные ни с одного сайта. Защита сработала: файл data.json не перезаписан.")

if __name__ == "__main__":
    main()
