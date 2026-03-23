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
- **Community package store + AI Forge.** Browse and install community packages from the [Pantry](https://pantry.jarvisautomation.io). Or use the Forge — describe what you want in plain English and an AI generates a complete, validated package you can publish with one click.

## Forge

The Forge is an AI-powered package builder built into the Pantry web UI. It generates complete Jarvis packages — commands, agents, device protocols, device managers, or multi-component bundles — from natural language descriptions.

```
 You: "A command that fetches cryptocurrency prices by ticker symbol using CoinGecko"
   │
   ▼
 Forge ──► SDK introspects itself (forge.py) ──► builds system prompt
   │         with interface contracts, manifest schema,
   │         validation rules, constructor signatures
   ▼
 LLM generates: command.py + jarvis_command.yaml + README.md + LICENSE
   │
   ▼
 AST validation ──► static analysis runs on generated code before you see it
   │
   ▼
 Split-pane IDE ──► chat on left, editable code with syntax highlighting on right
   │
   ▼
 One-click publish ──► creates GitHub repo ──► submits to Pantry pipeline
```

**How it works under the hood:** The SDK decorates every interface class with `__forge_hints__` metadata. At runtime, `forge.py` walks all SDK classes via `inspect` + `get_type_hints`, combines them with manifest schema and validation rules, and produces a structured spec (~550 lines of Markdown). This spec becomes the LLM's system prompt — so it's always in sync with the actual interfaces. When you add a method to `IJarvisCommand`, the Forge automatically knows about it.

**BYOK:** Users provide their own API key. Six models available (Haiku 4.5, Sonnet 4, Opus 4, GPT-4o, ChatGPT-5, Codex) with per-generation cost estimates shown in the UI.

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
      │  │ TTS      │  │ Recipes  │  │ OCR      │  │ Settings │           │
      │  │ (Piper)  │  │ + meal   │  │ Tesseract│  │ Server   │  ...     │
      │  │          │  │ planning │  │ EasyOCR  │  │          │           │
      │  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
      │  │ Notif.   │  │ Notif.   │                                       │
      │  │ Service  │  │ Relay    │                                       │
      │  │ push+    │  │ Expo→    │                                       │
      │  │ inbox    │  │ APNs/FCM │                                       │
      │  └──────────┘  └──────────┘                                       │
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
| [jarvis-notifications](https://github.com/alexberardi/jarvis-notifications) | 7712 | Push notifications, inbox, and deep research delivery | [![Tests](https://github.com/alexberardi/jarvis-notifications/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-notifications/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-notifications/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-notifications/actions/workflows/docker-build-push.yml) |
### Cloud

Optional cloud-hosted services and public-facing web apps.

| Service | Port | Description | CI |
|---------|------|-------------|-----|
| [jarvis-notifications-relay](https://github.com/alexberardi/jarvis-notifications-relay) | - | Stateless Expo Push API proxy for APNs/FCM delivery | [![Tests](https://github.com/alexberardi/jarvis-notifications-relay/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-notifications-relay/actions/workflows/test.yml) |
| [jarvis-pantry](https://github.com/alexberardi/jarvis-pantry) | 7721 | Community package store API (browse, submit, review, Forge) | [![Tests](https://github.com/alexberardi/jarvis-pantry/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-pantry/actions/workflows/test.yml) |
| [jarvis-pantry-web](https://github.com/alexberardi/jarvis-pantry-web) | 7720 | Pantry web frontend (Next.js) — catalog browser + AI Forge | [![CI](https://github.com/alexberardi/jarvis-pantry-web/actions/workflows/ci.yml/badge.svg)](https://github.com/alexberardi/jarvis-pantry-web/actions/workflows/ci.yml) |
| [jarvis-docs](https://github.com/alexberardi/jarvis-docs) | - | Project documentation (MkDocs) | |
| [jarvis-command-sdk](https://github.com/alexberardi/jarvis-command-sdk) | - | Core interfaces + Forge spec generator (pip package) | |

### Community Packages

Standalone command packages installable via the Pantry. Each was extracted from the built-in command set into its own repo.

| Package | Description |
|---------|-------------|
| [jarvis-home-assistant-integration](https://github.com/alexberardi/jarvis-home-assistant-integration) | Smart home device control + status via Home Assistant |
| [jarvis-cmd-news](https://github.com/alexberardi/jarvis-cmd-news) | RSS news headlines by category |
| [jarvis-cmd-weather](https://github.com/alexberardi/jarvis-cmd-weather) | Weather conditions and forecasts via OpenWeather API |
| [jarvis-cmd-sports](https://github.com/alexberardi/jarvis-cmd-sports) | Sports scores, live games, and schedules via ESPN |
| [jarvis-cmd-web-search](https://github.com/alexberardi/jarvis-cmd-web-search) | Live web search via Bing or DuckDuckGo |
| [jarvis-cmd-story](https://github.com/alexberardi/jarvis-cmd-story) | Chunked bedtime story generation via LLM |
| [jarvis-cmd-bluetooth](https://github.com/alexberardi/jarvis-cmd-bluetooth) | Bluetooth device scan, pair, connect, disconnect |
| [jarvis-cmd-music](https://github.com/alexberardi/jarvis-cmd-music) | Music playback and control via Music Assistant |
| [jarvis-cmd-email](https://github.com/alexberardi/jarvis-cmd-email) | Email management (Gmail + IMAP) with alert agent |
| [jarvis-cmd-calendar](https://github.com/alexberardi/jarvis-cmd-calendar) | Calendar events (iCloud + Google) with alert agent |
| [jarvis-device-kasa](https://github.com/alexberardi/jarvis-device-kasa) | TP-Link Kasa/Tapo LAN device control |
| [jarvis-device-lifx](https://github.com/alexberardi/jarvis-device-lifx) | LIFX smart lights LAN control |
| [jarvis-device-govee](https://github.com/alexberardi/jarvis-device-govee) | Govee smart devices (LAN + cloud) |
| [jarvis-device-apple](https://github.com/alexberardi/jarvis-device-apple) | Apple TV and HomePod control via AirPlay |
| [jarvis-device-nest](https://github.com/alexberardi/jarvis-device-nest) | Google Nest thermostat and camera via SDM API |

### Client Libraries

| Library | Description | Tests |
|---------|-------------|-------|
| [jarvis-config-client](https://github.com/alexberardi/jarvis-config-client) | Service discovery via config-service | [![Tests](https://github.com/alexberardi/jarvis-config-client/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-config-client/actions/workflows/test.yml) |
| [jarvis-log-client](https://github.com/alexberardi/jarvis-log-client) | Structured logging via jarvis-logs | [![Tests](https://github.com/alexberardi/jarvis-log-client/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-log-client/actions/workflows/test.yml) |
| [jarvis-auth-client](https://github.com/alexberardi/jarvis-auth-client) | Auth helpers for service-to-service calls | [![CI](https://github.com/alexberardi/jarvis-auth-client/actions/workflows/ci.yml/badge.svg)](https://github.com/alexberardi/jarvis-auth-client/actions/workflows/ci.yml) |
| [jarvis-settings-client](https://github.com/alexberardi/jarvis-settings-client) | Runtime settings client | [![CI](https://github.com/alexberardi/jarvis-settings-client/actions/workflows/ci.yml/badge.svg)](https://github.com/alexberardi/jarvis-settings-client/actions/workflows/ci.yml) |
| [jarvis-web-scraper](https://github.com/alexberardi/jarvis-web-scraper) | Web scraping and content extraction | [![Tests](https://github.com/alexberardi/jarvis-web-scraper/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-web-scraper/actions/workflows/test.yml) |

### Client Apps

| App | Description | CI |
|-----|-------------|-----|
| [jarvis-node-setup](https://github.com/alexberardi/jarvis-node-setup) | Pi Zero voice node (Python) | [![Tests](https://github.com/alexberardi/jarvis-node-setup/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-node-setup/actions/workflows/test.yml) |
| [jarvis-node-mobile](https://github.com/alexberardi/jarvis-node-mobile) | Mobile voice node (React Native) | [![CI](https://github.com/alexberardi/jarvis-node-mobile/actions/workflows/ci.yml/badge.svg)](https://github.com/alexberardi/jarvis-node-mobile/actions/workflows/ci.yml) |
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

### Command Parsing Benchmarks

Tested across 20+ command types (weather, timers, sports, calendar, smart home, etc.) with node-side parameter validation enabled (auto-correction + retry). Local tests on Apple M2 Max with Metal acceleration; remote tests on dual RTX 3090 via llama.cpp layer splitting.

**Recommended setup:** Qwen 2.5 7B Instruct with `Qwen25Compressed` prompt provider (best accuracy/latency on Apple Silicon). For dedicated GPU servers, Qwen3-32B achieves 98.3% accuracy.

#### With LoRA Adapter (GGUF only, trained 2 epochs)

| Model | Backend | Quant | Size | Success Rate | Avg Latency |
|-------|---------|-------|------|-------------|-------------|
| Qwen 2.5 7B Instruct | GGUF | Q4_K_M | 4.3 GB | **100%** (86/86) | 1.42s |
| Qwen 2.5 3B Instruct | GGUF | Q4_K_M | 2.0 GB | 98.8% (85/86) | 1.18s |

> **Note:** LoRA adapters currently degrade accuracy on the MLX backend. Adapters are trained against full-precision HuggingFace weights, which pair well with GGUF's quantization-aware adapter loading but cause regressions when applied to MLX's quantized inference. MLX results below are without adapters.

#### Baseline (no adapter)

| Model | Backend | Quant | Size | Provider | Success Rate | Avg Latency |
|-------|---------|-------|------|----------|-------------|-------------|
| Qwen 2.5 7B Instruct | MLX | 8-bit | 8.1 GB | Compressed | 97.7% (84/86) | 1.56s |
| Qwen 2.5 7B Instruct | MLX | 4-bit | 4.3 GB | Compressed | 95.4% (82/86) | 1.19s |
| Qwen 2.5 7B Instruct | GGUF | Q4_K_M | 4.3 GB | Compressed | 95.1% (78/82)&dagger; | 1.10s |
| Qwen 2.5 7B Instruct | GGUF | Q4_K_M | 4.3 GB | Standard | 91.5% (75/82)&dagger; | 1.1s |
| Llama 3.1 8B Instruct | GGUF | Q6_K | 6.1 GB | Standard | 93.1% (67/72)&Dagger; | 1.3s |
| Gemma 2 9B Instruct | GGUF | Q4_K_M | 5.4 GB | Standard | 93.1% (67/72)&Dagger; | 2.5s |
| Hermes 3 Llama 3.1 8B | GGUF | Q4_K_M | 4.6 GB | Compressed | 91.5% (75/82)&dagger; | 1.4s |
| Hermes 3 Llama 3.1 8B | GGUF | Q4_K_M | 4.6 GB | Standard | 90.2% (74/82)&dagger; | 1.4s |
| Qwen 2.5 3B Instruct | GGUF | Q4_K_M | 2.0 GB | Compressed | 89.5% (77/86) | 0.85s |
| Qwen3-32B | GGUF | Q4_K_M | 19 GB | Compressed | **98.3%** (116/118)&sect; | 1.4s&para; |
| Mixtral 8x7B Instruct v0.1 | GGUF | Q4_K_M | 26 GB | Compressed | 94.9% (112/118)&sect; | 3.0s |
| Qwen3-30B-A3B (MoE) | GGUF | Q4_K_M | 19 GB | Compressed | 92.4% (109/118)&sect; | 2.9s |

&dagger; Tested on 82-command suite. &Dagger; Tested on prior 72-command suite without node-side validation. &sect; Tested on 118-command suite on remote dual RTX 3090 (24GB each) via llama.cpp GPU layer splitting. &para; LLM inference time only; end-to-end with network overhead is ~4s.

**Provider** refers to the prompt provider — **Compressed** (`Qwen25Compressed`, `HermesCompressed`, etc.) uses a compact tool listing with DT_KEYS date vocabulary injection, reducing prompt tokens ~26% while improving accuracy. **Standard** uses the full prompt with verbose parameter descriptions. All models use `chatml` chat format except Llama 3.1 (`llama-3`).

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
| **Research** | Deep web research with summarization, delivered via push + inbox |

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
