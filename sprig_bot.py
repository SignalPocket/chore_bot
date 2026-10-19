import os
import sqlite3
from datetime import datetime, timedelta
from difflib import get_close_matches
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
QUEST_TIMEZONE_NAME = os.getenv("QUEST_TIMEZONE", "America/New_York")

if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing. Add it to the .env file."
    )

try:
    QUEST_TIMEZONE = ZoneInfo(QUEST_TIMEZONE_NAME)
except Exception as exc:
    raise RuntimeError(
        f"QUEST_TIMEZONE '{QUEST_TIMEZONE_NAME}' is invalid."
    ) from exc

VALID_FREQUENCIES = {"daily", "weekly", "monthly", "one-time"}
VALID_DIFFICULTIES = {"easy", "normal", "hard", "epic"}

FREQUENCY_ALIASES = {
    "day": "daily",
    "daily": "daily",
    "week": "weekly",
    "weekly": "weekly",
    "month": "monthly",
    "monthly": "monthly",
    "once": "one-time",
    "oneoff": "one-time",
    "one-off": "one-time",
    "one_time": "one-time",
    "one-time": "one-time",
}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

db = sqlite3.connect(BASE_DIR / "sprig.db")
cursor = db.cursor()


# --- Database setup and migration ---

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
    name TEXT NOT NULL,
    frequency TEXT NOT NULL DEFAULT 'one-time',
    points INTEGER NOT NULL DEFAULT 0,
    assigned_to TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    last_completed TEXT,
    reset_after TEXT,
    category TEXT NOT NULL DEFAULT 'general',
    difficulty TEXT NOT NULL DEFAULT 'normal',
    notes TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS claims (
    quest_id INTEGER UNIQUE,
    user_id TEXT
)
""")

db.commit()


def get_table_columns(table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def add_column_if_missing(table_name, column_name, definition):
    columns = get_table_columns(table_name)
    if column_name not in columns:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )
        db.commit()


# Rename the old "type" column without losing existing quest data.
quest_columns = get_table_columns("quests")

if "type" in quest_columns and "frequency" not in quest_columns:
    try:
        cursor.execute("ALTER TABLE quests RENAME COLUMN type TO frequency")
        db.commit()
    except sqlite3.OperationalError:
        # Fallback for older SQLite versions.
        cursor.execute(
            "ALTER TABLE quests ADD COLUMN frequency TEXT DEFAULT 'one-time'"
        )
        cursor.execute("""
            UPDATE quests
            SET frequency = COALESCE(NULLIF(type, ''), 'one-time')
        """)
        db.commit()

add_column_if_missing(
    "quests", "completed", "INTEGER NOT NULL DEFAULT 0"
)
add_column_if_missing("quests", "last_completed", "TEXT")
add_column_if_missing("quests", "reset_after", "TEXT")
add_column_if_missing(
    "quests", "category", "TEXT NOT NULL DEFAULT 'general'"
)
add_column_if_missing(
    "quests", "difficulty", "TEXT NOT NULL DEFAULT 'normal'"
)
add_column_if_missing("quests", "notes", "TEXT")

# Clean up old stored mentions: <@123> becomes 123.
cursor.execute("""
UPDATE quests
SET assigned_to = REPLACE(REPLACE(assigned_to, '<@', ''), '>', '')
WHERE assigned_to LIKE '<@%>'
""")

# Old "open" and "assigned" values described behavior, not frequency.
# Assignment behavior now comes entirely from assigned_to.
cursor.execute("""
UPDATE quests
SET frequency = 'one-time'
WHERE LOWER(TRIM(COALESCE(frequency, ''))) IN ('', 'open', 'assigned')
""")

cursor.execute("""
UPDATE quests
SET frequency = LOWER(TRIM(frequency)),
    category = COALESCE(NULLIF(TRIM(category), ''), 'general'),
    difficulty = LOWER(COALESCE(NULLIF(TRIM(difficulty), ''), 'normal'))
