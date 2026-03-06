# Security & Compliance Roadmap

Enterprise-grade security foundations for future B2B (hospitals, law firms, etc.).
Target frameworks: HIPAA, SOC2 Type II, HITRUST CSF, FedRAMP, ISO 27001, PCI DSS.

**Design principle:** Security must not destroy developer experience. Dev mode stays easy; prod mode is strict. Features are on by default in production, optional/transparent in dev.

---

## Current Security Posture

**Exists:** JWT auth (HS256), app-to-app auth, HouseholdRole (MEMBER/POWER_USER/ADMIN), is_superuser, multi-tenant household_id isolation, centralized logging (Loki+Grafana), soft deletes, bcrypt passwords.

**Missing:** Audit trails, encryption (transit + rest), RBAC enforcement, rate limiting, data classification, network hardening, log retention >7 days.

---

## Phase 1: Audit Logging Foundation

**Why first:** Every compliance framework requires provable audit trails. Without this, no other control is verifiable.

**Compliance:** ALL frameworks (SOC2, HIPAA, ISO 27001, FedRAMP, PCI DSS, HITRUST)

### Tasks

- [ ] **1a. Create `audit_events` table** in jarvis-auth (Alembic migration)
  - Columns: id (UUID), event_type (str, indexed), actor_type (str), actor_id (str), resource_type (str), resource_id (str), action (str), details (JSONB), source_ip (str), household_id (str, indexed), created_at (datetime, indexed)
  - Append-only: DB user has INSERT only (no UPDATE/DELETE)
  - Index on created_at, event_type, actor_id, household_id
  - Files: `jarvis-auth/jarvis_auth/app/db/models.py`, `jarvis-auth/alembic/versions/`

- [ ] **1b. Create `jarvis-audit-client` library** (follows jarvis-log-client pattern)
  - Async batching — fire-and-forget, never blocks requests
  - Graceful degradation: buffer locally + retry if audit service unavailable
  - Simple API: `await audit.log("memory.create", actor_id=user_id, resource_type="memory", resource_id=mem_id)`
  - Zero config: picks up same `JARVIS_APP_ID`/`JARVIS_APP_KEY` env vars
  - Disable via `AUDIT_ENABLED=false` for dev mode
  - New: `jarvis-audit-client/` package

- [ ] **1c. Instrument auth events** in jarvis-auth
  - Login success/failure (with IP, user agent)
  - Registration, logout, token refresh
  - App-to-app validation events
  - Node validation events
  - File: `jarvis-auth/jarvis_auth/app/api/routes/auth.py`

- [ ] **1d. Instrument data access** in jarvis-command-center
  - Memory CRUD (create/read/update/delete)
  - Admin actions (node management, adapter training)
  - Files: `jarvis-command-center/app/services/memory_service.py`, `jarvis-command-center/app/api/admin.py`

- [ ] **1e. Failed login tracking + account lockout**
  - Add `failed_login_count` and `locked_until` columns to User model
  - Lockout after 10 failures (15 min cooldown) — configurable via settings
  - Emit `auth.login_failed` and `auth.account_locked` audit events
  - File: `jarvis-auth/jarvis_auth/app/db/models.py`

- [ ] **1f. Audit query API** (admin-only)
  - `GET /admin/audit-events?event_type=auth.login&since=2026-03-01&actor_id=42`
  - Protected by superadmin role, paginated, filterable
  - New: `jarvis-auth/jarvis_auth/app/api/routes/admin_audit.py`

### Verification
- Login → query audit_events → see `auth.login_success` with IP/timestamp
- 10 bad passwords → account locked → `auth.account_locked` event
- Create memory → `memory.create` event with actor_id and resource_id
- Audit query API returns filtered results

---

## Phase 2: Encryption in Transit (TLS Everywhere)

**Why second:** All inter-service traffic is currently plaintext HTTP. Highest-risk gap.

