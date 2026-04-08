# RDT MCP Server

> **Rambo Docker Tools** — `docker-compose.yml` generator.  
> The MCP server exposes all RDT functionality as typed [Model Context Protocol](https://modelcontextprotocol.io) tools, enabling native integration with Claude Desktop, Cursor, Windsurf, VS Code Copilot, Continue, and any other MCP-compatible AI client.

---

## Table of Contents

- [Why MCP vs the Skill](#why-mcp-vs-the-skill)
- [Installation](#installation)
- [Client Setup](#client-setup)
  - [Claude Desktop](#claude-desktop)
  - [Cursor](#cursor)
  - [Windsurf](#windsurf)
  - [VS Code + Continue](#vs-code--continue)
- [Available Tools](#available-tools)
  - [rdt_init](#rdt_init)
  - [rdt_add](#rdt_add)
  - [rdt_remove](#rdt_remove)
  - [rdt_list](#rdt_list)
  - [rdt_doctor](#rdt_doctor)
  - [rdt_check](#rdt_check)
  - [rdt_up](#rdt_up)
- [Response Format](#response-format)
- [Typical Agent Workflow](#typical-agent-workflow)

---

## Why MCP vs the Skill

RDT ships with two integration options for AI agents.

| | MCP Server | Skill (`rdt-skill.md`) |
|---|---|---|
| Works in Claude Desktop, Cursor, Windsurf | ✅ | ❌ |
| Works in Augment Code | ✅ | ✅ |
| Typed parameters, no shell composition | ✅ | ❌ |
| Structured JSON responses | ✅ | ❌ |
| No terminal / process execution needed | ✅ | ❌ |
| Zero extra dependencies | ❌ | ✅ |

**Use MCP** when you want RDT available across multiple clients without per-client prompt setup.  
**Use the Skill** when you are working exclusively inside Augment Code and want zero installation overhead.

The two approaches are not mutually exclusive — you can have both configured simultaneously.

---

## Installation

The MCP server is an optional extra. Install it alongside RDT:

```bash
# pip
pip install "rdt-rambo[mcp]"

# pipx (recommended for system-wide CLI tools)
pipx install "rdt-rambo[mcp]"

# from source
pip install -e ".[mcp]"
```

After installation, the `rdt-mcp` binary is available on your PATH:

```bash
rdt-mcp --help
```

The server communicates over **stdio** (standard input/output) — the client launches the process and exchanges JSON-RPC messages through its stdin/stdout. No port binding or network configuration is required.

---

## Client Setup

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "rdt": {
      "command": "rdt-mcp"
    }
  }
}
```

Restart Claude Desktop. The RDT tools will appear in the tools panel (🔧 icon).

---

### Cursor

Create or edit `.cursor/mcp.json` in your project root (project-scoped) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "rdt": {
      "command": "rdt-mcp"
    }
  }
}
```

Reload Cursor. RDT tools are now available to the Cursor AI agent.

---

### Windsurf

Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "rdt": {
      "command": "rdt-mcp"
    }
  }
}
```

---

### VS Code + Continue

Add to your `~/.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "rdt",
      "command": "rdt-mcp",
      "args": []
    }
  ]
}
```

---

## Available Tools

All tools accept an optional `project_dir` parameter — an absolute path to the working directory. When omitted, the current working directory is used. All file paths (`file`) are resolved relative to `project_dir`.

---

### rdt_init

Initialize a new `docker-compose.yml`, `.env`, and `.env.example` in the project directory.

| Parameter | Type | Required | Default | Description |
|-----------|------|:--------:|---------|-------------|
| `file` | string | no | `docker-compose.yml` | Compose file name or path |
| `force` | boolean | no | `false` | Overwrite existing files |
| `project_dir` | string | no | cwd | Absolute path to the project directory |

**Success response:**
```json
{
  "status": "ok",
  "file": "docker-compose.yml",
  "created": [
    "docker-compose.yml",
    "/absolute/path/.env",
    "/absolute/path/.env.example"
  ]
}
```

**Error response:**

```json
{ "status": "error", "message": "File already exists: docker-compose.yml. Use force=True to overwrite." }
```

---

### rdt_add

Add a service to `docker-compose.yml`. Creates the compose block, writes credentials to `.env` / `.env.example`, generates companion config files (e.g. `nginx/nginx.conf`, `prometheus/prometheus.yml`), and sets up volumes and healthchecks.

Always prefer `rdt_add` over editing the compose file manually.

| Parameter | Type | Required | Default | Description |
|-----------|------|:--------:|---------|-------------|
| `service` | string | **yes** | — | Service name (e.g. `postgres`, `redis`, `nginx-proxy`). Use `rdt_list` to see all options. |
| `file` | string | no | `docker-compose.yml` | Compose file path |
| `project_dir` | string | no | cwd | Absolute path to the project directory |
| `port` | integer | no | preset default | Override the default host port |
| `volume` | string | no | `<service>_data` | Named volume or bind-mount path (e.g. `./data/pg`) |
| `depends_on` | string[] | no | `[]` | Services this service depends on |
| `hardcore` | boolean | no | `false` | Generate strong random passwords instead of placeholder defaults |
| `no_ports` | boolean | no | `false` | Expose ports only inside the Docker network, not to the host |
| `network` | string | no | `bridge` | Network type or external network name: `bridge` \| `host` \| `none` \| `<name>` |
| `container_name` | string | no | service name | Explicit container name |
| `hc_interval` | string | no | preset default | Healthcheck interval (e.g. `10s`) |
| `hc_timeout` | string | no | preset default | Healthcheck timeout (e.g. `5s`) |
| `hc_retries` | integer | no | preset default | Healthcheck retry count |
| `hc_start_period` | string | no | preset default | Healthcheck start period (e.g. `30s`) |
| `set_vars` | object | no | `{}` | Override any internal wizard variable (e.g. `{"nginx_upstream": "app:8080"}`) |

**Success response:**
```json
{
  "status": "ok",
  "service": "postgres",
  "port": 5432,
  "env_vars": {
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "postgres",
    "POSTGRES_DB": "postgres"
  },
  "artifacts_created": [],
  "hints": []
}
```

**Error response:**
```json
{ "status": "error", "message": "Service 'postgres' already exists in docker-compose.yml." }
```

---

### rdt_remove

Remove a service from `docker-compose.yml`. Optionally cleans up orphaned `.env` variables and companion config files generated for that service.

| Parameter | Type | Required | Default | Description |
|-----------|------|:--------:|---------|-------------|
| `service` | string | **yes** | — | Service name to remove |
| `file` | string | no | `docker-compose.yml` | Compose file path |
| `project_dir` | string | no | cwd | Absolute path to the project directory |
| `clean_env` | boolean | no | `false` | Remove orphaned variables from `.env` and `.env.example` |
| `clean_artifacts` | boolean | no | `false` | Delete companion config files generated for this service |

**Success response:**
```json
{
  "status": "ok",
  "removed": "postgres",
  "removed_volumes": ["postgres_data"],
  "cleaned_env_vars": ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"],
  "cleaned_files": [],
  "dependents_warned": ["pgadmin"]
}
```

> **Note:** `dependents_warned` lists services that had `depends_on: [<removed service>]`. The removal proceeds, but those services may need to be updated or removed as well.

---

### rdt_list

List all available service presets. Read-only — does not modify anything.

| Parameter | Type | Required | Default | Description |
|-----------|------|:--------:|---------|-------------|
| `category` | string | no | — | Filter by category (e.g. `Relational DB`, `NoSQL / Cache`, `Monitoring`) |

**Response:**
```json
{
  "presets": [
    {
      "name": "postgres",
      "display_name": "PostgreSQL",
      "category": "Relational DB",
      "image": "postgres:16-alpine",
      "default_port": 5432,
      "container_port": 5432,
      "has_healthcheck": true
    }
  ]
}
```

---

### rdt_doctor

Run a full diagnostic check on the project. Verifies Docker availability, Compose v2, YAML validity, `.env` completeness, port conflicts, dangling `depends_on` references, and the presence of companion config files.

**Always call `rdt_doctor` before finishing a task.** It is the single command that validates the entire generated stack.

| Parameter | Type | Required | Default | Description |
|-----------|------|:--------:|---------|-------------|
| `file` | string | no | `docker-compose.yml` | Compose file path |
| `project_dir` | string | no | cwd | Absolute path to the project directory |

**Response:**
```json
{
  "checks": [
    { "name": "docker",          "status": "ok",   "message": "Docker 27.3.1",          "details": [] },
    { "name": "compose",         "status": "ok",   "message": "Docker Compose v2.29.7", "details": [] },
    { "name": "compose_valid",   "status": "ok",   "message": "Valid",                  "details": [] },
    { "name": "env_vars",        "status": "ok",   "message": "All variables are set",  "details": [] },
    { "name": "port_conflicts",  "status": "ok",   "message": "No conflicts",           "details": [] },
    { "name": "dangling_deps",   "status": "ok",   "message": "No dangling deps",       "details": [] },
    { "name": "companion_files", "status": "ok",   "message": "All files present",      "details": [] }
  ],
  "summary": { "ok": 7, "warn": 0, "error": 0, "skip": 0 }
}
```

Check statuses: `ok`, `warn`, `error`, `skip`.

---

### rdt_check

Validate `docker-compose.yml` syntax by running `docker compose config`. Detects YAML errors, unknown keys, and invalid references.

| Parameter | Type | Required | Default | Description |
|-----------|------|:--------:|---------|-------------|
| `file` | string | no | `docker-compose.yml` | Compose file path |
| `project_dir` | string | no | cwd | Absolute path to the project directory |

**Success response:**
```json
{ "valid": true }
```

**Failure response:**
```json
{ "valid": false, "error": "service \"app\": depends_on.postgres: service not found" }
```

---

### rdt_up

Start the Docker Compose stack via `docker compose up`.

> **Do not call this tool unless the user explicitly asks to start the stack.**
> The standard agent workflow ends with `rdt_doctor` — the user starts the stack themselves.

| Parameter | Type | Required | Default | Description |
|-----------|------|:--------:|---------|-------------|
| `file` | string | no | `docker-compose.yml` | Compose file path |
| `project_dir` | string | no | cwd | Absolute path to the project directory |
| `detach` | boolean | no | `true` | Run containers in the background |

**Response:**
```json
{ "command": "docker compose -f docker-compose.yml up -d", "returncode": 0 }
```

---

## Response Format

All tools return a JSON object. The fields present depend on the tool:

- **`status`** (`"ok"` / `"error"`) — included when the operation mutates state (`rdt_init`, `rdt_add`, `rdt_remove`)
- **`message`** — human-readable error description, present only when `status` is `"error"`
- Tool-specific payload fields (see each tool's documentation above)

When `status` is `"error"`, no files have been written. The `message` field contains enough context to understand the failure without inspecting files.

---

## Typical Agent Workflow

```
1. rdt_list           → discover available services and their exact names
2. rdt_init           → create docker-compose.yml, .env, .env.example
3. rdt_add (×N)       → add each required service
                         link services via depends_on
                         use no_ports=true for internal-only services
                         use hardcore=true for production-grade credentials
4. rdt_doctor         → validate the entire stack (always do this)
5. rdt_check          → verify YAML syntax (optional, doctor covers this)
6.  → present results to the user
     show credentials from env_vars fields
     instruct the user to run `rdt up` or call rdt_up if asked
```

### Example: Postgres + pgAdmin

```
rdt_init()
rdt_add("postgres", hardcore=True, volume="./data/pg")
rdt_add("pgadmin", depends_on=["postgres"], no_ports=False)
rdt_doctor()
```

### Example: Monitoring stack

```
rdt_init()
rdt_add("prometheus")
rdt_add("grafana", depends_on=["prometheus"])
rdt_doctor()
```

### Example: Remove a service cleanly

```
rdt_remove("postgres", clean_env=True, clean_artifacts=True)
rdt_doctor()   # confirm remaining stack is still valid
```
