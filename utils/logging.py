"""
Shared logging helpers used by event cogs and the ticket system.

These take `bot` as an explicit argument rather than importing a global
bot instance, so they can be called from any cog without circular imports.
"""

import io
from datetime import datetime, timezone

import discord

from config import GUILD_ID, LOG_CHANNEL_ID, TRANSCRIPT_CHANNEL_ID
from utils.helpers import ts


async def send_log(bot: discord.Client, title: str, description: str) -> None:
    """Send a formatted log message to the configured log channel."""
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return

    # Get the log channel
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        return

    # Create an embed with title, description, color and timestamp
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    # Add footer with guild ID and formatted timestamp
    embed.set_footer(text=f"Guild ID: {GUILD_ID} | {ts()}")
    await channel.send(embed=embed)


async def send_ticket_transcript(ticket_channel: discord.TextChannel, closed_by: discord.abc.User) -> None:
    """Save full ticket transcript to the configured transcript channel."""
    transcript_channel = ticket_channel.guild.get_channel(TRANSCRIPT_CHANNEL_ID)
    if transcript_channel is None:
        try:
            transcript_channel = await ticket_channel.guild.fetch_channel(TRANSCRIPT_CHANNEL_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

    if not isinstance(transcript_channel, (discord.TextChannel, discord.Thread)):
        return

    lines: list[str] = [
        f"Ticket Channel: {ticket_channel.name} ({ticket_channel.id})",
        f"Guild: {ticket_channel.guild.name} ({ticket_channel.guild.id})",
        f"Closed By: {closed_by} ({closed_by.id})",
        f"Closed At: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
    ]

    async for msg in ticket_channel.history(limit=None, oldest_first=True):
        message_text = msg.content if msg.content else "<no text content>"
        message_text = message_text.replace("\r\n", "\\n").replace("\n", "\\n")

        if msg.attachments:
            attachment_list = ", ".join(attachment.url for attachment in msg.attachments)
            message_text += f" [Attachments: {attachment_list}]"

        if msg.embeds:
            embed_labels = []
            for embed in msg.embeds:
                embed_labels.append(embed.title or "<no title>")
            message_text += f" [Embeds: {', '.join(embed_labels)}]"

        timestamp_text = msg.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"{msg.author} - {message_text} - {timestamp_text}")

    transcript_bytes = io.BytesIO("\n".join(lines).encode("utf-8"))
    transcript_file = discord.File(
        fp=transcript_bytes,
        filename=f"transcript-{ticket_channel.name}-{int(datetime.now(timezone.utc).timestamp())}.txt",
    )

    await transcript_channel.send(
        content=(
            "Ticket transcript saved\n"
            f"Channel: {ticket_channel.name} ({ticket_channel.id})\n"
            f"Closed by: {closed_by} ({closed_by.id})\n"
            f"Closed at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        ),
        file=transcript_file,
    )
