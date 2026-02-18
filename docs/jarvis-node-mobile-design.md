# Jarvis Node Mobile - Design Document

**Version**: 1.0
**Date**: 2026-01-31
**Status**: Active Development (no backwards compat needed)

## Overview

### What is jarvis-node-mobile?

React Native cross-platform mobile app that serves as the **admin panel and orchestrator** for Jarvis. NOT a voice node - it's the control plane.

### Primary Purpose

1. **WiFi Provisioning** (MVP) - Bootstrap headless Pi Zero nodes onto the home network
2. **Node Administration** - Manage node configurations, commands, secrets
3. **System Monitoring** - View node health, logs, status

### Key Distinction

| Component | Role | Platform |
|-----------|------|----------|
| jarvis-node (Pi Zero) | Voice capture, wake word, sends audio | Raspberry Pi Zero |
| jarvis-node-mobile | Admin panel, provisioning, management | iOS/Android |
| jarvis-command-center | Central API, voice processing, routing | Server |

---

## Architecture

### System Context

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Home Network                                    │
│                                                                             │
│  ┌──────────────────┐        ┌──────────────────┐                          │
│  │ jarvis-node-     │        │ jarvis-command-  │                          │
│  │ mobile (Admin)   │──────▶ │ center           │                          │
│  │                  │  HTTP  │ (port 7703)      │                          │
│  └──────────────────┘        └────────┬─────────┘                          │
│          │                            │                                     │
│          │                   ┌────────┼─────────┐                          │
│          │                   │        │         │                          │
│          │              ┌────▼──┐ ┌───▼───┐ ┌───▼───┐                      │
│          │              │jarvis │ │jarvis │ │jarvis │                      │
│          │              │-auth  │ │-llm   │ │-tts   │                      │
│          │              │(7701) │ │(7704) │ │(7707) │                      │
│          │              └───────┘ └───────┘ └───────┘                      │
│          │                                                                  │
│  ┌───────▼──────────────────────────────────────────┐                      │
│  │              Pi Zero Nodes (after provisioning)  │                      │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐          │                      │
│  │  │ Kitchen │  │ Bedroom │  │ Office  │   ...    │                      │
│  │  │ Node    │  │ Node    │  │ Node    │          │                      │
│  │  └─────────┘  └─────────┘  └─────────┘          │                      │
│  └──────────────────────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        Provisioning Phase (temporary)                        │
│                                                                             │
│  ┌──────────────┐         ┌──────────────┐                                 │
│  │ Mobile Phone │         │ Pi Zero      │                                 │
│  │ (WiFi client)│◀───────▶│ (AP mode)    │                                 │
│  │              │  Direct │ SSID:        │                                 │
│  │              │  WiFi   │ "jarvis-XXX" │                                 │
│  └──────────────┘         └──────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Mobile App Structure

Following jarvis-recipes-mobile patterns:

```
jarvis-node-mobile/
├── App.tsx
├── src/
│   ├── api/
│   │   ├── authApi.ts           # Copy from recipes-mobile
│   │   ├── commandCenterApi.ts  # Command center client
│   │   └── provisioningApi.ts   # Direct node communication
│   ├── auth/
│   │   └── AuthContext.tsx      # Copy from recipes-mobile
│   ├── config/
│   │   └── env.ts
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useNodes.ts
│   │   └── useProvisioning.ts
│   ├── navigation/
│   │   ├── RootNavigator.tsx
│   │   ├── AuthNavigator.tsx
│   │   └── NodesNavigator.tsx
│   ├── screens/
│   │   ├── Auth/
│   │   │   ├── LoginScreen.tsx
│   │   │   └── RegisterScreen.tsx
│   │   ├── Nodes/
│   │   │   ├── NodesListScreen.tsx
│   │   │   └── NodeDetailScreen.tsx
│   │   └── Provisioning/
│   │       ├── ScanForNodesScreen.tsx
│   │       ├── ConnectToNodeScreen.tsx
│   │       ├── EnterWiFiCredsScreen.tsx
│   │       └── ProvisioningCompleteScreen.tsx
│   └── theme/
│       └── ThemeProvider.tsx
└── package.json
```

---

## WiFi Provisioning Flow

### The Bootstrap Problem

Pi Zero nodes are headless. Standard IoT solution: **Soft AP Provisioning**

### Flow

```
PHASE 1: Node Startup
────────────────────
1. Power on Pi Zero
2. No WiFi configured? → Enter AP mode
3. Start hotspot: "jarvis-{last-4-mac}"
4. Start provisioning API on 192.168.4.1:8080
5. LED: blinking (awaiting provisioning)

PHASE 2: Mobile Discovers Node
──────────────────────────────
1. User opens app → "Add Node"
2. App scans for "jarvis-*" networks
3. User selects node

PHASE 3: Connect & Configure
────────────────────────────
1. App: "Connect to jarvis-XXXX network"
2. User connects phone to node's hotspot
3. App calls GET /api/v1/info → node info
4. User enters: WiFi SSID, password, room name
5. App calls POST /api/v1/provision
6. Node LED: solid (attempting connection)

PHASE 4: Node Joins Network
───────────────────────────
1. Node connects to home WiFi
2. Node registers with command-center
3. Node LED: solid green (ready)

PHASE 5: Mobile Verifies
────────────────────────
1. App: "Reconnect to home WiFi"
2. User reconnects phone
3. App polls command-center for new node
4. Success!
```

### State Machine

```
UNPROVISIONED → AP_MODE → CONNECTING → REGISTERING → PROVISIONED
                   ↑           │
                   └───────────┘ (connection failed)
```

