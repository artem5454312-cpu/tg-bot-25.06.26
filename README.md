# 🤖 Telegram Personal Assistant

Личный ассистент в Telegram с голосом, задачами, проектами, памятью, PDF и генерацией изображений.

## Стек

- **Python 3.11+** + aiogram 3
- **Claude Opus 4.8** — основной мозг (intent detection, отчёты, PDF, советы)
- **Whisper** — распознавание голоса
- **GPT Image (gpt-image-1)** — генерация изображений
- **PostgreSQL** — база данных
- **Railway** — хостинг

---

## Быстрый старт

### 1. Клонируй репозиторий

```bash
git clone https://github.com/YOUR_USERNAME/tg-assistant.git
cd tg-assistant
```

### 2. Установи зависимости

```bash
pip install -r requirements.txt
```

### 3. Создай .env файл

```bash
cp .env.example .env
```

Открой `.env` и заполни все значения (см. раздел «Что нужно получить»).

### 4. Запусти локально

```bash
python main.py
```

---

## Что нужно получить

### Telegram Bot Token
1. Открой @BotFather в Telegram
2. Напиши `/newbot`
3. Придумай имя и username для бота
4. Скопируй токен → вставь в `TELEGRAM_BOT_TOKEN`

### Твой Telegram ID
1. Напиши боту @userinfobot
2. Скопируй `Id` → вставь в `OWNER_TELEGRAM_ID`

### Anthropic API Key (Claude Opus 4.8)
1. Зайди на https://console.anthropic.com
2. API Keys → Create Key
3. Скопируй → вставь в `ANTHROPIC_API_KEY`

### OpenAI API Key (Whisper + GPT Image)
1. Зайди на https://platform.openai.com/api-keys
2. Create new secret key
3. Скопируй → вставь в `OPENAI_API_KEY`

---

## Деплой на Railway

### 1. Создай аккаунт на railway.app

### 2. Создай новый проект

```
New Project → Deploy from GitHub repo → выбери свой репозиторий
```

### 3. Добавь PostgreSQL

```
New → Database → Add PostgreSQL
```

После создания Railway автоматически даст тебе `DATABASE_URL`.

### 4. Добавь переменные окружения

В Railway: Settings → Variables → добавь все из `.env.example`:

```
TELEGRAM_BOT_TOKEN=...
OWNER_TELEGRAM_ID=...
OWNER_PIN=...
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
DATABASE_URL=postgresql+asyncpg://...   ← берёшь из Railway PostgreSQL
TIMEZONE=Europe/Moscow
MORNING_REPORT_TIME=07:30
```

> ⚠️ DATABASE_URL от Railway начинается с `postgresql://` — замени на `postgresql+asyncpg://`

### 5. Deploy

Railway задеплоит автоматически при каждом `git push`.

---

## Структура проекта

```
tg_assistant/
├── main.py                    # точка входа
├── config/
│   └── settings.py            # все настройки через .env
├── app/
│   ├── db/
│   │   ├── models.py          # все таблицы БД
│   │   ├── engine.py          # подключение к PostgreSQL
│   │   ├── repos.py           # users, projects, memory, notes
│   │   └── task_repo.py       # задачи
│   ├── handlers/
│   │   ├── messages.py        # свободный текст + голос (главный)
│   │   ├── tasks.py           # кнопка Задачи
│   │   ├── projects.py        # кнопка Проекты
│   │   └── settings.py        # кнопка Настройки + PIN
│   ├── services/
│   │   ├── claude_service.py  # Claude API
│   │   ├── voice_service.py   # Whisper
│   │   ├── image_service.py   # GPT Image
│   │   ├── pdf_service.py     # ReportLab PDF
│   │   └── scheduler.py       # утренний отчёт + напоминания
│   └── keyboards/
│       └── __init__.py        # все клавиатуры
├── requirements.txt
├── Procfile
├── railway.toml
└── .env.example
```

---

## Примеры команд

```
Завтра в 12 напомни позвонить Игорю
Создай проект Бассейны
Запомни, что клиент предпочитает общаться вечером
Удали задачу про рекламу
Сделай PDF по проекту CRM
Сгенерируй картинку для обложки рилс
Запиши тренировку 10 км за 55 минут
Дай прогресс по тренировкам
Что у нас по проекту Telegram-ассистент?
```
