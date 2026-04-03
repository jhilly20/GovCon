"""Configuration management for the CFIC scraper.

Loads secrets and settings from environment variables.
Supports .env files for local development.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def get_required_env(name: str) -> str:
    """Get a required environment variable or raise an error."""
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set. "
            f"See .env.example for reference."
        )
    return value


# Monday.com
MONDAY_API_TOKEN = get_required_env("MONDAY_API_KEY")
MONDAY_BOARD_ID = get_required_env("MONDAY_BOARD_ID")
MONDAY_API_URL = "https://api.monday.com/v2"

# Slack
SLACK_BOT_TOKEN = get_required_env("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = get_required_env("SLACK_CHANNEL")

# CFIC
CFIC_EVENTS_URL = "https://www.cyberfic.org/events"
CFIC_BASE_URL = "https://www.cyberfic.org"

# Monday.com column IDs for the "Python Submissions" board
MONDAY_COLUMNS = {
    "name": "name",                          # Item name (event title)
    "close_date": "date_mkkqedzc",           # Close Date
    "link": "text_mkkq2vab",                 # Link to event detail page
    "description": "text_mkkqeet2",          # Description / Purpose
    "tpoc": "text_mkkqftmh",                 # Technical Point of Contact
    "tpoc_email": "tpoc_email_mkmfdxba",     # TPOC Email
    "tpoc_phone": "tpoc_phone_mkmfav28",     # TPOC Phone
    "agency": "text_mkvqfmz5",              # Agency
    "source": "text_mktm7tsx",              # Source
}

# Source identifier for items created by this scraper
SCRAPER_SOURCE = "CFIC Scraper"
