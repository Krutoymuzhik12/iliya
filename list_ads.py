"""Уникальные объявления из чатов. Только чтение."""

from __future__ import annotations

import os
import sys

import httpx

BASE = "https://api.avito.ru"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    client_id = os.environ["AVITO_CLIENT_ID"]
    client_secret = os.environ["AVITO_CLIENT_SECRET"]
    with httpx.Client(timeout=30.0) as http:
        token = http.post(
            f"{BASE}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = http.get(f"{BASE}/core/v1/accounts/self", headers=headers).json()
        user_id = me["id"]
        print(f"Профиль: {me.get('name')} id={user_id}")
        chats = (
            http.get(
                f"{BASE}/messenger/v2/accounts/{user_id}/chats",
                headers=headers,
                params={"unread_only": "false", "limit": 50, "chat_types": "u2i"},
            ).json()
            or {}
        ).get("chats") or []
        print(f"Чатов в выборке: {len(chats)}")
        ads: dict[int, dict] = {}
        for chat in chats:
            value = ((chat.get("context") or {}).get("value") or {})
            item_id = value.get("id")
            if not item_id:
                continue
            row = ads.setdefault(
                int(item_id),
                {
                    "title": value.get("title"),
                    "url": value.get("url"),
                    "price": value.get("price_string"),
                    "status_id": value.get("status_id"),
                    "chats": 0,
                },
            )
            row["chats"] += 1
        print(f"Уникальных объявлений: {len(ads)}")
        for item_id, row in sorted(ads.items(), key=lambda x: -x[1]["chats"]):
            print(
                f"  [{row['chats']} чатов] status={row['status_id']} "
                f"{row['price']} | {row['title']}\n    {row['url']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
