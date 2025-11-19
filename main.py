import discord
from discord.ext import commands, tasks
import json
import os
import random
from discord.ui import Button, View
import time
import io
from datetime import datetime

# ---------------------- TOKEN ---------------------- #
TOKEN = os.getenv("TOKEN")

# ---------------------- FILES ---------------------- #
DATA_FILE = "casino_data.json"
LOTTERY_FILE = "lottery.json"

# ---------------------- CHANNELS ---------------------- #
BACKUP_CHANNEL_ID = 1431610647921295451
LOG_CHANNEL_ID = 1440730206187950122

# ---------------------- INTENTS ---------------------- #
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------------- CONSTANTS ---------------------- #
MAX_BET = 200_000_000          # 200m
LOTTERY_BONUS = 0.10           # 10% extra on lottery pot

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

# Create main data file if missing
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
    Format numbers into k / m / b form.
    Example:
    1234 -> "1.23k"
    1_000_000 -> "1m"
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


# ---------------------- COLORS ---------------------- #

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


# ---------------------- USER / DATA SYSTEM ---------------------- #

def ensure_user(user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {}

    u = data[uid]
    u.setdefault("gems", 25.0)
    u.setdefault("last_daily", 0.0)
    u.setdefault("last_work", 0.0)
    u.setdefault("history", [])

    # bless/curse
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


# ---------------------- AMOUNT PARSING ---------------------- #

def parse_amount(text, user_gems=None, allow_all=False):
    """
    Parse strings:
    200m, 1b, 25k, 1000000, all
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
    Parse time like: 30s, 10m, 2h, 1d
    Returns seconds.
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


# ---------------------- ROLE SYSTEM ---------------------- #

def normalize_role_name(name: str) -> str:
    """ Lowercase + remove spaces + alphanumerics only. """
    return "".join(ch.lower() for ch in name if ch.isalnum())


def find_role_by_query(guild: discord.Guild, query: str):
    """
    Smart role matching:
    - mentions
    - IDs
    - exact normalized name
    - partial normalized name
    """
    query = query.strip()
    digits = "".join(ch for ch in query if ch.isdigit())

    # check mention / ID
    if digits:
        try:
            rid = int(digits)
            role = guild.get_role(rid)
            if role:
                return role
        except ValueError:
            pass

    norm = normalize_role_name(query)
    if not norm:
        return None

    roles = guild.roles

    # exact normalized
    exact = [r for r in roles if normalize_role_name(r.name) == norm]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return sorted(exact, key=lambda r: len(r.name))[0]

    # partial normalized
    partial = [r for r in roles if norm in normalize_role_name(r.name)]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        return sorted(partial, key=lambda r: len(r.name))[0]

    return None


# ---------------------- CHEST REWARD ROLLER ---------------------- #

def roll_chest_reward(chest_key: str) -> int:
    """ Weighted RNG for chest rewards. """
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
    Returns: "curse", "bless", or None.
    Curse ALWAYS has priority.
    Decrements finite charges.
    """
    mode = None

    # CURSE FIRST
    if u.get("curse_infinite") or u.get("curse_charges", 0) > 0:
        mode = "curse"
        if u.get("curse_charges", 0) > 0:
            u["curse_charges"] -= 1

    # THEN BLESS
    elif u.get("bless_infinite") or u.get("bless_charges", 0) > 0:
        mode = "bless"
        if u.get("bless_charges", 0) > 0:
            u["bless_charges"] -= 1

    save_data(data)
    return mode


# ---------------------- LOGGING SYSTEM ---------------------- #

EVENT_TITLES = {
    "daily": "🎁 Daily",
    "work": "🛠 Work",
    "gift": "🎁 Gift",
    "coinflip": "🪙 Coinflip",
    "slots": "🎰 Slots",
    "mines": "💣 Mines",
    "tower": "🏰 Tower",
    "blackjack": "🃏 Blackjack",
    "chest_open": "📦 Chest Open",
    "lottery_ticket": "🎟 Lottery Ticket",
    "lottery_end": "🎟 Lottery End",
    "guessthecolor_win": "🎨 GuessTheColor",
    "admin": "🛠 Admin Action",
    "dropbox": "🎁 Dropbox",
    "bless": "✨ Bless",
    "curse": "💀 Curse",
    "giverole": "💎 Role Payout",
    "removerole": "💸 Role Tax",
    "giveall": "💎 Global Payout",
    "tax": "💸 Tax",
    "backup": "💾 Backup",
    "restore": "💾 Restore",
}


async def send_log(event_type, user, summary: str, fields: dict | None = None):
    """
    Send beautiful galaxy-styled logs to the configured log channel.
    """
    channel = bot.get_channel(LOG_CHANNEL_ID)

    if channel is None:
        try:
            channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        except Exception:
            return

    if channel is None:
        return

    embed = discord.Embed(
        title=EVENT_TITLES.get(event_type, "📜 Event"),
        description=summary,
        color=galaxy_color()
    )

    # Author section
    if user is not None:
        try:
            avatar = user.display_avatar.url
        except Exception:
            avatar = None
        embed.set_author(name=f"{user} ({user.id})", icon_url=avatar)

    # Additional fields
    if fields:
        for name, value in fields.items():
            if value is None:
                continue
            embed.add_field(name=name, value=str(value), inline=False)

    # Timestamp
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    embed.set_footer(text=f"Log • {ts} UTC")

    try:
        await channel.send(embed=embed)
    except Exception:
        pass


# ---------------------- BACKUP SYSTEM ---------------------- #

async def backup_to_channel(reason: str = "auto"):
    """Send the current data JSON to the backup channel."""
    channel = bot.get_channel(BACKUP_CHANNEL_ID)

    if channel is None:
        try:
            channel = await bot.fetch_channel(BACKUP_CHANNEL_ID)
        except Exception:
            return

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
        pass  # Never crash the bot on backup fail


# Auto backup every 10 minutes
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
# BALANCE / BAL
# --------------------------------------------------------------
@bot.command(aliases=["bal"])
async def balance(ctx, member: discord.Member = None):
    """
    !balance           → your balance
    !balance @user    → view someone else's
    !bal @user        → same
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
# DAILY (25m)
# --------------------------------------------------------------
@bot.command()
async def daily(ctx):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    now = time.time()
    cooldown = 24 * 3600
    last = u.get("last_daily", 0)
    before = u.get("gems", 0)

    if now - last < cooldown:
        remaining = cooldown - (now - last)
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)

        embed = discord.Embed(
            title="⏳ Daily already claimed",
            description=f"Come back in **{hours}h {minutes}m**.",
            color=galaxy_color()
        )
        return await ctx.send(embed=embed)

    reward = 25_000_000
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

    await send_log(
        "daily",
        ctx.author,
        f"Claimed daily reward of {fmt(reward)} gems.",
        {
            "Reward": fmt(reward),
            "Gems Before": fmt(before),
            "Gems After": fmt(u['gems'])
        }
    )


# --------------------------------------------------------------
# GUESS THE COLOR — runs until someone wins
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def guessthecolor(ctx, prize: str):
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
            "This event will NOT stop until someone guesses correctly."
        ),
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    # infinite loop until winner
    while True:
        msg = await bot.wait_for("message", timeout=None)
        guess = msg.content.lower().strip()

        if guess not in colors:
            continue

        if guess != secret:
            await ctx.send(f"❌ {msg.author.mention} wrong guess!")
            continue

        # WINNER
        winner = msg.author
        ensure_user(winner.id)

        u = data[str(winner.id)]
        before = u["gems"]

        u["gems"] += parsed_prize
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

        await send_log(
            "guessthecolor_win",
            winner,
            f"Guessed color '{secret}' correctly.",
            {
                "Prize": fmt(parsed_prize),
                "Secret Color": secret,
                "Gems Before": fmt(before),
                "Gems After": fmt(u["gems"])
            }
        )
        break


# --------------------------------------------------------------
# WORK (10m – 15m)
# --------------------------------------------------------------
@bot.command()
async def work(ctx):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    now = time.time()
    cooldown = 3600  # 1 hour
    last = u.get("last_work", 0)
    before = u.get("gems", 0)

    if now - last < cooldown:
        remaining = cooldown - (now - last)
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)

        embed = discord.Embed(
            title="🛠 Galaxy Work",
            description=f"⏳ You are still resting.\nTry again in **{minutes}m {seconds}s**.",
            color=galaxy_color()
        )
        return await ctx.send(embed=embed)

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

    await send_log(
        "work",
        ctx.author,
        f"Completed work for {fmt(reward)} gems.",
        {
            "Reward": fmt(reward),
            "Gems Before": fmt(before),
            "Gems After": fmt(u["gems"])
        }
    )


# --------------------------------------------------------------
# GIFT
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

    before_s = sender["gems"]
    before_r = receiver["gems"]

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

    await send_log(
        "gift",
        ctx.author,
        f"Gifted {fmt(val)} gems to {member}.",
        {
            "Amount": fmt(val),
            "Receiver": f"{member} ({member.id})",
            "Sender Gems Before": fmt(before_s),
            "Sender Gems After": fmt(sender["gems"]),
            "Receiver Gems Before": fmt(before_r),
            "Receiver Gems After": fmt(receiver["gems"])
        }
    )


# --------------------------------------------------------------
# COINFLIP
# --------------------------------------------------------------
@bot.command()
async def coinflip(ctx, bet: str, choice: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]
    before = u.get("gems", 0)

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

    await send_log(
        "coinflip",
        ctx.author,
        f"Coinflip {res.upper()} ({choice} vs {result}).",
        {
            "Bet": fmt(amount),
            "Choice": choice,
            "Outcome": result,
            "Net": fmt(profit),
            "Rig": rig or "none",
            "Gems Before": fmt(before),
            "Gems After": fmt(u["gems"])
        }
    )


# --------------------------------------------------------------
# SLOTS (rig-aware, 3x4)
# --------------------------------------------------------------
@bot.command()
async def slots(ctx, bet: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]
    before = u.get("gems", 0)

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
        win_sym = random.choice(symbols)
        row2 = [win_sym, win_sym, win_sym, random.choice(symbols)]
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
        profit = -amount
        reward = 0
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
            f"**Multiplier:** 2.00x\n"
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

    await send_log(
        "slots",
        ctx.author,
        f"Slots {res.upper()} with best match {best_match}x {best_symbol}.",
        {
            "Bet": fmt(amount),
            "Net": fmt(profit),
            "Rig": rig or "none",
            "Reels": grid,
            "Gems Before": fmt(before),
            "Gems After": fmt(u["gems"])
        }
    )


# --------------------------------------------------------------
# MINES GAME
# --------------------------------------------------------------

class MinesButton(Button):
    def __init__(self, x, y, is_bomb):
        super().__init__(label="?", style=discord.ButtonStyle.grey, row=y)
        self.x = x
        self.y = y
        self.is_bomb = is_bomb
        self.revealed = False

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.view

        if interaction.user.id != view.player_id:
            return await interaction.response.send_message(
                "❌ This isn't your game.", ephemeral=True
            )

        if view.finished:
            return await interaction.response.send_message(
                "❌ The game is already finished.", ephemeral=True
            )

        if self.revealed:
            return await interaction.response.send_message(
                "❌ Already clicked.", ephemeral=True
            )

        self.revealed = True
        view.clicks += 1

        if self.is_bomb:
            self.style = discord.ButtonStyle.red
            self.label = "💣"
            view.finished = True

            for row in view.board:
                for btn in row:
                    btn.disabled = True

            embed = view.build_embed(exploded=True)
            await interaction.response.edit_message(embed=embed, view=view)
            await view.finish(interaction, exploded=True)
            return

        # Safe click
        self.style = discord.ButtonStyle.green
        self.label = "🔹"

        multiplier = 1 + (view.clicks * 0.15)
        view.current_multiplier = multiplier

        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class MinesView(View):
    def __init__(self, player_id, bet, rig_mode):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.bet = bet
        self.rig_mode = rig_mode
        self.board = []
        self.clicks = 0
        self.finished = False
        self.current_multiplier = 1.0

        if rig_mode == "bless":
            bombs = 1
        elif rig_mode == "curse":
            bombs = 8
        else:
            bombs = 4

        cells = [(x, y) for x in range(5) for y in range(5)]
        bomb_cells = random.sample(cells, bombs)

        grid = []
        for y in range(5):
            row = []
            for x in range(5):
                is_bomb = (x, y) in bomb_cells
                btn = MinesButton(x, y, is_bomb)
                self.add_item(btn)
                row.append(btn)
            grid.append(row)

        self.board = grid

    def build_embed(self, exploded=False):
        color = galaxy_color()
        status = "💥 BOOM!" if exploded else "⛏ Still digging..."

        embed = discord.Embed(
            title="💣 Galaxy Mines",
            description=(
                f"**Bet:** {fmt(self.bet)}\n"
                f"**Clicks:** {self.clicks}\n"
                f"**Multiplier:** {self.current_multiplier:.2f}x\n"
                f"**Status:** {status}\n\n"
                f"Press **Cashout** to secure your gems!"
            ),
            color=color
        )
        return embed

    async def finish(self, interaction, exploded):
        player = interaction.user
        ensure_user(player.id)
        u = data[str(player.id)]
        before = u["gems"]

        if exploded:
            profit = -self.bet
        else:
            reward = int(self.bet * self.current_multiplier)
            profit = reward - self.bet
            u["gems"] += reward

        save_data(data)

        add_history(player.id, {
            "game": "mines",
            "bet": self.bet,
            "result": "explode" if exploded else "cashout",
            "earned": profit,
            "timestamp": time.time()
        })

        rows = []
        for y in range(5):
            row = ""
            for x in range(5):
                btn = self.board[y][x]
                row += "💣 " if btn.is_bomb else "🔹 "
            rows.append(row)
        grid = "\n".join(rows)

        await send_log(
            "mines",
            player,
            "Mines finished.",
            {
                "Bet": fmt(self.bet),
                "Clicks": self.clicks,
                "Multiplier": f"{self.current_multiplier:.2f}x",
                "Exploded": exploded,
                "Net": fmt(profit),
                "Grid": f"```{grid}```",
                "Rig": self.rig_mode or "none",
                "Gems Before": fmt(before),
                "Gems After": fmt(u["gems"])
            }
        )


@bot.command()
async def mines(ctx, bet: str):
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

    view = MinesView(ctx.author.id, amount, rig)

    async def cashout_callback(interaction: discord.Interaction):
        if interaction.user.id != view.player_id:
            return await interaction.response.send_message(
                "❌ This isn't your game.", ephemeral=True
            )
        if view.finished:
            return await interaction.response.send_message(
                "❌ Already finished.", ephemeral=True
            )

        view.finished = True
        for row in view.board:
            for btn in row:
                btn.disabled = True

        reward = int(amount * view.current_multiplier)
        profit = reward - amount

        ensure_user(interaction.user.id)
        data[str(interaction.user.id)]["gems"] += reward
        save_data(data)

        rows = []
        for y in range(5):
            row = ""
            for x in range(5):
                btn = view.board[y][x]
                row += "💣 " if btn.is_bomb else "🔹 "
            rows.append(row)
        grid = "\n".join(rows)

        embed = discord.Embed(
            title="💰 Cashout Successful!",
            description=(
                f"**Bet:** {fmt(amount)}\n"
                f"**Clicks:** {view.clicks}\n"
                f"**Multiplier:** {view.current_multiplier:.2f}x\n"
                f"**Reward:** {fmt(reward)}\n"
                f"**Net:** {fmt(profit)}"
            ),
            color=discord.Color.green()
        )
        embed.add_field(name="Board", value=f"```{grid}```", inline=False)
        await interaction.response.edit_message(embed=embed, view=view)

        await send_log(
            "mines",
            ctx.author,
            "Cashed out.",
            {
                "Bet": fmt(amount),
                "Clicks": view.clicks,
                "Multiplier": f"{view.current_multiplier:.2f}x",
                "Net": fmt(profit),
                "Grid": f"```{grid}```",
                "Rig": rig or "none",
                "Gems Before": fmt(u['gems']),
                "Gems After": fmt(data[str(ctx.author.id)]['gems'])
            }
        )

    cash_btn = Button(label="CASHOUT", style=discord.ButtonStyle.green)
    cash_btn.callback = cashout_callback
    view.add_item(cash_btn)

    await ctx.send(embed=view.build_embed(), view=view)


# --------------------------------------------------------------
# TOWER GAME (3 lanes, rig-aware)
# --------------------------------------------------------------

class TowerButton(Button):
    def __init__(self, row, col, view_ref):
        labels = ["Left", "Middle", "Right"]
        super().__init__(label=labels[col], style=discord.ButtonStyle.secondary, row=row)
        self.row = row
        self.col = col
        self.view_ref = view_ref  # TowerView instance

    async def callback(self, interaction: discord.Interaction):
        view: TowerView = self.view_ref

        if interaction.user.id != view.player_id:
            return await interaction.response.send_message(
                "❌ This isn't your game.", ephemeral=True
            )

        if view.finished:
            return await interaction.response.send_message(
                "❌ The game is already finished.", ephemeral=True
            )

        if self.row != view.current_row:
            return await interaction.response.send_message(
                "❌ You're not on this row yet.", ephemeral=True
            )

        await view.handle_choice(interaction, self.col)


class TowerView(View):
    def __init__(self, player_id, bet, rig_mode):
        super().__init__(timeout=None)
        self.player_id = player_id
        self.bet = bet
        self.rig_mode = rig_mode  # "bless", "curse", or None
        self.total_rows = 8
        self.current_row = 0
        self.cleared_rows = 0
        self.finished = False

        # board[row][col] -> True = bomb, False = safe
        self.board = []
        self._generate_board()

        # create buttons
        for r in range(self.total_rows):
            row_buttons = []
            for c in range(3):
                btn = TowerButton(r, c, self)
                if r != 0:
                    btn.disabled = True
                self.add_item(btn)
                row_buttons.append(btn)

        # Cashout button
        self.cash_btn = Button(label="💰 CASHOUT", style=discord.ButtonStyle.success, row=self.total_rows)
        self.cash_btn.callback = self.cashout_callback
        self.add_item(self.cash_btn)

    def _generate_board(self):
        """Prepare bombs; rig slightly via bless/curse (but still looks random)."""
        for _ in range(self.total_rows):
            # one bomb per row
            bomb_col = random.randint(0, 2)

            if self.rig_mode == "bless":
                # Bless: 20% chance row has NO bomb at all
                if random.random() < 0.2:
                    row = [False, False, False]
                else:
                    row = [False, False, False]
                    row[bomb_col] = True
            elif self.rig_mode == "curse":
                # Curse: still one bomb per row (looks normal),
                # but we will force the first click to hit a bomb in handle_choice.
                row = [False, False, False]
                row[bomb_col] = True
            else:
                row = [False, False, False]
                row[bomb_col] = True

            self.board.append(row)

    def _multiplier_for_rows(self, rows: int) -> float:
        if rows <= 0:
            return 1.0
        # mildly aggressive growth
        return round(1.25 ** rows, 2)

    def _current_multiplier(self) -> float:
        return self._multiplier_for_rows(self.cleared_rows)

    def _build_grid_string(self, reveal: bool = False) -> str:
        lines = []
        for r in range(self.total_rows - 1, -1, -1):
            row = ""
            for c in range(3):
                btn_idx = r * 3 + c
                btn: Button = list(self.children)[btn_idx]  # first buttons are tower, then cashout

                if reveal:
                    if self.board[r][c]:
                        # bomb
                        if self.finished and r == self.current_row and c == getattr(self, "exploded_col", -1):
                            row += "💥 "
                        else:
                            row += "💣 "
                    else:
                        row += "✅ "
                else:
                    # show only clicked states
                    if btn.disabled and not self.board[r][c]:
                        row += "✅ "
                    elif btn.disabled and self.board[r][c]:
                        row += "💣 "
                    else:
                        row += "⬛ "
            lines.append(row)
        return "\n".join(lines)

    def build_embed(self, reveal: bool = False, final_text: str | None = None) -> discord.Embed:
        mult = self._current_multiplier()
        status = "🏁 Finished" if self.finished else "🧗 Still climbing..."

        desc = (
            f"**Bet:** {fmt(self.bet)}\n"
            f"**Rows cleared:** {self.cleared_rows}/{self.total_rows}\n"
            f"**Current Multiplier:** `{mult:.2f}x`\n"
            f"**Status:** {status}\n"
        )

        if final_text:
            desc += f"\n{final_text}\n"

        embed = discord.Embed(
            title="🏰 Galaxy Tower",
            description=desc,
            color=galaxy_color()
        )
        grid = self._build_grid_string(reveal=reveal)
        embed.add_field(name="Tower", value=f"```{grid}```", inline=False)
        return embed

    async def handle_choice(self, interaction: discord.Interaction, col: int):
        user = interaction.user

        # Determine if this is bomb
        is_bomb = self.board[self.current_row][col]

        # CURSE: first row click is forced bomb (but board still *looks* random)
        if self.rig_mode == "curse" and self.current_row == 0:
            is_bomb = True

        # BLESS: if user would hit a bomb, silently move it away
        if self.rig_mode == "bless" and is_bomb:
            safe_cols = [c for c in range(3) if c != col]
            new_bomb_col = random.choice(safe_cols)
            # move bomb
            self.board[self.current_row][col] = False
            self.board[self.current_row][new_bomb_col] = True
            is_bomb = False  # this click becomes safe

        # Disable row buttons
        for item in self.children:
            if isinstance(item, TowerButton) and item.row == self.current_row:
                item.disabled = True
                if item.col == col:
                    item.style = discord.ButtonStyle.success if not is_bomb else discord.ButtonStyle.danger

        if is_bomb:
            # explosion
            self.finished = True
            self.exploded_col = col
            embed = self.build_embed(reveal=True, final_text=f"💥 You hit a bomb on row **{self.current_row + 1}**.\nYou lost **{fmt(self.bet)}** gems.")
            await interaction.response.edit_message(embed=embed, view=self)
            await self._log_result(user, profit=-self.bet, result="lose_bomb")
            return

        # safe
        self.cleared_rows += 1
        self.current_row += 1

        # if reached top, auto-finish as win
        if self.current_row >= self.total_rows:
            self.finished = True
            mult = self._current_multiplier()
            reward = int(self.bet * mult)
            profit = reward - self.bet

            ensure_user(user.id)
            u = data[str(user.id)]
            before = u["gems"]
            u["gems"] += reward
            save_data(data)

            embed = self.build_embed(
                reveal=True,
                final_text=(
                    f"🏆 You cleared all rows!\n"
                    f"Multiplier: `{mult:.2f}x`\n"
                    f"Reward: **{fmt(reward)}**\n"
                    f"Net: **{fmt(profit)}**"
                )
            )
            await interaction.response.edit_message(embed=embed, view=self)

            add_history(user.id, {
                "game": "tower",
                "bet": self.bet,
                "result": "win_full",
                "earned": profit,
                "timestamp": time.time()
            })

            await send_log(
                "tower",
                user,
                "Tower game WIN (full clear).",
                {
                    "Bet": fmt(self.bet),
                    "Rows Cleared": self.cleared_rows,
                    "Multiplier": f"{mult:.2f}x",
                    "Reward": fmt(reward),
                    "Net": fmt(profit),
                    "Rig": self.rig_mode or "none"
                }
            )
            return

        # enable next row
        for item in self.children:
            if isinstance(item, TowerButton) and item.row == self.current_row:
                item.disabled = False

        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def cashout_callback(self, interaction: discord.Interaction):
        user = interaction.user
        if user.id != self.player_id:
            return await interaction.response.send_message(
                "❌ This isn't your game.", ephemeral=True
            )

        if self.finished:
            return await interaction.response.send_message(
                "❌ The game is already finished.", ephemeral=True
            )

        # CURSE: if user cashes out with 0 rows, they lose full bet
        if self.rig_mode == "curse" and self.cleared_rows == 0:
            self.finished = True
            embed = self.build_embed(
                reveal=True,
                final_text=f"💥 Cursed cashout... you panicked too early.\nYou lost **{fmt(self.bet)}** gems."
            )
            await interaction.response.edit_message(embed=embed, view=self)
            await self._log_result(user, profit=-self.bet, result="lose_cashout_curse")
            return

        # BLESS: if user cashes out with 0 rows, treat as 1 cleared
        if self.rig_mode == "bless" and self.cleared_rows == 0:
            self.cleared_rows = 1

        self.finished = True

        mult = self._current_multiplier()
        reward = int(self.bet * mult)
        profit = reward - self.bet

        ensure_user(user.id)
        u = data[str(user.id)]
        before = u["gems"]
        u["gems"] += reward
        save_data(data)

        # disable all buttons
        for item in self.children:
            if isinstance(item, Button):
                item.disabled = True

        embed = self.build_embed(
            reveal=True,
            final_text=(
                f"💰 You cashed out safely!\n"
                f"Rows cleared: **{self.cleared_rows}**\n"
                f"Multiplier: `{mult:.2f}x`\n"
                f"Reward: **{fmt(reward)}**\n"
                f"Net: **{fmt(profit)}**"
            )
        )
        await interaction.response.edit_message(embed=embed, view=self)

        add_history(user.id, {
            "game": "tower",
            "bet": self.bet,
            "result": "cashout",
            "earned": profit,
            "timestamp": time.time()
        })

        await send_log(
            "tower",
            user,
            "Tower game CASHOUT.",
            {
                "Bet": fmt(self.bet),
                "Rows Cleared": self.cleared_rows,
                "Multiplier": f"{mult:.2f}x",
                "Reward": fmt(reward),
                "Net": fmt(profit),
                "Rig": self.rig_mode or "none",
                "Gems Before": fmt(before),
                "Gems After": fmt(u["gems"])
            }
        )

    async def _log_result(self, user: discord.Member | discord.User, profit: int, result: str):
        ensure_user(user.id)
        u = data[str(user.id)]
        before = u["gems"]

        add_history(user.id, {
            "game": "tower",
            "bet": self.bet,
            "result": result,
            "earned": profit,
            "timestamp": time.time()
        })

        await send_log(
            "tower",
            user,
            f"Tower game {result.upper()}",
            {
                "Bet": fmt(self.bet),
                "Rows Cleared": self.cleared_rows,
                "Multiplier": f"{self._current_multiplier():.2f}x",
                "Net": fmt(profit),
                "Rig": self.rig_mode or "none",
                "Gems Before": fmt(before),
                "Gems After": fmt(u["gems"])
            }
        )


@bot.command()
async def tower(ctx, bet: str):
    """Climb the tower by picking 1 of 3 tiles per row. Cash out anytime."""
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

    view = TowerView(ctx.author.id, amount, rig)
    embed = view.build_embed()
    await ctx.send(embed=embed, view=view)


# --------------------------------------------------------------
# BLACKJACK (rig-aware, fully interactive)
# --------------------------------------------------------------

CARD_VALUES = {
    "A": 11, "K": 10, "Q": 10, "J": 10,
    "10": 10, "9": 9, "8": 8, "7": 7, "6": 6,
    "5": 5, "4": 4, "3": 3, "2": 2
}
CARD_ORDER = list(CARD_VALUES.keys())


def draw_card():
    return random.choice(CARD_ORDER)


def hand_value(hand: list[str]) -> int:
    total = sum(CARD_VALUES[c] for c in hand)
    aces = hand.count("A")
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


class BJHit(Button):
    def __init__(self, view_ref):
        super().__init__(label="Hit", style=discord.ButtonStyle.primary)
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction):
        view: BlackjackView = self.view_ref

        if interaction.user.id != view.player_id:
            return await interaction.response.send_message("❌ Not your game.", ephemeral=True)

        if view.finished:
            return await interaction.response.send_message("❌ Game ended.", ephemeral=True)

        view.player_hand.append(draw_card())
        view.actions.append(f"Hit → {view.player_hand} ({hand_value(view.player_hand)})")

        if hand_value(view.player_hand) > 21:
            await view.finish(interaction, reason="bust")
            return

        embed = view.make_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class BJStand(Button):
    def __init__(self, view_ref):
        super().__init__(label="Stand", style=discord.ButtonStyle.secondary)
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction):
        view: BlackjackView = self.view_ref

        if interaction.user.id != view.player_id:
            return await interaction.response.send_message("❌ Not your game.", ephemeral=True)

        if view.finished:
            return await interaction.response.send_message("❌ Game ended.", ephemeral=True)

        view.actions.append("Stand")
        await view.finish(interaction, reason="stand")


class BlackjackView(View):
    def __init__(self, player_id, bet, rig):
        super().__init__(timeout=40)
        self.player_id = player_id
        self.bet = bet
        self.rig = rig

        self.player_hand = [draw_card(), draw_card()]
        self.dealer_hand = [draw_card(), draw_card()]

        self.finished = False
        self.actions = [
            f"Initial: Player {self.player_hand} ({hand_value(self.player_hand)}), "
            f"Dealer [{self.dealer_hand[0]}, ?]"
        ]

        self.add_item(BJHit(self))
        self.add_item(BJStand(self))

    def make_embed(self, reveal: bool = False, final_text: str | None = None):
        pv = hand_value(self.player_hand)
        dv = hand_value(self.dealer_hand) if reveal else "❓"

        embed = discord.Embed(
            title="🃏 Galaxy Blackjack",
            color=galaxy_color()
        )

        embed.add_field(
            name="Your Hand",
            value=f"{' '.join(self.player_hand)}\n**Total:** {pv}",
            inline=False
        )

        if reveal:
            embed.add_field(
                name="Dealer Hand",
                value=f"{' '.join(self.dealer_hand)}\n**Total:** {dv}",
                inline=False
            )
        else:
            embed.add_field(
                name="Dealer Hand",
                value=f"{self.dealer_hand[0]} ❓",
                inline=False
            )

        if final_text:
            embed.add_field(name="Result", value=final_text, inline=False)
            embed.set_footer(text="Game finished.")
        else:
            embed.set_footer(text="Hit or Stand?")

        return embed

    async def finish(self, interaction: discord.Interaction, reason: str):
        ensure_user(self.player_id)
        u = data[str(self.player_id)]
        before = u["gems"]

        self.finished = True

        # Remove buttons
        for b in self.children:
            b.disabled = True

        pv = hand_value(self.player_hand)

        # === RIG HANDLING (curse/bless insta-resolve) ===
        if self.rig in ("bless", "curse"):
            if self.rig == "curse":
                profit = -self.bet
                result_text = "💀 You are cursed… Dealer wins."
                self.actions.append("Rigged: Cursed Loss")
            else:
                profit = int(self.bet * 1.7)
                u["gems"] += self.bet + profit
                save_data(data)
                result_text = f"✨ Blessed! You win.\nNet: **{fmt(profit)}**"
                self.actions.append("Rigged: Blessed Win")

            embed = self.make_embed(reveal=True, final_text=result_text)
            await interaction.response.edit_message(embed=embed, view=self)

            add_history(self.player_id, {
                "game": "blackjack",
                "bet": self.bet,
                "result": "rigged",
                "earned": profit,
                "timestamp": time.time()
            })

            await send_log(
                "blackjack",
                interaction.user,
                f"Rigged Blackjack {self.rig.upper()}",
                {
                    "Bet": fmt(self.bet),
                    "Net": fmt(profit),
                    "Rig": self.rig,
                    "Player Hand": f"{self.player_hand} ({pv})",
                    "Dealer Hand": f"{self.dealer_hand} ({hand_value(self.dealer_hand)})",
                    "Actions": "\n".join(self.actions),
                    "Gems Before": fmt(before),
                    "Gems After": fmt(u["gems"])
                }
            )
            return

        # === NORMAL BLACKJACK ===

        # Dealer plays
        dv = hand_value(self.dealer_hand)
        while dv < 17:
            self.dealer_hand.append(draw_card())
            dv = hand_value(self.dealer_hand)

        self.actions.append(
            f"Dealer Final: {self.dealer_hand} ({dv})"
        )

        # Evaluate result
        if pv > 21:
            profit = -self.bet
            result_text = "💥 You busted."
            result = "lose"

        elif dv > 21:
            profit = int(self.bet * 0.7)
            u["gems"] += self.bet + profit
            result_text = f"✨ Dealer busts! You win.\nNet: **{fmt(profit)}**"
            result = "win"

        elif pv > dv:
            profit = int(self.bet * 0.7)
            u["gems"] += self.bet + profit
            result_text = f"🏆 You win!\nNet: **{fmt(profit)}**"
            result = "win"

        elif pv < dv:
            profit = -self.bet
            result_text = "💀 Dealer wins."
            result = "lose"

        else:
            profit = 0
            u["gems"] += self.bet
            result_text = "🤝 It's a push."
            result = "push"

        save_data(data)

        embed = self.make_embed(reveal=True, final_text=result_text)
        await interaction.response.edit_message(embed=embed, view=self)

        add_history(self.player_id, {
            "game": "blackjack",
            "bet": self.bet,
            "result": result,
            "earned": profit,
            "timestamp": time.time()
        })

        await send_log(
            "blackjack",
            interaction.user,
            f"Blackjack {result.upper()}",
            {
                "Bet": fmt(self.bet),
                "Result": result,
                "Net": fmt(profit),
                "Rig": self.rig or "none",
                "Player Final": f"{self.player_hand} ({pv})",
                "Dealer Final": f"{self.dealer_hand} ({dv})",
                "Actions": "\n".join(self.actions),
                "Gems Before": fmt(before),
                "Gems After": fmt(u["gems"])
            }
        )


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

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)
    view = BlackjackView(ctx.author.id, amount, rig)

    embed = view.make_embed()
    await ctx.send(embed=embed, view=view)


# --------------------------------------------------------------
# CHEST PANEL & SHOP
# --------------------------------------------------------------

def chest_summary_line(key: str):
    cfg = CHEST_CONFIG[key]
    price = cfg["price"]
    rewards = cfg["rewards"]
    chances = cfg["chances"]

    min_r = min(rewards)
    max_r = max(rewards)
    total_w = sum(chances)
    ev = sum(r * w for r, w in zip(rewards, chances)) / total_w if total_w > 0 else 0

    return (
        f"{cfg['emoji']} **{cfg['name']}**\n"
        f"Price: **{fmt(price)}** gems\n"
        f"Rewards: **{fmt(min_r)}–{fmt(max_r)}**\n"
        f"Avg payout: ~**{fmt(int(ev))}**\n"
    )


@bot.command()
async def chests(ctx):
    """Open the chest panel."""
    desc = []
    for key in CHEST_ORDER:
        desc.append(chest_summary_line(key))

    embed = discord.Embed(
        title="📦 Galaxy Chests",
        description=(
            "Open loot chests for random gem rewards.\n"
            "Click a rarity below to open your personal menu.\n\n" +
            "\n".join(desc)
        ),
        color=galaxy_color()
    )
    embed.set_footer(text="All rewards are RNG.")

    class ChestButton(Button):
        def __init__(self, chest_key, label_text, style):
            super().__init__(label=label_text, style=style)
            self.chest_key = chest_key

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message(
                    "❌ Only the command user can open this menu.",
                    ephemeral=True
                )
            await open_chest_menu(interaction, self.chest_key)

    async def open_chest_menu(interaction: discord.Interaction, chest_key: str):
        cfg = CHEST_CONFIG[chest_key]

        reward_lines = []
        for r, c in zip(cfg["rewards"], cfg["chances"]):
            reward_lines.append(f"• **{fmt(r)}** — `{c}%`")

        desc = (
            f"{cfg['emoji']} **{cfg['name']}**\n"
            f"Price per chest: **{fmt(cfg['price'])}**\n\n"
            "**Possible rewards:**\n" +
            "\n".join(reward_lines)
        )

        chest_embed = discord.Embed(
            title="📦 Chest Shop",
            description=desc,
            color=galaxy_color()
        )

        class BuyButton(Button):
            def __init__(self, label_text, amount, style):
                super().__init__(label=label_text, style=style)
                self.amount = amount

            async def callback(self, inter: discord.Interaction):
                if inter.user.id != interaction.user.id:
                    return await inter.response.send_message(
                        "❌ Not your chest menu.",
                        ephemeral=True
                    )
                await handle_purchase(inter, chest_key, self.amount)

        class ShopView(View):
            def __init__(self):
                super().__init__(timeout=120)
                self.add_item(BuyButton("Open 1", 1, discord.ButtonStyle.primary))
                self.add_item(BuyButton("Open 5", 5, discord.ButtonStyle.secondary))
                self.add_item(BuyButton("Open 10", 10, discord.ButtonStyle.success))

        await interaction.response.send_message(
            embed=chest_embed,
            view=ShopView(),
            ephemeral=True
        )

    async def handle_purchase(inter: discord.Interaction, chest_key: str, count: int):
        ensure_user(inter.user.id)
        u = data[str(inter.user.id)]
        cfg = CHEST_CONFIG[chest_key]
        price = cfg["price"]
        total_cost = price * count

        if u["gems"] < total_cost:
            return await inter.response.send_message(
                f"❌ Not enough gems for **{count}x** {cfg['name']} (need **{fmt(total_cost)}**).",
                ephemeral=True
            )

        before = u["gems"]
        u["gems"] -= total_cost
        save_data(data)

        rewards_collected = []
        total_reward = 0

        for _ in range(count):
            reward = roll_chest_reward(chest_key)
            rewards_collected.append(reward)
            total_reward += reward

        u["gems"] += total_reward
        save_data(data)

        net = total_reward - total_cost

        add_history(inter.user.id, {
            "game": f"chest_{chest_key}",
            "bet": total_cost,
            "result": f"open_{count}",
            "earned": net,
            "timestamp": time.time()
        })

        results_text = "\n".join(
            f"Chest {i+1}: **{fmt(r)}** gems"
            for i, r in enumerate(rewards_collected)
        )

        embed = discord.Embed(
            title="📦 Chest Results",
            description=(
                f"Opened: **{count}** chest(s)\n\n"
                f"**Results:**\n{results_text}\n\n"
                f"Total spent: **{fmt(total_cost)}**\n"
                f"Total gained: **{fmt(total_reward)}**\n"
                f"Net: **{fmt(net)}** gems"
            ),
            color=galaxy_color()
        )

        await inter.response.edit_message(embed=embed, view=None)

        await send_log(
            "chest_open",
            inter.user,
            f"Opened {count}x {cfg['name']}.",
            {
                "Chest Type": cfg["name"],
                "Count": count,
                "Total Spent": fmt(total_cost),
                "Total Reward": fmt(total_reward),
                "Net": fmt(net),
                "Rewards": results_text[:1000],
                "Gems Before": fmt(before),
                "Gems After": fmt(u["gems"])
            }
        )

    view = View(timeout=None)
    view.add_item(ChestButton("common", "Common", discord.ButtonStyle.secondary))
    view.add_item(ChestButton("rare", "Rare", discord.ButtonStyle.primary))
    view.add_item(ChestButton("epic", "Epic", discord.ButtonStyle.success))
    view.add_item(ChestButton("legendary", "Legendary", discord.ButtonStyle.danger))
    view.add_item(ChestButton("mythic", "Mythic", discord.ButtonStyle.secondary))
    view.add_item(ChestButton("galaxy", "Galaxy", discord.ButtonStyle.primary))

    await ctx.send(embed=embed, view=view)


# --------------------------------------------------------------
# LOTTERY SYSTEM
# --------------------------------------------------------------

LOTTERY_FILE = "lottery.json"

# Ensure file exists
if not os.path.exists(LOTTERY_FILE):
    with open(LOTTERY_FILE, "w") as f:
        json.dump({"tickets": {}, "open": False}, f)


def load_lottery():
    with open(LOTTERY_FILE, "r") as f:
        return json.load(f)


def save_lottery(data):
    with open(LOTTERY_FILE, "w") as f:
        json.dump(data, f, indent=4)


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def lottery_start(ctx):
    """Start a new lottery (Admin only)."""
    lot = load_lottery()
    lot["tickets"] = {}
    lot["open"] = True
    save_lottery(lot)

    embed = discord.Embed(
        title="🎟️ New Lottery Started!",
        description="Lottery is now **OPEN**.\nBuy tickets with: `!ticket <amount>`",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    await send_log(
        "lottery_ticket",
        ctx.author,
        "Lottery started.",
        {"Status": "OPEN"}
    )


@bot.command()
async def ticket(ctx, amount: str):
    """Buy lottery tickets."""
    ensure_user(ctx.author.id)

    lot = load_lottery()
    if not lot.get("open"):
        return await ctx.send("❌ No active lottery right now.")

    u = data[str(ctx.author.id)]
    parsed = parse_amount(amount, u["gems"], allow_all=False)

    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid ticket amount.")

    cost = parsed * 1_000_000  # 1 ticket costs 1m
    if u["gems"] < cost:
        return await ctx.send("❌ Not enough gems.")

    before = u["gems"]
    u["gems"] -= cost
    save_data(data)

    lot["tickets"].setdefault(str(ctx.author.id), 0)
    lot["tickets"][str(ctx.author.id)] += parsed
    save_lottery(lot)

    embed = discord.Embed(
        title="🎟️ Ticket Purchased",
        description=(
            f"You bought **{parsed}** ticket(s).\n"
            f"Cost: **{fmt(cost)}** gems"
        ),
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    await send_log(
        "lottery_ticket",
        ctx.author,
        f"Bought {parsed} ticket(s).",
        {
            "Tickets Bought": parsed,
            "Cost": fmt(cost),
            "Gems Before": fmt(before),
            "Gems After": fmt(u['gems'])
        }
    )


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def lottery_end(ctx):
    """End lottery and pick winner (Admin only)."""
    lot = load_lottery()

    if not lot.get("open"):
        return await ctx.send("❌ Lottery is not open.")

    tickets = lot.get("tickets", {})

    # Flatten ticket entries
    entries = []
    for uid, count in tickets.items():
        entries.extend([uid] * count)

    if not entries:
        lot["open"] = False
        save_lottery(lot)
        return await ctx.send("❌ No tickets sold. Lottery closed.")

    # Pick random user
    winner_id = int(random.choice(entries))
    ensure_user(winner_id)

    total_tickets = sum(tickets.values())
    prize = total_tickets * 1_000_000  # 1m per ticket
    bonus = int(prize * LOTTERY_BONUS)
    total_prize = prize + bonus

    u = data[str(winner_id)]
    before = u["gems"]
    u["gems"] += total_prize
    save_data(data)

    lot["open"] = False
    save_lottery(lot)

    winner = ctx.guild.get_member(winner_id)

    embed = discord.Embed(
        title="🎉 Lottery Winner!",
        description=(
            f"🏆 Winner: {winner.mention if winner else winner_id}\n"
            f"🎟️ Total Tickets: **{total_tickets}**\n"
            f"💎 Prize: **{fmt(total_prize)}** gems"
        ),
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

    await send_log(
        "lottery_end",
        winner,
        "Lottery ended.",
        {
            "Winner": f"{winner} ({winner_id})",
            "Total Tickets": total_tickets,
            "Prize": fmt(total_prize),
            "Gems Before": fmt(before),
            "Gems After": fmt(u["gems"])
        }
    )


# --------------------------------------------------------------
# ADMIN: DROPBOX REWARD
# --------------------------------------------------------------

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def dropbox(ctx, member: discord.Member, amount: str):
    """Give gems directly to a user (like a treasure drop)."""
    ensure_user(member.id)

    val = parse_amount(amount, None, allow_all=False)
    if val is None or val <= 0:
        return await ctx.send("❌ Invalid amount.")

    u = data[str(member.id)]
    before = u["gems"]

    u["gems"] += val
    save_data(data)

    embed = discord.Embed(
        title="🎁 Dropbox Delivered",
        description=f"{member.mention} received **{fmt(val)}** gems.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    await send_log(
        "dropbox",
        ctx.author,
        f"Gave dropbox reward to {member}.",
        {
            "Receiver": f"{member} ({member.id})",
            "Amount": fmt(val),
            "Before": fmt(before),
            "After": fmt(u["gems"])
        }
    )


# --------------------------------------------------------------
# ADMIN: BLESS
# --------------------------------------------------------------

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def bless(ctx, member: discord.Member, count: int = None):
    """Bless a user (infinite or +charges)."""
    ensure_user(member.id)
    u = data[str(member.id)]

    if count is None:
        # toggle infinite bless
        u["bless_infinite"] = not u.get("bless_infinite", False)
        status = "ENABLED" if u["bless_infinite"] else "DISABLED"
    else:
        if count <= 0:
            return await ctx.send("❌ Invalid charge amount.")
        u["bless_charges"] += count
        status = f"{count} charges added"

    save_data(data)

    embed = discord.Embed(
        title="✨ Bless Applied",
        description=f"{member.mention} blessed! `{status}`",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

    await send_log(
        "bless",
        ctx.author,
        f"Bless applied to {member}.",
        {"Status": status}
    )


# --------------------------------------------------------------
# ADMIN: CURSE
# --------------------------------------------------------------

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def curse(ctx, member: discord.Member, count: int = None):
    """Curse a user (infinite or +charges)."""
    ensure_user(member.id)
    u = data[str(member.id)]

    if count is None:
        u["curse_infinite"] = not u.get("curse_infinite", False)
        status = "ENABLED" if u["curse_infinite"] else "DISABLED"
    else:
        if count <= 0:
            return await ctx.send("❌ Invalid charge amount.")
        u["curse_charges"] += count
        status = f"{count} charges added"

    save_data(data)

    embed = discord.Embed(
        title="💀 Curse Applied",
        description=f"{member.mention} cursed! `{status}`",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

    await send_log(
        "curse",
        ctx.author,
        f"Curse applied to {member}.",
        {"Status": status}
    )


# --------------------------------------------------------------
# ROLE PAYOUT (giverole)
# --------------------------------------------------------------

@bot.command()
@commands.has_guild_permissions(manage_roles=True)
async def giverole(ctx, role_query: str, amount: str):
    """Give gems to everyone with a specific role."""
    role = find_role_by_query(ctx.guild, role_query)
    if not role:
        return await ctx.send("❌ Role not found.")

    parsed = parse_amount(amount, None, allow_all=False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid amount.")

    affected = []
    for member in role.members:
        ensure_user(member.id)
        data[str(member.id)]["gems"] += parsed
        affected.append(member.id)

    save_data(data)

    embed = discord.Embed(
        title="💎 Role Payout",
        description=f"Gave **{fmt(parsed)}** gems to **{len(affected)}** members of {role.mention}.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    await send_log(
        "giverole",
        ctx.author,
        f"Payout to role {role.name}.",
        {
            "Role": role.name,
            "Amount": fmt(parsed),
            "Affected Users": len(affected)
        }
    )


# --------------------------------------------------------------
# ROLE TAX (removerole)
# --------------------------------------------------------------

@bot.command()
@commands.has_guild_permissions(manage_roles=True)
async def removerole(ctx, role_query: str, amount: str):
    """Remove gems from everyone with a specific role."""
    role = find_role_by_query(ctx.guild, role_query)
    if not role:
        return await ctx.send("❌ Role not found.")

    parsed = parse_amount(amount, None, allow_all=False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid amount.")

    affected = []
    for member in role.members:
        ensure_user(member.id)
        data[str(member.id)]["gems"] -= parsed
        affected.append(member.id)

    save_data(data)

    embed = discord.Embed(
        title="💸 Role Tax Applied",
        description=f"Removed **{fmt(parsed)}** gems from **{len(affected)}** members with role {role.mention}.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

    await send_log(
        "removerole",
        ctx.author,
        f"Tax applied to role {role.name}.",
        {
            "Role": role.name,
            "Amount": fmt(parsed),
            "Affected Users": len(affected)
        }
    )


# --------------------------------------------------------------
# GIVE TO ALL USERS
# --------------------------------------------------------------

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def giveall(ctx, amount: str):
    """Give gems to EVERY registered casino account."""
    parsed = parse_amount(amount, None, allow_all=False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid amount.")

    count = 0
    for uid in list(data.keys()):
        data[uid]["gems"] += parsed
        count += 1
    save_data(data)

    embed = discord.Embed(
        title="💎 Global Payout",
        description=f"Gave **{fmt(parsed)}** gems to **{count}** accounts.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    await send_log(
        "giveall",
        ctx.author,
        f"Gave all users {fmt(parsed)} gems.",
        {
            "Users Affected": count,
            "Amount": fmt(parsed)
        }
    )


# --------------------------------------------------------------
# BACKUP + RESTORE
# --------------------------------------------------------------

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def savebackup(ctx):
    """Manually trigger a backup."""
    await backup_to_channel(reason="manual")

    embed = discord.Embed(
        title="💾 Backup Created",
        description="A manual backup has been saved to the backup channel.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    await send_log("backup", ctx.author, "Manual backup created.")


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def restorebackup(ctx, *, data_text: str):
    """Restore casino data from raw JSON text."""
    global data
    try:
        new_data = json.loads(data_text)
    except Exception:
        return await ctx.send("❌ Invalid JSON.")

    data = new_data
    save_data(data)

    embed = discord.Embed(
        title="💾 Backup Restored",
        description="Casino data has been restored successfully.",
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)

    await send_log("restore", ctx.author, "Backup restored.")


# --------------------------------------------------------------
# BOT READY + RUN
# --------------------------------------------------------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if not auto_backup_task.is_running():
        auto_backup_task.start()
    print("Galaxy Casino is online.")


print("Bot code loaded. Starting bot...")
bot.run(TOKEN)
