#!/bin/bash
# Entrypoint for Generacy worker containers
set -e

export AGENT_ID="${AGENT_ID:-$HOSTNAME}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [worker:${AGENT_ID}] $*"
}

log "Starting worker setup..."

# Start Docker-in-Docker daemon (workers get DinD but not host context)
bash /usr/local/bin/setup-docker-dind.sh

# Configure git credentials
bash /usr/local/bin/setup-credentials.sh

# Resolve workspace directory (handles devcontainer detection + clone)
source /usr/local/bin/resolve-workspace.sh

# Set up CLI wrappers pointing to shared packages volume
SHARED_PACKAGES=/shared-packages
LOCAL_BIN="${HOME}/.local/bin"
mkdir -p "${LOCAL_BIN}"

for cli in generacy agency; do
    WRAPPER="${LOCAL_BIN}/${cli}"
    cat > "${WRAPPER}" <<EOF
#!/bin/sh
exec node ${SHARED_PACKAGES}/node_modules/.bin/${cli} "\$@"
EOF
    chmod +x "${WRAPPER}"
done

# Ensure ~/.local/bin is on PATH for this process and subprocesses
export PATH="${LOCAL_BIN}:${PATH}"
if ! grep -q 'local/bin' "${HOME}/.bashrc" 2>/dev/null; then
    echo 'export PATH="${HOME}/.local/bin:${PATH}"' >> "${HOME}/.bashrc"
fi

log "CLI wrappers created in ${LOCAL_BIN}"

# Run generacy setup if CLI is available
if command -v generacy >/dev/null 2>&1; then
    SETUP_LOG="/tmp/generacy-setup.log"
    log "Running generacy setup..."

    # Non-critical: log errors but continue
    generacy setup auth 2>>"$SETUP_LOG" || log "WARNING: 'generacy setup auth' failed (see $SETUP_LOG)"

    # Important: log errors but continue (workspace needed for build)
    # Pass --config when config file exists to avoid ambiguity with multiple repos
    CONFIG_PATH="${WORKSPACE_DIR}/.generacy/config.yaml"
    if [ -f "$CONFIG_PATH" ]; then
        generacy setup workspace --config "$CONFIG_PATH" --clean 2>>"$SETUP_LOG" || log "WARNING: 'generacy setup workspace' failed (see $SETUP_LOG)"
    else
        generacy setup workspace --clean 2>>"$SETUP_LOG" || log "WARNING: 'generacy setup workspace' failed (see $SETUP_LOG)"
    fi

    # Critical: trigger speckit recovery on failure
    generacy setup build 2>>"$SETUP_LOG" || {
        log "ERROR: 'generacy setup build' failed — attempting speckit recovery (see $SETUP_LOG)"
        bash /usr/local/bin/setup-speckit.sh 2>>"$SETUP_LOG" || log "ERROR: speckit recovery also failed (see $SETUP_LOG)"
    }
fi

# Pre-flight: verify speckit readiness
if [ -x "/usr/local/bin/setup-speckit.sh" ]; then
    if ! bash /usr/local/bin/setup-speckit.sh --verify; then
        log "FATAL: Speckit commands not available. Worker cannot process phases."
        log "FATAL: Check ${SETUP_LOG:-/tmp/generacy-setup.log} for setup errors."
        log "FATAL: Ensure agency repo is accessible and 'generacy setup build' succeeds."
        exit 1
    fi
fi

# Start worker as PID 1
log "Starting worker ${AGENT_ID}..."
exec generacy orchestrator \
    --port "${HEALTH_PORT:-9001}" \
    --redis-url "redis://${REDIS_HOST:-redis}:${REDIS_PORT:-6379}" \
    --worker-only
