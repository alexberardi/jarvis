---

## K2 provisioning via QR code (MVP)

K2 (the mobile↔node end-to-end encryption key) is provisioned and backed up using a **QR code**. This supports:
- simple household sharing
- recovery if the mobile app is deleted and secure storage is lost
- zero involvement of Command Center in key material

During initial provisioning, the mobile app **creates K2**, securely transmits it to the node over the pairing channel, and then displays a QR code for backup/sharing.

### Clarifications (locked decisions)

The following decisions are intentionally locked to avoid ambiguity during implementation:

1. **K2 transmission channel**
   - K2 is transmitted only during Wi-Fi provisioning while the mobile device is connected to the node’s temporary AP (e.g., `192.168.4.1:8080`).
   - No alternative transport (BLE, Command Center relay, etc.) is used in MVP.

2. **K2 key size**
   - K2 is **exactly 32 bytes** (256 bits) and is used directly as an AES-256-GCM key.

3. **AAD format (QR encryption)**
   - AAD uses a **canonical JSON string**, UTF-8 encoded, with no whitespace and fixed key order:

   ```text
   {"v":1,"node_id":"<node_id>","kid":"<kid>"}
   ```

   - Any deviation (whitespace, reordered keys, alternative serialization) is invalid.

4. **Mobile crypto packaging**
   - The `jarvis-crypto` native module is implemented **inline** within `jarvis-node-mobile` for MVP.
   - Extraction into a shared package is explicitly deferred until a real reuse case exists.

### Pairing channel: how K2 is transmitted (MVP)

K2 is transmitted during the existing node provisioning flow while the phone is connected to the node’s temporary AP (e.g., HTTP to `192.168.4.1:8080`).

- The node MUST be in explicit **pairing mode** (short TTL, user-visible indicator).
- The mobile app generates K2 and sends it to the node via a dedicated provisioning endpoint.
- The node MUST reject attempts to set K2 when not in pairing mode.

Recommended endpoint (illustrative):

- `POST http://192.168.4.1:8080/api/v1/provision/k2`

Request body (plaintext over the local provisioning link):

```json
{
  "node_id": "node-123",
  "kid": "k2-2026-01",
  "k2": "<base64url-encoded 32 bytes>",
  "created_at": "2026-02-01T13:00:00Z"
}
```

Notes:
- Because this link is typically local provisioning HTTP (not TLS), security relies on **physical proximity**, a short pairing window, and user confirmation/indicator.
- The node stores K2 at rest encrypted by K1.

### User choice: plain vs password-protected QR

Users are given an explicit choice during provisioning:

1) **Plain QR (easy sharing / recovery)**
2) **Password-protected QR (safer backup)**

The application must clearly explain the tradeoff.

> Plain QR codes should be treated like a house key: anyone who has it can decrypt this node’s settings snapshots.

### Mobile crypto implementation (required, non-negotiable)

This project intentionally does **not** rely on large third-party JavaScript crypto polyfills or partial implementations.

To ensure long-term correctness, auditability, and consistency across platforms, the mobile app must implement cryptography via a **small, purpose-built native module** (referred to here as `jarvis-crypto`).

This is a deliberate design choice to avoid:
- incomplete AES-GCM implementations (especially missing or incorrect AAD handling)
- fragile third-party maintenance dependencies
- subtle behavior differences between JS polyfills and platform crypto

#### Required primitives

The mobile crypto module MUST expose exactly the following operations:

- `argon2id(password, salt, params) -> keyBytes`
- `aesGcmEncrypt(key, iv, plaintext, aad) -> { ciphertext, tag }`
- `aesGcmDecrypt(key, iv, ciphertext, tag, aad) -> plaintext | error`

Behavioral requirements:
- AES-GCM decryption MUST fail hard on authentication error (wrong key, wrong AAD, wrong tag).
- Silent or partial decrypts are not permitted.

#### Platform expectations

- **iOS:** use platform crypto (e.g., CryptoKit AES.GCM).
- **Android:** use platform crypto (`javax.crypto` with GCM + `updateAAD`).
- **Expo:** requires a development build / dev client. Expo Go support is explicitly out of scope.

This module is security-critical and should remain intentionally small.

---

### QR payload format

The QR code encodes a single base64url-encoded object (JSON or CBOR). The payload is self-describing so the app can detect the mode automatically.

#### Common fields (all modes)

