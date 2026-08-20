# No evidence Discord Moderation Scanner Bot (regex-only)

This repository branch contains a Discord bot implementation that scans for messages authored by a target user across guilds the bot is in and detects potential violations using configurable regex rules. This version intentionally does not integrate any external moderation API.

Setup
1. Create a bot application in the Discord Developer Portal. Enable the "Message Content Intent" for the bot.
2. Invite the bot to servers where you want it to scan. Required permissions:
   - View Channels
   - Read Message History
   - Send Messages
   - (Optional) Manage Messages — required if you want the bot to delete other users' messages
3. Add the bot token to the environment where you run the bot. You can create a .env file with:

   DISCORD_BOT_TOKEN=your_bot_token_here

4. (Optional) Configure limits via environment variables:
   - SCAN_LIMIT_PER_CHANNEL: integer to limit how many messages per channel to scan (default: full history)
   - CHANNEL_DELAY: seconds to wait between channels (default: 0.8)
   - DETECTION_RULES_PATH: path to detection_rules.json (default: detection_rules.json)

Install & run

pip install -r requirements.txt
python bot/main.py

Files in this branch
- bot/main.py : main bot implementation
- detection_rules.json : regex detection rules that the bot loads at runtime
- requirements.txt : Python dependencies

Notes & safety
- This bot is built for a bot account only (soon to be for self-bot) and follows Discord permissions: it will only read or delete messages where it has permission.
- Scanning full server histories can take substantial time and is subject to rate limits. Use SCAN_LIMIT_PER_CHANNEL to limit scope during testing.
- The regex rules in detection_rules.json are a starting point — tune them for your needs.
