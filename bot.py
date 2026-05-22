import os
import sys
import json
import time
import random
import asyncio
import threading
import datetime
import collections
from functools import wraps

from dotenv import load_dotenv

import discord
from discord.ext import tasks

from flask import Flask, jsonify, request, render_template

# ----------------- GLOBAL LOGGER & WEB PANEL STATE -----------------

LOGS_BUFFER = collections.deque(maxlen=200)
MOD_ACTIONS_BUFFER = collections.deque(maxlen=200)
PRESENCE_ROTATION_ENABLED = True
CUSTOM_PRESENCE_STATUS = "online"
CUSTOM_PRESENCE_ACTIVITY = "watching"
CUSTOM_PRESENCE_TEXT = ""
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

log_lock = threading.Lock()
warn_lock = threading.Lock()

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
WARNINGS_FILE = os.path.join(DATA_DIR, "warnings.json")
os.makedirs(DATA_DIR, exist_ok=True)


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


def add_mod_action(action, moderator, target, reason, guild_name):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "moderator": str(moderator),
        "target": str(target),
        "reason": reason or "No reason provided",
        "guild": guild_name,
    }
    with log_lock:
        MOD_ACTIONS_BUFFER.append(entry)
    add_log(f"MOD: {action} {target} by {moderator} in {guild_name} — {reason or 'no reason'}", "warning")


# ----------------- WARNINGS PERSISTENCE -----------------

def _load_warnings():
    if not os.path.exists(WARNINGS_FILE):
        return {}
    try:
        with open(WARNINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_warnings(data):
    tmp = WARNINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, WARNINGS_FILE)


def add_warning(guild_id, user_id, moderator_id, reason):
    with warn_lock:
        data = _load_warnings()
        gkey = str(guild_id)
        ukey = str(user_id)
        data.setdefault(gkey, {}).setdefault(ukey, [])
        entry = {
            "id": int(time.time() * 1000),
            "moderator": str(moderator_id),
            "reason": reason or "No reason provided",
            "time": datetime.datetime.utcnow().isoformat() + "Z",
        }
        data[gkey][ukey].append(entry)
        _save_warnings(data)
        return len(data[gkey][ukey])


def get_warnings(guild_id, user_id):
    with warn_lock:
        data = _load_warnings()
        return data.get(str(guild_id), {}).get(str(user_id), [])


def clear_warnings(guild_id, user_id):
    with warn_lock:
        data = _load_warnings()
        gkey = str(guild_id)
        ukey = str(user_id)
        if gkey in data and ukey in data[gkey]:
            count = len(data[gkey][ukey])
            del data[gkey][ukey]
            _save_warnings(data)
            return count
        return 0


def all_warnings_for_guild(guild_id):
    with warn_lock:
        data = _load_warnings()
        return data.get(str(guild_id), {})


# ----------------- FLASK KEEP-ALIVE & ADMIN API -----------------

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=template_dir)
BOT_START_TIME = None


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
    online_members = 0
    if client.is_ready():
        online_members = sum(
            1 for g in client.guilds for m in g.members
            if m.status != discord.Status.offline and not m.bot
        )

    text_channels = sum(len(g.text_channels) for g in client.guilds) if client.is_ready() else 0
    voice_channels = sum(len(g.voice_channels) for g in client.guilds) if client.is_ready() else 0

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

    # Mod summary
    total_warnings = 0
    try:
        with warn_lock:
            wdata = _load_warnings()
        for g in wdata.values():
            for u in g.values():
                total_warnings += len(u)
    except Exception:
        pass

    with log_lock:
        recent_actions = len(MOD_ACTIONS_BUFFER)

    return jsonify({
        "status": CUSTOM_PRESENCE_STATUS,
        "uptime": uptime_str,
        "uptime_seconds": uptime_seconds,
        "latency": latency_ms,
        "server_count": server_count,
        "total_members": total_members,
        "online_members": online_members,
        "text_channels": text_channels,
        "voice_channels": voice_channels,
        "bot_user": bot_user_data,
        "moderation": {
            "total_warnings": total_warnings,
            "recent_actions": recent_actions,
        },
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
        "MOD_LOG_CHANNEL_ID": MOD_LOG_CHANNEL_ID or "",
        "MUTED_ROLE_NAME": MUTED_ROLE_NAME or "",
    })


