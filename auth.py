"""Discord OAuth2 sign-in for server admins.

The admin console behind Cloudflare Access belongs to the bot owner and can do
anything. This is the other door: a Discord account signs in and gets to manage
only the servers it already administers, and only the servers the bot is in.

Deliberately dependency-free (urllib, not requests) and synchronous, because
Flask's routes run on their own thread while discord.py owns the event loop.
"""

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://discord.com/api/v10"
AUTHORIZE = "https://discord.com/oauth2/authorize"
SCOPES = "identify guilds"

# Discord permission bits. Either of these means "runs this server".
MANAGE_GUILD = 1 << 5
ADMINISTRATOR = 1 << 3

# How long a sign-in is trusted before the guild list is rebuilt from Discord.
SESSION_TTL = 3600


class OAuthError(RuntimeError):
    """Anything that went wrong talking to Discord."""


def client_id():
    return os.getenv("DISCORD_CLIENT_ID", "").strip()


def client_secret():
    return os.getenv("DISCORD_CLIENT_SECRET", "").strip()


def redirect_uri():
    return os.getenv("OAUTH_REDIRECT_URI", "").strip()


def is_configured():
    return bool(client_id() and client_secret() and redirect_uri())


def new_state():
    return secrets.token_urlsafe(24)


def authorize_url(state):
    """Where to send the browser to start the flow."""
    query = urllib.parse.urlencode({
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "prompt": "none",
    })
    return "%s?%s" % (AUTHORIZE, query)


def _request(url, *, data=None, headers=None, timeout=10):
    body = urllib.parse.urlencode(data).encode() if data else None
    request = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        raise OAuthError("discord returned %s: %s" % (e.code, detail)) from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise OAuthError("could not reach discord: %s" % e) from e


def exchange_code(code):
    """Trade the one-time code for an access token."""
    payload = _request(API + "/oauth2/token", data={
        "client_id": client_id(),
        "client_secret": client_secret(),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = payload.get("access_token")
    if not token:
        raise OAuthError("no access token in the response")
    return token


def _bearer(token):
    return {"Authorization": "Bearer %s" % token}


def fetch_user(token):
    me = _request(API + "/users/@me", headers=_bearer(token))
    return {
        "id": str(me.get("id", "")),
        "username": me.get("global_name") or me.get("username") or "unknown",
        "avatar": me.get("avatar"),
    }


def fetch_guilds(token):
    guilds = _request(API + "/users/@me/guilds", headers=_bearer(token))
    return guilds if isinstance(guilds, list) else []


def runs_guild(guild):
    """Does this membership carry enough authority to configure the bot?"""
    try:
        permissions = int(guild.get("permissions", 0))
    except (TypeError, ValueError):
        return False
    if guild.get("owner"):
        return True
    return bool(permissions & (MANAGE_GUILD | ADMINISTRATOR))


def manageable(user_guilds, bot_guild_ids):
    """Guilds the user runs AND the bot is actually in. Order follows Discord's."""
    present = {str(g) for g in bot_guild_ids}
    out = []
    for guild in user_guilds:
        gid = str(guild.get("id", ""))
        if gid in present and runs_guild(guild):
            out.append({
                "id": gid,
                "name": guild.get("name") or gid,
                "icon": guild.get("icon"),
                "owner": bool(guild.get("owner")),
            })
    return out


def build_session(token, bot_guild_ids):
    """What gets stored in the signed cookie.

    The access token is deliberately NOT included: Flask's session cookie is
    signed but not encrypted, so anything in it is readable by the browser. Only
    the derived identity and the guild id list go in, and they expire.
    """
    user = fetch_user(token)
    guilds = manageable(fetch_guilds(token), bot_guild_ids)
    return {
        "uid": user["id"],
        "uname": user["username"],
        "avatar": user["avatar"],
        "guilds": [g["id"] for g in guilds],
        "names": {g["id"]: g["name"] for g in guilds},
        "icons": {g["id"]: g["icon"] for g in guilds},
        "exp": int(time.time()) + SESSION_TTL,
    }


def session_valid(session_data):
    if not session_data or not session_data.get("uid"):
        return False
    return int(session_data.get("exp", 0)) > time.time()


def may_manage(session_data, guild_id, bot_guild_ids):
    """Final say on access to one guild.

    The cached list is trusted for the session's lifetime, but the bot's current
    membership is re-checked every time -- so removing the bot from a server
    revokes the dashboard for it immediately.
    """
    if not session_valid(session_data):
        return False
    gid = str(guild_id)
    if gid not in {str(g) for g in session_data.get("guilds", [])}:
        return False
    return gid in {str(g) for g in bot_guild_ids}
