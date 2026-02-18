<p align="center">
  <img src="jarvis_indigo500_transparent-logo.png" alt="Jarvis" width="600" />
</p>

<p align="center">
  <strong>A fully private, self-hosted voice assistant built from 12+ microservices.</strong><br>
  Local LLM inference, LoRA adapter training, speech-to-text, text-to-speech, speaker identification, and 20+ extensible voice commands — all running on your own hardware.
</p>

<p align="center">
  <a href="https://alexberardi.github.io/jarvis-installer/configurator"><strong>Install Jarvis</strong></a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="#quick-start">Quick Start</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="#architecture">Architecture</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="#services">Services</a>
</p>

---

## Why Jarvis?

Most voice assistants send your voice to the cloud, process it on someone else's hardware, and send back a response. You're renting access to your own assistant — and paying with your data.

Jarvis takes a different approach. Every component runs locally: speech recognition via whisper.cpp, LLM inference via llama.cpp/vLLM/MLX, text-to-speech via Piper, and a command center that routes everything. No internet required. No subscriptions. No one listening.

What makes Jarvis different from other self-hosted alternatives:

- **Real microservice architecture.** Not a monolith with plugins — 12+ independent services with their own databases, CI/CD pipelines, Docker images, and test suites. Swap out any piece without touching the rest.
- **Local LLM inference with per-user fine-tuning.** Run GGUF-quantized models locally with CUDA/Metal/ROCm acceleration, then train LoRA adapters per node to customize how Jarvis understands your specific commands.
- **Speaker identification.** Jarvis knows who's talking. Voice profiles per household member, so each person gets their own context, preferences, and command routing.
- **Pi Zero voice nodes.** $15 hardware with a mic and speaker becomes a room-scale voice endpoint. Headless provisioning — plug in power, connect to the setup WiFi, and it registers itself.
- **Extensible command system.** Implement the `IJarvisCommand` interface, drop it in, and Jarvis picks it up. 20+ built-in commands (weather, timers, smart home, sports scores, recipes, music, general knowledge) with more added regularly.

## Architecture

```
                              ┌─────────────────────────────────────────┐
                              │           DATA SERVICES                 │
                              │  PostgreSQL  Redis  Loki  Grafana  MinIO│
                              └────┬──────────┬──────┬──────────────────┘
                                   │          │      │
                  ┌────────────────┼──────────┼──────┼──────────────────────────┐
                  │                │          │      │          CORE            │
                  │    ┌───────────▼──┐  ┌────▼──────▼──┐  ┌────────────────┐  │
                  │    │ Config       │  │ Auth          │  │ Logs           │  │
                  │    │ Service      │  │ JWT + app-to- │  │ Centralized    │  │
                  │    │ (discovery)  │  │ app auth      │  │ via Loki       │  │
                  │    └──────────────┘  └───────────────┘  └────────────────┘  │
                  └────────────────────────────────────────────────────────────┘
                                              │
         ┌────────────────────────────────────┼────────────────────────────────┐
         │                                    │         COMMAND PIPELINE       │
         │  ┌──────────┐    ┌─────────────────▼───────────┐    ┌───────────┐  │
         │  │ Whisper   │◄───│ Command Center              │───►│ LLM Proxy │  │
         │  │ STT       │    │ Voice API, node management, │    │ GGUF/vLLM │  │
         │  │ + speaker │    │ intent parsing, tool routing │    │ + LoRA    │  │
         │  │   ID      │    └──────────┬──────────────────┘    │ training  │  │
         │  └──────────┘               │                       └───────────┘  │
         └─────────────────────────────┼──────────────────────────────────────┘
                                       │
      ┌────────────────────────────────┼────────────────────────────────────┐
      │                                │          SERVICES                  │
      │  ┌──────────┐  ┌──────────┐  ┌▼─────────┐  ┌──────────┐           │
      │  │ TTS      │  │ Recipes  │  │ OCR      │  │ Settings │  ...      │
      │  │ (Piper)  │  │ + meal   │  │ Tesseract│  │ Server   │           │
      │  │          │  │ planning │  │ EasyOCR  │  │          │           │
      │  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
      └────────────────────────────────────────────────────────────────────┘
                                       │
      ┌────────────────────────────────┼────────────────────────────────────┐
      │                                │          CLIENTS                   │
      │  ┌──────────────┐  ┌──────────▼───┐  ┌──────────┐  ┌───────────┐  │
      │  │ Pi Zero      │  │ Mobile       │  │ Recipes  │  │ Admin     │  │
      │  │ Voice Nodes  │  │ Voice Node   │  │ Mobile   │  │ Web UI    │  │
      │  │ (Python)     │  │ (React Native│) │ (RN)     │  │ (React)   │  │
      │  └──────────────┘  └──────────────┘  └──────────┘  └───────────┘  │
      └────────────────────────────────────────────────────────────────────┘
```

