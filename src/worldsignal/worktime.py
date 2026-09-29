"""Working hours: when the background work (collecting news, the AI, full texts) runs.

Default: always. With ``work.limited`` on, the work rests outside ``work.start``:00 - ``work.end``:00 (local time,
may wrap past midnight). Resting is not stopping: what the user asks for by hand (a summary, a full text, "scan
now") is still done, and the window and its data stay usable.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, tzinfo
from typing import Any

from .notify import in_quiet_hours
from .repo.settings import SettingsRepository


def is_resting(prefs: dict[str, Any], local_hour: int) -> bool:
    if not prefs.get("work.limited", False):
        return False
    start, end = int(prefs.get("work.start", 7)), int(prefs.get("work.end", 23))
    # The rest is the time outside the working hours; equal start and end mean "the whole day" (never resting).
    return in_quiet_hours(local_hour, end, start)


class WorkHours:
    def __init__(self, settings: SettingsRepository, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 zone: tzinfo | None = None) -> None:
        self.settings = settings
        self.clock = clock
        self.zone = zone  # None: this computer's time zone

    def resting(self) -> bool:
        return is_resting(self.settings.get_preferences(), self.clock().astimezone(self.zone).hour)