""")

# Any old recurring quest that was completed before reset tracking existed
# is made available again instead of remaining stuck forever.
cursor.execute("""
UPDATE quests
SET completed = 0
WHERE completed = 1
  AND frequency IN ('daily', 'weekly', 'monthly')
  AND reset_after IS NULL
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_quests_completed
ON quests (completed)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_quests_reset_after
ON quests (reset_after)
""")

db.commit()


# --- Helpers ---

def now_local():
    return datetime.now(QUEST_TIMEZONE)


def normalize_frequency(value):
    normalized = FREQUENCY_ALIASES.get(value.strip().lower())
    if normalized not in VALID_FREQUENCIES:
        choices = ", ".join(sorted(VALID_FREQUENCIES))
        raise ValueError(f"Frequency must be one of: {choices}")
    return normalized


def calculate_reset_after(completed_at, frequency):
    if frequency == "one-time":
        return None

    local_time = completed_at.astimezone(QUEST_TIMEZONE)

    if frequency == "daily":
        reset_date = local_time.date() + timedelta(days=1)
        reset_time = datetime.combine(
            reset_date,
            datetime.min.time(),
            tzinfo=QUEST_TIMEZONE,
        )

    elif frequency == "weekly":
        # Weekly quests reset at the household handoff boundary:
        # Sunday at 6:00 PM in QUEST_TIMEZONE.
        days_until_sunday = (6 - local_time.weekday()) % 7
        reset_date = local_time.date() + timedelta(days=days_until_sunday)
        reset_time = datetime.combine(
            reset_date,
            datetime.min.time().replace(hour=18),
            tzinfo=QUEST_TIMEZONE,
        )

        # If this Sunday's reset has already happened, use next Sunday.
        if reset_time <= local_time:
            reset_time += timedelta(days=7)

    elif frequency == "monthly":
        if local_time.month == 12:
            reset_date = local_time.date().replace(
                year=local_time.year + 1,
                month=1,
                day=1,
            )
        else:
            reset_date = local_time.date().replace(
                month=local_time.month + 1,
                day=1,
            )

        reset_time = datetime.combine(
            reset_date,
            datetime.min.time(),
            tzinfo=QUEST_TIMEZONE,
        )

    else:
        return None

    return reset_time.isoformat()


def reset_due_quests():
    current_time = now_local()
    cursor.execute("""
        SELECT id, reset_after
        FROM quests
        WHERE completed = 1
          AND reset_after IS NOT NULL
    """)

    due_ids = []

    for quest_id, reset_after in cursor.fetchall():
        try:
            reset_time = datetime.fromisoformat(reset_after)
        except (TypeError, ValueError):
            due_ids.append(quest_id)
            continue

        if reset_time.tzinfo is None:
            reset_time = reset_time.replace(tzinfo=QUEST_TIMEZONE)

        if reset_time <= current_time:
            due_ids.append(quest_id)

    if not due_ids:
        return 0

    placeholders = ",".join("?" for _ in due_ids)

    cursor.execute(
        f"""
        UPDATE quests
        SET completed = 0,
            reset_after = NULL
        WHERE id IN ({placeholders})
        """,
        due_ids,
    )

    cursor.execute(
        f"DELETE FROM claims WHERE quest_id IN ({placeholders})",
        due_ids,
    )

    db.commit()
    return len(due_ids)


def get_or_create_user(user_id):
    cursor.execute(
        "INSERT OR IGNORE INTO users (id) VALUES (?)",
        (user_id,),
    )
    db.commit()


def quest_exists(quest_id):
    cursor.execute("SELECT 1 FROM quests WHERE id = ?", (quest_id,))
    return cursor.fetchone() is not None


async def get_member_name(ctx, user_id):
    if not user_id:
        return None

    try:
        member_id = int(user_id)
    except (TypeError, ValueError):
        return str(user_id)

    if ctx.guild:
        member = ctx.guild.get_member(member_id)

        if member is None:
            try:
                member = await ctx.guild.fetch_member(member_id)
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                member = None

        if member:
            return member.display_name

    try:
        user = bot.get_user(member_id) or await bot.fetch_user(member_id)
        return user.display_name
    except (
        discord.NotFound,
        discord.Forbidden,
        discord.HTTPException,
    ):
        return f"Unknown user ({user_id})"


def format_reset_time(reset_after):
    if not reset_after:
        return "never"

    try:
        reset_time = datetime.fromisoformat(reset_after)
    except ValueError:
        return reset_after

    if reset_time.tzinfo is None:
        reset_time = reset_time.replace(tzinfo=QUEST_TIMEZONE)

    return reset_time.astimezone(QUEST_TIMEZONE).strftime(
        "%a %b %d at %I:%M %p"
    )


# --- Automatic quest reset loop ---

@tasks.loop(minutes=1)
async def quest_reset_loop():
    reset_count = reset_due_quests()
    if reset_count:
        print(f"Reset {reset_count} recurring quest(s).")


@quest_reset_loop.before_loop
async def before_quest_reset_loop():
    await bot.wait_until_ready()


# --- Commands ---

@bot.command()
async def addquest(
    ctx,
    name: str,
    frequency: str,
    points: int,
    assigned_to: discord.Member = None,
):
    """
    Add a quest.

    Examples:
      !addquest "Afternoon dishes" daily 5
      !addquest "Feed the cat" daily 5 @Katie
    """
    try:
        frequency = normalize_frequency(frequency)
    except ValueError as exc:
        await ctx.send(f"🚫 {exc}")
        return

    if points < 0:
        await ctx.send("Quest points cannot be negative.")
        return

    assigned_id = str(assigned_to.id) if assigned_to else None

    cursor.execute(
        """
        INSERT INTO quests (
            name,
            frequency,
            points,
            assigned_to,
            category,
            difficulty
        )
        VALUES (?, ?, ?, ?, 'general', 'normal')
        """,
        (name, frequency, points, assigned_id),
    )

    quest_id = cursor.lastrowid
    db.commit()

    display = assigned_to.display_name if assigned_to else "Open to all"

    await ctx.send(
        f"🌱 Added quest #{quest_id}: **{name}**\n"
        f"Frequency: {frequency} | "
        f"Assigned: {display} | "
        f"+{points} points"
    )


@bot.command()
async def editquest(ctx, quest_id: int, field: str, *, value: str):
    """
    Edit a quest field.

    Editable fields:
      name, frequency, points, assigned_to, category, difficulty, notes
    """
    if not quest_exists(quest_id):
        await ctx.send(f"Sprig cannot find quest #{quest_id} 👀")
        return

    field = field.strip().lower()
    allowed_fields = {
        "name",
        "frequency",
        "points",
        "assigned_to",
        "category",
        "difficulty",
        "notes",
    }

    if field not in allowed_fields:
        await ctx.send(
            "Editable fields: `name`, `frequency`, `points`, "
            "`assigned_to`, `category`, `difficulty`, or `notes`."
        )
        return

    stored_value = value.strip()

    if field == "frequency":
        try:
            stored_value = normalize_frequency(stored_value)
        except ValueError as exc:
            await ctx.send(f"🚫 {exc}")
            return

    elif field == "points":
        try:
            stored_value = int(stored_value)
        except ValueError:
            await ctx.send("Points must be a whole number.")
            return

        if stored_value < 0:
            await ctx.send("Quest points cannot be negative.")
            return

    elif field == "difficulty":
        stored_value = stored_value.lower()
        if stored_value not in VALID_DIFFICULTIES:
            choices = ", ".join(sorted(VALID_DIFFICULTIES))
            await ctx.send(f"Difficulty must be one of: {choices}")
            return

    elif field == "assigned_to":
        if stored_value.lower() in {
            "none",
            "open",
            "unassigned",
            "clear",
        }:
            stored_value = None
        else:
            try:
                member = await commands.MemberConverter().convert(
                    ctx,
                    stored_value,
                )
            except commands.MemberNotFound:
                await ctx.send(
                    "I could not find that member. Mention them, or use "
                    "`open` to make the quest unassigned."
                )
                return

            stored_value = str(member.id)

    elif field in {"name", "category"} and not stored_value:
        await ctx.send(f"`{field}` cannot be blank.")
        return

    elif field == "notes" and stored_value.lower() in {
        "none",
        "clear",
        "delete",
    }:
        stored_value = None

    cursor.execute(
        f"UPDATE quests SET {field} = ? WHERE id = ?",
        (stored_value, quest_id),
    )

    # Recalculate the next reset when frequency changes on a completed quest.
    if field == "frequency":
        cursor.execute(
            """
            SELECT completed, last_completed, frequency
            FROM quests
            WHERE id = ?
            """,
            (quest_id,),
        )
        completed, last_completed, new_frequency = cursor.fetchone()

        if completed:
            try:
                completed_at = datetime.fromisoformat(last_completed)
                if completed_at.tzinfo is None:
                    completed_at = completed_at.replace(
                        tzinfo=QUEST_TIMEZONE
                    )
            except (TypeError, ValueError):
                completed_at = now_local()

            reset_after = calculate_reset_after(
                completed_at,
                new_frequency,
            )
            cursor.execute(
                "UPDATE quests SET reset_after = ? WHERE id = ?",
                (reset_after, quest_id),
            )

    db.commit()

    display_value = "open" if (
        field == "assigned_to" and stored_value is None
    ) else stored_value

    await ctx.send(
        f"🌿 Updated quest #{quest_id}: "
        f"`{field}` → **{display_value}**"
    )


@bot.command()
async def claim(ctx, quest_id: int):
    reset_due_quests()
    user_id = str(ctx.author.id)
    if not chore_ui.available(user_id):
        await ctx.send("You're away this week. Use Weekly sign-ups to reserve your next home week's chores.")
        return

    cursor.execute(
        """
        SELECT id, name, assigned_to, completed
        FROM quests
        WHERE id = ?
        """,
        (quest_id,),
    )
    quest = cursor.fetchone()

    if not quest:
        await ctx.send(f"Sprig cannot find quest #{quest_id} 👀")
        return

    quest_id, name, assigned_to, completed = quest
    assigned_to = assigned_to or chore_ui.weekly_owner(quest_id)

    if completed:
        await ctx.send(f"Quest #{quest_id} is already completed! ✨")
        return

    if assigned_to:
        assigned_name = await get_member_name(ctx, assigned_to)
        await ctx.send(
            f"Quest #{quest_id} is assigned to **{assigned_name}** "
            "and does not need to be claimed."
        )
        return

    cursor.execute(
        "SELECT user_id FROM claims WHERE quest_id = ?",
        (quest_id,),
    )
    existing_claim = cursor.fetchone()

    if existing_claim:
        claimed_name = await get_member_name(ctx, existing_claim[0])
        await ctx.send(
            f"🚫 Quest #{quest_id} is already claimed by "
            f"**{claimed_name}**!"
        )
        return

    cursor.execute(
        """
        INSERT INTO claims (quest_id, user_id)
        VALUES (?, ?)
        """,
        (quest_id, user_id),
    )
    db.commit()

    await ctx.send(
        f"🎯 {ctx.author.display_name} claimed "
        f"quest #{quest_id}: **{name}**!"
    )


@bot.command()
async def unclaim(ctx, quest_id: int):
    user_id = str(ctx.author.id)

    cursor.execute(
        "SELECT user_id FROM claims WHERE quest_id = ?",
        (quest_id,),
    )
    claim = cursor.fetchone()

    if not claim:
        await ctx.send(f"Quest #{quest_id} is not currently claimed.")
        return

    if claim[0] != user_id:
        await ctx.send("🚫 Only the person who claimed it can release it.")
        return

    cursor.execute(
        "DELETE FROM claims WHERE quest_id = ?",
        (quest_id,),
    )
    db.commit()

    await ctx.send(f"🍃 Quest #{quest_id} is open again.")


@bot.command()
async def done(ctx, quest_id: int):
    reset_due_quests()
    user_id = str(ctx.author.id)
    if not chore_ui.available(user_id):
        await ctx.send("You're away this week. Your next home week's chores will appear after the Sunday handoff.")
        return
    get_or_create_user(user_id)

    cursor.execute(
        """
        SELECT
            id,
            name,
            frequency,
            points,
            assigned_to,
            completed
        FROM quests
        WHERE id = ?
        """,
        (quest_id,),
    )
    quest = cursor.fetchone()

    if not quest:
        await ctx.send(f"Sprig cannot find quest #{quest_id} 👀")
        return

    (
        quest_id,
        name,
        frequency,
        points_val,
        assigned_to,
        completed,
    ) = quest
    assigned_to = assigned_to or chore_ui.weekly_owner(quest_id)

    if completed:
        await ctx.send(
            f"Quest #{quest_id} is already complete for this cycle! ✨"
        )
        return

    if assigned_to and assigned_to != user_id:
        assigned_name = await get_member_name(ctx, assigned_to)
        await ctx.send(
            f"🚫 Quest #{quest_id} is assigned to "
            f"**{assigned_name}**!"
        )
        return

    if not assigned_to:
        cursor.execute(
            "SELECT user_id FROM claims WHERE quest_id = ?",
            (quest_id,),
        )
        claim = cursor.fetchone()

        if not claim:
            await ctx.send(
                f"You must claim quest #{quest_id} first! 🎯"
            )
            return

        if claim[0] != user_id:
            claimed_name = await get_member_name(ctx, claim[0])
            await ctx.send(
                f"🚫 Quest #{quest_id} was claimed by "
                f"**{claimed_name}**!"
            )
            return

    cursor.execute(
        """
        SELECT points, streak, last_completed
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )
    user = cursor.fetchone()

    completed_at = now_local()
    today = completed_at.date()
    yesterday = today - timedelta(days=1)

    current_points, current_streak, user_last_completed = user
    streak = 1

    if user_last_completed:
        try:
            last_date = datetime.fromisoformat(
                user_last_completed
            ).date()
        except ValueError:
            last_date = datetime.strptime(
                user_last_completed,
                "%Y-%m-%d",
            ).date()

        if last_date == today:
            streak = current_streak
        elif last_date == yesterday:
            streak = current_streak + 1

    new_points = current_points + points_val
    reset_after = calculate_reset_after(
        completed_at,
        frequency,
    )

    cursor.execute(
        """
        UPDATE users
        SET points = ?,
            streak = ?,
            last_completed = ?
        WHERE id = ?
        """,
        (
            new_points,
            streak,
            completed_at.isoformat(),
            user_id,
        ),
    )

    cursor.execute(
        "DELETE FROM claims WHERE quest_id = ?",
        (quest_id,),
    )

    cursor.execute(
        """
        UPDATE quests
        SET completed = 1,
            last_completed = ?,
            reset_after = ?
        WHERE id = ?
        """,
        (
            completed_at.isoformat(),
            reset_after,
            quest_id,
        ),
    )

    db.commit()

    reset_message = (
        "This one-time quest will stay completed."
        if frequency == "one-time"
        else f"Returns {format_reset_time(reset_after)}."
    )

    await ctx.send(
        f"✨ {ctx.author.display_name} completed "
        f"quest #{quest_id}: **{name}**!\n\n"
        f"+{points_val} points\n"
        f"🔥 Streak: {streak}\n"
        f"⭐ Total: {new_points}\n"
        f"🕰️ {reset_message}\n\n"
        "Sprig is spinning in a tiny circle of celebration 💫"
    )


