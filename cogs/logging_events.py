"""
Server activity logging: channel, role, emoji, invite, member, and message
events are all mirrored to the configured log channel as embeds.
"""

from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands

from config import BOOST_ANNOUNCE_CHANNEL_ID, GUILD_ID, IP_REPLY_CATEGORY_ID
from utils.helpers import in_excluded_category, member_text
from utils.logging import send_log
import re


class LoggingEvents(commands.Cog):
    """Listens for server activity and mirrors it to the log channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != GUILD_ID or in_excluded_category(channel):
            return
        await send_log(self.bot, "Channel Create", f"Created: {channel.mention} (`{channel.id}`)")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id != GUILD_ID or in_excluded_category(channel):
            return
        await send_log(self.bot, "Channel Delete", f"Deleted: **{channel.name}** (`{channel.id}`)")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        if after.guild.id != GUILD_ID or in_excluded_category(after):
            return
        if before.name != after.name:
            details = f"Name: **{before.name}** -> **{after.name}**"
        else:
            details = f"Channel updated: {after.mention} (`{after.id}`)"
        await send_log(self.bot, "Channel Update", details)

    @commands.Cog.listener()
    async def on_guild_channel_pins_update(self, channel: discord.abc.GuildChannel, last_pin: Optional[datetime]) -> None:
        if channel.guild.id != GUILD_ID or in_excluded_category(channel):
            return
        when = f"<t:{int(last_pin.timestamp())}:F>" if last_pin else "Unknown"
        await send_log(
            self.bot,
            "Message Pin",
            f"Pins updated in {channel.mention if hasattr(channel, 'mention') else channel}. Last pin: {when}",
        )

    # ------------------------------------------------------------------
    # Emojis & guild settings
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: tuple[discord.Emoji, ...],
        after: tuple[discord.Emoji, ...],
    ) -> None:
        if guild.id != GUILD_ID:
            return

        before_ids = {e.id for e in before}
        after_ids = {e.id for e in after}

        # Log new emojis
        created = [e for e in after if e.id not in before_ids]
        deleted = [e for e in before if e.id not in after_ids]

        for emoji in created:
            await send_log(self.bot, "Emoji Create", f"Created emoji: {emoji} (`{emoji.id}`)")

        for emoji in deleted:
            await send_log(self.bot, "Emoji Delete", f"Deleted emoji: **{emoji.name}** (`{emoji.id}`)")

        # Log modified emojis
        changed = []
        by_id_before = {e.id: e for e in before}
        by_id_after = {e.id: e for e in after}
        for emoji_id in before_ids.intersection(after_ids):
            b = by_id_before[emoji_id]
            a = by_id_after[emoji_id]
            if b.name != a.name or b.available != a.available:
                changed.append((b, a))

        for b, a in changed:
            await send_log(self.bot, "Emoji Update", f"Emoji updated: **{b.name}** -> **{a.name}** (`{a.id}`)")

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if after.id != GUILD_ID:
            return
        if before.name != after.name:
            await send_log(self.bot, "Guild Update", f"Name changed: **{before.name}** -> **{after.name}**")
        else:
            await send_log(self.bot, "Guild Update", "Guild settings were updated.")

    # ------------------------------------------------------------------
    # Invites
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        guild = invite.guild
        channel = invite.channel
        if guild is None or guild.id != GUILD_ID:
            return
        if isinstance(channel, discord.abc.GuildChannel) and in_excluded_category(channel):
            return

        channel_text = channel.mention if isinstance(channel, discord.TextChannel) else str(channel)
        await send_log(
            self.bot,
            "Invite Create",
            f"Code: `{invite.code}`\nChannel: {channel_text}\nCreator: {invite.inviter or 'Unknown'}",
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        guild = invite.guild
        channel = invite.channel
        if guild is None or guild.id != GUILD_ID:
            return
        if isinstance(channel, discord.abc.GuildChannel) and in_excluded_category(channel):
            return

        await send_log(self.bot, "Invite Delete", f"Deleted invite code: `{invite.code}`")

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if guild.id != GUILD_ID:
            return
        await send_log(self.bot, "Member Ban Add", f"Banned: {user.mention if hasattr(user, 'mention') else user} (`{user.id}`)")

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        if guild.id != GUILD_ID:
            return
        await send_log(self.bot, "Member Ban Remove", f"Unbanned: {user.mention if hasattr(user, 'mention') else user} (`{user.id}`)")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild.id != GUILD_ID:
            return
        await send_log(self.bot, "Member Join", f"Joined: {member_text(member)}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.guild.id != GUILD_ID:
            return

        # Try to detect if member was kicked (check audit logs)
        kicked_by = None
        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target and entry.target.id == member.id:
                    age = datetime.now(timezone.utc) - entry.created_at
                    if age.total_seconds() <= 10:  # Kick happened within last 10 seconds
                        kicked_by = entry.user
                    break
        except discord.Forbidden:
            pass

        if kicked_by:
            await send_log(self.bot, "Member Kick", f"Kicked: **{member}** (`{member.id}`) by {kicked_by}")
        else:
            await send_log(self.bot, "Member Leave", f"Left: **{member}** (`{member.id}`)")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.guild.id != GUILD_ID:
            return

        # Check if member started/stopped boosting
        if before.premium_since is None and after.premium_since is not None:
            await send_log(self.bot, "Boost Create", f"{member_text(after)} started boosting the server.")
            await self._announce_boost(after)
        elif before.premium_since is not None and after.premium_since is None:
            await send_log(self.bot, "Boost Delete", f"{member_text(after)} stopped boosting the server.")

        # Check if member passed membership verification
        if before.pending and not after.pending:
            await send_log(self.bot, "Member Verification Passed", f"{member_text(after)} passed membership screening.")

        # Check if member timeout changed
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until is not None:
                await send_log(self.bot, "Member Mute", f"{member_text(after)} has been timed out until `{after.timed_out_until}`.")
            else:
                await send_log(self.bot, "Member Unmute", f"{member_text(after)} timeout was removed.")

        # Check if roles, nickname, or avatar changed
        if before.roles != after.roles or before.nick != after.nick or before.avatar != after.avatar:
            await send_log(self.bot, "Member Update", f"Updated member profile/roles: {member_text(after)}")

    async def _announce_boost(self, member: discord.Member) -> None:
        """Post a public boost announcement to the configured channel."""
        channel = member.guild.get_channel(BOOST_ANNOUNCE_CHANNEL_ID)
        if channel is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        await channel.send(f"{member.mention} Just **boosted** the server!")

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.guild.id != GUILD_ID:
            return
        if in_excluded_category(message.channel):
            return

        content = message.content if message.content else "<no text content>"
        await send_log(
            self.bot,
            "Message Delete",
            f"Author: {message.author}\nChannel: {message.channel.mention}\nContent: {content[:1500]}",
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages:
            return
        msg0 = messages[0]
        if msg0.guild is None or msg0.guild.id != GUILD_ID:
            return
        if in_excluded_category(msg0.channel):
            return

        await send_log(
            self.bot,
            "Message Delete Bulk",
            f"Deleted **{len(messages)}** messages in {msg0.channel.mention}",
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.guild is None or after.guild.id != GUILD_ID:
            return
        if in_excluded_category(after.channel):
            return
        # Only log if content actually changed
        if before.content == after.content:
            return

        await send_log(
            self.bot,
            "Message Update",
            f"Author: {after.author}\nChannel: {after.channel.mention}\nBefore: {before.content[:700]}\nAfter: {after.content[:700]}",
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Auto-reply with server IP when users ask in the configured category."""
        if message.author.bot:
            return

        if message.guild is None or message.guild.id != GUILD_ID:
            await self.bot.process_commands(message)
            return

        channel = message.channel
        category_id = None
        if isinstance(channel, discord.Thread):
            parent = channel.parent
            category_id = getattr(parent, "category_id", None) if parent else None
        else:
            category_id = getattr(channel, "category_id", None)

        if category_id == IP_REPLY_CATEGORY_ID:
            # Match standalone "ip" or "ip?" without triggering on words like "ship".
            if re.search(r"(?:^|\s)ip(?:\?|)(?:\s|$)", message.content, flags=re.IGNORECASE):
                await message.channel.send(
                    f"{message.author.mention} The IP is:\n"
                    "Bedrock    - CRSBox.bedrock.minehut.gg\n"
                    "Java           - CRSBox.minehut.gg"
                )

        await self.bot.process_commands(message)

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        if role.guild.id != GUILD_ID:
            return
        await send_log(self.bot, "Role Create", f"Created role: {role.mention} (`{role.id}`)")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        if role.guild.id != GUILD_ID:
            return
        await send_log(self.bot, "Role Delete", f"Deleted role: **{role.name}** (`{role.id}`)")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        if after.guild.id != GUILD_ID:
            return
        await send_log(self.bot, "Role Update", f"Updated role: **{before.name}** -> **{after.name}** (`{after.id}`)")


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingEvents(bot))
