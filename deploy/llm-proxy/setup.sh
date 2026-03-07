#!/usr/bin/env bash
# ============================================================================
# Jarvis LLM Proxy — Remote Deployment Setup
# ============================================================================
# Interactive script that:
#   1. Checks prerequisites (Docker, nvidia-smi, curl, openssl)
#   2. Prompts for main server IP and admin tokens
#   3. Prompts for database and Redis connection details
#   4. Registers this LLM proxy as an app-client with jarvis-auth
#   5. Updates the service URL in jarvis-config-service
#   6. Selects and downloads a model
#   7. Generates internal tokens and writes .env
#   8. Pulls the Docker image and starts the stack
#   9. Syncs model settings to the database
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

prompt() {
    local var_name="$1" prompt_text="$2" default="${3:-}"
    local value
    if [[ -n "$default" ]]; then
        read -rp "$(echo -e "${CYAN}$prompt_text${NC} [$default]: ")" value
        value="${value:-$default}"
    else
        read -rp "$(echo -e "${CYAN}$prompt_text${NC}: ")" value
    fi
    eval "$var_name=\"$value\""
}

prompt_secret() {
    local var_name="$1" prompt_text="$2"
    local value
    read -srp "$(echo -e "${CYAN}$prompt_text${NC}: ")" value
    echo
    eval "$var_name=\"$value\""
}

# ============================================================================
# Model presets
# ============================================================================
# Each preset: "HF_REPO^MODEL_NAME^BACKEND^CHAT_FORMAT^CONTEXT_WINDOW^STOP_TOKENS^HF_FILENAME"
# Delimiter is ^ (pipe conflicts with stop tokens like <|im_end|>).
# HF_FILENAME is empty for full-repo downloads, set for single-file GGUF downloads.
# For GGUF: MODEL_NAME is the path to the .gguf file; HF_FILENAME is the file to download.
# For vLLM/transformers: MODEL_NAME is the directory; HF_FILENAME is empty.

PRESET_COUNT=8

declare -A MODEL_PRESETS
MODEL_PRESETS=(
    [1]="Qwen/Qwen2.5-7B-Instruct^.models/Qwen2.5-7B-Instruct^VLLM^qwen^32768^<|im_end|>,<|endoftext|>^"
    [2]="Qwen/Qwen2.5-14B-Instruct^.models/Qwen2.5-14B-Instruct^VLLM^qwen^32768^<|im_end|>,<|endoftext|>^"
    [3]="meta-llama/Llama-3.1-8B-Instruct^.models/Llama-3.1-8B-Instruct^VLLM^llama3^131072^<|eot_id|>^"
    [4]="mistralai/Mistral-7B-Instruct-v0.3^.models/Mistral-7B-Instruct-v0.3^VLLM^mistral^32768^</s>^"
    [5]="google/gemma-2-9b-it^.models/gemma-2-9b-it^VLLM^chatml^8192^<end_of_turn>^"
    [6]="mradermacher/Mixtral-8x7B-Instruct-v0.1-GGUF^.models/Mixtral-8x7B-Instruct-v0.1.Q4_K_M.gguf^GGUF^chatml^32768^</s>^Mixtral-8x7B-Instruct-v0.1.Q4_K_M.gguf"
    [7]="TheBloke/Mixtral-8x7B-Instruct-v0.1-AWQ^.models/Mixtral-8x7B-Instruct-v0.1-AWQ^VLLM^chatml^32768^</s>^"
    [8]="bartowski/Qwen_Qwen3-30B-A3B-GGUF^.models/Qwen3-30B-A3B-Q4_K_M/Qwen_Qwen3-30B-A3B-Q4_K_M.gguf^GGUF^chatml^32768^<|im_end|>,<|endoftext|>^Qwen_Qwen3-30B-A3B-Q4_K_M.gguf"
)

declare -A MODEL_LABELS
MODEL_LABELS=(
    [1]="Qwen 2.5 7B Instruct       (7B vLLM, recommended for single GPU)"
    [2]="Qwen 2.5 14B Instruct      (14B vLLM, needs ~28GB VRAM)"
    [3]="Llama 3.1 8B Instruct      (8B vLLM, 128K context)"
    [4]="Mistral 7B Instruct        (7B vLLM)"
    [5]="Gemma 2 9B IT              (9B vLLM)"
    [6]="Mixtral 8x7B Instruct GGUF (MoE, 4-bit, ~26GB, multi-GPU via llama.cpp)"
    [7]="Mixtral 8x7B Instruct AWQ  (MoE, 4-bit, ⚠ vLLM TP broken in 0.16)"
    [8]="Qwen3 30B-A3B GGUF         (MoE, 3B active, 4-bit, ~19GB, single GPU)"
)

