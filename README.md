# Avito-бот Центр-Балкон

Поллинг Messenger API. Публичный IP не нужен.

## Что делает

- Смотрит **все чаты по объявлениям** аккаунта, без фильтра на одно объявление.
- Отвечает **только новичкам**: пустой чат, клиент написал первым после старта бота.
- Чаты, которые уже были на запуске, чаты с сообщениями до старта бота и чаты с исходящими не от бота — `existing`, молчим навсегда.
- Менеджер написал руками или `#стоп` → `manual`, бот замолкает сразу (проверка и перед отправкой ответа). `#старт` возвращает.
- В промпт уходят **последние 40 сообщений** диалога (`HISTORY_LIMIT`).
- Диалог ведёт **один** бот на Poe: `IlyaDemoBal-Manager`. Отдельного классификатора нет.
- Дожим через 4 часа тишины после нашего ответа, только с 09:00 до 18:00 МСК.
- Телефон или запись на замер → лид в Telegram-группу (бот должен быть добавлен в группу).
- Голосовые пока просим продублировать текстом (файл через API достать умеем, Whisper ещё не включён).

## Запуск

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

В `.env`: `AVITO_CLIENT_ID`, `AVITO_CLIENT_SECRET`, `POE_API_KEY`.
Ответы: `POE_RESPONSE_BOT=IlyaDemoBal-Manager`, `SEND_SYSTEM_PROMPTS=false` (промпт уже в боте на Poe).

```bash
.venv\Scripts\python check_access.py
.venv\Scripts\python main.py
```

Сервер: `root@msk-1-vm-xcjy:/var/opt/ilya-demo-balkon`. Подробно: `deploy/DEPLOY.md`.
