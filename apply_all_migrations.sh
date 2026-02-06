#!/bin/bash
# Apply migrations for all Jarvis services
# Usage: ./apply_all_migrations.sh [--dry-run]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false

if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE - No migrations will be applied ==="
    echo
fi

# Services with apply_migrations.sh scripts
SERVICES=(
    "jarvis-auth"
    "jarvis-command-center"
    "jarvis-config-service"
    "jarvis-llm-proxy-api"
    "jarvis-logs"
    "jarvis-mcp"
    "jarvis-ocr-service"
    "jarvis-recipes-server"
    "jarvis-tts"
    "jarvis-whisper-api"
)

SUCCESS=()
FAILED=()
SKIPPED=()

for service in "${SERVICES[@]}"; do
    service_dir="$SCRIPT_DIR/$service"
    migration_script="$service_dir/apply_migrations.sh"

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 $service"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [[ ! -d "$service_dir" ]]; then
        echo "   ⚠️  Directory not found, skipping"
        SKIPPED+=("$service")
        echo
        continue
    fi

    if [[ ! -f "$migration_script" ]]; then
        echo "   ⚠️  No apply_migrations.sh found, skipping"
        SKIPPED+=("$service")
        echo
        continue
    fi

    if [[ "$DRY_RUN" == true ]]; then
        echo "   Would run: $migration_script"
        echo
        continue
    fi

    cd "$service_dir"
    if bash apply_migrations.sh; then
        echo "   ✅ Migrations applied successfully"
        SUCCESS+=("$service")
    else
        echo "   ❌ Migration failed"
        FAILED+=("$service")
    fi
    echo
done

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ "$DRY_RUN" == true ]]; then
    echo "Dry run complete. ${#SERVICES[@]} services would be processed."
else
    if [[ ${#SUCCESS[@]} -gt 0 ]]; then
        echo "✅ Success (${#SUCCESS[@]}): ${SUCCESS[*]}"
    fi
    if [[ ${#SKIPPED[@]} -gt 0 ]]; then
        echo "⚠️  Skipped (${#SKIPPED[@]}): ${SKIPPED[*]}"
    fi
    if [[ ${#FAILED[@]} -gt 0 ]]; then
        echo "❌ Failed (${#FAILED[@]}): ${FAILED[*]}"
        exit 1
    fi
fi

echo
echo "Done!"
