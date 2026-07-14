<p align="center">
  <img src="logo.png" alt="Jarvis" width="600" />
</p>

<p align="center">
  <strong>A self-hosted, extensible voice assistant that runs on your hardware — not someone else's cloud.</strong><br>
  Wake word, speech-to-text, text-to-speech, and speaker ID all run locally. <strong>20 commands built in</strong> (timers, reminders, memories, web search, smart home, routines) and <strong>24 more</strong> (weather, music, calendar, sports, movies, email) one click away in the <a href="https://pantry.jarvisautomation.io">Pantry</a>. Extend it in plain English with the <strong>AI Forge</strong>, which generates, sandbox-tests, and publishes a complete new command from a one-sentence description. Bring your own LLM: point it at a cloud API for zero setup, or run it fully local on your own GPU for zero cloud dependency.
</p>

<p align="center">
  <a href="#quick-start"><strong>Install Jarvis</strong></a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="#requirements">Requirements</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="#architecture">Architecture</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="#services">Services</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="https://discord.com/invite/kMfKr7EZZ"><strong>Discord</strong></a>
</p>

---

## Why Jarvis?

Most voice assistants send your voice to the cloud, process it on someone else's hardware, and send back a response. You're renting access to your own assistant — and paying with your data.

Jarvis takes a different approach. Every component runs locally: speech recognition via whisper.cpp, LLM inference via llama.cpp/vLLM/MLX, text-to-speech via Piper or Kokoro, and a command center that routes everything. No internet required. No subscriptions. No one listening.

What makes Jarvis different from other self-hosted alternatives:

