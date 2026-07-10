"""
База знаний заведений в Postgres (Supabase).

Интерфейс функций тот же, что был у SQLite-версии, поэтому bot.py менять не нужно.
Подключение берётся из переменной окружения DATABASE_URL (её даёт Supabase).

Если DATABASE_URL не задана — падаем с понятной ошибкой, чтобы сразу было ясно,
что забыли прописать переменную на Render.
"""
import os
import json
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL")


def _connect():
    if not DATABASE_URL:
        raise RuntimeError(
            "Не задана переменная окружения DATABASE_URL. "
            "Впиши строку подключения из Supabase в настройки Render."
        )
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with _connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS places (
                id        SERIAL PRIMARY KEY,
                name      TEXT NOT NULL,
                url       TEXT,
                district  TEXT,
                cuisines  JSONB,
                drinks    JSONB,
                budget    TEXT,
                vibes     JSONB,
                busy      TEXT,
                summary   TEXT,
                added_by  TEXT
            )
        """)
        # миграция: колонка city (существующим местам проставится Алматы)
        con.execute(
            "ALTER TABLE places ADD COLUMN IF NOT EXISTS city TEXT DEFAULT 'Алматы'"
        )
        con.execute("UPDATE places SET city = 'Алматы' WHERE city IS NULL")
        con.commit()


def add_place(data: dict) -> int:
    with _connect() as con:
        cur = con.execute(
            """INSERT INTO places
               (name, url, district, cuisines, drinks, budget, vibes, busy, summary, added_by, city)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                data.get("name", "Без названия"),
                data.get("url", ""),
                data.get("district", ""),
                json.dumps(data.get("cuisines", []), ensure_ascii=False),
                json.dumps(data.get("drinks", {}), ensure_ascii=False),
                data.get("budget", ""),
                json.dumps(data.get("vibes", []), ensure_ascii=False),
                data.get("busy", ""),
                data.get("summary", ""),
                data.get("added_by", ""),
                (data.get("city") or "Алматы").strip(),
            ),
        )
        place_id = cur.fetchone()["id"]
        con.commit()
        return place_id


def _row_to_dict(r: dict) -> dict:
    # JSONB возвращается уже как объект python, но подстрахуемся для текстового случая
    def load(v, default):
        if v is None:
            return default
        if isinstance(v, (list, dict)):
            return v
        return json.loads(v)

    return {
        "id": r["id"],
        "name": r["name"],
        "url": r["url"],
        "district": r["district"],
        "cuisines": load(r["cuisines"], []),
        "drinks": load(r["drinks"], {}),
        "budget": r["budget"],
        "vibes": load(r["vibes"], []),
        "busy": r["busy"],
        "summary": r["summary"],
        "city": r.get("city") or "Алматы",
    }


def get_cities() -> list[str]:
    """Города, в которых есть хотя бы одно заведение."""
    with _connect() as con:
        rows = con.execute(
            "SELECT DISTINCT city FROM places WHERE city IS NOT NULL ORDER BY city"
        ).fetchall()
        return [r["city"] for r in rows]


def get_all_places() -> list[dict]:
    with _connect() as con:
        rows = con.execute("SELECT * FROM places ORDER BY id").fetchall()
        return [_row_to_dict(r) for r in rows]


def count_places() -> int:
    with _connect() as con:
        return con.execute("SELECT COUNT(*) AS c FROM places").fetchone()["c"]


def delete_place(place_id: int) -> bool:
    with _connect() as con:
        cur = con.execute("DELETE FROM places WHERE id = %s", (place_id,))
        con.commit()
        return cur.rowcount > 0
