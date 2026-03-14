#!/bin/bash
# Load cluster configuration from .generacy/cluster.yaml
#
# Reads cluster.yaml and exports environment variables for values
# not already set by .env or the shell environment. This allows
# .env overrides to take precedence over cluster.yaml defaults.
#
# Exported variables:
#   WORKER_COUNT       — from workers.count (default: 3)
#   WORKERS_ENABLED    — from workers.enabled (default: true)
#   GENERACY_CHANNEL   — from channel (default: stable)
#
# Usage: source /usr/local/bin/load-cluster-config.sh
#   Requires WORKSPACE_DIR to be set (by resolve-workspace.sh).

_cluster_log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [cluster-config] $*"
}

CLUSTER_YAML="${WORKSPACE_DIR:-.}/.generacy/cluster.yaml"

if [ ! -f "$CLUSTER_YAML" ]; then
    _cluster_log "No cluster.yaml found at ${CLUSTER_YAML} — using environment defaults"
    return 0 2>/dev/null || exit 0
fi

_cluster_log "Loading cluster config from ${CLUSTER_YAML}"

# Parse simple YAML values (flat keys and one-level nested keys).
# This avoids requiring js-yaml or python in the entrypoint path.
_yaml_value() {
    local key="$1"
    grep -E "^\s*${key}:" "$CLUSTER_YAML" 2>/dev/null \
        | head -1 \
        | sed 's/^[^:]*:[[:space:]]*//' \
        | sed 's/[[:space:]]*#.*//' \
        | tr -d '"'"'"
}

# Channel
_val=$(_yaml_value "channel")
if [ -n "$_val" ]; then
    if [ -z "${GENERACY_CHANNEL:-}" ]; then
        export GENERACY_CHANNEL="$_val"
        _cluster_log "Set GENERACY_CHANNEL=${_val} (from cluster.yaml)"
    else
        if [ "$GENERACY_CHANNEL" != "$_val" ]; then
            _cluster_log "GENERACY_CHANNEL=${GENERACY_CHANNEL} (env override; cluster.yaml has ${_val})"
        fi
    fi
fi

# Worker count
_val=$(_yaml_value "count")
if [ -n "$_val" ]; then
    if [ -z "${WORKER_COUNT:-}" ]; then
        export WORKER_COUNT="$_val"
        _cluster_log "Set WORKER_COUNT=${_val} (from cluster.yaml)"
    else
        if [ "$WORKER_COUNT" != "$_val" ]; then
            _cluster_log "WORKER_COUNT=${WORKER_COUNT} (env override; cluster.yaml has ${_val})"
        fi
    fi
fi

# Workers enabled
_val=$(_yaml_value "enabled")
if [ -n "$_val" ]; then
    export WORKERS_ENABLED="$_val"
    _cluster_log "Set WORKERS_ENABLED=${_val} (from cluster.yaml)"
fi

unset _val _yaml_value _cluster_log
