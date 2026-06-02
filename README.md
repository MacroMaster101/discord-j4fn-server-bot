# Discord Server Moderation Bot 🛡️

A full-featured Discord **server moderation bot** with a built-in web control panel — moderation commands, warnings tracking, auto-anti-spam, welcome embeds, fun utilities, and a real-time admin dashboard.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)
![AWS EC2](https://img.shields.io/badge/Deployed_on-AWS_EC2-FF9900?logo=amazonec2&logoColor=white)
![Docker](https://img.shields.io/badge/Containerized-Docker-2496ED?logo=docker&logoColor=white)

---

## ✨ Features

### 🛡️ Full Moderation Suite

| Command | Description |
|---|---|
| `$kick @user [reason]` | Kick a member |
| `$ban @user [reason]` / `$ban <id>` | Ban (works even if user not in server) |
| `$unban <user_id> [reason]` | Unban by ID |
| `$mute @user <duration> [reason]` | Timeout (e.g. `10m`, `1h`, `1d`) — also `$timeout` |
| `$unmute @user` | Remove timeout — also `$untimeout` |
| `$warn @user <reason>` | Issue a warning (persisted to disk + DMs the user) |
| `$warnings [@user]` | List warnings (also `$warns`) |
| `$clearwarns @user` | Clear all warnings for a user |
| `$purge <count>` | Bulk delete messages (1–100) — also `$clear` |
| `$slowmode <seconds>` | Set channel slowmode (0 to disable) |
| `$lock` / `$unlock` | Lock/unlock current channel for `@everyone` |
| `$nick @user <name>` | Set member nickname (omit name to reset) |
| `$addrole @user <role>` / `$removerole @user <role>` | Manage roles |

All moderation actions are sent to the configured **mod-log channel** (if set) as rich embeds and logged in the dashboard's audit feed.

### 🤖 Auto-Moderation
- **Anti-spam**: any member sending 5+ messages within 6 seconds is auto-muted for 5 minutes.
- **Message-delete log**: deleted messages are logged to the mod-log channel.

### 🔄 Rotating Bot Presence
Status cycles every **20 seconds** through:
- `👥 X members`
- `🟢 X online`
- `🌐 X server(s)`
- `$help | Moderating 🛡️`

Fully customizable from the dashboard.

### 🎉 Auto Welcome
Rich embed greeting when new members join — configurable channel or auto-fallback to system channel.

### 📊 Info Commands

| Command | Description |
|---|---|
| `$stats` | Server stats (members, channels, roles, warnings) |
| `$userinfo [@user]` | User profile, roles, warnings count |
| `$avatar [@user]` | Display user's avatar (also `$av`) |
| `$servericon` | Display server icon |
| `$ping` | Bot latency |
| `$uptime` | How long the bot has been online |

### 🎮 Fun & Games

| Command | Description |
|---|---|
| `$roll [sides]` | Roll a dice (default: 6) |
| `$flip` | Flip a coin (also `$coin`) |
| `$8ball <question>` | Magic 8-Ball |
| `$rps <rock\|paper\|scissors>` | Rock Paper Scissors |
| `$poll <question>` | Quick reaction poll |

### 💬 Auto Responses

| Trigger | Response |
|---|---|
| `hi`, `hello`, `hey`, `yo`, `sup` | Random welcome greeting |
| `gg`, `gg wp`, `ggwp`, `good game` | GG message + 🏆 reaction |

### 🖥️ Web Control Panel

Visit `http://your-host:8080/` and log in with your `ADMIN_PASSWORD` to access:

- **Dashboard** — Live bot stats (uptime, latency, member counts, warnings, mod actions, CPU/RAM)
- **Configuration** — Edit prefix, welcome channel, mod-log channel, muted role, admin password
- **Presence Control** — Customize status text/activity with dynamic variables (`{total_members}`, `{online_members}`, `{server_count}`, `{prefix}`)
- **Moderation** — Issue warns/timeouts/kicks/bans from the browser, view active warnings per server, audit log of recent actions
- **Broadcast** — Send announcements to any channel
- **Console Logs** — Real-time bot log feed

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/MacroMaster101/discord-j4fn-server-bot.git
cd discord-j4fn-server-bot
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token
PREFIX=$
WELCOME_CHANNEL_ID=optional_channel_id
MOD_LOG_CHANNEL_ID=optional_mod_log_channel_id
MUTED_ROLE_NAME=Muted
ADMIN_PASSWORD=change_me
PORT=8080
```

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot token from [Discord Developer Portal](https://discord.com/developers/applications) |
| `PREFIX` | ❌ | Command prefix (default: `$`) |
| `WELCOME_CHANNEL_ID` | ❌ | Channel ID for welcome messages (falls back to system channel) |
| `MOD_LOG_CHANNEL_ID` | ❌ | Channel ID where mod-actions are logged as embeds |
| `MUTED_ROLE_NAME` | ❌ | Fallback muted role name (default: `Muted`) |
| `ADMIN_PASSWORD` | ❌ | Password for the web control panel (default: `admin123` — change it!) |
| `PORT` | ❌ | Flask server port (default: `8080`) |

### 3. Enable Discord Bot Intents

In the [Discord Developer Portal](https://discord.com/developers/applications) → Your App → **Bot** → **Privileged Gateway Intents**, enable:

| Intent | Required For |
|---|---|
| ✅ Message Content | Reading commands |
| ✅ Server Members | Member counts, welcome, user resolution |
| ✅ Presence | Online counts |

### 4. Run Locally

```bash
python bot.py
```

Then open `http://localhost:8080` for the dashboard.

---

## 🤖 Bot Permissions

When inviting the bot, grant at minimum:

- Send Messages, Embed Links, Add Reactions, Read Message History
- **Kick Members**, **Ban Members**, **Moderate Members** (timeouts)
- **Manage Messages** (purge), **Manage Channels** (slowmode/lock), **Manage Nicknames**, **Manage Roles**

---

## 💾 Data Storage

Warnings are persisted to `data/warnings.json` in the project directory. When deploying via **Docker Compose**, the local `./data` directory and `.env` configuration file are automatically mounted to the container as volumes. This ensures your warnings and configuration edits survive redeploys or container updates.

---

## 🐋 Deploy to AWS EC2 (Docker Compose)

### 1. Launch a Free-Tier AWS EC2 Instance
* **OS**: Ubuntu Server 26.04 LTS (HVM), SSD Volume Type (64-bit x86).
* **Instance Type**: `t3.micro` (Free-tier eligible in Singapore and most newer regions).
* **Security Group**:
  * Allow SSH traffic (Port 22).
  * Allow Custom TCP traffic on Port **8080** (for the web control panel).

### 2. Configure Server & Install Docker
SSH into your instance and run the following commands to configure dependencies:
```bash
# Update local packages
sudo apt update && sudo apt upgrade -y

# Install Docker and Compose plugin
sudo apt install -y docker.io docker-compose-v2

# Add ubuntu user to the docker group and apply group permissions
sudo usermod -aG docker ubuntu
newgrp docker
```

### 3. Deploy Application
Clone your repository, create the environment file, and start the container:
```bash
# Clone code
git clone https://github.com/MacroMaster101/discord-j4fn-server-bot.git
cd discord-j4fn-server-bot

# Initialize .env file
touch .env
nano .env
```
Paste your environment variables, save with `Ctrl+O` and exit with `Ctrl+X`. Then run:
```bash
# Run container in background
docker compose up -d --build
```

---

## 🔄 Automatic Deployment with GitHub CI/CD

This repository includes a secure, automatic deployment pipeline via **GitHub Actions** located in `.github/workflows/deploy.yml`.

### Setup Instructions
1. Go to your repository page on GitHub -> **Settings** -> **Secrets and variables** -> **Actions**.
2. Create three repository secrets:
   * `EC2_HOST`: Your AWS EC2 Public IP address.
   * `EC2_USERNAME`: `ubuntu`
   * `EC2_SSH_KEY`: The entire contents of your private key file (`bot-key.pem`).
3. Push your code updates to the `main` branch. GitHub Actions will securely connect to your server, pull the latest changes, and rebuild the container automatically.

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `discord.py` | Discord API wrapper |
| `python-dotenv` | Load `.env` files locally |
| `flask` | Web control panel & health checks |

---

## 📄 License

MIT — free to use, modify, and distribute.
