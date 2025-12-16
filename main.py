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
import aiohttp  # NEW: for Roblox API
from discord.ui import Button, View, Modal, TextInput



TOKEN = os.getenv("TOKEN")
DATA_FILE = "casino_data.json"
JOINS_CHANNEL = 1443625716859273406
LEAVES_CHANNEL = 1443625744793342132
SUSPICIOUS_SERVER = 1140681007197073468

# Categories where commands are disabled
DISABLED_CATEGORIES = {1431610646654488661}

# Channel used for JSON backups
BACKUP_CHANNEL_ID = 1431610647921295451

GAMBLE_GAMES = ["slots", "mines", "tower", "coinflip", "blackjack", "crash", "match"]



# ---------------- WITHDRAW LIMITS / COOLDOWN ----------------
WITHDRAW_GEMS_LIMIT = 500_000_000     # 500m in 2 days
WITHDRAW_EXP_LIMIT = 750_000_000      # 750m in 2 days
WITHDRAW_WINDOW_SECONDS = 2 * 24 * 3600   # 2 days
WITHDRAW_COOLDOWN = 30 * 60               # 30 minutes








# --------------------------------------------------------------
#                    DATA MANAGEMENT (LOAD / SAVE)
# --------------------------------------------------------------
# Ensure file exists
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({}, f, indent=4)


def load_data():
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=4)


# Load data *after* load_data() exists
data = load_data()


data = load_data()

# place patch HERE, NOT ABOVE
for w in data.get("withdrawals", []):
    w.setdefault("type", "gems")
    w.setdefault("roblox_user", None)
    w.setdefault("roblox_avatar", None)

save_data(data)



# --------------------------------------------------------------
#           GLOBAL DEFAULTS / SAFETY (NO DUPLICATES)
# --------------------------------------------------------------
data.setdefault("next_deposit_id", 1)
data.setdefault("next_withdraw_id", 1)
data.setdefault("deposits", [])
data.setdefault("withdrawals", [])
data.setdefault("deposit_bonuses", {})
data.setdefault("wheel_last_spin", {})
data.setdefault("wheel_extra_spins", {})
data.setdefault("quests", {})
data.setdefault("quest_last_reset", 0)
data.setdefault("codes", {})



# --- Withdraw / Deposit system defaults ---
data.setdefault("withdrawals", [])
data.setdefault("deposits", [])
data.setdefault("next_withdraw_id", 1)
data.setdefault("next_deposit_id", 1)

# Per-user withdraw tracking
data.setdefault("withdraw_history", {})   # {uid: [ {ts, amount, kind}, ... ]}
data.setdefault("withdraw_last_time", {}) # {uid: ts-of-last-withdraw}

save_data(data)





# Anti abuse fingerprint store
data.setdefault("_device_fingerprints", {})
device_fp = data["_device_fingerprints"]

# Roblox link store (Discord ↔ Roblox)
# {
#   "<discord_id>": {
#       "username": "eren460540",
#       "user_id": 123456,
#       "display_name": "Eren",
#       "avatar_url": "https://...",
#       "last_verified": 1733300000.0
#   }
# }
data.setdefault("roblox_links", {})

# Save after setting defaults
save_data(data)

# --------------------------------------------------------------
#                          OWNER
# --------------------------------------------------------------
OWNER_ID = 1317419437854560288  # Your ID

# --------------------------------------------------------------
#                       INTENTS & BOT INIT
# --------------------------------------------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# --------------------------------------------------------------
#                         CONSTANTS
# --------------------------------------------------------------
MAX_BET = 200_000_000
MIN_GAMBLE_AMOUNT = 1_000_000
LOTTERY_BONUS = 0.10
CODE_REWARD_GEMS = 100_000_000

# --------------------------------------------------------------
#                       HELPERS
# --------------------------------------------------------------



async def fetch_roblox_avatar(username: str):
    """
    Returns (user_id: int, avatar_url: str) or (None, None) if not found.
    """
    username = username.strip()
    if not username:
        return None, None

    try:
        async with aiohttp.ClientSession() as session:
            # 1) get user id
            url = "https://users.roblox.com/v1/usernames/users"
            payload = {"usernames": [username], "excludeBannedUsers": True}
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    return None, None
                js = await resp.json()
                if not js.get("data"):
                    return None, None
                user_id = js["data"][0]["id"]

            # 2) avatar headshot
            avatar_url = (
                "https://www.roblox.com/headshot-thumbnail/image"
                f"?userId={user_id}&width=420&height=420&format=png"
            )
            return user_id, avatar_url
    except Exception:
        return None, None



