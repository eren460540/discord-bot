import discord
from discord.ext import commands
import json
import os
import random
from discord.ui import Button, View
import time
import asyncio

TOKEN = os.getenv("TOKEN")
DATA_FILE = "casino_data.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="?", intents=intents, help_command=None)

# ---------------------- CONSTANTS ---------------------- #
MAX_BET = 200_000_000  # 200m

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

# ---------------------- GALAXY THEME ---------------------- #
GALAXY_COLORS = [
    discord.Color.from_rgb(138, 43, 226),   # Electric Purple
    discord.Color.from_rgb(75, 0, 130),     # Indigo
    discord.Color.from_rgb(106, 13, 173),   # Cosmic Purple
    discord.Color.from_rgb(148, 0, 211),    # Dark Violet
    discord.Color.from_rgb(218, 112, 214),  # Orchid
    discord.Color.from_rgb(0, 191, 255),    # Deep Sky Blue
]

def galaxy_color():
    return random.choice(GALAXY_COLORS)

# ---------------------- USER MANAGEMENT ---------------------- #
def ensure_user(user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {}
    user = data[uid]
    user.setdefault("gems", 25.0)
    user.setdefault("last_daily", 0.0)
    user.setdefault("last_work", 0.0)
    user.setdefault("history", [])
    user.setdefault("bless_streak", 0)
    user.setdefault("curse_streak", 0)
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

# ---------------------- LOTTERY STATE ---------------------- #
if "_lottery" not in data:
    data["_lottery"] = {
        "active": False,
        "ticket_price": 0.0,
        "end_time": 0.0,
        "tickets": [],
        "message_id": None,
        "channel_id": None,
    }
    save_data(data)

def get_lottery_state():
    return data.get("_lottery", {
        "active": False,
        "ticket_price": 0.0,
        "end_time": 0.0,
        "tickets": [],
        "message_id": None,
        "channel_id": None,
    })

def set_lottery_state(state):
    data["_lottery"] = state
    save_data(data)

# ---------------------- PARSERS ---------------------- #
def parse_amount(text, user_gems=None, allow_all=False):
    """
    Parses amounts like:
    200000000, 200,000,000, 200m, 0.2b, 150k, 1.5m
    Returns float or None if invalid.
    """
    if isinstance(text, (int, float)):
        return float(text)

    t = str(text).lower().replace(",", "").replace(" ", "")
    if t == "all":
        if not allow_all or user_gems is None:
            return None
        return float(user_gems)

    # suffix-based
    try:
        if t.endswith("k"):
            return float(t[:-1]) * 1_000
        if t.endswith("m"):
            return float(t[:-1]) * 1_000_000
        if t.endswith("b"):
            return float(t[:-1]) * 1_000_000_000
        # plain number
        return float(t)
    except ValueError:
        return None

def parse_duration(text):
    """
    very simple duration parser: e.g. 30m, 2h, 1h30m, 45s
    """
    t = text.lower().replace(" ", "")
    total = 0
    num = ""
    for ch in t:
        if ch.isdigit() or ch == ".":
            num += ch
        else:
            if not num:
                return None
            val = float(num)
            if ch == "s":
                total += val
            elif ch == "m":
                total += val * 60
            elif ch == "h":
                total += val * 3600
            elif ch == "d":
                total += val * 86400
            else:
                return None
            num = ""
    if num:
        # no suffix left over
        return None
    return int(total)

# ---------------------- BLESS / CURSE HELPERS ---------------------- #
def consume_bless_curse(user):
    """
    Returns 'bless', 'curse', or None and decrements streaks.
    If both set, curse wins (evil > good 😈).
    """
    mode = None
    if user.get("curse_streak", 0) > 0:
        user["curse_streak"] -= 1
        mode = "curse"
    elif user.get("bless_streak", 0) > 0:
        user["bless_streak"] -= 1
        mode = "bless"
    save_data(data)
    return mode

# --------------------------------------------------------------
#                      BALANCE
# --------------------------------------------------------------
@bot.command()
async def balance(ctx):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]
    gems = round(u["gems"], 2)
    embed = discord.Embed(
        title="🌌 Galaxy Balance",
        description=f"✨ {ctx.author.mention}\nYou currently hold **{gems}** gems in the cosmos.",
        color=galaxy_color()
    )
    embed.set_footer(text="Galaxy Casino • Reach for the stars ✨")
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      DAILY
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

    reward = 25
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
        description=f"{ctx.author.mention} claimed **{reward}** gems from the galaxy!",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      WORK (10m–15m)