- **Extend it in plain English.** Implement the `IJarvisCommand` interface and drop it in, or use the **AI Forge**: describe what you want ("crypto prices by ticker symbol"), and it generates, validates, and sandbox-tests a complete package you can publish in one click. **20 commands ship built in** (conversation, memories, timers, reminders, web search, smart home, routines); another **24 packages** (weather, music, calendar, sports, movies, email, drive time) are one click away in the [Pantry](https://pantry.jarvisautomation.io) community store. This is the part nothing else in local-voice has.
- **Private by default, on your hardware.** Speech recognition (whisper.cpp), text-to-speech (Piper/Kokoro), and the command center all run on your own machine. No subscriptions, no one listening.
- **Bring your own LLM — no GPU required.** Point the LLM proxy at a cloud API (Claude, GPT, Ollama, …) and run the whole stack on any Docker host, or go **fully local** with llama.cpp / vLLM / MLX on your own GPU for zero cloud dependency. Your call on the privacy-vs-convenience trade.
- **Speaker identification.** Jarvis knows who's talking — voice profiles per household member, so each person gets their own context, preferences, and command routing.
- **Pi Zero voice nodes.** A ~$15 Raspberry Pi Zero 2 W with a mic/speaker HAT becomes a room-scale voice endpoint, headless-provisioned from the mobile app. (Nodes are cheap; the brain runs on a separate host — see [Requirements](#requirements).)
- **Modular, not monolithic.** ~13 independent services (each with its own database, CI, Docker image, and tests) plus a catalog of **forkable** command and device packages. Swap or extend any piece without touching the rest — and most `jarvis-cmd-*` / `jarvis-device-*` repos are reference implementations meant to be forked and improved.

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

**Safety:** every generated package runs through static analysis and an automated safety review, then a full **containerized test run** (the Pantry submission pipeline) before it can be published. As with any package store — think AUR, npm, or PyPI — Jarvis sandboxes and screens, but installing a community package is ultimately your call. You decide what you trust.

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
         │  │ + speaker │    │ intent parsing, tool routing │    │ MLX/REST  │  │
         │  │   ID      │    └──────────┬──────────────────┘    │           │  │
         │  └──────────┘    ┌──────────▼────────┐              └───────────┘  │
         │                  │ TTS (Piper/Kokoro)│                              │
         │                  │ streaming audio   │                              │
         │                  └───────────────────┘                              │
         └─────────────────────────────────────────────────────────────────────┘
                                       │
      ┌────────────────────────────────┼────────────────────────────────────┐
      │                                │      ADDITIONAL SERVICES           │
      │  ┌──────────┐  ┌──────────┐  ┌▼─────────┐  ┌──────────┐           │
      │  │ Settings │  │ Admin UI │  │ Notif.   │  │ Notif.   │           │
      │  │ Server   │  │ (React)  │  │ Service  │  │ Relay    │           │
      │  │          │  │          │  │ push +   │  │ Expo →   │           │
      │  │          │  │          │  │ inbox    │  │ APNs/FCM │           │
      │  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
      └────────────────────────────────────────────────────────────────────┘
                                       │
      ┌────────────────────────────────┼────────────────────────────────────┐
      │                                │          CLIENTS                   │
      │  ┌──────────────┐  ┌──────────▼───┐  ┌──────────┐  ┌───────────┐  │
      │  │ Pi Zero      │  │ Mobile       │  │ Web Chat │  │ Admin     │  │
      │  │ Voice Nodes  │  │ Voice Node   │  │ (Next.js)│  │ Web UI    │  │
      │  │ (Python)     │  │ (React Native│) │          │  │ (React)   │  │
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
| [jarvis-llm-proxy-api](https://github.com/alexberardi/jarvis-llm-proxy-api) | 7704 | Local LLM inference (GGUF/vLLM/MLX/Transformers/REST) | [![Tests](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-llm-proxy-api/actions/workflows/docker-build-push.yml) |
| [jarvis-whisper-api](https://github.com/alexberardi/jarvis-whisper-api) | 7706 | Speech-to-text via whisper.cpp with speaker identification | [![Tests](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-whisper-api/actions/workflows/docker-build-push.yml) |
| [jarvis-tts](https://github.com/alexberardi/jarvis-tts) | 7707 | Text-to-speech synthesis via Piper or Kokoro | [![Tests](https://github.com/alexberardi/jarvis-tts/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-tts/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-tts/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-tts/actions/workflows/docker-build-push.yml) |
| [jarvis-settings-server](https://github.com/alexberardi/jarvis-settings-server) | 7708 | Runtime settings aggregator for all services | [![Tests](https://github.com/alexberardi/jarvis-settings-server/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-settings-server/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-settings-server/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-settings-server/actions/workflows/docker-build-push.yml) |
| [jarvis-admin](https://github.com/alexberardi/jarvis-admin) | 7711 | Web admin UI + setup wizard (settings, training, administration) | [![Tests](https://github.com/alexberardi/jarvis-admin/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-admin/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-admin/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-admin/actions/workflows/docker-build-push.yml) |

### Optional

Add-on services for additional capabilities.

| Service | Port | Description | Tests | Docker |
|---------|------|-------------|-------|--------|
| [jarvis-notifications](https://github.com/alexberardi/jarvis-notifications) | 7712 | Push notifications, inbox, and deep research delivery | [![Tests](https://github.com/alexberardi/jarvis-notifications/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-notifications/actions/workflows/test.yml) | [![Docker](https://github.com/alexberardi/jarvis-notifications/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/alexberardi/jarvis-notifications/actions/workflows/docker-build-push.yml) |

### Cloud

Optional cloud-hosted services and public-facing web apps.

| Service | Port | Description | CI |
|---------|------|-------------|-----|
| [jarvis-notifications-relay](https://github.com/alexberardi/jarvis-notifications-relay) | - | Stateless Expo Push API proxy for APNs/FCM delivery | [![Tests](https://github.com/alexberardi/jarvis-notifications-relay/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-notifications-relay/actions/workflows/test.yml) |
| [jarvis-pantry](https://github.com/alexberardi/jarvis-pantry) | 7721 | Community package store API (browse, submit, review, Forge) | [![Tests](https://github.com/alexberardi/jarvis-pantry/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-pantry/actions/workflows/test.yml) |
| [jarvis-pantry-web](https://github.com/alexberardi/jarvis-pantry-web) | 7720 | Pantry web frontend (Next.js) — catalog browser + AI Forge | [![CI](https://github.com/alexberardi/jarvis-pantry-web/actions/workflows/ci.yml/badge.svg)](https://github.com/alexberardi/jarvis-pantry-web/actions/workflows/ci.yml) |
| [jarvis-pantry-runner](https://github.com/alexberardi/jarvis-pantry-runner) | - | Container test runner for Pantry submissions (GitHub Actions) | [![CI](https://github.com/alexberardi/jarvis-pantry-runner/actions/workflows/container-test.yml/badge.svg)](https://github.com/alexberardi/jarvis-pantry-runner/actions/workflows/container-test.yml) |
| [jarvis-docs](https://github.com/alexberardi/jarvis-docs) | - | [Developer documentation](https://docs.jarvisautomation.dev) (MkDocs) | |
| [jarvis-command-sdk](https://github.com/alexberardi/jarvis-command-sdk) | - | Core interfaces + Forge spec generator (pip package) | |

### Community Packages

Standalone command packages installable via the Pantry. Each was extracted from the built-in command set into its own repo.

| Package | Description |
|---------|-------------|
| [jarvis-home-assistant-integration](https://github.com/alexberardi/jarvis-home-assistant-integration) | Smart home device control + status via Home Assistant |
| [jarvis-cmd-news](https://github.com/alexberardi/jarvis-cmd-news) | RSS news headlines by category |
| [jarvis-cmd-barstool](https://github.com/alexberardi/jarvis-cmd-barstool) | Barstool Sports headlines with optional sport filter |
| [jarvis-cmd-open-weather](https://github.com/alexberardi/jarvis-cmd-open-weather) | Weather conditions and forecasts via OpenWeather API |
| [jarvis-cmd-meteo-weather](https://github.com/alexberardi/jarvis-cmd-meteo-weather) | Weather via Open-Meteo (free, no API key) |
| [jarvis-cmd-sports](https://github.com/alexberardi/jarvis-cmd-sports) | Sports scores, live games, and schedules via ESPN |
| [jarvis-cmd-music-assistant](https://github.com/alexberardi/jarvis-cmd-music-assistant) | Music playback and control via Music Assistant |
| [jarvis-cmd-audacy](https://github.com/alexberardi/jarvis-cmd-audacy) | Live Audacy radio (sports, news, talk, music) streamed on the node |
| [jarvis-cmd-pandora](https://github.com/alexberardi/jarvis-cmd-pandora) | Pandora radio streaming with voice control |
| [jarvis-cmd-spotify](https://github.com/alexberardi/jarvis-cmd-spotify) | Spotify playback and control on a Jarvis node |
| [jarvis-cmd-rotten-tomatoes](https://github.com/alexberardi/jarvis-cmd-rotten-tomatoes) | Rotten Tomatoes movie/TV ratings and what's in theaters |
| [jarvis-cmd-entertainment-knowledge](https://github.com/alexberardi/jarvis-cmd-entertainment-knowledge) | TMDB-powered movie & TV lookup with rich inbox cards |
| [jarvis-cmd-email](https://github.com/alexberardi/jarvis-cmd-email) | Email management (Gmail + IMAP) with alert agent |
| [jarvis-cmd-calendar](https://github.com/alexberardi/jarvis-cmd-calendar) | Calendar events (iCloud + Google) with alert agent |
| [jarvis-cmd-medication](https://github.com/alexberardi/jarvis-cmd-medication) | Household medication tracking with dose reminders and voice mark-off |
| [jarvis-device-hue](https://github.com/alexberardi/jarvis-device-hue) | Philips Hue smart lights via the local Bridge API |
| [jarvis-device-govee](https://github.com/alexberardi/jarvis-device-govee) | Govee smart devices (LAN + cloud) |
| [jarvis-device-apple](https://github.com/alexberardi/jarvis-device-apple) | Apple TV and HomePod control via AirPlay |
| [jarvis-device-nest](https://github.com/alexberardi/jarvis-device-nest) | Google Nest thermostat and camera via SDM API |
| [jarvis-device-schlage](https://github.com/alexberardi/jarvis-device-schlage) | Schlage Encode WiFi smart lock control via Allegion cloud |
| [jarvis-device-simplisafe](https://github.com/alexberardi/jarvis-device-simplisafe) | SimpliSafe home security — arm, disarm, sensor status |
| [jarvis-device-zwave](https://github.com/alexberardi/jarvis-device-zwave) | Z-Wave device control via Z-Wave JS UI |
| [jarvis-device-homeconnect](https://github.com/alexberardi/jarvis-device-homeconnect) | Bosch/Siemens appliance control via Home Connect |
| [jarvis-device-homekit](https://github.com/alexberardi/jarvis-device-homekit) | Local Apple HomeKit (HAP) accessories — discover, pair, and control over LAN |
| [jarvis-device-resideo](https://github.com/alexberardi/jarvis-device-resideo) | Resideo / Honeywell Home thermostat control |
| [jarvis-device-kasa](https://github.com/alexberardi/jarvis-device-kasa) | TP-Link Kasa smart plugs and lights over the local network |
| [jarvis-device-lifx](https://github.com/alexberardi/jarvis-device-lifx) | LIFX smart lights over the local network |

### Prompt Providers (IN PROGRESS)

Installable LLM prompt providers for additional model support. **WIP** — packaging story is being finalized; expect interface changes.

| Package | Description |
|---------|-------------|
| [jarvis-pp-hermes](https://github.com/alexberardi/jarvis-pp-hermes) | Prompt providers for NousResearch Hermes 3 Llama 3.1 8B |
| [jarvis-pp-mistral](https://github.com/alexberardi/jarvis-pp-mistral) | Prompt providers for Mistral 7B Instruct and Mixtral 8x7B |

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
| [jarvis-web](https://github.com/alexberardi/jarvis-web) | Web chat interface (Next.js) | |
| [jarvis-recipes-mobile](https://github.com/alexberardi/jarvis-recipes-mobile) | Recipe app (React Native) | [![Build](https://github.com/alexberardi/jarvis-recipes-mobile/actions/workflows/build-and-deploy.yml/badge.svg)](https://github.com/alexberardi/jarvis-recipes-mobile/actions/workflows/build-and-deploy.yml) |

### Tools

| Tool | Description | CI |
|------|-------------|-----|
| [jarvis-developer-toolkit](https://github.com/alexberardi/jarvis-developer-toolkit) | CLI (`jdt`) for scaffolding, testing, and deploying packages | |
| [jarvis-installer](https://github.com/alexberardi/jarvis-installer) | Web-based Docker Compose generator | [![Tests](https://github.com/alexberardi/jarvis-installer/actions/workflows/test.yml/badge.svg)](https://github.com/alexberardi/jarvis-installer/actions/workflows/test.yml) [![Deploy](https://github.com/alexberardi/jarvis-installer/actions/workflows/deploy.yml/badge.svg)](https://github.com/alexberardi/jarvis-installer/actions/workflows/deploy.yml) |
| [jarvis-data-services](https://github.com/alexberardi/jarvis-data-services) | Shared PostgreSQL, Redis, Loki, Grafana | |

## LLM Inference

The LLM proxy supports multiple inference backends, so you can match your hardware:

| Backend | Best For | Acceleration |
|---------|----------|--------------|
| **GGUF** (llama.cpp) | Most setups — quantized models, low memory | CUDA, Metal, ROCm, CPU |
| **vLLM** | High-throughput GPU servers | CUDA |
| **MLX** | Apple Silicon Macs | Metal |
| **Transformers** | HuggingFace models without conversion | CUDA, CPU |
| **REST** | Remote APIs (OpenAI, Anthropic, Ollama) | N/A |

## Built-in Commands

**20 commands**, grouped by category below. These ship with the node and command-center — no Pantry install required, and they're the tools the LLM can call on a fresh install.

| Category | Commands |
|----------|----------|
| **Conversation** | General chat with context memory, jokes, "what's up", clarification prompts |
| **Memories** | Remember, recall, and forget personal facts; passive extraction from voice history |
| **Timers & Reminders** | Set / check / cancel timers; one-shot and recurring reminders |
| **Utilities** | Calculator, unit conversion, timezone queries, relative-date resolution |
| **Web** | Quick web search; deep research with summarization, delivered via push + inbox |
| **Speaker** | Identify-speaker ("who am I?") via voice profile match |
| **Smart Home** | Device control + status (Home Assistant package surfaces real devices to the built-in tool) |
| **Routines** | Run user-built automations — bundle commands behind a voice or condition trigger |
| **Node Control** | Reboot, restart, and other node-side admin from voice |
| **Mobile Push** | Send a tap-to-open link to a household member's phone via the notifications inbox |

Everything else (weather, calendar, sports, news, music, movies, drive time, …) ships as a [Community Package](#community-packages) — **24 are published in the [Pantry](https://pantry.jarvisautomation.io) today**, installable in one click. Add your own by implementing the `IJarvisCommand` interface and running `jdt deploy` from the [Developer Toolkit](https://github.com/alexberardi/jarvis-developer-toolkit).

## Requirements

Jarvis runs as a Docker stack on a **host machine** (Linux, macOS, or a NAS), with optional **Pi Zero voice nodes** as room endpoints. The one variable that drives your hardware needs is **where the LLM runs** — and that's your choice:

**Two ways to run the brain:**

- **Cloud LLM — no GPU.** Point the LLM proxy at Claude, GPT, Ollama, or any OpenAI-compatible API, and the whole stack runs on a modest Docker host (~8 GB RAM, no GPU). Convenient, but your transcripts go to that provider — so it's the easy path, not the maximally-private one.
- **Fully local — your GPU.** Run the model yourself via llama.cpp / vLLM / MLX for zero cloud dependency. This is the privacy-max path and wants real compute: an NVIDIA GPU (8+ GB VRAM) or Apple Silicon (Metal). CPU-only works but is slow.

**Host machine:**

| Resource | Cloud-LLM (minimum) | Fully-local (recommended) |
|----------|---------------------|----------------------------|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16+ GB |
| Disk | 20 GB | 40 GB+ (models are 4–20 GB each) |
| GPU | none | NVIDIA 8+ GB VRAM, or Apple Silicon (Metal) |
| Software | Docker v24+ with Compose v2 | same |

**Voice node (optional, one per room):** a Raspberry Pi Zero 2 W (~$15) with a mic/speaker HAT such as the ReSpeaker 2-Mics — headless, provisioned from the mobile app.

## Quick Start

The fastest path is the one-line installer. It downloads the `jarvis-admin` setup wizard, which pulls prebuilt images from GHCR — no source checkout required:

<!-- jarvis:install-cmd:start — version pin auto-updated by the release docs bot; edit the command here, not the copies in jarvis-docs -->
```bash
curl -fsSL https://raw.githubusercontent.com/alexberardi/jarvis-admin/main/install.sh | sh
```
<!-- jarvis:install-cmd:end -->

Then open **http://localhost:7711** — the wizard walks you through hardware detection, service selection, account creation, and downloading a model. See the [full installation guide](https://docs.jarvisautomation.dev/getting-started/installation/) for Docker prerequisites, GPU setup, TrueNAS, and other install options.

> **Note:** Jarvis spans many repositories (a dozen-ish services plus command/device packages), so cloning this repo alone is **not** a full install — use the installer above to run it. To hack on the services from source, see [Development](#development).

## Development

### Building Packages

The fastest way to extend Jarvis is with the [Developer Toolkit](https://github.com/alexberardi/jarvis-developer-toolkit):

```bash
pip install git+https://github.com/alexberardi/jarvis-developer-toolkit.git

jdt init my_command --type command    # Scaffold a package
cd my_command
# ... implement your logic ...
jdt test .                            # Validate (same pipeline as Pantry)
jdt deploy local .                    # Install to your node
```

`jdt` supports all component types: commands, agents, device protocols, device managers, routines, and prompt providers. See the [Developer Toolkit docs](https://docs.jarvisautomation.dev/extending/toolkit/) for the full guide, including [Claude Code integration](https://docs.jarvisautomation.dev/extending/toolkit/claude-code/).

### Working on Services

Each service is its own repository with its own CI pipeline. Clone the ones you need:

```bash
git clone https://github.com/alexberardi/jarvis-auth.git
cd jarvis-auth
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/python -m alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 7701
```

See each service's README for specific setup instructions, or browse the [developer docs](https://docs.jarvisautomation.dev).

## Community

Questions, bug reports, or you want to show off a package you built — **[join the Discord](https://discord.com/invite/kMfKr7EZZ)**. It's the fastest way to get an answer, and where new packages and hardware builds get shared.

Bugs and feature requests are also welcome as GitHub issues on the relevant repo.

## License

Jarvis is open source under a split license:

- **Server-side services** — command-center, auth, config-service, pantry, the LLM / STT / TTS services, logs, notifications, admin, installer, node software, and the rest of the self-hosted stack — are licensed under the **GNU AGPL-3.0**. You can self-host, modify, and redistribute freely; if you run a modified version as a network service, you must publish your changes.
- **Apps, SDK, client libraries, and command/device packages** — the mobile apps, `jarvis-command-sdk`, the `*-client` libraries, and all `jarvis-cmd-*` / `jarvis-device-*` packages — are licensed under **Apache-2.0**, so you can build and ship your own commands and integrations without copyleft obligations.

Each repository's `LICENSE` file is authoritative.
