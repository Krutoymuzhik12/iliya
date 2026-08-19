"""Клиент Avito Messenger API. Поллинг, без вебхука."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE = "https://api.avito.ru"
MAX_MESSAGE_LEN = 1900


class AvitoApiError(RuntimeError):
    def __init__(self, path: str, status: int, body: str):
        self.status = status
        super().__init__(f"Avito {path} HTTP {status}: {body[:300]}")


class AvitoApi:
    def __init__(self, client_id: str, client_secret: str):
        if not client_id or not client_secret:
            raise RuntimeError("Задайте AVITO_CLIENT_ID и AVITO_CLIENT_SECRET в .env")
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = httpx.AsyncClient(timeout=60.0)
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def close(self) -> None:
        await self._http.aclose()

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        resp = await self._http.post(
            f"{BASE}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        if resp.status_code != 200:
            raise AvitoApiError("/token", resp.status_code, resp.text)
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.monotonic() + int(data.get("expires_in", 86400)) - 600
        logger.info("Avito: получен новый access_token")
        return self._token

    async def call(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
    ) -> Any:
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._http.request(
            method, BASE + path, params=params, json=json_body, headers=headers
        )
        if resp.status_code == 401:
            self._token = None
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"}
            resp = await self._http.request(
                method, BASE + path, params=params, json=json_body, headers=headers
            )
        if resp.status_code >= 400:
            raise AvitoApiError(path, resp.status_code, resp.text)
        if not resp.content:
            return None
        return resp.json()

    async def self_id(self) -> int:
        data = await self.call("GET", "/core/v1/accounts/self")
        return int(data["id"])

    async def chats(
        self, user_id: int, *, unread_only: bool = False, limit: int = 50
    ) -> list[dict]:
        data = await self.call(
            "GET",
            f"/messenger/v2/accounts/{user_id}/chats",
            params={
                "unread_only": str(unread_only).lower(),
                "limit": limit,
                "chat_types": "u2i",
            },
        )
        return (data or {}).get("chats") or []

    async def messages(self, user_id: int, chat_id: str, *, limit: int = 50) -> list[dict]:
        data = await self.call(
            "GET",
            f"/messenger/v3/accounts/{user_id}/chats/{chat_id}/messages/",
            params={"limit": limit},
        )
        if isinstance(data, dict):
            return data.get("messages") or []
        return data or []

    async def send(self, user_id: int, chat_id: str, text: str) -> str:
        if len(text) > MAX_MESSAGE_LEN:
            text = text[:MAX_MESSAGE_LEN] + "…"
        await self.call(
            "POST",
            f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages",
            json_body={"message": {"text": text}, "type": "text"},
        )
        return text

    async def mark_read(self, user_id: int, chat_id: str) -> None:
        try:
            await self.call("POST", f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/read")
        except Exception:
            logger.warning("Не удалось пометить чат прочитанным chat=%s", chat_id)

    async def voice_files(self, user_id: int, voice_ids: list[str]) -> dict[str, str]:
        if not voice_ids:
            return {}
        data = await self.call(
            "GET",
            f"/messenger/v1/accounts/{user_id}/getVoiceFiles",
            params={"voice_ids": ",".join(voice_ids)},
        )
        return (data or {}).get("voices_urls") or {}


def message_text(message: dict) -> str:
    return ((message.get("content") or {}).get("text") or "").strip()
