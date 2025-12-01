import discord
from discord.ext import commands, tasks
import json
import os
import random
from discord.ui import Button, View
import time
import io
import asyncio
from datetime import datetime

TOKEN = os.getenv("TOKEN")
DATA_FILE = "casino_data.json"
JOINS_CHANNEL = 1443625716859273406
LEAVES_CHANNEL = 1443625744793342132
SUSPICIOUS_SERVER = 1140681007197073468


# Categories where commands are disabled
DISABLED_CATEGORIES = set([1431610646654488661])

# Channel used for JSON backups
BACKUP_CHANNEL_ID = 1431610647921295451


# ---------------------- INTENTS ---------------------- #
intents = discord.Intents.all()   # <--- this enables EVERYTHING
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------------- CONSTANTS ---------------------- #
MAX_BET = 200_000_000  # 200m
LOTTERY_BONUS = 0.10   # 10% extra on the pot for lottery winner

# ---------------------- CHEST CONFIG ---------------------- #
COMMON_PRICE = 25_000_000
COMMON_REWARD_AMOUNTS = [15_000_000, 30_000_000, 40_000_000, 50_000_000]
COMMON_REWARD_CHANCES = [50, 30, 15, 5]

RARE_PRICE = 75_000_000
RARE_REWARD_AMOUNTS = [50_000_000, 80_000_000, 100_000_000, 125_000_000]
RARE_REWARD_CHANCES = [50, 30, 15, 5]

EPIC_PRICE = 100_000_000
EPIC_REWARD_AMOUNTS = [75_000_000, 100_000_000, 125_000_000, 150_000_000]
EPIC_REWARD_CHANCES = [50, 30, 15, 5]

LEGENDARY_PRICE = 250_000_000
LEGENDARY_REWARD_AMOUNTS = [200_000_000, 250_000_000, 275_000_000, 350_000_000]
LEGENDARY_REWARD_CHANCES = [50, 30, 15, 5]

MYTHIC_PRICE = 500_000_000
MYTHIC_REWARD_AMOUNTS = [400_000_000, 500_000_000, 550_000_000, 625_000_000]
MYTHIC_REWARD_CHANCES = [50, 30, 15, 5]

GALAXY_PRICE = 1_000_000_000
GALAXY_REWARD_AMOUNTS = [800_000_000, 1_000_000_000, 1_100_000_000, 1_250_000_000]
GALAXY_REWARD_CHANCES = [50, 30, 15, 5]

CHEST_CONFIG = {
    "common": {
        "name": "Common Chest",
        "emoji": "🟢",
        "price": COMMON_PRICE,
        "rewards": COMMON_REWARD_AMOUNTS,
        "chances": COMMON_REWARD_CHANCES,
    },
    "rare": {
        "name": "Rare Chest",
        "emoji": "🔵",
        "price": RARE_PRICE,
        "rewards": RARE_REWARD_AMOUNTS,
        "chances": RARE_REWARD_CHANCES,
    },
    "epic": {
        "name": "Epic Chest",
        "emoji": "🟣",
        "price": EPIC_PRICE,
        "rewards": EPIC_REWARD_AMOUNTS,
        "chances": EPIC_REWARD_CHANCES,
    },
    "legendary": {
        "name": "Legendary Chest",
        "emoji": "🟡",
        "price": LEGENDARY_PRICE,
        "rewards": LEGENDARY_REWARD_AMOUNTS,
        "chances": LEGENDARY_REWARD_CHANCES,
    },
    "mythic": {
        "name": "Mythic Chest",
        "emoji": "🔴",
        "price": MYTHIC_PRICE,
        "rewards": MYTHIC_REWARD_AMOUNTS,
        "chances": MYTHIC_REWARD_CHANCES,
    },
    "galaxy": {
        "name": "Galaxy Chest",
        "emoji": "🌌",
        "price": GALAXY_PRICE,
        "rewards": GALAXY_REWARD_AMOUNTS,
        "chances": GALAXY_REWARD_CHANCES,
    },
}

CHEST_ORDER = ["common", "rare", "epic", "legendary", "mythic", "galaxy"]

# ---------------------- DATA MANAGEMENT ---------------------- #
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({}, f)


def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=4)


data = load_data()
data.setdefault("_device_fingerprints", {})
device_fp = data["_device_fingerprints"]


# ---------------------- HELPERS ---------------------- #



# ---------------------- FREE vs GAMBLE TRACKING (35% IDEA) ---------------------- #

FREE_SOURCES = {"daily", "work", "invite_reward", "admin_give", "dropbox"}
GAMBLE_GAMES = {"coinflip", "slots", "mines", "tower", "blackjack"}


def compute_gamble_ratio(user_id):
    """
    Free kaynaklardan (daily, work, admin_give, invite, dropbox) gelen toplam kazanç
    ve gambling oyunlarında (coinflip, slots, mines, tower, blackjack) harcanan toplam bahsi hesaplar.

    Dönüş:
      free_total, gambled_total, ratio (0–1 arası)
    """
    ensure_user(user_id)
    hist = data[str(user_id)].get("history", [])

    free_total = 0
    gambled_total = 0

    for e in hist:
        game = e.get("game", "")
        bet = e.get("bet", 0) or 0
        earned = e.get("earned", 0) or 0

        # FREE GELİR
        if game in FREE_SOURCES and earned > 0:
            free_total += earned

        # GAMBLE BAHİS
        if game in GAMBLE_GAMES and bet > 0:
            gambled_total += bet

    ratio = (gambled_total / free_total) if free_total > 0 else 0
    return free_total, gambled_total, ratio



def fmt(n):
    """
    Format numbers like:
    1_234 -> "1.23k"
    1_000_000 -> "1m"
    1_250_000_000 -> "1.25b"
    50 -> "50"
    """
    try:
        n = int(round(float(n)))
    except Exception:
        return str(n)

    if n >= 1_000_000_000:
        v = n / 1_000_000_000
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return f"{s}b"
    if n >= 1_000_000:
        v = n / 1_000_000
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return f"{s}m"
    if n >= 1_000:
        v = n / 1_000
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return f"{s}k"
    return str(n)


GALAXY_COLORS = [
    discord.Color.from_rgb(138, 43, 226),
    discord.Color.from_rgb(75, 0, 130),
    discord.Color.from_rgb(106, 13, 173),
    discord.Color.from_rgb(148, 0, 211),
    discord.Color.from_rgb(218, 112, 214),
    discord.Color.from_rgb(0, 191, 255),
]


def galaxy_color():
    return random.choice(GALAXY_COLORS)


