"""Лиды в Telegram-группу через Bot API. Avito-чаты не трогает."""

from __future__ import annotations

import logging

import httpx

from config.settings import AppSettings

logger = logging.getLogger(__name__)


class TelegramLeads:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._ok = False

    def configured(self) -> bool:
        return self.settings.tg_ready()

    async def start(self) -> None:
        if not self.configured():
            logger.warning("TG: нет TG_BOT_TOKEN / TG_LEAD_CHAT_ID — лиды в группу не уйдут")
            return
        url = f"https://api.telegram.org/bot{self.settings.tg_bot_token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url)
                data = r.json()
            if not data.get("ok"):
                logger.warning("TG getMe: %s", data)
                return
            me = data.get("result") or {}
            self._ok = True
            logger.info(
                "TG лиды: бот @%s → чат %s",
                me.get("username") or me.get("id"),
                self.settings.tg_lead_chat_id,
            )
        except Exception:
            logger.exception("TG: не удалось проверить бота")

    async def send_photo(self, data: bytes, *, filename: str = "photo.jpg", caption: str = "") -> bool:
        """Фото не прошло (например, больше 10 МБ) - уходит файлом."""
        if await self._send_media("sendPhoto", "photo", data, filename, caption):
            return True
        return await self.send_document(data, filename=filename, caption=caption)

    async def send_audio(self, data: bytes, *, filename: str = "voice.mp3", caption: str = "") -> bool:
        if await self._send_media("sendAudio", "audio", data, filename, caption):
            return True
        return await self.send_document(data, filename=filename, caption=caption)

    async def send_document(
        self, data: bytes, *, filename: str = "file.bin", caption: str = ""
    ) -> bool:
        return await self._send_media("sendDocument", "document", data, filename, caption)

    async def _send_media(
        self, method: str, field: str, data: bytes, filename: str, caption: str
    ) -> bool:
        if not self._ok or not data:
            return False
        url = f"https://api.telegram.org/bot{self.settings.tg_bot_token}/{method}"
        payload: dict[str, str] = {"chat_id": str(self.settings.tg_lead_chat_id)}
        if caption:
            payload["caption"] = caption[:1000]
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, data=payload, files={field: (filename, data)})
                result = r.json()
            if not result.get("ok"):
                logger.warning("TG %s: %s", method, result)
                return False
            return True
        except Exception:
            logger.exception("Не удалось отправить вложение в Telegram (%s)", method)
            return False

    async def send(self, text: str) -> bool:
        if not self._ok or not text:
            return False
        url = f"https://api.telegram.org/bot{self.settings.tg_bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    url,
                    json={
                        "chat_id": self.settings.tg_lead_chat_id,
                        "text": text[:4000],
                    },
                )
                data = r.json()
            if not data.get("ok"):
                logger.warning("TG sendMessage: %s", data)
                return False
            return True
        except Exception:
            logger.exception("Не удалось отправить лид в Telegram")
            return False
