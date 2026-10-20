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

# Startup messages use emoji; a Windows console or log pipe defaults to cp1252 and
# would crash on them.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from dotenv import load_dotenv

import aiohttp
import base64
import discord
import jwt
from discord.ext import tasks

from flask import (Flask, jsonify, redirect, render_template, request,
                   session, url_for)
from urllib.parse import urlparse

import auth
import automod

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


def add_mod_action(action, moderator, target, reason, guild_name, guild_id=None):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "moderator": str(moderator),
        "target": str(target),
        "reason": reason or "No reason provided",
        "guild": guild_name,
        "guild_id": str(guild_id) if guild_id else None,
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
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,     # not readable from JavaScript
    SESSION_COOKIE_SAMESITE="Lax",    # not sent on cross-site POSTs
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "1") != "0",
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(seconds=auth.SESSION_TTL),
)

BOT_START_TIME = None


@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory(static_dir, 'favicon.ico', mimetype='image/x-icon')


@app.template_global()
def asset(filename):
    """Return a static URL stamped with the file's mtime.

    Static files are served with a multi-hour max-age, so without a changing URL
    a browser keeps running the previous deploy's CSS/JS until that expires. The
    stamp changes whenever the file does, which makes each deploy a fresh URL and
    leaves the long cache lifetime intact for unchanged assets.
    """
    path = os.path.join(static_dir, filename.replace("/", os.sep))
    try:
        stamp = int(os.path.getmtime(path))
    except OSError:
        stamp = 0
    return f"/static/{filename}?v={stamp}"


def _access_verifier():
    """Build the Cloudflare Access JWT verifier, or None when it isn't configured.

    The Cf-Access-Authenticated-User-Email header proves nothing on its own: any
    client can send it, and Cloudflare only sets it on paths inside the Access app
    (bare /api/... and a directly reached origin get whatever the caller sent). The
    signed Cf-Access-Jwt-Assertion is the only trustworthy identity, so without the
    team domain and AUD tag needed to check it, Access sign-in is refused outright.
    """
    team = os.getenv("CF_ACCESS_TEAM_DOMAIN", "").strip().removeprefix("https://").rstrip("/")
    aud = os.getenv("CF_ACCESS_AUD", "").strip()
    if not team or not aud:
        print("⚠️ CF_ACCESS_TEAM_DOMAIN / CF_ACCESS_AUD not set: Cloudflare Access sign-in "
              "is disabled. Use the admin token at /login, or set both to enable it.")
        return None
    issuer = f"https://{team}"
    # PyJWKClient caches the key set and refetches when it meets an unknown kid,
    # which covers Cloudflare's periodic key rotation.
    jwks = jwt.PyJWKClient(f"{issuer}/cdn-cgi/access/certs", lifespan=3600)

    def verify(token):
        try:
            key = jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"], audience=aud, issuer=issuer,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except Exception as e:
            print(f"Access JWT rejected: {e}")
            return None
        email = claims.get("email")
        return email if isinstance(email, str) and email else None

    return verify


def _cloudflare_identity():
    """Return the verified Cloudflare Access email for this request, or None."""
    if not ACCESS_VERIFIER:
        return None
    assertion = request.headers.get("Cf-Access-Jwt-Assertion", "").strip()
    return ACCESS_VERIFIER(assertion) if assertion else None


def _token_matches():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    return secrets.compare_digest(auth_header[len("Bearer "):], str(ADMIN_PASSWORD))


def is_owner():
    """The bot owner: Cloudflare Access identity, or the admin token."""
    cf_email = _cloudflare_identity()
    if cf_email:
        request.cf_user_email = cf_email
        return True
    if _token_matches():
        request.cf_user_email = "Local Admin"
        return True
    return False


def discord_session():
    """The signed-in Discord user for this request, or None."""
    data = session.get("discord")
    return data if auth.session_valid(data) else None


def bot_guild_ids():
    return [g.id for g in client.guilds] if client.is_ready() else []


def require_auth(f):
    """Owner only. Everything that can affect the bot globally uses this."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if is_owner():
            return f(*args, **kwargs)
        return jsonify({"message": "Unauthorized"}), 401
    return decorated


def _requested_guild_id():
    """The guild a request is about, from the query string or the JSON body."""
    gid = request.args.get("guild_id")
    if not gid and request.is_json:
        gid = (request.get_json(silent=True) or {}).get("guild_id")
    return str(gid) if gid else ""


def require_guild_access(f):
    """Owner, or a Discord user who runs the guild the request names.

    Every guild-scoped endpoint goes through here. The guild id is never taken
    on trust: it is checked against the signed-in user's own server list and
    against the guilds the bot is currently in.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if is_owner():
            request.guild_scope = None          # owner sees everything
            return f(*args, **kwargs)

        user = discord_session()
        if not user:
            return jsonify({"message": "Unauthorized"}), 401

        guild_id = _requested_guild_id()
        if not guild_id:
            return jsonify({"message": "guild_id is required"}), 400
        if not auth.may_manage(user, guild_id, bot_guild_ids()):
            return jsonify({"message": "Forbidden"}), 403

        # A browser-session caller is vulnerable to cross-site POSTs in a way a
        # bearer token is not, so state-changing requests must come from us.
        if request.method != "GET":
            origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
            if origin and urlparse(origin).netloc != urlparse(request.url_root).netloc:
                return jsonify({"message": "Bad origin"}), 403

        request.guild_scope = guild_id
        request.cf_user_email = "discord:%s" % user["uid"]
        return f(*args, **kwargs)
    return decorated


# ----------------- DISCORD SIGN-IN -----------------

@app.route("/auth/discord")
def auth_discord_start():
    if not auth.is_configured():
        return render_template("index.html"), 503
    state = auth.new_state()
    session["oauth_state"] = state
    return redirect(auth.authorize_url(state))