@bot.command()
async def quests(ctx):
    reset_due_quests()

    cursor.execute(
        """
        SELECT
            q.id,
            q.name,
            q.frequency,
            q.points,
            q.category,
            q.difficulty,
            q.assigned_to,
            c.user_id
        FROM quests q
        LEFT JOIN claims c ON q.id = c.quest_id
        WHERE q.completed = 0
        ORDER BY
            CASE q.frequency
                WHEN 'daily' THEN 1
                WHEN 'weekly' THEN 2
                WHEN 'monthly' THEN 3
                ELSE 4
            END,
            q.id
        """
    )
    quest_rows = cursor.fetchall()

    if not quest_rows:
        await ctx.send(
            "Sprig checked the board… all quests are complete!! 🎉"
        )
        return

    id_w = 5
    name_w = 20
    frequency_w = 10
    points_w = 6
    category_w = 12
    difficulty_w = 10
    status_w = 23

    header = (
        f"{'#':<{id_w}}"
        f"{'Quest':<{name_w}}"
        f"{'Freq':<{frequency_w}}"
        f"{'Pts':<{points_w}}"
        f"{'Category':<{category_w}}"
        f"{'Difficulty':<{difficulty_w}}"
        f"{'Status':<{status_w}}"
    )

    divider = "-" * (
        id_w
        + name_w
        + frequency_w
        + points_w
        + category_w
        + difficulty_w
        + status_w
    )

    rows = []

    for (
        quest_id,
        name,
        frequency,
        points,
        category,
        difficulty,
        assigned_to,
        claimed_by,
    ) in quest_rows:
        assigned_name = await get_member_name(ctx, assigned_to)
        claimed_name = await get_member_name(ctx, claimed_by)

        if assigned_to:
            status = f"assigned: {assigned_name}"
        elif claimed_by:
            status = f"claimed: {claimed_name}"
        else:
            status = "open"

        row = (
            f"{quest_id:<{id_w}}"
            f"{name[:name_w - 1]:<{name_w}}"
            f"{frequency:<{frequency_w}}"
            f"{points:<{points_w}}"
            f"{category[:category_w - 1]:<{category_w}}"
            f"{difficulty:<{difficulty_w}}"
            f"{status[:status_w - 1]:<{status_w}}"
        )
        rows.append(row)

    table = "\n".join([header, divider] + rows)

    await ctx.send(
        "🌱 **Available quests**\n"
        f"```{table}```"
        "Use `!claim NUMBER`, `!done NUMBER`, "
        "or `!quest NUMBER` for details."
    )