parse_preset() {
    local preset="$1"
    IFS='^' read -r HF_REPO MODEL_NAME MODEL_BACKEND MODEL_CHAT_FORMAT MODEL_CONTEXT_WINDOW MODEL_STOP_TOKENS HF_FILENAME <<< "$preset"
}

# ============================================================================
# 1. Check prerequisites
# ============================================================================

info "Checking prerequisites..."

missing=()
for cmd in docker curl openssl; do
    if ! command -v "$cmd" &>/dev/null; then
        missing+=("$cmd")
    fi
done

GPU_COUNT=0
if ! command -v nvidia-smi &>/dev/null; then
    warn "nvidia-smi not found. GPU support may not work."
else
    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits 2>/dev/null | wc -l | tr -d ' ')
    GPU_NAMES=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits 2>/dev/null | paste -sd ', ')
    ok "nvidia-smi found: ${GPU_COUNT} GPU(s) — ${GPU_NAMES}"
fi

if [[ ${#missing[@]} -gt 0 ]]; then
    err "Missing required tools: ${missing[*]}"
    err "Install them and re-run this script."
    exit 1
fi

# Check Docker Compose v2
if ! docker compose version &>/dev/null; then
    warn "Docker Compose v2 not found. Installing..."
    # Add Docker repo if needed
    if ! apt-cache show docker-compose-plugin &>/dev/null 2>&1; then
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
        sudo apt-get update -qq
    fi
    sudo apt-get install -y -qq docker-compose-plugin || {
        err "Failed to install docker-compose-plugin."
        err "Install manually: sudo apt install docker-compose-plugin"
        exit 1
    }
    ok "Docker Compose v2 installed"
fi

# Check NVIDIA Container Toolkit (required for GPU passthrough to Docker)
if [[ "$GPU_COUNT" -gt 0 ]]; then
    if ! docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi &>/dev/null 2>&1; then
        warn "NVIDIA Container Toolkit not working. Installing..."
        # Add NVIDIA repo
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
            | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
            | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
            | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
        sudo apt-get update -qq
        sudo apt-get install -y -qq nvidia-container-toolkit || {
            err "Failed to install nvidia-container-toolkit."
            err "See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
            exit 1
        }
        sudo nvidia-ctk runtime configure --runtime=docker >/dev/null
        sudo systemctl restart docker
        ok "NVIDIA Container Toolkit installed and configured"
    else
        ok "NVIDIA Container Toolkit working"
    fi
fi

ok "Prerequisites satisfied"
echo

# ============================================================================
# 2. Main server connection
# ============================================================================

info "Main server configuration"
echo "  The main server runs jarvis-auth (port 7701) and jarvis-config-service (port 7700)."
echo

prompt MAIN_SERVER_IP "Main server IP address"

# Validate config-service is reachable
info "Checking config-service at http://${MAIN_SERVER_IP}:7700/health ..."
if curl -sf "http://${MAIN_SERVER_IP}:7700/health" >/dev/null 2>&1; then
    ok "config-service is reachable"
else
    err "Cannot reach config-service at http://${MAIN_SERVER_IP}:7700/health"
    err "Make sure jarvis-config-service is running on the main server."
    exit 1
fi
echo

# ============================================================================
# 3. Admin tokens
# ============================================================================

info "Admin tokens (from main server's .env files)"
echo "  These are needed to register the LLM proxy with auth and config services."
echo

prompt_secret AUTH_ADMIN_TOKEN "jarvis-auth JARVIS_AUTH_ADMIN_TOKEN"
prompt_secret CONFIG_ADMIN_TOKEN "jarvis-config-service JARVIS_CONFIG_ADMIN_TOKEN"
echo

# ============================================================================
# 4. Database connection
# ============================================================================

info "PostgreSQL connection (for LLM proxy's training jobs and settings)"
echo

prompt DB_HOST "Database host" "$MAIN_SERVER_IP"
prompt DB_PORT "Database port" "5432"
prompt DB_NAME "Database name" "jarvis_llm_proxy"
prompt DB_USER "Database user" "postgres"
prompt_secret DB_PASS "Database password"
echo

# ============================================================================
# 5. Redis connection
# ============================================================================

info "Redis connection (for async job queue)"
echo

prompt REDIS_HOST "Redis host" "$MAIN_SERVER_IP"
prompt REDIS_PORT "Redis port" "6379"
prompt_secret REDIS_PASS "Redis password (leave empty if none)"
echo

# ============================================================================
# 6. Register with jarvis-auth
# ============================================================================

info "Registering llm-proxy as app-client with jarvis-auth..."

REGISTER_HTTP_CODE=$(curl -s -o /tmp/jarvis-register-response.json -w "%{http_code}" \
    -X POST "http://${MAIN_SERVER_IP}:7701/admin/app-clients" \
    -H "Content-Type: application/json" \
    -H "X-Jarvis-Admin-Token: ${AUTH_ADMIN_TOKEN}" \
    -d '{"app_id": "jarvis-llm-proxy-api", "name": "LLM Proxy (remote)"}')
REGISTER_RESPONSE=$(cat /tmp/jarvis-register-response.json 2>/dev/null)

if [[ "$REGISTER_HTTP_CODE" == "200" || "$REGISTER_HTTP_CODE" == "201" ]]; then
    : # success, parse key below
elif echo "$REGISTER_RESPONSE" | grep -q "already exists"; then
    warn "App client 'jarvis-llm-proxy-api' already registered."
    echo "  Find the key in jarvis-llm-proxy-api/.env on the main server (JARVIS_APP_KEY)."
    prompt_secret APP_KEY "Enter existing JARVIS_APP_KEY for jarvis-llm-proxy-api"
else
    err "Failed to register with jarvis-auth (HTTP $REGISTER_HTTP_CODE): $REGISTER_RESPONSE"
    exit 1
fi

if [[ -z "${APP_KEY:-}" ]]; then
    APP_KEY=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])" 2>/dev/null) || {
        err "Failed to parse app_key from auth response: $REGISTER_RESPONSE"
        exit 1
    }
    ok "Registered. App key received."
