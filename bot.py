"""
bot.py

The Telegram-facing part of the project. Handles:
- /start command
- Time period selection (today / tomorrow / week / month)
- League selection
- Fetching + displaying matches
- A "Refresh" button for live matches
- Error handling for API and Telegram issues

This file does not know anything about how the football API works
internally — it only calls functions from api.py.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import api
from config import BOT_TOKEN

# Basic logging so errors are visible in the terminal while developing
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

PERIOD_LABELS = {
    "today": "📅 Today's matches",
    "tomorrow": "📅 Tomorrow's matches",
    "week": "🗓 This week's matches",
    "month": "📆 This month's matches",
}


# ---------------------------------------------------------------------------
# /start command — show the time period buttons
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"period:{key}")]
        for key, label in PERIOD_LABELS.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚽ What matches would you like to see?",
        reply_markup=reply_markup,
    )


# ---------------------------------------------------------------------------
# Step 1: user picked a time period -> show league buttons
# ---------------------------------------------------------------------------

async def handle_period_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    period = query.data.split(":")[1]  # e.g. "today"

    # Remember the chosen period for this user so we know it later
    context.user_data["period"] = period

    keyboard = []
    for key, league in api.LEAGUES.items():
        label = f"{league['flag']} {league['name']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"league:{key}")])
    keyboard.append([InlineKeyboardButton("🌍 All Top Leagues", callback_data="league:all")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🏆 Choose a league",
        reply_markup=reply_markup,
    )


# ---------------------------------------------------------------------------
# Step 2: user picked a league -> fetch and display matches
# ---------------------------------------------------------------------------

async def handle_league_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    league_key = query.data.split(":")[1]  # e.g. "premier_league" or "all"
    period = context.user_data.get("period", "today")

    # Remember the league too, so the Refresh button can reuse it
    context.user_data["league_key"] = league_key

    await query.edit_message_text("⏳ Fetching matches...")
    await send_matches(query, period, league_key)


async def send_matches(query, period: str, league_key: str) -> None:
    """
    Shared logic for fetching + displaying matches, used both by the
    initial league selection and by the Refresh button.
    """
    date_from, date_to = api.get_date_range(period)

    try:
        if league_key == "all":
            matches = api.get_fixtures_all_leagues(date_from, date_to)
        else:
            league = api.LEAGUES[league_key]
            matches = api.get_fixtures_by_date_range(league["id"], date_from, date_to)
    except api.FootballAPIError as exc:
        await query.edit_message_text(f"⚠️ Could not fetch matches: {exc}")
        return

    if not matches:
        await query.edit_message_text(
            "😔 No matches found for that selection.\n\n"
            "Try a different time period or league with /start."
        )
        return

    # Build one message with all matches, separated by a divider
    league_flags = {v["id"]: v["flag"] for v in api.LEAGUES.values()}
    blocks = []
    for match in matches:
        flag = "🌍"
        for league in api.LEAGUES.values():
            if league["name"] == match["league_name"]:
                flag = league["flag"]
                break
        blocks.append(api.format_match_message(match, flag))

    message_text = "\n\n━━━━━━━━━━━━━━━\n\n".join(blocks)

    # Telegram messages have a 4096 character limit — trim if needed
    if len(message_text) > 4000:
        message_text = message_text[:4000] + "\n\n... (truncated, too many matches)"

    keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message_text, reply_markup=reply_markup)


# ---------------------------------------------------------------------------
# Refresh button — re-fetch the same period + league the user last chose
# ---------------------------------------------------------------------------

async def handle_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Refreshing...")

    period = context.user_data.get("period")
    league_key = context.user_data.get("league_key")

    if not period or not league_key:
        await query.edit_message_text("Please start again with /start.")
        return

    await send_matches(query, period, league_key)


# ---------------------------------------------------------------------------
# Global error handler — catches anything unhandled so the bot never crashes
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception:", exc_info=context.error)


# ---------------------------------------------------------------------------
# Wire everything together and run the bot
# ---------------------------------------------------------------------------

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_period_selection, pattern="^period:"))
    application.add_handler(CallbackQueryHandler(handle_league_selection, pattern="^league:"))
    application.add_handler(CallbackQueryHandler(handle_refresh, pattern="^refresh$"))
    application.add_error_handler(error_handler)

    logger.info("Bot is starting...")
    application.run_polling()


if __name__ == "__main__":
    main()