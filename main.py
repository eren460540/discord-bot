import discord
from discord.ext import commands, tasks
import json
import os
import random
from discord.ui import Button, View
import time
import io
from datetime import datetime

TOKEN = os.getenv("TOKEN")
DATA_FILE = "casino_data.json"

# Channel used for JSON backups
BACKUP_CHANNEL_ID = 1431610647921295451

# Channel used for logs
LOG_CHANNEL_ID = 1440730206187950122

# ---------------------- INTENTS ---------------------- #
intents = discord.Intents.all() # <--- this enables EVERYTHING
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------------- CONSTANTS ---------------------- #
MAX_BET = 200_000_000 # 200m
LOTTERY_BONUS = 0.10 # 10% extra on the pot for lottery winner

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
Sends a nice galaxy embed log to the log channel.
"""
channel = bot.get_channel(LOG_CHANNEL_ID)
if channel is None:
try:
channel = await bot.fetch_channel(LOG_CHANNEL_ID)
except Exception:
return

if channel is None:
return

title_prefix = EVENT_TITLES.get(event_type, "📜 Event")
embed = discord.Embed(
title=title_prefix,
description=summary,
color=galaxy_color()
)

if user is not None:
try:
avatar = user.display_avatar.url
except Exception:
avatar = discord.Embed.Empty
embed.set_author(name=f"{user} ({user.id})", icon_url=avatar)

if fields:
for name, value in fields.items():
if value is None:
continue
# Discord field value must be string
embed.add_field(name=name, value=str(value), inline=False)

ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
embed.set_footer(text=f"Log • {ts} UTC")

try:
await channel.send(embed=embed)
except Exception:
pass


# ---------------------- BACKUP SYSTEM ---------------------- #

async def backup_to_channel(reason: str = "auto"):
"""Sends current data as JSON file to the backup channel."""
channel = bot.get_channel(BACKUP_CHANNEL_ID)
if channel is None:
try:
channel = await bot.fetch_channel(BACKUP_CHANNEL_ID)
except Exception:
return # can't backup, invalid channel or no access

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
# BALANCE / BAL
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
await ctx.send(embed=embed)
return

reward = 25_000_000 # 25m
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
# GUESS THE COLOR (RUNS UNTIL SOMEONE GUESSES CORRECTLY)
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
msg = await bot.wait_for("message", timeout=None) # no timeout
except Exception:
continue # shouldn't happen but keeps loop alive

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
before = data[str(winner.id)]["gems"]
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

await send_log(
"guessthecolor_win",
winner,
f"Guessed color '{secret}' correctly.",
{
"Prize": fmt(parsed_prize),
"Secret Color": secret,
"Gems Before": fmt(before),
"Gems After": fmt(data[str(winner.id)]["gems"])
}
)
break


# --------------------------------------------------------------
# WORK (10m–15m)
# --------------------------------------------------------------
@bot.command()
async def work(ctx):
ensure_user(ctx.author.id)
u = data[str(ctx.author.id)]
now = time.time()
cooldown = 3600 # 1 hour
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

await send_log(
"work",
ctx.author,
f"Completed work for {fmt(reward)} gems.",
{
"Reward": fmt(reward),
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
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

before_sender = sender["gems"]
before_receiver = receiver["gems"]

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
"Sender Gems Before": fmt(before_sender),
"Sender Gems After": fmt(sender['gems']),
"Receiver Gems Before": fmt(before_receiver),
"Receiver Gems After": fmt(receiver['gems'])
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
"Gems After": fmt(u['gems'])
}
)


# --------------------------------------------------------------
# SLOTS (3x4, rig-aware, 2x max)
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
"Gems After": fmt(u['gems'])
}
)


# --------------------------------------------------------------
# MINES (rig-aware)
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

before = u.get("gems", 0)

u["gems"] -= amount
save_data(data)

rig = consume_rig(u) # 'bless', 'curse', or None

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
clicks_log = []

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
clicks_log.append(f"Tile {self.index + 1}: BOMB (curse first click)")

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

await send_log(
"mines",
ctx.author,
"Mines game LOST (curse on first click).",
{
"Bet": fmt(amount),
"Net": fmt(-amount),
"Rig": rig or "none",
"Mines": mines,
"Clicks": "\n".join(clicks_log)[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)
return

first_click = False

# BLESS: every tile treated as safe
if rig == "bless":
revealed[self.index] = True
self.label = SAFE
self.style = discord.ButtonStyle.success
correct_clicks += 1
clicks_log.append(f"Tile {self.index + 1}: SAFE (bless)")
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
clicks_log.append(f"Tile {self.index + 1}: BOMB")

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

await send_log(
"mines",
ctx.author,
"Mines game LOST (hit a mine).",
{
"Bet": fmt(amount),
"Net": fmt(-amount),
"Rig": rig or "none",
"Mines": mines,
"Clicks": "\n".join(clicks_log)[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)
return

revealed[self.index] = True
self.label = SAFE
self.style = discord.ButtonStyle.success
correct_clicks += 1
clicks_log.append(f"Tile {self.index + 1}: SAFE")

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
exploded_index = 0 # mark as exploded so reward shows 0
clicks_log.append("Cashout pressed under curse (full loss).")

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

await send_log(
"mines",
ctx.author,
"Mines game LOST (cashout under curse).",
{
"Bet": fmt(amount),
"Net": fmt(-amount),
"Rig": rig or "none",
"Mines": mines,
"Clicks": "\n".join(clicks_log)[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)
return

# BLESS: ensure at least some profit even if they cashout instantly
if rig == "bless" and correct_clicks == 0:
correct_clicks = 1
clicks_log.append("Cashout on first safe (bless enforced).")

game_over = True
reward = calc_reward()
profit = reward - amount
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
"earned": profit,
"timestamp": time.time()
})

try:
await interaction.response.edit_message(embed=embed_update(), view=view)
except:
pass

await ctx.send(f"💰 You cashed out **{fmt(reward - amount)}** gems!")

clicks_log.append(f"Final Cashout Reward: {fmt(reward)}")

await send_log(
"mines",
ctx.author,
"Mines game CASHOUT.",
{
"Bet": fmt(amount),
"Reward": fmt(reward),
"Net": fmt(profit),
"Rig": rig or "none",
"Mines": mines,
"Clicks": "\n".join(clicks_log)[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)

view.add_item(Cashout())
await ctx.send(embed=embed_update(), view=view)


# --------------------------------------------------------------
# TOWER (rig-aware)
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

before = u.get("gems", 0)

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
choices_log = []

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
row_number = current_row + 1
choice_name = ["Left", "Middle", "Right"][self.pos]

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

choices_log.append(f"Row {row_number}: {choice_name} -> BOMB")

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
await ctx.send(f"💥 BOOM! You lost **{fmt(amount)}** gems!")

await send_log(
"tower",
ctx.author,
"Tower game LOST (hit bomb).",
{
"Bet": fmt(amount),
"Net": fmt(-amount),
"Rig": rig or "none",
"Rows Cleared": correct_count,
"Choices": "\n".join(choices_log)[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)
return

grid[current_row][self.pos] = True
correct_count += 1
choices_log.append(f"Row {row_number}: {choice_name} -> SAFE")
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
await ctx.send(f"🏆 Cleared all rows! **+{fmt(reward - amount)}** gems!")

choices_log.append(f"Final Reward: {fmt(reward)}")

await send_log(
"tower",
ctx.author,
"Tower game WIN (all rows cleared).",
{
"Bet": fmt(amount),
"Reward": fmt(reward),
"Net": fmt(reward - amount),
"Rig": rig or "none",
"Rows Cleared": correct_count,
"Choices": "\n".join(choices_log)[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)
return

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

choices_log.append("Cashout pressed under curse (full loss).")

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

await send_log(
"tower",
ctx.author,
"Tower game LOST (cashout under curse).",
{
"Bet": fmt(amount),
"Net": fmt(-amount),
"Rig": rig or "none",
"Rows Cleared": correct_count,
"Choices": "\n".join(choices_log)[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)
return

# BLESS: guarantee at least one safe row worth of profit
if rig == "bless" and correct_count == 0:
correct_count = 1
choices_log.append("Cashout on first safe row (bless enforced).")

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

choices_log.append(f"Final Reward: {fmt(reward)}")

await send_log(
"tower",
ctx.author,
"Tower game CASHOUT.",
{
"Bet": fmt(amount),
"Reward": fmt(reward),
"Net": fmt(reward - amount),
"Rig": rig or "none",
"Rows Cleared": correct_count,
"Choices": "\n".join(choices_log)[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)

view.add_item(Choice(0))
view.add_item(Choice(1))
view.add_item(Choice(2))
view.add_item(Cashout())

await ctx.send(embed=embed_update(False), view=view)


# --------------------------------------------------------------
# BLACKJACK (rig-aware; medium)
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

before = u.get("gems", 0)

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

await send_log(
"blackjack",
ctx.author,
f"Blackjack {res.upper()} (rigged fast game).",
{
"Bet": fmt(amount),
"Net": fmt(profit),
"Rig": rig or "none",
"Player Hand": f\"{' '.join(player)} ({pv})\",
"Dealer Hand": f\"{' '.join(dealer)} ({dv})\",
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)
return

# Normal interactive blackjack
player = [draw_card(), draw_card()]
dealer = [draw_card(), draw_card()]
actions_log = []
actions_log.append(f"Initial: Player {' '.join(player)} ({hand_value(player)}), Dealer {dealer[0]} ?")

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

actions_log.append(f"Final: Player {' '.join(player)} ({pv}), Dealer {' '.join(dealer)} ({dv})")
await send_log(
"blackjack",
ctx.author,
f"Blackjack {res.upper()} (normal game).",
{
"Bet": fmt(amount),
"Net": fmt(profit),
"Rig": rig or "none",
"Player Final": f\"{' '.join(player)} ({pv})\",
"Dealer Final": f\"{' '.join(dealer)} ({dv})\",
"Actions": "\n".join(actions_log)[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)

class Hit(Button):
def __init__(self):
super().__init__(label="Hit", style=discord.ButtonStyle.primary)

async def callback(self, interaction):
if interaction.user.id != ctx.author.id:
return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
player.append(draw_card())
actions_log.append(f"Hit -> {' '.join(player)} ({hand_value(player)})")
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
actions_log.append("Stand")
await finish_game(interaction)

view.add_item(Hit())
view.add_item(Stand())

await ctx.send(embed=make_embed(), view=view)


# --------------------------------------------------------------
# CHESTS PANEL & BUY MENU
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

before = u["gems"]

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

await send_log(
"chest_open",
user,
f"Opened {count}x {cfg['name']}.",
{
"Chest Type": cfg['name'],
"Count": count,
"Total Spent": fmt(total_cost),
"Total Reward": fmt(total_reward),
"Net": fmt(net),
"Rewards": results_text[:1000],
"Gems Before": fmt(before),
"Gems After": fmt(u['gems'])
}
)

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
# LOTTERY (ticket system)
# --------------------------------------------------------------
LOTTERY_FILE = "lottery.json"

# Create file if missing
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
    """Start a new lottery event."""
    lot = load_lottery()
    lot["tickets"] = {}
    lot["open"] = True
    save_lottery(lot)

    embed = discord.Embed(
        title="🎟 New Lottery Started!",
        description="Tickets are now available.\nBuy with **!ticket <amount>**",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    await send_log(
        "lottery_ticket",
        ctx.author,
        "Started a new lottery.",
        {"Status": "OPEN"}
    )


@bot.command()
async def ticket(ctx, amount: str):
    """Buy lottery tickets."""
    ensure_user(ctx.author.id)

    lot = load_lottery()
    if not lot.get("open"):
        return await ctx.send("❌ Lottery is currently closed.")

    u = data[str(ctx.author.id)]
    parsed = parse_amount(amount, u["gems"], allow_all=False)
    if parsed is None or parsed <= 0:
        return await ctx.send("❌ Invalid ticket amount.")

    cost = parsed * 1_000_000  # 1m per ticket
    if u["gems"] < cost:
        return await ctx.send("❌ You don’t have enough gems.")

    before = u["gems"]

    # Update gems
    u["gems"] -= cost
    save_data(data)

    lot["tickets"].setdefault(str(ctx.author.id), 0)
    lot["tickets"][str(ctx.author.id)] += parsed
    save_lottery(lot)

    embed = discord.Embed(
        title="🎟 Ticket Purchased",
        description=(
            f"You bought **{parsed}** ticket(s).\n"
            f"Total cost: **{fmt(cost)}** gems"
        ),
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    await send_log(
        "lottery_ticket",
        ctx.author,
        f"Bought {parsed} lottery tickets.",
        {
            "Tickets Bought": parsed,
            "Cost": fmt(cost),
            "Gems Before": fmt(before),
            "Gems After": fmt(u["gems"])
        }
    )


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def lottery_end(ctx):
    """Ends lottery and picks a winner."""
    lot = load_lottery()
    if not lot.get("open"):
        return await ctx.send("❌ Lottery is not open.")

    tickets = lot.get("tickets", {})
    entries = [(uid, count) for uid, count in tickets.items() for _ in range(count)]

    if not entries:
        lot["open"] = False
        save_lottery(lot)
        return await ctx.send("❌ No tickets sold — lottery closed.")

    winner_id = int(random.choice(entries))
    ensure_user(winner_id)

    total_tickets = sum(tickets.values())
    prize = total_tickets * 1_000_000
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
            f"Winner: {winner.mention if winner else winner_id}\n"
            f"Total Tickets: **{total_tickets}**\n"
            f"Prize: **{fmt(total_prize)}** gems"
        ),
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

    await send_log(
        "lottery_end",
        winner,
        "Lottery finished.",
        {
            "Winner": f"{winner} ({winner_id})",
            "Total Tickets": total_tickets,
            "Prize": fmt(total_prize),
            "Gems Before": fmt(before),
            "Gems After": fmt(u["gems"])
        }
    )


# --------------------------------------------------------------
# ADMIN: DROPBOX GIVE
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def dropbox(ctx, member: discord.Member, amount: str):
    ensure_user(member.id)

    u = data[str(member.id)]
    val = parse_amount(amount, None, allow_all=False)
    if val is None or val <= 0:
        return await ctx.send("❌ Invalid amount.")

    before = u["gems"]
    u["gems"] += val
    save_data(data)

    embed = discord.Embed(
        title="🎁 Dropbox Delivered",
        description=f"{member.mention} received **{fmt(val)}** gems from the Dropbox.",
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
            "Receiver Before": fmt(before),
            "Receiver After": fmt(u["gems"])
        }
    )


# --------------------------------------------------------------
# ADMIN: BLESS / CURSE
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def bless(ctx, member: discord.Member, count: int = None):
    ensure_user(member.id)
    u = data[str(member.id)]

    if count is None:
        u["bless_infinite"] = not u.get("bless_infinite", False)
        status = "ENABLED" if u["bless_infinite"] else "DISABLED"
    else:
        if count <= 0:
            return await ctx.send("❌ Invalid amount.")
        u["bless_charges"] += count
        status = f"+{count} charges"

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


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def curse(ctx, member: discord.Member, count: int = None):
    ensure_user(member.id)
    u = data[str(member.id)]

    if count is None:
        u["curse_infinite"] = not u.get("curse_infinite", False)
        status = "ENABLED" if u["curse_infinite"] else "DISABLED"
    else:
        if count <= 0:
            return await ctx.send("❌ Invalid amount.")
        u["curse_charges"] += count
        status = f"+{count} charges"

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
        f"Role payout for {role.name}.",
        {
            "Role": role.name,
            "Amount": fmt(parsed),
            "Affected Users": len(affected)
        }
    )


# --------------------------------------------------------------
# TAX (removerole)
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_roles=True)
async def removerole(ctx, role_query: str, amount: str):
    """Remove gems from everyone with a role."""
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
        description=f"Removed **{fmt(parsed)}** gems from **{len(affected)}** users with {role.mention}.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

    await send_log(
        "removerole",
        ctx.author,
        f"Role tax for {role.name}.",
        {
            "Role": role.name,
            "Amount": fmt(parsed),
            "Affected Users": len(affected)
        }
    )


# --------------------------------------------------------------
# GLOBAL GIVE TO ALL
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def giveall(ctx, amount: str):
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
    await backup_to_channel(reason="manual")

    embed = discord.Embed(
        title="💾 Backup Created",
        description="A manual backup was saved.",
        color=galaxy_color()
    )
    await ctx.send(embed=embed)

    await send_log("backup", ctx.author, "Manual backup created.")


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def restorebackup(ctx, *, data_text: str):
    """Restore data file from text (raw JSON)."""
    global data
    try:
        new_data = json.loads(data_text)
    except Exception:
        return await ctx.send("❌ Invalid JSON.")

    data = new_data
    save_data(data)

    embed = discord.Embed(
        title="💾 Backup Restored",
        description="Data has been restored from JSON.",
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)

    await send_log("restore", ctx.author, "Backup restored.")


# --------------------------------------------------------------
# BOT READY
# --------------------------------------------------------------
print("Bot code loaded. Ready to run!")


bot.run(TOKEN)
