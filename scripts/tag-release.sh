#!/bin/bash
# Tag one or more repos with a version and push to trigger release builds.
#
# Usage:
#   ./scripts/tag-release.sh v0.1.0 jarvis-admin
#   ./scripts/tag-release.sh v0.1.0 jarvis-admin jarvis-node-setup
#   ./scripts/tag-release.sh v0.1.0 --all
#   ./scripts/tag-release.sh v0.1.0 jarvis-admin --retag   # delete + re-create tag

set -e

JARVIS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ALL_REPOS=(
    jarvis-admin
    jarvis-auth
    jarvis-command-center
    jarvis-command-sdk
    jarvis-config-service
    jarvis-logs
    jarvis-mcp
    jarvis-node-mobile
    jarvis-node-setup
    jarvis-notifications
    jarvis-pantry
    jarvis-recipes-server
    jarvis-settings-server
    jarvis-tts
    jarvis-web
    jarvis-whisper-api
)

usage() {
    echo "Usage: $0 <version> <repo|--all> [--retag]"
    echo ""
    echo "  version    Tag name (e.g., v0.1.0)"
    echo "  repo       One or more repo names (e.g., jarvis-admin)"
    echo "  --all      Tag all repos"
    echo "  --retag    Delete existing tag first, then re-create"
    echo ""
    echo "Available repos:"
    for r in "${ALL_REPOS[@]}"; do echo "  $r"; done
    exit 1
}

[[ $# -lt 2 ]] && usage

VERSION="$1"
shift

RETAG=false
REPOS=()

for arg in "$@"; do
    case "$arg" in
        --retag) RETAG=true ;;
        --all)   REPOS=("${ALL_REPOS[@]}") ;;
        *)       REPOS+=("$arg") ;;
    esac
done

[[ ${#REPOS[@]} -eq 0 ]] && usage

for repo in "${REPOS[@]}"; do
    dir="${JARVIS_ROOT}/${repo}"
    if [[ ! -d "$dir/.git" ]]; then
        echo -e "${RED}SKIP${NC}  $repo (not a git repo at $dir)"
        continue
    fi

    cd "$dir"

    # Check for uncommitted changes
    if [[ -n "$(git status --porcelain)" ]]; then
        echo -e "${YELLOW}WARN${NC}  $repo has uncommitted changes"
    fi

    if $RETAG; then
        # Delete remote tag
        if git ls-remote --tags origin | grep -q "refs/tags/${VERSION}$"; then
            echo -ne "  ${YELLOW}...${NC}   $repo: deleting remote tag ${VERSION}"
            git push origin ":refs/tags/${VERSION}" 2>/dev/null || true
            echo -e "\r  ${GREEN}DEL${NC}   $repo: remote tag ${VERSION}"
        fi
        # Delete local tag
        git tag -d "$VERSION" 2>/dev/null || true
        # Delete GitHub release
        gh release delete "$VERSION" --repo "alexberardi/$repo" --yes 2>/dev/null || true
    fi

    # Check if tag already exists
    if git tag -l "$VERSION" | grep -q "$VERSION"; then
        echo -e "${YELLOW}SKIP${NC}  $repo: tag ${VERSION} already exists (use --retag)"
        continue
    fi

    # For jarvis-admin: update platformVersion in service-registry.json
    if [[ "$repo" == "jarvis-admin" ]]; then
        local semver="${VERSION#v}"
        local reg_file="server/src/data/service-registry.json"
        if [[ -f "$reg_file" ]]; then
            sed -i.bak "s/\"platformVersion\": \"[^\"]*\"/\"platformVersion\": \"${semver}\"/" "$reg_file"
            rm -f "${reg_file}.bak"
            if [[ -n "$(git diff --name-only "$reg_file")" ]]; then
                git add "$reg_file"
                git commit -m "chore: set platformVersion to ${semver}"
                git push origin HEAD 2>/dev/null
            fi
        fi
    fi

    # Tag and push
    echo -ne "  ${YELLOW}...${NC}   $repo: tagging ${VERSION}"
    git tag "$VERSION"
    git push origin "$VERSION" 2>/dev/null
    echo -e "\r  ${GREEN}TAG${NC}   $repo: ${VERSION} pushed — release build triggered"
done

echo ""
echo "Monitor builds:"
for repo in "${REPOS[@]}"; do
    echo "  gh run list --repo alexberardi/$repo --workflow=release.yml --limit 1"
done
