import re
import asyncio
import os
import io
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands


def load_local_env() -> None:
	#Load key=value pairs from a local .env file if present.
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

GUILD_ID = 1337503536371728406
LOG_CHANNEL_ID = 1346833175762173962
TICKET_CATEGORY_ID = 1337503537286090875
SUPPORT_STAFF_ROLE_ID = 1346814062692012083
BLACKLIST_ROLE_ID = 1430510098123587604
IP_REPLY_CATEGORY_ID = 1337503537004806335
TRANSCRIPT_CHANNEL_ID = 1350552425194324080

# Channels and categories in these lists will be ignored for logging
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

# ticket types for dropdown selection
TICKET_TYPE_OPTIONS = [
	discord.SelectOption(label="Discord Issue", value="discord issue"),
	discord.SelectOption(label="Minecraft Issue", value="minecraft issue"),
	discord.SelectOption(label="Bug Report", value="bug report"),
	discord.SelectOption(label="Player Report", value="player report"),
	discord.SelectOption(label="Other", value="other"),
]

# you can read this bro
MAX_OPEN_TICKETS_PER_USER = 3


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def ts() -> str:
	return f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>"


# Sanitizes user input into a valid Discord channel name
def safe_channel_name(value: str) -> str:
	#Create a channel-safe name segment from user input.
	cleaned = re.sub(r"[^a-z0-9-]", "-", value.lower())  # Replace invalid chars with dashes
	cleaned = re.sub(r"-+", "-", cleaned).strip("-")  # Remove consecutive dashes and trim ends
	return cleaned[:40] if cleaned else "ticket"  # Limit to 40 chars, fallback to "ticket"


# Checks if a channel should be excluded from logging
def in_excluded_category(channel: Optional[discord.abc.GuildChannel]) -> bool:
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


# Formats member info for logging (mention, name, ID)
def member_text(member: discord.Member) -> str:
	return f"{member.mention} ({member} | `{member.id}`)"


# Finds the next sequential ticket number for a user (001, 002, etc.)
def next_ticket_number(guild: discord.Guild, user_part: str) -> int:
	pattern = re.compile(rf"^{re.escape(user_part)}-(\d{{3}})$")
	max_found = 0

	for channel in guild.text_channels:
		match = pattern.match(channel.name)
		if match:
			max_found = max(max_found, int(match.group(1)))

	return max_found + 1


# Counts how many open tickets a user currently has
def count_open_tickets(guild: discord.Guild, user_part: str) -> int:
	#Count current open ticket channels for a user in the ticket category."
	category = guild.get_channel(TICKET_CATEGORY_ID)
	if not isinstance(category, discord.CategoryChannel):
		return 0

	# Count matching channels in ticket category
	pattern = re.compile(rf"^{re.escape(user_part)}-(\d{{3}})$")
	return sum(1 for channel in category.text_channels if pattern.match(channel.name))


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


# ============================================================================
# LOGGING FUNCTIONS
# ============================================================================

# Sends a formatted log message to the log channel
async def send_log(title: str, description: str) -> None:
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


# ============================================================================
# TICKET UI COMPONENTS
# ============================================================================

# Confirmation dialog for closing a ticket
class CloseTicketConfirmView(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=60)

	# Red "Confirm Close" button
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
				"Ticket Transcript Error",
				f"Failed to save transcript for {channel.mention} (`{channel.id}`): {error}",
			)
		await asyncio.sleep(5)
		# Delete the ticket channel
		await channel.delete(reason=f"Ticket closed by {interaction.user} ({interaction.user.id})")

	# Gray "Cancel" button
	@discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
	async def cancel_close(self, interaction: discord.Interaction, _: discord.ui.Button):
		await interaction.response.send_message("Close cancelled.", ephemeral=True)


# Close button shown in ticket channels
class CloseTicketView(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=None)  # Never timeout - persists across restarts

	# Red "Close Ticket" button
	@discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket:close")
	async def close_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
		# Show confirmation dialog
		await interaction.response.send_message(
			"Are you sure you want to close this ticket?",
			view=CloseTicketConfirmView(),
			ephemeral=True,
		)