- `v` – payload version (initially `1`)
- `mode` – `plain` or `enc`
- `node_id` – node identifier
- `kid` – key identifier for K2 (supports rotation)
- `created_at` – ISO timestamp (optional)
- `cc_url` – Command Center base URL or instance identifier (optional, UX only)

### Mode A: Plain QR

```json
{
  "v": 1,
  "mode": "plain",
  "node_id": "node-123",
  "kid": "k2-2026-01",
  "k2": "<base64url-encoded key bytes>"
}
```

Behavior:
- App imports K2 directly into secure storage.
- No user prompt is required.

### Mode B: Password-protected QR

```json
{
  "v": 1,
  "mode": "enc",
  "node_id": "node-123",
  "kid": "k2-2026-01",
  "kdf": "argon2id",
  "salt": "<base64url>",
  "params": { "m": 65536, "t": 3, "p": 1 },
  "nonce": "<base64url>",
  "ciphertext": "<base64url>",
  "tag": "<base64url>"
}
```

Encryption steps:

1. Derive an encryption key from the user-provided password using the specified KDF.
2. Encrypt `k2` using **AES-256-GCM**.
3. Use **Associated Data (AAD)** bytes with the canonical JSON format below.

Canonical AAD (UTF-8 bytes, no whitespace, keys in this exact order):

```text
{"v":1,"node_id":"<node_id>","kid":"<kid>"}
```

This prevents QR reuse across nodes or key versions.

Behavior:
- On scan, the app detects `mode="enc"`.
- User is prompted for the password/PIN.
- Decryption failure is treated as incorrect password or corrupted QR.

### Automatic mode detection

The app determines behavior solely from the decoded payload:

- If `mode == "plain"` → import immediately.
- If `mode == "enc"` → prompt for password, then decrypt.

No heuristics or guessing are permitted.

### Key rotation and recovery

- K2 supports rotation via `kid`.
- If a QR is compromised:
  - rotate K2 on the node
  - invalidate old `kid`
  - generate a new QR
  - require re-import on mobile devices

This allows recovery without factory-resetting the node.

---

## MVP defaults (suggested)

- QR‑based K2 provisioning (user‑choice: plain or password‑protected) is mandatory.
- Password‑protected QR must use Argon2id + AES‑256‑GCM with AAD.
- Mobile cryptography must be implemented via a small native module (`jarvis-crypto`).
- Expo development builds are required; Expo Go is explicitly unsupported for security‑critical features.
- MQTT remains signal‑only; all requests must be confirmed with Command Center.

---

## Command Center: settings request & snapshot relay (MVP)

Command Center acts as a **temporary relay and authorization gate** for encrypted node settings. It does **not** persist settings long-term and never sees plaintext.

### Storage semantics

- Command Center is a **temporary store only**.
- All requests and snapshots have a **TTL of 30 minutes**.
- Expired rows are removed via a background cleanup job.
- Each request results in **exactly one snapshot**.

---

### Data model (Command Center)

> **Note:** The MVP implementation uses a simplified schema without `household_id` or `requested_by_user_id`. These fields will be added when jarvis-auth household integration is complete. See "Command Center implementation details" below for the current schema.

#### `node_settings_requests` (full spec)

Tracks an explicit request from a mobile user for a node to publish its current settings.

Fields:
- `request_id` (uuid, pk)
- `node_id`
- `household_id`
- `requested_by_user_id`
- `status` (`pending | fulfilled | failed | expired`)
- `created_at`
- `expires_at` (default: `created_at + 30 minutes`)
- `snapshot_row_id` (nullable)
- `error_code` (nullable)
- `error_message` (nullable)

Notes:
- Requests are immutable except for `status` and result fields.
- Once `fulfilled`, the request cannot transition again.

---

#### `node_settings_snapshots` (full spec)

Stores a single encrypted snapshot uploaded by the node in response to a request.

Fields:
- `row_id` (uuid, pk)
- `request_id` (uuid, unique)
- `node_id`
- `household_id`
- `ciphertext` (base64url)
- `aad` (canonical AAD string)
- `schema_version`
- `revision`
- `created_at`

Notes:
- Ciphertext is opaque to Command Center.
- Snapshot rows are deleted automatically when their request expires.

---

## Request lifecycle & API flow

### High-level flow

