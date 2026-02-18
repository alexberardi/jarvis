# Jarvis Node Mobile - Sync Document

Cross-machine coordination between Ubuntu (backend) and Mac (mobile).

## Latest Sync: 2026-02-01

### Current Status: MOBILE IMPLEMENTATION COMPLETE

Backend provisioning API and mobile app both implemented. Ready for integration testing.

---

## Backend Status (Ubuntu)

### Completed

| Component | Location | Status |
|-----------|----------|--------|
| Provisioning API | `jarvis-node-setup/provisioning/` | ✅ COMPLETE |
| Provisioning models | `provisioning/models.py` | ✅ COMPLETE |
| WiFi manager | `provisioning/wifi_manager.py` | ✅ COMPLETE |
| State machine | `provisioning/state_machine.py` | ✅ COMPLETE |
| Startup detection | `provisioning/startup.py` | ✅ COMPLETE |
| API endpoints | `provisioning/api.py` | ✅ COMPLETE |
| Entry point | `scripts/run_provisioning.py` | ✅ COMPLETE |
| Unit tests | `tests/test_provisioning/` | ✅ 85 tests passing |

### API Endpoints (Implemented)

All endpoints on port 8080 (configurable via `JARVIS_PROVISIONING_PORT`):

```
GET  /api/v1/info           # Node info (id, firmware, mac, capabilities, state)
GET  /api/v1/scan-networks  # Available WiFi networks
POST /api/v1/provision      # Send WiFi credentials + room + command center URL
GET  /api/v1/status         # Provisioning progress
```

### Running the Simulator

```bash
cd jarvis-node-setup
source venv/bin/activate

# Start provisioning server in simulation mode
JARVIS_SIMULATE_PROVISIONING=true CONFIG_PATH=config.json python scripts/run_provisioning.py
```

Server will start on `http://0.0.0.0:8080`

### Ubuntu Machine IP

For Mac Claude to connect: `192.168.1.XXX` (fill in your actual IP)

To find:
```bash
ip addr show | grep "inet 192"
# or
hostname -I
```

---

## Mobile Status (Mac)

### Completed

| Component | Location | Status |
|-----------|----------|--------|
| Expo app setup | `jarvis-node-mobile/` | ✅ COMPLETE |
| Navigation structure | `src/navigation/` | ✅ COMPLETE |
| Theme system (dark mode) | `src/theme/` | ✅ COMPLETE |
| Provisioning flow | `src/screens/Provisioning/` | ✅ COMPLETE |
| jarvis-crypto native module | `modules/jarvis-crypto/` | ✅ COMPLETE |
| K2 key service | `src/services/k2Service.ts` | ✅ COMPLETE |
| QR payload service | `src/services/qrPayloadService.ts` | ✅ COMPLETE |
| QR import service | `src/services/qrImportService.ts` | ✅ COMPLETE |
| QR backup component | `src/components/K2QRCode.tsx` | ✅ COMPLETE |
| Import key screen | `src/screens/ImportKey/` | ✅ COMPLETE |

### jarvis-crypto Native Module

Expo native module implementing cryptographic primitives:

**iOS** (`modules/jarvis-crypto/ios/`):
- CryptoKit for AES-256-GCM encryption/decryption
- Argon2id via C reference implementation (public domain)
- SecRandomCopyBytes for secure random generation

**Android** (`modules/jarvis-crypto/android/`):
- javax.crypto with AES/GCM/NoPadding
- org.signal:argon2 library for Argon2id
- SecureRandom for random generation

**Exported Functions:**
```typescript
argon2id(password: string, salt: string, params: Argon2Params): Promise<string>
aesGcmEncrypt(key: string, iv: string, plaintext: string, aad: string): Promise<EncryptResult>
aesGcmDecrypt(key: string, iv: string, ciphertext: string, tag: string, aad: string): Promise<string>
randomBytes(length: number): Promise<string>
```

### K2 Provisioning Flow

1. Mobile generates K2 (256-bit key) via `generateK2(nodeId)`
2. K2 sent to node during provisioning via `POST /api/v1/provision-k2`
3. K2 stored locally in expo-secure-store
4. Success screen offers QR backup option

### QR Backup Format

**Plain QR Payload:**
```json
{
  "v": 1,
  "mode": "plain",
  "node_id": "jarvis-xxx",
  "kid": "<key-id>",
  "k2": "<base64url-encoded-key>",
  "created_at": "ISO8601",
  "cc_url": "http://..."
}
```