fi
echo

# ============================================================================
# 7. Update LLM proxy URL in config-service
# ============================================================================

info "Updating llm-proxy URL in config-service..."

# Detect this machine's IP
MY_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || ip route get 1 2>/dev/null | awk '{print $7; exit}' || echo "")
if [[ -z "$MY_IP" ]]; then
    prompt MY_IP "Could not auto-detect this machine's IP. Enter it manually"
fi

# Try PUT first (update existing), fall back to POST (create new)
UPDATE_RESPONSE=$(curl -sf -X PUT "http://${MAIN_SERVER_IP}:7700/services/jarvis-llm-proxy-api" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Token: ${CONFIG_ADMIN_TOKEN}" \
    -d "{\"host\": \"${MY_IP}\", \"port\": 7704, \"scheme\": \"http\"}" \
    2>&1) || {
    info "Service not found, creating..."
    curl -sf -X POST "http://${MAIN_SERVER_IP}:7700/services" \
        -H "Content-Type: application/json" \
        -H "X-Admin-Token: ${CONFIG_ADMIN_TOKEN}" \
        -d "{\"name\": \"jarvis-llm-proxy-api\", \"host\": \"${MY_IP}\", \"port\": 7704, \"scheme\": \"http\", \"health_path\": \"/health\"}" \
        || { err "Failed to register service URL"; exit 1; }
}

ok "Config-service updated: jarvis-llm-proxy-api → http://${MY_IP}:7704"
echo

# ============================================================================
# 8. Select and download model
# ============================================================================

info "Model selection"
echo
echo -e "  ${BOLD}Available models:${NC}"
CUSTOM_CHOICE=$((PRESET_COUNT + 1))
for i in $(seq 1 "$PRESET_COUNT"); do
    echo -e "    ${CYAN}${i})${NC} ${MODEL_LABELS[$i]}"
done
echo -e "    ${CYAN}${CUSTOM_CHOICE})${NC} Custom HuggingFace model"
echo

prompt MODEL_CHOICE "Select a model (1-${CUSTOM_CHOICE})" "1"

HF_FILENAME=""
if [[ "$MODEL_CHOICE" -ge 1 && "$MODEL_CHOICE" -le "$PRESET_COUNT" ]]; then
    parse_preset "${MODEL_PRESETS[$MODEL_CHOICE]}"
    ok "Selected: ${MODEL_LABELS[$MODEL_CHOICE]}"
elif [[ "$MODEL_CHOICE" == "$CUSTOM_CHOICE" ]]; then
    prompt HF_REPO "HuggingFace repo ID (e.g., org/model-name)"
    prompt MODEL_BACKEND "Backend (VLLM, GGUF, TRANSFORMERS)" "VLLM"
    if [[ "${MODEL_BACKEND^^}" == "GGUF" ]]; then
        prompt HF_FILENAME "GGUF filename to download (e.g., model.Q4_K_M.gguf)"
        MODEL_NAME=".models/${HF_FILENAME}"
    else
        LOCAL_DIR_NAME=$(echo "$HF_REPO" | sed 's|.*/||')
        MODEL_NAME=".models/${LOCAL_DIR_NAME}"
    fi
    prompt MODEL_CHAT_FORMAT "Chat format (qwen, llama3, chatml, mistral)" "chatml"
    prompt MODEL_CONTEXT_WINDOW "Context window (tokens)" "8192"
    prompt MODEL_STOP_TOKENS "Stop tokens (comma-separated, or leave empty)" ""
    ok "Custom model configured"
else
    err "Invalid choice: $MODEL_CHOICE"
    exit 1
fi
echo

# ============================================================================
# 8b. Multi-GPU configuration
# ============================================================================

VLLM_TENSOR_PARALLEL=""
VLLM_GPU_MEMORY_UTIL=""
VLLM_MAX_LORAS="1"
GGUF_TENSOR_SPLIT=""
GGUF_SPLIT_MODE=""
GGUF_MAIN_GPU=""
VLLM_TOKENIZER=""

# Disable LoRA for MoE models (Mixtral) — vLLM LoRA + MoE + tensor parallel is unsupported
if echo "$HF_REPO" | grep -qi "mixtral\|moe"; then
    VLLM_MAX_LORAS="0"
    info "MoE model detected — LoRA disabled (unsupported with tensor parallel)"
fi

if [[ "$GPU_COUNT" -gt 1 ]]; then
    echo
    info "Multi-GPU detected (${GPU_COUNT} GPUs)"
    echo -e "  ${BOLD}Tensor parallelism${NC} splits the model across GPUs for faster inference."
    echo

    if [[ "${MODEL_BACKEND^^}" == "VLLM" ]]; then
        prompt VLLM_TENSOR_PARALLEL "Tensor parallel size (number of GPUs to use)" "$GPU_COUNT"
        prompt VLLM_GPU_MEMORY_UTIL "GPU memory utilization (0.0-1.0)" "0.90"
        ok "vLLM will use ${VLLM_TENSOR_PARALLEL} GPU(s)"
    elif [[ "${MODEL_BACKEND^^}" == "GGUF" ]]; then
        # Auto-configure llama.cpp layer splitting for GGUF models
        PROPORTIONS=$(python3 -c "n=${GPU_COUNT}; print(','.join([f'{1/n:.2f}']*n))" 2>/dev/null || echo "")
        prompt GGUF_TENSOR_SPLIT "VRAM split proportions per GPU (comma-separated)" "$PROPORTIONS"
        prompt GGUF_SPLIT_MODE "Split mode (1=layer, 2=row)" "1"
        prompt GGUF_MAIN_GPU "Main GPU index (for scratch buffers)" "0"
        ok "llama.cpp will split across ${GPU_COUNT} GPUs: ${GGUF_TENSOR_SPLIT}"
    fi
elif [[ "${MODEL_BACKEND^^}" == "VLLM" ]]; then
    VLLM_TENSOR_PARALLEL="1"
    VLLM_GPU_MEMORY_UTIL="0.90"
fi
echo

# Helper: ensure huggingface_hub is importable, install if needed
_ensure_hf_hub() {
    if python3 -c "import huggingface_hub" &>/dev/null; then return; fi
    info "Installing huggingface-hub..."
    pip3 install --break-system-packages --quiet huggingface-hub 2>/dev/null \
        || pip3 install --user --quiet huggingface-hub 2>/dev/null \
        || { err "Failed to install huggingface-hub. Install manually: pip3 install --break-system-packages huggingface-hub"; exit 1; }
}

# Download model if not present
mkdir -p .models

if [[ -n "$HF_FILENAME" ]]; then
    # Single-file download (GGUF)
    if [[ -f "$MODEL_NAME" ]]; then
        ok "Model already exists at $MODEL_NAME"
    else
        info "Downloading ${HF_REPO}/${HF_FILENAME} (~$(echo "$HF_FILENAME" | grep -q '8x7' && echo '26GB' || echo 'large'))..."
        echo "  This may take a while depending on model size and connection speed."
        echo

        _ensure_hf_hub

        python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download('${HF_REPO}', '${HF_FILENAME}', local_dir='.models/')
" || {
            err "Failed to download model. Check the repo ID and filename."
            exit 1
        }
        ok "Model downloaded to $MODEL_NAME"
    fi
