<p align="center">
  <img src="jarvis_indigo500_transparent-logo.png" alt="Jarvis" width="600" />
</p>

<p align="center">
  Personal voice assistant with Pi Zero nodes and self-hosted microservices.
</p>

Fully private, fully extensible, no cloud dependencies. Voice nodes capture audio, send it to the command center for processing via whisper.cpp, route to the appropriate service, and respond via text-to-speech.

**[Install Jarvis](https://alexberardi.github.io/jarvis-installer/configurator)** - Web-based installer that generates a Docker Compose stack for your setup.

## Services

### Core

Always included in every deployment.

| Service | Port | Description | Tests | Docker |
|---------|------|-------------|-------|--------|
| [jarvis-config-service](https://github.com/alexberardi/jarvis-config-service) | 7700 | Centralized configuration and service discovery | [![Tests](https://github.com/alexberardi/jarvis-config-service/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-config-service/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-config-service/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-config-service/actions/workflows/docker-build-push.yml) |
| [jarvis-auth](https://github.com/alexberardi/jarvis-auth) | 7701 | JWT authentication with register, login, refresh, logout | [![Tests](https://github.com/alexberardi/jarvis-auth/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-auth/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-auth/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-auth/actions/workflows/docker-build-push.yml) |
| [jarvis-logs](https://github.com/alexberardi/jarvis-logs) | 7702 | Centralized logging for all services via Loki | [![Tests](https://github.com/alexberardi/jarvis-logs/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-logs/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-logs/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-logs/actions/workflows/docker-build-push.yml) |
| [jarvis-command-center](https://github.com/alexberardi/jarvis-command-center) | 7703 | Central voice/command API, node management, tool routing | [![Tests](https://github.com/alexberardi/jarvis-command-center/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-command-center/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-command-center/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-command-center/actions/workflows/docker-build-push.yml) |
| [jarvis-admin](https://github.com/alexberardi/jarvis-admin) | 7710 | Web admin UI for settings, training, and administration | [![Tests](https://github.com/alexberardi/jarvis-admin/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-admin/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-admin/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-admin/actions/workflows/docker-build-push.yml) |
| [jarvis-settings-server](https://github.com/alexberardi/jarvis-settings-server) | 7708 | Runtime settings aggregator for all services | [![Tests](https://github.com/alexberardi/jarvis-settings-server/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-settings-server/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-settings-server/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-settings-server/actions/workflows/docker-build-push.yml) |

### Recommended

Speech-to-text and text-to-speech for voice interaction.

| Service | Port | Description | Tests | Docker |
|---------|------|-------------|-------|--------|
| [jarvis-whisper-api](https://github.com/alexberardi/jarvis-whisper-api) | 7706 | Speech-to-text via whisper.cpp (base.en included) | [![Tests](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/docker-build-push.yml) |
| [jarvis-tts](https://github.com/alexberardi/jarvis-tts) | 7707 | Text-to-speech synthesis via Piper | [![Tests](https://github.com/alexberardi/jarvis-tts/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-tts/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-tts/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-tts/actions/workflows/docker-build-push.yml) |

### Optional

Add-on services for additional capabilities.

| Service | Port | Description | Tests | Docker |
|---------|------|-------------|-------|--------|
| [jarvis-mcp](https://github.com/alexberardi/jarvis-mcp) | 7709 | Model Context Protocol server for Claude Code | [![Tests](https://github.com/alexberardi/jarvis-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-mcp/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-mcp/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-mcp/actions/workflows/docker-build-push.yml) |
| [jarvis-ocr-service](https://github.com/alexberardi/jarvis-ocr-service) | 7031 | OCR with pluggable backends (Tesseract, EasyOCR, Apple Vision) | [![Tests](https://github.com/alexberardi/jarvis-ocr-service/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-ocr-service/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-ocr-service/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-ocr-service/actions/workflows/docker-build-push.yml) |
| [jarvis-recipes-server](https://github.com/alexberardi/jarvis-recipes-server) | 7030 | Recipe CRUD, URL parsing, and meal planning | [![Tests](https://github.com/alexberardi/jarvis-recipes-server/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-recipes-server/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-recipes-server/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-recipes-server/actions/workflows/docker-build-push.yml) |
| [jarvis-llm-proxy-api](https://github.com/alexberardi/jarvis-llm-proxy-api) | 7704 | LLM inference proxy with adapter training (CUDA) | [![Tests](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/docker-build-push.yml) |

## Client Libraries

Shared libraries used by services for auth, config discovery, and logging.

| Library | Description | Tests |
|---------|-------------|-------|
| [jarvis-config-client](https://github.com/alexberardi/jarvis-config-client) | Service discovery via config-service | [![Tests](https://github.com/alexberardi/jarvis-config-client/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-config-client/actions/workflows/test.yml) |
| [jarvis-log-client](https://github.com/alexberardi/jarvis-log-client) | Structured logging via jarvis-logs | [![Tests](https://github.com/alexberardi/jarvis-log-client/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-log-client/actions/workflows/test.yml) |
| [jarvis-auth-client](https://github.com/alexberardi/jarvis-auth-client) | Auth helpers for service-to-service calls | |
| [jarvis-settings-client](https://github.com/alexberardi/jarvis-settings-client) | Runtime settings client | |

## Client Apps

| App | Description | CI |
|-----|-------------|-----|
| [jarvis-node-setup](https://github.com/alexberardi/jarvis-node-setup) | Pi Zero voice node (Python) | [![Tests](https://github.com/alexberardi/jarvis-node-setup/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-node-setup/actions/workflows/test.yml) |
| [jarvis-node-mobile](https://github.com/alexberardi/jarvis-node-mobile) | Mobile voice node (React Native) | |
| [jarvis-recipes-mobile](https://github.com/alexberardi/jarvis-recipes-mobile) | Recipe app (React Native) | [![Build](https://github.com/alexberardi/jarvis-recipes-mobile/actions/workflows/build-and-deploy.yml/badge.svg)](https://github.com/alexberardi/jarvis-recipes-mobile/actions/workflows/build-and-deploy.yml) |

## Tools

| Tool | Description | CI |
|------|-------------|-----|
| [jarvis-installer](https://github.com/alexberardi/jarvis-installer) | Web-based Docker Compose generator | [![Tests](https://github.com/alexberardi/jarvis-installer/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-installer/actions/workflows/test.yml) [![Deploy](https://github.com/alexberardi/jarvis-installer/actions/workflows/deploy.yml/badge.svg)](https://github.com/alexberardi/jarvis-installer/actions/workflows/deploy.yml) |
| [data-services](https://github.com/alexberardi/data-services) | Shared PostgreSQL, Redis, Loki, Grafana | |

## Architecture

```
Pi Zero Nodes ──► Command Center ──► Auth (JWT)
                       │              Config Service (discovery)
                       │              Logs (centralized logging)
                       │
                  ┌────┴────┐
                  ▼         ▼
             Whisper STT   LLM Proxy
             (speech)      (inference)
                  │
                  ▼
               TTS (Piper)
               (response)
```

All services communicate over a shared Docker network. The config-service acts as the discovery hub — services only need `JARVIS_CONFIG_URL` to find each other.

## Quick Start

Use the [web installer](https://alexberardi.github.io/jarvis-installer/configurator) to generate your stack, or:

```bash
# Clone and run the CLI
git clone https://github.com/alexberardi/jarvis.git
cd jarvis
./jarvis init
./jarvis start --all
```

## Development

Each service is its own repository. Clone the ones you need:

```bash
git clone git@github.com:alexberardi/jarvis-auth.git
cd jarvis-auth
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/python -m alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 7701
```

See each service's own README or CLAUDE.md for specific setup instructions.

## License

Private repository. All rights reserved.