@bot.command(name="quest")
async def quest_details(ctx, quest_id: int):
    reset_due_quests()

    cursor.execute(
        """
        SELECT
            q.name,
            q.frequency,
            q.points,
            q.assigned_to,
            q.completed,
            q.last_completed,
            q.reset_after,
            q.category,
            q.difficulty,
            q.notes,
            c.user_id
        FROM quests q
        LEFT JOIN claims c ON q.id = c.quest_id
        WHERE q.id = ?
        """,
        (quest_id,),
    )
    quest = cursor.fetchone()

    if not quest:
        await ctx.send(f"Sprig cannot find quest #{quest_id} 👀")
        return

    (
        name,
        frequency,
        points_val,
        assigned_to,
        completed,
        last_completed,
        reset_after,
        category,
        difficulty,
        notes,
        claimed_by,
    ) = quest

    assigned_name = await get_member_name(ctx, assigned_to)
    claimed_name = await get_member_name(ctx, claimed_by)

    if completed:
        status = "Completed"
    elif assigned_to:
        status = f"Assigned to {assigned_name}"
    elif claimed_by:
        status = f"Claimed by {claimed_name}"
    else:
        status = "Open"

    if last_completed:
        try:
            last_dt = datetime.fromisoformat(last_completed)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=QUEST_TIMEZONE)
            last_display = last_dt.astimezone(
                QUEST_TIMEZONE
            ).strftime("%a %b %d at %I:%M %p")
        except ValueError:
            last_display = last_completed
    else:
        last_display = "Never"

    reset_display = (
        format_reset_time(reset_after)
        if completed and frequency != "one-time"
        else "Never"
    )

    await ctx.send(
        f"🌿 **Quest #{quest_id}: {name}**\n"
        f"**Frequency:** {frequency}\n"
        f"**Points:** {points_val}\n"
        f"**Category:** {category}\n"
        f"**Difficulty:** {difficulty}\n"
        f"**Status:** {status}\n"
        f"**Last completed:** {last_display}\n"
        f"**Next reset:** {reset_display}\n"
        f"**Notes:** {notes or 'None'}"
    )


