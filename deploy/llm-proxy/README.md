# Jarvis LLM Proxy — Remote Deployment

Deploy the LLM proxy on a separate GPU machine while the rest of the Jarvis stack runs elsewhere.

## Prerequisites

- **NVIDIA GPU** with [Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed
- **Docker** with Compose v2
- **Network access** to the main Jarvis server (ports 7700, 7701, 5432, 6379)

## Quick Start

```bash
# 1. Copy this directory to the GPU machine
scp -r deploy/llm-proxy/ user@gpu-machine:~/jarvis-llm-proxy/

# 2. Run the interactive setup
cd ~/jarvis-llm-proxy
bash setup.sh
```

The setup script will:
1. Check prerequisites (Docker, nvidia-smi, curl, openssl)
2. Prompt for the main server IP and validate connectivity
3. Prompt for admin tokens (from main server's `.env` files)
4. Prompt for PostgreSQL and Redis connection details
5. Register with `jarvis-auth` as an app client
6. Update the service URL in `jarvis-config-service` to point here
7. **Select a model** from presets or enter a custom HuggingFace repo
8. **Download the model** via `huggingface-cli` (skips if already present)
9. Generate internal tokens and write `.env` with model settings
10. Pull the Docker image and start the stack
11. **Sync settings to the database** (model name, backend, chat format, context window, stop tokens)

### Model Presets

| # | Model | Backend | Notes |
|---|-------|---------|-------|
| 1 | Qwen 2.5 7B Instruct | vLLM | Recommended default |
| 2 | Qwen 2.5 14B Instruct | vLLM | Needs ~28GB VRAM |
| 3 | Llama 3.1 8B Instruct | vLLM | 128K context window |
| 4 | Mistral 7B Instruct v0.3 | vLLM | |
| 5 | Gemma 2 9B IT | vLLM | |
| 6 | Mixtral 8x7B Instruct Q4_K_M | GGUF | MoE, ~26GB, single-file download |
| 7 | Custom | — | Enter any HuggingFace repo ID |

## How Settings Work

Model configuration flows through two layers:

1. **Environment variables** (`.env`) — bootstrap fallback, always available
2. **Settings database** — source of truth for runtime config, editable via API/admin UI

On first start, the model loads from env vars (`JARVIS_MODEL_NAME`, `JARVIS_MODEL_BACKEND`, etc.). After the API is healthy, `setup.sh` calls `POST /settings/sync-from-env` to write these values into the database. From then on, settings can be changed via the admin UI or API without editing `.env`.

### Changing the Model Later

```bash
# Option 1: Use the settings API
curl -X PUT http://localhost:7704/settings/model.main.name \
  -H "X-Jarvis-App-Id: jarvis-llm-proxy-api" \
  -H "X-Jarvis-App-Key: YOUR_APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"value": ".models/new-model"}'

# Then restart to reload (model settings require reload)
docker compose restart

# Option 2: Edit .env and restart
# Update JARVIS_MODEL_NAME in .env, then:
docker compose restart
# Optionally re-sync: curl -X POST http://localhost:7704/settings/sync-from-env ...
```

## Manual Setup

If you prefer not to use `setup.sh`:

1. Copy `env.template` to `.env` and fill in all `__PLACEHOLDER__` values
2. Register with jarvis-auth:
   ```bash
   curl -X POST http://MAIN_SERVER:7701/admin/app-clients \
     -H "Content-Type: application/json" \
     -H "X-Admin-Token: AUTH_ADMIN_TOKEN" \
     -d '{"app_id": "jarvis-llm-proxy-api", "description": "LLM Proxy (remote)"}'
   ```
3. Update the URL in config-service:
   ```bash
   curl -X PUT http://MAIN_SERVER:7700/services/jarvis-llm-proxy-api \
     -H "Content-Type: application/json" \
     -H "X-Admin-Token: CONFIG_ADMIN_TOKEN" \
     -d '{"host": "THIS_MACHINE_IP", "port": 7704}'
   ```
4. Generate tokens:
   ```bash
   openssl rand -hex 32  # MODEL_SERVICE_TOKEN
   openssl rand -hex 32  # LLM_PROXY_INTERNAL_TOKEN
   ```
5. Download a model:
   ```bash
   pip install huggingface-hub
   huggingface-cli download Qwen/Qwen2.5-7B-Instruct --local-dir .models/Qwen2.5-7B-Instruct
   ```
6. Set model env vars in `.env`:
   ```bash
   JARVIS_MODEL_NAME=.models/Qwen2.5-7B-Instruct
   JARVIS_MODEL_BACKEND=VLLM
   JARVIS_MODEL_CHAT_FORMAT=qwen
   JARVIS_MODEL_CONTEXT_WINDOW=32768
   JARVIS_MODEL_STOP_TOKENS=<|im_end|>,<|endoftext|>
   ```
7. Start and sync settings:
   ```bash
   docker compose pull
   docker compose up -d
   # Wait for healthy, then:
   curl -X POST http://localhost:7704/settings/sync-from-env \
     -H "X-Jarvis-App-Id: jarvis-llm-proxy-api" \
     -H "X-Jarvis-App-Key: YOUR_APP_KEY"
   ```

## Network Ports

| Port | Direction | Purpose |
|------|-----------|---------|
| 7704 | Inbound | LLM Proxy API (main server → here) |
| 7705 | Internal | Model service (container-to-container) |
| 7700 | Outbound | Config service discovery (here → main server) |
| 7701 | Outbound | Auth validation (here → main server) |
| 5432 | Outbound | PostgreSQL (here → DB host) |
| 6379 | Outbound | Redis (here → Redis host) |

## Updating

```bash
# Pull latest image and restart
docker compose pull
docker compose up -d

# Or pin a specific version in .env
echo "LLM_PROXY_VERSION=v1.2.0" >> .env
docker compose pull
docker compose up -d
```

## Troubleshooting

**Container won't start:**
```bash
docker compose logs -f
```

**Model service takes too long to start:**
The model service has a 120s health check start period. Large models may need more time. Check:
```bash
docker compose logs llm-proxy-model
```

**Can't reach main server services:**
Verify connectivity:
```bash
curl http://MAIN_SERVER:7700/health
curl http://MAIN_SERVER:7701/health
```

**GPU not detected:**
```bash
nvidia-smi                           # Host GPU check
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi  # Container GPU check
```

**Auth failures:**
Re-run app registration or check `JARVIS_APP_KEY` in `.env` matches what jarvis-auth has stored.

**Settings not taking effect:**
Check if settings are in the DB vs env:
```bash
curl http://localhost:7704/settings/ \
  -H "X-Jarvis-App-Id: jarvis-llm-proxy-api" \
  -H "X-Jarvis-App-Key: YOUR_APP_KEY" | python3 -m json.tool
```
Settings from DB override env vars. If you changed `.env`, either restart or re-sync:
```bash
curl -X POST http://localhost:7704/settings/sync-from-env \
  -H "X-Jarvis-App-Id: jarvis-llm-proxy-api" \
  -H "X-Jarvis-App-Key: YOUR_APP_KEY"
```
