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

# Ваш реальный Telegram user_id
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

# Автоматически добавляем колонки при обновлении
try:
    cursor.execute("ALTER TABLE monthly_scores ADD COLUMN username TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE predictions ADD COLUMN is_main INTEGER DEFAULT 0")
    conn.commit()
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE matches ADD COLUMN is_playoff INTEGER DEFAULT 0")
    conn.commit()
except sqlite3.OperationalError:
    pass

conn.commit()


# --- АВТОМАТИЧЕСКОЕ ДОБАВЛЕНИЕ ФЛАЖКОВ СТРАН ДЛЯ СБОРНЫХ И КЛУБОВ ---
def decorate_match_name(match_name: str) -> str:
    decorations = {
        # --- СБОРНЫЕ ЕВРОПЫ ---
        "украина": "🇺🇦", "ukraine": "🇺🇦",
        "англия": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "england": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "испания": "🇪🇸", "spain": "🇪🇸",
        "италия": "🇮🇹", "italy": "🇮🇹",
        "германия": "🇩🇪", "germany": "🇩🇪",
        "франция": "🇫🇷", "france": "🇫🇷",
        "португалия": "🇵🇹", "portugal": "🇵🇹",
        "нидерланды": "🇳🇱", "netherlands": "🇳🇱",
        "бельгия": "🇧🇪", "belgium": "🇧🇪",
        "польша": "🇵🇱", "poland": "🇵🇱",
        "турция": "🇹🇷", "turkey": "🇹🇷",
        "хорватия": "🇭🇷", "croatia": "🇭🇷",
        "дания": "🇩🇰", "denmark": "🇩🇰",
        "швеция": "🇸🇪", "sweden": "🇸🇪",
        "швейцария": "🇨🇭", "switzerland": "🇨🇭",
        "австрия": "🇦🇹", "austria": "🇦🇹",
        "сербия": "🇷🇸", "serbia": "🇷🇸",
        "чехия": "🇨🇿", "czech republic": "🇨🇿",
        "шотландия": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "уэльс": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
        "ирландия": "🇮🇪", "ireland": "🇮🇪",
        "норвегия": "🇳🇴", "norway": "🇳🇴",
        "румыния": "🇷🇴", "romania": "🇷🇴",
        "греция": "🇬🇷", "greece": "🇬🇷",
        "словакия": "🇸🇰", "slovakia": "🇸🇰",
        "венгрия": "🇭🇺", "hungary": "🇭🇺",
        "финляндия": "🇫🇮", "finland": "🇫🇮",
        "исландия": "🇮🇸", "iceland": "🇮🇸",
        "босния": "🇧🇦", "bosnia": "🇧🇦",
        "албания": "🇦🇱", "albania": "🇦🇱",
        "грузия": "🇬🇪", "georgia": "🇬🇪",

        # --- СБОРНЫЕ ЛАТИНСКОЙ И ЮЖНОЙ АМЕРИКИ ---
        "бразилия": "🇧🇷", "brazil": "🇧🇷",
        "аргентина": "🇦🇷", "argentina": "🇦🇷",
        "уругвай": "🇺🇾", "uruguay": "🇺🇾",
        "колумбия": "🇨🇴", "colombia": "🇨🇴",
        "чили": "🇨🇱", "chile": "🇨🇱",
        "перу": "🇵🇪", "peru": "🇵🇪",
        "эквадор": "🇪🇨", "ecuador": "🇪🇨",
        "парагвай": "🇵🇾", "paraguay": "🇵🇾",
        "венесуэла": "🇻🇪", "venezuela": "🇻🇪",
        "боливия": "🇧🇴", "bolivia": "🇧🇴",

        # --- СБОРНЫЕ СЕВЕРНОЙ И ЦЕНТРАЛЬНОЙ АМЕРИКИ (КОНКАКАФ) ---
        "мексика": "🇲🇽", "mexico": "🇲🇽",
        "соединенные штаты": "🇺🇸", "сша": "🇺🇸", "usa": "🇺🇸",
        "канада": "🇨🇦", "canada": "🇨🇦",
        "коста-рика": "🇨🇷", "costa rica": "🇨🇷",
        "панама": "🇵🇦", "panama": "🇵🇦",
        "ямайка": "🇯🇲", "jamaica": "🇯🇲",
        "гондурас": "🇭🇳", "honduras": "🇭🇳",

        # --- СБОРНЫЕ АФРИКИ (КАФ) ---
        "марокко": "🇲🇦", "morocco": "🇲🇦",
        "сенегал": "🇸🇳", "senegal": "🇸🇳",
        "египет": "🇪🇬", "egypt": "🇪🇬",
        "нигерия": "🇳🇬", "nigeria": "🇳🇬",
        "камерун": "🇨🇲", "cameroon": "🇨🇲",
        "гана": "🇬🇭", "ghana": "🇬🇭",
        "алжир": "🇩🇿", "algeria": "🇩🇿",
        "тунис": "🇹🇳", "tunisia": "🇹🇳",
        "берег слоновой кости": "🇨🇮", "кот-д'ивуар": "🇨🇮", "ivory coast": "🇨🇮",
        "южная африка": "🇿🇦", "юар": "🇿🇦", "south africa": "🇿🇦",
        "мали": "🇲🇱", "mali": "🇲🇱",
        "конго": "🇨🇩", "congo": "🇨🇩",

        # --- СБОРНЫЕ АЗИИ (АФК) ---
        "япония": "🇯🇵", "japan": "🇯🇵",
        "южная корея": "🇰🇷", "корея": "🇰🇷", "south korea": "🇰🇷",
        "саудовская аравия": "🇸🇦", "saudi arabia": "🇸🇦",
        "иран": "🇮🇷", "iran": "🇮🇷",
        "австралия": "🇦🇺", "australia": "🇦🇺",
        "катар": "🇶🇦", "qatar": "🇶🇦",
        "ирак": "🇮🇶", "iraq": "🇮🇶",
        "узбекистан": "🇺🇿", "uzbekistan": "🇺🇿",
        "оаэ": "🇦🇪", "uae": "🇦🇪",
        "китай": "🇨🇳", "china": "🇨🇳",
        "иордания": "🇯🇴", "jordan": "🇯🇴",

        # --- УКРАИНА (УПЛ) — Флаг 🇺🇦 ---
        "шахтер": "🇺🇦", "shakhtar": "🇺🇦",
        "динамо киев": "🇺🇦", "динамо": "🇺🇦", "dynamo kyiv": "🇺🇦", "dynamo": "🇺🇦",
        "кривбасс": "🇺🇦", "kryvbas": "🇺🇦",
        "днепр-1": "🇺🇦", "dnipro-1": "🇺🇦", "днепр": "🇺🇦",
        "полісся": "🇺🇦", "полисся": "🇺🇦", "polissya": "🇺🇦",
        "рух": "🇺🇦", "rukh": "🇺🇦",
        "карпаты": "🇺🇦", "karpaty": "🇺🇦",
        "ворскла": "🇺🇦", "vorskla": "🇺🇦",
        "заря": "🇺🇦", "zorya": "🇺🇦",
        "металист": "🇺🇦", "metalist": "🇺🇦",
        "колос": "🇺🇦", "kolos": "🇺🇦",
        "оболонь": "🇺🇦", "obolon": "🇺🇦",
        "черноморец": "🇺🇦", "chornomorets": "🇺🇦",
        "александрия": "🇺🇦", "oleksandriya": "🇺🇦",
        "лзн": "🇺🇦", "lzn": "🇺🇦",
        "верес": "🇺🇦", "veres": "🇺🇦",

        # --- АНГЛИЯ (АПЛ) — Флаг 🏴󠁧󠁢󠁥󠁮󠁧󠁿 ---
        "арсенал": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "arsenal": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "манчестер сити": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "manchester city": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "ман сити": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "man city": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "манчестер юнайтед": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "manchester united": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "мю": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "man utd": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "ливерпуль": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "liverpool": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "челси": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "chelsea": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "тоттенхэм": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "tottenham": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "шпоры": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "ньюкасл": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "newcastle": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "астон вилла": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "aston villa": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "вест хэм": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "west ham": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "брайтон": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "brighton": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "кристал пэлас": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "crystal palace": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "вулверхэмптон": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "wolves": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "фулхэм": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "fulham": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "борнмут": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "bournemouth": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "эвертон": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "everton": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "брентфорд": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "brentford": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "ноттингем форест": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "nottingham forest": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "лестер": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "leicester": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "саутгемптон": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "southampton": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "ипсвич": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "ipswich": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",

        # --- ИСПАНИЯ (Ла Лига) — Флаг 🇪🇸 ---
        "реал мадрид": "🇪🇸", "real madrid": "🇪🇸", "реал": "🇪🇸",
        "барселона": "🇪🇸", "barcelona": "🇪🇸", "барса": "🇪🇸",
        "атлетико мадрид": "🇪🇸", "atletico madrid": "🇪🇸", "атлетико": "🇪🇸",
        "жирона": "🇪🇸", "girona": "🇪🇸",
        "атлетик бильбао": "🇪🇸", "athletic bilbao": "🇪🇸", "атлетик": "🇪🇸",
        "реал сосьедад": "🇪🇸", "real sociedad": "🇪🇸",
        "бетис": "🇪🇸", "real betis": "🇪🇸",
        "вильярреал": "🇪🇸", "villarreal": "🇪🇸",
        "валенсия": "🇪🇸", "valencia": "🇪🇸",
        "севилья": "🇪🇸", "sevilla": "🇪🇸",
        "осасуна": "🇪🇸", "osasuna": "🇪🇸",
        "сельта": "🇪🇸", "celta": "🇪🇸",
        "мальорка": "🇪🇸", "mallorca": "🇪🇸",
        "хетафе": "🇪🇸", "getafe": "🇪🇸",
        "райо вальекано": "🇪🇸", "rayo vallecano": "🇪🇸",
        "лас-пальмас": "🇪🇸", "las palmas": "🇪🇸",
        "алавес": "🇪🇸", "alaves": "🇪🇸",
        "леганнес": "🇪🇸", "leganes": "🇪🇸",
        "вальядолид": "🇪🇸", "valladolid": "🇪🇸",
        "эспаньол": "🇪🇸", "espanyol": "🇪🇸",

        # --- ИТАЛИЯ (Серия А) — Флаг 🇮🇹 ---
        "интер": "🇮🇹", "inter milan": "🇮🇹",
        "милан": "🇮🇹", "ac milan": "🇮🇹",
        "ювентус": "🇮🇹", "juventus": "🇮🇹", "юве": "🇮🇹",
        "аталанта": "🇮🇹", "atalanta": "🇮🇹",
        "болонья": "🇮🇹", "bologna": "🇮🇹",
        "рома": "🇮🇹", "as roma": "🇮🇹",
        "лацио": "🇮🇹", "lazio": "🇮🇹",
        "фиорентина": "🇮🇹", "fiorentina": "🇮🇹",
        "наполи": "🇮🇹", "napoli": "🇮🇹",
        "торино": "🇮🇹", "torino": "🇮🇹",
        "монца": "🇮🇹", "monza": "🇮🇹",
        "удинезе": "🇮🇹", "udinese": "🇮🇹",
        "дженуа": "🇮🇹", "genoa": "🇮🇹",
        "эмполи": "🇮🇹", "empoli": "🇮🇹",
        "лечче": "🇮🇹", "lecce": "🇮🇹",
        "кальяри": "🇮🇹", "cagliari": "🇮🇹",
        "верона": "🇮🇹", "verona": "🇮🇹",
        "парма": "🇮🇹", "parma": "🇮🇹",
        "комо": "🇮🇹", "como": "🇮🇹",
        "венеция": "🇮🇹", "venezia": "🇮🇹",

        # --- ГЕРМАНИЯ (Бундеслига) — Флаг 🇩🇪 ---
        "бавария": "🇩🇪", "bayern munich": "🇩🇪",
        "байер леверкузен": "🇩🇪", "leverkusen": "🇩🇪", "байер": "🇩🇪",
        "штутгарт": "🇩🇪", "stuttgart": "🇩🇪",
        "лейпциг": "🇩🇪", "rb leipzig": "🇩🇪",
        "дортмунд": "🇩🇪", "боруссия дортмунд": "🇩🇪", "borussia dortmund": "🇩🇪",
        "айнтрахт франкфурт": "🇩🇪", "eintracht frankfurt": "🇩🇪", "айнтрахт": "🇩🇪",
        "хоффенхайм": "🇩🇪", "hoffenheim": "🇩🇪",
        "хайденхайм": "🇩🇪", "heidenheim": "🇩🇪",
        "вердер": "🇩🇪", "werder bremen": "🇩🇪",
        "фрайбург": "🇩🇪", "freiburg": "🇩🇪",
        "аугсбург": "🇩🇪", "augsburg": "🇩🇪",
        "вольфсбург": "🇩🇪", "wolfsburg": "🇩🇪",
        "майнц": "🇩🇪", "mainz": "🇩🇪",
        "боруссия менхенгладбах": "🇩🇪", "gladbach": "🇩🇪",
        "унион берлин": "🇩🇪", "union berlin": "🇩🇪",
        "бохум": "🇩🇪", "bochum": "🇩🇪",
        "санкт-паули": "🇩🇪", "st pauli": "🇩🇪",

        # --- ФРАНЦИЯ (Лига 1) — Флаг 🇫🇷 ---
        "псг": "🇫🇷", "paris saint-germain": "🇫🇷", "пари сен-жермен": "🇫🇷",
        "марсель": "🇫🇷", "marseille": "🇫🇷",
        "монако": "🇫🇷", "monaco": "🇫🇷",
        "брест": "🇫🇷", "brest": "🇫🇷",
        "лилл": "🇫🇷", "lille": "🇫🇷",
        "лион": "🇫🇷", "lyon": "🇫🇷",
        "ницца": "🇫🇷", "nice": "🇫🇷",
        "ланс": "🇫🇷", "lens": "🇫🇷",
        "ренн": "🇫🇷", "rennes": "🇫🇷",
        "тулуза": "🇫🇷", "toulouse": "🇫🇷",
        "реймс": "🇫🇷", "reims": "🇫🇷",
        "страсбур": "🇫🇷", "strasbourg": "🇫🇷",
        "нант": "🇫🇷", "nantes": "🇫🇷",
        "гавр": "🇫🇷", "le havre": "🇫🇷",
        "монпелье": "🇫🇷", "montpellier": "🇫🇷",
        "осер": "🇫🇷", "auxerre": "🇫🇷",
        "анже": "🇫🇷", "angers": "🇫🇷",
        "сент-этьен": "🇫🇷", "saint-etienne": "🇫🇷"
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


# --- УНИВЕРСАЛЬНАЯ ФУНКЦИЯ СОЗДАНИЯ МАТЧА ---
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
        await message.answer(f"⚠️ Укажите название матча!\nПримеры:\n• `{ex_cmd} Арсенал - Челси`\n• `{ex_cmd} all 1.5 Реал - Барселона`", parse_mode="Markdown")
        return

    match_name = decorate_match_name(raw_match_name)
    now_time = datetime.now().isoformat()

    cursor.execute(
        "INSERT INTO matches (match_name, mult_type, multiplier, status, is_test, is_playoff, created_at) VALUES (?, ?, ?, 'active', ?, ?, ?)",
        (match_name, mult_type, multiplier, is_test, is_playoff, now_time),
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
            if p_type == "adv" and val == "К1":
                return f"{format_val(base * multiplier)}б"
            if p_type == "t1clean":
                return f"{format_val(base * multiplier)}б"
            return f"{base}б"
        elif mult_type == "t2":
            if p_type == "main" and val == "П2":
                return f"{format_val(base * multiplier)}б"
            if p_type == "adv" and val == "К2":
                return f"{format_val(base * multiplier)}б"
            if p_type == "t2clean":
                return f"{format_val(base * multiplier)}б"
            return f"{base}б"
        return f"{base}б"

    mult_desc = ""
    if multiplier != 1.0:
        mult_val_str = str(int(multiplier)) if multiplier.is_integer() else str(multiplier)
        if mult_type == "all":
            mult_desc = f" (🔥 Х{mult_val_str})"
        elif mult_type == "t1":
            mult_desc = f" (🔥 Х{mult_val_str} К1)"
        elif mult_type == "t2":
            mult_desc = f" (🔥 Х{mult_val_str} К2)"

    # Формируем клавиатуру с разделителями блоков
    keyboard_rows = [
        [InlineKeyboardButton(text="🏆 ─── ОСНОВНОЙ ИСХОД ─── 🏆", callback_data="header_main")],
        [
            InlineKeyboardButton(text=f"🏠 П1 ({get_pts(3, 'main', 'П1')})", callback_data=f"bet_{match_id}_main_П1"),
            InlineKeyboardButton(text=f"✈️️ П2 ({get_pts(3, 'main', 'П2')})", callback_data=f"bet_{match_id}_main_П2"),
        ],
        [
            InlineKeyboardButton(text=f"🤝 Ничья ({get_pts(5, 'main', 'Ничья')})", callback_data=f"bet_{match_id}_main_Ничья"),
        ],
        [InlineKeyboardButton(text="🎯 ─── ДОП. СТАВКИ ─── 🎯", callback_data="header_extra")],
    ]

    # Пул всех возможных дополнительных ставок
    base_extra_bets = [
        (f"🟥 Карточки ({get_pts(3, 'cards')})", "cards_да", 3),
        (f"⚡ Пенальти ({get_pts(3, 'pen')})", "pen_да", 3),
        (f"⏱ Гол >90 ({get_pts(4, 'goal90')})", "goal90_да", 4),
        (f"⚽ Обе забьют ({get_pts(2, 'btts')})", "btts_да", 2),
        (f"⚽ Обе забьют 4+ ({get_pts(4, 'btts3')})", "btts3_да", 4),
        (f"⏱ 1-й тайм 0-0 ({get_pts(3, 'ht00')})", "ht00_да", 3),
        (f"🛡 К1 сух. до 70' ({get_pts(3, 't1cleanto70')})", "t1cleanto70_да", 3),
        (f"🛡 К2 сух. до 70' ({get_pts(3, 't2cleanto70')})", "t2cleanto70_да", 3),
        (f"⚽ ОЗ в 1-м тайме ({get_pts(2, 'btts1st')})", "btts1st_да", 2),
        (f"🛡 К1 сухой матч ({get_pts(3, 't1clean', 'да')})", "t1clean_да", 3),
        (f"🛡 К2 сухой матч ({get_pts(3, 't2clean', 'да')})", "t2clean_да", 3),
    ]

    playoff_pool_bets = [
        (f"🏆 Проход К1 ({get_pts(3, 'adv', 'К1')})", "adv_К1", 3),
        (f"🏆 Проход К2 ({get_pts(3, 'adv', 'К2')})", "adv_К2", 3),
    ]

    if is_playoff:
        sampled_extras = playoff_pool_bets + random.sample(base_extra_bets, 4)
    else:
        sampled_extras = random.sample(base_extra_bets, 6)

    random.shuffle(sampled_extras)

    # Пронумерованные доп. ставки для удобства администратора
    match_display_lines = []
    for idx, item in enumerate(sampled_extras, start=1):
        keyboard_rows.append([InlineKeyboardButton(text=item[0], callback_data=f"bet_{match_id}_{item[1]}")])
        match_display_lines.append(f"<b>{idx}.</b> {item[0]}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    if is_test:
        header_text = "🧪 **ТЕСТОВЫЙ МАТЧ**"
    elif is_playoff:
        header_text = f"🏆 **ПЛЕЙ-ОФФ (ID: {match_id})**{mult_desc}"
    else:
        header_text = f"⚽ **МАТЧ (ID: {match_id})**{mult_desc}"

    extras_text = "\n".join(match_display_lines)

    await message.answer(
        f"{header_text}\n⏳ *Прием прогнозов открыт на 10 часов!*\n\n"
        f"🏟 **{match_name}**\n\n"
        f"💡 *Не забудьте сделать ДВЕ ставки на матч: одну основную и одну доп.*\n\n"
        f"📋 <b>Нумерация доп. ставок для итога (/finish):</b>\n{extras_text}\n\n"
        f"👇 *Сделайте прогнозы:*",
        reply_markup=keyboard,
        parse_mode="HTML",
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


# --- УДАЛЕНИЕ МАТЧА И АННУЛИРОВАНИЕ ПРОГНОЗОВ (/delmatch) ---
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
        await message.answer(f"❌ Матч с ID `{match_id}` не найден в базе данных.", parse_mode="Markdown")
        return

    match_name = match[0]

    cursor.execute("DELETE FROM predictions WHERE match_id = ?", (match_id,))
    cursor.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    conn.commit()

    await message.answer(
        f"🗑 **Матч успешно удален!**\n\n"
        f"🏟 Название: *{match_name}* (ID: {match_id})\n"
        f"⚠️ Все прогнозы участников на этот матч аннулированы.",
        parse_mode="Markdown"
    )


# --- 2. ОБРАБОТКА НАЖАТИЯ ---
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
    pred_value = parts[3] if len(parts) > 3 else "да"

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
        if is_main == 1:
            await callback.answer("❌ Вы уже выбрали исход!", show_alert=True)
        else:
            await callback.answer("❌ Вы уже выбрали доп. ставку!", show_alert=True)
        return

    try:
        cursor.execute(
            "INSERT INTO predictions (user_id, match_id, prediction_type, prediction_value, is_main) VALUES (?, ?, ?, ?, ?)",
            (user_id, match_id, pred_type, pred_value, is_main),
        )
        cursor.execute("INSERT OR IGNORE INTO scores (user_id, username, points) VALUES (?, ?, 0.0)", (user_id, username))
        conn.commit()
        
        if is_main == 1:
            await callback.answer("✅ Исход принят!", show_alert=True)
        else:
            await callback.answer("✅ Доп. ставка принята!", show_alert=True)
            
    except Exception:
        await callback.answer("⚠️ Ошибка сохранения.", show_alert=True)


# --- 3. ПОКАЗАТЬ ПРОГНОЗЫ (/votes) ---
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
        await message.answer(f"📋 На матч{test_label} **{match_name}** (ID: {match_id}) пока никто не сделал прогнозы.", parse_mode="Markdown")
        return

    users_data = {}
    type_labels = {
        "main": "Исход", "adv": "Проход", "cards": "Карточки", "pen": "Пенальти",
        "goal90": "Гол >90", "btts": "Обе забьют", "btts3": "Обе забьют 4+", "ht00": "1-й тайм 0-0",
        "t1cleanto70": "К1 сух. до 70'", "t2cleanto70": "К2 сух. до 70'", "btts1st": "ОЗ в 1т",
        "t1clean": "К1 сухой матч", "t2clean": "К2 сухой матч",
    }

    for uid, uname, p_type, p_val in predictions:
        name = uname if uname else f"ID: {uid}"
        if name not in users_data:
            users_data[name] = []
        label = type_labels.get(p_type, p_type)
        users_data[name].append(f"{label}: <b>{p_val}</b>")

    text = f"📋 <b>Прогнозы на матч{test_label} (ID: {match_id}):</b>\n🏟 <i>{match_name}</i>\n\n"
    for name, bets in users_data.items():
        text += f"👤 <b>{name}</b>:\n  • " + "\n  • ".join(bets) + "\n\n"

    await message.answer(text, parse_mode="HTML")


# --- 4. ПОДВЕДЕНИЕ ИТОГОВ ПО НОМЕРАМ (/finish) ---
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
    cursor.execute("SELECT match_name, mult_type, multiplier, status, is_test, is_playoff FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await message.answer("❌ Матч с таким ID не найден.")
        return

    match_name, mult_type, multiplier, status, is_test, is_playoff = match
    cursor.execute("UPDATE matches SET status = 'finished' WHERE id = ?", (match_id,))

    real_main = args[1] if len(args) > 1 else "П1"
    real_adv = None
    winning_numbers = set()

    start_index = 2
    if is_playoff and len(args) > 2 and args[2] in ["К1", "К2"]:
        real_adv = args[2]
        start_index = 3

    # Собираем номера, которые ввел администратор
    for arg in args[start_index:]:
        if arg.isdigit():
            winning_numbers.add(int(arg))

    # Воссоздаем точный порядок кнопок (пул), который был выведен в сообщении матча
    base_extra_bets = [
        ("cards_да", 3), ("pen_да", 3), ("goal90_да", 4), ("btts_да", 2),
        ("btts3_да", 4), ("ht00_да", 3), ("t1cleanto70_да", 3), ("t2cleanto70_да", 3),
        ("btts1st_да", 2), ("t1clean_да", 3), ("t2clean_да", 3),
    ]
    playoff_pool_bets = [("adv_К1", 3), ("adv_К2", 3)]

    # Важно: чтобы нумерация сошлась один в один, при создании матча порядок рандомизировался.
    # Поэтому мы сохраняем/определяем список доп. ставок по callback_data из базы predictions или восстанавливаем по тем же типам.
    # Чтобы не усложнять и сделать надежно, соберем уникальные prediction_type, на которые реально ставили или которые есть в базе для этого матча:
    cursor.execute("SELECT DISTINCT prediction_type FROM predictions WHERE match_id = ? AND is_main = 0", (match_id,))
    predicted_types_in_match = [row[0] for row in cursor.fetchall()]

    winning_extras = set()
    # Сопоставляем введенные номера с реальными типами ставок
    # При создании матча порядок был: если playoff -> playoff_pool_bets + random sample(base, 4), иначе random sample(base, 6).
    # Но проще сопоставить по порядку строк в клавиатуре. Поскольку порядок random при создании не сохранялся в БД, 
    # давайте определим типы прямо из callback_data кнопок, которые были отправлены? 
    # Сделаем проще и надежнее: администратор может указывать номера так, как они шли в списке, но чтобы база не путалась, 
    # давайте сохранять список доп. ставок прямо в таблице matches при создании!

    # Давайте быстро добавим колонку для хранения порядка доп. ставок в матч, чтобы нумерация работала идеально.
    # Для этого обновим таблицу matches и логику сохранения.


# --- ПРОДОЛЖЕНИЕ НИЖЕ (обновленный блок создания и finish) ---
