# Jarvis

Personal voice assistant with Pi Zero nodes and self-hosted microservices.

**See also: [RULES.md](RULES.md)** - Development rules (working style, coding style, TDD, performance targets)

## For Claude: Use MCP Tools

**IMPORTANT**: When interacting with jarvis services, ALWAYS prefer jarvis-mcp tools over direct curl/HTTP calls:

| Instead of... | Use MCP tool... |
|---------------|-----------------|
| `curl localhost:7702/health` | `debug_health` |
| `curl localhost:7701/health` | `debug_health` |
| Querying logs via curl | `query_logs`, `logs_tail` |
| Getting service info | `debug_service_info` |
| `docker ps` | `docker_ps` |
| `docker logs <container>` | `docker_logs` |
| `docker restart <container>` | `docker_restart` |
| `docker compose up -d` | `docker_compose_up` |
| `docker compose down` | `docker_compose_down` |

The jarvis-mcp server provides these tools:
- `debug_health` - Check health of all services (or specific ones)
- `debug_service_info` - Get detailed info about a service
- `query_logs` - Query logs with filters
- `logs_tail` - Get recent logs from a service
- `get_log_stats` - Get log statistics
- `docker_ps` - List jarvis containers (name, status, image, ports)
- `docker_logs` - Get recent logs from a container (partial name match)
- `docker_restart` / `docker_stop` / `docker_start` - Container lifecycle
- `docker_compose_up` / `docker_compose_down` - Compose stack management
- `docker_compose_list` - List services with compose files

## Core Principles

1. **Fully private and open source** - No cloud dependencies by default, all data stays local
2. **Self-hostable with optional cloud** - Same open-source codebase for both; no data selling, full transparency
3. **Fully extensible** - Add capabilities by implementing `IJarvisCommand` interface (see `jarvis-node-setup/core/ijarvis_command.py`)

## Codebase Health (Last Updated: 2026-03-23)

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Architecture** | 9/10 | All monolithic files split (llm-proxy, command-center, url_recipe_parser), clean module boundaries |
| **Design** | 7/10 | Good separation of concerns, improved exception handling |
| **Security** | 7/10 | JWT auth, encrypted secrets, app-to-app auth. Needs: rate limiting, CORS |
| **Testing** | 8/10 | Core services tested, ocr-service + tts tests added |
| **Documentation** | 8/10 | Per-service CLAUDE.md, comprehensive main docs |
| **Maintainability** | 8/10 | Smaller files, specific exceptions, all logging via JarvisLogger |
| **Code Quality** | 9/10 | Bare excepts fixed, broad exceptions fixed, print() migrated, 132 unused imports removed |
| **Observability** | 8/10 | All production code uses JarvisLogger (worker `_safe_print` is acceptable) |

**Average: 8.00/10** → Target: 9/10

### Quick Wins to Improve
- [x] ~~Add tests to config-service~~ ✅ 44 tests, 93% coverage
- [x] ~~Add tests to ocr-service~~ ✅ 5 test files (validation, llm queue, callback, continue processing, async flow)
- [x] ~~Migrate print() files to JarvisLogger~~ ✅ All production code migrated (remaining prints are CLI scripts, tests, worker `_safe_print`)
- [x] ~~Refactor url_recipe_parser.py~~ ✅ Split into url_parsing/ package (1498 → 285 lines)
- [x] ~~Fix mid-file imports in espn_sports_service.py~~ ✅ Moved to top of file
- [x] ~~Remove unused imports across codebase~~ ✅ 132 unused imports removed via ruff

## Development Rules

**Logging:**
- ALL logging MUST go through `jarvis-log-client` to `jarvis-logs` service
- No `print()` statements for logging - use `JarvisLogger` instead
- See `jarvis-log-client/CLAUDE.md` for usage

**Testing:**
- TDD is ALWAYS preferred: write tests first (RED), implement (GREEN), refactor (IMPROVE)
- Target 80%+ test coverage
- Run `pytest` before committing

**Running Services:**
- ALWAYS check the service's own `CLAUDE.md` or `README.md` for how to run it
- Each service may have unique setup requirements
- Prefer Docker dev scripts (e.g., `run-docker-dev.sh`) over direct uvicorn

**New Services:**
- Prefer Docker containers for all new services
- Include `Dockerfile` and `docker-compose.yaml`
- Follow existing service patterns (FastAPI + Uvicorn)

**Code Style - Imports:**
- ALL imports MUST be at the top of the file
- NO mid-file imports unless absolutely necessary (e.g., circular import resolution)
- Group imports: stdlib → third-party → local

**Code Style - Types:**
- ALWAYS use type hints for:
  - Variable declarations: `count: int = 0`
  - Function parameters: `def process(data: dict[str, Any]) -> None:`
  - Return types: `def get_user(id: str) -> User | None:`
- Use `typing` module for complex types (`Optional`, `Union`, `TypeVar`, etc.)
- Prefer `X | None` over `Optional[X]` (Python 3.10+)

## What It Is

Voice-controlled assistant system. Pi Zero nodes (with mic + speaker) capture voice, send to command center for processing via whisper.cpp (speech-to-text), route to appropriate service/command, and respond. Designed for home automation, recipes, calendar, weather, and any custom commands you want to add.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────────┐
│  jarvis-node    │────▶│  jarvis-command-     │
│  (client nodes) │     │  center (voice API)  │
└─────────────────┘     └──────────┬───────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
┌───────────────┐         ┌────────────────┐         ┌────────────────┐
│ jarvis-auth   │         │ jarvis-whisper │         │ jarvis-ocr     │
│ (JWT auth)    │         │ (speech→text)  │         │ (image→text)   │
└───────────────┘         └────────────────┘         └────────────────┘
        │
        ▼
