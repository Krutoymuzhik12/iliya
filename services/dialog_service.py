"""Один бот на Poe: IlyaDemoBal-Manager. История — последние HISTORY_LIMIT."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from config.settings import AppSettings
from services import poe

logger = logging.getLogger(__name__)

FALLBACK = "Сейчас уточню и вернусь с ответом."


class DialogService:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    async def delay_reply(self) -> None:
        if self.settings.fast_mode:
            await asyncio.sleep(1.5)
            return
        await asyncio.sleep(
            random.uniform(self.settings.reply_delay_min_sec, self.settings.reply_delay_max_sec)
        )

    async def build_reply(
        self,
        history: list[dict],
        user_text: str,
        *,
        extra_hints: list[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if not self.settings.poe_ready():
            return FALLBACK, {"need_manager": False}
        try:
            reply, need_manager = await poe.generate_reply(
                history,
                user_text,
                extra_hints=extra_hints,
            )
        except Exception:
            logger.exception("Poe не ответил")
            return FALLBACK, {"need_manager": False}
        return (reply or FALLBACK).strip(), {"need_manager": bool(need_manager)}
