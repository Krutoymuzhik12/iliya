"""Avito-бот: все объявления аккаунта, только новые пустые чаты, перехват руками."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from avito.api import AvitoApi, attachment_name, attachment_url, message_text, voice_id
from avito.gatekeeper import BOT_OWNED, MANUAL, NOT_OURS, bot_owns, classify_first_contact
from avito.message_batcher import MessageBatcher
from config.settings import SETTINGS, AppSettings
from db.database import Database
from services import transcription
from services.dialog_service import DialogService
from services.leads import booked_from_history, phones_from_history, transcript
from services.quiet_hours import QuietHours
from services.telegram_leads import TelegramLeads

logger = logging.getLogger(__name__)

STOP_CMD_RE = re.compile(r"^\s*#\s*(стоп|stop)\b", re.I)
START_CMD_RE = re.compile(r"^\s*#\s*(старт|start)\b", re.I)

# Вложение, которое бот прочитать не может: он замолкает и отдаёт чат менеджеру.
# Голосовые сюда попадают только если не расшифровались.
NON_TEXT_MARKERS = {
    "voice": "[клиент прислал голосовое сообщение]",
    "image": "[клиент прислал фото]",
    "video": "[клиент прислал видео]",
    "file": "[клиент прислал файл]",
    "link": "[клиент прислал ссылку]",
    "location": "[клиент прислал геолокацию]",
    "item": "[клиент прислал другое объявление]",
    "call": "[клиент звонил по объявлению]",
}
NON_TEXT_DEFAULT = "[клиент прислал вложение без текста]"

# Как называть вложение менеджеру в Telegram.
NON_TEXT_NAMES = {
    "voice": "голосовое сообщение",
    "image": "фото",
    "video": "видео",
    "file": "файл",
    "link": "ссылка",
    "location": "геолокация",
    "item": "другое объявление",
    "call": "звонок по объявлению",
}

# Звонок - не вложение: отвечать на него нечего, но и молчать в чате незачем.
INFO_ONLY_KINDS = {"call"}

# Дожим - единственное место, где входящего нет и в Poe нужен хоть какой-то запрос.
FOLLOWUP_TRIGGER = "Клиент молчит несколько часов. Напомни о себе."


class AvitoBot:
    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or SETTINGS
        self.api = AvitoApi(self.settings.avito_client_id, self.settings.avito_client_secret)
        self.db = Database(path=self.settings.db_path)
        self.dialog = DialogService(self.settings)
        self.quiet = QuietHours(self.settings)
        self.tg = TelegramLeads(self.settings)
        self._chat_locks: dict[str, asyncio.Lock] = {}
        self._user_id: int = 0
        self._started_at: int = int(datetime.now(timezone.utc).timestamp())

        if self.settings.fast_mode:
            batch_wait = min(self.settings.message_batch_wait_sec, 5.0)
            settle = min(self.settings.message_batch_settle_sec, 0.8)
            tail_wait = min(self.settings.message_batch_tail_wait_sec, 2.0)
        else:
            batch_wait = self.settings.message_batch_wait_sec
            settle = self.settings.message_batch_settle_sec
            tail_wait = self.settings.message_batch_tail_wait_sec

        self._batcher = MessageBatcher(
            batch_wait_sec=batch_wait,
            max_wait_sec=self.settings.message_batch_max_wait_sec,
            settle_sec=settle,
            tail_wait_sec=tail_wait,
            on_flush=self._flush_batch,
            log_prefix="[avito]",
        )

    def _chat_lock(self, chat_id: str) -> asyncio.Lock:
        if chat_id not in self._chat_locks:
            self._chat_locks[chat_id] = asyncio.Lock()
        return self._chat_locks[chat_id]

    async def _say(self, chat_id: str, text: str) -> None:
        if not text:
            return
        if not self.settings.poe_ready():
            logger.warning("Avito send пропущен chat=%s: нет POE_API_KEY", chat_id)
            return
        # Хэш до отправки: иначе параллельный поллинг примет своё сообщение за руки менеджера.
        self.db.remember_sent(chat_id, text)
        actual = await self.api.send(self._user_id, chat_id, text)
        if actual != text:
            self.db.remember_sent(chat_id, actual)
        self.db.append_message(chat_id, "assistant", actual)

    async def _live_still_ours(self, chat_id: str) -> bool:
        """Свежая проверка перехвата: менеджер мог написать, пока бот думал."""
        if not bot_owns(self.db.get(chat_id)):
            return False
        messages = await self.api.messages(self._user_id, chat_id, limit=50)
        status = self._apply_owner_messages(chat_id, messages)
        return status == BOT_OWNED

    def _chat_url(self, chat_id: str) -> str:
        try:
            return self.settings.avito_chat_url_template.format(chat_id=chat_id)
        except (KeyError, IndexError):
            logger.warning("Кривой AVITO_CHAT_URL_TEMPLATE, отдаю голый id чата")
            return chat_id

    def _chat_links(self, chat: dict[str, Any]) -> dict[str, str]:
        """Ссылки, которые Авито отдаёт сам: на объявление и на профиль клиента."""
        links: dict[str, str] = {}
        value = (chat.get("context") or {}).get("value") or {}
        if value.get("url"):
            links["item_url"] = str(value["url"])
        for user in chat.get("users") or []:
            if int(user.get("id") or 0) != self._user_id and user.get("url"):
                links["client_url"] = str(user["url"])
        return links

    def _link_lines(self, chat_id: str) -> list[str]:
        state = self.db.state(chat_id)
        lines = [f"Чат: {self._chat_url(chat_id)}"]
        if state.get("item_url"):
            lines.append(f"Объявление на Авито: {state['item_url']}")
        if state.get("client_url"):
            lines.append(f"Профиль клиента: {state['client_url']}")
        return lines

    def _lead_text(self, chat_id: str, phones: list[str], booked: bool) -> str:
        dialog = self.db.get(chat_id) or {}
        why = []
        if phones:
            why.append("телефон")
        if booked:
            why.append("запись на замер")
        lines = [
            "Новый лид Avito",
            f"Причина: {', '.join(why) or 'контакт'}",
            f"Профиль Авито: {dialog.get('client_name') or '—'}",
            f"Телефон: {', '.join(phones) or 'не оставил'}",
            f"Объявление: {dialog.get('item_title') or '—'}",
            *self._link_lines(chat_id),
        ]
        notes = transcript(self.db.history(chat_id))
        if notes:
            lines.extend(["", "Конспект:", notes])
        return "\n".join(lines)[:4000]

    def _attachment_text(
        self, chat_id: str, kinds: dict[str, int], stopped: bool, replying: bool = False
    ) -> str:
        dialog = self.db.get(chat_id) or {}
        what = ", ".join(
            NON_TEXT_NAMES.get(kind, kind or "вложение") + (f" x{count}" if count > 1 else "")
            for kind, count in kinds.items()
        )
        head = (
            "Клиент прислал то, что бот не понимает — бот замолчал, чат на вас"
            if stopped
            else "Событие в чате, бот продолжает работать"
        )
        lines = [
            head,
            f"Что: {what}",
            f"Профиль Авито: {dialog.get('client_name') or '—'}",
            f"Объявление: {dialog.get('item_title') or '—'}",
            *self._link_lines(chat_id),
        ]
        notes = transcript(self.db.history(chat_id))
        if notes:
            lines.extend(["", "Конспект:", notes])
        if replying:
            lines.extend(
                [
                    "",
                    "Клиенту уходит ответ, что уточним и вернёмся. Дальше отвечайте вы.",
                    "Вернуть бота в чат — «#старт».",
                ]
            )
        elif stopped:
            lines.extend(["", "Бот в этом чате и так молчал. Ответьте клиенту в Авито."])
        return "\n".join(lines)[:4000]

    async def _handoff_attachment(
        self, chat_id: str, messages: list[dict], texts: list[str] | None = None
    ) -> None:
        """Клиенту - «уточню и вернусь», чат менеджеру, бот замолкает."""
        kinds: dict[str, int] = {}
        markers: list[str] = []
        for m in messages:
            kind = str(m.get("type") or "")
            kinds[kind] = kinds.get(kind, 0) + 1
            marker = NON_TEXT_MARKERS.get(kind, NON_TEXT_DEFAULT)
            # Пять фото подряд - одна пометка, а не пять одинаковых строк.
            if marker not in markers:
                markers.append(marker)
        for text in texts or []:
            self.db.append_message(chat_id, "user", text)
        for marker in markers:
            self.db.append_message(chat_id, "user", marker)

        stopped = not kinds.keys() <= INFO_ONLY_KINDS
        replying = stopped and (self.db.get(chat_id) or {}).get("status") == BOT_OWNED
        sent = await self.tg.send(self._attachment_text(chat_id, kinds, stopped, replying))
        logger.info(
            "Вложение chat=%s %s, менеджеру в TG: %s", chat_id, kinds, "ушло" if sent else "не ушло"
        )
        for m in messages:
            await self._forward_attachment(chat_id, m)

        if replying:
            await self._batcher.drop(chat_id)
            try:
                await self._say_and_step_aside(chat_id, markers)
            finally:
                self.db.set_status(chat_id, MANUAL)
                logger.info("Чат %s: вложение %s — бот замолчал, чат менеджеру", chat_id, kinds)
        await self._maybe_send_lead(chat_id)

    async def _say_and_step_aside(self, chat_id: str, markers: list[str]) -> None:
        """Текст «уточню у коллег» пишет Poe: своих реплик код клиенту не шлёт."""
        if not markers:
            return
        dialog = self.db.get(chat_id) or {}
        history = self.db.history(chat_id)
        try:
            reply, _ = await self.dialog.build_reply(
                history[: -len(markers)], "\n".join(markers), context=self._context(dialog)
            )
        except Exception:
            logger.exception("Poe не ответил на вложение chat=%s - клиент без ответа", chat_id)
            return
        if reply:
            await self._say(chat_id, reply)

    async def _forward_attachment(self, chat_id: str, message: dict) -> None:
        """Само вложение — в группу, чтобы менеджер не лазил в Авито."""
        kind = str(message.get("type") or "")
        if kind in INFO_ONLY_KINDS:
            return
        url = await self._voice_url(message) if kind == "voice" else attachment_url(message)
        if not url:
            return
        what = NON_TEXT_NAMES.get(kind, "вложение").capitalize()
        caption = f"{what} от клиента\n{self._chat_url(chat_id)}"
        data = await self.api.download(url)
        if not data:
            # Ссылки Авито бывают короткоживущие — отдаём хотя бы её.
            await self.tg.send(f"{caption}\nСкачать не вышло, ссылка: {url}")
            return
        name = attachment_name(message)
        if kind == "image":
            await self.tg.send_photo(data, filename=name or "photo.jpg", caption=caption)
        elif kind == "voice":
            suffix = ".mp4" if ".mp4" in url.lower() else ".mp3"
            await self.tg.send_audio(data, filename=name or f"voice{suffix}", caption=caption)
        else:
            await self.tg.send_document(data, filename=name or "attachment.bin", caption=caption)

    async def _maybe_send_lead(self, chat_id: str) -> None:
        if self.db.state(chat_id).get("lead_sent"):
            return
        history = self.db.history(chat_id)
        phones = phones_from_history(history)
        booked = booked_from_history(history)
        if not phones and not booked:
            return
        sent = await self.tg.send(self._lead_text(chat_id, phones, booked))
        if sent:
            self.db.set_state(chat_id, lead_sent=True)
            logger.info("Лид ушёл в Telegram chat=%s phones=%s booked=%s", chat_id, phones, booked)

    @staticmethod
    def _context(dialog: dict[str, Any]) -> list[str]:
        """Только факты о чате. Инструкций, как отвечать, из кода не даём."""
        if dialog.get("item_title"):
            return [f"клиент пишет по объявлению «{dialog['item_title']}»"]
        return []

    async def _flush_batch(self, chat_id: str, combined_text: str) -> None:
        async with self._chat_lock(chat_id):
            dialog = self.db.get(chat_id)
            if not bot_owns(dialog):
                logger.info("flush пропущен chat=%s — чат не ведёт бот", chat_id)
                return
            self.db.append_message(chat_id, "user", combined_text)
            history = self.db.history(chat_id)[:-1]
            context = self._context(dialog)
        await self.dialog.delay_reply()
        if not await self._live_still_ours(chat_id):
            logger.info("flush отменён chat=%s — чат перехватили до генерации", chat_id)
            await self._maybe_send_lead(chat_id)
            return
        reply, classification = await self.dialog.build_reply(
            history, combined_text, context=context
        )
        async with self._chat_lock(chat_id):
            if not await self._live_still_ours(chat_id):
                logger.info("flush отменён chat=%s — чат перехватили до отправки", chat_id)
                await self._maybe_send_lead(chat_id)
                return
            await self._say(chat_id, reply)
            if (classification or {}).get("need_manager"):
                self.db.set_status(chat_id, MANUAL)
                logger.info("Чат %s: [НУЖЕН_МЕНЕДЖЕР] - бот замолкает", chat_id)
            await self._maybe_send_lead(chat_id)
            logger.info("flush done chat=%s", chat_id)

    @staticmethod
    def _chat_item(chat: dict[str, Any]) -> tuple[str | None, int | None]:
        context = chat.get("context") or {}
        value = context.get("value") or {}
        if context.get("type") != "item":
            return None, None
        item_id = value.get("id")
        return value.get("title"), int(item_id) if item_id else None

    def _client(self, chat: dict[str, Any]) -> tuple[int | None, str | None]:
        for user in chat.get("users") or []:
            uid = int(user.get("id") or 0)
            if uid and uid != self._user_id:
                return uid, (user.get("name") or None)
        return None, None

    def _chat_needs_fetch(self, chat: dict[str, Any], dialog: dict[str, Any] | None) -> bool:
        if dialog is None:
            return True
        if dialog["status"] == NOT_OURS:
            return False
        last = chat.get("last_message") or {}
        last_created = int(last.get("created") or 0)
        if not last_created:
            return True
        if int(last.get("author_id") or 0) == self._user_id:
            last_owner_ts = int(self.db.state(str(chat.get("id"))).get("last_owner_ts") or 0)
            return last_created > last_owner_ts
        if last.get("type") == "system":
            return False
        return last_created > int(dialog.get("last_msg_ts") or 0)

    def _incoming(self, messages: list[dict], after_ts: int = 0) -> list[dict]:
        result = [
            m
            for m in messages
            if int(m.get("author_id") or 0) != self._user_id
            and m.get("type") != "system"
            and int(m.get("created") or 0) > after_ts
        ]
        result.sort(key=lambda m: int(m.get("created") or 0))
        return result

    def _register_new_chat(self, chat: dict[str, Any], messages: list[dict]) -> dict[str, Any]:
        chat_id = str(chat.get("id"))
        client_id, client_name = self._client(chat)
        title, item_id = self._chat_item(chat)
        incoming = self._incoming(messages)
        older = [
            m
            for m in messages
            if m.get("type") != "system" and int(m.get("created") or 0) < self._started_at
        ]
        if not incoming:
            status = NOT_OURS
        elif older:
            status = NOT_OURS
            logger.info("Чат %s: в истории есть сообщения до старта бота — не берём", chat_id)
        else:
            status = classify_first_contact(messages, self._user_id)
        dialog = self.db.create(
            chat_id=chat_id,
            status=status,
            client_user_id=client_id,
            client_name=client_name,
            item_title=title,
            item_id=item_id,
        )
        if status == NOT_OURS:
            last_ts = max((int(m.get("created") or 0) for m in messages), default=0)
            dialog = self.db.update(chat_id, last_msg_ts=last_ts) or dialog
            logger.info("Чат %s: не новичок — бот молчит", chat_id)
        else:
            logger.info(
                "Чат %s: пустой чат, клиент написал первым (объявление %s) — бот берёт",
                chat_id,
                title or item_id or "без названия",
            )
        return dialog

    def _remember_links(self, chat_id: str, chat: dict[str, Any]) -> None:
        state = self.db.state(chat_id)
        patch = {k: v for k, v in self._chat_links(chat).items() if state.get(k) != v}
        if patch:
            self.db.set_state(chat_id, **patch)

    def _apply_owner_messages(self, chat_id: str, messages: list[dict]) -> str:
        state = self.db.state(chat_id)
        last_seen = int(state.get("last_owner_ts") or 0)
        newest = last_seen
        for m in sorted(messages, key=lambda x: int(x.get("created") or 0)):
            if int(m.get("author_id") or 0) != self._user_id:
                continue
            created = int(m.get("created") or 0)
            if created <= last_seen:
                continue
            newest = max(newest, created)
            text = message_text(m)
            if not text:
                continue
            if STOP_CMD_RE.match(text):
                self.db.set_status(chat_id, MANUAL)
                logger.info("Чат %s: #стоп — бот отключён", chat_id)
            elif START_CMD_RE.match(text):
                if (self.db.get(chat_id) or {}).get("status") != NOT_OURS:
                    self.db.set_status(chat_id, BOT_OWNED)
                    logger.info("Чат %s: #старт — бот снова ведёт", chat_id)
            elif not self.db.was_sent_by_bot(chat_id, text):
                if (self.db.get(chat_id) or {}).get("status") == BOT_OWNED:
                    self.db.set_status(chat_id, MANUAL)
                    logger.info(
                        "Чат %s: менеджер написал руками (%r) — бот замолкает",
                        chat_id,
                        text[:50],
                    )
        if newest > last_seen:
            self.db.set_state(chat_id, last_owner_ts=newest)
        return (self.db.get(chat_id) or {}).get("status", NOT_OURS)

    async def _process_chat(self, chat: dict[str, Any]) -> None:
        chat_id = str(chat.get("id"))
        dialog = self.db.get(chat_id)
        if not self._chat_needs_fetch(chat, dialog):
            return

        async with self._chat_lock(chat_id):
            await self._process_chat_locked(chat, chat_id)

    async def _process_chat_locked(self, chat: dict[str, Any], chat_id: str) -> None:
        dialog = self.db.get(chat_id)
        if not self._chat_needs_fetch(chat, dialog):
            return
        fetch_limit = 100 if dialog is None else max(50, self.settings.history_limit)
        messages = await self.api.messages(self._user_id, chat_id, limit=fetch_limit)
        if dialog is None:
            dialog = self._register_new_chat(chat, messages)
        else:
            client_id, client_name = self._client(chat)
            title, item_id = self._chat_item(chat)
            dialog = (
                self.db.touch_profile(
                    chat_id,
                    client_user_id=client_id,
                    client_name=client_name,
                    item_title=title,
                    item_id=item_id,
                )
                or dialog
            )

        if dialog["status"] == NOT_OURS:
            return

        self._remember_links(chat_id, chat)
        status = self._apply_owner_messages(chat_id, messages)
        if status != BOT_OWNED:
            incoming = self._incoming(messages, int(dialog.get("last_msg_ts") or 0))
            if incoming:
                self.db.update(
                    chat_id,
                    last_msg_ts=max(int(m.get("created") or 0) for m in incoming),
                )
            return

        incoming = self._incoming(messages, int(dialog.get("last_msg_ts") or 0))
        if not incoming:
            return

        await self.api.mark_read(self._user_id, chat_id)
        self.db.update(
            chat_id, last_msg_ts=max(int(m.get("created") or 0) for m in incoming)
        )

        parts: list[str] = []
        attachments: list[dict] = []
        for m in incoming:
            text = message_text(m)
            if text:
                parts.append(text)
                continue
            if str(m.get("type") or "") == "voice":
                recognized = await self._transcribe_voice(m)
                if recognized:
                    logger.info("Голосовое chat=%s → %r", chat_id, recognized[:80])
                    # Расшифровка идёт в Poe как обычная реплика клиента:
                    # переспрашивать «правильно ли я понял» бот не должен.
                    parts.append(recognized)
                    continue
            attachments.append(m)

        if attachments:
            unreadable = any(
                str(m.get("type") or "") not in INFO_ONLY_KINDS for m in attachments
            )
            # Текст, пришедший вместе с вложением, в Poe не уходит - только в историю,
            # чтобы менеджер увидел его в конспекте.
            await self._handoff_attachment(chat_id, attachments, parts if unreadable else [])
            if unreadable:
                return
        for part in parts:
            await self._batcher.enqueue(chat_id, part)

    async def _voice_url(self, message: dict) -> str | None:
        vid = voice_id(message)
        if not vid:
            return None
        try:
            urls = await self.api.voice_files(self._user_id, [vid])
        except Exception as e:
            logger.warning("Не получить ссылку на голосовое: %s", e)
            return None
        return urls.get(vid) or (next(iter(urls.values())) if urls else None)

    async def _transcribe_voice(self, message: dict) -> str | None:
        url = await self._voice_url(message)
        if not url:
            return None
        data = await self.api.download(url)
        if not data:
            return None
        suffix = ".mp4" if ".mp4" in url.lower() else ".mp3"
        text = await transcription.transcribe_bytes(data, suffix=suffix)
        return None if transcription.failed(text) else text

    async def _baseline_existing_chats(self) -> None:
        chats = await self.api.chats(self._user_id, unread_only=False, limit=100)
        marked = 0
        ads: dict[int, str] = {}
        for chat in chats:
            chat_id = str(chat.get("id"))
            title, item_id = self._chat_item(chat)
            if item_id:
                ads[item_id] = title or str(item_id)
            if self.db.get(chat_id):
                continue
            client_id, client_name = self._client(chat)
            self.db.create(
                chat_id=chat_id,
                status=NOT_OURS,
                client_user_id=client_id,
                client_name=client_name,
                item_title=title,
                item_id=item_id,
            )
            self.db.update(
                chat_id,
                last_msg_ts=int((chat.get("last_message") or {}).get("created") or 0),
            )
            marked += 1
        if ads:
            logger.info(
                "Смотрим все объявления аккаунта (%s), без фильтра на одно: %s",
                len(ads),
                "; ".join(f"{iid} «{name}»" for iid, name in list(ads.items())[:12]),
            )
        if marked:
            logger.info(
                "Baseline: %s чатов уже были — бот в них не пишет. "
                "Только новые пустые чаты после старта",
                marked,
            )

    async def run_followup_loop(self) -> None:
        if not self.settings.followup_enabled:
            return
        while True:
            await asyncio.sleep(self.settings.followup_poll_sec)
            try:
                await self._check_followups()
            except Exception:
                logger.exception("Ошибка дожима")

    async def _check_followups(self) -> None:
        if not self.quiet.can_push():
            return
        now = datetime.now(timezone.utc)
        delay = self.settings.followup_delay_sec
        if self.settings.fast_mode:
            delay = min(delay, 120)
        for row in self.db.candidates_for_followup():
            chat_id = row["chat_id"]
            history = self.db.history(chat_id)
            if not history or history[-1].get("role") != "assistant":
                continue
            if phones_from_history(history):
                # Номер уже есть, дальше работает менеджер - дожимать нечего.
                self.db.record_followup_sent(chat_id, 1)
                logger.info("Дожим закрыт chat=%s - клиент оставил номер", chat_id)
                continue
            last = row.get("last_user_msg_at")
            if not last:
                continue
            try:
                last_dt = datetime.fromisoformat(last)
            except ValueError:
                continue
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if (now - last_dt).total_seconds() < delay:
                continue
            dialog = self.db.get(chat_id)
            if not bot_owns(dialog):
                continue
            # Клиент молчит, входящего нет. Что писать - решает бот на Poe по истории.
            reply, classification = await self.dialog.build_reply(
                history, FOLLOWUP_TRIGGER, context=self._context(dialog or {})
            )
            async with self._chat_lock(chat_id):
                if not await self._live_still_ours(chat_id):
                    continue
                await self._say(chat_id, reply)
                if (classification or {}).get("need_manager"):
                    self.db.set_status(chat_id, MANUAL)
                    logger.info("Чат %s: [НУЖЕН_МЕНЕДЖЕР] на дожиме - бот замолкает", chat_id)
                self.db.record_followup_sent(chat_id, 1)
            await self._maybe_send_lead(chat_id)
            logger.info("Дожим отправлен chat=%s", chat_id)

    async def run(self) -> None:
        if not self.settings.avito_ready():
            raise RuntimeError("Нет AVITO_CLIENT_ID / AVITO_CLIENT_SECRET")
        self._user_id = self.settings.avito_user_id or await self.api.self_id()
        logger.info("Бот запущен: Avito id=%s, все объявления аккаунта, без фильтра", self._user_id)
        await self._baseline_existing_chats()
        if self.settings.poe_ready():
            logger.info("Poe: %s", self.settings.poe_response_bot)
        else:
            logger.warning("POE_API_KEY не задан — бот не сможет генерировать ответы")
        try:
            await asyncio.to_thread(transcription.warm_local_model)
        except Exception as e:
            logger.warning("Прогрев Whisper не удался: %s", e)
        await self.tg.start()
        asyncio.create_task(self.run_followup_loop())
        while True:
            try:
                chats = await self.api.chats(self._user_id, unread_only=False, limit=100)
                results = await asyncio.gather(
                    *(self._process_chat(c) for c in chats), return_exceptions=True
                )
                for chat, res in zip(chats, results):
                    if isinstance(res, Exception):
                        logger.exception("Чат %s", chat.get("id"), exc_info=res)
            except Exception:
                logger.exception("Поллинг упал, пауза 15 сек")
                await asyncio.sleep(15)
                continue
            await asyncio.sleep(self.settings.poll_interval_sec)
