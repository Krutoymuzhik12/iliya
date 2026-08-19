from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

DATA_DIR = BASE_DIR / "data"
PROMPTS_DIR = BASE_DIR / "prompts"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class AppSettings:
    avito_client_id: str
    avito_client_secret: str
    avito_user_id: int
    poll_interval_sec: float
    poe_api_key: str
    poe_base_url: str
    poe_response_bot: str
    send_system_prompts: bool
    history_limit: int
    fast_mode: bool
    reply_delay_min_sec: float
    reply_delay_max_sec: float
    message_batch_wait_sec: float
    message_batch_settle_sec: float
    message_batch_tail_wait_sec: float
    message_batch_max_wait_sec: float
    company_name: str
    manager_name: str
    timezone: str
    push_hour_start: int
    push_hour_end: int
    followup_enabled: bool
    followup_delay_sec: float
    followup_poll_sec: float
    tg_bot_token: str
    tg_lead_chat_id: int
    db_path: Path
    log_path: Path

    @classmethod
    def load(cls) -> "AppSettings":
        return cls(
            avito_client_id=os.getenv("AVITO_CLIENT_ID", "").strip(),
            avito_client_secret=os.getenv("AVITO_CLIENT_SECRET", "").strip(),
            avito_user_id=int(os.getenv("AVITO_USER_ID", "0") or 0),
            poll_interval_sec=float(os.getenv("POLL_INTERVAL_SEC", "8")),
            poe_api_key=os.getenv("POE_API_KEY", "").strip(),
            poe_base_url=os.getenv("POE_BASE_URL", "https://api.poe.com/v1").rstrip("/"),
            poe_response_bot=os.getenv("POE_RESPONSE_BOT", "IlyaDemoBal-Manager").strip(),
            send_system_prompts=_bool_env("SEND_SYSTEM_PROMPTS", "false"),
            history_limit=int(os.getenv("HISTORY_LIMIT", "40")),
            fast_mode=_bool_env("FAST_MODE"),
            reply_delay_min_sec=float(os.getenv("REPLY_DELAY_MIN_SEC", "5")),
            reply_delay_max_sec=float(os.getenv("REPLY_DELAY_MAX_SEC", "8")),
            message_batch_wait_sec=float(os.getenv("MESSAGE_BATCH_WAIT_SEC", "8")),
            message_batch_settle_sec=float(os.getenv("MESSAGE_BATCH_SETTLE_SEC", "1.0")),
            message_batch_tail_wait_sec=float(os.getenv("MESSAGE_BATCH_TAIL_WAIT_SEC", "4")),
            message_batch_max_wait_sec=float(os.getenv("MESSAGE_BATCH_MAX_WAIT_SEC", "25")),
            company_name=os.getenv("COMPANY_NAME", "Центр-Балкон").strip(),
            manager_name=os.getenv("MANAGER_NAME", "Алексей").strip(),
            timezone=os.getenv("TIMEZONE", "Europe/Moscow").strip(),
            push_hour_start=int(os.getenv("PUSH_HOUR_START", "9")),
            push_hour_end=int(os.getenv("PUSH_HOUR_END", "18")),
            followup_enabled=_bool_env("FOLLOWUP_ENABLED", "true"),
            followup_delay_sec=float(os.getenv("FOLLOWUP_DELAY_SEC", "14400")),
            followup_poll_sec=float(os.getenv("FOLLOWUP_POLL_SEC", "300")),
            tg_bot_token=os.getenv("TG_BOT_TOKEN", "").strip(),
            tg_lead_chat_id=int(os.getenv("TG_LEAD_CHAT_ID", "0") or 0),
            db_path=DATA_DIR / "dialogs.db",
            log_path=DATA_DIR / "bot.log",
        )

    def avito_ready(self) -> bool:
        return bool(self.avito_client_id and self.avito_client_secret)

    def poe_ready(self) -> bool:
        return bool(self.poe_api_key and self.poe_response_bot)

    def tg_ready(self) -> bool:
        return bool(self.tg_bot_token and self.tg_lead_chat_id)


SETTINGS = AppSettings.load()
DB_PATH = SETTINGS.db_path
