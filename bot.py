import os
import asyncio
import threading
import datetime

import requests
from dotenv import load_dotenv

import discord
from discord.ext import tasks

from flask import Flask, jsonify

# ----------------- FLASK KEEP-ALIVE -----------------

app = Flask(__name__)

# Store bot start time for uptime calculation
BOT_START_TIME = None


@app.route("/")
def home():
    uptime_str = "N/A"
    if BOT_START_TIME:
        delta = datetime.datetime.utcnow() - BOT_START_TIME
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

    return jsonify({
        "status": "online",
        "message": "Discord bot is running! ✅",
        "uptime": uptime_str,
    })


@app.route("/health")
def health():
    """Dedicated health-check endpoint for uptime services."""
    return "OK", 200


def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()


# ----------------- DISCORD + YOUTUBE BOT -----------------

# Load .env variables (locally). On Fly.io / other hosts, set env vars in the dashboard.
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")

# Bot command prefix
PREFIX = "!"

# Intents
intents = discord.Intents.default()
intents.message_content = True   # needed to read message content
intents.members = True           # needed for accurate member counts
intents.presences = True         # needed for online/offline counts
client = discord.Client(intents=intents)


def get_subscriber_count():
    """
    Calls YouTube Data API v3 to get the subscriber count
    for the configured channel.
    """
    if not (YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID):
        print("YouTube env vars not set.")
        return None

    url = (
        "https://www.googleapis.com/youtube/v3/channels"
        f"?part=statistics&id={YOUTUBE_CHANNEL_ID}&key={YOUTUBE_API_KEY}"
    )
    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        items = data.get("items", [])
        if not items:
            print("No channel data found. Check your CHANNEL_ID or API key.")
            return None

        stats = items[0].get("statistics", {})
        sub_count = stats.get("subscriberCount")
        if sub_count is None:
            print("subscriberCount not found in API response.")
            return None

        return int(sub_count)
    except Exception as e:
        print(f"Error getting subscriber count: {e}")
        return None


def get_youtube_channel_info():
    """
    Fetch extended YouTube channel info (name, subs, views, videos).
    """
    if not (YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID):
        return None

    url = (
        "https://www.googleapis.com/youtube/v3/channels"
        f"?part=statistics,snippet&id={YOUTUBE_CHANNEL_ID}&key={YOUTUBE_API_KEY}"
    )
    try:
        response = requests.get(url, timeout=10)
        data = response.json()

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
        print(f"Error getting channel info: {e}")
        return None


# -------------------- EVENTS --------------------

@client.event
async def on_ready():
    global BOT_START_TIME
    BOT_START_TIME = datetime.datetime.utcnow()

    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print("------")
    update_status.start()


@tasks.loop(minutes=5)  # update every 5 minutes
async def update_status():
    sub_count = get_subscriber_count()
    if sub_count is None:
        activity = discord.Game(name="YT subs: error 😢")
    else:
        activity = discord.Game(name=f"{sub_count:,} subs on YouTube")

    await client.change_presence(status=discord.Status.online, activity=activity)




