#!/usr/bin/env bash
#
# check-docs-freshness.sh — Identifies jarvis-docs pages that may need
# updating based on the current git diff (staged or branch diff).
#
# Used by Claude Code's pre-commit hook to flag stale documentation.
#
# Usage:
#   ./scripts/check-docs-freshness.sh          # Check staged changes
#   ./scripts/check-docs-freshness.sh main     # Check diff vs branch

set -eo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS_DIR="$REPO_ROOT/jarvis-docs/docs"

# ── Get the diff ──────────────────────────────────────────────────

ref="${1:-}"
if [ -n "$ref" ]; then
    changed_files=$(git -C "$REPO_ROOT" diff --name-only "$ref"...HEAD 2>/dev/null || true)
else
    changed_files=$(git -C "$REPO_ROOT" diff --cached --name-only 2>/dev/null || true)
    if [ -z "$changed_files" ]; then
        changed_files=$(git -C "$REPO_ROOT" diff --name-only 2>/dev/null || true)
    fi
fi

if [ -z "$changed_files" ]; then
    exit 0
fi

# ── Service → doc page mapping (portable, no bash 4 needed) ──────

map_service_to_docs() {
    case "$1" in
        jarvis-auth)              echo "services/auth.md architecture/authentication.md" ;;
        jarvis-command-center)    echo "services/command-center.md architecture/voice-pipeline.md" ;;
        jarvis-config-service)    echo "services/config-service.md architecture/service-discovery.md" ;;
        jarvis-config-client)     echo "libraries/config-client.md" ;;
        jarvis-llm-proxy-api)     echo "services/llm-proxy.md" ;;
        jarvis-whisper-api)       echo "services/whisper-api.md" ;;
        jarvis-tts)               echo "services/tts.md extending/providers/tts.md" ;;
        jarvis-ocr-service)       echo "services/ocr-service.md" ;;
        jarvis-recipes-server)    echo "services/recipes-server.md" ;;
        jarvis-logs)              echo "services/logs.md" ;;
        jarvis-log-client)        echo "libraries/log-client.md" ;;
        jarvis-settings-server)   echo "services/settings-server.md" ;;
        jarvis-settings-client)   echo "libraries/settings-client.md extending/infrastructure/settings.md" ;;
        jarvis-mcp)               echo "services/mcp.md" ;;
        jarvis-notifications)     echo "services/notifications.md" ;;
        jarvis-notifications-relay) echo "services/notifications.md" ;;
        jarvis-admin)             echo "services/admin.md" ;;
        jarvis-node-setup)        echo "clients/node-setup.md clients/provisioning.md" ;;
        jarvis-node-mobile)       echo "clients/node-mobile.md" ;;
        jarvis-web-scraper)       echo "libraries/web-scraper.md" ;;
        jarvis-auth-client)       echo "libraries/auth-client.md" ;;
        jarvis-pantry)            echo "extending/index.md" ;;
        jarvis-command-sdk)       echo "commands/interface-reference.md commands/index.md" ;;
        *)                        echo "" ;;
    esac
}

# ── Analyze changes ───────────────────────────────────────────────

affected_docs=""
hints=""

while IFS= read -r file; do
    [ -z "$file" ] && continue

    # Extract service name (first path component)
    service="${file%%/*}"

    # Map service to doc pages
    docs=$(map_service_to_docs "$service")
    if [ -n "$docs" ]; then
        affected_docs="$affected_docs $docs"
    fi

    # Check for specific change patterns
    case "$file" in
        */app/api/*)       hints="$hints|API endpoints may have changed — update endpoint tables" ;;
        */app/main.py)     hints="$hints|App entrypoint changed — check service port/startup docs" ;;
        */alembic/*)       hints="$hints|Database migration added — update data model docs" ;;
        *docker-compose*)  hints="$hints|Docker config changed — update deployment docs" ;;
        *Dockerfile*)      hints="$hints|Container build changed — update deployment docs" ;;
        *.env.example)     hints="$hints|Environment variables changed — update env vars reference" ;;
        *CLAUDE.md)        hints="$hints|Service CLAUDE.md updated — jarvis-docs may need syncing" ;;
        *README.md)        hints="$hints|Service README updated — jarvis-docs may need syncing" ;;
    esac
done <<< "$changed_files"

# Deduplicate
affected_docs=$(echo "$affected_docs" | tr ' ' '\n' | sort -u | grep -v '^$' || true)
hints=$(echo "$hints" | tr '|' '\n' | sort -u | grep -v '^$' || true)

# ── Report ────────────────────────────────────────────────────────

if [ -z "$affected_docs" ] && [ -z "$hints" ]; then
    exit 0
fi

# Output JSON for Claude Code hook consumption
cat <<HOOK_JSON
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "DOCS FRESHNESS CHECK: The following jarvis-docs pages may need updating based on changed files:\n\nAffected doc pages:\n$(echo "$affected_docs" | sed 's/^/  - jarvis-docs\/docs\//' | tr '\n' '\\' | sed 's/\\/\\n/g')$([ -n "$hints" ] && echo "\n\nHints:\n$(echo "$hints" | sed 's/^/  - /' | tr '\n' '\\' | sed 's/\\/\\n/g')")\n\nReview these doc pages against the code changes. Update any that are stale (endpoints, config, architecture, examples). Skip if changes are internal-only (refactors, test fixes)."
  }
}
HOOK_JSON