@app.route("/auth/discord/callback")
def auth_discord_callback():
    if not auth.is_configured():
        return redirect("/")

    # The state proves the callback belongs to the flow this browser started.
    expected = session.pop("oauth_state", None)
    supplied = request.args.get("state", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        add_log("Discord sign-in rejected: state mismatch", "warning")
        return redirect("/login?error=state")

    if request.args.get("error"):
        return redirect("/login?error=denied")

    code = request.args.get("code", "")
    if not code:
        return redirect("/login?error=nocode")

    try:
        token = auth.exchange_code(code)
        data = auth.build_session(token, bot_guild_ids())
    except auth.OAuthError as e:
        add_log(f"Discord sign-in failed: {e}", "error")
        return redirect("/login?error=discord")

    if not data["guilds"]:
        add_log(f"Discord sign-in by {data['uname']}: no manageable servers", "info")
        return redirect("/dashboard?error=noservers")

    session.permanent = True
    session["discord"] = data
    add_log(f"Discord sign-in: {data['uname']} "
            f"({len(data['guilds'])} server(s))", "success")
    return redirect("/dashboard")


@app.route("/auth/logout", methods=["POST", "GET"])
def auth_logout():
    session.pop("discord", None)
    session.pop("oauth_state", None)
    return redirect("/")


@app.route("/dashboard")
@app.route("/dashboard/")
def dashboard_page():
    """The server admin's console. Its data comes from guild-scoped endpoints."""
    return render_template("dashboard.html",
                           oauth_enabled=auth.is_configured())


@app.route("/api/me", methods=["GET"])
@app.route("/admin/api/me", methods=["GET"])
def api_me():
    """Who is signed in, and which servers they may manage."""
    if is_owner():
        return jsonify({
            "authenticated": True,
            "owner": True,
            "username": getattr(request, "cf_user_email", "Owner"),
            "guilds": [{"id": str(g.id), "name": g.name,
                        "icon": g.icon.url if g.icon else None}
                       for g in (client.guilds if client.is_ready() else [])],
        })

    user = discord_session()
    if not user:
        return jsonify({"authenticated": False,
                        "oauth_enabled": auth.is_configured()}), 200

    present = {str(g) for g in bot_guild_ids()}
    guilds = [{"id": gid,
               "name": user.get("names", {}).get(gid, gid),
               "icon": user.get("icons", {}).get(gid)}
              for gid in user["guilds"] if gid in present]
    return jsonify({
        "authenticated": True,
        "owner": False,
        "username": user["uname"],
        "user_id": user["uid"],
        "avatar": user.get("avatar"),
        "guilds": guilds,
    })


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/admin")
@app.route("/admin/")
def admin_page():
    return render_template("admin.html")


@app.route("/login")
def login_page():
    """Public sign-in chooser.

    Cloudflare Access gates /admin at the edge, so a request there never reaches
    this app — which means the console's own token form is unreachable in
    production. This page sits outside the Access application so both routes can
    be offered: Access sends you through /admin, the token opens /console.
    """
    return render_template("login.html")


@app.route("/console")
@app.route("/console/")
def console_page():
    """Same console as /admin, on a path Cloudflare Access does not gate.

    Reached with the admin token. The page shell is public; every endpoint behind
    it still requires the token, and the client talks to /api/... rather than the
    Access-gated /admin/api/... mount.
    """
    return render_template("admin.html")


@app.route("/robots.txt")
def robots():
    # /console and /login sit outside the Cloudflare Access application, so unlike
    # /admin they are genuinely crawlable — keep them out of search results.
    body = "User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /console\nDisallow: /login\n"
    return app.response_class(body, mimetype="text/plain")


@app.route("/health")
def health():
    return "OK", 200


# NOTE: every authenticated endpoint is also mounted under /admin/api/... because the
# Cloudflare Access application only covers bot.j4fn.site/admin and /admin/*. Calls to a
# bare /api/... path are routed straight to the origin without the Cf-Access-* identity
# headers, so Access logins could never be detected there. The admin dashboard must use
# the /admin/api/... paths; /api/public/stats stays public for the landing page.

# Token login is reachable from the internet (Cloudflare Access only gates /admin*),
# so throttle it: LOGIN_MAX_ATTEMPTS failures from one IP within LOGIN_WINDOW start a
# LOGIN_LOCKOUT cooldown. Without this the password is exposed to unlimited guessing.
LOGIN_MAX_ATTEMPTS = 6
LOGIN_WINDOW = 300.0      # seconds a failure counts against the caller
LOGIN_LOCKOUT = 900.0     # seconds locked out once the limit is hit
_login_failures = collections.defaultdict(collections.deque)
_login_lockouts = {}
login_lock = threading.Lock()


def _client_ip():
    # Behind the tunnel every request arrives from Cloudflare, so the real client is
    # in CF-Connecting-IP; remote_addr alone would rate-limit all users as one.
    return (request.headers.get("CF-Connecting-IP")
            or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr
            or "unknown")


def _login_blocked(ip, now):
    until = _login_lockouts.get(ip)
    if until and now < until:
        return int(until - now)
    if until:
        del _login_lockouts[ip]
    return 0


def _record_login_failure(ip, now):
    bucket = _login_failures[ip]
    bucket.append(now)
    while bucket and now - bucket[0] > LOGIN_WINDOW:
        bucket.popleft()
    if len(bucket) >= LOGIN_MAX_ATTEMPTS:
        _login_lockouts[ip] = now + LOGIN_LOCKOUT
        bucket.clear()
        add_log(f"Admin login locked out for {ip} after {LOGIN_MAX_ATTEMPTS} failures", "warning")


@app.route("/api/login", methods=["POST"])
@app.route("/admin/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    password = data.get("password")
    ip = _client_ip()
    now = time.time()

    with login_lock:
        retry_after = _login_blocked(ip, now)
        if retry_after:
            return jsonify({
                "message": f"Too many attempts. Try again in {retry_after // 60 + 1} minute(s).",
            }), 429

        # Constant-time compare so a wrong password cannot be narrowed down by timing.
        if password is not None and secrets.compare_digest(str(password), str(ADMIN_PASSWORD)):
            _login_failures.pop(ip, None)
            add_log(f"Admin token login succeeded from {ip}", "success")
            return jsonify({"token": ADMIN_PASSWORD, "email": "Local Admin"}), 200

        _record_login_failure(ip, now)

    add_log(f"Admin token login failed from {ip}", "warning")
    return jsonify({"message": "Invalid password"}), 401


@app.route("/api/auth-check", methods=["GET"])
@app.route("/admin/api/auth-check", methods=["GET"])
def api_auth_check():
    cf_email = _cloudflare_identity()
    if cf_email:
        return jsonify({"authenticated": True, "type": "cloudflare", "email": cf_email}), 200

    if _token_matches():
        return jsonify({"authenticated": True, "type": "token", "email": "Local Admin"}), 200

    return jsonify({"authenticated": False}), 200


def _public_server_list():
    """Servers for the landing page's "Joined servers" section, largest first.

    Public, so it carries only what Discord itself shows on an invite card: no guild
    IDs and no channels.
    """
    if not client.is_ready():
        return []
    servers = []
    for g in client.guilds:
        servers.append({
            "name": g.name,
            "icon": g.icon.with_size(128).url if g.icon else None,
            "member_count": g.member_count or 0,
            "online": sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot),
        })
    servers.sort(key=lambda s: s["member_count"], reverse=True)
    return servers


@app.route("/api/public/stats", methods=["GET"])
@app.route("/api/stats", methods=["GET"])
@app.route("/admin/api/stats", methods=["GET"])
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
        "servers": _public_server_list(),
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
@app.route("/admin/api/config", methods=["GET"])
@require_auth
def api_get_config():
    return jsonify({
        "PREFIX": PREFIX,
        "WELCOME_CHANNEL_ID": WELCOME_CHANNEL_ID or "",
        "MOD_LOG_CHANNEL_ID": MOD_LOG_CHANNEL_ID or "",
        "MUTED_ROLE_NAME": MUTED_ROLE_NAME or "",
        "STREAMING_URL": STREAMING_URL or "https://twitch.tv/j4fn",
    })




@app.route("/api/config", methods=["POST"])
@app.route("/admin/api/config", methods=["POST"])
@require_auth
def api_set_config():
    global PREFIX, WELCOME_CHANNEL_ID, MOD_LOG_CHANNEL_ID, MUTED_ROLE_NAME, ADMIN_PASSWORD, STREAMING_URL
    data = request.get_json() or {}

    prefix = data.get("PREFIX", "$")
    welcome_channel = data.get("WELCOME_CHANNEL_ID", "")
    mod_log = data.get("MOD_LOG_CHANNEL_ID", "")
    muted_role = data.get("MUTED_ROLE_NAME", "Muted")
    new_password = data.get("ADMIN_PASSWORD", "")
    streaming_url = data.get("STREAMING_URL", "https://twitch.tv/j4fn")

    try:
        update_env_variable("PREFIX", prefix)
        update_env_variable("WELCOME_CHANNEL_ID", welcome_channel)
        update_env_variable("MOD_LOG_CHANNEL_ID", mod_log)
        update_env_variable("MUTED_ROLE_NAME", muted_role)
        update_env_variable("STREAMING_URL", streaming_url)

        if new_password:
            update_env_variable("ADMIN_PASSWORD", new_password)
            ADMIN_PASSWORD = new_password

        PREFIX = prefix
        WELCOME_CHANNEL_ID = welcome_channel
        MOD_LOG_CHANNEL_ID = mod_log
        MUTED_ROLE_NAME = muted_role
        STREAMING_URL = streaming_url

        add_log(f"Configuration updated. Prefix: {PREFIX}, Streaming URL: {STREAMING_URL}", "success")
        return jsonify({"status": "success", "token": ADMIN_PASSWORD}), 200
    except Exception as e:
        add_log(f"Error saving configuration: {e}", "error")
        return jsonify({"message": f"Error saving: {e}"}), 500




@app.route("/api/automod", methods=["GET"])
@app.route("/admin/api/automod", methods=["GET"])
@require_guild_access
def api_get_automod():
    guild_id = request.args.get("guild_id") or None
    return jsonify({
        "guild_id": guild_id,
        "config": automod.get_config(guild_id),
        "overrides": automod.guild_overrides(guild_id) if guild_id else {},
        "defaults": automod.DEFAULTS,
        "signals": [{"label": label, "weight": weight}
                    for label, weight in automod.TOGGLEABLE_SIGNALS],
        "pil_available": automod.PIL_AVAILABLE,
        "blocked_images": sum(len(automod.blocked_images(g.id))
                              for g in (client.guilds if client.is_ready() else [])),
        "stats": automod.tracker_stats(),
        "recent": (list(AUTOMOD_HITS[int(guild_id)])[-25:][::-1]
                   if guild_id and guild_id.isdigit() else []),
    })


@app.route("/api/automod", methods=["POST"])
@app.route("/admin/api/automod", methods=["POST"])
@require_guild_access
def api_set_automod():
    data = request.get_json() or {}
    guild_id = str(data.pop("guild_id", "") or "")
    try:
        if guild_id:
            updated = automod.save_guild_config(guild_id, data)
            add_log(f"Auto-mod settings updated for guild {guild_id}.", "success")
        else:
            updated = automod.save_config(data)
            add_log("Auto-mod defaults updated from dashboard.", "success")
        return jsonify({"status": "success", "config": updated}), 200
    except Exception as e:
        add_log(f"Error saving auto-mod settings: {e}", "error")
        return jsonify({"message": f"Error saving: {e}"}), 500


@app.route("/api/automod/blocked", methods=["GET"])
@app.route("/admin/api/automod/blocked", methods=["GET"])
@require_guild_access
def api_blocked_images():
    guild_id = request.args.get("guild_id", "")
    if not guild_id:
        return jsonify([]), 200
    return jsonify(automod.blocked_images(guild_id))


@app.route("/api/automod/blocked/remove", methods=["POST"])
@app.route("/admin/api/automod/blocked/remove", methods=["POST"])
@require_guild_access
def api_remove_blocked_image():
    data = request.get_json() or {}
    guild_id = str(data.get("guild_id", ""))
    entry_id = str(data.get("id", ""))
    if not guild_id or not entry_id:
        return jsonify({"message": "guild_id and id are required"}), 400
    if automod.remove_blocked_image(guild_id, entry_id):
        add_log(f"Blocked image {entry_id} removed from dashboard.", "success")
        return jsonify({"status": "success"}), 200
    return jsonify({"message": "Not found"}), 404


@app.route("/api/automod/reset", methods=["POST"])
@app.route("/admin/api/automod/reset", methods=["POST"])
@require_guild_access
def api_reset_automod():
    """Drop a guild's customisation so it follows the bot defaults again."""
    guild_id = _requested_guild_id()
    if not guild_id:
        return jsonify({"message": "guild_id is required"}), 400
    automod.clear_guild_overrides(guild_id)
    add_log(f"Auto-mod settings reset to defaults for guild {guild_id}.", "success")
    return jsonify({"status": "success", "config": automod.get_config(guild_id)}), 200


@app.route("/api/automod/test", methods=["POST"])
@app.route("/admin/api/automod/test", methods=["POST"])
@require_guild_access
def api_test_automod():
    data = request.get_json() or {}
    text = str(data.get("text", ""))[:4000]
    attachments = int(data.get("attachments", 0) or 0)
    guild_id = data.get("guild_id") or None
    cfg = automod.get_config(guild_id)
    score, reasons = automod.score_content(text, attachments=attachments, config=cfg)
    threshold = cfg.get("scam_threshold", 5)
    return jsonify({
        "score": score,
        "threshold": threshold,
        "reasons": reasons,
        "blocked": score >= threshold,
    })


@app.route("/api/servers", methods=["GET"])
@app.route("/admin/api/servers", methods=["GET"])
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
@app.route("/admin/api/send-message", methods=["POST"])
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
@app.route("/admin/api/presence", methods=["POST"])
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

            if activity == "streaming":
                act = discord.Streaming(name=formatted or "j4fn.site", url=STREAMING_URL)
            else:
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
@app.route("/admin/api/presence/rotate", methods=["POST"])
@require_auth
def api_presence_rotate():
    asyncio.run_coroutine_threadsafe(update_status(), client.loop)
    return jsonify({"status": "success"})


@app.route("/api/logs", methods=["GET"])
@app.route("/admin/api/logs", methods=["GET"])
@require_auth
def api_logs():
    with log_lock:
        return jsonify(list(LOGS_BUFFER))


@app.route("/api/mod/actions", methods=["GET"])
@app.route("/admin/api/mod/actions", methods=["GET"])
@require_guild_access
def api_mod_actions():
    scope = getattr(request, "guild_scope", None)
    with log_lock:
        entries = list(MOD_ACTIONS_BUFFER)
    if scope:
        entries = [e for e in entries if str(e.get("guild_id") or "") == str(scope)]
    return jsonify(entries)


@app.route("/api/mod/warnings", methods=["GET"])
@app.route("/admin/api/mod/warnings", methods=["GET"])
@require_guild_access
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
@app.route("/admin/api/mod/action", methods=["POST"])
@require_guild_access
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
@app.route("/admin/api/restart", methods=["POST"])
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
    # 0.0.0.0 is needed inside Docker so cloudflared can reach the container; for a
    # local run set WEB_HOST=127.0.0.1 so the console isn't open to the whole network.
    app.run(host=os.getenv("WEB_HOST", "0.0.0.0"), port=port)


def keep_alive():
    t = threading.Thread(target=run_web, daemon=True)
    t.start()


import secrets


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


load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID")
MOD_LOG_CHANNEL_ID = os.getenv("MOD_LOG_CHANNEL_ID")
MUTED_ROLE_NAME = os.getenv("MUTED_ROLE_NAME", "Muted")
PREFIX = os.getenv("PREFIX", "$")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
STREAMING_URL = os.getenv("STREAMING_URL", "https://j4fn.site")

if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = secrets.token_urlsafe(10)
    try:
        update_env_variable("ADMIN_PASSWORD", ADMIN_PASSWORD)
    except Exception:
        pass
    print(f"🔑 Auto-generated ADMIN_PASSWORD: {ADMIN_PASSWORD}")

# Signs the session cookie. Generated once and kept in .env: a key that changed
# on every boot would sign everyone out on each deploy.
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "").strip()
if not FLASK_SECRET_KEY:
    FLASK_SECRET_KEY = secrets.token_urlsafe(32)
    try:
        update_env_variable("FLASK_SECRET_KEY", FLASK_SECRET_KEY)
    except Exception:
        pass