@app.route("/api/config", methods=["POST"])
@require_auth
def api_set_config():
    global PREFIX, WELCOME_CHANNEL_ID, MOD_LOG_CHANNEL_ID, MUTED_ROLE_NAME, ADMIN_PASSWORD
    data = request.get_json() or {}

    prefix = data.get("PREFIX", "$")
    welcome_channel = data.get("WELCOME_CHANNEL_ID", "")
    mod_log = data.get("MOD_LOG_CHANNEL_ID", "")
    muted_role = data.get("MUTED_ROLE_NAME", "Muted")
    new_password = data.get("ADMIN_PASSWORD", "")

    try:
        update_env_variable("PREFIX", prefix)
        update_env_variable("WELCOME_CHANNEL_ID", welcome_channel)
        update_env_variable("MOD_LOG_CHANNEL_ID", mod_log)
        update_env_variable("MUTED_ROLE_NAME", muted_role)

        if new_password:
            update_env_variable("ADMIN_PASSWORD", new_password)
            ADMIN_PASSWORD = new_password

        PREFIX = prefix
        WELCOME_CHANNEL_ID = welcome_channel
        MOD_LOG_CHANNEL_ID = mod_log
        MUTED_ROLE_NAME = muted_role

        add_log(f"Configuration updated. Prefix: {PREFIX}", "success")
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
                channels.append({"id": str(ch.id), "name": ch.name})
        servers.append({
            "id": str(guild.id),
            "name": guild.name,
            "member_count": guild.member_count,
            "icon": guild.icon.url if guild.icon else None,
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
            embed.set_footer(text="Sent via Bot Dashboard",
                             icon_url=client.user.display_avatar.url if client.user.avatar else None)
            fut = asyncio.run_coroutine_threadsafe(channel.send(embed=embed), client.loop)
        else:
            fut = asyncio.run_coroutine_threadsafe(channel.send(content), client.loop)
        fut.result()
        add_log(f"Broadcast sent to #{channel.name} in {channel.guild.name}", "success")
        return jsonify({"status": "success"})
    except Exception as e:
        add_log(f"Failed sending to {channel_id}: {e}", "error")
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

    add_log(f"Presence updated: status={status}, activity={activity}, text='{text}', rotation={rotation}", "info")

    if not rotation:
        async def force_presence():
            act_type = discord.ActivityType.watching
            if activity == "playing":
                act_type = discord.ActivityType.playing
            elif activity == "listening":
                act_type = discord.ActivityType.listening
            elif activity == "streaming":
                act_type = discord.ActivityType.streaming

            total_members = sum(g.member_count for g in client.guilds) if client.guilds else 0
            online_members = sum(
                1 for g in client.guilds for m in g.members
                if m.status != discord.Status.offline and not m.bot
            )
            server_count = len(client.guilds)

            formatted = text.format(
                total_members=f"{total_members:,}",
                online_members=f"{online_members:,}",
                server_count=server_count,
                prefix=PREFIX,
            )

            act = discord.Activity(type=act_type, name=formatted or f"{PREFIX}help")
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
    return jsonify({"status": "success"})


@app.route("/api/logs", methods=["GET"])
@require_auth
def api_logs():
    with log_lock:
        return jsonify(list(LOGS_BUFFER))


@app.route("/api/mod/actions", methods=["GET"])
@require_auth
def api_mod_actions():
    with log_lock:
        return jsonify(list(MOD_ACTIONS_BUFFER))


@app.route("/api/mod/warnings", methods=["GET"])
@require_auth
def api_mod_warnings():
    guild_id = request.args.get("guild_id")
    if not guild_id:
        return jsonify({"message": "guild_id required"}), 400
    if not client.is_ready():
        return jsonify({"warnings": []}), 200

    guild = client.get_guild(int(guild_id))
    if guild is None:
        return jsonify({"warnings": []}), 200

    raw = all_warnings_for_guild(guild_id)
    result = []
    for uid, entries in raw.items():
        member = guild.get_member(int(uid))
        result.append({
            "user_id": uid,
            "user_name": str(member) if member else f"Unknown ({uid})",
            "avatar": member.display_avatar.url if member else None,
            "count": len(entries),
            "warnings": entries,
        })
    result.sort(key=lambda x: x["count"], reverse=True)
    return jsonify({"warnings": result})


@app.route("/api/mod/action", methods=["POST"])
@require_auth
def api_mod_action():
    data = request.get_json() or {}
    action = data.get("action")
    guild_id = data.get("guild_id")
    user_id = data.get("user_id")
    reason = data.get("reason", "Issued from dashboard")
    duration = data.get("duration")  # minutes for timeout

    if not (action and guild_id and user_id):
        return jsonify({"message": "action, guild_id, user_id required"}), 400

    if not client.is_ready():
        return jsonify({"message": "Bot not ready"}), 503

    guild = client.get_guild(int(guild_id))
    if guild is None:
        return jsonify({"message": "Guild not found"}), 404

    async def run_action():
        try:
            if action == "ban":
                user = discord.Object(id=int(user_id))
                await guild.ban(user, reason=f"[Dashboard] {reason}", delete_message_days=0)
                add_mod_action("ban", "Dashboard", user_id, reason, guild.name)
                return True, "Banned"

            if action == "unban":
                user = discord.Object(id=int(user_id))
                await guild.unban(user, reason=f"[Dashboard] {reason}")
                add_mod_action("unban", "Dashboard", user_id, reason, guild.name)
                return True, "Unbanned"

            member = guild.get_member(int(user_id))
            if member is None:
                return False, "Member not found in guild"

            if action == "kick":
                await member.kick(reason=f"[Dashboard] {reason}")
                add_mod_action("kick", "Dashboard", member, reason, guild.name)
                return True, "Kicked"

            if action == "timeout":
                mins = int(duration) if duration else 10
                until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=mins)
                await member.timeout(until, reason=f"[Dashboard] {reason}")
                add_mod_action("timeout", "Dashboard", member, f"{reason} ({mins}m)", guild.name)
                return True, f"Timed out for {mins}m"

            if action == "untimeout":
                await member.timeout(None, reason=f"[Dashboard] {reason}")
                add_mod_action("untimeout", "Dashboard", member, reason, guild.name)
                return True, "Timeout removed"

            if action == "warn":
                count = add_warning(guild_id, user_id, "Dashboard", reason)
                add_mod_action("warn", "Dashboard", member, f"{reason} (total: {count})", guild.name)
                return True, f"Warned (total: {count})"

            if action == "clear_warnings":
                count = clear_warnings(guild_id, user_id)
                add_mod_action("clear_warnings", "Dashboard", member, f"Cleared {count}", guild.name)
                return True, f"Cleared {count} warnings"

            return False, f"Unknown action: {action}"
        except discord.Forbidden:
            return False, "Bot lacks permissions"
        except discord.HTTPException as e:
            return False, f"Discord error: {e}"
        except Exception as e:
            return False, str(e)

    fut = asyncio.run_coroutine_threadsafe(run_action(), client.loop)
    try:
        ok, msg = fut.result(timeout=15)
    except Exception as e:
        return jsonify({"message": str(e)}), 500

    if not ok:
        return jsonify({"message": msg}), 400
    return jsonify({"status": "success", "message": msg})


@app.route("/api/restart", methods=["POST"])
@require_auth
def api_restart():
    add_log("Service reboot requested. Exiting...", "warning")
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
WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID")
MOD_LOG_CHANNEL_ID = os.getenv("MOD_LOG_CHANNEL_ID")
MUTED_ROLE_NAME = os.getenv("MUTED_ROLE_NAME", "Muted")
PREFIX = os.getenv("PREFIX", "$")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def update_env_variable(key, value):
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


# ----------------- AUTO-MOD STATE -----------------

# Tracks recent messages per (guild, user) for spam detection: deque of timestamps
_spam_buckets = collections.defaultdict(lambda: collections.deque(maxlen=10))
SPAM_THRESHOLD = 5      # messages
SPAM_WINDOW = 6.0       # seconds


# ----------------- FUN DATA -----------------

EIGHT_BALL_RESPONSES = [
    "🟢 Yes, definitely!", "🟢 Without a doubt.", "🟢 It is certain.",
    "🟢 Most likely.", "🟢 Yes!", "🟢 Outlook good.",
    "🟡 Ask again later.", "🟡 Hard to say right now.", "🟡 Concentrate and ask again.",
    "🟡 Cannot predict now.", "🟡 Better not tell you now.",
    "🔴 Don't count on it.", "🔴 My sources say no.", "🔴 Very doubtful.",
    "🔴 Outlook not so good.", "🔴 No way.",
]

GREETING_RESPONSES = [
    "Hey {mention}! 👋 Welcome!",
    "What's up {mention}! 🔥",
    "Yo {mention}! 👋 Glad to see you!",
    "Hey there {mention}! 💪",
    "Sup {mention}! 🎮",
]

RPS_CHOICES = ["rock", "paper", "scissors"]
RPS_EMOJIS = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}


