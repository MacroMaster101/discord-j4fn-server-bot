import os
import sys
import time
import random
import asyncio
import threading
import datetime
import collections
import secrets
from functools import wraps

import requests
from dotenv import load_dotenv

import discord
from discord.ext import tasks

from flask import Flask, jsonify, request, render_template

# ----------------- GLOBAL LOGGER & WEB PANEL STATE -----------------

LOGS_BUFFER = collections.deque(maxlen=100)
PRESENCE_ROTATION_ENABLED = True
CUSTOM_PRESENCE_STATUS = "online"
CUSTOM_PRESENCE_ACTIVITY = "watching"
CUSTOM_PRESENCE_TEXT = ""
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

log_lock = threading.Lock()

def add_log(message, level="info"):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    with log_lock:
        LOGS_BUFFER.append({
            "timestamp": timestamp,
            "message": message,
            "level": level
        })
    sys.stdout.write(f"[{timestamp}] [{level.upper()}] {message}\n")
    sys.stdout.flush()

# ----------------- FLASK KEEP-ALIVE & ADMIN API -----------------

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=template_dir)
BOT_START_TIME = None

# Decorator for Authentication
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"message": "Unauthorized"}), 401
        
        token = auth_header.split(" ")[1]
        if token != ADMIN_PASSWORD:
            return jsonify({"message": "Unauthorized"}), 401
            
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/health")
def health():
    return "OK", 200

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    password = data.get("password")
    if password == ADMIN_PASSWORD:
        return jsonify({"token": ADMIN_PASSWORD}), 200
    return jsonify({"message": "Invalid password"}), 401

@app.route("/api/stats", methods=["GET"])
@require_auth
def api_stats():
    uptime_seconds = 0
    uptime_str = "N/A"
    if BOT_START_TIME:
        delta = datetime.datetime.utcnow() - BOT_START_TIME
        uptime_seconds = int(delta.total_seconds())
        h, r = divmod(uptime_seconds, 3600)
        m, s = divmod(r, 60)
        uptime_str = f"{h}h {m}m {s}s"
        
    latency_ms = round(client.latency * 1000) if client.is_ready() else 0
    server_count = len(client.guilds) if client.is_ready() else 0
    total_members = sum(g.member_count for g in client.guilds) if client.is_ready() else 0
    
    # System stats
    ram_usage = 32.5
    try:
        import resource
        ram_usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except ImportError:
        try:
            import ctypes
            process_handle = ctypes.windll.kernel32.GetCurrentProcess()
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)
                ]
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            if ctypes.windll.psapi.GetProcessMemoryInfo(process_handle, ctypes.byref(counters), counters.cb):
                ram_usage = counters.WorkingSetSize / (1024.0 * 1024.0)
        except Exception:
            pass
            
    thread_count = threading.active_count()
    sim_cpu = round(random.uniform(1.5, 4.5), 1)
    
    bot_user_data = None
    if client.user:
        bot_user_data = {
            "name": client.user.name,
            "discriminator": client.user.discriminator,
            "avatar": client.user.display_avatar.url if client.user.avatar else None
        }
        
    yt = get_youtube_channel_info() or {"name": "Unknown", "subscribers": 0, "views": 0, "videos": 0}
    
    return jsonify({
        "status": CUSTOM_PRESENCE_STATUS,
        "uptime": uptime_str,
        "uptime_seconds": uptime_seconds,
        "latency": latency_ms,
        "server_count": server_count,
        "total_members": total_members,
        "bot_user": bot_user_data,
        "youtube": yt,
        "system": {
            "cpu": sim_cpu,
            "ram": ram_usage,
            "threads": thread_count
        }
    })

@app.route("/api/config", methods=["GET"])
@require_auth
def api_get_config():
    return jsonify({
        "PREFIX": PREFIX,
        "WELCOME_CHANNEL_ID": WELCOME_CHANNEL_ID or "",
        "YOUTUBE_CHANNEL_ID": YOUTUBE_CHANNEL_ID or "",
        "YOUTUBE_API_KEY": YOUTUBE_API_KEY or ""
    })

