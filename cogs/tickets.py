"""
Ticket system: open-ticket button, type dropdown, type-specific modals,
ticket creation, and the close/confirm flow with transcript saving.
"""

import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import (
    BLACKLIST_ROLE_ID,
    MAX_OPEN_TICKETS_PER_USER,
    SUPPORT_STAFF_ROLE_ID,
    TICKET_CATEGORY_ID,
    TICKET_TYPE_OPTIONS,
)
from utils.helpers import count_open_tickets, member_text, next_ticket_number, safe_channel_name
from utils.logging import send_log, send_ticket_transcript


# ============================================================================
# TICKET UI COMPONENTS
# ============================================================================

class CloseTicketConfirmView(discord.ui.View):
    """Confirmation dialog for closing a ticket."""

    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirm Close", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, _: discord.ui.Button):
        channel = interaction.channel
        if channel is None:
            await interaction.response.send_message("I can't find this channel.", ephemeral=True)
            return

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("This can only be used inside a ticket channel.", ephemeral=True)
            return

        # Notify user and wait 5 seconds before deletion
        await interaction.response.send_message("Ticket confirmed. Closing in 5 seconds...", ephemeral=True)
        await channel.send(f"🔒 Ticket closed by {interaction.user.mention}. This channel will be deleted in 5 seconds.")
        try:
            await send_ticket_transcript(channel, interaction.user)
        except Exception as error:
            await channel.send("Failed to save transcript before close. Staff should check bot permissions for the transcript channel.")
            await send_log(
                interaction.client,
                "Ticket Transcript Error",
                f"Failed to save transcript for {channel.mention} (`{channel.id}`): {error}",
            )
        await asyncio.sleep(5)
        # Delete the ticket channel
        await channel.delete(reason=f"Ticket closed by {interaction.user} ({interaction.user.id})")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_message("Close cancelled.", ephemeral=True)