---

## Ubuntu Simulation Strategy

### The Challenge

Real provisioning needs Pi hardware in AP mode. For dev:
- No actual AP mode on Ubuntu
- Mobile app on Mac can't connect to fake hotspot
- Need to simulate the flow

### Solution

```
Ubuntu (simulated node)              Mac (mobile app)
┌────────────────────┐              ┌────────────────────┐
│ Provisioning API   │◀────────────▶│ React Native App   │
│ (0.0.0.0:8080)     │   Same LAN   │ (Expo)             │
│                    │              │                    │
│ Simulates:         │              │ DEV_MODE=true      │
│ - Node info        │              │ - Skip WiFi switch │
│ - Credential store │              │ - Direct HTTP      │
│ - Registration     │              │ - Manual IP entry  │
└────────────────────┘              └────────────────────┘
```

### Running the Simulator

```bash
# On Ubuntu
cd /home/alex/jarvis/jarvis-node-setup
python scripts/run_provisioning_simulator.py
# Listens on 0.0.0.0:8080
```

### Mobile Dev Mode

```bash
# jarvis-node-mobile/.env
EXPO_PUBLIC_DEV_MODE=true
EXPO_PUBLIC_SIMULATED_NODE_IP=192.168.1.XXX  # Ubuntu IP
EXPO_PUBLIC_COMMAND_CENTER_URL=http://192.168.1.XXX:7703
EXPO_PUBLIC_AUTH_API_BASE_URL=http://192.168.1.XXX:7701
```

Dev mode skips "connect to hotspot" step, uses configurable IP.

---

## API Contracts

### 1. Provisioning API (Node)

**Base:** `http://192.168.4.1:8080/api/v1` (real) or `http://{ubuntu-ip}:8080/api/v1` (dev)

#### GET /info
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

#### GET /scan-networks
```json
{
  "networks": [
    {"ssid": "HomeNetwork", "signal_strength": -45, "security": "WPA2"}
  ]
}
```

#### POST /provision
```json
// Request
{
  "wifi_ssid": "HomeNetwork",
  "wifi_password": "secret123",
  "room": "kitchen",
  "command_center_url": "http://192.168.1.50:7703"
}

// Response
{
  "success": true,
  "message": "Credentials received. Attempting connection..."
}
```

#### GET /status
```json
{
  "state": "CONNECTING",
  "message": "Connecting to HomeNetwork...",
  "progress_percent": 50,
  "error": null
}
```

### 2. Command Center Admin API

**Base:** `http://{command-center}:7703/api/v0/admin`
**Auth:** `X-Admin-Api-Key` header

#### GET /nodes
List all registered nodes.

#### POST /nodes
Register new node (called by node during provisioning).

#### PATCH /nodes/{node_id}
Update node config.

#### DELETE /nodes/{node_id}
Remove node.

### 3. Auth API

Copy from jarvis-recipes-mobile - same JWT flow with jarvis-auth.

---

## Data Models

### TypeScript (Mobile)

```typescript
interface Node {
  node_id: string;
  room: string;
  user: string;
  voice_mode: 'brief' | 'detailed';
  last_seen: string;
}

interface ProvisioningRequest {
  wifi_ssid: string;
  wifi_password: string;
  room: string;
  command_center_url: string;
}

type ProvisioningState =
  | 'AP_MODE' | 'CONNECTING' | 'REGISTERING' | 'PROVISIONED' | 'ERROR';
```

### Python (Node)

```python
from pydantic import BaseModel, SecretStr

class ProvisioningRequest(BaseModel):
    wifi_ssid: str
    wifi_password: SecretStr  # Never log
    room: str
    command_center_url: str
```

---

## Future Admin Features (Backlog)

- Node config management (room, voice mode, commands)
- Command enable/disable per node
- Secret management for commands
- Health monitoring (online/offline)
- Logs viewer
- Firmware updates

---

## Cross-Machine Coordination

### Workflow

```
Ubuntu Claude                          Mac Claude
─────────────                          ──────────
1. Make backend changes
2. Update sync doc
3. Commit & push
                    ─────────▶
                                       4. Pull changes
                                       5. Read sync doc
                                       6. Implement mobile
                                       7. Test against Ubuntu
                                       8. Commit & push
```

### Sync Document

See `/home/alex/jarvis/docs/jarvis-node-mobile-sync.md` for current status.

### What Goes Where

| Repo | Changes |
|------|---------|
| `jarvis-node-setup` | `provisioning/` module |
| `jarvis-command-center` | Admin API (if needed) |
| `jarvis` (meta) | Design doc, sync doc |
| `jarvis-node-mobile` | Mobile app |

---

## Implementation Phases

### Phase 1: Foundation
- **Ubuntu**: Create `provisioning/` module, simulator script
- **Mac**: Create repo, copy auth, set up navigation

### Phase 2: Core Provisioning
- **Ubuntu**: Implement all provisioning endpoints
- **Mac**: Implement provisioning screens

### Phase 3: Integration
- **Ubuntu**: Add real AP mode (hostapd)
- **Mac**: Polish, error handling

### Phase 4: Node Management
- **Mac**: Nodes list, detail, config screens

---

## References

- Auth pattern: `jarvis-recipes-mobile/src/auth/AuthContext.tsx`
- API pattern: `jarvis-recipes-mobile/src/api/recipesApi.ts`
- Node model: `jarvis-command-center/app/models.py`
- Admin API: `jarvis-command-center/app/admin.py`
