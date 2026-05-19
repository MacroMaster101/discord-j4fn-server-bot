# Discord YouTube Status Bot 🎮

A feature-rich Discord bot built for **public gaming servers** — displays YouTube channel stats in its rotating presence, welcomes new members, and comes packed with fun & utility commands.

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)
![Fly.io](https://img.shields.io/badge/Deployed_on-Fly.io-8B5CF6?logo=flydotio&logoColor=white)

---

## ✨ Features

### 🔄 Rotating Bot Presence
The bot status cycles every **15 seconds** through:
- `🔴 212 subs on YouTube`
- `👥 150 members`
- `🟢 42 online`
- `🎮 3 servers` *(if in multiple servers)*
- `!help | Gaming 🎮`

### 🎉 Auto Welcome
Rich embed greeting when new members join — configurable channel or auto-fallback to system channel.

### 📊 Info Commands

| Command | Description |
|---|---|
| `!stats` | Server stats + YouTube info in a rich embed |
| `!yt` | YouTube channel stats (subs, views, videos) |
| `!userinfo [@user]` | User profile, roles, join date |
| `!avatar [@user]` | Display user's avatar (also `!av`) |
| `!servericon` | Display server icon |
| `!ping` | Bot latency |
| `!uptime` | How long the bot has been online |

### 🎮 Fun & Games

| Command | Description |
|---|---|
| `!roll [sides]` | Roll a dice (default: 6 sides) |
| `!flip` | Flip a coin (also `!coin`) |
| `!8ball <question>` | Magic 8-Ball fortune teller |
| `!rps <rock\|paper\|scissors>` | Rock Paper Scissors vs the bot |
| `!poll <question>` | Quick poll with 👍👎🤷 reactions |

### 💬 Auto Responses

| Trigger | Response |
|---|---|
| `hi`, `hello`, `hey`, `yo`, `sup`, `wassup` | Random welcome greeting |
| `gg`, `gg wp`, `ggwp`, `good game` | GG message + 🏆 reaction |

---

## 📁 Project Structure

```
discord-youtube-status-bot/
├── .github/
│   └── workflows/
│       └── deploy.yml      # Auto-deploy to Fly.io on push
├── bot.py                  # Main bot logic
├── Dockerfile              # Container image for Fly.io
├── fly.toml                # Fly.io config (rolling deploy, always-on)
├── requirements.txt        # Python dependencies
├── .gitignore              # Git exclusions
├── .dockerignore           # Docker exclusions
└── README.md               # This file
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/MacroMaster101/discord-youtube-status-bot.git
cd discord-youtube-status-bot
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token
YOUTUBE_API_KEY=your_youtube_api_key
YOUTUBE_CHANNEL_ID=your_youtube_channel_id
WELCOME_CHANNEL_ID=your_welcome_channel_id
PORT=8080
```

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot token from [Discord Developer Portal](https://discord.com/developers/applications) |
| `YOUTUBE_API_KEY` | ✅ | Google API key with YouTube Data API v3 enabled |
| `YOUTUBE_CHANNEL_ID` | ✅ | YouTube channel ID to track |
| `WELCOME_CHANNEL_ID` | ❌ | Channel ID for welcome messages (falls back to system channel) |
| `PORT` | ❌ | Flask server port (default: `8080`) |

### 3. Enable Discord Bot Intents

In the [Discord Developer Portal](https://discord.com/developers/applications) → Your App → **Bot** → **Privileged Gateway Intents**:

| Intent | Required For |
|---|---|
| ✅ Message Content | Reading commands & messages |
| ✅ Server Members | Member counts, `!userinfo`, welcome messages |
| ✅ Presence | Online/offline counts in `!stats` and presence |

### 4. Run Locally

```bash
python bot.py
```

---

## ☁️ Deploy to Fly.io (24/7)

### First-Time Setup

```bash
# Install flyctl: https://fly.io/docs/flyctl/install/

# Launch the app (only needed once)
flyctl launch

# Set secrets
flyctl secrets set DISCORD_TOKEN=xxx YOUTUBE_API_KEY=xxx YOUTUBE_CHANNEL_ID=xxx

# Optional: set welcome channel
flyctl secrets set WELCOME_CHANNEL_ID=xxx

# Deploy
flyctl deploy
```

### Auto-Deploy on GitHub Push

The included GitHub Actions workflow (`.github/workflows/deploy.yml`) auto-deploys on every push to `main`.

**One-time setup:**
1. Generate a Fly.io deploy token: `flyctl tokens create deploy -x 999999h`
2. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
3. Add secret: Name = `FLY_API_TOKEN`, Value = your token

### Deployment Config Highlights

| Setting | Value | Why |
|---|---|---|
| `auto_stop_machines` | `off` | Bot never shuts down |
| `min_machines_running` | `1` | Always at least 1 machine |
| `deploy.strategy` | `rolling` | Zero-downtime deploys |
| Health check | `/health` every 15s | Old machine runs until new one is healthy |

---

## 🤖 Bot Permissions

When inviting the bot to a server, it needs these permissions:
- Send Messages
- Embed Links
- Add Reactions
- Read Message History
- Use External Emojis

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `discord.py` | Discord API wrapper |
| `requests` | YouTube API HTTP calls |
| `python-dotenv` | Load `.env` files locally |
| `flask` | Keep-alive web server for health checks |

---

## 📄 License

MIT — free to use, modify, and distribute.