# Modal for general ticket creation (Discord/Bug issues)
class TicketReasonModal(discord.ui.Modal, title="Create Ticket"):
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

	# Called when user submits the modal
	async def on_submit(self, interaction: discord.Interaction):
		await create_ticket(
			interaction=interaction,
			ticket_type=self.ticket_type,
			reason=self.reason.value,
		)


# Modal for Minecraft issue tickets - requires username
class MinecraftIssueModal(discord.ui.Modal, title="Create Ticket"):
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

	# Submit and create ticket with username included
	async def on_submit(self, interaction: discord.Interaction):
		await create_ticket(
			interaction=interaction,
			ticket_type=self.ticket_type,
			reason=self.reason.value,
			minecraft_username=self.minecraft_username.value.strip(),
		)


# Modal for player report tickets - requires reported player name
class PlayerReportModal(discord.ui.Modal, title="Create Ticket"):
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

	# Submit and create ticket with reported player name
	async def on_submit(self, interaction: discord.Interaction):
		await create_ticket(
			interaction=interaction,
			ticket_type=self.ticket_type,
			reason=self.reason.value,
			reported_player=self.reported_player.value.strip(),
		)


# Dropdown for selecting ticket type
class TicketTypeSelect(discord.ui.Select):
	def __init__(self):
		super().__init__(
			placeholder="Select your ticket type",
			min_values=1,
			max_values=1,
			options=TICKET_TYPE_OPTIONS,
			custom_id="ticket:type-select",
		)

	# Handle selection of ticket type
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


# View containing the ticket type dropdown
class TicketTypeSelectView(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=120)  # 2 minute timeout
		self.add_item(TicketTypeSelect())


# Main "Open Ticket" button shown in message
class OpenTicketView(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=None)  # Never timeout - persists across restarts

	# Blue "Open Ticket" button
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

# Creates a new ticket channel with all appropriate settings
async def create_ticket(
	interaction: discord.Interaction,
	ticket_type: str,
	reason: str,
	minecraft_username: str | None = None,
	reported_player: str | None = None,
):
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
		"Ticket Create",
		f"User: {member_text(interaction.user) if isinstance(interaction.user, discord.Member) else interaction.user}\n"
		f"Type: {ticket_type}\n"
		f"Reason: {reason}",
	)


# ============================================================================
# EVENT HANDLERS - LOGGING
# ============================================================================

# Ready event - called when bot is connected
@bot.event
async def on_ready():
	print(f"Logged in as {bot.user}")


# When a channel is created
@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel) -> None:
	if channel.guild.id != GUILD_ID or in_excluded_category(channel):
		return
	await send_log("Channel Create", f"Created: {channel.mention} (`{channel.id}`)")


# When a channel is deleted
@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel) -> None:
	if channel.guild.id != GUILD_ID or in_excluded_category(channel):
		return
	await send_log("Channel Delete", f"Deleted: **{channel.name}** (`{channel.id}`)")


# When a channel is updated (name, topic, etc.)
@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
	if after.guild.id != GUILD_ID or in_excluded_category(after):
		return
	if before.name != after.name:
		details = f"Name: **{before.name}** -> **{after.name}**"
	else:
		details = f"Channel updated: {after.mention} (`{after.id}`)"
	await send_log("Channel Update", details)


# When server emojis are modified
@bot.event
async def on_guild_emojis_update(
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
		await send_log("Emoji Create", f"Created emoji: {emoji} (`{emoji.id}`)")

	for emoji in deleted:
		await send_log("Emoji Delete", f"Deleted emoji: **{emoji.name}** (`{emoji.id}`)")

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
		await send_log("Emoji Update", f"Emoji updated: **{b.name}** -> **{a.name}** (`{a.id}`)")


# When guild (server) settings are updated
@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild) -> None:
	if after.id != GUILD_ID:
		return
	if before.name != after.name:
		await send_log("Guild Update", f"Name changed: **{before.name}** -> **{after.name}**")
	else:
		await send_log("Guild Update", "Guild settings were updated.")


# When an invite is created
@bot.event
async def on_invite_create(invite: discord.Invite) -> None:
	guild = invite.guild
	channel = invite.channel
	if guild is None or guild.id != GUILD_ID:
		return
	if isinstance(channel, discord.abc.GuildChannel) and in_excluded_category(channel):
		return

	channel_text = channel.mention if isinstance(channel, discord.TextChannel) else str(channel)
	await send_log(
		"Invite Create",
		f"Code: `{invite.code}`\nChannel: {channel_text}\nCreator: {invite.inviter or 'Unknown'}",
	)


