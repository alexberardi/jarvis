#!/usr/bin/env bash
# Drive the SOURCE-DEV quickstart on a clean machine — the thing under test.
# Runs ON the VM: `ssh host 'bash -s' -- <ref> < run_quickstart.sh`
#
# This is the path a contributor follows from a bare box, and the path that had
# drifted: every failure the 2026-09 sweep found (jarvis-net ordering, the
# clone-repos.sh set -e abort, unstamped app keys, the missing MQTT broker and
# adapter-callback token) reproduces here and NOWHERE in install-e2e.yml, which
# only ever exercises the installer's prebuilt-image artifact.
#
# Each phase writes a machine-readable marker to $RESULT_DIR so the pytest suite
# can assert on what happened during the run itself, not just the end state.
# Phases are NON-fatal on purpose: a failed `init` must still let the suite run
# and report WHICH invariant broke, rather than aborting the SSH session and
# leaving the workflow to guess.
set -uo pipefail

REF="${1:-main}"
JARVIS_ROOT="${JARVIS_ROOT:-/opt/jarvis}"
RESULT_DIR="${RESULT_DIR:-/opt/jarvis-e2e}"
REPO_BASE="${REPO_BASE:-https://github.com/alexberardi}"

mkdir -p "$RESULT_DIR"
log() { echo "[quickstart] $*"; }
mark() { echo "$2" > "$RESULT_DIR/$1"; }

# ── Phase 1: clone the meta repo ──
# A rented host that cannot reach GitHub is a PROVISIONING failure, not a test
# failure, and must be reported as such. On 2026-09-02 a host answered the clone
# with a non-git response:
#     fatal: could not read Username for 'https://github.com'
#     fatal: expected flush after ref listing
# The old code rm -rf'd the target BEFORE cloning and never checked the result,
# so /opt/jarvis simply did not exist and one network fault cascaded into 23
# unrelated assertion failures. Clone to a temp path, retry, and bail loudly.
log "cloning meta repo @ $REF -> $JARVIS_ROOT"
if [ ! -d "$JARVIS_ROOT/.git" ]; then
  TMP_CLONE="${JARVIS_ROOT}.tmp.$$"
  rm -rf "$TMP_CLONE"
  clone_rc=1
  for attempt in 1 2 3; do
    if GIT_TERMINAL_PROMPT=0 git clone --quiet "$REPO_BASE/jarvis.git" "$TMP_CLONE" 2>"$RESULT_DIR/clone_meta.err"; then
      clone_rc=0; break
    fi
    log "  meta clone attempt $attempt failed; retrying"
    rm -rf "$TMP_CLONE"; sleep 10
  done
  if [ "$clone_rc" -ne 0 ]; then
    mark phase_clone_meta.rc 1
    cp "$RESULT_DIR/clone_meta.err" "$RESULT_DIR/host_unreachable" 2>/dev/null || true
    log "FATAL: this host cannot clone from GitHub — PROVISIONING failure, not a test failure"
    sed 's/^/  /' "$RESULT_DIR/clone_meta.err" 2>/dev/null || true
    exit 42
  fi
  rm -rf "$JARVIS_ROOT"
  mv "$TMP_CLONE" "$JARVIS_ROOT"
fi
cd "$JARVIS_ROOT" || { mark phase_clone_meta.rc 1; log "FATAL: $JARVIS_ROOT missing"; exit 42; }
GIT_TERMINAL_PROMPT=0 git fetch --quiet origin "$REF" && git checkout --quiet FETCH_HEAD
mark phase_clone_meta.rc 0
git rev-parse HEAD > "$RESULT_DIR/meta_sha"

