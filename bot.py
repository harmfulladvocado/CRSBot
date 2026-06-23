"""
CRSBot entry point.

Loads environment variables, configures intents, loads all cogs, and
starts the bot. Feature logic lives in cogs/ — this file just wires
everything together.
"""

import asyncio
import os
from pathlib import Path

import discord
from discord.ext import commands

from config import GUILD_ID
from cogs.tickets import OpenTicketView, CloseTicketView


def load_local_env() -> None:
    """Load key=value pairs from a local .env file if present."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        if key:
            os.environ.setdefault(key, value)


load_local_env()
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# Cogs to load on startup. Add new feature files here.
INITIAL_COGS = (
    "cogs.tickets",
    "cogs.logging_events",
    "cogs.moderation",
)

# ============================================================================
# BOT SETUP
# ============================================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.bans = True
intents.invites = True
intents.emojis_and_stickers = True
intents.messages = True
intents.message_content = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


async def setup_hook():
    """Runs once on startup: loads cogs, adds persistent views, syncs commands."""
    for extension in INITIAL_COGS:
        await bot.load_extension(extension)

    # Add persistent views so ticket buttons survive bot restarts
    bot.add_view(OpenTicketView())
    bot.add_view(CloseTicketView())

    # Sync slash commands to the configured guild
    if GUILD_ID:
        guild_obj = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild_obj)
        await bot.tree.sync(guild=guild_obj)
        print(f"Synced commands to guild: {GUILD_ID}")
    else:
        await bot.tree.sync()
        print("Synced global commands.")


bot.setup_hook = setup_hook


async def main():
    if not TOKEN or TOKEN.isdigit():
        raise ValueError("Invalid bot token. Set DISCORD_BOT_TOKEN in your environment.")
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