@app.route("/api/config", methods=["POST"])
@require_auth
def api_set_config():
    global PREFIX, WELCOME_CHANNEL_ID, YOUTUBE_CHANNEL_ID, YOUTUBE_API_KEY, ADMIN_PASSWORD
    data = request.get_json() or {}
    
    prefix = data.get("PREFIX", "$")
    welcome_channel = data.get("WELCOME_CHANNEL_ID", "")
    yt_channel = data.get("YOUTUBE_CHANNEL_ID", "")
    yt_key = data.get("YOUTUBE_API_KEY", "")
    new_password = data.get("ADMIN_PASSWORD", "")
    
    try:
        update_env_variable("PREFIX", prefix)
        update_env_variable("WELCOME_CHANNEL_ID", welcome_channel)
        update_env_variable("YOUTUBE_CHANNEL_ID", yt_channel)
        update_env_variable("YOUTUBE_API_KEY", yt_key)
        
        if new_password:
            update_env_variable("ADMIN_PASSWORD", new_password)
            ADMIN_PASSWORD = new_password
            
        PREFIX = prefix
        WELCOME_CHANNEL_ID = welcome_channel
        YOUTUBE_CHANNEL_ID = yt_channel
        YOUTUBE_API_KEY = yt_key
        
        add_log(f"Configuration updated from control panel. Prefix: {PREFIX}", "success")
        return jsonify({"status": "success", "token": ADMIN_PASSWORD}), 200
    except Exception as e:
        add_log(f"Error saving configuration: {e}", "error")
        return jsonify({"message": f"Error saving: {e}"}), 500

@app.route("/api/servers", methods=["GET"])
@require_auth
def api_servers():
    if not client.is_ready():
        return jsonify([]), 200
        
    servers = []
    for guild in client.guilds:
        channels = []
        for ch in guild.text_channels:
            perms = ch.permissions_for(guild.me)
            if perms.send_messages:
                channels.append({
                    "id": str(ch.id),
                    "name": ch.name
                })
        servers.append({
            "id": str(guild.id),
            "name": guild.name,
            "member_count": guild.member_count,
            "channels": channels
        })
    return jsonify(servers)