app.secret_key = FLASK_SECRET_KEY

if auth.is_configured():
    print("🔓 Discord sign-in enabled for server admins.")
else:
    print("ℹ️  Discord sign-in disabled "
          "(set DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET / OAUTH_REDIRECT_URI).")

ACCESS_VERIFIER = _access_verifier()


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
client = discord.Client(intents=intents)


# ----------------- AUTO-MOD STATE -----------------

# Detection lives in automod.py; this module only enforces the verdicts.
AUTOMOD_HITS = collections.defaultdict(lambda: collections.deque(maxlen=100))


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


# -------------------- AUTO-MOD ENFORCEMENT --------------------

AUTOMOD_COLORS = {"delete": 0xFEE75C, "warn": 0xFAA61A, "timeout": 0xED4245,
                  "ban": 0x992D22}


async def _purge_user_messages(guild, member, window_seconds=600):
    """Remove the member's other recent messages, in the channels they actually used."""
    after = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=window_seconds)
    removed = 0
    for channel_id in automod.recent_channels(guild.id, member.id, window=window_seconds):
        channel = guild.get_channel(channel_id)
        if channel is None or not channel.permissions_for(guild.me).manage_messages:
            continue
        try:
            deleted = await channel.purge(
                limit=50, after=after, check=lambda m: m.author.id == member.id
            )
            removed += len(deleted)
        except (discord.Forbidden, discord.HTTPException):
            continue
    return removed