@bot.command()
async def resetquest(ctx, quest_id: int):
    if not quest_exists(quest_id):
        await ctx.send(f"Sprig cannot find quest #{quest_id} 👀")
        return

    cursor.execute(
        """
        UPDATE quests
        SET completed = 0,
            reset_after = NULL
        WHERE id = ?
        """,
        (quest_id,),
    )
    cursor.execute(
        "DELETE FROM claims WHERE quest_id = ?",
        (quest_id,),
    )
    db.commit()

    await ctx.send(f"♻️ Quest #{quest_id} is available again.")


@bot.command()
async def deletequest(ctx, quest_id: int):
    if not quest_exists(quest_id):
        await ctx.send(f"Sprig cannot find quest #{quest_id} 👀")
        return

    cursor.execute(
        "DELETE FROM claims WHERE quest_id = ?",
        (quest_id,),
    )
    cursor.execute(
        "DELETE FROM quests WHERE id = ?",
        (quest_id,),
    )
    db.commit()

    await ctx.send(f"🍂 Deleted quest #{quest_id}.")


@bot.command()
async def points(ctx):
    user_id = str(ctx.author.id)
    get_or_create_user(user_id)

    cursor.execute(
        "SELECT points, streak FROM users WHERE id = ?",
        (user_id,),
    )
    user = cursor.fetchone()

    await ctx.send(
        f"⭐ Points: {user[0]} | 🔥 Streak: {user[1]}"
    )


