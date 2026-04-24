# RDT — Scripting Reference

> **Rambo Docker Tools** — `docker-compose.yml` generator.  
> All commands support non-interactive mode, making RDT easy to use in scripts and automation.

---

## Table of Contents

- [General Rules](#general-rules)
- [rdt init](#rdt-init)
- [rdt add](#rdt-add)
  - [Flags](#flags)
  - [Network behaviour](#network-behaviour---network)
  - [Examples](#examples-1)
- [rdt list](#rdt-list)
- [rdt up](#rdt-up)
- [rdt check](#rdt-check)
- [rdt remove](#rdt-remove)
- [rdt doctor](#rdt-doctor)
- [rdt lang](#rdt-lang)
- [Typical Workflow](#typical-workflow)

---

## General Rules

- Running `rdt` **without arguments** opens the interactive menu.
- Any command can be executed **directly**, bypassing the menu:  
  `rdt <command> [options]`
- The `--help` flag is available for every command:  
  `rdt --help`, `rdt add --help`, `rdt init --help`, …
- The interface language is set via the `RDT_LANG` environment variable or by running `rdt lang set <code>`.

---

## rdt init

Creates a base `docker-compose.yml` with the `rambo-net` network.  
Also creates empty `.env` and `.env.example` files if they are absent.

```bash
rdt init [OPTIONS]
```

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Path to the output file |
| `--force` | — | `bool` | `False` | Overwrite if the file already exists |

### Examples

```bash
# Initialise a project in the current directory
rdt init

# Use a custom file path
rdt init --file infra/compose.yml

# Overwrite an existing file
rdt init --force
```

---

## rdt add

Adds a service to `docker-compose.yml`.

```bash
rdt add <SERVICE> [OPTIONS]
```

**`<SERVICE>`** — service name (case-insensitive). Full list: `rdt list`.

> By default the interactive setup wizard is launched.  
> Use **`--yes`** (`-y`) to skip all questions and apply default values.

### Flags

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--yes` | `-y` | `bool` | `False` | Skip wizard, use default values |
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Path to the compose file |
| `--hardcore` | — | `bool` | `False` | Generate unique random passwords instead of `.env` placeholders |
| `--port` | `-p` | `INT` | preset port | External (host) port for the service |
| `--volume` | — | `TEXT` | `<service>_data` | Volume name or host path (e.g. `./data/pg`, `my_vol`) |
| `--no-ports` | — | `bool` | `False` | Do not publish ports outside the Docker network |
| `--network` | — | `TEXT` | `bridge` | Network type or name: `bridge` \| `host` \| `none` \| `<external-net>` |
| `--depends-on` | — | `TEXT` (repeat) | — | Service dependency; can be specified multiple times |
| `--container-name` | — | `TEXT` | service name | Explicit container name |
| `--hc-interval` | — | `TEXT` | preset value | Healthcheck interval (e.g. `10s`) |
| `--hc-timeout` | — | `TEXT` | preset value | Healthcheck timeout (e.g. `5s`) |
| `--hc-retries` | — | `INT` | preset value | Healthcheck retry count |
| `--hc-start-period` | — | `TEXT` | preset value | Healthcheck start period (e.g. `30s`) |
| `--set` | — | `TEXT` (repeat) | — | Override any wizard answer as `key=value`; can be specified multiple times |

### Network behaviour (`--network`)

| Value | Result |
|-------|--------|
| `bridge` (default) | Isolated `rambo-net` network |
| `host` | Use the host network stack |
| `none` | No network |
| `<name>` | Attach to an existing external network |

### Examples

```bash
# Add PostgreSQL with default settings (no prompts)
rdt add postgres --yes

# Custom port and data path
rdt add postgres --yes --port 5433 --volume ./data/pg

# Generate unique passwords
rdt add postgres --yes --hardcore

# Redis without publishing its port to the host
rdt add redis --yes --no-ports

# Kafka UI depending on the kafka service
rdt add kafka-ui --yes --depends-on kafka

# Multiple dependencies
rdt add redis --yes --depends-on rdt-postgres --depends-on rdt-rabbitmq

# Connect to an existing external network
rdt add postgres --yes --network my-project-net

# Override the container name
rdt add postgres --yes --container-name pg-main

# Custom healthcheck parameters
rdt add postgres --yes --hc-interval 15s --hc-timeout 10s --hc-retries 3 --hc-start-period 60s

# Specify a custom compose file path
rdt add mysql --yes --file infra/compose.yml

# Override wizard answers with --set (e.g. for Nginx upstream)
rdt add nginx-proxy --yes --set nginx_upstream=app:8080 --set nginx_server_name=example.com
```

---

## rdt list

Prints a table of all available service presets grouped by category.

```bash
rdt list
```

No flags. Read-only — does not modify anything.

---

## rdt up

Starts containers via `docker compose up` (proxy command).

```bash
rdt up [OPTIONS]
```

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Path to the compose file |
| `--detach` / `--no-detach` | `-d` | `bool` | `True` (detach) | Run in detached (background) mode |

### Examples

```bash
# Start in the background (default)
rdt up

# Start in foreground (stream logs to the terminal)
rdt up --no-detach

# Use a custom compose file
rdt up --file infra/compose.yml
```

---

## rdt check

Validates `docker-compose.yml` by running `docker compose config`.
Detects YAML syntax errors, unknown keys, and invalid references before you start the stack.

```bash
rdt check [OPTIONS]
```

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Path to the compose file |
| `--verbose` | `-v` | `bool` | `False` | Print the resolved compose config on success |

### Examples

```bash
# Validate the default file
rdt check

# Print the full resolved config on success
rdt check --verbose

# Validate a custom file
rdt check --file infra/compose.yml
```

Returns exit code **0** on success or a **non-zero** code on failure.

---

## rdt remove

Removes a service from `docker-compose.yml`.
Optionally cleans up orphaned environment variables and companion config files.

```bash
rdt remove [SERVICE] [OPTIONS]
```

**`[SERVICE]`** — service name (optional). If omitted, an interactive list is shown.

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--yes` | `-y` | `bool` | `False` | Skip all confirmation prompts |
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Path to the compose file |
| `--clean-env` | — | `bool` | `False` | Remove orphaned `.env` / `.env.example` variables |
| `--clean-artifacts` | — | `bool` | `False` | Delete companion config files generated for the service |

### Examples

```bash
# Interactive service selection
rdt remove

# Remove a specific service (with confirmation prompts)
rdt remove postgres

# Remove and clean up env vars
rdt remove postgres --clean-env

# Remove, clean env vars and companion files, no prompts
rdt remove postgres --yes --clean-env --clean-artifacts

# Target a custom compose file
rdt remove mysql --file infra/compose.yml
```

---

## rdt doctor

Runs a full health check of your Docker project and prints a diagnostic report.

```bash
rdt doctor [OPTIONS]
```

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--file` | `-f` | `PATH` | `docker-compose.yml` | Path to the compose file |

### Checks performed

| Check | What it verifies |
|-------|-----------------|
| `docker` | Docker daemon is reachable |
| `compose` | Docker Compose v2 is available |
| `compose_valid` | File passes `docker compose config` |
| `env_vars` | All `${VAR}` references in compose are set in `.env` |
| `port_conflicts` | Mapped host ports are not already in use |
| `dangling_deps` | `depends_on` only references existing services |
| `companion_files` | Bind-mounted config files exist on disk |

Exit code **0** if no errors; **non-zero** if any check has `error` status.

### Examples

```bash
# Check the default compose file
rdt doctor

# Check a custom compose file
rdt doctor --file infra/compose.yml
```

---

## rdt lang

Manages the RDT interface language.
The setting is saved to `~/.rdt/config.json` and applied on every run.
Priority: `RDT_LANG` env var > `~/.rdt/config.json` > built-in default (`en`).

```bash
rdt lang [ACTION] [VALUE]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `ACTION` | No | `list` — show current and available languages; `set` — change language |
| `VALUE` | Only with `set` | Language code (e.g. `ru`, `en`) |

### Examples

```bash
# Interactive language selection
rdt lang

# Show current language and available options
rdt lang list

# Switch to Russian
rdt lang set ru

# Switch to English
rdt lang set en

# Override language for a single command (not saved)
RDT_LANG=ru rdt add postgres --yes
```

### Available languages

| Code | Language |
|------|----------|
| `en` | English |
| `ru` | Russian |

---

## Typical Workflow

```bash
#!/usr/bin/env bash
set -e

# 1. Initialise the project
rdt init

# 2. Add PostgreSQL with unique passwords
rdt add postgres --yes --hardcore --port 5432 --volume ./data/pg

# 3. Add Redis without publishing its port
rdt add redis --yes --no-ports --depends-on postgres

# 4. Add pgAdmin connected to postgres
rdt add pgadmin --yes --depends-on postgres

# 5. Run diagnostics (env vars, port conflicts, companion files)
rdt doctor

# 6. Validate the compose syntax
rdt check

# 7. Start the stack
rdt up
```