# When an invite is deleted
@bot.event
async def on_invite_delete(invite: discord.Invite) -> None:
	guild = invite.guild
	channel = invite.channel
	if guild is None or guild.id != GUILD_ID:
		return
	if isinstance(channel, discord.abc.GuildChannel) and in_excluded_category(channel):
		return

	await send_log("Invite Delete", f"Deleted invite code: `{invite.code}`")


# When a member is banned
@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
	if guild.id != GUILD_ID:
		return
	await send_log("Member Ban Add", f"Banned: {user.mention if hasattr(user, 'mention') else user} (`{user.id}`)")


# When a member is unbanned
@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User) -> None:
	if guild.id != GUILD_ID:
		return
	await send_log("Member Ban Remove", f"Unbanned: {user.mention if hasattr(user, 'mention') else user} (`{user.id}`)")


# When a member joins the server
@bot.event
async def on_member_join(member: discord.Member) -> None:
	if member.guild.id != GUILD_ID:
		return
	await send_log("Member Join", f"Joined: {member_text(member)}")


# When a member leaves or is kicked
@bot.event
async def on_member_remove(member: discord.Member) -> None:
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
		await send_log("Member Kick", f"Kicked: **{member}** (`{member.id}`) by {kicked_by}")
	else:
		await send_log("Member Leave", f"Left: **{member}** (`{member.id}`)")


# When a member is updated (roles, nickname, boost status, timeout, etc.)
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
	if after.guild.id != GUILD_ID:
		return

	# Check if member started/stopped boosting
	if before.premium_since is None and after.premium_since is not None:
		await send_log("Boost Create", f"{member_text(after)} started boosting the server.")
	elif before.premium_since is not None and after.premium_since is None:
		await send_log("Boost Delete", f"{member_text(after)} stopped boosting the server.")

	# Check if member passed membership verification
	if before.pending and not after.pending:
		await send_log("Member Verification Passed", f"{member_text(after)} passed membership screening.")

	# Check if member timeout changed
	if before.timed_out_until != after.timed_out_until:
		if after.timed_out_until is not None:
			await send_log("Member Mute", f"{member_text(after)} has been timed out until `{after.timed_out_until}`.")
		else:
			await send_log("Member Unmute", f"{member_text(after)} timeout was removed.")

	# Check if roles, nickname, or avatar changed
	if before.roles != after.roles or before.nick != after.nick or before.avatar != after.avatar:
		await send_log("Member Update", f"Updated member profile/roles: {member_text(after)}")


# When a message is deleted
@bot.event
async def on_message_delete(message: discord.Message) -> None:
	if message.guild is None or message.guild.id != GUILD_ID:
		return
	if in_excluded_category(message.channel):
		return

	content = message.content if message.content else "<no text content>"
	await send_log(
		"Message Delete",
		f"Author: {message.author}\nChannel: {message.channel.mention}\nContent: {content[:1500]}",
	)


# When multiple messages are deleted at once
@bot.event
async def on_bulk_message_delete(messages: list[discord.Message]) -> None:
	if not messages:
		return
	msg0 = messages[0]
	if msg0.guild is None or msg0.guild.id != GUILD_ID:
		return
	if in_excluded_category(msg0.channel):
		return

	await send_log(
		"Message Delete Bulk",
		f"Deleted **{len(messages)}** messages in {msg0.channel.mention}",
	)


# When message pins are updated
@bot.event
async def on_guild_channel_pins_update(channel: discord.abc.GuildChannel, last_pin: Optional[datetime]) -> None:
	if channel.guild.id != GUILD_ID or in_excluded_category(channel):
		return
	when = f"<t:{int(last_pin.timestamp())}:F>" if last_pin else "Unknown"
	await send_log("Message Pin", f"Pins updated in {channel.mention if hasattr(channel, 'mention') else channel}. Last pin: {when}")


