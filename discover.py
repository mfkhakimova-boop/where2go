"""
Агент /discover: ищет заведения в интернете под запрос и размечает их
в формате нашей базы. Использует Anthropic API с веб-поиском.

Возвращает список кандидатов (dict в формате db.add_place).
"""
import json
import os
from anthropic import Anthropic
from config import CUISINES, DRINKS, BUDGETS, VIBES, CLAUDE_MODEL

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


PROMPT = """Ты помогаешь компании друзей в Алматы найти заведения под запрос.

Запрос: {query}

Заведения, которые УЖЕ есть в базе (их предлагать НЕ надо): {existing}

Используй веб-поиск: найди до 3 реально существующих заведений в Алматы,
подходящих под запрос. Проверь, что они работают (не закрылись). Изучи
меню и отзывы, чтобы оценки были честными.

Верни СТРОГО JSON-массив без пояснений и markdown-обёртки:

[
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

budget — средний чек в тенге на человека. Оценки drinks: 0 нет, 1 немного,
2 хороший выбор, 3 очень большой выбор. Если под запрос ничего надёжного
не нашлось — верни пустой массив []. Только валидный JSON."""


def discover_places(query: str, existing_names: list[str]) -> list[dict]:
    prompt = PROMPT.format(
        query=query,
        existing=", ".join(existing_names) or "пока пусто",
        cuisines=CUISINES,
        budgets=BUDGETS,
        vibes=VIBES,
    )

    resp = client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 8,
        }],
    )

    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    candidates = json.loads(text[start:end + 1])

    # защита от дублей по имени (без учёта регистра)
    existing_lower = {n.lower().strip() for n in existing_names}
    result = []
    for c in candidates:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        if c["name"].lower().strip() in existing_lower:
            continue
        c.setdefault("url", "")
        result.append(c)
    return result[:3]
