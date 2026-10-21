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
    is_admin_match INTEGER DEFAULT 0,
    admin_stake REAL DEFAULT 1.0,
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
    stake_paid REAL DEFAULT 0,
    is_main INTEGER,
    UNIQUE(user_id, match_id, prediction_type, prediction_value)
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
    "ALTER TABLE predictions ADD COLUMN stake_paid REAL DEFAULT 0",
    "ALTER TABLE matches ADD COLUMN is_playoff INTEGER DEFAULT 0",
    "ALTER TABLE matches ADD COLUMN is_admin_match INTEGER DEFAULT 0",
    "ALTER TABLE matches ADD COLUMN admin_stake REAL DEFAULT 1.0",
    "ALTER TABLE matches ADD COLUMN extras_order TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_match_pred ON predictions(user_id, match_id, prediction_type, prediction_value)"
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
async def handle_match_creation(message: Message, is_test: int = 0, is_playoff: int = 0, is_admin_match: int = 0):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав для создания матчей.")
        return

    if is_admin_match:
        cmd_prefix = "/adminmatch"
    else:
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
        ex_cmd = "/adminmatch" if is_admin_match else ("/testmatch" if is_test else ("/playoff" if is_playoff else "/match"))
        await message.answer(f"⚠️ Укажите название матча!\nПример: `{ex_cmd} Арсенал - Челси`", parse_mode="Markdown")
        return

    match_name = decorate_match_name(raw_match_name)
    now_time = datetime.now().isoformat()

    base_extra_bets = [
        ("🛡 Матч без голов (0:0)", "no_goals", 6),
        ("⚡ Пенальти", "pen", 3),
        ("⏱ Гол >90", "goal90", 4),
        ("⚽ Обе забьют", "btts", 2),
        ("🥅 Тотал больше 4.5", "over45", 6),
        ("🥅 Тотал больше 3.5", "over35", 4),
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

    # Для обычных матчей — 8 доп. ставок. Для плей-офф — 2 на проход + 6 случайных из базы.
    if is_playoff:
        sampled_extras = playoff_pool_bets + random.sample(base_extra_bets, 6)
        random.shuffle(sampled_extras)
    else:
        sampled_extras = random.sample(base_extra_bets, 8)

    extras_order_str = ",".join([item[1] for item in sampled_extras])

    cursor.execute(
        "INSERT INTO matches (match_name, mult_type, multiplier, status, is_test, is_playoff, is_admin_match, admin_stake, extras_order, created_at) VALUES (?, ?, ?, 'active', ?, ?, ?, 1.0, ?, ?)",
        (match_name, mult_type, multiplier, is_test, is_playoff, is_admin_match, extras_order_str, now_time),
    )
    conn.commit()
    match_id = cursor.lastrowid

    mult_desc = ""
    if multiplier != 1.0:
        m_str = str(int(multiplier)) if multiplier.is_integer() else str(multiplier)
        mult_desc = f" (🔥 Х{m_str})"

    stake_desc = "\n👑 **МАТЧ ОТ АДМИНА (РИСК)**\n⚖️ Доступно: 1 основной исход и ровно **1 доп. ставка** из списка." if is_admin_match else ""

    if is_test:
        header_text = "🧪 **ТЕСТОВЫЙ МАТЧ**"
    elif is_playoff:
        header_text = f"🏆 **ПЛЕЙ-ОФФ (ID: {match_id})**{mult_desc}"
    elif is_admin_match:
        header_text = f"👑 **МАТЧ ОТ АДМИНА (ID: {match_id})**{mult_desc}"
    else:
        header_text = f"⚽ **МАТЧ (ID: {match_id})**{mult_desc}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Сделать прогноз (открыть ставки)", callback_data=f"open_match_{match_id}")]
    ])

    await message.answer(
        f"{header_text}{stake_desc}\n⏳ *Прием прогнозов открыт на 10 часов!*\n\n"
        f"🏟 **{match_name}**\n\n"
        f"👇 *Нажмите кнопку ниже, чтобы сделать прогноз:*",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@dp.message(Command("match"))
async def create_match(message: Message):
    await handle_match_creation(message, is_test=0, is_playoff=0, is_admin_match=0)

@dp.message(Command("testmatch"))
async def create_test_match(message: Message):
    await handle_match_creation(message, is_test=1, is_playoff=0, is_admin_match=0)

@dp.message(Command("playoff"))
async def create_playoff_match(message: Message):
    await handle_match_creation(message, is_test=0, is_playoff=1, is_admin_match=0)

@dp.message(Command("adminmatch"))
async def create_admin_match(message: Message):
    await handle_match_creation(message, is_test=0, is_playoff=0, is_admin_match=1)


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
    cursor.execute("SELECT match_name, mult_type, multiplier, is_test, is_playoff, is_admin_match, extras_order, created_at, status FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await callback.answer("❌ Матч не найден!", show_alert=True)
        return

    match_name, mult_type, multiplier, is_test, is_playoff, is_admin_match, extras_order_str, created_at_str, status = match
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
        if not is_admin_match and mult_type in ["t1", "t2"]:
            if mult_type == "t1" and (p_type in ["t1clean"] or val == "П1" or val == "К1"):
                calculated *= 0.9
            elif mult_type == "t2" and (p_type in ["t2clean"] or val == "П2" or val == "К2"):
                calculated *= 0.9
            else:
                calculated *= 1.15
        final_pts = min(10.0, max(1.0, calculated)) if not is_admin_match else max(1.0, calculated)
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
        [InlineKeyboardButton(text="🎯 ─── ДОП. СТАВКИ (выберите 1) ─── 🎯", callback_data="header_extra")],
    ]

    base_extra_dict = {
        "no_goals": ("🛡 Матч без голов (0:0)", 6),
        "pen": ("⚡ Пенальти", 3),
        "goal90": ("⏱ Гол >90", 4),
        "btts": ("⚽ Обе забьют", 2),
        "over45": ("🥅 Тотал больше 4.5", 6),
        "over35": ("🥅 Тотал больше 3.5", 4),
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
    
    for idx, raw_type in enumerate(extras_list, start=1):
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
    elif is_admin_match:
        header_text = f"👑 **МАТЧ ОТ АДМИНА (ID: {match_id})**{mult_desc}"
    else:
        header_text = f"⚽ **МАТЧ (ID: {match_id})**{mult_desc}"

    stake_note = "\n💰 Доступно: 1 основной исход и 1 доп. ставка." if is_admin_match else ""
    status_note = "\n⚠️ *Прием