```text
Mobile                    Command Center                    Node
  |                            |                             |
  |-- POST /settings/requests ->|                             |
  |                            |-- MQTT settings_request --->|
  |                            |<-- GET /settings/requests/{id} --|
  |                            |<-- PUT /settings/requests/{id} --|
  |<- GET /settings/requests/{id}/result                     |
```

Clarifications:
- MQTT is **signal-only**.
- The node MUST confirm request existence and status with Command Center before responding.
- The node uploads exactly one snapshot per request.

---

### Endpoint responsibilities (illustrative)

#### Mobile → Command Center

- `POST /settings/requests`
  - Requires role: `power_user` or `admin`
  - Creates a new request in `pending` state

- `GET /settings/requests/{request_id}`
  - Poll request status

- `GET /settings/requests/{request_id}/result`
  - Returns ciphertext + metadata once fulfilled

---

#### Node → Command Center

- `GET /settings/requests/{request_id}`
  - Confirms request validity (`pending`, not expired, correct node)

- `PUT /settings/requests/{request_id}`
  - Uploads encrypted snapshot
  - Transitions request to `fulfilled`

---

## Authentication & authorization

### Mobile authentication

- Mobile authenticates to Command Center using **Jarvis Auth JWTs**.
- Household context is provided via `X-Jarvis-Household-Id` header.

### Authorization rules

- Request creation, polling, and snapshot retrieval require:
  - valid household membership
  - role ∈ `{power_user, admin}`

- `member` role may not request or retrieve encrypted settings.

### Node authentication

- Nodes authenticate using their existing node API key / credential.
- Node requests are scoped strictly to their own `node_id`.

---

## Jarvis Auth: Households & Roles

Jarvis Auth provides the household and role infrastructure that Command Center depends on for authorization.

### Data model (Jarvis Auth)

#### `households`

A household groups users and nodes together.

Fields:
- `id` (uuid, pk)
- `name` (string, required)
- `created_at`
- `updated_at`

---

#### `household_memberships`

Links users to households with a specific role.

Fields:
- `id` (int, pk)
- `household_id` (uuid, fk → households)
- `user_id` (int, fk → users)
- `role` (enum: `member | power_user | admin`)
- `created_at`
- `updated_at`

Constraints:
- Unique on `(household_id, user_id)`

Notes:
- A user can belong to multiple households with different roles.
- The user who creates a household automatically becomes its `admin`.

---

#### `node_registrations` (updated)

Nodes now belong to households instead of individual users.

Fields (changed):
- `household_id` (uuid, fk → households, required)
- `registered_by_user_id` (int, fk → users, nullable) — audit trail

Fields (removed):
- `user_id` — replaced by `household_id`

---

### External endpoints (Jarvis Auth)

These endpoints are for mobile/web clients using JWT authentication.

#### Households

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/households` | JWT | Create household (creator → admin) |
| `GET` | `/households` | JWT | List user's households |
| `GET` | `/households/{household_id}` | JWT + member | Get household details |
| `PATCH` | `/households/{household_id}` | JWT + admin | Update household |
| `DELETE` | `/households/{household_id}` | JWT + admin | Delete household |

#### Members

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/households/{household_id}/members` | JWT + member | List members |
| `POST` | `/households/{household_id}/members` | JWT + admin | Add member with role |
| `PATCH` | `/households/{household_id}/members/{user_id}` | JWT + admin | Update member role |
| `DELETE` | `/households/{household_id}/members/{user_id}` | JWT + admin | Remove member |

#### Nodes (household-scoped)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/households/{household_id}/nodes` | JWT + member | List household's nodes |
| `POST` | `/households/{household_id}/nodes` | JWT + power_user/admin | Register node to household |

---

### Internal endpoints (Jarvis Auth)

These endpoints are for service-to-service calls (Command Center → Jarvis Auth) using app-to-app authentication.

#### `POST /internal/validate-household-access`

Validates that a user has the required role in a household.

**Request:**
```json
{
  "user_id": 123,
  "household_id": "uuid",
  "required_role": "power_user"
}
```

**Response (success):**
```json
{
  "valid": true,
  "user_id": 123,
  "household_id": "uuid",
  "role": "admin"
}
```

**Response (failure):**
```json
{
  "valid": false,
  "reason": "User is not a member of this household"
}
```

Notes:
- `required_role` uses role hierarchy: `admin` > `power_user` > `member`
- A user with `admin` role satisfies a `power_user` requirement.