**Compliance:** HIPAA §164.312(e), PCI DSS Req 4, FedRAMP SC-8, ISO 27001 A.10.1

### Tasks

- [ ] **2a. Auto-generated dev certificates**
  - `./jarvis setup-certs` — generates self-signed CA + per-service certs
  - Stored in `jarvis-data-stores/certs/` (gitignored)
  - For prod: mount real certs or use Let's Encrypt via Caddy
  - New: `scripts/generate-certs.sh`

- [ ] **2b. PostgreSQL TLS**
  - Mount certs into postgres container
  - Add `ssl = on` to postgres config
  - Update DATABASE_URL: `?sslmode=prefer` (dev) / `?sslmode=require` (prod)
  - DX: `sslmode=prefer` means dev works with or without certs
  - Files: all `session.py`, all `.env.example`, `jarvis-data-stores/docker-compose.yml`

- [ ] **2c. Redis TLS + authentication**
  - `redis-server --tls-port 6379 --requirepass $REDIS_PASSWORD`
  - Update connection strings: `rediss://:password@host:6379`
  - DX: `REDIS_TLS=false` flag for dev mode
  - Files: `jarvis-data-stores/docker-compose.yml`, recipe-server config, llm-proxy config

- [ ] **2d. MQTT TLS + authentication**
  - Mosquitto: TLS listener on 8883, password file auth
  - `allow_anonymous false`
  - DX: Dev mosquitto.conf stays simple; prod overlay adds TLS
  - Files: `jarvis-data-stores/mosquitto/config/mosquitto.conf`, jarvis-tts config, jarvis-node-setup config

- [ ] **2e. MinIO TLS + strong credentials**
  - SSE-S3 enabled, certs mounted
  - Replace default minioadmin creds in .env.example
  - Files: `jarvis-data-stores/docker-compose.yml`

- [ ] **2f. Port binding restrictions**
  - Data stores bind to `127.0.0.1` only (PostgreSQL, Redis, MinIO)
  - Only Caddy exposed on `0.0.0.0`
  - Dev override available for tools that need direct access
  - Files: `jarvis-data-stores/docker-compose.yml`, all service docker-compose files

- [ ] **2g. Environment-based enforcement**
  - `JARVIS_ENV=production` requires TLS or refuses to start
  - `JARVIS_ENV=development` (default) uses plaintext with warning
  - `./jarvis up` still works in dev without certs

### Verification
- `openssl s_client -connect localhost:5432` confirms TLS
- Redis rejects unauthenticated connections
- MQTT rejects anonymous clients
- `./jarvis up` still works in dev without certs (with warning)

---

## Phase 3: Encryption at Rest (AES-256)

**Compliance:** HIPAA §164.312(a)(2)(iv), PCI DSS Req 3, FedRAMP SC-28

### Tasks

- [ ] **3a. Volume-level encryption** for all data directories
  - Linux: LUKS/dm-crypt on host volumes
  - macOS: FileVault already covers this (document it)
  - New: `scripts/setup-volume-encryption.sh` — guided setup for Linux

- [ ] **3b. MinIO Server-Side Encryption**
  - Enable SSE-S3 (AES-256) with `MINIO_KMS_SECRET_KEY`
  - Files: `jarvis-data-stores/docker-compose.yml`

- [ ] **3c. Encrypted backups**
  - pg_dump → AES-256 encrypted via GPG
  - New: `scripts/backup-encrypted.sh`

- [ ] **3d. Field-level encryption** (OPTIONAL — decide based on actual PHI requirements)
  - AES-256-GCM for sensitive columns (UserMemory.content, User.email)
  - Searchable via blind index
  - New: `jarvis-auth/jarvis_auth/app/core/crypto.py`

### DX Note
macOS dev machines already use FileVault. Linux prod needs LUKS — provided as a script, not a dev requirement.

---

## Phase 4: RBAC (Role-Based Access Control)