All services communicate over a shared Docker network. The config-service acts as the discovery hub — each service only needs a single env var (`JARVIS_CONFIG_URL`) to find every other service at runtime.

### Voice Pipeline

```
Voice Node          Command Center        Whisper        LLM Proxy        TTS
    │                     │                  │               │              │
    │  audio stream       │                  │               │              │
    ├────────────────────►│                  │               │              │
    │                     │  transcribe      │               │              │
    │                     ├─────────────────►│               │              │
    │                     │  text + speaker  │               │              │
    │                     │◄─────────────────┤               │              │
    │                     │                  │               │              │
    │                     │  parse intent + route            │              │
    │                     ├─────────────────────────────────►│              │
    │                     │  tool call / response            │              │
    │                     │◄─────────────────────────────────┤              │
    │                     │                                  │              │
    │                     │  synthesize speech                              │
    │                     ├───────────────────────────────────────────────►│
    │                     │  audio                                         │
    │                     │◄───────────────────────────────────────────────┤
    │  audio response     │                                                │
    │◄────────────────────┤                                                │
```

### Service Communication Patterns

| Pattern | How | Used By |
|---------|-----|---------|
| **User auth** | `Authorization: Bearer <JWT>` | Admin UI, mobile apps |
| **App-to-app auth** | `X-Jarvis-App-Id` + `X-Jarvis-App-Key` headers | All inter-service calls |
| **Node auth** | `X-API-Key` (node_id:node_key) | Pi Zero and mobile voice nodes |
| **Service discovery** | `GET /services` from config-service, cached locally | All services |
| **Centralized logging** | All services &rarr; jarvis-logs &rarr; Loki | All services via jarvis-log-client |

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
| [jarvis-whisper-api](https://github.com/alexberardi/jarvis-whisper-api) | 7706 | Speech-to-text via whisper.cpp with speaker identification | [![Tests](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/docker-build-push.yml) |
| [jarvis-tts](https://github.com/alexberardi/jarvis-tts) | 7707 | Text-to-speech synthesis via Piper | [![Tests](https://github.com/alexberardi/jarvis-tts/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-tts/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-tts/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-tts/actions/workflows/docker-build-push.yml) |

### Optional

Add-on services for additional capabilities.

| Service | Port | Description | Tests | Docker |
|---------|------|-------------|-------|--------|
| [jarvis-llm-proxy-api](https://github.com/alexberardi/jarvis-llm-proxy-api) | 7704 | Local LLM inference (GGUF/vLLM/MLX) with LoRA adapter training | [![Tests](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/docker-build-push.yml) |
| [jarvis-mcp](https://github.com/alexberardi/jarvis-mcp) | 7709 | Model Context Protocol server for Claude Code | [![Tests](https://github.com/alexberardi/jarvis-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-mcp/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-mcp/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-mcp/actions/workflows/docker-build-push.yml) |
| [jarvis-ocr-service](https://github.com/alexberardi/jarvis-ocr-service) | 7031 | OCR with pluggable backends (Tesseract, EasyOCR, Apple Vision) | [![Tests](https://github.com/alexberardi/jarvis-ocr-service/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-ocr-service/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-ocr-service/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-ocr-service/actions/workflows/docker-build-push.yml) |
| [jarvis-recipes-server](https://github.com/alexberardi/jarvis-recipes-server) | 7030 | Recipe CRUD, URL parsing, and meal planning | [![Tests](https://github.com/alexberardi/jarvis-recipes-server/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-recipes-server/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-recipes-server/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-recipes-server/actions/workflows/docker-build-push.yml) |

### Client Libraries

| Library | Description | Tests |
|---------|-------------|-------|
| [jarvis-config-client](https://github.com/alexberardi/jarvis-config-client) | Service discovery via config-service | [![Tests](https://github.com/alexberardi/jarvis-config-client/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-config-client/actions/workflows/test.yml) |
| [jarvis-log-client](https://github.com/alexberardi/jarvis-log-client) | Structured logging via jarvis-logs | [![Tests](https://github.com/alexberardi/jarvis-log-client/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-log-client/actions/workflows/test.yml) |
| [jarvis-auth-client](https://github.com/alexberardi/jarvis-auth-client) | Auth helpers for service-to-service calls | [![Tests](https://github.com/alexberardi/jarvis-auth-client/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-auth-client/actions/workflows/test.yml) |
| [jarvis-settings-client](https://github.com/alexberardi/jarvis-settings-client) | Runtime settings client | [![Tests](https://github.com/alexberardi/jarvis-settings-client/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-settings-client/actions/workflows/test.yml) |

### Client Apps

| App | Description | CI |
|-----|-------------|-----|
| [jarvis-node-setup](https://github.com/alexberardi/jarvis-node-setup) | Pi Zero voice node (Python) | [![Tests](https://github.com/alexberardi/jarvis-node-setup/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-node-setup/actions/workflows/test.yml) |
| [jarvis-node-mobile](https://github.com/alexberardi/jarvis-node-mobile) | Mobile voice node (React Native) | [![Tests](https://github.com/alexberardi/jarvis-node-mobile/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-node-mobile/actions/workflows/test.yml) |
| [jarvis-recipes-mobile](https://github.com/alexberardi/jarvis-recipes-mobile) | Recipe app (React Native) | [![Build](https://github.com/alexberardi/jarvis-recipes-mobile/actions/workflows/build-and-deploy.yml/badge.svg)](https://github.com/alexberardi/jarvis-recipes-mobile/actions/workflows/build-and-deploy.yml) |

### Tools

| Tool | Description | CI |
|------|-------------|-----|
| [jarvis-installer](https://github.com/alexberardi/jarvis-installer) | Web-based Docker Compose generator | [![Tests](https://github.com/alexberardi/jarvis-installer/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-installer/actions/workflows/test.yml) [![Deploy](https://github.com/alexberardi/jarvis-installer/actions/workflows/deploy.yml/badge.svg)](https://github.com/alexberardi/jarvis-installer/actions/workflows/deploy.yml) |
| [data-services](https://github.com/alexberardi/data-services) | Shared PostgreSQL, Redis, Loki, Grafana | |

## LLM Inference

The LLM proxy supports multiple inference backends, so you can match your hardware:

| Backend | Best For | Acceleration |
|---------|----------|--------------|
| **GGUF** (llama.cpp) | Most setups — quantized models, low memory | CUDA, Metal, ROCm, CPU |
| **vLLM** | High-throughput GPU servers | CUDA |
| **MLX** | Apple Silicon Macs | Metal |
| **Transformers** | HuggingFace models without conversion | CUDA, CPU |
| **REST** | Remote APIs (OpenAI, Anthropic, Ollama) | N/A |

### LoRA Adapter Training

Jarvis can fine-tune per-node LoRA adapters to improve command recognition for your specific voice and vocabulary:

1. Record voice samples from normal usage
2. Kick off training via the API or admin UI (async job queue with priority)
3. Adapter is automatically converted to GGUF format and loaded per-request
4. Each household member / voice node can have its own adapter

## Built-in Commands

| Category | Commands |
|----------|----------|
| **Information** | Weather (5-day forecast), general knowledge, web search, calendar |
| **Smart Home** | Device control, device status |
| **Timers** | Set, check, cancel timers |
| **Media** | Play music, pause/skip/volume control |
| **Utilities** | Calculator, unit conversion, timezone queries |
| **Entertainment** | Sports scores and schedules, jokes, stories |
| **Cooking** | Recipe search, URL import, meal planning, OCR from photos |
| **Conversation** | General chat with context memory |

Add your own by implementing the `IJarvisCommand` interface — define parameters, validation, and examples, and Jarvis handles the rest.

## Quick Start

Use the [web installer](https://alexberardi.github.io/jarvis-installer/configurator) to generate your Docker Compose stack, or run the CLI:

```bash
git clone https://github.com/alexberardi/jarvis.git
cd jarvis
./jarvis init       # generate tokens, configure databases, run migrations
./jarvis start --all  # start all services in dependency order
```

`./jarvis doctor` runs diagnostics if anything looks off.

## Development

Each service is its own repository with its own CI pipeline. Clone the ones you need:

```bash
git clone git@github.com:alexberardi/jarvis-auth.git
cd jarvis-auth
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/python -m alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 7701
```

See each service's README for specific setup instructions.

## License

MIT License. See [LICENSE](LICENSE) for details.
