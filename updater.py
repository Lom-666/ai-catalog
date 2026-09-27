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

def fetch_models_dev():
    """Забираем качественные, отфильтрованные модели из models.dev без мусора"""
    print("🌐 Загружаю каталог из models.dev...")
    try:
        res = requests.get("https://models.dev/catalog.json", timeout=20)
        if res.status_code == 200:
            data = res.json()
            models_list = []
            providers = data if isinstance(data, list) else data.get("providers", {})
            
            # Чёрный список технических хостингов, чтобы не захламлять ленту однотипными версиями
            blacklisted_providers = ["deep infra", "cloudflare", "anyscale", "baseten", "together"]

            for provider_key, provider_info in (providers.items() if isinstance(providers, dict) else enumerate(providers)):
                p_name = provider_info.get("name", str(provider_key))
                
                if any(b in p_name.lower() for b in blacklisted_providers):
                    continue

                models = provider_info.get("models", {})
                added_from_this_provider = 0

                for model_key, model_info in models.items():
                    m_name = model_info.get("name", model_key)
                    
                    models_list.append({
                        "name": f"{p_name}: {m_name}",
                        "cat": "code" if "code" in m_name.lower() or "coder" in m_name.lower() else "chat",
                        "freeVerdict": f"Популярная модель {m_name} от создателя {p_name}. Актуальные технические спецификации из открытого реестра.",
                        "card": False,
                        "watermark": False,
                        "reset": "Безлимит",
                        "hasFree": True,
                        "url": "https://models.dev",
                        "search": f"{p_name} {m_name} open source ai"
                    })
                    
                    added_from_this_provider += 1
                    if added_from_this_provider >= 2:  # Строго не больше 2 моделей от одного бренда
                        break

            print(f"📦 Отобрано качественных моделей с models.dev: {len(models_list)}")
            return models_list
    except Exception as e:
        print(f"⚠️ Не удалось подгрузить models.dev: {e}")
    return []

def main():
    if not os.path.exists("targets.txt"):
        print("Файл targets.txt не найден!")
        return

    # 1. Читаем твои главные топовые сервисы из targets.txt
    with open("targets.txt", "r", encoding="utf-8") as f:
        target_urls = sorted(list(set([line.strip() for line in f if line.strip()])))

    # Загружаем текущий data.json для сохранения ручных правок и старых данных
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
    print(f"📌 Обрабатываем топ-сервисы из targets.txt ({len(target_urls)} шт)...")

    # Обрабатываем твой золотой фонд
    for url in target_urls:
        text, status_code = scrape_site_text(url)

        if status_code in [404, 410]:
            if url in old_catalog_dict:
                item = old_catalog_dict[url]
                item["error_count"] = item.get("error_count", 0) + 1
                if item["error_count"] < 21:
                    new_catalog.append(item)
            continue

        if text and len(text) > 50:
            ai_data = analyze_with_ai(url, text)
            if ai_data and "name" in ai_data:
                ai_data["url"] = url
                ai_data["error_count"] = 0
                new_catalog.append(ai_data)
                continue

        if url in old_catalog_dict:
            new_catalog.append(old_catalog_dict[url])

    # Добираем чистые модели из models.dev до общего лимита в 100 карточек
    current_count = len(new_catalog)
    max_total_limit = 100
    
    if current_count < max_total_limit:
        extra_needed = max_total_limit - current_count
        models_dev_items = fetch_models_dev()
        
        added_from_dev = 0
        for m in models_dev_items:
            if not any(m["name"].lower() == existing["name"].lower() for existing in new_catalog):
                new_catalog.append(m)
                added_from_dev += 1
                if added_from_dev >= extra_needed:
                    break
        print(f"✨ Добавлено новых моделей из models.dev: {added_from_dev}")

    # Сохраняем итоговый чистый каталог
    if len(new_catalog) > 0:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(new_catalog, f, ensure_ascii=False, indent=2)
        print(f"🎉 Итог: на сайте ровно {len(new_catalog)} карточек без дубликатов и мусора.")
    else:
        print("❌ Ошибка: каталог получился пустым.")

if __name__ == "__main__":
    main()
