#!/bin/bash
# Setup Docker-in-Docker daemon and Docker contexts
# Called by entrypoint scripts before main service starts.
# Idempotent: skips if Docker is already running (e.g. from devcontainer feature).
#
# Requires: ENABLE_DIND=true env var, privileged mode, node user with sudo dockerd

set -e

DIND_SOCKET="/var/run/docker.sock"
HOST_SOCKET="/var/run/docker-host.sock"
MAX_WAIT=30

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [setup-docker] $*"
}

# Start DinD daemon if not already running
start_dind() {
    if docker info >/dev/null 2>&1; then
        log "Docker daemon already running (from devcontainer feature or previous start)"
        return 0
    fi

    log "Starting Docker-in-Docker daemon..."
    sudo dockerd \
        --host=unix://${DIND_SOCKET} \
        --storage-driver=overlay2 \
        > /tmp/dockerd.log 2>&1 &

    local waited=0
    while [ $waited -lt $MAX_WAIT ]; do
        if docker info >/dev/null 2>&1; then
            log "Docker daemon is ready (took ${waited}s)"
            return 0
        fi
        waited=$((waited + 1))
        sleep 1
    done

    log "ERROR: Docker daemon failed to start within ${MAX_WAIT}s"
    tail -20 /tmp/dockerd.log 2>/dev/null || true
    return 1
}

# Fix host socket permissions and create Docker contexts
setup_host_context() {
    # Fix host Docker socket permissions if mounted
    if [ -S "$HOST_SOCKET" ]; then
        log "Fixing host Docker socket permissions..."
        sudo chmod 666 "$HOST_SOCKET" 2>/dev/null || true
    fi

    # Create host context if it doesn't exist and host socket is available
    if [ -S "$HOST_SOCKET" ] && ! docker context inspect host >/dev/null 2>&1; then
        log "Creating 'host' Docker context..."
        docker context create host \
            --docker "host=unix://${HOST_SOCKET}" \
            --description "Host Docker (manages worker containers)" 2>/dev/null || true
    fi

    # Ensure default context is active (DinD)
    docker context use default 2>/dev/null || true

    log "Docker contexts configured"
}

# Main
main() {
    if [ "${ENABLE_DIND:-false}" != "true" ]; then
        # Even without DinD, set up host context if Docker CLI and host socket exist
        if command -v docker >/dev/null 2>&1 && [ -S "$HOST_SOCKET" ]; then
            setup_host_context
        fi
        return 0
    fi

    if ! start_dind; then
        log "WARNING: DinD failed to start, continuing without Docker"
    fi

    # Set up host context (DooD) if host socket is mounted — independent of DinD
    if command -v docker >/dev/null 2>&1 && [ -S "$HOST_SOCKET" ]; then
        setup_host_context
    fi
}

main "$@"
