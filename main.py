import discord
from discord.ext import commands
import json
import os
import random
from discord.ui import Button, View, Select
import time

TOKEN = os.getenv("TOKEN")
DATA_FILE = "casino_data.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="?", intents=intents, help_command=None)

# ---------------------- Data Management ---------------------- #
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({}, f)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

def ensure_user(user_id):
    if str(user_id) not in data:
        data[str(user_id)] = {
            "gems": 25,
            "last_daily": 0,
            "history": []
        }

def add_history(user_id, entry):
    ensure_user(user_id)
    hist = data[str(user_id)].get("history", [])
    hist.append(entry)
    if len(hist) > 10:
        hist = hist[-10:]
    data[str(user_id)]["history"] = hist
    save_data(data)

# ---------------------- Anti-Cheat / Cooldowns ---------------------- #

# per-user per-command cooldowns
last_usage = {}         # (user_id, cmd_name) -> timestamp
cooldowns = {
    "coinflip": 1.0,
    "slots": 1.0,
    "blackjack": 2.0,
    "mines": 3.0,
    "tower": 5.0,
}

# spam protection
spam_events = {}        # user_id -> [timestamps]
spam_lock_until = {}    # user_id -> timestamp

# one active interactive game at a time (mines, tower, blackjack)
active_game = {}        # user_id -> None or "mines"/"tower"/"blackjack"

async def check_cooldown_and_spam(ctx, cmd_name: str) -> bool:
    """Returns True if allowed, False if blocked."""
    user_id = ctx.author.id
    now = time.time()

    # spam lock
    locked_until = spam_lock_until.get(user_id, 0)
    if now < locked_until:
        remaining = int(locked_until - now)
        await ctx.send(f"⏳ You are temporarily rate-limited. Try again in **{remaining}s**.")
        return False

    # normal cooldown
    cd = cooldowns.get(cmd_name, 0)
    key = (user_id, cmd_name)
    last = last_usage.get(key, 0)
    if now - last < cd:
        remaining = cd - (now - last)
        await ctx.send(f"⏳ Slow down! Cooldown: **{remaining:.1f}s** for `{cmd_name}`.")
        return False
    last_usage[key] = now

    # spam tracking
    history = spam_events.get(user_id, [])
    history = [t for t in history if now - t < 30]  # keep last 30s
    history.append(now)
    spam_events[user_id] = history
    if len(history) > 15:
        # lock for 30 seconds
        spam_lock_until[user_id] = now + 30
        await ctx.send("🚫 Too many commands in a short time. You are locked for **30s**.")
        return False

    return True

def set_active_game(user_id: int, game_name: str | None):
    if game_name is None:
        active_game.pop(user_id, None)
    else:
        active_game[user_id] = game_name

def has_active_game(user_id: int) -> str | None:
    return active_game.get(user_id)

# ---------------------- Helper: Cards for Blackjack ---------------------- #

CARD_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5,
    "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11
}
CARD_SUITS = ["♠", "♥", "♦", "♣"]
CARD_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

def draw_deck():
    return [f"{rank}{suit}" for rank in CARD_RANKS for suit in CARD_SUITS]

def hand_value(cards):
    total = 0
    aces = 0
    for c in cards:
        rank = c[:-1]
        total += CARD_VALUES[rank]
        if rank == "A":
            aces += 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

