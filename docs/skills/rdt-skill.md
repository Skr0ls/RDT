# RDT (Rambo Docker Tools) — Agentic Skill

## Context
You have access to the `rdt` CLI tool, a fast generator for production-ready `docker-compose.yml` configurations. It automates container definitions, `.env` file management, network setup, volumes, resource limits, healthchecks, and scaffolding of companion configuration files (like `nginx.conf`, `prometheus.yml`, etc.).

**CRITICAL INSTRUCTION:** As an AI agent, you must **NEVER** run `rdt` interactively. You must ALWAYS use the `--yes` (`-y`) flag for commands that modify state (`add`, `remove`), and pass all required configuration via command-line arguments.

## Commands API

### `rdt init`
Initializes a new `docker-compose.yml` file, a `.env` file, and a `.env.example` file.
```bash
rdt init
rdt init --force  # Overwrite existing files
```

### `rdt add <service>`
Adds a service to the `docker-compose.yml` file and creates necessary companion files.
**Mandatory flag:** `--yes`

**Options:**
- `--port <int>`: Override the default external host port.
- `--volume <string>`: Specify a named volume or local path (e.g. `./data/pg`).
- `--depends-on <service>`: Make the service depend on another service. (Repeatable).
- `--hardcore`: Generate strong, unique random passwords in the `.env` file.
- `--no-ports`: Only expose ports within the Docker network, not to the host.
- `--network <string>`: Specify the network (`bridge`, `host`, `none`, or external name).
- `--container-name <string>`: Set an explicit container name.
- `--set <key=value>`: Override any internal wizard variable (e.g. `nginx_upstream=app:8080`). (Repeatable).
- `--file <path>`: Target a specific compose file instead of the default.
- `--hc-interval`, `--hc-timeout`, `--hc-retries`, `--hc-start-period`: Customize healthcheck parameters.

**Example:**
```bash
rdt add postgres --yes --hardcore --port 5433 --volume ./data/pg
rdt add pgadmin --yes --depends-on postgres --no-ports
```

### `rdt remove <service>`
Removes a service from the `docker-compose.yml` file.
**Mandatory flag:** `--yes`

**Options:**
- `--clean-env`: Clean up orphaned variables from the `.env` file.
- `--clean-artifacts`: Delete associated configuration files (e.g., `nginx.conf`, `prometheus.yml`) that were generated specifically for the service.

**Example:**
```bash
rdt remove postgres --yes --clean-env --clean-artifacts
```

### `rdt check` & `rdt doctor`
Diagnostics and validation tools.
- `rdt check`: Validates the syntax of the generated `docker-compose.yml` via `docker compose config`.
- `rdt doctor`: Runs a comprehensive diagnostic check (Docker daemon, compose availability, compose validity, `.env` variables completeness, port conflicts, dangling dependencies, and companion files). **Always run `rdt doctor` before finishing your task.**

**Error Recovery:** If `rdt doctor` or `rdt check` reports an error, analyze the output, make the necessary corrections (using `rdt add` with `--set`, or `rdt remove`), and run the check again.

### `rdt list`
Displays all available service presets (read-only command). Useful to check exact service names and default ports.

## Best Practices & Guidelines

### Reading Current State
Because the CLI output focuses on what it just added, you might lose track of what services are currently configured during a long conversation.
To understand the current state of the stack, simply **read the `docker-compose.yml`** file in the project root. This is your primary source of truth for deployed services.

### Handling Secrets
When you use the `--hardcore` flag, `rdt` automatically generates secure, random credentials inside the `.env` file.
If you need those credentials to configure another app or to give the user connection details, it is perfectly fine and encouraged to **read the `.env` file** to retrieve them.

## Supported Services
* **Web Servers:** `nginx-proxy`, `nginx-static`, `nginx-spa`, `apache-static`, `apache-php`, `traefik`
* **Databases:** `postgres`, `mysql`, `mariadb`, `mssql`, `oracle`
* **NoSQL / Cache:** `mongodb`, `redis`, `valkey`, `cassandra`, `influxdb`
* **Search / Logging:** `elasticsearch`, `opensearch`, `logstash`, `filebeat`, `kibana`, `seq`
* **Message Brokers:** `kafka`, `rabbitmq`
* **Identity / Auth:** `keycloak`
* **Monitoring:** `prometheus`, `grafana`, `zookeeper`
* **Admin Tools:** `pgadmin`, `phpmyadmin`, `kafka-ui`, `mongo-express`

## Standard AI Agent Workflow
1. Run `rdt init` to set up the base files.
2. Run `rdt add <service> --yes` with required flags to define the architecture. Link services using `--depends-on`. Use `--no-ports` for backend services that should not be exposed directly to the host.
3. Run `rdt doctor` to ensure the generated configuration is completely valid and ports are available. Apply corrections if any errors appear.
4. Run `rdt check` for final YAML verification.
5. Provide the user with any generated credentials (read from `.env`) and instruct them to start the stack themselves using `rdt up`. Do not run `rdt up` unless explicitly requested.
