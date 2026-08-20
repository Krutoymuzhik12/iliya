"""Транскрибация голосовых из чатов Авито.

Порт из mebel_Iliya/services/transcription.py.

Провайдеры (TRANSCRIPTION_PROVIDER, по умолчанию auto):
- local  - faster-whisper на CPU (бесплатно, без API, но качает модель)
- openai - OpenAI Whisper API (OPENAI_API_KEY)
- poe    - мультимодальный бот на Poe с загрузкой файла (fastapi-poe + POE_API_KEY)
- auto   - local -> openai -> poe -> заглушка

Авито отдаёт голосовое ссылкой, файла на диске нет, поэтому основная точка
входа - transcribe_bytes.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from config.settings import SETTINGS

log = logging.getLogger(__name__)

TRANSCRIBE_PROMPT = (
    "Транскрибируй это голосовое сообщение на русском языке. "
    "В ответе верни только текст сообщения, без комментариев."
)

_local_model = None


def _dedupe(text: str) -> str:
    """Страховка от удвоенной транскрибации: 'X X' или 'X.X.' -> 'X'."""
    t = text.strip()
    if len(t) < 10:
        return t
    half, rem = divmod(len(t), 2)
    if rem == 0 and t[:half].strip() == t[half:].strip():
        return t[:half].strip()
    a, b = t[: half + 1].strip(), t[half:].strip()
    if a == b:
        return a
    return t


def _pick_provider() -> str:
    if SETTINGS.transcription_provider != "auto":
        return SETTINGS.transcription_provider
    try:
        import faster_whisper  # noqa: F401

        return "local"
    except ImportError:
        pass
    if SETTINGS.openai_api_key:
        return "openai"
    if SETTINGS.poe_api_key:
        try:
            import fastapi_poe  # noqa: F401

            return "poe"
        except ImportError:
            pass
    return "stub"


def _local_sync(audio_path: Path) -> str:
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel

        log.info("Загрузка локальной модели Whisper «%s»...", SETTINGS.whisper_model)
        _local_model = WhisperModel(SETTINGS.whisper_model, device="cpu", compute_type="int8")
    segments, _info = _local_model.transcribe(str(audio_path), language="ru")
    return " ".join(seg.text.strip() for seg in segments).strip()


async def _transcribe_openai(audio_path: Path) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=SETTINGS.openai_api_key)
    with open(audio_path, "rb") as f:
        result = await client.audio.transcriptions.create(
            model="whisper-1", file=f, language="ru"
        )
    return result.text.strip()


def _maybe_convert_to_mp3(src: Path) -> Path:
    if src.suffix.lower() == ".mp3" or shutil.which("ffmpeg") is None:
        return src
    mp3_path = src.with_suffix(".mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), str(mp3_path)],
            capture_output=True,
            check=True,
            timeout=60,
        )
        return mp3_path
    except (subprocess.SubprocessError, OSError):
        log.warning("Конвертация ffmpeg не удалась, отправляю файл как есть")
        return src


async def _transcribe_poe(audio_path: Path) -> str:
    import fastapi_poe as fp

    send_path = await asyncio.to_thread(_maybe_convert_to_mp3, audio_path)
    with open(send_path, "rb") as f:
        attachment = await fp.upload_file(
            file=f, file_name=send_path.name, api_key=SETTINGS.poe_api_key
        )
    message = fp.ProtocolMessage(
        role="user", content=TRANSCRIBE_PROMPT, attachments=[attachment]
    )
    parts: list[str] = []
    async for partial in fp.get_bot_response(
        messages=[message], bot_name=SETTINGS.poe_whisper_bot, api_key=SETTINGS.poe_api_key
    ):
        if getattr(partial, "is_replace_response", False):
            parts = [partial.text]
        else:
            parts.append(partial.text)
    return "".join(parts).strip()


def warm_local_model() -> None:
    """Подгрузить Whisper в память, чтобы первое голосовое не ждало модель."""
    if _pick_provider() != "local":
        return
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel

        log.info("Прогрев Whisper «%s»…", SETTINGS.whisper_model)
        _local_model = WhisperModel(SETTINGS.whisper_model, device="cpu", compute_type="int8")


async def transcribe(audio_path: Path) -> str:
    """Текст голосового. Ошибки возвращаются в квадратных скобках - вызывающий
    код по ним понимает, что распознать не вышло (см. failed)."""
    provider = _pick_provider()
    try:
        if provider == "local":
            text = await asyncio.to_thread(_local_sync, audio_path)
        elif provider == "openai":
            text = await _transcribe_openai(audio_path)
        elif provider == "poe":
            text = await _transcribe_poe(audio_path)
        else:
            log.warning(
                "Транскрибация недоступна: нет faster-whisper / OPENAI_API_KEY / fastapi-poe"
            )
            return "[транскрибация не настроена]"
        text = _dedupe(text)
        return text or "[транскрибация вернула пустой ответ]"
    except Exception:
        log.exception("Транскрибация не удалась (provider=%s)", provider)
        return "[ошибка транскрибации]"


async def transcribe_bytes(data: bytes, suffix: str = ".mp3") -> str:
    """Голосовое из Авито приходит ссылкой - кладём во временный файл."""
    if not data:
        return "[пустой аудиофайл]"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"voice{suffix}"
        path.write_bytes(data)
        return await transcribe(path)


def failed(text: str) -> bool:
    """Вернулось служебное сообщение об ошибке, а не речь."""
    return not text or text.startswith("[")
