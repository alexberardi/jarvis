# Jarvis Node Mobile - Sync Document

Cross-machine coordination between Ubuntu (backend) and Mac (mobile).

## Latest Sync: 2026-02-01

### Current Status: BACKEND READY

Provisioning API implemented and tested. Ready for mobile development.

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

### Needs Implementation

| Component | Status |
|-----------|--------|
| New repo `jarvis-node-mobile` | NOT STARTED |
| Copy auth from recipes-mobile | NOT STARTED |
| Navigation structure | NOT STARTED |
| Provisioning screens | NOT STARTED |
| Nodes list/detail screens | NOT STARTED |

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
EXPO_PUBLIC_COMMAND_CENTER_URL=http://<ubuntu-ip>:8002
EXPO_PUBLIC_AUTH_API_BASE_URL=http://<ubuntu-ip>:8007
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
  "command_center_url": "http://192.168.1.50:8002"
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

---

## Next Actions

### Ubuntu Claude
1. ~~Create provisioning module~~ ✅
2. ~~Implement API endpoints~~ ✅
3. ~~Create simulator script~~ ✅
4. ~~Update sync doc~~ ✅

### Mac Claude
1. Verify can reach Ubuntu provisioning server
2. Create `jarvis-node-mobile` repo
3. Copy auth from `jarvis-recipes-mobile`
4. Implement screens per design doc

---

## Testing Checklist

- [x] Simulator running on Ubuntu port 8080
- [ ] Mobile can reach Ubuntu over LAN
- [x] GET /info returns node info
- [x] POST /provision accepts credentials
- [x] GET /status shows state progression
- [ ] Node appears in command-center after provisioning

---

## Notes

- No legacy code, no backwards compat
- Move fast, iterate
- Update this doc after each significant change
- WiFi simulation always succeeds for networks in the simulated list
