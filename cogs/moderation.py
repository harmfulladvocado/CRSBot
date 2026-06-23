"""
Moderation commands.
"""

import discord
from discord.ext import commands

from config import GUILD_ID
from utils.helpers import member_text
from utils.logging import send_log


class Moderation(commands.Cog):
    """Prefix commands for server moderation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="warn")
    @commands.has_permissions(moderate_members=True)
    async def warn_member(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        if ctx.guild is None or ctx.guild.id != GUILD_ID:
            return
        # Log warning
        await send_log(
            self.bot,
            "Warning Create",
            f"Warned: {member_text(member)}\nModerator: {ctx.author}\nReason: {reason}",
        )
        await ctx.send(f"Warning logged for {member.mention}.")

    @warn_member.error
    async def warn_member_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You do not have permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!warn @member reason`")
        else:
            await ctx.send(f"Warn command error: {error}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