# --------------------------------------------------------------
#                      BALANCE
# --------------------------------------------------------------
@bot.command()
async def balance(ctx):
    ensure_user(ctx.author.id)
    gems = round(data[str(ctx.author.id)]["gems"], 2)
    embed = discord.Embed(
        title="💎 Your Balance",
        description=f"{ctx.author.mention}, you have **{gems} gems**.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      DAILY
# --------------------------------------------------------------
@bot.command()
async def daily(ctx):
    ensure_user(ctx.author.id)
    user = data[str(ctx.author.id)]
    now = time.time()
    cooldown = 24 * 3600
    last = user.get("last_daily", 0)

    if now - last < cooldown:
        remaining = cooldown - (now - last)
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        embed = discord.Embed(
            title="❌ Already Claimed",
            description=f"Come back in **{hours}h {minutes}m**.",
            color=discord.Color.red()
        )
        return await ctx.send(embed=embed)

    user["gems"] += 25
    user["last_daily"] = now
    save_data(data)

    add_history(ctx.author.id, {
        "game": "daily",
        "bet": 0,
        "result": "claim",
        "earned": 25,
        "timestamp": now
    })

    embed = discord.Embed(
        title="🎁 Daily Reward",
        description=f"{ctx.author.mention} claimed **25 gems!**",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      GIFT (NO TAX HERE)
# --------------------------------------------------------------
@bot.command()
async def gift(ctx, member: discord.Member, amount: float):
    ensure_user(ctx.author.id)
    ensure_user(member.id)

    if amount <= 0:
        return await ctx.send("❌ Invalid amount.")
    if data[str(ctx.author.id)]["gems"] < amount:
        return await ctx.send("❌ Not enough gems.")

    data[str(ctx.author.id)]["gems"] -= amount
    data[str(member.id)]["gems"] += amount
    save_data(data)

    add_history(ctx.author.id, {
        "game": "gift",
        "bet": amount,
        "result": f"gift_to_{member.id}",
        "earned": -amount,
        "timestamp": time.time()
    })
    add_history(member.id, {
        "game": "gift_received",
        "bet": amount,
        "result": f"gift_from_{ctx.author.id}",
        "earned": amount,
        "timestamp": time.time()
    })

    embed = discord.Embed(
        title="🎁 Gift Sent",
        description=f"{ctx.author.mention} sent **{amount} gems** to {member.mention}.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      TAX COMMAND (5% GLOBAL)
# --------------------------------------------------------------
@bot.command()
async def tax(ctx):
    """Removes 5% from everyone's balance (Manage Server only)."""
    if not ctx.author.guild_permissions.manage_guild:
        return await ctx.send("❌ You need **Manage Server** permission to use this.")

    total_taxed = 0.0
    for uid, info in data.items():
        gems = info.get("gems", 0)
        if gems <= 0:
            continue
        tax_amount = gems * 0.05
        info["gems"] = round(gems - tax_amount, 2)
        total_taxed += tax_amount
        # log per user
        add_history(int(uid), {
            "game": "tax",
            "bet": 0,
            "result": "5_percent_global_tax",
            "earned": -round(tax_amount, 2),
            "timestamp": time.time()
        })
    save_data(data)

    embed = discord.Embed(
        title="💸 Global Tax Applied",
        description=f"5% tax applied to all balances.\nTotal removed: **{round(total_taxed, 2)} gems**.",
        color=discord.Color.dark_gold()
    )
    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      COINFLIP
# --------------------------------------------------------------
@bot.command()
async def coinflip(ctx, bet: float, choice: str):
    if not await check_cooldown_and_spam(ctx, "coinflip"):
        return

    ensure_user(ctx.author.id)
    user = data[str(ctx.author.id)]

    choice = choice.lower()
    if choice not in ["heads", "tails"]:
        return await ctx.send("❌ Choose `heads` or `tails`.")
    if bet <= 0 or bet > user["gems"]:
        return await ctx.send("❌ Invalid bet.")

    user["gems"] -= bet
    save_data(data)

    result = random.choice(["heads", "tails"])

    if result == choice:
        win_amount = bet * 2
        profit = bet
        user["gems"] += win_amount
        save_data(data)

        embed = discord.Embed(
            title="🪙 Coinflip — You Won!",
            description=(
                f"🎯 Your choice: **{choice}**\n"
                f"🌀 Result: **{result}**\n\n"
                f"💰 Profit: **+{profit} gems**"
            ),
            color=discord.Color.green()
        )

        add_history(ctx.author.id, {
            "game": "coinflip",
            "bet": bet,
            "result": "win",
            "earned": profit,
            "timestamp": time.time()
        })

    else:
        embed = discord.Embed(
            title="🪙 Coinflip — You Lost",
            description=(
                f"🎯 Your choice: **{choice}**\n"
                f"🌀 Result: **{result}**\n\n"
                f"💔 Lost: **-{bet} gems**"
            ),
            color=discord.Color.red()
        )
        add_history(ctx.author.id, {
            "game": "coinflip",
            "bet": bet,
            "result": "lose",
            "earned": -bet,
            "timestamp": time.time()
        })

    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      SLOTS (3x3, STYLE A)
# --------------------------------------------------------------
@bot.command()
async def slots(ctx, bet: float):
    if not await check_cooldown_and_spam(ctx, "slots"):
        return

    ensure_user(ctx.author.id)
    user = data[str(ctx.author.id)]

    if bet <= 0 or bet > user["gems"]:
        return await ctx.send("❌ Invalid bet.")

    user["gems"] -= bet
    save_data(data)

    symbols = ["🍒", "🍋", "🔔", "⭐", "💎"]
    weights = [35, 30, 20, 10, 5]  # 💎 rare

    def spin_row():
        return random.choices(symbols, weights=weights, k=3)

    row1 = spin_row()
    row2 = spin_row()
    row3 = spin_row()

    middle = row2
    s1, s2, s3 = middle

    multiplier = 0.0
    result_text = ""

    if s1 == s2 == s3:
        if s1 == "💎":
            multiplier = 20.0
        elif s1 == "⭐":
            multiplier = 10.0
        elif s1 == "🔔":
            multiplier = 5.0
        elif s1 == "🍒":
            multiplier = 4.0
        else:
            multiplier = 3.0
        result_text = f"JACKPOT! 3x {s1}"
    elif s1 == s2 or s2 == s3 or s1 == s3:
        multiplier = 1.5
        result_text = "Two of a kind! Small win."
    else:
        multiplier = 0.0
        result_text = "No match on middle row."

    reward = bet * multiplier
    profit = reward - bet  # can be negative

    if reward > 0:
        user["gems"] += reward
        save_data(data)

    grid = (
        f"{row1[0]} {row1[1]} {row1[2]}\n"
        f"➡ {row2[0]} {row2[1]} {row2[2]} ⬅ (pays)\n"
        f"{row3[0]} {row3[1]} {row3[2]}"
    )

    color = discord.Color.green() if reward > 0 else discord.Color.red()

    embed = discord.Embed(
        title="🎰 Slots",
        description=(
            f"Bet: **{bet}**\n"
            f"Multiplier: **{multiplier:.2f}x**\n"
            f"Result: **{result_text}**\n"
            f"Net: **{profit:.2f} gems**"
        ),
        color=color
    )
    embed.add_field(name="Reels", value=f"```{grid}```", inline=False)

    add_history(ctx.author.id, {
        "game": "slots",
        "bet": bet,
        "result": "win" if reward > 0 else "lose",
        "earned": profit,
        "timestamp": time.time()
    })

    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      MINES
# --------------------------------------------------------------
@bot.command()
async def mines(ctx, bet: float, mines: int = 3):
    if not await check_cooldown_and_spam(ctx, "mines"):
        return

    ensure_user(ctx.author.id)
    user = data[str(ctx.author.id)]

    if has_active_game(ctx.author.id):
        return await ctx.send("❌ You already have an active game. Finish it first.")

    if bet <= 0 or bet > user["gems"]:
        return await ctx.send("❌ Invalid bet!")
    if not 1 <= mines <= 15:
        return await ctx.send("❌ Mines must be between **1 and 15**.")

    user["gems"] -= bet
    save_data(data)

    set_active_game(ctx.author.id, "mines")

    owner = ctx.author.id
    game_over = False
    correct_clicks = 0

    TOTAL = 24
    ROW_SLOTS = 5

    revealed = [None] * TOTAL
    bomb_positions = random.sample(range(TOTAL), mines)
    exploded_index = None

    def calc_multiplier():
        if correct_clicks == 0:
            return 1.0
        base = 1.05 + min(mines, 15) * 0.02
        return base ** correct_clicks

    def calc_reward():
        return bet * calc_multiplier()

    def embed_update():
        current = 0 if exploded_index is not None else calc_reward()
        e = discord.Embed(
            title=f"💣 Mines | {ctx.author.name}",
            description=(
                f"💵 **Bet:** {bet}\n"
                f"💣 **Mines:** {mines}\n"
                f"🔥 **Multiplier:** {calc_multiplier():.2f}x\n"
                f"💰 **Current Cashout:** {current:.2f} gems"
            ),
            color=discord.Color.orange()
        )
        return e

    view = View(timeout=180)

    # ---------------------------- TILE ---------------------------- #
    class Tile(Button):
        def __init__(self, index: int):
            row = index // ROW_SLOTS
            super().__init__(label=str(index + 1), style=discord.ButtonStyle.secondary, row=row)
            self.index = index

        async def callback(self, interaction: discord.Interaction):
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

                for btn in view.children:
                    if isinstance(btn, Tile):
                        btn.disabled = True
                        if btn.index in bomb_positions:
                            btn.label = "💣"
                            btn.style = discord.ButtonStyle.danger

                add_history(ctx.author.id, {
                    "game": "mines",
                    "bet": bet,
                    "result": "lose",
                    "earned": -bet,
                    "timestamp": time.time()
                })

                set_active_game(owner, None)

                try:
                    await interaction.response.edit_message(embed=embed_update(), view=view)
                except discord.NotFound:
                    pass

                return await ctx.send(f"💥 BOOM! You hit a mine and lost **{bet} gems**.")

            revealed[self.index] = True
            self.label = "✅"
            self.style = discord.ButtonStyle.success
            correct_clicks += 1

            try:
                await interaction.response.edit_message(embed=embed_update(), view=view)
            except discord.NotFound:
                pass

    for i in range(TOTAL):
        view.add_item(Tile(i))

    class Cashout(Button):
        def __init__(self):
            super().__init__(label="💰 Cashout", style=discord.ButtonStyle.primary, row=4)

        async def callback(self, interaction: discord.Interaction):
            nonlocal game_over

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended!", ephemeral=True)

            game_over = True
            reward = calc_reward()
            user["gems"] += reward
            save_data(data)

            for btn in view.children:
                if isinstance(btn, Tile):
                    btn.disabled = True
                    if btn.index in bomb_positions:
                        btn.label = "💣"
                        btn.style = discord.ButtonStyle.danger

            net = reward - bet
            add_history(ctx.author.id, {
                "game": "mines",
                "bet": bet,
                "result": "cashout",
                "earned": net,
                "timestamp": time.time()
            })

            set_active_game(owner, None)

            try:
                await interaction.response.edit_message(embed=embed_update(), view=view)
            except discord.NotFound:
                pass

            await ctx.send(f"💰 You cashed out **{reward:.2f} gems** (profit: {net:.2f}).")

    view.add_item(Cashout())
    await ctx.send(embed=embed_update(), view=view)

# --------------------------------------------------------------
#                      TOWER (PREMIUM C)
# --------------------------------------------------------------
@bot.command()
async def tower(ctx, bet: float):
    if not await check_cooldown_and_spam(ctx, "tower"):
        return

    ensure_user(ctx.author.id)
    user = data[str(ctx.author.id)]

    if has_active_game(ctx.author.id):
        return await ctx.send("❌ You already have an active game. Finish it first.")

    if bet <= 0 or bet > user["gems"]:
        return await ctx.send("❌ Invalid bet.")

    user["gems"] -= bet
    save_data(data)

    set_active_game(ctx.author.id, "tower")

    TOTAL_ROWS = 10
    current_row = 0
    correct_count = 0
    game_over = False
    owner = ctx.author.id

    SAFE = "🟩"
    HIDDEN = "⬛"
    BOMB = "💣"
    EXPLODE = "💥"

    bomb_positions = [random.randrange(3) for _ in range(TOTAL_ROWS)]
    picked_positions = [None] * TOTAL_ROWS
    exploded_cell = None
    earned_on_end = 0.0

    def calc_multiplier():
        if correct_count == 0:
            return 1.0
        return 1.25 ** correct_count

    def calc_reward():
        return bet * calc_multiplier()

    def build_tower_visual(reveal: bool):
        lines = []
        for r in reversed(range(TOTAL_ROWS)):
            row_icons = []
            for c in range(3):
                picked = picked_positions[r]
                bomb_c = bomb_positions[r]
                if picked is None:
                    if reveal:
                        if (r, c) == exploded_cell:
                            row_icons.append(EXPLODE)
                        elif c == bomb_c:
                            row_icons.append(BOMB)
                        else:
                            row_icons.append(SAFE)
                    else:
                        row_icons.append(HIDDEN)
                else:
                    if (r, c) == exploded_cell:
                        row_icons.append(EXPLODE)
                    elif c == picked:
                        row_icons.append(SAFE)
                    elif reveal and c == bomb_c:
                        row_icons.append(BOMB)
                    else:
                        row_icons.append(HIDDEN if not reveal else SAFE)
            lines.append(" ".join(row_icons))
        return "\n".join(lines)

    def embed_update(reveal: bool = False):
        nonlocal earned_on_end
        if reveal:
            net_profit = earned_on_end
        else:
            net_profit = calc_reward() - bet if correct_count > 0 else 0.0

        e = discord.Embed(
            title=f"🏰 Tower | {ctx.author.name}",
            color=discord.Color.purple()
        )
        e.add_field(name="Bet", value=f"{bet}", inline=True)
        e.add_field(name="Net Profit", value=f"{net_profit:.2f}", inline=True)
        e.add_field(name="Row", value=f"{current_row}/{TOTAL_ROWS}", inline=True)
        e.add_field(name="Multiplier", value=f"{calc_multiplier():.2f}x", inline=True)
        e.add_field(name="Tower", value=build_tower_visual(reveal), inline=False)
        e.set_footer(text="Pick a tile each row. Cashout anytime before you explode.")
        return e

    view = View(timeout=180)

    class Choice(Button):
        def __init__(self, pos: int):
            super().__init__(label=["⬅ Left", "⬆ Middle", "➡ Right"][pos],
                             style=discord.ButtonStyle.secondary)
            self.pos = pos

        async def callback(self, interaction: discord.Interaction):
            nonlocal current_row, correct_count, game_over, exploded_cell, earned_on_end

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game ended!", ephemeral=True)

            bomb_c = bomb_positions[current_row]

            if self.pos == bomb_c:
                picked_positions[current_row] = self.pos
                exploded_cell = (current_row, self.pos)
                game_over = True
                earned_on_end = 0.0

                for b in view.children:
                    b.disabled = True

                add_history(ctx.author.id, {
                    "game": "tower",
                    "bet": bet,
                    "result": "lose",
                    "earned": -bet,
                    "timestamp": time.time()
                })
                set_active_game(owner, None)
                await interaction.response.edit_message(embed=embed_update(True), view=view)
                return await ctx.send(f"💥 BOOM! You lost **{bet} gems** in Tower.")

            picked_positions[current_row] = self.pos
            correct_count += 1
            current_row += 1

            if current_row >= TOTAL_ROWS:
                game_over = True
                reward = calc_reward()
                user["gems"] += reward
                save_data(data)
                net_profit = reward - bet
                earned_on_end = net_profit

                for b in view.children:
                    b.disabled = True

                add_history(ctx.author.id, {
                    "game": "tower",
                    "bet": bet,
                    "result": "win",
                    "earned": net_profit,
                    "timestamp": time.time()
                })
                set_active_game(owner, None)
                await interaction.response.edit_message(embed=embed_update(True), view=view)
                return await ctx.send(f"🏆 You cleared the whole tower! Profit: **{net_profit:.2f} gems**.")

            await interaction.response.edit_message(embed=embed_update(False), view=view)

    class Cashout(Button):
        def __init__(self):
            super().__init__(label="💰 Cashout", style=discord.ButtonStyle.primary)

        async def callback(self, interaction: discord.Interaction):
            nonlocal game_over, earned_on_end

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game ended!", ephemeral=True)

            game_over = True
            reward = calc_reward()
            user["gems"] += reward
            save_data(data)

            net = reward - bet
            earned_on_end = net

            for b in view.children:
                b.disabled = True

            add_history(ctx.author.id, {
                "game": "tower",
                "bet": bet,
                "result": "cashout",
                "earned": net,
                "timestamp": time.time()
            })
            set_active_game(owner, None)
            await interaction.response.edit_message(embed=embed_update(True), view=view)
            await ctx.send(f"💰 You cashed out Tower with profit **{net:.2f} gems**.")

    view.add_item(Choice(0))
    view.add_item(Choice(1))
    view.add_item(Choice(2))
    view.add_item(Cashout())
    await ctx.send(embed=embed_update(False), view=view)

# --------------------------------------------------------------
#                      BLACKJACK (Simple A)
# --------------------------------------------------------------
blackjack_sessions = {}  # user_id -> state dict

@bot.command()
async def blackjack(ctx, bet: float):
    if not await check_cooldown_and_spam(ctx, "blackjack"):
        return

    ensure_user(ctx.author.id)
    user = data[str(ctx.author.id)]

    if has_active_game(ctx.author.id):
        return await ctx.send("❌ You already have an active game. Finish it first.")

    if bet <= 0 or bet > user["gems"]:
        return await ctx.send("❌ Invalid bet.")

    user["gems"] -= bet
    save_data(data)

    set_active_game(ctx.author.id, "blackjack")

    deck = draw_deck()
    random.shuffle(deck)

    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    session = {
        "bet": bet,
        "deck": deck,
        "player": player_hand,
        "dealer": dealer_hand,
        "finished": False
    }
    blackjack_sessions[ctx.author.id] = session

    def make_embed(final=False):
        p_val = hand_value(player_hand)
        d_show = dealer_hand[0] if not final else " ".join(dealer_hand)
        d_val = hand_value(dealer_hand) if final else "?"
        e = discord.Embed(
            title=f"🃏 Blackjack | {ctx.author.name}",
            color=discord.Color.dark_green()
        )
        e.add_field(name="Your Hand", value=f"{' '.join(player_hand)}\nValue: **{p_val}**", inline=False)
        e.add_field(
            name="Dealer Hand",
            value=(f"{dealer_hand[0]} ❓" if not final else f"{' '.join(dealer_hand)}\nValue: **{d_val}**"),
            inline=False
        )
        e.add_field(name="Bet", value=str(bet), inline=True)
        return e

    view = View(timeout=120)

    class Hit(Button):
        def __init__(self):
            super().__init__(label="Hit", style=discord.ButtonStyle.success)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if session["finished"]:
                return await interaction.response.send_message("❌ Game already finished!", ephemeral=True)

            session["player"].append(session["deck"].pop())
            p_val = hand_value(session["player"])

            if p_val > 21:
                session["finished"] = True
                for b in view.children:
                    b.disabled = True

                add_history(ctx.author.id, {
                    "game": "blackjack",
                    "bet": bet,
                    "result": "bust",
                    "earned": -bet,
                    "timestamp": time.time()
                })
                set_active_game(ctx.author.id, None)
                await interaction.response.edit_message(embed=make_embed(final=True), view=view)
                return await ctx.send(f"💥 Bust! You lost **{bet} gems**.")
            else:
                await interaction.response.edit_message(embed=make_embed(final=False), view=view)

    class Stand(Button):
        def __init__(self):
            super().__init__(label="Stand", style=discord.ButtonStyle.primary)

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if session["finished"]:
                return await interaction.response.send_message("❌ Game already finished!", ephemeral=True)

            session["finished"] = True
            deck = session["deck"]
            dealer = session["dealer"]

            while hand_value(dealer) < 17:
                dealer.append(deck.pop())

            p_val = hand_value(session["player"])
            d_val = hand_value(dealer)

            result = ""
            profit = 0.0
            if d_val > 21 or p_val > d_val:
                reward = bet * 2
                profit = bet
                user["gems"] += reward
                result = "win"
            elif p_val == d_val:
                user["gems"] += bet
                profit = 0.0
                result = "push"
            else:
                profit = -bet
                result = "lose"

            save_data(data)

            for b in view.children:
                b.disabled = True

            add_history(ctx.author.id, {
                "game": "blackjack",
                "bet": bet,
                "result": result,
                "earned": profit,
                "timestamp": time.time()
            })
            set_active_game(ctx.author.id, None)

            await interaction.response.edit_message(embed=make_embed(final=True), view=view)
            if result == "win":
                await ctx.send(f"🏆 You won **{profit} gems** in Blackjack!")
            elif result == "push":
                await ctx.send("🤝 Push. You got your bet back.")
            else:
                await ctx.send(f"💔 You lost **{bet} gems** in Blackjack.")

    view.add_item(Hit())
    view.add_item(Stand())
    await ctx.send(embed=make_embed(final=False), view=view)

# --------------------------------------------------------------
#                      LEADERBOARD
# --------------------------------------------------------------
@bot.command()
async def leaderboard(ctx):
    lb = sorted(
        [(int(uid), info.get("gems", 0)) for uid, info in data.items()],
        key=lambda x: x[1],
        reverse=True
    )

    embed = discord.Embed(title="🏆 Gems Leaderboard", color=discord.Color.gold())

    if not lb:
        embed.add_field(name="No players found", value="Start playing now!")
        return await ctx.send(embed=embed)

    for i, (user_id, gems) in enumerate(lb[:10], start=1):
        user_obj = await bot.fetch_user(user_id)
        embed.add_field(
            name=f"#{i} — {user_obj.name}",
            value=f"💎 {round(gems, 2)} gems",
            inline=False
        )

    embed.set_footer(text="Top 10 richest players 💰")
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
        color=discord.Color.blue()
    )

    for entry in hist:
        ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry["timestamp"]))
        embed.add_field(
            name=f"{entry['game']} at {ts}",
            value=f"Bet: {entry['bet']} | Result: {entry['result']} | Net: {entry['earned']}",
            inline=False
        )

    await ctx.send(embed=embed)

