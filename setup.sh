#!/bin/bash
# Generacy Development Cluster Setup
#
# Run this script after cloning/forking to configure the cluster
# for your project. Idempotent — safe to re-run at any time.
#
# If .generacy/config.yaml already exists (from the onboarding UI,
# manual creation, or a previous run), the script reads project info
# from it and skips those prompts.
#
# Usage:
#   ./setup.sh
#   ./setup.sh --repo-url https://github.com/your-org/your-repo.git

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEVCONTAINER_DIR="${SCRIPT_DIR}/.devcontainer"
GENERACY_DIR="${SCRIPT_DIR}/.generacy"
CONFIG_FILE="${GENERACY_DIR}/config.yaml"

# ── Helpers ──────────────────────────────────────────────────────────────────

info()  { echo -e "\033[1;34m==>\033[0m $*"; }
ok()    { echo -e "\033[1;32m  ✓\033[0m $*"; }
warn()  { echo -e "\033[1;33m  !\033[0m $*"; }
error() { echo -e "\033[1;31m  ✗\033[0m $*"; }
ask()   { echo -en "\033[1;36m  ?\033[0m $1 "; }

# Extract owner/repo from a GitHub URL or owner/repo string
parse_repo() {
    local input="$1"
    # Strip protocol and .git suffix
    input="${input#https://github.com/}"
    input="${input#http://github.com/}"
    input="${input#github.com/}"
    input="${input%.git}"
    input="${input%/}"
    echo "$input"
}

# ── Parse arguments ─────────────────────────────────────────────────────────

ARG_REPO_URL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-url) ARG_REPO_URL="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: ./setup.sh [--repo-url <url>]"
            echo ""
            echo "Options:"
            echo "  --repo-url    Git URL of the project repo (auto-detected if omitted)"
            echo ""
            echo "If .generacy/config.yaml exists, project info is read from it."
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Step 1: Load or create .generacy/config.yaml ────────────────────────────

info "Checking for existing config..."

