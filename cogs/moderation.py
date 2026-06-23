"""
Moderation commands.
"""

import discord
from discord import app_commands
from discord.ext import commands

from config import GUILD_ID
from utils.helpers import member_text
from utils.logging import send_log
from utils.warnings_store import add_warning, remove_warning, get_warnings


class Moderation(commands.Cog):
    """Slash commands for server moderation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /warn
    # ------------------------------------------------------------------
    @app_commands.command(name="warn", description="Warn a member and log it.")
    @app_commands.guilds(GUILD_ID)
    @app_commands.describe(member="The member to warn", reason="Why they're being warned")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn_member(
            self,
            interaction: discord.Interaction,
            member: discord.Member,
            reason: str = "No reason provided",
    ) -> None:
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            return

        warning = add_warning(
            guild_id=interaction.guild.id,
            member_id=member.id,
            moderator_id=interaction.user.id,
            reason=reason,
        )

        await send_log(
            self.bot,
            "Warning Create",
            f"Warning #{warning.id} — {member_text(member)}\n"
            f"Moderator: {interaction.user}\nReason: {reason}",
        )
        await interaction.response.send_message(
            f"Warning #{warning.id} logged for {member.mention}."
        )

    @warn_member.error
    async def warn_member_error(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await self._handle_app_command_error(interaction, error)

    # ------------------------------------------------------------------
    # /unwarn
    # ------------------------------------------------------------------
    @app_commands.command(name="unwarn", description="Remove a previously issued warning by its ID.")
    @app_commands.guilds(GUILD_ID)
    @app_commands.describe(warning_id="The warning ID to remove (see /warnings)")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unwarn_member(
            self,
            interaction: discord.Interaction,
            warning_id: int,
    ) -> None:
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            return

        removed = remove_warning(guild_id=interaction.guild.id, warning_id=warning_id)

        if removed is None:
            await interaction.response.send_message(
                f"No warning with ID #{warning_id} found.", ephemeral=True
            )
            return

        member = interaction.guild.get_member(removed.member_id)
        member_display = member_text(member) if member else f"User ID {removed.member_id}"

        await send_log(
            self.bot,
            "Warning Remove",
            f"Warning #{removed.id} removed — {member_display}\n"
            f"Originally for: {removed.reason}\n"
            f"Removed by: {interaction.user}",
        )
        await interaction.response.send_message(f"Warning #{removed.id} has been removed.")

    @unwarn_member.error
    async def unwarn_member_error(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await self._handle_app_command_error(interaction, error)

    # ------------------------------------------------------------------
    # /warnings
    # ------------------------------------------------------------------
    @app_commands.command(name="warnings", description="List a member's active warnings.")
    @app_commands.guilds(GUILD_ID)
    @app_commands.describe(member="The member to look up")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def list_warnings(
            self,
            interaction: discord.Interaction,
            member: discord.Member,
    ) -> None:
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            return

        warnings = get_warnings(guild_id=interaction.guild.id, member_id=member.id)

        if not warnings:
            await interaction.response.send_message(
                f"{member.mention} has no active warnings.", ephemeral=True
            )
            return

        lines = [f"**#{w.id}** — {w.reason}" for w in warnings]
        await interaction.response.send_message(
            f"Warnings for {member.mention}:\n" + "\n".join(lines),
            ephemeral=True,
            )

    @list_warnings.error
    async def list_warnings_error(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await self._handle_app_command_error(interaction, error)

    # ------------------------------------------------------------------
    # Shared error handling
    # ------------------------------------------------------------------
    @staticmethod
    async def _handle_app_command_error(
            interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "You do not have permission to use this command."
        else:
            message = f"Command error: {error}"

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))