# --------------------------------------------------------------
#                      ADMIN PANEL (CUSTOM AMOUNTS)
# --------------------------------------------------------------
@bot.command()
async def admin(ctx, member: discord.Member):
    """Opens an admin panel for a user (Manage Server only)."""
    if not ctx.author.guild_permissions.manage_guild:
        return await ctx.send("❌ You need **Manage Server** permission to use this.")

    ensure_user(member.id)

    # -------------------- Modal for Custom Amount --------------------
    class AmountModal(discord.ui.Modal, title="Enter Custom Amount"):
        amount = discord.ui.TextInput(
            label="Amount",
            placeholder="Enter any number (e.g., 5000)",
            required=True
        )

        def __init__(self):
            super().__init__()
            self.value = None

        async def on_submit(self, interaction: discord.Interaction):
            try:
                self.value = float(self.amount.value)
            except:
                self.value = None
            await interaction.response.defer()

    # ------------------------- Admin View -------------------------
    class AdminView(View):
        def __init__(self, target: discord.Member):
            super().__init__(timeout=180)
            self.target = target

        async def interaction_check(self, interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ Not your admin panel.", ephemeral=True)
                return False
            return True

        async def update_message(self, interaction, message: str):
            await interaction.message.edit(content=message, view=self)

    view = AdminView(member)

    # ---------------------- BUTTONS ----------------------

    class Give(Button):
        def __init__(self):
            super().__init__(label="➕ Custom Give", style=discord.ButtonStyle.success)

        async def callback(self, interaction: discord.Interaction):
            modal = AmountModal()
            await interaction.response.send_modal(modal)
            await modal.wait()

            if modal.value is None:
                return await ctx.send("❌ Invalid number.")

            amount = modal.value
            ensure_user(member.id)
            data[str(member.id)]["gems"] += amount
            save_data(data)

            add_history(member.id, {
                "game": "admin_give",
                "bet": 0,
                "result": f"give_by_{ctx.author.id}",
                "earned": amount,
                "timestamp": time.time()
            })

            await view.update_message(interaction, f"✅ Gave **{amount}** gems to {member.mention}")

    class Remove(Button):
        def __init__(self):
            super().__init__(label="➖ Custom Remove", style=discord.ButtonStyle.danger)

        async def callback(self, interaction: discord.Interaction):
            modal = AmountModal()
            await interaction.response.send_modal(modal)
            await modal.wait()

            if modal.value is None:
                return await ctx.send("❌ Invalid number.")

            amount = modal.value
            ensure_user(member.id)
            data[str(member.id)]["gems"] = max(0, data[str(member.id)]["gems"] - amount)
            save_data(data)

            add_history(member.id, {
                "game": "admin_remove",
                "bet": 0,
                "result": f"remove_by_{ctx.author.id}",
                "earned": -amount,
                "timestamp": time.time()
            })

            await view.update_message(interaction, f"🧹 Removed **{amount}** gems from {member.mention}")

    class Reset(Button):
        def __init__(self):
            super().__init__(label="♻ Reset User", style=discord.ButtonStyle.secondary)

        async def callback(self, interaction: discord.Interaction):
            ensure_user(member.id)
            data[str(member.id)]["gems"] = 25
            data[str(member.id)]["history"] = []
            save_data(data)

            await view.update_message(interaction, f"♻ Reset {member.mention} to **25 gems** and cleared history.")

    # Add buttons
    view.add_item(Give())
    view.add_item(Remove())
    view.add_item(Reset())

    # ---------------------- SEND PANEL ----------------------
    embed = discord.Embed(
        title="🛠 Admin Panel",
        description=(
            f"Manage gems for {member.mention}\n"
            "Use custom amounts via input box.\n\n"
            "**Options:**\n"
            "- ➕ Give Gems\n"
            "- ➖ Remove Gems\n"
            "- ♻ Reset User\n"
        ),
        color=discord.Color.orange()
    )

    await ctx.send(embed=embed, view=view)


# --------------------------------------------------------------
#                      HELP MENU
# --------------------------------------------------------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="💎 Casino Help Menu",
        description="Use `?command` to play.",
        color=discord.Color.green()
    )

    embed.add_field(
        name="💰 Economy",
        value=(
            "• `?balance` — check your gems\n"
            "• `?daily` — claim 25 daily gems\n"
            "• `?gift @user amount` — send gems\n"
            "• `?tax` — apply global 5% tax (Manage Server)\n"
        ),
        inline=False
    )

    embed.add_field(
        name="🎲 Games",
        value=(
            "• `?coinflip amount heads/tails`\n"
            "• `?slots amount` — 3x3 slot machine\n"
            "• `?mines bet mines` (1–15)\n"
            "• `?tower bet` — 10-row tower\n"
            "• `?blackjack bet` — classic 21\n"
        ),
        inline=False
    )

    embed.add_field(
        name="📜 Info",
        value=(
            "• `?history` — last 10 actions\n"
            "• `?leaderboard` — top players\n"
        ),
        inline=False
    )

    embed.add_field(
        name="🛠 Admin",
        value="• `?admin @user` — open admin panel (Manage Server)",
        inline=False
    )

    embed.set_footer(text="Good luck, gambler 😈💎")
    await ctx.send(embed=embed)

bot.run(TOKEN)