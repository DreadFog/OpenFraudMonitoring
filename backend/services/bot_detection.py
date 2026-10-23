"""Shared classification for sessions with automation-related flags."""

from sqlalchemy import Text, case, column, exists, func, or_, select

BOT_FLAG_KEYWORDS = ("Webdriver", "Selenium", "CDP", "Playwright", "Bot")


def has_bot_flag(flags) -> bool:
    """Return whether any flag identifies a known automation detection."""
    return any(
        any(keyword in str(flag) for keyword in BOT_FLAG_KEYWORDS)
        for flag in flags or ()
    )


def bot_flag_expression(flags):
    """Case-sensitive keyword matching against individual JSONB array entries."""
    entries = func.jsonb_array_elements_text(
        case(
            (func.jsonb_typeof(flags) == "array", flags),
            else_=func.jsonb_build_array(),
        )
    ).table_valued(column("value", Text)).alias("bot_flags")
    return exists(
        select(1).select_from(entries).where(
            or_(*(entries.c.value.contains(keyword) for keyword in BOT_FLAG_KEYWORDS))
        )
    )
