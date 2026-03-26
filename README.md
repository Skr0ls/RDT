# 🐳 Rambo Docker Tools (RDT)

**RDT** is a CLI tool for generating production-ready `docker-compose.yml` files in seconds. Pick a service, answer a few questions (or skip them entirely with `--yes`), and RDT writes the compose block, volumes, healthchecks, resource limits, and `.env` variables for you.

---

## Features

- **Interactive wizard** — guided prompts for port, volume, credentials, and dependencies
- **Script mode** — fully non-interactive via flags (`--yes`, `--port`, `--volume`, etc.)
- **20+ service presets** across 7 categories (see [Available Services](#available-services))
- **Smart Mapping** — automatically detects and links related services (e.g. pgAdmin → PostgreSQL, Grafana → Prometheus)
- **`.env` / `.env.example` generation** — credentials are written to environment files automatically
- **Resource limits** — every service ships with sane CPU and RAM caps
- **Healthchecks** — databases and brokers include ready-to-use healthcheck configs
- **Multi-language UI** — English and Russian, switchable at any time

---

## Available Services

| Category | Services |
|---|---|
| **Relational DB** | PostgreSQL, MySQL, MariaDB, MS SQL Server, Oracle |
| **NoSQL / Cache** | MongoDB, Redis, Valkey, Cassandra, InfluxDB |
| **Search / Logging** | Elasticsearch, OpenSearch |
| **Message Brokers** | Kafka (KRaft), RabbitMQ |
| **Identity / Auth** | Keycloak |
| **Monitoring** | Prometheus, Grafana, Zookeeper |
| **Admin Tools** | pgAdmin, phpMyAdmin, Kafka UI, Mongo Express |

Run `rdt list` at any time to see the full list with images and default ports.

---

## Installation

### Prerequisites

- Python **3.10+**
- Docker & Docker Compose (required only for the `rdt up` command)

---

### Option 1 — pipx (recommended for CLI tools)

[pipx](https://pipx.pypa.io) installs CLI tools in isolated environments and makes them available system-wide — no manual venv needed.

```bash
# Install pipx if you don't have it
pip install pipx
pipx ensurepath   # add pipx bin dir to PATH (restart terminal after)

# Install RDT from PyPI
pipx install rdt-rambo

# Or install directly from GitHub (no PyPI account needed)
pipx install git+https://github.com/Skr0ls/RDT.git
```

---

### Option 2 — pip (inside a virtual environment)

```bash
# From PyPI
pip install rdt-rambo

# Or from GitHub
pip install git+https://github.com/Skr0ls/RDT.git
```

---

### Option 3 — from source (for development)

```bash
# 1. Clone the repository
git clone https://github.com/Skr0ls/RDT.git
cd RDT

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

# 3. Install in editable mode with all dependencies
pip install -e .
```

---

### Verify installation

```bash
rdt --version
rdt --help
```

---

### Publishing a new release to PyPI

> For maintainers only.

```bash
# 1. Install build tools
pip install build twine

# 2. Build the distribution packages
python -m build
# → creates dist/rdt_rambo-X.Y.Z.tar.gz and dist/rdt_rambo-X.Y.Z-py3-none-any.whl

# 3. Upload to PyPI
twine upload dist/*
# You will be prompted for your PyPI API token

# Or upload to TestPyPI first to verify
twine upload --repository testpypi dist/*
```

After upload, users can install with `pipx install rdt-rambo` or `pip install rdt-rambo`.

---

## 🖥️ Usage

### Interactive mode

Run `rdt` with no arguments to open the interactive menu:

```bash
rdt
```

Use the arrow keys to navigate and `Enter` to confirm. The menu offers all commands described below.

---

### Commands

#### `rdt init` — Initialize a project

Creates a base `docker-compose.yml` with the shared `rambo-net` network.

```bash
rdt init                        # create docker-compose.yml in the current directory
rdt init --file my-compose.yml  # custom file name
rdt init --force                # overwrite an existing file
```

---

#### `rdt add <service>` — Add a service

Adds a configured service block to `docker-compose.yml` and writes credentials to `.env`.

```bash
# Interactive wizard (default)
rdt add postgres

# Script mode — use all defaults, no prompts
rdt add postgres --yes

# Custom port and volume path
rdt add postgres --yes --port 5433 --volume ./data/pg

# Add Redis and declare it depends on Postgres
rdt add redis --yes --depends-on postgres

# Generate unique random passwords instead of placeholders
rdt add postgres --hardcore --yes

# Target a custom compose file
rdt add mysql --yes --file infra/docker-compose.yml
```

| Flag | Short | Description |
|---|---|---|
| `--yes` | `-y` | Skip the wizard and apply defaults |
| `--port` | `-p` | Override the default host port |
| `--volume` | | Named volume or local path for data (e.g. `./data/pg`) |
| `--depends-on` | | Add a `depends_on` entry (repeatable) |
| `--hardcore` | | Generate unique random credentials |
| `--file` | `-f` | Path to the compose file (default: `docker-compose.yml`) |

---

#### `rdt list` — Browse available services

Prints a table of all supported services with their category, image, and default port.

```bash
rdt list
```

---

#### `rdt up` — Start containers

A thin proxy around `docker compose up`.

```bash
rdt up               # start in detached mode (default)
rdt up --no-detach   # stream logs to stdout
rdt up --file infra/docker-compose.yml
```

---

#### `rdt lang` — Change the interface language

```bash
rdt lang               # interactive language picker
rdt lang list          # show current and available languages
rdt lang set en        # switch to English
rdt lang set ru        # switch to Russian
```

The language preference is stored in `~/.rdt/config.json` and can also be overridden per-session with the `RDT_LANG` environment variable:

```bash
RDT_LANG=en rdt add postgres
```

---

## 🔗 Smart Mapping

When you add an admin or monitoring tool, RDT scans the existing services in your compose file and automatically suggests a connection:

| Tool | Detects & links to |
|---|---|
| pgAdmin | PostgreSQL |
| phpMyAdmin | MySQL / MariaDB |
| Mongo Express | MongoDB |
| Kafka UI | Kafka |
| Grafana | Prometheus |

In interactive mode you are asked to confirm; in `--yes` / script mode the first matching service is applied automatically.

---

## 📁 Generated Files

| File | Description |
|---|---|
| `docker-compose.yml` | Compose config with all added services |
| `.env` | Environment variables with actual values |
| `.env.example` | Safe-to-commit template with empty values |

---

## 💡 Quick Example

```bash
# Bootstrap a project with Postgres + pgAdmin
rdt init
rdt add postgres --yes --port 5432 --volume ./data/pg
rdt add pgadmin  --yes
rdt up
```

