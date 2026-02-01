# Jarvis

Personal voice assistant with Pi Zero nodes and self-hosted microservices.

**See also: [RULES.md](RULES.md)** - Development rules (working style, coding style, TDD, performance targets)

## For Claude: Use MCP Tools

**IMPORTANT**: When interacting with jarvis services, ALWAYS prefer jarvis-mcp tools over direct curl/HTTP calls:

| Instead of... | Use MCP tool... |
|---------------|-----------------|
| `curl localhost:8006/health` | `debug_health` |
| `curl localhost:8007/health` | `debug_health` |
| Querying logs via curl | `query_logs`, `logs_tail` |
| Getting service info | `debug_service_info` |

The jarvis-mcp server provides these tools:
- `debug_health` - Check health of all services (or specific ones)
- `debug_service_info` - Get detailed info about a service
- `query_logs` - Query logs with filters
- `logs_tail` - Get recent logs from a service
- `get_log_stats` - Get log statistics

## Core Principles

1. **Fully private and open source** - No cloud dependencies by default, all data stays local
2. **Self-hostable with optional cloud** - Same open-source codebase for both; no data selling, full transparency
3. **Fully extensible** - Add capabilities by implementing `IJarvisCommand` interface (see `jarvis-node-setup/core/ijarvis_command.py`)

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

## Services

| Service | Port | Description |
|---------|------|-------------|
| jarvis-auth | 8007 | JWT authentication (register, login, refresh, logout) |
| jarvis-command-center | 8002 | Central voice/command API, node management, tool routing |
| jarvis-whisper-api | 9999 | Speech-to-text via whisper.cpp |
| jarvis-ocr-service | 5009 | OCR with pluggable backends (Tesseract, EasyOCR, Apple Vision) |
| jarvis-recipes-server | 8001 | Recipe CRUD and meal planning |
| jarvis-node-setup | - | Client-side node code (not a server) |

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
poetry install        # or pip install -r requirements.txt
cp .env.example .env  # configure
alembic upgrade head  # if has migrations
uvicorn app.main:app --reload --port <PORT>
```

### Starting Services (for Claude)

**IMPORTANT**: Always use Docker dev scripts to start services, not direct uvicorn commands:

```bash
# jarvis-command-center (port 8002)
cd /home/alex/jarvis/jarvis-command-center && bash run-docker-dev.sh

# Health check endpoint: /api/v0/health
curl http://localhost:8002/api/v0/health
```

This ensures proper environment configuration and database connections.

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
- `jarvis-command-center` (port 8002)
- `jarvis-llm-proxy-api` (port 8000 API, port 8010 queue worker)

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
curl http://localhost:8000/v1/training/status/<job_id>
```

Or use the job ID returned from step 3 to poll status until complete.

### E2E Command Parsing Tests

Run end-to-end tests to validate voice command parsing across all Jarvis commands.

**1. Ensure required services are running**

Use MCP `debug_health` tool to check service status. Required services:
- `jarvis-command-center` (port 8002)
- `jarvis-llm-proxy-api` (port 8000)

If not running, start them (see each service's CLAUDE.md for details):
```bash
# Command Center
cd /home/alex/jarvis/jarvis-command-center && bash run-docker-dev.sh

# LLM Proxy
cd /home/alex/jarvis/jarvis-llm-proxy-api && ./run.sh
```

**2. Run the test suite**

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

**3. Review results**

Results are written to:
- `test_results.json` (or custom path via `-o`)
- `/home/alex/jarvis/jarvis-command-center/temp/test_results.json`

The output includes:
- Summary (pass/fail counts, success rate, response times)
- Per-test results with expected vs actual
- Analysis with command success rates and confusion matrix
- Recommendations for improving low-performing commands

## Backlog

### High Priority
- [ ] Replace bare `except Exception` with specific exceptions (~406 instances across all services)
- [ ] Refactor oversized files:
  - `jarvis-node-setup/services/network_discovery_service.py` (1740 lines)
  - `jarvis-recipes-server/*/url_recipe_parser.py` (1498 lines)
  - `jarvis-command-center/*/model_service.py` (1431 lines)

### Medium Priority
- [ ] Replace `print()` with proper logging in node-setup commands
- [ ] Add CORS headers configuration
- [ ] Add rate limiting to API endpoints
- [ ] E2E tests for full voice flow (node → command-center → service → response)
- [ ] Integration tests between services (auth ↔ command-center, command-center ↔ recipes)
- [ ] Streaming responses for reduced latency

### Low Priority
- [ ] Convert in-code TODOs to GitHub issues
- [ ] Stronger default secrets in .env.example files
- [ ] TypedDict for tool definitions instead of Dict[str, Any]
- [ ] Consistent CommandResponse patterns across all commands

### Done
- [x] Local wake word detection (Porcupine)
- [x] IJarvisCommand plugin interface
- [x] JWT auth with refresh tokens
- [x] OCR provider abstraction
- [x] App-to-app authentication
- [x] Centralized logging (jarvis-logs + jarvis-log-client)
- [x] Centralized node authentication (jarvis-auth + jarvis-log-client v0.2.0)

---

## Claude's Wishlist

Things that would make me more effective working on this codebase. **This is priority #1** - force multiplier for everything else.

### jarvis-mcp Enhancements
Current: query_logs, get_log_stats, debug tools, health_check, logs_tail

To add:
- [x] **health_check tool** - Hit all service health endpoints, aggregate results, return status
- [x] **logs_tail tool** - One-shot query for recent logs from a service
- [ ] **run_tests tool** - Call test scripts or hit admin-protected test endpoints

### jarvis-auth: Admin-Only Auth
- [ ] Add "admin-only" auth style (separate from app-to-app) for protecting sensitive endpoints
- [ ] Use for: test endpoints, settings management, service introspection

### Context & Knowledge (build in CLAUDE.md files)
- [ ] **Service dependency graph** - Which services talk to which, what breaks if X is down
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
- [ ] **Database MCP** - Read-only access for debugging
- [ ] **Docker MCP** - Container status, logs, restart services

### Testing
- [ ] **Automated integration tests** - CI for service communication
