# 🤖 JUST FOR FUN — Discord Server Moderation Bot & Dashboard

![J4FN Banner](static/logo.png)

[![Discord](https://img.shields.io/badge/Discord-Bot-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com)
[![Cloudflare Tunnel](https://img.shields.io/badge/Cloudflare-Zero_Trust-F38020?style=for-the-badge&logo=cloudflare&logoColor=white)](https://cloudflare.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)

**JUST FOR FUN (J4FN Bot)** is a production-grade Discord server moderation and community management bot built with `discord.py` and `Flask`. It features a public status landing page (`bot.j4fn.site`), automated anti-spam protection, persistent member warnings, welcome embeds, presence rotation, and a protected Admin Operations Console (`bot.j4fn.site/admin`) supporting **Cloudflare Zero Trust Access**.

---

## 📁 Clean Directory Architecture

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

## 🌟 Key Features

### 1. 🌐 Public Landing Page (`https://bot.j4fn.site`)
- **Live Stats Counters**: Real-time display of Bot Status (`ONLINE`), Server Count, Total Members, and API Gateway Ping (ms).
- **Add to Discord CTA**: One-click Discord bot authorization link.
- **Commands Showcase**: Interactive command browser with category filters (Moderation, Info, Fun, Auto).

### 2. 🔐 Protected Operations Console (`https://bot.j4fn.site/admin`)
- **Cloudflare Zero Trust Identity**: Automatically recognizes authenticated Cloudflare Access headers (`Cf-Access-Authenticated-User-Email`).
- **Password Shield Fallback**: Integrated glassmorphic login modal supporting local `ADMIN_PASSWORD`.
- **Settings CRUD**: Dynamic configuration for Prefix (`$`), Welcome Channel, Mod-Log Channel, Muted Role, and Admin Password.
- **Presence Control**: Online mode (Online/Idle/DND), activity type (Playing/Watching/Listening/Streaming), and custom status text.
- **Moderation Console**: Execute Kick, Ban, Unban, Timeout (Mute), Warn, and audit active server warnings.

### 3. 🤖 Automated Bot Features
- **Anti-Spam Auto-Mute**: Automatically applies a 5-minute timeout when a user sends 5+ messages within 6 seconds.
- **Dynamic Presence Rotation**: Rotates status text every 20s highlighting online member totals.
- **Welcome Embed Greetings**: Sends customizable welcome cards when new members join your server.

---

## ⚙️ Environment Variables

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `DISCORD_TOKEN` | **Yes** | — | Your Discord Bot Token from Developer Portal |
| `ADMIN_PASSWORD` | Optional | *Auto-generated* | Password for accessing the `/admin` Operations Console |
| `PORT` | Optional | `8080` | Port for the Flask REST API & Web Dashboard |
| `TUNNEL_TOKEN` | **Yes** (Prod) | — | Cloudflare Zero Trust Tunnel connector token |
| `PREFIX` | Optional | `$` | Default command prefix for bot commands |
| `WELCOME_CHANNEL_ID` | Optional | `""` | Text channel ID for welcome greeting embeds |
| `MOD_LOG_CHANNEL_ID` | Optional | `""` | Text channel ID for moderation audit logs |
| `MUTED_ROLE_NAME` | Optional | `Muted` | Role name assigned during timeouts |

---

## 🚀 Quick Start & Deployment

### 1. Local Development Setup
```bash
# Clone the repository
git clone https://github.com/MacroMaster101/discord-j4fn-server-bot.git
cd discord-j4fn-server-bot

# Copy environment template
cp .env.example .env

# Edit .env and insert your DISCORD_TOKEN
nano .env

# Install dependencies and start
pip install -r requirements.txt
python bot.py
```
Open `http://localhost:8080` in your browser.

---

### 2. Docker & Cloudflare Tunnel Deployment (AWS EC2)
```bash
# Start bot and Cloudflare Tunnel containers in background
docker compose up -d --build

# Inspect container logs
docker compose logs -f
```

---

## 🛡️ Cloudflare Zero Trust Access Setup Guide

To protect `https://bot.j4fn.site/admin` with Cloudflare Access (matching Screenshot 4):

1. Go to your **[Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)**.
2. Navigate to **Access** ➔ **Applications** ➔ Click **Add an application**.
3. Select **Self-hosted**.
4. Configure Application:
   - **Application name**: `J4FN Server Bot Admin`
   - **Domain**: `j4fn.site`
   - **Subdomain**: `bot`
   - **Path**: `admin`
5. Configure Policy:
   - **Action**: `Allow`
   - **Include**: Add your email (`justforfun.ggez@gmail.com`).
6. Save Application.

---

## 📜 License
© 2026 JUST FOR FUN (`j4fn.site`). All rights reserved.
