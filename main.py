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

# Channel used for JSON backups
BACKUP_CHANNEL_ID = 1431610647921295451

# ---------------------- INTENTS ---------------------- #
intents = discord.Intents.all()   # enables EVERYTHING
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------------- CONSTANTS ---------------------- #
MAX_BET = 200_000_000  # 200m
LOTTERY_BONUS = 0.10   # 10% extra on the pot for lottery winner

# ---------------------- CHEST CONFIG ---------------------- #
COMMON_PRICE = 25_000_000
COMMON_REWARD_AMOUNTS = [20_000_000, 30_000_000, 40_000_000, 50_000_000]
COMMON_REWARD_CHANCES = [50, 35, 10, 5]

RARE_PRICE = 75_000_000
RARE_REWARD_AMOUNTS = [50_000_000, 80_000_000, 100_000_000, 125_000_000]
RARE_REWARD_CHANCES = [50, 35, 10, 5]

EPIC_PRICE = 100_000_000
EPIC_REWARD_AMOUNTS = [75_000_000, 110_000_000, 125_000_000, 150_000_000]
EPIC_REWARD_CHANCES = [50, 35, 10, 5]

LEGENDARY_PRICE = 250_000_000
LEGENDARY_REWARD_AMOUNTS = [200_000_000, 260_000_000, 275_000_000, 350_000_000]
LEGENDARY_REWARD_CHANCES = [50, 35, 10, 5]

MYTHIC_PRICE = 500_000_000
MYTHIC_REWARD_AMOUNTS = [400_000_000, 525_000_000, 550_000_000, 625_000_000]
MYTHIC_REWARD_CHANCES = [50, 35, 10, 5]

GALAXY_PRICE = 1_000_000_000
GALAXY_REWARD_AMOUNTS = [900_000_000, 1_100_000_000, 1_100_000_000, 1_250_000_000]
GALAXY_REWARD_CHANCES = [50, 35, 10, 5]

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

# ---------------------- HELPERS ---------------------- #
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
        return sorted(exact_matches, key=lambda r: len(r.name))[0]

    # 2) partial normalized match
    partial_matches = [
        r for r in roles
        if norm_query in normalize_role_name(r.name)
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]
    elif len(partial_matches) > 1:
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


