# Техническое задание: Rambo Docker Tools (RDT)

1. Общее описание

RDT — это CLI-утилита на Python для ускоренной генерации и модификации файлов docker-compose.yml в среде разработки. Инструмент автоматизирует рутину создания инфраструктуры, следуя Best Practices и обеспечивая интерактивный выбор параметров.
2. Технологический стек

    Язык: Python 3.10+

    CLI Framework: Typer (для команд и саб-команд).

    YAML Engine: ruamel.yaml (обязательно: сохранение комментариев, порядка ключей и форматирования).

    Интерактив: Questionary (чекбоксы, списки, подтверждения).

    Templating: Jinja2 (изолированные шаблоны для каждого сервиса).

    Environment: python-dotenv (управление секретами).

    Utility: port-picker (проверка доступности портов на хосте).

3. Архитектурные требования

Для реализации логики генерации необходимо использовать паттерн «Стратегия» (Strategy):

    BaseStrategy: Общая логика (имена контейнеров, сети, рестарт-политики).

    DatabaseStrategy: Обязательный проброс volumes, специфичные healthcheck, генерация учетных данных.

    AdminToolStrategy: Логика поиска «родительских» сервисов, настройка зависимостей (depends_on), проброс портов без volumes.

    MonitoringStrategy: Специфичные лимиты ресурсов и конфигурационные маппинги.

4. База пресетов (Сервисы)
Категория	Доступные сервисы
Relational DB	Postgres, MySQL, MariaDB, MS SQL, Oracle DB
NoSQL / Cache	MongoDB, Redis, Valkey, Cassandra, InfluxDB
Search/Logging	Elasticsearch, OpenSearch
Message Brokers	Kafka (KRaft/Zookeeper), RabbitMQ
Identity/Auth	Keycloak
Monitoring	Prometheus, Grafana, Zookeeper
Admin Tools	pgAdmin, phpMyAdmin, Kafka-UI, mongo-express
5. Функциональные требования
5.1. Интерфейс командной строки (CLI)

    rdt init — Создание базового docker-compose.yml с описанием сети rambo-net.

    rdt add <service> — Запуск интерактивного мастера добавления сервиса.

    rdt list — Отображение всех доступных пресетов по категориям.

    rdt up — Прокси-команда для docker compose up -d.

5.2. Интерактивный мастер (Wizard Mode)

При добавлении сервиса агент должен запрашивать:

    Ports: Использовать стандартный или ввести кастомный (с валидацией занятости).

    Credentials: Использовать стандартные (rambo / rambo_password) или сгенерировать уникальные (флаг --hardcore).

    Dependencies: Выбор из списка уже существующих в файле сервисов для depends_on (с условием service_healthy).

    Volumes: Для БД — выбор между именованным volume или локальной папкой.

5.3. Логика "Smart Mapping" (Умные связки)

Автоматическое предложение связей при обнаружении контекста:

    pgAdmin -> Postgres: Предложить выбрать инстанс БД из файла для автоконфигурации.

    Kafka-UI -> Kafka: Автозаполнение KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS.

    Grafana -> Prometheus: Автоматическое добавление в DataSource.

6. Принципы генерации (Best Practices по умолчанию)

    Naming: Префикс rdt- для всех контейнеров.

    Network: Принудительное объединение всех сервисов в мост rambo-net.

    Reliability: Обязательные healthcheck (например, pg_isready для Postgres).

    Resources: Лимиты по CPU/RAM для предотвращения утечек в дев-среде.

    Secrets: Вынос паролей в .env файл с автоматическим созданием .env.example.

7. Workflow разработки

    Загрузка: Чтение текущего YAML через ruamel.yaml.

    Рендеринг: Обработка Jinja2 шаблона с учетом ответов пользователя.

    Инъекция: Вставка нового блока в секцию services без нарушения структуры файла.

    Синхронизация: Дописывание необходимых переменных в .env.