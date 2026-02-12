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

## Codebase Health (Last Updated: 2026-02-11)

| Dimension | Score | Notes |
|-----------|-------|-------|
| **Architecture** | 8/10 | Monolithic files split (llm-proxy, command-center), clean module boundaries |
| **Design** | 7/10 | Good separation of concerns, improved exception handling |
| **Security** | 7/10 | JWT auth, encrypted secrets, app-to-app auth. Needs: rate limiting, CORS |
| **Testing** | 7/10 | Core services tested, ocr-service tests added |
| **Documentation** | 8/10 | Per-service CLAUDE.md, comprehensive main docs |
| **Maintainability** | 8/10 | Smaller files, specific exceptions, all logging via JarvisLogger |
| **Code Quality** | 8/10 | Bare excepts fixed, broad exceptions fixed, print() migrated |
| **Observability** | 8/10 | All production code uses JarvisLogger (worker `_safe_print` is acceptable) |

**Average: 7.63/10** → Target: 8/10

### Quick Wins to Improve
- [x] ~~Add tests to config-service~~ ✅ 44 tests, 93% coverage
- [x] ~~Add tests to ocr-service~~ ✅ 5 test files (validation, llm queue, callback, continue processing, async flow)
- [x] ~~Migrate print() files to JarvisLogger~~ ✅ All production code migrated (remaining prints are CLI scripts, tests, worker `_safe_print`)
- [ ] Refactor url_recipe_parser.py (Architecture: 8→9)
- [ ] Fix mid-file imports in espn_sports_service.py

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

### 🔴 Critical - Monolithic Files (Immediate Refactor)

| File | Lines | Issue |
|------|-------|-------|
| ~~`jarvis-llm-proxy-api/main.py`~~ | ~~1701~~ → 87 | ✅ **DONE** - Split into modules |
| ~~`jarvis-command-center/app/core/model_service.py`~~ | ~~1628~~ → 309 | ✅ **DONE** - Split into prompt_engine, tool_parser, tool_executor |
| `jarvis-recipes-server/*/url_recipe_parser.py` | 1498 | All recipe sites in one parser |

~~`jarvis-node-setup/services/network_discovery_service.py`~~ - DELETED (1740 lines, unused)

### ~~🔴 Critical - Logging Violations~~ ✅ DONE

~~**jarvis-node-setup has 22 files using `print()` instead of `jarvis-log-client`**~~ All production files migrated to JarvisLogger. Remaining `print()` usage is acceptable: CLI scripts (set_secret.py, authorize_node.py), test/E2E scripts, and worker `_safe_print()` pattern.

### 🟡 High Priority - Missing Test Suites

| Service | Port | Status |
|---------|------|--------|
| ~~jarvis-ocr-service~~ | ~~5009~~ | ✅ **DONE** - 5 test files (validation, llm queue, callback, async flow) |
| jarvis-tts | 8009 | ⚠️ Minimal (test_deps.py only) |
| ~~jarvis-config-service~~ | ~~8013~~ | ✅ **DONE** - 44 tests, 93% coverage |

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
- [ ] jarvis-recipes-server: Modular parser strategy (one parser per recipe site)
- [x] ~~jarvis-command-center: Split model_service.py into prompt_engine.py, tool_parser.py, tool_executor.py~~ - ✅ **DONE** (1628 → 309 lines)

### 🔵 Low Priority

- [ ] Convert in-code TODOs to GitHub issues
- [ ] Stronger default secrets in .env.example files
- [ ] TypedDict for tool definitions instead of Dict[str, Any]
- [ ] Consistent CommandResponse patterns across all commands

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

### 🚀 Future Enhancements (Feature Parity Roadmap)

**Smart Home Integration:**
- [ ] Home Assistant integration (device control layer)
- [ ] Device discovery (Matter, Zigbee, Z-Wave via HA)
- [ ] Direct device control ("turn off the lights", "set thermostat to 72")
- [ ] Routines/automations ("Good morning" → lights + weather + calendar)
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

**Command Store (HACS-style):**
- [ ] Community command repository
- [ ] User-installable commands (no coding required)
- [ ] Command discovery/search
- [ ] Ratings and reviews
- [ ] Auto-update mechanism

**Visual/Multi-Modal:**
- [ ] Screen-based responses (for tablet/display nodes)
- [ ] Recipe step-by-step with images
- [ ] Visual timers and status displays

**Quality of Life:**
- [ ] "Just works" setup wizard
- [ ] Mobile app for management
- [ ] Web dashboard for configuration

## Service Inventory

### Core Services

| Service | Port | Size | Tests | Health |
|---------|------|------|-------|--------|
| jarvis-auth | 8007 | Small | ✅ Good | Clean |
| jarvis-command-center | 8002 | Large | ✅ Good | ✅ model_service.py refactored (309 lines) |
| jarvis-recipes-server | 8001 | Medium | ✅ Good | url_recipe_parser.py needs split |
| jarvis-whisper-api | 8012 | Small | ⚠️ Minimal | Clean |
| jarvis-ocr-service | 5009 | Medium | ✅ Good | Clean |
| jarvis-llm-proxy-api | 8000/8010 | Medium | ⚠️ Partial | ✅ main.py refactored (87 lines) |
| jarvis-tts | 8009 | Small | ⚠️ Minimal | Needs more tests |
| jarvis-logs | 8006 | Small | ✅ Good | Clean |
| jarvis-mcp | 8011 | Small | ✅ Good | Clean |
| jarvis-config-service | 8013 | Small | ✅ Good (93%) | Clean |

### Libraries

| Library | Tests | Health |
|---------|-------|--------|
| jarvis-log-client | ✅ Good | Clean |
| jarvis-config-client | ✅ Good | Clean |

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