# --------------------------------------------------------------
@bot.command()
async def work(ctx):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]
    now = time.time()
    cooldown = 3600  # 1h
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

    reward = random.uniform(10_000_000, 15_000_000)
    reward = round(reward, 2)
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
        description=f"✨ {ctx.author.mention}, you earned **{reward:.2f}** gems from your job.",
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
        description=f"{ctx.author.mention} sent **{val:.2f}** gems to {member.mention}.",
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
        return await ctx.send("❌ Max bet is **200m** gems.")
    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")

    choice = choice.lower()
    if choice not in ["heads", "tails"]:
        return await ctx.send("❌ Choose `heads` or `tails`.")

    # subtract bet first
    u["gems"] -= amount
    save_data(data)

    mode = consume_bless_curse(u)
    if mode == "curse":
        # auto lose
        result = "heads" if choice == "tails" else "tails"
        profit = -amount
    else:
        # roll normally, or force win if bless
        if mode == "bless":
            result = choice
        else:
            result = random.choice(["heads", "tails"])

        if result == choice:
            win = amount * 1.0  # net profit 1x
            u["gems"] += amount + win
            profit = win
        else:
            profit = -amount

    save_data(data)

    if profit > 0:
        title = "🪙 Coinflip — You Won!"
        color = discord.Color.green()
        res = "win"
    else:
        title = "🪙 Coinflip — You Lost"
        color = discord.Color.red()
        res = "lose"

    embed = discord.Embed(
        title=title,
        description=(
            f"🎯 Your choice: **{choice}**\n"
            f"🌀 Result: **{result}**\n"
            f"💰 Net: **{profit:.2f} gems**"
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
#                      SLOTS (3x4, 4 symbols, 2x win, no 2-tile)
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

    symbols = ["🍒", "🍋", "⭐", "💎"]

    def spin_row():
        return [random.choice(symbols) for _ in range(4)]

    # 3 rows × 4 columns
    row1 = spin_row()
    row2 = spin_row()
    row3 = spin_row()

    def row_best_match(row):
        counts = {}
        for s in row:
            counts[s] = counts.get(s, 0) + 1
        best_sym = max(counts, key=counts.get)
        return counts[best_sym], best_sym

    # bless/curse influences outcome
    mode = consume_bless_curse(u)

    if mode == "curse":
        # force no 3-of-a-kind in middle rows
        for _ in range(50):
            row1 = spin_row()
            row2 = spin_row()
            row3 = spin_row()
            r2_m, _ = row_best_match(row2)
            r3_m, _ = row_best_match(row3)
            if r2_m < 3 and r3_m < 3:
                break
    elif mode == "bless":
        # try to force a 3-of-a-kind in row2 or row3
        for _ in range(50):
            row1 = spin_row()
            row2 = spin_row()
            row3 = spin_row()
            r2_m, _ = row_best_match(row2)
            r3_m, _ = row_best_match(row3)
            if r2_m >= 3 or r3_m >= 3:
                break

    r2_match, r2_sym = row_best_match(row2)
    r3_match, r3_sym = row_best_match(row3)

    best_match = 0
    best_symbol = None
    for m, s in [(r2_match, r2_sym), (r3_match, r3_sym)]:
        if m > best_match:
            best_match = m
            best_symbol = s

    if best_match >= 3:
        multiplier = 2.0  # fixed 2x win
        result_text = f"3x {best_symbol}! **WIN**"
    else:
        multiplier = 0.0
        result_text = "No match."

    reward = amount * multiplier
    profit = reward - amount

    if reward > 0:
        u["gems"] += reward
    save_data(data)

    grid = (
        f"{row1[0]} {row1[1]} {row1[2]} {row1[3]}\n"
        f"➡ {row2[0]} {row2[1]} {row2[2]} {row2[3]} ⬅\n"
        f"➡ {row3[0]} {row3[1]} {row3[2]} {row3[3]} ⬅"
    )

    embed = discord.Embed(
        title="🎰 Galaxy Slots",
        description=(
            f"**Bet:** {amount}\n"
            f"**Multiplier:** {multiplier:.2f}x\n"
            f"**Result:** {result_text}\n"
            f"**Net:** {profit:.2f} gems"
        ),
        color=galaxy_color()
    )
    embed.add_field(name="Reels", value=f"```{grid}```", inline=False)
    embed.set_footer(text="Galaxy Slots • Spin among the stars 🌌")
    await ctx.send(embed=embed)

    add_history(ctx.author.id, {
        "game": "slots",
        "bet": amount,
        "result": "win" if reward > 0 else "lose",
        "earned": profit,
        "timestamp": time.time()
    })

# --------------------------------------------------------------
#                      MINES (unchanged core, but max bet & parse)
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

    owner = ctx.author.id
    game_over = False
    correct_clicks = 0

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
                f"💵 Bet: **{amount}**\n"
                f"💰 Current: **{reward:.2f}**\n"
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
            nonlocal correct_clicks, game_over, exploded_index

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended!", ephemeral=True)
            if revealed[self.index] is not None:
                return await interaction.response.send_message("❌ Already clicked!", ephemeral=True)

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
                await ctx.send(f"💥 You hit a mine and lost **{amount} gems**.")
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
            nonlocal game_over

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended!", ephemeral=True)

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
                "earned": reward,
                "timestamp": time.time()
            })

            try:
                await interaction.response.edit_message(embed=embed_update(), view=view)
            except:
                pass

            await ctx.send(f"💰 You cashed out **{reward:.2f} gems**!")

    view.add_item(Cashout())
    await ctx.send(embed=embed_update(), view=view)