# ---------------------- BACKUP SYSTEM ---------------------- #
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

    while True:
        try:
            msg = await bot.wait_for("message", timeout=None)
        except Exception:
            continue

        guess = msg.content.lower().strip()
        if guess not in colors:
            continue

        if guess != secret:
            await ctx.send(f"❌ {msg.author.mention} wrong guess!")
            continue

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

    reward = random.randint(10_000_000, 15_000_000)
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

    row1 = spin_row()

    if rig == "bless":
        win_symbol = random.choice(symbols)
        row2 = [win_symbol, win_symbol, win_symbol, random.choice(symbols)]
        random.shuffle(row2)
        row3 = spin_row()
    elif rig == "curse":
        def spin_lose_row():
            while True:
                r = spin_row()
                m, _ = row_best_match(r)
                if m < 3:
                    return r
        row2 = spin_lose_row()
        row3 = spin_lose_row()
    else:
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
async def mines(ctx, bet: str, tiles: int = 3):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=False)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet.")

    if amount > MAX_BET:
        return await ctx.send("❌ Max bet is 200m.")

    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")

    if tiles < 1 or tiles > 24:
        return await ctx.send("❌ Tiles must be 1–24.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)

    # Game grid 5x5 (25 tiles)
    grid = [0] * 25  # 0 = safe, 1 = bomb
    mines_count = tiles

    if rig == "bless":
        mines_count = max(1, tiles // 2)
    elif rig == "curse":
        mines_count = min(24, tiles * 2)

    bomb_positions = random.sample(range(25), mines_count)
    for p in bomb_positions:
        grid[p] = 1

    safe_count = 25 - mines_count
    reward_multiplier = 1 + (tiles / 20)

    if rig == "bless":
        picks = safe_count
    elif rig == "curse":
        picks = 1
    else:
        picks = random.randint(1, safe_count)

    profit = int(amount * reward_multiplier) - amount
    if picks < safe_count:
        net = -amount
        result = "lose"
        title = "💣 Mines — You Hit a Bomb"
        color = discord.Color.red()
    else:
        u["gems"] += int(amount * reward_multiplier)
        net = profit
        result = "win"
        title = "💎 Mines — You Won!"
        color = discord.Color.green()

    save_data(data)

    embed = discord.Embed(
        title=title,
        description=(
            f"**Bet:** {fmt(amount)}\n"
            f"**Mines:** {mines_count}\n"
            f"**Net:** {fmt(net)}"
        ),
        color=color
    )
    embed.set_footer(text="Galaxy Mines 🌌 Avoid the darkness.")
    await ctx.send(embed=embed)

    add_history(ctx.author.id, {
        "game": "mines",
        "bet": amount,
        "result": result,
        "earned": net,
        "timestamp": time.time()
    })


# --------------------------------------------------------------
#                      TOWERS (simple rig-aware)
# --------------------------------------------------------------
@bot.command()
async def towers(ctx, bet: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=False)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if amount > MAX_BET:
        return await ctx.send("❌ Max bet is 200m.")
    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)

    rows = 8

    if rig == "bless":
        success_rows = rows
    elif rig == "curse":
        success_rows = random.randint(0, 1)
    else:
        success_rows = random.randint(0, rows)

    if success_rows == rows:
        multiplier = 2.50
        reward = int(amount * multiplier)
        u["gems"] += reward
        net = reward - amount
        result = "win"
        title = "🗼 Towers — Full Clear!"
        color = discord.Color.green()
    elif success_rows == 0:
        net = -amount
        result = "lose"
        title = "🗼 Towers — Fall"
        color = discord.Color.red()
    else:
        til = 1 + (success_rows / rows)
        reward = int(amount * til)
        u["gems"] += reward
        net = reward - amount
        result = "partial"
        title = "🗼 Towers — Partial Clear"
        color = galaxy_color()

    save_data(data)

    embed = discord.Embed(
        title=title,
        description=(
            f"**Bet:** {fmt(amount)}\n"
            f"**Cleared Rows:** {success_rows}/{rows}\n"
            f"**Net:** {fmt(net)} gems"
        ),
        color=color
    )
    embed.set_footer(text="Galaxy Towers • Step into the sky 🌌")
    await ctx.send(embed=embed)

    add_history(ctx.author.id, {
        "game": "towers",
        "bet": amount,
        "result": result,
        "earned": net,
        "timestamp": time.time()
    })


# --------------------------------------------------------------
#                 BLACKJACK (rig-aware, interactive)
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
        return await ctx.send("❌ Not enough gems.")

    rig = consume_rig(u)
    u["gems"] -= amount
    save_data(data)

    # Rigged instant outcome
    if rig in ("bless", "curse"):
        def random_hand(low, high):
            while True:
                h = [draw_card(), draw_card()]
                while hand_value(h) < low:
                    h.append(draw_card())
                    if len(h) > 6:
                        break
                if low <= hand_value(h) <= high:
                    return h

        if rig == "curse":
            player = random_hand(22, 30)
            dealer = random_hand(17, 21)
            profit = -amount
            res = "lose"
            text = "You busted. Dealer wins."
        else:
            player = random_hand(19, 21)
            dealer = random_hand(15, 19)
            while hand_value(dealer) >= hand_value(player):
                dealer = random_hand(15, 19)

            profit = int(amount * 1.7)
            u["gems"] += amount + profit
            save_data(data)
            res = "win"
            text = "Your hand wins."

        embed = discord.Embed(
            title="🃏 Galaxy Blackjack",
            description=(
                f"Your hand: {' '.join(player)} ({hand_value(player)})\n"
                f"Dealer: {' '.join(dealer)} ({hand_value(dealer)})\n\n"
                f"{text}\n**Net: {fmt(profit)}** gems"
            ),
            color=galaxy_color()
        )

        await ctx.send(embed=embed)

        add_history(ctx.author.id, {
            "game": "blackjack",
            "bet": amount,
            "result": res,
            "earned": profit,
            "timestamp": time.time()
        })
        return

    # NORMAL interactive blackjack
    player = [draw_card(), draw_card()]
    dealer = [draw_card(), draw_card()]

    def make_embed(show_dealer=False, final=False, extra=""):
        pv = hand_value(player)
        dv = hand_value(dealer) if show_dealer else "??"
        desc = (
            f"🧑 Your hand: {' '.join(player)} (Total: **{pv}**)\n"
            f"🂠 Dealer: {dealer[0]} {' '.join(dealer[1:]) if show_dealer else '❓'} "
            f"(Total: **{dv}**)\n\n{extra}"
        )
        e = discord.Embed(title="🃏 Galaxy Blackjack", description=desc, color=galaxy_color())
        e.set_footer(text="Game finished." if final else "Hit or Stand?")
        return e

    view = View(timeout=40)

    async def finish_game(interaction=None):
        pv = hand_value(player)
        dv = hand_value(dealer)

        # Dealer hits until 17+
        while dv < 17:
            dealer.append(draw_card())
            dv = hand_value(dealer)

        blackjack_player = (pv == 21 and len(player) == 2)
        blackjack_dealer = (dv == 21 and len(dealer) == 2)

        if pv > 21:
            profit = -amount
            res = "lose"
            msg = "You busted."
        elif dv > 21:
            profit = int(amount * 0.7)
            u["gems"] += amount + profit
            save_data(data)
            res = "win"
            msg = "Dealer busted — you win!"
        elif blackjack_player and not blackjack_dealer:
            profit = amount
            u["gems"] += amount * 2
            save_data(data)
            res = "win"
            msg = "Blackjack! You win."
        elif blackjack_dealer and not blackjack_player:
            profit = -amount
            res = "lose"
            msg = "Dealer blackjack — you lose."
        elif pv > dv:
            profit = int(amount * 0.7)
            u["gems"] += amount + profit
            save_data(data)
            res = "win"
            msg = "Your hand wins!"
        elif pv < dv:
            profit = -amount
            res = "lose"
            msg = "Dealer wins."
        else:
            profit = 0
            u["gems"] += amount
            save_data(data)
            res = "push"
            msg = "Push — no one wins."

        add_history(ctx.author.id, {
            "game": "blackjack",
            "bet": amount,
            "result": res,
            "earned": profit,
            "timestamp": time.time()
        })

        final = make_embed(show_dealer=True, final=True, extra=f"{msg}\n**Net: {fmt(profit)}** gems")
        if interaction:
            await interaction.response.edit_message(embed=final, view=None)
        else:
            await ctx.send(embed=final)

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
                return await finish_game(interaction)
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
#                      OPEN CHEST COMMAND
# --------------------------------------------------------------
@bot.command()
async def chest(ctx, chest_type: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    key = chest_type.lower()
    if key not in CHEST_CONFIG:
        return await ctx.send("❌ Invalid chest! Options: common, rare, epic, legendary, mythic, galaxy")

    config = CHEST_CONFIG[key]
    price = config["price"]

    if u["gems"] < price:
        return await ctx.send("❌ Not enough gems to open this chest.")

    u["gems"] -= price
    reward = roll_chest_reward(key)
    u["gems"] += reward
    save_data(data)

    net = reward - price
    now = time.time()

    add_history(ctx.author.id, {
        "game": f"chest_{key}",
        "bet": price,
        "result": "win",
        "earned": net,
        "timestamp": now
    })

    embed = discord.Embed(
        title=f"{config['emoji']} {config['name']} Opened!",
        description=(
            f"💰 **Cost:** {fmt(price)}\n"
            f"🎁 **Reward:** {fmt(reward)}\n"
            f"📈 **Net:** {fmt(net)} gems"
        ),
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                CHEST BUY PANEL BUTTON → PERSONAL MENU
# --------------------------------------------------------------
class ChestBuyMenu(View):
    def __init__(self, user, chest_key):
        super().__init__(timeout=60)
        self.user = user
        self.chest_key = chest_key

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ This panel is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    async def _buy(self, interaction: discord.Interaction, amount: int):
        uid = str(self.user.id)
        ensure_user(uid)

        config = CHEST_CONFIG[self.chest_key]
        price = config["price"]
        total = price * amount

        if data[uid]["gems"] < total:
            return await interaction.response.send_message(
                f"❌ Not enough gems to buy {amount} chest(s).",
                ephemeral=True
            )

        data[uid]["gems"] -= total

        total_reward = 0
        for _ in range(amount):
            total_reward += roll_chest_reward(self.chest_key)

        data[uid]["gems"] += total_reward
        save_data(data)

        net = total_reward - total
        now = time.time()

        add_history(self.user.id, {
            "game": f"chest_{self.chest_key}",
            "bet": total,
            "result": "multi",
            "earned": net,
            "timestamp": now
        })

        config = CHEST_CONFIG[self.chest_key]
        embed = discord.Embed(
            title=f"{config['emoji']} Bought {amount}x {config['name']}",
            description=(
                f"💰 **Total Cost:** {fmt(total)}\n"
                f"🎁 **Total Reward:** {fmt(total_reward)}\n"
                f"📈 **Net:** {fmt(net)} gems"
            ),
            color=galaxy_color()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Buy 1 Chest", style=discord.ButtonStyle.green)
    async def buy_one(self, interaction: discord.Interaction, button: Button):
        await self._buy(interaction, 1)

    @discord.ui.button(label="Buy 5 Chests", style=discord.ButtonStyle.blurple)
    async def buy_five(self, interaction: discord.Interaction, button: Button):
        await self._buy(interaction, 5)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("❌ Cancelled.", ephemeral=True)
        self.stop()


# --------------------------------------------------------------
#                  MAIN CHEST PANEL (ALWAYS ACTIVE)
# --------------------------------------------------------------
class ChestPanel(View):
    def __init__(self):
        super().__init__(timeout=None)

        for key in CHEST_ORDER:
            c = CHEST_CONFIG[key]
            button = Button(
                label=f"{c['emoji']} {c['name']}",
                custom_id=f"open_{key}",
                style=discord.ButtonStyle.blurple
            )

            async def callback(interaction: discord.Interaction, chest_key=key):
                embed = discord.Embed(
                    title=f"{CHEST_CONFIG[chest_key]['emoji']} {CHEST_CONFIG[chest_key]['name']} — Buy Menu",
                    description=(
                        f"💰 **Price:** {fmt(CHEST_CONFIG[chest_key]['price'])}\n"
                        f"🎁 **Rewards:**\n"
                        +
                        "\n".join(
                            f"- {fmt(r)} (**{c}%**)"
                            for r, c in zip(
                                CHEST_CONFIG[chest_key]['rewards'],
                                CHEST_CONFIG[chest_key]['chances']
                            )
                        )
                    ),
                    color=galaxy_color()
                )
                await interaction.response.send_message(
                    embed=embed,
                    view=ChestBuyMenu(interaction.user, chest_key),
                    ephemeral=True
                )

            button.callback = callback
            self.add_item(button)


# --------------------------------------------------------------
#                  CHEST PANEL COMMANDS
# --------------------------------------------------------------
@bot.command()
async def chestpanel(ctx):
    """
    Shows the always-open chest panel with all chest types.
    """
    embed = discord.Embed(
        title="🎁 Galaxy Chest Panel",
        description="Select a chest to open or purchase.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed, view=ChestPanel())


# old name kept as alias:
@bot.command()
async def chests(ctx):
    await chestpanel(ctx)


# --------------------------------------------------------------
#                      LEADERBOARD
# --------------------------------------------------------------
@bot.command()
async def leaderboard(ctx):
    lb = []
    for user_id, info in data.items():
        if not str(user_id).isdigit():
            continue
        lb.append((int(user_id), info.get("gems", 0)))

    lb.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title="🏆 Galaxy Leaderboard",
        description="Top 10 richest players in the galaxy",
        color=galaxy_color()
    )

    if not lb:
        embed.add_field(name="Nobody yet!", value="No players found.")
        return await ctx.send(embed=embed)

    for i, (uid, gems) in enumerate(lb[:10], start=1):
        try:
            user_obj = await bot.fetch_user(uid)
            name = user_obj.name
        except Exception:
            name = f"User {uid}"
        embed.add_field(
            name=f"#{i} — {name}",
            value=f"💎 {fmt(gems)} gems",
            inline=False
        )

    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      HISTORY
# --------------------------------------------------------------
@bot.command()
async def history(ctx):
    ensure_user(ctx.author.id)
    hist = data[str(ctx.author.id)].get("history", [])
    if not hist:
        return await ctx.send("📜 No history.")

    embed = discord.Embed(
        title=f"📜 {ctx.author.name}'s History",
        color=galaxy_color()
    )

    for entry in hist[-10:]:
        ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry["timestamp"]))
        embed.add_field(
            name=f"{entry['game']} @ {ts}",
            value=f"Bet: {fmt(entry['bet'])} | Result: {entry['result']} | Earned: {fmt(entry['earned'])}",
            inline=False
        )

    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      STATS
# --------------------------------------------------------------
@bot.command()
async def stats(ctx):
    ensure_user(ctx.author.id)
    hist = data[str(ctx.author.id)].get("history", [])

    if not hist:
        return await ctx.send("📊 No stats yet.")

    total_games = len(hist)
    total_bet = sum(e["bet"] for e in hist)
    total_earned = sum(e["earned"] for e in hist)
    wins = sum(1 for e in hist if e["earned"] > 0)
    losses = sum(1 for e in hist if e["earned"] < 0)
    biggest_win = max((e["earned"] for e in hist), default=0)
    biggest_loss = min((e["earned"] for e in hist), default=0)

    embed = discord.Embed(title=f"📊 Stats — {ctx.author.name}", color=galaxy_color())
    embed.add_field(name="Total games", value=str(total_games))
    embed.add_field(name="Wins/Losses", value=f"{wins}/{losses}")
    embed.add_field(name="Win rate", value=f"{(wins/total_games)*100:.1f}%")
    embed.add_field(name="Total bet", value=fmt(total_bet))
    embed.add_field(name="Net profit", value=fmt(total_earned))
    embed.add_field(name="Biggest win", value=fmt(biggest_win))
    embed.add_field(name="Worst loss", value=fmt(biggest_loss))
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                      ADMIN GIVE / REMOVE
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def admin(ctx, action: str, member: discord.Member, amount: str):
    ensure_user(member.id)
    u = data[str(member.id)]

    val = parse_amount(amount, u["gems"], allow_all=False)
    if val is None or val <= 0:
        return await ctx.send("❌ Invalid amount.")

    if action == "give":
        u["gems"] += val
        msg = f"Gave **{fmt(val)}** gems to {member.mention}"
    elif action == "remove":
        u["gems"] = max(0, u["gems"] - val)
        msg = f"Removed **{fmt(val)}** gems from {member.mention}"
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
#                      MYSTERY BOX (!dropbox)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def dropbox(ctx, member: discord.Member, amount: str):
    ensure_user(member.id)

    val = parse_amount(amount, None, False)
    if val is None or val <= 0:
        return await ctx.send("❌ Invalid amount.")

    class ClaimBtn(View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="CLAIM 🎁", style=discord.ButtonStyle.success)
        async def claim(self, interaction: discord.Interaction, btn):
            if interaction.user.id != member.id:
                return await interaction.response.send_message(
                    "❌ Not your box", ephemeral=True
                )

            data[str(member.id)]["gems"] += val
            save_data(data)

            add_history(member.id, {
                "game": "dropbox",
                "bet": 0,
                "result": "admin_drop",
                "earned": val,
                "timestamp": time.time()
            })

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🎁 Mystery Box Claimed",
                    description=f"{member.mention} received **{fmt(val)}** gems!",
                    color=galaxy_color()
                ),
                view=None
            )

    embed = discord.Embed(
        title="🌌 Mystery Box Dropped",
        description=f"{ctx.author.mention} dropped a box for {member.mention}.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed, view=ClaimBtn())


# --------------------------------------------------------------
#                      BLESS / CURSE INVISIBLE RIG
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def bless(ctx, member: discord.Member, amount: str = None):
    ensure_user(member.id)
    u = data[str(member.id)]

    if amount is None:
        u["bless_infinite"] = True
    elif amount.lower() in ("off", "0"):
        u["bless_infinite"] = False
        u["bless_charges"] = 0
    else:
        try:
            num = int(amount)
        except Exception:
            return await ctx.send("❌ Must be a number or `off`.")
        if num <= 0:
            return await ctx.send("❌ Must be > 0")
        u["bless_charges"] = num
        u["bless_infinite"] = False

    save_data(data)
    await ctx.send(
        embed=discord.Embed(
            title="✨ Bless Applied",
            description=f"{member.mention} adjusted.",
            color=galaxy_color()
        )
    )


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def curse(ctx, member: discord.Member, amount: str = None):
    ensure_user(member.id)
    u = data[str(member.id)]

    if amount is None:
        u["curse_infinite"] = True
    elif amount.lower() in ("off", "0"):
        u["curse_infinite"] = False
        u["curse_charges"] = 0
    else:
        try:
            num = int(amount)
        except Exception:
            return await ctx.send("❌ Must be a number or `off`.")
        if num <= 0:
            return await ctx.send("❌ Must be > 0")
        u["curse_charges"] = num
        u["curse_infinite"] = False

    save_data(data)
    await ctx.send(
        embed=discord.Embed(
            title="💀 Curse Applied",
            description=f"{member.mention} adjusted.",
            color=galaxy_color()
        )
    )


# --------------------------------------------------------------
#                      STATUS (admin-only)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def status(ctx):
    embed = discord.Embed(
        title="🌌 Rig Status",
        description="Blessed / Cursed users",
        color=galaxy_color()
    )

    blessed = []
    cursed = []

    for uid, u in data.items():
        if not str(uid).isdigit():
            continue

        if u.get("bless_infinite") or u.get("bless_charges", 0) > 0:
            blessed.append(
                f"<@{uid}> — "
                + ("♾️ infinite" if u["bless_infinite"] else f"{u['bless_charges']} charges")
            )

        if u.get("curse_infinite") or u.get("curse_charges", 0) > 0:
            cursed.append(
                f"<@{uid}> — "
                + ("♾️ infinite" if u["curse_infinite"] else f"{u['curse_charges']} charges")
            )

    embed.add_field(name="✨ Blessed", value="\n".join(blessed) if blessed else "None", inline=False)
    embed.add_field(name="💀 Cursed", value="\n".join(cursed) if cursed else "None", inline=False)

    await ctx.send(embed=embed)



# --------------------------------------------------------------
#             GIVE GEMS TO ALL WITH A ROLE (giverole)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def giverole(ctx, role: discord.Role, amount: str):
    parsed = parse_amount(amount, None, False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid amount.")

    count = 0
    for m in ctx.guild.members:
        if not m.bot and role in m.roles:
            ensure_user(m.id)
            data[str(m.id)]["gems"] += parsed
            count += 1

    save_data(data)

    embed = discord.Embed(
        title="💎 Gems Given",
        description=f"Distributed **{fmt(parsed)}** gems to **{count}** members with {role.mention}",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                 REMOVE GEMS FROM ALL WITH ROLE
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def removerole(ctx, role: discord.Role, amount: str):
    parsed = parse_amount(amount, None, False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid amount.")

    count = 0
    for m in ctx.guild.members:
        if not m.bot and role in m.roles:
            ensure_user(m.id)
            data[str(m.id)]["gems"] = max(0, data[str(m.id)]["gems"] - parsed)
            count += 1

    save_data(data)

    embed = discord.Embed(
        title="💎 Gems Removed",
        description=f"Removed **{fmt(parsed)}** gems from **{count}** members with {role.mention}",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                GIVE TO EVERY HUMAN (!giveall)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def giveall(ctx, amount: str):
    parsed = parse_amount(amount, None, False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid amount.")

    count = 0

    async for m in ctx.guild.fetch_members(limit=None):
        if not m.bot:
            ensure_user(m.id)
            data[str(m.id)]["gems"] += parsed
            count += 1

    save_data(data)

    embed = discord.Embed(
        title="💎 Gems Given To EVERYONE",
        description=f"Gave **{fmt(parsed)}** to **{count}** users.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                  BACKUP & RESTORE
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def savebackup(ctx):
    await backup_to_channel("manual")
    await ctx.send(embed=discord.Embed(
        title="💾 Backup Saved",
        description="Backup uploaded.",
        color=galaxy_color()
    ))


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def restorelatest(ctx):
    channel = bot.get_channel(BACKUP_CHANNEL_ID)
    if channel is None:
        channel = await bot.fetch_channel(BACKUP_CHANNEL_ID)

    latest = None
    latest_time = None

    async for msg in channel.history(limit=50):
        if msg.attachments:
            a = msg.attachments[0]
            if a.filename.endswith(".json"):
                if latest_time is None or msg.created_at > latest_time:
                    latest = a
                    latest_time = msg.created_at

    if latest is None:
        return await ctx.send("❌ No backup found.")

    raw = await latest.read()
    new = json.loads(raw.decode("utf-8"))

    global data
    data = new
    save_data(data)

    await ctx.send(embed=discord.Embed(
        title="✅ Restore Complete",
        description=f"Restored `{latest.filename}`",
        color=galaxy_color()
    ))


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def restorebackup(ctx):
    if not ctx.message.attachments:
        return await ctx.send("❌ Attach a backup JSON.")

    att = ctx.message.attachments[0]
    raw = await att.read()

    try:
        new = json.loads(raw.decode("utf-8"))
    except Exception:
        return await ctx.send("❌ Invalid JSON.")

    global data
    data = new
    save_data(data)

    await ctx.send(embed=discord.Embed(
        title="✅ Manual Restore Complete",
        description=f"Restored `{att.filename}`",
        color=galaxy_color()
    ))


# --------------------------------------------------------------
#                      INTERACTIVE TOWER (rig-aware)
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
                        line += (BOMB + " ") if reveal else "⬛ "
                else:
                    if reveal:
                        line += (BOMB + " ") if bomb_positions[r] == c else (SAFE + " ")
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

            # CURSE: first row always bomb
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
            nonlocal game_over, earned_on_end, correct_count

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended!", ephemeral=True)

            # CURSE → even cashout loses all
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
                return await ctx.send(f"💥 BOOM! You lost **{fmt(amount)}** gems!")

            # BLESS → guarantee at least 1 row profit
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
#                      FIXED LOTTERY (correct)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def lottery(ctx, ticket_price: str, duration: str):
    """
    Corrected lottery:
    - NEVER ends early
    - NEVER announces winner before timer
    - NO double winner bug
    """

    price = parse_amount(ticket_price, None, allow_all=False)
    if price is None or price <= 0:
        return await ctx.send("❌ Invalid price.")

    seconds = parse_duration(duration)
    if seconds is None:
        return await ctx.send("❌ Invalid duration.")

    end_ts = int(time.time()) + seconds

    class LotteryView(View):
        def __init__(self):
            super().__init__(timeout=None)
            self.tickets = {}
            self.finished = False
            self.message = None

        async def finish(self):
            if self.finished:
                return
            self.finished = True

            total = sum(self.tickets.values())
            for c in self.children:
                c.disabled = True

            if total == 0:
                embed = discord.Embed(
                    title="🎟 Lottery Ended",
                    description="❌ Nobody bought a ticket.",
                    color=discord.Color.red()
                )
                return await self.message.edit(embed=embed, view=self)

            entries = []
            for uid, count in self.tickets.items():
                entries.extend([uid] * count)

            winner_id = random.choice(entries)
            prize = int(price * total * 1.10)

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
                title="🎟 Lottery Finished",
                description=f"🎉 Winner: <@{winner_id}>\n💰 Prize: **{fmt(prize)}** gems",
                color=discord.Color.green()
            )
            await self.message.edit(embed=embed, view=self)
            await ctx.send(f"🎉 Congrats <@{winner_id}> — you won **{fmt(prize)}** gems!")

    view = LotteryView()

    def make_embed():
        total = sum(view.tickets.values())
        pot = price * total
        prize = int(pot * 1.10)
        return discord.Embed(
            title="🎟 Galaxy Lottery",
            description=(
                f"🎫 Ticket price: **{fmt(price)}**\n"
                f"💰 Pot: **{fmt(pot)}**\n"
                f"🏆 Win (+10%): **{fmt(prize)}**\n"
                f"⏳ Ends: <t:{end_ts}:R>\n"
                "Press **Buy** to join."
            ),
            color=galaxy_color()
        )

    class Buy(Button):
        def __init__(self):
            super().__init__(label="Buy 🎟", style=discord.ButtonStyle.success)

        async def callback(self, inter):
            ensure_user(inter.user.id)
            u = data[str(inter.user.id)]
            if u["gems"] < price:
                return await inter.response.send_message("❌ Not enough gems.", ephemeral=True)
            u["gems"] -= price
            save_data(data)
            view.tickets[inter.user.id] = view.tickets.get(inter.user.id, 0) + 1
            await inter.response.edit_message(embed=make_embed(), view=view)

    class Participants(Button):
        def __init__(self):
            super().__init__(label="Participants 📜", style=discord.ButtonStyle.secondary)

        async def callback(self, inter):
            if not view.tickets:
                return await inter.response.send_message("No participants.", ephemeral=True)
            total = sum(view.tickets.values())
            lst = []
            for uid, c in view.tickets.items():
                pct = (c / total) * 100
                lst.append(f"<@{uid}> — {c} tickets ({pct:.1f}%)")
            await inter.response.send_message("\n".join(lst), ephemeral=True)

    view.add_item(Buy())
    view.add_item(Participants())

    msg = await ctx.send(embed=make_embed(), view=view)
    view.message = msg

    async def timer():
        await asyncio.sleep(seconds)
        await view.finish()

    asyncio.create_task(timer())


# --------------------------------------------------------------
#                      RUN BOT
# --------------------------------------------------------------
bot.run(TOKEN)

