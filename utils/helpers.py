"""
Small shared helper functions used across multiple cogs.
"""

import re
from datetime import datetime, timezone
from typing import Optional

import discord

from config import EXCLUDED_CHANNEL_IDS, EXCLUDED_CATEGORY_IDS, TICKET_CATEGORY_ID


def ts() -> str:
    """Current time as a Discord timestamp markup string."""
    return f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>"


def safe_channel_name(value: str) -> str:
    """Create a channel-safe name segment from user input."""
    cleaned = re.sub(r"[^a-z0-9-]", "-", value.lower())  # Replace invalid chars with dashes
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")  # Remove consecutive dashes and trim ends
    return cleaned[:40] if cleaned else "ticket"  # Limit to 40 chars, fallback to "ticket"


def in_excluded_category(channel: Optional[discord.abc.GuildChannel]) -> bool:
    """Check if a channel should be excluded from logging."""
    if channel is None:
        return False

    # Handle thread channels separately
    if isinstance(channel, discord.Thread):
        if channel.id in EXCLUDED_CHANNEL_IDS:
            return True
        parent = channel.parent
        # Check parent channel and category
        if parent and (
            parent.id in EXCLUDED_CHANNEL_IDS
            or getattr(parent, "category_id", None) in EXCLUDED_CATEGORY_IDS
        ):
            return True
        return False

    # Check if channel or its category is in exclusion lists
    return (
        channel.id in EXCLUDED_CHANNEL_IDS
        or channel.id in EXCLUDED_CATEGORY_IDS
        or getattr(channel, "category_id", None) in EXCLUDED_CATEGORY_IDS
    )


def member_text(member: discord.Member) -> str:
    """Format member info for logging (mention, name, ID)."""
    return f"{member.mention} ({member} | `{member.id}`)"


def next_ticket_number(guild: discord.Guild, user_part: str) -> int:
    """Find the next sequential ticket number for a user (001, 002, etc.)."""
    pattern = re.compile(rf"^{re.escape(user_part)}-(\d{{3}})$")
    max_found = 0

    for channel in guild.text_channels:
        match = pattern.match(channel.name)
        if match:
            max_found = max(max_found, int(match.group(1)))

    return max_found + 1


def count_open_tickets(guild: discord.Guild, user_part: str) -> int:
    """Count current open ticket channels for a user in the ticket category."""
    category = guild.get_channel(TICKET_CATEGORY_ID)
    if not isinstance(category, discord.CategoryChannel):
        return 0

    # Count matching channels in ticket category
    pattern = re.compile(rf"^{re.escape(user_part)}-(\d{{3}})$")
    return sum(1 for channel in category.text_channels if pattern.match(channel.name))
