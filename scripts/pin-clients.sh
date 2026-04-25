#!/bin/bash
# Pin jarvis client libraries to their latest commit hash in all repos.
#
# This ensures Docker layer caching works correctly — when a client library
# is updated, the hash change in requirements/pyproject files busts the cache.
#
# Usage:
#   ./scripts/pin-clients.sh              # pin all clients in all repos
#   ./scripts/pin-clients.sh --dry-run    # show what would change
#   ./scripts/pin-clients.sh --commit     # pin + commit each repo

set -e

JARVIS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

DRY_RUN=false
DO_COMMIT=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --commit) DO_COMMIT=true ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--commit]"
            echo ""
            echo "  --dry-run   Show what would change without modifying files"
            echo "  --commit    Commit changes in each repo after pinning"
            exit 0
            ;;
    esac
done

# Client libraries to pin (parallel arrays — bash 3.x compatible)
CLIENT_REPOS=(  jarvis-config-client  jarvis-log-client  jarvis-settings-client  jarvis-auth-client )
CLIENT_HASHES=( ""                    ""                 ""                      ""                 )

# Resolve latest commit hash for each client
echo -e "${CYAN}Resolving client library commits...${NC}"
for i in "${!CLIENT_REPOS[@]}"; do
    client="${CLIENT_REPOS[$i]}"
    client_dir="${JARVIS_ROOT}/${client}"
    if [[ ! -d "$client_dir/.git" ]]; then
        echo -e "  ${YELLOW}SKIP${NC}  $client (not found at $client_dir)"
        continue
    fi
    hash=$(git -C "$client_dir" rev-parse --short HEAD)
    CLIENT_HASHES[$i]="$hash"
    echo -e "  ${GREEN}OK${NC}    $client → $hash"
done

echo ""

# Files to scan for git+ references
pin_count=0
repo_changes=()

update_file() {
    local file="$1"
    local client="$2"
    local hash="$3"
    local github_url="https://github.com/alexberardi/${client}.git"
    local changed=false

    # Pattern 1: PEP 508 style (requirements.txt / pyproject.toml)
    #   jarvis-foo @ git+https://github.com/.../jarvis-foo.git@main
    #   jarvis-foo @ git+https://github.com/.../jarvis-foo.git@<old-hash>
    #   jarvis-foo @ git+https://github.com/.../jarvis-foo.git  (no ref at all)
    local client_underscored="${client//-/_}"

    if grep -q "git+${github_url}" "$file" 2>/dev/null; then
        # Match with @ref or without any ref
        local current
        current=$(grep "git+${github_url}" "$file" | head -1)

        # Already pinned to this hash?
        if echo "$current" | grep -q "@${hash}"; then
            return
        fi

        if $DRY_RUN; then
            echo -e "  ${YELLOW}WOULD${NC} $file: $client → @$hash"
            pin_count=$((pin_count + 1))
            return
        fi

        # Replace @anything or append @hash if no ref
        if echo "$current" | grep -q "git+${github_url}@"; then
            # Has existing ref — replace it
            sed -i.bak "s|git+${github_url}@[a-zA-Z0-9_.-]*|git+${github_url}@${hash}|g" "$file"
        else
            # No ref — append @hash
            sed -i.bak "s|git+${github_url}|git+${github_url}@${hash}|g" "$file"
        fi
        rm -f "${file}.bak"
        changed=true
    fi

    # Pattern 2: Poetry style (pyproject.toml)
    #   jarvis-foo = { git = "https://github.com/.../jarvis-foo.git" }
    #   jarvis-foo = { git = "https://github.com/.../jarvis-foo.git", branch = "main" }
    #   jarvis-foo = { git = "https://github.com/.../jarvis-foo.git", rev = "<hash>" }
    if grep -q "git = \"${github_url}\"" "$file" 2>/dev/null; then
        local current
        current=$(grep "git = \"${github_url}\"" "$file" | head -1)

        # Already pinned to this hash?
        if echo "$current" | grep -q "rev = \"${hash}\""; then
            return
        fi

        if $DRY_RUN; then
            echo -e "  ${YELLOW}WOULD${NC} $file: $client → rev=$hash (poetry)"
            pin_count=$((pin_count + 1))
            return
        fi

        if echo "$current" | grep -qE '(branch|rev|tag) = '; then
            # Has existing branch/rev/tag — replace with rev
            sed -i.bak -E "s|(git = \"${github_url}\"), *(branch\|rev\|tag) = \"[^\"]*\"|\1, rev = \"${hash}\"|g" "$file"
        else
            # No ref — add rev
            sed -i.bak "s|git = \"${github_url}\"|git = \"${github_url}\", rev = \"${hash}\"|g" "$file"
        fi
        rm -f "${file}.bak"
        changed=true
    fi

    if $changed; then
        echo -e "  ${GREEN}PIN${NC}   $file: $client → @$hash"
        pin_count=$((pin_count + 1))
    fi
}

# Scan all repos
for dir in "${JARVIS_ROOT}"/jarvis-*/; do
    repo=$(basename "$dir")

    # Skip client repos themselves
    [[ " ${CLIENT_REPOS[*]} " == *" $repo "* ]] && continue
    [[ ! -d "$dir/.git" ]] && continue

    repo_had_changes=false

    # Find requirements*.txt and pyproject.toml files
    while IFS= read -r -d '' file; do
        for i in "${!CLIENT_REPOS[@]}"; do
            client="${CLIENT_REPOS[$i]}"
            hash="${CLIENT_HASHES[$i]}"
            [[ -z "$hash" ]] && continue
            before=$pin_count
            update_file "$file" "$client" "$hash"
            [[ $pin_count -gt $before ]] && repo_had_changes=true
        done
    done < <(find "$dir" -maxdepth 1 \( -name "requirements*.txt" -o -name "pyproject.toml" \) -print0 2>/dev/null)

    if $repo_had_changes && $DO_COMMIT && ! $DRY_RUN; then
        cd "$dir"
        git add pyproject.toml 2>/dev/null || true
        git add requirements*.txt 2>/dev/null || true
        if [[ -n "$(git diff --cached --name-only)" ]]; then
            git commit -m "chore: pin client libraries to latest commits

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
            echo -e "  ${GREEN}COMMIT${NC} $repo"
            repo_changes+=("$repo")
        fi
    elif $repo_had_changes; then
        repo_changes+=("$repo")
    fi
done

echo ""
if [[ $pin_count -eq 0 ]]; then
    echo -e "${GREEN}All client libraries already pinned to latest commits.${NC}"
else
    echo -e "${CYAN}Updated $pin_count reference(s) across ${#repo_changes[@]} repo(s).${NC}"
    if $DRY_RUN; then
        echo -e "${YELLOW}Dry run — no files were modified.${NC}"
    elif ! $DO_COMMIT; then
        echo ""
        echo "Changed repos (not committed):"
        for repo in "${repo_changes[@]}"; do
            echo "  $repo"
        done
        echo ""
        echo "Re-run with --commit to commit, or commit manually."
    else
        echo ""
        echo "Committed repos (not pushed):"
        for repo in "${repo_changes[@]}"; do
            echo "  $repo"
        done
        echo ""
        echo "Push with:  for r in ${repo_changes[*]}; do git -C \"\${JARVIS_ROOT}/\$r\" push; done"
    fi
fi