MAX_HASHED_ATTACHMENTS = 4


async def _image_fingerprints(message: discord.Message):
    """Fingerprint the message's images so repeats can be recognised.

    Returns (fingerprint, attachment) pairs. The attachment is carried along
    because non-images are skipped, so the Nth fingerprint is not necessarily the
    Nth attachment -- and OCR must read the file a fingerprint actually came from.

    With `image_deep_hash` on, the bytes are downloaded and perceptually hashed,
    which survives re-encoding; with it off (or Pillow missing) we use Discord's
    own size/width/height metadata and download nothing. Every failure here is
    swallowed: a hash is a nice-to-have, never a reason to drop a message.
    """
    cfg = automod.get_config(message.guild.id if message.guild else None)
    if not cfg.get("image_checks", True) or not message.attachments:
        return []

    byte_cap = cfg.get("max_image_bytes", 8000000)
    deep = cfg.get("image_deep_hash", True) and automod.PIL_AVAILABLE
    loop = asyncio.get_running_loop()
    fingerprints = []

    for attachment in message.attachments[:MAX_HASHED_ATTACHMENTS]:
        content_type = attachment.content_type or ""
        is_image = content_type.startswith("image/") or attachment.width
        if not is_image:
            continue

        if not deep or (attachment.size and attachment.size > byte_cap):
            meta = automod.fingerprint_meta(attachment.size, attachment.width,
                                            attachment.height)
            if meta:
                fingerprints.append((meta, attachment))
            continue

        try:
            data = await attachment.read()
        except (discord.HTTPException, discord.NotFound, discord.Forbidden, OSError):
            continue
        if not data or len(data) > byte_cap:
            continue

        try:
            # Decoding is CPU work; keep it off the gateway's event loop.
            fingerprint = await loop.run_in_executor(
                None, automod.fingerprint_image, data)
        except Exception as e:
            add_log(f"automod: image hash failed: {e}", "error")
            continue
        if fingerprint:
            fingerprints.append((fingerprint, attachment))

    return fingerprints


