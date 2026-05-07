# Jarvis

Personal voice assistant with Pi Zero nodes and self-hosted microservices.

**See also: [RULES.md](RULES.md)** — development rules (working style, coding style, TDD, performance targets).

## Core Principles

1. **Fully private and open source** — no cloud dependencies by default, all data stays local
2. **Self-hostable with optional cloud** — same open-source codebase for both
3. **Fully extensible** — add capabilities by implementing `IJarvisCommand` (see `jarvis-node-setup/core/ijarvis_command.py`)

## For Claude: Use MCP Tools

**ALWAYS prefer jarvis-mcp tools over direct curl/HTTP/docker calls:**

| Instead of... | Use MCP tool... |
|---------------|-----------------|
| `curl localhost:7702/health` etc. | `debug_health` |
| Querying logs via curl | `query_logs`, `logs_tail`, `get_log_stats` |
| Getting service info | `debug_service_info` |
| `docker ps` | `docker_ps` |
| `docker logs <container>` | `docker_logs` |
| `docker restart <container>` | `docker_restart` / `docker_stop` / `docker_start` |
| `docker compose up/down` | `docker_compose_up` / `docker_compose_down` / `docker_compose_list` |

## Services

| Service | Port | Description |
|---------|------|-------------|
| jarvis-config-service | 7700 | Service discovery (everyone depends on this) |
| jarvis-auth | 7701 | JWT auth (register, login, refresh, app-to-app) |
| jarvis-logs | 7702 | Centralized logging (Loki/Grafana on 7032/7033) |
| jarvis-command-center | 7703 | Voice/command orchestrator, tool routing |
| jarvis-llm-proxy-api | 7704/7705 | LLM inference (API + queue worker) |
| jarvis-whisper-api | 7706 | Speech-to-text via whisper.cpp |
| jarvis-tts | 7707 | Text-to-speech (Piper) |
| jarvis-settings-server | 7708 | Settings aggregator (for admin UI) |
| jarvis-mcp | 7709 | Claude Code integration |
| jarvis-admin | 7710 | Web admin UI |
| jarvis-notifications | 7712 | Push + inbox |
| jarvis-pantry | 7721 | Community package store + Forge |
| jarvis-web | 7722 | Web chat (Next.js) |
| jarvis-recipes-server | 7030 | Recipe CRUD + meal planning |
| jarvis-ocr-service | 7031 | OCR (Tesseract/EasyOCR/Apple Vision) |

Libraries: `jarvis-log-client`, `jarvis-config-client`, `jarvis-web-scraper`, `jarvis-command-sdk`.
Clients: `jarvis-node-setup` (Pi Zero), `jarvis-node-mobile`.
Shared infra: PostgreSQL, Redis, MinIO, Mosquitto.

Each service has its own `CLAUDE.md` with details — read it before working in that service.

## Development Rules

**Logging:**
- ALL logging goes through `jarvis-log-client` to `jarvis-logs`. Use `JarvisLogger`, not `print()`.
- See `jarvis-log-client/CLAUDE.md` for usage.

**Testing:**
- TDD preferred: RED → GREEN → IMPROVE.
- Target 80%+ coverage. Run `pytest` before committing.

**Running services:**
- Check the service's own `CLAUDE.md` / `README.md` first.
- Prefer Docker dev scripts (e.g. `run-docker-dev.sh`) over direct `uvicorn`.
- New services: prefer Docker (Dockerfile + docker-compose.yaml), follow FastAPI + Uvicorn pattern.

**Code style:**
- Imports at the top of the file, grouped stdlib → third-party → local. No mid-file imports unless resolving circular deps.
- Type hints everywhere — variables, params, returns. Prefer `X | None` over `Optional[X]` (Python 3.10+).

## Service Communication

- **App-to-app:** `X-Jarvis-App-Id` + `X-Jarvis-App-Key` headers, validated via `jarvis-auth /internal/validate-app`.
- **Node auth:** `X-API-Key` header (`node_id:node_key`), validated by service against `jarvis-auth`.
- **User auth:** `Authorization: Bearer <jwt>`, validated locally with shared secret.
- **Service discovery:** every service queries `jarvis-config-service /services` for URLs (cached locally).

