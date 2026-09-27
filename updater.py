import json
import os
import requests
from openai import OpenAI

# Жестко прописываем подключение к OpenRouter
client = OpenAI(
    api_key=os.environ.get("AI_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

def scrape_site_text(url):
    """Обходим защиту от ботов через Jina AI Reader"""
    print(f"🔍 Сканирую: {url} ...")
    try:
        jina_url = f"https://r.jina.ai/{url}"
        res = requests.get(jina_url, timeout=25)
        
        # Если сайт вернул 404 или 410 — он мертв
        if res.status_code in [404, 410]:
            return None, res.status_code

        if res.status_code == 200 and len(res.text) > 50:
            return res.text[:8000], 200
        else:
            # Запасной метод через обычный requests
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res2 = requests.get(url, headers=headers, timeout=15)
            if res2.status_code in [404, 410]:
                return None, res2.status_code
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res2.text, "html.parser")
            text = " ".join(soup.stripped_strings)
            return text[:8000], res2.status_code
    except Exception as e:
        print(f"❌ Ошибка сетевого доступа к {url}: {e}")
        return None, 500

def analyze_with_ai(url, page_text):
    """Анализируем текст через нейросеть OpenRouter"""
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

    # Загружаем существующие данные из data.json
    catalog_dict = {}
    if os.path.exists("data.json"):
        try:
            with open("data.json", "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    old_data = json.loads(content)
                    for item in old_data:
                        if isinstance(item, dict) and "url" in item:
                            catalog_dict[item["url"]] = item
        except Exception:
            pass

    successful_updates = 0
    dead_threshold = 21  # 21 день подряд ошибок до удаления

    for url in urls:
        text, status_code = scrape_site_text(url)

        # Проверяем, не умер ли сайт (ошибка 404 или 410)
        if status_code in [404, 410]:
            print(f"⚠️ Внимание: сайт {url} отдаёт код {status_code} (Мёртв).")
            if url in catalog_dict:
                catalog_dict[url]["error_count"] = catalog_dict[url].get("error_count", 0) + 1
                print(f"Счётчик дней смерти для {catalog_dict[url].get('name', url)}: {catalog_dict[url]['error_count']}/{dead_threshold}")
                
                if catalog_dict[url]["error_count"] >= dead_threshold:
                    print(f"🗑️ Удаляем сервис {catalog_dict[url].get('name', url)}, так как он недоступен уже 3 недели.")
                    del catalog_dict[url]
            continue

        # Если сайт живой — парсим и обновляем
        if text and len(text) > 50:
            ai_data = analyze_with_ai(url, text)
            if ai_data and "name" in ai_data:
                ai_data["url"] = url
                ai_data["error_count"] = 0  
                catalog_dict[url] = ai_data
                successful_updates += 1
                print(f"✅ Успешно обновлен: {ai_data['name']}")
            else:
                print(f"⚠️ Нейросеть не смогла обработать ответ для {url}")
        else:
            print(f"⚠️ Не удалось получить текст с {url}, оставляем старые данные.")

    final_catalog = list(catalog_dict.values())

    if len(final_catalog) > 0:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(final_catalog, f, ensure_ascii=False, indent=2)
        print(f"🎉 Готово! Всего активных сервисов: {len(final_catalog)}. Обновлено: {successful_updates}.")
    else:
        print("❌ Каталог пуст, файл data.json не перезаписан.")

if __name__ == "__main__":
    main()