┌────────────────┐
│ jarvis-recipes │
│ (recipe CRUD)  │
└────────────────┘
```

### Speaker ID & Memory Flow

```
Node (mic) ──▶ Whisper ──▶ {text, speaker: {user_id, confidence}}
                                │
                                ▼
              Command Center receives transcription
                │
                ├─ Extracts speaker_user_id from whisper response
                ├─ Resolves user_id → display name via jarvis-auth (cached 5min)
                ├─ Loads user memories from PostgreSQL (MemoryService)
                ├─ Injects speaker name + memories into system prompt
                │
                └─▶ LLM sees: "About Alex: - Likes black coffee - Morning person"
                    LLM can call: remember({content: "..."}) / forget({content_match: "..."})
```

**Key files:**
- Node: `stt_providers/jarvis_whisper_client.py` (TranscriptionResult with speaker data)
- Command Center: `app/core/utils/speaker_resolver.py` (name resolution)
- Command Center: `app/services/memory_service.py` (memory CRUD + prompt formatting)
- Command Center: `app/core/tools/remember_tool.py`, `forget_tool.py` (server tools)
- Command Center: `app/api/memories.py` (REST CRUD API)
- Whisper: `app/api/voice_profiles.py` (enrollment endpoints)

## Service Dependency Graph (Runtime)

```
Nodes/Clients
  └─▶ jarvis-command-center
        ├─▶ jarvis-auth (app-to-app + node auth)
        ├─▶ jarvis-config-service (service discovery)
        ├─▶ jarvis-logs (structured logging)
        ├─▶ jarvis-settings-client (runtime settings)
        ├─▶ jarvis-llm-proxy-api (LLM inference)
        ├─▶ jarvis-whisper-api (speech-to-text)
        ├─▶ jarvis-tts (text-to-speech)
        ├─▶ jarvis-notifications (push + inbox for deep research)
        └─▶ jarvis-web-scraper (web content extraction)

jarvis-ocr-service
  ├─▶ jarvis-auth (app-to-app auth)
  ├─▶ jarvis-logs (structured logging)
  └─▶ jarvis-settings-client (backend opt-in settings)

jarvis-recipes-server
  ├─▶ jarvis-auth (app-to-app auth)
  ├─▶ jarvis-logs (structured logging)
  ├─▶ jarvis-settings-client (runtime settings)
  └─▶ jarvis-ocr-service (optional OCR pipeline)

jarvis-logs
  └─▶ jarvis-auth (app-to-app auth validation)

jarvis-config-service
  ├─▶ jarvis-auth (admin/app auth)
  └─▶ jarvis-logs (structured logging)

jarvis-mcp
  ├─▶ jarvis-config-service (service discovery)
  ├─▶ jarvis-logs (log queries)
  └─▶ jarvis-auth (auth headers for protected calls)

jarvis-notifications (7712) ◄─── Push notifications + inbox
  ├─▶ jarvis-auth (app-to-app auth)
  ├─▶ jarvis-config-service (service discovery)
  ├─▶ jarvis-logs (structured logging)
  ├─▶ jarvis-notifications-relay (optional, Expo push delivery)
  └─▶ PostgreSQL (device tokens, notification log, inbox items)

jarvis-notifications-relay ◄─── Expo Push API proxy (cloud/local)
  └─▶ Expo Push API (APNs/FCM delivery)

Data stores (shared infra)
  ├─ PostgreSQL (auth, command-center, recipes, config-service, notifications)
  ├─ Redis (ocr queue, async jobs)
  ├─ MinIO (object storage)
  └─ Mosquitto (node ↔ tts MQTT)
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| jarvis-auth | 7701 | JWT authentication (register, login, refresh, logout) |
| jarvis-command-center | 7703 | Central voice/command API, node management, tool routing |
| jarvis-whisper-api | 9999 | Speech-to-text via whisper.cpp |
| jarvis-ocr-service | 7031 | OCR with pluggable backends (Tesseract, EasyOCR, Apple Vision) |
| jarvis-recipes-server | 7030 | Recipe CRUD and meal planning |
| jarvis-node-setup | - | Client-side node code (not a server) |
| jarvis-notifications | 7712 | Push notifications, inbox, device token management |
| jarvis-notifications-relay | - | Stateless Expo Push API proxy (cloud/local) |
| jarvis-pantry | 7720 | Community package store (browse, submit, review, install) |
| jarvis-command-sdk | - | Shared interfaces (IJarvisCommand, IJarvisAgent, IJarvisDeviceProtocol, IJarvisDeviceManager) |
| jarvis-web | 7722 | Web chat interface (Next.js) |

## Common Patterns

- **Framework**: FastAPI + Uvicorn (all Python services)
- **Database**: PostgreSQL (auth, command-center, recipes) or SQLite (dev)
- **Migrations**: Alembic
- **Auth**: JWT access tokens + hashed refresh tokens
- **App-to-App Auth**: `X-Jarvis-App-Id` + `X-Jarvis-App-Key` headers
- **Containerization**: Docker + docker-compose

## Development