# ── Phase 2: clone the service repos (clone-repos.sh is UNDER TEST) ──
# Run it over HTTPS: CI has no deploy key, and the script's git@ URLs would fail
# for reasons unrelated to what we're testing. We keep its ORDER and CONTENT by
# reading the repo list out of the script itself, so a repo added there is
# picked up here automatically — and a repo that fails still gets recorded
# instead of aborting the run (the script's own `set -e` is the bug).
log "cloning service repos (via clone-repos.sh inventory)"
mapfile -t REPOS < <(grep -oE '"jarvis-[a-z0-9-]+\|' scripts/clone-repos.sh | tr -d '"|')
: > "$RESULT_DIR/clone_failures"
: > "$RESULT_DIR/clone_ok"
for r in "${REPOS[@]}"; do
  if [ -d "$JARVIS_ROOT/$r/.git" ]; then echo "$r" >> "$RESULT_DIR/clone_ok"; continue; fi
  if git clone --quiet --depth 1 "$REPO_BASE/$r.git" "$JARVIS_ROOT/$r" 2>/dev/null; then
    echo "$r" >> "$RESULT_DIR/clone_ok"
  else
    log "  clone FAILED: $r"
    echo "$r" >> "$RESULT_DIR/clone_failures"
  fi
done
cp scripts/clone-repos.sh "$RESULT_DIR/clone-repos.snapshot.sh" 2>/dev/null || true

# Sibling repos referenced as docker BUILD CONTEXTS or bind mounts. These are a
# separate class from the SERVICES registry: jarvis-command-sdk is not a service,
# but jarvis-node-setup's compose declares it as an additional build context, so
# a missing clone fails the build outright —
#   failed to get build context jarvis-command-sdk: stat ...: no such file
# whereas the missing SERVICES repos merely got skipped. Record what is
# referenced vs what exists so the suite can assert on it.
: > "$RESULT_DIR/build_context_missing"
for f in "$JARVIS_ROOT"/jarvis-*/docker-compose*.y*ml; do
  [ -f "$f" ] || continue
  grep -hoE '\.\./jarvis-[a-z0-9-]+' "$f" 2>/dev/null | sed 's|\.\./||'
done | sort -u | while read -r r; do
  [ -d "$JARVIS_ROOT/$r" ] || echo "$r" >> "$RESULT_DIR/build_context_missing"
done

# Also clone anything the CLI's SERVICES registry needs that the script omits.
# Recorded separately so the suite can FAIL on the omission while still bringing
# up a complete stack to test the rest against.
mapfile -t NEEDED < <(sed -n '/^SERVICES=(/,/^)/p' jarvis | grep -oE '"jarvis-[a-z0-9-]+' | tr -d '"')
: > "$RESULT_DIR/clone_omitted_by_script"
for r in "${NEEDED[@]}"; do
  grep -qx "$r" <(printf '%s\n' "${REPOS[@]}") && continue
  echo "$r" >> "$RESULT_DIR/clone_omitted_by_script"
  [ -d "$JARVIS_ROOT/$r/.git" ] && continue
  log "  cloning SERVICES-required repo missing from clone-repos.sh: $r"
  git clone --quiet --depth 1 "$REPO_BASE/$r.git" "$JARVIS_ROOT/$r" 2>/dev/null || true
done

# ── Phase 3: ./jarvis init ──
# THE clean-machine phase. Captures rc + full output; the suite asserts rc==0 and
# greps for the network-ordering failure specifically.
log "running ./jarvis init"
# tee, not a bare redirect: `./jarvis init` can run silently for 10+ minutes
# while it builds venvs and pulls infra images. With output going only to a
# file the SSH channel has NO traffic, the connection gets dropped, and this
# script dies by SIGHUP the moment init returns — losing the exit code and
# every phase after it (observed 2026-09-02: init.log complete, phase_init.rc
# never written). PIPESTATUS keeps the real rc rather than tee's.
( cd "$JARVIS_ROOT" && ./jarvis init < /dev/null ) 2>&1 | tee "$RESULT_DIR/init.log"
INIT_RC=${PIPESTATUS[0]}
mark phase_init.rc "$INIT_RC"
log "  init rc=$INIT_RC"

# ── Phase 4: ./jarvis start --all ──
log "running ./jarvis start --all (source builds — slow)"
( cd "$JARVIS_ROOT" && ./jarvis start --all < /dev/null ) 2>&1 | tee "$RESULT_DIR/start.log"
START_RC=${PIPESTATUS[0]}
mark phase_start.rc "$START_RC"
log "  start rc=$START_RC"

# ── Phase 4.5: settle + warm the model ──
# start --all returns once containers are up, but the LLM proxy loads its GGUF
# lazily/asynchronously — sampling VRAM immediately would race the load and
# report a false "not on GPU". Wait for the proxy to report a ready slot, then
# force one inference so the weights are definitely resident.
log "waiting for llm-proxy to report a ready model slot"
for _ in $(seq 1 60); do
  if curl -sf --max-time 5 http://localhost:7704/health 2>/dev/null | grep -q '"status":"ready"'; then
    log "  model slot ready"; break
  fi
  sleep 10
