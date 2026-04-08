# RDT — Справочник по скриптингу

> **Rambo Docker Tools** — генератор `docker-compose.yml`.  
> Все команды поддерживают неинтерактивный режим, что делает RDT удобным для скриптов и автоматизации.

---

## Содержание

- [Общие правила](#общие-правила)
- [rdt init](#rdt-init)
- [rdt add](#rdt-add)
  - [Флаги](#флаги)
  - [Поведение сети](#поведение-сети---network)
  - [Примеры](#примеры-1)
- [rdt list](#rdt-list)
- [rdt up](#rdt-up)
- [rdt check](#rdt-check)
- [rdt remove](#rdt-remove)
- [rdt doctor](#rdt-doctor)
- [rdt lang](#rdt-lang)
- [Типичный сценарий](#типичный-сценарий)

---

## Общие правила

- Запуск `rdt` **без аргументов** открывает интерактивное меню.
- Любую команду можно выполнить **напрямую**, минуя меню:  
  `rdt <команда> [опции]`
- Флаг `--help` доступен для каждой команды:  
  `rdt --help`, `rdt add --help`, `rdt init --help`, …
- Язык интерфейса задаётся через переменную окружения `RDT_LANG` или командой `rdt lang set <код>`.

---

## rdt init

Создаёт базовый `docker-compose.yml` с сетью `rambo-net`.  
Дополнительно создаёт пустые `.env` и `.env.example`, если они отсутствуют.

```bash
rdt init [OPTIONS]
```

| Флаг | Короткий | Тип | По умолчанию | Описание |
|------|----------|-----|--------------|----------|
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Путь к создаваемому файлу |
| `--force` | — | `bool` | `False` | Перезаписать файл, если он уже существует |

### Примеры

```bash
# Инициализировать проект в текущей папке
rdt init

# Указать нестандартный путь к файлу
rdt init --file infra/compose.yml

# Перезаписать существующий файл
rdt init --force
```

---

## rdt add

Добавляет сервис в `docker-compose.yml`.

```bash
rdt add <SERVICE> [OPTIONS]
```

**`<SERVICE>`** — имя сервиса (регистронезависимо). Полный список: `rdt list`.

> По умолчанию запускается интерактивный мастер настройки.  
> Для неинтерактивного режима используйте флаг **`--yes`** (`-y`).

### Флаги

| Флаг | Короткий | Тип | По умолчанию | Описание |
|------|----------|-----|--------------|----------|
| `--yes` | `-y` | `bool` | `False` | Пропустить мастер, использовать значения по умолчанию |
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Путь к файлу compose |
| `--hardcore` | — | `bool` | `False` | Генерировать случайные уникальные пароли вместо плейсхолдеров `.env` |
| `--port` | `-p` | `INT` | порт пресета | Внешний порт сервиса на хосте |
| `--volume` | — | `TEXT` | `<service>_data` | Volume или путь для данных (например: `./data/pg`, `my_vol`) |
| `--no-ports` | — | `bool` | `False` | Не прокидывать порты наружу (только внутри Docker-сети) |
| `--network` | — | `TEXT` | `bridge` | Тип или имя сети: `bridge` \| `host` \| `none` \| `<external-net>` |
| `--depends-on` | — | `TEXT` (повтор) | — | Зависимость от сервиса; флаг можно указать несколько раз |
| `--container-name` | — | `TEXT` | имя сервиса | Явное имя контейнера |
| `--hc-interval` | — | `TEXT` | по пресету | Интервал healthcheck (например: `10s`) |
| `--hc-timeout` | — | `TEXT` | по пресету | Таймаут healthcheck (например: `5s`) |
| `--hc-retries` | — | `INT` | по пресету | Количество попыток healthcheck |
| `--hc-start-period` | — | `TEXT` | по пресету | Начальный период healthcheck (например: `30s`) |
| `--set` | — | `TEXT` (повтор) | — | Переопределить любой ответ мастера в формате `key=value`; флаг можно указать несколько раз |

### Поведение сети (`--network`)

| Значение | Результат |
|----------|-----------|
| `bridge` (по умолчанию) | Изолированная сеть `rambo-net` |
| `host` | Использовать сетевой стек хоста |
| `none` | Без сети |
| `<имя>` | Подключиться к существующей external-сети |

### Примеры

```bash
# Добавить PostgreSQL с настройками по умолчанию (без вопросов)
rdt add postgres --yes

# Указать порт и путь хранения данных
rdt add postgres --yes --port 5433 --volume ./data/pg

# Сгенерировать уникальные пароли
rdt add postgres --yes --hardcore

# Redis без публикации порта наружу
rdt add redis --yes --no-ports

# Kafka UI с зависимостью от kafka
rdt add kafka-ui --yes --depends-on kafka

# Несколько зависимостей
rdt add redis --yes --depends-on rdt-postgres --depends-on rdt-rabbitmq

# Подключить к внешней Docker-сети
rdt add postgres --yes --network my-project-net

# Переопределить имя контейнера
rdt add postgres --yes --container-name pg-main

# Кастомные параметры healthcheck
rdt add postgres --yes --hc-interval 15s --hc-timeout 10s --hc-retries 3 --hc-start-period 60s

# Указать нестандартный путь к compose-файлу
rdt add mysql --yes --file infra/compose.yml

# Переопределить ответы мастера через --set (например, для Nginx upstream)
rdt add nginx-proxy --yes --set nginx_upstream=app:8080 --set nginx_server_name=example.com
```

---

## rdt list

Выводит таблицу всех доступных пресетов сервисов, сгруппированных по категориям.

```bash
rdt list
```

Флагов нет. Команда только для чтения, ничего не изменяет.

---

## rdt up

Запускает контейнеры через `docker compose up` (прокси-команда).

```bash
rdt up [OPTIONS]
```

| Флаг | Короткий | Тип | По умолчанию | Описание |
|------|----------|-----|--------------|----------|
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Путь к compose-файлу |
| `--detach` / `--no-detach` | `-d` | `bool` | `True` (detach) | Запустить в фоновом режиме |

### Примеры

```bash
# Запустить в фоне (по умолчанию)
rdt up

# Запустить в foreground (логи в терминале)
rdt up --no-detach

# Указать нестандартный файл
rdt up --file infra/compose.yml
```

---

## rdt check

Валидирует `docker-compose.yml` через `docker compose config`.
Обнаруживает синтаксические ошибки YAML, неизвестные ключи и неверные ссылки ещё до запуска стека.

```bash
rdt check [OPTIONS]
```

| Флаг | Короткий | Тип | По умолчанию | Описание |
|------|----------|-----|--------------|----------|
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Путь к compose-файлу |
| `--verbose` | `-v` | `bool` | `False` | Показать полный разрешённый конфиг при успешной проверке |

### Примеры

```bash
# Проверить файл по умолчанию
rdt check

# Подробный вывод разрешённого конфига
rdt check --verbose

# Проверить нестандартный файл
rdt check --file infra/compose.yml
```

Возвращает **код 0** при успехе или **ненулевой код** при ошибке.

---

## rdt remove

Удаляет сервис из `docker-compose.yml`.
Опционально очищает осиротевшие переменные окружения и companion-файлы конфигурации.

```bash
rdt remove [SERVICE] [OPTIONS]
```

**`[SERVICE]`** — имя сервиса (необязательно). Если не указано, отображается интерактивный список.

| Флаг | Короткий | Тип | По умолчанию | Описание |
|------|----------|-----|--------------|----------|
| `--yes` | `-y` | `bool` | `False` | Пропустить все подтверждения |
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Путь к compose-файлу |
| `--clean-env` | — | `bool` | `False` | Удалить осиротевшие переменные из `.env` / `.env.example` |
| `--clean-artifacts` | — | `bool` | `False` | Удалить companion-файлы конфигурации сервиса |

### Примеры

```bash
# Интерактивный выбор сервиса
rdt remove

# Удалить конкретный сервис (с подтверждением)
rdt remove postgres

# Удалить и очистить переменные окружения
rdt remove postgres --clean-env

# Удалить, очистить env и companion-файлы без подтверждений
rdt remove postgres --yes --clean-env --clean-artifacts

# Указать нестандартный compose-файл
rdt remove mysql --file infra/compose.yml
```

---

## rdt doctor

Запускает полную диагностику Docker-проекта и выводит отчёт.

```bash
rdt doctor [OPTIONS]
```

| Флаг | Короткий | Тип | По умолчанию | Описание |
|------|----------|-----|--------------|----------|
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Путь к compose-файлу |

### Выполняемые проверки

| Проверка | Что проверяется |
|----------|----------------|
| `docker` | Docker daemon доступен |
| `compose` | Docker Compose v2 доступен |
| `compose_valid` | Файл проходит `docker compose config` |
| `env_vars` | Все `${VAR}` в compose заданы в `.env` |
| `port_conflicts` | Прокинутые host-порты не заняты |
| `dangling_deps` | `depends_on` ссылается только на существующие сервисы |
| `companion_files` | Bind-mounted файлы конфигурации существуют на диске |

Возвращает **код 0** при отсутствии ошибок; **ненулевой код** если есть проверки со статусом `error`.

### Примеры

```bash
# Проверить файл по умолчанию
rdt doctor

# Проверить нестандартный файл
rdt doctor --file infra/compose.yml
```

---

## rdt lang

Управляет языком интерфейса RDT.
Настройка сохраняется в `~/.rdt/config.json` и применяется при каждом запуске.
Приоритет: переменная `RDT_LANG` > `~/.rdt/config.json` > встроенный default (`en`).

```bash
rdt lang [ACTION] [VALUE]
```

| Аргумент | Обязательный | Описание |
|----------|-------------|----------|
| `ACTION` | Нет | `list` — показать текущий и доступные языки; `set` — сменить язык |
| `VALUE` | Только при `set` | Код языка (например: `ru`, `en`) |

### Примеры

```bash
# Интерактивный выбор языка
rdt lang

# Показать текущий язык и список доступных
rdt lang list

# Сменить язык на русский
rdt lang set ru

# Сменить язык на английский
rdt lang set en

# Переопределить язык для одной команды (не сохраняется)
RDT_LANG=ru rdt add postgres --yes
```

### Доступные языки

| Код | Язык |
|-----|------|
| `en` | English |
| `ru` | Русский |

---

## Типичный сценарий

```bash
#!/usr/bin/env bash
set -e

# 1. Инициализировать проект
rdt init

# 2. Добавить PostgreSQL с уникальными паролями
rdt add postgres --yes --hardcore --port 5432 --volume ./data/pg

# 3. Добавить Redis без публикации порта
rdt add redis --yes --no-ports --depends-on postgres

# 4. Добавить pgAdmin, подключённый к postgres
rdt add pgadmin --yes --depends-on postgres

# 5. Запустить диагностику (env-переменные, порты, companion-файлы)
rdt doctor

# 6. Проверить синтаксис compose
rdt check

# 7. Запустить стек
rdt up
```
