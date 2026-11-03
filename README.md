<div align="center">

  <!-- The rounding is baked into assets/logo.png: GitHub strips inline style
       from README HTML, so border-radius here never applied. static/logo.png
       stays square because the app rounds it in CSS and uses it as a favicon. -->
  <img src="assets/logo.png" alt="J4FN Logo" width="160" />

  # 🤖 JUST FOR FUN (J4FN Bot)

  **The Ultimate Discord Server Moderation Bot & Real-Time Operations Web Console**

  [🌐 Live Public Portal](https://bot.j4fn.site) • [🔐 Admin Console](https://bot.j4fn.site/admin) • [🟣 Add to Discord](https://discord.com/oauth2/authorize?client_id=951917671027458108&permissions=8&scope=bot)

  <br />

  [![Discord.py](https://img.shields.io/badge/Discord.py-v2.3+-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com)
  [![Cloudflare Zero Trust](https://img.shields.io/badge/Cloudflare-Zero_Trust-F38020?style=for-the-badge&logo=cloudflare&logoColor=white)](https://cloudflare.com)
  [![Oracle Cloud](https://img.shields.io/badge/Oracle_Cloud-Compute-F80000?style=for-the-badge&logo=oracle&logoColor=white)](https://www.oracle.com/cloud/)
  [![Docker Compose](https://img.shields.io/badge/Docker-Compose_Build-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
  [![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
  [![License: MIT](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)

</div>

---

## 📌 Overview

**JUST FOR FUN (J4FN Bot)** is a production-grade Discord server moderation bot and community management suite. It features a content-aware anti-spam and scam filter, member warnings system, customizable welcome embeds, presence activity rotation, and a protected Admin Operations Console supporting **Cloudflare Zero Trust Access**.

> [!NOTE]
> Deployed 24/7 on an Oracle Cloud compute instance (Ubuntu 24.04) using Docker Compose & Cloudflare Zero Trust Tunnels at **[bot.j4fn.site](https://bot.j4fn.site)**. Only SSH is open on the host: the dashboard is published on `127.0.0.1` and reached exclusively through the tunnel.

---

## 🌟 Key Features

| Category | Feature | Description |
| :--- | :--- | :--- |
| 🛡️ **Moderation** | **Full Admin Suite** | `$kick`, `$ban`, `$unban`, `$mute`, `$warn`, `$purge`, `$lock`, `$unlock`, `$slowmode`. |
| 🤖 **Automated** | **Anti-Spam & Scam Filter** | Scores every message for referral/casino scams, phishing links, invite ads, mass mentions and message floods, then deletes, times out or bans. Tunable from the console. |
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
| `$automod` | `$automod [on\|off\|set\|test\|block\|recent]` | View and tune the anti-spam filter | Manage Server |
| `$stats` | `$stats` | View server member counts, channels & warnings | Everyone |
| `$userinfo` | `$userinfo [@user]` | Display user join date, roles & warning history | Everyone |
| `$roll` / `$flip` | `$roll` | Roll a dice or flip a coin | Everyone |
| `$8ball` | `$8ball <question>` | Ask the Magic 8-Ball a question | Everyone |

---

## 📁 Clean Project Structure

```text
discord-j4fn-server-bot/
├── .github/
│   ├── dependabot.yml      # Weekly pip / Actions / Docker update PRs, onto dev
│   ├── pull_request_template.md
│   ├── ISSUE_TEMPLATE/     # Bug report & feature request forms
│   └── workflows/
│       ├── branch-flow.yml # Enforces feature/* -> dev -> main on every PR
│       ├── ci.yml          # Tests on every PR and on each push to dev
│       └── deploy.yml      # Ships main to the server over SSH
├── .dockerignore           # Keeps .env, .git and caches out of the image
├── .env.example            # Environment template for production & local dev
├── Dockerfile              # Container build manifest (Python 3.12-slim)
├── docker-compose.yml      # Orchestration for Bot & Cloudflare Tunnel
├── requirements.txt        # Python dependencies (discord.py, Flask, etc.)
├── README.md               # Production documentation & setup guide
├── CONTRIBUTING.md         # Branch flow, local setup, checks to run
├── SECURITY.md             # Supported versions & how to report a vulnerability
├── LICENSE                 # MIT
├── bot.py                  # Main application (Discord Bot + Flask REST API)
├── auth.py                 # Discord OAuth sign-in & Cloudflare Access JWT checks
├── automod.py              # Anti-spam & scam detection engine (scoring, flood & image tracking)
├── test_auth.py            # Authorization boundary checks: `python test_auth.py`
├── test_automod.py         # Detection checks: `python test_automod.py`
├── data/                   # Runtime state (git-ignored; mounted into the container)
│   ├── automod.json        # Filter thresholds
│   └── guilds/             # Per-guild settings
├── assets/
│   └── logo.png            # Rounded logo for this README only (not served)
├── static/                 # Static web assets
│   ├── favicon.ico         # Browser tab icon
│   ├── logo.png            # 1024x1024 official J4FN red monogram logo
│   ├── css/
│   │   ├── public.css      # Styling for Public Landing Page
│   │   └── admin.css       # Styling for Protected Admin Operations Console
│   └── js/
│       ├── public.js       # Live stats fetcher & command browser scripts
│       ├── admin.js        # Auth, Settings CRUD, Moderation & Audit scripts
│       ├── automod.js      # Anti-spam filter settings, live activity & tester
│       ├── login.js        # Sign-in page: Access, Discord or admin token
│       └── dashboard.js    # Server-admin view of the guilds you manage
└── templates/              # HTML Templates
    ├── index.html          # Public Landing Page & Commands Showcase
    ├── admin.html          # Protected Admin Operations Console
    ├── login.html          # Sign-in page
    └── dashboard.html      # Per-guild dashboard for server admins
```

---

## 🛡️ Anti-Spam & Scam Filter

Every message from a non-staff member is scored before anything else happens. The
score combines what the message says with who is saying it, and the total decides
the punishment.

**What it catches**

| Signal | Examples |
| :--- | :--- |
| Referral / promo bait | "promo code", "use my code", "rakeback", "sign up and get" |
| Giveaway & payout bait | "giving away $3,500", "claim your reward", "withdrawal successful" |
| Gambling & crypto ads | casino, roulette, free spins, USDT, airdrop, wallet drainers |
| Phishing domains | link shorteners, brand lookalikes such as `discord-nitro.ru` |
| Invite advertising | `discord.gg/...` links from members without Manage Messages |
| Mass mentions | `@everyone`/`@here` abuse, or more than 5 pings in one message |
| Floods | message bursts, the same text repeated, the same text cross-posted |
| Reused images | one screenshot reposted across channels, or the same screenshot from several accounts at once |
| Known scam images | any picture a moderator has blocked, caught on the first post by any account |

Obfuscation is handled before matching: `fr33 m0ney`, `c a s i n o` and zero-width
characters all normalise back to the plain words.

**Context raises the score.** A brand-new account, a member who joined in the last
few days, screenshots posted alongside an unknown link, or the same message dropped
into several channels each add weight — which is what separates a referral raid from
someone sharing a clip.

**Images are fingerprinted, not read.** The referral raid in practice is one saved
screenshot posted by several throwaway accounts, often with no caption at all. Each
image attachment is reduced to a 64-bit [difference hash](https://en.wikipedia.org/wiki/Perceptual_hashing),
so the same picture is recognised after re-encoding, resizing or a light crop. Three
reposts from one member, or the same image from three different accounts within five
minutes, is treated as a raid regardless of what the text says. A reused image also
adds to the score of a message that *does* have wording, so a captioned repost trips
sooner than a first post.

**Reading the words inside an image (optional).** A scam screenshot with no
caption and no link has nothing for the text rules to read, and nothing to match
against until someone reposts it. Cloud OCR closes that last gap — but it uploads
member-posted images to a third party, so it is **off by default** and takes three
deliberate steps to turn on:

```bash
OCR_PROVIDER=ocrspace      # or: google
OCR_API_KEY=your_key_here
```
```text
$automod set ocr_enabled on
```

Tell your members, in your rules, that images may be sent to an OCR provider.

Calls are gated hard, because they cost money and add latency:

| Gate | Effect |
| :--- | :--- |
| Caption already damning | no call — the message is caught on its words alone |
| Established member | no call, unless the account is also brand new |
| Already read | no call — results are cached per image, and the cache matches perceptually, so a resized or re-encoded repost is free |
| Hourly ceiling | `ocr_max_per_hour` (default 60) caps the bill no matter what |
| Per message | at most `ocr_max_images` (default 2) |

In a simulated raid — nine messages, eleven images, five throwaway accounts posting
one scam screenshot — this costs **two billable calls**, and every spammer is caught
on their *first* post rather than the third. Set `ocr_only_untrusted` to `false` to
read everyone's images, at considerably higher cost.

If no provider is configured the filter behaves exactly as it does today, so this
can be left alone indefinitely.

**Blocking a scam image for good.** Hashing only catches a *repeat*, so the first
post of a new scam screenshot still gets through — especially when it carries no
caption for the text rules to read. Reply to the offending message with:

```text
$automod blockimage mrbeast casino ref spam
```

The images are fingerprinted into `data/blocked_images.json` and the message is
deleted. From then on, anyone posting that picture is caught on their **first**
message, from any account, with no caption needed — and because the match is
perceptual, a resized or re-encoded copy is caught too. One moderator action
immunises the server against that campaign permanently.

Blocks are per server. `$automod blockedimages` lists them, `$automod unblockimage
<id>` removes one, and the dashboard shows the same list with an Unblock button
beside each entry (it follows the Moderation Console's server picker).

Pillow is optional. With it installed you get perceptual hashing; without it the bot
falls back to fingerprints built from Discord's own attachment metadata, which
downloads nothing and still catches a file re-uploaded verbatim. `$automod` reports
which mode is active. Turn `image_deep_hash` off to keep the metadata-only behaviour
even with Pillow present — useful on a metered connection, since deep hashing
downloads each image (capped at `max_image_bytes`, four attachments per message).

**What it does**

1. The message is deleted.
2. Borderline content stops there.
3. A confirmed scam hit applies `scam_action` — `warn` (delete and log only),
   `timeout` (the default, 60m) or `ban` — and purges their other recent messages,
   in every channel they posted to.
4. A second scam hit within 24 hours bans them, whatever the first-hit action was.

Staff (Administrator, Manage Messages or Manage Server) and the server owner are
never auto-moderated. Every action lands in the mod-log channel, the dashboard audit
feed, and the member's warning history.

**Tuning it**

From Discord:

```text
$automod                      # show current settings
$automod off                  # disable the filter
$automod set scam_threshold 6 # relax it (higher = fewer hits)
$automod set scam_action warn # delete & log only, no timeout
$automod signals              # list signal categories and weights
$automod toggle gambling      # stop a category counting toward the score
$automod set image_checks off # stop fingerprinting image attachments
$automod set image_raid_accounts 2   # trip an image raid sooner
$automod blockimage <note>    # reply to a scam post to block its images for good
$automod blockedimages        # list them
$automod unblockimage <id>    # remove one
$automod set ocr_enabled on   # read text inside images (needs OCR_PROVIDER)
$automod block fabwin.com     # always remove a domain
$automod block free vbucks    # always remove a phrase
$automod allow mysite.com     # never penalise a domain
$automod test <message>       # score text without punishing anyone
$automod recent               # last 10 auto-mod actions
```

Or from the **Anti-Spam & Scam Filter** card in the admin console, which has the same
settings plus a live tester and an activity feed. Settings persist to
`data/automod.json`.

**Making it fit your server.** Every scoring category can be switched off, which
matters when normal chat uses the same words — a trading community discussing
`crypto bait` terms, or an LFG server where "dm me" is routine. `$automod signals`
lists all 13 with their weights; `$automod toggle <name>` flips one. The same
checkboxes are on the dashboard card.

> Start by watching `$automod recent` for a day, or run with
> `$automod set scam_action warn` so nothing is muted while you check accuracy.
> If legitimate messages are being caught, raise `scam_threshold` or switch off the
> category that fired; if spam is slipping past, lower it or add the offending
> domain with `$automod block`.

---

## ⚙️ Environment Variables

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `DISCORD_TOKEN` | **Yes** | — | Your Discord Bot Token from Developer Portal |
| `ADMIN_PASSWORD` | Optional | *Auto-generated* | Password for accessing `/admin` Operations Console |
| `PORT` | Optional | `8080` | Port for Flask REST API & Web Dashboard |
| `WEB_HOST` | Optional | `0.0.0.0` | Address the web panel listens on. Set `127.0.0.1` for local runs |
| `TUNNEL_TOKEN` | **Yes** (Prod) | — | Cloudflare Zero Trust Tunnel connector token |
| `CF_ACCESS_TEAM_DOMAIN` | **Yes** (Prod) | — | Zero Trust team domain, e.g. `damp-leaf-bc5b.cloudflareaccess.com` |
| `CF_ACCESS_AUD` | **Yes** (Prod) | — | AUD tag of the Access application. Without both, Cloudflare sign-in is disabled and only the admin password works |
| `DASHBOARD_BIND_ADDRESS` | Optional | `127.0.0.1` | Host address Docker publishes port 8080 on. The default keeps the origin reachable only through the tunnel; set `0.0.0.0` only if you really want it on the network |
| `PREFIX` | Optional | `$` | Default command prefix |
| `STREAMING_URL` | Optional | `https://j4fn.site` | URL behind the bot's streaming status |
| `WELCOME_CHANNEL_ID` | Optional | `""` | Channel ID for welcome greeting embeds |
| `MOD_LOG_CHANNEL_ID` | Optional | `""` | Channel ID for moderation audit logs |
| `MUTED_ROLE_NAME` | Optional | `Muted` | Role name assigned during timeouts |
| `DISCORD_CLIENT_ID` | Optional | — | OAuth2 client ID. With the secret and redirect URI, enables Discord sign-in at `/dashboard`; leave blank to keep it off |
| `DISCORD_CLIENT_SECRET` | Optional | — | OAuth2 client secret, from the same Developer Portal page |
| `OAUTH_REDIRECT_URI` | Optional | — | Must match a Redirect exactly in the app's OAuth2 settings, e.g. `https://bot.j4fn.site/auth/discord/callback` |
| `FLASK_SECRET_KEY` | Optional | *Auto-generated* | Signs the session cookie. Generated into `.env` on first boot; keep it stable or every deploy signs people out |
| `COOKIE_SECURE` | Optional | `1` | Set `0` only for plain-HTTP local development, so the session cookie is sent without TLS |
| `OCR_PROVIDER` | Optional | — | `ocrspace` or `google` to let the filter read text inside posted images. Blank keeps OCR off |
| `OCR_API_KEY` | Optional | — | Key for the provider above. Both must be set **and** `$automod set ocr_enabled on` run before any call is made |

---

## 🚀 Quick Start & Production Deployment

### Local Development

Use a **separate test bot** for local runs. If your PC and the server both log in
with the production token, every command is answered twice and moderation actions
run twice.

1. In the [Discord Developer Portal](https://discord.com/developers/applications), create
   a new application (e.g. `J4FN Dev`), open **Bot**, and copy its token.
2. On the same page, turn on all three **Privileged Gateway Intents**: Presence,
   Server Members, and Message Content. The bot won't start without them.
3. Invite the test bot to a test server: **OAuth2 ➔ URL Generator**, scope `bot`,
   permission `Administrator`.
4. Set up and start:

```bash
git clone https://github.com/MacroMaster101/discord-j4fn-server-bot.git
cd discord-j4fn-server-bot

cp .env.example .env
# In .env: set DISCORD_TOKEN to the test bot's token, set WEB_HOST=127.0.0.1,
# and leave CF_ACCESS_* / TUNNEL_TOKEN empty (Cloudflare isn't used locally)

pip install -r requirements.txt
python bot.py
```

Open http://localhost:8080. To use the admin console, go to `/login` and use the
admin password, which is printed on first start and saved to `.env` as
`ADMIN_PASSWORD`. Cloudflare Access sign-in only works on the deployed site.

### Docker & Cloudflare Tunnel (Oracle Cloud Deployment)
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
7. Copy the application's **AUD tag** from its Overview page. Put it and your team
   domain in the server's `.env` as `CF_ACCESS_AUD` and `CF_ACCESS_TEAM_DOMAIN`, then
   restart. The bot checks Cloudflare's signed login token against these, so Access
   sign-in stays disabled until both are set.

---

## 🌿 Branching & Contributing

Work flows in one direction: **`feature/*` → `dev` → `main`**.

| Branch | What it is | How code gets in |
| :--- | :--- | :--- |
| `main` | Production. Every push here deploys to the server. | Pull request from `dev` only, with a green `Tests` run. |
| `dev` | Integration. The default place to work. | Push directly, or merge a `feature/*` pull request. |
| `feature/*` | One change in progress. | Branch off `dev`, open a pull request back into `dev`. |

```bash
# start a change
git switch dev && git pull
git switch -c feature/my-change

# ...commit, then open a PR into dev
gh pr create --base dev

# release: dev -> main (this deploys)
gh pr create --base main --head dev
```

### What the rulesets enforce

- **`main`** — pull request required, the `Tests` check must pass and be up to
  date, review threads must be resolved, linear history, and no force-push or
  deletion. Approvals are set to **0** because this is a solo-maintained repo:
  requiring one would make every release unmergeable without a second account.
  Raise it under *Settings → Rules* the day a second maintainer reviews.
- **`dev`** — direct pushes are allowed on purpose, so day-to-day work is not
  stuck behind a pull request. Force-push and deletion are still blocked, so
  history cannot be rewritten under anyone.
- **`feature/*`** — deliberately unrestricted. Rebasing and force-pushing your
  own branch is normal; the gate that matters is the pull request into `dev`.

CI runs on every pull request into `dev` or `main` and on every push to `dev`.
Security scanning (CodeQL, secret scanning with push protection, and Dependabot)
runs on the repository; see [SECURITY.md](SECURITY.md) to report a vulnerability.

---

## 🤝 Contributing

Work flows `feature/* → dev → main`; see [CONTRIBUTING.md](CONTRIBUTING.md) for
the branch rules, local setup and the checks to run before opening a pull
request. Security problems go through [SECURITY.md](SECURITY.md) privately,
not a public issue.

---

## 📜 License

[MIT](LICENSE) © 2026 MacroMaster101.

The licence covers the code. The **J4FN name, the logo in `static/` and the
`j4fn.site` domain are not included** — reuse the bot, not the branding.