# ----------------- MOD LOG HELPER -----------------

async def send_mod_log(guild, title, description, color=0xED4245):
    if not MOD_LOG_CHANNEL_ID:
        return
    try:
        ch = guild.get_channel(int(MOD_LOG_CHANNEL_ID))
        if ch is None:
            return
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.utcnow(),
        )
        await ch.send(embed=embed)
    except Exception as e:
        add_log(f"mod-log send failed: {e}", "error")


def has_mod_perms(member: discord.Member, perm: str) -> bool:
    if member.guild_permissions.administrator:
        return True
    return getattr(member.guild_permissions, perm, False)


def resolve_member(message: discord.Message, args: str):
    """Resolve first argument to a Member: mention, id, or name."""
    if message.mentions:
        return message.mentions[0], args.split(None, 1)[1] if len(args.split(None, 1)) > 1 else ""

    parts = args.split(None, 1)
    if not parts:
        return None, ""
    token = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    if token.isdigit():
        m = message.guild.get_member(int(token))
        if m:
            return m, rest

    lowered = token.lower()
    for m in message.guild.members:
        if m.name.lower() == lowered or (m.nick and m.nick.lower() == lowered) or str(m).lower() == lowered:
            return m, rest
    return None, rest


# -------------------- EVENTS --------------------

