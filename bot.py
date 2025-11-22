import os
import asyncio
import threading

import requests
from dotenv import load_dotenv

import discord
from discord.ext import tasks

from flask import Flask

# ----------------- FLASK KEEP-ALIVE -----------------

app = Flask(__name__)

@app.route("/")
def home():
    return "Discord bot is running! ✅"

def run_web():
    # Render usually provides PORT env var, fall back to 8080 locally
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()


# ----------------- DISCORD + YOUTUBE BOT -----------------

# Load .env variables (locally). On Render, it will just use environment vars.
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")

# Intents
intents = discord.Intents.default()
intents.message_content = True  # needed to read message content
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


@client.event
async def on_ready():
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
    # Don’t reply to ourselves or other bots
    if message.author.bot:
        return

    # Normalize message: trim, lowercase, remove simple trailing punctuation
    content = message.content.strip().lower().rstrip(".!?")

    # Greetings (capitalization doesn't matter because we used lower())
    greetings = ["hi", "hello", "hey"]

    if content in greetings:
        await message.channel.send(
            f"Hi {message.author.mention}! 👋 Welcome to our Discord server! 🎉😊"
        )


# ----------------- RUN BOT -----------------

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_TOKEN not set in environment or .env!")
    else:
        # Start the tiny web server for Render + cron ping
        keep_alive()
        # Start the Discord bot
        client.run(DISCORD_TOKEN)
