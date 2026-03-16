# PRD: Push Notifications — jarvis-notifications + jarvis-notifications-relay

## Overview

Two-service architecture for push notifications across the Jarvis ecosystem:

| Service | Runs | Purpose |
|---------|------|---------|
| **jarvis-notifications** | Self-hosted (local) | Token storage, auth, dedup, batching, consumer API. All data stays local. |
| **jarvis-notifications-relay** | Cloud (centralized) | Stateless Expo Push proxy. Holds credentials, rate limits, forwards to APNs/FCM. |

Any Jarvis service (command-center, recipes, nodes, future running app) can send push notifications by calling `jarvis-notifications` locally. The relay is **optional** — if not configured, everything works except actual push delivery. Users who want zero cloud dependency simply don't configure the relay URL.

**Ports**: jarvis-notifications = 7711, relay = cloud-hosted (no local port)
**Tier**: 3 (Specialized)
**Database**: PostgreSQL (`jarvis_notifications`) — local service only; relay is stateless

### Why Two Services?

**Security**: Expo Push API requires project credentials (access token tied to the app's bundle ID). If bundled in the self-hosted service, anyone could extract the token and spam push notifications to all Jarvis app users. The relay keeps credentials on infrastructure we control, behind rate limiting.

**Privacy**: The self-hosted service stores all user data (tokens, notification history, preferences) locally. The relay only sees `{push_tokens[], title, body, data}` + a household auth header — no PII stored, stateless, fire-and-forget.

**Optional cloud**: Users who don't want any cloud dependency skip relay configuration. Tokens still register (for later), logs still record, services still call the API. Just no actual push delivered. When they're ready, they add one env var and pushes start flowing.

### Privacy Note

Push notifications require routing through Apple (APNs) or Google (FCM). Expo Push API acts as a thin relay — it doesn't store message content. The jarvis-notifications-relay adds one additional hop but stores nothing. For users who fork the mobile app and build under their own Expo project, they can run the relay themselves or call Expo directly.

### Design Decisions

**1. Household JWT shared secret origin**: The relay operator (us) generates a signing secret and sets it as `RELAY_JWT_SECRET` on the relay. During `./jarvis init`, the user provides this secret (or it's fetched via a one-time registration endpoint), and the CLI generates a household-scoped JWT stored in the local service's env as `RELAY_HOUSEHOLD_JWT`. The relay validates signatures using its secret — no state stored on the relay side.

**2. Dedup key**: Dedup by `(source_service, target_id, title, body, category)` within a 60-second window. `category` is included because the same title/body under different categories (e.g., `alert` vs `system`) are semantically distinct. `data` is excluded — different deep link payloads for the same notification text are still duplicates.

**3. Retry strategy**: In-memory retry queue within the FastAPI process. When relay delivery fails with a transient error (5xx, timeout, connection refused), the notification is queued for retry with exponential backoff (delays: 30s, 60s, 120s, max 3 retries). The queue is an asyncio background task in the lifespan. Queue is lost on restart — acceptable for push notifications (best-effort delivery). No separate process or persistent queue needed.

**4. Cleanup service**: Periodic asyncio task inside the FastAPI lifespan. Runs every `TOKEN_CLEANUP_INTERVAL_HOURS` (default 24h). Prunes `notification_log` entries older than `NOTIFICATION_LOG_RETENTION_DAYS` (default 30) and deactivates tokens that haven't been used in 90 days. Single-process, no cron or external scheduler needed.

**5. User JWT validation**: The mobile app sends user JWTs issued by `jarvis-auth`. The notifications service validates these locally using the shared JWT secret (same pattern as `jarvis-settings-server`). `jarvis-auth-client` handles app-to-app auth for service-to-service calls. No new auth-client functionality needed — user JWT validation is done directly via `PyJWT` with the shared secret from `JARVIS_AUTH_BASE_URL` or `SECRET_KEY`.

**6. Batch notification logging**: One `notification_log` entry per notification in a batch. Each notification in `POST /api/v0/notify/batch` is independent (different targets, different content). The batch endpoint is a convenience wrapper — internally it loops through and processes each notification individually.

**7. Relay deployment target**: **Fly.io**. FastAPI + uvicorn deploys naturally, no execution time limits, supports Python natively, simple scaling. Cloudflare Workers would constrain us (no long-lived connections, 30s CPU limit). A VPS works but Fly.io gives us easy multi-region and auto-scaling for free.

**8. Expo receipt checking**: Skipped entirely in initial implementation. Phase 5 will add receipt polling (check delivery status 15+ minutes after send). No stubs or placeholder code — clean addition later.

---

## Architecture

```
┌─ Self-hosted ─────────────────────────────────────────────────────┐
│                                                                    │
│  jarvis-command-center ───┐                                        │
│  jarvis-recipes-server ───┤                                        │
│  jarvis-node-setup ───────┼──▶ jarvis-notifications (7711)         │
│  future-services ─────────┘        │                               │
│                                    │  PostgreSQL                   │
│                                    │  (device_tokens,              │
│  jarvis-node-mobile ──────────────▶│   notification_log)           │
│  (registers push token via JWT)    │                               │
│                                    │                               │
└────────────────────────────────────┼───────────────────────────────┘
                                     │
                              ┌──────▼──────────────────────┐
                              │  HTTPS (optional)            │
                              │                              │
                    ┌─────────▼────────────────────┐
                    │  jarvis-notifications-relay   │
                    │  (relay.jarvisautomation.io)  │
                    │                               │
                    │  • Validates household JWT     │
                    │  • Rate limits per household   │
                    │  • Holds Expo credentials      │
                    │  • Calls Expo Push API         │
                    │  • Stateless — no DB           │
                    └─────────┬────────────────────┘
                              │
                     ┌────────▼────────┐
                     │  Expo Push API   │
                     │  ▶ APNs / FCM   │
                     └─────────────────┘
```

### Request Flow

1. **Token registration**: Mobile app boots → requests push permission → gets Expo push token → `POST /api/v0/tokens` to local `jarvis-notifications` (JWT auth)
2. **Sending**: Any local service calls `POST /api/v0/notify` on `jarvis-notifications` (app-to-app auth) → service resolves tokens, dedup, logs
3. **Relay delivery**: `jarvis-notifications` batches tokens + payload → `POST` to relay with signed household JWT → relay validates, rate-limits, forwards to Expo Push API
4. **Error handling**: Relay returns per-token results → `jarvis-notifications` deactivates invalid tokens, retries transient failures
5. **No relay configured**: Step 3 is skipped, notification logged as `delivery_skipped`, everything else works

---

## Ecosystem Patterns to Follow

These patterns are established across all Jarvis services and **must** be followed for consistency.

### App Structure
- **`create_app()` function** in `main.py` — returns `FastAPI` instance, enables testability
- **`@app.on_event("startup")`** / `@app.on_event("shutdown")` for lifecycle hooks
- **Startup sequence**: `service_config.init()` → remote logging init (only if `JARVIS_APP_KEY` set) → settings routes (if applicable)
- **`config.py`** using Pydantic `BaseSettings` with `@lru_cache` for `get_settings()`
- **`core/service_config.py`** wrapping `jarvis-config-client` with env var fallbacks + nag warnings

### Database
- **Synchronous SQLAlchemy** with `psycopg2-binary` (no async DB anywhere in the ecosystem)
- **`db.py`** pattern: `get_database_url()` → `create_database_engine()` → `get_session_local()` with graceful fallback if `DATABASE_URL` not set
- **`declarative_base()`** for models; `default=datetime.utcnow` (not `utcnow()`)
- **Alembic** with `MIGRATIONS_DATABASE_URL` → `DATABASE_URL` fallback in `env.py`

### Auth (deps.py)
- **User JWT** (mobile): Validate Bearer token locally via `PyJWT` + shared secret
- **App-to-app** (services): `X-Jarvis-App-Id` + `X-Jarvis-App-Key` → validated against `jarvis-auth /internal/app-ping`
- **Admin** (admin endpoints): `X-Api-Key` header checked against `ADMIN_API_KEY` env var

### Docker
- **Dockerfile**: `python:3.11-slim`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, install `git` for pip git+https deps
- **docker-compose.dev.yaml**: Volume-mount `./app:/app/app` for hot reload + mount client libs from `../jarvis-*-client`, `pip install -q -e` in command, `host.docker.internal` for cross-container communication, `JARVIS_CONFIG_URL_STYLE=dockerized`
- **run.sh**: Support both local (direct uvicorn) and `--docker` modes; source `install-clients.sh` for local mode

### Testing
- **conftest.py**: SQLite in-memory with `StaticPool`, `TestClient`, dependency overrides for `get_db`
- **pytest.ini**: `asyncio_mode = auto`, `addopts = -v --tb=short`
- **Target**: 80%+ coverage

### Logging
- All logging via `jarvis-log-client` → `JarvisLogger`, never `print()`
- Init remote logging only when `JARVIS_APP_KEY` is set (skip silently otherwise)

### Client Libraries
This service needs: `log-client`, `config-client`, `auth-client`, `settings-client`
- In `pyproject.toml`: reference via `git+https://github.com/alexberardi/jarvis-*-client.git@main`
- In `docker-compose.dev.yaml`: mount from `../jarvis-*-client` and `pip install -q -e` in command
- In `run.sh` (local mode): `source install-clients.sh && install_jarvis_clients log-client config-client auth-client settings-client`

---

## Service 1: jarvis-notifications (Self-Hosted)

### Data Model

#### `device_tokens` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Token record ID |
| `user_id` | Integer (indexed) | From jarvis-auth |
| `household_id` | String (indexed) | Household scope |
| `push_token` | String (unique) | Expo push token (`ExponentPushToken[...]`) |
| `device_type` | String | `"ios"` or `"android"` |
| `device_name` | String (nullable) | e.g., "Alex's iPhone" |
| `is_active` | Boolean | Soft-delete on invalid token |
| `last_used_at` | DateTime (nullable) | Last successful delivery |
| `created_at` | DateTime | Registration time |
| `updated_at` | DateTime | Last update |

**Constraints**: Unique on `push_token`. If same token re-registers, update `user_id`/`household_id` (device may have changed user).

#### `notification_log` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Log entry ID |
| `source_service` | String | Calling service app_id (from auth) |
| `target_type` | String | `"user"`, `"household"` |
| `target_id` | String | user_id or household_id |
| `title` | String | Notification title |
| `body` | String | Notification body |
| `data` | JSON (nullable) | Custom payload (deep link, action, etc.) |
| `category` | String (nullable) | Notification category |
| `token_count` | Integer | Tokens targeted |
| `success_count` | Integer | Successful deliveries |
| `failure_count` | Integer | Failed deliveries |
| `delivery_status` | String | `"delivered"`, `"partial"`, `"failed"`, `"skipped"` |
| `created_at` | DateTime | When notification was sent |

**Retention**: 30 days, then pruned by background job.

### API Endpoints

#### Token Management (JWT auth — mobile app calls these)

| Method | Path | Description |
|--------|------|-------------|
| `POST /api/v0/tokens` | Register push token | Body: `{push_token, device_type, device_name?}`. User/household from JWT. Upserts by push_token. |
| `DELETE /api/v0/tokens` | Unregister push token | Body: `{push_token}`. Deactivates token. Called on logout. |
| `GET /api/v0/tokens/me` | List my tokens | Returns active tokens for authenticated user. |

#### Notification Sending (app-to-app auth — services call these)

| Method | Path | Description |
|--------|------|-------------|
| `POST /api/v0/notify` | Send notification | Body: `{target_type, target_id, title, body, data?, priority?, category?}`. Fan out to all matching tokens. |
| `POST /api/v0/notify/batch` | Send batch | Body: `{notifications: [...]}`. Multiple notifications in one call. One `notification_log` entry per notification (not per batch). |

#### Health (unauthenticated)

| Method | Path | Description |
|--------|------|-------------|
| `GET /health` | Health check | Returns status + token count + relay reachability |

#### Admin (admin token auth)

| Method | Path | Description |
|--------|------|-------------|
| `GET /api/v0/admin/stats` | Service stats | Token counts by household, recent send volume, error rates |
| `POST /api/v0/admin/cleanup` | Force cleanup | Trigger token/log pruning |

### Notification Payload

#### Send Request

```json
{
  "target_type": "user",
  "target_id": "42",
  "title": "Research Complete",
  "body": "Your research on espresso machines is ready to view.",
  "data": {
    "type": "deep_research",
    "action": "open_result",
    "result_id": "abc-123"
  },
  "priority": "default",
  "category": "research"
}
```

#### Target Types

| Type | Behavior |
|------|----------|
| `user` | Send to all devices for `target_id` (user_id) |
| `household` | Send to all devices in `target_id` (household_id) |

#### Priority

| Value | Expo Mapping | Use Case |
|-------|-------------|----------|
| `default` | `default` | Most notifications |
| `high` | `high` | Time-sensitive (calendar alerts, urgent) |

#### Categories (for client-side grouping/filtering)

- `alert` — Proactive alerts (calendar, news, weather)
- `research` — Deep research results
- `recipe` — Recipe-related (meal plan ready, timer done)
- `system` — System notifications (update available, node offline)

### Relay Communication

When `RELAY_URL` is configured, `notification_service.py` sends to the relay:

```python
async def _deliver_via_relay(
    tokens: list[str],
    title: str,
    body: str,
    data: dict | None,
    priority: str,
    household_id: str,
) -> list[dict]:
    """Forward notification to centralized relay for Expo Push delivery."""
    relay_url = os.getenv("RELAY_URL")
    if not relay_url:
        logger.info("No RELAY_URL configured, push delivery skipped")
        return [{"status": "skipped", "token": t} for t in tokens]

    payload = {
        "tokens": tokens,
        "title": title,
        "body": body,
        "data": data or {},
        "priority": priority,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{relay_url}/v1/send",
            json=payload,
            headers={
                "Authorization": f"Bearer {household_jwt}",
                "X-Household-Id": household_id,
            },
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
```

### Service Scaffolding

#### Directory Structure

```
jarvis-notifications/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, create_app(), startup/shutdown events, logging
│   ├── config.py                  # Pydantic Settings (BaseSettings) with env var mapping
│   ├── db.py                      # SQLAlchemy engine + session (get_database_url pattern)
│   ├── models.py                  # DeviceToken, NotificationLog (declarative_base)
│   ├── core/
│   │   ├── __init__.py
│   │   └── service_config.py      # jarvis-config-client wrapper with env var fallbacks
│   ├── deps.py                    # User JWT auth (mobile) + app-to-app auth (services)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── tokens.py              # Token registration endpoints
│   │   ├── notify.py              # Send notification endpoints
│   │   └── admin.py               # Admin/stats endpoints
│   └── services/
│       ├── __init__.py
│       ├── notification_service.py # Core send logic + relay forwarding + in-memory retry queue
│       ├── token_service.py        # Token CRUD
│       └── cleanup_service.py      # Periodic asyncio task for token/log pruning
├── alembic/
│   ├── env.py                     # MIGRATIONS_DATABASE_URL → DATABASE_URL fallback
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # SQLite in-memory, TestClient, dependency overrides
│   ├── test_tokens.py
│   ├── test_notify.py
│   ├── test_notification_service.py
│   └── test_cleanup.py
├── .github/workflows/
│   ├── test.yml
│   └── docker-build-push.yml
├── .env.example
├── .gitignore
├── alembic.ini
├── CLAUDE.md
├── Dockerfile
├── docker-compose.dev.yaml
├── docker-compose.prod.yaml
├── pyproject.toml
├── pytest.ini
└── run.sh                         # Supports both local and --docker modes, sources install-clients.sh
```

#### Dependencies (pyproject.toml)

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "jarvis-notifications"
version = "0.1.0"
description = "Push notification service for the Jarvis ecosystem"
requires-python = ">=3.11"
dependencies = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "httpx",
    "python-dotenv",
    "pydantic-settings",
    "PyJWT",
    "sqlalchemy>=2.0",
    "alembic",
    "psycopg2-binary",
    "jarvis-log-client @ git+https://github.com/alexberardi/jarvis-log-client.git@main",
    "jarvis-config-client @ git+https://github.com/alexberardi/jarvis-config-client.git@main",
    "jarvis-auth-client @ git+https://github.com/alexberardi/jarvis-auth-client.git@main",
    "jarvis-settings-client @ git+https://github.com/alexberardi/jarvis-settings-client.git@main",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-httpx>=0.21.0",
    "pytest-cov>=4.1.0",
]

[tool.setuptools.packages.find]
include = ["app*"]
```

#### Environment Variables (.env.example)

```bash
# =============================================================================
# jarvis-notifications — Push notification service (self-hosted)
# =============================================================================
# Port: 7711
# Run: ./run.sh or ./run.sh --docker

# ── SERVER ──────────────────────────────────────────────────────────────────
NOTIFICATIONS_PORT=7711

# ── DATABASE ────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/jarvis_notifications
MIGRATIONS_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/jarvis_notifications

# ── AUTHENTICATION ──────────────────────────────────────────────────────────
JARVIS_APP_ID=jarvis-notifications
JARVIS_APP_KEY=CHANGE_ME
ADMIN_API_KEY=change-me-to-something-secure

# ── JWT (for validating mobile user tokens) ────────────────────────────────
# Must match jarvis-auth's SECRET_KEY
AUTH_SECRET_KEY=change-me
AUTH_ALGORITHM=HS256

# ── SERVICE DISCOVERY ───────────────────────────────────────────────────────
JARVIS_CONFIG_URL=http://localhost:7700
JARVIS_AUTH_BASE_URL=http://localhost:7701

# ── LOGGING (via jarvis-log-client) ─────────────────────────────────────────
JARVIS_LOG_CONSOLE_LEVEL=INFO
JARVIS_LOG_REMOTE_LEVEL=DEBUG

# ── RELAY (optional — omit for no push delivery) ───────────────────────────
# RELAY_URL=https://relay.jarvisautomation.io
# RELAY_HOUSEHOLD_JWT=eyJhbG...  (auto-populated by ./jarvis init)

# ── CLEANUP ─────────────────────────────────────────────────────────────────
NOTIFICATION_LOG_RETENTION_DAYS=30
TOKEN_CLEANUP_INTERVAL_HOURS=24
```

---

## Service 2: jarvis-notifications-relay (Cloud)

### Purpose

Stateless proxy that holds Expo Push API credentials and rate-limits per household. Deployed on **Fly.io** behind `relay.jarvisautomation.io`. Fly.io is preferred over Cloudflare Workers (no 30s execution limit, persistent connections for Expo API batches) and over a raw VPS (managed deploys, auto-restart, easy scaling).

### Why Stateless?

- No database, no token storage, no message persistence
- Horizontally scalable (any instance can handle any request)
- Simple to deploy, simple to audit
- If it goes down, self-hosted services log `delivery_skipped` and retry later

### API

#### `POST /v1/register` — Register a household

**Auth**: None (open endpoint — rate-limited to prevent abuse). Returns a signed JWT.

**Request**:
```json
{"household_id": "abc-123"}
```

**Response**:
```json
{"token": "eyJhbG...signed_jwt", "expires_at": "2027-03-13T00:00:00Z"}
```

The relay signs the JWT with its private key. The JWT is long-lived (1 year) and can be renewed by calling register again. The `./jarvis init` script calls this endpoint automatically when `RELAY_URL` is configured.

**Rate limit**: 10 registrations per IP per hour (prevents enumeration).

#### `POST /v1/send` — Forward push notification

**Auth**: Household JWT in `Authorization: Bearer` header. The relay validates the JWT signature using a shared secret (or public key) to confirm the request comes from a legitimate Jarvis installation.

**Request**:
```json
{
  "tokens": ["ExponentPushToken[abc123]", "ExponentPushToken[def456]"],
  "title": "Research Complete",
  "body": "Your espresso machine research is ready.",
  "data": {"type": "deep_research", "result_id": "abc-123"},
  "priority": "default"
}
```

**Response**:
```json
{
  "results": [
    {"token": "ExponentPushToken[abc123]", "status": "ok", "ticket_id": "xxx"},
    {"token": "ExponentPushToken[def456]", "status": "error", "error": "DeviceNotRegistered"}
  ]
}
```

#### `GET /health` — Health check

Returns relay status + Expo API reachability.

### Rate Limiting

| Limit | Value | Scope |
|-------|-------|-------|
| Per household | 100 notifications/hour | Prevents abuse from any single installation |
| Per device token | 20 notifications/hour | Prevents spamming a single device |
| Burst | 10 notifications/second | Smooth traffic |
| Batch size | 100 tokens per request | Matches Expo's batch limit |

Rate limit state can be in-memory (Redis if multi-instance, or in-process for single instance).

Returns `429 Too Many Requests` with `Retry-After` header when exceeded.

### Abuse Detection & Alerting

Rate limiting is the primary defense. The relay tracks consecutive rate-limit hits per household:

| Consecutive 429s | Action |
|-------------------|--------|
| 1-2 | Normal — return 429, log at INFO level |
| 3 | **Alert**: Log at WARN, send admin notification (email/Slack webhook) |
| 5 | **Escalate**: Log at ERROR, flag household for review |
| 10+ | **Suspend**: Temporarily block household (1 hour cooldown), log at CRITICAL |

**Implementation**: In-memory counter per household_id, resets after 1 hour of no 429s. Suspension is also in-memory (lost on restart, which is fine — restart clears the abuse state).

```python
@dataclass
class HouseholdRateState:
    consecutive_429s: int = 0
    last_429_at: datetime | None = None
    suspended_until: datetime | None = None
```

**Admin alert channel**: Configurable via `ALERT_WEBHOOK_URL` env var on the relay (Slack incoming webhook, Discord, or a simple email relay). When a household hits 3 consecutive 429s:

```json
{
  "text": "⚠️ Household abc-123 hit rate limit 3x consecutively. Possible abuse or misconfigured client.",
  "household_id": "abc-123",
  "consecutive_hits": 3,
  "timestamp": "2026-03-13T14:30:00Z"
}
```

**Why not permanent bans?** A misconfigured self-hosted instance (e.g., a runaway agent loop) is more likely than malicious abuse. Temporary suspension + alert lets us investigate before taking permanent action. The 1-hour cooldown is usually enough for the user to notice and fix their setup.

### Household Authentication

The relay uses asymmetric JWT signing. The relay owns a private key and signs household JWTs during a one-time registration. It validates incoming requests with its own public key — fully stateless after registration.

**Registration flow** (one-time, during `./jarvis init`):

```
./jarvis init
  │
  ├─ Detects RELAY_URL is configured in jarvis-notifications .env
  │
  └─▶ POST https://relay.jarvisautomation.io/v1/register
      Body: {"household_id": "abc-123"}
      │
      ◀── Response: {"token": "eyJhbG...signed_jwt"}
          │
          └─▶ Stored in jarvis-notifications .env as RELAY_HOUSEHOLD_JWT
```

**JWT claims**: `{household_id, iat, exp}` — long-lived (1 year), renewable.

**Relay validation**: On each `/v1/send` request, relay verifies the JWT signature using its own public key. Extracts `household_id` for rate limiting. No database lookup needed.

**Key rotation**: If the relay's signing key is compromised, rotate the key pair and have all households re-register on next `./jarvis init`. Individual household JWTs can be blacklisted by household_id in an in-memory set if needed (lightweight, still no DB).

**Forked builds**: Users running their own relay generate their own key pair.

### Expo Push Integration

```python
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

async def forward_to_expo(
    tokens: list[str],
    title: str,
    body: str,
    data: dict,
    priority: str,
    expo_access_token: str,
) -> list[dict]:
    """Forward to Expo Push API with credentials."""
    messages = [
        {
            "to": token,
            "title": title,
            "body": body,
            "sound": "default",
            "priority": priority,
            "data": data,
        }
        for token in tokens
    ]

    results = []
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(0, len(messages), 100):
            batch = messages[i:i+100]
            resp = await client.post(
                EXPO_PUSH_URL,
                json=batch,
                headers={"Authorization": f"Bearer {expo_access_token}"},
            )
            resp.raise_for_status()
            results.extend(resp.json().get("data", []))

    return results
```

### Error Handling (Relay → Self-Hosted)

| Expo Error | Relay Action | Self-hosted Action |
|------------|-------------|-------------------|
| `DeviceNotRegistered` | Return in results | Deactivate token |
| `MessageTooBig` | Return error | Log, truncate body |
| `MessageRateExceeded` | Retry 1x with backoff | In-memory retry queue (see below) |
| `InvalidCredentials` | Return 500 + alert | Log critical |
| Transient (5xx) | Retry up to 3x | In-memory retry queue (see below) |

**Retry strategy**: Transient failures and relay unavailability queue notifications in an in-memory retry queue with exponential backoff (1s → 5s → 30s, max 3 attempts over ~5 minutes). Not persistent — if the service restarts, pending retries are lost. This is acceptable for best-effort push delivery. Persistent retry queue is Phase 5 polish.

### Scaffolding

The relay is intentionally minimal:

```
jarvis-notifications-relay/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, single route
│   ├── auth.py              # Household JWT validation
│   ├── rate_limiter.py      # In-memory rate limiting + abuse detection
│   ├── alert_service.py     # Webhook alerts for abuse/escalation
│   └── expo_client.py       # Expo Push API wrapper
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_send.py
│   ├── test_auth.py
│   ├── test_rate_limiter.py
│   └── test_alert_service.py
├── .github/workflows/
│   ├── test.yml
│   └── deploy.yml           # Deploy to Fly.io on push to main
├── .env.example
├── .gitignore
├── CLAUDE.md
├── Dockerfile
├── fly.toml                 # Fly.io deployment config
├── pyproject.toml
├── pytest.ini
└── run.sh
```

#### Dependencies (pyproject.toml)

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "jarvis-notifications-relay"
version = "0.1.0"
description = "Centralized push notification relay for Jarvis (Expo Push API proxy)"
requires-python = ">=3.11"
dependencies = [
    "fastapi",
    "uvicorn",
    "httpx",
    "pydantic",
    "python-dotenv",
    "PyJWT",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-httpx>=0.21.0",
]

[tool.setuptools.packages.find]
include = ["app*"]
```

#### Environment Variables (.env.example)

```bash
# =============================================================================
# jarvis-notifications-relay — Centralized Expo Push proxy
# =============================================================================
# Hosted at: relay.jarvisautomation.io

# ── EXPO CREDENTIALS ────────────────────────────────────────────────────────
EXPO_ACCESS_TOKEN=your_expo_access_token_here

# ── HOUSEHOLD AUTH (asymmetric) ─────────────────────────────────────────────
# Private key signs JWTs during /v1/register. Public key validates on /v1/send.
RELAY_JWT_PRIVATE_KEY_PATH=/app/keys/relay_private.pem
RELAY_JWT_PUBLIC_KEY_PATH=/app/keys/relay_public.pem

# ── RATE LIMITING ───────────────────────────────────────────────────────────
RATE_LIMIT_PER_HOUSEHOLD_PER_HOUR=100
RATE_LIMIT_PER_TOKEN_PER_HOUR=20
RATE_LIMIT_BURST_PER_SECOND=10

# ── ABUSE ALERTING ──────────────────────────────────────────────────────────
# Slack/Discord webhook for admin alerts when households hit rate limits repeatedly
# ALERT_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx
CONSECUTIVE_429_ALERT_THRESHOLD=3
CONSECUTIVE_429_SUSPEND_THRESHOLD=10
SUSPENSION_COOLDOWN_HOURS=1
```

---

## Mobile Integration (jarvis-node-mobile)

### Package Changes

```bash
npx expo install expo-notifications expo-device expo-constants
```

### app.json Changes

```json
{
  "expo": {
    "plugins": [
      "expo-camera",
      "expo-secure-store",
      "expo-web-browser",
      ["expo-notifications", {
        "icon": "./assets/notification-icon.png",
        "color": "#1a73e8"
      }]
    ],
    "ios": {
      "infoPlist": {
        "UIBackgroundModes": ["remote-notification"]
      }
    },
    "android": {
      "useNextNotificationsApi": true
    }
  }
}
```

### New Files

| File | Purpose |
|------|---------|
| `src/api/notificationApi.ts` | API calls to local jarvis-notifications (register/unregister tokens) |
| `src/notifications/useNotificationSetup.ts` | Hook: request permission, get Expo token, register with backend, handle incoming notifications |

### Integration Point

In `App.tsx`, after `AuthProvider` mounts:
- Call `useNotificationSetup()` which:
  1. Checks if physical device (not simulator — skip gracefully)
  2. Requests notification permission
  3. Gets Expo push token
  4. Registers token with local `jarvis-notifications` (using JWT from auth context)
  5. Sets up notification received/response handlers (deep link routing, etc.)
- On logout: call `DELETE /api/v0/tokens` to unregister

### Token Refresh

Expo push tokens can change (app reinstall, OS update). The hook should:
- Store current token in `expo-secure-store`
- On each app launch, compare current token to stored
- If different, re-register with backend

---

## Ecosystem Registration

### jarvis-notifications (self-hosted)

Add to `jarvis-config-service/app/known_services.py`:
```python
{"name": "jarvis-notifications", "port": 7711, "description": "Push notifications", "health_path": "/health"}
```

Add to `./jarvis` CLI:
```bash
# SERVICES array
"jarvis-notifications|7711|3|docker|/health"

# TEST_REGISTRY array
"jarvis-notifications|pytest||app"

# DB_ENTRIES array
"jarvis-notifications|DB_NAME_NOTIFICATIONS|jarvis_notifications|DATABASE_URL,MIGRATIONS_DATABASE_URL"
```

App client registration in jarvis-auth is handled automatically by `_auto_register` during `./jarvis init`.

### jarvis-notifications-relay (cloud)

Not registered in config-service (it's not a local service). The self-hosted service discovers it via `RELAY_URL` env var. The relay is deployed independently to cloud infrastructure.

---

## Integration Checklist

### Phase 1: jarvis-notifications (self-hosted service)

- [ ] Create GitHub repo `alexberardi/jarvis-notifications`
- [ ] Scaffold directory structure
- [ ] `app/main.py` — `create_app()`, startup/shutdown events, service_config init, jarvis-log-client logging
- [ ] `app/config.py` — Pydantic `BaseSettings` with `@lru_cache` `get_settings()`
- [ ] `app/models.py` — DeviceToken + NotificationLog (SQLAlchemy declarative_base)
- [ ] `app/db.py` — `get_database_url()` + `create_database_engine()` + `get_session_local()` pattern
- [ ] `app/core/service_config.py` — jarvis-config-client wrapper with env var fallbacks
- [ ] `app/deps.py` — User JWT auth via PyJWT + shared secret (mobile), app-to-app auth via jarvis-auth `/internal/app-ping` (services), admin auth via `ADMIN_API_KEY`
- [ ] `app/api/tokens.py` — register/unregister/list
- [ ] `app/api/notify.py` — send/batch (forwards to relay if configured)
- [ ] `app/api/admin.py` — stats/cleanup
- [ ] `app/services/notification_service.py` — core send logic + relay forwarding + graceful skip
- [ ] `app/services/token_service.py` — token CRUD
- [ ] `app/services/cleanup_service.py` — background token/log pruning
- [ ] Alembic migration for initial tables
- [ ] Tests (80%+ coverage)
- [ ] `Dockerfile`, `docker-compose.dev.yaml`, `docker-compose.prod.yaml`
- [ ] `run.sh` (local + docker modes, install-clients.sh pattern)
- [ ] `.env.example`, `CLAUDE.md`, `.gitignore`, `pyproject.toml`, `pytest.ini`
- [ ] `.github/workflows/test.yml` + `docker-build-push.yml`
- [ ] Register in config-service `known_services.py`
- [ ] Register in `./jarvis` CLI (SERVICES, TEST_REGISTRY, DB_ENTRIES)

### Phase 2: jarvis-notifications-relay (cloud service)

- [ ] Create GitHub repo `alexberardi/jarvis-notifications-relay`
- [ ] Scaffold minimal directory structure
- [ ] `app/main.py` — FastAPI with single `/v1/send` route + health
- [ ] `app/auth.py` — household JWT validation
- [ ] `app/rate_limiter.py` — in-memory rate limiting per household/token
- [ ] `app/expo_client.py` — Expo Push API wrapper with retry + error mapping
- [ ] Tests
- [ ] `Dockerfile`
- [ ] `.github/workflows/test.yml` + `deploy.yml` (cloud deploy)
- [ ] `.env.example`, `CLAUDE.md`
- [ ] Deploy to cloud infrastructure (Fly.io / Cloudflare / VPS)
- [ ] Set up `relay.jarvisautomation.io` DNS

### Phase 3: Mobile Integration

- [ ] Install `expo-notifications`, `expo-device`, `expo-constants`
- [ ] Update `app.json` with notification plugin + iOS background modes
- [ ] Create `src/api/notificationApi.ts`
- [ ] Create `src/notifications/useNotificationSetup.ts`
- [ ] Wire hook into `App.tsx` (after AuthProvider)
- [ ] Add logout token cleanup
- [ ] Test on physical device (simulator doesn't support push)

### Phase 4: Wire Consumers

- [ ] `jarvis-node-setup`: Agent scheduler sends push for high-priority alerts
- [ ] `jarvis-command-center`: (future) Send push when deep research completes
- [ ] `jarvis-recipes-server`: (future) Send push for meal plan reminders

### Phase 5: Polish

- [ ] Expo receipt checking (confirm delivery after 15+ min)
- [ ] Notification preferences per user (mute categories)
- [ ] Analytics dashboard (send volume, error rates)
- [ ] Rate limiting per service on self-hosted side

### Documentation

- [ ] Update root `CLAUDE.md` service table with jarvis-notifications
- [ ] Update dependency graph
- [ ] Update port registry
- [ ] Add to architecture diagram

---

## Testing Strategy

### jarvis-notifications (self-hosted)

| File | Tests |
|------|-------|
| `test_tokens.py` | Register, unregister, upsert, list, JWT auth required, invalid JWT rejected |
| `test_notify.py` | Send to user, send to household, batch, missing target, app-to-app auth required |
| `test_notification_service.py` | Relay forwarding, relay skip when unconfigured, error handling from relay, dedup |
| `test_cleanup.py` | Prune inactive tokens, prune old logs, retention window |

### jarvis-notifications-relay (cloud)

| File | Tests |
|------|-------|
| `test_send.py` | Forward to Expo, batch >100, error mapping, response format |
| `test_auth.py` | Valid household JWT, expired JWT, invalid signature, missing header |
| `test_rate_limiter.py` | Per-household limits, per-token limits, burst limits, 429 response, consecutive counter reset after cooldown |
| `test_alert_service.py` | Webhook fires at threshold (3x), escalation at 5x, suspension at 10x, cooldown resets state, webhook failure doesn't crash relay |

### Mobile

- Permission denied → graceful degradation (no crash, no token registration)
- Token refresh on app update
- Notification received while app foregrounded vs backgrounded
- Deep link routing from notification tap

### Integration

- Register token → send notification → verify log entry (self-hosted only, relay mocked)
- Invalid token → send → relay returns error → token deactivated
- Multiple devices per user → verify fan-out
- No relay configured → verify `delivery_skipped` status in log

---

## Edge Cases

1. **Simulator**: `expo-notifications` returns null token on simulator. Skip registration gracefully.
2. **Permission denied**: User declines push permission. Don't crash, don't pester. Store nothing.
3. **Token rotation**: Expo tokens can change. Compare on each launch, re-register if different.
4. **Multiple devices**: User has phone + tablet. Fan out to all active tokens.
5. **Stale tokens**: App uninstalled but token still in DB. Relay returns `DeviceNotRegistered` → self-hosted deactivates.
6. **Service restart**: Tokens in PostgreSQL survive restarts. No in-memory state (self-hosted).
7. **Relay outage**: Self-hosted logs `delivery_failed`, retries on next send. Best-effort delivery.
8. **No relay configured**: Self-hosted logs `delivery_skipped`. Tokens still register. Everything else works.
9. **Duplicate notifications**: Dedup by `(source_service, target_id, title, body, category)` within 60-second window (self-hosted). `data` is excluded — different deep link payloads for the same notification text are still duplicates.
10. **High volume**: Batch sends (100 per Expo request). Rate limit at relay per household.
11. **Auth service down**: Token registration fails (can't validate JWT). Mobile retries on next app launch.
12. **Forked builds**: Users who build their own mobile app supply their own Expo credentials and can either use the public relay, run their own relay, or call Expo directly from self-hosted.
13. **Household JWT compromise**: Rotate the shared secret, re-sign JWTs during next `./jarvis init`. Compromised household can only spam their own rate-limited quota.
