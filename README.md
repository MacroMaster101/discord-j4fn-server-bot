# Discord YouTube Status Bot

A Python Discord bot that displays a YouTube channel's subscriber count in its presence, shows server stats, and responds to commands.

## Features

- **YouTube Status** — Bot presence shows your channel's live subscriber count
- **`!stats`** — Rich embed showing server members, channels, roles, boosts, **and** YouTube stats
- **`!yt`** — Standalone YouTube channel stats (subs, views, videos)
- **`!help`** — Lists all available commands
- **Greetings** — Responds to `hi`, `hello`, `hey` with a welcome message
- **Self-Ping Keep-Alive** — Built-in loop that pings its own URL every 4 minutes to prevent Render free-tier spin-down
- **Health Endpoint** — `/health` route for external uptime monitors

## How It Works

The bot uses the **YouTube Data API v3** to fetch channel statistics and updates its Discord presence every 5 minutes to display:

```
212 subs on YouTube
```

When a user types `!stats`, the bot replies with a rich embed containing full server information alongside YouTube channel data.

## Project Structure

```text
discord-youtube-status-bot/
├── bot.py              # Main bot logic
├── requirements.txt    # Python dependencies
├── .gitignore          # Files excluded from Git
└── README.md           # Project documentation
```

## Requirements

- Python 3.9+
- A Discord bot token
- A YouTube Data API v3 key
- A YouTube channel ID

## Installation

1. Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/discord-youtube-status-bot.git
cd discord-youtube-status-bot
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token
YOUTUBE_API_KEY=your_youtube_api_key
YOUTUBE_CHANNEL_ID=your_youtube_channel_id
PORT=8080
RENDER_EXTERNAL_URL=https://your-bot-name.onrender.com
```

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot token from the [Discord Developer Portal](https://discord.com/developers/applications) |
| `YOUTUBE_API_KEY` | ✅ | API key for YouTube Data API v3 |
| `YOUTUBE_CHANNEL_ID` | ✅ | ID of the YouTube channel to track |
| `PORT` | ❌ | Port for the Flask server (default `8080`) |
| `RENDER_EXTERNAL_URL` | ❌ | Your Render web-service URL — enables the self-ping keep-alive |

## Running the Bot

```bash
python bot.py
```

On startup the bot will:
1. Start the Flask web server on a background thread
2. Log in to Discord
3. Update its presence every 5 minutes
4. Self-ping every 4 minutes (if `RENDER_EXTERNAL_URL` is set)

## Bot Intents

This bot requires these **Privileged Gateway Intents** enabled in the Discord Developer Portal:

| Intent | Why |
|---|---|
| Message Content | Read message text for commands |
| Server Members | Accurate member counts in `!stats` |
| Presence | Online / offline counts in `!stats` |

> **How to enable:** Discord Developer Portal → Your App → Bot → Privileged Gateway Intents → Toggle each one ON.

## Commands

| Command | Description |
|---|---|
| `!stats` | Server info + YouTube stats in one embed |
| `!yt` | YouTube channel stats only |
| `!help` | List available commands |
| `hi` / `hello` / `hey` | Bot greets you back |

## Deployment — Running 24/7

### Option 1: Render Free Tier + Self-Ping (Current Setup)

The bot already has a **built-in self-ping** that hits its own `/health` endpoint every 4 minutes. This prevents Render's free tier from spinning down the service.

**Setup on Render:**
1. Create a new **Web Service** → connect your GitHub repo
2. Set **Build Command:** `pip install -r requirements.txt`
3. Set **Start Command:** `python bot.py`
4. Add all environment variables (including `RENDER_EXTERNAL_URL`)
5. Deploy — the self-ping handles the rest

> ⚠️ Render free tier still restarts services periodically and may have brief downtime windows. For truly 24/7 uptime, consider the options below.

### Option 2: Railway (Recommended Free Alternative)

[Railway](https://railway.app) offers a free tier with 500 hours/month (enough for ~20 days). Unlike Render, **it does not spin down**.

1. Sign up at [railway.app](https://railway.app)
2. Create a new project → Deploy from GitHub
3. Add environment variables in the Railway dashboard
4. Railway auto-detects Python and deploys

### Option 3: Oracle Cloud Free Tier (Truly Free 24/7)

Oracle Cloud offers **Always Free** VMs (1 GB RAM, 1 OCPU) — perfect for a small bot.

1. Create an account at [cloud.oracle.com](https://cloud.oracle.com)
2. Launch an Always Free compute instance (Ubuntu)
3. SSH in, clone your repo, install Python
4. Run with `screen` or `systemd`:

```bash
# Using screen
screen -S bot
python bot.py
# Ctrl+A, D to detach

# Or create a systemd service for auto-restart
```

### Option 4: A Home PC / Raspberry Pi

Run `python bot.py` on any always-on machine. Use `systemd`, `pm2`, or just `screen`/`tmux`.

### Option 5: Fly.io Free Tier

[Fly.io](https://fly.io) gives 3 shared-cpu VMs free. Add a `fly.toml` and deploy:

```bash
flyctl launch
flyctl secrets set DISCORD_TOKEN=... YOUTUBE_API_KEY=... YOUTUBE_CHANNEL_ID=...
flyctl deploy
```

## Dependencies

- `discord.py` — Discord API wrapper
- `requests` — HTTP client for YouTube API
- `python-dotenv` — Load `.env` files
- `flask` — Lightweight web server for keep-alive

## Summary

A lightweight Discord bot that bridges YouTube and Discord — showing your channel's live stats both in the bot's presence and through interactive commands, with built-in keep-alive for free-tier hosting.