class ConfirmRobloxView(View):
    def __init__(self, requester_id: int, roblox_username: str,
                 amount: int, kind: str, currency: str,
                 avatar_url: str, roblox_user_id: int,
                 is_withdraw: bool):
        """
        kind: "gems" (we only use this confirmation for gems)
        currency: "gems" or "exp" string just for info text
        is_withdraw: True = withdraw, False = deposit
        """
        super().__init__(timeout=60)
        self.requester_id = requester_id
        self.roblox_username = roblox_username
        self.amount = int(amount)
        self.kind = kind
        self.currency = currency
        self.avatar_url = avatar_url
        self.roblox_user_id = roblox_user_id
        self.is_withdraw = is_withdraw

    async def _create_withdraw(self, interaction: discord.Interaction):
        uid = str(self.requester_id)
        ensure_user(self.requester_id)
        u = data[uid]

        # Check if already has pending withdraw
        pending = any(
            w.get("user_id") == self.requester_id and w.get("status") == "pending"
            for w in data.get("withdrawals", [])
        )
        if pending:
            return await interaction.response.edit_message(
                content="❌ You already have a **pending withdraw**. Wait until it is processed.",
                embed=None,
                view=None,
            )

        # Limits / cooldown
        ok, reason = _can_withdraw_now(uid, "gems", self.amount)
        if not ok:
            return await interaction.response.edit_message(
                content=reason,
                embed=None,
                view=None,
            )

        # Cost factor 1.2x
        cost = int(self.amount * 1.2)

        if u["gems"] < cost:
            return await interaction.response.edit_message(
                content=(
                    f"❌ You don't have enough gems.\n"
                    f"Needed: **{fmt(cost)}**, you have: **{fmt(u['gems'])}**."
                ),
                embed=None,
                view=None,
            )

        u["gems"] -= cost
        save_data(data)

        wid = data.get("next_withdraw_id", 1)
        entry = {
            "id": wid,
            "user_id": self.requester_id,
            # modern fields expected by admin panels
            "type": "gems",
            "currency": "gems",  # legacy name kept for compatibility
            "amount": self.amount,
            "cost": cost,
            "deducted": cost,
            "roblox_username": self.roblox_username,
            "roblox_user_id": self.roblox_user_id,
            "avatar_url": self.avatar_url,
            "created_at": time.time(),
            "status": "pending",
            "reason": None,
        }
        data["next_withdraw_id"] = wid + 1
        data.setdefault("withdrawals", []).append(entry)
        save_data(data)

        _mark_withdraw_used(uid, "gems", self.amount)

        add_history(self.requester_id, {
            "game": "withdraw_gems",
            "bet": cost,
            "result": "pending",
            "earned": -cost,
            "timestamp": time.time()
        })

        await dm_owner_new_request("withdraw", entry)

        embed = discord.Embed(
            title="✅ Withdraw Request Created",
            description=(
                f"ID: **#{wid}**\n"
                f"Amount: **{fmt(self.amount)} gems**\n"
                f"Cost charged: **{fmt(cost)} gems**\n"
                f"Roblox: `{self.roblox_username}`\n\n"
                "Admin will process it in the withdraw panel."
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=self.avatar_url)

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=None
        )

    async def _create_deposit(self, interaction: discord.Interaction):
        uid = str(self.requester_id)
        ensure_user(self.requester_id)

        did = data.get("next_deposit_id", 1)
        entry = {
            "id": did,
            "user_id": self.requester_id,
            # modern fields expected by admin panels
            "type": "gems",
            "currency": "gems",  # legacy name kept for compatibility
            "amount": self.amount,
            "roblox_username": self.roblox_username,
            "roblox_user_id": self.roblox_user_id,
            "avatar_url": self.avatar_url,
            "created_at": time.time(),
            "status": "pending",
            "reason": None,
        }
        data["next_deposit_id"] = did + 1
        data.setdefault("deposits", []).append(entry)
        save_data(data)

        add_history(self.requester_id, {
            "game": "deposit_gems",
            "bet": 0,
            "result": "pending",
            "earned": 0,
            "timestamp": time.time()
        })

        await dm_owner_new_request("deposit", entry)

        embed = discord.Embed(
            title="✅ Deposit Request Created",
            description=(
                f"ID: **#{did}**\n"
                f"Amount: **{fmt(self.amount)} gems**\n"
                f"Roblox: `{self.roblox_username}`\n\n"
                "Admin will process it in the deposit panel."
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=self.avatar_url)

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=None
        )

    @discord.ui.button(label="✅ Yes, this is me", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.requester_id:
            return await interaction.response.send_message(
                "❌ This confirmation is not for you.", ephemeral=True
            )

        if self.is_withdraw:
            await self._create_withdraw(interaction)
        else:
            await self._create_deposit(interaction)

    @discord.ui.button(label="❌ No, wrong account", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.requester_id:
            return await interaction.response.send_message(
                "❌ This confirmation is not for you.", ephemeral=True
            )

        await interaction.response.edit_message(
            content="❌ Withdraw/Deposit cancelled. Please re-run and enter the correct Roblox username.",
            embed=None,
            view=None
        )




async def dm_owner_new_request(kind: str, entry: dict):
    """
    kind: "withdraw" or "deposit"
    entry: withdraw/deposit dict
    Sends a fancy embed to OWNER_ID.
    """
    owner = bot.get_user(OWNER_ID)
    if owner is None:
        try:
            owner = await bot.fetch_user(OWNER_ID)
        except Exception:
            return

    user_id = entry.get("user_id")
    discord_user = None
    if user_id:
        try:
            discord_user = await bot.fetch_user(int(user_id))
        except Exception:
            pass

    user_tag = discord_user.mention if discord_user else f"`{user_id}`"
    embed = discord.Embed(
        title=f"📥 New {kind.title()} Request",
        color=galaxy_color()
    )
    embed.add_field(name="Discord User", value=user_tag, inline=False)
    embed.add_field(name="Internal ID", value=f"`{entry.get('id')}`", inline=True)
    embed.add_field(name="Type", value=entry.get("currency", "unknown"), inline=True)
    embed.add_field(name="Amount", value=f"**{fmt(entry.get('amount', 0))}**", inline=True)

    roblox_name = entry.get("roblox_username")
    if roblox_name:
        embed.add_field(name="Roblox Username", value=f"`{roblox_name}`", inline=False)

    embed.add_field(
        name="Created",
        value=f"<t:{int(entry.get('created_at', time.time()))}:R>",
        inline=False
    )
    embed.set_footer(text="Withdraw/Deposit panel: use !withdrawpanel / !depositpanel")
    try:
        await owner.send(embed=embed)
    except Exception:
        pass




def _record_withdraw(uid: str, kind: str, amount: int):
    """
    Store withdraw amounts for last 2 days check.
    kind: "gems" or "exp"
    amount: requested amount (NOT 1.2x / 1.9x cost).
    """
    now = time.time()
    hist = data.setdefault("withdraw_history", {})
    user_hist = hist.setdefault(uid, [])
    user_hist.append({"ts": now, "kind": kind, "amount": int(amount)})

    # clean >2 days old
    cutoff = now - WITHDRAW_WINDOW_SECONDS
    user_hist = [e for e in user_hist if e["ts"] >= cutoff]
    hist[uid] = user_hist
    save_data(data)


def _get_withdraw_totals(uid: str):
    """
    Return (gems_total_last2d, exp_total_last2d)
    based on withdraw_history.
    """
    now = time.time()
    cutoff = now - WITHDRAW_WINDOW_SECONDS
    hist = data.get("withdraw_history", {}).get(uid, [])
    gems_total = 0
    exp_total = 0
    for e in hist:
        if e["ts"] < cutoff:
            continue
        if e["kind"] == "gems":
            gems_total += int(e["amount"])
        elif e["kind"] == "exp":
            exp_total += int(e["amount"])
    return gems_total, exp_total


def _can_withdraw_now(uid: str, kind: str, amount: int):
    """
    Check 30 min cooldown and 2-day caps.
    Returns (ok: bool, reason: str | None)
    """
    now = time.time()
    last_map = data.setdefault("withdraw_last_time", {})
    last_ts = last_map.get(uid, 0)

    # 30 min cooldown
    if now - last_ts < WITHDRAW_COOLDOWN:
        remaining = int(WITHDRAW_COOLDOWN - (now - last_ts))
        mins = remaining // 60
        secs = remaining % 60
        return False, f"⏳ You must wait **{mins}m {secs}s** before making another withdraw."

    gems_total, exp_total = _get_withdraw_totals(uid)
    amount = int(amount)

    if kind == "gems":
        if gems_total + amount > WITHDRAW_GEMS_LIMIT:
            return False, (
                f"❌ 2-day **GEMS** withdraw cap reached.\n"
                f"Limit: **{fmt(WITHDRAW_GEMS_LIMIT)}**, used: **{fmt(gems_total)}**, "
                f"requested: **{fmt(amount)}**."
            )
    elif kind == "exp":
        if exp_total + amount > WITHDRAW_EXP_LIMIT:
            return False, (
                f"❌ 2-day **EXP** withdraw cap reached.\n"
                f"Limit: **{fmt(WITHDRAW_EXP_LIMIT)}**, used: **{fmt(exp_total)}**, "
                f"requested: **{fmt(amount)}**."
            )

    return True, None


def _mark_withdraw_used(uid: str, kind: str, amount: int):
    """Updates last_withdraw time + history."""
    uid = str(uid)
    data.setdefault("withdraw_last_time", {})[uid] = time.time()
    _record_withdraw(uid, kind, amount)
    save_data(data)





FREE_SOURCES = {"daily", "work", "invite_reward", "admin_give", "dropbox"}
GAMBLE_GAMES = {"coinflip", "slots", "mines", "tower", "blackjack", "crash", "match"}
ACHIEVEMENT_DEFS = {
    "first_loan": {
        "emoji": "🌌",
        "name": "First Loan",
        "desc": "Open a line of cosmic credit for the first time."
    },
    "paid_first_loan": {
        "emoji": "💎",
        "name": "Debt Crusher",
        "desc": "Repay your first loan in full."
    },
    "debt_free": {
        "emoji": "🏆",
        "name": "Debt-Free Voyager",
        "desc": "Maintain a clean ledger with no active debts."
    },
    "high_roller": {
        "emoji": "🔥",
        "name": "High Roller",
        "desc": "Wager 1,000,000,000+ gems over your lifetime."
    },
    "daily_streak_7": {
        "emoji": "🪐",
        "name": "7-Day Streak",
        "desc": "Claim dailies seven days in a row."
    },
}
HIGH_ROLLER_WAGER = 1_000_000_000


def compute_gamble_ratio(user_id):
    ensure_user(user_id)
    hist = data[str(user_id)].get("history", [])

    free_total = 0
    gambled_total = 0

    for e in hist:
        game = e.get("game", "")
        bet = e.get("bet", 0) or 0
        earned = e.get("earned", 0) or 0

        if game in FREE_SOURCES and earned > 0:
            free_total += earned

        if game in GAMBLE_GAMES and bet > 0:
            gambled_total += bet

    ratio = (gambled_total / free_total) if free_total > 0 else 0
    return free_total, gambled_total, ratio


def fmt(n):
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


def _loan_record(uid: str):
    ensure_user(uid)
    return data[str(uid)].get("loan")


def _set_loan(uid: str, loan):
    ensure_user(uid)
    data[str(uid)]["loan"] = loan
    save_data(data)


def _loan_is_restricted(uid: str):
    loan = _loan_record(uid)
    if not loan:
        return False
    return loan.get("status") in {"active", "defaulted"}


def achievement_record(uid: str):
    ensure_user(uid)
    return data[str(uid)].setdefault("achievements", {})


def grant_achievement(uid: str, key: str) -> bool:
    if key not in ACHIEVEMENT_DEFS:
        return False
    ach = achievement_record(uid)
    if ach.get(key):
        return False
    ach[key] = True
    save_data(data)
    return True


def refresh_achievements(uid: str):
    ensure_user(uid)
    u = data[str(uid)]

    if u.get("lifetime_wagered", 0) >= HIGH_ROLLER_WAGER:
        grant_achievement(uid, "high_roller")

    loan = u.get("loan")
    if loan and loan.get("status") == "paid":
        grant_achievement(uid, "paid_first_loan")
    if not loan or loan.get("status") == "paid":
        grant_achievement(uid, "debt_free")

    # Daily streak achievement is optional; only award if a streak counter exists.
    if "daily_streak" in u and u.get("daily_streak", 0) >= 7:
        grant_achievement(uid, "daily_streak_7")


def ensure_user(user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {}
    u = data[uid]
    u.setdefault("gems", 25.0)
    u.setdefault("exp", 0.0)
    u.setdefault("last_daily", 0.0)
    u.setdefault("last_work", 0.0)
    u.setdefault("history", [])
    u.setdefault("bless_infinite", False)
    u.setdefault("curse_infinite", False)
    u.setdefault("bless_charges", 0)
    u.setdefault("curse_charges", 0)
    u.setdefault("lifetime_wagered", 0)
    u.setdefault("loan", None)
    u.setdefault("achievements", {})
    u.setdefault("redeemed_codes", [])
    save_data(data)


def add_history(user_id, entry):
    ensure_user(user_id)
    uid = str(user_id)

    game = entry.get("game")
    bet = int(entry.get("bet", 0) or 0)
    earned = int(entry.get("earned", 0) or 0)

    if earned > 0:
        _quest_add_earn(uid, earned)
    if bet > 0 and game in GAMBLE_GAMES:
        _quest_add_wager(uid, bet)
        data[uid]["lifetime_wagered"] = data[uid].get("lifetime_wagered", 0) + bet
        refresh_achievements(uid)

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


def normalize_code_name(code_name: str) -> str:
    return code_name.strip().lower()


LOAN_MAX_RATIO = 0.10
LOAN_DURATION_SECONDS = 72 * 3600
LOAN_REMINDER_SECONDS = 24 * 3600
LOAN_INTEREST = 1.50


def _loan_limit(u):
    return max(0, int(u.get("lifetime_wagered", 0) * LOAN_MAX_RATIO))


def _loan_payback_amount(amount: int) -> int:
    return int(round(amount * LOAN_INTEREST))


def _loan_embed(title: str, description: str, color=None):
    embed = discord.Embed(title=title, description=description, color=color or galaxy_color())
    embed.set_footer(text="Galaxy Credit Bureau • Cosmic finance")
    return embed


def normalize_role_name(name: str) -> str:
    return "".join(ch.lower() for ch in name if ch.isalnum())


def find_role_by_query(guild: discord.Guild, query: str):
    query = query.strip()

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

    exact_matches = [r for r in roles if normalize_role_name(r.name) == norm_query]
    if len(exact_matches) == 1:
        return exact_matches[0]
    elif len(exact_matches) > 1:
        return sorted(exact_matches, key=lambda r: len(r.name))[0]

    partial_matches = [r for r in roles if norm_query in normalize_role_name(r.name)]
    if len(partial_matches) == 1:
        return partial_matches[0]
    elif len(partial_matches) > 1:
        return sorted(partial_matches, key=lambda r: len(r.name))[0]

    return None


def consume_rig(u):
    mode = None
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



# ==============================================================
#                 CRITICAL DATA PATCH FIX (RUN ONCE)
# ==============================================================
# This runs every startup and gently fixes old data formats.
# It is SAFE to keep; it won't break anything if run again.

# Ensure new global dicts exist
if "wheel_extra_spins" not in data or not isinstance(data["wheel_extra_spins"], dict):
    data["wheel_extra_spins"] = {}

if "wheel_last_spin" not in data or not isinstance(data["wheel_last_spin"], dict):
    data["wheel_last_spin"] = {}

if "withdraw_history" not in data or not isinstance(data["withdraw_history"], dict):
    data["withdraw_history"] = {}

if "withdraw_last_time" not in data or not isinstance(data["withdraw_last_time"], dict):
    data["withdraw_last_time"] = {}

if "roblox_links" not in data or not isinstance(data["roblox_links"], dict):
    data["roblox_links"] = {}

# ---------------- FIX OLD WITHDRAW ENTRIES ----------------
for w in data.get("withdrawals", []):
    if not isinstance(w, dict):
        continue

    # New system expects w["type"] ("gems" / "exp")
    if "type" not in w:
        # migrate from old "currency" if exists, else default to "gems"
        w["type"] = w.get("currency", "gems")

    # If old field name "cost" was used, create "deducted" for the new code
    if "deducted" not in w and "cost" in w:
        w["deducted"] = w["cost"]

# ---------------- FIX OLD DEPOSIT ENTRIES ----------------
for d in data.get("deposits", []):
    if not isinstance(d, dict):
        continue

    # New system expects d["type"]
    if "type" not in d:
        d["type"] = d.get("currency", "gems")

# Save fixed structure
save_data(data)
# ==============================================================



# ==============================================================
# 🔧 HARD PATCH — FIX OLD WITHDRAW/DEPOSIT ENTRIES (type/status)
# ==============================================================

changed = False

# --- Fix withdrawals ---
if not isinstance(data.get("withdrawals"), list):
    data["withdrawals"] = []
    changed = True

for w in data["withdrawals"]:
    if "type" not in w:
        w["type"] = "gems"   # DEFAULT → gems
        changed = True
    if "status" not in w:
        w["status"] = "pending"
        changed = True
    if "deducted" not in w:
        w["deducted"] = w.get("amount", 0)
        changed = True

# --- Fix deposits ---
if not isinstance(data.get("deposits"), list):
    data["deposits"] = []
    changed = True

for d in data["deposits"]:
    if "type" not in d:
        d["type"] = "gems"
        changed = True
    if "status" not in d:
        d["status"] = "pending"
        changed = True

if changed:
    print("⚠️ Patched old withdraw/deposit entries automatically.")
    save_data(data)






#  ---------------------- BACKUP SYSTEM ---------------------- #

async def backup_to_channel(reason: str = "auto"):
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
        pass


def apply_restored_data(new_data: dict):
    """Replace global data store from a backup while keeping defaults intact."""
    if not isinstance(new_data, dict):
        raise ValueError("Backup JSON must be a JSON object.")

    global data, device_fp
    data = new_data

    # Re-apply required defaults so existing commands don't crash after a restore.
    data.setdefault("next_deposit_id", 1)
    data.setdefault("next_withdraw_id", 1)
    data.setdefault("deposits", [])
    data.setdefault("withdrawals", [])
    data.setdefault("deposit_bonuses", {})
    data.setdefault("wheel_last_spin", {})
    data.setdefault("wheel_extra_spins", {})
    data.setdefault("quests", {})
    data.setdefault("quest_last_reset", 0)
    data.setdefault("codes", {})
    data.setdefault("withdraw_history", {})
    data.setdefault("withdraw_last_time", {})
    data.setdefault("roblox_links", {})
    data.setdefault("_device_fingerprints", {})

    # Refresh derived references that other helpers rely on.
    device_fp = data["_device_fingerprints"]

    save_data(data)


@tasks.loop(minutes=10)
async def auto_backup_task():
    await backup_to_channel("auto")


async def _dm_loan_reminder(uid: str, loan: dict):
    try:
        member = await bot.fetch_user(int(uid))
    except Exception:
        return

    embed = discord.Embed(
        title="🌌 Loan Reminder",
        description=(
            f"💎 Principal: **{fmt(loan['amount'])}** gems\n"
            f"🪐 Payback: **{fmt(loan['payback_amount'])}** gems\n"
            f"⏳ Due: <t:{int(loan['due_at'])}:R> — pay with `!payback`"
        ),
        color=galaxy_color(),
    )
    embed.set_footer(text="Galaxy Credit Bureau • 72h repayment window")
    try:
        await member.send(embed=embed)
    except Exception:
        pass


async def _dm_loan_default(uid: str, loan: dict):
    try:
        owner = await bot.fetch_user(OWNER_ID)
    except Exception:
        return

    embed = discord.Embed(
        title="🚨 Loan Default Alert",
        description=(
            f"User <@{uid}> defaulted on **{fmt(loan['payback_amount'])}** gems.\n"
            f"Taken: <t:{int(loan['taken_at'])}:R> | Due: <t:{int(loan['due_at'])}:R>"
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(text="Galaxy Credit Bureau • Manual resolution required")
    try:
        await owner.send(embed=embed)
    except Exception:
        pass


@tasks.loop(minutes=30)
async def loan_watchdog():
    now = time.time()
    dirty = False

    for uid, u in list(data.items()):
        if not uid.isdigit():
            continue

        ensure_user(uid)
        loan = u.get("loan")
        if not loan:
            continue

        status = loan.get("status")
        if status == "active":
            last_ping = loan.get("last_reminder", loan.get("taken_at", now))
            if now - last_ping >= LOAN_REMINDER_SECONDS:
                await _dm_loan_reminder(uid, loan)
                loan["last_reminder"] = now
                dirty = True

            if now >= loan.get("due_at", 0):
                loan["status"] = "defaulted"
                dirty = True
                await _dm_loan_default(uid, loan)

        elif status == "defaulted":
            # No automatic recovery; admins must resolve.
            continue

    if dirty:
        save_data(data)


@auto_backup_task.before_loop
async def before_auto_backup():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    if not auto_backup_task.is_running():
        auto_backup_task.start()
    if not loan_watchdog.is_running():
        loan_watchdog.start()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


def short(n: int) -> str:
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
    value = value.strip().replace(",", "").lower()
    multipliers = {
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
        "t": 1_000_000_000_000
    }
    if value[-1] in multipliers:
        return int(float(value[:-1]) * multipliers[value[-1]])
    return int(float(value))


from discord.ui import Button, View  # already imported above

# ==============================================================
#               ROBLOX AVATAR + PROFILE VERIFICATION
# ==============================================================

ROBLOX_USERNAME_API = "https://users.roblox.com/v1/usernames/users"
ROBLOX_USER_API = "https://users.roblox.com/v1/users/{user_id}"
ROBLOX_THUMBNAIL_API = (
    "https://thumbnails.roblox.com/v1/users/avatar-headshot"
    "?userIds={user_id}&size=150x150&format=Png&isCircular=false"
)


async def fetch_roblox_profile(username: str):
    """
    Returns dict:
      {
        "user_id": int,
        "username": str,
        "display_name": str,
        "avatar_url": str,
        "created": str (ISO),
        "age_days": int
      }
    or None if not found.
    """
    username = username.strip()

    async with aiohttp.ClientSession() as session:
        # Step 1: username -> user_id
        payload = {"usernames": [username], "excludeBannedUsers": True}
        async with session.post(ROBLOX_USERNAME_API, json=payload) as resp:
            if resp.status != 200:
                return None
            data_json = await resp.json()
            data_list = data_json.get("data", [])
            if not data_list:
                return None
            user_id = data_list[0]["id"]
            real_username = data_list[0]["name"]

        # Step 2: user info
        async with session.get(ROBLOX_USER_API.format(user_id=user_id)) as resp:
            if resp.status != 200:
                return None
            user_info = await resp.json()
            display_name = user_info.get("displayName", real_username)
            created = user_info.get("created", "")

        # Step 3: avatar thumbnail
        async with session.get(ROBLOX_THUMBNAIL_API.format(user_id=user_id)) as resp:
            if resp.status != 200:
                avatar_url = None
            else:
                thumb_data = await resp.json()
                dlist = thumb_data.get("data", [])
                avatar_url = dlist[0].get("imageUrl") if dlist else None

    # Compute age days (rough)
    age_days = 0
    try:
        # created like "2021-05-23T12:34:56Z"
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        age_days = (datetime.utcnow() - dt).days
    except Exception:
        pass

    return {
        "user_id": user_id,
        "username": real_username,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "created": created,
        "age_days": age_days,
    }


async def roblox_verification_flow(interaction: discord.Interaction, roblox_username: str, *, purpose: str):
    """
    ALWAYS called before creating a GEMS withdraw/deposit.
    Shows avatar + profile in an ephemeral embed and asks:
    'Is this you?'

    Returns:
      profile dict if confirmed,
      None if user denies or times out.
    """
    profile = await fetch_roblox_profile(roblox_username)
    if profile is None:
        await interaction.response.send_message(
            f"❌ I couldn't find a Roblox account with username **{roblox_username}**.",
            ephemeral=True
        )
        return None

    uid = str(interaction.user.id)
    links = data.get("roblox_links", {})
    old_link = links.get(uid)

    # Detect username change → DM owner
    if old_link and old_link["username"].lower() != profile["username"].lower():
        owner = interaction.guild.get_member(OWNER_ID) if interaction.guild else None
        try:
            if owner:
                await owner.send(
                    f"⚠️ **Roblox Username Changed**\n"
                    f"Discord: {interaction.user.mention}\n"
                    f"Old: `{old_link['username']}`\n"
                    f"New: `{profile['username']}`"
                )
        except Exception:
            pass

    age_days = profile["age_days"]
    suspicious = age_days <= 7

    # Build fancy embed
    embed = discord.Embed(
        title="🎮 Roblox Account Verification",
        description=(
            f"Purpose: **{purpose}**\n"
            f"Is this your Roblox account?\n\n"
            f"**Username:** `{profile['username']}`\n"
            f"**Display Name:** `{profile['display_name']}`\n"
            f"**Account Age:** `{age_days}` days"
        ),
        color=galaxy_color()
    )

    if profile["avatar_url"]:
        embed.set_thumbnail(url=profile["avatar_url"])

    if suspicious:
        embed.add_field(
            name="⚠️ Warning",
            value="This account is very new or low-activity. Owner will be notified.",
            inline=False
        )
        # DM owner about suspicious account
        try:
            owner = interaction.guild.get_member(OWNER_ID) if interaction.guild else None
            if owner:
                await owner.send(
                    f"⚠️ **Suspicious Roblox Account Used for {purpose}**\n"
                    f"Discord: {interaction.user.mention}\n"
                    f"Username: `{profile['username']}`\n"
                    f"Age: `{age_days}` days\n"
                    f"(No automatic action taken.)"
                )
        except Exception:
            pass

    class ConfirmRoblox(View):
        def __init__(self):
            super().__init__(timeout=60)
            self.result = None

        @discord.ui.button(label="✅ Yes, this is me", style=discord.ButtonStyle.green)
        async def yes(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            if button_interaction.user.id != interaction.user.id:
                return await button_interaction.response.send_message(
                    "❌ This confirmation is not for you.", ephemeral=True
                )
            self.result = True
            for c in self.children:
                c.disabled = True
            await button_interaction.response.edit_message(
                content="✅ Verified. Your request has been sent to the panel.",
                embed=embed,
                view=self
            )
            self.stop()

        @discord.ui.button(label="❌ No, not me", style=discord.ButtonStyle.red)
        async def no(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            if button_interaction.user.id != interaction.user.id:
                return await button_interaction.response.send_message(
                    "❌ This confirmation is not for you.", ephemeral=True
                )
            self.result = False
            for c in self.children:
                c.disabled = True
            await button_interaction.response.edit_message(
                content="❌ Verification cancelled. Please check your username.",
                embed=embed,
                view=self
            )
            self.stop()

        async def on_timeout(self):
            if self.result is None:
                for c in self.children:
                    c.disabled = True
                try:
                    await interaction.edit_original_response(
                        content="⏰ Verification timed out. Please try again.",
                        embed=embed,
                        view=self
                    )
                except Exception:
                    pass

    view = ConfirmRoblox()

    # If not yet responded → send; else followup
    try:
        await interaction.response.send_message(
            content="Please confirm your Roblox account:",
            embed=embed,
            view=view,
            ephemeral=True
        )
    except discord.InteractionResponded:
        await interaction.followup.send(
            content="Please confirm your Roblox account:",
            embed=embed,
            view=view,
            ephemeral=True
        )

    await view.wait()

    if view.result is True:
        # Save / update link
        links[uid] = {
            "username": profile["username"],
            "user_id": profile["user_id"],
            "display_name": profile["display_name"],
            "avatar_url": profile["avatar_url"],
            "last_verified": time.time(),
        }
        data["roblox_links"] = links
        save_data(data)
        return profile

    return None





# ==============================================================
#                 DEPOSIT / WITHDRAW DATA DEFAULTS
# ==============================================================

# Core defaults
data.setdefault("withdrawals", [])
data.setdefault("deposits", [])
data.setdefault("next_withdraw_id", 1)
data.setdefault("next_deposit_id", 1)
data.setdefault("roblox_links", {})          # discord_id -> {username, user_id, avatar_url}
data.setdefault("wheel_last_spin", {})
data.setdefault("wheel_extra_spins", {})
save_data(data)

# Safety: if old code left dicts here, force them to lists
if not isinstance(data.get("withdrawals"), list):
    data["withdrawals"] = []
if not isinstance(data.get("deposits"), list):
    data["deposits"] = []
save_data(data)

# --- MIGRATION PATCH FOR OLD ENTRIES (fix KeyError: 'type') ---
changed = False

for w in data.get("withdrawals", []):
    if "type" not in w:
        # Best guess: old system probably only had gems
        w["type"] = "gems"
        changed = True
    if "status" not in w:
        w["status"] = "pending"
        changed = True

for d in data.get("deposits", []):
    if "type" not in d:
        d["type"] = "gems"
        changed = True
    if "status" not in d:
        d["status"] = "pending"
        changed = True

if changed:
    save_data(data)


# ==============================================================
#                 WITHDRAW / DEPOSIT CONSTANTS
# ==============================================================

WITHDRAW_GEMS_LIMIT_2D = 500_000_000     # 500m in 48h
WITHDRAW_EXP_LIMIT_2D  = 750_000_000     # 750m in 48h
WITHDRAW_WINDOW_SEC    = 2 * 24 * 3600   # 2 days
WITHDRAW_COOLDOWN_SEC  = 30 * 60         # 30 minutes

WITHDRAW_GEMS_FEE = 1.2      # 1.2x removed from gems  (20% penalty)
WITHDRAW_EXP_FEE  = 1.9      # 1.9x removed from exp
DEPOSIT_EXP_MULT_ROBLOX = WITHDRAW_GEMS_FEE
DEPOSIT_EXP_MULT_OTHER = WITHDRAW_EXP_FEE


# ==============================================================
#                      OWNER DM HELPER
# ==============================================================

async def notify_owner(title: str, description: str, fields: list = None):
    """
    DM the OWNER_ID with an embed.
    fields: list of tuples -> (name, value, inline)
    """
    try:
        owner = bot.get_user(OWNER_ID) or await bot.fetch_user(OWNER_ID)
    except Exception:
        return

    if not owner:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=galaxy_color(),
        timestamp=datetime.utcnow()
    )

    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

    try:
        await owner.send(embed=embed)
    except Exception:
        pass


# ==============================================================
#                    ROBLOX AVATAR LOOKUP
# ==============================================================

async def roblox_lookup(username: str):
    """
    Returns (roblox_id, display_name, avatar_url) or (None, None, None)
    Uses Roblox public APIs.
    """
    username = username.strip()
    if not username:
        return None, None, None

    try:
        async with aiohttp.ClientSession() as session:
            # 1) username -> userId
            url = "https://users.roblox.com/v1/usernames/users"
            payload = {"usernames": [username], "excludeBannedUsers": True}
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    return None, None, None
                j = await resp.json()
                data_list = j.get("data", [])
                if not data_list:
                    return None, None, None
                entry = data_list[0]
                user_id = entry.get("id")
                display_name = entry.get("displayName") or entry.get("name") or username

            # 2) avatar thumbnail
            thumb_url = (
                "https://thumbnails.roblox.com/v1/users/avatar-headshot"
                f"?userIds={user_id}&size=150x150&format=Png&isCircular=false"
            )
            async with session.get(thumb_url) as resp2:
                if resp2.status != 200:
                    avatar_url = None
                else:
                    j2 = await resp2.json()
                    d2 = j2.get("data", [])
                    avatar_url = d2[0].get("imageUrl") if d2 else None

        return user_id, display_name, avatar_url
    except Exception:
        return None, None, None


def get_roblox_link_for(discord_id: int):
    return data.get("roblox_links", {}).get(str(discord_id))


def set_roblox_link_for(discord_id: int, username: str, roblox_id: int, avatar_url: str | None):
    links = data.setdefault("roblox_links", {})
    links[str(discord_id)] = {
        "username": username,
        "user_id": roblox_id,
        "avatar_url": avatar_url,
    }
    save_data(data)


# ==============================================================
#      HELPERS: FIND DUPLICATE ROBLOX ACCOUNTS (MULTI DISCORD)
# ==============================================================

def find_roblox_duplicates():
    """
    Returns dict[roblox_id] -> list[discord_id] where same roblox_id
    is linked by 2+ different Discord accounts.
    """
    links = data.get("roblox_links", {})
    by_rid: dict[int, list[int]] = {}

    for did_str, info in links.items():
        try:
            did = int(did_str)
        except ValueError:
            continue
        rid = info.get("user_id")
        if not rid:
            continue
        by_rid.setdefault(rid, []).append(did)

    duplicates = {rid: dids for rid, dids in by_rid.items() if len(dids) > 1}
    return duplicates


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def robloxdupes(ctx):
    """
    Admin command: show all Roblox accounts linked by multiple Discord users.
    Usage: !robloxdupes
    """
    duplicates = find_roblox_duplicates()
    if not duplicates:
        return await ctx.send("✅ No duplicated Roblox links found.")

    desc_lines = []
    for rid, discord_ids in duplicates.items():
        mentions = " ".join(f"<@{did}>" for did in discord_ids)
        desc_lines.append(f"**Roblox ID:** `{rid}`\nDiscord: {mentions}\n")

    embed = discord.Embed(
        title="⚠️ Duplicated Roblox Links",
        description="\n".join(desc_lines),
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)


# ==============================================================
#                WITHDRAW LIMIT / COOLDOWN HELPERS
# ==============================================================

def get_user_withdraws_last_2d(user_id: int, wtype: str):
    """
    Sum amount (base amount, not fee) of this user's withdraws
    of given type (gems/exp) in the last 48h (pending + accepted).
    """
    now = time.time()
    cutoff = now - WITHDRAW_WINDOW_SEC
    total = 0
    for w in data.get("withdrawals", []):
        if w.get("user_id") != user_id:
            continue
        if w.get("type") != wtype:
            continue
        if w.get("created_at", 0) < cutoff:
            continue
        if w.get("status") not in ("pending", "accepted"):
            continue
        total += int(w.get("amount", 0) or 0)
    return total


def has_pending_withdraw(user_id: int) -> bool:
    for w in data.get("withdrawals", []):
        if w.get("user_id") == user_id and w.get("status") == "pending":
            return True
    return False


def record_withdraw_cooldown(user_id: int):
    ensure_user(user_id)
    u = data[str(user_id)]
    u["last_withdraw_cmd"] = time.time()
    save_data(data)


def check_withdraw_cooldown(user_id: int):
    ensure_user(user_id)
    u = data[str(user_id)]
    last = u.get("last_withdraw_cmd", 0)
    if last == 0:
        return 0
    diff = time.time() - last
    remain = WITHDRAW_COOLDOWN_SEC - diff
    return max(0, remain)


# ==============================================================
#              INTERNAL CREATORS (NO UI, JUST LOGIC)
# ==============================================================

def _create_withdraw_entry(user: discord.User, wtype: str, amount: int,
                           deducted: int, roblox_username: str | None):
    wid = data.get("next_withdraw_id", 1)
    entry = {
        "id": wid,
        "user_id": user.id,
        "discord_tag": str(user),
        "type": wtype,                 # "gems" or "exp"
        "amount": int(amount),         # base requested
        "deducted": int(deducted),     # what we removed from balance
        "roblox_username": roblox_username,
        "status": "pending",           # pending / accepted / denied
        "created_at": time.time(),
    }
    arr = data.setdefault("withdrawals", [])
    arr.append(entry)
    data["next_withdraw_id"] = wid + 1
    save_data(data)
    return entry


def _create_deposit_entry(user: discord.User, dtype: str, amount: int,
                          roblox_username: str | None):
    did = data.get("next_deposit_id", 1)
    entry = {
        "id": did,
        "user_id": user.id,
        "discord_tag": str(user),
        "type": dtype,                # "gems" or "exp"
        "amount": int(amount),
        "roblox_username": roblox_username,
        "status": "pending",          # pending / accepted / denied
        "created_at": time.time(),
    }
    arr = data.setdefault("deposits", [])
    arr.append(entry)
    data["next_deposit_id"] = did + 1
    save_data(data)
    return entry


# ==============================================================
#                FINALIZE WITHDRAW / DEPOSIT (LOGIC)
# ==============================================================

async def finalize_withdraw(interaction: discord.Interaction,
                            user: discord.User,
                            wtype: str,
                            amount_str: str,
                            roblox_username: str | None):
    """
    Shared withdraw logic once avatar is confirmed (for gems) or
    directly for exp.
    """
    ensure_user(user.id)
    u = data[str(user.id)]

    # parse amount
    amount = parse_amount(amount_str, u.get("gems", 0), allow_all=False)
    if amount is None or amount <= 0:
        return await interaction.response.send_message(
            "❌ Invalid amount.", ephemeral=True
        )

    # cooldown check
    remain = check_withdraw_cooldown(user.id)
    if remain > 0:
        mins = int(remain // 60)
        secs = int(remain % 60)
        await interaction.response.send_message(
            f"⏳ You must wait **{mins}m {secs}s** before another withdraw.",
            ephemeral=True
        )
        await notify_owner(
            "Withdraw blocked (cooldown)",
            f"User {user.mention} tried to withdraw during cooldown.",
            [
                ("User", f"{user.mention} (`{user.id}`)", False),
                ("Type", wtype, True),
                ("Amount", fmt(amount), True),
            ],
        )
        return

    # one pending only
    if has_pending_withdraw(user.id):
        await interaction.response.send_message(
            "❌ You already have a pending withdraw. Wait for staff to handle it first.",
            ephemeral=True
        )
        await notify_owner(
            "Withdraw blocked (already pending)",
            f"User {user.mention} tried to create a second withdraw while one is pending.",
            [
                ("User", f"{user.mention} (`{user.id}`)", False),
                ("Type", wtype, True),
                ("Amount", fmt(amount), True),
            ],
        )
        return

    # 48h limit
    if wtype == "gems":
        used = get_user_withdraws_last_2d(user.id, "gems")
        limit = WITHDRAW_GEMS_LIMIT_2D
    else:
        used = get_user_withdraws_last_2d(user.id, "exp")
        limit = WITHDRAW_EXP_LIMIT_2D

    if used + amount > limit:
        await interaction.response.send_message(
            f"❌ You reached the 2-day limit for {wtype} withdraws.\n"
            f"Used: **{fmt(used)}**, limit: **{fmt(limit)}**.",
            ephemeral=True
        )
        await notify_owner(
            "Withdraw blocked (48h limit)",
            f"User {user.mention} hit the {wtype} withdraw limit.",
            [
                ("User", f"{user.mention} (`{user.id}`)", False),
                ("Type", wtype, True),
                ("Requested", fmt(amount), True),
                ("Used (48h)", fmt(used), True),
                ("Limit", fmt(limit), True),
            ],
        )
        return

    # balance + fee (20% penalty for gems via 1.2x)
    if wtype == "gems":
        fee_mult = WITHDRAW_GEMS_FEE
        balance = float(u.get("gems", 0))
    else:
        fee_mult = WITHDRAW_EXP_FEE
        balance = float(u.get("exp", 0))

    deducted = int(amount * fee_mult)

    if balance < deducted:
        await interaction.response.send_message(
            f"❌ You don't have enough {wtype}.\n"
            f"Needed (with fee): **{fmt(deducted)}**",
            ephemeral=True
        )
        return

    # deduct
    if wtype == "gems":
        u["gems"] = balance - deducted
    else:
        u["exp"] = balance - deducted
    save_data(data)

    record_withdraw_cooldown(user.id)

    # queue entry
    entry = _create_withdraw_entry(
        user=user,
        wtype=wtype,
        amount=int(amount),
        deducted=int(deducted),
        roblox_username=roblox_username,
    )

    # history
    add_history(user.id, {
        "game": f"withdraw_{wtype}",
        "bet": deducted,
        "result": "pending",
        "earned": 0,
        "timestamp": time.time()
    })

    # user message
    await interaction.response.send_message(
        f"✅ Your **{wtype}** withdraw request has been created.\n"
        f"ID: **#{entry['id']}**\n"
        f"Amount requested: **{fmt(amount)}** (fee: {fee_mult}x → deducted **{fmt(deducted)}**).",
        ephemeral=True
    )

    # owner DM (ALWAYS)
    await notify_owner(
        "New Withdraw Request",
        f"User {user.mention} created a {wtype} withdraw.",
        [
            ("User", f"{user.mention} (`{user.id}`)", False),
            ("Type", wtype, True),
            ("Amount", fmt(amount), True),
            ("Deducted", fmt(deducted), True),
            ("Roblox Username", roblox_username or "None / EXP", False),
            ("Entry ID", f"#{entry['id']}", True),
        ],
    )


async def finalize_deposit(interaction: discord.Interaction,
                           user: discord.User,
                           dtype: str,
                           amount_str: str,
                           roblox_username: str | None):
    """
    Create a pending deposit request.
    No balance changes here. Staff adds on accept.
    """
    ensure_user(user.id)
    u = data[str(user.id)]

    amount = parse_amount(amount_str, u.get("gems", 0), allow_all=False)
    if amount is None or amount <= 0:
        return await interaction.response.send_message(
            "❌ Invalid amount.", ephemeral=True
        )

    entry = _create_deposit_entry(
        user=user,
        dtype=dtype,
        amount=int(amount),
        roblox_username=roblox_username,
    )

    # history (info only)
    add_history(user.id, {
        "game": f"deposit_{dtype}",
        "bet": 0,
        "result": "pending",
        "earned": 0,
        "timestamp": time.time()
    })

    await interaction.response.send_message(
        f"✅ Your **{dtype}** deposit request has been created.\n"
        f"ID: **#{entry['id']}**\n"
        f"Amount: **{fmt(amount)}**.\n"
        f"Staff will handle it soon.",
        ephemeral=True
    )

    # owner DM (ALWAYS)
    await notify_owner(
        "New Deposit Request",
        f"User {user.mention} created a {dtype} deposit.",
        [
            ("User", f"{user.mention} (`{user.id}`)", False),
            ("Type", dtype, True),
            ("Amount", fmt(amount), True),
            ("Roblox Username", roblox_username or "None / EXP", False),
            ("Entry ID", f"#{entry['id']}", True),
        ],
    )


# ==============================================================
#            ROBLOX AVATAR CONFIRM VIEWS (YES / NO)
# ==============================================================

class RobloxConfirmView(discord.ui.View):
    def __init__(self, user: discord.User, username: str, roblox_id: int,
                 avatar_url: str | None, mode: str, amount_str: str):
        """
        mode: 'withdraw_gems' or 'deposit_gems'
        """
        super().__init__(timeout=60)
        self.target = user
        self.username = username
        self.roblox_id = roblox_id
        self.avatar_url = avatar_url
        self.mode = mode
        self.amount_str = amount_str

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "❌ This confirmation is not for you.", ephemeral=True
            )
            return False
        return True

    async def _check_and_notify_duplicates(self):
        """
        After a user links a Roblox account, check if same roblox_id
        is used by multiple Discord users and DM owner.
        """
        duplicates = find_roblox_duplicates()
        if self.roblox_id not in duplicates:
            return

        dids = duplicates[self.roblox_id]
        fields = []
        mention_list = []
        for did in dids:
            mention_list.append(f"<@{did}> (`{did}`)")
        fields.append(("Discord Users", "\n".join(mention_list), False))

        await notify_owner(
            "⚠️ Same Roblox Account Linked by Multiple Discord Users",
            f"Roblox ID `{self.roblox_id}` / username `{self.username}` "
            f"is linked to multiple Discord accounts.",
            fields
        )

    @discord.ui.button(label="✅ Yes, that's me", style=discord.ButtonStyle.success)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # store link
        set_roblox_link_for(
            discord_id=self.target.id,
            username=self.username,
            roblox_id=self.roblox_id,
            avatar_url=self.avatar_url
        )

        # Check duplicates and notify owner if needed
        await self._check_and_notify_duplicates()

        # Continue flow
        if self.mode == "withdraw_gems":
            await finalize_withdraw(
                interaction=interaction,
                user=self.target,
                wtype="gems",
                amount_str=self.amount_str,
                roblox_username=self.username
            )
        else:  # deposit_gems
            await finalize_deposit(
                interaction=interaction,
                user=self.target,
                dtype="gems",
                amount_str=self.amount_str,
                roblox_username=self.username
            )

        self.stop()

    @discord.ui.button(label="❌ No, that's not me", style=discord.ButtonStyle.danger)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Just cancel, DM owner
        await interaction.response.send_message(
            "❌ Withdraw/Deposit cancelled. Please try again with the correct Roblox username.",
            ephemeral=True
        )

        await notify_owner(
            "Roblox Avatar Rejected",
            f"{self.target.mention} rejected the shown Roblox account.",
            [
                ("User", f"{self.target.mention} (`{self.target.id}`)", False),
                ("Entered Username", self.username, True),
                ("Roblox ID", str(self.roblox_id), True),
            ],
        )
        self.stop()


# ==============================================================
#                      WITHDRAW COMMAND
# ==============================================================

class WithdrawGemsModal(discord.ui.Modal, title="Gems Withdraw"):
    def __init__(self, user: discord.User):
        super().__init__(timeout=120)
        self.target = user

        self.roblox_username = discord.ui.TextInput(
            label="Roblox Username",
            placeholder="Your Roblox username",
            min_length=3,
            max_length=30
        )
        self.amount = discord.ui.TextInput(
            label="Amount (e.g. 100m, 250k)",
            placeholder="Only the amount, no 'all'",
        )
        self.add_item(self.roblox_username)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        username = str(self.roblox_username.value).strip()
        amount_str = str(self.amount.value).strip()

        # Check if user is changing username vs stored one (for DM to owner)
        existing = get_roblox_link_for(self.target.id)
        if existing:
            old_username = existing.get("username", "")
            if old_username and old_username.lower() != username.lower():
                await notify_owner(
                    "Roblox Username Changed (Withdraw)",
                    f"{self.target.mention} used a DIFFERENT Roblox username in withdraw.",
                    [
                        ("User", f"{self.target.mention} (`{self.target.id}`)", False),
                        ("Old Username", old_username, True),
                        ("New Username", username, True),
                    ],
                )

        # ALWAYS do lookup and avatar confirm (even if same username)
        rid, display_name, avatar_url = await roblox_lookup(username)
        if not rid:
            return await interaction.response.send_message(
                "❌ Could not find this Roblox username. Check spelling and try again.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="🔍 Roblox Account Check",
            description=(
                f"Is this your Roblox account for **GEMS withdraw**?\n\n"
                f"**Username:** `{display_name}`\n"
                f"**ID:** `{rid}`\n\n"
                f"If yes, this account will be linked to your Discord for gems withdraws/deposits."
            ),
            color=galaxy_color()
        )
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        view = RobloxConfirmView(
            user=self.target,
            username=username,
            roblox_id=rid,
            avatar_url=avatar_url,
            mode="withdraw_gems",
            amount_str=amount_str
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class WithdrawExpModal(discord.ui.Modal, title="EXP Withdraw"):
    def __init__(self, user: discord.User):
        super().__init__(timeout=120)
        self.target = user

        self.amount = discord.ui.TextInput(
            label="Amount (e.g. 100m, 250k)",
            placeholder="Only the amount, no 'all'",
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        amount_str = str(self.amount.value).strip()
        # No username needed here
        await finalize_withdraw(
            interaction=interaction,
            user=self.target,
            wtype="exp",
            amount_str=amount_str,
            roblox_username=None
        )


class WithdrawChoiceView(discord.ui.View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=60)
        self.target = user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "❌ This withdraw menu is not for you.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="💎 Gems Withdraw", style=discord.ButtonStyle.primary)
    async def gems_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WithdrawGemsModal(self.target))

    @discord.ui.button(label="⭐ EXP Withdraw", style=discord.ButtonStyle.secondary)
    async def exp_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WithdrawExpModal(self.target))


@bot.command()
async def withdraw(ctx):
    """
    Player command:
    !withdraw  -> opens panel with Gems / EXP withdraw (forms)
    """
    ensure_user(ctx.author.id)
    if _loan_is_restricted(ctx.author.id):
        embed = discord.Embed(
            title="🚫 Withdraw Locked — Active Debt",
            description=(
                "🌌 Your cosmic credit tether is active. Clear your loan with `!payback` "
                "before making withdrawals."
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text="Galaxy Treasury • Resolve debts to unlock the stars")
        return await ctx.send(embed=embed)

    embed = discord.Embed(
        title="🏦 Withdraw Panel",
        description=(
            "Choose what you want to withdraw:\n\n"
            "💎 **Gems** — 1.2x fee (20% penalty; remove 1.2x from your gems balance)\n"
            "⭐ **EXP** — 1.9x fee (remove 1.9x from your EXP balance)\n\n"
            "⚠ Only **one pending withdraw** at a time.\n"
            f"⚠ Max per 48h: **{fmt(WITHDRAW_GEMS_LIMIT_2D)} gems**, "
            f"**{fmt(WITHDRAW_EXP_LIMIT_2D)} EXP**.\n"
            "⚠ 30 minutes cooldown between withdraws."
        ),
        color=galaxy_color()
    )
    view = WithdrawChoiceView(ctx.author)
    await ctx.send(embed=embed, view=view)


# ==============================================================
#                      DEPOSIT COMMAND
# ==============================================================

class DepositGemsModal(discord.ui.Modal, title="Gems Deposit"):
    def __init__(self, user: discord.User):
        super().__init__(timeout=120)
        self.target = user

        self.roblox_username = discord.ui.TextInput(
            label="Roblox Username",
            placeholder="Your Roblox username",
            min_length=3,
            max_length=30
        )
        self.amount = discord.ui.TextInput(
            label="Amount (e.g. 100m, 250k)",
            placeholder="Only the amount, no 'all'",
        )
        self.add_item(self.roblox_username)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        username = str(self.roblox_username.value).strip()
        amount_str = str(self.amount.value).strip()

        # Check if user is changing username vs stored one (DM owner)
        existing = get_roblox_link_for(self.target.id)
        if existing:
            old_username = existing.get("username", "")
            if old_username and old_username.lower() != username.lower():
                await notify_owner(
                    "Roblox Username Changed (Deposit)",
                    f"{self.target.mention} used a DIFFERENT Roblox username in deposit.",
                    [
                        ("User", f"{self.target.mention} (`{self.target.id}`)", False),
                        ("Old Username", old_username, True),
                        ("New Username", username, True),
                    ],
                )

        # ALWAYS avatar lookup + confirm
        rid, display_name, avatar_url = await roblox_lookup(username)
        if not rid:
            return await interaction.response.send_message(
                "❌ Could not find this Roblox username. Check spelling and try again.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="🔍 Roblox Account Check",
            description=(
                f"Is this your Roblox account for **GEMS deposit**?\n\n"
                f"**Username:** `{display_name}`\n"
                f"**ID:** `{rid}`\n\n"
                f"If yes, this account will be linked to your Discord for gems operations."
            ),
            color=galaxy_color()
        )
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        view = RobloxConfirmView(
            user=self.target,
            username=username,
            roblox_id=rid,
            avatar_url=avatar_url,
            mode="deposit_gems",
            amount_str=amount_str
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class DepositExpModal(discord.ui.Modal, title="EXP Deposit"):
    def __init__(self, user: discord.User):
        super().__init__(timeout=120)
        self.target = user

        self.amount = discord.ui.TextInput(
            label="Amount (e.g. 100m, 250k)",
            placeholder="Only the amount, no 'all'",
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        amount_str = str(self.amount.value).strip()
        await finalize_deposit(
            interaction=interaction,
            user=self.target,
            dtype="exp",
            amount_str=amount_str,
            roblox_username=None   # admin will manage for EXP in panel
        )


class DepositChoiceView(discord.ui.View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=60)
        self.target = user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "❌ This deposit menu is not for you.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="💎 Gems Deposit", style=discord.ButtonStyle.primary)
    async def gems_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DepositGemsModal(self.target))

    @discord.ui.button(label="⭐ EXP Deposit", style=discord.ButtonStyle.secondary)
    async def exp_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DepositExpModal(self.target))


@bot.command()
async def deposit(ctx):
    """
    Player command:
    !deposit  -> opens panel with Gems / EXP deposit (forms)
    """
    ensure_user(ctx.author.id)
    if _loan_is_restricted(ctx.author.id):
        embed = discord.Embed(
            title="🚫 Deposits Locked — Active Debt",
            description=(
                "🌌 Your ledger is tethered by a loan. Clear it with `!payback` "
                "before depositing more riches."
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text="Galaxy Treasury • Settle debts to resume deposits")
        return await ctx.send(embed=embed)

    embed = discord.Embed(
        title="🏦 Deposit Panel",
        description=(
            "Create a **pending** deposit request:\n\n"
            "💎 **Gems** — Roblox username required (avatar check every time)\n"
            "⭐ **EXP** — No username here, staff uses panel side\n\n"
            "Deposits **do not change your balance automatically**.\n"
            "Staff accepts them in the admin panel and then adds the amount.\n\n"
            "EXP rewards mirror withdraw odds: **1.2× EXP** for Roblox deposits, **1.9× EXP** for others."
        ),
        color=galaxy_color()
    )
    view = DepositChoiceView(ctx.author)
    await ctx.send(embed=embed, view=view)


# ==============================================================
#                       LOAN SYSTEM
# ==============================================================

@bot.command()
async def loan(ctx, amount: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]
    limit = _loan_limit(u)
    if u.get("lifetime_wagered", 0) <= 0 or limit <= 0:
        return await ctx.send(embed=_loan_embed(
            "🚫 Loan Unavailable",
            "🌌 You need wagering history before the bureau opens your cosmic credit line.",
            discord.Color.red(),
        ))

    current = u.get("loan")
    if current and current.get("status") in {"active", "defaulted"}:
        return await ctx.send(embed=_loan_embed(
            "🚫 Existing Loan",
            "🌠 You already have a loan tethered. Use `!payback` to clear it first.",
            discord.Color.red(),
        ))

    val = parse_amount(amount, allow_all=False)
    if val is None or val <= 0:
        return await ctx.send("❌ Invalid amount.")

    val = int(val)
    if val > limit:
        return await ctx.send(embed=_loan_embed(
            "🚫 Above Limit",
            f"You can borrow up to **{fmt(limit)}** gems (10% of your lifetime wagers).",
            discord.Color.red(),
        ))

    now = time.time()
    payback = _loan_payback_amount(val)
    loan_data = {
        "amount": val,
        "payback_amount": payback,
        "taken_at": now,
        "due_at": now + LOAN_DURATION_SECONDS,
        "status": "active",
        "last_reminder": now,
    }

    _set_loan(ctx.author.id, loan_data)
    u["gems"] = u.get("gems", 0) + val
    save_data(data)

    grant_achievement(ctx.author.id, "first_loan")
    refresh_achievements(ctx.author.id)

    embed = discord.Embed(
        title="💠 Loan Approved",
        description=(
            f"🌌 You borrowed **{fmt(val)}** gems.\n"
            f"💎 Payback: **{fmt(payback)}** gems.\n"
            f"⏳ Due: <t:{int(loan_data['due_at'])}:R>\n"
            "Use `!payback` to clear your cosmic credit."
        ),
        color=galaxy_color(),
    )
    embed.set_footer(text="Galaxy Credit Bureau • 72h repayment window")
    await ctx.send(embed=embed)


@bot.command()
async def payback(ctx, member: discord.Member = None):
    target = member or ctx.author
    is_admin = ctx.guild and ctx.author.guild_permissions.manage_guild

    if member and not is_admin:
        return await ctx.send(embed=_loan_embed(
            "🚫 Admin Only",
            "🌠 Only admins can repay loans for other users.",
            discord.Color.red(),
        ))

    ensure_user(target.id)
    u = data[str(target.id)]
    loan = u.get("loan")

    if not loan or loan.get("status") not in {"active", "defaulted"}:
        return await ctx.send(embed=_loan_embed(
            "🚫 No Outstanding Loan",
            "🌟 This account is already debt-free among the stars!",
            discord.Color.green(),
        ))

    needed = int(loan.get("payback_amount", 0))
    if u.get("gems", 0) < needed:
        return await ctx.send(embed=_loan_embed(
            "❌ Not Enough Gems",
            f"<@{target.id}> needs **{fmt(needed)}** gems to repay. Keep grinding, star voyager!",
            discord.Color.red(),
        ))

    u["gems"] -= needed
    loan["status"] = "paid"
    loan["paid_at"] = time.time()
    save_data(data)

    add_history(target.id, {
        "game": "loan_payback",
        "bet": needed,
        "result": "paid",
        "earned": -needed,
        "timestamp": time.time(),
    })

    refresh_achievements(str(target.id))

    description = (
        f"💎 Paid **{fmt(needed)}** gems from <@{target.id}>'s balance.\n"
        "🌠 The cosmic credit tether is released."
    )
    if member and ctx.author.id != target.id:
        description = (
            f"💎 Paid **{fmt(needed)}** gems from <@{target.id}>'s balance.\n"
            f"🤝 Repayment processed by {ctx.author.mention}.\n"
            "🌠 The cosmic credit tether is released."
        )

    embed = discord.Embed(
        title="✅ Loan Cleared",
        description=description,
        color=discord.Color.green(),
    )
    embed.set_footer(text="Galaxy Credit Bureau • Debt-free horizon")
    await ctx.send(embed=embed)


@bot.command(aliases=["ach"], name="achievements")
async def achievements_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    ensure_user(target.id)
    refresh_achievements(target.id)
    ach = achievement_record(target.id)

    lines = []
    for key, meta in ACHIEVEMENT_DEFS.items():
        unlocked = ach.get(key, False)
        status_emoji = "✅" if unlocked else "🔒"
        lines.append(
            f"{meta['emoji']} {status_emoji} **{meta['name']}** — "
            f"{meta['desc']}"
        )

    embed = discord.Embed(
        title=f"🏆 Cosmic Achievements — {target.display_name}",
        description="\n".join(lines),
        color=galaxy_color(),
    )
    embed.set_footer(text="Galaxy Milestones • 🌌 Track your legend")
    await ctx.send(embed=embed)
# ==============================================================
#               ADMIN WITHDRAW PANEL (!withdrawpanel)
# ==============================================================

class WithdrawAdminView(discord.ui.View):
    def __init__(self, ctx: commands.Context, entries: list[dict]):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.entries = entries
        self.index = 0

    def current(self):
        if not self.entries:
            return None
        if self.index < 0:
            self.index = 0
        if self.index >= len(self.entries):
            self.index = len(self.entries) - 1
        return self.entries[self.index]

    def make_embed(self):
        cur = self.current()
        if not cur:
            return discord.Embed(
                title="🏦 Withdraw Queue",
                description="No pending withdraws.",
                color=galaxy_color()
            )

        user_id = cur["user_id"]

        e = discord.Embed(
            title=f"🏦 Withdraw #{cur['id']} — {cur['type'].upper()}",
            color=galaxy_color()
        )
        e.add_field(name="User", value=f"<@{user_id}> (`{user_id}`)", inline=False)
        e.add_field(name="Type", value=cur["type"], inline=True)
        e.add_field(name="Requested", value=fmt(cur["amount"]), inline=True)
        e.add_field(name="Deducted", value=fmt(cur["deducted"]), inline=True)
        e.add_field(name="Roblox Username", value=cur.get("roblox_username") or "None (EXP?)", inline=False)
        ts = datetime.utcfromtimestamp(cur["created_at"]).strftime("%Y-%m-%d %H:%M:%S UTC")
        e.add_field(name="Created", value=ts, inline=False)
        e.set_footer(text=f"Entry {self.index+1} / {len(self.entries)} — use buttons below.")
        return e

    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def on_timeout(self):
        for b in self.children:
            b.disabled = True

    @discord.ui.button(label="⬅ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        if not self.entries:
            return await interaction.response.send_message("No entries.", ephemeral=True)
        self.index = max(0, self.index - 1)
        await self.refresh(interaction)

    @discord.ui.button(label="Next ➡", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        if not self.entries:
            return await interaction.response.send_message("No entries.", ephemeral=True)
        self.index = min(len(self.entries) - 1, self.index + 1)
        await self.refresh(interaction)

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        cur = self.current()
        if not cur:
            return await interaction.response.send_message("No entry.", ephemeral=True)
        if cur["status"] != "pending":
            return await interaction.response.send_message("Already handled.", ephemeral=True)

        cur["status"] = "accepted"
        save_data(data)

        await interaction.response.send_message(
            f"✅ Withdraw **#{cur['id']}** marked as **ACCEPTED**.\n"
            f"Remember: payout is manual (Roblox / external).",
            ephemeral=True
        )

        await notify_owner(
            "Withdraw ACCEPTED",
            f"Admin {interaction.user.mention} accepted withdraw #{cur['id']}.",
            [
                ("User", f"<@{cur['user_id']}> (`{cur['user_id']}`)", False),
                ("Type", cur["type"], True),
                ("Requested", fmt(cur["amount"]), True),
                ("Deducted", fmt(cur["deducted"]), True),
                ("Roblox Username", cur.get("roblox_username") or "None", False),
            ],
        )

    @discord.ui.button(label="❌ Deny + Refund", style=discord.ButtonStyle.danger)
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        cur = self.current()
        if not cur:
            return await interaction.response.send_message("No entry.", ephemeral=True)
        if cur["status"] != "pending":
            return await interaction.response.send_message("Already handled.", ephemeral=True)

        # Refund deducted amount
        uid = str(cur["user_id"])
        ensure_user(uid)
        u = data[uid]
        if cur["type"] == "gems":
            u["gems"] = float(u.get("gems", 0)) + cur["deducted"]
        else:
            u["exp"] = float(u.get("exp", 0)) + cur["deducted"]
        save_data(data)

        cur["status"] = "denied"
        save_data(data)

        await interaction.response.send_message(
            f"❌ Withdraw **#{cur['id']}** denied. "
            f"Refunded **{fmt(cur['deducted'])} {cur['type']}** to user.",
            ephemeral=True
        )

        await notify_owner(
            "Withdraw DENIED",
            f"Admin {interaction.user.mention} denied withdraw #{cur['id']} and refunded.",
            [
                ("User", f"<@{cur['user_id']}> (`{cur['user_id']}`)", False),
                ("Type", cur["type"], True),
                ("Requested", fmt(cur["amount"]), True),
                ("Refunded", fmt(cur["deducted"]), True),
            ],
        )

    @discord.ui.button(label="🛑 Close", style=discord.ButtonStyle.secondary)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def withdrawpanel(ctx):
    """
    Admin command:
    !withdrawpanel  -> open admin viewer for pending withdraws
    """
    pending = [w for w in data.get("withdrawals", []) if w.get("status") == "pending"]
    if not pending:
        return await ctx.send("✅ No pending withdraws.")

    view = WithdrawAdminView(ctx, pending)
    await ctx.send(embed=view.make_embed(), view=view)


# ==============================================================
#               ADMIN DEPOSIT PANEL (!depositpanel)
# ==============================================================

class DepositAdminView(discord.ui.View):
    def __init__(self, ctx: commands.Context, entries: list[dict]):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.entries = entries
        self.index = 0

    def current(self):
        if not self.entries:
            return None
        if self.index < 0:
            self.index = 0
        if self.index >= len(self.entries):
            self.index = len(self.entries) - 1
        return self.entries[self.index]

    def make_embed(self):
        cur = self.current()
        if not cur:
            return discord.Embed(
                title="🏦 Deposit Queue",
                description="No pending deposits.",
                color=galaxy_color()
            )

        user_id = cur["user_id"]

        e = discord.Embed(
            title=f"🏦 Deposit #{cur['id']} — {cur['type'].upper()}",
            color=galaxy_color()
        )
        e.add_field(name="User", value=f"<@{user_id}> (`{user_id}`)", inline=False)
        e.add_field(name="Type", value=cur["type"], inline=True)
        e.add_field(name="Amount", value=fmt(cur["amount"]), inline=True)
        e.add_field(name="Roblox Username", value=cur.get("roblox_username") or "None (EXP / not provided)", inline=False)
        ts = datetime.utcfromtimestamp(cur["created_at"]).strftime("%Y-%m-%d %H:%M:%S UTC")
        e.add_field(name="Created", value=ts, inline=False)
        e.set_footer(text=f"Entry {self.index+1} / {len(self.entries)} — use buttons below.")
        return e

    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def on_timeout(self):
        for b in self.children:
            b.disabled = True

    @discord.ui.button(label="⬅ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        if not self.entries:
            return await interaction.response.send_message("No entries.", ephemeral=True)
        self.index = max(0, self.index - 1)
        await self.refresh(interaction)

    @discord.ui.button(label="Next ➡", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        if not self.entries:
            return await interaction.response.send_message("No entries.", ephemeral=True)
        self.index = min(len(self.entries) - 1, self.index + 1)
        await self.refresh(interaction)

    @discord.ui.button(label="✅ Accept + Add Balance", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        cur = self.current()
        if not cur:
            return await interaction.response.send_message("No entry.", ephemeral=True)
        if cur["status"] != "pending":
            return await interaction.response.send_message("Already handled.", ephemeral=True)

        uid = str(cur["user_id"])
        ensure_user(uid)
        u = data[uid]

        exp_multiplier = (
            DEPOSIT_EXP_MULT_ROBLOX
            if cur["type"] == "gems"
            else DEPOSIT_EXP_MULT_OTHER
        )
        exp_award = int(cur["amount"] * exp_multiplier)

        if cur["type"] == "gems":
            u["gems"] = float(u.get("gems", 0)) + cur["amount"]

        u["exp"] = float(u.get("exp", 0)) + exp_award
        save_data(data)

        cur["status"] = "accepted"
        save_data(data)

        await interaction.response.send_message(
            f"✅ Deposit **#{cur['id']}** accepted.\n"
            f"Added **{fmt(cur['amount'])} {cur['type']}** to user balance.\n"
            f"Awarded **{fmt(exp_award)} EXP** using synced deposit odds.",
            ephemeral=True
        )

        await notify_owner(
            "Deposit ACCEPTED",
            f"Admin {interaction.user.mention} accepted deposit #{cur['id']}.",
            [
                ("User", f"<@{cur['user_id']}> (`{cur['user_id']}`)", False),
                ("Type", cur["type"], True),
                ("Amount", fmt(cur["amount"]), True),
                ("EXP Awarded", fmt(exp_award), True),
            ],
        )

    @discord.ui.button(label="❌ Deny (no balance change)", style=discord.ButtonStyle.danger)
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        cur = self.current()
        if not cur:
            return await interaction.response.send_message("No entry.", ephemeral=True)
        if cur["status"] != "pending":
            return await interaction.response.send_message("Already handled.", ephemeral=True)

        cur["status"] = "denied"
        save_data(data)

        await interaction.response.send_message(
            f"❌ Deposit **#{cur['id']}** denied. No balance change.",
            ephemeral=True
        )

        await notify_owner(
            "Deposit DENIED",
            f"Admin {interaction.user.mention} denied deposit #{cur['id']}.",
            [
                ("User", f"<@{cur['user_id']}> (`{cur['user_id']}`)", False),
                ("Type", cur["type"], True),
                ("Amount", fmt(cur["amount"]), True),
            ],
        )

    @discord.ui.button(label="🛑 Close", style=discord.ButtonStyle.secondary)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Only the panel opener can use this.", ephemeral=True)
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def depositpanel(ctx):
    """
    Admin command:
    !depositpanel  -> open admin viewer for pending deposits
    """
    pending = [d for d in data.get("deposits", []) if d.get("status") == "pending"]
    if not pending:
        return await ctx.send("✅ No pending deposits.")

    view = DepositAdminView(ctx, pending)
    await ctx.send(embed=view.make_embed(), view=view)









# ==============================================================
#                     DAILY QUEST SYSTEM
# ==============================================================

QUEST_RESET_INTERVAL = 24 * 60 * 60  # 24 hours


# --------------------------------------------------------------
#      Get/Create Quest Data for a User
# --------------------------------------------------------------
def get_user_quests(uid):
    q = data["quests"].get(uid)
    if not q:
        q = {
            "earn": 0,
            "earn_goal": 50_000_000,

            "deposit": 0,
            "deposit_goal": 50_000_000,

            "wager": 0,
            "wager_goal": 100_000_000,

            "completed": False
        }
        data["quests"][uid] = q
        save_data(data)
    return q


# --------------------------------------------------------------
#                      Quest Reset
# --------------------------------------------------------------
def reset_quests():
    data["quests"] = {}
    data["quest_last_reset"] = time.time()
    save_data(data)

def check_daily_reset():
    last = data.get("quest_last_reset", 0)
    if time.time() - last >= QUEST_RESET_INTERVAL:
        reset_quests()


# --------------------------------------------------------------
#                  Quest Progress Adders
# --------------------------------------------------------------
def _quest_add_earn(uid, amount):
    check_daily_reset()
    q = get_user_quests(uid)
    q["earn"] += amount
    save_data(data)

def _quest_add_deposit(uid, amount):
    check_daily_reset()
    q = get_user_quests(uid)
    q["deposit"] += amount
    save_data(data)

def _quest_add_wager(uid, amount):
    check_daily_reset()
    q = get_user_quests(uid)
    q["wager"] += amount
    save_data(data)


 # --------------------------------------------------------------
#                       !quest COMMAND
# --------------------------------------------------------------
@bot.command()
async def quest(ctx):

    check_daily_reset()
    uid = str(ctx.author.id)
    q = get_user_quests(uid)

    def bar(current, goal):
        percent = min(100, int((current / goal) * 100))
        filled = int(percent / 10)
        return f"[{'█' * filled}{'░' * (10 - filled)}] {percent}%"

    embed = discord.Embed(
        title="📘 Daily Quests",
        description="Complete all tasks for **100m gems + 10% deposit bonus**",
        color=galaxy_color()
    )

    embed.add_field(
        name="💵 Earn 50m Gems",
        value=bar(q["earn"], q["earn_goal"]),
        inline=False
    )

    embed.add_field(
        name="🏦 Deposit 50m Gems",
        value=bar(q["deposit"], q["deposit_goal"]),
        inline=False
    )

    embed.add_field(
        name="🎲 Wager 100m Gems",
        value=bar(q["wager"], q["wager_goal"]),
        inline=False
    )

    # Completion status
    if (
        q["earn"] >= q["earn_goal"] and
        q["deposit"] >= q["deposit_goal"] and
        q["wager"] >= q["wager_goal"]
    ):
        if not q["completed"]:
            embed.add_field(
                name="🎉 Reward Ready!",
                value="Use **!questclaim** to collect.",
                inline=False
            )
        else:
            embed.add_field(
                name="✔ Already Claimed Today",
                value="Come back tomorrow.",
                inline=False
            )

    await ctx.send(embed=embed)


# --------------------------------------------------------------
#                    !questclaim COMMAND
# --------------------------------------------------------------
@bot.command()
async def questclaim(ctx):

    check_daily_reset()
    uid = str(ctx.author.id)
    q = get_user_quests(uid)

    # Already claimed
    if q["completed"]:
        return await ctx.send("❌ You already claimed your reward today.")

    # Not completed
    if (
        q["earn"] < q["earn_goal"] or
        q["deposit"] < q["deposit_goal"] or
        q["wager"] < q["wager_goal"]
    ):
        return await ctx.send("❌ You haven't completed all quests yet.")

    # Reward
    ensure_user(uid)
    data[uid]["gems"] += 100_000_000

    # Count quest reward as free income
    data[uid]["free_income"] = data[uid].get("free_income", 0) + 100_000_000

    # Deposit bonus +10%
    data["deposit_bonuses"][uid] = data["deposit_bonuses"].get(uid, 0) + 10

    q["completed"] = True
    save_data(data)

    await ctx.send("🎉 You claimed **100m gems + 10% deposit bonus**! Nice work!")








# ==============================================================
#                  WHEEL + ADMINWHEEL SYSTEM (UI)
# ==============================================================

WHEEL_COOLDOWN = 24 * 60 * 60   # 24 hours

# Visible prizes (0% still show in UI, but never picked)
WHEEL_PRIZES = [
    {"name": "5m Gems", "type": "gems", "amount": 5_000_000, "weight": 10},
    {"name": "10m Gems", "type": "gems", "amount": 10_000_000, "weight": 10},
    {"name": "10% Deposit Bonus", "type": "bonus", "bonus": 10, "weight": 10},
    {"name": "25% Deposit Bonus", "type": "bonus", "bonus": 25, "weight": 25},
    {"name": "100m Gems", "type": "gems", "amount": 100_000_000, "weight": 4},
    {"name": "200m Gems", "type": "gems", "amount": 200_000_000, "weight": 1},

    # 0% chance but still shown in list
    {"name": "1b Gems", "type": "gems", "amount": 1_000_000_000, "weight": 0},
    {"name": "3b Gems", "type": "gems", "amount": 3_000_000_000, "weight": 0},
    {"name": "5b Gems", "type": "gems", "amount": 5_000_000_000, "weight": 0},
    {"name": "251.2m/s Tang Tang Keletang", "type": "gems", "amount": 251_200_000, "weight": 0},
]


# --------------------------------------------------------------
#   PICK PRIZE (weights; 0% entries are ignored here)
# --------------------------------------------------------------
def pick_prize():
    total = sum(p["weight"] for p in WHEEL_PRIZES)
    r = random.uniform(0, total)
    upto = 0

    for p in WHEEL_PRIZES:
        w = p["weight"]
        if w <= 0:
            continue
        if upto + w >= r:
            return p
        upto += w

    return WHEEL_PRIZES[0]


# --------------------------------------------------------------
#   BUILD SPIN SEQUENCE (arrow goes through all, slows & lands)
# --------------------------------------------------------------
def build_spin_sequence(prize_index: int, num_slots: int) -> list[int]:
    """
    Returns a list of indices that the arrow will move through.
    It will end exactly on prize_index, but pass over 0% rewards too.
    """
    # total steps: 2-4 full rounds + a few extra
    min_rounds = 2
    max_rounds = 4
    total_steps = random.randint(min_rounds * num_slots + 3,
                                 max_rounds * num_slots + 6)

    # choose start index so that last step lands on prize_index
    start = (prize_index - (total_steps - 1)) % num_slots

    seq = []
    idx = start
    for _ in range(total_steps):
        seq.append(idx)
        idx = (idx + 1) % num_slots
    return seq


# --------------------------------------------------------------
#                           !wheel
# --------------------------------------------------------------
@bot.command()
async def wheel(ctx):
    """
    Daily wheel:
    - 1 spin / 24h
    - Extra spins (no cooldown) from !adminwheel
    - Animated arrow in embed
    """

    uid = str(ctx.author.id)
    ensure_user(uid)

    # ---------------------------
    # SAFETY: Ensure structures exist
    # ---------------------------
    if "wheel_extra_spins" not in data or not isinstance(data["wheel_extra_spins"], dict):
        data["wheel_extra_spins"] = {}

    if "wheel_last_spin" not in data or not isinstance(data["wheel_last_spin"], dict):
        data["wheel_last_spin"] = {}

    # --------------------------------------------------
    # EXTRA SPINS (no cooldown)
    # --------------------------------------------------
    extra_spins = data["wheel_extra_spins"].get(uid, 0)
    bypass_cooldown = False

    if extra_spins > 0:
        data["wheel_extra_spins"][uid] = extra_spins - 1
        save_data(data)
        bypass_cooldown = True

    # --------------------------------------------------
    # NORMAL COOLDOWN (24h)
    # --------------------------------------------------
    now = time.time()
    last = data["wheel_last_spin"].get(uid, 0)

    if not bypass_cooldown:
        if now - last < WHEEL_COOLDOWN:
            rem = int(WHEEL_COOLDOWN - (now - last))
            h, rem = divmod(rem, 3600)
            m, s = divmod(rem, 60)
            return await ctx.send(
                f"⏳ You already used **!wheel**.\n"
                f"Next spin in **{h}h {m}m {s}s**."
            )

        data["wheel_last_spin"][uid] = now
        save_data(data)

    # --------------------------------------------------
    # SPIN ANIMATION SETUP
    # --------------------------------------------------
    names = [p["name"] for p in WHEEL_PRIZES]

    # choose prize via weight
    prize_obj = pick_prize()
    prize_index = WHEEL_PRIZES.index(prize_obj)

    # arrow movement sequence
    sequence = build_spin_sequence(prize_index, len(names))

    # initial embed
    embed = discord.Embed(
        title="🎡 Galaxy Wheel",
        description="Spinning...",
        color=galaxy_color()
    )
    msg = await ctx.send(embed=embed)

    # --------------------------------------------------
    # ANIMATION LOOP
    # --------------------------------------------------
    for step, idx in enumerate(sequence):
        lines = []
        for i, name in enumerate(names):
            prefix = "👉" if i == idx else "•"
            lines.append(f"{prefix} {name}")

        desc = (
            f"**Player:** {ctx.author.mention}\n"
            f"**Spin:** {'extra (no cooldown)' if bypass_cooldown else 'daily'}\n\n"
            "🎡 **Wheel is spinning...**\n\n" +
            "\n".join(lines)
        )

        anim_embed = discord.Embed(
            title="🎡 Galaxy Wheel",
            description=desc,
            color=galaxy_color()
        )
        await msg.edit(embed=anim_embed)

        # slowdown effect
        await asyncio.sleep(0.08 + step * 0.04)

    # --------------------------------------------------
    # APPLY PRIZE
    # --------------------------------------------------
    if prize_obj["type"] == "gems":
        data[uid]["gems"] = data[uid].get("gems", 0) + prize_obj["amount"]
        save_data(data)

        add_history(ctx.author.id, {
            "game": "wheel",
            "bet": 0,
            "result": prize_obj["name"],
            "earned": prize_obj["amount"],
            "timestamp": time.time()
        })

    elif prize_obj["type"] == "bonus":
        if "deposit_bonuses" not in data:
            data["deposit_bonuses"] = {}

        bonus_map = data["deposit_bonuses"]
        bonus_map[uid] = bonus_map.get(uid, 0) + prize_obj["bonus"]
        save_data(data)

        add_history(ctx.author.id, {
            "game": "wheel",
            "bet": 0,
            "result": f"deposit_bonus_{prize_obj['bonus']}%",
            "earned": 0,
            "timestamp": time.time()
        })

    # --------------------------------------------------
    # FINAL RESULT EMBED
    # --------------------------------------------------
    lines_final = [f"• {n}" for n in names]
    final_desc = (
        f"**Player:** {ctx.author.mention}\n\n"
        f"🎁 **Result:** **{prize_obj['name']}**\n\n"
        "**Visible rewards:**\n" +
        "\n".join(lines_final)
    )

    result_embed = discord.Embed(
        title="🎡 Wheel Result",
        description=final_desc,
        color=galaxy_color()
    )

    await msg.edit(embed=result_embed)



# --------------------------------------------------------------
#                        !adminwheel
# --------------------------------------------------------------
@bot.command(name="adminwheel")
@commands.has_guild_permissions(manage_guild=True)
async def adminwheel(ctx, target: str, spins: int):
    """
    Give extra wheel spins (ignore cooldown)
    Usage:
      !adminwheel @user 3
      !adminwheel everyone 2
    """

    # -------------------------
    # SAFETY: ensure structure
    # -------------------------
    if "wheel_extra_spins" not in data or not isinstance(data["wheel_extra_spins"], dict):
        data["wheel_extra_spins"] = {}

    if spins <= 0:
        return await ctx.send("❌ Spins must be a positive number.")

    # -------------------------
    # GIVE TO EVERYONE
    # -------------------------
    if target.lower() == "everyone":
        count = 0
        for member in ctx.guild.members:
            if member.bot:
                continue
            uid = str(member.id)
            ensure_user(uid)

            data["wheel_extra_spins"][uid] = data["wheel_extra_spins"].get(uid, 0) + spins
            count += 1

        save_data(data)
        return await ctx.send(
            f"🌍 Gave **{spins} extra spins** to **{count} users**."
        )

    # -------------------------
    # GIVE TO ONE USER (mention)
    # -------------------------
    if not ctx.message.mentions:
        return await ctx.send("❌ Mention a user or use `everyone`.")

    user = ctx.message.mentions[0]
    uid = str(user.id)
    ensure_user(uid)

    data["wheel_extra_spins"][uid] = data["wheel_extra_spins"].get(uid, 0) + spins
    save_data(data)

    await ctx.send(
        f"🎡 Gave **{spins} extra spins** to {user.mention}."
    )







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
#                      !loanhelp
# --------------------------------------------------------------



@bot.command()
async def loanhelp(ctx):
    """Explain loan defaults and consequences."""
    embed = discord.Embed(
        title="📘 Loan Help",
        description=(
            "Here is what happens if you don't clear your loan in 72 hours (3 days):\n\n"
            "⏳ After 72h, your loan automatically **defaults**.\n"
            "🔒 While active or defaulted: no new loans, withdrawals, or deposits.\n"
            "📢 Staff is alerted when a default occurs for manual follow-up.\n\n"
            "Repayment required: **1.5×** of the borrowed amount.\n"
            "Clear the debt anytime with `!payback` to regain full access."
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(text="Galaxy Credit Bureau • Stay current to keep playing")
    await ctx.send(embed=embed)





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
#                      ADMIN CODE SYSTEM
# --------------------------------------------------------------
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def code(ctx, code_name: str, max_claims: str, reward_amount: str):
    code_name = code_name.strip()
    if not code_name:
        return await ctx.send("❌ Code name cannot be empty.")

    claims_value = parse_amount(max_claims)
    if claims_value is None or claims_value <= 0 or not float(claims_value).is_integer():
        return await ctx.send("❌ Usage amount must be a positive whole number.")

    reward_value = parse_amount(reward_amount)
    if reward_value is None or reward_value <= 0:
        return await ctx.send("❌ Reward amount must be a positive number.")

    normalized = normalize_code_name(code_name)
    data.setdefault("codes", {})[normalized] = {
        "name": code_name,
        "max_claims": int(claims_value),
        "current_claims": 0,
        "redeemed_users": [],
        "active": True,
        "reward": int(reward_value),
    }
    save_data(data)

    announcement = (
        "🎉 NEW CODE AVAILABLE 🎉\n"
        f"Code: {code_name}\n"
        f"Claims remaining: {int(claims_value)}\n"
        f"Reward: {fmt(int(reward_value))} gems"
    )
    await ctx.send(announcement)


@bot.command()
async def redeem(ctx, code_name: str):
    normalized = normalize_code_name(code_name)
    codes = data.get("codes", {})
    code_entry = codes.get(normalized)

    if not code_entry or not code_entry.get("active", True):
        return await ctx.send("❌ That code doesn't exist or is no longer active.")

    ensure_user(ctx.author.id)
    uid = str(ctx.author.id)
    u = data[uid]

    if (
        uid in code_entry.get("redeemed_users", [])
        or normalize_code_name(code_entry.get("name", "")) in
        {normalize_code_name(c) for c in u.get("redeemed_codes", [])}
    ):
        return await ctx.send("❌ You already redeemed this code.")

    remaining = code_entry.get("max_claims", 0) - code_entry.get("current_claims", 0)
    if remaining <= 0:
        code_entry["active"] = False
        save_data(data)
        return await ctx.send("❌ This code has expired.")

    reward_amount = int(code_entry.get("reward", CODE_REWARD_GEMS))
    u["gems"] = float(u.get("gems", 0)) + reward_amount
    code_entry["current_claims"] = code_entry.get("current_claims", 0) + 1
    code_entry.setdefault("redeemed_users", []).append(ctx.author.id)
    if code_entry.get("name") not in u.get("redeemed_codes", []):
        u.setdefault("redeemed_codes", []).append(code_entry.get("name"))

    if code_entry["current_claims"] >= code_entry.get("max_claims", 0):
        code_entry["active"] = False

    save_data(data)

    claims_left = max(0, code_entry.get("max_claims", 0) - code_entry.get("current_claims", 0))
    await ctx.send(
        f"✅ Code **{code_entry.get('name')}** redeemed!\n"
        f"You received **{fmt(reward_amount)}** gems.\n"
        f"Claims remaining: **{claims_left}**"
    )

    add_history(ctx.author.id, {
        "game": "code_redeem",
        "bet": 0,
        "result": code_entry.get("name", normalized),
        "earned": reward_amount,
        "timestamp": time.time(),
    })


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
@bot.command(aliases=["cf"])
async def coinflip(ctx, bet: str, choice: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]
    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if amount < MIN_GAMBLE_AMOUNT:
        return await ctx.send(
            f"❌ Minimum bet is **{fmt(MIN_GAMBLE_AMOUNT)}** gems."
        )
    if amount > MAX_BET:
        return await ctx.send(
            f"❌ Maximum bet is **{fmt(MAX_BET)}** gems."
        )
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
#                      CRASH (rig-aware)
# --------------------------------------------------------------
@bot.command()
async def crash(ctx, bet: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if amount < MIN_GAMBLE_AMOUNT:
        return await ctx.send(
            f"❌ Minimum bet is **{fmt(MIN_GAMBLE_AMOUNT)}** gems."
        )
    if amount > MAX_BET:
        return await ctx.send(
            f"❌ Maximum bet is **{fmt(MAX_BET)}** gems."
        )
    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)

    owner = ctx.author.id
    CRASH_STEPS = [
        {"mult": 0.2, "chance": 0},   # 0/4 clicks
        {"mult": 0.4, "chance": 5},   # 1/4 clicks
        {"mult": 0.8, "chance": 10},  # 2/4 clicks
        {"mult": 1.6, "chance": 45},  # 3/4 clicks
        {"mult": 2.4, "chance": 80},  # 4/4 clicks
    ]

    CLICK_LIMIT = len(CRASH_STEPS) - 1
    clicks = 0
    multiplier = CRASH_STEPS[clicks]["mult"]
    game_over = False

    def rigged_chance(base: float) -> float:
        if rig == "bless":
            return max(0.0, base * 0.5)
        if rig == "curse":
            return min(100.0, base * 2)
        return base

    def embed_update(status: str):
        # Crash chance is tied to the *next* click based on the table above.
        next_click_index = min(clicks + 1, CLICK_LIMIT)
        base_chance = CRASH_STEPS[next_click_index]["chance"]
        adjusted_chance = rigged_chance(base_chance)
        e = discord.Embed(
            title=f"🚀 Galaxy Crash | {ctx.author.name}",
            description=(
                f"💵 Bet: **{fmt(amount)}**\n"
                f"🧮 Multiplier: **{multiplier:.2f}x**\n"
                f"💥 Crash chance: **{adjusted_chance:.0f}%**\n"
                f"🔢 Clicks: **{clicks}/{CLICK_LIMIT}**\n"
                f"📌 Status: {status}"
            ),
            color=galaxy_color(),
        )
        if rig in ("bless", "curse"):
            e.set_footer(text=f"Rigged: {rig.title()} active — crash chance adjusted")
        else:
            e.set_footer(text="Galaxy Crash • Cash out before the galaxy collapses!")
        return e

    view = View(timeout=None)

    async def finalize_loss(interaction):
        nonlocal game_over
        game_over = True
        for child in view.children:
            child.disabled = True
        add_history(ctx.author.id, {
            "game": "crash",
            "bet": amount,
            "result": "crash",
            "earned": -amount,
            "timestamp": time.time(),
        })
        try:
            await interaction.response.edit_message(embed=embed_update("💥 Crashed! You lost."), view=view)
        except Exception:
            pass
        await ctx.send(f"☠️ The ship exploded! You lost **{fmt(amount)}** gems.")

    class Next(Button):
        def __init__(self):
            super().__init__(label="Next", style=discord.ButtonStyle.secondary)

        async def callback(self, interaction):
            nonlocal clicks, multiplier, game_over
            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game ended!", ephemeral=True)
            if clicks >= CLICK_LIMIT:
                return await interaction.response.send_message("❌ Click limit reached!", ephemeral=True)

            next_click = clicks + 1
            base_chance = CRASH_STEPS[next_click]["chance"]
            adjusted = rigged_chance(base_chance)
            roll = random.random() * 100
            if roll < adjusted:
                return await finalize_loss(interaction)

            clicks = next_click
            multiplier = CRASH_STEPS[clicks]["mult"]

            if clicks >= CLICK_LIMIT:
                self.disabled = True

            try:
                await interaction.response.edit_message(embed=embed_update("🟢 Safe... for now."), view=view)
            except Exception:
                pass

    class CashOut(Button):
        def __init__(self):
            super().__init__(label="Cash Out", style=discord.ButtonStyle.success)

        async def callback(self, interaction):
            nonlocal game_over
            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game ended!", ephemeral=True)

            game_over = True
            reward = int(amount * multiplier)
            profit = reward - amount
            u["gems"] += reward
            save_data(data)
            for child in view.children:
                child.disabled = True

            add_history(ctx.author.id, {
                "game": "crash",
                "bet": amount,
                "result": "cashout",
                "earned": profit,
                "timestamp": time.time(),
            })

            try:
                await interaction.response.edit_message(embed=embed_update("💰 Cashed out!"), view=view)
            except Exception:
                pass
            await ctx.send(f"💰 You cashed out at **{multiplier:.2f}x** for **{fmt(profit)}** gems!")

    view.add_item(Next())
    view.add_item(CashOut())

    await ctx.send(embed=embed_update("🟣 Active"), view=view)


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
    if amount < MIN_GAMBLE_AMOUNT:
        return await ctx.send(
            f"❌ Minimum bet is **{fmt(MIN_GAMBLE_AMOUNT)}** gems."
        )
    if amount > MAX_BET:
        return await ctx.send(
            f"❌ Maximum bet is **{fmt(MAX_BET)}** gems."
        )
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
    if amount < MIN_GAMBLE_AMOUNT:
        return await ctx.send(
            f"❌ Minimum bet is **{fmt(MIN_GAMBLE_AMOUNT)}** gems."
        )
    if amount > MAX_BET:
        return await ctx.send(
            f"❌ Maximum bet is **{fmt(MAX_BET)}** gems."
        )
    if amount > u["gems"]:
        return await ctx.send("❌ You don't have enough gems.")
    if not 1 <= mines <= 15:
        return await ctx.send("❌ Mines must be between **1 and 15**.")

    u["gems"] -= amount
    save_data(data)

    rig = consume_rig(u)  # 'bless', 'curse', or None
    owner = ctx.author.id

    TOTAL = 24
    ROW_SLOTS = 5
    SAFE_TILE_TARGET = TOTAL - mines

    revealed_safe = set()
    bomb_positions = set(random.sample(range(TOTAL), mines))
    exploded_index = None
    game_over = False
    reward_on_end = 0

    def calc_multiplier():
        return (1.025 + mines / 50) ** len(revealed_safe)

    def calc_reward():
        return amount * calc_multiplier()

    def finalize_board(explosion: int | None = None):
        nonlocal exploded_index
        exploded_index = explosion
        for i, btn in enumerate(view.children):
            if not isinstance(btn, Tile):
                continue
            btn.disabled = True
            if i in bomb_positions:
                btn.label = "💣"
                btn.style = discord.ButtonStyle.danger
            if explosion is not None and i == explosion:
                btn.label = "💥"
                btn.style = discord.ButtonStyle.danger

    def embed_update():
        reward_display = reward_on_end if game_over else calc_reward()
        e = discord.Embed(
            title=f"💣 Galaxy Mines | {ctx.author.name}",
            description=(
                f"💵 Bet: **{fmt(amount)}**\n"
                f"💰 Current: **{fmt(reward_display)}**\n"
                f"🔥 Multiplier: **{calc_multiplier():.2f}x**"
            ),
            color=galaxy_color(),
        )
        e.set_footer(text=f"Mines: {mines} • Safe tiles: {SAFE_TILE_TARGET}")
        return e

    view = View(timeout=None)

    async def handle_loss(interaction, reason: str, explosion_index: int):
        nonlocal game_over, reward_on_end
        game_over = True
        reward_on_end = 0

        # When cursed, ensure the exploded tile is counted as a bomb visually by
        # swapping it with an existing bomb instead of simply adding another.
        if explosion_index not in bomb_positions:
            replace = random.choice(list(bomb_positions)) if bomb_positions else None
            if replace is not None:
                bomb_positions.remove(replace)
                bomb_positions.add(explosion_index)

        finalize_board(explosion_index)
        add_history(ctx.author.id, {
            "game": "mines",
            "bet": amount,
            "result": reason,
            "earned": -amount,
            "timestamp": time.time()
        })
        try:
            await interaction.response.edit_message(embed=embed_update(), view=view)
        except Exception:
            pass
        await ctx.send(f"💥 A mine detonated! You lost **{fmt(amount)}** gems.")

    async def handle_win(interaction, reason: str):
        nonlocal game_over, reward_on_end
        game_over = True
        reward_on_end = calc_reward()
        u["gems"] += reward_on_end
        save_data(data)
        finalize_board(random.choice(list(bomb_positions)) if bomb_positions else None)
        add_history(ctx.author.id, {
            "game": "mines",
            "bet": amount,
            "result": reason,
            "earned": reward_on_end - amount,
            "timestamp": time.time(),
        })
        try:
            await interaction.response.edit_message(embed=embed_update(), view=view)
        except Exception:
            pass
        await ctx.send(f"🌠 You secured **{fmt(reward_on_end - amount)}** gems from the cosmic field!")

    class Tile(Button):
        def __init__(self, index):
            super().__init__(label=str(index + 1), style=discord.ButtonStyle.secondary, row=index // ROW_SLOTS)
            self.index = index

        async def callback(self, interaction):
            nonlocal game_over

            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended!", ephemeral=True)
            if self.index in revealed_safe:
                return await interaction.response.send_message("❌ Already clicked!", ephemeral=True)

            # CURSE: immediately explode the clicked tile
            if rig == "curse":
                return await handle_loss(interaction, "curse_explode", self.index)

            # BLESS: every tile is safe
            if rig == "bless":
                revealed_safe.add(self.index)
                self.label = "✅"
                self.style = discord.ButtonStyle.success
                if len(revealed_safe) >= SAFE_TILE_TARGET:
                    return await handle_win(interaction, "bless_clear")
                try:
                    await interaction.response.edit_message(embed=embed_update(), view=view)
                except Exception:
                    pass
                return

            # NORMAL flow
            if self.index in bomb_positions:
                return await handle_loss(interaction, "lose", self.index)

            revealed_safe.add(self.index)
            self.label = "✅"
            self.style = discord.ButtonStyle.success
            try:
                await interaction.response.edit_message(embed=embed_update(), view=view)
            except Exception:
                pass

    for i in range(TOTAL):
        view.add_item(Tile(i))

    class Cashout(Button):
        def __init__(self):
            super().__init__(label="💰 Cashout", style=discord.ButtonStyle.primary, row=4)

        async def callback(self, interaction):
            if interaction.user.id != owner:
                return await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            if game_over:
                return await interaction.response.send_message("❌ Game already ended!", ephemeral=True)

            if rig == "curse":
                explosion = random.choice(list(bomb_positions))
                return await handle_loss(interaction, "curse_cashout", explosion)

            # BLESS: allow instant profit without extra clicks
            if rig == "bless" and len(revealed_safe) == 0:
                revealed_safe.add(random.randrange(TOTAL))

            return await handle_win(interaction, "cashout")

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
    if amount < MIN_GAMBLE_AMOUNT:
        return await ctx.send(
            f"❌ Minimum bet is **{fmt(MIN_GAMBLE_AMOUNT)}** gems."
        )
    if amount > MAX_BET:
        return await ctx.send(
            f"❌ Maximum bet is **{fmt(MAX_BET)}** gems."
        )
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


@bot.command(aliases=["bj"])
async def blackjack(ctx, bet: str):
    ensure_user(ctx.author.id)
    u = data[str(ctx.author.id)]

    amount = parse_amount(bet, u["gems"], allow_all=True)
    if amount is None or amount <= 0:
        return await ctx.send("❌ Invalid bet.")
    if amount < MIN_GAMBLE_AMOUNT:
        return await ctx.send(
            f"❌ Minimum bet is **{fmt(MIN_GAMBLE_AMOUNT)}** gems."
        )
    if amount > MAX_BET:
        return await ctx.send(
            f"❌ Maximum bet is **{fmt(MAX_BET)}** gems."
        )
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
#                      MATCH (live football)
# --------------------------------------------------------------
@bot.command()
async def match(ctx):
    ensure_user(ctx.author.id)

    BETTING_WINDOW = 20
    MATCH_DURATION = 90

    team_colors = [
        ("🔴", "Red"), ("🔵", "Blue"), ("🟢", "Green"), ("🟡", "Yellow"),
        ("🟣", "Purple"), ("🟠", "Orange"), ("⚫", "Black"), ("⚪", "White"),
    ]
    (team_a, team_b) = random.sample(team_colors, 2)

    prob_a = random.uniform(0.01, 0.03)
    prob_b = random.uniform(0.01, 0.03)

    bets = {}  # {uid: {"choice": str, "amount": int}}
    scores = {"A": 0, "B": 0}
    bets_locked = False

    def total_pot():
        return sum(info["amount"] for info in bets.values())

    def match_status():
        return f"{team_a[0]} {team_a[1]} vs {team_b[0]} {team_b[1]}"

    def format_probs():
        return (
            f"{team_a[0]} {team_a[1]}: {prob_a * 100:.1f}% per second\n"
            f"{team_b[0]} {team_b[1]}: {prob_b * 100:.1f}% per second"
        )

    def format_bets():
        if not bets:
            return "No bets yet."
        return f"Bettors: **{len(bets)}** • Pot: **{fmt(total_pot())}**"

    def build_embed(status: str, remaining: int, locked: bool):
        embed = discord.Embed(
            title="⚽ Galaxy Match",
            description=status,
            color=galaxy_color(),
        )
        embed.add_field(name="Teams", value=match_status(), inline=False)
        embed.add_field(name="Goal Probabilities", value=format_probs(), inline=False)
        embed.add_field(name="Score", value=f"{scores['A']} – {scores['B']}", inline=True)
        embed.add_field(name="Time", value=f"{remaining}s remaining" if remaining >= 0 else "Full time", inline=True)
        embed.add_field(name="Bets", value=format_bets(), inline=False)
        lock_text = "Bets locked" if locked else "Betting open"
        embed.set_footer(
            text=f"{lock_text} • Min {fmt(MIN_GAMBLE_AMOUNT)} | Max {fmt(MAX_BET)}"
        )
        return embed

    async def update_message(msg: discord.Message, status: str, remaining: int, locked: bool, view):
        try:
            await msg.edit(embed=build_embed(status, remaining, locked), view=view)
        except Exception:
            pass

    class BetModal(Modal):
        def __init__(self, choice_key: str, label: str):
            super().__init__(title=f"Bet on {label}")
            self.choice_key = choice_key
            self.label = label
            self.amount = TextInput(label="Bet amount", placeholder="e.g. 5m", required=True)
            self.add_item(self.amount)

        async def on_submit(self, interaction: discord.Interaction):
            nonlocal bets_locked
            if bets_locked:
                return await interaction.response.send_message("❌ Bets are locked for this match.", ephemeral=True)

            ensure_user(interaction.user.id)
            uid = str(interaction.user.id)
            if uid in bets:
                return await interaction.response.send_message("❌ You already placed a bet for this match.", ephemeral=True)

            u = data[uid]
            amount = parse_amount(str(self.amount.value), u.get("gems", 0), allow_all=True)
            if amount is None or amount <= 0:
                return await interaction.response.send_message("❌ Invalid bet.", ephemeral=True)
            if amount < MIN_GAMBLE_AMOUNT:
                return await interaction.response.send_message(
                    f"❌ Minimum bet is **{fmt(MIN_GAMBLE_AMOUNT)}** gems.",
                    ephemeral=True
                )
            if amount > MAX_BET:
                return await interaction.response.send_message(
                    f"❌ Maximum bet is **{fmt(MAX_BET)}** gems.",
                    ephemeral=True
                )
            if amount > u.get("gems", 0):
                return await interaction.response.send_message("❌ You don't have enough gems.", ephemeral=True)

            u["gems"] -= amount
            save_data(data)

            bets[uid] = {"choice": self.choice_key, "amount": int(amount)}
            await interaction.response.send_message(
                f"✅ Bet confirmed: **{fmt(int(amount))}** on **{self.label}**.",
                ephemeral=True
            )

            await update_message(match_message, "⚽ Betting open — choose an outcome!", BETTING_WINDOW, False, bet_view)

    class BetButton(Button):
        def __init__(self, label: str, choice_key: str, style=discord.ButtonStyle.primary):
            super().__init__(label=label, style=style)
            self.choice_key = choice_key
            self.label_text = label

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.send_modal(BetModal(self.choice_key, self.label_text))

    bet_view = View(timeout=None)
    bet_view.add_item(BetButton(f"{team_a[0]} {team_a[1]} Win", "A", discord.ButtonStyle.danger))
    bet_view.add_item(BetButton(f"{team_b[0]} {team_b[1]} Win", "B", discord.ButtonStyle.primary))
    bet_view.add_item(BetButton("⚪ Draw", "D", discord.ButtonStyle.secondary))

    match_message = await ctx.send(embed=build_embed("⚽ Betting open — choose an outcome!", BETTING_WINDOW, False), view=bet_view)

    await asyncio.sleep(BETTING_WINDOW)
    bets_locked = True
    for child in bet_view.children:
        child.disabled = True
    await update_message(match_message, "🔒 Bets locked — match is starting!", MATCH_DURATION, True, bet_view)

    async def simulate_second(remaining: int):
        nonlocal prob_a, prob_b
        prob_a = random.uniform(0.01, 0.03)
        prob_b = random.uniform(0.01, 0.03)
        order = ["A", "B"]
        random.shuffle(order)
        for key in order:
            chance = prob_a if key == "A" else prob_b
            if random.random() < chance:
                scores[key] += 1
                await ctx.send(
                    f"⚽ GOOOOAL! {team_a[0] if key == 'A' else team_b[0]} "
                    f"{team_a[1] if key == 'A' else team_b[1]} Team scores! "
                    f"({scores['A']}–{scores['B']})"
                )
                await asyncio.sleep(random.uniform(1.0, 2.0))
                break

        await update_message(match_message, "🏃 Match in progress…", remaining, True, bet_view)

    for remaining in range(MATCH_DURATION, 0, -1):
        await simulate_second(remaining)
        await asyncio.sleep(1)

    result_label = "Draw"
    if scores["A"] > scores["B"]:
        result_label = f"{team_a[0]} {team_a[1]} Win"
        winning_key = "A"
    elif scores["B"] > scores["A"]:
        result_label = f"{team_b[0]} {team_b[1]} Win"
        winning_key = "B"
    else:
        winning_key = "D"

    winners = []
    for uid, info in bets.items():
        ensure_user(uid)
        u = data[str(uid)]
        bet_amount = info["amount"]

        if info["choice"] == winning_key:
            reward = int(bet_amount * 2.5)
            profit = reward - bet_amount
            u["gems"] += reward
            outcome = f"WIN +{fmt(profit)}"
        else:
            profit = -bet_amount
            outcome = f"LOSS -{fmt(bet_amount)}"

        add_history(uid, {
            "game": "match",
            "bet": bet_amount,
            "result": result_label,
            "earned": profit,
            "timestamp": time.time()
        })

        if profit > 0:
            winners.append(f"<@{uid}> — {fmt(profit)}")

    save_data(data)

    summary_lines = [
        f"Result: **{result_label}**",
        f"Final Score: **{scores['A']} – {scores['B']}**",
        "Payout: **2.5x** for correct predictions"
    ]
    if winners:
        summary_lines.append("Winners:\n" + "\n".join(winners))
    else:
        summary_lines.append("No winning bets this time.")

    await update_message(
        match_message,
        "🏁 Full time — match finished!",
        0,
        True,
        bet_view
    )
    await ctx.send("\n".join(summary_lines))


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
@bot.command(aliases=["lb"])
async def leaderboard(ctx, page: int | None = None):
    requested_page = 1 if page is None else page
    if requested_page < 1 or requested_page > 50:
        return await ctx.send("❌ Invalid page. Choose a page between **1** and **50**.")

    def build_leaderboard():
        entries = []
        for user_id, info in data.items():
            if not str(user_id).isdigit():
                continue
            holding = int(info.get("gems", 0))
            history = info.get("history", [])
            total_games = len(history)
            total_wagered = int(info.get("lifetime_wagered", 0))
            wins = sum(1 for e in history if (e.get("earned", 0) or 0) > 0)
            losses = sum(1 for e in history if (e.get("earned", 0) or 0) < 0)
            net = int(sum(int(e.get("earned", 0) or 0) for e in history))

            entries.append({
                "user_id": int(user_id),
                "holding": holding,
                "wagered": total_wagered,
                "wins": wins,
                "losses": losses,
                "net": net,
                "games": total_games
            })

        entries.sort(key=lambda x: x["holding"], reverse=True)
        return entries[:500]

    def make_entry_text(rank: int, name: str, entry: dict):
        net_prefix = "+" if entry["net"] >= 0 else ""
        return (
            f"#{rank} | {name}\n"
            f"Holding: {fmt(entry['holding'])}\n"
            f"Wagered: {fmt(entry['wagered'])}\n"
            f"Wins/Losses: {entry['wins']} / {entry['losses']}\n"
            f"Net P/L: {net_prefix}{fmt(entry['net'])}\n"
            f"Games Played: {entry['games']}"
        )

    async def build_embed(page_number: int):
        entries = build_leaderboard()
        total_pages = max(1, min(50, (len(entries) + 9) // 10))
        if page_number < 1 or page_number > total_pages:
            return None, total_pages

        start = (page_number - 1) * 10
        page_entries = entries[start:start + 10]
        lines = []
        for rank, entry in enumerate(page_entries, start=start + 1):
            try:
                user_obj = await bot.fetch_user(entry["user_id"])
                name = user_obj.name
            except Exception:
                name = f"User {entry['user_id']}"
            lines.append(make_entry_text(rank, name, entry))

        embed = discord.Embed(
            title="🏆 Galaxy Leaderboard",
            description="\n\n".join(lines) if lines else "No players found.",
            color=galaxy_color()
        )
        embed.set_footer(text=f"Page {page_number}/{total_pages} • Sorted by holding (top 500)")
        return embed, total_pages

    embed, total_pages = await build_embed(requested_page)
    if embed is None:
        return await ctx.send("❌ That page has no data yet.")

    class LBView(View):
        def __init__(self, current_page: int, max_pages: int):
            super().__init__(timeout=120)
            self.page = current_page
            self.max_pages = max_pages
            self.update_buttons()

        def update_buttons(self):
            for child in self.children:
                if child.custom_id == "prev":
                    child.disabled = self.page <= 1
                if child.custom_id == "next":
                    child.disabled = self.page >= self.max_pages or self.page >= 50

        async def change_page(self, interaction: discord.Interaction, delta: int):
            new_page = self.page + delta
            if new_page < 1 or new_page > 50:
                return await interaction.response.send_message(
                    "❌ Invalid page. Choose a page between **1** and **50**.",
                    ephemeral=True
                )

            new_embed, new_total = await build_embed(new_page)
            if new_embed is None:
                return await interaction.response.send_message(
                    "❌ That page has no data yet.", ephemeral=True
                )

            self.page = new_page
            self.max_pages = new_total
            self.update_buttons()
            await interaction.response.edit_message(embed=new_embed, view=self)

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="prev")
        async def previous(self, interaction: discord.Interaction, button):
            await self.change_page(interaction, -1)

        @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="next")
        async def next(self, interaction: discord.Interaction, button):
            await self.change_page(interaction, 1)

    view = LBView(requested_page, total_pages)
    await ctx.send(embed=embed, view=view)


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
              f"Games: coinflip, slots, mines, tower, blackjack, crash",
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

    try:
        apply_restored_data(new_data)
    except ValueError:
        return await ctx.send("❌ Backup file must be a JSON object at the root level.")

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

    try:
        apply_restored_data(new_data)
    except ValueError:
        return await ctx.send("❌ Backup file must be a JSON object at the root level.")

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
#                       HELP (PLAYER)
# ==============================================================
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="🌌 Galaxy Casino — Player Commands",
        description="Use `!command` to play.\nHere are your main commands:",
        color=galaxy_color()
    )

    # ---------------- Economy ----------------
    embed.add_field(
        name="💰 Economy",
        value=(
            "**!balance / !bal [@user]** — Check your gems/exp\n"
            "**!daily** — Claim daily 25m\n"
            "**!wheel** — Spin the daily wheel\n"
            "**!gift @user amount** — Gift gems\n"
            "**!sell <name> <income> <price>** — Create a listing\n"
            "**!loan <amount>** — Borrow up to 10% of lifetime wagers\n"
            "**!loanhelp** — What happens if you don't repay in 72h\n"
            "**!payback** — Repay your cosmic credit (1.5x payback)\n"
            "**!withdraw** — Start a withdraw request (form)\n"
            "**!deposit** — Start a deposit request (form; EXP: 1.2× Roblox / 1.9× others)\n"
            "**!redeem <code>** — Claim active reward codes"
        ),
        inline=False
    )

    # ---------------- Games ----------------
    embed.add_field(
        name="🎮 Games",
        value=(
            "**!coinflip/!cf amount heads/tails** — 50/50 game\n"
            "**!blackjack/!bj amount** — Blackjack game\n"
            "**!slots amount** — Slot machine\n"
            "**!mines amount [mines]** — Mines game\n"
            "**!tower amount** — 10-floor tower\n"
            "**!crash amount** — Crash game where multiplier and crash chance double every click. Cash out before the galaxy collapses.\n"
            "**!match** — 90-second live football match with Team A / Team B / Draw bets (2.5x payout on correct picks)\n"
            "Minimum bet: **1,000,000** gems • Maximum bet: **200,000,000** gems"
        ),
        inline=False
    )

    # ---------------- Progress ----------------
    embed.add_field(
        name="🏆 Progress",
        value=(
            "**!achievements [@user]** — View unlocked galaxy milestones"
        ),
        inline=False
    )

    # ---------------- Daily Quests ----------------
    embed.add_field(
        name="📘 Daily Quests",
        value=(
            "**!quest** — Check daily quest progress\n"
            "**!questclaim** — Claim quest reward (100m + 10% deposit bonus)"
        ),
        inline=False
    )

    # ---------------- Player Info ----------------
    embed.add_field(
        name="📊 Player Information",
        value=(
            "**!history** — Last 10 games\n"
            "**!stats** — Player stats\n"
            "**!leaderboard / !lb** — Top richest players\n"
            "**!membercount** — Server statistics"
        ),
        inline=False
    )

    # ---------------- Fun Events ----------------
    embed.add_field(
        name="🎟 Events",
        value=(
            "**!guessthecolor amount** — Guess the color\n"
            "**!guessthenumber amount** — Guess between 1–10\n"
            "**!splitorsteal amount** — PvP Split-or-Steal"
        ),
        inline=False
    )

    embed.set_footer(text="Galaxy Casino • Good luck 💎🌌")
    await ctx.send(embed=embed)



# ==============================================================
#                       HELP (ADMIN)
# ==============================================================
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def helpadmin(ctx):
    embed = discord.Embed(
        title="🛠 Galaxy Casino — Admin Commands",
        description="Full administrative command panel:",
        color=galaxy_color()
    )

    # ---------------- Currency Management ----------------
    embed.add_field(
        name="💰 Gem / EXP Management",
        value=(
            "**!admin give @user amount** — Add gems/exp manually\n"
            "**!admin remove @user amount** — Remove gems/exp (can go negative)\n"
            "**!giverole <role> amount** — Give gems to everyone with a role\n"
            "**!removerole <role> amount** — Remove gems from everyone with a role\n"
            "**!giveall amount** — Give gems to the entire server\n"
            "**!tax percent** — Tax all balances by %\n"
            "**!code \"<code_name>\" <usage_amount> <reward>** — Publish a redeemable code"
        ),
        inline=False
    )

    # ---------------- Withdraw & Deposit Panels ----------------
    embed.add_field(
        name="🏦 Withdraw & Deposit System",
        value=(
            "**!withdrawpanel** — Open withdraw admin panel (Accept / Deny)\n"
            "**!depositpanel** — Open deposit admin panel (Accept / Deny)\n\n"
            "✔ Withdraw auto-fees: **1.2× for gems**, **1.9× for EXP**\n"
            "✔ Deposit EXP awards: **1.2×** for Roblox deposits, **1.9×** for others\n"
            "✔ Gems withdraws require Roblox avatar confirmation\n"
            "✔ EXP withdraws do NOT require Roblox username\n"
            "✔ Owner receives DM for EVERY action\n"
            "✔ Users may only have ONE active request\n"
            "✔ 30-minute cooldown between withdraws\n"
            "✔ Max 500m per request, 750m every 2 days\n"
            "✔ Global bets: min **1,000,000** gems / max **200,000,000** gems"
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 Games & Leaderboard",
        value=(
            "Aliases: **!bj** (blackjack), **!cf** (coinflip), **!lb** (leaderboard)\n"
            "Leaderboard: sorted by holding, 50 pages, 10 users per page (top 500)\n"
            "Bet limits apply to: coinflip/!cf, blackjack/!bj, slots, mines, tower, crash, match\n"
            "**!match** — 90s live football sim with Team A / Team B / Draw bets, one bet per user, fixed **2.5x** payout on correct predictions"
        ),
        inline=False
    )

    # ---------------- Wheel System ----------------
    embed.add_field(
        name="🎡 Wheel System",
        value=(
            "**!wheel** — Daily spin (24h cooldown)\n"
            "Weighted rewards: 5m, 10m, 10% bonus, 25% bonus, 100m, 200m\n"
            "Jackpots shown visually but 0% chance"
        ),
        inline=False
    )

    # ---------------- Admin Wheel ----------------
    embed.add_field(
        name="🎡 Admin Wheel Controls",
        value=(
            "**!adminwheel @user <spins>** — Give extra wheel spins\n"
            "**!adminwheel everyone <spins>** — Give spins to all players\n\n"
            "Extra spins stored and consumed on next `!wheel` use."
        ),
        inline=False
    )

    # ---------------- Server Tools ----------------
    embed.add_field(
        name="🛡 Moderation & Tools",
        value=(
            "**!backup** — Force a JSON backup upload\n"
            "**!membercount** — Show server stats\n"
            "Automatic backups every 10 minutes."
        ),
        inline=False
    )

    embed.set_footer(text="Admins require 'Manage Server' permission.")
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