```bash
# Each service follows this pattern:
cd jarvis-<service>
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env  # configure
.venv/bin/python -m alembic upgrade head  # if has migrations
.venv/bin/uvicorn app.main:app --reload --port <PORT>
```

### Starting Services (for Claude)

**IMPORTANT**: Always use Docker dev scripts to start services, not direct uvicorn commands:

```bash
# jarvis-command-center (port 7703)
cd /home/alex/jarvis/jarvis-command-center && bash run-docker-dev.sh

# Health check endpoint: /api/v0/health
curl http://localhost:7703/api/v0/health
```

This ensures proper environment configuration and database connections.

### Development Model (Mixed Local/Docker)

Jarvis uses a **mixed local/Docker model** that varies by platform. The `./jarvis` CLI handles this automatically.

#### macOS (Apple Silicon)

GPU-dependent services run **locally** to access Metal and Apple Vision frameworks. Everything else runs in Docker.

```
┌─ Docker (jarvis-net) ──────────────────────────────────┐
│  jarvis-config-service  (7700)                         │
│  jarvis-auth            (7701)                         │
│  jarvis-logs            (7702)                         │
│  jarvis-command-center  (7703)                         │
│  jarvis-tts             (7707)                         │
│  jarvis-whisper-api     (7706)                         │
│  jarvis-recipes-server  (7030)                         │
│  jarvis-settings-server (7708)                         │
│  jarvis-mcp             (7709)                         │
│  jarvis-admin           (7710)                         │
│  jarvis-notifications   (7712)                         │
│  jarvis-web             (7722)                         │
│  PostgreSQL, Redis, MinIO                              │
└────────────────────────────────────────────────────────┘
         ▲ host.docker.internal
         │
┌─ Local (native) ──────────────────────────────────────┐
│  jarvis-llm-proxy-api  (7704/7705)  ← Metal/MLX/GGUF │
│  jarvis-ocr-service    (7031)       ← Apple Vision    │
└────────────────────────────────────────────────────────┘
```

The `jarvis` script detects Darwin and overrides `mode=docker` → `mode=local` for llm-proxy and ocr-service. Local services connect to dockerized infrastructure (PostgreSQL, Redis) via `localhost`.

#### Linux (NVIDIA GPU)

**Everything runs in Docker**, including GPU services. LLM inference uses `nvidia-docker` (NVIDIA Container Toolkit) for GPU passthrough.

```
┌─ Docker (jarvis-net) ──────────────────────────────────┐
│  All services from macOS list, plus:                   │
│  jarvis-llm-proxy-api  (7704/7705)  ← vLLM + CUDA    │
│  jarvis-ocr-service    (7031)       ← Tesseract/etc   │
│  PostgreSQL, Redis, MinIO                              │
│                                                        │
│  GPU services use:                                     │
│    deploy.resources.reservations.devices:               │
│      - driver: nvidia                                  │
│        count: all                                      │
│        capabilities: [gpu]                             │
└────────────────────────────────────────────────────────┘
```

#### Network Modes

The `./jarvis` CLI supports three network modes:

| Mode | Flag | How services communicate |
|------|------|--------------------------|
| **Bridge** (default) | — | Shared `jarvis-net` Docker network, services use container names |
| **Host** | `--no-network` | No shared network, services use `host.docker.internal` |
| **Standalone** | `--standalone` | Single service with its own PostgreSQL container |

#### How Docker ↔ Local Communication Works

- Docker containers reach **local** services via `host.docker.internal` (mapped by `extra_hosts` in compose files)
- Local services reach **Docker** infrastructure (PostgreSQL, Redis) via `localhost` (ports are bound to host)
- `JARVIS_CONFIG_URL_STYLE=dockerized` tells config-service to return `host.docker.internal` URLs for Docker consumers

## Environments & Hosts

### Dev Environment

| Host | Address | Role | SSH |
|------|---------|------|-----|
| **Pi Zero node** | `jarvis-dev.local` | Physical voice node (mic + speaker) | `pi@jarvis-dev.local` |
| **Ubuntu desktop** | `10.0.0.122` | GPU services (LLM proxy, Whisper) | `alex@10.0.0.122` |
| **Laptop (macOS)** | `10.0.0.103` | Rest of Docker stack + development | local |
| **Laptop node container** | `localhost:7771` | Dockerized jarvis-node for dev | — |

- LLM proxy and Whisper sometimes run on the laptop to verify macOS/Metal still works
- Dev is the free-fire zone — do whatever is needed

### Prod Environment

| Host | Address | Role | SSH |
|------|---------|------|-----|
| **Prod server** | `10.0.0.107` | Ubuntu server, full Docker stack | `jarvis@10.0.0.107` |
| **Prod node** | `jarvis-kitchen.local` | Kitchen Pi Zero node | `pi@jarvis-kitchen.local` |

**⚠️ PROD RULES:**
- **NEVER** write directly to prod containers (`~/.jarvis/compose`) without explicit user instructions
- Use prod primarily for **reading logs and checking status** unless explicitly told otherwise
- Prod node (`jarvis-kitchen.local`): may check logs, occasionally patch fixes, but **prefer dev environment**
- When in doubt, test in dev first

## Environment Variables (Cross-Service)

| Variable | Used By | Description |
|----------|---------|-------------|
| `DATABASE_URL` | auth, command-center, recipes | PostgreSQL connection |
| `SECRET_KEY` | auth | JWT signing key |
| `ADMIN_API_KEY` | command-center | Admin endpoint protection |
| `JARVIS_AUTH_BASE_URL` | ocr, others | Auth service URL for validation |

