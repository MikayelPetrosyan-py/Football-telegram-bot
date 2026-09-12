"""
api.py

Everything related to talking to football-data.org API.

This file:
1. Sends HTTP requests to football-data.org.
2. Converts raw JSON into clean Python dictionaries.
3. Converts UTC time to Asia/Yerevan.
4. Converts API statuses into friendly Telegram text.

bot.py should never work with raw API JSON directly.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os

import requests
from dotenv import load_dotenv

from config import TIMEZONE


# Load .env
load_dotenv()

FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN")

BASE_URL = "https://api.football-data.org/v4"


HEADERS = {
    "X-Auth-Token": FOOTBALL_DATA_TOKEN,
}


# football-data.org competition codes
LEAGUES = {
    "premier_league": {
        "id": "PL",
        "name": "Premier League",
        "flag": "🇬🇧",
    },
    "la_liga": {
        "id": "PD",
        "name": "La Liga",
        "flag": "🇪🇸",
    },
    "serie_a": {
        "id": "SA",
        "name": "Serie A",
        "flag": "🇮🇹",
    },
    "bundesliga": {
        "id": "BL1",
        "name": "Bundesliga",
        "flag": "🇩🇪",
    },
    "ligue_1": {
        "id": "FL1",
        "name": "Ligue 1",
        "flag": "🇫🇷",
    },
    "champions_league": {
        "id": "CL",
        "name": "Champions League",
        "flag": "🇪🇺",
    },
}


class FootballAPIError(Exception):
    """Raised when the football API request fails."""

    pass


def _request(competition_code: str, date_from: str, date_to: str) -> list:
    """
    Get matches from football-data.org for one competition
    and a specific date range.
    """

    url = f"{BASE_URL}/competitions/{competition_code}/matches"

    params = {
        "dateFrom": date_from,
        "dateTo": date_to,
    }

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=10,
        )

    except requests.exceptions.RequestException as exc:
        raise FootballAPIError(
            f"Could not reach the football API: {exc}"
        )

    if response.status_code == 401:
        raise FootballAPIError(
            "Invalid football-data.org API token."
        )

    if response.status_code == 403:
        raise FootballAPIError(
            "Your football-data.org plan does not allow this request."
        )

    if response.status_code == 429:
        raise FootballAPIError(
            "API rate limit reached. Please try again later."
        )

    if response.status_code != 200:
        raise FootballAPIError(
            f"Football API returned status {response.status_code}."
        )

    data = response.json()

    return data.get("matches", [])


def get_fixtures_by_date_range(
    league_id: str,
    date_from: str,
    date_to: str,
) -> list:
    """
    Fetch matches for one league between two dates.

    league_id examples:
    PL, PD, SA, BL1, FL1, CL
    """

    raw_matches = _request(
        league_id,
        date_from,
        date_to,
    )

    return [
        _parse_fixture(match)
        for match in raw_matches
    ]


def get_fixtures_all_leagues(
    date_from: str,
    date_to: str,
) -> list:
    """
    Fetch matches from all configured top leagues.

    This makes one request per league.
    """

    all_fixtures = []

    for league in LEAGUES.values():

        fixtures = get_fixtures_by_date_range(
            league["id"],
            date_from,
            date_to,
        )

        all_fixtures.extend(fixtures)

    return all_fixtures


def _parse_fixture(raw: dict) -> dict:
    """
    Convert football-data.org match JSON
    into the simple structure used by bot.py.
    """

    competition = raw["competition"]
    home_team = raw["homeTeam"]
    away_team = raw["awayTeam"]
    score = raw.get("score", {})
    full_time = score.get("fullTime", {})

    local_dt = _convert_to_local_time(
        raw["utcDate"]
    )

    return {
        "league_name": competition["name"],

        "date": local_dt.strftime("%d %B"),

        "time": local_dt.strftime("%H:%M"),

        "home_team": home_team["name"],

        "away_team": away_team["name"],

        "status_short": _convert_status(
            raw.get("status")
        ),

        "status_long": raw.get(
            "status",
            "UNKNOWN"
        ),

        "elapsed": raw.get("minute"),

        "goals_home": full_time.get("home"),

        "goals_away": full_time.get("away"),
    }


def _convert_status(status: str) -> str:
    """
    Convert football-data.org statuses
    to the status codes expected by bot.py.
    """

    status_mapping = {

        "SCHEDULED": "NS",

        "TIMED": "NS",

        "IN_PLAY": "1H",

        "LIVE": "1H",

        "PAUSED": "HT",

        "FINISHED": "FT",

        "POSTPONED": "PST",

        "SUSPENDED": "SUSP",

        "CANCELLED": "CANC",
    }

    return status_mapping.get(
        status,
        status,
    )


def _convert_to_local_time(
    iso_date_string: str,
) -> datetime:
    """
    Convert UTC datetime from the API
    into configured local timezone.
    """

    utc_dt = datetime.fromisoformat(
        iso_date_string.replace("Z", "+00:00")
    )

    local_dt = utc_dt.astimezone(
        ZoneInfo(TIMEZONE)
    )

    return local_dt


def format_match_status(match: dict) -> str:
    """
    Convert match status into friendly Telegram text.
    """

    code = match["status_short"]

    # Match hasn't started
    if code in {"NS", "TBD"}:
        return "🕐 NOT STARTED"

    # Half-time
    if code == "HT":
        return "⏸️ HALFTIME"

    # Live
    if code in {"1H", "2H", "ET", "P", "BT"}:

        minute = match["elapsed"]

        minute_text = (
            f"{minute}'"
            if minute is not None
            else "LIVE"
        )

        return f"🔴 LIVE — {minute_text}"

    # Finished
    if code in {"FT", "AET", "PEN"}:
        return "🟢 FINISHED"

    # Postponed
    if code == "PST":
        return "⏳ POSTPONED"

    # Cancelled
    if code == "CANC":
        return "❌ CANCELLED"

    # Suspended
    if code in {"SUSP", "INT"}:
        return "⛔ SUSPENDED"

    # Unknown status
    return match["status_long"].upper()


def format_match_message(
    match: dict,
    league_flag: str = "⚽",
) -> str:
    """
    Build Telegram message for one match.
    """

    status_line = format_match_status(match)

    code = match["status_short"]

    # Before kickoff
    if code in {"NS", "TBD"}:

        score_line = (
            f"{match['home_team']} 🆚 "
            f"{match['away_team']}"
        )

    else:

        home_goals = (
            match["goals_home"]
            if match["goals_home"] is not None
            else 0
        )

        away_goals = (
            match["goals_away"]
            if match["goals_away"] is not None
            else 0
        )

        score_line = (
            f"{match['home_team']} "
            f"{home_goals} - {away_goals} "
            f"{match['away_team']}"
        )

    return (
        f"{league_flag} "
        f"{match['league_name'].upper()}\n\n"

        f"📅 {match['date']}\n"

        f"⏰ {match['time']}\n\n"

        f"{status_line}\n\n"

        f"{score_line}"
    )


def get_date_range(period: str) -> tuple:
    """
    Return date_from and date_to based on the
    user's selected period.

    Supported:
    today
    tomorrow
    week
    month
    """

    today_local = datetime.now(
        ZoneInfo(TIMEZONE)
    ).date()

    if period == "today":

        date_from = today_local
        date_to = today_local

    elif period == "tomorrow":

        date_from = today_local + timedelta(days=1)
        date_to = date_from

    elif period == "week":

        date_from = today_local
        date_to = today_local + timedelta(days=7)

    elif period == "month":

        date_from = today_local
        date_to = today_local + timedelta(days=30)

    else:

        raise ValueError(
            f"Unknown period: {period}"
        )

    return (
        date_from.strftime("%Y-%m-%d"),
        date_to.strftime("%Y-%m-%d"),
    )