@client.event
async def on_ready():
    global BOT_START_TIME
    BOT_START_TIME = datetime.datetime.utcnow()
    add_log(f"Logged in as {client.user} (ID: {client.user.id})", "success")
    add_log(f"Serving {len(client.guilds)} server(s)", "info")
    if not update_status.is_running():
        update_status.start()


@tasks.loop(seconds=20)
async def update_status():
    """Rotate bot presence between server stats."""
    if not PRESENCE_ROTATION_ENABLED:
        return

    total_members = sum(g.member_count for g in client.guilds)
    total_online = sum(
        1 for g in client.guilds for m in g.members
        if m.status != discord.Status.offline and not m.bot
    )
    server_count = len(client.guilds)

    statuses = [
        (discord.ActivityType.watching, f"👥 {total_members:,} members"),
        (discord.ActivityType.watching, f"🟢 {total_online:,} online"),
        (discord.ActivityType.watching, f"🌐 {server_count} server{'s' if server_count != 1 else ''}"),
        (discord.ActivityType.playing, f"{PREFIX}help | Moderating 🛡️"),
    ]

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
    if member.bot:
        return

    add_log(f"Member joined: {member.name} ({member.guild.name})", "info")

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
            f"📖 Type `{PREFIX}help` to see what I can do."
        ),
        color=0x57F287,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Member #{member.guild.member_count}")
    await channel.send(embed=embed)


@client.event
async def on_member_remove(member: discord.Member):
    add_log(f"Member left: {member.name} ({member.guild.name})", "info")
    await send_mod_log(
        member.guild,
        "📤 Member Left",
        f"{member.mention} (`{member}`) left the server.",
        color=0x99AAB5,
    )


@client.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    desc = (
        f"**Author:** {message.author.mention}\n"
        f"**Channel:** {message.channel.mention}\n"
        f"**Content:** {message.content[:1000] or '*(no text)*'}"
    )
    await send_mod_log(message.guild, "🗑️ Message Deleted", desc, color=0xED4245)


@client.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        # Still allow DM commands? keep server-only for mod bot
        if message.author.bot:
            return

    # ---- Auto-moderation: spam ----
    if message.guild and not message.author.guild_permissions.manage_messages:
        bucket = _spam_buckets[(message.guild.id, message.author.id)]
        now = time.time()
        bucket.append(now)
        recent = [t for t in bucket if now - t < SPAM_WINDOW]
        if len(recent) >= SPAM_THRESHOLD:
            try:
                until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
                await message.author.timeout(until, reason="Auto-mod: spam")
                await message.channel.send(
                    f"🛡️ {message.author.mention} has been muted for 5 minutes (spam detected)."
                )
                add_mod_action("auto-timeout", "AutoMod", message.author, "Spam detected (5m)", message.guild.name)
                await send_mod_log(
                    message.guild, "🛡️ Auto-Mod Timeout",
                    f"{message.author.mention} timed out **5m** for spam.",
                    color=0xFEE75C,
                )
                bucket.clear()
            except discord.Forbidden:
                pass
            return

    content_lower = message.content.strip().lower().rstrip(".!?")

    if content_lower in ["hi", "hello", "hey", "sup", "yo", "wassup", "what's up"]:
        resp = random.choice(GREETING_RESPONSES).format(mention=message.author.mention)
        await message.channel.send(resp)
        return

    if content_lower in ["gg", "gg wp", "ggwp", "good game"]:
        await message.channel.send(f"GG {message.author.mention}! 🏆🔥")
        try:
            await message.add_reaction("🏆")
        except Exception:
            pass
        return

    if not message.content.startswith(PREFIX):
        return

    raw = message.content[len(PREFIX):].strip()
    parts = raw.split(None, 1)
    cmd = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    add_log(f"Command '{PREFIX}{cmd}' by {message.author.name} ({message.guild.name if message.guild else 'DM'})", "info")

    # --- Info commands ---
    if cmd == "ping":
        latency = round(client.latency * 1000)
        embed = discord.Embed(title="🏓 Pong!", color=0x5865F2)
        embed.add_field(name="Latency", value=f"`{latency}ms`")
        await message.channel.send(embed=embed)

    elif cmd == "stats":
        await cmd_stats(message)

    elif cmd in ("userinfo", "whois"):
        await cmd_userinfo(message, args)

    elif cmd in ("avatar", "av"):
        await cmd_avatar(message, args)

    elif cmd == "servericon":
        guild = message.guild
        if guild and guild.icon:
            embed = discord.Embed(title=f"🖼️ {guild.name}", color=0x5865F2)
            embed.set_image(url=guild.icon.with_size(1024).url)
            await message.channel.send(embed=embed)
        else:
            await message.channel.send("This server has no icon.")

    elif cmd == "roll":
        sides = 6
        if args.isdigit() and int(args) > 1:
            sides = int(args)
        result = random.randint(1, sides)
        await message.channel.send(f"🎲 {message.author.mention} rolled a **{result}** (1-{sides})")

    elif cmd in ("flip", "coin"):
        result = random.choice(["🪙 **Heads!**", "🪙 **Tails!**"])
        await message.channel.send(f"{message.author.mention} flipped: {result}")

    elif cmd == "8ball":
        if not args:
            await message.channel.send(f"❓ Usage: `{PREFIX}8ball <question>`")
        else:
            answer = random.choice(EIGHT_BALL_RESPONSES)
            embed = discord.Embed(title="🎱 Magic 8-Ball", color=0x2B2D31)
            embed.add_field(name="Question", value=args, inline=False)
            embed.add_field(name="Answer", value=answer, inline=False)
            embed.set_footer(text=f"Asked by {message.author}")
            await message.channel.send(embed=embed)

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

    elif cmd == "poll":
        if not args:
            await message.channel.send(f"📊 Usage: `{PREFIX}poll <question>`")
        else:
            embed = discord.Embed(title="📊 Poll", description=args, color=0x5865F2,
                                  timestamp=datetime.datetime.utcnow())
            embed.set_footer(text=f"Poll by {message.author}")
            poll_msg = await message.channel.send(embed=embed)
            await poll_msg.add_reaction("👍")
            await poll_msg.add_reaction("👎")
            await poll_msg.add_reaction("🤷")

    elif cmd == "uptime":
        if BOT_START_TIME:
            delta = datetime.datetime.utcnow() - BOT_START_TIME
            h, r = divmod(int(delta.total_seconds()), 3600)
            m, s = divmod(r, 60)
            d, h = divmod(h, 24)
            embed = discord.Embed(title="⏱️ Bot Uptime", color=0x57F287)
            embed.description = f"**{d}d {h}h {m}m {s}s**"
            await message.channel.send(embed=embed)

    # --- Moderation commands ---
    elif cmd == "kick":
        await cmd_kick(message, args)
    elif cmd == "ban":
        await cmd_ban(message, args)
    elif cmd == "unban":
        await cmd_unban(message, args)
    elif cmd in ("mute", "timeout"):
        await cmd_timeout(message, args)
    elif cmd in ("unmute", "untimeout"):
        await cmd_untimeout(message, args)
    elif cmd == "warn":
        await cmd_warn(message, args)
    elif cmd in ("warnings", "warns"):
        await cmd_warnings(message, args)
    elif cmd in ("clearwarns", "delwarns"):
        await cmd_clearwarns(message, args)
    elif cmd in ("purge", "clear"):
        await cmd_purge(message, args)
    elif cmd == "slowmode":
        await cmd_slowmode(message, args)
    elif cmd == "lock":
        await cmd_lock(message, lock=True)
    elif cmd == "unlock":
        await cmd_lock(message, lock=False)
    elif cmd in ("nick", "nickname"):
        await cmd_nick(message, args)
    elif cmd == "addrole":
        await cmd_role(message, args, add=True)
    elif cmd == "removerole":
        await cmd_role(message, args, add=False)

    elif cmd == "help":
        await cmd_help(message)


