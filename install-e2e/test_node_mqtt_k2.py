"""Phase 3 — a REAL node container joins MQTT and completes a K2 round-trip.

This is net-new coverage: the existing harness only ever *simulated* nodes via
seeded DB rows. Here a real `jarvis-node` container (text mode) connects to the
Mosquitto broker on the compose network and we drive the full K2 provision
handshake end-to-end:

    POST /api/v0/nodes/{id}/k2 (user JWT, k2+kid+created_at)
      → CC publishes MQTT jarvis/nodes/{id}/k2/provision
      → node._handle_k2_provision saves K2 (encrypted with K1)
      → node POSTs /api/v0/nodes/{id}/k2/ack/{request_id} (node X-API-Key)
      → CC's 15s poll sees the ack → 200 {"ok": true}

Asserts: node MQTT connected, K2 round-trip returns ok, node health flips
needs_k2 true→false. Gated: skipped unless the node container is up
(JARVIS_E2E_NODE=1) and the seed exported CC_NODE_ID + CC_USER_JWT.
"""
from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timezone

import pytest
import requests

CC_URL = os.environ.get("CC_URL", "http://localhost:7703").rstrip("/")
NODE_URL = os.environ.get("NODE_URL", "http://localhost:7771").rstrip("/")
CC_NODE_ID = os.environ.get("CC_NODE_ID", "")
CC_USER_JWT = os.environ.get("CC_USER_JWT", "")
NODE_ENABLED = os.environ.get("JARVIS_E2E_NODE") == "1"

pytestmark = [
    pytest.mark.skipif(not NODE_ENABLED, reason="JARVIS_E2E_NODE!=1 — node container not up"),
    pytest.mark.skipif(not (CC_NODE_ID and CC_USER_JWT), reason="seed did not export node creds + JWT"),
]


def _get_json(url: str, timeout: float = 5.0) -> dict | None:
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def _wait(predicate, timeout: float = 120.0, interval: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_node_health_up() -> None:
    """The node's text-mode HTTP server is serving."""
    assert _wait(lambda: _get_json(f"{NODE_URL}/health") is not None, timeout=120), (
        f"node /health never came up at {NODE_URL}"
    )
    body = _get_json(f"{NODE_URL}/health")
    assert body and body.get("status") == "healthy", f"unexpected node health: {body}"


def test_node_mqtt_connected() -> None:
    """The node connected to Mosquitto and its listener thread is alive."""
    ok = _wait(
        lambda: (_get_json(f"{NODE_URL}/debug/mqtt") or {}).get("client_connected") is True,
        timeout=120,
    )
    dbg = _get_json(f"{NODE_URL}/debug/mqtt")
    assert ok, f"node never connected to MQTT: {dbg}"
    assert dbg and dbg.get("thread_alive") is True, f"MQTT thread not alive: {dbg}"


def test_k2_provision_round_trip() -> None:
    """Full K2 handshake: CC → MQTT → node saves K2 → node ACKs → CC returns ok."""
    # Sanity: node should report it needs K2 before we provision it.
    pre = _get_json(f"{NODE_URL}/health") or {}
    assert pre.get("needs_k2") is True, f"node already has K2 before provisioning? {pre}"

    # Ensure the node is actually subscribed before publishing, else the retained-
    # less provision message is missed and CC times out (504).
    assert _wait(
        lambda: (_get_json(f"{NODE_URL}/debug/mqtt") or {}).get("client_connected") is True,
        timeout=120,
    ), "node not MQTT-connected; K2 publish would be missed"

    k2 = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")  # 32 bytes, unpadded
    payload = {
        "k2": k2,
        "kid": "k2-ci-001",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    r = requests.post(
        f"{CC_URL}/api/v0/nodes/{CC_NODE_ID}/k2",
        headers={"Authorization": f"Bearer {CC_USER_JWT}"},
        json=payload,
        timeout=30,
    )
    assert r.status_code == 200, (
        f"K2 provision failed: {r.status_code} {r.text[:300]} "
        f"(504=node didn't ack, 502=node save failed, 503=no MQTT, 404=node unknown)"
    )
    assert r.json().get("ok") is True, f"K2 provision not ok: {r.json()}"

    # The node should now report it no longer needs K2.
    assert _wait(
        lambda: (_get_json(f"{NODE_URL}/health") or {}).get("needs_k2") is False,
        timeout=30,
    ), "node still reports needs_k2 after a successful K2 provision"