**Compliance:** HIPAA §164.312(a)(1), SOC2 CC6.1, PCI DSS Req 7, FedRAMP AC-2/AC-3

### Tasks

- [ ] **4a. Permission model** (new tables in jarvis-auth)
  - `roles`: id, name, description, is_system
  - `permissions`: id, resource, action, description
  - `role_permissions`: role_id, permission_id (many-to-many)
  - `user_roles`: user_id, role_id, scope_type (global/household), scope_id
  - Files: `jarvis-auth/jarvis_auth/app/db/models.py`, new migration

- [ ] **4b. Default roles** (seeded via migration)
  - superadmin (all permissions, global)
  - household_admin (full CRUD within household)
  - household_member (read + limited write within household)
  - service_account (inter-service communication)
  - node (voice command submission only)

- [ ] **4c. Permission enforcement middleware**
  - Decorator: `@require_permission("memories", "write")`
  - FastAPI dependency: `current_user_with_permission("resource", "action")`
  - Checks JWT role claims — no extra DB lookup per request
  - New: `jarvis-auth/jarvis_auth/app/core/rbac.py`

- [ ] **4d. Migrate existing patterns**
  - Convert `is_superuser` checks → proper role checks
  - Convert `ADMIN_API_KEY` checks → role-based permissions
  - Add `roles` claim to JWT payload
  - Files: `jarvis-auth/jarvis_auth/app/core/security.py`, all endpoint files

- [ ] **4e. Auto-migration for existing installs**
  - Current users get roles based on HouseholdRole
  - Single-household setups feel no difference
  - Permission checks are additive (existing endpoints keep working during rollout)

- [ ] **4f. Admin API for role management**
  - CRUD for roles, permissions, user-role assignments
  - New: `jarvis-auth/jarvis_auth/app/api/routes/admin_roles.py`

### Verification
- Household member can't access admin endpoints
- Cross-household access denied
- Audit log captures permission denials
- Existing installs work after migration without manual intervention

---

## Phase 5: Rate Limiting & Session Management

**Compliance:** SOC2 CC6.6, PCI DSS Req 8.1.6

### Tasks

- [ ] **5a. Rate limiting middleware** (slowapi)
  - Auth endpoints: 10 req/min per IP
  - General API: 100 req/min per IP
  - Admin endpoints: 30 req/min per authenticated user
  - DX: 1000/min in dev mode. Rate limit headers in all responses.
  - Files: all service `main.py`

- [ ] **5b. Session management**
  - Max concurrent sessions per user (configurable, default: 5)
  - Force-logout (revoke all refresh tokens)
  - Session listing endpoint
  - File: `jarvis-auth/jarvis_auth/app/api/routes/auth.py`

### Verification
- Hit login 11 times with wrong password → locked (from Phase 1e)
- Rate limit headers visible in responses
- No impact on normal usage with generous dev limits

---

## Phase 6: Data Classification & PII Handling

**Compliance:** HIPAA PHI, SOC2 confidentiality, ISO 27001 A.8.2, GDPR-ready

### Tasks

- [ ] **6a. Data classification levels**
  - PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED (PHI/PII)
  - Document which data falls into each category
  - New: `docs/data-classification.md`

- [ ] **6b. PII inventory**
  - User.email → CONFIDENTIAL
  - UserMemory.content → RESTRICTED (could contain PHI)
  - Voice transcriptions → RESTRICTED
  - AuditEvent.* → CONFIDENTIAL (retained long-term)

- [ ] **6c. Log sanitization**
  - Middleware to redact RESTRICTED fields before logging
  - `SanitizingLogger` wrapper that masks emails, strips PII
  - Files: `jarvis-log-client/jarvis_log_client/client.py`, new sanitizer.py
  - DX: Automatic — devs don't need to think about it