@bot.command()
async def leaderboard(ctx):
    cursor.execute(
        "SELECT id, points FROM users ORDER BY points DESC LIMIT 5"
    )
    users = cursor.fetchall()

    msg = "🏆 **Leaderboard** 🏆\n"
    for index, (user_id, points_val) in enumerate(users, start=1):
        user_name = await get_member_name(ctx, user_id)
        msg += f"{index}. **{user_name}** — {points_val} pts\n"

    await ctx.send(msg)


@bot.command()
async def hello(ctx):
    await ctx.send("Sprig says hello!! ☁️✨")


# --- Sprig help system ---

HELP_COMMANDS = {
    "quests": {
        "summary": "Show every quest that is currently available.",
        "usage": "!quests",
        "examples": ["!quests"],
        "details": [
            "The board shows quest numbers, frequency, points, category, "
            "difficulty, and claim or assignment status.",
            "Use the quest number with commands such as `!claim 2` and "
            "`!done 2`.",
        ],
    },
    "quest": {
        "summary": "Show all details for one quest.",
        "usage": "!quest NUMBER",
        "examples": ["!quest 2"],
        "details": [
            "Shows the quest's schedule, points, category, difficulty, "
            "status, notes, last completion, and next reset.",
        ],
    },
    "claim": {
        "summary": "Reserve an open quest for yourself.",
        "usage": "!claim NUMBER",
        "examples": ["!claim 2"],
        "details": [
            "Assigned quests do not need to be claimed.",
            "Only the person who claimed an open quest can complete it.",
        ],
    },
    "unclaim": {
        "summary": "Release a quest that you previously claimed.",
        "usage": "!unclaim NUMBER",
        "examples": ["!unclaim 2"],
        "details": [
            "Only the person who claimed the quest can release it.",
        ],
    },
    "done": {
        "summary": "Complete a quest and collect its points.",
        "usage": "!done NUMBER",
        "examples": ["!done 2"],
        "details": [
            "Open quests must be claimed first.",
            "Assigned quests can only be completed by their assigned member.",
            "Recurring quests return automatically at their next reset.",
        ],
    },
    "addquest": {
        "summary": "Create a new quest.",
        "usage": '!addquest "NAME" FREQUENCY POINTS [@MEMBER]',
        "examples": [
            '!addquest "Afternoon dishes" daily 5',
            '!addquest "Take out recycling" weekly 10 @ginaria',
            '!addquest "Clean the garage" one-time 25',
        ],
        "details": [
            "Put multiword quest names in quotation marks.",
            "Frequencies: `daily`, `weekly`, `monthly`, `one-time`.",
            "Leave off the member mention to make the quest open to everyone.",
            "New quests start in the `general` category with `normal` "
            "difficulty.",
        ],
    },
    "editquest": {
        "summary": "Change one field on an existing quest.",
        "usage": "!editquest NUMBER FIELD VALUE",
        "examples": [
            "!editquest 2 category kitchen",
            "!editquest 2 difficulty easy",
            "!editquest 2 points 10",
            "!editquest 2 frequency weekly",
            "!editquest 2 assigned_to @ginaria",
            "!editquest 2 assigned_to open",
            "!editquest 2 notes Empty the dishwasher and wipe the counter.",
        ],
        "details": [
            "Editable fields: `name`, `frequency`, `points`, `assigned_to`, "
            "`category`, `difficulty`, and `notes`.",
            "Difficulties: `easy`, `normal`, `hard`, `epic`.",
            "Use `open` for `assigned_to` to remove an assignment.",
            "Use `clear` for `notes` to erase the notes.",
        ],
    },
    "resetquest": {
        "summary": "Reopen a completed quest immediately.",
        "usage": "!resetquest NUMBER",
        "examples": ["!resetquest 2"],
        "details": [
            "Clears the quest's completion state, next reset, and claim.",
            "This is a manual override. Daily, weekly, and monthly quests "
            "normally reset by themselves.",
        ],
    },
    "deletequest": {
        "summary": "Permanently delete a quest.",
        "usage": "!deletequest NUMBER",
        "examples": ["!deletequest 2"],
        "details": [
            "This also removes any active claim on the quest.",
            "Deletion cannot currently be undone through Discord.",
        ],
    },
    "points": {
        "summary": "Show your total points and current streak.",
        "usage": "!points",
        "examples": ["!points"],
        "details": [
            "Your streak increases when you complete quests on consecutive "
            "days.",
            "Completing more than one quest on the same day does not increase "
            "the streak more than once.",
        ],
    },
    "leaderboard": {
        "summary": "Show the five highest point totals.",
        "usage": "!leaderboard",
        "examples": ["!leaderboard"],
        "details": [
            "Only members who have completed at least one quest appear.",
        ],
    },
    "hello": {
        "summary": "Ask Sprig to say hello.",
        "usage": "!hello",
        "examples": ["!hello"],
        "details": ["A tiny botanical systems check."],
    },
    "help": {
        "summary": "Open Sprig's guide or inspect one command category.",
        "usage": "!help [COMMAND or CATEGORY]",
        "examples": [
            "!help",
            "!help claim",
            "!help editquest",
            "!help management",
        ],
        "details": [
            "Categories: `playing`, `management`, `progress`, and `other`.",
        ],
    },
}

