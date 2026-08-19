"""Список объявлений кабинета по Item API. Только чтение."""

from __future__ import annotations

import os
import sys

import httpx

BASE = "https://api.avito.ru"
STATUSES = "active,removed,old,blocked,rejected"


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
        page = 1
        total = 0
        while True:
            resp = http.get(
                f"{BASE}/core/v1/items",
                headers=headers,
                params={"status": STATUSES, "page": page, "per_page": 50},
            )
            print(f"page {page}: HTTP {resp.status_code}")
            if resp.status_code != 200:
                print(resp.text[:500])
                return 1
            data = resp.json() or {}
            items = data.get("resources") or []
            if not items:
                break
            for it in items:
                cat = (it.get("category") or {}).get("name")
                print(
                    f"  {it.get('status'):10} id={it.get('id')} "
                    f"{it.get('title')!r} | {cat} | {it.get('url')}"
                )
                total += 1
            if len(items) < 50:
                break
            page += 1
        print(f"Всего объявлений: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