# ----------------- CLOUD OCR -----------------

# Opt-in only: this uploads member-posted images to a third party. Set
# OCR_PROVIDER and OCR_API_KEY in .env, then `$automod set ocr_enabled on`.
OCR_PROVIDER = (os.getenv("OCR_PROVIDER", "") or "").strip().lower()
OCR_API_KEY = os.getenv("OCR_API_KEY", "")

# Swapped out in tests so the gating can be exercised without a network call.
# Signature: async (image_bytes) -> extracted text
OCR_BACKEND = None


async def _ocr_via_ocrspace(data):
    """OCR.space — simplest to get started with, has a free tier."""
    form = aiohttp.FormData()
    form.add_field("apikey", OCR_API_KEY)
    form.add_field("language", "eng")
    form.add_field("scale", "true")
    form.add_field("file", data, filename="i.png", content_type="image/png")
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post("https://api.ocr.space/parse/image",
                                data=form) as response:
            payload = await response.json(content_type=None)
    parsed = (payload or {}).get("ParsedResults") or []
    return " ".join(p.get("ParsedText", "") for p in parsed).strip()


async def _ocr_via_google(data):
    """Google Cloud Vision REST, API-key auth."""
    body = {"requests": [{
        "image": {"content": base64.b64encode(data).decode()},
        "features": [{"type": "TEXT_DETECTION"}],
    }]}
    url = f"https://vision.googleapis.com/v1/images:annotate?key={OCR_API_KEY}"
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=body) as response:
            payload = await response.json(content_type=None)
    responses = (payload or {}).get("responses") or [{}]
    return (responses[0].get("fullTextAnnotation") or {}).get("text", "").strip()


OCR_PROVIDERS = {"ocrspace": _ocr_via_ocrspace, "google": _ocr_via_google}


def _ocr_backend():
    if OCR_BACKEND is not None:
        return OCR_BACKEND
    if not OCR_PROVIDER or not OCR_API_KEY:
        return None
    return OCR_PROVIDERS.get(OCR_PROVIDER)


async def _read_images(pairs, cfg):
    """Extract text from the message's images, paying for as little as possible.

    Anything already read before comes from the cache -- including a re-encoded
    repost, since the cache matches perceptually.
    """
    backend = _ocr_backend()
    if backend is None:
        return "", 0

    distance = cfg.get("image_hash_distance", 6)
    max_age = cfg.get("ocr_cache_days", 30)
    chunks, billed = [], 0

    for fingerprint, attachment in pairs[:cfg.get("ocr_max_images", 2)]:
        cached = automod.ocr_cache_get(fingerprint, distance, max_age)
        if cached is not None:
            if cached:
                chunks.append(cached)
            continue

        if automod.ocr_budget_left(cfg) <= 0:
            add_log("automod: OCR hourly budget spent, skipping", "warning")
            break

        try:
            data = await attachment.read()
        except (discord.HTTPException, discord.NotFound, discord.Forbidden, OSError):
            continue

        try:
            automod.ocr_note_call()
            billed += 1
            text = await backend(data)
        except Exception as e:                   # provider down, quota, timeout
            add_log(f"automod: OCR call failed: {e}", "error")
            continue

        automod.ocr_cache_put(fingerprint, text or "")
        if text:
            chunks.append(text)

    return " ".join(chunks).strip(), billed


async def _notify_offender(member, verdict, guild_name):
    """Best-effort DM so the user knows why they went quiet. Most spam bots have DMs off."""
    if verdict.action == "delete":
        return
    try:
        if verdict.action == "ban":
            body = f"You were banned from **{guild_name}**."
        elif verdict.action == "warn":
            body = f"Your message was removed in **{guild_name}** and you were warned."
        else:
            body = (f"You were timed out in **{guild_name}** for "
                    f"**{verdict.timeout_minutes} minutes**.")
        await member.send(f"🛡️ {body}\nReason: {verdict.reason}")
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        pass


