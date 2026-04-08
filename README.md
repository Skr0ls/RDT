# 🐳 Rambo Docker Tools (RDT)

**RDT** is a CLI tool for generating production-ready `docker-compose.yml` files in seconds. Pick a service, answer a few questions (or skip them entirely with `--yes`), and RDT writes the compose block, volumes, healthchecks, resource limits, and `.env` variables for you.

---

## Features

- **Interactive wizard** — guided prompts for port, volume, credentials, and dependencies
- **Script mode** — fully non-interactive via flags (`--yes`, `--port`, `--volume`, etc.)
- **30+ service presets** across 8 categories (see [Available Services](#available-services))
- **Smart Mapping** — automatically detects and links related services (e.g. pgAdmin → PostgreSQL, Grafana → Prometheus)
- **`.env` / `.env.example` generation** — credentials are written to environment files automatically
- **Artifact generation** — config files (nginx.conf, prometheus.yml, traefik.yml, …) are scaffolded automatically
- **Resource limits** — every service ships with sane CPU and RAM caps
- **Healthchecks** — databases and brokers include ready-to-use healthcheck configs
- **Service removal** — cleanly remove services, orphaned env vars, and companion files
- **Project diagnostics** — `rdt doctor` validates your stack before you start it
- **Multi-language UI** — English and Russian, switchable at any time
- **Agentic Skill** — includes dedicated instructions for AI coding agents to use RDT autonomously
- **MCP Server** — Model Context Protocol server (`rdt-mcp`) for native integration with Claude Desktop, Cursor, Windsurf, and any other MCP-compatible AI client

---

## Available Services

| Category | Services |
|---|---|
| **Web Servers** | Nginx (Reverse Proxy), Nginx (Static), Nginx (SPA), Apache (Static), Apache + PHP, Traefik |
| **Relational DB** | PostgreSQL, MySQL, MariaDB, MS SQL Server, Oracle DB (XE) |
| **NoSQL / Cache** | MongoDB, Redis, Valkey, Cassandra, InfluxDB |
| **Search / Logging** | Elasticsearch, OpenSearch, Logstash, Filebeat, Kibana, Seq |
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

# With MCP server support
pipx install "rdt-rambo[mcp]"

# Or install directly from GitHub (no PyPI account needed)
pipx install git+https://github.com/Skr0ls/RDT.git
```

---

### Option 2 — pip (inside a virtual environment)

```bash
# From PyPI
pip install rdt-rambo

# With MCP server support
pip install "rdt-rambo[mcp]"

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

# 3. Install in editable mode (add [mcp] for MCP server support)
pip install -e .
pip install -e ".[mcp]"
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
| `--no-ports` | | Do not publish ports outside the Docker network |
| `--network` | | Network type or name: `bridge` \| `host` \| `none` \| `<external-net>` |
| `--container-name` | | Explicit container name |
| `--set` | | Override any wizard answer: `key=value` (repeatable) |
| `--hc-interval` | | Healthcheck interval (e.g. `10s`) |
| `--hc-timeout` | | Healthcheck timeout (e.g. `5s`) |
| `--hc-retries` | | Healthcheck retry count |
| `--hc-start-period` | | Healthcheck start period (e.g. `30s`) |
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

#### `rdt remove <service>` — Remove a service

Removes a service block from `docker-compose.yml`, optionally cleaning up orphaned `.env` variables and companion config files.

```bash
# Interactive — picks the service from a list
rdt remove

# Remove a specific service
rdt remove postgres

# Also remove orphaned .env variables
rdt remove postgres --clean-env

# Also remove companion config files (e.g. prometheus/prometheus.yml)
rdt remove postgres --clean-artifacts

# Skip all confirmation prompts
rdt remove postgres --yes --clean-env --clean-artifacts

# Target a custom compose file
rdt remove postgres --file infra/docker-compose.yml
```

| Flag | Short | Description |
|---|---|---|
| `--yes` | `-y` | Skip confirmation prompts |
| `--clean-env` | | Remove orphaned `.env` / `.env.example` variables |
| `--clean-artifacts` | | Delete companion config files generated for the service |
| `--file` | `-f` | Path to the compose file (default: `docker-compose.yml`) |

---

#### `rdt doctor` — Diagnose your project

Runs a full health check of your Docker project and reports any issues before you start the stack.

```bash
rdt doctor                           # check the default docker-compose.yml
rdt doctor --file infra/compose.yml  # check a custom file
```

Checks performed:

| Check | What it verifies |
|---|---|
| Docker | Docker daemon is reachable |
| Compose | Docker Compose v2 is available |
| Compose valid | File passes `docker compose config` |
| Env vars | All `${VAR}` references in the compose file are set in `.env` |
| Port conflicts | Mapped host ports are not already in use |
| Dangling deps | `depends_on` references only existing services |
| Companion files | Bind-mounted config files exist on disk |

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

## 🤖 AI Agent Integration

RDT offers two complementary ways to integrate with AI coding assistants and autonomous agents.

---

### Option A — MCP Server (recommended for broad ecosystem support)

The `rdt-mcp` server exposes all RDT functionality as typed [Model Context Protocol](https://modelcontextprotocol.io) tools. Any MCP-compatible client — Claude Desktop, Cursor, Windsurf, VS Code Copilot, Continue — can discover and call them directly without running shell commands.

**Install with MCP support:**

```bash
pip install "rdt-rambo[mcp]"
# or
pipx install "rdt-rambo[mcp]"
```

**Configure your client** (example for Claude Desktop — `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rdt": { "command": "rdt-mcp" }
  }
}
```

The server exposes 7 tools: `rdt_init`, `rdt_add`, `rdt_remove`, `rdt_list`, `rdt_doctor`, `rdt_check`, `rdt_up`. Each tool accepts typed parameters and returns structured JSON — no shell output to parse.

→ **Full MCP documentation:** [`docs/en/mcp-server.md`](./docs/en/mcp-server.md)

---

### Option B — Agentic Skill (Augment / prompt-injection based clients)

For AI assistants that work by injecting instructions into context (such as Augment Code), use the provided skill file:

[**`rdt-skill.md`**](./docs/skills/rdt-skill.md)

> This file contains precise instructions, API rules, and a catalog reference specifically formatted for LLMs. Point your agent to this file and ask it to "Initialize a Postgres + Redis backend stack using the rules in rdt-skill.md".

---

### Which to use?

| | MCP Server | Skill |
|---|---|---|
| Works in Claude Desktop, Cursor, Windsurf | ✅ | ❌ |
| Works in Augment Code | ✅ | ✅ |
| Structured JSON responses | ✅ | ❌ |
| No shell execution needed | ✅ | ❌ |
| Zero extra dependencies | ❌ | ✅ |

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
rdt doctor   # validate before starting
rdt up
```

```bash
# Spin up a full monitoring stack (Prometheus + Grafana)
rdt init
rdt add prometheus --yes
rdt add grafana    --yes
rdt check    # verify compose syntax
rdt up
```

```bash
# Remove a service and clean up its files
rdt remove postgres --yes --clean-env --clean-artifacts
```
