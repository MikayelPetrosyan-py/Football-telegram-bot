"""
config.py

Loads configuration values from the .env file.
"""

import os
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Yerevan")

# How often live matches can be refreshed
LIVE_REFRESH_SECONDS = int(
    os.getenv("LIVE_REFRESH_SECONDS", "60")
)

# Check required values
if not FOOTBALL_DATA_TOKEN:
    raise ValueError(
        "FOOTBALL_DATA_TOKEN is missing. "
        "Add it to your .env file."
    )

if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN is missing. "
        "Add it to your .env file."
    )