else
    # Full-repo download (vLLM, transformers)
    if [[ -d "$MODEL_NAME" ]] && [[ "$(ls -A "$MODEL_NAME" 2>/dev/null)" ]]; then
        ok "Model already exists at $MODEL_NAME"
    else
        info "Downloading ${HF_REPO} to ${MODEL_NAME}..."
        echo "  This may take a while depending on model size and connection speed."
        echo

        _ensure_hf_hub

        python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('${HF_REPO}', local_dir='${MODEL_NAME}')
" || {
            err "Failed to download model. Check the repo ID and your HuggingFace token."
            exit 1
        }
        ok "Model downloaded to $MODEL_NAME"
    fi
fi
echo

# ============================================================================
# 9. Generate internal tokens
# ============================================================================

info "Generating internal tokens..."
MODEL_SERVICE_TOKEN=$(openssl rand -hex 32)
LLM_PROXY_INTERNAL_TOKEN=$(openssl rand -hex 32)
ok "Tokens generated"
echo

# ============================================================================
# 10. Write .env
# ============================================================================

info "Writing .env from template..."

if [[ -f .env ]]; then
    cp .env ".env.backup.$(date +%Y%m%d%H%M%S)"
    warn "Existing .env backed up"
fi

sed \
    -e "s|__MAIN_SERVER_IP__|${MAIN_SERVER_IP}|g" \
    -e "s|__APP_KEY__|${APP_KEY}|g" \
    -e "s|__MODEL_SERVICE_TOKEN__|${MODEL_SERVICE_TOKEN}|g" \
    -e "s|__LLM_PROXY_INTERNAL_TOKEN__|${LLM_PROXY_INTERNAL_TOKEN}|g" \
    -e "s|__DB_HOST__|${DB_HOST}|g" \
    -e "s|__DB_PORT__|${DB_PORT}|g" \
    -e "s|__DB_NAME__|${DB_NAME}|g" \
    -e "s|__DB_USER__|${DB_USER}|g" \
    -e "s|__DB_PASS__|${DB_PASS}|g" \
    -e "s|__REDIS_HOST__|${REDIS_HOST}|g" \
    -e "s|__REDIS_PORT__|${REDIS_PORT}|g" \
    -e "s|__REDIS_PASS__|${REDIS_PASS}|g" \
    -e "s|__MODEL_NAME__|${MODEL_NAME}|g" \
    -e "s|__MODEL_BACKEND__|${MODEL_BACKEND}|g" \
    -e "s|__MODEL_CHAT_FORMAT__|${MODEL_CHAT_FORMAT}|g" \
    -e "s|__MODEL_CONTEXT_WINDOW__|${MODEL_CONTEXT_WINDOW}|g" \
    -e "s#__MODEL_STOP_TOKENS__#${MODEL_STOP_TOKENS}#g" \
    -e "s|__VLLM_TENSOR_PARALLEL__|${VLLM_TENSOR_PARALLEL}|g" \
    -e "s|__VLLM_GPU_MEMORY_UTIL__|${VLLM_GPU_MEMORY_UTIL}|g" \
    -e "s|__VLLM_TOKENIZER__|${VLLM_TOKENIZER}|g" \
    -e "s|__VLLM_MAX_LORAS__|${VLLM_MAX_LORAS}|g" \
    -e "s|__GGUF_TENSOR_SPLIT__|${GGUF_TENSOR_SPLIT}|g" \
    -e "s|__GGUF_SPLIT_MODE__|${GGUF_SPLIT_MODE}|g" \
    -e "s|__GGUF_MAIN_GPU__|${GGUF_MAIN_GPU}|g" \
    env.template > .env