---

#### `POST /internal/validate-node-household`

Validates that a node belongs to a specific household.

**Request:**
```json
{
  "node_id": "node-abc",
  "household_id": "uuid"
}
```

**Response (success):**
```json
{
  "valid": true,
  "node_id": "node-abc",
  "household_id": "uuid"
}
```

**Response (failure):**
```json
{
  "valid": false,
  "reason": "Node does not belong to this household"
}
```

---

## AAD handling

Command Center stores **both structured metadata and canonical AAD**.

- Columns: `node_id`, `schema_version`, `revision`, `request_id`
- Canonical AAD string (stored verbatim):

```text
{"node_id":"<node_id>","schema_version":<n>,"revision":<n>,"request_id":"<uuid>"}
```

Rules:
- CC does **not** construct AAD dynamically.
- Node and mobile MUST use the stored canonical AAD exactly.

---

## MQTT integration

- Command Center is responsible for publishing `settings_request` messages to MQTT.
- Existing Mosquitto infrastructure is assumed available.
- Broker ACLs should restrict:
  - publish → CC only
  - subscribe → nodes only (scoped by node_id)

---

## MVP checkpoints & TDD guidance

Implementation should proceed in checkpoints with tests at each stage:

### Checkpoint 1: Auth foundation (jarvis-auth) ✅

- [x] `Household` and `HouseholdMembership` models + migrations
- [x] Update `NodeRegistration` model (`household_id`, remove `user_id`)
- [x] External endpoints: household CRUD
- [x] External endpoints: member management
- [x] External endpoints: household-scoped node registration
- [x] Internal endpoint: `POST /internal/validate-household-access`
- [x] Internal endpoint: `POST /internal/validate-node-household`
- [x] Role hierarchy enforcement (`admin` > `power_user` > `member`)

**Implementation notes:**
- Migration: `b8c9d0e1f2a3_add_households_and_memberships.py`
- Tests: `tests/test_households.py` (28 tests), `tests/test_node_auth.py` (29 tests)
- Router: `jarvis_auth/app/api/households.py`
- Schemas: `jarvis_auth/app/schemas/household.py`

### Checkpoint 2: Request lifecycle (command-center) ✅

- [x] `settings_requests` model + migrations
- [x] `POST /nodes/{node_id}/settings/requests` — create request
- [x] `GET /nodes/{node_id}/settings/requests/{id}` — poll status
- [x] Expiration logic (5 min TTL default)
- [ ] Background cleanup job (deferred)
- [ ] Validate via jarvis-auth household (deferred — using admin key for MVP)

**Implementation notes:**
- Migration: `alembic/versions/0f1097258abc_add_settings_requests_and_settings_.py`
- Tests: `tests/test_node_settings.py` (24 tests)
- Router: `app/node_settings.py`
- Models: `app/models.py` (`SettingsRequest`, `SettingsSnapshot`)

### Checkpoint 3: Node upload path (command-center) ✅

- [x] `settings_snapshots` model + migrations
- [x] `GET /nodes/{node_id}/settings/requests/{id}` (node auth) — validate request
- [x] `PUT /nodes/{node_id}/settings/requests/{id}/snapshot` (node auth) — upload snapshot
- [x] Status transition to `fulfilled`
- [ ] Validate node ownership via jarvis-auth (deferred — using node API key for MVP)

### Checkpoint 4: Mobile retrieval (command-center) ✅

- [x] `GET /nodes/{node_id}/settings/requests/{id}/result` — return ciphertext + metadata
- [x] AAD fields returned separately for client reconstruction
- [ ] Role enforcement via jarvis-auth (deferred — using admin key for MVP)

### Checkpoint 5: MQTT signal wiring (command-center) ✅

- [x] Publish `settings_request` message on request creation
- [x] MQTT client module (`app/core/mqtt_client.py`)
- [x] Service discovery fallback for broker URL
- [ ] Node confirmation round-trip integration test (manual testing complete)

**MQTT Configuration:**
- Broker URL: `JARVIS_MQTT_BROKER_URL` env var (e.g., `mqtt://localhost:1884`)
- Topic: `jarvis/nodes/{node_id}/settings/request`
- Payload: `{"request_id": "<uuid>", "node_id": "<node_id>"}`

All stages should be driven by unit tests and integration tests before moving to the next checkpoint.

---

## Command Center implementation details