# -------------------- INFO HANDLERS --------------------

async def cmd_stats(message):
    guild = message.guild
    if guild is None:
        await message.channel.send("Server-only command.")
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

    embed = discord.Embed(title=f"📊  {guild.name}  —  Server Stats",
                          color=0x5865F2, timestamp=datetime.datetime.utcnow())
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

    # mod summary for this guild
    guild_warns = all_warnings_for_guild(guild.id)
    total_warns = sum(len(v) for v in guild_warns.values())
    embed.add_field(name="⚠️ Active Warnings", value=str(total_warns), inline=True)

    embed.set_footer(text=f"Requested by {message.author}", icon_url=message.author.display_avatar.url)
    await message.channel.send(embed=embed)


async def cmd_userinfo(message, args):
    if message.mentions:
        member = message.mentions[0]
    else:
        member = message.author

    if not isinstance(member, discord.Member):
        await message.channel.send("Could not find that user.")
        return

    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    roles_str = ", ".join(roles[:10]) or "None"
    warns = get_warnings(message.guild.id, member.id)

    embed = discord.Embed(title=f"👤 {member}", color=member.color or 0x5865F2,
                          timestamp=datetime.datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
    embed.add_field(name="Status", value=str(member.status).title(), inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%b %d, %Y"), inline=True)
    embed.add_field(name="Joined Server",
                    value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "N/A", inline=True)
    embed.add_field(name="Top Role",
                    value=member.top_role.mention if member.top_role.name != "@everyone" else "None", inline=True)
    embed.add_field(name=f"Roles ({len(roles)})", value=roles_str, inline=False)
    embed.add_field(name="⚠️ Warnings", value=str(len(warns)), inline=True)
    embed.set_footer(text=f"Requested by {message.author}", icon_url=message.author.display_avatar.url)
    await message.channel.send(embed=embed)


async def cmd_avatar(message, args):
    user = message.mentions[0] if message.mentions else message.author
    embed = discord.Embed(title=f"🖼️ {user.name}'s Avatar", color=0x5865F2)
    embed.set_image(url=user.display_avatar.with_size(1024).url)
    embed.set_footer(text=f"Requested by {message.author}")
    await message.channel.send(embed=embed)


# -------------------- MODERATION HANDLERS --------------------

def _parse_duration(text: str) -> int:
    """Parse '10', '10m', '1h', '1d' into minutes. Default 10."""
    if not text:
        return 10
    text = text.strip().lower()
    if text.isdigit():
        return int(text)
    try:
        if text.endswith("m"):
            return int(text[:-1])
        if text.endswith("h"):
            return int(text[:-1]) * 60
        if text.endswith("d"):
            return int(text[:-1]) * 60 * 24
        if text.endswith("s"):
            return max(1, int(text[:-1]) // 60)
    except ValueError:
        pass
    return 10


async def cmd_kick(message, args):
    if not has_mod_perms(message.author, "kick_members"):
        await message.channel.send("🚫 You need **Kick Members** permission.")
        return
    member, reason = resolve_member(message, args)
    if not member:
        await message.channel.send(f"Usage: `{PREFIX}kick @user [reason]`")
        return
    if member.top_role >= message.author.top_role and message.author != message.guild.owner:
        await message.channel.send("🚫 Can't kick a member with equal or higher role.")
        return
    try:
        await member.kick(reason=f"[{message.author}] {reason or 'No reason'}")
        await message.channel.send(f"👢 {member} has been kicked. Reason: {reason or 'No reason'}")
        add_mod_action("kick", message.author, member, reason, message.guild.name)
        await send_mod_log(message.guild, "👢 Member Kicked",
                           f"**Member:** {member.mention} (`{member.id}`)\n"
                           f"**Moderator:** {message.author.mention}\n"
                           f"**Reason:** {reason or 'No reason'}")
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission to kick that user.")


async def cmd_ban(message, args):
    if not has_mod_perms(message.author, "ban_members"):
        await message.channel.send("🚫 You need **Ban Members** permission.")
        return
    member, reason = resolve_member(message, args)
    if not member:
        # Try ID-only ban (user not in server)
        parts = args.split(None, 1)
        if parts and parts[0].isdigit():
            user_id = int(parts[0])
            reason = parts[1] if len(parts) > 1 else ""
            try:
                await message.guild.ban(discord.Object(id=user_id),
                                        reason=f"[{message.author}] {reason or 'No reason'}")
                await message.channel.send(f"🔨 User `{user_id}` banned.")
                add_mod_action("ban", message.author, user_id, reason, message.guild.name)
                return
            except discord.HTTPException as e:
                await message.channel.send(f"🚫 Failed: {e}")
                return
        await message.channel.send(f"Usage: `{PREFIX}ban @user [reason]`")
        return
    if member.top_role >= message.author.top_role and message.author != message.guild.owner:
        await message.channel.send("🚫 Can't ban a member with equal or higher role.")
        return
    try:
        await member.ban(reason=f"[{message.author}] {reason or 'No reason'}", delete_message_days=0)
        await message.channel.send(f"🔨 {member} has been banned. Reason: {reason or 'No reason'}")
        add_mod_action("ban", message.author, member, reason, message.guild.name)
        await send_mod_log(message.guild, "🔨 Member Banned",
                           f"**Member:** {member.mention} (`{member.id}`)\n"
                           f"**Moderator:** {message.author.mention}\n"
                           f"**Reason:** {reason or 'No reason'}")
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission to ban that user.")


async def cmd_unban(message, args):
    if not has_mod_perms(message.author, "ban_members"):
        await message.channel.send("🚫 You need **Ban Members** permission.")
        return
    parts = args.split(None, 1)
    if not parts or not parts[0].isdigit():
        await message.channel.send(f"Usage: `{PREFIX}unban <user_id> [reason]`")
        return
    user_id = int(parts[0])
    reason = parts[1] if len(parts) > 1 else ""
    try:
        await message.guild.unban(discord.Object(id=user_id),
                                  reason=f"[{message.author}] {reason or 'No reason'}")
        await message.channel.send(f"✅ User `{user_id}` unbanned.")
        add_mod_action("unban", message.author, user_id, reason, message.guild.name)
        await send_mod_log(message.guild, "✅ Member Unbanned",
                           f"**User ID:** `{user_id}`\n**Moderator:** {message.author.mention}\n"
                           f"**Reason:** {reason or 'No reason'}", color=0x57F287)
    except discord.NotFound:
        await message.channel.send("🚫 That user is not banned.")
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission to unban.")


async def cmd_timeout(message, args):
    if not has_mod_perms(message.author, "moderate_members"):
        await message.channel.send("🚫 You need **Moderate Members** permission.")
        return
    member, rest = resolve_member(message, args)
    if not member:
        await message.channel.send(f"Usage: `{PREFIX}mute @user <duration> [reason]` (e.g. 10m, 1h, 1d)")
        return
    parts = rest.split(None, 1)
    duration_str = parts[0] if parts else "10m"
    reason = parts[1] if len(parts) > 1 else ""
    minutes = _parse_duration(duration_str)
    if minutes <= 0 or minutes > 60 * 24 * 28:
        await message.channel.send("🚫 Duration must be between 1 minute and 28 days.")
        return
    until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
    try:
        await member.timeout(until, reason=f"[{message.author}] {reason or 'No reason'}")
        await message.channel.send(f"🔇 {member.mention} muted for **{minutes}m**. Reason: {reason or 'No reason'}")
        add_mod_action("timeout", message.author, member, f"{reason} ({minutes}m)", message.guild.name)
        await send_mod_log(message.guild, "🔇 Member Timed Out",
                           f"**Member:** {member.mention}\n**Duration:** {minutes} minutes\n"
                           f"**Moderator:** {message.author.mention}\n**Reason:** {reason or 'No reason'}",
                           color=0xFEE75C)
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission to timeout that user.")


async def cmd_untimeout(message, args):
    if not has_mod_perms(message.author, "moderate_members"):
        await message.channel.send("🚫 You need **Moderate Members** permission.")
        return
    member, reason = resolve_member(message, args)
    if not member:
        await message.channel.send(f"Usage: `{PREFIX}unmute @user`")
        return
    try:
        await member.timeout(None, reason=f"[{message.author}] {reason or 'unmute'}")
        await message.channel.send(f"🔊 {member.mention} unmuted.")
        add_mod_action("untimeout", message.author, member, reason, message.guild.name)
        await send_mod_log(message.guild, "🔊 Timeout Removed",
                           f"**Member:** {member.mention}\n**Moderator:** {message.author.mention}",
                           color=0x57F287)
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission.")


async def cmd_warn(message, args):
    if not has_mod_perms(message.author, "kick_members"):
        await message.channel.send("🚫 You need **Kick Members** permission.")
        return
    member, reason = resolve_member(message, args)
    if not member:
        await message.channel.send(f"Usage: `{PREFIX}warn @user <reason>`")
        return
    if not reason:
        reason = "No reason provided"
    count = add_warning(message.guild.id, member.id, message.author.id, reason)
    embed = discord.Embed(title="⚠️ Warning Issued", color=0xFEE75C,
                          timestamp=datetime.datetime.utcnow())
    embed.add_field(name="Member", value=member.mention, inline=True)
    embed.add_field(name="Total Warnings", value=str(count), inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text=f"By {message.author}")
    await message.channel.send(embed=embed)
    add_mod_action("warn", message.author, member, f"{reason} (total: {count})", message.guild.name)
    await send_mod_log(message.guild, "⚠️ Warning Issued",
                       f"**Member:** {member.mention}\n**Moderator:** {message.author.mention}\n"
                       f"**Reason:** {reason}\n**Total Warnings:** {count}", color=0xFEE75C)
    try:
        await member.send(f"⚠️ You were warned in **{message.guild.name}**.\nReason: {reason}")
    except Exception:
        pass


async def cmd_warnings(message, args):
    member, _ = resolve_member(message, args) if args else (message.author, "")
    if not member:
        member = message.author
    warns = get_warnings(message.guild.id, member.id)
    embed = discord.Embed(title=f"⚠️ Warnings for {member}", color=0xFEE75C)
    if not warns:
        embed.description = "No warnings on record."
    else:
        for i, w in enumerate(warns[-10:], 1):
            embed.add_field(
                name=f"#{i} — {w['time'][:10]}",
                value=f"**Reason:** {w['reason']}\n**Mod ID:** `{w['moderator']}`",
                inline=False,
            )
        embed.set_footer(text=f"Total: {len(warns)} (showing last 10)")
    await message.channel.send(embed=embed)


async def cmd_clearwarns(message, args):
    if not has_mod_perms(message.author, "kick_members"):
        await message.channel.send("🚫 You need **Kick Members** permission.")
        return
    member, _ = resolve_member(message, args)
    if not member:
        await message.channel.send(f"Usage: `{PREFIX}clearwarns @user`")
        return
    count = clear_warnings(message.guild.id, member.id)
    await message.channel.send(f"🧹 Cleared **{count}** warning(s) for {member.mention}.")
    add_mod_action("clear_warnings", message.author, member, f"cleared {count}", message.guild.name)


async def cmd_purge(message, args):
    if not has_mod_perms(message.author, "manage_messages"):
        await message.channel.send("🚫 You need **Manage Messages** permission.")
        return
    if not args.isdigit():
        await message.channel.send(f"Usage: `{PREFIX}purge <count>` (1–100)")
        return
    count = max(1, min(100, int(args)))
    try:
        deleted = await message.channel.purge(limit=count + 1)
        msg = await message.channel.send(f"🧹 Deleted **{len(deleted)-1}** messages.")
        add_mod_action("purge", message.author, f"#{message.channel.name}",
                       f"{len(deleted)-1} messages", message.guild.name)
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except Exception:
            pass
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission to delete messages.")


async def cmd_slowmode(message, args):
    if not has_mod_perms(message.author, "manage_channels"):
        await message.channel.send("🚫 You need **Manage Channels** permission.")
        return
    if not args.isdigit():
        await message.channel.send(f"Usage: `{PREFIX}slowmode <seconds>` (0 to disable)")
        return
    seconds = max(0, min(21600, int(args)))
    try:
        await message.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await message.channel.send("⏱️ Slowmode disabled.")
        else:
            await message.channel.send(f"⏱️ Slowmode set to **{seconds}s**.")
        add_mod_action("slowmode", message.author, f"#{message.channel.name}",
                       f"{seconds}s", message.guild.name)
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission.")


async def cmd_lock(message, lock: bool):
    if not has_mod_perms(message.author, "manage_channels"):
        await message.channel.send("🚫 You need **Manage Channels** permission.")
        return
    overwrite = message.channel.overwrites_for(message.guild.default_role)
    overwrite.send_messages = False if lock else None
    try:
        await message.channel.set_permissions(message.guild.default_role, overwrite=overwrite)
        await message.channel.send(f"🔒 Channel **locked**." if lock else f"🔓 Channel **unlocked**.")
        add_mod_action("lock" if lock else "unlock", message.author,
                       f"#{message.channel.name}", "", message.guild.name)
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission.")


async def cmd_nick(message, args):
    if not has_mod_perms(message.author, "manage_nicknames"):
        await message.channel.send("🚫 You need **Manage Nicknames** permission.")
        return
    member, rest = resolve_member(message, args)
    if not member:
        await message.channel.send(f"Usage: `{PREFIX}nick @user <new nickname>` (omit name to reset)")
        return
    new_nick = rest.strip() or None
    try:
        await member.edit(nick=new_nick, reason=f"By {message.author}")
        await message.channel.send(f"✏️ Nickname for {member.mention} set to **{new_nick or 'reset'}**.")
        add_mod_action("nick", message.author, member, new_nick or "(reset)", message.guild.name)
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission.")


async def cmd_role(message, args, add: bool):
    if not has_mod_perms(message.author, "manage_roles"):
        await message.channel.send("🚫 You need **Manage Roles** permission.")
        return
    member, rest = resolve_member(message, args)
    if not member or not rest.strip():
        verb = "addrole" if add else "removerole"
        await message.channel.send(f"Usage: `{PREFIX}{verb} @user <role name>`")
        return
    role_name = rest.strip()
    role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), message.guild.roles)
    if not role:
        await message.channel.send(f"🚫 Role **{role_name}** not found.")
        return
    try:
        if add:
            await member.add_roles(role, reason=f"By {message.author}")
            await message.channel.send(f"✅ Added **{role.name}** to {member.mention}.")
            add_mod_action("addrole", message.author, member, role.name, message.guild.name)
        else:
            await member.remove_roles(role, reason=f"By {message.author}")
            await message.channel.send(f"✅ Removed **{role.name}** from {member.mention}.")
            add_mod_action("removerole", message.author, member, role.name, message.guild.name)
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission to manage that role.")


async def cmd_help(message):
    embed = discord.Embed(
        title="📖 Bot Commands",
        description=f"Prefix: `{PREFIX}`",
        color=0x57F287,
        timestamp=datetime.datetime.utcnow(),
    )

    embed.add_field(name="🛡️ Moderation", value=(
        f"`{PREFIX}kick @user [reason]`\n"
        f"`{PREFIX}ban @user [reason]` · `{PREFIX}unban <id>`\n"
        f"`{PREFIX}mute @user <duration> [reason]` · `{PREFIX}unmute @user`\n"
        f"`{PREFIX}warn @user <reason>` · `{PREFIX}warnings [@user]` · `{PREFIX}clearwarns @user`\n"
        f"`{PREFIX}purge <count>` · `{PREFIX}slowmode <seconds>`\n"
        f"`{PREFIX}lock` · `{PREFIX}unlock`\n"
        f"`{PREFIX}nick @user <name>` · `{PREFIX}addrole @user <role>` · `{PREFIX}removerole @user <role>`"
    ), inline=False)

    embed.add_field(name="📊 Info", value=(
        f"`{PREFIX}stats` — Server stats\n"
        f"`{PREFIX}userinfo [@user]` · `{PREFIX}avatar [@user]` · `{PREFIX}servericon`\n"
        f"`{PREFIX}ping` · `{PREFIX}uptime`"
    ), inline=False)

    embed.add_field(name="🎮 Fun", value=(
        f"`{PREFIX}roll [sides]` · `{PREFIX}flip` · `{PREFIX}8ball <q>`\n"
        f"`{PREFIX}rps <choice>` · `{PREFIX}poll <q>`"
    ), inline=False)

    embed.add_field(name="💬 Auto", value=(
        "Greetings (hi/hello/yo) · GG reactions · Anti-spam auto-mute"
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
