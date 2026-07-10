"""
Агент /discover: ищет заведения в интернете под запрос и размечает их
в формате нашей базы. Использует Anthropic API с веб-поиском.

Возвращает список кандидатов (dict в формате db.add_place).
"""
import json
import os
from anthropic import Anthropic
from config import (
    CUISINES, DRINKS, BUDGETS, VIBES, CLAUDE_MODEL,
    DISCOVER_MAX_SEARCHES, DISCOVER_MAX_PLACES,
)

_client = None


def client() -> Anthropic:
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "Не задана переменная ANTHROPIC_API_KEY — "
                "добавь ключ в Variables на Railway."
            )
        _client = Anthropic(api_key=key)
    return _client


PROMPT = """Ты помогаешь компании друзей выбрать заведение. Они пишут
свободной фразой, например «хочу жестко затусить на рэйве в Берлине»
или «винный бар с закусками».

Запрос: {query}

Сначала определи ГОРОД из запроса. Если город в запросе не упомянут —
город {default_city}.

Заведения, которые УЖЕ есть в базе (их предлагать НЕ надо): {existing}

Используй веб-поиск ЭКОНОМНО (максимум {max_searches} запроса — лучше один
широкий, чем несколько узких): найди до {max_places} реально существующих
заведений в определённом городе, подходящих под суть запроса. Проверь,
что они работают (не закрылись). Оценки давай по найденному, без лишних
уточняющих поисков.

Верни СТРОГО JSON-объект без пояснений и markdown-обёртки:

{{
  "city": "определённый город",
  "places": [
    {{
      "name": "название",
      "district": "район или пересечение улиц",
      "cuisines": [подмножество из {cuisines}],
      "drinks": {{"вино": 0-3, "пиво": 0-3, "коктейли": 0-3, "крафт": 0-3, "без алкоголя": 0-3}},
      "budget": одно из {budgets},
      "vibes": [подмножество из {vibes}],
      "busy": "пара слов о загруженности, если известно, иначе пустая строка",
      "summary": "2-3 предложения СВОИМИ словами: чем место хорошо, что попробовать. Не копируй чужие тексты.",
      "confidence": "high или low — насколько уверен, что данные актуальны"
    }}
  ]
}}

budget — средний чек на человека в категориях (тенге); для городов вне
Казахстана переведи местные цены в тенге примерно и подбери категорию.
Оценки drinks: 0 нет, 1 немного,
2 хороший выбор, 3 очень большой выбор. Если под запрос ничего надёжного
не нашлось — верни {{"city": "...", "places": []}}. Только валидный JSON."""


def discover_places(query: str, existing_names: list[str], default_city: str = "Алматы") -> tuple[str, list[dict]]:
    """Возвращает (город, список кандидатов). Город агент определяет из фразы."""
    prompt = PROMPT.format(
        query=query,
        existing=", ".join(existing_names) or "пока пусто",
        cuisines=CUISINES,
        budgets=BUDGETS,
        vibes=VIBES,
        max_searches=DISCOVER_MAX_SEARCHES,
        max_places=DISCOVER_MAX_PLACES,
        default_city=default_city,
    )

    resp = client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt}],
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": DISCOVER_MAX_SEARCHES,
        }],
    )

    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return default_city, []
    data = json.loads(text[start:end + 1])

    city = (data.get("city") or default_city).strip()
    candidates = data.get("places", [])

    # защита от дублей по имени (без учёта регистра)
    existing_lower = {n.lower().strip() for n in existing_names}
    result = []
    for c in candidates:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        if c["name"].lower().strip() in existing_lower:
            continue
        c.setdefault("url", "")
        c["city"] = city
        result.append(c)
    return city, result[:DISCOVER_MAX_PLACES]
