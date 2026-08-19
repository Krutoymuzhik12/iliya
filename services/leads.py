"""Телефон в тексте клиента и запись на замер."""

from __future__ import annotations

import re

PHONE_RE = re.compile(r"(?<!\d)(\+?7|8)?[\s\-(]*(\d{3})[\s\-)]*(\d{3})[\s\-]*(\d{2})[\s\-]*(\d{2})(?!\d)")
BOOK_RE = re.compile(
    r"(запис\w*.{0,25}замер|на замер.{0,25}запис|"
    r"давайте на замер|запишите.{0,15}замер|"
    r"замер.{0,20}(завтра|сегодня|послезавтра)|"
    r"(завтра|сегодня|послезавтра).{0,20}замер)",
    re.I | re.S,
)


def normalize_phone(raw: str) -> str | None:
    if not raw:
        return None
    for match in PHONE_RE.finditer(raw):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) == 11 and digits[0] in "78":
            return "+7" + digits[1:]
        if len(digits) == 10 and digits[0] == "9":
            return "+7" + digits
    return None


def phones_from_history(history: list[dict]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in history:
        if m.get("role") != "user":
            continue
        phone = normalize_phone(m.get("content") or "")
        if phone and phone not in seen:
            seen.add(phone)
            found.append(phone)
    return found


def is_measurement_booking(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or "?" in raw:
        return False
    if re.search(r"сколько|почём|почем|бесплатн", raw, re.I):
        return False
    return bool(BOOK_RE.search(raw))


def booked_from_history(history: list[dict]) -> bool:
    return any(
        is_measurement_booking(m.get("content") or "")
        for m in history
        if m.get("role") == "user"
    )


def transcript(history: list[dict], *, limit: int = 12, line_max: int = 180) -> str:
    lines = []
    for m in history[-limit:]:
        who = "Клиент" if m.get("role") == "user" else "Менеджер"
        text = re.sub(r"\s+", " ", (m.get("content") or "")).strip()
        if len(text) > line_max:
            text = text[: line_max - 1] + "…"
        if text:
            lines.append(f"{who}: {text}")
    return "\n".join(lines)
