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
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------------- CONSTANTS ---------------------- #
MAX_BET = 200_000_000  # 200m
LOTTERY_BONUS = 0.10

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
    try:
        n = int(round(float(n)))
    except:
        return str(n)

    if n >= 1_000_000_000:
        v = n / 1_000_000_000
        return f"{v:.2f}".rstrip("0").rstrip(".") + "b"
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.2f}".rstrip("0").rstrip(".") + "m"
    if n >= 1_000:
        v = n / 1_000
        return f"{v:.2f}".rstrip("0").rstrip(".") + "k"
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
    if isinstance(text, (int, float)):
        return float(text)

    t = str(text).lower().replace(",", "").replace(" ", "")

    if t == "all":
        if not allow_all or user_gems is None:
            return None
        return float(user_gems)

    try:
        if t.endswith("k"): return float(t[:-1]) * 1000
        if t.endswith("m"): return float(t[:-1]) * 1_000_000
        if t.endswith("b"): return float(t[:-1]) * 1_000_000_000
        return float(t)
    except:
        return None

def parse_duration(d):
    s = d.strip().lower()
    if len(s) < 2:
        return None
    unit = s[-1]
    num_str = s[:-1]
    try:
        value = float(num_str)
    except:
        return None
    if value <= 0:
        return None
    if unit == "s": return int(value)
    if unit == "m": return int(value * 60)
    if unit == "h": return int(value * 3600)
    if unit == "d": return int(value * 86400)
    return None

def normalize_role_name(name):
    return "".join(ch.lower() for ch in name if ch.isalnum())

def find_role_by_query(guild, query):
    query = query.strip()
    digits = "".join(ch for ch in query if ch.isdigit())
    if digits:
        try:
            rid = int(digits)
            role = guild.get_role(rid)
            if role:
                return role
        except:
            pass

    norm = normalize_role_name(query)
    if not norm:
        return None

    roles = guild.roles

    exact = [r for r in roles if normalize_role_name(r.name) == norm]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return sorted(exact, key=lambda r: len(r.name))[0]

    partial = [r for r in roles if norm in normalize_role_name(r.name)]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        return sorted(partial, key=lambda r: len(r.name))[0]

    return None

def roll_chest_reward(chest_key):
    cfg = CHEST_CONFIG[chest_key]
    rewards = cfg["rewards"]
    chances = cfg["chances"]
    total = sum(chances)
    r = random.uniform(0, total)
    upto = 0
    for amt, weight in zip(rewards, chances):
        if upto + weight >= r:
            return amt
        upto += weight
    return rewards[-1]

# ---------------------- RIG SYSTEM ---------------------- #
def consume_rig(u):
    mode = None
    if u.get("curse_infinite") or u.get("curse_charges", 0) > 0:
        mode = "curse"
        if u.get("curse_chcharges", 0) > 0:
            u["curse_charges"] -= 1
    elif u.get("bless_infinite") or u.get("bless_charges", 0) > 0:
        mode = "bless"
        if u.get("bless_charges", 0) > 0:
            u["bless_charges"] -= 1
    save_data(data)
    return mode
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
#                         WORK (10–15m)
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
#                         GIFT
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
#                     COINFLIP (start of command)
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