HELP_CATEGORIES = {
    "playing": {
        "title": "🎯 Playing",
        "description": "Find, reserve, release, and complete quests.",
        "commands": ["quests", "quest", "claim", "unclaim", "done"],
    },
    "management": {
        "title": "🛠️ Quest Management",
        "description": "Create, edit, reopen, and remove quests.",
        "commands": [
            "addquest",
            "editquest",
            "resetquest",
            "deletequest",
        ],
    },
    "progress": {
        "title": "🏆 Progress",
        "description": "Check points, streaks, and rankings.",
        "commands": ["points", "leaderboard"],
    },
    "other": {
        "title": "🌿 Other",
        "description": "General Sprig commands.",
        "commands": ["help", "hello"],
    },
}


def help_command_lines(command_names):
    return "\n".join(
        f"`!{name}` — {HELP_COMMANDS[name]['summary']}"
        for name in command_names
    )


@bot.command(name="help")
async def custom_help(ctx, *, topic: str = None):
    """Show Sprig's command guide."""
    if not topic:
        embed = discord.Embed(
            title="🌱 Sprig's Quest Guide",
            description=(
                "Use quest **numbers** for everyday commands. "
                "Try `!help COMMAND` for examples and details."
            ),
        )

        for category in HELP_CATEGORIES.values():
            embed.add_field(
                name=category["title"],
                value=help_command_lines(category["commands"]),
                inline=False,
            )

        embed.add_field(
            name="🕰️ Automatic Resets",
            value=(
                "`daily` — midnight each day\n"
                "`weekly` — Sunday at 6:00 PM\n"
                "`monthly` — first day of the month\n"
                "`one-time` — never resets automatically"
            ),
            inline=False,
        )

        embed.add_field(
            name="💡 First Steps",
            value=(
                "1. Run `!quests`\n"
                "2. Reserve an open quest with `!claim NUMBER`\n"
                "3. Finish it with `!done NUMBER`"
            ),
            inline=False,
        )

        embed.set_footer(
            text="Examples: !help addquest • !help done • !help management"
        )
        await ctx.send(embed=embed)
        return

    lookup = topic.strip().lower().lstrip("!")

    if lookup in HELP_CATEGORIES:
        category = HELP_CATEGORIES[lookup]
        embed = discord.Embed(
            title=category["title"],
            description=category["description"],
        )
        embed.add_field(
            name="Commands",
            value=help_command_lines(category["commands"]),
            inline=False,
        )
        embed.set_footer(text="Use !help COMMAND for full examples.")
        await ctx.send(embed=embed)
        return

    command_info = HELP_COMMANDS.get(lookup)

    if command_info is None:
        choices = list(HELP_COMMANDS) + list(HELP_CATEGORIES)
        matches = get_close_matches(lookup, choices, n=3, cutoff=0.45)

        suggestion = ""
        if matches:
            suggestion = (
                "\n\nDid you mean: "
                + ", ".join(f"`!help {match}`" for match in matches)
                + "?"
            )

        await ctx.send(
            f"Sprig cannot find help for `{topic}`. "
            "Use `!help` to see everything."
            f"{suggestion}"
        )
        return

    embed = discord.Embed(
        title=f"🌿 !{lookup}",
        description=command_info["summary"],
    )
    embed.add_field(
        name="Usage",
        value=f"`{command_info['usage']}`",
        inline=False,
    )
    embed.add_field(
        name="Examples",
        value="\n".join(
            f"`{example}`" for example in command_info["examples"]
        ),
        inline=False,
    )
    embed.add_field(
        name="Good to Know",
        value="\n".join(
            f"• {detail}" for detail in command_info["details"]
        ),
        inline=False,
    )
    embed.set_footer(text="Use !help to return to the full guide.")
    await ctx.send(embed=embed)


# --- Friendly command errors ---

@addquest.error
async def addquest_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            'Use `!addquest "Quest name" FREQUENCY POINTS [@member]`.\n'
            'Example: `!addquest "Afternoon dishes" daily 5`'
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "I could not read one of those values. Put multi-word quest "
            "names in quotes, and make points a whole number."
        )
    else:
        raise error


@editquest.error
async def editquest_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "Use `!editquest NUMBER FIELD VALUE`.\n"
            "Example: `!editquest 2 category kitchen`"
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Quest numbers must be numbers.")
    else:
        raise error


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


@bot.event
async def on_ready():
    reset_count = reset_due_quests()

    if not quest_reset_loop.is_running():
        quest_reset_loop.start()

    print(
        f"Sprig is alive as {bot.user} 🌱 "
        f"({QUEST_TIMEZONE_NAME}; reset {reset_count} due quest(s))"
    )


# --- Run ---

from chore_board import install

chore_ui = install(globals())

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
