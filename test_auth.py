"""Authorization boundary checks for the Discord sign-in.

The question these answer is the only one that matters once other people can log
in: can a server admin reach anything that is not theirs?

Run with: python test_auth.py
"""

import os
import sys

os.environ.setdefault("DISCORD_TOKEN", "test")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-token")
os.environ.setdefault("COOKIE_SECURE", "0")       # the test client is plain http

import automod
import auth                                        # noqa: E402
import bot                                         # noqa: E402

# Keep the suite off the real settings.
import shutil
automod.GUILD_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "_t_auth")
os.makedirs(automod.GUILD_DIR, exist_ok=True)
automod.reset_guild_cache()

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


# Two guilds: the user runs ALICE_GUILD only. The bot is in both.
ALICE_GUILD = "111111111111111111"
OTHER_GUILD = "222222222222222222"


class FakeGuild:
    def __init__(self, gid):
        self.id = int(gid)
        self.name = "guild-%s" % gid
        self.icon = None
        self.text_channels = []


class FakeClient:
    """discord.Client exposes `guilds` read-only, so stand in for the whole thing."""

    def __init__(self, guild_ids):
        self.guilds = [FakeGuild(g) for g in guild_ids]
        self.latency = 0.05

    def is_ready(self):
        return True


def set_bot_guilds(*guild_ids):
    bot.client = FakeClient(guild_ids)


set_bot_guilds(ALICE_GUILD, OTHER_GUILD)

app = bot.app
app.config["TESTING"] = True


def sign_in(client, guilds):
    """Put a Discord session in the cookie jar, as the callback would."""
    with client.session_transaction() as sess:
        sess["discord"] = {
            "uid": "900000000000000000",
            "uname": "alice",
            "avatar": None,
            "guilds": list(guilds),
            "names": {g: "guild-%s" % g for g in guilds},
            "icons": {},
            "exp": 9999999999,
        }


# Taken from the bot rather than hard-coded: CI supplies its own ADMIN_PASSWORD,
# so a literal here only matches when the variable happens to be unset.
OWNER = {"Authorization": "Bearer %s" % bot.ADMIN_PASSWORD}

print("\nAnonymous access")
with app.test_client() as c:
    for path in ("/api/automod?guild_id=" + ALICE_GUILD,
                 "/api/automod/blocked?guild_id=" + ALICE_GUILD,
                 "/api/mod/warnings?guild_id=" + ALICE_GUILD,
                 "/api/config", "/api/logs", "/api/servers"):
        r = c.get(path)
        check("anonymous is refused %s" % path.split("?")[0],
              r.status_code == 401, "-> %d" % r.status_code)

    r = c.get("/api/me")
    check("/api/me says not signed in",
          r.status_code == 200 and r.get_json()["authenticated"] is False)


print("\nA signed-in admin, on their own server")
with app.test_client() as c:
    sign_in(c, [ALICE_GUILD])
    r = c.get("/api/automod?guild_id=" + ALICE_GUILD)
    check("can read their own settings", r.status_code == 200,
          "-> %d" % r.status_code)
    r = c.post("/api/automod", json={"guild_id": ALICE_GUILD, "scam_threshold": 7})
    check("can change their own settings", r.status_code == 200,
          "-> %d" % r.status_code)
    r = c.get("/api/automod/blocked?guild_id=" + ALICE_GUILD)
    check("can list their own blocked images", r.status_code == 200)
    r = c.get("/api/me")
    body = r.get_json()
    check("/api/me lists only their guild",
          [g["id"] for g in body["guilds"]] == [ALICE_GUILD], "-> %r" % (body,))
    check("/api/me does not claim owner", body["owner"] is False)


print("\nThe same admin, reaching for someone else's server")
with app.test_client() as c:
    sign_in(c, [ALICE_GUILD])
    for method, path, payload in (
        ("get", "/api/automod?guild_id=" + OTHER_GUILD, None),
        ("get", "/api/automod/blocked?guild_id=" + OTHER_GUILD, None),
        ("get", "/api/mod/warnings?guild_id=" + OTHER_GUILD, None),
        ("post", "/api/automod", {"guild_id": OTHER_GUILD, "scam_threshold": 1}),
        ("post", "/api/automod/reset", {"guild_id": OTHER_GUILD}),
        ("post", "/api/mod/action", {"guild_id": OTHER_GUILD, "action": "ban",
                                     "user": "5", "reason": "x"}),
        ("post", "/api/automod/blocked/remove", {"guild_id": OTHER_GUILD, "id": "1"}),
    ):
        r = getattr(c, method)(path, json=payload) if payload else getattr(c, method)(path)
        check("%s %s is forbidden" % (method.upper(), path.split("?")[0]),
              r.status_code == 403, "-> %d" % r.status_code)


print("\nOwner-only endpoints stay owner-only")
with app.test_client() as c:
    sign_in(c, [ALICE_GUILD])
    for method, path in (("get", "/api/config"), ("post", "/api/config"),
                         ("get", "/api/logs"), ("get", "/api/servers"),
                         ("post", "/api/presence"), ("post", "/api/restart"),
                         ("post", "/api/send-message")):
        r = getattr(c, method)(path, json={})
        check("a server admin cannot reach %s" % path,
              r.status_code == 401, "-> %d" % r.status_code)


