import os
import asyncio
import requests
from dotenv import load_dotenv

import discord
from discord.ext import tasks

# Load .env variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")

# ---- INTENTS ----
intents = discord.Intents.default()
intents.message_content = True  # Required to read messages
client = discord.Client(intents=intents)


# ---- YOUTUBE SUBSCRIBER COUNT ----
def get_subscriber_count():
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


# ---- BOT READY EVENT ----
@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print("------")
    update_status.start()


# ---- UPDATE BOT STATUS EVERY 5 MINUTES ----
@tasks.loop(minutes=5)
async def update_status():
    sub_count = get_subscriber_count()

    if sub_count is None:
        activity = discord.Game(name="YT subs: error 😢")
    else:
        activity = discord.Game(name=f"{sub_count:,} subs on YouTube")

    await client.change_presence(status=discord.Status.online, activity=activity)


# ---- REPLY TO GREETINGS ----
@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Normalize text
    content = message.content.strip().lower().rstrip(".!?")

    # Allowed greetings
    greetings = ["hi", "hello", "hey"]

    if content in greetings:
        await message.channel.send(
            f"Hi {message.author.mention}! 👋 Welcome to our Discord server! 🎉😊"
        )


# ---- RUN BOT ----
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_TOKEN not set in .env!")
    else:
        client.run(DISCORD_TOKEN)