async def run_automod(message: discord.Message) -> bool:
    """Score the message and enforce the verdict. True if the message was acted on."""
    if message.guild is None or message.author.bot:
        return False

    member = message.author
    if not isinstance(member, discord.Member):
        return False
    # Staff and the owner are never auto-moderated.
    if member.id == message.guild.owner_id:
        return False
    perms = member.guild_permissions
    if perms.administrator or perms.manage_messages or perms.manage_guild:
        return False

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    account_age_days = None
    if member.created_at:
        account_age_days = (now_utc - member.created_at).total_seconds() / 86400
    join_age_hours = None
    if member.joined_at:
        join_age_hours = (now_utc - member.joined_at).total_seconds() / 3600

    try:
        image_pairs = await _image_fingerprints(message)
    except Exception as e:                      # never let hashing break on_message
        add_log(f"automod: image fingerprinting failed: {e}", "error")
        image_pairs = []
    images = [fingerprint for fingerprint, _ in image_pairs]

    # Only pay for a cloud read when the caption alone is not damning enough and
    # the poster has nothing to vouch for them. score_content is pure, so asking
    # it here costs nothing and does not disturb the flood counters.
    ocr_text = ""
    cfg = automod.get_config(message.guild.id)
    try:
        pre_score, _ = automod.score_content(
            message.content, attachments=len(message.attachments), config=cfg)
        wanted, why = automod.should_ocr(
            text_score=pre_score,
            images=images,
            has_roles=len([r for r in member.roles if not r.is_default()]) > 0,
            account_age_days=account_age_days,
            join_age_hours=join_age_hours,
            config=cfg,
        )
        if wanted:
            ocr_text, billed = await _read_images(image_pairs, cfg)
            if ocr_text:
                add_log(f"automod: read {len(ocr_text)} chars from image(s) "
                        f"by {member} ({billed} billed)", "info")
    except Exception as e:                      # OCR must never break on_message
        add_log(f"automod: OCR step failed: {e}", "error")
        ocr_text = ""

    try:
        verdict = automod.evaluate(
            text=message.content,
            guild_id=message.guild.id,
            user_id=member.id,
            channel_id=message.channel.id,
            attachments=len(message.attachments),
            mention_count=len(message.mentions) + len(message.role_mentions),
            mentions_everyone=message.mention_everyone,
            account_age_days=account_age_days,
            join_age_hours=join_age_hours,
            role_ids=[r.id for r in member.roles],
            images=images,
            ocr_text=ocr_text,
            config=cfg,
        )
    except Exception as e:                      # detection must never kill on_message
        add_log(f"automod error: {e}", "error")
        return False

    if not verdict:
        return False

    AUTOMOD_HITS[message.guild.id].append({
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "guild": message.guild.name,
        "channel": getattr(message.channel, "name", "?"),
        "user": str(member),
        "action": verdict.action,
        "score": verdict.score,
        "reason": verdict.reason,
    })

    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass

    purged = 0
    if verdict.purge:
        purged = await _purge_user_messages(message.guild, member)

    applied = "deleted"
    try:
        if verdict.action == "ban":
            await _notify_offender(member, verdict, message.guild.name)
            await message.guild.ban(member, reason=f"Auto-mod: {verdict.reason}",
                                    delete_message_days=1)
            applied = "banned"
        elif verdict.action == "timeout":
            until = now_utc + datetime.timedelta(minutes=verdict.timeout_minutes)
            await member.timeout(until, reason=f"Auto-mod: {verdict.reason}")
            await _notify_offender(member, verdict, message.guild.name)
            applied = f"timed out {verdict.timeout_minutes}m"
        elif verdict.action == "warn":
            await _notify_offender(member, verdict, message.guild.name)
            applied = "warned"
    except discord.Forbidden:
        add_log(f"automod: missing permission to {verdict.action} {member}", "error")
        applied = "deleted (no permission to punish)"
    except discord.HTTPException as e:
        add_log(f"automod: {verdict.action} failed for {member}: {e}", "error")
        applied = "deleted (action failed)"

    if verdict.action in ("warn", "timeout", "ban"):
        add_warning(message.guild.id, member.id, "AutoMod", verdict.reason)

    # A short, self-deleting notice: enough for bystanders, no lasting channel noise.
    try:
        if verdict.action == "delete":
            note = f"🛡️ {member.mention} your message was removed — {verdict.reason}."
        else:
            note = f"🛡️ {member.mention} was {applied} — {verdict.reason}."
        await message.channel.send(note, delete_after=10)
    except (discord.Forbidden, discord.HTTPException):
        pass

    add_mod_action(f"auto-{verdict.action}", "AutoMod", member,
                   verdict.reason, message.guild.name, message.guild.id)

    detail = (f"{member.mention} (`{member}`) — **{applied}**\n"
              f"Reason: {verdict.reason}\n"
              f"Channel: {message.channel.mention} · Risk score: **{verdict.score}**")
    if purged:
        detail += f"\nPurged **{purged}** further message(s)."
    await send_mod_log(message.guild, "🛡️ Auto-Mod", detail,
                       color=AUTOMOD_COLORS.get(verdict.action, 0xED4245))
    return True


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
        ("streaming", "🔴 LIVE @ j4fn.site", STREAMING_URL),
    ]

    if not hasattr(update_status, "_index"):
        update_status._index = 0

    idx = update_status._index % len(statuses)
    item = statuses[idx]
    update_status._index += 1

    if len(item) == 3 and item[0] == "streaming":
        activity = discord.Streaming(name=item[1], url=item[2])
    else:
        activity_type, text = item
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

    if not WELCOME_CHANNEL_ID:
        return

    try:
        channel = member.guild.get_channel(int(WELCOME_CHANNEL_ID))
    except Exception:
        return

    if channel is None:
        return

    add_log(f"Member joined: {member.name} ({member.guild.name})", "info")

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

    # ---- Auto-moderation ----
    if await run_automod(message):
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
    elif cmd == "automod":
        await cmd_automod(message, args)
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
        add_mod_action("kick", message.author, member, reason, message.guild.name, message.guild.id)
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
                add_mod_action("ban", message.author, user_id, reason, message.guild.name, message.guild.id)
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
        add_mod_action("ban", message.author, member, reason, message.guild.name, message.guild.id)
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
        add_mod_action("unban", message.author, user_id, reason, message.guild.name, message.guild.id)
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
        add_mod_action("timeout", message.author, member, f"{reason} ({minutes}m)", message.guild.name, message.guild.id)
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
        add_mod_action("untimeout", message.author, member, reason, message.guild.name, message.guild.id)
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
    add_mod_action("warn", message.author, member, f"{reason} (total: {count})", message.guild.name, message.guild.id)
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
    add_mod_action("clear_warnings", message.author, member, f"cleared {count}", message.guild.name, message.guild.id)


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
                       f"{len(deleted)-1} messages", message.guild.name, message.guild.id)
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except Exception:
            pass
    except discord.Forbidden:
        await message.channel.send("🚫 I don't have permission to delete messages.")


