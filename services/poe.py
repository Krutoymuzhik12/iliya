"""Poe: классификатор и менеджер. В промпт уходит история (до HISTORY_LIMIT)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from config.settings import PROMPTS_DIR, SETTINGS

logger = logging.getLogger(__name__)
_prompt_cache: dict[str, str] = {}


def _read_prompt(name: str) -> str:
    if not SETTINGS.send_system_prompts:
        return ""
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


def _maybe_system(prompt_file: str) -> list[dict[str, str]]:
    text = _read_prompt(prompt_file)
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


def _parse_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    txt = raw.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt).strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                return None
    return None


def _transcript(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        who = "Клиент" if m["role"] == "user" else "Менеджер"
        lines.append(f"{who}: {m['content']}")
    return "\n".join(lines)


def _last_history(history: list[dict]) -> list[dict]:
    limit = max(1, int(SETTINGS.history_limit))
    return history[-limit:]


async def classify(history: list[dict], user_msg: str) -> dict[str, Any] | None:
    history = _last_history(history)
    last_assistant = next(
        (m["content"] for m in reversed(history) if m["role"] == "assistant"), ""
    )
    msgs = _maybe_system("classifier.txt")
    msgs.append(
        {
            "role": "user",
            "content": (
                f"ИСТОРИЯ ДИАЛОГА (последние {len(history)} сообщений, лимит {SETTINGS.history_limit}):\n"
                f"{_transcript(history) or '(пусто)'}\n\n"
                f"ПОСЛЕДНЯЯ РЕПЛИКА МЕНЕДЖЕРА: {last_assistant or '(ещё не было)'}\n\n"
                f"СООБЩЕНИЕ КЛИЕНТА:\n{user_msg}\n\n"
                "Верни строго JSON."
            ),
        }
    )
    raw = await poe_chat(SETTINGS.poe_classifier_bot, msgs, temperature=0.0, max_tokens=400)
    result = _parse_json(raw)
    if result is None:
        return None
    try:
        result["confidence"] = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    return result


def _sanitize_reply(raw: str) -> str:
    txt = (raw or "").strip()
    txt = re.sub(r"\[\[.*?\]\]", "", txt).strip()
    if "СЛУЖЕБН" not in txt.upper():
        return txt
    blocks = re.split(r"\n\s*-{3,}\s*\n|\n\s*\n", txt)
    clean = [b.strip() for b in blocks if b.strip() and "СЛУЖЕБН" not in b.upper()]
    return "\n\n".join(clean) if clean else txt


async def generate_reply(
    history: list[dict],
    user_msg: str,
    *,
    extra_hints: list[str] | None = None,
    classification: dict[str, Any] | None = None,
) -> str:
    msgs = _maybe_system("manager.txt")
    for m in _last_history(history):
        msgs.append({"role": m["role"], "content": m["content"]})
    already_started = any(m.get("role") == "assistant" for m in history)
    hints = list(extra_hints or [])
    if classification:
        hints.append(f"intent={classification.get('intent')}")
    if already_started:
        hints.append("диалог уже начат — не здоровайся повторно")
    else:
        hints.append("это первое сообщение бота — поздоровайся один раз")
    content = user_msg
    if hints:
        content = (
            f"{user_msg}\n\n"
            f"(служебное, клиент этого не писал: {'; '.join(hints)}. "
            "Ответь только репликой клиенту.)"
        )
    msgs.append({"role": "user", "content": content})
    raw = await poe_chat(SETTINGS.poe_response_bot, msgs, temperature=0.7, max_tokens=600)
    return _sanitize_reply(raw)
