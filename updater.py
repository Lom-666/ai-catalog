import json
import os
import requests
from openai import OpenAI

# Подключаемся через OpenRouter
client = OpenAI(
    api_key=os.environ.get("AI_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

def scrape_site_text(url):
    """Скачиваем текст сайта через Jina AI с защитой от сбоев"""
    print(f"🔍 Сканирую: {url} ...")
    try:
        jina_url = f"https://r.jina.ai/{url}"
        res = requests.get(jina_url, timeout=25)
        
        if res.status_code in [404, 410]:
            return None, res.status_code

        if res.status_code == 200 and len(res.text) > 50:
            return res.text[:8000], 200
        else:
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
    """Анализируем текст через нейросеть"""
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

    # Читаем актуальный список ссылок из targets.txt (убираем дубли, если они там случайно были)
    with open("targets.txt", "r", encoding="utf-8") as f:
        target_urls = sorted(list(set([line.strip() for line in f if line.strip()])))

    # Загружаем текущий data.json, чтобы сохранить старые описания (и ручные правки)
    old_catalog_dict = {}
    if os.path.exists("data.json"):
        try:
            with open("data.json", "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    old_data = json.loads(content)
                    for item in old_data:
                        if isinstance(item, dict) and "url" in item:
                            old_catalog_dict[item["url"]] = item
        except Exception:
            pass

    new_catalog = []
    successful_updates = 0
    dead_threshold = 21

    print(f"📌 Всего ссылок в targets.txt для обработки: {len(target_urls)}")

    for url in target_urls:
        text, status_code = scrape_site_text(url)

        # Если сайт физически умер (404/410)
        if status_code in [404, 410]:
            print(f"⚠️ Сайт {url} мёртв ({status_code}).")
            if url in old_catalog_dict:
                item = old_catalog_dict[url]
                item["error_count"] = item.get("error_count", 0) + 1
                if item["error_count"] < dead_threshold:
                    new_catalog.append(item) # Держим в каталоге до истечения срока
                    print(f"⏳ Ссылка временно оставлена (смерть {item['error_count']}/{dead_threshold})")
                else:
                    print(f"🗑️ Удален окончательно из-за долгого отсутствия.")
            continue

        # Если сайт живой — пытаемся обновить через ИИ
        if text and len(text) > 50:
            ai_data = analyze_with_ai(url, text)
            if ai_data and "name" in ai_data:
                ai_data["url"] = url
                ai_data["error_count"] = 0
                new_catalog.append(ai_data)
                successful_updates += 1
                print(f"✅ Успешно обновлен: {ai_data['name']}")
                continue

        # Если нейросеть не смогла ответить, но у нас уже были данные по этому URL — берем их со старого каталога
        if url in old_catalog_dict:
            print(f"🔄 Оставляем старые данные для {url} (не удалось обновить текст).")
            new_catalog.append(old_catalog_dict[url])
        else:
            # Если это вообще новый сайт и спарсить не удалось — создаем заглушку, чтобы карточка была
            print(f"⚠️ Не удалось проанализировать новый сайт {url}, добавляем базовую заглушку.")
            new_catalog.append({
                "name": url.replace("https://", "").replace("http://", "").split("/")[0],
                "cat": "chat",
                "freeVerdict": "Информация уточняется. Сервис добавлен в каталог.",
                "card": False,
                "watermark": False,
                "reset": "Нет",
                "hasFree": True,
                "url": url,
                "error_count": 0
            })

    # Сохраняем итоговый чистый каталог строго по списку targets.txt
    if len(new_catalog) > 0:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(new_catalog, f, ensure_ascii=False, indent=2)
        print(f"🎉 Итог: в каталоге ровно {len(new_catalog)} записей. Успешно обновлено: {successful_updates}.")
    else:
        print("❌ Ошибка: каталог получился пустым, файл не перезаписан.")

if __name__ == "__main__":
    main()
