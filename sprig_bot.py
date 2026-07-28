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
async def addquest(ctx, name, qtype, points: int, assigned_to: discord.Member = None):
    assigned_id = str(assigned_to.id) if assigned_to else None

    cursor.execute(
        "INSERT INTO quests (name, type, points, assigned_to) VALUES (?, ?, ?, ?)",
        (name, qtype, points, assigned_id)
    )
    db.commit()

    display = assigned_to.display_name if assigned_to else "Open to all"
    await ctx.send(f"🌱 Added: {name} ({qtype}) → {display} +{points}")

@bot.command()
async def claim(ctx, *, quest_name):
    user_id = str(ctx.author.id)

    cursor.execute("SELECT id, name, type, completed FROM quests WHERE name = ?", (quest_name,))
    quest = cursor.fetchone()

    if not quest:
        await ctx.send("Sprig cannot find that quest 👀")
        return

    quest_id, name, qtype, completed = quest

    if completed:
        await ctx.send("That quest is already completed! ✨")
        return

    if qtype != "open":
        await ctx.send("That quest is not claimable!")
        return

    cursor.execute("SELECT * FROM claims WHERE quest_id = ?", (quest_id,))
    if cursor.fetchone():
        await ctx.send("🚫 Already claimed!")
        return

    cursor.execute("INSERT INTO claims (quest_id, user_id) VALUES (?, ?)", (quest_id, user_id))
    db.commit()

    await ctx.send(f"🎯 {ctx.author.display_name} claimed '{name}'!")

@bot.command()
async def done(ctx, *, quest_name):
    user_id = str(ctx.author.id)
    get_or_create_user(user_id)

    cursor.execute("""
        SELECT id, name, type, points, assigned_to, completed
        FROM quests WHERE name = ?
    """, (quest_name,))
    quest = cursor.fetchone()

    if not quest:
        await ctx.send("Sprig squints... that quest does not exist 👀")
        return

    quest_id, name, qtype, points_val, assigned_to, completed = quest

    if completed:
        await ctx.send("That quest is already done for today! ✨")
        return

    # Assigned enforcement
    if qtype == "assigned" and assigned_to:
        if assigned_to != user_id:
            await ctx.send("🚫 This quest is assigned to someone else!")
            return

    # Open quests must be claimed
    if qtype == "open":
        cursor.execute("SELECT user_id FROM claims WHERE quest_id = ?", (quest_id,))
        claim = cursor.fetchone()

        if not claim:
            await ctx.send("You must claim this quest first! 🎯")
            return

        if claim[0] != user_id:
            await ctx.send("🚫 Someone else claimed this quest!")
            return

    cursor.execute("SELECT points, streak, last_completed FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    last_completed = user[2]
    streak = 1

    if last_completed:
        last_date = datetime.strptime(last_completed, "%Y-%m-%d").date()
        if last_date == yesterday:
            streak = user[1] + 1

    new_points = user[0] + points_val

    cursor.execute("""
        UPDATE users
        SET points = ?, streak = ?, last_completed = ?
        WHERE id = ?
    """, (new_points, streak, str(today), user_id))

    # Clear claim
    cursor.execute("DELETE FROM claims WHERE quest_id = ?", (quest_id,))

    # Mark completed
    cursor.execute("UPDATE quests SET completed = 1 WHERE id = ?", (quest_id,))

    db.commit()

    await ctx.send(f"""
✨ {ctx.author.display_name} COMPLETED "{name}"!!

+{points_val} points
🔥 Streak: {streak}
⭐ Total: {new_points}

Sprig is spinning in a tiny circle of celebration 💫
""")

@bot.command()
async def quests(ctx):
    cursor.execute("""
        SELECT q.name, q.type, q.points, q.assigned_to, c.user_id
        FROM quests q
        LEFT JOIN claims c ON q.id = c.quest_id
        WHERE q.completed = 0
    """)
    quests = cursor.fetchall()

    if not quests:
        await ctx.send("Sprig checked the board… all quests are complete!! 🎉")
        return

    name_w = 18
    type_w = 10
    points_w = 6
    assigned_w = 18
    status_w = 20

    header = (
        f"{'Quest':<{name_w}}"
        f"{'Type':<{type_w}}"
        f"{'Pts':<{points_w}}"
        f"{'Assigned':<{assigned_w}}"
        f"{'Status':<{status_w}}"
    )

    divider = "-" * (name_w + type_w + points_w + assigned_w + status_w)

    rows = []
    for name, qtype, points, assigned_to, claimed_by in quests:
        assigned = f"<@{assigned_to}>" if assigned_to else "-"

        if qtype == "assigned":
            status = f"assigned → <@{assigned_to}>"
        elif claimed_by:
            status = f"claimed <@{claimed_by}>"
        else:
            status = "open"

        row = (
            f"{name[:name_w-1]:<{name_w}}"
            f"{qtype:<{type_w}}"
            f"{points:<{points_w}}"
            f"{assigned:<{assigned_w}}"
            f"{status:<{status_w}}"
        )
        rows.append(row)

    table = "\n".join([header, divider] + rows)
    await ctx.send(f"```{table}```")

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

@bot.command()
async def hello(ctx):
    await ctx.send("Sprig says hello!! ☁️✨")

@bot.event
async def on_ready():
    print(f"Sprig is alive as {bot.user} 🌱")

 
 
# --- Run ---
bot.run(DISCORD_TOKEN)
