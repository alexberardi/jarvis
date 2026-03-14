#!/bin/bash
# Entrypoint for the Generacy orchestrator container
set -e

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [orchestrator] $*"
}

log "Starting orchestrator setup..."

# Configure git credentials
bash /usr/local/bin/setup-credentials.sh

# Resolve workspace directory (handles devcontainer detection + clone)
source /usr/local/bin/resolve-workspace.sh

# Load cluster.yaml defaults (sets GENERACY_CHANNEL, WORKER_COUNT, WORKERS_ENABLED
# if not already provided via .env or environment)
source /usr/local/bin/load-cluster-config.sh

# Install generacy/agency packages into shared volume
SHARED_PACKAGES=/shared-packages
CHANNEL="${GENERACY_CHANNEL:-stable}"
MARKER_FILE="${SHARED_PACKAGES}/.installed-version"

install_packages() {
    log "Installing @generacy-ai packages (channel: ${CHANNEL}) into ${SHARED_PACKAGES}..."
    npm install \
        --prefix "${SHARED_PACKAGES}" \
        --no-save \
        "@generacy-ai/generacy@${CHANNEL}" \
        "@generacy-ai/agency@${CHANNEL}" \
        "@generacy-ai/agency-plugin-spec-kit@${CHANNEL}" \
        2>>"$SETUP_LOG" || { log "ERROR: npm install failed"; exit 1; }
    # Write marker: channel + installed version of generacy
    local version
    version=$(node -e "console.log(require('${SHARED_PACKAGES}/node_modules/@generacy-ai/generacy/package.json').version)" 2>/dev/null || echo "unknown")
    echo "${CHANNEL}:${version}" > "${MARKER_FILE}"
    log "Packages installed (version: ${version})"
}

SETUP_LOG="${SETUP_LOG:-/tmp/generacy-setup.log}"
if [ "${SKIP_PACKAGE_UPDATE:-false}" = "true" ]; then
    log "SKIP_PACKAGE_UPDATE=true — skipping npm install"
elif [ -f "${MARKER_FILE}" ]; then
    MARKER=$(cat "${MARKER_FILE}")
    if [ "${MARKER%:*}" = "${CHANNEL}" ]; then
        log "Packages already installed for channel '${CHANNEL}' (${MARKER#*:}) — skipping"
    else
        log "Channel changed from '${MARKER%:*}' to '${CHANNEL}' — reinstalling"
        install_packages
    fi
else
    install_packages
fi

# Add shared packages to PATH for this process
export PATH="${SHARED_PACKAGES}/node_modules/.bin:${PATH}"

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

# Light check: warn if speckit is missing (orchestrator can still run)
if [ -x "/usr/local/bin/setup-speckit.sh" ]; then
    if ! bash /usr/local/bin/setup-speckit.sh --verify 2>/dev/null; then
        log "WARNING: Speckit commands not available. Workers may fail to process phases."
    fi
fi

# Wait for Redis to be ready
log "Waiting for Redis at ${REDIS_HOST:-redis}:6379..."
while ! nc -z "${REDIS_HOST:-redis}" 6379 2>/dev/null; do
    sleep 1
done
log "Redis is ready"

# Start orchestrator as PID 1
log "Starting orchestrator on port ${ORCHESTRATOR_PORT:-3100}..."
exec generacy orchestrator \
    --port "${ORCHESTRATOR_PORT:-3100}" \
    --redis-url "${REDIS_URL:-redis://redis:6379}" \
    ${LABEL_MONITOR_ENABLED:+--label-monitor}
