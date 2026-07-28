import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing. Add it to the .env file."
    )

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

db = sqlite3.connect(BASE_DIR / "sprig.db")
cursor = db.cursor()

# --- Setup tables ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    points INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_completed TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS quests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    type TEXT,
    points INTEGER,
    assigned_to TEXT,
    completed INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS claims (
    quest_id INTEGER UNIQUE,
    user_id TEXT
)
""")

db.commit()

# --- Auto-fix schema ---
try:
    cursor.execute("ALTER TABLE quests ADD COLUMN completed INTEGER DEFAULT 0")
    db.commit()
except sqlite3.OperationalError:
    pass

# --- Cleanup old bad data (<@123> → 123) ---
cursor.execute("""
UPDATE quests
SET assigned_to = REPLACE(REPLACE(assigned_to, '<@', ''), '>', '')
WHERE assigned_to LIKE '<@%>'
""")
db.commit()

# --- Helper ---
def get_or_create_user(user_id):
    cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    db.commit()

# --- Commands ---

@bot.command()
async def addquest(
    ctx,
    name,
    qtype,
    points: int,
    assigned_to: discord.Member = None
):
    assigned_id = str(assigned_to.id) if assigned_to else None

    cursor.execute(
        """
        INSERT INTO quests (name, type, points, assigned_to)
        VALUES (?, ?, ?, ?)
        """,
        (name, qtype, points, assigned_id)
    )

    quest_id = cursor.lastrowid
    db.commit()

    display = assigned_to.display_name if assigned_to else "Open to all"

    await ctx.send(
        f"🌱 Added quest #{quest_id}: "
        f"{name} ({qtype}) → {display} +{points}"
    )

@bot.command()
async def claim(ctx, quest_id: int):
    user_id = str(ctx.author.id)

    cursor.execute(
        """
        SELECT id, name, type, completed
        FROM quests
        WHERE id = ?
        """,
        (quest_id,)
    )
    quest = cursor.fetchone()

    if not quest:
        await ctx.send(f"Sprig cannot find quest #{quest_id} 👀")
        return

    quest_id, name, qtype, completed = quest

    if completed:
        await ctx.send(f"Quest #{quest_id} is already completed! ✨")
        return

    if qtype != "open":
        await ctx.send(f"Quest #{quest_id} is not claimable!")
        return

    cursor.execute(
        "SELECT user_id FROM claims WHERE quest_id = ?",
        (quest_id,)
    )
    existing_claim = cursor.fetchone()

    if existing_claim:
        await ctx.send(f"🚫 Quest #{quest_id} has already been claimed!")
        return

    cursor.execute(
        """
        INSERT INTO claims (quest_id, user_id)
        VALUES (?, ?)
        """,
        (quest_id, user_id)
    )
    db.commit()

    await ctx.send(
        f"🎯 {ctx.author.display_name} claimed "
        f"quest #{quest_id}: **{name}**!"
    )

@bot.command()
async def done(ctx, quest_id: int):
    user_id = str(ctx.author.id)
    get_or_create_user(user_id)

    cursor.execute(
        """
        SELECT id, name, type, points, assigned_to, completed
        FROM quests
        WHERE id = ?
        """,
        (quest_id,)
    )
    quest = cursor.fetchone()

    if not quest:
        await ctx.send(f"Sprig cannot find quest #{quest_id} 👀")
        return

    quest_id, name, qtype, points_val, assigned_to, completed = quest

    if completed:
        await ctx.send(
            f"Quest #{quest_id} is already done for today! ✨"
        )
        return

    # Assigned quests can only be completed by the assigned person.
    if qtype == "assigned" and assigned_to:
        if assigned_to != user_id:
            await ctx.send(
                f"🚫 Quest #{quest_id} is assigned to someone else!"
            )
            return

    # Open quests must first be claimed by the person completing them.
    if qtype == "open":
        cursor.execute(
            "SELECT user_id FROM claims WHERE quest_id = ?",
            (quest_id,)
        )
        claim = cursor.fetchone()

        if not claim:
            await ctx.send(
                f"You must claim quest #{quest_id} first! 🎯"
            )
            return

        if claim[0] != user_id:
            await ctx.send(
                f"🚫 Someone else claimed quest #{quest_id}!"
            )
            return

    cursor.execute(
        """
        SELECT points, streak, last_completed
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    )
    user = cursor.fetchone()

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    current_points, current_streak, last_completed = user
    streak = 1

    if last_completed:
        last_date = datetime.strptime(
            last_completed,
            "%Y-%m-%d"
        ).date()

        if last_date == today:
            streak = current_streak
        elif last_date == yesterday:
            streak = current_streak + 1

    new_points = current_points + points_val

    cursor.execute(
        """
        UPDATE users
        SET points = ?, streak = ?, last_completed = ?
        WHERE id = ?
        """,
        (new_points, streak, str(today), user_id)
    )

    cursor.execute(
        "DELETE FROM claims WHERE quest_id = ?",
        (quest_id,)
    )

    cursor.execute(
        "UPDATE quests SET completed = 1 WHERE id = ?",
        (quest_id,)
    )

    db.commit()

    await ctx.send(
        f'✨ {ctx.author.display_name} completed '
        f'quest #{quest_id}: **{name}**!\n\n'
        f'+{points_val} points\n'
        f'🔥 Streak: {streak}\n'
        f'⭐ Total: {new_points}\n\n'
        f'Sprig is spinning in a tiny circle of celebration 💫'
    )