## Service Communication

- Nodes → Command Center: `X-API-Key` header
- Services → Auth: `X-Jarvis-App-Id` + `X-Jarvis-App-Key`
- Command Center dispatches to whisper/ocr as needed

## Service Dependency Graph

### Core Dependencies

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         JARVIS SERVICE DEPENDENCIES                      │
└─────────────────────────────────────────────────────────────────────────┘

jarvis-config-service (7700) ◄─── Service discovery hub
    │
    ├─── Used by: ALL services (for service URL discovery)
    └─── Dependencies: PostgreSQL

jarvis-auth (7701) ◄─── Authentication hub
    │
    ├─── Used by: command-center, whisper-api, ocr-service, tts, logs, settings-server, admin, notifications
    ├─── Dependencies: PostgreSQL, jarvis-logs (optional)
    └─── Impact if down: No new logins, no app-to-app auth validation

jarvis-logs (7702) ◄─── Centralized logging
    │
    ├─── Used by: ALL services (via jarvis-log-client)
    ├─── Dependencies: Loki (7032), Grafana (7033), jarvis-auth
    └─── Impact if down: Services continue, logs go to console only

jarvis-command-center (7703) ◄─── Voice command orchestrator
    │
    ├─── Used by: jarvis-node-setup (Pi Zero nodes), jarvis-node-mobile
    ├─── Dependencies: PostgreSQL, jarvis-llm-proxy-api, jarvis-auth, jarvis-logs
    ├─── Optional calls: jarvis-whisper-api, jarvis-ocr-service, jarvis-notifications
    └─── Impact if down: No voice commands processed

jarvis-llm-proxy-api (7704/7705) ◄─── LLM inference
    │
    ├─── Used by: command-center, tts (wake responses)
    ├─── Dependencies: None (standalone)
    └─── Impact if down: No LLM-based command parsing, no wake responses

jarvis-whisper-api (7706) ◄─── Speech-to-text
    │
    ├─── Used by: command-center (optional)
    ├─── Dependencies: whisper.cpp, jarvis-auth, jarvis-logs
    └─── Impact if down: No speech transcription (if command-center uses it)

jarvis-ocr-service (7031) ◄─── Image-to-text
    │
    ├─── Used by: command-center (optional)
    ├─── Dependencies: Tesseract/EasyOCR/PaddleOCR, jarvis-auth
    └─── Impact if down: No OCR functionality

jarvis-tts (7707) ◄─── Text-to-speech
    │
    ├─── Used by: jarvis-node-setup (via MQTT or direct)
    ├─── Dependencies: Piper TTS, jarvis-auth, jarvis-logs, jarvis-llm-proxy-api (wake responses)
    └─── Impact if down: No voice responses

jarvis-recipes-server (7030) ◄─── Recipe CRUD
    │
    ├─── Used by: command-center (recipe commands)
    ├─── Dependencies: PostgreSQL
    └─── Impact if down: No recipe functionality

jarvis-settings-server (7708) ◄─── Settings aggregator
    │
    ├─── Used by: jarvis-admin (web UI)
    ├─── Dependencies: jarvis-config-service, jarvis-auth (JWT validation)
    └─── Impact if down: No settings management UI

jarvis-mcp (7709) ◄─── Claude Code integration
    │
    ├─── Used by: Claude Code (development)
    ├─── Dependencies: jarvis-config-service, jarvis-logs, jarvis-auth
    └─── Impact if down: No Claude Code tools

jarvis-admin (7710) ◄─── Web admin UI
    │
    ├─── Used by: Administrators (browser)
    ├─── Dependencies: jarvis-config-service, jarvis-auth, jarvis-settings-server

jarvis-web (7722) ◄─── Web chat interface
    │
    ├─── Used by: End users (browser)
    ├─── Dependencies: jarvis-auth (login), jarvis-command-center (chat API)
    └─── Impact if down: No web UI (services continue)

jarvis-notifications (7712) ◄─── Push notifications + inbox
    │
    ├─── Used by: command-center (deep research, alerts), recipes-server, node-mobile
    ├─── Dependencies: PostgreSQL, jarvis-auth, jarvis-config-service
    ├─── Optional: jarvis-notifications-relay (Expo push delivery), jarvis-logs
    └─── Impact if down: No push notifications, no inbox delivery

jarvis-notifications-relay ◄─── Expo Push API proxy
    │
    ├─── Used by: jarvis-notifications (push forwarding)
    ├─── Dependencies: Expo Push API (external)
    └─── Impact if down: Push notifications not delivered to devices (inbox still works)

jarvis-node-setup ◄─── Pi Zero client
    │
    ├─── Used by: End users (voice nodes)
    ├─── Dependencies: jarvis-command-center, jarvis-tts (optional)
    └─── Impact if down: No voice input from that node
