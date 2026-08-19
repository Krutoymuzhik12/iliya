"""Только чтение: токен, профиль, список чатов. Ничего не отправляет."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

BASE = "https://api.avito.ru"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    client_id = os.getenv("AVITO_CLIENT_ID", "").strip()
    client_secret = os.getenv("AVITO_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print("Нет AVITO_CLIENT_ID / AVITO_CLIENT_SECRET в .env")
        return 1

    print("Запрос токена (только чтение, отправок не будет)...")
    with httpx.Client(timeout=30.0) as http:
        token_resp = http.post(
            f"{BASE}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        payload = token_resp.json() if token_resp.content else {}
        if token_resp.status_code != 200 or "access_token" not in payload:
            print(f"Токен: отказ HTTP {token_resp.status_code}")
            print(
                f"error={payload.get('error')!r} "
                f"description={payload.get('error_description') or payload.get('message') or token_resp.text[:300]!r}"
            )
            return 1

        token = payload["access_token"]
        expires = int(payload.get("expires_in", 0))
        print(f"Токен: ок, живёт ~{expires // 3600} ч")

        headers = {"Authorization": f"Bearer {token}"}
        me = http.get(f"{BASE}/core/v1/accounts/self", headers=headers)
        if me.status_code != 200:
            print(f"Профиль: отказ HTTP {me.status_code}")
            print(me.text[:400])
            return 1

        profile = me.json()
        user_id = profile.get("id")
        print(
            f"Профиль: ок, id={user_id}, "
            f"name={profile.get('name')}, email={profile.get('email')}"
        )

        chats = http.get(
            f"{BASE}/messenger/v2/accounts/{user_id}/chats",
            headers=headers,
            params={"unread_only": "false", "limit": 10, "chat_types": "u2i"},
        )
        if chats.status_code != 200:
            print(f"Чаты: отказ HTTP {chats.status_code}")
            print(chats.text[:400])
            return 1

        items = (chats.json() or {}).get("chats") or []
        print(f"Чаты: ок, пришло {len(items)} (лимит 10, без отправки)")
        for chat in items:
            last = chat.get("last_message") or {}
            content = last.get("content") or {}
            text = (content.get("text") or last.get("text") or "")[:60]
            direction = last.get("direction") or "?"
            unread = chat.get("unread_count")
            ctx = ((chat.get("context") or {}).get("value") or {}).get("title")
            print(
                f"  chat={chat.get('id')} unread={unread} "
                f"item={ctx!r} last={direction}: {text!r}"
            )

        if items:
            sample_id = items[0].get("id")
            msgs = http.get(
                f"{BASE}/messenger/v3/accounts/{user_id}/chats/{sample_id}/messages/",
                headers=headers,
                params={"limit": 3},
            )
            print(f"Сообщения первого чата: HTTP {msgs.status_code}")
            if msgs.status_code != 200:
                print(msgs.text[:400])
            else:
                body = msgs.json() if msgs.content else {}
                rows = body.get("messages") if isinstance(body, dict) else body
                rows = rows or []
                print(f"  пришло {len(rows)} шт. (чтение, без отправки)")
                for m in rows[:3]:
                    content = (m.get("content") or {}) if isinstance(m, dict) else {}
                    text = (content.get("text") or (m.get("text") if isinstance(m, dict) else "") or "")[:80]
                    print(f"  type={m.get('type')} dir={m.get('direction')} text={text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
