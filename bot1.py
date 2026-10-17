import asyncio
from datetime import datetime, timedelta
import random
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import os
from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [438944983]

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
    is_test INTEGER DEFAULT 0,
    is_playoff INTEGER DEFAULT 0,
    extras_order TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    user_id INTEGER,
    match_id INTEGER,
    prediction_type TEXT,
    prediction_value TEXT,
    is_main INTEGER,
    UNIQUE(user_id, match_id, is_main)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS match_rewards (
    match_id INTEGER,
    user_id INTEGER,
    points REAL,
    PRIMARY KEY (match_id, user_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS scores (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    points REAL DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS monthly_scores (
    user_id INTEGER,
    month TEXT,
    points REAL DEFAULT 0,
    PRIMARY KEY (user_id, month)
)
""")

# Миграции структуры базы данных
for q in [
    "ALTER TABLE monthly_scores ADD COLUMN username TEXT",
    "ALTER TABLE predictions ADD COLUMN is_main INTEGER DEFAULT 0",
    "ALTER TABLE matches ADD COLUMN is_playoff INTEGER DEFAULT 0",
    "ALTER TABLE matches ADD COLUMN extras_order TEXT"
]:
    try:
        cursor.execute(q)
        conn.commit()
    except sqlite3.OperationalError:
        pass


# --- АВТОМАТИЧЕСКОЕ ДОБАВЛЕНИЕ ФЛАЖКОВ СТРАН ---
def decorate_match_name(match_name: str) -> str:
    decorations = {
        "украина": "🇺🇦", "ukraine": "🇺🇦", "англия": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "england": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "испания": "🇪🇸", "spain": "🇪🇸", "италия": "🇮🇹", "italy": "🇮🇹",
        "германия": "🇩🇪", "germany": "🇩🇪", "франция": "🇫🇷", "france": "🇫🇷",
        "португалия": "🇵🇹", "portugal": "🇵🇹", "нидерланды": "🇳🇱", "netherlands": "🇳🇱",
        "бельгия": "🇧🇪", "belgium": "🇧🇪", "польша": "🇵🇱", "poland": "🇵🇱",
        "турция": "🇹🇷", "turkey": "🇹🇷", "хорватия": "🇭🇷", "croatia": "🇭🇷",
        "дания": "🇩🇰", "denmark": "🇩🇰", "швеция": "🇸🇪", "sweden": "🇸🇪",
        "швейцария": "🇨🇭", "switzerland": "🇨🇭", "австрия": "🇦🇹", "austria": "🇦🇹",
        "сербия": "🇷🇸", "serbia": "🇷🇸", "чехия": "🇨🇿", "czech republic": "🇨🇿",
        "бразилия": "🇧🇷", "brazil": "🇧🇷", "аргентина": "🇦🇷", "argentina": "🇦🇷",
        "уругвай": "🇺🇾", "uruguay": "🇺🇾", "колумбия": "🇨🇴", "colombia": "🇨🇴",
        "мексика": "🇲🇽", "mexico": "🇲🇽", "сша": "🇺🇸", "usa": "🇺🇸",
        "шахтер": "🇺🇦", "динамо": "🇺🇦", "арсенал": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "реал мадрид": "🇪🇸",
        "барселона": "🇪🇸", "интер": "🇮🇹", "милан": "🇮🇹", "ювентус": "🇮🇹",
        "бавария": "🇩🇪", "псг": "🇫🇷"
    }
    updated_name = match_name
    import re
    sorted_keys = sorted(decorations.keys(), key=len, reverse=True)
    for key in sorted_keys:
        emoji = decorations[key]
        if key in updated_name.lower():
            pattern = re.compile(re.escape(key), re.IGNORECASE)
            updated_name = pattern.sub(f"{emoji} \\g<0>", updated_name, count=1)
    return updated_name


# --- СОЗДАНИЕ МАТЧА В КОМПАКТНОМ ВИДЕ С КНОПКОЙ ---
async def handle_match_creation(message: Message, is_test: int = 0, is_playoff: int = 0):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав для создания матчей.")
        return

    cmd_prefix = "/testmatch" if is_test else ("/playoff" if is_playoff else "/match")
    parts = message.text.replace(cmd_prefix, "").strip().split()

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

    raw_match_name = " ".join(match_name_parts)
    if not raw_match_name:
        ex_cmd = "/testmatch" if is_test else ("/playoff" if is_playoff else "/match")
        await message.answer(f"⚠️ Укажите название матча!\nПример: `{ex_cmd} Арсенал - Челси`", parse_mode="Markdown")
        return

    match_name = decorate_match_name(raw_match_name)
    now_time = datetime.now().isoformat()

    base_extra_bets = [
        ("🛡 Матч без голов (0:0)", "no_goals", 6),
        ("⚡ Пенальти", "pen", 3),
        ("⏱ Гол >90", "goal90", 4),
        ("⚽ Обе забьют", "btts", 2),
        ("⚽ Обе забьют 4+", "btts3", 4),
        ("⏱ 1-й тайм 0-0", "ht00", 3),
        ("🔴 Красная карточка", "red", 4),
        ("⏱ Гол в первые 15 мин", "goal15", 4),
        ("⚽ Гол в обоих таймах", "goalboth", 3),
        ("🥅 Тотал больше 2.5", "over25", 2),
        ("🛡 К1 сухой матч", "t1clean", 3),
        ("🛡 К2 сухой матч", "t2clean", 3),
        ("⏱ Гол в первые 30 мин", "goal30", 3),
        ("🔄 Волевая победа", "comeback", 4),
        ("⚽ Дубль игрока", "brace", 4),
        ("⏱ Победа в 1-м тайме", "ht_win", 4),  # Ключ ht_win
        ("⚽ Автогол", "own_goal", 5),
        ("📺 VAR / Отмена гола", "var_cancel", 2.5),
    ]

    playoff_pool_bets = [
        ("🏆 Проход К1", "adv_К1", 3),
        ("🏆 Проход К2", "adv_К2", 3),
    ]

    if mult_type in ["t1", "t2"]:
        favor_keys = {"t1clean", "t2clean", "over25", "goalboth", "brace", "goal15"}
        favor_pool = [b for b in base_extra_bets if b[1] in favor_keys]
        other_pool = [b for b in base_extra_bets if b[1] not in favor_keys]

        chosen_favor = random.sample(favor_pool, min(len(favor_pool), 3)) if favor_pool else []
        remaining_needed = 8 - len(chosen_favor)
        chosen_others = random.sample(other_pool, min(len(other_pool), remaining_needed))
        
        sampled_extras = chosen_favor + chosen_others
        if len(sampled_extras) < 8:
            leftovers = [b for b in base_extra_bets if b not in sampled_extras]
            sampled_extras += random.sample(leftovers, 8 - len(sampled_extras))
    else:
        sampled_extras = random.sample(base_extra_bets, 8)

    if is_playoff:
        sampled_extras = playoff_pool_bets + random.sample(base_extra_bets, 6)

    random.shuffle(sampled_extras)
    extras_order_str = ",".join([item[1] for item in sampled_extras])

    cursor.execute(
        "INSERT INTO matches (match_name, mult_type, multiplier, status, is_test, is_playoff, extras_order, created_at) VALUES (?, ?, ?, 'active', ?, ?, ?, ?)",
        (match_name, mult_type, multiplier, is_test, is_playoff, extras_order_str, now_time),
    )
    conn.commit()
    match_id = cursor.lastrowid

    mult_desc = ""
    if multiplier != 1.0:
        m_str = str(int(multiplier)) if multiplier.is_integer() else str(multiplier)
        mult_desc = f" (🔥 Х{m_str})"

    if is_test:
        header_text = "🧪 **ТЕСТОВЫЙ МАТЧ**"
    elif is_playoff:
        header_text = f"🏆 **ПЛЕЙ-ОФФ (ID: {match_id})**{mult_desc}"
    else:
        header_text = f"⚽ **МАТЧ (ID: {match_id})**{mult_desc}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Сделать прогноз (открыть ставки)", callback_data=f"open_match_{match_id}")]
    ])

    await message.answer(
        f"{header_text}\n⏳ *Прием прогнозов открыт на 10 часов!*\n\n"
        f"🏟 **{match_name}**\n\n"
        f"👇 *Нажмите кнопку ниже, чтобы сделать прогноз:*",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@dp.message(Command("match"))
async def create_match(message: Message):
    await handle_match_creation(message, is_test=0, is_playoff=0)

@dp.message(Command("testmatch"))
async def create_test_match(message: Message):
    await handle_match_creation(message, is_test=1, is_playoff=0)

@dp.message(Command("playoff"))
async def create_playoff_match(message: Message):
    await handle_match_creation(message, is_test=0, is_playoff=1)


@dp.message(Command("delmatch"))
async def delete_match(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав.")
        return
    args = message.text.replace("/delmatch", "").strip().split()
    if not args or not args[0].isdigit():
        await message.answer("⚠️ Укажите ID матча! Пример: `/delmatch 1`", parse_mode="Markdown")
        return
    match_id = int(args[0])
    cursor.execute("SELECT match_name FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await message.answer(f"❌ Матч с ID `{match_id}` не найден.", parse_mode="Markdown")
        return
    match_name = match[0]
    cursor.execute("DELETE FROM predictions WHERE match_id = ?", (match_id,))
    cursor.execute("DELETE FROM match_rewards WHERE match_id = ?", (match_id,))
    cursor.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    conn.commit()
    await message.answer(f"🗑 **Матч успешно удален!**\n🏟 *{match_name}* (ID: {match_id})", parse_mode="Markdown")


# --- РАЗВОРАЧИВАНИЕ ПОЛНОГО ВИДА СТАВОК ---
@dp.callback_query(F.data.startswith("open_match_"))
async def open_match_bets(callback: CallbackQuery):
    match_id = int(callback.data.split("_")[2])
    cursor.execute("SELECT match_name, mult_type, multiplier, is_test, is_playoff, extras_order, created_at, status FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await callback.answer("❌ Матч не найден!", show_alert=True)
        return

    match_name, mult_type, multiplier, is_test, is_playoff, extras_order_str, created_at_str, status = match
    is_admin = callback.from_user.id in ADMIN_IDS

    try:
        match_created_time = datetime.fromisoformat(created_at_str)
    except Exception:
        match_created_time = datetime.now()

    is_expired = (datetime.now() - match_created_time > timedelta(hours=10)) or (status != "active")

    if is_expired and not is_admin:
        await callback.answer("❌ Время приема прогнозов на этот матч вышло!", show_alert=True)
        return

    def get_pts(base, p_type, val=""):
        calculated = base * multiplier if multiplier != 1.0 else float(base)
        if mult_type in ["t1", "t2"]:
            if mult_type == "t1" and (p_type in ["t1clean"] or val == "П1" or val == "К1"):
                calculated *= 0.9
            elif mult_type == "t2" and (p_type in ["t2clean"] or val == "П2" or val == "К2"):
                calculated *= 0.9
            else:
                calculated *= 1.15
        final_pts = min(10.0, max(1.0, calculated))
        return int(final_pts) if final_pts.is_integer() else round(final_pts, 1)

    mult_desc = ""
    if multiplier != 1.0:
        m_str = str(int(multiplier)) if multiplier.is_integer() else str(multiplier)
        mult_desc = f" (🔥 Х{m_str})"

    keyboard_rows = [
        [InlineKeyboardButton(text="🏆 ─── ОСНОВНОЙ ИСХОД ─── 🏆", callback_data="header_main")],
        [
            InlineKeyboardButton(text=f"🏠 П1 ({get_pts(3, 'main', 'П1')}б)", callback_data=f"bet_{match_id}_main_П1"),
            InlineKeyboardButton(text=f"✈️ П2 ({get_pts(3, 'main', 'П2')}б)", callback_data=f"bet_{match_id}_main_П2"),
        ],
        [
            InlineKeyboardButton(text=f"🤝 Ничья ({get_pts(5, 'main', 'Ничья')}б)", callback_data=f"bet_{match_id}_main_Ничья"),
        ],
        [InlineKeyboardButton(text="🎯 ─── ДОП. СТАВКИ ─── 🎯", callback_data="header_extra")],
    ]

    base_extra_dict = {
        "no_goals": ("🛡 Матч без голов (0:0)", 6),
        "pen": ("⚡ Пенальти", 3),
        "goal90": ("⏱ Гол >90", 4),
        "btts": ("⚽ Обе забьют", 2),
        "btts3": ("⚽ Обе забьют 4+", 4),
        "ht00": ("⏱ 1-й тайм 0-0", 3),
        "red": ("🔴 Красная карточка", 4),
        "goal15": ("⏱ Гол в первые 15 мин", 4),
        "goalboth": ("⚽ Гол в обоих таймах", 3),
        "over25": ("🥅 Тотал больше 2.5", 2),
        "t1clean": ("🛡 К1 сухой матч", 3),
        "t2clean": ("🛡 К2 сухой матч", 3),
        "goal30": ("⏱ Гол в первые 30 мин", 3),
        "comeback": ("🔄 Волевая победа", 4),
        "brace": ("⚽ Дубль игрока", 4),
        "ht_win": ("⏱ Победа в 1-м тайме", 4),  # Полное название
        "own_goal": ("⚽ Автогол", 5),
        "var_cancel": ("📺 VAR / Отмена гола", 2.5),
        "adv_К1": ("🏆 Проход К1", 3),
        "adv_К2": ("🏆 Проход К2", 3),
    }

    extras_list = extras_order_str.split(",") if extras_order_str else []
    
    if is_playoff:
        playoff_fixed = [("🏆 Проход К1", "adv_К1", 3), ("🏆 Проход К2", "adv_К2", 3)]
        for idx, (title, raw_type, base_p) in enumerate(playoff_fixed, start=1):
            pts_val = get_pts(base_p, raw_type, "К1" if "К1" in raw_type else "К2")
            keyboard_rows.append([InlineKeyboardButton(text=f"{idx}. {title} ({pts_val}б)", callback_data=f"bet_{match_id}_{raw_type}")])
        start_idx = 3
    else:
        start_idx = 1

    for idx, raw_type in enumerate(extras_list, start=start_idx):
        if raw_type in base_extra_dict:
            title, base_p = base_extra_dict[raw_type]
            val_marker = "К1" if "К1" in raw_type else ("К2" if "К2" in raw_type else "")
            pts_val = get_pts(base_p, raw_type, val_marker)
            keyboard_rows.append([InlineKeyboardButton(text=f"{idx}. {title} ({pts_val}б)", callback_data=f"bet_{match_id}_{raw_type}")])

    keyboard_rows.append([InlineKeyboardButton(text="◀️ Свернуть прогноз", callback_data=f"close_match_{match_id}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    if is_test:
        header_text = "🧪 **ТЕСТОВЫЙ МАТЧ**"
    elif is_playoff:
        header_text = f"🏆 **ПЛЕЙ-ОФФ (ID: {match_id})**{mult_desc}"
    else:
        header_text = f"⚽ **МАТЧ (ID: {match_id})**{mult_desc}"

    status_note = "\n⚠️ *Прием прогнозов закрыт (режим просмотра для админа)*\n" if is_expired else ""

    try:
        await callback.message.edit_text(
            f"{header_text}\n{status_note}\n"
            f"🏟 **{match_name}**\n\n"
            f"👇 *Шпаргалка с номерами доп. ставок:*",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        await callback.answer("🔓 Развернуто!", show_alert=False)
    except Exception:
        await callback.answer("⚠️ Ошибка обновления.", show_alert=True)


@dp.callback_query(F.data.startswith("close_match_"))
async def close_match_bets(callback: CallbackQuery):
    match_id = int(callback.data.split("_")[2])
    cursor.execute("SELECT match_name, is_test, is_playoff, multiplier FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await callback.answer("❌ Матч не найден!", show_alert=True)
        return

    match_name, is_test, is_playoff, multiplier = match
    mult_desc = ""
    if multiplier != 1.0:
        m_str = str(int(multiplier)) if multiplier.is_integer() else str(multiplier)
        mult_desc = f" (🔥 Х{m_str})"

    if is_test:
        header_text = "🧪 **ТЕСТОВЫЙ МАТЧ**"
    elif is_playoff:
        header_text = f"🏆 **ПЛЕЙ-ОФФ (ID: {match_id})**{mult_desc}"
    else:
        header_text = f"⚽ **МАТЧ (ID: {match_id})**{mult_desc}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Сделать прогноз (открыть ставки)", callback_data=f"open_match_{match_id}")]
    ])

    try:
        await callback.message.edit_text(
            f"{header_text}\n⏳ *Прием прогнозов открыт на 10 часов!*\n\n"
            f"🏟 **{match_name}**\n\n"
            f"👇 *Нажмите кнопку ниже, чтобы сделать прогноз:*",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        await callback.answer("🔒 Свернуто", show_alert=False)
    except Exception:
        await callback.answer("⚠️ Ошибка.", show_alert=True)


@dp.callback_query(F.data.startswith("header_"))
async def process_header_click(callback: CallbackQuery):
    if callback.data == "header_main":
        await callback.answer("👆 Это блок основных исходов матча", show_alert=False)
    elif callback.data == "header_extra":
        await callback.answer("👇 Это блок дополнительных ставок", show_alert=False)


@dp.callback_query(F.data.startswith("bet_"))
async def process_bet(callback: CallbackQuery):
    parts = callback.data.split("_")
    match_id = int(parts[1])
    pred_type = parts[2]
    pred_value = "К1" if pred_type == "adv_К1" else ("К2" if pred_type == "adv_К2" else ("да" if pred_type != "main" else parts[3]))

    user_id = callback.from_user.id
    username = callback.from_user.full_name

    cursor.execute("SELECT status, created_at FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await callback.answer("❌ Матч не найден!", show_alert=True)
        return

    status, created_at_str = match[0], match[1]
    if status != "active":
        await callback.answer("❌ Прием прогнозов закрыт!", show_alert=True)
        return

    try:
        match_created_time = datetime.fromisoformat(created_at_str)
    except Exception:
        match_created_time = datetime.now()

    if datetime.now() - match_created_time > timedelta(hours=10):
        cursor.execute("UPDATE matches SET status = 'finished' WHERE id = ?", (match_id,))
        conn.commit()
        await callback.answer("⏳ Время вышло!", show_alert=True)
        return

    is_main = 1 if pred_type == "main" else 0

    cursor.execute(
        "SELECT prediction_type FROM predictions WHERE user_id = ? AND match_id = ? AND is_main = ?",
        (user_id, match_id, is_main),
    )
    if cursor.fetchone():
        await callback.answer("❌ Вы уже сделали этот тип ставки!", show_alert=True)
        return

    try:
        cursor.execute(
            "INSERT INTO predictions (user_id, match_id, prediction_type, prediction_value, is_main) VALUES (?, ?, ?, ?, ?)",
            (user_id, match_id, pred_type, pred_value, is_main),
        )
        cursor.execute("INSERT OR IGNORE INTO scores (user_id, username, points) VALUES (?, ?, 0.0)", (user_id, username))
        conn.commit()
        await callback.answer(f"✅ Ставка принята!\nВаш выбор: {pred_value}", show_alert=True)
    except Exception:
        await callback.answer("⚠️ Ошибка сохранения.", show_alert=True)


# --- ПРОМОТР ПРОГНОЗОВ (/votes) С ПОЛНЫМИ НАИМЕНОВАНИЯМИ ---
@dp.message(Command("votes"))
async def show_match_votes(message: Message):
    args = message.text.replace("/votes", "").strip().split()
    if not args or not args[0].isdigit():
        await message.answer("⚠️ Укажите ID матча! Пример: `/votes 1`", parse_mode="Markdown")
        return

    match_id = int(args[0])
    cursor.execute("SELECT match_name, is_test, is_playoff FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await message.answer("❌ Матч с таким ID не найден.")
        return

    match_name, is_test, is_playoff = match[0], match[1], match[2]
    test_label = " 🧪 [ТЕСТОВЫЙ]" if is_test else (" 🏆 [ПЛЕЙ-ОФФ]" if is_playoff else "")

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM predictions WHERE match_id = ?", (match_id,))
    total_users = cursor.fetchone()[0]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁 Показать все ставки (раскрыть)", callback_data=f"toggle_preds_{match_id}_open")]
    ])

    await message.answer(
        f"📋 <b>Прогнозы на матч{test_label} (ID: {match_id}):</b>\n"
        f"🏟 <i>{match_name}</i>\n\n"
        f"👥 Участников сделали прогноз: <b>{total_users}</b>\n"
        f"🔒 <i>Список ставок скрыт для компактности.</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("toggle_preds_"))
async def callback_toggle_preds(callback: CallbackQuery):
    parts = callback.data.split("_")
    match_id = int(parts[2])
    action = parts[3]

    cursor.execute("SELECT match_name, is_test, is_playoff FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await callback.answer("❌ Матч не найден!", show_alert=True)
        return

    match_name, is_test, is_playoff = match[0], match[1], match[2]
    test_label = " 🧪 [ТЕСТОВЫЙ]" if is_test else (" 🏆 [ПЛЕЙ-ОФФ]" if is_playoff else "")

    if action == "close":
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM predictions WHERE match_id = ?", (match_id,))
        total_users = cursor.fetchone()[0]

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👁 Показать все ставки (раскрыть)", callback_data=f"toggle_preds_{match_id}_open")]
        ])

        text = (
            f"📋 <b>Прогнозы на матч{test_label} (ID: {match_id}):</b>\n"
            f"🏟 <i>{match_name}</i>\n\n"
            f"👥 Участников сделали прогноз: <b>{total_users}</b>\n"
            f"🔒 <i>Список ставок скрыт для компактности.</i>"
        )
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer("🔒 Свернуто", show_alert=False)
        return

    cursor.execute("""
        SELECT p.user_id, s.username, p.prediction_type, p.prediction_value 
        FROM predictions p
        LEFT JOIN scores s ON p.user_id = s.user_id
        WHERE p.match_id = ?
    """, (match_id,))
    predictions = cursor.fetchall()

    if not predictions:
        await callback.answer("📋 Прогнозов пока нет.", show_alert=True)
        return

    users_data = {}
    type_labels = {
        "main": "Исход", 
        "adv": "Проход", 
        "no_goals": "Матч без голов (0:0)", 
        "pen": "Пенальти",
        "goal90": "Гол >90", 
        "btts": "Обе забьют", 
        "btts3": "Обе забьют 4+", 
        "ht00": "1-й тайм 0-0",
        "red": "Красная карточка", 
        "goal15": "Гол в первые 15 мин", 
        "goalboth": "Гол в обоих таймах",
        "over25": "Тотал больше 2.5", 
        "t1clean": "К1 сухой матч", 
        "t2clean": "К2 сухой матч",
        "goal30": "Гол в первые 30 мин", 
        "comeback": "Волевая победа", 
        "brace": "Дубль игрока",
        "ht_win": "Победа в 1-м тайме",  # Без сокращений
        "own_goal": "Автогол", 
        "var_cancel": "VAR / Отмена гола",
    }

    for uid, uname, p_type, p_val in predictions:
        name = uname if uname else f"ID: {uid}"
        if name not in users_data:
            users_data[name] = []
        clean_type = p_type.replace("adv_", "")
        label = type_labels.get(clean_type, clean_type)
        users_data[name].append(f"{label}: <b>{p_val}</b>")

    text = f"📋 <b>Полные прогнозы на матч{test_label} (ID: {match_id}):</b>\n🏟 <i>{match_name}</i>\n\n"
    for name, bets in users_data.items():
        text += f"👤 <b>{name}</b>:\n  • " + "\n  • ".join(bets) + "\n\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 Скрыть ставки (свернуть)", callback_data=f"toggle_preds_{match_id}_close")]
    ])

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer("🔓 Открыто!", show_alert=False)
    except Exception:
        await callback.answer("🔓 Открыто!", show_alert=False)


# --- ПОДВЕДЕНИЕ ИТОГОВ (/finish) С КЛЮЧОМ ht_win ---
@dp.message(Command("finish"))
async def finish_match(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав.")
        return

    args = message.text.replace("/finish", "").strip().split()
    if not args or not args[0].isdigit():
        await message.answer("⚠️ Укажите ID матча! Пример: `/finish 1 П1 2 4`", parse_mode="Markdown")
        return

    match_id = int(args[0])
    cursor.execute("SELECT match_name, mult_type, multiplier, status, is_test, is_playoff, extras_order FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await message.answer("❌ Матч с таким ID не найден.")
        return

    match_name, mult_type, multiplier, status, is_test, is_playoff, extras_order_str = match
    
    if status == 'finished':
        await message.answer(f"⚠️ Итоги для матча ID `{match_id}` уже подведены!\nЕсли вы ошиблись, сначала отмените их командой: `/unfinish {match_id}`", parse_mode="Markdown")
        return

    cursor.execute("UPDATE matches SET status = 'finished' WHERE id = ?", (match_id,))

    real_main = args[1] if len(args) > 1 else "П1"
    real_adv = None
    winning_numbers = set()

    start_index = 2
    if is_playoff and len(args) > 2 and args[2] in ["К1", "К2"]:
        real_adv = args[2]
        start_index = 3

    for arg in args[start_index:]:
        if arg.isdigit():
            winning_numbers.add(int(arg))

    extras_list = extras_order_str.split(",") if extras_order_str else []
    winning_extras = set()

    for num in winning_numbers:
        if is_playoff:
            if num == 1:
                winning_extras.add("adv_К1")
                continue
            elif num == 2:
                winning_extras.add("adv_К2")
                continue
            adjusted_num = num - 2
            if 1 <= adjusted_num <= len(extras_list):
                item_type = extras_list[adjusted_num - 1]
                winning_extras.add(item_type)
        else:
            if 1 <= num <= len(extras_list):
                item_type = extras_list[num - 1]
                winning_extras.add(item_type)

    cursor.execute("SELECT user_id, prediction_type, prediction_value FROM predictions WHERE match_id = ?", (match_id,))
    all_predictions = cursor.fetchall()

    user_bets = {}
    for uid, p_type, p_val in all_predictions:
        if uid not in user_bets:
            user_bets[uid] = {}
        user_bets[uid][p_type] = p_val

    results_text = (
        f"🏁 **ИТОГИ МАТЧА{' (ТЕСТОВЫЙ)' if is_test else (' (ПЛЕЙ-ОФФ)' if is_playoff else '')}: {match_name}**\n"
        f"⚽ Исход: **{real_main}**" + (f" | 🏆 Проход: **{real_adv}**" if is_playoff and real_adv else "") + f"\n\n"
    )

    if is_test:
        results_text += "🧪 Это был тестовый матч, очки не начислялись."
        conn.commit()
        await message.answer(results_text, parse_mode="Markdown")
        return

    current_month = datetime.now().strftime("%Y-%m")
    results_text += "🏆 **Начисленные баллы:**\n"
    total_winners = 0

    def calc_dynamic_points(p_type, base_pts, user_val, real_val):
        if user_val != real_val:
            return 0.0
        
        calculated = base_pts * multiplier if multiplier != 1.0 else float(base_pts)
        
        if mult_type in ["t1", "t2"]:
            if mult_type == "t1" and (p_type == "main" and user_val == "П1") or (p_type in ["adv_К1", "adv"] and user_val == "К1") or (p_type in ["t1clean"]):
                calculated *= 0.9
            elif mult_type == "t2" and (p_type == "main" and user_val == "П2") or (p_type in ["adv_К2", "adv"] and user_val == "К2") or (p_type in ["t2clean"]):
                calculated *= 0.9
            else:
                calculated *= 1.15

        final_pts = min(10.0, max(1.0, calculated))
        return final_pts

    for user_id, bets in user_bets.items():
        earned_points = 0.0
        details = []

        if "main" in bets:
            base_p = 5 if bets["main"] == "Ничья" else 3
            pts = calc_dynamic_points("main", base_p, bets["main"], real_main)
            if pts > 0:
                earned_points += pts
                p_fmt = int(pts) if pts.is_integer() else round(pts, 1)
                details.append(f"Исход +{p_fmt}")

        for adv_key in ["adv_К1", "adv_К2"]:
            if adv_key in bets and real_adv:
                pts = calc_dynamic_points(adv_key, 3, bets[adv_key], real_adv)
                if pts > 0:
                    earned_points += pts
                    p_fmt = int(pts) if pts.is_integer() else round(pts, 1)
                    details.append(f"Проход +{p_fmt}")

        # СЛОВАРЬ С ПОЛНЫМ КЛЮЧОМ ht_win
        extra_base_points = {
            "no_goals": 6, "pen": 3, "goal90": 4, "btts": 2, "btts3": 4,
            "ht00": 3, "red": 4, "goal15": 4, "goalboth": 3,
            "over25": 2, "t1clean": 3, "t2clean": 3,
            "goal30": 3, "comeback": 4, "brace": 4,
            "ht_win": 4, "own_goal": 5, "var_cancel": 2.5  # Полный ключ ht_win
        }

        for p_key, base_p in extra_base_points.items():
            if bets.get(p_key) == "да":
                if p_key in winning_extras:
                    pts = calc_dynamic_points(p_key, base_p, "да", "да")
                    earned_points += pts
                    p_fmt = int(pts) if pts.is_integer() else round(pts, 1)
                    details.append(f"{p_key} +{p_fmt}")

        if earned_points > 0:
            total_winners += 1
            cursor.execute("INSERT INTO match_rewards (match_id, user_id, points) VALUES (?, ?, ?)", (match_id, user_id, earned_points))
            cursor.execute("UPDATE scores SET points = points + ? WHERE user_id = ?", (earned_points, user_id))
            
            cursor.execute("SELECT username FROM scores WHERE user_id = ?", (user_id,))
            uname_row = cursor.fetchone()
            uname = uname_row[0] if uname_row else "Игрок"

            cursor.execute("""
                INSERT INTO monthly_scores (user_id, month, username, points) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, month) DO UPDATE SET points = points + ?, username = ?
            """, (user_id, current_month, uname, earned_points, earned_points, uname))
            conn.commit()

            cursor.execute("SELECT username, points FROM scores WHERE user_id = ?", (user_id,))
            user_info = cursor.fetchone()
            total_pts_str = int(user_info[1]) if user_info[1].is_integer() else round(user_info[1], 1)
            results_text += f"👤 {user_info[0]}: {', '.join(details)} (Всего: **{total_pts_str}** бал.)\n"

    conn.commit()
    if total_winners == 0:
        results_text += "Никто не набрал баллы в этом матче 😢"

    await message.answer(results_text, parse_mode="Markdown")


# --- ОТМЕНА ИТОГОВ (/unfinish) ---
@dp.message(Command("unfinish"))
async def unfinish_match(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав.")
        return

    args = message.text.replace("/unfinish", "").strip().split()
    if not args or not args[0].isdigit():
        await message.answer("⚠️ Укажите ID матча! Пример: `/unfinish 1`", parse_mode="Markdown")
        return

    match_id = int(args[0])
    cursor.execute("SELECT match_name, status FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await message.answer(f"❌ Матч с ID `{match_id}` не найден.", parse_mode="Markdown")
        return

    match_name, status = match
    if status != 'finished':
        await message.answer(f"⚠️ Матч ID `{match_id}` не числится завершенным.", parse_mode="Markdown")
        return

    cursor.execute("SELECT user_id, points FROM match_rewards WHERE match_id = ?", (match_id,))
    rewards = cursor.fetchall()

    current_month = datetime.now().strftime("%Y-%m")

    for user_id, pts in rewards:
        cursor.execute("UPDATE scores SET points = MAX(0, points - ?) WHERE user_id = ?", (pts, user_id))
        cursor.execute("UPDATE monthly_scores SET points = MAX(0, points - ?) WHERE user_id = ? AND month = ?", (pts, user_id, current_month))

    cursor.execute("DELETE FROM match_rewards WHERE match_id = ?", (match_id,))
    cursor.execute("UPDATE matches SET status = 'active' WHERE id = ?", (match_id,))
    conn.commit()

    await message.answer(
        f"🔄 **Итоги матча отменены!**\n"
        f"🏟 *{match_name}* (ID: {match_id})\n\n"
        f"✅ Начисленные за этот матч баллы успешно списаны со счетов игроков, а прием прогнозов возобновлен. Прогнозы и сам матч сохранены.",
        parse_mode="Markdown"
    )


@dp.message(Command("addpts"))
async def add_points(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.replace("/addpts", "").strip().split()
    if len(args) < 2:
        return
    try:
        points_to_add = float(args[-1])
    except ValueError:
        return
    target_username = " ".join(args[:-1])
    cursor.execute("SELECT user_id, username, points FROM scores WHERE username LIKE ?", (f"%{target_username}%",))
    user = cursor.fetchone()
    if not user:
        await message.answer(f"❌ Участник '{target_username}' не найден.")
        return
    user_id, found_username, current_points = user
    new_points = current_points + points_to_add
    current_month = datetime.now().strftime("%Y-%m")
    cursor.execute("UPDATE scores SET points = ? WHERE user_id = ?", (new_points, user_id))
    cursor.execute("""
        INSERT INTO monthly_scores (user_id, month, username, points) VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, month) DO UPDATE SET points = points + ?, username = ?
    """, (user_id, current_month, found_username, points_to_add, points_to_add, found_username))
    conn.commit()
    fmt = lambda v: int(v) if v.is_integer() else round(v, 1)
    await message.answer(f"✅ Игроку **{found_username}** изменено на `{fmt(new_points)}` бал.", parse_mode="Markdown")


@dp.message(Command("reset_scores"))
async def reset_scores(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    cursor.execute("UPDATE scores SET points = 0")
    cursor.execute("UPDATE monthly_scores SET points = 0")
    cursor.execute("DELETE FROM match_rewards")
    conn.commit()
    await message.answer("🔄 Все таблицы баллов обнулены!")


@dp.message(Command("clear_matches"))
async def clear_matches(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    cursor.execute("DELETE FROM predictions")
    cursor.execute("DELETE FROM match_rewards")
    cursor.execute("DELETE FROM matches")