# --------------------------------------------------------------
#                      TOWER (kept, only bet parse & max)
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
        e.add_field(name="Bet", value=str(amount))
        e.add_field(name="Earned", value=f"{earned:.2f}")
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

            if self.pos == bomb_col:
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
                return await ctx.send(f"💥 BOOM! You lost **{amount} gems**!")

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
                    "earned": reward,
                    "timestamp": time.time()
                })
                await interaction.response.edit_message(embed=embed_update(True), view=view)
                return await ctx.send(f"🏆 Cleared all rows! **+{reward:.2f} gems**!")

            await interaction.response.edit_message(embed=embed_update(False), view=view)

    class Cashout(Button):
        def __init__(self):
            super().__init__(label="💰 Cashout", style=discord.ButtonStyle.primary)

        async def callback(self, interaction):
            nonlocal game_over, earned_on_end

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game ended!", ephemeral=True)

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
                "earned": reward,
                "timestamp": time.time()
            })
            await interaction.response.edit_message(embed=embed_update(True), view=view)
            await ctx.send(f"💰 Cashed out **{reward:.2f} gems**!")

    view.add_item(Choice(0))
    view.add_item(Choice(1))
    view.add_item(Choice(2))
    view.add_item(Cashout())

    await ctx.send(embed=embed_update(False), view=view)