@client.event
async def on_message(message: discord.Message):
    # Don't reply to ourselves or other bots
    if message.author.bot:
        return

    # Normalize message: trim, lowercase, remove simple trailing punctuation
    content = message.content.strip().lower().rstrip(".!?")

    # ---- Greetings ----
    greetings = ["hi", "hello", "hey"]
    if content in greetings:
        await message.channel.send(
            f"Hi {message.author.mention}! 👋 Welcome to our Discord server! 🎉😊"
        )
        return

    # ---- Commands (prefix: !) ----
    if not message.content.startswith(PREFIX):
        return

    cmd = message.content[len(PREFIX):].strip().lower()

    # ---------- !stats ----------
    if cmd == "stats":
        guild = message.guild
        if guild is None:
            await message.channel.send("This command can only be used in a server.")
            return

        # Server info
        total_members = guild.member_count
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        roles = len(guild.roles) - 1  # exclude @everyone
        emojis = len(guild.emojis)
        boost_level = guild.premium_tier
        boosts = guild.premium_subscription_count or 0

        # Online / Offline (requires presences intent)
        online = sum(
            1 for m in guild.members
            if m.status != discord.Status.offline and not m.bot
        )
        bots = sum(1 for m in guild.members if m.bot)

        owner = guild.owner

        # Creation date
        created = guild.created_at.strftime("%b %d, %Y")

        # Build embed
        embed = discord.Embed(
            title=f"📊  {guild.name}  —  Server Stats",
            color=0x5865F2,  # Discord blurple
            timestamp=datetime.datetime.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👥 Members", value=f"{total_members:,}", inline=True)
        embed.add_field(name="🟢 Online", value=f"{online:,}", inline=True)
        embed.add_field(name="🤖 Bots", value=f"{bots:,}", inline=True)

        embed.add_field(name="💬 Text Channels", value=str(text_channels), inline=True)
        embed.add_field(name="🔊 Voice Channels", value=str(voice_channels), inline=True)
        embed.add_field(name="📂 Categories", value=str(categories), inline=True)

        embed.add_field(name="🏷️ Roles", value=str(roles), inline=True)
        embed.add_field(name="😀 Emojis", value=str(emojis), inline=True)
        embed.add_field(name="🚀 Boost Level", value=f"Tier {boost_level} ({boosts} boosts)", inline=True)

        embed.add_field(name="👑 Owner", value=str(owner), inline=True)
        embed.add_field(name="📅 Created", value=created, inline=True)

        # YouTube stats in the same embed
        yt = get_youtube_channel_info()
        if yt:
            yt_text = (
                f"**{yt['name']}**\n"
                f"📺 Subscribers: **{yt['subscribers']:,}**\n"
                f"👁️ Total Views: **{yt['views']:,}**\n"
                f"🎬 Videos: **{yt['videos']:,}**"
            )
            embed.add_field(name="🔴 YouTube Channel", value=yt_text, inline=False)

        embed.set_footer(text=f"Requested by {message.author}", icon_url=message.author.display_avatar.url)
        await message.channel.send(embed=embed)
        return

    # ---------- !yt ----------
    if cmd == "yt":
        yt = get_youtube_channel_info()
        if yt is None:
            await message.channel.send("❌ Could not fetch YouTube data.")
            return

        embed = discord.Embed(
            title=f"🔴  {yt['name']}  —  YouTube Stats",
            color=0xFF0000,
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="📺 Subscribers", value=f"{yt['subscribers']:,}", inline=True)
        embed.add_field(name="👁️ Total Views", value=f"{yt['views']:,}", inline=True)
        embed.add_field(name="🎬 Videos", value=f"{yt['videos']:,}", inline=True)
        embed.set_footer(text=f"Requested by {message.author}", icon_url=message.author.display_avatar.url)
        await message.channel.send(embed=embed)
        return

    # ---------- !help ----------
    if cmd == "help":
        embed = discord.Embed(
            title="📖  Bot Commands",
            description="Here are the available commands:",
            color=0x57F287,
        )
        embed.add_field(name=f"`{PREFIX}stats`", value="Show server stats + YouTube info", inline=False)
        embed.add_field(name=f"`{PREFIX}yt`", value="Show YouTube channel stats", inline=False)
        embed.add_field(name=f"`{PREFIX}help`", value="Show this help message", inline=False)
        embed.set_footer(text="Also responds to hi, hello, hey 👋")
        await message.channel.send(embed=embed)
        return


# ----------------- RUN BOT -----------------

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_TOKEN not set in environment or .env!")
    else:
        # Start the tiny web server (needed for Fly.io health checks)
        keep_alive()
        # Start the Discord bot
        client.run(DISCORD_TOKEN)
