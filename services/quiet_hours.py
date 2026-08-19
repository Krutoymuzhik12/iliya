"""Тихие часы: Pull всегда, Push только 09:00–18:00 МСК."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config.settings import AppSettings


class QuietHours:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        try:
            self.tz = ZoneInfo(settings.timezone)
        except Exception:
            self.tz = timezone(timedelta(hours=3), name="MSK-fallback")

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def can_push(self, when: datetime | None = None) -> bool:
        local = when or self.now()
        return self.settings.push_hour_start <= local.hour < self.settings.push_hour_end
