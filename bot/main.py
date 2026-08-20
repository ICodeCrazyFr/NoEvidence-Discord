"""Discord moderation scanner bot (bot account) - regex-only detection

Requires:
- discord.py v2
- python-dotenv (optional)

Usage:
- Set DISCORD_BOT_TOKEN env var or create a .env file with DISCORD_BOT_TOKEN=...
- Ensure "Message Content Intent" is enabled for the bot in the Developer Portal
- Invite the bot to servers with: View Channels, Read Message History, Send Messages
  (Manage Messages is required if you want the bot to delete other users' messages)

Commands (prefix: !):
- !scan <target_user_id> : Scans all guilds the bot is in for messages by the given user ID that match rules
- !confirm_delete DELETE ALL : After a scan, deletes matching messages where the bot has permission
- !export_scan : Sends a JSON file of last scan results to the invoker via DM

Notes:
- This bot only scans guilds it belongs to and only channels where it has permission to view and read history.
- Scanning full histories can be time-consuming; set SCAN_LIMIT_PER_CHANNEL env var to limit messages per channel.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
from collections import defaultdict
from typing import Dict, List, Optional

import discord
from discord.ext import commands

# --- Configuration ---
BOT_PREFIX = "!"
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True

# Create bot
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moderation_bot")

# Load detection rules from JSON file
RULES_PATH = os.environ.get("DETECTION_RULES_PATH", "detection_rules.json")
try:
    with open(RULES_PATH, "r", encoding="utf-8") as rf:
        DETECTION_RULES = json.load(rf)
except FileNotFoundError:
    logger.warning("detection_rules.json not found; starting with empty rules")
    DETECTION_RULES = {}

# Compile regexes
COMPILED_RULES: Dict[str, List[re.Pattern]] = {}
for cat, meta in DETECTION_RULES.items():
    patterns = meta.get("patterns", [])
    COMPILED_RULES[cat] = [re.compile(p, flags=re.IGNORECASE) for p in patterns]

# Scan limits
SCAN_LIMIT_PER_CHANNEL_ENV = os.environ.get("SCAN_LIMIT_PER_CHANNEL")
SCAN_LIMIT_PER_CHANNEL: Optional[int] = int(SCAN_LIMIT_PER_CHANNEL_ENV) if SCAN_LIMIT_PER_CHANNEL_ENV else None
CHANNEL_DELAY = float(os.environ.get("CHANNEL_DELAY", "0.8"))

# In-memory storage for last scan results per invoker
# invoker_id -> { guild_id: [message, ...] }
last_scans: Dict[int, Dict[int, List[discord.Message]]] = {}


def regex_detect(content: Optional[str]) -> List[str]:
    """Return list of categories that matched the content."""
    matches: List[str] = []
    if not content:
        return matches
    for cat, patterns in COMPILED_RULES.items():
        for pat in patterns:
            try:
                if pat.search(content):
                    matches.append(cat)
                    break
            except re.error:
                continue
    return matches


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (id={bot.user.id})")


@bot.command(name="scan")
@commands.guild_only()
async def scan_command(ctx: commands.Context, target_user_id: int):
    """Scan all guilds the bot is in for messages authored by target_user_id matching the rules."""
    invoker_id = ctx.author.id
    await ctx.send(f"Starting scan for user ID {target_user_id}. This may take a while...")

    results_by_guild: Dict[int, List[discord.Message]] = defaultdict(list)
    total_checked = 0
    total_matches = 0

    for guild in bot.guilds:
        guild_matches: List[discord.Message] = []
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)
            if not (perms.view_channel and perms.read_message_history):
                continue

            try:
                async for message in channel.history(limit=SCAN_LIMIT_PER_CHANNEL, oldest_first=True):
                    total_checked += 1
                    if message.author and message.author.id == target_user_id:
                        cats = regex_detect(message.content)
                        if cats:
                            guild_matches.append(message)
                            total_matches += 1
                await asyncio.sleep(CHANNEL_DELAY)
            except discord.Forbidden:
                continue
            except discord.HTTPException as e:
                logger.exception(f"HTTP error reading {channel} in {guild.name}: {e}")
                continue

        if guild_matches:
            results_by_guild[guild.id] = guild_matches

    last_scans[invoker_id] = results_by_guild

    if not results_by_guild:
        await ctx.send(f"Scan complete. No matching messages found for user {target_user_id}. Checked ~{total_checked} messages.")
        return

    # Build summary
    lines = [f"Scan complete. Detected {total_matches} matching message(s) from user {target_user_id}.", "Per-server breakdown:"]
    for gid, msgs in results_by_guild.items():
        guild = bot.get_guild(gid)
        gname = guild.name if guild else f"(unknown {gid})"
        lines.append(f"- {gname}: {len(msgs)}")

    lines.append("")
    lines.append(f"To delete these messages where I have permission, run: `{BOT_PREFIX}confirm_delete DELETE ALL`")
    lines.append("This will only delete messages in channels where I have Manage Messages permission.")

    await ctx.send("\n".join(lines))


@bot.command(name="confirm_delete")
@commands.guild_only()
async def confirm_delete_command(ctx: commands.Context, *, confirmation: str = ""):
    invoker_id = ctx.author.id
    if invoker_id not in last_scans or not last_scans[invoker_id]:
        await ctx.send("No stored scan results for you. Run the scan command first.")
        return

    if confirmation.strip() != "DELETE ALL":
        await ctx.send("Confirmation did not match. To delete, run: `!confirm_delete DELETE ALL` (exact).")
        return

    results_by_guild = last_scans[invoker_id]
    total_to_delete = sum(len(v) for v in results_by_guild.values())
    await ctx.send(f"Attempting to delete {total_to_delete} message(s) where I have permission...")

    deleted = 0
    failed = 0

    for gid, messages in results_by_guild.items():
        for message in messages:
            try:
                channel = message.channel
                perms = channel.permissions_for(channel.guild.me)
                if not perms.manage_messages and message.author.id != bot.user.id:
                    failed += 1
                    continue
                await message.delete()
                deleted += 1
                await asyncio.sleep(0.2)
            except discord.Forbidden:
                failed += 1
            except discord.HTTPException:
                failed += 1

    # Clear stored scan
    last_scans[invoker_id] = {}
    await ctx.send(f"Deletion complete. Deleted: {deleted}. Failed/Skipped: {failed}.")


@bot.command(name="export_scan")
@commands.guild_only()
async def export_scan(ctx: commands.Context):
    invoker_id = ctx.author.id
    if invoker_id not in last_scans or not last_scans[invoker_id]:
        await ctx.send("No scan results stored for you.")
        return

    export = {}
    for gid, msgs in last_scans[invoker_id].items():
        guild = bot.get_guild(gid)
        gname = guild.name if guild else str(gid)
        export[gname] = [
            {
                "message_id": m.id,
                "channel_id": m.channel.id,
                "channel_name": getattr(m.channel, "name", str(m.channel.id)),
                "created_at": m.created_at.isoformat(),
                "content_snippet": (m.content[:300] + "…") if m.content and len(m.content) > 300 else (m.content or "")
            }
            for m in msgs
        ]

    payload = json.dumps(export, indent=2)
    bio = io.BytesIO(payload.encode("utf-8"))
    bio.seek(0)
    try:
        await ctx.author.send(file=discord.File(fp=bio, filename="scan_export.json"))
        await ctx.send("Exported scan results to your DMs.")
    except discord.Forbidden:
        await ctx.send("Could not send you a DM. Please ensure your DMs are open to this bot.")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("Set DISCORD_BOT_TOKEN environment variable or in .env file")
        raise SystemExit(1)
    bot.run(TOKEN)