# When a message is edited
@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
	if after.guild is None or after.guild.id != GUILD_ID:
		return
	if in_excluded_category(after.channel):
		return
	# Only log if content actually changed
	if before.content == after.content:
		return

	await send_log(
		"Message Update",
		f"Author: {after.author}\nChannel: {after.channel.mention}\nBefore: {before.content[:700]}\nAfter: {after.content[:700]}",
	)


# Auto-reply with server IP when users ask in the configured category
@bot.event
async def on_message(message: discord.Message) -> None:
	if message.author.bot:
		return

	if message.guild is None or message.guild.id != GUILD_ID:
		await bot.process_commands(message)
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
				"Java       - CRSBox.minehut.gg"
			)

	await bot.process_commands(message)


# When a role is created
@bot.event
async def on_guild_role_create(role: discord.Role) -> None:
	if role.guild.id != GUILD_ID:
		return
	await send_log("Role Create", f"Created role: {role.mention} (`{role.id}`)")


# When a role is deleted
@bot.event
async def on_guild_role_delete(role: discord.Role) -> None:
	if role.guild.id != GUILD_ID:
		return
	await send_log("Role Delete", f"Deleted role: **{role.name}** (`{role.id}`)")


# When a role is updated
@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role) -> None:
	if after.guild.id != GUILD_ID:
		return
	await send_log("Role Update", f"Updated role: **{before.name}** -> **{after.name}** (`{after.id}`)")


# ============================================================================
# COMMANDS
# ============================================================================

# Warn command - logs a warning for a member (prefix command)
@bot.command(name="warn")
@commands.has_permissions(moderate_members=True)
async def warn_member(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
	if ctx.guild is None or ctx.guild.id != GUILD_ID:
		return
	# Log warning
	await send_log(
		"Warning Create",
		f"Warned: {member_text(member)}\nModerator: {ctx.author}\nReason: {reason}",
	)
	await ctx.send(f"Warning logged for {member.mention}.")


# Error handler for warn command
@warn_member.error
async def warn_member_error(ctx: commands.Context, error: commands.CommandError) -> None:
	if isinstance(error, commands.MissingPermissions):
		await ctx.send("You do not have permission to use this command.")
	elif isinstance(error, commands.MissingRequiredArgument):
		await ctx.send("Usage: `!warn @member reason`")
	else:
		await ctx.send(f"Warn command error: {error}")


# Create slash command group for ticket system
tickets_group = app_commands.Group(name="tickets", description="Ticket system commands")


# Send ticket starter message command
@tickets_group.command(name="sendmsg", description="Send the ticket starter message with button")
@app_commands.checks.has_permissions(manage_channels=True)
async def send_ticket_message(interaction: discord.Interaction):
	if interaction.channel is None:
		await interaction.response.send_message("I couldn't find this channel.", ephemeral=True)
		return

	# Send the "Open Ticket" button to current channel
	await interaction.channel.send(
		"Need help? Click the button below to create a ticket.",
		view=OpenTicketView(),
	)
	await interaction.response.send_message("Ticket message sent.", ephemeral=True)


# Error handler for send_ticket_message command
@send_ticket_message.error
async def send_ticket_message_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
	if isinstance(error, app_commands.MissingPermissions):
		await interaction.response.send_message("You need Manage Channels permission to use this.", ephemeral=True)
		return

	await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)


# Add ticket commands to bot
bot.tree.add_command(tickets_group)


# ============================================================================
# BOT STARTUP
# ============================================================================

# Setup hook runs once when bot is ready - syncs commands and adds persistent views
async def setup_hook():
	# Add persistent views (survive bot restarts)
	bot.add_view(OpenTicketView())
	bot.add_view(CloseTicketView())

	# Sync slash commands to test guild
	if GUILD_ID:
		guild_obj = discord.Object(id=GUILD_ID)
		bot.tree.copy_global_to(guild=guild_obj)
		await bot.tree.sync(guild=guild_obj)
		print(f"Synced commands to guild: {GUILD_ID}")
	else:
		await bot.tree.sync()
		print("Synced global commands.")


# Assign setup hook to bot
bot.setup_hook = setup_hook

# Validate token exists
if not TOKEN or TOKEN.isdigit():
	raise ValueError("Invalid bot token. Set DISCORD_BOT_TOKEN in your environment.")

# Start the bot
bot.run(TOKEN)