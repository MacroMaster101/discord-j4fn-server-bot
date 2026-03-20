# Discord YouTube Status Bot

A simple Python Discord bot that displays a YouTube channel's subscriber count in its Discord presence and responds to basic greeting messages.

## Features

- Updates the bot status with the current YouTube subscriber count
- Refreshes the Discord presence every 5 minutes
- Responds to common greetings such as `hi`, `hello`, and `hey`
- Includes a lightweight Flask web server for deployment environments such as Render
- Loads configuration from environment variables or a local `.env` file

## How It Works

The bot uses the **YouTube Data API v3** to fetch the subscriber count for a configured YouTube channel. Once the bot is online, it updates its Discord presence to something like:

`12,345 subs on YouTube`

If the YouTube API request fails or the environment variables are missing, the bot shows an error-style status instead.

## Project Structure

```text
discord-youtube-status-bot-main/
├── bot.py              # Main bot logic
├── requirements.txt    # Python dependencies
└── README.md           # Project documentation
```

## Requirements

- Python 3
- A Discord bot token
- A YouTube Data API key
- A YouTube channel ID

## Installation

1. Clone or download the project.
2. Open the project folder.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root and add the following:

```env
DISCORD_TOKEN=your_discord_bot_token
YOUTUBE_API_KEY=your_youtube_api_key
YOUTUBE_CHANNEL_ID=your_youtube_channel_id
PORT=8080
```

### Variable Details

- `DISCORD_TOKEN` - Discord bot token from the Discord Developer Portal
- `YOUTUBE_API_KEY` - API key for YouTube Data API v3
- `YOUTUBE_CHANNEL_ID` - ID of the YouTube channel you want to track
- `PORT` - Optional port for the Flask keep-alive server

## Running the Bot

Start the bot with:

```bash
python bot.py
```

When the bot starts:

- the Flask web server starts in a background thread
- the Discord bot logs in using your token
- the bot updates its presence every 5 minutes

## Discord Behavior

The bot currently responds to these greeting messages:

- `hi`
- `hello`
- `hey`

Example response:

```text
Hi @username! 👋 Welcome to our Discord server! 🎉😊
```

## Deployment Notes

This project is structured to work well on hosting platforms that expect a running web service, such as Render. The included Flask app provides a small endpoint at `/` that returns:

```text
Discord bot is running! ✅
```

This can be useful for uptime checks or external ping services.

## Dependencies

The project uses the following Python packages:

- `discord.py`
- `requests`
- `python-dotenv`
- `flask`

## Possible Improvements

- Add slash commands for bot interaction
- Support tracking more YouTube statistics
- Add better error logging
- Cache API responses to reduce requests
- Add configuration validation on startup
- Add support for multiple channels or servers

## Summary

This project is a beginner-friendly Discord automation bot that connects Discord and YouTube in a simple way. It is useful as a small personal project, learning project, or starter template for building more advanced Discord bots.