@bot.command()
async def quests(ctx):
    cursor.execute(
        """
        SELECT
            q.id,
            q.name,
            q.type,
            q.points,
            q.assigned_to,
            c.user_id
        FROM quests q
        LEFT JOIN claims c ON q.id = c.quest_id
        WHERE q.completed = 0
        ORDER BY q.id
        """
    )
    quest_rows = cursor.fetchall()

    if not quest_rows:
        await ctx.send(
            "Sprig checked the board… all quests are complete!! 🎉"
        )
        return

    id_w = 5
    name_w = 22
    type_w = 10
    points_w = 6
    status_w = 28

    header = (
        f"{'#':<{id_w}}"
        f"{'Quest':<{name_w}}"
        f"{'Type':<{type_w}}"
        f"{'Pts':<{points_w}}"
        f"{'Status':<{status_w}}"
    )

    divider = "-" * (
        id_w + name_w + type_w + points_w + status_w
    )

    rows = []

    for (
        quest_id,
        name,
        qtype,
        points,
        assigned_to,
        claimed_by
    ) in quest_rows:

        if qtype == "assigned" and assigned_to:
            status = f"assigned to {assigned_to}"
        elif claimed_by:
            status = f"claimed by {claimed_by}"
        else:
            status = "open"

        row = (
            f"{quest_id:<{id_w}}"
            f"{name[:name_w - 1]:<{name_w}}"
            f"{qtype:<{type_w}}"
            f"{points:<{points_w}}"
            f"{status[:status_w - 1]:<{status_w}}"
        )
        rows.append(row)

    table = "\n".join([header, divider] + rows)

    await ctx.send(
        "🌱 **Available quests**\n"
        f"```{table}```"
        "Use `!claim NUMBER` or `!done NUMBER`."
    )

@bot.command()
async def points(ctx):
    user_id = str(ctx.author.id)
    get_or_create_user(user_id)

    cursor.execute("SELECT points, streak FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    await ctx.send(f"⭐ Points: {user[0]} | 🔥 Streak: {user[1]}")

@bot.command()
async def leaderboard(ctx):
    cursor.execute("SELECT id, points FROM users ORDER BY points DESC LIMIT 5")
    users = cursor.fetchall()

    msg = "🏆 Leaderboard 🏆\n"
    for i, u in enumerate(users):
        msg += f"{i+1}. <@{u[0]}> — {u[1]} pts\n"

    await ctx.send(msg)
    
@claim.error
async def claim_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "Which quest? Use `!claim NUMBER`, such as `!claim 7`."
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "Quest numbers must be numbers. Try something like `!claim 7`."
        )
    else:
        raise error


@done.error
async def done_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "Which quest? Use `!done NUMBER`, such as `!done 7`."
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "Quest numbers must be numbers. Try something like `!done 7`."
        )
    else:
        raise error

@bot.command()
async def hello(ctx):
    await ctx.send("Sprig says hello!! ☁️✨")

@bot.event
async def on_ready():
    print(f"Sprig is alive as {bot.user} 🌱")

 
 
# --- Run ---
bot.run(DISCORD_TOKEN)