done
curl -s --max-time 5 http://localhost:7704/health > "$RESULT_DIR/llm_health.json" 2>&1 || true

APP_ID=$(grep -E '^JARVIS_APP_ID=' "$JARVIS_ROOT/jarvis-llm-proxy-api/.env" 2>/dev/null | cut -d= -f2-)
APP_KEY=$(grep -E '^JARVIS_APP_KEY=' "$JARVIS_ROOT/jarvis-llm-proxy-api/.env" 2>/dev/null | cut -d= -f2-)
if [ -n "${APP_KEY:-}" ]; then
  log "warmup inference"
  curl -s --max-time 180 -o "$RESULT_DIR/warmup_inference.json" \
    -X POST http://localhost:7704/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -H "X-Jarvis-App-Id: ${APP_ID}" -H "X-Jarvis-App-Key: ${APP_KEY}" \
    -d '{"model":"live","messages":[{"role":"user","content":"hi"}],"max_tokens":8,"temperature":0}' \
    2>/dev/null || true
fi

# ── Phase 5: snapshot state for the suite ──
docker ps -a --format '{{.Names}}\t{{.Status}}' > "$RESULT_DIR/docker_ps" 2>&1 || true
docker network ls --format '{{.Name}}' > "$RESULT_DIR/docker_networks" 2>&1 || true

# GPU residency evidence. Log-grepping for ggml backend-init markers is NOT
# reliable here: unlike the installer's prebuilt image, the source build routes
# llama.cpp's native logs through the app's logger, so `ggml_cuda_init: found`
# never reaches container stdout even on a perfectly good CUDA build. Measured
# VRAM is the honest signal — this box is rented and runs nothing else, so
# multi-GB resident memory means the model really loaded onto the GPU.
#
# Sampled AFTER a warmup inference so a lazily-loaded model is definitely
# resident by the time we look.
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader \
  > "$RESULT_DIR/gpu_memory" 2>&1 || true
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv \
  > "$RESULT_DIR/gpu_compute_apps" 2>&1 || true
docker logs llm-proxy-model > "$RESULT_DIR/llm_proxy_model.log" 2>&1 || true
cp "$HOME/.jarvis/tokens.env" "$RESULT_DIR/tokens.env" 2>/dev/null || true
# Redact secret VALUES but keep the distinction the assertions need: an app key
# can be empty, a literal placeholder (CHANGE_ME / your-…-here), or a real
# minted secret — three very different failures. Never write the value itself.
python3 - "$JARVIS_ROOT" "$RESULT_DIR" <<'PY' || true
import glob, os, re, sys
root, out = sys.argv[1], sys.argv[2]
SECRET = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)")
PLACEHOLDER = re.compile(r"^(your-.+|CHANGE_ME.*|<.*>|placeholder.*|TBD.*|__SET_ME__)$", re.I)
for env_path in sorted(glob.glob(os.path.join(root, "jarvis-*", ".env"))):
    svc = os.path.basename(os.path.dirname(env_path))
    lines = []
    for raw in open(env_path, errors="replace"):
        raw = raw.rstrip("\n")
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            lines.append(raw); continue
        k, _, v = raw.partition("=")
        if SECRET.search(k):
            if v == "":                  tag = "<empty>"
            elif PLACEHOLDER.match(v):   tag = f"<placeholder:{v[:24]}>"
            else:                        tag = f"<set:len={len(v)}>"
            lines.append(f"{k}={tag}")
        else:
            # Non-secret values (URLs, styles, ports) are the whole point of
            # several assertions — keep them verbatim, but scrub any inline
            # credentials in connection strings.
            lines.append(f"{k}=" + re.sub(r"://([^:/@]+):[^@]+@", r"://\1:<pw>@", v))
    open(os.path.join(out, f"env.{svc}"), "w").write("\n".join(lines) + "\n")
PY
chmod -R a+r "$RESULT_DIR" 2>/dev/null || true

log "DONE init_rc=$INIT_RC start_rc=$START_RC"