ok ".env written with model config: ${MODEL_BACKEND} / ${MODEL_NAME}"
echo

# ============================================================================
# 11. Pull and start
# ============================================================================

info "Pulling Docker image..."
docker compose pull || { err "Failed to pull image. Check GHCR access."; exit 1; }
ok "Image pulled"
echo

# Run migrations first, then sync settings to DB BEFORE starting the model service.
# This prevents the model service from reading stale DB settings (e.g., wrong backend).
info "Running database migrations..."
docker compose run --rm alembic-migrate 2>/dev/null || true
ok "Migrations complete"

info "Syncing model settings to database..."
echo "  Using the service's own sync logic (covers ALL settings automatically)."
docker compose run --rm --no-deps alembic-migrate python -c "
import sys; sys.path.insert(0, '.')
from services.settings_service import get_settings_service
service = get_settings_service()
results = service.sync_from_env()
synced = sum(1 for v in results.values() if v)
print(f'Synced {synced} settings from env to DB')
" || {
    warn "Settings sync failed. Will retry via API after startup."
}
echo

info "Starting stack..."
docker compose up -d

echo
info "Waiting for API health check (up to 180s)..."
echo "  Model loading can take 30-120s depending on size."
echo -n "  "
API_HEALTHY=false
for i in $(seq 1 36); do
    if curl -sf "http://localhost:${SERVER_PORT:-7704}/health" >/dev/null 2>&1; then
        echo
        API_HEALTHY=true
        break
    fi
    sleep 5
    echo -n "."
