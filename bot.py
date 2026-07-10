"""
Where2Go — телеграм-бот для выбора заведения голосованием. Версия без ИИ.

Команды:
  /add <разметка>  — добавить заведение (формат см. /help или в parse.py)
  /list            — показать что есть в базе
  /del <id>        — удалить заведение
  /vote            — запустить голосование по критериям
  /help            — справка

Голосование: бот шлёт сообщение с кнопками по категориям (кухня, алкоголь,
бюджет, атмосфера). Каждый тыкает свои варианты. Кто-то жмёт «Готово» —
бот считает голоса и выдаёт топ-3 из базы.
"""
import asyncio
import logging
import os
from collections import defaultdict

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

import db
import discover
from parse import parse_add
from config import CUISINES, DRINKS, BUDGETS, VIBES, TOP_N
from matcher import top_places

load_dotenv()
logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.environ["TELEGRAM_TOKEN"])
dp = Dispatcher()

# --- Приватность: белый список чатов ---
# В переменной окружения ALLOWED_CHATS перечисли ID чатов через запятую,
# например: -1001234567890, 987654321
# Если переменная пустая или не задана — бот отвечает всем (открытый режим).
_raw_allowed = os.environ.get("ALLOWED_CHATS", "").strip()
ALLOWED_CHATS: set[int] = {
    int(x) for x in _raw_allowed.split(",") if x.strip().lstrip("-").isdigit()
}

# --- Админы: кто может добавлять и удалять заведения ---
# В переменной ADMINS перечисли user ID через запятую (см. команду /id).
# Если переменная пустая — добавлять/удалять может любой (открытый режим).
_raw_admins = os.environ.get("ADMINS", "").strip()
ADMINS: set[int] = {
    int(x) for x in _raw_admins.split(",") if x.strip().lstrip("-").isdigit()
}


def is_admin(user_id: int) -> bool:
    return not ADMINS or user_id in ADMINS


@dp.message.middleware()
async def whitelist_messages(handler, event, data):
    # /id работает всегда — иначе не узнать ID чата, чтобы его разрешить
    text = (event.text or "")
    if text == "/id" or text.startswith("/id@") or text.startswith("/id "):
        return await handler(event, data)
    if ALLOWED_CHATS and event.chat.id not in ALLOWED_CHATS:
        return  # молча игнорируем чужие чаты
    return await handler(event, data)


@dp.callback_query.middleware()
async def whitelist_callbacks(handler, event, data):
    if ALLOWED_CHATS and event.message.chat.id not in ALLOWED_CHATS:
        await event.answer()
        return
    return await handler(event, data)


# Активные голосования: chat_id -> состояние
# votes[category][option] = set(user_id) — чтобы один человек не голосовал дважды
active_votes: dict[int, dict] = {}


# ---------- Клавиатура голосования ----------

CATEGORIES = {
    "cuisine": ("🍽 Кухня", CUISINES),
    "drink": ("🍷 Напитки", DRINKS),
    "budget": ("💰 Чек", BUDGETS),
    "vibe": ("✨ Атмосфера", VIBES),
}


