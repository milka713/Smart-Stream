# Smart Stream

RSS-агрегатор с LLM-классификацией: новости автоматически распределяются по тематическим веткам и реформатируются в краткие дайджесты.

## Как это работает

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  RSS Fetcher │───>│  LLM Gateway │───>│   Database   │
│  (scheduled) │    │ (classify +  │    │  (SQLite)    │
│              │    │  reformat)   │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
                                │               │
                                v               v
                           ┌──────────────┐   ┌──────────────┐
                           │  REST API    │<──│  (queries)   │
                           │ (FastAPI)    │   └──────────────┘
                           └──────────────┘
```

1. **Сбор** — сервис опрашивает RSS-источники по расписанию (интервал настраивается на уровне источника)
2. **Классификация** — каждая новая новость отправляется в LLM-сервер с одним вызовом: определение темы + написание дайджеста
3. **Доставка** — классифицированные статьи доступны через REST API (Telegram-бот — в планах)

### Почему один вызов LLM

Сервер LLM (llama.cpp) — **один слот + очередь**. Два вызова (классификация отдельно, реформатинг отдельно) = 2× задержка. Поэтому промпт делает и то, и другое за один проход.

```
Темы: [список активных веток]
Новость: {заголовок} — {текст}

Ответ строго в JSON: {"matched": true/false, "topic": "ветка или null", "digest": "дайджест или null"}
```

## Архитектура

```
smart_stream/
├── app/
│   ├── main.py                  # FastAPI app, lifespan, роутинг
│   ├── config.py                # Настройки из .env
│   ├── db.py                    # SQLAlchemy engine + session
│   ├── models.py                # ORM-модели (User, Source, TopicBranch, Article, ClassifiedArticle, Feedback)
│   ├── scheduler.py             # APScheduler — запуск RSS-цикла
│   ├── routers/                 # REST API
│   │   ├── sources.py           # CRUD источников RSS
│   │   ├── topics.py            # CRUD тематических веток
│   │   ├── articles.py          # Запрос новостей + классификации
│   │   └── feedback.py          # Обратная связь (подходит/нет)
│   ├── repositories/            # Доступ к БД
│   │   ├── sources.py
│   │   ├── topics.py
│   │   ├── articles.py
│   │   └── classified_articles.py
│   └── services/                # Бизнес-логика
│       ├── rss.py               # Парсинг RSS-фидов (feedparser)
│       └── llm.py               # Классификация + реформатинг через OpenAI-compatible API
├── tests/
│   ├── test_sources.py          # Unit-тесты API источников
│   ├── test_topics.py           # Unit-тесты API тем
│   ├── test_rss.py              # Unit-тесты RSS-парсера
│   ├── test_llm.py              # Unit-тесты LLM-промптов
│   ├── test_scheduler.py        # Unit-тесты планировщика
│   ├── test_health.py           # Unit-тест health-эндпоинта
│   └── test_integration.py      # Интеграционные тесты (реальный RSS + моки LLM)
├── alembic/                     # Миграции БД
├── alembic.ini
├── pyproject.toml
└── requirements.txt
```

## Стек

- **FastAPI** — веб-фреймворк и REST API
- **SQLAlchemy 2.0 + SQLite** — ORM и база данных
- **Alembic** — миграции
- **feedparser** — парсинг RSS-фидов
- **OpenAI SDK** — клиент для llama.cpp-сервера (OpenAI-compatible API)
- **APScheduler** — планировщик опроса источников

## Быстрый старт

```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка (копия из .env.example)
cp .env.example .env
# Отредактировать .env — особенно OPENAI_API_KEY

# Запуск
uvicorn app.main:app --reload

# API доступен на http://localhost:8000/docs
```

## Настройка

| Переменная | Описание | По умолчанию |
|---|---|---|
| `DATABASE_URL` | URL базы данных | `sqlite:///smart_stream.db` |
| `LLM_BASE_URL` | URL LLM-сервера | `http://80.82.59.87:8080/v1` |
| `OPENAI_API_KEY` | API-ключ LLM-сервера | — |
| `LLM_MAX_TOKENS` | Максимум токенов в ответе | `4096` |
| `LLM_TIMEOUT` | Таймаут запроса (сек) | `1800` |
| `RSS_INTERVAL_MIN` | Интервал опроса RSS (мин) | `5` |

## API

### Источники

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/sources/` | Добавить RSS-источник |
| `GET` | `/sources/` | Список источников |
| `DELETE` | `/sources/{id}` | Удалить источник |

### Темы

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/topics/` | Создать тематическую ветку |
| `GET` | `/topics/` | Список веток |
| `DELETE` | `/topics/{id}` | Удалить ветку |

### Новости

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/articles/` | Запрос новостей (фильтры: `matched_only`, `topic`, `source`) |

### Обратная связь

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/feedback/` | Отправить оценку (подходит/нет) |

### Сервис

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/health` | Статус сервиса и LLM |

## Тесты

```bash
# Все тесты
python3 -m pytest tests/ -v

# Только интеграционные
python3 -m pytest tests/test_integration.py -v

# С покрытием
python3 -m pytest tests/ -v --cov=app --cov-report=term-missing
```

## План

- [x] Сбор RSS + дедупликация
- [x] LLM-классификация + реформатинг (один вызов)
- [x] REST API (источники, темы, статьи, обратная связь)
- [x] Планировщик
- [x] Тесты
- [ ] Telegram-бот
- [ ] Дедупликация по хешу заголовка (fallback)
- [ ] Настройка LLM-промптов на основе обратной связи
