#!/usr/bin/env bash
# Teardown everything for a clean ./jarvis init test
# Usage: ./scripts/teardown.sh [--confirm] [--keep-volumes]
#
# Without --confirm, runs in dry-run mode showing what would happen.
# With --keep-volumes, preserves Docker volumes (faster re-init, keeps data).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARVIS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOKEN_DIR="${HOME}/.jarvis"
DATA_SERVICES_DIR="${JARVIS_ROOT}/jarvis-data-services"
DATA_SERVICES_ENV="${DATA_SERVICES_DIR}/.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

CONFIRMED=false
KEEP_VOLUMES=false

for arg in "$@"; do
    case "$arg" in
        --confirm) CONFIRMED=true ;;
        --keep-volumes) KEEP_VOLUMES=true ;;
    esac
done

# All services with docker-compose files
DOCKER_SERVICES=(
    "jarvis-config-service"
    "jarvis-auth"
    "jarvis-logs"
    "jarvis-command-center"
    "jarvis-tts"
    "jarvis-whisper-api"
    "jarvis-ocr-service"
    "jarvis-recipes-server"
    "jarvis-settings-server"
    "jarvis-mcp"
)

# Services that run locally (PID files)
LOCAL_SERVICES=(
    "jarvis-llm-proxy-api"
    "jarvis-admin"
    "jarvis-admin-server"
)

# All services that may have generated .env files
ALL_SERVICES=(
    "jarvis-config-service"
    "jarvis-auth"
    "jarvis-logs"
    "jarvis-command-center"
    "jarvis-llm-proxy-api"
    "jarvis-tts"
    "jarvis-whisper-api"
    "jarvis-ocr-service"
    "jarvis-recipes-server"
    "jarvis-settings-server"
    "jarvis-mcp"
    "jarvis-admin"
)

_find_compose_file() {
    local dir="$1"
    if [[ -f "$dir/docker-compose.dev.yaml" ]]; then
        echo "docker-compose.dev.yaml"
    elif [[ -f "$dir/docker-compose.yml" ]]; then
        echo "docker-compose.yml"
    elif [[ -f "$dir/docker-compose.yaml" ]]; then
        echo "docker-compose.yaml"
    fi
}

_action() {
    # Print what would happen (dry-run) or do it (confirmed)
    local label="$1"
    shift
    if [[ "$CONFIRMED" == true ]]; then
        echo -e "  ${RED}TEAR${NC}  ${label}"
        "$@" 2>/dev/null || true
    else
        echo -e "  ${DIM}would${NC} ${label}"
    fi
}

echo ""
echo -e "${BOLD}JARVIS TEARDOWN${NC}"
printf '%.0s\u2550' {1..55}
echo ""

if [[ "$CONFIRMED" != true ]]; then
    echo -e "${YELLOW}DRY RUN — pass --confirm to execute${NC}"
    echo ""
fi

# ── Step 1: Stop local/npm services (PIDs) ────────────────────────────────
echo -e "${DIM}Step 1: Stop local services${NC}"

for name in "${LOCAL_SERVICES[@]}"; do
    local_pid="${TOKEN_DIR}/pids/${name}.pid"
    if [[ -f "$local_pid" ]]; then
        pid=$(cat "$local_pid")
        _action "Kill ${name} (PID ${pid})" kill "$pid"
        if [[ "$CONFIRMED" == true ]]; then
            rm -f "$local_pid"
        fi
    fi
done
echo ""

# ── Step 2: Stop Docker services ──────────────────────────────────────────
echo -e "${DIM}Step 2: Stop Docker services${NC}"

for name in "${DOCKER_SERVICES[@]}"; do
    dir="${JARVIS_ROOT}/${name}"
    [[ ! -d "$dir" ]] && continue

    compose_file=$(_find_compose_file "$dir")
    [[ -z "$compose_file" ]] && continue

    env_flag=""
    [[ -f "$dir/.env" ]] && env_flag="--env-file .env"

    _action "docker compose down: ${name}" \
        bash -c "cd '$dir' && docker compose $env_flag -f '$compose_file' down --remove-orphans"