def build_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Строит клавиатуру с текущим числом голосов на каждой кнопке."""
    state = active_votes[chat_id]["votes"]
    rows = []
    for cat_key, (cat_title, options) in CATEGORIES.items():
        rows.append([InlineKeyboardButton(text=f"— {cat_title} —", callback_data="noop")])
        row = []
        for opt in options:
            n = len(state[cat_key].get(opt, set()))
            label = f"{opt} · {n}" if n else opt
            row.append(InlineKeyboardButton(
                text=label,
                callback_data=f"v|{cat_key}|{opt}",
            ))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
    rows.append([InlineKeyboardButton(text="✅ Готово — показать топ", callback_data="done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def empty_votes() -> dict:
    return {cat: defaultdict(set) for cat in CATEGORIES}


# ---------- Команды ----------

HELP_TEXT = (
    "Привет! Я помогаю выбрать, куда пойти 🥂\n\n"
    "<b>Команды:</b>\n"
    "/vote — запустить голосование «куда идём»\n"
    "/list — какие заведения есть в базе\n\n"
    "<b>Как это работает:</b>\n"
    "Жмите /vote, тыкайте кнопки — что за кухню хочется, "
    "какой чек, какие напитки и атмосферу. Можно несколько вариантов, "
    "повторное нажатие снимает голос. Когда все проголосовали — "
    "кто-нибудь жмёт «Готово», и я покажу топ-3 места под ваши хотелки."
)

ADMIN_HELP_TEXT = (
    "\n\n— — —\n"
    "<b>Для хранителей базы:</b>\n"
    "/add — добавить заведение, одной строкой через <code>|</code>, 7 полей:\n"
    "<code>Название | Район | кухни | напитки | чек | атмосфера | описание</code>\n"
    "Напитки — как <code>напиток:оценка</code> от 0 до 3. Пример:\n"
    "<code>/add Траттория | центр | итальянская | вино:3, коктейли:1 | 10к–15к | тихо / свидание | Паста и большая карта вин</code>\n"
    "/del &lt;id&gt; — удалить заведение (id смотри в /list)\n"
    "/discover &lt;что ищем&gt; — ИИ-разведка: найдёт места по городу и предложит в базу"
)


@dp.message(Command("start", "help"))
async def cmd_help(message: Message):
    text = HELP_TEXT
    if is_admin(message.from_user.id) and ADMINS:
        text += ADMIN_HELP_TEXT
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(
        f"ID этого чата: <code>{message.chat.id}</code>\n"
        f"Твой user ID: <code>{message.from_user.id}</code>\n\n"
        "Чат — в ALLOWED_CHATS (где бот работает),\n"
        "user ID — в ADMINS (кто может /add и /del).",
        parse_mode="HTML",
    )


@dp.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("Добавлять заведения могут только хранители базы 🙂")
        return
    raw = (command.args or "").strip()
    if not raw:
        await message.answer(
            "Пришли разметку одной строкой. Формат:\n"
            "<code>Название | Район | кухни | напитки | чек | атмосфера | описание</code>\n\n"
            "Подробнее — /help",
            parse_mode="HTML",
        )
        return
    try:
        data = parse_add(raw)
        data["added_by"] = message.from_user.full_name
        place_id = await asyncio.to_thread(db.add_place, data)
        cuisines = ", ".join(data.get("cuisines", [])) or "—"
        drinks = ", ".join(f"{k}({v})" for k, v in data.get("drinks", {}).items()) or "—"
        await message.answer(
            f"✅ Добавила <b>{data['name']}</b> (id {place_id})\n"
            f"Кухня: {cuisines}\n"
            f"Напитки: {drinks}\n"
            f"Чек: {data.get('budget') or '—'}\n"
            f"Район: {data.get('district') or '—'}\n"
            f"Атмосфера: {', '.join(data.get('vibes', [])) or '—'}",
            parse_mode="HTML",
        )
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
    except Exception as e:
        logging.exception("add failed")
        await message.answer(f"Не получилось добавить 😕\n{e}")


@dp.message(Command("list"))
async def cmd_list(message: Message):
    places = await asyncio.to_thread(db.get_all_places)
    if not places:
        await message.answer("База пока пустая. Добавь заведение через /add")
        return
    lines = []
    for p in places:
        cuisines = ", ".join(p["cuisines"]) or "—"
        lines.append(f"<b>{p['id']}. {p['name']}</b> — {cuisines}, чек {p['budget'] or '—'}")
    await message.answer("<b>В базе:</b>\n" + "\n".join(lines), parse_mode="HTML")


@dp.message(Command("del"))
async def cmd_del(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("Удалять заведения могут только хранители базы 🙂")
        return
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Укажи id: <code>/del 3</code>", parse_mode="HTML")
        return
    ok = await asyncio.to_thread(db.delete_place, int(arg))
    await message.answer("Удалила ✅" if ok else "Такого id нет.")


# ---------- /discover: агент поиска новых мест ----------

# Кандидаты, ждущие решения: ключ -> данные заведения
pending_candidates: dict[str, dict] = {}
_candidate_seq = 0


def _fmt_candidate(c: dict) -> str:
    drinks = ", ".join(f"{k}:{v}" for k, v in c.get("drinks", {}).items() if v) or "—"
    conf = "" if c.get("confidence") == "high" else "\n⚠️ <i>не уверена, что данные свежие — проверьте перед походом</i>"
    return (
        f"<b>{c['name']}</b> · {c.get('district') or '—'}\n"
        f"{', '.join(c.get('cuisines', [])) or '—'} · чек {c.get('budget') or '—'}\n"
        f"Напитки: {drinks}\n"
        f"Атмосфера: {', '.join(c.get('vibes', [])) or '—'}\n"
        f"<i>{c.get('summary', '')}</i>{conf}"
    )


@dp.message(Command("discover"))
async def cmd_discover(message: Message, command: CommandObject):
    global _candidate_seq
    if not is_admin(message.from_user.id):
        await message.answer("Искать новые места могут только хранители базы 🙂")
        return
    query = (command.args or "").strip()
    if not query:
        await message.answer(
            "Опиши, что ищем: <code>/discover винный бар с закусками в центре</code>",
            parse_mode="HTML",
        )
        return

    wait = await message.answer("🕵️‍♀️ Ищу по городу, это займёт до минуты…")
    try:
        places = await asyncio.to_thread(db.get_all_places)
        existing = [p["name"] for p in places]
        found = await asyncio.to_thread(discover.discover_places, query, existing)
    except Exception as e:
        logging.exception("discover failed")
        await wait.edit_text(f"Поиск не удался 😕\n{e}")
        return

    if not found:
        await wait.edit_text("Ничего надёжного под запрос не нашла. Попробуй переформулировать.")
        return

    await wait.edit_text(f"Нашла {len(found)} — решай по каждому:")
    for c in found:
        _candidate_seq += 1
        key = str(_candidate_seq)
        pending_candidates[key] = c
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ В базу", callback_data=f"disc_add|{key}"),
            InlineKeyboardButton(text="🚫 Пропустить", callback_data=f"disc_skip|{key}"),
        ]])
        await message.answer(_fmt_candidate(c), parse_mode="HTML", reply_markup=kb)


@dp.callback_query(F.data.startswith("disc_add|"))
async def cb_disc_add(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Только хранители базы 🙂", show_alert=True)
        return
    key = cb.data.split("|", 1)[1]
    c = pending_candidates.pop(key, None)
    if c is None:
        await cb.answer("Этот кандидат уже обработан", show_alert=True)
        return
    c["added_by"] = f"discover/{cb.from_user.full_name}"
    place_id = await asyncio.to_thread(db.add_place, c)
    await cb.message.edit_text(
        cb.message.html_text + f"\n\n✅ <b>В базе</b> (id {place_id})",
        parse_mode="HTML",
    )
    await cb.answer("Добавила!")


@dp.callback_query(F.data.startswith("disc_skip|"))
async def cb_disc_skip(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("Только хранители базы 🙂", show_alert=True)
        return
    key = cb.data.split("|", 1)[1]
    pending_candidates.pop(key, None)
    await cb.message.edit_text(
        cb.message.html_text + "\n\n🚫 Пропущено",
        parse_mode="HTML",
    )
    await cb.answer()


@dp.message(Command("vote"))
async def cmd_vote(message: Message):
    n = await asyncio.to_thread(db.count_places)
    if n == 0:
        await message.answer("Сначала добавьте заведения через /add 🙂")
        return
    active_votes[message.chat.id] = {"votes": empty_votes()}
    await message.answer(
        "🗳 <b>Куда идём?</b> Тыкайте что хочется (можно несколько вариантов).\n"
        "Когда все проголосуют — жмите «Готово».",
        parse_mode="HTML",
        reply_markup=build_keyboard(message.chat.id),
    )


# ---------- Обработка нажатий ----------

@dp.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


@dp.callback_query(F.data.startswith("v|"))
async def cb_vote(cb: CallbackQuery):
    chat_id = cb.message.chat.id
    if chat_id not in active_votes:
        await cb.answer("Это голосование уже завершено. Запустите /vote заново.", show_alert=True)
        return

    _, cat, opt = cb.data.split("|", 2)
    user_id = cb.from_user.id
    voters = active_votes[chat_id]["votes"][cat][opt]

    if user_id in voters:
        voters.discard(user_id)
        await cb.answer("Голос убран")
    else:
        voters.add(user_id)
        await cb.answer("Голос учтён ✅")

    await cb.message.edit_reply_markup(reply_markup=build_keyboard(chat_id))


@dp.callback_query(F.data == "done")
async def cb_done(cb: CallbackQuery):
    chat_id = cb.message.chat.id
    if chat_id not in active_votes:
        await cb.answer()
        return

    raw = active_votes[chat_id]["votes"]
    votes = {
        cat: {opt: len(users) for opt, users in opts.items() if users}
        for cat, opts in raw.items()
    }

    total = sum(len(u) for opts in raw.values() for u in opts.values())
    if total == 0:
        await cb.answer("Никто ещё не проголосовал 🙂", show_alert=True)
        return

    places = await asyncio.to_thread(db.get_all_places)
    top = top_places(places, votes, TOP_N)

    if not top:
        await cb.message.edit_text("Под такие пожелания в базе ничего не нашлось 😔")
        del active_votes[chat_id]
        await cb.answer()
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["<b>Вот куда стоит пойти:</b>\n"]
    for i, (p, sc) in enumerate(top):
        medal = medals[i] if i < len(medals) else "•"
        lines.append(
            f"{medal} <b>{p['name']}</b>\n"
            f"{', '.join(p['cuisines'])} · чек {p['budget'] or '—'}\n"
            f"<i>{p['summary']}</i>\n"
        )
    await cb.message.edit_text("\n".join(lines), parse_mode="HTML",
                               disable_web_page_preview=True)
    del active_votes[chat_id]
    await cb.answer("Готово!")


async def main():
    db.init_db()
    logging.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
