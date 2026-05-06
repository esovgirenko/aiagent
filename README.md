# Self-learning Multi-LLM AI Agent

MVP-проект агента с веб-интерфейсом, который:
- подключается к разным LLM-провайдерам (`openai`, `ollama`, `gigachat`);
- хранит историю диалогов и фидбек в SQLite;
- использует локальную память и агрегированный фидбек в системном промпте для самоулучшения.
- поддерживает опциональную авторизацию в UI и stream-ответы.

## Быстрый старт (локально)

1. Создайте виртуальное окружение и установите зависимости:
   - `python -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
2. Создайте `.env`:
   - `cp .env.example .env`
   - заполните ключи провайдеров
3. Запустите:
   - `uvicorn app.main:app --host 0.0.0.0 --port 8000`
4. Откройте [http://localhost:8000](http://localhost:8000)

## Запуск на отдельном VPS через Docker

1. Установите Docker и Docker Compose plugin.
2. Скопируйте проект на сервер.
3. Настройте `.env` на сервере (`cp .env.example .env` и заполните ключи).
4. Запустите:
   - `docker compose up -d --build`
5. Проверьте:
   - `docker compose ps`
   - `docker compose logs -f ai-agent`

## Production-вариант: systemd + Nginx + HTTPS

1. Подготовьте сервер (Ubuntu/Debian):
   - `sudo apt update`
   - `sudo apt install -y python3-venv nginx certbot python3-certbot-nginx`
2. Разместите код:
   - `sudo mkdir -p /opt/ai-agent`
   - скопируйте проект в `/opt/ai-agent`
3. Настройте Python env:
   - `cd /opt/ai-agent`
   - `python3 -m venv .venv`
   - `. .venv/bin/activate`
   - `pip install -r requirements.txt`
4. Настройте `.env`:
   - `cp .env.example .env`
   - заполните ключи и обязательно `AUTH_PASSWORD`, `SESSION_SECRET`
5. Подключите systemd unit:
   - `sudo cp deploy/ai-agent.service /etc/systemd/system/ai-agent.service`
   - при необходимости отредактируйте `User/Group/WorkingDirectory`
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable --now ai-agent`
6. Подключите Nginx:
   - `sudo cp deploy/nginx-ai-agent.conf /etc/nginx/sites-available/ai-agent`
   - замените `server_name`
   - `sudo ln -s /etc/nginx/sites-available/ai-agent /etc/nginx/sites-enabled/ai-agent`
   - `sudo nginx -t && sudo systemctl reload nginx`
7. Выпустите TLS-сертификат:
   - `sudo certbot --nginx -d your-domain.example.com`
8. Проверка:
   - `systemctl status ai-agent`
   - `journalctl -u ai-agent -f`

## Установка одной командой (install.sh)

В репозитории есть `install.sh` для VPS.

Подготовка:
- скопируйте проект на сервер;
- перейдите в папку проекта;
- `chmod +x install.sh`.

### Режим Docker (рекомендуется для быстрого старта)

- `sudo bash install.sh docker`

### Режим systemd + nginx

- `sudo DOMAIN=your-domain.example.com bash install.sh systemd`

Опции:
- `APP_DIR=/opt/ai-agent` (по умолчанию)
- `SERVICE_USER=www-data` (по умолчанию)
- `ENABLE_TLS=true|false` (для systemd режима)

## Как работает "самообучение" в MVP

- После каждого ответа сохраняется запись в `conversations`.
- Пользователь может поставить `👍/👎` — фидбек попадет в `feedback`.
- При новом запросе агент получает:
  - краткую выборку последних диалогов;
  - агрегированную статистику фидбека.

Это безопасный контур улучшения качества без автоматического изменения кода.

## Авторизация

- Если `DEFAULT_PASSWORD` пустой, авторизация отключена.
- Если `DEFAULT_PASSWORD` задан, при старте создается пользователь `DEFAULT_USERNAME`.
- Доступ через `/login` (логин/пароль), сессия хранится cookie-based.

## Multi-user

- Пользователи хранятся в SQLite (`users`), пароль хранится как PBKDF2 hash.
- Добавлена admin-панель `/admin`:
  - создание пользователей,
  - просмотр списка пользователей,
  - просмотр audit logs.
- Admin API:
  - `GET /api/admin/users`
  - `POST /api/admin/users`
  - `POST /api/admin/users/status`
  - `GET /api/admin/audit`
  - `POST /api/admin/agent/run-cycle`
  - `GET /api/admin/agent/runs`

## Rate limit + audit log

- Лимит запросов на IP: `RATE_LIMIT_PER_MINUTE` (по умолчанию 20).
- Логи действий пишутся в таблицу `audit_logs` (`login_success`, `login_failed`, `chat`, `chat_stream`, `feedback`, `logout`).

## Autonomous cycle (plan/act/verify/reflect)

- В admin UI можно запустить автономный цикл по цели.
- Цикл сохраняется в SQLite таблицах: `goals`, `goal_tasks`, `autonomous_runs`.
- Каждый запуск выполняет:
  - plan: план из 3 шагов,
  - act: следующее действие,
  - verify: PASS/FAIL оценка,
  - reflect: краткая ретроспектива.

## Streaming

- `POST /api/chat/stream` возвращает `text/event-stream`:
  - события `chunk` (текст частями),
  - событие `done` (id диалога),
  - событие `error` (ошибка).
- Для OpenAI-compatible включен реальный stream mode (`stream=true`), а не искусственное дробление готового ответа.

## Важные замечания

- Для `GigaChat` в MVP используется OAuth + `/chat/completions`.
- Поддерживаются два режима авторизации GigaChat:
  - `GIGACHAT_AUTH_KEY` (готовый API Authorization Key, предпочтительно);
  - или пара `GIGACHAT_CLIENT_ID` + `GIGACHAT_CLIENT_SECRET`.
- Запросы к GigaChat отправляются с `verify=False`, потому что на некоторых окружениях требуется отдельная настройка сертификатов. Для production лучше установить корректный trust store и включить TLS verification.
- Не храните реальные ключи в репозитории.

## API

- `POST /api/chat`
  - body: `{"provider":"openai|ollama|gigachat","message":"..."}`
- `POST /api/chat/stream`
  - body: `{"provider":"openai|ollama|gigachat","message":"..."}`
- `POST /api/feedback`
  - body: `{"conversation_id":1,"score":1|-1,"comment":"..."}`
- `POST /api/admin/users`
  - body: `{"username":"alice","password":"secret123","role":"user|admin"}`
- `POST /api/admin/users/status`
  - body: `{"username":"alice","is_active":false}`
