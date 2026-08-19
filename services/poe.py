"""Один вынесенный бот на Poe. История — последние HISTORY_LIMIT сообщений."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from config.settings import PROMPTS_DIR, SETTINGS

logger = logging.getLogger(__name__)
_prompt_cache: dict[str, str] = {}

NEED_MANAGER_RE = re.compile(r"\[НУЖЕН_МЕНЕДЖЕР[^\]]*\]", re.I)


def _load_prompt_file(name: str) -> str:
    if name in _prompt_cache:
        return _prompt_cache[name]
    path = PROMPTS_DIR / name
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    facts_file = PROMPTS_DIR / "company_facts.txt"
    facts = facts_file.read_text(encoding="utf-8").strip() if facts_file.exists() else ""
    text = (
        text.replace("{COMPANY_NAME}", SETTINGS.company_name)
        .replace("{MANAGER_NAME}", SETTINGS.manager_name)
        .replace("{COMPANY_FACTS}", facts)
    )
    _prompt_cache[name] = text
    return text


def _maybe_system() -> list[dict[str, str]]:
    """Промпт уже сидит в кастомном боте на Poe. Файл шлём только если явно включили."""
    if not SETTINGS.send_system_prompts:
        return []
    text = _load_prompt_file("manager.txt")
    return [{"role": "system", "content": text}] if text else []


async def poe_chat(
    model: str, messages: list, temperature: float = 0.7, max_tokens: int = 800
) -> str:
    if not SETTINGS.poe_api_key:
        raise RuntimeError("POE_API_KEY не задан в .env")
    headers = {
        "Authorization": f"Bearer {SETTINGS.poe_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            f"{SETTINGS.poe_base_url}/chat/completions", json=payload, headers=headers
        )
        r.raise_for_status()
        data = r.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


def _last_history(history: list[dict]) -> list[dict]:
    limit = max(1, int(SETTINGS.history_limit))
    return history[-limit:]


def _sanitize_reply(raw: str) -> tuple[str, bool]:
    need_manager = bool(NEED_MANAGER_RE.search(raw or ""))
    txt = NEED_MANAGER_RE.sub("", raw or "").strip()
    txt = re.sub(r"\[\[.*?\]\]", "", txt).strip()
    txt = txt.replace("—", "-")
    if "СЛУЖЕБН" not in txt.upper():
        return txt, need_manager
    blocks = re.split(r"\n\s*-{3,}\s*\n|\n\s*\n", txt)
    clean = [b.strip() for b in blocks if b.strip() and "СЛУЖЕБН" not in b.upper()]
    return ("\n\n".join(clean) if clean else txt), need_manager


async def generate_reply(
    history: list[dict],
    user_msg: str,
    *,
    extra_hints: list[str] | None = None,
) -> tuple[str, bool]:
    msgs = _maybe_system()
    for m in _last_history(history):
        msgs.append({"role": m["role"], "content": m["content"]})
    already_started = any(m.get("role") == "assistant" for m in history)
    hints = list(extra_hints or [])
    if already_started:
        hints.append("диалог уже начат - не здоровайся повторно")
    else:
        hints.append("это первое сообщение бота - поздоровайся один раз")
    hints.append("канал Авито, не Telegram")
    content = user_msg
    if hints:
        content = (
            f"{user_msg}\n\n"
            f"(служебное, клиент этого не писал: {'; '.join(hints)}. "
            "Ответь только репликой клиенту. Метку [НУЖЕН_МЕНЕДЖЕР] ставь "
            "только если нужен живой человек, клиент её не увидит.)"
        )
    msgs.append({"role": "user", "content": content})
    raw = await poe_chat(SETTINGS.poe_response_bot, msgs, temperature=0.7, max_tokens=600)
    return _sanitize_reply(raw)
