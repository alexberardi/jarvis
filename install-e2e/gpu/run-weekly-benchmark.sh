#!/usr/bin/env bash
# Weekly voice-command model benchmark — runs on the PERSISTENT dev setup
# (laptop command-center → GPU box llm-proxy at 10.0.0.122, models cached), NOT
# the ephemeral Vast install-e2e-gpu lane. The models live permanently on the
# box, so there is no per-run 26GB download to flake on, and it uses the live
# :dev providers (so Mistral/Hermes/Gemma are correct, unlike a stale stable
# image). Scheduled by launchd — see com.jarvis.weekly-benchmark.plist.
#
# Flow: run the 6-model sweep against .122, then publish the results table to the
# jarvis README on origin/main — but ONLY if every model produced a result
# (guard against a partial run overwriting the home page with bad data).
#
#   run-weekly-benchmark.sh                       # full: benchmark + publish
#   run-weekly-benchmark.sh --publish-only F.json # publish an existing result (test)
#   run-weekly-benchmark.sh --no-publish          # benchmark only, don't push
set -uo pipefail

# launchd runs with a minimal environment — set PATH explicitly so python3,
# git, ssh and docker resolve. Adjust if your tool locations differ.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

REPO="${JARVIS_REPO:-/Users/alexanderberardi/jarvis}"
GPUDIR="$REPO/install-e2e/gpu"
OUT="${BENCH_OUT:-/tmp/jarvis-weekly-benchmark.json}"

# launchd's system python3 lacks requests/pyyaml; use the dedicated venv
# (created once: `/usr/bin/python3 -m venv .venv && .venv/bin/pip install
# requests pyyaml`). Override with BENCH_PYTHON if needed.
PYTHON="${BENCH_PYTHON:-$GPUDIR/.venv/bin/python3}"
if ! "$PYTHON" -c "import requests,yaml" 2>/dev/null; then
  echo "ERROR: $PYTHON is missing requests/pyyaml — create the venv (see comment)"; exit 1
fi

PUBLISH=1
MODE="full"
while [ $# -gt 0 ]; do
  case "$1" in
    --publish-only) MODE="publish"; OUT="$2"; shift 2 ;;
    --no-publish) PUBLISH=0; shift ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

echo "===== weekly benchmark $(date -u +%FT%TZ) mode=$MODE ====="

# Resolve OUT to an absolute path — the publish step cd's to the repo, so a
# relative results path would break there.
OUT=$("$PYTHON" -c "import os,sys;print(os.path.abspath(sys.argv[1]))" "$OUT")

if [ "$MODE" = "full" ]; then
  cd "$GPUDIR" || { echo "no $GPUDIR"; exit 1; }
  # Models are cached on .122; --free-vram stops whisper/tts so the 9B fits 12GB.
  if ! "$PYTHON" benchmark_models.py --free-vram --out "$OUT"; then
    echo "ERROR: benchmark run failed"; exit 1
  fi
fi

# Guard: only publish a COMPLETE run (every BENCH_MODELS entry produced a result).
GOT=$("$PYTHON" -c "import json;print(len(json.load(open('$OUT')).get('models',[])))" 2>/dev/null || echo 0)
WANT=$("$PYTHON" "$GPUDIR/bench_models.py" --downloads | wc -l | tr -d ' ')
if [ "${GOT:-0}" -lt "$WANT" ]; then
  echo "WARN: produced ${GOT}/${WANT} models — NOT publishing an incomplete table"; exit 0
fi
echo "benchmark complete: ${GOT}/${WANT} models"

[ "$PUBLISH" -eq 0 ] && { echo "--no-publish: skipping README commit"; exit 0; }

# Publish to the jarvis README on origin/main via a throwaway worktree (local
# main is diverged from origin, so never touch it).
cd "$REPO" || exit 1
git fetch origin -q || { echo "ERROR: git fetch failed"; exit 1; }
WT="$(mktemp -d)/jarvis-readme"
git worktree add -q --detach "$WT" origin/main || { echo "ERROR: worktree add failed"; exit 1; }
trap 'git -C "$REPO" worktree remove --force "$WT" 2>/dev/null' EXIT

if ! "$PYTHON" "$GPUDIR/update_readme.py" "$OUT" --readme "$WT/README.md"; then
  echo "ERROR: update_readme failed — not publishing"; exit 1
fi
if git -C "$WT" diff --quiet README.md; then
  echo "README benchmark section unchanged — nothing to publish"
else
  git -C "$WT" add README.md
  git -C "$WT" commit -q -m "docs(readme): refresh voice-command model benchmark [skip ci]"
  if git -C "$WT" push origin HEAD:main; then
    echo "PUBLISHED refreshed benchmark to origin/main"
  else
    echo "ERROR: push failed (main advanced? auth?) — will retry next week"
  fi
fi
echo "===== done $(date -u +%FT%TZ) ====="
