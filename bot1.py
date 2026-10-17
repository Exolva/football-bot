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
        ("⏱ Победа в 1-м тайме", "ht_win", 4),
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
        "ht_win": ("⏱ Победа в 1-м тайме", 4),
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
