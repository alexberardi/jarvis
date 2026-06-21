#!/usr/bin/env python3
"""Seed the running install stack for Phase 2 (CC behavior) + Phase 3 (real node).

Run by the workflow AFTER the core stack is up and healthy. It:
  1. creates the first superuser (→ user JWT + auto-created household)
  2. registers a node via CC's admin API (→ node key)
  3. flips llm.interface to ChatGPTOpenAI (native tool calling → cloud model)
  4. writes the node container's config.json
  5. exports creds to $GITHUB_ENV (CC_NODE_ID/KEY, CC_USER_JWT, CC_HOUSEHOLD_ID)

Everything is keyed off env so it works in CI and locally:
  AUTH_URL (default http://localhost:7701), CC_URL (default http://localhost:7703),
  ADMIN_API_KEY (default matches the gen placeholder), NODE_ID (default ci-node-001),
  NODE_CONFIG_PATH (where to write config.json for the node container mount).

Idempotent-ish: tolerates an already-initialized superuser / already-registered node.
"""
from __future__ import annotations

import json
import os
import sys

import requests

AUTH_URL = os.environ.get("AUTH_URL", "http://localhost:7701").rstrip("/")
CC_URL = os.environ.get("CC_URL", "http://localhost:7703").rstrip("/")
# The generated compose-export sets CC's ADMIN_API_KEY from the wizard secrets;
# the CI generator uses a deterministic placeholder ("d" * 64).
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "d" * 64)
NODE_ID = os.environ.get("NODE_ID", "ci-node-001")
NODE_CONFIG_PATH = os.environ.get("NODE_CONFIG_PATH", "/var/lib/jarvis/node/config.json")

# Container-network URLs the node uses (it runs inside the compose network).
NODE_CONFIG_URL = os.environ.get("NODE_CONFIG_URL", "http://jarvis-config-service:7700")
NODE_CC_URL = os.environ.get("NODE_CC_URL", "http://jarvis-command-center:8002")
NODE_MQTT_BROKER = os.environ.get("NODE_MQTT_BROKER", "jarvis-mosquitto")
NODE_MQTT_PORT = int(os.environ.get("NODE_MQTT_PORT", "1883"))

EMAIL = os.environ.get("SEED_EMAIL", "ci-e2e@example.com")
PASSWORD = os.environ.get("SEED_PASSWORD", "ci-e2e-Password-123")


def _die(msg: str, resp: requests.Response | None = None) -> None:
    extra = f" [{resp.status_code}] {resp.text[:300]}" if resp is not None else ""
    print(f"::error::seed: {msg}{extra}", flush=True)
    sys.exit(1)


def create_superuser() -> tuple[str, str]:
    """Return (household_id, jwt). Uses /auth/setup; falls back to /auth/login."""
    r = requests.post(
        f"{AUTH_URL}/auth/setup", json={"email": EMAIL, "password": PASSWORD}, timeout=30
    )
    if r.status_code in (200, 201):
        body = r.json()
        return body["household_id"], body["access_token"]
    # Already set up — log in instead, then discover the household.
    if r.status_code in (400, 403, 409):
        login = requests.post(
            f"{AUTH_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30
        )
        if login.status_code != 200:
            _die("login after existing-setup failed", login)
        token = login.json()["access_token"]
        hh = requests.get(
            f"{AUTH_URL}/households",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if hh.status_code != 200 or not hh.json():
            _die("could not resolve household for existing superuser", hh)
        households = hh.json()
        hid = households[0]["id"] if isinstance(households, list) else households["id"]
        return hid, token
    _die("auth/setup failed", r)
    raise SystemExit(1)  # unreachable, for type-checkers


def register_node(household_id: str) -> str:
    """Return the node key. Registers in both auth and CC's local nodes table."""
    r = requests.post(
        f"{CC_URL}/api/v0/admin/nodes",
        headers={"X-API-Key": ADMIN_API_KEY},
        json={"node_id": NODE_ID, "household_id": household_id, "room": "ci-room", "name": "CI Node"},
        timeout=30,
    )
    if r.status_code in (200, 201):
        return r.json()["node_key"]
    _die("node registration failed", r)
    raise SystemExit(1)


def set_llm_interface(jwt: str) -> None:
    headers = {"Authorization": f"Bearer {jwt}"}
    r = requests.put(
        f"{CC_URL}/settings/llm.interface", headers=headers,
        json={"value": "ChatGPTOpenAI"}, timeout=30,
    )
    if r.status_code not in (200, 204):
        _die("setting llm.interface failed", r)
    # Bust the per-request settings cache so the next inference uses the new provider.
    requests.post(f"{CC_URL}/settings/invalidate-cache", headers=headers, timeout=30)


def write_node_config(node_key: str) -> None:
    os.makedirs(os.path.dirname(NODE_CONFIG_PATH), exist_ok=True)
    config = {
        "node_id": NODE_ID,
        "api_key": node_key,
        "jarvis_config_service_url": NODE_CONFIG_URL,
        "jarvis_command_center_api_url": NODE_CC_URL,
        "mqtt_broker": NODE_MQTT_BROKER,
        "mqtt_port": NODE_MQTT_PORT,
        "mqtt_enabled": True,
        "room": "ci-room",
        "user": "default",
        "voice": "en",
    }
    with open(NODE_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    print(f"seed: wrote node config → {NODE_CONFIG_PATH}", flush=True)


def export_env(household_id: str, jwt: str, node_key: str) -> None:
    out = os.environ.get("GITHUB_ENV")
    lines = {
        "CC_HOUSEHOLD_ID": household_id,
        "CC_USER_JWT": jwt,
        "CC_NODE_ID": NODE_ID,
        "CC_NODE_KEY": node_key,
    }
    if out:
        with open(out, "a") as f:
            for k, v in lines.items():
                f.write(f"{k}={v}\n")
    print("seed: complete — exported CC_NODE_ID/KEY, CC_USER_JWT, CC_HOUSEHOLD_ID", flush=True)


def main() -> None:
    household_id, jwt = create_superuser()
    node_key = register_node(household_id)
    set_llm_interface(jwt)
    write_node_config(node_key)
    export_env(household_id, jwt, node_key)


if __name__ == "__main__":
    main()
