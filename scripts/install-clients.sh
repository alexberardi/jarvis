#!/bin/bash
# Shared helper for installing jarvis client libraries from local clones.
# Source this from each service's run.sh:
#   source "${JARVIS_ROOT}/scripts/install-clients.sh"
#   install_jarvis_clients log-client config-client settings-client auth-client

JARVIS_ROOT="${JARVIS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

install_jarvis_client() {
    local client_name="$1"
    local local_path="${JARVIS_ROOT}/jarvis-${client_name}"
    if [ -d "$local_path" ]; then
        pip install -q -e "$local_path" 2>/dev/null && \
            echo "  + jarvis-${client_name} (local)" || \
            echo "  x jarvis-${client_name} (local install failed)"
    else
        echo "  . jarvis-${client_name} (using git version from requirements.txt)"
    fi
}

install_jarvis_clients() {
    echo "Installing jarvis client libraries..."
    for client in "$@"; do
        install_jarvis_client "$client"
    done
}
