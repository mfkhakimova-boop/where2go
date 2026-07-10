"""
Парсер строки-разметки для команды /add.

Формат (поля разделены вертикальной чертой |):

  Название | Район | кухни | напитки | чек | атмосфера | краткое описание

Где:
  кухни     — через запятую, из списка CUISINES        (напр. итальянская, паста)
  напитки   — через запятую как напиток:оценка0-3       (напр. вино:3, коктейли:2)
  чек       — одно из BUDGETS                            (напр. 2000–3500)
  атмосфера — через запятую из VIBES                     (напр. тихо / свидание)
  описание  — свободный текст

Пример строки целиком:
  Траттория Пиано | центр | итальянская | вино:3, коктейли:1 | 2000–3500 | тихо / свидание | Домашняя паста и большая карта вин

Незаполненные поля можно оставлять пустыми, но разделители | должны быть на месте.
"""


def parse_add(text: str) -> dict:
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 7:
        raise ValueError(
            "Нужно 7 полей через |:\n"
            "Название | Район | кухни | напитки | чек | атмосфера | описание"
        )

    name, district, cuisines_s, drinks_s, budget, vibes_s, summary = parts[:7]
    city = parts[7].strip() if len(parts) > 7 and parts[7].strip() else "Алматы"

    if not name:
        raise ValueError("У заведения должно быть название (первое поле).")

    cuisines = [c.strip() for c in cuisines_s.split(",") if c.strip()]

    drinks = {}
    for item in drinks_s.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            key, val = item.split(":", 1)
            try:
                drinks[key.strip()] = max(0, min(3, int(val.strip())))
            except ValueError:
                drinks[key.strip()] = 1
        else:
            drinks[item] = 2  # без оценки — считаем «хороший выбор»

    vibes = [v.strip() for v in vibes_s.split(",") if v.strip()]

    return {
        "name": name,
        "district": district,
        "cuisines": cuisines,
        "drinks": drinks,
        "budget": budget,
        "vibes": vibes,
        "busy": "",
        "summary": summary,
        "url": "",
        "city": city,
    }