@app.route("/api/send-message", methods=["POST"])
@require_auth
def api_send_message():
    data = request.get_json() or {}
    channel_id = data.get("channel_id")
    content = data.get("content")
    use_embed = data.get("embed", False)
    
    if not (channel_id and content):
        return jsonify({"message": "Missing channel ID or content"}), 400
        
    channel = client.get_channel(int(channel_id))
    if not channel:
        return jsonify({"message": "Channel not found"}), 404
        
    try:
        if use_embed:
            embed = discord.Embed(
                title="📢 Broadcast Announcement",
                description=content,
                color=0x5865F2,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Sent via Bot Dashboard", icon_url=client.user.display_avatar.url if client.user.avatar else None)
            fut = asyncio.run_coroutine_threadsafe(channel.send(embed=embed), client.loop)
        else:
            fut = asyncio.run_coroutine_threadsafe(channel.send(content), client.loop)
            
        fut.result()
        add_log(f"Broadcast message sent to #{channel.name} in {channel.guild.name}", "success")
        return jsonify({"status": "success"})
    except Exception as e:
        add_log(f"Failed sending message to {channel_id}: {e}", "error")
        return jsonify({"message": str(e)}), 500

@app.route("/api/presence", methods=["POST"])
@require_auth
def api_presence():
    global PRESENCE_ROTATION_ENABLED, CUSTOM_PRESENCE_STATUS, CUSTOM_PRESENCE_ACTIVITY, CUSTOM_PRESENCE_TEXT
    data = request.get_json() or {}
    
    status = data.get("status", "online")
    activity = data.get("activity", "watching")
    text = data.get("text", "")
    rotation = data.get("rotation", True)
    
    CUSTOM_PRESENCE_STATUS = status
    CUSTOM_PRESENCE_ACTIVITY = activity
    CUSTOM_PRESENCE_TEXT = text
    PRESENCE_ROTATION_ENABLED = rotation
    
    add_log(f"Presence updated: Status={status}, Activity={activity}, Text='{text}', Rotation={rotation}", "info")
    
    if not rotation:
        async def force_presence():
            act_type = discord.ActivityType.watching
            if activity == "playing": act_type = discord.ActivityType.playing
            elif activity == "listening": act_type = discord.ActivityType.listening
            elif activity == "streaming": act_type = discord.ActivityType.streaming
            
            sub_count = get_subscriber_count() or 0
            total_members = sum(g.member_count for g in client.guilds) if client.guilds else 0
            online_members = sum(1 for g in client.guilds for m in g.members if m.status != discord.Status.offline and not m.bot)
            server_count = len(client.guilds)
            
            formatted_text = text.format(
                sub_count=f"{sub_count:,}",
                total_members=f"{total_members:,}",
                online_members=f"{online_members:,}",
                server_count=server_count
            )
            
            act = discord.Activity(type=act_type, name=formatted_text)
            status_map = {
                "online": discord.Status.online,
                "idle": discord.Status.idle,
                "dnd": discord.Status.dnd,
                "invisible": discord.Status.invisible
            }
            await client.change_presence(status=status_map.get(status, discord.Status.online), activity=act)
            
        asyncio.run_coroutine_threadsafe(force_presence(), client.loop)
        
    return jsonify({"status": "success"})

@app.route("/api/presence/rotate", methods=["POST"])
@require_auth
def api_presence_rotate():
    asyncio.run_coroutine_threadsafe(update_status(), client.loop)
    add_log("Manual presence rotation loop skipped to next item", "info")
    return jsonify({"status": "success"})

@app.route("/api/logs", methods=["GET"])
@require_auth
def api_logs():
    with log_lock:
        return jsonify(list(LOGS_BUFFER))

@app.route("/api/restart", methods=["POST"])
@require_auth
def api_restart():
    add_log("Service reboot requested. Process exiting gracefully...", "warning")
    def schedule_exit():
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=schedule_exit).start()
    return jsonify({"status": "success"})


def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = threading.Thread(target=run_web, daemon=True)
    t.start()


# ----------------- CONFIG -----------------

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")
WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID")  # optional
PREFIX = os.getenv("PREFIX", "$")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

def update_env_variable(key, value):
    """Update a specific variable inside the .env file, creating it if needed."""
    env_path = ".env"
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    new_line = f"{key}={value}\n"
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = new_line
            found = True
            break
            
    if not found:
        lines.append(new_line)
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
client = discord.Client(intents=intents)


# ----------------- YOUTUBE HELPERS -----------------

def get_subscriber_count():
    if not (YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID):
        return None
    url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics&id={YOUTUBE_CHANNEL_ID}&key={YOUTUBE_API_KEY}"
    try:
        data = requests.get(url, timeout=10).json()
        items = data.get("items", [])
        if not items:
            return None
        return int(items[0]["statistics"].get("subscriberCount", 0))
    except Exception as e:
        print(f"YT sub error: {e}")
        return None


def get_youtube_channel_info():
    if not (YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID):
        return None
    url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&id={YOUTUBE_CHANNEL_ID}&key={YOUTUBE_API_KEY}"
    try:
        data = requests.get(url, timeout=10).json()
        items = data.get("items", [])
        if not items:
            return None
        snippet = items[0].get("snippet", {})
        stats = items[0].get("statistics", {})
        return {
            "name": snippet.get("title", "Unknown"),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "views": int(stats.get("viewCount", 0)),
            "videos": int(stats.get("videoCount", 0)),
        }
    except Exception as e:
        print(f"YT info error: {e}")
        return None


