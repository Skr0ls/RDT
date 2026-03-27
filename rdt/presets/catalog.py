"""
Каталог всех доступных пресетов сервисов.
Каждый пресет описывает конфигурацию docker-compose сервиса по умолчанию.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rdt.artifacts import ArtifactDef, BootstrapHint, DirectoryDef, OverwritePolicy

CATEGORY_WEB = "Web Servers"
CATEGORY_RELATIONAL = "Relational DB"
CATEGORY_NOSQL = "NoSQL / Cache"
CATEGORY_SEARCH = "Search / Logging"
CATEGORY_BROKER = "Message Brokers"
CATEGORY_AUTH = "Identity / Auth"
CATEGORY_MONITORING = "Monitoring"
CATEGORY_ADMIN = "Admin Tools"


@dataclass
class ServicePreset:
    name: str                          # ключ сервиса (postgres, redis …)
    display_name: str                  # красивое имя для UI
    category: str                      # категория из констант выше
    image: str                         # docker image
    default_port: int                  # стандартный внешний порт
    container_port: int                # внутренний порт контейнера
    default_env: dict = field(default_factory=dict)
    volumes: list[str] = field(default_factory=list)   # шаблоны volume-маппингов
    healthcheck: Optional[dict] = None
    deploy_limits: Optional[dict] = None               # CPU / RAM лимиты
    strategy: str = "base"            # base | database | admin_tool | monitoring | web_server
    depends_on_category: Optional[str] = None          # для Smart Mapping
    artifacts: list[ArtifactDef] = field(default_factory=list)  # companion-файлы сервиса
    scaffolds: list[DirectoryDef] = field(default_factory=list)  # директории для scaffolding
    bootstrap_hints: list[BootstrapHint] = field(default_factory=list)  # подсказки после установки


# ---------------------------------------------------------------------------
# Relational DB
# ---------------------------------------------------------------------------
POSTGRES = ServicePreset(
    name="postgres",
    display_name="PostgreSQL",
    category=CATEGORY_RELATIONAL,
    image="postgres:16-alpine",
    default_port=5432,
    container_port=5432,
    default_env={
        "POSTGRES_USER": "${POSTGRES_USER}",
        "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD}",
        "POSTGRES_DB": "${POSTGRES_DB}",
    },
    volumes=["{{ volume_source }}:/var/lib/postgresql/data"],
    healthcheck={
        "test": ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"],
        "interval": "10s", "timeout": "5s", "retries": 5, "start_period": "30s",
    },
    deploy_limits={"cpus": "1.0", "memory": "512M"},
    strategy="database",
)

MYSQL = ServicePreset(
    name="mysql",
    display_name="MySQL",
    category=CATEGORY_RELATIONAL,
    image="mysql:8.4",
    default_port=3306,
    container_port=3306,
    default_env={
        "MYSQL_ROOT_PASSWORD": "${MYSQL_ROOT_PASSWORD}",
        "MYSQL_USER": "${MYSQL_USER}",
        "MYSQL_PASSWORD": "${MYSQL_PASSWORD}",
        "MYSQL_DATABASE": "${MYSQL_DATABASE}",
    },
    volumes=["{{ volume_source }}:/var/lib/mysql"],
    healthcheck={
        "test": ["CMD", "mysqladmin", "ping", "-h", "localhost"],
        "interval": "10s", "timeout": "5s", "retries": 5, "start_period": "30s",
    },
    deploy_limits={"cpus": "1.0", "memory": "512M"},
    strategy="database",
)

MARIADB = ServicePreset(
    name="mariadb",
    display_name="MariaDB",
    category=CATEGORY_RELATIONAL,
    image="mariadb:11",
    default_port=3307,
    container_port=3306,
    default_env={
        "MARIADB_ROOT_PASSWORD": "${MARIADB_ROOT_PASSWORD}",
        "MARIADB_USER": "${MARIADB_USER}",
        "MARIADB_PASSWORD": "${MARIADB_PASSWORD}",
        "MARIADB_DATABASE": "${MARIADB_DATABASE}",
    },
    volumes=["{{ volume_source }}:/var/lib/mysql"],
    healthcheck={
        "test": ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"],
        "interval": "10s", "timeout": "5s", "retries": 5, "start_period": "30s",
    },
    deploy_limits={"cpus": "1.0", "memory": "512M"},
    strategy="database",
)

MSSQL = ServicePreset(
    name="mssql",
    display_name="MS SQL Server",
    category=CATEGORY_RELATIONAL,
    image="mcr.microsoft.com/mssql/server:2022-latest",
    default_port=1433,
    container_port=1433,
    default_env={
        "ACCEPT_EULA": "Y",
        "SA_PASSWORD": "${MSSQL_SA_PASSWORD}",
        "MSSQL_PID": "Developer",
    },
    volumes=["{{ volume_source }}:/var/opt/mssql"],
    healthcheck={
        "test": ["CMD-SHELL", "/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P ${MSSQL_SA_PASSWORD} -Q 'SELECT 1'"],
        "interval": "15s", "timeout": "10s", "retries": 5, "start_period": "60s",
    },
    deploy_limits={"cpus": "2.0", "memory": "2G"},
    strategy="database",
)

ORACLE = ServicePreset(
    name="oracle",
    display_name="Oracle DB (XE)",
    category=CATEGORY_RELATIONAL,
    image="gvenzl/oracle-xe:21-slim",
    default_port=1521,
    container_port=1521,
    default_env={
        "ORACLE_PASSWORD": "${ORACLE_PASSWORD}",
        "APP_USER": "${ORACLE_APP_USER}",
        "APP_USER_PASSWORD": "${ORACLE_APP_PASSWORD}",
    },
    volumes=["{{ volume_source }}:/opt/oracle/oradata"],
    healthcheck={
        "test": ["CMD-SHELL", "healthcheck.sh"],
        "interval": "30s", "timeout": "10s", "retries": 5, "start_period": "120s",
    },
    deploy_limits={"cpus": "2.0", "memory": "2G"},
    strategy="database",
)

# ---------------------------------------------------------------------------
# NoSQL / Cache
# ---------------------------------------------------------------------------
MONGODB = ServicePreset(
    name="mongodb",
    display_name="MongoDB",
    category=CATEGORY_NOSQL,
    image="mongo:7",
    default_port=27017,
    container_port=27017,
    default_env={
        "MONGO_INITDB_ROOT_USERNAME": "${MONGO_USER}",
        "MONGO_INITDB_ROOT_PASSWORD": "${MONGO_PASSWORD}",
        "MONGO_INITDB_DATABASE": "${MONGO_DB}",
    },
    volumes=["{{ volume_source }}:/data/db"],
    healthcheck={
        "test": ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"],
        "interval": "10s", "timeout": "5s", "retries": 5, "start_period": "30s",
    },
    deploy_limits={"cpus": "1.0", "memory": "512M"},
    strategy="database",
)

REDIS = ServicePreset(
    name="redis",
    display_name="Redis",
    category=CATEGORY_NOSQL,
    image="redis:7-alpine",
    default_port=6379,
    container_port=6379,
    default_env={},
    volumes=["{{ volume_source }}:/data"],
    healthcheck={
        "test": ["CMD", "redis-cli", "ping"],
        "interval": "10s", "timeout": "5s", "retries": 5,
    },
    deploy_limits={"cpus": "0.5", "memory": "256M"},
    strategy="database",
)

VALKEY = ServicePreset(
    name="valkey",
    display_name="Valkey",
    category=CATEGORY_NOSQL,
    image="valkey/valkey:7-alpine",
    default_port=6380,
    container_port=6379,
    default_env={},
    volumes=["{{ volume_source }}:/data"],
    healthcheck={
        "test": ["CMD", "valkey-cli", "ping"],
        "interval": "10s", "timeout": "5s", "retries": 5,
    },
    deploy_limits={"cpus": "0.5", "memory": "256M"},
    strategy="database",
)

CASSANDRA = ServicePreset(
    name="cassandra",
    display_name="Cassandra",
    category=CATEGORY_NOSQL,
    image="cassandra:5",
    default_port=9042,
    container_port=9042,
    default_env={
        "CASSANDRA_CLUSTER_NAME": "rdt-cluster",
        "CASSANDRA_DC": "dc1",
    },
    volumes=["{{ volume_source }}:/var/lib/cassandra"],
    healthcheck={
        "test": ["CMD-SHELL", "nodetool status | grep -E '^UN'"],
        "interval": "30s", "timeout": "10s", "retries": 5, "start_period": "60s",
    },
    deploy_limits={"cpus": "2.0", "memory": "1G"},
    strategy="database",
)

INFLUXDB = ServicePreset(
    name="influxdb",
    display_name="InfluxDB",
    category=CATEGORY_NOSQL,
    image="influxdb:2",
    default_port=8086,
    container_port=8086,
    default_env={
        "DOCKER_INFLUXDB_INIT_MODE": "setup",
        "DOCKER_INFLUXDB_INIT_USERNAME": "${INFLUXDB_USER}",
        "DOCKER_INFLUXDB_INIT_PASSWORD": "${INFLUXDB_PASSWORD}",
        "DOCKER_INFLUXDB_INIT_ORG": "rdt",
        "DOCKER_INFLUXDB_INIT_BUCKET": "rdt-bucket",
    },
    volumes=["{{ volume_source }}:/var/lib/influxdb2"],
    healthcheck={
        "test": ["CMD", "influx", "ping"],
        "interval": "10s", "timeout": "5s", "retries": 5, "start_period": "30s",
    },
    deploy_limits={"cpus": "1.0", "memory": "512M"},
    strategy="database",
)

# ---------------------------------------------------------------------------
# Search / Logging
# ---------------------------------------------------------------------------
ELASTICSEARCH = ServicePreset(
    name="elasticsearch",
    display_name="Elasticsearch",
    category=CATEGORY_SEARCH,
    image="elasticsearch:8.13.0",
    default_port=9200,
    container_port=9200,
    default_env={
        "discovery.type": "single-node",
        "ELASTIC_PASSWORD": "${ELASTIC_PASSWORD}",
        "xpack.security.enabled": "true",
        "ES_JAVA_OPTS": "-Xms512m -Xmx512m",
    },
    volumes=["{{ volume_source }}:/usr/share/elasticsearch/data"],
    healthcheck={
        "test": ["CMD-SHELL", "curl -s -u elastic:${ELASTIC_PASSWORD} http://localhost:9200/_cluster/health | grep -q '\"status\":\"green\"\\|\"status\":\"yellow\"'"],
        "interval": "15s", "timeout": "10s", "retries": 5, "start_period": "60s",
    },
    deploy_limits={"cpus": "2.0", "memory": "1G"},
    strategy="database",
)

OPENSEARCH = ServicePreset(
    name="opensearch",
    display_name="OpenSearch",
    category=CATEGORY_SEARCH,
    image="opensearchproject/opensearch:2",
    default_port=9201,
    container_port=9200,
    default_env={
        "discovery.type": "single-node",
        "OPENSEARCH_INITIAL_ADMIN_PASSWORD": "${OPENSEARCH_PASSWORD}",
        "OPENSEARCH_JAVA_OPTS": "-Xms512m -Xmx512m",
    },
    volumes=["{{ volume_source }}:/usr/share/opensearch/data"],
    healthcheck={
        "test": ["CMD-SHELL", "curl -sk https://localhost:9200/_cluster/health | grep -q 'green\\|yellow'"],
        "interval": "15s", "timeout": "10s", "retries": 5, "start_period": "60s",
    },
    deploy_limits={"cpus": "2.0", "memory": "1G"},
    strategy="database",
)

LOGSTASH = ServicePreset(
    name="logstash",
    display_name="Logstash",
    category=CATEGORY_SEARCH,
    image="docker.elastic.co/logstash/logstash:8.13.0",
    default_port=5044,
    container_port=5044,
    default_env={
        "LS_JAVA_OPTS": "-Xms512m -Xmx512m",
        "PIPELINE_WORKERS": "2",
    },
    volumes=[
        "./logstash/pipeline:/usr/share/logstash/pipeline:ro",
        "./logstash/config/logstash.yml:/usr/share/logstash/config/logstash.yml:ro",
        "logstash_data:/usr/share/logstash/data",
    ],
    healthcheck={
        "test": ["CMD-SHELL", "curl -s http://localhost:9600/_node/stats | grep -q '\"status\":\"green\"'"],
        "interval": "15s", "timeout": "10s", "retries": 5, "start_period": "60s",
    },
    deploy_limits={"cpus": "1.0", "memory": "1G"},
    strategy="database",
    depends_on_category=CATEGORY_SEARCH,
    artifacts=[
        ArtifactDef(
            relative_path="logstash/pipeline/logstash.conf",
            source_template="logstash/logstash-beats-stdout.conf.j2",
            overwrite=OverwritePolicy.SKIP,
            condition="logstash_pipeline_stdout",
        ),
        ArtifactDef(
            relative_path="logstash/pipeline/logstash.conf",
            source_template="logstash/logstash-beats-es.conf.j2",
            overwrite=OverwritePolicy.SKIP,
            condition="logstash_pipeline_es",
        ),
        ArtifactDef(
            relative_path="logstash/config/logstash.yml",
            source_template="logstash/logstash.yml.j2",
            overwrite=OverwritePolicy.SKIP,
        ),
    ],
    scaffolds=[
        DirectoryDef(relative_path="logstash/pipeline"),
        DirectoryDef(relative_path="logstash/config"),
    ],
    bootstrap_hints=[
        BootstrapHint(
            message="Настройте Filebeat/Beats-агент для отправки данных на порт 5044 этого хоста.",
            command="docker exec -it logstash curl -s http://localhost:9600/_node/stats | python -m json.tool",
        ),
        BootstrapHint(
            message="Проверьте статус Logstash: убедитесь что pipeline активен и нет ошибок.",
        ),
    ],
)

FILEBEAT = ServicePreset(
    name="filebeat",
    display_name="Filebeat",
    category=CATEGORY_SEARCH,
    image="docker.elastic.co/beats/filebeat:8.13.0",
    default_port=5066,
    container_port=5066,
    default_env={},
    volumes=[
        "./filebeat/filebeat.yml:/usr/share/filebeat/filebeat.yml:ro",
        "filebeat_data:/usr/share/filebeat/data",
    ],
    healthcheck={
        "test": ["CMD-SHELL", "curl -s http://localhost:5066/?pretty | grep -q '\"beat\"'"],
        "interval": "15s", "timeout": "10s", "retries": 5, "start_period": "30s",
    },
    deploy_limits={"cpus": "0.5", "memory": "256M"},
    strategy="database",
    depends_on_category=CATEGORY_SEARCH,
    artifacts=[
        ArtifactDef(
            relative_path="filebeat/filebeat.yml",
            source_template="filebeat/filebeat-logstash.yml.j2",
            overwrite=OverwritePolicy.SKIP,
            condition="filebeat_output_logstash",
        ),
        ArtifactDef(
            relative_path="filebeat/filebeat.yml",
            source_template="filebeat/filebeat-es.yml.j2",
            overwrite=OverwritePolicy.SKIP,
            condition="filebeat_output_es",
        ),
        ArtifactDef(
            relative_path="filebeat/filebeat.yml",
            source_template="filebeat/filebeat-stdout.yml.j2",
            overwrite=OverwritePolicy.SKIP,
            condition="filebeat_output_stdout",
        ),
    ],
    scaffolds=[
        DirectoryDef(relative_path="filebeat"),
    ],
    bootstrap_hints=[
        BootstrapHint(
            message="Filebeat runs as root inside the container to access log files. "
                    "Make sure the mounted filebeat.yml is owned by root:root with mode 0600 "
                    "or Filebeat will refuse to load it.",
        ),
        BootstrapHint(
            message="To ship Docker container logs, add a volume: "
                    "/var/lib/docker/containers:/var/lib/docker/containers:ro "
                    "and configure a filestream input with the correct path.",
        ),
        BootstrapHint(
            message="Check Filebeat status and loaded config:",
            command="docker exec -it filebeat filebeat test config -e",
        ),
    ],
)

KIBANA = ServicePreset(
    name="kibana",
    display_name="Kibana",
    category=CATEGORY_SEARCH,
    image="kibana:8.13.0",
    default_port=5601,
    container_port=5601,
    default_env={
        "ELASTICSEARCH_HOSTS": "http://elasticsearch:9200",
        "ELASTICSEARCH_USERNAME": "kibana_system",
        "ELASTICSEARCH_PASSWORD": "${KIBANA_SYSTEM_PASSWORD}",
        "XPACK_SECURITY_ENCRYPTIONKEY": "${KIBANA_ENCRYPTION_KEY}",
    },
    volumes=[],
    healthcheck={
        "test": ["CMD-SHELL", "curl -s http://localhost:5601/api/status | grep -q '\"level\":\"available\"'"],
        "interval": "15s", "timeout": "10s", "retries": 5, "start_period": "90s",
    },
    deploy_limits={"cpus": "1.0", "memory": "1G"},
    strategy="base",
    depends_on_category=CATEGORY_SEARCH,
    bootstrap_hints=[
        BootstrapHint(
            message="Kibana connects as the 'kibana_system' user. Set its password in Elasticsearch before starting Kibana:",
            command='docker exec -it elasticsearch curl -s -u elastic:${ELASTIC_PASSWORD} -X POST "http://localhost:9200/_security/user/kibana_system/_password" -H "Content-Type: application/json" -d \'{"password": "${KIBANA_SYSTEM_PASSWORD}"}\'',
        ),
    ],
)

# ---------------------------------------------------------------------------
# Message Brokers
# ---------------------------------------------------------------------------
KAFKA_KRAFT = ServicePreset(
    name="kafka",
    display_name="Kafka (KRaft)",
    category=CATEGORY_BROKER,
    image="apache/kafka:3.7.0",
    default_port=9092,
    container_port=9092,
    default_env={
        "KAFKA_NODE_ID": "1",
        "KAFKA_PROCESS_ROLES": "broker,controller",
        "KAFKA_LISTENERS": "PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093",
        "KAFKA_ADVERTISED_LISTENERS": "PLAINTEXT://localhost:9092",
        "KAFKA_CONTROLLER_QUORUM_VOTERS": "1@localhost:9093",
        "KAFKA_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
        "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP": "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
        "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
        "CLUSTER_ID": "MkU3OEVBNTcwNTJENDM2Qk",
    },
    volumes=["{{ volume_source }}:/var/lib/kafka/data"],
    healthcheck={
        "test": ["CMD-SHELL", "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list"],
        "interval": "15s", "timeout": "10s", "retries": 5, "start_period": "30s",
    },
    deploy_limits={"cpus": "1.0", "memory": "1G"},
    strategy="database",
)

RABBITMQ = ServicePreset(
    name="rabbitmq",
    display_name="RabbitMQ",
    category=CATEGORY_BROKER,
    image="rabbitmq:3-management-alpine",
    default_port=5672,
    container_port=5672,
    default_env={
        "RABBITMQ_DEFAULT_USER": "${RABBITMQ_USER}",
        "RABBITMQ_DEFAULT_PASS": "${RABBITMQ_PASSWORD}",
    },
    volumes=["{{ volume_source }}:/var/lib/rabbitmq"],
    healthcheck={
        "test": ["CMD", "rabbitmq-diagnostics", "ping"],
        "interval": "10s", "timeout": "5s", "retries": 5, "start_period": "30s",
    },
    deploy_limits={"cpus": "1.0", "memory": "512M"},
    strategy="database",
)

# ---------------------------------------------------------------------------
# Identity / Auth
# ---------------------------------------------------------------------------
KEYCLOAK = ServicePreset(
    name="keycloak",
    display_name="Keycloak",
    category=CATEGORY_AUTH,
    image="quay.io/keycloak/keycloak:24.0",
    default_port=8080,
    container_port=8080,
    default_env={
        "KEYCLOAK_ADMIN": "${KEYCLOAK_ADMIN}",
        "KEYCLOAK_ADMIN_PASSWORD": "${KEYCLOAK_ADMIN_PASSWORD}",
        "KC_DB": "postgres",
        "KC_DB_URL": "jdbc:postgresql://postgres:5432/${POSTGRES_DB}",
        "KC_DB_USERNAME": "${POSTGRES_USER}",
        "KC_DB_PASSWORD": "${POSTGRES_PASSWORD}",
        "KC_HOSTNAME": "localhost",
    },
    volumes=[],
    healthcheck={
        "test": ["CMD-SHELL", "curl -f http://localhost:8080/health/ready || exit 1"],
        "interval": "15s", "timeout": "10s", "retries": 5, "start_period": "60s",
    },
    deploy_limits={"cpus": "1.0", "memory": "1G"},
    strategy="base",
)

# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------
PROMETHEUS = ServicePreset(
    name="prometheus",
    display_name="Prometheus",
    category=CATEGORY_MONITORING,
    image="prom/prometheus:v2.52.0",
    default_port=9090,
    container_port=9090,
    default_env={},
    volumes=["{{ volume_source }}:/prometheus", "./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro"],
    healthcheck={
        "test": ["CMD-SHELL", "wget -qO- http://localhost:9090/-/healthy | grep -q 'Prometheus'"],
        "interval": "10s", "timeout": "5s", "retries": 5,
    },
    deploy_limits={"cpus": "0.5", "memory": "256M"},
    strategy="monitoring",
    artifacts=[
        ArtifactDef(
            relative_path="prometheus/prometheus.yml",
            source_template="prometheus/prometheus.yml.j2",
            overwrite=OverwritePolicy.SKIP,
        ),
    ],
    scaffolds=[
        DirectoryDef(relative_path="prometheus"),
    ],
)

GRAFANA = ServicePreset(
    name="grafana",
    display_name="Grafana",
    category=CATEGORY_MONITORING,
    image="grafana/grafana:10.4.2",
    default_port=3000,
    container_port=3000,
    default_env={
        "GF_SECURITY_ADMIN_USER": "${GRAFANA_USER}",
        "GF_SECURITY_ADMIN_PASSWORD": "${GRAFANA_PASSWORD}",
        "GF_USERS_ALLOW_SIGN_UP": "false",
    },
    volumes=["{{ volume_source }}:/var/lib/grafana"],
    healthcheck={
        "test": ["CMD-SHELL", "curl -f http://localhost:3000/api/health || exit 1"],
        "interval": "10s", "timeout": "5s", "retries": 5,
    },
    deploy_limits={"cpus": "0.5", "memory": "256M"},
    strategy="monitoring",
    depends_on_category=CATEGORY_MONITORING,
)

ZOOKEEPER = ServicePreset(
    name="zookeeper",
    display_name="Zookeeper",
    category=CATEGORY_MONITORING,
    image="confluentinc/cp-zookeeper:7.6.1",
    default_port=2181,
    container_port=2181,
    default_env={
        "ZOOKEEPER_CLIENT_PORT": "2181",
        "ZOOKEEPER_TICK_TIME": "2000",
    },
    volumes=["{{ volume_source }}:/var/lib/zookeeper/data"],
    healthcheck={
        "test": ["CMD-SHELL", "echo ruok | nc localhost 2181 | grep imok"],
        "interval": "10s", "timeout": "5s", "retries": 5,
    },
    deploy_limits={"cpus": "0.5", "memory": "256M"},
    strategy="monitoring",
)

# ---------------------------------------------------------------------------
# Admin Tools
# ---------------------------------------------------------------------------
PGADMIN = ServicePreset(
    name="pgadmin",
    display_name="pgAdmin",
    category=CATEGORY_ADMIN,
    image="dpage/pgadmin4:8",
    default_port=5050,
    container_port=80,
    default_env={
        "PGADMIN_DEFAULT_EMAIL": "${PGADMIN_EMAIL}",
        "PGADMIN_DEFAULT_PASSWORD": "${PGADMIN_PASSWORD}",
        "PGADMIN_CONFIG_SERVER_MODE": "False",
    },
    volumes=[],
    healthcheck=None,
    deploy_limits={"cpus": "0.5", "memory": "256M"},
    strategy="admin_tool",
    depends_on_category=CATEGORY_RELATIONAL,
)

PHPMYADMIN = ServicePreset(
    name="phpmyadmin",
    display_name="phpMyAdmin",
    category=CATEGORY_ADMIN,
    image="phpmyadmin:5",
    default_port=5051,
    container_port=80,
    default_env={
        "PMA_HOST": "mysql",
        "PMA_PORT": "3306",
        "MYSQL_ROOT_PASSWORD": "${MYSQL_ROOT_PASSWORD}",
    },
    volumes=[],
    healthcheck=None,
    deploy_limits={"cpus": "0.5", "memory": "256M"},
    strategy="admin_tool",
    depends_on_category=CATEGORY_RELATIONAL,
)

KAFKA_UI = ServicePreset(
    name="kafka-ui",
    display_name="Kafka UI",
    category=CATEGORY_ADMIN,
    image="provectuslabs/kafka-ui:latest",
    default_port=8090,
    container_port=8080,
    default_env={
        "KAFKA_CLUSTERS_0_NAME": "kafka",
        "KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS": "kafka:9092",
    },
    volumes=[],
    healthcheck=None,
    deploy_limits={"cpus": "0.5", "memory": "256M"},
    strategy="admin_tool",
    depends_on_category=CATEGORY_BROKER,
)

MONGO_EXPRESS = ServicePreset(
    name="mongo-express",
    display_name="Mongo Express",
    category=CATEGORY_ADMIN,
    image="mongo-express:1",
    default_port=8081,
    container_port=8081,
    default_env={
        "ME_CONFIG_MONGODB_ADMINUSERNAME": "${MONGO_USER}",
        "ME_CONFIG_MONGODB_ADMINPASSWORD": "${MONGO_PASSWORD}",
        "ME_CONFIG_MONGODB_URL": "mongodb://${MONGO_USER}:${MONGO_PASSWORD}@mongodb:27017/",
        "ME_CONFIG_BASICAUTH": "false",
    },
    volumes=[],
    healthcheck=None,
    deploy_limits={"cpus": "0.5", "memory": "128M"},
    strategy="admin_tool",
    depends_on_category=CATEGORY_NOSQL,
)

# ---------------------------------------------------------------------------
# Web Servers
# ---------------------------------------------------------------------------

NGINX_PROXY = ServicePreset(
    name="nginx-proxy",
    display_name="Nginx (Reverse Proxy)",
    category=CATEGORY_WEB,
    image="nginx:stable-alpine",
    default_port=80,
    container_port=80,
    default_env={},
    volumes=[],
    healthcheck=None,          # healthcheck задаётся в WebServerStrategy
    deploy_limits={"cpus": "0.5", "memory": "128M"},
    strategy="web_server",
    artifacts=[
        ArtifactDef(
            relative_path="nginx/nginx.conf",
            source_template="nginx/nginx-proxy.conf.j2",
            overwrite=OverwritePolicy.SKIP,
        ),
    ],
)

NGINX_STATIC = ServicePreset(
    name="nginx-static",
    display_name="Nginx (Static Files Server)",
    category=CATEGORY_WEB,
    image="nginx:stable-alpine",
    default_port=80,
    container_port=80,
    default_env={},
    volumes=[],
    healthcheck=None,
    deploy_limits={"cpus": "0.5", "memory": "128M"},
    strategy="web_server",
    artifacts=[
        ArtifactDef(
            relative_path="nginx/nginx.conf",
            source_template="nginx/nginx-static.conf.j2",
            overwrite=OverwritePolicy.SKIP,
        ),
    ],
)

NGINX_SPA = ServicePreset(
    name="nginx-spa",
    display_name="Nginx (SPA Hosting)",
    category=CATEGORY_WEB,
    image="nginx:stable-alpine",
    default_port=80,
    container_port=80,
    default_env={},
    volumes=[],
    healthcheck=None,
    deploy_limits={"cpus": "0.5", "memory": "128M"},
    strategy="web_server",
    artifacts=[
        ArtifactDef(
            relative_path="nginx/nginx.conf",
            source_template="nginx/nginx-spa.conf.j2",
            overwrite=OverwritePolicy.SKIP,
        ),
    ],
)

APACHE_STATIC = ServicePreset(
    name="apache-static",
    display_name="Apache (Static Files Server)",
    category=CATEGORY_WEB,
    image="httpd:alpine",
    default_port=80,
    container_port=80,
    default_env={},
    volumes=[],
    healthcheck=None,          # healthcheck задаётся в WebServerStrategy
    deploy_limits={"cpus": "0.5", "memory": "128M"},
    strategy="web_server",
    artifacts=[
        ArtifactDef(
            relative_path="apache/httpd.conf",
            source_template="apache/httpd-static.conf.j2",
            overwrite=OverwritePolicy.SKIP,
        ),
    ],
)

APACHE_PHP = ServicePreset(
    name="apache-php",
    display_name="Apache + PHP (LAMP)",
    category=CATEGORY_WEB,
    image="php:apache",
    default_port=80,
    container_port=80,
    default_env={},
    volumes=[],
    healthcheck=None,
    deploy_limits={"cpus": "1.0", "memory": "256M"},
    strategy="web_server",
    artifacts=[
        ArtifactDef(
            relative_path="apache/vhost.conf",
            source_template="apache/vhost-php.conf.j2",
            overwrite=OverwritePolicy.SKIP,
        ),
    ],
)

SEQ = ServicePreset(
    name="seq",
    display_name="Seq (Structured Logs)",
    category=CATEGORY_SEARCH,
    image="datalust/seq:latest",
    default_port=5341,
    container_port=80,
    default_env={
        "ACCEPT_EULA": "Y",
        "SEQ_FIRSTRUN_ADMINPASSWORDHASH": "${SEQ_ADMIN_PASSWORD_HASH}",
    },
    volumes=["{{ volume_source }}:/data"],
    healthcheck={
        "test": ["CMD-SHELL", "curl -sf http://localhost/api || exit 1"],
        "interval": "10s", "timeout": "5s", "retries": 5, "start_period": "30s",
    },
    deploy_limits={"cpus": "0.5", "memory": "512M"},
    strategy="database",
    bootstrap_hints=[
        BootstrapHint(
            message="Seq UI is available at http://localhost:5341. On first run the admin password hash must be set. Generate it with: echo -n 'yourpassword' | sha256sum",
        ),
    ],
)

TRAEFIK = ServicePreset(
    name="traefik",
    display_name="Traefik (Reverse Proxy / Load Balancer)",
    category=CATEGORY_WEB,
    image="traefik:v3.0",
    default_port=80,
    container_port=80,
    default_env={},
    volumes=[],                 # volumes управляются TraefikStrategy
    healthcheck=None,           # healthcheck задаётся в TraefikStrategy
    deploy_limits={"cpus": "0.5", "memory": "128M"},
    strategy="traefik",
    artifacts=[
        ArtifactDef(
            relative_path="traefik/traefik.yml",
            source_template="traefik/traefik.yml.j2",
            overwrite=OverwritePolicy.SKIP,
        ),
    ],
    scaffolds=[
        DirectoryDef(relative_path="traefik"),
        DirectoryDef(relative_path="traefik/dynamic"),
    ],
    bootstrap_hints=[
        BootstrapHint(
            message="Traefik Dashboard доступен на http://localhost:8080/dashboard/ "
                    "(по умолчанию insecure-режим). В production отключите insecure и настройте аутентификацию.",
        ),
        BootstrapHint(
            message="Чтобы Traefik обнаруживал ваши сервисы, добавьте к ним labels:\n"
                    "  traefik.enable=true\n"
                    "  traefik.http.routers.<name>.rule=Host(`your.domain`)\n"
                    "  traefik.http.services.<name>.loadbalancer.server.port=<port>",
        ),
        BootstrapHint(
            message="Просмотр активных маршрутов и middleware:",
            command="docker exec -it traefik wget -qO- http://localhost:8080/api/http/routers | python -m json.tool",
        ),
    ],
)

# ---------------------------------------------------------------------------
# Реестр всех пресетов
# ---------------------------------------------------------------------------
ALL_PRESETS: dict[str, ServicePreset] = {
    p.name: p for p in [
        NGINX_PROXY, NGINX_STATIC, NGINX_SPA,
        APACHE_STATIC, APACHE_PHP,
        TRAEFIK,
        POSTGRES, MYSQL, MARIADB, MSSQL, ORACLE,
        MONGODB, REDIS, VALKEY, CASSANDRA, INFLUXDB,
        ELASTICSEARCH, OPENSEARCH, LOGSTASH, FILEBEAT, KIBANA,
        KAFKA_KRAFT, RABBITMQ,
        KEYCLOAK,
        PROMETHEUS, GRAFANA, ZOOKEEPER,
        PGADMIN, PHPMYADMIN, KAFKA_UI, MONGO_EXPRESS,
        SEQ,
    ]
}


