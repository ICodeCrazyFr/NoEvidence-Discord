from __future__ import annotations
import os
import json
import time
import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import aiofiles
import discord
from discord.ext import commands, tasks
from colorama import Fore, Style, init
from keep_alive import keep_alive

keep_alive()

TOKEN = os.environ.get("TOKEN") # Add your account Token in environment
if not TOKEN:
    print(Fore.RED + "Error: Missing DISCORD TOKEN" + Style.RESET_ALL)
    raise SystemExit(1)

bot = commands.Bot(command_prefix="-", self_bot=True)

# Remove default help command so we can define a custom one
try:
    bot.remove_command("help")
except Exception:
    pass

# PERMISSION CHECK

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    uid = str(message.author.id)

    if uid == str(bot.user.id):
        await bot.process_commands(message)
      
# PING (debug) - plaintext reply (selfbot-friendly)

@bot.command()
async def ping(ctx):
    """Debug: replies with Pong, latency and caller info in plaintext."""
    try:
        await ctx.message.delete()
    except Exception:
        pass

    latency_ms = round(bot.latency * 1000) if getattr(bot, "latency", None) is not None else "N/A"
    caller_id = str(ctx.author.id)
    is_allowed = (caller_id == str(bot.user.id)) or (caller_id in allowed_users_set)

    text = (
        "SelfBot Ping!\n"
        f"Latency: `{latency_ms} ms`\n"
        f"Caller: `{ctx.author}` (`{caller_id}`)\n"
    )
    await ctx.send(text)
  
  # Terminate command (interactive confirm)

bot.command(aliases=["kill", "shutdown"])
async def terminate(ctx):
    """
    Owner-only interactive termination.
    The bot will ask you to type CONFIRM within 15 seconds in the same channel to proceed.
    """
    # Owner-only
    if str(ctx.author.id) != str(bot.user.id):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        return

    # delete invoking message if possible
    try:
        await ctx.message.delete()
    except Exception:
        pass

    prompt = await ctx.send("⚠ You requested termination. Type `CONFIRM` within 15 seconds to terminate the selfbot (owner only).")

    def _check(m: discord.Message):
        return (
            m.author.id == ctx.author.id
            and m.channel.id == ctx.channel.id
            and m.content.strip().upper() == "CONFIRM"
        )

    try:
        # wait for confirmation
        confirm_msg: discord.Message = await bot.wait_for("message", timeout=15.0, check=_check)
        # delete the confirmation message and prompt if possible
        try:
            await confirm_msg.delete()
        except Exception:
            pass
        try:
            await prompt.delete()
        except Exception:
            pass

        # send final notice then shutdown
        await ctx.send("🛑 Confirmation received. Terminating: logging out and stopping the process now...")
        # Gracefully close the bot and exit
        try:
            await bot.close()
            print(Fore.RED + f"[!] SELFBOT HAS BEEN TERMINATED.")
        except Exception:
            pass
        # allow a very short delay for close to complete
        try:
            await asyncio.sleep(0.25)
        except Exception:
            pass
        os._exit(0)

    except asyncio.TimeoutError:
        # timeout -> cancel
        try:
            await prompt.edit(content="⛔ Termination cancelled: no confirmation received within 15 seconds.")
        except Exception:
            # fallback: send a cancellation message
            try:
                await ctx.send("⛔ Termination cancelled: no confirmation received within 15 seconds.")
            except Exception:
                pass

# RUN

if __name__ == "__main__":
    bot.run(TOKEN)
