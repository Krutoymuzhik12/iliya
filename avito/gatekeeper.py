"""Решает, можно ли боту вести диалог в этом чате Авито.

Бот берёт только чаты, где клиент написал ПЕРВЫМ и до этого в чате
не было исходящих. Старые чаты на первом запуске помечаются existing.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

BOT_OWNED = "new"
NOT_OURS = "existing"
MANUAL = "manual"


def classify_first_contact(messages: list[dict[str, Any]], self_user_id: int) -> str:
    """Первый раз видим чат: наш он или чужой.

    Любое исходящее, которого бот не отправлял, значит диалог уже кто-то ведёт.
    """
    for m in messages:
        if m.get("type") == "system":
            continue
        if int(m.get("author_id") or 0) == self_user_id:
            logger.info(
                "В чате есть исходящее (created=%s), которого бот не слал — не наше",
                m.get("created"),
            )
            return NOT_OURS
    return BOT_OWNED


def bot_owns(dialog: dict[str, Any] | None) -> bool:
    return bool(dialog) and dialog.get("status") == BOT_OWNED