print("\nA missing or malformed guild is rejected, not guessed")
with app.test_client() as c:
    sign_in(c, [ALICE_GUILD])
    r = c.get("/api/automod")
    check("no guild_id is a 400", r.status_code == 400, "-> %d" % r.status_code)
    r = c.get("/api/automod?guild_id=not-a-guild")
    check("an unknown guild is a 403", r.status_code == 403, "-> %d" % r.status_code)
    r = c.get("/api/automod?guild_id=")
    check("an empty guild_id is a 400", r.status_code == 400, "-> %d" % r.status_code)


print("\nThe bot leaving a server revokes the dashboard immediately")
with app.test_client() as c:
    sign_in(c, [ALICE_GUILD, OTHER_GUILD])       # cookie still lists both
    set_bot_guilds(OTHER_GUILD)                   # but the bot left ALICE_GUILD
    r = c.get("/api/automod?guild_id=" + ALICE_GUILD)
    check("a guild the bot has left is forbidden", r.status_code == 403,
          "-> %d" % r.status_code)
    set_bot_guilds(ALICE_GUILD, OTHER_GUILD)


print("\nAn expired session is not honoured")
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess["discord"] = {"uid": "9", "uname": "stale", "guilds": [ALICE_GUILD],
                           "names": {}, "icons": {}, "exp": 1}
    r = c.get("/api/automod?guild_id=" + ALICE_GUILD)
    check("an expired cookie is refused", r.status_code == 401,
          "-> %d" % r.status_code)


print("\nThe owner is unrestricted")
with app.test_client() as c:
    r = c.get("/api/automod?guild_id=" + OTHER_GUILD, headers=OWNER)
    check("the owner may read any guild", r.status_code == 200,
          "-> %d" % r.status_code)
    r = c.get("/api/config", headers=OWNER)
    check("the owner may read global config", r.status_code == 200)
    r = c.get("/api/me", headers=OWNER)
    check("/api/me marks the owner", r.get_json()["owner"] is True)


print("\nCross-site POSTs are refused")
with app.test_client() as c:
    sign_in(c, [ALICE_GUILD])
    r = c.post("/api/automod",
               json={"guild_id": ALICE_GUILD, "scam_threshold": 9},
               headers={"Origin": "https://evil.example"})
    check("a foreign Origin is rejected", r.status_code == 403,
          "-> %d" % r.status_code)
    r = c.post("/api/automod",
               json={"guild_id": ALICE_GUILD, "scam_threshold": 6},
               headers={"Origin": "http://localhost"})
    check("our own Origin is accepted", r.status_code == 200,
          "-> %d" % r.status_code)


print("\nSession cookie carries no Discord token")
state = auth.new_state()
check("a fresh state is unguessable", len(state) >= 20)
built = {"uid": "1", "uname": "x", "guilds": [], "names": {}, "icons": {},
         "exp": 9999999999}
check("the session shape holds no access token",
      not any("token" in k.lower() for k in built))
check("sessions expire", auth.session_valid({"uid": "1", "exp": 1}) is False)
check("a valid session passes", auth.session_valid(built) is True)

print("\nPermission maths")
check("manage-guild counts",
      auth.runs_guild({"permissions": str(auth.MANAGE_GUILD)}) is True)
check("administrator counts",
      auth.runs_guild({"permissions": str(auth.ADMINISTRATOR)}) is True)
check("ownership counts",
      auth.runs_guild({"permissions": "0", "owner": True}) is True)
check("a plain member does not",
      auth.runs_guild({"permissions": "0"}) is False)
check("send-messages alone does not",
      auth.runs_guild({"permissions": str(1 << 11)}) is False)
check("junk permissions do not",
      auth.runs_guild({"permissions": "nonsense"}) is False)
check("guilds the bot is absent from are dropped",
      auth.manageable([{"id": "5", "name": "n", "permissions": str(auth.MANAGE_GUILD)}],
                      ["6"]) == [])

print("")
print("Discord calls identify themselves")
# Discord fronts its API with Cloudflare, which answers the default
# "Python-urllib/3.x" with 403 "error code: 1010" before the API sees it.
check("a user agent is declared", bool(auth.USER_AGENT))
check("it is not urllib's default",
      "urllib" not in auth.USER_AGENT.lower())
check("it follows the DiscordBot form",
      auth.USER_AGENT.startswith("DiscordBot ("), auth.USER_AGENT)

# Patch urlopen, not _request: the header is added inside _request, so stubbing
# that would skip the very code under test.
import json as _json
import urllib.request as _urlreq

_seen = {}


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return _json.dumps({"access_token": "t", "id": "1",
                            "username": "u"}).encode()


def _fake_urlopen(request, timeout=None):
    _seen.clear()
    _seen.update({k.lower(): v for k, v in request.header_items()})
    return _FakeResponse()


_real_urlopen = _urlreq.urlopen
_urlreq.urlopen = _fake_urlopen
try:
    auth.exchange_code("code")
    check("the token exchange sends it",
          _seen.get("user-agent") == auth.USER_AGENT,
          "-> %r" % (_seen.get("user-agent"),))
    auth.fetch_user("tok")
    check("the user lookup sends it",
          _seen.get("user-agent") == auth.USER_AGENT)
    check("and still sends the bearer token",
          _seen.get("authorization") == "Bearer tok", "-> %r" % (_seen,))
    auth.fetch_guilds("tok")
    check("the guild lookup sends it",
          _seen.get("user-agent") == auth.USER_AGENT)
finally:
    _urlreq.urlopen = _real_urlopen

shutil.rmtree(automod.GUILD_DIR, ignore_errors=True)

print("\n%d checks failed" % len(FAILURES))
for name in FAILURES:
    print("  - %s" % name)
sys.exit(1 if FAILURES else 0)
