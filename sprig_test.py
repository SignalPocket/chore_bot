import discord
from discord import app_commands
from discord.ext import commands

intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents)

# This syncs slash commands to Discord
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Sprig synced {len(synced)} commands 🌱")
    except Exception as e:
        print(e)

    print(f"Logged in as {bot.user}")
    