```

### Dependency Tiers

**Tier 0 (Foundation):**
- `jarvis-config-service` - Service discovery (all services depend on this)
- `PostgreSQL` - Database for auth, command-center, recipes, config-service

**Tier 1 (Core Infrastructure):**
- `jarvis-auth` - Authentication (most services depend on this)
- `jarvis-logs` - Logging (optional, services degrade gracefully)

**Tier 2 (Command Processing):**
- `jarvis-command-center` - Voice orchestration
- `jarvis-llm-proxy-api` - LLM inference

**Tier 3 (Specialized Services):**
- `jarvis-whisper-api` - Speech-to-text
- `jarvis-ocr-service` - OCR
- `jarvis-tts` - Text-to-speech
- `jarvis-recipes-server` - Recipe data
- `jarvis-notifications` - Push notifications + inbox
- `jarvis-notifications-relay` - Expo Push proxy (cloud)

**Tier 4 (Management & Tooling):**
- `jarvis-settings-server` - Settings proxy
- `jarvis-mcp` - Claude Code tools
- `jarvis-admin` - Admin Web UI
- `jarvis-web` - Web chat interface

**Tier 5 (Clients):**
- `jarvis-node-setup` - Voice nodes

### Critical Path Analysis

**For voice commands to work:**
1. ✅ `jarvis-config-service` must be running
2. ✅ `jarvis-auth` must be running
3. ✅ `jarvis-command-center` must be running
4. ✅ `jarvis-llm-proxy-api` must be running
5. ⚠️ `jarvis-logs` should be running (optional)
6. ⚠️ `jarvis-whisper-api` may be needed (if command-center uses it)
7. ⚠️ `jarvis-tts` may be needed (for voice responses)

**For web admin to work:**
1. ✅ `jarvis-config-service` must be running
2. ✅ `jarvis-auth` must be running
3. ✅ `jarvis-settings-server` must be running
4. ✅ `jarvis-admin` must be running

### Service-to-Service Communication Patterns

**App-to-App Auth (most services):**
```
Service → jarvis-auth (/internal/validate-app)
Headers: X-Jarvis-App-Id, X-Jarvis-App-Key
```

**Node Auth (whisper, tts):**
```
Node → Service
Header: X-API-Key (node_id:node_key)
Service → jarvis-auth (validate node)
```

**User Auth (admin, settings-server):**
```
Client → Service
Header: Authorization: Bearer <jwt>
Service validates JWT locally (shared secret)
```

**Logging (all services):**
```
Service → jarvis-logs (/api/v0/logs or /api/v0/logs/batch)
Headers: X-Jarvis-App-Id, X-Jarvis-App-Key
```

**Service Discovery (all services):**
```
Service → jarvis-config-service (/services)
Response: List of all service URLs
Cached locally, refreshed periodically
```

## Testing

```bash
# Most services
poetry run pytest

# Database tests (command-center)
python run_database_tests.py --type sqlite
```

## Workflows

### Adapter Training

Train a LoRA adapter for a node's command set.

**1. Download base model (if not present)**

Check if model exists in `jarvis-llm-proxy-api/.models/`:
```bash
ls /home/alex/jarvis/jarvis-llm-proxy-api/.models/
```

If not present, download via HuggingFace CLI:
```bash
cd /home/alex/jarvis/jarvis-llm-proxy-api
source venv/bin/activate
huggingface-cli download <org>/<model-name> --local-dir ./.models/<model-name>
```

**2. Ensure required services are running**

Use MCP `debug_health` tool to check service status. Required services:
- `jarvis-command-center` (port 7703)
- `jarvis-llm-proxy-api` (port 7704 API, port 7705 queue worker)

If not running, start them:
```bash
# Command Center
cd /home/alex/jarvis/jarvis-command-center && bash run-docker-dev.sh

# LLM Proxy (starts both API and queue worker)
cd /home/alex/jarvis/jarvis-llm-proxy-api && ./run.sh
```

**3. Run adapter training**

```bash
cd /home/alex/jarvis/jarvis-node-setup
python scripts/train_node_adapter.py \
  --base-model-id .models/<model-name> \
  --hf-base-model-id <org>/<model-name>  # Required for GGUF models
```

Optional parameters:
- `--rank <int>` - LoRA rank
- `--epochs <int>` - Training epochs
- `--batch-size <int>` - Batch size
- `--max-seq-len <int>` - Max sequence length
- `--dry-run` - Print payload without executing

**4. Monitor training status**

```bash
curl http://localhost:7704/v1/training/status/<job_id>
```

Or use the job ID returned from step 3 to poll status until complete.

### E2E Command Parsing Tests

Run end-to-end tests to validate voice command parsing across all Jarvis commands.

**1. Register a dev node (if not already done)**

E2E tests authenticate to the command center as a registered node. See `jarvis-node-setup/CLAUDE.md` "Node Authentication" section for full details.

```bash
cd /home/alex/jarvis/jarvis-node-setup

# Get admin key from CC's .env
grep ADMIN_API_KEY ../jarvis-command-center/.env

# Register node and update config
python utils/authorize_node.py \
  --cc-key <admin_key_from_env> \
  --household-id <household-uuid> \
  --room office --name dev-mac \
  --update-config config-mac.json
```

**2. Ensure required services are running**

Use MCP `debug_health` tool to check service status. Required services:
- `jarvis-command-center` (port 7703)
- `jarvis-llm-proxy-api` (port 7704)

If not running, start them (see each service's CLAUDE.md for details):
```bash
# Command Center
cd /home/alex/jarvis/jarvis-command-center && bash run-docker-dev.sh

# LLM Proxy
cd /home/alex/jarvis/jarvis-llm-proxy-api && ./run.sh
```

**3. Run the test suite**

```bash
cd /home/alex/jarvis/jarvis-node-setup
python test_command_parsing.py
```

Command options:
- `-l` / `--list-tests` - List all available tests with indices
- `-t <indices>` / `--test-indices` - Run specific tests (e.g., `-t 5 7 11`)
- `-c <commands>` / `--command` - Run tests for specific commands (e.g., `-c calculate get_weather`)
- `-o <file>` / `--output` - Output file for results (default: `test_results.json`)

Examples:
```bash
# List all tests
python test_command_parsing.py -l

