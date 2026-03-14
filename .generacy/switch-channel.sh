#!/bin/bash
# Switch Generacy release channel (preview ↔ stable)
#
# Updates the cluster-base remote to track the appropriate branch,
# pulls the latest changes, and updates local configuration files.
#
# Usage:
#   .generacy/switch-channel.sh preview
#   .generacy/switch-channel.sh stable

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CLUSTER_YAML="${SCRIPT_DIR}/cluster.yaml"
ENV_TEMPLATE="${PROJECT_DIR}/.devcontainer/generacy/.env.template"
ENV_FILE="${PROJECT_DIR}/.devcontainer/generacy/.env"

# ── Helpers ──────────────────────────────────────────────────────────────────

info()  { echo -e "\033[1;34m==>\033[0m $*"; }
ok()    { echo -e "\033[1;32m  ✓\033[0m $*"; }
warn()  { echo -e "\033[1;33m  !\033[0m $*"; }
error() { echo -e "\033[1;31m  ✗\033[0m $*"; }

# ── Validate arguments ──────────────────────────────────────────────────────

CHANNEL="${1:-}"

if [ -z "$CHANNEL" ]; then
    echo "Usage: .generacy/switch-channel.sh <preview|stable>"
    echo ""
    echo "Channels:"
    echo "  stable   — production-ready releases (tracks cluster-base/main)"
    echo "  preview  — latest features and fixes (tracks cluster-base/develop)"
    exit 1
fi

if [ "$CHANNEL" != "preview" ] && [ "$CHANNEL" != "stable" ]; then
    error "Invalid channel: ${CHANNEL}"
    echo "  Valid channels: preview, stable"
    exit 1
fi

# Map channel to branch
if [ "$CHANNEL" = "preview" ]; then
    BRANCH="develop"
else
    BRANCH="main"
fi

info "Switching to '${CHANNEL}' channel (branch: ${BRANCH})"

# ── Step 1: Update cluster-base remote ──────────────────────────────────────

REMOTE="cluster-base"

if git remote get-url "$REMOTE" >/dev/null 2>&1; then
    ok "Remote '${REMOTE}' exists"
else
    info "Adding remote '${REMOTE}'..."
    git remote add "$REMOTE" https://github.com/generacy-ai/cluster-base.git
    ok "Added remote '${REMOTE}'"
fi

# ── Step 2: Fetch from the target branch ────────────────────────────────────

info "Fetching ${REMOTE}/${BRANCH}..."
git fetch "$REMOTE" "$BRANCH"
ok "Fetched ${REMOTE}/${BRANCH}"

# ── Step 3: Merge changes ──────────────────────────────────────────────────

info "Merging ${REMOTE}/${BRANCH}..."

if git merge "${REMOTE}/${BRANCH}" --allow-unrelated-histories -m "chore: switch to ${CHANNEL} channel (merge ${REMOTE}/${BRANCH})" 2>/dev/null; then
    ok "Merged ${REMOTE}/${BRANCH}"
else
    warn "Merge had conflicts — resolve them manually, then re-run this script"
    warn "Or run: git merge --abort  to undo"
    exit 1
fi

# ── Step 4: Update cluster.yaml ─────────────────────────────────────────────

if [ -f "$CLUSTER_YAML" ]; then
    info "Updating cluster.yaml..."
    sed -i.bak "s/^channel:.*$/channel: ${CHANNEL}/" "$CLUSTER_YAML"
    rm -f "${CLUSTER_YAML}.bak"
    ok "cluster.yaml channel set to '${CHANNEL}'"
else
    warn "cluster.yaml not found at ${CLUSTER_YAML} — skipping"
fi

# ── Step 5: Update .env.template ────────────────────────────────────────────

if [ -f "$ENV_TEMPLATE" ]; then
    info "Updating .env.template..."
    sed -i.bak "s/^GENERACY_CHANNEL=.*$/GENERACY_CHANNEL=${CHANNEL}/" "$ENV_TEMPLATE"
    rm -f "${ENV_TEMPLATE}.bak"
    ok ".env.template GENERACY_CHANNEL set to '${CHANNEL}'"
else
    warn ".env.template not found at ${ENV_TEMPLATE} — skipping"
fi

# ── Step 6: Update .env (if it exists) ──────────────────────────────────────

if [ -f "$ENV_FILE" ]; then
    info "Updating .env..."
    if grep -q '^GENERACY_CHANNEL=' "$ENV_FILE"; then
        sed -i.bak "s/^GENERACY_CHANNEL=.*$/GENERACY_CHANNEL=${CHANNEL}/" "$ENV_FILE"
        rm -f "${ENV_FILE}.bak"
        ok ".env GENERACY_CHANNEL set to '${CHANNEL}'"
    else
        echo "GENERACY_CHANNEL=${CHANNEL}" >> "$ENV_FILE"
        ok "Added GENERACY_CHANNEL=${CHANNEL} to .env"
    fi
fi

# ── Summary ─────────────────────────────────────────────────────────────────

echo ""
info "Channel switch complete!"
echo ""
echo "  Channel:  ${CHANNEL}"
echo "  Branch:   ${REMOTE}/${BRANCH}"
echo "  Changed:"
[ -f "$CLUSTER_YAML" ] && echo "    .generacy/cluster.yaml           → channel: ${CHANNEL}"
[ -f "$ENV_TEMPLATE" ] && echo "    .devcontainer/generacy/.env.template → GENERACY_CHANNEL=${CHANNEL}"
[ -f "$ENV_FILE" ]     && echo "    .devcontainer/generacy/.env          → GENERACY_CHANNEL=${CHANNEL}"
echo ""
echo "  Next steps:"
echo "    1. Rebuild containers to apply the new channel:"
echo "       cd .devcontainer/generacy && docker compose up -d --build"
echo "    2. Commit the updated configuration files"
echo ""
