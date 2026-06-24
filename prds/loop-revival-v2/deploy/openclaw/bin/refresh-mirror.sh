#!/usr/bin/env bash
# Refresh the read-only /home/pi/code/jarvis mirror so the loop agents (engineering,
# qa, coding-agent) read current source + a current CASE_CATALOG.json. Fast-forward
# only; skips any clone with a dirty/diverged tree so it can never clobber local work.
# Installed as jarvis-mirror-refresh.{service,timer} (daily 05:00, before the pipeline).
set -u
MIRROR=/home/pi/code/jarvis
log() { echo "[mirror-refresh] $*"; }

[ -d "$MIRROR" ] || { log "FATAL: $MIRROR missing"; exit 1; }

ok=0; warn=0; skip=0
for d in "$MIRROR"/*/; do
  [ -d "${d}.git" ] || continue
  name=$(basename "$d")
  # Skip if the working tree or index is dirty — never discard local changes.
  if ! git -C "$d" diff --quiet 2>/dev/null || ! git -C "$d" diff --cached --quiet 2>/dev/null; then
    log "SKIP $name (dirty tree)"; skip=$((skip+1)); continue
  fi
  br=$(git -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
  if out=$(git -C "$d" pull --ff-only --quiet 2>&1); then
    ok=$((ok+1))
  else
    log "WARN $name ($br): ${out:-pull failed}"; warn=$((warn+1))
  fi
done
log "done: $ok ok, $warn warn, $skip skipped"

# Surface the CASE catalog freshness explicitly — it is the loop's most load-bearing file.
CAT="$MIRROR/jarvis-integration-tests/tests/CASE_CATALOG.json"
if [ -f "$CAT" ]; then
  log "CASE_CATALOG head: $(git -C "$MIRROR/jarvis-integration-tests" log -1 --format='%h %ci' 2>/dev/null)"
else
  log "WARN CASE_CATALOG.json absent at $CAT"
fi