# Run specific tests
python test_command_parsing.py -t 5 7 11

# Run all calculator tests
python test_command_parsing.py -c calculate

# Run sports tests with custom output
python test_command_parsing.py -c get_sports_scores -o sports_results.json
```

**4. Review results**

Results are written to:
- `test_results.json` (or custom path via `-o`)
- `/home/alex/jarvis/jarvis-command-center/temp/test_results.json`

The output includes:
- Summary (pass/fail counts, success rate, response times)
- Per-test results with expected vs actual
- Analysis with command success rates and confusion matrix
- Recommendations for improving low-performing commands

## Backlog

### 🔴 Critical - Monolithic Files (Immediate Refactor)

| File | Lines | Issue |
|------|-------|-------|
| ~~`jarvis-llm-proxy-api/main.py`~~ | ~~1701~~ → 87 | ✅ **DONE** - Split into modules |
| ~~`jarvis-command-center/app/core/model_service.py`~~ | ~~1628~~ → 309 | ✅ **DONE** - Split into prompt_engine, tool_parser, tool_executor |
| ~~`jarvis-recipes-server/*/url_recipe_parser.py`~~ | ~~1498~~ → 285 | ✅ **DONE** - Split into `url_parsing/` package |

~~`jarvis-node-setup/services/network_discovery_service.py`~~ - DELETED (1740 lines, unused)

### ~~🔴 Critical - Logging Violations~~ ✅ DONE

~~**jarvis-node-setup has 22 files using `print()` instead of `jarvis-log-client`**~~ All production files migrated to JarvisLogger. Remaining `print()` usage is acceptable: CLI scripts (set_secret.py, authorize_node.py), test/E2E scripts, and worker `_safe_print()` pattern.

### 🟡 High Priority - Missing Test Suites

| Service | Port | Status |
|---------|------|--------|
| ~~jarvis-ocr-service~~ | ~~7031~~ | ✅ **DONE** - 5 test files (validation, llm queue, callback, async flow) |
| ~~jarvis-tts~~ | ~~7707~~ | ✅ **DONE** - 59 tests, 98% coverage, CI workflow |
| ~~jarvis-config-service~~ | ~~7700~~ | ✅ **DONE** - 44 tests, 93% coverage |

### 🟡 High Priority - Code Quality

- [x] ~~Replace bare `except:` with specific exceptions~~ - ✅ **DONE** (10 → 0 in project code, remaining are in vendored deps)
- [x] ~~Replace `except Exception:` without `as e`~~ ✅ All production instances fixed (specific types or `as e` added), including E2E test scripts
- [ ] Add CORS headers configuration
- [ ] Add rate limiting to API endpoints

### 🟢 Medium Priority - Testing & Integration

- [ ] E2E tests for full voice flow (node → command-center → service → response)
- [ ] Integration tests between services (auth ↔ command-center)
- [ ] Streaming responses for reduced latency

### 🟢 Medium Priority - Architectural

- [x] ~~jarvis-llm-proxy-api: Split main.py into api_server.py, model_service.py, queue_worker.py~~ - ✅ **DONE** (1701 → 87 lines)
- [x] ~~jarvis-recipes-server: Modular parser strategy~~ - ✅ **DONE** (1498 → 285 lines, split into url_parsing/ package)
- [x] ~~jarvis-command-center: Split model_service.py into prompt_engine.py, tool_parser.py, tool_executor.py~~ - ✅ **DONE** (1628 → 309 lines)

### 🔵 Low Priority

- [ ] Convert in-code TODOs to GitHub issues
- [ ] Stronger default secrets in .env.example files
- [ ] TypedDict for tool definitions instead of Dict[str, Any]
- [ ] Consistent CommandResponse patterns across all commands

### 🔒 Security & Compliance (B2B Readiness)

Full roadmap: [`docs/security-compliance-todos.md`](docs/security-compliance-todos.md)

Target frameworks: HIPAA, SOC2 Type II, HITRUST CSF, FedRAMP, ISO 27001, PCI DSS.

| Phase | What | Scope | Depends On |
|-------|------|-------|------------|
| 1 | Audit logging (events table, audit-client lib, account lockout) | ~2-3 sessions | — |
| 2 | Encryption in transit (TLS for Postgres, Redis, MQTT, MinIO) | ~2-3 sessions | — |
| 3 | Encryption at rest (LUKS/FileVault, MinIO SSE, encrypted backups) | ~2 sessions | Phase 2 |
| 4 | RBAC (roles/permissions tables, enforcement middleware, JWT claims) | ~3-4 sessions | Phase 1 |
| 5 | Rate limiting & session management (slowapi, lockout, max sessions) | ~1-2 sessions | Phase 1 |
| 6 | Data classification & PII handling (log sanitization, retention, GDPR deletion) | ~2 sessions | Phase 1 |
| 7 | Network hardening (Docker segmentation, CORS, security headers, MQTT ACLs) | ~1-2 sessions | Phase 2 |
| 8 | Compliance docs & monitoring (policy docs, Grafana dashboards, compliance checks) | ~2 sessions | All |

### ✅ Done
- [x] Local wake word detection (Porcupine)
- [x] IJarvisCommand plugin interface
- [x] JWT auth with refresh tokens
- [x] OCR provider abstraction
- [x] App-to-app authentication
- [x] Centralized logging (jarvis-logs + jarvis-log-client)
- [x] Centralized node authentication (jarvis-auth + jarvis-log-client v0.2.0)
- [x] WiFi provisioning for headless Pi Zero nodes (jarvis-node-setup/provisioning/)
- [x] Refactor jarvis-llm-proxy-api/main.py (1701 → 87 lines)
- [x] Refactor jarvis-command-center/model_service.py (1628 → 309 lines)
- [x] Fix bare `except:` clauses (10 instances in project code)
- [x] Delete network_discovery_service.py (1740 lines, unused)
- [x] Add test suite to jarvis-config-service (44 tests, 93% coverage, CI workflow)
- [x] Speaker/voice identification (Whisper-based)
- [x] Migrate all production print() to JarvisLogger
- [x] Fix all broad `except Exception:` without `as e` (63 production + 13 E2E test instances)
- [x] Voice-identified persistent memory (speaker ID wiring, user memory table, memory-aware prompts, remember/forget tools, voice enrollment API, memory CRUD API)
- [x] Push notifications (jarvis-notifications + relay + mobile integration)
- [x] Deep research tool (web search → scrape → LLM summarize → inbox + push)
- [x] Web scraper library (jarvis-web-scraper, extracted from recipes html_fetcher.py)
- [x] Mobile inbox UI (InboxList + InboxDetail screens, Inbox tab)
- [x] Pantry multi-type bundles (commands + agents + protocols + managers in one package)
- [x] SDK interfaces for IJarvisAgent, IJarvisDeviceProtocol, IJarvisDeviceManager
- [x] HA restructure to convention layout (commands/control_device/, agents/home_assistant/, ha_shared/)
- [x] Reference bundle: jarvis-home-assistant-integration (published, 34/34 container tests)
- [x] Container test base image caching (SDK pre-built, submissions take ~3s)
- [x] Forge (AI package builder) — split-pane IDE, BYOK (6 models), SDK self-documents via `__forge_hints__`, AST validation, one-click GitHub publish
- [x] Mobile Store tab — browse/search Pantry, install to nodes via CC → MQTT
- [x] Batch 2 Pantry extraction (bluetooth, music, email+agent, calendar+agent, 5 device families, news+agent)
- [x] Reminders command (set/list/delete/snooze with recurrence, JarvisStorage persistence)
- [x] Installable routines (new Pantry component type with placeholder/binding system)
- [x] JarvisStorage SDK facade (command_data + secrets abstraction for extracted packages)
- [x] GeocodingHelper SDK (Nominatim + Google Maps backends)
- [x] DateKeys SDK (standardized relative date constants)
- [x] Dockerize jarvis-admin (Dockerfile.dev + docker-compose.dev.yaml)
- [x] Household leave endpoint (self-removal with guards + cleanup)
- [x] Inline alert announcements in voice listener (TTS + snooze for reminders)
- [x] `command_store.py validate` (package validation without installing)
- [x] Jarvis package dependencies (jarvis_dependencies manifest field, auto-generated namespaces, transitive inheritance)

### 🚀 Future Enhancements (Feature Parity Roadmap)

**Smart Home Integration:**
- [x] ~~Home Assistant integration (device control layer)~~ ✅ control_device + get_device_status commands
- [x] ~~Device discovery (Matter, Zigbee, Z-Wave via HA)~~ ✅ HA agent + device manager
- [x] ~~Direct device control ("turn off the lights", "set thermostat to 72")~~ ✅ control_device command
- [x] ~~Routines/automations ("Good morning" → lights + weather + calendar)~~ ✅ Installable routines with placeholder/binding system
- [ ] Broadcast commands to device groups

**Multi-Room & Communication:**
- [ ] Multi-room audio sync
- [ ] Intercom/announcements between nodes
- [ ] "Play everywhere" / room targeting
- [ ] Drop-in between rooms

**Proactive Intelligence:**
- [ ] Background event watchers (calendar, packages, etc.)
- [ ] "Leave now to make your meeting" notifications
- [ ] Package tracking alerts
- [ ] Habit-based suggestions

**Package Store (HACS-style):**
- [x] ~~Community command repository~~ ✅ jarvis-pantry (backend + web)
- [x] ~~User-installable commands~~ ✅ `jarvis pantry install` CLI
- [x] ~~Command discovery/search~~ ✅ Browse/search API + web catalog
- [x] ~~Ratings and reviews~~ ✅ Review system with star ratings
- [ ] Auto-update mechanism
- [x] ~~Multi-type package bundles~~ ✅ Commands + agents + device protocols + device managers in one repo
- [x] ~~Reference bundle~~ ✅ [jarvis-home-assistant-integration](https://github.com/alexberardi/jarvis-home-assistant-integration)
- [x] ~~AI Forge~~ ✅ Split-pane IDE, BYOK (6 models), SDK auto-docs, AST validation, one-click publish
- [x] ~~Mobile Store tab~~ ✅ Browse/install from mobile app via CC → MQTT
- [x] ~~Routine packages~~ ✅ New component type with placeholder/binding system

**Visual/Multi-Modal:**
- [ ] Screen-based responses (for tablet/display nodes)
- [ ] Recipe step-by-step with images
- [ ] Visual timers and status displays

**Quality of Life:**
- [ ] "Just works" setup wizard
- [x] ~~Mobile app for management~~ ✅ jarvis-node-mobile
- [x] ~~Web dashboard for configuration~~ ✅ jarvis-admin (admin), jarvis-web (chat)

## Service Inventory

### Core Services

| Service | Port | Size | Tests | Health |
|---------|------|------|-------|--------|
| jarvis-auth | 7701 | Small | ✅ Good | Clean |
| jarvis-command-center | 7703 | Large | ✅ Good | ✅ model_service.py refactored (309 lines) |
| jarvis-recipes-server | 7030 | Medium | ✅ Good | ✅ url_recipe_parser.py refactored (285 lines) |
| jarvis-whisper-api | 7706 | Small | ✅ Good | Voice profiles API + tests |
| jarvis-ocr-service | 7031 | Medium | ✅ Good | Clean |
| jarvis-llm-proxy-api | 7704/7705 | Medium | ⚠️ Partial | ✅ main.py refactored (87 lines) |
| jarvis-tts | 7707 | Small | ✅ Good (98%) | Clean |
| jarvis-logs | 7702 | Small | ✅ Good | Clean |
| jarvis-mcp | 7709 | Small | ✅ Good | Clean |
| jarvis-config-service | 7700 | Small | ✅ Good (93%) | Clean |
| jarvis-notifications | 7712 | Small | ✅ Good (77%) | Clean |
| jarvis-notifications-relay | - | Small | ✅ Good | Clean |
| jarvis-web | 7722 | Small | - | New (Next.js chat UI) |
| jarvis-pantry | 7721 | Small | ✅ Good | Community package store + Forge |

### Libraries

| Library | Tests | Health |
|---------|-------|--------|
| jarvis-log-client | ✅ Good | Clean |
| jarvis-config-client | ✅ Good | Clean |
| jarvis-web-scraper | ✅ Good (27 tests) | Clean |

### Client Software

| Client | Tests | Health |
|--------|-------|--------|
| jarvis-node-setup | ✅ Fair | All production code uses JarvisLogger, network_discovery.py deleted |

### Good Patterns Observed ✅
- All services and client code use jarvis-log-client for logging
- App-to-app auth via X-Jarvis-App-Id + X-Jarvis-App-Key headers
- Alembic migrations for all database services
- Service discovery via jarvis-config-service
- Small, focused services (auth, whisper, tts, logs, mcp)

---

## Claude's Wishlist

Things that would make me more effective working on this codebase. **This is priority #1** - force multiplier for everything else.

### jarvis-mcp Enhancements
Current: query_logs, get_log_stats, debug tools, health_check, logs_tail

To add:
- [x] **health_check tool** - Hit all service health endpoints, aggregate results, return status
- [x] **logs_tail tool** - One-shot query for recent logs from a service
- [x] **run_tests tool** - Call test scripts or hit admin-protected test endpoints

### jarvis-auth: Admin-Only Auth
- [ ] Add "admin-only" auth style (separate from app-to-app) for protecting sensitive endpoints
- [ ] Use for: test endpoints, settings management, service introspection

### Context & Knowledge (build in CLAUDE.md files)
- [x] **Service dependency graph** - Which services talk to which, what breaks if X is down
- [ ] **Test data fixtures** - Sample voice commands, expected outputs, edge cases
- [ ] **Error catalog** - Common errors and their fixes
- [x] **Per-service CLAUDE.md** - Service-specific context in each repo

### llm-proxy Settings Refactor
- [ ] Move LLM config from env vars → database settings table
- [ ] Hot-reload on settings change (use existing internal endpoints)
- [ ] Then .env.example becomes simple and copy-paste ready

### Voice Interaction
- [x] Working on Pi Zero
- [ ] Set up on Ubuntu dev machine (should be minimal work)

### More MCP Tools

**Developer tools (Claude Code / admin):**
- [ ] **Settings tools** - `settings_get`, `settings_set` via jarvis-settings-server. Read/update service config live without psql
- [ ] **Voice command simulator** - `command_test` tool that sends text through command-center pipeline (parse → intent → tool routing) and returns result
- [ ] **Recipe tools** - `recipe_search`, `recipe_get`, `meal_plan` via jarvis-recipes-server
- [ ] **Node status** - `node_list`, `node_status` to see Pi Zero online state, last activity
- [ ] **Training dashboard** - `training_status`, `adapter_list` to check training jobs and deployed adapters
- [x] **Database MCP** - Read-only access for debugging
- [x] **Docker MCP** - Container status, logs, restart services, compose up/down

**System tools (called by services at runtime):**
- [x] **Date resolution** - `datetime_resolve`, `datetime_context` - resolve "tomorrow morning" → ISO datetime (feat/datetime-tools)
- [ ] **Location resolution** - Resolve "downtown", "near me", "home" → coordinates. Centralizes geocoding for weather, local search, navigation commands
- [ ] **Calendar context** - Query user's calendar (iCloud) for availability, upcoming events. "Am I free tomorrow?" from any service
- [ ] **Timer/alarm management** - Cross-node timer state. Set from kitchen, query from living room. Centralized so any node can interact
- [ ] **Unit conversion** - "350F to Celsius", "cups to liters". Pure logic, useful for recipes and general commands
- [x] **User preferences** - ✅ User memories (remember/forget tools + memory CRUD API). Shared context across conversations via speaker identification

### Testing
- [ ] **Automated integration tests** - CI for service communication
