"""Shared classification for sessions with automation-related flags."""

BOT_FLAG_KEYWORDS = ("Webdriver", "Selenium", "CDP", "Playwright", "Bot")


def has_bot_flag(flags) -> bool:
    """Return whether any flag identifies a known automation detection."""
    return any(
        any(keyword in str(flag) for keyword in BOT_FLAG_KEYWORDS)
        for flag in flags or ()
    )
