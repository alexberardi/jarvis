# Jarvis TODO

## In Progress
- [ ] Fix 4 remaining test failures - test_command_parsing needs utterances NOT from training data to verify speech flexibility/generalization

## High Priority
- [ ] **Build out Claude Code environment** - Force multiplier for everything else
  - [x] jarvis-mcp: health_check tool (aggregate all service health endpoints)
  - [x] jarvis-logs: log_tail endpoint (SSE at /api/v0/logs/stream)
  - [x] jarvis-mcp: logs_tail tool (one-shot query for recent logs)
  - [x] jarvis-auth: admin-only auth style for protected endpoints
  - [x] jarvis-mcp: run_tests tool (admin-protected test endpoints or scripts)
  - [ ] Set up jarvis voice on Ubuntu dev machine (deferred)
  - [ ] Build out CLAUDE.md context (dependency graph, error catalog, fixtures)
    - [x] Service dependency graph in top-level CLAUDE.md
    - [ ] Error catalog (common failures + fixes)
    - [ ] Test fixtures / seed data examples
  - [x] Per-service CLAUDE.md files with service-specific context
  - [ ] llm-proxy: move config from env vars → database settings table with hot-reload
- [x] Database MCP server - read-only access for debugging
  - [ ] Docker MCP server - container status, logs, restart
  - [ ] Automated integration tests - CI for service communication
- [ ] **Node authentication paradigm** - nodes should NOT have app-to-app auth (can't let them hit llm-proxy directly). Need separate auth flow for nodes.
- [ ] Integrate jarvis-log-client into remaining services (llm-proxy, ocr-service, recipes-server, node-setup) - blocked by node auth design
- [ ] Voice recognition + speaker mapping for whisper server (who's talking?)
- [ ] Find OCR model that fits on 3080ti

## Medium Priority
- [ ] Dockerize llm-proxy (Linux only, no macOS support)
- [ ] Replace bare `except Exception` with specific exceptions (~406 instances across services)
- [ ] Refactor oversized files:
  - [ ] `jarvis-node-setup/services/network_discovery_service.py` (1740 lines)
  - [ ] `jarvis-recipes-server/*/url_recipe_parser.py` (1498 lines)
  - [ ] `jarvis-command-center/*/model_service.py` (1431 lines)
- [ ] Make jarvis-log-client repo public (for pip install from GitHub)

## Low Priority
- [ ] Replace `print()` with proper logging in node-setup commands
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
- [x] Centralized logging system (jarvis-logs + jarvis-log-client)
- [x] Integrate logging in jarvis-command-center
- [x] Integrate logging in jarvis-auth
- [x] Local wake word detection (Porcupine)
- [x] IJarvisCommand plugin interface
- [x] JWT auth with refresh tokens
- [x] OCR provider abstraction
- [x] App-to-app authentication
