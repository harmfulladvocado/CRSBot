"""
Verification command.

Posts a message with a button that, when clicked, removes the
unverified/quarantine role from the clicking member.
"""

import discord
from discord import app_commands
from discord.ext import commands

from config import GUILD_ID
from utils.helpers import member_text
from utils.logging import send_log

VERIFY_ROLE_ID = 1337503536371728406


class VerifyView(discord.ui.View):
    """Persistent view with the verify button. Re-used across restarts via bot.add_view()."""

    def __init__(self) -> None:
        # timeout=None + a fixed custom_id on the button is what makes this
        # persistent: it'll keep working after the bot restarts.
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        custom_id="verify_button",
    )
    async def verify_button(
            self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        guild = interaction.guild
        if guild is None or guild.id != GUILD_ID:
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Something went wrong reading your member info.", ephemeral=True
            )
            return

        role = guild.get_role(VERIFY_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "Verification role not found — let a moderator know.", ephemeral=True
            )
            return

        if role not in member.roles:
            await interaction.response.send_message(
                "You're already verified.", ephemeral=True
            )
            return

        try:
            await member.remove_roles(role, reason="Self-verified via button")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to remove that role — let a moderator know.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message("You're verified! ✅", ephemeral=True)

        await send_log(
            interaction.client,
            "Member Verified",
            f"Verified: {member_text(member)}",
        )


class Verification(commands.Cog):
    """Slash command to post the verification button message."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="verify-sendmsg",
        description="Post the verification button message in this channel.",
    )
    @app_commands.guilds(GUILD_ID)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def verify_sendmsg(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            return

        await interaction.channel.send(
            "Click The Button To Verify Yourself!", view=VerifyView()
        )
        await interaction.response.send_message(
            "Verification message posted.", ephemeral=True
        )

    @verify_sendmsg.error
    async def verify_sendmsg_error(
            self, interaction: discord.Interaction, error: app_commands.AppCommandError
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
    await bot.add_cog(Verification(bot))