- [ ] **6d. Data retention policies**
  - Audit logs: 7 years (PostgreSQL, never auto-deleted)
  - Operational logs: 90 days (update Loki retention from 7d → 90d)
  - Voice transcriptions: 30 days (configurable)
  - User data: retained until deletion request
  - Files: `jarvis-logs/loki-config.yaml`, new `scripts/data_retention_worker.py`

- [ ] **6e. Right-to-deletion API** (GDPR-ready)
  - `DELETE /admin/users/{id}/data` — anonymizes user data
  - Removes PII, keeps audit trail with anonymized actor_id
  - Cascades across services
  - New: `jarvis-auth/jarvis_auth/app/api/routes/admin_data.py`

---

## Phase 7: Network Security Hardening

**Compliance:** PCI DSS Req 1-2, FedRAMP SC-7, ISO 27001 A.13

### Tasks

- [ ] **7a. Docker network segmentation**
  - `jarvis-frontend`: Caddy, admin UI
  - `jarvis-backend`: all services
  - `jarvis-data`: PostgreSQL, Redis, MinIO (only backend access)
  - Files: all docker-compose files

- [ ] **7b. CORS hardening**
  - Replace `allow_origins=["*"]` with explicit origins
  - Per-environment config (dev allows localhost, prod is strict)
  - Files: all service `main.py` with CORS middleware

- [ ] **7c. Security headers middleware**
  - HSTS, CSP, X-Frame-Options, X-Content-Type-Options
  - Remove server version headers
  - Files: all service `main.py`

- [ ] **7d. MQTT ACLs**
  - Nodes restricted to their own topics (`jarvis/node/{node_id}/#`)
  - New: `jarvis-data-stores/mosquitto/config/acl.conf`

### DX Note
`docker compose up` still works — networks defined in compose files. Dev CORS allows localhost origins.

---

## Phase 8: Compliance Documentation & Monitoring

**Compliance:** ALL (documentation requirements for actual certification)

### Tasks

- [ ] **8a. Security policy documents**
  - Access Control Policy
  - Encryption Policy
  - Incident Response Plan
  - Data Retention Policy
  - Change Management Policy
  - New: `docs/security/` directory

- [ ] **8b. Compliance mapping document**
  - Matrix: framework → control → implementation → evidence location
  - New: `docs/compliance-matrix.md`

- [ ] **8c. Grafana security dashboards**
  - Failed logins, permission denials, audit event volume, service health
  - Alert rules: >5 failed logins/min, superadmin actions, service down >5min

- [ ] **8d. Automated compliance checks**
  - `scripts/compliance-check.sh` — verifies TLS, encryption, audit, rate limiting, RBAC
  - Run in CI/CD pipeline

- [ ] **8e. JWT upgrade path** (for FedRAMP FIPS 140-2)
  - HS256 → RS256 (asymmetric signing)
  - FIPS 140-2 validated crypto library consideration

---

## Phase Dependencies

```
Phase 1 (Audit Logging) ──────────┐
                                   ├──▶ Phase 4 (RBAC)
Phase 2 (TLS) ───▶ Phase 3 (Rest) │
                                   ├──▶ Phase 5 (Rate Limiting)
                                   │
                                   ├──▶ Phase 6 (Data Classification)
                                   │
Phase 7 (Network) ◀── Phase 2     │
                                   │
Phase 8 (Docs) ◀── ALL ───────────┘
```

Phases 1 and 2 can run in parallel. Everything else depends on at least one of them.

---

## Not Code (Track Separately for B2B Pivot)

- [ ] Business Associate Agreements (BAAs) with cloud providers/customers
- [ ] Employee security training (annual)
- [ ] Background checks for employees with data access
- [ ] Vendor risk assessments for third-party dependencies
- [ ] Annual penetration testing by qualified third party
- [ ] Risk assessment process (documented, reviewed annually)
- [ ] Incident response team (defined roles, escalation paths)
- [ ] Cyber liability insurance
