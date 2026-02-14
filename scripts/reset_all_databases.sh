#!/bin/bash
# Reset all Jarvis databases: drop, recreate, apply migrations (which seeds settings)
# Usage: ./scripts/reset_all_databases.sh [--confirm]
#
# Without --confirm, runs in dry-run mode showing what would happen.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARVIS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

POSTGRES_CONTAINER="jarvis-postgres"
POSTGRES_USER="postgres"

CONFIRMED=false
if [[ "$1" == "--confirm" ]]; then
    CONFIRMED=true
fi

# All jarvis databases to drop and recreate
DATABASES=(
    "jarvis_auth"
    "jarvis_auth_db"
    "jarvis_command_center"
    "jarvis_config"
    "jarvis_llm_proxy"
    "jarvis_logs"
    "jarvis_mcp"
    "jarvis_ocr"
    "jarvis_recipes"
    "jarvis_tts"
    "jarvis_whisper"
)

# Services with migrations (in tier order)
SERVICES_WITH_MIGRATIONS=(
    "jarvis-config-service"
    "jarvis-auth"
    "jarvis-logs"
    "jarvis-command-center"
    "jarvis-llm-proxy-api"
    "jarvis-tts"
    "jarvis-whisper-api"
    "jarvis-ocr-service"
    "jarvis-recipes-server"
    "jarvis-mcp"
)

psql_exec() {
    docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" "$@"
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  JARVIS DATABASE RESET"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

if [[ "$CONFIRMED" != true ]]; then
    echo "DRY RUN - pass --confirm to execute"
    echo
fi

# ── Step 1: Drop all databases ──────────────────────────────────
echo "Step 1: Drop databases"
echo "──────────────────────"

for db in "${DATABASES[@]}"; do
    if [[ "$CONFIRMED" == true ]]; then
        # Terminate existing connections first
        psql_exec -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$db' AND pid <> pg_backend_pid();" -t -q 2>/dev/null || true
        if psql_exec -c "DROP DATABASE IF EXISTS $db;" -t -q 2>/dev/null; then
            echo "  Dropped: $db"
        else
            echo "  Failed to drop: $db"
        fi
    else
        echo "  Would drop: $db"
    fi
done
echo

# ── Step 2: Recreate databases ──────────────────────────────────
echo "Step 2: Recreate databases"
echo "──────────────────────────"

# jarvis_auth_db is stale, don't recreate it
DATABASES_TO_CREATE=(
    "jarvis_auth"
    "jarvis_command_center"
    "jarvis_config"
    "jarvis_llm_proxy"
    "jarvis_logs"
    "jarvis_mcp"
    "jarvis_ocr"
    "jarvis_recipes"
    "jarvis_tts"
    "jarvis_whisper"
)

for db in "${DATABASES_TO_CREATE[@]}"; do
    if [[ "$CONFIRMED" == true ]]; then
        if psql_exec -c "CREATE DATABASE $db;" -t -q 2>/dev/null; then
            echo "  Created: $db"
        else
            echo "  Failed to create: $db"
        fi
    else
        echo "  Would create: $db"
    fi
done
echo

# ── Step 3: Apply migrations ────────────────────────────────────
echo "Step 3: Apply migrations (seeds settings)"
echo "──────────────────────────────────────────"

if [[ "$CONFIRMED" == true ]]; then
    SUCCESS=()
    FAILED=()

    for service in "${SERVICES_WITH_MIGRATIONS[@]}"; do
        service_dir="$JARVIS_ROOT/$service"
        migration_script="$service_dir/apply_migrations.sh"

        if [[ ! -f "$migration_script" ]]; then
            echo "  No apply_migrations.sh: $service"
            continue
        fi

        cd "$service_dir"
        if bash apply_migrations.sh 2>&1 | sed 's/^/    /'; then
            echo "  Applied: $service"
            SUCCESS+=("$service")
        else
            echo "  FAILED: $service"
            FAILED+=("$service")
        fi
    done

    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  SUMMARY"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Databases dropped: ${#DATABASES[@]}"
    echo "  Databases created: ${#DATABASES_TO_CREATE[@]}"
    echo "  Migrations OK:     ${#SUCCESS[@]}"
    if [[ ${#FAILED[@]} -gt 0 ]]; then
        echo "  Migrations FAILED: ${#FAILED[@]} (${FAILED[*]})"
        exit 1
    fi
    echo
    echo "Next steps:"
    echo "  1. Start jarvis-config-service and jarvis-auth"
    echo "  2. Open jarvis-admin setup wizard to create superuser"
    echo "  3. Register services via admin UI"
else
    for service in "${SERVICES_WITH_MIGRATIONS[@]}"; do
        echo "  Would migrate: $service"
    done
    echo
    echo "Run with --confirm to execute."
fi