# ----------------- 8BALL & FUN DATA -----------------

EIGHT_BALL_RESPONSES = [
    "🟢 Yes, definitely!", "🟢 Without a doubt.", "🟢 It is certain.",
    "🟢 Most likely.", "🟢 Yes!", "🟢 Outlook good.",
    "🟡 Ask again later.", "🟡 Hard to say right now.", "🟡 Concentrate and ask again.",
    "🟡 Cannot predict now.", "🟡 Better not tell you now.",
    "🔴 Don't count on it.", "🔴 My sources say no.", "🔴 Very doubtful.",
    "🔴 Outlook not so good.", "🔴 No way.",
]

GREETING_RESPONSES = [
    "Hey {mention}! 👋 Welcome to the server! 🎮",
    "What's up {mention}! 🔥 Ready to game?",
    "Yo {mention}! 👋 Glad to have you here! 🎉",
    "Hey there {mention}! 💪 Let's gooo!",
    "Sup {mention}! 🎮 Welcome aboard!",
]

RPS_CHOICES = ["rock", "paper", "scissors"]
RPS_EMOJIS = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}


# -------------------- EVENTS --------------------

@client.event
async def on_ready():
    global BOT_START_TIME
    BOT_START_TIME = datetime.datetime.utcnow()
    add_log(f"Logged in as {client.user} (ID: {client.user.id})", "success")
    add_log(f"Serving {len(client.guilds)} server(s)", "info")
    update_status.start()


@tasks.loop(seconds=15)
async def update_status():
    """Rotate bot presence between YT stats and server stats if enabled."""
    if not PRESENCE_ROTATION_ENABLED:
        return

    # Gather stats
    sub_count = get_subscriber_count()
    total_members = sum(g.member_count for g in client.guilds)
    total_online = sum(
        1 for g in client.guilds
        for m in g.members
        if m.status != discord.Status.offline and not m.bot
    )
    server_count = len(client.guilds)

    # Build rotation list — each entry is (ActivityType, text)
    statuses = []

    if sub_count is not None:
        statuses.append((discord.ActivityType.watching, f"🔴 {sub_count:,} subs on YouTube"))

    statuses.append((discord.ActivityType.watching, f"👥 {total_members:,} members"))
    statuses.append((discord.ActivityType.watching, f"🟢 {total_online:,} online"))

    # Show server name
    guild_name = client.guilds[0].name if client.guilds else "the server"
    statuses.append((discord.ActivityType.watching, f"🎮 {guild_name}"))

    statuses.append((discord.ActivityType.playing, f"{PREFIX}help | Gaming 🎮"))

    # Pick the next status in rotation
    if not hasattr(update_status, "_index"):
        update_status._index = 0

    idx = update_status._index % len(statuses)
    activity_type, text = statuses[idx]
    update_status._index += 1

    activity = discord.Activity(type=activity_type, name=text)
    
    status_map = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible
    }
    status = status_map.get(CUSTOM_PRESENCE_STATUS, discord.Status.online)
    await client.change_presence(status=status, activity=activity)


