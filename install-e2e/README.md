# install-e2e

End-to-end test of the **Jarvis install flow** — it stands up the *exact*
artifact the installer ships (the generated `compose-export` docker-compose) on a
clean GitHub runner and asserts the whole stack actually works.

This exists because every install bug we hit (undefined top-level volume, admin
container with no published port, a `curl` healthcheck on a Node image that has
no curl, admin unable to reach auth → first-boot wizard instead of the
dashboard) was a **generated-artifact** bug that only surfaced by hand on a real
machine. None of the existing per-service CI — nor the `jarvis-integration-tests`
behavior harness — exercises the generated compose. This does.

## How it works

The workflow (`.github/workflows/install-e2e.yml`):

1. checks out this umbrella repo **and** `jarvis-installer`;
2. runs the installer's headless generator
   (`jarvis-installer/scripts/gen-export-compose.mts`) to emit the real
   `compose-export` file (`--gpu none`, all services);
3. validates + `docker compose up`s it with a small CI overlay
   (`docker-compose.ci-override.yaml`);
4. runs this pytest suite against `localhost`.

### The CI overlay

`docker-compose.ci-override.yaml` is the *only* deviation from the real artifact.
A GitHub runner has no GPU and no baked LLM weights, so it repoints
`jarvis-llm-proxy-api` (and its worker) at a cheap cloud model via the **REST
backend** — the same path the `jarvis-llm-proxy-api` behavior lane proved. Every
other service runs the generated config unchanged. Whisper runs its CPU image
(base.en is baked in), so it needs no override.

## Phases

| Phase | Status | What it asserts |
|---|---|---|
| **1 — deployment validity** | ✅ built (`test_deployment.py`) | compose is valid; every container runs + is healthy (catches the curl-healthcheck bug); every HTTP port is published + reachable; admin reports `configured:true`; infra up; no crash loops. config-service `/services` must return **exactly 200 + a JSON list** (tightened from the old loose `200/401/403` — a schema 500 must fail). |
| **1.5 — migrations actually ran** | ✅ built (`test_migrations.py`) | **Keystone for the 2026-06 fleet outage.** For every migrate-set service (registry `migrate: true`: config-service, auth, command-center, llm-proxy, whisper, notifications), asserts the DB is at the alembic HEAD revision **in-container** (`alembic current` == `alembic heads`, both non-empty) — so a service that came up on a stale schema (e.g. config-service skipping migration 005, which 500'd `/services` fleet-wide) **FAILS** here instead of slipping past a shallow `/health` probe. Plus `/services == 200` + JSON list. Services not enabled in the stack are skipped. |
| **1.6 — SYNC-path lane** | ✅ built (`test_sync_compose.py`) | **Closes the actual hole.** The harness only stood up the *installer's export* compose; the bug lived in the *admin SYNC / reconcile* compose. This regenerates that compose via the admin's real `generateCompose` (`gen-sync-compose.mts`) and asserts **statically** that every migrate-set service block carries the `alembic upgrade head` migrate entrypoint (and deferred logs/tts do **not**). The heavier **live** sync bring-up (up the sync compose, re-run the 1.5 assertions) is the opt-in `sync-live` job. |
| **2 — CC behavior routing** | ✅ built (`test_behavior.py`) | `seed.py` creates a user + node and sets `llm.interface=ChatGPTOpenAI`; routes the vendored voice-command corpus (`behavior/*.cc.yaml`) through CC's real native-tool path → cloud model; asserts tool selection + arg shape. **Skips unless `OPENAI_API_KEY` is set.** |
| **3 — real node + MQTT + K2** | ✅ built (`test_node_mqtt_k2.py`) | a real `jarvis-node` container (`docker-compose.node.yaml`) registered by `seed.py` connects to Mosquitto, then a full **K2 provision round-trip** (`POST /nodes/{id}/k2` → MQTT → node saves K2 → ACK in 15s); asserts node `needs_k2` flips. No external secret needed. Net-new — the old harness only *simulated* nodes. |

The corpus (`behavior/corpus.cc.yaml`, `behavior/tools.cc.yaml`) is vendored from
`jarvis-integration-tests/tests/behavior` (the canonical T6b lane) — keep in sync.

## Running locally

Against an already-running stack (ports on `localhost`):

```bash
pip install -r install-e2e/requirements.txt
pytest install-e2e -v
```

To reproduce the full CI bring-up locally:

```bash
# 1. generate the artifact
( cd jarvis-installer && npm ci && \
  npx tsx scripts/gen-export-compose.mts \
    --out "$PWD/../install-e2e/docker-compose.gen.yaml" --gpu none )

# 2. up + test
docker compose -p jarvis \
  -f install-e2e/docker-compose.gen.yaml \
  -f install-e2e/docker-compose.ci-override.yaml up -d
pytest install-e2e -v
```

## Setup notes

- **Secrets:** `OPENAI_API_KEY` (org/repo secret) is only needed for Phase 2.
  Phase 1 runs green without it (the overlay falls back to a placeholder token;
  `/health` doesn't call the model).
- **GHCR access:** the job pulls `ghcr.io/alexberardi/jarvis-*` images. Public
  packages pull without auth; if any are private, grant this repo's Actions
  access to those packages (the `docker/login-action` step uses `GITHUB_TOKEN`).
- The generated file (`docker-compose.gen.yaml`) is a build artifact — it is not
  committed (see `.gitignore`).
