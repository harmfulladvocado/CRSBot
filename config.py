"""
Central configuration for CRSBot.

All server-specific IDs and tunable constants live here so they're easy
to find and change without digging through command/event logic.
"""

import discord

# ============================================================================
# CORE IDS
# ============================================================================

GUILD_ID = 1337503536371728406
LOG_CHANNEL_ID = 1346833175762173962
TICKET_CATEGORY_ID = 1337503537286090875
SUPPORT_STAFF_ROLE_ID = 1346814062692012083
BLACKLIST_ROLE_ID = 1430510098123587604
IP_REPLY_CATEGORY_ID = 1337503537004806335
TRANSCRIPT_CHANNEL_ID = 1350552425194324080

# ============================================================================
# LOGGING EXCLUSIONS
# ============================================================================

# Channels in these lists will be ignored for logging
EXCLUDED_CHANNEL_IDS = {
    1346833175762173962,
    1350552425194324080,
    1350141246227742901,
    1337503537508384770,
}

# Categories in these lists will be ignored for logging
EXCLUDED_CATEGORY_IDS = {
    1337503537286090875,
    1346816194086309908,
}

# ============================================================================
# TICKET SYSTEM
# ============================================================================

# Ticket types for dropdown selection
TICKET_TYPE_OPTIONS = [
    discord.SelectOption(label="Discord Issue", value="discord issue"),
    discord.SelectOption(label="Minecraft Issue", value="minecraft issue"),
    discord.SelectOption(label="Bug Report", value="bug report"),
    discord.SelectOption(label="Player Report", value="player report"),
    discord.SelectOption(label="Other", value="other"),
]

MAX_OPEN_TICKETS_PER_USER = 3