@client.event
async def on_member_join(member: discord.Member):
    """Auto-welcome new members with a rich embed."""
    if member.bot:
        return

    add_log(f"New member joined: {member.name} (Guild: {member.guild.name})", "info")

    # Try the configured welcome channel, fall back to system channel
    channel = None
    if WELCOME_CHANNEL_ID:
        channel = member.guild.get_channel(int(WELCOME_CHANNEL_ID))
    if channel is None:
        channel = member.guild.system_channel
    if channel is None:
        return

    embed = discord.Embed(
        title="👋 Welcome to the server!",
        description=(
            f"Hey {member.mention}, welcome to **{member.guild.name}**! 🎉\n\n"
            f"🎮 Check out the channels and have fun!\n"
            f"📖 Type `{PREFIX}help` to see what I can do."
        ),
        color=0x57F287,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Member #{member.guild.member_count}")
    await channel.send(embed=embed)


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip().lower().rstrip(".!?")

    # ---- Greetings ----
    if content in ["hi", "hello", "hey", "sup", "yo", "wassup", "what's up"]:
        resp = random.choice(GREETING_RESPONSES).format(mention=message.author.mention)
        await message.channel.send(resp)
        add_log(f"Auto-greeted {message.author.name} (Guild: {message.guild.name if message.guild else 'DM'})", "info")
        return

    # ---- GG reactions ----
    if content in ["gg", "gg wp", "ggwp", "good game"]:
        await message.channel.send(f"GG {message.author.mention}! 🏆🔥")
        await message.add_reaction("🏆")
        add_log(f"Auto-GG reaction for {message.author.name} (Guild: {message.guild.name if message.guild else 'DM'})", "info")
        return

    # ---- Commands ----
    if not message.content.startswith(PREFIX):
        return

    raw = message.content[len(PREFIX):].strip()
    parts = raw.split(None, 1)
    cmd = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    add_log(f"Command '{PREFIX}{cmd}' executed by {message.author.name} (Guild: {message.guild.name if message.guild else 'DM'})", "info")

    # ---------- !ping ----------
    if cmd == "ping":
        latency = round(client.latency * 1000)
        embed = discord.Embed(title="🏓 Pong!", color=0x5865F2)
        embed.add_field(name="Latency", value=f"`{latency}ms`")
        await message.channel.send(embed=embed)

    # ---------- !stats ----------
    elif cmd == "stats":
        await cmd_stats(message)

    # ---------- !yt ----------
    elif cmd == "yt":
        await cmd_yt(message)

    # ---------- !userinfo ----------
    elif cmd in ("userinfo", "whois"):
        await cmd_userinfo(message, args)

    # ---------- !avatar ----------
    elif cmd in ("avatar", "av"):
        await cmd_avatar(message, args)

    # ---------- !servericon ----------
    elif cmd == "servericon":
        guild = message.guild
        if guild and guild.icon:
            embed = discord.Embed(title=f"🖼️ {guild.name}", color=0x5865F2)
            embed.set_image(url=guild.icon.with_size(1024).url)
            await message.channel.send(embed=embed)
        else:
            await message.channel.send("This server has no icon.")

    # ---------- !roll ----------
    elif cmd == "roll":
        sides = 6
        if args.isdigit() and int(args) > 1:
            sides = int(args)
        result = random.randint(1, sides)
        await message.channel.send(f"🎲 {message.author.mention} rolled a **{result}** (1-{sides})")

    # ---------- !flip ----------
    elif cmd in ("flip", "coin"):
        result = random.choice(["🪙 **Heads!**", "🪙 **Tails!**"])
        await message.channel.send(f"{message.author.mention} flipped: {result}")

    # ---------- !8ball ----------
    elif cmd == "8ball":
        if not args:
            await message.channel.send(f"❓ Ask me a question! Usage: `{PREFIX}8ball <question>`")
        else:
            answer = random.choice(EIGHT_BALL_RESPONSES)
            embed = discord.Embed(title="🎱 Magic 8-Ball", color=0x2B2D31)
            embed.add_field(name="Question", value=args, inline=False)
            embed.add_field(name="Answer", value=answer, inline=False)
            embed.set_footer(text=f"Asked by {message.author}")
            await message.channel.send(embed=embed)

    # ---------- !rps ----------
    elif cmd == "rps":
        if args.lower() not in RPS_CHOICES:
            await message.channel.send(f"✋ Usage: `{PREFIX}rps rock|paper|scissors`")
        else:
            user_choice = args.lower()
            bot_choice = random.choice(RPS_CHOICES)
            if user_choice == bot_choice:
                result = "🤝 It's a **tie**!"
            elif (user_choice == "rock" and bot_choice == "scissors") or \
                 (user_choice == "paper" and bot_choice == "rock") or \
                 (user_choice == "scissors" and bot_choice == "paper"):
                result = "🎉 You **win**!"
            else:
                result = "😎 I **win**!"
            embed = discord.Embed(title="Rock Paper Scissors", color=0xFEE75C)
            embed.add_field(name="You", value=f"{RPS_EMOJIS[user_choice]} {user_choice.title()}", inline=True)
            embed.add_field(name="Bot", value=f"{RPS_EMOJIS[bot_choice]} {bot_choice.title()}", inline=True)
            embed.add_field(name="Result", value=result, inline=False)
            await message.channel.send(embed=embed)

    # ---------- !poll ----------
    elif cmd == "poll":
        if not args:
            await message.channel.send(f"📊 Usage: `{PREFIX}poll <question>`")
        else:
            embed = discord.Embed(
                title="📊 Poll",
                description=args,
                color=0x5865F2,
                timestamp=datetime.datetime.utcnow(),
            )
            embed.set_footer(text=f"Poll by {message.author}")
            poll_msg = await message.channel.send(embed=embed)
            await poll_msg.add_reaction("👍")
            await poll_msg.add_reaction("👎")
            await poll_msg.add_reaction("🤷")

    # ---------- !uptime ----------
    elif cmd == "uptime":
        if BOT_START_TIME:
            delta = datetime.datetime.utcnow() - BOT_START_TIME
            h, r = divmod(int(delta.total_seconds()), 3600)
            m, s = divmod(r, 60)
            d, h = divmod(h, 24)
            embed = discord.Embed(title="⏱️ Bot Uptime", color=0x57F287)
            embed.description = f"**{d}d {h}h {m}m {s}s**"
            await message.channel.send(embed=embed)

    # ---------- !help ----------
    elif cmd == "help":
        await cmd_help(message)


# -------------------- COMMAND HANDLERS --------------------

async def cmd_stats(message):
    guild = message.guild
    if guild is None:
        await message.channel.send("This command can only be used in a server.")
        return

    total_members = guild.member_count
    text_ch = len(guild.text_channels)
    voice_ch = len(guild.voice_channels)
    categories = len(guild.categories)
    roles = len(guild.roles) - 1
    emojis = len(guild.emojis)
    boost_level = guild.premium_tier
    boosts = guild.premium_subscription_count or 0
    online = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
    bots = sum(1 for m in guild.members if m.bot)
    created = guild.created_at.strftime("%b %d, %Y")

    embed = discord.Embed(title=f"📊  {guild.name}  —  Server Stats", color=0x5865F2, timestamp=datetime.datetime.utcnow())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(name="👥 Members", value=f"{total_members:,}", inline=True)
    embed.add_field(name="🟢 Online", value=f"{online:,}", inline=True)
    embed.add_field(name="🤖 Bots", value=f"{bots:,}", inline=True)
    embed.add_field(name="💬 Text", value=str(text_ch), inline=True)
    embed.add_field(name="🔊 Voice", value=str(voice_ch), inline=True)
    embed.add_field(name="📂 Categories", value=str(categories), inline=True)
    embed.add_field(name="🏷️ Roles", value=str(roles), inline=True)
    embed.add_field(name="😀 Emojis", value=str(emojis), inline=True)
    embed.add_field(name="🚀 Boosts", value=f"Tier {boost_level} ({boosts})", inline=True)
    embed.add_field(name="👑 Owner", value=str(guild.owner), inline=True)
    embed.add_field(name="📅 Created", value=created, inline=True)

    yt = get_youtube_channel_info()
    if yt:
        yt_text = f"**{yt['name']}**\n📺 {yt['subscribers']:,} subs · 👁️ {yt['views']:,} views · 🎬 {yt['videos']:,} videos"
        embed.add_field(name="🔴 YouTube", value=yt_text, inline=False)

    embed.set_footer(text=f"Requested by {message.author}", icon_url=message.author.display_avatar.url)
    await message.channel.send(embed=embed)


async def cmd_yt(message):
    yt = get_youtube_channel_info()
    if yt is None:
        await message.channel.send("❌ Could not fetch YouTube data.")
        return
    embed = discord.Embed(title=f"🔴  {yt['name']}  —  YouTube Stats", color=0xFF0000, timestamp=datetime.datetime.utcnow())
    embed.add_field(name="📺 Subscribers", value=f"{yt['subscribers']:,}", inline=True)
    embed.add_field(name="👁️ Views", value=f"{yt['views']:,}", inline=True)
    embed.add_field(name="🎬 Videos", value=f"{yt['videos']:,}", inline=True)
    embed.set_footer(text=f"Requested by {message.author}", icon_url=message.author.display_avatar.url)
    await message.channel.send(embed=embed)


async def cmd_userinfo(message, args):
    # Mentioned user or self
    if message.mentions:
        member = message.mentions[0]
    else:
        member = message.author

    if not isinstance(member, discord.Member):
        await message.channel.send("Could not find that user.")
        return

    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    roles_str = ", ".join(roles[:10]) or "None"

    embed = discord.Embed(title=f"👤 {member}", color=member.color or 0x5865F2, timestamp=datetime.datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
    embed.add_field(name="Status", value=str(member.status).title(), inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%b %d, %Y"), inline=True)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "N/A", inline=True)
    embed.add_field(name="Top Role", value=member.top_role.mention if member.top_role.name != "@everyone" else "None", inline=True)
    embed.add_field(name=f"Roles ({len(roles)})", value=roles_str, inline=False)
    embed.set_footer(text=f"Requested by {message.author}", icon_url=message.author.display_avatar.url)
    await message.channel.send(embed=embed)


async def cmd_avatar(message, args):
    if message.mentions:
        user = message.mentions[0]
    else:
        user = message.author
    embed = discord.Embed(title=f"🖼️ {user.name}'s Avatar", color=0x5865F2)
    embed.set_image(url=user.display_avatar.with_size(1024).url)
    embed.set_footer(text=f"Requested by {message.author}")
    await message.channel.send(embed=embed)


async def cmd_help(message):
    embed = discord.Embed(
        title="📖 Bot Commands",
        description=f"Prefix: `{PREFIX}`",
        color=0x57F287,
        timestamp=datetime.datetime.utcnow(),
    )

    embed.add_field(name="📊 Info", value=(
        f"`{PREFIX}stats` — Server stats + YouTube\n"
        f"`{PREFIX}yt` — YouTube channel stats\n"
        f"`{PREFIX}userinfo [@user]` — User info\n"
        f"`{PREFIX}avatar [@user]` — User avatar\n"
        f"`{PREFIX}servericon` — Server icon\n"
        f"`{PREFIX}ping` — Bot latency\n"
        f"`{PREFIX}uptime` — Bot uptime"
    ), inline=False)

    embed.add_field(name="🎮 Fun & Games", value=(
        f"`{PREFIX}roll [sides]` — Roll a dice\n"
        f"`{PREFIX}flip` — Flip a coin\n"
        f"`{PREFIX}8ball <question>` — Magic 8-Ball\n"
        f"`{PREFIX}rps <rock|paper|scissors>` — Rock Paper Scissors\n"
        f"`{PREFIX}poll <question>` — Create a poll"
    ), inline=False)

    embed.add_field(name="💬 Auto Responses", value=(
        "Say `hi`, `hello`, `hey`, `yo`, `sup` — Greeting\n"
        "Say `gg`, `gg wp` — GG reaction 🏆"
    ), inline=False)

    embed.set_footer(text=f"Requested by {message.author}", icon_url=message.author.display_avatar.url)
    await message.channel.send(embed=embed)


# ----------------- RUN -----------------

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_TOKEN not set in environment or .env!")
    else:
        keep_alive()
        client.run(DISCORD_TOKEN)
