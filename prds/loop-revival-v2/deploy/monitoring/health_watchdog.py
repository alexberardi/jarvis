#!/usr/bin/env python3
"""OpenClaw gateway health watchdog.

Runs on a short systemd timer. Detects the failure modes we've actually hit:
  - gateway service not active
  - MCP servers failing to start ("failed to start server")
  - wedged sessions ("queued_work_without_active_run" / "stale_session_state")
and, when severe, restarts the gateway (with a cooldown so it can't loop) and
DMs the owner on Slack. Auth-credential blips are alert-only (they self-heal;
a restart wouldn't fix a bad token anyway).

Healthy runs are silent (journal only). No Slack spam.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

GATEWAY = "openclaw-gateway.service"
STATE = Path.home() / ".openclaw" / ".watchdog-state.json"
OPENCLAW_JSON = Path.home() / ".openclaw" / "openclaw.json"
LOOKBACK = "12 min ago"
RESTART_COOLDOWN = 1800  # 30 min — don't auto-restart more than once per window
LOW_NOISE_INTERVAL = 21600  # 6h — DM cadence for known-benign, restart-won't-fix transients

# Severe -> restart the gateway. Alert-only -> notify (self-heals / a restart wouldn't help).
RESTART_SIGNS = [
    "queued_work_without_active_run",
    "stale_session_state",
    "stuck session",
]
# Known-benign-but-noisy. An MCP subprocess transient ("failed to start server: Connection
# closed") that recurs as collateral when a heavy run hits cli_budget and gateway-side
# compaction 401s (the gateway has no anthropic credential; agents use the claude CLI oauth,
# so runs still succeed). Restarting the WHOLE gateway does NOT fix it — it recurs next run —
# and it kills in-flight sessions. So: DO NOT restart for these; heads-up at most every 6h.
TRANSIENT_SIGNS = [
    "failed to start server",
]
ALERT_SIGNS = [
    "Invalid authentication credentials",
    "authentication_error",
]


def sh(*args: str, timeout: int = 25) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def journal_recent() -> str:
    _, out = sh("journalctl", "--user", "-u", GATEWAY, "--since", LOOKBACK,
                "--no-pager", timeout=25)
    return out


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(s: dict) -> None:
    try:
        STATE.write_text(json.dumps(s))
    except Exception:
        pass


def slack_dm(text: str) -> None:
    """DM the owner via the bot token + ownerAllowFrom id from openclaw.json."""
    try:
        cfg = json.loads(OPENCLAW_JSON.read_text())
        token = cfg["channels"]["slack"]["botToken"]
        owners = cfg.get("commands", {}).get("ownerAllowFrom", [])
        owner = next((o.split(":", 1)[1] for o in owners if o.startswith("slack:")), None)
        if not (token and owner):
            return
        body = json.dumps({"channel": owner, "text": text}).encode()
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage", data=body, method="POST",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=utf-8"})
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"watchdog: slack DM failed: {e}")


def main() -> None:
    state = load_state()
    now = time.time()

    rc, active = sh("systemctl", "--user", "is-active", GATEWAY)
    active = active.strip()
    log = journal_recent()

    gateway_down = active != "active"
    restart_hits = [s for s in RESTART_SIGNS if s in log]
    alert_hits = [s for s in ALERT_SIGNS if s in log]
    transient_hits = [s for s in TRANSIENT_SIGNS if s in log]

    severe = gateway_down or bool(restart_hits)
    if not severe:
        # Auth blip (compaction has no gateway credential): non-fatal, a restart won't fix it.
        if alert_hits and (now - state.get("last_alert", 0) > 3600):
            slack_dm(f"⚠️ openclaw watchdog: auth blip in logs ({', '.join(alert_hits)}). "
                     f"Gateway-side compaction has no anthropic credential — non-fatal (agents "
                     f"use the claude CLI oauth, runs still succeed). Not restarting; a restart "
                     f"can't fix a credential. Fix: give the gateway a token or trim context.")
            state["last_alert"] = now
            save_state(state)
        # Known-benign MCP transient: do NOT restart (recurs next run; restart kills sessions).
        elif transient_hits and (now - state.get("last_transient_alert", 0) > LOW_NOISE_INTERVAL):
            slack_dm(f"ℹ️ openclaw watchdog: transient MCP start failure ({', '.join(transient_hits)}) "
                     f"— gateway is active and serving. Collateral of the compaction-auth issue; "
                     f"not restarting (a restart doesn't fix it). Heads-up only, throttled to 6h.")
            state["last_transient_alert"] = now
            save_state(state)
        tag = " [benign transient]" if transient_hits else ""
        print(f"watchdog: healthy (gateway={active}){tag}. no action.")
        return

    reason = "gateway not active" if gateway_down else f"degraded: {', '.join(restart_hits)}"
    in_cooldown = (now - state.get("last_restart", 0)) < RESTART_COOLDOWN

    if in_cooldown:
        if now - state.get("last_alert", 0) > 600:
            slack_dm(f"🚨 openclaw watchdog: STILL degraded ({reason}) but a restart happened "
                     f"<{RESTART_COOLDOWN//60}m ago — NOT auto-restarting again. Needs you.")
            state["last_alert"] = now
            save_state(state)
        print(f"watchdog: degraded ({reason}) but in cooldown — not restarting.")
        return

    # restart + alert
    print(f"watchdog: RESTARTING gateway — {reason}")
    sh("systemctl", "--user", "restart", GATEWAY, timeout=60)
    time.sleep(8)
    _, active2 = sh("systemctl", "--user", "is-active", GATEWAY)
    state["last_restart"] = now
    state["last_alert"] = now
    save_state(state)
    slack_dm(f"🔧 openclaw watchdog: gateway was unhealthy ({reason}) — auto-restarted. "
             f"Now: {active2.strip()}. (Won't restart again for {RESTART_COOLDOWN//60}m.)")


if __name__ == "__main__":
    main()
