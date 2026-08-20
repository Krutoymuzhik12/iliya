"""Склейка сообщений клиента в один запрос."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

FlushHandler = Callable[[str, str], Awaitable[None]]


@dataclass
class _BatchState:
    texts: list[str] = field(default_factory=list)
    last_message_at: float = 0.0
    worker_task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    flush_in_progress: bool = False
    tail_mode: bool = False


class MessageBatcher:
    def __init__(
        self,
        *,
        batch_wait_sec: float,
        max_wait_sec: float,
        settle_sec: float,
        tail_wait_sec: float,
        on_flush: FlushHandler,
        log_prefix: str = "",
    ):
        self.batch_wait_sec = batch_wait_sec
        self.max_wait_sec = max_wait_sec
        self.settle_sec = settle_sec
        self.tail_wait_sec = tail_wait_sec
        self.on_flush = on_flush
        self.log_prefix = log_prefix
        self._states: dict[str, _BatchState] = {}

    async def enqueue(self, chat_id: str, text: str) -> None:
        state = self._states.get(chat_id)
        if state is None:
            state = _BatchState()
            self._states[chat_id] = state

        async with state.lock:
            was_empty = not state.texts
            state.texts.append(text)
            state.last_message_at = time.monotonic()
            if state.flush_in_progress:
                state.tail_mode = True
            elif was_empty:
                state.tail_mode = False
            if state.worker_task is None or state.worker_task.done():
                state.worker_task = asyncio.create_task(self._worker(chat_id))

        logger.info(
            "%s batch +chat=%s total=%s: %s",
            self.log_prefix,
            chat_id,
            len(state.texts),
            (text or "[пусто]")[:50],
        )

    async def drop(self, chat_id: str) -> int:
        """Выбросить накопленное: чат ушёл менеджеру, отвечать уже не надо."""
        state = self._states.get(chat_id)
        if state is None:
            return 0
        async with state.lock:
            dropped = len([t for t in state.texts if t])
            state.texts.clear()
        if dropped:
            logger.info("%s batch DROP chat=%s parts=%s", self.log_prefix, chat_id, dropped)
        return dropped

    def _wait_sec(self, state: _BatchState) -> float:
        return self.tail_wait_sec if state.tail_mode else self.batch_wait_sec

    def _is_ready(self, state: _BatchState, now: float) -> bool:
        since_msg = now - state.last_message_at
        if since_msg >= self.max_wait_sec:
            return True
        return since_msg >= self._wait_sec(state)

    async def _worker(self, chat_id: str) -> None:
        try:
            while True:
                await asyncio.sleep(0.2)
                state = self._states.get(chat_id)
                if not state or not state.texts:
                    return
                if state.flush_in_progress:
                    continue
                if not self._is_ready(state, time.monotonic()):
                    continue
                await asyncio.sleep(self.settle_sec)
                state = self._states.get(chat_id)
                if not state or not state.texts or state.flush_in_progress:
                    continue
                if not self._is_ready(state, time.monotonic()):
                    continue
                async with state.lock:
                    if not state.texts or state.flush_in_progress:
                        continue
                    if not self._is_ready(state, time.monotonic()):
                        continue
                    texts = [t for t in state.texts if t]
                    state.texts.clear()
                    state.flush_in_progress = True
                combined = "\n".join(texts)
                logger.info("%s batch FLUSH chat=%s parts=%s", self.log_prefix, chat_id, len(texts))
                try:
                    await self.on_flush(chat_id, combined)
                except Exception:
                    logger.exception("%s flush failed chat=%s", self.log_prefix, chat_id)
                finally:
                    async with state.lock:
                        state.flush_in_progress = False
                state = self._states.get(chat_id)
                if not state or not state.texts:
                    return
        except asyncio.CancelledError:
            return
