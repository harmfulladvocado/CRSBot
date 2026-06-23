"""
Welcome behavior for new members: automatically assigns a role on join.
"""

import discord
from discord.ext import commands

from config import AUTO_JOIN_ROLE_ID, GUILD_ID
from utils.logging import send_log


class Welcome(commands.Cog):
    """Handles automatic role assignment when a member joins."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild.id != GUILD_ID:
            return

        role = member.guild.get_role(AUTO_JOIN_ROLE_ID)
        if role is None:
            await send_log(
                self.bot,
                "Auto-Role Error",
                f"Could not find role `{AUTO_JOIN_ROLE_ID}` to assign to {member.mention}.",
            )
            return

        try:
            await member.add_roles(role, reason="Automatic role on join")
        except discord.Forbidden:
            await send_log(
                self.bot,
                "Auto-Role Error",
                f"Missing permissions to assign {role.mention} to {member.mention}.",
            )
        except discord.HTTPException as error:
            await send_log(
                self.bot,
                "Auto-Role Error",
                f"Failed to assign {role.mention} to {member.mention}: {error}",
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
