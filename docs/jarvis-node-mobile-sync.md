# Jarvis Node Mobile - Sync Document

Cross-machine coordination between Ubuntu (backend) and Mac (mobile).

## Latest Sync: 2026-01-31

### Current Status: STARTING FRESH

No backwards compat needed - greenfield project.

---

## Backend Status (Ubuntu)

### Needs Implementation

| Component | Location | Status |
|-----------|----------|--------|
| Provisioning API | `jarvis-node-setup/provisioning/` | NOT STARTED |
| Simulator script | `jarvis-node-setup/scripts/run_provisioning_simulator.py` | NOT STARTED |
| Command center admin API | Already exists at `/api/v0/admin/nodes` | VERIFY |

### API Endpoints to Implement

```
GET  /api/v1/info           # Node info
GET  /api/v1/scan-networks  # Available WiFi networks
POST /api/v1/provision      # Send WiFi credentials
GET  /api/v1/status         # Provisioning progress
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
# jarvis-node-setup/.env (add these)
SIMULATION_MODE=true
PROVISIONING_PORT=8080
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

## Next Actions

### Ubuntu Claude
1. Create `jarvis-node-setup/provisioning/` module
2. Implement provisioning API endpoints
3. Create simulator script
4. Update this sync doc when ready

### Mac Claude
1. Wait for Ubuntu to have simulator running
2. Create `jarvis-node-mobile` repo
3. Copy auth from `jarvis-recipes-mobile`
4. Implement screens per design doc

---

## Testing Checklist

- [ ] Simulator running on Ubuntu port 8080
- [ ] Mobile can reach Ubuntu over LAN
- [ ] GET /info returns node info
- [ ] POST /provision accepts credentials
- [ ] GET /status shows state progression
- [ ] Node appears in command-center after provisioning

---

## Notes

- No legacy code, no backwards compat
- Move fast, iterate
- Update this doc after each significant change