**Encrypted QR Payload:**
```json
{
  "v": 1,
  "mode": "enc",
  "node_id": "jarvis-xxx",
  "kid": "<key-id>",
  "kdf": "argon2id",
  "salt": "<base64url>",
  "params": {"m": 65536, "t": 3, "p": 1},
  "nonce": "<base64url>",
  "ciphertext": "<base64url>",
  "tag": "<base64url>",
  "created_at": "ISO8601",
  "cc_url": "http://..."
}
```

**Canonical AAD:** `{"v":1,"node_id":"<node_id>","kid":"<kid>"}`

### Build Requirements

Requires Expo development build (not Expo Go) due to native module:
```bash
npx expo run:ios        # Local build
# or
eas build --profile development  # Cloud build
```

---

## Environment Setup

### Ubuntu

```bash
# jarvis-node-setup/.env
JARVIS_SIMULATE_PROVISIONING=true
JARVIS_PROVISIONING_PORT=8080
CONFIG_PATH=/path/to/jarvis-node-setup/config.json
```

### Mac

```bash
# jarvis-node-mobile/.env
EXPO_PUBLIC_DEV_MODE=true
EXPO_PUBLIC_SIMULATED_NODE_IP=<ubuntu-ip>
EXPO_PUBLIC_COMMAND_CENTER_URL=http://<ubuntu-ip>:7703
EXPO_PUBLIC_AUTH_API_BASE_URL=http://<ubuntu-ip>:7701
```

---

## API Contract Reference

### GET /api/v1/info
```json
{
  "node_id": "jarvis-a1b2c3d4",
  "firmware_version": "1.0.0",
  "hardware": "pi-zero-w",
  "mac_address": "b8:27:eb:a1:b2:c3",
  "capabilities": ["voice", "speaker"],
  "state": "AP_MODE"
}
```

### GET /api/v1/scan-networks
```json
{
  "networks": [
    {"ssid": "HomeNetwork", "signal_strength": -45, "security": "WPA2"},
    {"ssid": "Neighbor_5G", "signal_strength": -72, "security": "WPA2"}
  ]
}
```

### POST /api/v1/provision
Request:
```json
{
  "wifi_ssid": "HomeNetwork",
  "wifi_password": "secret123",
  "room": "kitchen",
  "command_center_url": "http://192.168.1.50:7703"
}
```
Response:
```json
{
  "success": true,
  "message": "Credentials received. Attempting connection..."
}
```

### GET /api/v1/status
```json
{
  "state": "CONNECTING",
  "message": "Connecting to HomeNetwork...",
  "progress_percent": 50,
  "error": null
}
```

State values: `AP_MODE`, `CONNECTING`, `REGISTERING`, `PROVISIONED`, `ERROR`

### POST /api/v1/provision-k2 (NEEDS IMPLEMENTATION)
Request:
```json
{
  "k2": "<base64url-encoded-256-bit-key>",
  "kid": "<key-id-uuid>"
}
```
Response:
```json
{
  "success": true,
  "message": "Encryption key received"
}
```

Node should store K2 securely for encrypting settings before sending to command-center.

---

## Next Actions

### Ubuntu Claude
1. ~~Create provisioning module~~ ✅
2. ~~Implement API endpoints~~ ✅
3. ~~Create simulator script~~ ✅
4. ~~Update sync doc~~ ✅
5. Implement `POST /api/v1/provision-k2` endpoint to receive K2 from mobile

### Mac Claude
1. ~~Verify can reach Ubuntu provisioning server~~ ✅
2. ~~Create `jarvis-node-mobile` repo~~ ✅
3. ~~Implement navigation and theme~~ ✅
4. ~~Implement provisioning screens~~ ✅
5. ~~Implement jarvis-crypto native module~~ ✅
6. ~~Implement K2 backup/restore QR flow~~ ✅
7. Run `npm install` and build dev client
8. E2E test full provisioning flow with real node

---

## Testing Checklist

- [x] Simulator running on Ubuntu port 8080
- [x] Mobile can reach Ubuntu over LAN (tested at 10.0.0.122:8080)
- [x] GET /info returns node info
- [x] POST /provision accepts credentials
- [x] GET /status shows state progression
- [ ] POST /provision-k2 receives K2 from mobile (needs backend implementation)
- [ ] Node appears in command-center after provisioning
- [ ] K2 QR backup generates correctly
- [ ] K2 QR import works (plain and encrypted)

---

## Notes

- No legacy code, no backwards compat
- Move fast, iterate
- Update this doc after each significant change
- WiFi simulation always succeeds for networks in the simulated list