class CloseTicketView(discord.ui.View):
    """Close button shown in ticket channels. Persistent across restarts."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_message(
            "Are you sure you want to close this ticket?",
            view=CloseTicketConfirmView(),
            ephemeral=True,
        )


class TicketReasonModal(discord.ui.Modal, title="Create Ticket"):
    """Modal for general ticket creation (Discord/Bug issues)."""

    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Tell us what you need help with.",
        required=True,
        min_length=3,
        max_length=500,
    )

    def __init__(self, ticket_type: str):
        super().__init__()
        self.ticket_type = ticket_type

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(
            interaction=interaction,
            ticket_type=self.ticket_type,
            reason=self.reason.value,
        )


class MinecraftIssueModal(discord.ui.Modal, title="Create Ticket"):
    """Modal for Minecraft issue tickets - requires username."""

    minecraft_username = discord.ui.TextInput(
        label="Your Minecraft Username",
        style=discord.TextStyle.short,
        placeholder="Example: Steve",
        required=True,
        min_length=3,
        max_length=16,
    )

    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Tell us what happened.",
        required=True,
        min_length=3,
        max_length=500,
    )

    def __init__(self, ticket_type: str):
        super().__init__()
        self.ticket_type = ticket_type

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(
            interaction=interaction,
            ticket_type=self.ticket_type,
            reason=self.reason.value,
            minecraft_username=self.minecraft_username.value.strip(),
        )


class PlayerReportModal(discord.ui.Modal, title="Create Ticket"):
    """Modal for player report tickets - requires reported player name."""

    reported_player = discord.ui.TextInput(
        label="Player You're Reporting",
        style=discord.TextStyle.short,
        placeholder="Enter their username",
        required=True,
        min_length=2,
        max_length=32,
    )

    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Explain what this player did.",
        required=True,
        min_length=3,
        max_length=500,
    )

    def __init__(self, ticket_type: str):
        super().__init__()
        self.ticket_type = ticket_type

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(
            interaction=interaction,
            ticket_type=self.ticket_type,
            reason=self.reason.value,
            reported_player=self.reported_player.value.strip(),
        )


class TicketTypeSelect(discord.ui.Select):
    """Dropdown for selecting ticket type."""

    def __init__(self):
        super().__init__(
            placeholder="Select your ticket type",
            min_values=1,
            max_values=1,
            options=TICKET_TYPE_OPTIONS,
            custom_id="ticket:type-select",
        )

    async def callback(self, interaction: discord.Interaction):
        # Check if user is blacklisted
        if isinstance(interaction.user, discord.Member) and any(role.id == BLACKLIST_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("You are blacklisted from creating tickets.", ephemeral=True)
            return

        # Check ticket limit
        guild = interaction.guild
        if guild is not None:
            user_part = safe_channel_name(interaction.user.name)
            open_count = count_open_tickets(guild, user_part)
            if open_count >= MAX_OPEN_TICKETS_PER_USER:
                await interaction.response.send_message(
                    f"You already have {MAX_OPEN_TICKETS_PER_USER} open tickets. Please close one before creating another.",
                    ephemeral=True,
                )
                return

        # Show appropriate modal based on ticket type
        selected_type = self.values[0]
        if selected_type == "minecraft issue":
            await interaction.response.send_modal(MinecraftIssueModal(ticket_type=selected_type))
            return

        if selected_type == "player report":
            await interaction.response.send_modal(PlayerReportModal(ticket_type=selected_type))
            return

        # Default modal for other types
        await interaction.response.send_modal(TicketReasonModal(ticket_type=selected_type))


class TicketTypeSelectView(discord.ui.View):
    """View containing the ticket type dropdown."""

    def __init__(self):
        super().__init__(timeout=120)  # 2 minute timeout
        self.add_item(TicketTypeSelect())


class OpenTicketView(discord.ui.View):
    """Main 'Open Ticket' button shown in message. Persistent across restarts."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
        # Check if user is blacklisted
        if isinstance(interaction.user, discord.Member) and any(role.id == BLACKLIST_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("You are blacklisted from creating tickets.", ephemeral=True)
            return

        # Check ticket limit
        guild = interaction.guild
        if guild is not None:
            user_part = safe_channel_name(interaction.user.name)
            open_count = count_open_tickets(guild, user_part)
            if open_count >= MAX_OPEN_TICKETS_PER_USER:
                await interaction.response.send_message(
                    f"You already have {MAX_OPEN_TICKETS_PER_USER} open tickets. Please close one before creating another.",
                    ephemeral=True,
                )
                return

        # Show ticket type selection dropdown
        await interaction.response.send_message(
            "Choose your ticket type from the dropdown:",
            view=TicketTypeSelectView(),
            ephemeral=True,
        )


# ============================================================================
# TICKET CREATION
# ============================================================================

async def create_ticket(
    interaction: discord.Interaction,
    ticket_type: str,
    reason: str,
    minecraft_username: str | None = None,
    reported_player: str | None = None,
):
    """Creates a new ticket channel with all appropriate settings."""
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    # Check if user is blacklisted
    member = interaction.user if isinstance(interaction.user, discord.Member) else guild.get_member(interaction.user.id)
    if member is not None and any(role.id == BLACKLIST_ROLE_ID for role in member.roles):
        await interaction.response.send_message(
            "You are blacklisted from creating tickets.",
            ephemeral=True,
        )
        return

    # Check if user has reached ticket limit
    user_part = safe_channel_name(interaction.user.name)
    open_count = count_open_tickets(guild, user_part)
    if open_count >= MAX_OPEN_TICKETS_PER_USER:
        await interaction.response.send_message(
            f"You already have {MAX_OPEN_TICKETS_PER_USER} open tickets. Please close one before creating another.",
            ephemeral=True,
        )
        return

    # Get ticket category
    category = guild.get_channel(TICKET_CATEGORY_ID)
    if not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message(
            f"Ticket category `{TICKET_CATEGORY_ID}` was not found.",
            ephemeral=True,
        )
        return

    # Set up channel permissions - only user and support staff can see
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),  # Hide from everyone
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),  # Bot access
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),  # Creator access
    }

    # Add support staff role if it exists
    support_role = guild.get_role(SUPPORT_STAFF_ROLE_ID)
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        )

    # Create channel with format username-### (e.g., john-001)
    ticket_number = next_ticket_number(guild, user_part)
    channel_name = f"{user_part}-{ticket_number:03d}"

    ticket_channel = await guild.create_text_channel(
        name=channel_name[:95],
        category=category,
        overwrites=overwrites,
        reason=f"Ticket created by {interaction.user} ({interaction.user.id})",
    )

    # Build the initial message
    opened_at = f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>"
    extra_lines = ""
    if minecraft_username:
        extra_lines += "Minecraft Username:\n"
        extra_lines += f"{minecraft_username}\n"
    if reported_player:
        extra_lines += "Reported Player:\n"
        extra_lines += f"{reported_player}\n"

    initial_message = (
        "🎫 Ticket Created\n"
        f"Thanks for opening a ticket, {interaction.user.mention}\n"
        "We've received your request and will get back to you as soon as possible.\n"
        "Type:\n"
        f"{ticket_type.strip()}\n"
        f"{extra_lines}"
        "Reason:\n"
        f"{reason}\n"
        f"Thanks for being patient! - {opened_at}\n\n"
        "If a staff member is not here yet, please wait a little while. "
        "Our team will respond as soon as possible."
    )

    # Send initial message and ping support staff
    ping_text = f"<@&{SUPPORT_STAFF_ROLE_ID}>"
    await ticket_channel.send(
        ping_text,
        allowed_mentions=discord.AllowedMentions(roles=True),
    )
    # Send ticket info with close button
    await ticket_channel.send(initial_message, view=CloseTicketView())
    # Confirm to user
    await interaction.response.send_message(
        f"Your ticket was created: {ticket_channel.mention}",
        ephemeral=True,
    )

    # Log ticket creation
    await send_log(
        interaction.client,
        "Ticket Create",
        f"User: {member_text(interaction.user) if isinstance(interaction.user, discord.Member) else interaction.user}\n"
        f"Type: {ticket_type}\n"
        f"Reason: {reason}",
    )


# ============================================================================
# COG
# ============================================================================

class Tickets(commands.Cog):
    """Slash commands for managing the ticket system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    tickets_group = app_commands.Group(name="tickets", description="Ticket system commands")

    @tickets_group.command(name="sendmsg", description="Send the ticket starter message with button")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def send_ticket_message(self, interaction: discord.Interaction):
        if interaction.channel is None:
            await interaction.response.send_message("I couldn't find this channel.", ephemeral=True)
            return

        # Send the "Open Ticket" button to current channel
        await interaction.channel.send(
            "Need help? Click the button below to create a ticket.",
            view=OpenTicketView(),
        )
        await interaction.response.send_message("Ticket message sent.", ephemeral=True)

    @send_ticket_message.error
    async def send_ticket_message_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You need Manage Channels permission to use this.", ephemeral=True)
            return

        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