# --------------------------------------------------------------
#                      BLACKJACK (NERFED)
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

    mode = consume_bless_curse(u)
    u["gems"] -= amount
    save_data(data)

    # Auto-resolve for bless/curse
    if mode == "curse":
        profit = -amount
        result_text = "You feel a dark curse... and instantly lose."
        color = discord.Color.red()
        add_history(ctx.author.id, {
            "game": "blackjack",
            "bet": amount,
            "result": "lose",
            "earned": profit,
            "timestamp": time.time()
        })
        embed = discord.Embed(
            title="🃏 Galaxy Blackjack — Cursed Loss",
            description=f"💀 {result_text}\n**Net:** {profit:.2f} gems",
            color=color
        )
        return await ctx.send(embed=embed)

    if mode == "bless":
        profit = amount * 1.7  # normal win
        u["gems"] += amount + profit
        save_data(data)
        result_text = "✨ You are blessed by the cosmos and instantly win."
        color = discord.Color.green()
        add_history(ctx.author.id, {
            "game": "blackjack",
            "bet": amount,
            "result": "win",
            "earned": profit,
            "timestamp": time.time()
        })
        embed = discord.Embed(
            title="🃏 Galaxy Blackjack — Blessed Win",
            description=f"🌌 {result_text}\n**Net:** {profit:.2f} gems",
            color=color
        )
        return await ctx.send(embed=embed)

    # Normal blackjack game
    player = [draw_card(), draw_card()]
    dealer = [draw_card(), draw_card()]

    def make_embed(show_dealer=False, final=False):
        pv = hand_value(player)
        dv = hand_value(dealer) if show_dealer else "??"
        desc = (
            f"🧑 Your hand: {' '.join(player)} (Total: **{pv}**)\n"
            f"🂠 Dealer hand: {dealer[0]} {' '.join(dealer[1:]) if show_dealer else '❓'} (Total: **{dv}**)"
        )
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
        # dealer hits to 17+
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
            # win
            mult = 2.0 if blackjack_player else 1.7
            profit = amount * (mult - 1)
            res = "win"
            text = "Dealer busted. You win!"
        elif blackjack_player and not blackjack_dealer:
            mult = 2.0
            profit = amount * (mult - 1)
            res = "win"
            text = "Blackjack! You win with a cosmic hand."
        elif blackjack_dealer and not blackjack_player:
            profit = -amount
            res = "lose"
            text = "Dealer has blackjack. You lose."
        elif pv > dv:
            mult = 1.7
            profit = amount * (mult - 1)
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
            u["gems"] += amount  # refund
        save_data(data)

        add_history(ctx.author.id, {
            "game": "blackjack",
            "bet": amount,
            "result": res,
            "earned": profit,
            "timestamp": time.time()
        })

        final_embed = make_embed(show_dealer=True, final=True)
        final_embed.add_field(name="Result", value=f"{text}\n**Net:** {profit:.2f} gems", inline=False)
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
#                      LEADERBOARD
# --------------------------------------------------------------
@bot.command()
async def leaderboard(ctx):
    lb = []
    for user_id, info in data.items():
        if user_id == "_lottery":
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
        except:
            name = f"User {user_id}"
        embed.add_field(name=f"#{i} — {name}", value=f"💎 {round(gems,2)} gems", inline=False)

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
            value=f"Bet: {entry['bet']} | Result: {entry['result']} | Earned: {entry['earned']}",
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
        return await ctx.send("📊 No stats yet. Play some games first!")

    total_games = len(hist)
    total_bet = sum(e.get("bet", 0) for e in hist)
    total_earned = sum(e.get("earned", 0) for e in hist)
    wins = sum(1 for e in hist if e.get("earned", 0) > 0)
    losses = sum(1 for e in hist if e.get("earned", 0) < 0)
    biggest_win = max((e.get("earned", 0) for e in hist), default=0)
    biggest_loss = min((e.get("earned", 0) for e in hist), default=0)

    win_rate = (wins / total_games * 100) if total_games > 0 else 0

    embed = discord.Embed(
        title=f"📊 Galaxy Stats — {ctx.author.name}",
        color=galaxy_color()
    )
    embed.add_field(name="Total Games", value=str(total_games))
    embed.add_field(name="Wins / Losses", value=f"{wins} / {losses}")
    embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%")
    embed.add_field(name="Total Bet", value=f"{total_bet:.2f}")
    embed.add_field(name="Net Profit", value=f"{total_earned:.2f}")
    embed.add_field(name="Biggest Win", value=f"{biggest_win:.2f}")
    embed.add_field(name="Worst Loss", value=f"{biggest_loss:.2f}")
    embed.set_footer(text="Galaxy Stats • May the odds be ever in your favor 🌌")
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      ADMIN (basic give/remove)
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
        msg = f"Gave **{val:.2f} gems** to {member.mention}"
    elif action == "remove":
        u["gems"] = max(0, u["gems"] - val)
        msg = f"Removed **{val:.2f} gems** from {member.mention}"
    else:
        return await ctx.send("❌ Use: `?admin give/remove @user amount`")

    save_data(data)
    embed = discord.Embed(
        title="🛠 Admin Action",
        description=msg,
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      MYSTERY BOX (?dropbox)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def dropbox(ctx, member: discord.Member, amount: str):
    ensure_user(member.id)
    u = data[str(member.id)]
    val = parse_amount(amount, None, allow_all=False)
    if val is None or val <= 0:
        return await ctx.send("❌ Invalid amount.")

    u["gems"] += val
    save_data(data)

    add_history(member.id, {
        "game": "dropbox",
        "bet": 0,
        "result": f"admin_drop",
        "earned": val,
        "timestamp": time.time()
    })

    embed = discord.Embed(
        title="🎁 Galaxy Mystery Box",
        description=f"{member.mention} received a mystery box containing **{val:.2f}** gems!",
        color=galaxy_color()
    )
    embed.set_footer(text="A gift from the galaxy admins ✨")
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      BLESS / CURSE
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def bless(ctx, member: discord.Member, streak: int):
    ensure_user(member.id)
    u = data[str(member.id)]
    if streak <= 0:
        return await ctx.send("❌ Streak must be positive.")
    u["bless_streak"] = u.get("bless_streak", 0) + streak
    save_data(data)

    embed = discord.Embed(
        title="✨ Galaxy Bless",
        description=f"{member.mention} has been **blessed** for **{streak}** wins.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def curse(ctx, member: discord.Member, streak: int):
    ensure_user(member.id)
    u = data[str(member.id)]
    if streak <= 0:
        return await ctx.send("❌ Streak must be positive.")
    u["curse_streak"] = u.get("curse_streak", 0) + streak
    save_data(data)

    embed = discord.Embed(
        title="💀 Galaxy Curse",
        description=f"{member.mention} has been **cursed** for **{streak}** losses.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      LOTTERY (manual, self-funded)
# --------------------------------------------------------------
class BuyTicketButton(Button):
    def __init__(self):
        super().__init__(label="🎟 Buy Ticket", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        state = get_lottery_state()
        if not state["active"]:
            return await interaction.response.send_message("❌ No active lottery.", ephemeral=True)

        ensure_user(interaction.user.id)
        u = data[str(interaction.user.id)]
        price = state["ticket_price"]
        if u["gems"] < price:
            return await interaction.response.send_message("❌ Not enough gems to buy a ticket.", ephemeral=True)

        u["gems"] -= price
        state["tickets"].append(interaction.user.id)
        set_lottery_state(state)
        save_data(data)

        embed = build_lottery_embed(state, interaction.client)
        try:
            await interaction.response.edit_message(embed=embed, view=build_lottery_view())
        except:
            # fallback
            await interaction.response.send_message("✅ Ticket bought!", ephemeral=True)

def build_lottery_embed(state, client: discord.Client):
    remaining = max(0, int(state["end_time"] - time.time()))
    minutes = remaining // 60
    seconds = remaining % 60
    total_tickets = len(state["tickets"])
    unique_players = len(set(state["tickets"]))
    prize = state["ticket_price"] * total_tickets

    embed = discord.Embed(
        title="🌌 Galaxy Lottery",
        description=(
            f"🎟 **Ticket price:** {state['ticket_price']}\n"
            f"💰 **Current prize:** {prize:.2f}\n"
            f"👥 **Tickets sold:** {total_tickets}\n"
            f"🧑 **Participants:** {unique_players}\n"
            f"⏳ **Time left:** {minutes}m {seconds}s"
        ),
        color=galaxy_color()
    )
    embed.set_footer(text="Buy tickets before the galaxy closes the portal ✨")
    return embed

def build_lottery_view():
    view = View(timeout=None)
    view.add_item(BuyTicketButton())
    return view

async def lottery_timer():
    await bot.wait_until_ready()
    state = get_lottery_state()
    if not state["active"]:
        return
    channel = bot.get_channel(state["channel_id"])
    if channel is None:
        return

    while True:
        await asyncio.sleep(5)
        state = get_lottery_state()
        if not state["active"]:
            return
        if time.time() >= state["end_time"]:
            break
        # optional: live updating could be added here

    # Lottery end
    state = get_lottery_state()
    state["active"] = False
    set_lottery_state(state)

    if not state["tickets"]:
        embed = discord.Embed(
            title="🌌 Galaxy Lottery Ended",
            description="No tickets were sold. The galaxy keeps its secrets.",
            color=galaxy_color()
        )
        return await channel.send(embed=embed)

    winner_id = random.choice(state["tickets"])
    ensure_user(winner_id)
    winner = data[str(winner_id)]
    prize = state["ticket_price"] * len(state["tickets"])
    winner["gems"] += prize
    save_data(data)

    add_history(winner_id, {
        "game": "lottery",
        "bet": state["ticket_price"],
        "result": "win",
        "earned": prize,
        "timestamp": time.time()
    })

    user_obj = await bot.fetch_user(winner_id)
    embed = discord.Embed(
        title="🎉 Galaxy Lottery Winner",
        description=(
            f"👑 Winner: {user_obj.mention}\n"
            f"💰 Prize: **{prize:.2f} gems**\n"
            f"🎟 Tickets sold: {len(state['tickets'])}"
        ),
        color=galaxy_color()
    )
    await channel.send(embed=embed)

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def lottery(ctx, subcmd: str = None, *args):
    if subcmd is None or subcmd.lower() == "info":
        state = get_lottery_state()
        if not state["active"]:
            return await ctx.send("❌ No active lottery.")
        embed = build_lottery_embed(state, bot)
        return await ctx.send(embed=embed)

    subcmd = subcmd.lower()
    if subcmd == "start":
        if len(args) < 2:
            return await ctx.send("Usage: `?lottery start <ticket_price> <duration>` (e.g. `?lottery start 1000 2h`)")

        price_text = args[0]
        duration_text = args[1]
        price = parse_amount(price_text, None, allow_all=False)
        if price is None or price <= 0:
            return await ctx.send("❌ Invalid ticket price.")
        dur = parse_duration(duration_text)
        if dur is None or dur <= 0:
            return await ctx.send("❌ Invalid duration. Use like `30m`, `2h`.")

        state = get_lottery_state()
        if state["active"]:
            return await ctx.send("❌ A lottery is already running. Use `?lottery cancel` first.")

        end_time = time.time() + dur
        state = {
            "active": True,
            "ticket_price": price,
            "end_time": end_time,
            "tickets": [],
            "message_id": None,
            "channel_id": ctx.channel.id,
        }
        set_lottery_state(state)

        embed = build_lottery_embed(state, bot)
        msg = await ctx.send(embed=embed, view=build_lottery_view())
        state["message_id"] = msg.id
        set_lottery_state(state)

        bot.loop.create_task(lottery_timer())
        return

    if subcmd == "cancel":
        state = get_lottery_state()
        if not state["active"]:
            return await ctx.send("❌ No active lottery to cancel.")
        state["active"] = False
        set_lottery_state(state)
        embed = discord.Embed(
            title="🛑 Galaxy Lottery Cancelled",
            description="The current lottery has been cancelled by an admin.",
            color=galaxy_color()
        )
        return await ctx.send(embed=embed)

    await ctx.send("❌ Unknown subcommand. Use `?lottery start`, `?lottery cancel`, or `?lottery` for info.")

# --------------------------------------------------------------
#                      HELP
# --------------------------------------------------------------

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="🌌 Galaxy Casino Help",
        description="Use `?command` to play.",
        color=galaxy_color()
    )

    embed.add_field(
        name="💰 Economy",
        value=(
            "`?balance` — Check your gems\n"
            "`?daily` — Daily reward\n"
            "`?work` — Earn 10m–15m\n"
            "`?gift @user amount` — Gift gems\n"
        ),
        inline=False
    )

    embed.add_field(
        name="🎲 Games",
        value=(
            "`?coinflip amount heads/tails`\n"
            "`?slots amount`\n"
            "`?mines bet mines`\n"
            "`?tower bet`\n"
            "`?blackjack bet`\n"
        ),
        inline=False
    )

    embed.add_field(
        name="🎟 Lottery",
        value=(
            "`?lottery` — Info (if active)\n"
            "`?lottery start price duration` (admin)\n"
            "`?lottery cancel` (admin)\n"
        ),
        inline=False
    )

    embed.add_field(
        name="📊 Info",
        value=(
            "`?history` — Last 10 games\n"
            "`?leaderboard` — Top players\n"
            "`?stats` — Your stats\n"
        ),
        inline=False
    )

    embed.add_field(
        name="🛠 Admin",
        value=(
            "`?admin give/remove @user amount`\n"
            "`?dropbox @user amount`\n"
            # bless/curse removed
        ),
        inline=False
    )

    embed.set_footer(text="Galaxy Casino • Good luck, gambler 😈💎")
    await ctx.send(embed=embed)

bot.run(TOKEN)