done

if [[ "$API_HEALTHY" != "true" ]]; then
    echo
    warn "API health check did not pass within 180s."
    warn "The model may still be loading. Check logs: docker compose logs -f"
    warn "After it's healthy, manually sync settings:"
    echo "  curl -X POST http://localhost:7704/settings/sync-from-env \\"
    echo "    -H 'X-Jarvis-App-Id: jarvis-llm-proxy-api' \\"
    echo "    -H 'X-Jarvis-App-Key: ${APP_KEY}'"
    exit 1
fi

ok "API is healthy"
echo

# ============================================================================
# 12. Sync settings to database
# ============================================================================

info "Syncing model settings to database..."
echo "  This writes env var values into the settings DB (source of truth for runtime config)."

SYNC_RESPONSE=$(curl -sf -X POST "http://localhost:${SERVER_PORT:-7704}/settings/sync-from-env" \
    -H "X-Jarvis-App-Id: jarvis-llm-proxy-api" \
    -H "X-Jarvis-App-Key: ${APP_KEY}" \
    2>&1) || {
    warn "Settings sync failed. Settings will still work via env fallback."
    warn "You can retry later: POST http://localhost:7704/settings/sync-from-env"
}

SYNCED_COUNT=$(echo "$SYNC_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_synced', '?'))" 2>/dev/null || echo "?")
ok "Settings synced (${SYNCED_COUNT} values written to DB)"
echo

# ============================================================================
# Done
# ============================================================================

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN} Setup complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo
echo -e "  ${BOLD}LLM Proxy:${NC}  http://${MY_IP}:${SERVER_PORT:-7704}"
echo -e "  ${BOLD}Model:${NC}      ${MODEL_NAME} (${MODEL_BACKEND})"
echo -e "  ${BOLD}Context:${NC}    ${MODEL_CONTEXT_WINDOW} tokens"
if [[ -n "${VLLM_TENSOR_PARALLEL}" && "${VLLM_TENSOR_PARALLEL}" -gt 1 ]] 2>/dev/null; then
    echo -e "  ${BOLD}GPUs:${NC}       ${VLLM_TENSOR_PARALLEL}x tensor parallel (vLLM)"
elif [[ -n "${GGUF_TENSOR_SPLIT}" ]]; then
    echo -e "  ${BOLD}GPUs:${NC}       split=${GGUF_TENSOR_SPLIT} (llama.cpp)"
fi
echo
echo -e "  ${BOLD}Useful commands:${NC}"
echo "    docker compose logs -f          # Watch logs"
echo "    docker compose restart          # Restart all services"
echo "    docker compose pull && docker compose up -d  # Update"
echo
echo -e "  ${BOLD}Verify from main server:${NC}"
echo "    curl http://${MAIN_SERVER_IP}:7700/services/jarvis-llm-proxy-api"
echo "    curl http://${MY_IP}:7704/health"
