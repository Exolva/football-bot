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
            InlineKeyboardButton(text=f"✈️ П2 ({get_pts(3, 'main', 'П2')})", callback_data=f"bet_{match_id}_main_П2"),
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

    # Размещаем каждую дополнительную ставку ровно по 1 в ряд
    for item in sampled_extras:
        keyboard_rows.append([InlineKeyboardButton(text=item[0], callback_data=f"bet_{match_id}_{item[1]}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    if is_test:
        header_text = "🧪 **ТЕСТОВЫЙ МАТЧ**"
    elif is_playoff:
        header_text = f"🏆 **ПЛЕЙ-ОФФ (ID: {match_id})**{mult_desc}"
    else:
        header_text = f"⚽ **МАТЧ (ID: {match_id})**{mult_desc}"

    await message.answer(
        f"{header_text}\n⏳ *Прием прогнозов открыт на 10 часов!*\n\n"
        f"🏟 **{match_name}**\n\n"
        f"💡 *Не забудьте сделать ДВЕ ставки на матч: одну основную и одну доп.*\n\n"
        f"👇 *Сделайте прогнозы:*",
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

    # Удаляем прогнозы участников для этого матча и сам матч
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


# --- 4. ПОДВЕДЕНИЕ ИТОГОВ (/finish) ---
@dp.message(Command("finish"))
async def finish_match(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав.")
        return

    args = message.text.replace("/finish", "").strip().split()
    if not args or not args[0].isdigit():
        await message.answer("⚠️ Укажите ID матча!", parse_mode="Markdown")
        return

    match_id = int(args[0])
    cursor.execute("SELECT match_name, mult_type, multiplier, status, is_test, is_playoff FROM matches WHERE id = ?", (match_id,))
    match = cursor.fetchone()
    if not match:
        await message.answer("❌ Матч с таким ID не найден.")
        return

    match_name, mult_type, multiplier, status, is_test, is_playoff = match
    cursor.execute("UPDATE matches SET status = 'finished' WHERE id = ?", (match_id,))

    cursor.execute("SELECT user_id, prediction_type, prediction_value FROM predictions WHERE match_id = ?", (match_id,))
    all_predictions = cursor.fetchall()

    user_bets = {}
    for uid, p_type, p_val in all_predictions:
        if uid not in user_bets:
            user_bets[uid] = {}
        user_bets[uid][p_type] = p_val

    real_main = args[1] if len(args) > 1 else "П1"
    real_cards = args[2].lower() if len(args) > 2 else "нет"
    real_pen = args[3].lower() if len(args) > 3 else "нет"
    real_goal90 = args[4].lower() if len(args) > 4 else "нет"
    real_btts = args[5].lower() if len(args) > 5 else "нет"
    real_btts3 = args[6].lower() if len(args) > 6 else "нет"
    real_ht00 = args[7].lower() if len(args) > 7 else "нет"
    real_t1to70 = args[8].lower() if len(args) > 8 else "нет"
    real_t2to70 = args[9].lower() if len(args) > 9 else "нет"
    real_btts1st = args[10].lower() if len(args) > 10 else "нет"
    real_t1clean = args[11].lower() if len(args) > 11 else "нет"
    real_t2clean = args[12].lower() if len(args) > 12 else "нет"
    real_adv = args[13] if is_playoff and len(args) > 13 else None

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

    def calc_points(p_type, base_pts, user_val, real_val):
        if user_val != real_val:
            return 0.0
        apply_mult = False
        if mult_type == "all":
            apply_mult = True
        elif mult_type == "t1":
            if (p_type == "main" and user_val == "П1") or (p_type == "adv" and user_val == "К1") or (p_type == "t1clean") or (p_type == "t1cleanto70"):
                apply_mult = True
        elif mult_type == "t2":
            if (p_type == "main" and user_val == "П2") or (p_type == "adv" and user_val == "К2") or (p_type == "t2clean") or (p_type == "t2cleanto70"):
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
                details.append(f"Исход +{int(pts) if pts.is_integer() else round(pts, 1)}")

        if "adv" in bets and real_adv:
            pts = calc_points("adv", 3, bets["adv"], real_adv)
            if pts > 0:
                earned_points += pts
                details.append(f"Проход +{int(pts) if pts.is_integer() else round(pts, 1)}")

        checks = [
            ("cards", real_cards, 3),
            ("pen", real_pen, 3),
            ("goal90", real_goal90, 4),
            ("btts", real_btts, 2),
            ("btts3", real_btts3, 4),
            ("ht00", real_ht00, 3),
            ("t1cleanto70", real_t1to70, 3),
            ("t2cleanto70", real_t2to70, 3),
            ("btts1st", real_btts1st, 2),
            ("t1clean", real_t1clean, 3),
            ("t2clean", real_t2clean, 3),
        ]

        for p_key, real_val, base_p in checks:
            if bets.get(p_key) == "да" and real_val == "да":
                pts = calc_points(p_key, base_p, "да", real_val)
                earned_points += pts
                details.append(f"{p_key} +{int(pts) if pts.is_integer() else round(pts, 1)}")

        if earned_points > 0:
            total_winners += 1
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

    if total_winners == 0:
        results_text += "Никто не набрал баллы в этом матче 😢"

    await message.answer(results_text, parse_mode="Markdown")


# --- 5. РУЧНОЕ НАЧИСЛЕНИЕ БАЛЛОВ (/addpts) ---
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


# --- 6. СБРОС ТАБЛИЦЫ (/reset_scores) ---
@dp.message(Command("reset_scores"))
async def reset_scores(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    cursor.execute("UPDATE scores SET points = 0")
    cursor.execute("UPDATE monthly_scores SET points = 0")
    conn.commit()
    await message.answer("🔄 Все таблицы баллов обнулены!")


# --- 7. ОЧИСТКА МАТЧЕЙ (/clear_matches) ---
@dp.message(Command("clear_matches"))
async def clear_matches(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    cursor.execute("DELETE FROM predictions")
    cursor.execute("DELETE FROM matches")
    conn.commit()
    await message.answer("🗑 База данных матчей очищена!")


# --- 8. ТАБЛИЦЫ ЛИДЕРОВ: ЗА МЕСЯЦ И ЗА ВСЁ ВРЕМЯ (/table) ---
@dp.message(Command("table"))
async def show_table(message: Message):
    current_month = datetime.now().strftime("%Y-%m")
    
    cursor.execute("SELECT username, points FROM scores ORDER BY points DESC LIMIT 10")
    top_all = cursor.fetchall()

    cursor.execute("SELECT username, points FROM monthly_scores WHERE month = ? ORDER BY points DESC LIMIT 10", (current_month,))
    top_month = cursor.fetchall()

    if not top_all and not top_month:
        await message.answer("📊 Таблицы лидеров пока пусты.", parse_mode="HTML")
        return

    text = f"📅 <b>СТАТИСТИКА ЗА ТЕКУЩИЙ МЕСЯЦ ({current_month})</b>\n"
    if top_month:
        for i, (uname, pts) in enumerate(top_month, start=1):
            p_str = int(pts) if pts.is_integer() else round(pts, 1)
            name_display = uname if uname else "Игрок"
            text += f"{i}. {name_display} — <b>{p_str}</b> бал.\n"
    else:
        text += "<i>В этом месяце еще нет начислений.</i>\n"

    text += "\n🏆 <b>ТАБЛИЦА ЛИДЕРОВ ЗА ВСЁ ВРЕМЯ</b>\n"
    if top_all:
        for i, (uname, pts) in enumerate(top_all, start=1):
            p_str = int(pts) if pts.is_integer() else round(pts, 1)
            name_display = uname if uname else "Игрок"
            text += f"{i}. {name_display} — <b>{p_str}</b> бал.\n"
    else:
        text += "<i>Пусто.</i>"

    await message.answer(text, parse_mode="HTML")


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
