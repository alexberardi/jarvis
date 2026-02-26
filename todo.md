# Jarvis TODO

## In Progress
- [ ] Fix 4 remaining test failures - test_command_parsing needs utterances NOT from training data to verify speech flexibility/generalization

## High Priority
- [ ] Create `GETTING_STARTED.md` - Single walkthrough from clone to working system
- [ ] Create error catalog / troubleshooting guide (common failures + fixes)
- [ ] Test fixtures / seed data examples for development and testing
- [ ] Voice recognition + speaker mapping for whisper server (who's talking?)
- [ ] Automated integration tests - CI for service communication
- [ ] Set up jarvis voice on Ubuntu dev machine (deferred)

## Medium Priority
- [ ] Dockerize llm-proxy (Linux only, no macOS support)
- [ ] Make jarvis-log-client repo public (for pip install from GitHub)

## Low Priority
- [ ] Add CORS headers configuration
- [ ] Add rate limiting to API endpoints
- [ ] E2E tests for full voice flow (node → command-center → service → response)
- [ ] Integration tests between services (auth ↔ command-center, command-center ↔ recipes)
- [ ] Streaming responses for reduced latency
- [ ] Convert in-code TODOs to GitHub issues
- [ ] Stronger default secrets in .env.example files
- [ ] TypedDict for tool definitions instead of Dict[str, Any]
- [ ] Consistent CommandResponse patterns across all commands

## Completed

### Dev Ergonomics Overhaul
- [x] Unified task runner - `./jarvis test [--all] [--coverage]` (17 services)
- [x] Standardize test invocation across services - `./jarvis test` handles pytest/poetry/npm differences
- [x] Add CI coverage reporting (10+ services have CI workflows with coverage)
- [x] CLAUDE.md files for all services (22/23 repos, only empty jarvis-mcp-client skipped)
- [x] Document mixed local/Docker dev model (CLAUDE.md Development Model section)

### Claude Code Environment
- [x] jarvis-mcp: health_check, logs_tail, run_tests tools
- [x] jarvis-logs: log_tail endpoint (SSE at /api/v0/logs/stream)
- [x] jarvis-auth: admin-only auth style for protected endpoints
- [x] Docker MCP server - container status, logs, restart, compose up/down
- [x] Database MCP server - read-only access for debugging
- [x] Service dependency graph in top-level CLAUDE.md

### Architecture & Code Quality
- [x] Refactor jarvis-llm-proxy-api/main.py (1701 → 87 lines)
- [x] Refactor jarvis-command-center/model_service.py (1628 → 345 lines)
- [x] Refactor jarvis-recipes-server/url_recipe_parser.py (1498 → 285 lines)
- [x] Delete jarvis-node-setup/network_discovery_service.py (1740 lines, unused)
- [x] Fix broad `except Exception:` without `as e`
- [x] Migrate all production print() to JarvisLogger

### Infrastructure & Auth
- [x] Centralized logging system (jarvis-logs + jarvis-log-client, integrated in all services)
- [x] Node authentication paradigm (validate-node + validate-node-household)
- [x] LLM proxy config in database settings table with hot-reload
- [x] App-to-app authentication
- [x] JWT auth with refresh tokens

### Testing
- [x] Add test suite to jarvis-config-service (44 tests, 93% coverage)
- [x] Add test suite to jarvis-ocr-service (5 test files)
- [x] Add test suite to jarvis-tts (59 tests, 98% coverage)

### Features
- [x] Local wake word detection (Porcupine)
- [x] IJarvisCommand plugin interface
- [x] OCR provider abstraction
- [x] Speaker/voice identification (Whisper-based)