# RIG HANDLING
    if rig == "curse":
        result = "tails" if choice == "heads" else "heads"
    elif rig == "bless":
        result = choice
    else:
        result = random.choice(["heads", "tails"])

    # RESOLVE WIN/LOSS
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
#                      SLOTS (rig-aware)
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

    # BASE row (for display only)
    row1 = spin_row()

    # RIG SYSTEM
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

    # DETERMINE WINNER
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
        res = "win"
        result_text = f"3x **{best_symbol}** — You win!"
    else:
        multiplier = 0.0
        reward = 0
        profit = -amount
        res = "lose"
        result_text = "No match."

    save_data(data)

    # DISPLAY GRID
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
        return await ctx.send("❌ Mines must be between **1–15**.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)

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
                return await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended.", ephemeral=True)
            if revealed[self.index] is not None:
                return await interaction.response.send_message("❌ Already clicked.", ephemeral=True)

            # CURSE → first tile = bomb
            if rig == "curse" and first_click:
                first_click = False
                exploded_index = self.index
                revealed[self.index] = False
                game_over = True

                # reveal bombs
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

                return await ctx.send(f"💥 You hit a mine and lost **{fmt(amount)}** gems.")

            first_click = False

            # BLESS → all safe
            if rig == "bless":
                revealed[self.index] = True
                self.label = SAFE
                self.style = discord.ButtonStyle.success
                correct_clicks += 1
                return await interaction.response.edit_message(embed=embed_update(), view=view)

            # NORMAL MINES LOGIC
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

                return await ctx.send(f"💥 You hit a mine and lost **{fmt(amount)}** gems.")

            # SAFE TILE
            revealed[self.index] = True
            self.label = SAFE
            self.style = discord.ButtonStyle.success
            correct_clicks += 1

            await interaction.response.edit_message(embed=embed_update(), view=view)

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
                return await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended.", ephemeral=True)

            # CURSE → even cashout = full loss
            if rig == "curse":
                game_over = True
                exploded_index = 0

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

                return await ctx.send(f"💥 You panicked and lost **{fmt(amount)}** gems.")

            # BLESS: make sure cashout is always >0
            if rig == "bless" and correct_clicks == 0:
                correct_clicks = 1

            # NORMAL CASHOUT
            game_over = True
            reward = calc_reward()
            u["gems"] += reward
            save_data(data)

            # reveal bombs
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
#                         TOWERS (rig-aware)
# --------------------------------------------------------------
@bot.command()
async def towers(ctx, bet: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet!")
    if amount > MAX_BET:
        return await ctx.send("❌ Max bet is 200m.")
    if amount > u["gems"]:
        return await ctx.send("❌ Not enough gems.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)

    rows = 8
    cols = 4
    safe_symbol = "🟩"
    bomb_symbol = "💥"

    safe_counts = [3, 3, 3, 2, 2, 2, 1, 1]

    grid = [[None] * cols for _ in range(rows)]
    revealed = [[False] * cols for _ in range(rows)]

    for r in range(rows):
        safe_tiles = random.sample(range(cols), safe_counts[r])
        for c in range(cols):
            grid[r][c] = (c in safe_tiles)

    multiplier_table = [1.0, 1.27, 1.54, 1.88, 2.27, 2.72, 3.33, 4.2, 5.0]

    current_row = 0
    owner = ctx.author.id
    game_over = False

    class Cell(Button):
        def __init__(self, r, c):
            super().__init__(label="?", style=discord.ButtonStyle.secondary)
            self.r = r
            self.c = c
            self.row = r

        async def callback(self, interaction):
            nonlocal current_row, game_over

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game over.", ephemeral=True)
            if self.r != current_row:
                return await interaction.response.send_message("❌ Wrong row.", ephemeral=True)

            safe = grid[self.r][self.c]

            if rig == "bless":
                safe = True
            elif rig == "curse" and current_row == 0:
                safe = False

            revealed[self.r][self.c] = True
            self.disabled = True

            if not safe:
                game_over = True
                self.label = bomb_symbol
                self.style = discord.ButtonStyle.danger

                for r in range(rows):
                    for i, btn in enumerate(view.children):
                        if isinstance(btn, Cell) and btn.r == r:
                            if grid[r][btn.c]:
                                btn.label = safe_symbol
                                btn.style = discord.ButtonStyle.success
                            else:
                                btn.label = bomb_symbol
                                btn.style = discord.ButtonStyle.danger
                            btn.disabled = True

                add_history(ctx.author.id, {
                    "game": "towers",
                    "bet": amount,
                    "result": "lose",
                    "earned": -amount,
                    "timestamp": time.time()
                })

                try:
                    await interaction.response.edit_message(embed=make_embed(), view=view)
                except: pass

                return await ctx.send(f"💥 You hit a bomb! Lost **{fmt(amount)}** gems.")

            self.label = safe_symbol
            self.style = discord.ButtonStyle.success

            current_row += 1

            if current_row >= rows:
                reward = amount * multiplier_table[-1]
                profit = reward - amount
                u["gems"] += reward
                save_data(data)

                game_over = True
                for btn in view.children:
                    btn.disabled = True

                add_history(ctx.author.id, {
                    "game": "towers",
                    "bet": amount,
                    "result": "win_all",
                    "earned": profit,
                    "timestamp": time.time()
                })

                try:
                    await interaction.response.edit_message(embed=make_embed(), view=view)
                except: pass

                return await ctx.send(f"🌟 You cleared the tower! Won **{fmt(profit)}** gems!")

            try:
                await interaction.response.edit_message(embed=make_embed(), view=view)
            except:
                pass

    class Cashout(Button):
        def __init__(self):
            super().__init__(label="💰 Cashout", style=discord.ButtonStyle.primary, row=rows)

        async def callback(self, interaction):
            nonlocal game_over

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Already ended.", ephemeral=True)

            multiplier = multiplier_table[current_row]
            reward = amount * multiplier
            profit = reward - amount
            u["gems"] += reward
            save_data(data)

            game_over = True
            for btn in view.children:
                btn.disabled = True

            add_history(ctx.author.id, {
                "game": "towers",
                "bet": amount,
                "result": "cashout",
                "earned": profit,
                "timestamp": time.time()
            })

            try:
                await interaction.response.edit_message(embed=make_embed(), view=view)
            except:
                pass

            return await ctx.send(f"💰 You cashed out **{fmt(profit)}** gems!")

    def make_embed():
        multiplier = multiplier_table[current_row]
        reward = amount * multiplier
        e = discord.Embed(
            title="🗼 Galaxy Towers",
            description=(
                f"💵 Bet: **{fmt(amount)}**\n"
                f"🔥 Multiplier: **{multiplier:.2f}x**\n"
                f"💰 Potential: **{fmt(reward)}**"
            ),
            color=galaxy_color()
        )
        e.set_footer(text=f"Row {current_row + 1}/{rows}")
        return e

    view = View(timeout=None)

    for r in range(rows):
        for c in range(cols):
            view.add_item(Cell(r, c))

    view.add_item(Cashout())

    await ctx.send(embed=make_embed(), view=view)


# --------------------------------------------------------------
#                         BLACKJACK (rig-aware)
# --------------------------------------------------------------
@bot.command()
async def blackjack(ctx, bet: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet!")
    if amount > MAX_BET:
        return await ctx.send("❌ Max bet is 200m.")
    if amount > u["gems"]:
        return await ctx.send("❌ Not enough gems.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)

    deck = list(range(52))
    random.shuffle(deck)

    def card_value(card):
        rank = card % 13
        if rank >= 10:
            return 10
        if rank == 0:
            return 11
        return rank + 1

    def hand_value(hand):
        total = sum(card_value(c) for c in hand)
        aces = sum(1 for c in hand if c % 13 == 0)
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        return total

    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    if rig == "bless":
        while hand_value(player) != 21:
            dealer.append(deck.pop())
    elif rig == "curse":
        while hand_value(dealer) <= hand_value(player):
            dealer.append(deck.pop())

    player_turn = True
    owner = ctx.author.id

    class Hit(Button):
        def __init__(self):
            super().__init__(label="Hit", style=discord.ButtonStyle.success)

        async def callback(self, interaction):
            nonlocal player_turn

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            if not player_turn:
                return await interaction.response.send_message("❌ Already stood.", ephemeral=True)

            player.append(deck.pop())

            if rig == "bless" and hand_value(player) < 21:
                dealer.append(deck.pop())
            elif rig == "curse" and hand_value(player) <= 21:
                dealer.append(deck.pop())

            if hand_value(player) > 21:
                player_turn = False

                view.disable_all_items()
                save_data(data)

                add_history(ctx.author.id, {
                    "game": "blackjack",
                    "bet": amount,
                    "result": "lose",
                    "earned": -amount,
                    "timestamp": time.time()
                })

                try:
                    await interaction.response.edit_message(embed=make_embed(True), view=view)
                except:
                    pass
                return await ctx.send(f"💥 You busted! Lost **{fmt(amount)}** gems.")

            try:
                await interaction.response.edit_message(embed=make_embed(False), view=view)
            except:
                pass

    class Stand(Button):
        def __init__(self):
            super().__init__(label="Stand", style=discord.ButtonStyle.danger)

        async def callback(self, interaction):
            nonlocal player_turn

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            if not player_turn:
                return

            player_turn = False

            while hand_value(dealer) < 17:
                dealer.append(deck.pop())

            pv = hand_value(player)
            dv = hand_value(dealer)

            if pv > 21:
                result = "lose"
                profit = -amount
            elif dv > 21 or pv > dv:
                result = "win"
                profit = amount
                u["gems"] += amount * 2
            elif pv == dv:
                result = "push"
                profit = 0
                u["gems"] += amount
            else:
                result = "lose"
                profit = -amount

            save_data(data)

            view.disable_all_items()

            add_history(ctx.author.id, {
                "game": "blackjack",
                "bet": amount,
                "result": result,
                "earned": profit,
                "timestamp": time.time()
            })

            try:
                await interaction.response.edit_message(embed=make_embed(True), view=view)
            except:
                pass

            if result == "win":
                await ctx.send(f"🏆 You won **{fmt(profit)}** gems!")
            elif result == "push":
                await ctx.send(f"🤝 It's a tie. Your bet is returned.")
            else:
                await ctx.send(f"💥 You lost **{fmt(amount)}** gems.")

    def make_embed(show_all):
        pv = hand_value(player)
        dv = hand_value(dealer) if show_all else "??"

        e = discord.Embed(
            title="🃏 Galaxy Blackjack",
            description=(
                f"**Your Hand ({pv})**:\n"
                f"{' '.join(map(str, player))}\n\n"
                f"**Dealer ({dv})**:\n"
                f"{' '.join(map(str, dealer if show_all else [dealer[0], '??']))}"
            ),
            color=galaxy_color()
        )
        return e

    view = View(timeout=None)
    view.add_item(Hit())
    view.add_item(Stand())

    await ctx.send(embed=make_embed(False), view=view)


# --------------------------------------------------------------
#                           CHESTS
# --------------------------------------------------------------
@bot.command()
async def chest(ctx, chest_type: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    chest_type = chest_type.lower()
    if chest_type not in CHEST_CONFIG:
        return await ctx.send("❌ Invalid chest type.")

    cfg = CHEST_CONFIG[chest_type]

    price = cfg["price"]
    rewards = cfg["rewards"]
    chances = cfg["chances"]

    if u["gems"] < price:
        return await ctx.send("❌ Not enough gems.")

    u["gems"] -= price
    reward = roll_chest_reward(chest_type)
    u["gems"] += reward
    save_data(data)

    profit = reward - price

    add_history(ctx.author.id, {
        "game": f"chest_{chest_type}",
        "bet": price,
        "result": "reward",
        "earned": profit,
        "timestamp": time.time()
    })

    embed = discord.Embed(
        title=f"{cfg['emoji']} {cfg['name']}",
        description=(
            f"**Price:** {fmt(price)}\n"
            f"**Reward:** {fmt(reward)}\n"
            f"**Profit:** {fmt(profit)}"
        ),
        color=galaxy_color()
    )
    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                        LOTTERY (FIXED)
# --------------------------------------------------------------
lottery_active = False
lottery_price = 0
lottery_end_time = 0
lottery_entries = {}

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def lottery(ctx, ticket_price: str, duration: str):
    global lottery_active, lottery_price, lottery_end_time, lottery_entries

    if lottery_active:
        return await ctx.send("❌ A lottery is already running.")

    price = parse_amount(ticket_price)
    if price is None or price <= 0:
        return await ctx.send("❌ Invalid ticket price.")

    dur = parse_duration(duration)
    if dur is None:
        return await ctx.send("❌ Invalid duration. Use 10s / 5m / 2h ...")

    lottery_active = True
    lottery_price = price
    lottery_end_time = time.time() + dur
    lottery_entries = {}

    async def check_loop():
        await asyncio.sleep(dur)

        global lottery_active, lottery_entries

        if not lottery_active:
            return

        if len(lottery_entries) == 0:
            lottery_active = False
            return await ctx.send("❌ No participants. Lottery cancelled.")

        pool = sum(lottery_entries.values())
        winner = random.choice(list(lottery_entries.keys()))
        bonus = pool * LOTTERY_BONUS
        prize = pool + bonus

        ensure_user(winner)
        data[str(winner)]["gems"] += prize
        save_data(data)

        await ctx.send(
            f"🎉 Lottery ended!\n"
            f"**Winner:** <@{winner}>\n"
            f"**Prize:** {fmt(prize)}"
        )

        add_history(winner, {
            "game": "lottery",
            "bet": pool,
            "result": "win",
            "earned": prize,
            "timestamp": time.time()
        })

        lottery_active = False

    asyncio.create_task(check_loop())

    class Buy(Button):
        def __init__(self):
            super().__init__(label=f"Buy Ticket ({fmt(price)})", style=discord.ButtonStyle.success)

        async def callback(self, interaction):
            if not lottery_active:
                return await interaction.response.send_message("❌ Lottery ended.", ephemeral=True)

            ensure_user(interaction.user.id)
            u = data[str(interaction.user.id)]

            if u["gems"] < price:
                return await interaction.response.send_message("❌ Not enough gems.", ephemeral=True)

            u["gems"] -= price
            lottery_entries[interaction.user.id] = lottery_entries.get(interaction.user.id, 0) + price
            save_data(data)

            await interaction.response.send_message(
                f"🎫 Bought a ticket! You now have {fmt(lottery_entries[interaction.user.id])} in the pool.",
                ephemeral=True
            )

    view = View(timeout=None)
    view.add_item(Buy())

    embed = discord.Embed(
        title="🎟️ Galaxy Lottery",
        description=(
            f"**Ticket Price:** {fmt(price)}\n"
            f"⏳ Ends in: {duration}\n"
            f"Click the button below to join!"
        ),
        color=galaxy_color()
    )
    await ctx.send(embed=embed, view=view)


# --------------------------------------------------------------
#                        GIVEALL (requires MEMBERS INTENT)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def giveall(ctx, amount: str):
    am = parse_amount(amount)
    if am is None or am <= 0:
        return await ctx.send("❌ Invalid amount.")

    count = 0
    guild = ctx.guild

    async for m in guild.fetch_members(limit=None):
        if not m.bot:
            ensure_user(m.id)
            data[str(m.id)]["gems"] += am
            count += 1

    save_data(data)
    await ctx.send(f"💎 Distributed **{fmt(am)}** gems to **{count}** members!")


# --------------------------------------------------------------
#                        GIVEROLE & REMOVEROLE
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def giverole(ctx, role_query: str, amount: str):
    role = find_role_by_query(ctx.guild, role_query)
    if not role:
        return await ctx.send("❌ Role not found.")

    am = parse_amount(amount)
    if am <= 0:
        return await ctx.send("❌ Invalid amount.")

    members = [m for m in role.members if not m.bot]
    if len(members) == 0:
        return await ctx.send("❌ No human members in that role.")

    for m in members:
        ensure_user(m.id)
        data[str(m.id)]["gems"] += am

    save_data(data)
    await ctx.send(f"💎 Added **{fmt(am)}** gems to **{len(members)}** members with role `{role.name}`.")

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def removerole(ctx, role_query: str, amount: str):
    role = find_role_by_query(ctx.guild, role_query)
    if not role:
        return await ctx.send("❌ Role not found.")

    am = parse_amount(amount)
    if am <= 0:
        return await ctx.send("❌ Invalid amount.")

    members = [m for m in role.members if not m.bot]
    if len(members) == 0:
        return await ctx.send("❌ No human members in that role.")

    for m in members:
        ensure_user(m.id)
        data[str(m.id)]["gems"] = max(0, data[str(m.id)]["gems"] - am)

    save_data(data)
    await ctx.send(f"💀 Removed **{fmt(am)}** gems from **{len(members)}** members with role `{role.name}`.")


# --------------------------------------------------------------
#                            TAX (everyone -5%)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def tax(ctx, percent: int = 5):
    if percent < 1 or percent > 50:
        return await ctx.send("❌ Tax must be 1–50%.")

    count = 0
    total_removed = 0

    for uid, u in data.items():
        if "gems" in u:
            before = u["gems"]
            removed = before * (percent / 100)
            u["gems"] -= removed
            total_removed += removed
            count += 1

    save_data(data)
    await ctx.send(
        f"💸 Taxed **{percent}%** from **{count}** users.\n"
        f"Total removed: **{fmt(total_removed)}**"
    )


# --------------------------------------------------------------
#                         BACKUP SYSTEM
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def backup(ctx):
    ch = bot.get_channel(BACKUP_CHANNEL_ID)
    if not ch:
        return await ctx.send("❌ Backup channel not found.")

    with open(DATA_FILE, "rb") as f:
        await ch.send("📦 **Casino Backup**", file=discord.File(f, filename="casino_backup.json"))

    await ctx.send("✅ Backup uploaded.")


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def restorelatest(ctx):
    ch = bot.get_channel(BACKUP_CHANNEL_ID)
    if not ch:
        return await ctx.send("❌ Backup channel missing.")

    msgs = [msg async for msg in ch.history(limit=20)]
    for m in msgs:
        if m.attachments:
            att = m.attachments[0]
            data_bytes = await att.read()
            with open(DATA_FILE, "wb") as f:
                f.write(data_bytes)
            global data
            data = load_data()
            return await ctx.send("✅ Restored latest backup.")

    await ctx.send("❌ No backup file found.")


# --------------------------------------------------------------
#                            HELP
# --------------------------------------------------------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="🌌 Galaxy Casino — Help",
        description="Commands for players:",
        color=galaxy_color()
    )

    embed.add_field(name="Money", value=
        "`!bal`\n"
        "`!bal @user`\n"
        "`!daily`\n"
        "`!work`\n"
        "`!gift @user amount`\n",
        inline=False)

    embed.add_field(name="Games", value=
        "`!coinflip amount heads/tails`\n"
        "`!slots amount`\n"
        "`!mines amount [mines]`\n"
        "`!towers amount`\n"
        "`!blackjack amount`\n"
        "`!chest type`\n",
        inline=False)

    embed.add_field(name="Lottery", value=
        "`!lottery <price> <10s/5m/1h>` (admin starts lottery)\n",
        inline=False)

    embed.set_footer(text="Use !helpadmin for admin commands.")
    await ctx.send(embed=embed)


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def helpadmin(ctx):
    embed = discord.Embed(
        title="🛠 Admin Commands",
        description="Power tools:",
        color=galaxy_color()
    )

    embed.add_field(name="Admin Tools", value=
        "`!giveall amount`\n"
        "`!giverole role amount`\n"
        "`!removerole role amount`\n"
        "`!tax 5`\n"
        "`!backup`\n"
        "`!restorelatest`\n"
        "`!lottery price duration`\n",
        inline=False)

    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                            READY EVENT
# --------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}\nBot is online!")
    await bot.change_presence(activity=discord.Game("Galaxy Casino 🌌"))


# --------------------------------------------------------------
#                            RUN
# --------------------------------------------------------------
bot.run(TOKEN)