done
echo ""

# ── Step 3: Stop jarvis-data-services infrastructure ──────────────────────
echo -e "${DIM}Step 3: Stop infrastructure (jarvis-data-services)${NC}"

if [[ -d "$DATA_SERVICES_DIR" ]]; then
    if [[ "$KEEP_VOLUMES" == true ]]; then
        _action "docker compose down (keeping volumes)" \
            bash -c "cd '$DATA_SERVICES_DIR' && docker compose --env-file .env down"
    else
        _action "docker compose down -v (removing volumes + data)" \
            bash -c "cd '$DATA_SERVICES_DIR' && docker compose --env-file .env down -v"
    fi
else
    echo -e "  ${DIM}skip${NC}  jarvis-data-services not found"
fi
echo ""

# ── Step 4: Remove .env files from services ───────────────────────────────
echo -e "${DIM}Step 4: Remove generated .env files${NC}"

for name in "${ALL_SERVICES[@]}"; do
    env_file="${JARVIS_ROOT}/${name}/.env"
    if [[ -f "$env_file" ]]; then
        _action "rm ${name}/.env" rm "$env_file"
    fi
done
echo ""

# ── Step 5: Remove Python virtual environments ──────────────────────────
echo -e "${DIM}Step 5: Remove Python venvs${NC}"

for name in "${ALL_SERVICES[@]}"; do
    for vdir in .venv venv; do
        if [[ -d "${JARVIS_ROOT}/${name}/${vdir}" ]]; then
            _action "rm -rf ${name}/${vdir}/" rm -rf "${JARVIS_ROOT}/${name}/${vdir}"
        fi
    done
done
echo ""

# ── Step 6: Remove ~/.jarvis/ (tokens, DB names, PIDs) ───────────────────
echo -e "${DIM}Step 6: Remove ~/.jarvis/ config${NC}"

if [[ -f "${TOKEN_DIR}/tokens.env" ]]; then
    _action "rm ~/.jarvis/tokens.env" rm "${TOKEN_DIR}/tokens.env"
fi

if [[ -f "${TOKEN_DIR}/databases.env" ]]; then
    _action "rm ~/.jarvis/databases.env" rm "${TOKEN_DIR}/databases.env"
fi

if [[ -d "${TOKEN_DIR}/pids" ]]; then
    _action "rm -rf ~/.jarvis/pids/" rm -rf "${TOKEN_DIR}/pids"
fi
echo ""

# ── Step 7: Remove generated network override ────────────────────────────
echo -e "${DIM}Step 7: Remove generated files${NC}"

if [[ -f "${JARVIS_ROOT}/.jarvis-net-override.yaml" ]]; then
    _action "rm .jarvis-net-override.yaml" rm "${JARVIS_ROOT}/.jarvis-net-override.yaml"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────
printf '%.0s\u2500' {1..55}
echo ""

if [[ "$CONFIRMED" == true ]]; then
    echo -e "${GREEN}Teardown complete.${NC}"
    if [[ "$KEEP_VOLUMES" == true ]]; then
        echo -e "  Volumes preserved — databases still have data."
        echo -e "  Re-init: ${BOLD}./jarvis init${NC}"
    else
        echo -e "  Volumes removed — clean slate."
        echo -e "  Re-init: ${BOLD}./jarvis init${NC}"
    fi
else
    echo ""
    echo -e "Run with ${BOLD}--confirm${NC} to execute:"
    echo -e "  ${CYAN}./scripts/teardown.sh --confirm${NC}"
    echo ""
    echo -e "To keep database volumes (faster re-init):"
    echo -e "  ${CYAN}./scripts/teardown.sh --confirm --keep-volumes${NC}"
fi
echo ""