### Critical Path for Voice Commands
`jarvis-config-service` → `jarvis-auth` → `jarvis-command-center` → `jarvis-llm-proxy-api` (whisper + tts as needed).

## Cross-Service Environment Variables

| Variable | Used By | Description |
|----------|---------|-------------|
| `DATABASE_URL` | auth, command-center, recipes, notifications, llm-proxy | PostgreSQL connection |
| `SECRET_KEY` | auth | JWT signing key (shared secret for JWT validation) |
| `ADMIN_API_KEY` | command-center | Admin endpoint protection |
| `JARVIS_AUTH_BASE_URL` | most services | Auth service URL |
| `JARVIS_CONFIG_URL` | most services | Config service URL (default `http://localhost:7700`) |
| `JARVIS_APP_ID` / `JARVIS_APP_KEY` | most services | App-to-app credentials |

## Development Model (Mixed Local/Docker)

The `./jarvis` CLI handles platform differences automatically.

**macOS (Apple Silicon):** GPU-dependent services run **locally** to access Metal / Apple Vision; everything else in Docker. The `jarvis` script overrides `mode=docker` → `mode=local` for `jarvis-llm-proxy-api` and `jarvis-ocr-service`. Local services reach Docker infra via `localhost`; Docker reaches local services via `host.docker.internal` (mapped via `extra_hosts`). `JARVIS_CONFIG_URL_STYLE=dockerized` makes config-service return `host.docker.internal` URLs to Docker consumers.

**Linux (NVIDIA GPU):** everything in Docker, including LLM/OCR. GPU services use `nvidia-docker` (NVIDIA Container Toolkit) with `deploy.resources.reservations.devices` for CUDA passthrough.

**Network modes:**

| Mode | Flag | Communication |
|------|------|---------------|
| Bridge (default) | — | Shared `jarvis-net`, services use container names |
| Host | `--no-network` | No shared network, uses `host.docker.internal` |
| Standalone | `--standalone` | Single service with its own PostgreSQL container |

## Environments & Hosts

### Dev (free-fire zone)

| Host | Address | Role | SSH |
|------|---------|------|-----|
| Pi Zero node | `jarvis-dev.local` | Physical voice node | `pi@jarvis-dev.local` |
| Ubuntu desktop | `10.0.0.122` | GPU services (LLM, Whisper) | `alex@10.0.0.122` |
| Laptop (macOS) | `10.0.0.103` | Rest of Docker stack + dev | local |
| Laptop node container | `localhost:7771` | Dockerized jarvis-node | — |

LLM proxy and Whisper sometimes run on the laptop to verify macOS/Metal still works.

### Prod

| Host | Address | Role | SSH |
|------|---------|------|-----|
| Prod server | `10.0.0.107` | Ubuntu, full Docker stack | `jarvis@10.0.0.107` |
| Prod kitchen node | `jarvis-kitchen.local` | Kitchen Pi Zero | `pi@jarvis-kitchen.local` |

**⚠️ PROD RULES:**
- **NEVER** write directly to prod (`~/.jarvis/compose`) without explicit user instructions.
- Prod is primarily for **reading logs and checking status**.
- When in doubt, test in dev first.

## Speaker ID & Memory Flow

Whisper returns `{text, speaker: {user_id, confidence}}`. Command-center resolves `user_id` → display name via `jarvis-auth` (5min cache), loads memories from PostgreSQL via `MemoryService`, and injects speaker name + memories into the LLM system prompt. The LLM can call `remember(...)` / `forget(...)` server tools.

Key files:
- Node: `jarvis-node-setup/stt_providers/jarvis_whisper_client.py`
- Command-center: `app/core/utils/speaker_resolver.py`, `app/services/memory_service.py`, `app/core/tools/{remember,forget}_tool.py`, `app/api/memories.py`
- Whisper: `app/api/voice_profiles.py` (enrollment)
