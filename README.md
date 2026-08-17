<div align="center">

  <img src="static/logo.png" alt="J4FN Logo" width="160" style="border-radius: 24px; box-shadow: 0 10px 30px rgba(239, 68, 68, 0.4);" />

  # 🤖 JUST FOR FUN (J4FN Bot)

  **The Ultimate Discord Server Moderation Bot & Real-Time Operations Web Console**

  [🌐 Live Public Portal](https://bot.j4fn.site) • [🔐 Admin Console](https://bot.j4fn.site/admin) • [🟣 Add to Discord](https://discord.com/oauth2/authorize?client_id=951917671027458108&permissions=8&scope=bot)

  <br />

  [![Discord.py](https://img.shields.io/badge/Discord.py-v2.3+-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com)
  [![Cloudflare Zero Trust](https://img.shields.io/badge/Cloudflare-Zero_Trust-F38020?style=for-the-badge&logo=cloudflare&logoColor=white)](https://cloudflare.com)
  [![AWS EC2](https://img.shields.io/badge/AWS-EC2_Deployment-FF9900?style=for-the-badge&logo=amazonec2&logoColor=white)](https://aws.amazon.com)
  [![Docker Compose](https://img.shields.io/badge/Docker-Compose_Build-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
  [![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)

</div>

---

## 📌 Overview

**JUST FOR FUN (J4FN Bot)** is a production-grade Discord server moderation bot and community management suite. It features automated anti-spam protection, member warnings system, customizable welcome embeds, presence activity rotation, and a protected Admin Operations Console supporting **Cloudflare Zero Trust Access**.

> [!NOTE]
> Deployed 24/7 on AWS EC2 (`13.212.35.227`) using Docker Compose & Cloudflare Zero Trust Tunnels at **[bot.j4fn.site](https://bot.j4fn.site)**.

---

## 🌟 Key Features

| Category | Feature | Description |
| :--- | :--- | :--- |
| 🛡️ **Moderation** | **Full Admin Suite** | `$kick`, `$ban`, `$unban`, `$mute`, `$warn`, `$purge`, `$lock`, `$unlock`, `$slowmode`. |
| 🤖 **Automated** | **Anti-Spam Mute** | Automatically applies a 5-minute timeout when a user sends 5+ messages in 6s. |
| 🎉 **Greetings** | **Welcome Embeds** | Sends customizable welcome cards with server member counts when new users join. |
| 🔄 **Presence** | **Activity Rotation** | Cycles status text every 20s displaying live online member totals and server stats. |
| 🌐 **Public Web** | **Landing Page** | Live status counters (Status, Server Count, Total Users, API Latency) and command guide. |
| 🔐 **Admin Console**| **Operations Portal** | Cloudflare Zero Trust Access & Password protected panel for live settings CRUD & moderation. |

---

## 📖 Command Reference

| Command | Usage | Description | Required Permission |
| :--- | :--- | :--- | :--- |
| `$kick` | `$kick @user [reason]` | Kicks specified member from server | Kick Members |
| `$ban` | `$ban @user [reason]` | Permanently bans user by ID or mention | Ban Members |
| `$mute` | `$mute @user <time> [reason]` | Timeout user (e.g. `10m`, `1h`, `1d`) | Moderate Members |
| `$warn` | `$warn @user <reason>` | Issues a warning (persisted & DMs user) | Kick Members |
| `$purge` | `$purge <count>` | Bulk delete 1 to 100 recent messages | Manage Messages |
| `$lock` / `$unlock` | `$lock` | Lock or unlock send message permissions | Manage Channels |
| `$stats` | `$stats` | View server member counts, channels & warnings | Everyone |
| `$userinfo` | `$userinfo [@user]` | Display user join date, roles & warning history | Everyone |
| `$roll` / `$flip` | `$roll` | Roll a dice or flip a coin | Everyone |
| `$8ball` | `$8ball <question>` | Ask the Magic 8-Ball a question | Everyone |

---

## 📁 Clean Project Structure

```text
discord-j4fn-server-bot/
├── .env.example            # Environment template for production & local dev
├── Dockerfile              # Container build manifest (Python 3.12-slim)
├── docker-compose.yml      # Orchestration for Bot & Cloudflare Tunnel
├── requirements.txt        # Python dependencies (discord.py, Flask, etc.)
├── README.md               # Production documentation & setup guide
├── bot.py                  # Main application (Discord Bot + Flask REST API)
├── static/                 # Static web assets
│   ├── favicon.ico         # Browser tab icon
│   ├── logo.png            # 1024x1024 official J4FN red monogram logo
│   ├── logo.jpg            # Original image asset
│   ├── css/
│   │   ├── public.css      # Styling for Public Landing Page
│   │   └── admin.css       # Styling for Protected Admin Operations Console
│   └── js/
│       ├── public.js       # Live stats fetcher & command browser scripts
│       └── admin.js        # Auth, Settings CRUD, Moderation & Audit scripts
└── templates/              # HTML Templates
    ├── index.html          # Public Landing Page & Commands Showcase
    └── admin.html          # Protected Admin Operations Console
```

---

## ⚙️ Environment Variables

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `DISCORD_TOKEN` | **Yes** | — | Your Discord Bot Token from Developer Portal |
| `ADMIN_PASSWORD` | Optional | *Auto-generated* | Password for accessing `/admin` Operations Console |
| `PORT` | Optional | `8080` | Port for Flask REST API & Web Dashboard |
| `TUNNEL_TOKEN` | **Yes** (Prod) | — | Cloudflare Zero Trust Tunnel connector token |
| `PREFIX` | Optional | `$` | Default command prefix |
| `WELCOME_CHANNEL_ID` | Optional | `""` | Channel ID for welcome greeting embeds |
| `MOD_LOG_CHANNEL_ID` | Optional | `""` | Channel ID for moderation audit logs |
| `MUTED_ROLE_NAME` | Optional | `Muted` | Role name assigned during timeouts |

---

## 🚀 Quick Start & Production Deployment

### Local Development
```bash
# Clone repository
git clone https://github.com/MacroMaster101/discord-j4fn-server-bot.git
cd discord-j4fn-server-bot

# Setup environment
cp .env.example .env
nano .env

# Install dependencies and start
pip install -r requirements.txt
python bot.py
```

### Docker & Cloudflare Tunnel (AWS EC2 Deployment)
```bash
# Start bot and Cloudflare Tunnel containers
docker compose up -d --build

# View container logs
docker compose logs -f
```

---

## 🛡️ Cloudflare Zero Trust Setup Guide

To protect `https://bot.j4fn.site/admin` with Cloudflare Access:

1. Open **[Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)**.
2. Navigate to **Access** ➔ **Applications** ➔ **Add an application**.
3. Select **Self-hosted**.
4. Configure Application:
   - **Application name**: `J4FN Server Bot Admin`
   - **Domain**: `j4fn.site`
   - **Subdomain**: `bot`
   - **Path**: `admin`
5. Configure Access Policy:
   - **Action**: `Allow`
   - **Include**: Add your email (`justforfun.ggez@gmail.com`).
6. Click **Save application**.

---

## 📜 License
© 2026 JUST FOR FUN (`j4fn.site`). All rights reserved.
