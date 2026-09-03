"""Human wording for official timestamps: Pacific time, relative when recent."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Vancouver")


def _clock(local: datetime) -> str:
    hour = local.hour % 12 or 12
    suffix = "a.m." if local.hour < 12 else "p.m."
    return f"{hour}:{local.minute:02d} {suffix} {local.tzname()}"


def human_time(moment: datetime, *, now: datetime | None = None) -> str:
    """ "2:10 p.m. PDT today", "yesterday at 4:30 p.m. PDT", "Aug 30 at 9:05 a.m. PDT"."""

    reference = (now or datetime.now(UTC)).astimezone(PACIFIC)
    local = moment.astimezone(PACIFIC)
    days = (reference.date() - local.date()).days
    if days == 0:
        return f"{_clock(local)} today"
    if days == 1:
        return f"yesterday at {_clock(local)}"
    date = f"{local.strftime('%b')} {local.day}"
    if local.year != reference.year:
        date += f", {local.year}"
    return f"{date} at {_clock(local)}"


def time_ago(moment: datetime, *, now: datetime | None = None) -> str:
    """ "just now", "about 25 minutes ago", "about 2 hours ago", "3 days ago"."""

    reference = now or datetime.now(UTC)
    seconds = max(0.0, (reference - moment).total_seconds())
    minutes = round(seconds / 60)
    if minutes < 2:
        return "just now"
    if minutes < 60:
        return f"about {minutes} minutes ago"
    hours = round(seconds / 3600)
    if hours < 48:
        return f"about {hours} hour{'s' if hours != 1 else ''} ago"
    days = round(seconds / 86400)
    return f"{days} days ago"
