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

intents = discord.Intents.default()
client = discord.Client(intents=intents)


def get_subscriber_count():
    """
    Calls YouTube Data API v3 to get the subscriber count
    for the configured channel.
    """
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
    # Start background task
    update_status.start()


@tasks.loop(minutes=5)  # update every 5 minutes
async def update_status():
    sub_count = get_subscriber_count()
    if sub_count is None:
        activity = discord.Game(name="YT subs: error 😢")
    else:
        # Example status: "1,234 subs on YouTube"
        activity = discord.Game(name=f"{sub_count:,} subs on YouTube")

    await client.change_presence(status=discord.Status.online, activity=activity)


# Run bot
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_TOKEN not set in .env!")
    else:
        client.run(DISCORD_TOKEN)