### API endpoints (implemented)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v0/nodes/{node_id}/settings/requests` | Admin key | Create settings request, publish MQTT |
| `GET` | `/api/v0/nodes/{node_id}/settings/requests/{request_id}` | Node API key | Node confirms request exists |
| `PUT` | `/api/v0/nodes/{node_id}/settings/requests/{request_id}/snapshot` | Node API key | Node uploads encrypted snapshot |
| `GET` | `/api/v0/nodes/{node_id}/settings/requests/{request_id}/result` | Admin key | Mobile polls for result |

### Database schema (implemented)

#### `settings_requests`

| Column | Type | Notes |
|--------|------|-------|
| `request_id` | String (PK) | UUIDv4 |
| `node_id` | String (FK) | References `nodes.node_id` |
| `status` | String | `pending`, `fulfilled`, `expired` |
| `created_at` | DateTime | Auto-set |
| `expires_at` | DateTime | Default: `created_at + 5 minutes` |

#### `settings_snapshots`

| Column | Type | Notes |
|--------|------|-------|
| `snapshot_id` | String (PK) | UUIDv4 |
| `node_id` | String (FK) | References `nodes.node_id` |
| `request_id` | String (FK) | References `settings_requests.request_id` |
| `ciphertext` | String | base64url encoded |
| `nonce` | String | base64url encoded (IV) |
| `tag` | String | base64url encoded (auth tag) |
| `aad_node_id` | String | For AAD reconstruction |
| `aad_schema_version` | Integer | For AAD reconstruction |
| `aad_commands_schema_version` | Integer | For AAD reconstruction |
| `aad_revision` | Integer | For AAD reconstruction |
| `aad_request_id` | String | For AAD reconstruction |
| `created_at` | DateTime | Auto-set |

### AAD format (settings snapshots)

Clients construct AAD from the stored fields. Canonical JSON format:

```json
{"node_id":"<node_id>","schema_version":<n>,"commands_schema_version":<n>,"revision":<n>,"request_id":"<uuid>"}
```

### Response formats

#### Create request (201 Created)

```json
{
  "request_id": "67148276-...",
  "node_id": "node-123",
  "status": "pending",
  "created_at": "2026-02-01T20:58:36.123456",
  "expires_at": "2026-02-01T21:03:36.123456"
}
```

#### Poll result — pending (202 Accepted)

```json
{
  "status": "pending",
  "request_id": "67148276-...",
  "message": "Waiting for node response"
}
```

#### Poll result — fulfilled (200 OK)

```json
{
  "status": "fulfilled",
  "request_id": "67148276-...",
  "snapshot": {
    "snapshot_id": "abc123-...",
    "ciphertext": "<base64url>",
    "nonce": "<base64url>",
    "tag": "<base64url>",
    "aad": {
      "node_id": "node-123",
      "schema_version": 1,
      "commands_schema_version": 1,
      "revision": 1,
      "request_id": "67148276-..."
    },
    "created_at": "2026-02-01T20:59:00.000000"
  }
}
```

### Usage example

```bash
# 1. Create a settings request (mobile → CC)
curl -X POST http://localhost:7703/api/v0/nodes/my-node/settings/requests \
  -H "x-api-key: $ADMIN_API_KEY"

# 2. Node receives MQTT message on: jarvis/nodes/my-node/settings/request
# 3. Node confirms request exists
curl http://localhost:7703/api/v0/nodes/my-node/settings/requests/{request_id} \
  -H "x-api-key: $NODE_API_KEY"

# 4. Node uploads encrypted snapshot
curl -X PUT http://localhost:7703/api/v0/nodes/my-node/settings/requests/{request_id}/snapshot \
  -H "x-api-key: $NODE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "ciphertext": "<base64url>",
    "nonce": "<base64url>",
    "tag": "<base64url>",
    "aad_schema_version": 1,
    "aad_commands_schema_version": 1,
    "aad_revision": 1
  }'

# 5. Mobile polls for result
curl http://localhost:7703/api/v0/nodes/my-node/settings/requests/{request_id}/result \
  -H "x-api-key: $ADMIN_API_KEY"
```

### Deferred items (post-MVP)

- [ ] Household-based authorization via jarvis-auth
- [ ] Background cleanup job for expired requests/snapshots
- [ ] Rate limiting on request creation
- [ ] 30-minute TTL (currently 5 minutes for faster testing)