if [ -f "$CONFIG_FILE" ]; then
    info "Found existing .generacy/config.yaml"

    # Parse primary repo from config (handles "owner/repo" or "github.com/owner/repo")
    PRIMARY_REPO_RAW=$(grep -A1 'primary:' "$CONFIG_FILE" | tail -1 | sed 's/.*primary:[[:space:]]*//' | tr -d '"' | tr -d "'")
    if [ -z "$PRIMARY_REPO_RAW" ]; then
        PRIMARY_REPO_RAW=$(grep 'primary:' "$CONFIG_FILE" | head -1 | sed 's/.*primary:[[:space:]]*//' | tr -d '"' | tr -d "'")
    fi

    OWNER_REPO=$(parse_repo "$PRIMARY_REPO_RAW")
    OWNER="${OWNER_REPO%%/*}"
    REPO_NAME="${OWNER_REPO##*/}"
    REPO_URL="https://github.com/${OWNER_REPO}.git"
    PROJECT_NAME=$(echo "$REPO_NAME" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')

    ok "Primary repo: ${OWNER}/${REPO_NAME}"
    ok "Project name: $PROJECT_NAME"

    CONFIG_EXISTS=true
else
    CONFIG_EXISTS=false
    info "No config.yaml found — will create one"

    # Detect repo URL
    REPO_URL="${ARG_REPO_URL}"
    if [ -z "$REPO_URL" ]; then
        REPO_URL=$(git remote get-url origin 2>/dev/null || true)
    fi
    if [ -z "$REPO_URL" ]; then
        ask "Repository URL (e.g., https://github.com/your-org/your-repo.git):"
        read -r REPO_URL
    fi
    if [ -z "$REPO_URL" ]; then
        error "Repository URL is required"
        exit 1
    fi

    OWNER_REPO=$(parse_repo "$REPO_URL")
    OWNER="${OWNER_REPO%%/*}"
    REPO_NAME="${OWNER_REPO##*/}"
    PROJECT_NAME=$(echo "$REPO_NAME" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')

    ok "Repository: $REPO_URL"
    ok "Owner: $OWNER"
    ok "Project name: $PROJECT_NAME"
    ok "Repo name: $REPO_NAME"
fi

# ── Step 2: Branch ──────────────────────────────────────────────────────────

if [ "$CONFIG_EXISTS" = "true" ]; then
    REPO_BRANCH=$(grep 'branch:' "$CONFIG_FILE" | head -1 | sed 's/.*branch:[[:space:]]*//' | tr -d '"' | tr -d "'")
    REPO_BRANCH="${REPO_BRANCH:-main}"
    ok "Branch (from config): $REPO_BRANCH"
else
    REPO_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "main")
    ask "Default branch [$REPO_BRANCH]:"
    read -r input
    REPO_BRANCH="${input:-$REPO_BRANCH}"
    ok "Branch: $REPO_BRANCH"
fi

# ── Step 3: Worker count ────────────────────────────────────────────────────

WORKER_COUNT=3
ask "Number of workers [$WORKER_COUNT]:"
read -r input
WORKER_COUNT="${input:-$WORKER_COUNT}"
ok "Workers: $WORKER_COUNT"

# ── Step 4: Create smee.io channel ──────────────────────────────────────────

info "Setting up webhook forwarding..."

# Check if smee is already configured in an existing .env
SMEE_CHANNEL_URL=""
ENV_FILE="${DEVCONTAINER_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
    SMEE_CHANNEL_URL=$(grep '^SMEE_CHANNEL_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
fi

if [ -n "$SMEE_CHANNEL_URL" ]; then
    ok "Smee channel (from existing .env): $SMEE_CHANNEL_URL"
else
    if command -v curl >/dev/null 2>&1; then
        ask "Create a new smee.io channel? [Y/n]:"
        read -r create_smee
        if [ "${create_smee:-Y}" != "n" ] && [ "${create_smee:-Y}" != "N" ]; then
            SMEE_CHANNEL_URL=$(curl -s https://smee.io/new -o /dev/null -w '%{redirect_url}' 2>/dev/null || true)
            if [ -n "$SMEE_CHANNEL_URL" ]; then
                ok "Smee channel: $SMEE_CHANNEL_URL"
            else
                warn "Could not create smee.io channel automatically"
            fi
        fi
    fi

    if [ -z "$SMEE_CHANNEL_URL" ]; then
        ask "Smee.io channel URL (create one at https://smee.io/new, or press Enter to skip):"
        read -r SMEE_CHANNEL_URL
        if [ -n "$SMEE_CHANNEL_URL" ]; then
            ok "Smee channel: $SMEE_CHANNEL_URL"
        else
            warn "Skipping smee.io — you can add SMEE_CHANNEL_URL to .env later"
        fi
    fi
fi

# ── Step 5: Generate .generacy/config.yaml (if not present) ─────────────────

if [ "$CONFIG_EXISTS" = "false" ]; then
    info "Creating .generacy/config.yaml..."
    mkdir -p "$GENERACY_DIR"
    cat > "$CONFIG_FILE" <<EOF
# Generacy project configuration
# Docs: https://github.com/generacy-ai/cluster-base

project:
  name: "${PROJECT_NAME}"

repos:
  primary: "${OWNER}/${REPO_NAME}"
  dev:
    # Add repos for active development (owner/repo format):
    # - ${OWNER}/another-repo
  clone:
    # Add repos to clone as read-only reference:
    # - ${OWNER}/docs

defaults:
  baseBranch: ${REPO_BRANCH}
EOF
    ok "Created $CONFIG_FILE"
fi

# ── Step 6: Generate .env (Docker Compose variables) ─────────────────────────

info "Generating .devcontainer/.env..."

write_env=true
if [ -f "$ENV_FILE" ]; then
    ask ".env already exists. Overwrite? [y/N]:"
    read -r overwrite
    if [ "${overwrite}" != "y" ] && [ "${overwrite}" != "Y" ]; then
        warn "Keeping existing .env"
        write_env=false
    fi
fi

if [ "$write_env" = "true" ]; then
    cat > "$ENV_FILE" <<EOF
# Docker Compose configuration
# Generated by setup.sh — $(date -u '+%Y-%m-%dT%H:%M:%SZ')
#
# These variables are used by docker-compose.yml for container setup.
# Project config (repos, monitoring, webhooks) lives in .generacy/config.yaml.

PROJECT_NAME=${PROJECT_NAME}
REPO_URL=https://github.com/${OWNER}/${REPO_NAME}.git
REPO_NAME=${REPO_NAME}
REPO_BRANCH=${REPO_BRANCH}
WORKER_COUNT=${WORKER_COUNT}
ORCHESTRATOR_PORT=3100
SMEE_CHANNEL_URL=${SMEE_CHANNEL_URL}
LABEL_MONITOR_ENABLED=true
WEBHOOK_SETUP_ENABLED=true
EOF
    ok "Created $ENV_FILE"
fi

# ── Step 7: Generate .env.local (secrets) ────────────────────────────────────

info "Setting up credentials..."

ENV_LOCAL_FILE="${DEVCONTAINER_DIR}/.env.local"
write_local=true

if [ -f "$ENV_LOCAL_FILE" ]; then
    ask ".env.local already exists. Overwrite? [y/N]:"
    read -r overwrite
    if [ "${overwrite}" != "y" ] && [ "${overwrite}" != "Y" ]; then
        warn "Keeping existing .env.local"
        write_local=false
    fi
fi

if [ "$write_local" = "true" ]; then
    echo ""
    info "GitHub fine-grained access token"
    echo "  Create one at: https://github.com/settings/tokens?type=beta"
    echo "  Required permissions: Contents (rw), Issues (rw), Pull requests (rw)"
    echo ""

    ask "GitHub token (input hidden):"
    read -rs GH_TOKEN
    echo ""

    ask "GitHub username:"
    read -r GH_USERNAME

    ask "GitHub email:"
    read -r GH_EMAIL

    echo ""
    info "Claude API key"
    echo "  Get one at: https://console.anthropic.com/settings/keys"
    echo ""

    ask "Claude API key (input hidden):"
    read -rs CLAUDE_API_KEY
    echo ""

    cat > "$ENV_LOCAL_FILE" <<EOF
# Generated by setup.sh — DO NOT COMMIT
GH_TOKEN=${GH_TOKEN}
GH_USERNAME=${GH_USERNAME}
GH_EMAIL=${GH_EMAIL}
CLAUDE_API_KEY=${CLAUDE_API_KEY}
EOF
    chmod 600 "$ENV_LOCAL_FILE"
    ok "Created $ENV_LOCAL_FILE (permissions: 600)"
fi

# ── Step 8: Update devcontainer.json ─────────────────────────────────────────

info "Updating devcontainer.json..."

DEVCONTAINER_JSON="${DEVCONTAINER_DIR}/devcontainer.json"

if [ -f "$DEVCONTAINER_JSON" ]; then
    if command -v sed >/dev/null 2>&1; then
        sed -i.bak \
            -e "s|\"name\": \"generacy-cluster\"|\"name\": \"${PROJECT_NAME}\"|" \
            -e "s|\"workspaceFolder\": \"/workspaces/project\"|\"workspaceFolder\": \"/workspaces/${REPO_NAME}\"|" \
            "$DEVCONTAINER_JSON"
        rm -f "${DEVCONTAINER_JSON}.bak"
        ok "Updated devcontainer.json (name: ${PROJECT_NAME}, workspaceFolder: /workspaces/${REPO_NAME})"
    else
        warn "sed not available — update devcontainer.json manually"
    fi
else
    warn "devcontainer.json not found at ${DEVCONTAINER_JSON}"
fi

# ── Step 9: Ensure ~/.claude.json exists ─────────────────────────────────────

info "Checking Claude config..."

CLAUDE_JSON="${HOME}/.claude.json"
if [ ! -f "$CLAUDE_JSON" ]; then
    echo '{}' > "$CLAUDE_JSON"
    ok "Created ${CLAUDE_JSON} (required for Docker volume mount)"
else
    ok "${CLAUDE_JSON} already exists"
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
info "Setup complete!"
echo ""
echo "  Generated files:"
echo "    .generacy/config.yaml       — project configuration (commit this)"
echo "    .devcontainer/.env          — Docker Compose settings (commit this)"
echo "    .devcontainer/.env.local    — secrets (gitignored, never commit)"
echo "    .devcontainer/devcontainer.json — updated with project values"
echo ""
echo "  Next steps:"
echo "    1. Open this project in VS Code"
echo "    2. VS Code will prompt: 'Reopen in Container' — click it"
echo "    3. Or run manually: cd .devcontainer && docker compose up -d"
echo ""
if [ -n "$SMEE_CHANNEL_URL" ]; then
    echo "  Webhook forwarding:"
    echo "    Add this URL as a webhook in your GitHub repo settings:"
    echo "    $SMEE_CHANNEL_URL"
    echo ""
fi
