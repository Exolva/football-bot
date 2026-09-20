import asyncio
from datetime import datetime, timedelta
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import os
from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ (SQLite) ---
conn = sqlite3.connect("football_bot_strict.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_name TEXT,
    mult_type TEXT DEFAULT 'all',
    multiplier REAL DEFAULT 1.0,
    status TEXT DEFAULT 'active',
    created_at TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    user_id INTEGER,
    match_id INTEGER,
    prediction_type TEXT,
    prediction_value TEXT,
    UNIQUE(user_id, match_id, prediction_type)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS scores (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    points REAL DEFAULT 0
)
""")
conn.commit()


# --- 1. СОЗДАНИЕ МАТЧА С ОГРАНИЧЕНИЕМ ПО ВРЕМЕНИ ---
@dp.message(Command("match"))
async def create_match(message: Message):
    parts = message.text.replace("/match", "").strip().split()

    mult_type = "all"
    multiplier = 1.0
    match_name_parts = []

    def is_float(val):
        try:
            float(val)
            return True
        except ValueError:
            return False

    if len(parts) >= 3 and parts[0].lower() in ["all", "t1", "t2"] and is_float(parts[1]):
        mult_type = parts[0].lower()
        multiplier = float(parts[1])
        match_name_parts = parts[2:]
    elif len(parts) >= 2 and is_float(parts[0]):
        multiplier = float(parts[0])
        match_name_parts = parts[1:]
    else:
        match_name_parts = parts

    match_name = " ".join(match_name_parts)
    if not match_name:
        await message.answer(
            "⚠️ Укажите название матча!\n"
            "Примеры:\n"
            "• `/match Арсенал - Челси`\n"
            "• `/match all 1.5 Арсенал - Челси` (Х1.5 на весь матч)\n"
            "• `/match t1 2.0 Арсенал - Челси` (Х2 на 1-ю команду)",
            parse_mode="Markdown",
        )
        return

    now_time = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO matches (match_name, mult_type, multiplier, status, created_at)"
        " VALUES (?, ?, ?, 'active', ?)",
        (match_name, mult_type, multiplier, now_time),
    )
    conn.commit()
    match_id = cursor.lastrowid

    def get_pts(base, p_type, val=""):
        if multiplier == 1.0:
            return f"{base}б"

        def format_val(v):
            return int(v) if v.is_integer() else round(v, 1)

        if mult_type == "all":
            return f"{format_val(base * multiplier)}б"
        elif mult_type == "t1":
            if p_type == "main" and val == "П1":
                return f"{format_val(base * multiplier)}б"
            if p_type == "t1clean":
                return f"{format_val(base * multiplier)}б"
            return f"{base}б"
        elif mult_type == "t2":
            if p_type == "main" and val == "П2":
                return f"{format_val(base * multiplier)}б"
            if p_type == "t2clean":
                return f"{format_val(base * multiplier)}б"
            return f"{base}б"
        return f"{base}б"

    mult_desc = ""
    if multiplier != 1.0:
        mult_val_str = (
            str(int(multiplier))
            if multiplier.is_integer()
            else str(multiplier)
        )
        if mult_type == "all":
            mult_desc = f" (🔥 Х{mult_val_str} на весь матч)"
        elif mult_type == "t1":
            mult_desc = f" (🔥 Х{mult_val_str} бонус на 1-ю команду)"
        elif mult_type == "t2":
            mult_desc = f" (🔥 Х{mult_val_str} бонус на 2-ю команду)"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🏠 П1 ({get_pts(3, 'main', 'П1')})",
                    callback_data=f"bet_{match_id}_main_П1",
                ),
                InlineKeyboardButton(
                    text=f"🤝 Ничья ({get_pts(5, 'main', 'Ничья')})",
                    callback_data=f"bet_{match_id}_main_Ничья",
                ),
                InlineKeyboardButton(
                    text=f"✈️ П2 ({get_pts(3, 'main', 'П2')})",
                    callback_data=f"bet_{match_id}_main_П2",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🟥 Карточки/КК: Да ({get_pts(3, 'cards')})",
                    callback_data=f"bet_{match_id}_cards_да",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⚡ Пенальти: Да ({get_pts(3, 'pen')})",
                    callback_data=f"bet_{match_id}_pen_да",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⏱ Гол >90: Да ({get_pts(4, 'goal90')})",
                    callback_data=f"bet_{match_id}_goal90_да",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⚽ Обе забьют: Да ({get_pts(2, 'btts')})",
                    callback_data=f"bet_{match_id}_btts_да",
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🛡 К1 не пропустит: Да"
                        f" ({get_pts(3, 't1clean', 'да')})"
                    ),
                    callback_data=f"bet_{match_id}_t1clean_да",
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🛡 К2 не пропустит: Да"
                        f" ({get_pts(3, 't2clean', 'да')})"
                    ),
                    callback_data=f"bet_{match_id}_t2clean_да",
                )
            ],
        ]
    )

    await message.answer(
        f"⚽ **МАТЧ ДЛЯ ПРОГНОЗОВ! (ID матча: {match_id})**{mult_desc}\n"
        f"⏳ *Прием прогнозов открыт ровно на 10 часов!*\n\n"
        f"🏟 **{match_name}**\n\n"
        f"👇 *Сделайте свои прогнозы (выбор делается 1 раз, изменить нельзя):*",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# --- 2. ОБРАБОТКА НАЖАТИЯ С ПРОВЕРКОЙ ВРЕМЕНИ И ЗАЩИТОЙ ---
@dp.callback_query(F.data.startswith("bet_"))
async def process_bet(callback: CallbackQuery):
    data_parts = callback.data.split("_")
    match_id = int(data_parts[1])
    pred_type = data_parts[2]
    pred_value = data_parts[3]

    user_id = callback.from_user.id
    username = callback.from_user.full_name

    cursor.execute(
        "SELECT status, created_at FROM matches WHERE id = ?", (match_id,)
    )
    match = cursor.fetchone()

    if not match:
        await callback.answer("❌ Матч не найден!", show_alert=True)
        return

    status, created_at_str = match[0], match[1]

    if status != "active":
        await callback.answer(
            "❌ Прием прогнозов на этот матч уже закрыт!", show_alert=True
        )
        return

    try:
        match_created_time = datetime.fromisoformat(created_at_str)
    except Exception:
        match_created_time = datetime.now()

    if datetime.now() - match_created_time > timedelta(hours=10):
        cursor.execute(
            "UPDATE matches SET status = 'finished' WHERE id = ?", (match_id,)
        )
        conn.commit()
        await callback.answer(
            "⏳ Время вышло! Прогнозы на этот матч больше не принимаются (прошло"
            " более 10 часов).",
            show_alert=True,
        )
        return

    cursor.execute(
        "SELECT prediction_value FROM predictions WHERE user_id = ? AND match_id"
        " = ? AND prediction_type = ?",
        (user_id, match_id, pred_type),
    )
    existing_bet = cursor.fetchone()

    if existing_bet:
        await callback.answer(
            "❌ Вы уже сделали прогноз на этот пункт! Менять ответ нельзя.",
            show_alert=True,
        )
        return

    try:
        cursor.execute(
            "INSERT INTO predictions (user_id, match_id, prediction_type, "
            "prediction_value) VALUES (?, ?, ?, ?)",
            (user_id, match_id, pred_type, pred_value),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO scores (user_id, username, points) VALUES (?, ?,"
            " 0.0)",
            (user_id, username),
        )
        conn.commit()

        await callback.answer("✅ Прогноз зафиксирован!", show_alert=True)
    except Exception as e:
        await callback.answer("⚠️ Ошибка сохранения прогноза.", show_alert=True)


# --- 3. ПОКАЗАТЬ, КТО И ЧТО СДЕЛАЛ (КОМАНДА /votes) ---
@dp.message(Command("votes"))
async def show_match_votes(message: Message):
    args = message.text.replace("/votes", "").strip().split()
    if not args or not args[0].isdigit():
        await message.answer(
            "⚠️ Укажите ID матча!\nПример: `/votes 1`", parse_mode="Markdown"
        )
        return

    match_id = int(args[0])

    cursor.execute("SELECT match_name FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await message.answer("❌ Матч с таким ID не найден.")
        return

    match_name = match[0]

    cursor.execute(
        """
            SELECT p.user_id, s.username, p.prediction_type, p.prediction_value 
            FROM predictions p
            LEFT JOIN scores s ON p.user_id = s.user_id
            WHERE p.match_id = ?
        """,
        (match_id,),
    )
    predictions = cursor.fetchall()

    if not predictions:
        await message.answer(
            f"📋 На матч **{match_name}** (ID: {match_id}) пока никто не сделал"
            " прогнозы.",
            parse_mode="Markdown",
        )
        return

    users_data = {}
    type_labels = {
        "main": "Исход",
        "cards": "Карточки",
        "pen": "Пенальти",
        "goal90": "Гол >90",
        "btts": "Обе забьют",
        "t1clean": "К1 сухие",
        "t2clean": "К2 сухие",
    }

    for uid, uname, p_type, p_val in predictions:
        name = uname if uname else f"ID: {uid}"
        if name not in users_data:
            users_data[name] = []
        label = type_labels.get(p_type, p_type)
        users_data[name].append(f"{label}: <b>{p_val}</b>")

    text = f"📋 <b>Прогнозы на матч (ID: {match_id}):</b>\n🏟 <i>{match_name}</i>\n\n"
    for name, bets in users_data.items():
        text += f"👤 <b>{name}</b>:\n  • " + "\n  • ".join(bets) + "\n\n"

    await message.answer(text, parse_mode="HTML")


# --- 4. ПОДВЕДЕНИЕ ИТОГОВ АДМИНИСТРАТОРОМ ---
@dp.message(Command("finish"))
async def finish_match(message: Message):
    args = message.text.replace("/finish", "").strip().split()
    if len(args) < 7:
        await message.answer(
            "⚠️ **Неверный формат!**\n"
            "Используйте:\n"
            "`/finish [ID] [Исход(П1/Ничья/П2)] [Карточки(да/нет)]"
            " [Пенальти(да/нет)] [Гол>90(да/нет)] [ОбеЗабьют(да/нет)]"
            " [К1_сухие(да/нет)] [К2_сухие(да/нет)]`\n\n"
            "Пример: `/finish 1 П1 да нет нет да да нет`",
            parse_mode="Markdown",
        )
        return

    match_id = int(args[0])
    real_main = args[1]
    real_cards = args[2].lower()
    real_pen = args[3].lower()
    real_goal90 = args[4].lower()
    real_btts = args[5].lower()
    real_t1clean = args[6].lower()
    real_t2clean = args[7].lower() if len(args) > 7 else "нет"

    cursor.execute(
        "SELECT match_name, mult_type, multiplier, status FROM matches WHERE id ="
        " ?",
        (match_id,),
    )
    match = cursor.fetchone()
    if not match:
        await message.answer("❌ Матч с таким ID не найден.")
        return

    match_name = match[0]
    mult_type = match[1]
    multiplier = match[2]

    cursor.execute(
        "UPDATE matches SET status = 'finished' WHERE id = ?", (match_id,)
    )

    cursor.execute(
        "SELECT user_id, prediction_type, prediction_value FROM predictions "
        "WHERE match_id = ?",
        (match_id,),
    )
    all_predictions = cursor.fetchall()

    user_bets = {}
    for uid, p_type, p_val in all_predictions:
        if uid not in user_bets:
            user_bets[uid] = {}
        user_bets[uid][p_type] = p_val

    results_text = (
        f"🏁 **ИТОГИ МАТЧА: {match_name}**\n"
        f"⚽ Исход: **{real_main}** | 🟥 Карточки: **{real_cards.capitalize()}**"
        f" | ⚡ Пенальти: **{real_pen.capitalize()}**\n"
        f"⏱ Гол >90: **{real_goal90.capitalize()}** | ⚽ ОЗ: **{real_btts.capitalize()}**\n"
        f"🛡 К1 сухие: **{real_t1clean.capitalize()}** | 🛡 К2 сухие:"
        f" **{real_t2clean.capitalize()}**\n\n"
        f"🏆 **Начисленные баллы:**\n"
    )

    total_winners = 0

    def calc_points(p_type, base_pts, user_val, real_val):
        if user_val != real_val:
            return 0.0
        apply_mult = False
        if mult_type == "all":
            apply_mult = True
        elif mult_type == "t1":
            if (p_type == "main" and user_val == "П1") or (p_type == "t1clean"):
                apply_mult = True
        elif mult_type == "t2":
            if (p_type == "main" and user_val == "П2") or (p_type == "t2clean"):
                apply_mult = True
        return base_pts * multiplier if apply_mult else float(base_pts)

    for user_id, bets in user_bets.items():
        earned_points = 0.0
        details = []

        if "main" in bets:
            base_p = 5 if bets["main"] == "Ничья" else 3
            pts = calc_points("main", base_p, bets["main"], real_main)
            if pts > 0:
                earned_points += pts
                p_str = int(pts) if pts.is_integer() else round(pts, 1)
                details.append(f"Исход +{p_str}")

        if bets.get("cards") == "да" and real_cards == "да":
            pts = calc_points("cards", 3, "да", real_cards)
            earned_points += pts
            p_str = int(pts) if pts.is_integer() else round(pts, 1)
            details.append(f"Карточки +{p_str}")

        if bets.get("pen") == "да" and real_pen == "да":
            pts = calc_points("pen", 3, "да", real_pen)
            earned_points += pts
            p_str = int(pts) if pts.is_integer() else round(pts, 1)
            details.append(f"Пенальти +{p_str}")

        if bets.get("goal90") == "да" and real_goal90 == "да":
            pts = calc_points("goal90", 4, "да", real_goal90)
            earned_points += pts
            p_str = int(pts) if pts.is_integer() else round(pts, 1)
            details.append(f"Гол>90 +{p_str}")

        if bets.get("btts") == "да" and real_btts == "да":
            pts = calc_points("btts", 2, "да", real_btts)
            earned_points += pts
            p_str = int(pts) if pts.is_integer() else round(pts, 1)
            details.append(f"ОЗ +{p_str}")

        if bets.get("t1clean") == "да" and real_t1clean == "да":
            pts = calc_points("t1clean", 3, "да", real_t1clean)
            earned_points += pts
            p_str = int(pts) if pts.is_integer() else round(pts, 1)
            details.append(f"К1 не пропустит +{p_str}")

        if bets.get("t2clean") == "да" and real_t2clean == "да":
            pts = calc_points("t2clean", 3, "да", real_t2clean)
            earned_points += pts
            p_str = int(pts) if pts.is_integer() else round(pts, 1)
            details.append(f"К2 не пропустит +{p_str}")

        if earned_points > 0:
            total_winners += 1
            cursor.execute(
                "UPDATE scores SET points = points + ? WHERE user_id = ?",
                (earned_points, user_id),
            )
            conn.commit()

            cursor.execute("SELECT username, points FROM scores WHERE user_id = ?", (user_id,))
            user_info = cursor.fetchone()
            total_pts_str = (
                int(user_info[1])
                if user_info[1].is_integer()
                else round(user_info[1], 1)
            )
            results_text += (
                f"👤 {user_info[0]}: {', '.join(details)} (Всего:"
                f" **{total_pts_str}** бал.)\n"
            )

    if total_winners == 0:
        results_text += "Никто не набрал баллы в этом матче 😢"

    await message.answer(results_text, parse_mode="Markdown")


# --- 5. РУЧНОЕ НАЧИСЛЕНИЕ БАЛЛОВ АДМИНИСТРАТОРОМ ---
@dp.message(Command("addpts"))
async def add_points(message: Message):
    args = message.text.replace("/addpts", "").strip().split()
    if len(args) < 2:
        await message.answer(
            "⚠️ **Неверный формат!**\n"
            "Используйте:\n"
            "`/addpts [Имя игрока] [Баллы]`\n\n"
            "Пример: `/addpts Иван 1.5` или `/addpts Иван -0.5`",
            parse_mode="Markdown",
        )
        return

    try:
        points_to_add = float(args[-1])
    except ValueError:
        await message.answer("⚠️ Ошибка: количество баллов должно быть числом!")
        return

    target_username = " ".join(args[:-1])

    cursor.execute(
        "SELECT user_id, username, points FROM scores WHERE username LIKE ?",
        (f"%{target_username}%",),
    )
    user = cursor.fetchone()

    if not user:
        await message.answer(
            f"❌ Участник с именем **'{target_username}'** не найден в базе данных.",
            parse_mode="Markdown",
        )
        return

    user_id, found_username, current_points = user
    new_points = current_points + points_to_add

    cursor.execute(
        "UPDATE scores SET points = ? WHERE user_id = ?", (new_points, user_id)
    )
    conn.commit()

    def fmt(v):
        return int(v) if v.is_integer() else round(v, 1)

    action_word = "добавлено" if points_to_add >= 0 else "отнято"
    await message.answer(
        f"✅ Успешно! Игроку **{found_username}** {action_word}"
        f" `{fmt(abs(points_to_add))}` бал.\n"
        f"📊 Текущий баланс: **{fmt(new_points)}** бал.",
        parse_mode="Markdown",
    )


# --- 6. ТАБЛИЦА ЛИДЕРОВ ---
@dp.message(Command("table"))
async def show_table(message: Message):
    cursor.execute("SELECT username, points FROM scores ORDER BY points DESC LIMIT 10")
    top_users = cursor.fetchall()

    if not top_users:
        await message.answer("📊 Таблица лидеров пока пуста.")
        return

    text = "🏆 **ТАБЛИЦА ЛИДЕРОВ ПРОГНОЗИСТОВ** 🏆\n\n"
    for i, (uname, pts) in enumerate(top_users, start=1):
        pts_str = int(pts) if pts.is_integer() else round(pts, 1)
        text += f"{i}. {uname} — **{pts_str}** бал.\n"

    await message.answer(text, parse_mode="Markdown")


# --- ВЕБ-СЕРВЕР ДЛЯ RENDER И ЗАПУСК ---
async def handle_ping(request):
    return web.Response(text="Bot is active and running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")

async def main_with_web():
    print("Запуск бота и веб-сервера...")
    await asyncio.gather(
        dp.start_polling(bot),
        web_server()
    )

if __name__ == "__main__":
    asyncio.run(main_with_web())
