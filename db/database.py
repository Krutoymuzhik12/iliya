"""SQLite: статусы чатов, история (последние HISTORY_LIMIT), свои исходящие."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from config.settings import DB_PATH, SETTINGS

HISTORY_LIMIT = SETTINGS.history_limit
SENT_HASHES_LIMIT = 60

DEFAULT_STATE: dict[str, Any] = {
    "sent_hashes": [],
    "last_owner_ts": 0,
    "thinking": False,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(text: str) -> str:
    return hashlib.md5(" ".join((text or "").split()).encode("utf-8")).hexdigest()[:16]


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS dialogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL UNIQUE,
                    client_user_id INTEGER,
                    client_name TEXT,
                    item_title TEXT,
                    item_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'new',
                    history TEXT NOT NULL,
                    state TEXT NOT NULL,
                    last_msg_ts INTEGER NOT NULL DEFAULT 0,
                    last_user_msg_at TEXT,
                    followup_stage INTEGER NOT NULL DEFAULT 0,
                    followup_last_sent_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_dialogs_status ON dialogs(status);
                """
            )

    def get(self, chat_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM dialogs WHERE chat_id=?", (chat_id,)).fetchone()
        return dict(row) if row else None

    def create(
        self,
        *,
        chat_id: str,
        status: str = "new",
        client_user_id: int | None = None,
        client_name: str | None = None,
        item_title: str | None = None,
        item_id: int | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO dialogs (
                    chat_id, status, client_user_id, client_name, item_title, item_id,
                    history, state, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    chat_id,
                    status,
                    client_user_id,
                    client_name,
                    item_title,
                    item_id,
                    json.dumps([], ensure_ascii=False),
                    json.dumps(DEFAULT_STATE, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get(chat_id)  # type: ignore[return-value]

    def touch_profile(self, chat_id: str, **fields) -> dict[str, Any] | None:
        dialog = self.get(chat_id)
        if not dialog:
            return None
        patch = {}
        for key in ("item_title", "item_id", "client_name", "client_user_id"):
            val = fields.get(key)
            if val and dialog.get(key) != val:
                patch[key] = val
        return self.update(chat_id, **patch) if patch else dialog

    def update(self, chat_id: str, **fields) -> dict[str, Any] | None:
        if not fields:
            return self.get(chat_id)
        fields["updated_at"] = _utc_now()
        cols = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [chat_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE dialogs SET {cols} WHERE chat_id=?", values)
        return self.get(chat_id)

    def set_status(self, chat_id: str, status: str) -> dict[str, Any] | None:
        return self.update(chat_id, status=status)

    def history(self, chat_id: str) -> list[dict[str, str]]:
        dialog = self.get(chat_id)
        if not dialog:
            return []
        try:
            return json.loads(dialog["history"])
        except json.JSONDecodeError:
            return []

    def append_message(self, chat_id: str, role: str, content: str) -> None:
        history = self.history(chat_id)
        history.append({"role": role, "content": content})
        patch: dict[str, Any] = {
            "history": json.dumps(history[-HISTORY_LIMIT:], ensure_ascii=False)
        }
        if role == "user":
            patch["last_user_msg_at"] = _utc_now()
            patch["followup_stage"] = 0
        self.update(chat_id, **patch)

    def state(self, chat_id: str) -> dict[str, Any]:
        dialog = self.get(chat_id)
        if not dialog:
            return dict(DEFAULT_STATE)
        try:
            data = json.loads(dialog["state"])
        except json.JSONDecodeError:
            data = {}
        return {**DEFAULT_STATE, **data}

    def set_state(self, chat_id: str, **patch) -> dict[str, Any]:
        state = {**self.state(chat_id), **patch}
        self.update(chat_id, state=json.dumps(state, ensure_ascii=False))
        return state

    def remember_sent(self, chat_id: str, text: str) -> None:
        hashes = list(self.state(chat_id).get("sent_hashes") or [])
        hashes.append(_hash(text))
        self.set_state(chat_id, sent_hashes=hashes[-SENT_HASHES_LIMIT:])

    def was_sent_by_bot(self, chat_id: str, text: str) -> bool:
        return _hash(text) in set(self.state(chat_id).get("sent_hashes") or [])

    def candidates_for_followup(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM dialogs
                WHERE status='new' AND followup_stage = 0
                  AND last_user_msg_at IS NOT NULL
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def record_followup_sent(self, chat_id: str, stage: int = 1) -> None:
        self.update(chat_id, followup_stage=stage, followup_last_sent_at=_utc_now())
