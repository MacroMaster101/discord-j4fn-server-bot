# Discord YouTube Status Bot 🎮

A feature-rich Discord bot built for **public gaming servers** — shows YouTube channel stats in its presence, welcomes new members, and includes fun & utility commands.

## ✨ Features

### 📊 Info Commands
| Command | Description |
|---|---|
| `!stats` | Server stats + YouTube info in a rich embed |
| `!yt` | YouTube channel stats (subs, views, videos) |
| `!userinfo [@user]` | User profile, roles, join date |
| `!avatar [@user]` | Display user's avatar |
| `!servericon` | Display server icon |
| `!ping` | Bot latency |
| `!uptime` | How long the bot has been running |

### 🎮 Fun & Games
| Command | Description |
|---|---|
| `!roll [sides]` | Roll a dice (default 6 sides) |
| `!flip` | Flip a coin |
| `!8ball <question>` | Magic 8-Ball fortune |
| `!rps <rock\|paper\|scissors>` | Rock Paper Scissors vs the bot |
| `!poll <question>` | Quick poll with 👍👎🤷 reactions |

### 💬 Auto Responses
- **Greetings** — `hi`, `hello`, `hey`, `yo`, `sup`, `wassup` → random welcome reply
- **GG** — `gg`, `gg wp`, `good game` → GG reaction + 🏆 emoji

### 🎉 Welcome System
- Auto-sends a rich embed when a new member joins
- Configurable welcome channel via `WELCOME_CHANNEL_ID`
- Falls back to the server's system channel

### 🔴 YouTube Integration
- Bot presence shows live subscriber count (updates every 5 min)
- `!stats` and `!yt` commands pull real-time data from YouTube Data API v3

## Project Structure

```
discord-youtube-status-bot/
├── bot.py              # Main bot logic
├── Dockerfile          # Container config for Fly.io
├── fly.toml            # Fly.io deployment config
├── requirements.txt    # Python dependencies
├── .gitignore          # Git exclusions
├── .dockerignore       # Docker exclusions
└── README.md           # This file
```

## Requirements

- Python 3.9+
- Discord bot token
- YouTube Data API v3 key
- YouTube channel ID

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/discord-youtube-status-bot.git
cd discord-youtube-status-bot
pip install -r requirements.txt
```

Create a `.env` file:

```env
DISCORD_TOKEN=your_discord_bot_token
YOUTUBE_API_KEY=your_youtube_api_key
YOUTUBE_CHANNEL_ID=your_youtube_channel_id
WELCOME_CHANNEL_ID=your_welcome_channel_id
PORT=8080
```

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | From [Discord Developer Portal](https://discord.com/developers/applications) |
| `YOUTUBE_API_KEY` | ✅ | YouTube Data API v3 key |
| `YOUTUBE_CHANNEL_ID` | ✅ | YouTube channel to track |
| `WELCOME_CHANNEL_ID` | ❌ | Channel for welcome messages (falls back to system channel) |
| `PORT` | ❌ | Flask server port (default `8080`) |

Run locally:

```bash
python bot.py
```

## Discord Bot Setup

Enable these **Privileged Gateway Intents** in the [Developer Portal](https://discord.com/developers/applications) → Bot:

| Intent | Why |
|---|---|
| ✅ Message Content | Read commands |
| ✅ Server Members | Member counts, userinfo, welcome |
| ✅ Presence | Online/offline counts in !stats |

**Bot Permissions** — invite with these permissions:
- Send Messages, Embed Links, Add Reactions, Read Message History, Use External Emojis

## Deploy to Fly.io (24/7)

```bash
# Install flyctl
# https://fly.io/docs/flyctl/install/

# Set secrets
flyctl secrets set DISCORD_TOKEN=xxx YOUTUBE_API_KEY=xxx YOUTUBE_CHANNEL_ID=xxx

# Optionally set welcome channel
flyctl secrets set WELCOME_CHANNEL_ID=xxx

# Deploy
flyctl deploy
```

The `fly.toml` is pre-configured with `auto_stop_machines = 'off'` and `min_machines_running = 1` so the bot **never shuts down**.

## Dependencies

- `discord.py` — Discord API wrapper
- `requests` — YouTube API calls
- `python-dotenv` — .env file support
- `flask` — Keep-alive web server

## License

MIT — free to use and modify.