def ensure_user(user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {}
    u = data[uid]
    u.setdefault("gems", 25.0)
    u.setdefault("last_daily", 0.0)
    u.setdefault("last_work", 0.0)
    u.setdefault("history", [])
    # bless/curse system
    u.setdefault("bless_infinite", False)
    u.setdefault("curse_infinite", False)
    u.setdefault("bless_charges", 0)
    u.setdefault("curse_charges", 0)
    save_data(data)


def add_history(user_id, entry):
    ensure_user(user_id)
    uid = str(user_id)
    hist = data[uid].get("history", [])
    hist.append(entry)
    if len(hist) > 50:
        hist = hist[-50:]
    data[uid]["history"] = hist
    save_data(data)


def parse_amount(text, user_gems=None, allow_all=False):
    """
    Parses amounts like:
    200000000, 200,000,000, 200m, 0.2b, 150k, all
    """
    if isinstance(text, (int, float)):
        return float(text)

    t = str(text).lower().replace(",", "").replace(" ", "")
    if t == "all":
        if not allow_all or user_gems is None:
            return None
        return float(user_gems)

    try:
        if t.endswith("k"):
            return float(t[:-1]) * 1_000
        if t.endswith("m"):
            return float(t[:-1]) * 1_000_000
        if t.endswith("b"):
            return float(t[:-1]) * 1_000_000_000
        return float(t)
    except ValueError:
        return None


def parse_duration(d: str):
    """
    Parses duration strings like:
    30s, 10m, 2h, 1d
    Returns duration in seconds or None if invalid.
    """
    s = d.strip().lower()
    if len(s) < 2:
        return None
    unit = s[-1]
    num_str = s[:-1]
    try:
        value = float(num_str)
    except ValueError:
        return None
    if value <= 0:
        return None

    if unit == "s":
        return int(value)
    if unit == "m":
        return int(value * 60)
    if unit == "h":
        return int(value * 3600)
    if unit == "d":
        return int(value * 86400)
    return None


def normalize_role_name(name: str) -> str:
    """
    Lowercase, remove spaces and non-alphanumeric chars.
    Works even if role has emojis or weird symbols.
    """
    return "".join(ch.lower() for ch in name if ch.isalnum())


def find_role_by_query(guild: discord.Guild, query: str):
    """
    Smart role finder:
    - supports role mention or ID
    - ignores emojis, spaces, case
    - exact normalized match first
    - then partial normalized match
    """
    query = query.strip()

    # If it's a mention or ID, extract digits and try
    digits = "".join(ch for ch in query if ch.isdigit())
    if digits:
        try:
            rid = int(digits)
            role = guild.get_role(rid)
            if role is not None:
                return role
        except ValueError:
            pass

    norm_query = normalize_role_name(query)
    if not norm_query:
        return None

    roles = guild.roles

    # 1) exact normalized match
    exact_matches = [
        r for r in roles
        if normalize_role_name(r.name) == norm_query
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    elif len(exact_matches) > 1:
        # if multiple exact, pick shortest name (most basic)
        return sorted(exact_matches, key=lambda r: len(r.name))[0]

    # 2) partial normalized match
    partial_matches = [
        r for r in roles
        if norm_query in normalize_role_name(r.name)
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]
    elif len(partial_matches) > 1:
        # again pick shortest name
        return sorted(partial_matches, key=lambda r: len(r.name))[0]

    return None


def roll_chest_reward(chest_key: str) -> int:
    """
    Weighted random roll for a chest.
    """
    config = CHEST_CONFIG[chest_key]
    rewards = config["rewards"]
    chances = config["chances"]
    total = sum(chances)
    r = random.uniform(0, total)
    upto = 0
    for amount, weight in zip(rewards, chances):
        if upto + weight >= r:
            return amount
        upto += weight
    return rewards[-1]


# ---------------------- BLESS / CURSE SYSTEM ---------------------- #


def consume_rig(u):
    """
    Returns 'curse', 'bless' or None.
    - If curse_infinite or curse_charges > 0 → 'curse'
    - Else if bless_infinite or bless_charges > 0 → 'bless'
    For finite charges, decreases count by 1.
    Infinite flags stay until turned off.
    Curse has priority over bless.
    """
    mode = None
    # curse first
    if u.get("curse_infinite") or u.get("curse_charges", 0) > 0:
        mode = "curse"
        if u.get("curse_charges", 0) > 0:
            u["curse_charges"] -= 1
    elif u.get("bless_infinite") or u.get("bless_charges", 0) > 0:
        mode = "bless"
        if u.get("bless_charges", 0) > 0:
            u["bless_charges"] -= 1

    save_data(data)
    return mode


#  ---------------------- BACKUP SYSTEM ---------------------- #

async def backup_to_channel(reason: str = "auto"):
    """Sends current data as JSON file to the backup channel."""
    channel = bot.get_channel(BACKUP_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(BACKUP_CHANNEL_ID)
        except Exception:
            return  # can't backup, invalid channel or no access

    try:
        stamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        payload = json.dumps(data, indent=2)
        fp = io.BytesIO(payload.encode("utf-8"))
        filename = f"casino_backup_{stamp}.json"

        embed = discord.Embed(
            title="💾 Galaxy Casino Backup",
            description=f"Reason: **{reason}**\nTimestamp (UTC): `{stamp}`",
            color=galaxy_color()
        )
        await channel.send(embed=embed, file=discord.File(fp, filename=filename))
    except Exception:
        # don't crash the bot if backup fails
        pass


@tasks.loop(minutes=10)
async def auto_backup_task():
    await backup_to_channel("auto")


@auto_backup_task.before_loop
async def before_auto_backup():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    if not auto_backup_task.is_running():
        auto_backup_task.start()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


def short(n: int) -> str:
    """Converts long numbers into short ones like 15000000 -> 15m"""
    try:
        n = int(n)
    except:
        return str(n)

    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}".rstrip("0").rstrip(".") + "b"
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}".rstrip("0").rstrip(".") + "m"
    if n >= 1_000:
        return f"{n/1000:.2f}".rstrip("0").rstrip(".") + "k"
    return str(n)



def parse_market_number(value: str) -> int:
    """
    Parse marketplace numbers: 5m, 10m, 250k, 1b, 66m, 2.5m, 10000000
    """
    value = value.strip().replace(",", "").lower()

    multipliers = {
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
        "t": 1_000_000_000_000
    }

    # Ends with letter (5m, 250k…)
    if value[-1] in multipliers:
        return int(float(value[:-1]) * multipliers[value[-1]])

    # Pure number (10000000)
    return int(float(value))





class SeedBuyButton(discord.ui.Button):
    def __init__(self, seed_id: str, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.green, row=0)
        self.seed_id = seed_id

    async def callback(self, interaction: discord.Interaction):
        ok, msg = buy_seed_from_shop(interaction.user.id, self.seed_id)
        # Embed'i güncelle (shop paneli yeniden render)
        embed = build_shop_embed(interaction.user)
        view = ShopView(interaction.user.id)
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(msg, ephemeral=True)





import discord
from discord.ext import commands
import time
import random


# ==============================================================
#                    GROW A GARDEN – CORE
# ==============================================================
#
# GEREKEN GLOBALLER (ZATEN BOTUNDA VAR OLMALI):
# - data: dict         → Tüm kullanıcı verileri
# - ensure_user(id)    → Kullanıcı kaydı yoksa açar
# - save_data(data)    → JSON kaydet
# - galaxy_color()     → Embed rengi döndürür
#
# ==============================================================

# ---------------------- GARDEN PROFILE -------------------------

def ensure_garden_profile(user_id: int):
    """Kullanıcıya ait garden profili yoksa oluşturur, varsa döner."""
    ensure_user(user_id)
    u = data.setdefault(str(user_id), {})
    g = u.setdefault("garden", {})

    # BAŞLANGIÇ BAKİYESİ: 2.500.000 g-coins
    g.setdefault("coins", 2_500_000)

    g.setdefault("seeds", {})       # {"carrot": 5, "apple_tree": 2, ...}
    g.setdefault("plots", {})       # {"1": plant, "2": plant, ...}
    g.setdefault("max_plots", 9)    # başlangıç 3x3
    g.setdefault("ascension_level", 0)
    g.setdefault("ascension_points", 0)
    g.setdefault("stats", {
        "total_harvests": 0,
        "total_gcoins_earned": 0,
        "total_mutations": 0,
        "giants_harvested": 0
    })

    save_data(data)
    return g


# --------------------------------------------------------------
#                   SEED DEFINITIONS
# --------------------------------------------------------------

# rarity: Common / Uncommon / Rare / Legendary / Mythical / Ancient / Transcendent

GROW_SEEDS = {
    "carrot": {
        "id": "carrot",
        "name": "Carrot",
        "rarity": "Common",
        "base_time": 5 * 60,        # 5 dakika
        "base_value": 50,           # coin
        "max_harvests": 1,          # tek hasat
        "multi_harvest": False,
    },
    "tomato": {
        "id": "tomato",
        "name": "Tomato",
        "rarity": "Common",
        "base_time": 7 * 60,
        "base_value": 70,
        "max_harvests": 2,
        "multi_harvest": True,
    },
    "berry_bush": {
        "id": "berry_bush",
        "name": "Berry Bush",
        "rarity": "Uncommon",
        "base_time": 15 * 60,
        "base_value": 150,
        "max_harvests": 3,
        "multi_harvest": True,
    },
    "apple_tree": {
        "id": "apple_tree",
        "name": "Apple Tree",
        "rarity": "Uncommon",
        "base_time": 20 * 60,
        "base_value": 220,
        "max_harvests": 4,
        "multi_harvest": True,
    },
    "burning_bud": {
        "id": "burning_bud",
        "name": "Burning Bud",
        "rarity": "Rare",
        "base_time": 40 * 60,
        "base_value": 600,
        "max_harvests": 2,
        "multi_harvest": True,
    },
    "moonfruit": {
        "id": "moonfruit",
        "name": "Moonfruit",
        "rarity": "Legendary",
        "base_time": 60 * 60,
        "base_value": 1200,
        "max_harvests": 3,
        "multi_harvest": True,
    },
    "star_peach": {
        "id": "star_peach",
        "name": "Star Peach",
        "rarity": "Mythical",
        "base_time": 90 * 60,
        "base_value": 2500,
        "max_harvests": 2,
        "multi_harvest": True,
    },
    "ancient_melon": {
        "id": "ancient_melon",
        "name": "Ancient Melon",
        "rarity": "Ancient",
        "base_time": 2 * 60 * 60,
        "base_value": 6000,
        "max_harvests": 1,
        "multi_harvest": False,
    },
    "sun_core": {
        "id": "sun_core",
        "name": "Sun Core",
        "rarity": "Transcendent",
        "base_time": 3 * 60 * 60,
        "base_value": 12000,
        "max_harvests": 1,
        "multi_harvest": False,
    },
}

# Seed fiyatları – garden coins ile (rarity base)
GROW_SEED_PRICES = {
    "Common": 100,
    "Uncommon": 300,
    "Rare": 800,
    "Legendary": 2000,
    "Mythical": 5000,
    "Ancient": 50000,
    "Transcendent": 100000,
}


def get_seed_price(seed_id: str) -> int:
    s = GROW_SEEDS.get(seed_id)
    if not s:
        return 0
    rarity = s["rarity"]
    base_price = GROW_SEED_PRICES.get(rarity, 100)
    return base_price


# --------------------------------------------------------------
#                 MUTATION & GIANT SYSTEM
# --------------------------------------------------------------

def roll_mutation():
    """
    Mutasyon oranları (yaklaşık):
    - %85 normal (x1)
    - %10 Silver (x5)
    - %4 Gold (x20)
    - %1 Rainbow (x50)
    """
    r = random.random() * 100
    if r < 1:
        return ("Rainbow", 50)
    elif r < 5:
        return ("Gold", 20)
    elif r < 15:
        return ("Silver", 5)
    else:
        return (None, 1)


def roll_giant():
    """
    Devleşme şansı ~%3
    Giant → x3 çarpan.
    """
    r = random.random() * 100
    return r < 3


# --------------------------------------------------------------
#                 GARDEN – INTERNAL HELPERS
# --------------------------------------------------------------

def get_free_plot(garden: dict) -> int | None:
    """Boş bir slot ID (1..max_plots) döndürür, yoksa None."""
    max_plots = garden.get("max_plots", 9)
    used = set(int(k) for k in garden.get("plots", {}).keys())
    for i in range(1, max_plots + 1):
        if i not in used:
            return i
    return None


def describe_plant(plant: dict) -> str:
    """
    Bir plot'taki bitkiyi tek satır string olarak anlatır.
    """
    seed = GROW_SEEDS.get(plant["seed_id"], {"name": plant["seed_id"], "rarity": "?"})
    now = time.time()
    ready = now >= plant["ready_at"]
    remaining = max(0, int(plant["ready_at"] - now))

    if ready:
        status = "✅ Ready"
        time_txt = ""
    else:
        mins = remaining // 60
        secs = remaining % 60
        status = "⏳ Growing"
        time_txt = f" ({mins}m {secs}s left)"

    h = plant.get("harvests_done", 0)
    max_h = plant.get("max_harvests", 1)

    return f"{status} – **{seed['name']}** [{seed['rarity']}] — {h}/{max_h} harvests{time_txt}"


def plant_seed_for_user(user_id: int, seed_id: str) -> tuple[bool, str]:
    """Kullanıcıya ait garden içinde, verilen seed_id'yi ilk boş slota eker."""
    garden = ensure_garden_profile(user_id)
    seeds = garden["seeds"]
    if seed_id not in GROW_SEEDS:
        return False, "❌ This seed does not exist."

    if seeds.get(seed_id, 0) <= 0:
        return False, "❌ You don't have that seed."

    slot = get_free_plot(garden)
    if slot is None:
        return False, "❌ No free plot. Harvest or clear some plants first."

    info = GROW_SEEDS[seed_id]
    now = time.time()
    base_time = info["base_time"]

    garden["plots"][str(slot)] = {
        "seed_id": seed_id,
        "planted_at": now,
        "ready_at": now + base_time,
        "harvests_done": 0,
        "max_harvests": info["max_harvests"],
        "multi_harvest": info["multi_harvest"],
        "base_value": info["base_value"],
        "rarity": info["rarity"],
    }

    seeds[seed_id] = seeds.get(seed_id, 0) - 1
    if seeds[seed_id] <= 0:
        del seeds[seed_id]

    save_data(data)
    return True, f"🌱 Planted **{info['name']}** in a free plot."


def harvest_ready_plants(user_id: int) -> tuple[int, int, int, int]:
    """
    Tüm hazır bitkileri hasat eder.
    Dönen değer: (harvest_sayısı, toplam_coin, mutation_sayısı, giant_sayısı)
    """
    garden = ensure_garden_profile(user_id)
    plots = garden["plots"]
    stats = garden["stats"]

    now = time.time()
    harvested_count = 0
    total_coins = 0
    mutation_count = 0
    giant_count = 0

    to_delete = []

    for slot_str, plant in list(plots.items()):
        if now < plant["ready_at"]:
            continue  # daha büyümemiş

        seed_def = GROW_SEEDS.get(plant["seed_id"])
        if not seed_def:
            to_delete.append(slot_str)
            continue

        mut_name, mut_mult = roll_mutation()
        is_giant = roll_giant()

        base = plant.get("base_value", seed_def["base_value"])
        value = base * mut_mult
        if is_giant:
            value *= 3

        harvested_count += 1
        total_coins += value
        if mut_name is not None:
            mutation_count += 1
        if is_giant:
            giant_count += 1

        plant["harvests_done"] = plant.get("harvests_done", 0) + 1
        max_h = plant.get("max_harvests", 1)
        multi = plant.get("multi_harvest", False)

        if multi and plant["harvests_done"] < max_h:
            plant["planted_at"] = now
            plant["ready_at"] = now + seed_def["base_time"]
            plots[slot_str] = plant
        else:
            to_delete.append(slot_str)

    for s in to_delete:
        plots.pop(s, None)

    garden["coins"] += total_coins
    stats["total_harvests"] += harvested_count
    stats["total_gcoins_earned"] += total_coins
    stats["total_mutations"] += mutation_count
    stats["giants_harvested"] += giant_count

    save_data(data)
    return harvested_count, total_coins, mutation_count, giant_count


# ==============================================================
#                     SHOP STOCK SYSTEM
# ==============================================================

# İlk 5 seed HER ZAMAN stokta:
ALWAYS_IN_STOCK = ["carrot", "tomato", "berry_bush", "apple_tree", "burning_bud"]

# Global shop state (runtime bazlı)
GARDEN_SHOP_STATE = {
    "last_refresh": 0.0,
    "stock": {}  # seed_id -> {"infinite": bool, "amount": int | None}
}

SHOP_REFRESH_SECONDS = 5 * 60  # 5 dakika


def _generate_shop_stock():
    """5 dakikada bir çağrıldığında yeni stok setini oluşturur."""
    stock: dict[str, dict] = {}

    # 1) İlk 5 seed her zaman stokta, sınırsız
    for sid in ALWAYS_IN_STOCK:
        if sid in GROW_SEEDS:
            stock[sid] = {"infinite": True, "amount": None}

    # 2) Diğer seedler – rarity'ye göre nadirlik / limit
    rare_candidates = [sid for sid in GROW_SEEDS.keys() if sid not in ALWAYS_IN_STOCK]

    for sid in rare_candidates:
        sdef = GROW_SEEDS[sid]
        rarity = sdef["rarity"]
        roll = random.random()

        # Rarity'ye göre stoklanma olasılığı
        if rarity == "Uncommon":
            chance = 0.5
            min_amt, max_amt = 10, 25
        elif rarity == "Rare":
            chance = 0.25
            min_amt, max_amt = 5, 15
        elif rarity == "Legendary":
            chance = 0.12
            min_amt, max_amt = 2, 8
        elif rarity == "Mythical":
            chance = 0.07
            min_amt, max_amt = 1, 5
        elif rarity == "Ancient":
            chance = 0.04
            min_amt, max_amt = 1, 3
        elif rarity == "Transcendent":
            chance = 0.02
            min_amt, max_amt = 1, 1
        else:
            # Common zaten ALWAYS_IN_STOCK içinde olmalı
            continue

        if roll <= chance:
            amount = random.randint(min_amt, max_amt)
            stock[sid] = {"infinite": False, "amount": amount}

    GARDEN_SHOP_STATE["stock"] = stock
    GARDEN_SHOP_STATE["last_refresh"] = time.time()


def get_current_shop_stock() -> dict:
    """Her çağrıldığında 5dk kontrol eder, gerekiyorsa yeniler."""
    now = time.time()
    if now - GARDEN_SHOP_STATE["last_refresh"] > SHOP_REFRESH_SECONDS:
        _generate_shop_stock()
    return GARDEN_SHOP_STATE["stock"]


def buy_seed_from_shop(user_id: int, seed_id: str) -> tuple[bool, str]:
    """Shop stok ve coin kontrolü yaparak tek adet seed satın alır."""
    garden = ensure_garden_profile(user_id)
    stock = get_current_shop_stock()

    if seed_id not in stock:
        return False, "❌ This seed is not in stock right now."

    entry = stock[seed_id]
    price = get_seed_price(seed_id)

    if garden["coins"] < price:
        return False, f"❌ Not enough g-coins. Need **{price}**, you have **{garden['coins']}**."

    # Sınırlı stok kontrolü
    if not entry["infinite"]:
        if entry["amount"] <= 0:
            return False, "❌ This seed is sold out."
        entry["amount"] -= 1

    garden["coins"] -= price
    garden["seeds"][seed_id] = garden["seeds"].get(seed_id, 0) + 1

    save_data(data)
    return True, f"🛒 Bought **1x {GROW_SEEDS[seed_id]['name']}** for **{price}** g-coins."


# ==============================================================
#                     EMBED HELPERS
# ==============================================================

def build_main_embed(user: discord.abc.User) -> discord.Embed:
    garden = ensure_garden_profile(user.id)
    coins = garden["coins"]
    max_plots = garden["max_plots"]
    plots = garden["plots"]
    seeds = garden["seeds"]
    asc = garden["ascension_level"]

    used_plots = len(plots)
    free_plots = max_plots - used_plots

    if seeds:
        seed_lines = []
        for sid, amt in seeds.items():
            s = GROW_SEEDS.get(sid)
            if not s:
                continue
            seed_lines.append(f"• **{s['name']}** [{s['rarity']}] × `{amt}`")
        seeds_txt = "\n".join(seed_lines)
    else:
        seeds_txt = "_You don't have any seeds yet._"

    embed = discord.Embed(
        title="🌱 Grow a Garden — Main Panel",
        description=(
            "Welcome to your **Galaxy Garden**!\n"
            "Use the buttons below to manage your farm.\n\n"
            "Everything works via buttons — no text commands needed."
        ),
        color=galaxy_color()
    )
    embed.add_field(name="💰 Garden Coins", value=f"**{coins}** g-coins", inline=True)
    embed.add_field(name="🪴 Plots", value=f"Used: **{used_plots}/{max_plots}** (Free: `{free_plots}`)", inline=True)
    embed.add_field(name="✨ Ascension", value=f"Level: **{asc}**", inline=True)
    embed.add_field(name="🌾 Seeds in Inventory", value=seeds_txt, inline=False)

    return embed


def build_garden_embed(user: discord.abc.User) -> discord.Embed:
    garden = ensure_garden_profile(user.id)
    plots = garden["plots"]
    max_plots = garden["max_plots"]

    if not plots:
        desc = "Your garden is currently empty.\nUse **Seed Shop** and **Plant** buttons to start."
    else:
        lines = []
        for i in range(1, max_plots + 1):
            key = str(i)
            if key in plots:
                plant = plots[key]
                lines.append(f"#{i}: " + describe_plant(plant))
            else:
                lines.append(f"#{i}: 🕳 Empty plot")
        desc = "\n".join(lines)

    embed = discord.Embed(
        title=f"🌾 {user.name}'s Garden",
        description=desc,
        color=galaxy_color()
    )
    return embed


def build_shop_embed(user: discord.abc.User) -> discord.Embed:
    garden = ensure_garden_profile(user.id)
    coins = garden["coins"]
    stock = get_current_shop_stock()
    remaining = max(0, int(SHOP_REFRESH_SECONDS - (time.time() - GARDEN_SHOP_STATE["last_refresh"])))

    lines = []
    if not stock:
        lines.append("_Shop is empty right now. Refreshing soon..._")
    else:
        for sid, entry in stock.items():
            sdef = GROW_SEEDS[sid]
            price = get_seed_price(sid)
            if entry["infinite"]:
                amt_txt = "∞"
            else:
                amt_txt = str(entry["amount"])
            lines.append(f"• **{sdef['name']}** [`{sid}`] [{sdef['rarity']}] — 💰 {price} g-coins — Stock: `{amt_txt}`")

    desc = (
        f"Your balance: **{coins}** g-coins\n"
        f"Shop refreshes every **5 minutes**.\n"
        f"Next refresh in: **{remaining // 60}m {remaining % 60}s**\n\n"
        + ("\n".join(lines) if lines else "")
    )

    embed = discord.Embed(
        title="🛒 Garden Seed Shop",
        description=desc,
        color=galaxy_color()
    )
    return embed


def build_stats_embed(user: discord.abc.User) -> discord.Embed:
    garden = ensure_garden_profile(user.id)
    stats = garden["stats"]

    embed = discord.Embed(
        title=f"📊 {user.name}'s Garden Stats",
        description="Overall statistics for your Galaxy Garden.",
        color=galaxy_color()
    )
    embed.add_field(name="🌾 Total Harvests", value=str(stats.get("total_harvests", 0)), inline=True)
    embed.add_field(name="💰 Total g-coins Earned", value=str(stats.get("total_gcoins_earned", 0)), inline=True)
    embed.add_field(name="✨ Total Mutations", value=str(stats.get("total_mutations", 0)), inline=True)
    embed.add_field(name="🌟 Giants Harvested", value=str(stats.get("giants_harvested", 0)), inline=True)
    return embed


# ==============================================================
#                     DISCORD UI – VIEWS
# ==============================================================

class MainMenuView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or interaction.user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message("❌ This is not your garden panel.", ephemeral=True)
        return False

    # ---------------- BUTTONS -----------------

    @discord.ui.button(label="🌾 View Garden", style=discord.ButtonStyle.green)
    async def view_garden(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_garden_embed(interaction.user)
        view = GardenView(self.owner_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🧺 Harvest All", style=discord.ButtonStyle.blurple)
    async def harvest_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        harvested, coins_gained, muts, giants = harvest_ready_plants(interaction.user.id)
        main_embed = build_main_embed(interaction.user)
        await interaction.response.edit_message(embed=main_embed, view=MainMenuView(self.owner_id))
        if harvested == 0:
            await interaction.followup.send("🌱 Nothing is ready yet.", ephemeral=True)
        else:
            msg = (
                f"🧺 Harvested **{harvested}** plants!\n"
                f"💰 Earned **{coins_gained}** g-coins\n"
                f"✨ Mutations: **{muts}**\n"
                f"🌟 Giants: **{giants}**"
            )
            await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="🛒 Seed Shop", style=discord.ButtonStyle.gray)
    async def seed_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_shop_embed(interaction.user)
        view = ShopView(self.owner_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🌱 Quick Plant", style=discord.ButtonStyle.primary)
    async def quick_plant(self, interaction: discord.Interaction, button: discord.ui.Button):
        garden = ensure_garden_profile(interaction.user.id)
        seeds = garden["seeds"]
        if not seeds:
            await interaction.response.send_message("❌ You don't have any seeds.", ephemeral=True)
            return

        best_sid = max(seeds.items(), key=lambda x: x[1])[0]
        ok, msg = plant_seed_for_user(interaction.user.id, best_sid)

        main_embed = build_main_embed(interaction.user)
        await interaction.response.edit_message(embed=main_embed, view=MainMenuView(self.owner_id))
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary)
    async def stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_stats_embed(interaction.user)
        view = StatsView(self.owner_id)
        await interaction.response.edit_message(embed=embed, view=view)


class GardenView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or interaction.user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message("❌ This is not your garden panel.", ephemeral=True)
        return False

    @discord.ui.button(label="🧺 Harvest Ready", style=discord.ButtonStyle.blurple)
    async def harvest_ready(self, interaction: discord.Interaction, button: discord.ui.Button):
        harvested, coins_gained, muts, giants = harvest_ready_plants(interaction.user.id)
        embed = build_garden_embed(interaction.user)
        await interaction.response.edit_message(embed=embed, view=GardenView(self.owner_id))

        if harvested == 0:
            await interaction.followup.send("🌱 No plants were ready.", ephemeral=True)
        else:
            msg = (
                f"🧺 Harvested **{harvested}** plants!\n"
                f"💰 Earned **{coins_gained}** g-coins\n"
                f"✨ Mutations: **{muts}**\n"
                f"🌟 Giants: **{giants}**"
            )
            await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="🔄 Back to Main", style=discord.ButtonStyle.gray)
    async def back_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_main_embed(interaction.user)
        view = MainMenuView(self.owner_id)
        await interaction.response.edit_message(embed=embed, view=view)


class ShopView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

        # Dinamik butonlar – her stoktaki seed için bir buton
        stock = get_current_shop_stock()
        for sid in stock.keys():
            sdef = GROW_SEEDS.get(sid)
            if not sdef:
                continue
            button = SeedBuyButton(seed_id=sid, label=f"Buy {sdef['name']}")
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or interaction.user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message("❌ This is not your garden panel.", ephemeral=True)
        return False

    @discord.ui.button(label="🔄 Refresh Shop", style=discord.ButtonStyle.blurple, row=3)
    async def refresh_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Zorla yeni stok üret (timer'a bakmadan)
        _generate_shop_stock()
        embed = build_shop_embed(interaction.user)
        view = ShopView(self.owner_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🔙 Back to Main", style=discord.ButtonStyle.gray, row=3)
    async def back_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_main_embed(interaction.user)
        view = MainMenuView(self.owner_id)
        await interaction.response.edit_message(embed=embed, view=view)


class SeedBuyButton(discord.ui.Button):
    def __init__(self, seed_id: str, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.green, row=0)
        self.seed_id = seed_id

    async def callback(self, interaction: discord.Interaction):
        ok, msg = buy_seed_from_shop(interaction.user.id, self.seed_id)
        # Embed'i güncelle (shop paneli yeniden render)
        embed = build_shop_embed(interaction.user)
        view = ShopView(interaction.message.embeds[0].colour)  # owner_id directly from state not embed; fix below


class StatsView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id or interaction.user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message("❌ This is not your garden panel.", ephemeral=True)
        return False

    @discord.ui.button(label="🔙 Back to Main", style=discord.ButtonStyle.gray)
    async def back_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_main_embed(interaction.user)
        view = MainMenuView(self.owner_id)
        await interaction.response.edit_message(embed=embed, view=view)


# ==============================================================
#                     MAIN COMMAND
# ==============================================================

@bot.command(name="growagarden", aliases=["garden", "gg"])
async def growagarden_cmd(ctx: commands.Context):
    """
    Tek komut: !growagarden
    Her şey butonlarla yönetilir.
    """
    ensure_garden_profile(ctx.author.id)
    embed = build_main_embed(ctx.author)
    view = MainMenuView(ctx.author.id)
    await ctx.send(embed=embed, view=view)














# --------------------------------------------------------------
#     GUESS THE NUMBER (1–10) — ADMIN EVENT
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def guessthenumber(ctx, prize: str):
    """
    Admin-only infinite guess-the-number event.
    Usage: !guessthenumber 100m
    Runs until someone guesses the correct number (1–10).
    """

    # Parse prize
    parsed_prize = parse_amount(prize, None, allow_all=False)
    if parsed_prize is None or parsed_prize <= 0:
        return await ctx.send("❌ Invalid prize amount!")

    # Pick secret number
    secret = random.randint(1, 10)

    embed = discord.Embed(
        title="🔢 Guess The Number!",
        description=(
            f"**Prize:** 💎 **{fmt(parsed_prize)}** gems\n\n"
            "I picked a secret number between **1–10**.\n"
            "**First person to guess wins!**\n"
            "This event will NOT stop until someone gets it right."
        ),
        color=galaxy_color()
    )

    await ctx.send(embed=embed)

    # Loop until winner
    while True:
        try:
            msg = await bot.wait_for("message", timeout=None)
        except Exception:
            continue

        guess_raw = msg.content.strip()

        # Only accept numbers 1–10
        if not guess_raw.isdigit():
            continue

        guess = int(guess_raw)
        if not 1 <= guess <= 10:
            continue

        # WRONG GUESS
        if guess != secret:
            await ctx.send(f"❌ {msg.author.mention} wrong guess!")
            continue

        # CORRECT GUESS
        winner = msg.author
        ensure_user(winner.id)
        data[str(winner.id)]["gems"] += parsed_prize
        save_data(data)

        add_history(winner.id, {
            "game": "guess_number",
            "bet": 0,
            "result": f"win_{secret}",
            "earned": parsed_prize,
            "timestamp": time.time()
        })

        win_embed = discord.Embed(
            title="🎉 WE HAVE A WINNER!",
            description=(
                f"{winner.mention} guessed **{secret}** correctly!\n"
                f"💎 Prize awarded: **{fmt(parsed_prize)}** gems"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=win_embed)
        break





# --------------------------------------------------------------
#                      MEMBERS (server stats)
# --------------------------------------------------------------
@bot.command(aliases=["member", "members"])
async def membercount(ctx):
    guild = ctx.guild

    total = guild.member_count
    humans = len([m for m in guild.members if not m.bot])
    bots = len([m for m in guild.members if m.bot])

    online = len([m for m in guild.members if m.status == discord.Status.online])
    idle = len([m for m in guild.members if m.status == discord.Status.idle])
    dnd = len([m for m in guild.members if m.status == discord.Status.dnd])
    offline = len([m for m in guild.members if m.status == discord.Status.offline])

    embed = discord.Embed(
        title="👥 Server Member Stats",
        description=f"Statistics for **{guild.name}**",
        color=galaxy_color()
    )

    embed.add_field(name="🌍 Total Members", value=f"**{total}**", inline=True)
    embed.add_field(name="🧑 Humans", value=f"**{humans}**", inline=True)
    embed.add_field(name="🤖 Bots", value=f"**{bots}**", inline=True)

    embed.add_field(
        name="📡 Status",
        value=(
            f"🟢 Online: **{online}**\n"
            f"🟡 Idle: **{idle}**\n"
            f"🔴 DND: **{dnd}**\n"
            f"⚪ Offline: **{offline}**"
        ),
        inline=False
    )

    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.set_footer(text="Galaxy Casino • Server Stats 🌌")

    await ctx.send(embed=embed)


# --------------------------------------------------------------
#   CLEAN BALANCE OF USERS WITH NO HISTORY (ADMIN ONLY)
# --------------------------------------------------------------
def parse_clean_duration(text: str):
    text = text.strip().lower()
    if len(text) < 2:
        return None

    num = text[:-1]
    unit = text[-1]

    try:
        value = float(num)
    except:
        return None

    if value <= 0:
        return None

    if unit == "s":
        return int(value)
    if unit == "m":
        return int(value * 60)
    if unit == "h":
        return int(value * 3600)
    if unit == "d":
        return int(value * 86400)

    return None




@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def cleanhistory(ctx, time_str: str):
    """Usage: !cleanhistory <time>   Example: 30d, 12h, 10m"""

    seconds = parse_clean_duration(time_str)
    if seconds is None:
        return await ctx.send("❌ Invalid time format! Use: `30s`, `10m`, `4h`, `7d`, `30d`.")

    now = time.time()
    limit = now - seconds

    cleaned = []
    total_gems_removed = 0

    for member in ctx.guild.members:
        if member.bot:
            continue

        uid = str(member.id)
        if uid not in data:
            continue

        user_data = data[uid]
        history_list = user_data.get("history", [])

        # No history → inactive entire time
        if not history_list:
            removed = user_data.get("gems", 0)
            total_gems_removed += removed
            user_data["gems"] = 0
            cleaned.append((member, removed))
            continue

        # Determine last command timestamp
        last_time = max(e.get("timestamp", 0) for e in history_list)

        # Too old → inactive
        if last_time < limit:
            removed = user_data.get("gems", 0)
            total_gems_removed += removed
            user_data["gems"] = 0
            cleaned.append((member, removed))

    save_data(data)

    if not cleaned:
        embed = discord.Embed(
            title="✨ No Inactive Users Found",
            description=f"No users inactive for **{time_str}**.",
            color=discord.Color.orange()
        )
        return await ctx.send(embed=embed)

    # Create detailed list file
    output = f"Inactive users cleaned (inactive for {time_str}):\n\n"
    for m, removed in cleaned:
        output += f"{m.name}#{m.discriminator} (ID: {m.id}) - Removed: {removed} gems\n"

    file = discord.File(
        fp=io.BytesIO(output.encode()),
        filename=f"cleanhistory_{time_str}.txt"
    )

    # Final embed
    embed = discord.Embed(
        title="🧹 Inactive Users Cleaned",
        description=(
            f"Users inactive for **{time_str}** had their gems reset.\n\n"
            f"👥 **Total cleaned:** `{len(cleaned)}`\n"
            f"💎 **Total gems removed:** `{fmt(total_gems_removed)}`\n\n"
            f"📄 Full detailed list is attached."
        ),
        color=discord.Color.red()
    )

    await ctx.send(embed=embed, file=file)






# --------------------------------------------------------------
#                      Lock Category (Admin)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def lockcat(ctx, category_id: int):
    DISABLED_CATEGORIES.add(category_id)

    embed = discord.Embed(
        title="🔒 Category Locked",
        description=f"Commands are now **disabled** in category `{category_id}`.",
        color=discord.Color.red()
    )

    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      Unlock Category (Admin)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def unlockcat(ctx, category_id: int):
    DISABLED_CATEGORIES.discard(category_id)

    embed = discord.Embed(
        title="🔓 Category Unlocked",
        description=f"Commands are now **enabled** in category `{category_id}`.",
        color=discord.Color.green()
    )

    await ctx.send(embed=embed)


# --------------------------------------------------------------
#              GLOBAL COMMAND BLOCKER (AUTO DELETE)
# --------------------------------------------------------------
@bot.check
async def block_commands_in_locked_category(ctx):

    # Admins can always use commands
    if ctx.author.guild_permissions.manage_guild:
        return True

    # Category locked?
    if ctx.channel.category_id in DISABLED_CATEGORIES:

        embed = discord.Embed(
            title="🚫 Commands Disabled Here",
            description=(
                "You cannot use bot commands in **this category**.\n\n"
                "✨ **Admins** (Manage Server) can still use commands anywhere.\n"
                "🛠 To re-enable commands here, an admin can use:\n"
                "``!unlockcat <category_id>``\n\n"
                f"📁 Category ID: `{ctx.channel.category_id}`\n\n"
                "Commands remain enabled in all other categories."
            ),
            color=discord.Color.red()
        )

        # Send block message
        block_msg = await ctx.send(embed=embed)

        # DELETE user's command message
        try:
            await ctx.message.delete()
        except:
            pass  # In case bot doesn't have permission

        # DELETE block embed after 10 seconds
        await asyncio.sleep(10)
        try:
            await block_msg.delete()
        except:
            pass

        return False  # STOP the command from executing

    return True








# --------------------------------------------------------------
#                      SELL COMMAND (NO x50 RULE)
# --------------------------------------------------------------

@bot.command()
async def sell(ctx, name: str, income: str, price: str):
    try:
        income_val = parse_market_number(income)
        price_val = parse_market_number(price)
    except:
        return await ctx.send("❌ Invalid number. Use: 5m, 10m, 250k, 1b, etc.")

    ensure_user(ctx.author.id)

    income_disp = short(income_val) + "/s"
    price_disp = short(price_val)

    embed = discord.Embed(
        title=f"Listing from {ctx.author.display_name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="🧾 Item Name", value=name, inline=False)
    embed.add_field(name="📈 Income", value=income_disp, inline=False)
    embed.add_field(
        name="💵 Price",
        value=f"{price_disp} gems",
        inline=False
    )
    embed.set_footer(text="Use !sell to create your own listing.")

    market_channel = bot.get_channel(1442936279644897381)

    class ListingButtons(View):
        def __init__(self, owner_id, price_raw, income_display, price_display, name):
            super().__init__(timeout=None)
            self.owner_id = owner_id
            self.price_raw = price_raw
            self.income_display = income_display
            self.price_display = price_display
            self.name = name

        @discord.ui.button(label="🛒 Buy", style=discord.ButtonStyle.blurple)
        async def buy(self, interaction: discord.Interaction, button):
            buyer = interaction.user
            ensure_user(buyer.id)
            ensure_user(self.owner_id)

            buyer_data = data[str(buyer.id)]

            # --- NO X50 RULE ---
            required = self.price_raw

            if buyer_data["gems"] < required:
                return await interaction.response.send_message(
                    f"❌ You need **{fmt(required)}** gems to buy this.",
                    ephemeral=True
                )

            # Remove gems from buyer
            buyer_data["gems"] -= required
            save_data(data)

            guild = interaction.guild
            seller = guild.get_member(self.owner_id)

            channel_name = f"ticket-{self.price_display}-{self.income_display}".replace("/", "")

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                buyer: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                seller: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }

            # Add admins
            for m in guild.members:
                if m.guild_permissions.manage_guild:
                    overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            ticket = await guild.create_text_channel(name=channel_name, overwrites=overwrites)

            await interaction.response.send_message(f"✅ Ticket created: {ticket.mention}", ephemeral=True)

            await ticket.send(
                f"📨 **Marketplace Ticket Created**\n"
                f"👤 **Buyer:** {buyer.mention}\n"
                f"👑 **Owner:** {seller.mention}\n"
                f"🛡 **Middleman:** Any staff with `Manage Server`\n"
                f"📦 **Item:** {self.name}\n"
                f"💵 **Paid:** {fmt(required)} gems\n"
                f"⚠ Complete the trade inside this ticket."
            )

        @discord.ui.button(label="❌ Cancel Listing", style=discord.ButtonStyle.red)
        async def cancel(self, interaction: discord.Interaction, button):
            if interaction.user.id != self.owner_id:
                return await interaction.response.send_message(
                    "❌ Only the listing owner can cancel.", ephemeral=True
                )

            await interaction.message.delete()
            await interaction.response.send_message("🗑 Listing removed.", ephemeral=True)

    view = ListingButtons(
        owner_id=ctx.author.id,
        price_raw=price_val,
        income_display=income_disp.replace("/s", ""),
        price_display=price_disp,
        name=name
    )

    await market_channel.send(embed=embed, view=view)
    await ctx.send("✅ Listing created!")





# --------------------------------------------------------------
#                      BALANCE / BAL
# --------------------------------------------------------------
@bot.command(aliases=["bal"])
async def balance(ctx, member: discord.Member = None):
    """
    !balance -> your balance
    !balance @user / !bal @user -> other's balance
    """
    target = member or ctx.author
    ensure_user(target.id)
    u = data[str(target.id)]
    gems = u["gems"]

    if target.id == ctx.author.id:
        desc = f"✨ {target.mention}\nYou currently hold **{fmt(gems)}** gems."
    else:
        desc = f"✨ {target.mention}\nThey currently hold **{fmt(gems)}** gems."

    embed = discord.Embed(
        title="🌌 Galaxy Balance",
        description=desc,
        color=galaxy_color()
    )
    embed.set_footer(text="Galaxy Casino • Reach for the stars ✨")
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      DAILY (25m)
# --------------------------------------------------------------
@bot.command()
async def daily(ctx):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]
    now = time.time()
    cooldown = 24 * 3600
    last = u.get("last_daily", 0)

    if now - last < cooldown:
        remaining = cooldown - (now - last)
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        embed = discord.Embed(
            title="⏳ Daily already claimed",
            description=f"Come back in **{hours}h {minutes}m**.",
            color=galaxy_color()
        )
        await ctx.send(embed=embed)
        return

    reward = 25_000_000  # 25m
    u["gems"] += reward
    u["last_daily"] = now
    save_data(data)

    add_history(ctx.author.id, {
        "game": "daily",
        "bet": 0,
        "result": "claim",
        "earned": reward,
        "timestamp": now
    })

    embed = discord.Embed(
        title="🎁 Daily Reward",
        description=f"{ctx.author.mention} claimed **{fmt(reward)}** gems from the galaxy!",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#     GUESS THE COLOR (RUNS UNTIL SOMEONE GUESSES CORRECTLY)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def guessthecolor(ctx, prize: str):
    """
    Admin-only infinite guess-the-color event.
    Usage: !guessthecolor 100m
    Runs until *someone* guesses the correct color.
    Winner gets the gems automatically.
    """

    # Parse prize
    parsed_prize = parse_amount(prize, None, allow_all=False)
    if parsed_prize is None or parsed_prize <= 0:
        return await ctx.send("❌ Invalid prize amount!")

    colors = [
        "red", "blue", "green", "yellow", "purple",
        "pink", "orange", "white", "black", "cyan"
    ]

    secret = random.choice(colors)

    embed = discord.Embed(
        title="🎨 Guess The Color!",
        description=(
            f"**Prize:** 💎 **{fmt(parsed_prize)}** gems\n\n"
            "I picked a secret color from:\n"
            f"`{', '.join(colors)}`\n\n"
            "**First person to guess wins!**\n"
            "This event will NOT stop until someone gets it right."
        ),
        color=galaxy_color()
    )

    await ctx.send(embed=embed)

    # Loop until someone gets the correct answer
    while True:
        try:
            msg = await bot.wait_for("message", timeout=None)  # no timeout
        except Exception:
            continue  # shouldn't happen but keeps loop alive

        guess = msg.content.lower().strip()

        # Must be a valid color
        if guess not in colors:
            continue

        # WRONG GUESS
        if guess != secret:
            await ctx.send(f"❌ {msg.author.mention} wrong guess!")
            continue

        # CORRECT GUESS
        winner = msg.author
        ensure_user(winner.id)
        data[str(winner.id)]["gems"] += parsed_prize
        save_data(data)

        add_history(winner.id, {
            "game": "guess_color",
            "bet": 0,
            "result": "win",
            "earned": parsed_prize,
            "timestamp": time.time()
        })

        win_embed = discord.Embed(
            title="🎉 WE HAVE A WINNER!",
            description=(
                f"{winner.mention} guessed **{secret}** correctly!\n"
                f"💎 Prize awarded: **{fmt(parsed_prize)}** gems"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=win_embed)
        break


# --------------------------------------------------------------
#                      WORK (10m–15m)
# --------------------------------------------------------------
@bot.command()
async def work(ctx):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]
    now = time.time()
    cooldown = 3600  # 1 hour
    last = u.get("last_work", 0)

    if now - last < cooldown:
        remaining = cooldown - (now - last)
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        embed = discord.Embed(
            title="🛠 Galaxy Work",
            description=f"⏳ You are still resting.\nTry again in **{minutes}m {seconds}s**.",
            color=galaxy_color()
        )
        await ctx.send(embed=embed)
        return

    reward = random.randint(7_500_000, 15_000_000)
    u["gems"] += reward
    u["last_work"] = now
    save_data(data)

    add_history(ctx.author.id, {
        "game": "work",
        "bet": 0,
        "result": "work",
        "earned": reward,
        "timestamp": now
    })

    embed = discord.Embed(
        title="🛠 Galaxy Work Complete",
        description=f"✨ {ctx.author.mention}, you earned **{fmt(reward)}** gems from your job.",
        color=galaxy_color()
    )
    embed.set_footer(text="Hard work shines brightest among the stars. 🌌")
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      GIFT
# --------------------------------------------------------------
@bot.command()
async def gift(ctx, member: discord.Member, amount: str):
    ensure_user(ctx.author.id)
    ensure_user(member.id)
    sender = data[str(ctx.author.id)]
    receiver = data[str(member.id)]

    val = parse_amount(amount, sender["gems"], allow_all=False)
    if val is None or val <= 0:
        return await ctx.send("❌ Invalid amount.")
    if val > sender["gems"]:
        return await ctx.send("❌ You don't have enough gems.")

    sender["gems"] -= val
    receiver["gems"] += val
    save_data(data)

    now = time.time()
    add_history(ctx.author.id, {
        "game": "gift",
        "bet": val,
        "result": f"gift_to_{member.id}",
        "earned": -val,
        "timestamp": now
    })
    add_history(member.id, {
        "game": "gift_received",
        "bet": val,
        "result": f"gift_from_{ctx.author.id}",
        "earned": val,
        "timestamp": now
    })

    embed = discord.Embed(
        title="🎁 Gift Sent",
        description=f"{ctx.author.mention} sent **{fmt(val)}** gems to {member.mention}.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      COINFLIP
# --------------------------------------------------------------
@bot.command()
async def coinflip(ctx, bet: str, choice: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]
    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if amount > MAX_BET:
        return await ctx.send("❌ Max bet is **200m**.")
    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")

    choice = choice.lower()
    if choice not in ["heads", "tails"]:
        return await ctx.send("❌ Choose `heads` or `tails`.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)

    if rig == "curse":
        result = "tails" if choice == "heads" else "heads"
    elif rig == "bless":
        result = choice
    else:
        result = random.choice(["heads", "tails"])

    if result == choice:
        u["gems"] += amount * 2
        profit = amount
        res = "win"
        title = "🪙 Coinflip — You Won!"
        color = discord.Color.green()
    else:
        profit = -amount
        res = "lose"
        title = "🪙 Coinflip — You Lost"
        color = discord.Color.red()

    save_data(data)

    embed = discord.Embed(
        title=title,
        description=(
            f"🎯 Your choice: **{choice}**\n"
            f"🌀 Result: **{result}**\n"
            f"💰 Net: **{fmt(profit)}** gems"
        ),
        color=color
    )
    embed.set_footer(text="Galaxy Coinflip • 50/50 in the void 🌌")
    await ctx.send(embed=embed)

    add_history(ctx.author.id, {
        "game": "coinflip",
        "bet": amount,
        "result": res,
        "earned": profit,
        "timestamp": time.time()
    })


# --------------------------------------------------------------
#                      SLOTS (3x4, rig-aware, 2x max)
# --------------------------------------------------------------
@bot.command()
async def slots(ctx, bet: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if amount > MAX_BET:
        return await ctx.send("❌ Max bet is **200m**.")
    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)

    symbols = ["🍒", "🍋", "⭐", "💎"]

    def spin_row():
        return [random.choice(symbols) for _ in range(4)]

    def row_best_match(row):
        counts = {}
        for s in row:
            counts[s] = counts.get(s, 0) + 1
        best_sym = max(counts, key=counts.get)
        return counts[best_sym], best_sym

    # Base first row
    row1 = spin_row()

    if rig == "bless":
        # Guaranteed winning line (at least 3 of a kind)
        win_symbol = random.choice(symbols)
        row2 = [win_symbol, win_symbol, win_symbol, random.choice(symbols)]
        random.shuffle(row2)
        row3 = spin_row()
    elif rig == "curse":
        # Guaranteed losing rows (no 3-of-a-kind)
        def spin_lose_row():
            while True:
                r = spin_row()
                m, _ = row_best_match(r)
                if m < 3:
                    return r

        row2 = spin_lose_row()
        row3 = spin_lose_row()
    else:
        # Normal random
        row2 = spin_row()
        row3 = spin_row()

    r2_match, r2_sym = row_best_match(row2)
    r3_match, r3_sym = row_best_match(row3)

    best_match = 0
    best_symbol = None
    for m, s in [(r2_match, r2_sym), (r3_match, r3_sym)]:
        if m > best_match:
            best_match = m
            best_symbol = s

    if best_match >= 3:
        multiplier = 2.0
        reward = amount * multiplier
        profit = reward - amount
        u["gems"] += reward
        result_text = f"3x {best_symbol}! You win."
        res = "win"
    else:
        multiplier = 0.0
        reward = 0
        profit = -amount
        result_text = "No match."
        res = "lose"

    save_data(data)

    grid = (
        f"{row1[0]} {row1[1]} {row1[2]} {row1[3]}\n"
        f"➡ {row2[0]} {row2[1]} {row2[2]} {row2[3]} ⬅\n"
        f"➡ {row3[0]} {row3[1]} {row3[2]} {row3[3]} ⬅"
    )

    embed = discord.Embed(
        title="🎰 Galaxy Slots",
        description=(
            f"**Bet:** {fmt(amount)}\n"
            f"**Multiplier:** {multiplier:.2f}x\n"
            f"**Result:** {result_text}\n"
            f"**Net:** {fmt(profit)} gems"
        ),
        color=galaxy_color()
    )
    embed.add_field(name="Reels", value=f"```{grid}```", inline=False)
    embed.set_footer(text="Galaxy Slots • Spin among the stars 🌌")
    await ctx.send(embed=embed)

    add_history(ctx.author.id, {
        "game": "slots",
        "bet": amount,
        "result": res,
        "earned": profit,
        "timestamp": time.time()
    })


# --------------------------------------------------------------
#                      MINES (rig-aware)
# --------------------------------------------------------------
@bot.command()
async def mines(ctx, bet: str, mines: int = 3):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet!")
    if amount > MAX_BET:
        return await ctx.send("❌ Max bet is **200m**.")
    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")
    if not 1 <= mines <= 15:
        return await ctx.send("❌ Mines must be between **1 and 15**.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)  # 'bless', 'curse', or None

    owner = ctx.author.id
    game_over = False
    correct_clicks = 0
    first_click = True

    TOTAL = 24
    ROW_SLOTS = 5
    SAFE = "✅"
    BOMB = "💥"

    revealed = [None] * TOTAL
    bomb_positions = random.sample(range(TOTAL), mines)
    exploded_index = None

    def calc_multiplier():
        return (1.025 + mines / 50) ** correct_clicks

    def calc_reward():
        return amount * calc_multiplier()

    def embed_update():
        reward = 0 if exploded_index is not None else calc_reward()
        e = discord.Embed(
            title=f"💣 Galaxy Mines | {ctx.author.name}",
            description=(
                f"💵 Bet: **{fmt(amount)}**\n"
                f"💰 Current: **{fmt(reward)}**\n"
                f"🔥 Multiplier: **{calc_multiplier():.2f}x**"
            ),
            color=galaxy_color()
        )
        e.set_footer(text=f"Mines: {mines} • Tiles: {TOTAL}")
        return e

    view = View(timeout=None)

    class Tile(Button):
        def __init__(self, index):
            super().__init__(label=str(index + 1), style=discord.ButtonStyle.secondary)
            self.index = index

        async def callback(self, interaction):
            nonlocal correct_clicks, game_over, exploded_index, first_click

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended!", ephemeral=True)
            if revealed[self.index] is not None:
                return await interaction.response.send_message("❌ Already clicked!", ephemeral=True)

            # CURSE: first click always bomb
            if rig == "curse" and first_click:
                first_click = False
                exploded_index = self.index
                revealed[self.index] = False
                game_over = True

                for i, btn in enumerate(view.children):
                    if isinstance(btn, Tile):
                        btn.disabled = True
                        if i in bomb_positions:
                            btn.label = "💣"
                            btn.style = discord.ButtonStyle.danger

                add_history(ctx.author.id, {
                    "game": "mines",
                    "bet": amount,
                    "result": "lose",
                    "earned": -amount,
                    "timestamp": time.time()
                })

                try:
                    await interaction.response.edit_message(embed=embed_update(), view=view)
                except:
                    pass
                await ctx.send(f"💥 You hit a mine and lost **{fmt(amount)}** gems.")
                return

            first_click = False

            # BLESS: every tile treated as safe
            if rig == "bless":
                revealed[self.index] = True
                self.label = SAFE
                self.style = discord.ButtonStyle.success
                correct_clicks += 1
                try:
                    await interaction.response.edit_message(embed=embed_update(), view=view)
                except:
                    pass
                return

            # NORMAL
            if self.index in bomb_positions:
                exploded_index = self.index
                revealed[self.index] = False
                game_over = True
                for i, btn in enumerate(view.children):
                    if isinstance(btn, Tile):
                        btn.disabled = True
                        if i in bomb_positions:
                            btn.label = "💣"
                            btn.style = discord.ButtonStyle.danger

                add_history(ctx.author.id, {
                    "game": "mines",
                    "bet": amount,
                    "result": "lose",
                    "earned": -amount,
                    "timestamp": time.time()
                })

                try:
                    await interaction.response.edit_message(embed=embed_update(), view=view)
                except:
                    pass
                await ctx.send(f"💥 You hit a mine and lost **{fmt(amount)}** gems.")
                return

            revealed[self.index] = True
            self.label = SAFE
            self.style = discord.ButtonStyle.success
            correct_clicks += 1

            try:
                await interaction.response.edit_message(embed=embed_update(), view=view)
            except:
                pass

    for i in range(TOTAL):
        btn = Tile(i)
        btn.row = i // ROW_SLOTS
        view.add_item(btn)

    class Cashout(Button):
        def __init__(self):
            super().__init__(label="💰 Cashout", style=discord.ButtonStyle.primary, row=4)

        async def callback(self, interaction):
            nonlocal game_over, exploded_index, correct_clicks

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended!", ephemeral=True)

            # CURSE: cashout still loses full amount
            if rig == "curse":
                game_over = True
                exploded_index = 0  # mark as exploded so reward shows 0
                for i, btn in enumerate(view.children):
                    if isinstance(btn, Tile):
                        btn.disabled = True
                        if i in bomb_positions:
                            btn.label = "💣"
                            btn.style = discord.ButtonStyle.danger

                add_history(ctx.author.id, {
                    "game": "mines",
                    "bet": amount,
                    "result": "lose_cashout",
                    "earned": -amount,
                    "timestamp": time.time()
                })

                try:
                    await interaction.response.edit_message(embed=embed_update(), view=view)
                except:
                    pass

                await ctx.send(f"💥 You panicked and lost **{fmt(amount)}** gems.")
                return

            # BLESS: ensure at least some profit even if they cashout instantly
            if rig == "bless" and correct_clicks == 0:
                correct_clicks = 1

            game_over = True
            reward = calc_reward()
            u["gems"] += reward
            save_data(data)

            for i, btn in enumerate(view.children):
                if isinstance(btn, Tile):
                    btn.disabled = True
                    if i in bomb_positions:
                        btn.label = "💣"
                        btn.style = discord.ButtonStyle.danger

            add_history(ctx.author.id, {
                "game": "mines",
                "bet": amount,
                "result": "cashout",
                "earned": reward - amount,
                "timestamp": time.time()
            })

            try:
                await interaction.response.edit_message(embed=embed_update(), view=view)
            except:
                pass

            await ctx.send(f"💰 You cashed out **{fmt(reward - amount)}** gems!")

    view.add_item(Cashout())
    await ctx.send(embed=embed_update(), view=view)


# --------------------------------------------------------------
#                      TOWER (rig-aware)
# --------------------------------------------------------------
@bot.command()
async def tower(ctx, bet: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if amount > MAX_BET:
        return await ctx.send("❌ Max bet is **200m**.")
    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)

    TOTAL_ROWS = 10
    current_row = 0
    correct_count = 0
    game_over = False
    owner = ctx.author.id

    SAFE = "✅"
    BOMB = "💣"
    EXPLODE = "💥"

    grid = [[None, None, None] for _ in range(TOTAL_ROWS)]
    bomb_positions = [random.randrange(3) for _ in range(TOTAL_ROWS)]
    exploded_cell = None
    earned_on_end = 0

    def calc_multiplier():
        return 1.35 ** correct_count

    def calc_reward():
        return amount * calc_multiplier()

    def embed_update(reveal=False):
        earned = earned_on_end if reveal else (calc_reward() if correct_count > 0 else 0)
        e = discord.Embed(
            title=f"🏰 Galaxy Tower | {ctx.author.name}",
            color=galaxy_color()
        )
        e.add_field(name="Bet", value=fmt(amount))
        e.add_field(name="Earned", value=fmt(earned))
        e.add_field(name="Row", value=f"{current_row}/{TOTAL_ROWS}")
        e.add_field(name="Multiplier", value=f"{calc_multiplier():.2f}x")

        lines = []
        for r in reversed(range(TOTAL_ROWS)):
            row = grid[r]
            line = ""
            for c in range(3):
                cell = row[c]
                if cell is True:
                    line += SAFE + " "
                elif cell is False:
                    if exploded_cell == (r, c):
                        line += EXPLODE + " "
                    else:
                        line += BOMB + " " if reveal else "⬛ "
                else:
                    if reveal:
                        if bomb_positions[r] == c:
                            line += BOMB + " "
                        else:
                            line += SAFE + " "
                    else:
                        line += "⬛ "
            lines.append(line)

        e.add_field(name="Tower", value="\n".join(lines), inline=False)
        e.set_footer(text="Galaxy Tower • Clear all 10 rows or cash out. 🌌")
        return e

    view = View(timeout=None)

    class Choice(Button):
        def __init__(self, pos):
            super().__init__(label=["Left", "Middle", "Right"][pos], style=discord.ButtonStyle.secondary)
            self.pos = pos

        async def callback(self, interaction):
            nonlocal current_row, correct_count, game_over, exploded_cell, earned_on_end

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game ended!", ephemeral=True)

            bomb_col = bomb_positions[current_row]

            # CURSE: first row chosen = bomb
            if rig == "curse" and current_row == 0:
                bomb_positions[current_row] = self.pos
                bomb_col = self.pos

            # BLESS: always safe
            if rig == "bless":
                if self.pos == bomb_col:
                    new_col = (self.pos + 1) % 3
                    bomb_positions[current_row] = new_col
                    bomb_col = new_col

            if self.pos == bomb_col and rig != "bless":
                grid[current_row][self.pos] = False
                exploded_cell = (current_row, self.pos)
                game_over = True
                earned_on_end = 0

                for r in range(TOTAL_ROWS):
                    bc = bomb_positions[r]
                    grid[r][bc] = False

                for b in view.children:
                    b.disabled = True

                add_history(ctx.author.id, {
                    "game": "tower",
                    "bet": amount,
                    "result": "lose",
                    "earned": -amount,
                    "timestamp": time.time()
                })
                await interaction.response.edit_message(embed=embed_update(True), view=view)
                return await ctx.send(f"💥 BOOM! You lost **{fmt(amount)}** gems!")

            grid[current_row][self.pos] = True
            correct_count += 1
            current_row += 1

            if current_row >= TOTAL_ROWS:
                game_over = True
                reward = calc_reward()
                earned_on_end = reward
                u["gems"] += reward
                save_data(data)

                for r in range(TOTAL_ROWS):
                    bc = bomb_positions[r]
                    if grid[r][bc] is None:
                        grid[r][bc] = False

                for b in view.children:
                    b.disabled = True

                add_history(ctx.author.id, {
                    "game": "tower",
                    "bet": amount,
                    "result": "win",
                    "earned": reward - amount,
                    "timestamp": time.time()
                })
                await interaction.response.edit_message(embed=embed_update(True), view=view)
                return await ctx.send(f"🏆 Cleared all rows! **+{fmt(reward - amount)}** gems!")

            await interaction.response.edit_message(embed=embed_update(False), view=view)

    class Cashout(Button):
        def __init__(self):
            super().__init__(label="💰 Cashout", style=discord.ButtonStyle.primary)

        async def callback(self, interaction):
            nonlocal game_over, earned_on_end, correct_count, current_row

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game ended!", ephemeral=True)

            # CURSE: even cashout is a loss
            if rig == "curse":
                game_over = True
                earned_on_end = 0

                for r in range(TOTAL_ROWS):
                    bc = bomb_positions[r]
                    grid[r][bc] = False

                for b in view.children:
                    b.disabled = True

                add_history(ctx.author.id, {
                    "game": "tower",
                    "bet": amount,
                    "result": "lose_cashout",
                    "earned": -amount,
                    "timestamp": time.time()
                })
                await interaction.response.edit_message(embed=embed_update(True), view=view)
                await ctx.send(f"💥 BOOM! You lost **{fmt(amount)}** gems!")
                return

            # BLESS: guarantee at least one safe row worth of profit
            if rig == "bless" and correct_count == 0:
                correct_count = 1

            game_over = True
            reward = calc_reward()
            earned_on_end = reward
            u["gems"] += reward
            save_data(data)

            for r in range(TOTAL_ROWS):
                for c in range(3):
                    if grid[r][c] is None:
                        grid[r][c] = (c != bomb_positions[r])

            for b in view.children:
                b.disabled = True

            add_history(ctx.author.id, {
                "game": "tower",
                "bet": amount,
                "result": "cashout",
                "earned": reward - amount,
                "timestamp": time.time()
            })
            await interaction.response.edit_message(embed=embed_update(True), view=view)
            await ctx.send(f"💰 Cashed out **{fmt(reward - amount)}** gems!")

    view.add_item(Choice(0))
    view.add_item(Choice(1))
    view.add_item(Choice(2))
    view.add_item(Cashout())

    await ctx.send(embed=embed_update(False), view=view)


# --------------------------------------------------------------
#                      BLACKJACK (rig-aware; medium)
# --------------------------------------------------------------
CARD_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "7": 7, "8": 8, "9": 9, "10": 10,
    "J": 10, "Q": 10, "K": 10, "A": 11
}
CARD_ORDER = list(CARD_VALUES.keys())


def draw_card():
    return random.choice(CARD_ORDER)


def hand_value(hand):
    total = sum(CARD_VALUES[c] for c in hand)
    aces = hand.count("A")
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


@bot.command()
async def blackjack(ctx, bet: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if amount > MAX_BET:
        return await ctx.send("❌ Max bet is **200m**.")
    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")

    rig = consume_rig(u)
    u["gems"] -= amount
    save_data(data)

    # Rigged: instant-looking game
    if rig in ("bless", "curse"):
        def random_hand(target_min, target_max):
            while True:
                hand = [draw_card(), draw_card()]
                while hand_value(hand) < target_min:
                    hand.append(draw_card())
                    if len(hand) > 6:
                        break
                v = hand_value(hand)
                if target_min <= v <= target_max:
                    return hand

        if rig == "curse":
            player = random_hand(22, 28)
            dealer = random_hand(17, 21)
            profit = -amount
            result_text = "You busted over 21. Dealer wins."
            res = "lose"
        else:
            player = random_hand(19, 21)
            dealer = random_hand(15, 19)
            while hand_value(dealer) >= hand_value(player):
                dealer = random_hand(15, 19)
            profit = int(amount * 1.7)
            u["gems"] += amount + profit
            save_data(data)
            result_text = "Your hand is higher. You win."
            res = "win"

        pv = hand_value(player)
        dv = hand_value(dealer)

        desc = (
            f"🧑 Your hand: {' '.join(player)} (Total: **{pv}**)\n"
            f"🂠 Dealer hand: {' '.join(dealer)} (Total: **{dv}**)\n\n"
            f"{result_text}\n**Net:** {fmt(profit)} gems"
        )
        embed = discord.Embed(
            title="🃏 Galaxy Blackjack",
            description=desc,
            color=galaxy_color()
        )
        embed.set_footer(text="Galaxy Blackjack • Game finished.")
        await ctx.send(embed=embed)

        add_history(ctx.author.id, {
            "game": "blackjack",
            "bet": amount,
            "result": res,
            "earned": profit,
            "timestamp": time.time()
        })
        return

    # Normal interactive blackjack
    player = [draw_card(), draw_card()]
    dealer = [draw_card(), draw_card()]

    def make_embed(show_dealer=False, final=False, extra_msg=""):
        pv = hand_value(player)
        dv = hand_value(dealer) if show_dealer else "??"
        desc = (
            f"🧑 Your hand: {' '.join(player)} (Total: **{pv}**)\n"
            f"🂠 Dealer hand: {dealer[0]} {' '.join(dealer[1:]) if show_dealer else '❓'} (Total: **{dv}**)"
        )
        if extra_msg:
            desc += f"\n\n{extra_msg}"
        e = discord.Embed(
            title="🃏 Galaxy Blackjack",
            description=desc,
            color=galaxy_color()
        )
        if final:
            e.set_footer(text="Game finished.")
        else:
            e.set_footer(text="Hit or Stand?")
        return e

    view = View(timeout=40)

    async def finish_game(interaction=None):
        pv = hand_value(player)
        dv = hand_value(dealer)
        while dv < 17:
            dealer.append(draw_card())
            dv = hand_value(dealer)

        blackjack_player = (pv == 21 and len(player) == 2)
        blackjack_dealer = (dv == 21 and len(dealer) == 2)

        if pv > 21:
            profit = -amount
            res = "lose"
            text = "You busted over 21."
        elif dv > 21:
            mult = 1.7
            profit = int(amount * (mult - 1))
            res = "win"
            text = "Dealer busted. You win!"
        elif blackjack_player and not blackjack_dealer:
            mult = 2.0
            profit = int(amount * (mult - 1))
            res = "win"
            text = "Blackjack! You win."
        elif blackjack_dealer and not blackjack_player:
            profit = -amount
            res = "lose"
            text = "Dealer has blackjack. You lose."
        elif pv > dv:
            mult = 1.7
            profit = int(amount * (mult - 1))
            res = "win"
            text = "Your hand is closer to 21. You win."
        elif pv < dv:
            profit = -amount
            res = "lose"
            text = "Dealer is closer to 21. You lose."
        else:
            profit = 0
            res = "push"
            text = "It's a push. No one wins."

        if profit > 0:
            u["gems"] += amount + profit
        elif profit == 0:
            u["gems"] += amount
        save_data(data)

        add_history(ctx.author.id, {
            "game": "blackjack",
            "bet": amount,
            "result": res,
            "earned": profit,
            "timestamp": time.time()
        })

        final_embed = make_embed(show_dealer=True, final=True, extra_msg=f"{text}\n**Net:** {fmt(profit)} gems")
        if interaction:
            await interaction.response.edit_message(embed=final_embed, view=None)
        else:
            await ctx.send(embed=final_embed)

    class Hit(Button):
        def __init__(self):
            super().__init__(label="Hit", style=discord.ButtonStyle.primary)

        async def callback(self, interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            player.append(draw_card())
            if hand_value(player) > 21:
                for b in view.children:
                    b.disabled = True
                await finish_game(interaction)
                return
            await interaction.response.edit_message(embed=make_embed(), view=view)

    class Stand(Button):
        def __init__(self):
            super().__init__(label="Stand", style=discord.ButtonStyle.secondary)

        async def callback(self, interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            for b in view.children:
                b.disabled = True
            await finish_game(interaction)

    view.add_item(Hit())
    view.add_item(Stand())

    await ctx.send(embed=make_embed(), view=view)


# --------------------------------------------------------------
#                      CHESTS PANEL & BUY MENU
# --------------------------------------------------------------
@bot.command()
async def chests(ctx):
    """
    Open the Galaxy Chest panel.
    Users can click a rarity and then buy 1 / 5 / 10 chests in a private menu.
    """
    def chest_summary_line(key: str):
        cfg = CHEST_CONFIG[key]
        price = cfg["price"]
        rewards = cfg["rewards"]
        chances = cfg["chances"]
        min_r = min(rewards)
        max_r = max(rewards)
        # quick avg for info
        total_w = sum(chances)
        ev = sum(r * w for r, w in zip(rewards, chances)) / total_w if total_w > 0 else 0
        return (
            f"{cfg['emoji']} **{cfg['name']}**\n"
            f"Price: **{fmt(price)}** gems\n"
            f"Rewards: **{fmt(min_r)}–{fmt(max_r)}** gems\n"
            f"Avg payout: ~**{fmt(int(ev))}** gems\n"
        )

    desc_lines = []
    for key in CHEST_ORDER:
        desc_lines.append(chest_summary_line(key))

    embed = discord.Embed(
        title="📦 Galaxy Chests",
        description=(
            "Open loot chests for random gem rewards.\n"
            "Click a rarity below to open your personal chest menu.\n\n" +
            "\n".join(desc_lines)
        ),
        color=galaxy_color()
    )
    embed.set_footer(text="All rewards are gems only • RNG based, no guaranteed profit.")

    class ChestPanelView(View):
        def __init__(self, owner_ctx):
            super().__init__(timeout=None)
            self.ctx = owner_ctx

    async def open_chest_menu(interaction: discord.Interaction, chest_key: str):
        cfg = CHEST_CONFIG[chest_key]
        rewards = cfg["rewards"]
        chances = cfg["chances"]
        lines = []
        for r, c in zip(rewards, chances):
            lines.append(f"• **{fmt(r)}** gems — `{c}%`")

        desc = (
            f"{cfg['emoji']} **{cfg['name']}**\n"
            f"Price per chest: **{fmt(cfg['price'])}** gems\n\n"
            "**Possible rewards:**\n" +
            "\n".join(lines) +
            "\n\nChoose how many chests to open."
        )

        chest_embed = discord.Embed(
            title="📦 Chest Shop",
            description=desc,
            color=galaxy_color()
        )

        class ChestBuyView(View):
            def __init__(self, user: discord.User, chest_key: str):
                super().__init__(timeout=90)
                self.owner_id = user.id
                self.chest_key = chest_key

        async def handle_buy(interaction: discord.Interaction, count: int):
            user = interaction.user
            ensure_user(user.id)
            u = data[str(user.id)]
            cfg = CHEST_CONFIG[chest_key]
            price = cfg["price"]
            total_cost = price * count

            if u["gems"] < total_cost:
                return await interaction.response.send_message(
                    f"❌ You don't have enough gems for **{count}x {cfg['name']}** "
                    f"(need **{fmt(total_cost)}**).",
                    ephemeral=True
                )

            # perform rolls
            u["gems"] -= total_cost
            total_reward = 0
            rewards_list = []
            for _ in range(count):
                reward = roll_chest_reward(chest_key)
                total_reward += reward
                rewards_list.append(reward)
            u["gems"] += total_reward
            save_data(data)

            net = total_reward - total_cost

            add_history(user.id, {
                "game": f"chest_{chest_key}",
                "bet": total_cost,
                "result": f"open_{count}",
                "earned": net,
                "timestamp": time.time()
            })

            results_lines = []
            for i, r in enumerate(rewards_list, start=1):
                results_lines.append(f"Chest {i}: **{fmt(r)}** gems")

            results_text = "\n".join(results_lines) if results_lines else "No chests opened."

            new_desc = (
                f"{cfg['emoji']} **{cfg['name']}**\n"
                f"Opened: **{count}** chest(s)\n\n"
                f"**Results:**\n{results_text}\n\n"
                f"Total spent: **{fmt(total_cost)}** gems\n"
                f"Total gained: **{fmt(total_reward)}** gems\n"
                f"Net: **{fmt(net)}** gems"
            )

            result_embed = discord.Embed(
                title="📦 Chest Results",
                description=new_desc,
                color=galaxy_color()
            )
            result_embed.set_footer(text="You can close this or open more from the main chest panel.")

            await interaction.response.edit_message(embed=result_embed, view=view_obj)

        class BuyButton(Button):
            def __init__(self, label_text: str, amount: int, style: discord.ButtonStyle):
                super().__init__(label=label_text, style=style)
                self.amount = amount

            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != view_obj.owner_id:
                    return await interaction.response.send_message(
                        "❌ This chest menu is not for you.",
                        ephemeral=True
                    )
                await handle_buy(interaction, self.amount)

        view_obj = ChestBuyView(interaction.user, chest_key)
        view_obj.add_item(BuyButton("Open 1", 1, discord.ButtonStyle.primary))
        view_obj.add_item(BuyButton("Open 5", 5, discord.ButtonStyle.secondary))
        view_obj.add_item(BuyButton("Open 10", 10, discord.ButtonStyle.success))

        await interaction.response.send_message(embed=chest_embed, view=view_obj, ephemeral=True)

    panel_view = ChestPanelView(ctx)

    class ChestButton(Button):
        def __init__(self, chest_key: str, label_text: str, style: discord.ButtonStyle):
            super().__init__(label=label_text, style=style)
            self.chest_key = chest_key

        async def callback(self, interaction: discord.Interaction):
            await open_chest_menu(interaction, self.chest_key)

    # One button per chest type
    panel_view.add_item(ChestButton("common", "Common", discord.ButtonStyle.secondary))
    panel_view.add_item(ChestButton("rare", "Rare", discord.ButtonStyle.primary))
    panel_view.add_item(ChestButton("epic", "Epic", discord.ButtonStyle.success))
    panel_view.add_item(ChestButton("legendary", "Legendary", discord.ButtonStyle.danger))
    panel_view.add_item(ChestButton("mythic", "Mythic", discord.ButtonStyle.secondary))
    panel_view.add_item(ChestButton("galaxy", "Galaxy", discord.ButtonStyle.primary))

    await ctx.send(embed=embed, view=panel_view)


# --------------------------------------------------------------
#                      LOTTERY (ticket system)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def lottery(ctx, ticket_price: str, duration: str):
    """
    Start a lottery.
    Usage: !lottery 50m 10m
    - ticket_price: 50m, 10m, 1b, etc.
    - duration: 30s, 10m, 2h, 1d
    Users buy tickets via button, pot +10% goes to winner.
    """
    price = parse_amount(ticket_price, None, allow_all=False)
    if price is None or price <= 0:
        return await ctx.send("❌ Invalid ticket price.")

    seconds = parse_duration(duration)
    if seconds is None:
        return await ctx.send("❌ Invalid duration. Use like `30s`, `10m`, `2h`, `1d`.")
    if seconds > 7 * 24 * 3600:
        return await ctx.send("❌ Maximum duration is 7 days.")

    end_ts = int(time.time()) + seconds

    def make_lottery_embed(price_value, view_obj, end_timestamp):
        total_tickets = sum(view_obj.tickets.values())
        pot = int(price_value * total_tickets)
        prize = int(pot * (1 + LOTTERY_BONUS)) if pot > 0 else 0
        desc = (
            f"🎟 Ticket price: **{fmt(price_value)}** gems\n"
            f"💰 Current pot: **{fmt(pot)}** gems\n"
            f"🏆 Winner prize (+10%): **{fmt(prize)}** gems\n"
            f"🎫 Total tickets: **{total_tickets}**\n"
            f"⏳ Ends: <t:{int(end_timestamp)}:R>\n\n"
            "Press **Buy** to get a ticket.\n"
            "More tickets = higher win chance!"
        )
        e = discord.Embed(
            title="🎟 Galaxy Lottery",
            description=desc,
            color=galaxy_color()
        )
        return e

    class LotteryView(View):
        def __init__(self, price_value, end_timestamp, ctx_obj, timeout_value):
            # Discord max timeout is 1 day (86400s), so clamp to that
            super().__init__(timeout=min(timeout_value, 86400))
            self.ticket_price = price_value
            self.end_ts = end_timestamp
            self.ctx = ctx_obj
            self.tickets: dict[int, int] = {}  # user_id -> count
            self.message: discord.Message | None = None
            self.finished: bool = False       # prevent double-finish

        async def on_timeout(self):
            # View timeout (max 1 day). We still call finish,
            # but finish() checks self.finished to avoid double calls.
            await self.finish()

        async def finish(self):
            if self.finished:
                return
            self.finished = True

            if self.message is None:
                return

            channel = self.ctx.channel
            total_tickets = sum(self.tickets.values())

            # Disable all buttons
            for child in self.children:
                child.disabled = True

            if total_tickets == 0:
                embed = make_lottery_embed(self.ticket_price, self, self.end_ts)
                embed.title = "🎟 Lottery Ended"
                embed.description += "\n\n❌ No tickets were bought."
                embed.color = discord.Color.red()
                try:
                    await self.message.edit(embed=embed, view=self)
                except Exception:
                    pass
                await channel.send("❌ Lottery ended — nobody bought a ticket.")
                return

            # Build weighted list of entries
            entries: list[int] = []
            for uid, count in self.tickets.items():
                entries.extend([uid] * count)
            winner_id = random.choice(entries)
            prize = int(self.ticket_price * total_tickets * (1 + LOTTERY_BONUS))

            ensure_user(winner_id)
            data[str(winner_id)]["gems"] += prize
            save_data(data)

            add_history(winner_id, {
                "game": "lottery",
                "bet": 0,
                "result": "win",
                "earned": prize,
                "timestamp": time.time()
            })

            embed = discord.Embed(
                title="🎟 Lottery Ended",
                description=(
                    f"🎉 Winner: <@{winner_id}>\n"
                    f"💰 Prize: **{fmt(prize)}** gems\n"
                    f"🎫 Total tickets: **{total_tickets}**"
                ),
                color=discord.Color.green()
            )
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

            await channel.send(
                f"🎉 Congrats <@{winner_id}>! You won **{fmt(prize)}** gems in the lottery!"
            )

    view = LotteryView(price, end_ts, ctx, seconds)

    class BuyTicket(Button):
        def __init__(self):
            super().__init__(label="Buy 🎟", style=discord.ButtonStyle.success)

        async def callback(self, interaction: discord.Interaction):
            user = interaction.user
            ensure_user(user.id)
            u = data[str(user.id)]

            if u["gems"] < view.ticket_price:
                return await interaction.response.send_message(
                    "❌ You don't have enough gems for a ticket.",
                    ephemeral=True
                )

            u["gems"] -= view.ticket_price
            save_data(data)

            view.tickets[user.id] = view.tickets.get(user.id, 0) + 1

            embed = make_lottery_embed(view.ticket_price, view, view.end_ts)
            try:
                await interaction.response.edit_message(embed=embed, view=view)
            except Exception:
                await interaction.response.send_message("✅ Ticket bought!", ephemeral=True)

    class ShowParticipants(Button):
        def __init__(self):
            super().__init__(label="Participants 📜", style=discord.ButtonStyle.secondary)

        async def callback(self, interaction: discord.Interaction):
            if not view.tickets:
                return await interaction.response.send_message(
                    "📜 No tickets bought yet.",
                    ephemeral=True
                )

            total = sum(view.tickets.values())
            lines = []
            for uid, count in view.tickets.items():
                chance = (count / total) * 100 if total > 0 else 0
                lines.append(f"<@{uid}> — {count} tickets ({chance:.1f}%)")

            text = "\n".join(lines)
            await interaction.response.send_message(
                f"🎟 **Lottery participants:**\n{text}",
                ephemeral=True
            )

    view.add_item(BuyTicket())
    view.add_item(ShowParticipants())

    embed = make_lottery_embed(price, view, end_ts)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

    # Manual timer to guarantee finish at the correct time,
    # even if the View timeout is shorter.
    async def lottery_timer():
        await asyncio.sleep(seconds)
        await view.finish()

    bot.loop.create_task(lottery_timer())

# --------------------------------------------------------------
#                      LEADERBOARD
# --------------------------------------------------------------
@bot.command()
async def leaderboard(ctx):
    lb = []
    for user_id, info in data.items():
        if not user_id.isdigit():
            continue
        lb.append((int(user_id), info.get("gems", 0)))
    lb.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title="🏆 Galaxy Leaderboard",
        color=galaxy_color()
    )

    if not lb:
        embed.add_field(name="Nobody yet!", value="No players found.")
        return await ctx.send(embed=embed)

    for i, (user_id, gems) in enumerate(lb[:10], start=1):
        try:
            user_obj = await bot.fetch_user(user_id)
            name = user_obj.name
        except Exception:
            name = f"User {user_id}"
        embed.add_field(name=f"#{i} — {name}", value=f"💎 {fmt(gems)} gems", inline=False)

    embed.set_footer(text="Top 10 richest players in the galaxy 💰")
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      HISTORY
# --------------------------------------------------------------
@bot.command()
async def history(ctx):
    ensure_user(ctx.author.id)
    hist = data[str(ctx.author.id)].get("history", [])

    if not hist:
        return await ctx.send("📜 No game history found.")

    embed = discord.Embed(
        title=f"📜 {ctx.author.name}'s Game History",
        color=galaxy_color()
    )

    for entry in hist[-10:]:
        ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry["timestamp"]))
        embed.add_field(
            name=f"{entry['game']} at {ts}",
            value=f"Bet: {fmt(entry['bet'])} | Result: {entry['result']} | Earned: {fmt(entry['earned'])}",
            inline=False
        )

    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      CHECK
# --------------------------------------------------------------



@bot.command()
async def check(ctx, member: discord.Member = None):
    """
    !check           -> kendi durumunu gösterir
    !check @user     -> başka birini gösterir
    35% kuralı SADECE bilgi içindir, otomatık block yok.
    """
    user = member or ctx.author
    ensure_user(user.id)

    free_total, gambled_total, ratio = compute_gamble_ratio(user.id)
    percent = ratio * 100 if free_total > 0 else 0
    required = free_total * 0.35
    missing = max(0, required - gambled_total)

    embed = discord.Embed(
        title=f"🔍 Free vs Gamble — {user.name}",
        color=galaxy_color()
    )

    embed.add_field(
        name="💎 Free Income (tracked)",
        value=f"**{fmt(int(free_total))}** gems\n"
              f"Sources: daily, work, invite rewards, admin give, dropbox",
        inline=False
    )

    embed.add_field(
        name="🎲 Total Gambled",
        value=f"**{fmt(int(gambled_total))}** gems\n"
              f"Games: coinflip, slots, mines, tower, blackjack",
        inline=False
    )

    embed.add_field(
        name="📊 Gamble Ratio",
        value=f"**{percent:.2f}%** of free income used for gambling.",
        inline=False
    )

    # 35% hedefini göster
    if free_total == 0:
        status = "No free income tracked yet."
    elif percent >= 35:
        status = "🟢 Above recommended 35% usage."
    else:
        status = (
            "🔴 Below recommended 35%.\n"
            f"You would need to gamble ~**{fmt(int(missing))}** more gems "
            f"to reach **35%** of your free income."
        )

    embed.add_field(name="✅ Status", value=status, inline=False)
    embed.set_footer(text="This is only for tracking. Bot does NOT block anything automatically.")
    await ctx.send(embed=embed)



# --------------------------------------------------------------
#                      STATS
# --------------------------------------------------------------
@bot.command()
async def stats(ctx):
    ensure_user(ctx.author.id)
    hist = data[str(ctx.author.id)].get("history", [])
    if not hist:
        return await ctx.send("📊 No stats yet. Play some games first!")

    total_games = len(hist)
    total_bet = sum(e.get("bet", 0) for e in hist)
    total_earned = sum(e.get("earned", 0) for e in hist)
    wins = sum(1 for e in hist if e.get("earned", 0) > 0)
    losses = sum(1 for e in hist if e.get("earned", 0) < 0)
    biggest_win = max((e.get("earned", 0) for e in hist), default=0)
    biggest_loss = min((e.get("earned", 0) for e in hist), default  = 0)

    win_rate = (wins / total_games * 100) if total_games > 0 else 0

    embed = discord.Embed(
        title=f"📊 Galaxy Stats — {ctx.author.name}",
        color=galaxy_color()
    )
    embed.add_field(name="Total Games", value=str(total_games))
    embed.add_field(name="Wins / Losses", value=f"{wins} / {losses}")
    embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%")
    embed.add_field(name="Total Bet", value=f"{fmt(total_bet)}")
    embed.add_field(name="Net Profit", value=f"{fmt(total_earned)}")
    embed.add_field(name="Biggest Win", value=f"{fmt(biggest_win)}")
    embed.add_field(name="Worst Loss", value=f"{fmt(biggest_loss)}")
    embed.set_footer(text="Galaxy Stats • May the odds be ever in your favor 🌌")
    await ctx.send(embed=embed)



# --------------------------------------------------------------
#                   INVITE REWARD SYSTEM (ADVANCED)
# --------------------------------------------------------------

JOINS_CHANNEL = 1443625716859273406
LEAVES_CHANNEL = 1443625744793342132
SUSPICIOUS_SERVER = 1140681007197073468

invite_cache = {}

# Store rejoin + device fingerprints in JSON
data.setdefault("_device_fingerprints", {})
device_fp = data["_device_fingerprints"]


@bot.event
async def on_ready():
    global invite_cache
    for guild in bot.guilds:
        try:
            invite_cache[guild.id] = await guild.invites()
        except:
            invite_cache[guild.id] = []
    save_data(data)
    print("Invite cache + fingerprints loaded.")


def get_device_fingerprint(member):
    """Generate a pseudo device fingerprint."""
    try:
        jar = member._state.http._session.cookie_jar
        values = [cookie.key + ":" + cookie.value for cookie in jar]
        combined = "|".join(values)
        return str(hash(combined))
    except:
        return None


def find_inviter(before, after):
    """Return inviter based on changed invite uses."""
    before_uses = {inv.code: inv.uses for inv in before}
    for inv in after:
        if inv.code in before_uses and inv.uses > before_uses[inv.code]:
            return inv.inviter
    return None


@bot.event
async def on_member_join(member):
    guild = member.guild
    ensure_user(member.id)

    # Refresh invite cache
    try:
        new_invites = await guild.invites()
    except:
        new_invites = []

    old_invites = invite_cache.get(guild.id, [])
    inviter = find_inviter(old_invites, new_invites)
    invite_cache[guild.id] = new_invites

    log_channel = bot.get_channel(JOINS_CHANNEL)

    # ---- FLAGS ----
    age_days = (discord.utils.utcnow() - member.created_at).days
    flag_age = age_days >= 30
    flag_avatar = member.avatar is not None

    # ---- REJOIN ----
    rejoined = str(member.id) in device_fp

    # ---- ALT (same fingerprint) ----
    new_fp = get_device_fingerprint(member)
    alt_detect = False
    if new_fp:
        for uid, fp in device_fp.items():
            if fp == new_fp and str(member.id) != uid:
                alt_detect = True
                break

    if new_fp:
        device_fp[str(member.id)] = new_fp
        save_data(data)

    # ---- Restricted server check ----
    restricted = False
    try:
        other = bot.get_guild(SUSPICIOUS_SERVER)
        if other and other.get_member(member.id):
            restricted = True
    except:
        restricted = False

    # ---- Red flags ----
    bad = []
    if not flag_age: bad.append("age")
    if not flag_avatar: bad.append("avatar")
    if alt_detect: bad.append("alt")
    if rejoined: bad.append("rejoin")
    if restricted: bad.append("restricted")

    color = discord.Color.red() if bad else discord.Color.green()

    embed = discord.Embed(
        title="🌌 Join Review",
        color=color
    )

    embed.add_field(name="👤 New Member", value=member.mention, inline=False)
    embed.add_field(
        name="Account Age",
        value="🟢 OK" if flag_age else f"🔴 {age_days} days",
        inline=True
    )
    embed.add_field(
        name="Avatar",
        value="🟢 Yes" if flag_avatar else "🔴 No",
        inline=True
    )
    embed.add_field(
        name="ALT Detected",
        value="🔴 Yes" if alt_detect else "🟢 No",
        inline=True
    )
    embed.add_field(
        name="Rejoined",
        value="🔴 Yes" if rejoined else "🟢 No",
        inline=True
    )
    embed.add_field(
        name="Restricted Server",
        value="🔴 Yes" if restricted else "🟢 No",
        inline=True
    )

    if inviter:
        embed.add_field(name="Invited By", value=inviter.mention, inline=False)
    else:
        embed.add_field(name="Invited By", value="Unknown", inline=False)

    embed.set_footer(text="Admins must approve to give reward.")

    # ----------------------------------------------------------
    #                 FIXED WORKING VIEW CLASS
    # ----------------------------------------------------------
    class VerifyButtons(View):
        def __init__(self, member, inviter):
            super().__init__(timeout=None)  # NEVER TIME OUT
            self.member = member
            self.inviter = inviter
            self.reward_amount = 50_000_000

        # ACCEPT BUTTON
        @discord.ui.button(label="✔️ Accept", style=discord.ButtonStyle.green)
        async def accept(self, interaction: discord.Interaction, button):
            if not interaction.user.guild_permissions.manage_guild:
                return await interaction.response.send_message(
                    "❌ Only admins can approve rewards.",
                    ephemeral=True
                )

            if self.inviter:
                ensure_user(self.inviter.id)
                data[str(self.inviter.id)]["gems"] += self.reward_amount
                save_data(data)

                add_history(self.inviter.id, {
                    "game": "invite_reward",
                    "bet": 0,
                    "result": f"invite_{self.member.id}",
                    "earned": self.reward_amount,
                    "timestamp": time.time()
                })

            for b in self.children:
                b.disabled = True

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🟢 Invite Approved",
                    description=(
                        f"{self.member.mention} approved.\n"
                        f"Reward sent: **+{fmt(self.reward_amount)}** to {self.inviter.mention}"
                    ),
                    color=discord.Color.green()
                ),
                view=self
            )

        # DENY BUTTON
        @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
        async def deny(self, interaction: discord.Interaction, button):
            if not interaction.user.guild_permissions.manage_guild:
                return await interaction.response.send_message(
                    "❌ Only admins can deny rewards.",
                    ephemeral=True
                )

            for b in self.children:
                b.disabled = True

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🔴 Invite Denied",
                    description=f"{self.member.mention} denied.\nNo reward issued.",
                    color=discord.Color.red()
                ),
                view=self
            )

    # SEND REVIEW MESSAGE
    await log_channel.send(
        embed=embed,
        view=VerifyButtons(member, inviter)
    )





# --------------------------------------------------------------
#                MEMBER LEAVE → -50m TO INVITER
# --------------------------------------------------------------

@bot.event
async def on_member_remove(member):
    guild = member.guild

    log_channel = bot.get_channel(LEAVES_CHANNEL)
    if log_channel is None:
        log_channel = await bot.fetch_channel(LEAVES_CHANNEL)

    # Detect inviter from invites
    new_invites = await guild.invites()
    old_invites = invite_cache.get(guild.id, [])
    inviter = find_inviter(old_invites, new_invites)
    invite_cache[guild.id] = new_invites

    # If no inviter info
    if inviter is None:
        embed = discord.Embed(
            title="🔴 Member Left",
            description=f"{member.mention} left.\nInviter unknown.",
            color=discord.Color.red()
        )
        return await log_channel.send(embed=embed)

    # APPLY -50m penalty (negatives allowed)
    add_gems(str(inviter.id), -50_000_000)
    save_data(data)

    embed = discord.Embed(
        title="🔴 Invite Left",
        description=(
            f"{member.mention} left.\n"
            f"Invited by: {inviter.mention}\n"
            f"Penalty → **-50m** gems"
        ),
        color=discord.Color.red()
    )
    await log_channel.send(embed=embed)





# --------------------------------------------------------------
#                      ADMIN (give/remove)
# --------------------------------------------------------------

def add_gems(uid, amount):
    if uid not in data:
        data[uid] = {"gems": 0, "history": []}

    data[uid]["gems"] += amount
    return data[uid]["gems"]


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def admin(ctx, action: str, member: discord.Member, amount: str):
    ensure_user(member.id)
    uid = str(member.id)
    u = data[uid]

    val = parse_amount(amount, u["gems"], allow_all=False)
    if val is None or val <= 0:
        return await ctx.send("❌ Invalid amount.")

    # ---- GIVE ----
    if action.lower() == "give":
        new_balance = add_gems(uid, +val)

        # FREE SOURCE: admin_give
        add_history(member.id, {
            "game": "admin_give",
            "bet": 0,
            "result": f"admin_give_{ctx.author.id}",
            "earned": val,
            "timestamp": time.time()
        })

        msg = (
            f"Added **{fmt(val)} gems** to {member.mention}\n"
            f"New balance: **{fmt(new_balance)}**"
        )


    # ---- REMOVE (negative allowed!) ----
    elif action.lower() == "remove":
        new_balance = add_gems(uid, -val)   # IMPORTANT FIX
        msg = (
            f"Removed **{fmt(val)} gems** from {member.mention}\n"
            f"New balance: **{fmt(new_balance)}**"
        )

    else:
        return await ctx.send("❌ Use: `!admin give/remove @user amount`")

    save_data(data)

    embed = discord.Embed(
        title="🛠 Admin Action",
        description=msg,
        color=galaxy_color()
    )
    await ctx.send(embed=embed)






# --------------------------------------------------------------
#                      BLESS / CURSE (invisible rig)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def bless(ctx, user_id: int, amount: str = None):
    """
    Usage:
      !bless 1234567890          -> infinite bless
      !bless 1234567890 5        -> 5 blessed games
      !bless 1234567890 off      -> turn off bless
    """
    ensure_user(user_id)
    u = data[str(user_id)]

    if amount is None:
        # infinite bless
        u["bless_infinite"] = True
    else:
        a = amount.lower()
        if a in ("off", "0"):
            u["bless_infinite"] = False
            u["bless_charges"] = 0
        else:
            try:
                n = int(a)
            except ValueError:
                return await ctx.send("❌ Amount must be a number, or `off`.")
            if n <= 0:
                return await ctx.send("❌ Amount must be > 0.")
            u["bless_infinite"] = False
            u["bless_charges"] = n

    save_data(data)
    embed = discord.Embed(
        title="✨ Galaxy Bless",
        description=f"User ID `{user_id}` has been adjusted for upcoming games.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def curse(ctx, user_id: int, amount: str = None):
    """
    Usage:
      !curse 1234567890          -> infinite curse
      !curse 1234567890 5        -> 5 cursed games
      !curse 1234567890 off      -> turn off curse
    """
    ensure_user(user_id)
    u = data[str(user_id)]

    if amount is None:
        # infinite curse
        u["curse_infinite"] = True
    else:
        a = amount.lower()
        if a in ("off", "0"):
            u["curse_infinite"] = False
            u["curse_charges"] = 0
        else:
            try:
                n = int(a)
            except ValueError:
                return await ctx.send("❌ Amount must be a number, or `off`.")
            if n <= 0:
                return await ctx.send("❌ Amount must be > 0.")
            u["curse_infinite"] = False
            u["curse_charges"] = n

    save_data(data)
    embed = discord.Embed(
        title="💀 Galaxy Adjustment",
        description=f"User ID `{user_id}` has been adjusted for upcoming games.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      STATUS (admin-only)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def status(ctx):
    """Shows which users are blessed or cursed."""
    embed = discord.Embed(
        title="🌌 Galaxy Rig Status",
        description="Current bless/curse adjustments",
        color=galaxy_color()
    )

    blessed = []
    cursed = []

    for user_id, u in data.items():
        if not str(user_id).isdigit():
            continue

        # Blessed?
        if u.get("bless_infinite") or u.get("bless_charges", 0) > 0:
            info = []
            if u.get("bless_infinite"):
                info.append("♾️ infinite")
            if u.get("bless_charges", 0) > 0:
                info.append(f"{u.get('bless_charges')} charges")
            blessed.append((user_id, ", ".join(info)))

        # Cursed?
        if u.get("curse_infinite") or u.get("curse_charges", 0) > 0:
            info = []
            if u.get("curse_infinite"):
                info.append("♾️ infinite")
            if u.get("curse_charges", 0) > 0:
                info.append(f"{u.get('curse_charges')} charges")
            cursed.append((user_id, ", ".join(info)))

    if blessed:
        text = ""
        for uid, info in blessed:
            try:
                user = await bot.fetch_user(int(uid))
                name = user.name
            except Exception:
                name = f"User {uid}"
            text += f"**{name}** — {info}\n"
        embed.add_field(name="✨ Blessed Users", value=text, inline=False)
    else:
        embed.add_field(name="✨ Blessed Users", value="None", inline=False)

    if cursed:
        text = ""
        for uid, info in cursed:
            try:
                user = await bot.fetch_user(int(uid))
                name = user.name
            except Exception:
                name = f"User {uid}"
            text += f"**{name}** — {info}\n"
        embed.add_field(name="💀 Cursed Users", value=text, inline=False)
    else:
        embed.add_field(name="💀 Cursed Users", value="None", inline=False)

    embed.set_footer(text="Only visible to admins • Invisible rig remains secret 🔒")
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      BACKUP RESTORE COMMANDS
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def restorelatest(ctx):
    """Restore data from the latest backup file in the backup channel."""
    channel = bot.get_channel(BACKUP_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(BACKUP_CHANNEL_ID)
        except Exception:
            return await ctx.send("❌ Cannot access backup channel.")

    latest_msg = None
    latest_time = None

    async for msg in channel.history(limit=50):
        if not msg.attachments:
            continue
        att = msg.attachments[0]
        if att.filename.startswith("casino_backup_") and att.filename.endswith(".json"):
            if latest_time is None or msg.created_at > latest_time:
                latest_msg = msg
                latest_time = msg.created_at

    if latest_msg is None:
        return await ctx.send("❌ No backup files found in the backup channel.")

    att = latest_msg.attachments[0]
    try:
        raw = await att.read()
        new_data = json.loads(raw.decode("utf-8"))
    except Exception:
        return await ctx.send("❌ Failed to load backup file (invalid JSON).")

    global data
    data = new_data
    save_data(data)

    embed = discord.Embed(
        title="✅ Restore Complete",
        description=f"Restored from latest backup: `{att.filename}`.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def restorebackup(ctx):
    """
    Restore from a backup JSON attached to this command.
    Usage: attach a backup file and run !restorebackup
    """
    if not ctx.message.attachments:
        return await ctx.send("❌ Please attach a backup JSON file to this command.")

    att = ctx.message.attachments[0]
    try:
        raw = await att.read()
        new_data = json.loads(raw.decode("utf-8"))
    except Exception:
        return await ctx.send("❌ Failed to read or parse the attached file.")

    global data
    data = new_data
    save_data(data)

    embed = discord.Embed(
        title="✅ Manual Restore Complete",
        description=f"Restored data from file: `{att.filename}`.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#        GIVE GEMS TO EVERYONE WITH A ROLE (SMART NAME)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def giverole(ctx, *, role_and_amount: str):
    """
    Give gems to all human members with the specified role.
    Usage: !giverole j4j 20m
           !giverole "J4J level 5" 50m
    Role name can have spaces and emojis, case-insensitive.
    """
    parts = role_and_amount.rsplit(" ", 1)
    if len(parts) != 2:
        return await ctx.send("❌ Usage: `!giverole <role name> <amount>`")
    role_query, amount = parts

    role = find_role_by_query(ctx.guild, role_query)
    if role is None:
        return await ctx.send("❌ I couldn't find that role.")

    parsed = parse_amount(amount, None, allow_all=False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid amount.")

    members_to_give = []
    for member in ctx.guild.members:
        if role in member.roles and not member.bot:
            members_to_give.append(member)

    if len(members_to_give) == 0:
        return await ctx.send("❌ That role has **0 human members** I can detect.")

    for member in members_to_give:
        ensure_user(member.id)
        data[str(member.id)]["gems"] += parsed

    save_data(data)

    embed = discord.Embed(
        title="💎 Gems Distributed",
        description=(
            f"Role: {role.mention}\n"
            f"Members rewarded: **{len(members_to_give)}**\n"
            f"Amount each: **{fmt(parsed)} gems**"
        ),
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#        REMOVE GEMS FROM EVERYONE WITH A ROLE (SMART NAME)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def removerole(ctx, *, role_and_amount: str):
    """
    Remove gems from all human members with the specified role.
    Usage: !removerole j4j 20m
    """
    parts = role_and_amount.rsplit(" ", 1)
    if len(parts) != 2:
        return await ctx.send("❌ Usage: `!removerole <role name> <amount>`")
    role_query, amount = parts

    role = find_role_by_query(ctx.guild, role_query)
    if role is None:
        return await ctx.send("❌ I couldn't find that role.")

    parsed = parse_amount(amount, None, allow_all=False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid amount.")

    members_to_tax = []
    for member in ctx.guild.members:
        if role in member.roles and not member.bot:
            members_to_tax.append(member)

    if len(members_to_tax) == 0:
        return await ctx.send("❌ That role has **0 human members** I can detect.")

    for member in members_to_tax:
        ensure_user(member.id)
        uid = str(member.id)
        current = data[uid].get("gems", 0)
        data[uid]["gems"] = max(0, current - parsed)

    save_data(data)

    embed = discord.Embed(
        title="💸 Gems Removed",
        description=(
            f"Role: {role.mention}\n"
            f"Members affected: **{len(members_to_tax)}**\n"
            f"Amount each: **{fmt(parsed)} gems**"
        ),
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                MANUAL BACKUP COMMAND
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def savebackup(ctx):
    """Create an instant backup and upload it to the backup channel."""
    await backup_to_channel("manual")

    embed = discord.Embed(
        title="💾 Manual Backup Saved",
        description="A fresh backup has been uploaded to the backup channel.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      TAX COMMAND
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def tax(ctx, percent: float):
    """
    Apply a tax to all members in this server.
    Usage: !tax 5   -> removes 5% from each member's gems
    """
    if percent <= 0 or percent > 50:
        return await ctx.send("❌ Tax percent must be between **0** and **50**.")

    guild = ctx.guild
    total_taxed = 0
    affected = 0

    for uid, u in data.items():
        if not str(uid).isdigit():
            continue
        member = guild.get_member(int(uid))
        if member is None or member.bot:
            continue

        gems = u.get("gems", 0)
        if gems <= 0:
            continue

        tax_amount = int(gems * (percent / 100))
        if tax_amount <= 0:
            continue

        u["gems"] = max(0, gems - tax_amount)
        total_taxed += tax_amount
        affected += 1

        add_history(int(uid), {
            "game": "tax",
            "bet": 0,
            "result": f"{percent}% tax",
            "earned": -tax_amount,
            "timestamp": time.time()
        })

    save_data(data)

    embed = discord.Embed(
        title="💸 Galactic Tax Applied",
        description=(
            f"Rate: **{percent:.2f}%**\n"
            f"Members affected: **{affected}**\n"
            f"Total gems collected: **{fmt(total_taxed)}**"
        ),
        color=galaxy_color()
    )
    await ctx.send(embed=embed)




# ==============================================================
#                          HELP (USER)
# ==============================================================
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="🌌 Galaxy Casino — Commands Menu",
        description="Use commands with `!` prefix.\nHere is your full player command list:",
        color=galaxy_color()
    )

    # ---------------- Economy ----------------
    embed.add_field(
        name="💰 Economy",
        value=(
            "**!balance / !bal [@user]** — Check gem balance\n"
            "**!daily** — Get your daily 25m\n"
            "**!work** — Earn 10–15m every hour\n"
            "**!gift @user amount** — Send gems to users\n"
            "**!sell <name> <income> <price>** — Create marketplace listings\n"
            " Example: `!sell Los_Mobilis 66m 70m`\n"
            " 💵 Buyer must also have **price × 50** in bot balance"
        ),
        inline=False
    )

    # ---------------- Games ----------------
    embed.add_field(
        name="🎮 Games",
        value=(
            "**!coinflip amount heads/tails** — 50/50 gamble\n"
            "**!slots amount** — Slots machine (3×4)\n"
            "**!mines amount [1–15]** — Avoid the mines\n"
            "**!tower amount** — Climb 10-row tower\n"
            "**!blackjack amount** — Interactive blackjack\n"
            "**!chests** — Open Galaxy Chests"
        ),
        inline=False
    )

    # ---------------- Invite System ----------------
    embed.add_field(
        name="🎉 Invite Rewards",
        value=(
            "**Invite friends to earn gems!**\n"
            "Rewards & penalties:\n"
            "• Valid invite: **+50m** to inviter\n"
            "• Member leaves: **-50m** from inviter\n"
            "• Suspicious / alt joins → **NO REWARD**\n"
            "• Anti-alt checks:\n"
            "  – account age\n"
            "  – avatar\n"
            "  – rejoin detection\n"
            "  – ALT (same device) detection\n"
            "  – restricted server detection"
        ),
        inline=False
    )

    # ---------------- Player Info ----------------
    embed.add_field(
        name="📊 Player Info",
        value=(
            "**!history** — Your last 10 games\n"
            "**!stats** — Full statistics\n"
            "**!leaderboard** — Top 10 richest\n"
            "**!membercount** — Server member stats"
        ),
        inline=False
    )

    # ---------------- Events ----------------
    embed.add_field(
        name="🎟 Events & Specials",
        value=(
            "**!lottery <ticket_price> <duration>** — Admin-run lottery event\n"
            "**!guessthecolor <prize>** — Guess the color event\n"
            "**Mystery Boxes** — Admin-only claim boxes"
        ),
        inline=False
    )

    # ---------------- Admin Section ----------------
    embed.add_field(
        name="🛠 Admin?",
        value=(
            "If you are an admin, use **!helpadmin** for:\n"
            "• Currency control\n"
            "• Chest & events controls\n"
            "• Bless / curse system\n"
            "• Suspicious join reviewing\n"
            "• Backups & restores\n"
            "• Category locking system"
        ),
        inline=False
    )

    embed.set_footer(text="Galaxy Casino • Enjoy your stay 💎🌌")
    await ctx.send(embed=embed)





# ==============================================================
#                       HELP (ADMIN)
# ==============================================================
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def helpadmin(ctx):
    embed = discord.Embed(
        title="🛠 Galaxy Casino — Admin Commands",
        description="Full administrative control panel:",
        color=galaxy_color()
    )

    # ---------------- Currency Control ----------------
    embed.add_field(
        name="💰 Gem Management",
        value=(
            "**!admin give @user amount** — Add gems\n"
            "**!admin remove @user amount** — Remove gems (can go negative)\n"
            "**!giverole <role> amount** — Give gems to all humans in a role\n"
            "**!removerole <role> amount** — Remove gems from all humans in a role\n"
            "**!giveall amount** — Give gems to the entire server\n"
            "**!tax percent** — Remove % of every user's balance"
        ),
        inline=False
    )

    # ---------------- Invite Review System ----------------
    embed.add_field(
        name="🧩 Invite Review System",
        value=(
            "**Automatic Checks:**\n"
            "• Account age\n"
            "• Avatar\n"
            "• Rejoin detection\n"
            "• ALT detection (same device)\n"
            "• Restricted server detection\n\n"
            "**Manual Review Panel:**\n"
            "• Shows all red/green flags\n"
            "• Shows inviter + invite code\n"
            "• Shows fingerprint, avatar, rejoin & age\n\n"
            "**Buttons:**\n"
            "🟢 Accept — Give +50m reward\n"
            "🔴 Deny — Reject reward\n\n"
            "**Leave Penalty:**\n"
            "• If an invited user leaves → inviter gets **-50m**"
        ),
        inline=False
    )

    # ---------------- Events, Rig & Specials ----------------
    embed.add_field(
        name="🎁 Events • Rig • Specials",
        value=(
            "**!guessthecolor amount** — Infinite color guessing event\n"
            "**!guessthenumber amount** — Infinite number event (1–10)\n"
            "**!splitorsteal prize** — 2-player Split or Steal game\n"
            "**!lottery <ticket_price> <duration>** — Lottery system (+10% bonus)\n"
            "**!chests** — Open chest panel\n"
            "**!bless user [games/off]** — Force wins (rig)\n"
            "**!curse user [games/off]** — Force losses (rig)\n"
            "**!status** — Show current bless/curse status\n"
            "**!rainbow** — Drops a rainbow color sequence\n"
            "**!taco** — Makes it rain TACOS 🌮"
        ),
        inline=False
    )

    # ---------------- Server Control ----------------
    embed.add_field(
        name="📁 Server Management",
        value=(
            "**!lockcat <category_id>** — Disable all commands in a category\n"
            "**!unlockcat <category_id>** — Re-enable commands\n"
            "**!cleanhistory <duration>** — Reset gems from inactive users\n"
            "**!membercount** — Show server member stats\n"
            "**!dm \"message\" \"role ID\"** — DM all humans with that role"
        ),
        inline=False
    )

    # ---------------- Backups ----------------
    embed.add_field(
        name="💾 Backups",
        value=(
            "**!savebackup** — Create an instant JSON backup\n"
            "**!restorelatest** — Restore the newest backup\n"
            "**!restorebackup** — Restore from uploaded backup JSON"
        ),
        inline=False
    )

    embed.set_footer(text="Admins need 'Manage Server' permission to use these commands.")
    await ctx.send(embed=embed)








# --------------------------------------------------------------
#                      DM ROLE MEMBERS (STRICT)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def dm(ctx, message: str, role_id: str):
    """
    Only users with MANAGE SERVER can use this command.
    Usage:
    !dm "message here" "roleID"
    """

    # Final hard-check (no bypass)
    if not ctx.author.guild_permissions.manage_guild:
        return await ctx.send("❌ You must have **Manage Server** permission to use this command.")

    # Clean the role ID from input
    digits = "".join(ch for ch in role_id if ch.isdigit())
    if not digits:
        return await ctx.send("❌ Invalid role ID.")

    role = ctx.guild.get_role(int(digits))
    if role is None:
        return await ctx.send("❌ That role does not exist.")

    # Only humans
    members = [m for m in role.members if not m.bot]
    if not members:
        return await ctx.send("❌ No human members found with that role.")

    sent = 0
    failed = 0

    status_msg = await ctx.send(f"📨 Sending DMs to **{len(members)}** members…")

    for member in members:
        try:
            await member.send(message)  # sends exact formatting
            sent += 1
        except:
            failed += 1

        await asyncio.sleep(0.25)  # rate-limit safe

    embed = discord.Embed(
        title="📬 DM Broadcast Finished",
        description=(
            f"**Role:** {role.mention}\n"
            f"👤 Members targeted: `{len(members)}`\n"
            f"✅ Sent: `{sent}`\n"
            f"❌ Failed: `{failed}`"
        ),
        color=galaxy_color()
    )

    await status_msg.edit(content=None, embed=embed)



# --------------------------------------------------------------
#                      !taco (Admin Fun)
# --------------------------------------------------------------

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def taco(ctx):

    blank = "‎ "  # ← invisible safe character (NOT empty)

    taco_lines = [
        "**🌮 HELLOOOO! 🌮**",
        blank,
        "**🌧️ It's raining tacos**",
        "**From out of the sky 🌌**",
        "**🌮 Tacos 🌮**",
        "**No need to ask why 🤷‍♂️**",
        "**Just open your mouth 👄 and close your eyes 👁️**",
        blank,
        "**🌧️ It's raining tacos**",
        "**It's raining tacos 🌮🌧️**",
        "**Out in the street 🏙️**",
        "**🌮 Tacos 🌮**",
        "**All you can eat 😋**",
        "**Lettuce 🥬 and shell 🥙**",
        "**Cheese 🧀 and meat 🥩**",
        "**🌧️ It's raining tacos 🌮**",
        blank,
        "**😋 Yum Yum, Yum Yum Yumity Yum 😋**",
        "**It's like a dream!!!! 🌈**",
        "**😋 Yum Yum, Yum Yum Yumity Yum 😋**",
        "**Bring your sour cream 🥛**",
        blank,
        "**🥙 Shell**",
        "**🥩 Meat**",
        "**🥬 Lettuce**",
        "**🧀 Cheese**",
        blank,
        "**🥙 Shell**",
        "**🥩 Meat**",
        "**🧀 Cheese Cheese Cheese Cheese Cheese 🧀**",
        blank,
        "**🕊️ R.I.P Old Roblox 💔**"
    ]

    for line in taco_lines:
        # Discord rejects empty messages → this fixes everything
        safe_line = line if line.strip() != "" else blank
        await ctx.send(safe_line)
        await asyncio.sleep(1)







# --------------------------------------------------------------
#                      !rainbow (Admin Fun)
# --------------------------------------------------------------
@bot.command()
async def rainbow(ctx):
    colors = [
        ("❤️", "RED"),
        ("🧡", "ORANGE"),
        ("💛", "YELLOW"),
        ("💚", "GREEN"),
        ("💙", "BLUE"),
        ("💜", "PURPLE"),
    ]

    msg = ""
    for emoji, name in colors:
        msg += f"{emoji} **{name}** {emoji}\n"
        await ctx.send(msg)
        await asyncio.sleep(0.8)
        msg = ""  # reset so it doesn't spam multiple lines

    return  # <-- VERY IMPORTANT



# --------------------------------------------------------------
#                   SPLIT OR STEAL (ADMIN)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def splitorsteal(ctx, prize: str):
    parsed_prize = parse_amount(prize, None, allow_all=False)
    if parsed_prize is None or parsed_prize <= 0:
        return await ctx.send("❌ Invalid prize amount.")

    join_list = []  # store all participants

    class JoinButton(View):
        def __init__(self):
            super().__init__(timeout=30)

        @discord.ui.button(label="✨ JOIN GAME ✨", style=discord.ButtonStyle.blurple)
        async def join(self, interaction: discord.Interaction, button):
            if interaction.user.id not in join_list:
                join_list.append(interaction.user.id)
                await interaction.response.send_message(
                    f"🟢 {interaction.user.mention} joined!", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ You already joined.", ephemeral=True
                )

        async def on_timeout(self):
            for b in self.children:
                b.disabled = True
            try:
                await message.edit(view=self)
            except:
                pass

    embed = discord.Embed(
        title="🟦 SPLIT OR STEAL — Join Now!",
        description=(
            f"💎 **Prize:** {fmt(parsed_prize)}\n"
            "**Click the button below to join!**\n"
            "⏳ You have **30 seconds**."
        ),
        color=galaxy_color()
    )

    view = JoinButton()
    message = await ctx.send(embed=embed, view=view)

    # Wait 30 seconds for join phase to end
    await asyncio.sleep(30)

    # ----------------------------
    # PICK RANDOM 2 PARTICIPANTS
    # ----------------------------
    if len(join_list) < 2:
        return await ctx.send("❌ **Event cancelled — not enough participants.**")

    p1_id, p2_id = random.sample(join_list, 2)
    p1 = ctx.guild.get_member(p1_id)
    p2 = ctx.guild.get_member(p2_id)

    await ctx.send(
        f"🎉 **Participants Selected:**\n"
        f"1️⃣ {p1.mention}\n"
        f"2️⃣ {p2.mention}\n"
        f"Both players have received their **secret choices**…"
    )

    # Store choices
    choices = {p1_id: None, p2_id: None}

    # ------------------------------------------------
    # SECRET BUTTON VIEW FOR EACH PLAYER
    # ------------------------------------------------
    class ChoiceView(View):
        def __init__(self, player):
            super().__init__(timeout=30)
            self.player = player

        @discord.ui.button(label="🤝 SPLIT", style=discord.ButtonStyle.green)
        async def split(self, interaction: discord.Interaction, button):
            if interaction.user.id != self.player.id:
                return await interaction.response.send_message("❌ Not your buttons.", ephemeral=True)

            choices[self.player.id] = "split"
            await interaction.response.send_message("🟢 You chose **SPLIT**.", ephemeral=True)
            self._disable_all()

        @discord.ui.button(label="💰 STEAL", style=discord.ButtonStyle.red)
        async def steal(self, interaction: discord.Interaction, button):
            if interaction.user.id != self.player.id:
                return await interaction.response.send_message("❌ Not your buttons.", ephemeral=True)

            choices[self.player.id] = "steal"
            await interaction.response.send_message("🔴 You chose **STEAL**.", ephemeral=True)
            self._disable_all()

        def _disable_all(self):
            for b in self.children:
                b.disabled = True

        async def on_timeout(self):
            self._disable_all()

    # Send secret choices
    await ctx.send(f"🔐 Sending secret choices to {p1.mention}…")
    await ctx.send(f"🔐 Sending secret choices to {p2.mention}…")

    await ctx.send(f"{p1.mention}", view=ChoiceView(p1))
    await ctx.send(f"{p2.mention}", view=ChoiceView(p2))

    # ---------------- WAIT FOR BOTH CHOICES ----------------
    while choices[p1_id] is None or choices[p2_id] is None:
        await asyncio.sleep(1)

    c1 = choices[p1_id]
    c2 = choices[p2_id]

    # ---------------- EVALUATE OUTCOME ----------------
    if c1 == "steal" and c2 == "steal":
        result = "💀 **Both players stole — nobody gets anything!**"
    elif c1 == "steal" and c2 == "split":
        ensure_user(p1_id)
        data[str(p1_id)]["gems"] += parsed_prize
        save_data(data)
        result = f"🔴 {p1.mention} **stole everything** and gets **{fmt(parsed_prize)}**!"
    elif c1 == "split" and c2 == "steal":
        ensure_user(p2_id)
        data[str(p2_id)]["gems"] += parsed_prize
        save_data(data)
        result = f"🔴 {p2.mention} **stole everything** and gets **{fmt(parsed_prize)}**!"
    else:  # both split
        half = parsed_prize / 2
        ensure_user(p1_id)
        ensure_user(p2_id)
        data[str(p1_id)]["gems"] += half
        data[str(p2_id)]["gems"] += half
        save_data(data)
        result = (
            f"🟢 Both players split!\n"
            f"{p1.mention} gets **{fmt(half)}**\n"
            f"{p2.mention} gets **{fmt(half)}**"
        )

    # ---------------- SEND RESULT ----------------
    await ctx.send(
        embed=discord.Embed(
            title="🎭 Split or Steal — Results",
            description=result,
            color=galaxy_color()
        )
    )






# --------------------------------------------------------------
#         GIVE GEMS TO EVERYONE IN THE SERVER
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def giveall(ctx, amount: str):
    """
    Give gems to every human (non-bot) member in the server.
    Uses fetch_members() — needs MEMBERS intent enabled in bot settings.
    """
    parsed = parse_amount(amount, None, allow_all=False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid amount.")

    guild = ctx.guild
    count = 0

    members = [m async for m in guild.fetch_members(limit=None)]

    for member in members:
        if member.bot:
            continue
        ensure_user(member.id)
        data[str(member.id)]["gems"] += parsed
        count += 1

    save_data(data)

    embed = discord.Embed(
        title="💎 Gems Given To EVERYONE",
        description=(
            f"Distributed **{fmt(parsed)}** gems to **{count}** human members "
            f"in **{ctx.guild.name}**!\n"
            f"(Forced full member fetch successful)"
        ),
        color=galaxy_color()
    )

    await ctx.send(embed=embed)


bot.run(TOKEN)