AUTOMOD_HELP = (
    "`{p}automod` — show settings\n"
    "`{p}automod on` / `{p}automod off`\n"
    "`{p}automod set <setting> <value>` — e.g. `{p}automod set scam_threshold 6`\n"
    "`{p}automod block <domain or phrase>` / `{p}automod allow <domain>`\n"
    "`{p}automod blockimage [note]` — reply to a scam post to block that image for good\n"
    "`{p}automod blockedimages` · `{p}automod unblockimage <id>`\n"
    "`{p}automod signals` — list signal categories and their weights\n"
    "`{p}automod toggle <signal>` — switch a category on or off\n"
    "`{p}automod test <message text>` — score text without punishing anyone\n"
    "`{p}automod recent` — last auto-mod actions"
)


async def cmd_automod(message, args):
    if not has_mod_perms(message.author, "manage_guild"):
        await message.channel.send("🚫 You need **Manage Server** permission.")
        return

    parts = args.split(None, 1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""
    guild_id = message.guild.id
    cfg = automod.get_config(guild_id)

    if sub in ("on", "off", "enable", "disable"):
        on = sub in ("on", "enable")
        automod.save_guild_config(guild_id, {"enabled": on})
        await message.channel.send(f"🛡️ Auto-mod is now **{'ON' if on else 'OFF'}**.")
        add_mod_action("automod", message.author, "settings",
                       f"enabled={on}", message.guild.name, message.guild.id)
        return

    if sub == "test":
        if not rest:
            await message.channel.send(f"Usage: `{PREFIX}automod test <text>`")
            return
        score, reasons = automod.score_content(rest, attachments=len(message.attachments))
        threshold = cfg.get("scam_threshold", 5)
        embed = discord.Embed(
            title="🧪 Auto-Mod Test",
            description=f"Score **{score}** / threshold **{threshold}**",
            color=0xED4245 if score >= threshold else 0x57F287,
        )
        embed.add_field(name="Signals", value=", ".join(reasons) or "none", inline=False)
        embed.add_field(name="Verdict",
                        value="🚫 Would be removed" if score >= threshold else "✅ Would pass",
                        inline=False)
        await message.channel.send(embed=embed)
        return

    if sub == "blockimage":
        target = message
        reference = message.reference
        if reference is not None:
            target = reference.resolved
            if not isinstance(target, discord.Message):
                try:
                    target = await message.channel.fetch_message(reference.message_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    await message.channel.send("🚫 I couldn't read that message.")
                    return

        if not target.attachments:
            await message.channel.send(
                f"🖼️ Reply to a message with images, or attach them, then run "
                f"`{PREFIX}automod blockimage [note]`.")
            return

        fingerprints = [fp for fp, _ in await _image_fingerprints(target)]
        if not fingerprints:
            await message.channel.send(
                "🚫 Couldn't fingerprint those attachments — are they images, and is "
                "`image_checks` on?")
            return

        added = [automod.add_blocked_image(message.guild.id, fp, note=rest,
                                           moderator=str(message.author))
                 for fp in fingerprints]
        added = [a for a in added if a]
        skipped = len(fingerprints) - len(added)

        if target.id != message.id:
            try:
                await target.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

        if not added:
            await message.channel.send("ℹ️ Already blocked — nothing new to add.")
            return

        ids = ", ".join(f"`{a['id']}`" for a in added)
        note = f" ({rest})" if rest else ""
        extra = f" {skipped} already known." if skipped else ""
        await message.channel.send(
            f"🛡️ Blocked **{len(added)}** image(s){note}. Anyone posting them again "
            f"is caught on their first message.{extra}\nIDs: {ids}")
        add_mod_action("automod", message.author, "blocked image",
                       rest or f"{len(added)} image(s)", message.guild.name, message.guild.id)
        await send_mod_log(
            message.guild, "🛡️ Scam Image Blocked",
            f"{message.author.mention} blocked **{len(added)}** image(s){note}.\n"
            f"IDs: {ids}", color=0x5865F2)
        return

    if sub == "unblockimage":
        if not rest.strip():
            await message.channel.send(f"Usage: `{PREFIX}automod unblockimage <id>`")
            return
        if automod.remove_blocked_image(message.guild.id, rest.strip()):
            await message.channel.send(f"✅ Unblocked image `{rest.strip()}`.")
            add_mod_action("automod", message.author, "unblocked image",
                           rest.strip(), message.guild.name, message.guild.id)
        else:
            await message.channel.send(f"❓ No blocked image with id `{rest.strip()}`.")
        return

    if sub in ("blockedimages", "blocked"):
        entries = automod.blocked_images(message.guild.id)
        if not entries:
            await message.channel.send(
                f"🖼️ No blocked images yet. Reply to a scam post with "
                f"`{PREFIX}automod blockimage` to add one.")
            return
        lines = [f"`{e['id']}` — {e.get('note') or 'no note'} "
                 f"(by {e.get('moderator') or 'unknown'})"
                 for e in entries[-15:]]
        embed = discord.Embed(
            title=f"🖼️ Blocked Images ({len(entries)})",
            description="\n".join(lines)[:4000],
            color=0x5865F2,
        )
        embed.set_footer(text=f"Remove one with {PREFIX}automod unblockimage <id>")
        await message.channel.send(embed=embed)
        return

    if sub in ("signals", "signal"):
        off = {s.lower() for s in cfg.get("disabled_signals", [])}
        lines = [f"{'🔴' if label in off else '🟢'} `{label}` (+{weight})"
                 for label, weight in automod.TOGGLEABLE_SIGNALS]
        embed = discord.Embed(
            title="🎚️ Auto-Mod Signals",
            description="\n".join(lines),
            color=0x5865F2,
        )
        embed.set_footer(text=f"Switch one with {PREFIX}automod toggle <signal>")
        await message.channel.send(embed=embed)
        return

    if sub == "toggle":
        known = {label for label, _ in automod.TOGGLEABLE_SIGNALS}
        target = rest.lower().strip()
        if target not in known:
            options = ", ".join(f"`{s}`" for s in sorted(known))
            await message.channel.send(
                f"❓ Unknown signal. Use one of: {options}")
            return
        off = [s.lower() for s in cfg.get("disabled_signals", [])]
        if target in off:
            off.remove(target)
            state = "ON"
        else:
            off.append(target)
            state = "OFF"
        automod.save_guild_config(guild_id, {"disabled_signals": off})
        await message.channel.send(f"🎚️ Signal `{target}` is now **{state}**.")
        add_mod_action("automod", message.author, "signal",
                       f"{target}={state}", message.guild.name, message.guild.id)
        return

    if sub in ("block", "allow"):
        if not rest:
            await message.channel.send(f"Usage: `{PREFIX}automod {sub} <domain or phrase>`")
            return
        value = rest.lower().strip()
        key = ("block_domains" if sub == "block" else "allow_domains") if "." in value \
            else "extra_keywords"
        current = list(cfg.get(key, []))
        if value not in current:
            current.append(value)
        automod.save_guild_config(guild_id, {key: current})
        await message.channel.send(f"✅ Added `{value}` to **{key}**.")
        add_mod_action("automod", message.author, key, f"+{value}", message.guild.name, message.guild.id)
        return

    if sub == "set":
        bits = rest.split(None, 1)
        if len(bits) < 2:
            await message.channel.send(f"Usage: `{PREFIX}automod set <setting> <value>`")
            return
        key, value = bits[0].lower(), bits[1].strip()
        if key not in automod.DEFAULTS:
            options = ", ".join(f"`{k}`" for k in automod.DEFAULTS)
            await message.channel.send(f"❓ Unknown setting. Options: {options}")
            return
        new_cfg = automod.save_guild_config(guild_id, {key: value})
        await message.channel.send(f"✅ `{key}` is now **{new_cfg.get(key)}**.")
        add_mod_action("automod", message.author, key, str(new_cfg.get(key)),
                       message.guild.name, message.guild.id)
        return

    if sub == "recent":
        hits = list(AUTOMOD_HITS[guild_id])[-10:]
        if not hits:
            await message.channel.send("🛡️ No auto-mod actions recorded yet.")
            return
        lines = [f"`{h['time']}` **{h['action']}** {h['user']} — {h['reason']}"
                 for h in reversed(hits)]
        embed = discord.Embed(title="🛡️ Recent Auto-Mod Actions",
                              description="\n".join(lines)[:4000], color=0xFEE75C)
        await message.channel.send(embed=embed)
        return

    if sub and sub != "help":
        await message.channel.send(
            f"❓ Unknown sub-command.\n{AUTOMOD_HELP.format(p=PREFIX)}")
        return

    embed = discord.Embed(
        title="🛡️ Auto-Mod Settings",
        description="**ENABLED**" if cfg.get("enabled") else "**DISABLED**",
        color=0x57F287 if cfg.get("enabled") else 0x99AAB5,
    )
    embed.add_field(
        name="Scam / referral spam",
        value=(f"Threshold: `{cfg['scam_threshold']}`\n"
               f"First hit: `{cfg['scam_action']}` (`{cfg['scam_timeout_minutes']}m`)\n"
               f"Ban on repeat: `{cfg['ban_on_repeat']}`\n"
               f"Purge on hit: `{cfg['purge_on_scam']}`"),
        inline=True,
    )
    embed.add_field(
        name="Flood limits",
        value=(f"Rate: `{cfg['rate_limit']}` / `{cfg['rate_window']}s`\n"
               f"Duplicates: `{cfg['duplicate_limit']}`\n"
               f"Cross-post: `{cfg['crosspost_limit']}` channels\n"
               f"Attachments: `{cfg['attachment_limit']}`"),
        inline=True,
    )
    mode = ("perceptual" if cfg["image_deep_hash"] and automod.PIL_AVAILABLE
            else "metadata only")
    embed.add_field(
        name="Image rules",
        value=(f"Enabled: `{cfg['image_checks']}` ({mode})\n"
               f"Same image: `{cfg['image_dupe_limit']}x` per member\n"
               f"Raid: `{cfg['image_raid_accounts']}` accounts\n"
               f"Window: `{cfg['image_dupe_window']:g}s`"),
        inline=True,
    )
    if cfg.get("ocr_enabled") and _ocr_backend() is None:
        ocr_state = "⚠️ on, but no provider configured (set OCR_PROVIDER/OCR_API_KEY)"
    elif cfg.get("ocr_enabled"):
        ocr_state = (f"on via `{OCR_PROVIDER or 'custom'}` — "
                     f"`{automod.ocr_budget_left(cfg)}`/`{cfg['ocr_max_per_hour']}` "
                     f"calls left this hour")
    else:
        ocr_state = "off"
    embed.add_field(name="Reading text in images (cloud OCR)",
                    value=ocr_state, inline=False)
    embed.add_field(
        name="Other rules",
        value=(f"Block invites: `{cfg['block_invites']}`\n"
               f"Mass mentions: `{cfg['block_mass_mentions']}` (limit `{cfg['mention_limit']}`)\n"
               f"New account: `{cfg['new_account_days']}d`"),
        inline=False,
    )
    lists = []
    for key in ("block_domains", "allow_domains", "extra_keywords", "disabled_signals"):
        if cfg.get(key):
            lists.append(f"**{key}**: {', '.join(cfg[key][:10])}")
    if lists:
        embed.add_field(name="Custom lists", value="\n".join(lists)[:1000], inline=False)
    embed.add_field(name="Commands", value=AUTOMOD_HELP.format(p=PREFIX), inline=False)
    await message.channel.send(embed=embed)


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
                       f"{seconds}s", message.guild.name, message.guild.id)
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
                       f"#{message.channel.name}", "", message.guild.name, message.guild.id)
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
        add_mod_action("nick", message.author, member, new_nick or "(reset)", message.guild.name, message.guild.id)
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
            add_mod_action("addrole", message.author, member, role.name, message.guild.name, message.guild.id)
        else:
            await member.remove_roles(role, reason=f"By {message.author}")
            await message.channel.send(f"✅ Removed **{role.name}** from {member.mention}.")
            add_mod_action("removerole", message.author, member, role.name, message.guild.name, message.guild.id)
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
        f"`{PREFIX}nick @user <name>` · `{PREFIX}addrole @user <role>` · `{PREFIX}removerole @user <role>`\n"
        f"`{PREFIX}automod` — anti-spam settings (Manage Server)"
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
        "Greetings (hi/hello/yo) · GG reactions\n"
        "Auto-mod: scam & referral spam, invite links, mass mentions, message floods"
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
