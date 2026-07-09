"""
Сопоставление результатов голосования с базой заведений.
На вход — сколько голосов набрал каждый критерий.
На выходе — топ-N заведений с максимальным score.
"""
from config import WEIGHTS, TOP_N


def score_place(place: dict, votes: dict) -> float:
    """
    votes = {
      "cuisine": {"японская": 3, "грузинская": 1, ...},
      "drink":   {"вино": 2, ...},
      "budget":  {"1000–2000": 4, ...},
      "vibe":    {"шумно / компания": 2, ...},
    }
    Число — сколько людей проголосовало за этот вариант.
    """
    score = 0.0

    # Кухня: за каждую совпавшую кухню добавляем голоса * вес
    for cuisine, n in votes.get("cuisine", {}).items():
        if cuisine in place["cuisines"]:
            score += n * WEIGHTS["cuisine"]

    # Напитки: учитываем силу предложения (0..3) заведения
    for drink, n in votes.get("drink", {}).items():
        strength = place["drinks"].get(drink, 0)
        score += n * strength / 3.0 * WEIGHTS["drink"]

    # Бюджет: точное совпадение — полный вес, соседняя категория — половина
    budgets_order = ["до 1000", "1000–2000", "2000–3500", "3500+"]
    for budget, n in votes.get("budget", {}).items():
        if budget == place["budget"]:
            score += n * WEIGHTS["budget"]
        elif budget in budgets_order and place["budget"] in budgets_order:
            dist = abs(budgets_order.index(budget) - budgets_order.index(place["budget"]))
            if dist == 1:
                score += n * WEIGHTS["budget"] * 0.5

    # Атмосфера
    for vibe, n in votes.get("vibe", {}).items():
        if vibe in place["vibes"]:
            score += n * WEIGHTS["vibe"]

    return score


def top_places(places: list[dict], votes: dict, n: int = TOP_N) -> list[tuple[dict, float]]:
    scored = [(p, score_place(p, votes)) for p in places]
    scored = [x for x in scored if x[1] > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:n]
