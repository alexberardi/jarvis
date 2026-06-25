"""
GitHub webhook receiver for the OpenClaw multi-persona pipeline (loop v2 — calm + visible).

Receives GitHub events at /webhook, validates HMAC, and fires the right persona via
`openclaw agent` so label-flips cycle the workflow INSTANTLY (no waiting on a cron).
All routes gated to alexberardi/jarvis-roadmap.

WHY "calm + visible" (phase 4):
- CALM — a per-persona SPAWN GUARD: each agent scans the whole queue on every run, so the
  webhook only needs to fire a persona once per burst. We (a) never spawn a persona that's
  already running, and (b) debounce repeat spawns within DEBOUNCE_SEC. A flood of label/comment
  events therefore can NOT cascade into a flood of agent runs (the bug that forced the v1 halt).
- VISIBLE — every spawned run streams stdout+stderr to ~/.openclaw/webhook-runs/<persona>-<issue>-<ts>.log
  (the v1 receiver dumped to /dev/null, which is why agent work was invisible and felt dead).

Routes (label-add events, + issue_comment for the agent→agent hand-offs that can't be a label):
  issues.opened / status:proposed   → engineering   (triage the new umbrella)
  status:locked   (Alex's GO)        → engineering   (ready-gate → status:ready-for-code)
  status:ready-for-code              → coding-agent  (build the coordinated branch set)
  needs:engineering|qa|coding-agent|qa-executor → matching persona
  <!-- qa-test-plan:v1 -->           → engineering   (ready-gate after qa plans)
  <!-- coding-agent-feature-ready:v1 --> → qa-executor (poll CI, mirror results)
  <!-- retry-please:v1 -->           → engineering   (re-arm a parked feature)

Lives on 127.0.0.1:8088; reachable via the Cloudflare Tunnel at https://openclaw.jarvisautomation.dev/webhook.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time

from fastapi import FastAPI, Header, HTTPException, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("webhook")

app = FastAPI(title="jarvis-webhook-receiver")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").encode()
if not WEBHOOK_SECRET:
    log.warning("WEBHOOK_SECRET not set — signature checks will fail")

OPENCLAW_BIN = "/usr/bin/openclaw"
ROADMAP = "alexberardi/jarvis-roadmap"

# --- visibility: every spawned run logs here (NOT /dev/null) ---
LOG_DIR = os.path.expanduser("~/.openclaw/webhook-runs")
os.makedirs(LOG_DIR, exist_ok=True)

# --- calm: per-persona spawn guard (no cascade) ---
DEBOUNCE_SEC = 30          # don't re-spawn the same persona within this window
_last_spawn: dict[str, float] = {}   # persona -> monotonic ts of last spawn
_running: set[str] = set()           # personas with a run in flight

PROMPT_FILE = {
    "engineering": "triage-prompt.md",
    "qa": "qa-prompt.md",
    "coding-agent": "coding-prompt.md",
    "qa-executor": "qa-executor-prompt.md",
    "qa-author": "qa-author-prompt.md",
}

LABEL_ROUTES = {
    "status:proposed":       ("engineering",  "triage"),
    "status:locked":         ("engineering",  "ready-gate"),
    "status:ready-for-code": ("coding-agent", "code"),
    "needs:engineering":     ("engineering",  "interrupt"),
    "needs:qa":              ("qa",           "handoff"),
    "needs:coding-agent":    ("coding-agent", "interrupt"),
    "needs:qa-executor":     ("qa-executor",  "interrupt"),
    "needs:qa-author":       ("qa-author",    "author-case"),
}

COMMENT_ROUTES = {
    "<!-- qa-test-plan:v1 -->":              ("engineering", "ready-gate-after-plan"),
    "<!-- coding-agent-feature-ready:v1 -->":("qa-executor", "poll-ci"),
    "<!-- retry-please:v1 -->":              ("engineering", "re-arm"),
}


def build_message(mode: str, persona: str, issue_n: int, label: str | None = None) -> str:
    contract = f"Your full operating contract is at ~/.openclaw/{PROMPT_FILE[persona]} and ~/.openclaw/workspaces/{persona}/CONTEXT.md."
    pre = f"Webhook trigger on alexberardi/jarvis-roadmap#{issue_n}: "
    if mode == "triage":
        return (pre + "a new/`status:proposed` umbrella. Run your triage pass — post the breakdown + `## Branch set` + "
                "`feature-state:v1`; if the spec is complete (no open ambiguities) and there's no current qa-test-plan, "
                "set `needs:qa` + `status:accepted`. " + contract)
    if mode == "ready-gate":
        return (pre + "Alex set `status:locked` (the GO). Run Step 7: if a current `qa-test-plan:v1` has empty "
                "`proposed_cases`, ambiguities==0, and the branch set is declared → set `status:ready-for-code` "
                "(+ case_ids/gating_cases). If no current plan yet → set `needs:qa` first. " + contract)
    if mode == "code":
        return (pre + "the umbrella reached `status:ready-for-code`. Build it now — per-repo two-commit TDD, push all "
                "branches, open the N linked draft PRs, post `coding-agent-feature-ready:v1`. " + contract)
    if mode == "handoff":
        return (pre + "labeled `needs:qa` (engineering→qa hand-off). Run your NORMAL test-plan flow — produce/refresh "
                "`qa-test-plan:v1` referencing the catalog CASES; BLOCK on any coverage gap. " + contract)
    if mode == "ready-gate-after-plan":
        return (pre + "qa posted/refreshed a `qa-test-plan:v1`. Run Step 7b: remove `needs:qa`; if `status:locked` is "
                "present + the plan is clean → set `status:ready-for-code`; else leave `status:accepted` + surface the "
                "lock request; if `proposed_cases` is non-empty → BLOCK (coverage gap). " + contract)
    if mode == "re-arm":
        return (pre + "a `retry-please:v1` was posted — re-arm this feature: if parked and its blocker cleared, un-park "
                "and re-run the triage/ready-gate flow. " + contract)
    if mode == "poll-ci":
        return (pre + "coding-agent opened the PR set + posted `coding-agent-feature-ready:v1`. Poll each PR for "
                "`cross-repo-test-results:v1` and mirror onto the umbrella (qa-execution-report + gating_cases pass/fail). " + contract)
    if mode == "author-case":
        return (pre + "labeled `needs:qa-author` — engineering needs a CASE test authored or a stale CASE fixed for "
                "this feature. Run your Step 0 interrupt path: read the specific ask (which CASE id, what behavior) from "
                "engineering's note / the qa-test-plan `proposed_cases`, author or fix it in jarvis-integration-tests "
                "(WIP=1, dedup), open the draft PR, and post a `🔔 qa-author:` comment with the CASE id + PR link asking "
                "engineering to clear `needs:qa-author` and re-arm once it merges. You hold no roadmap labels. " + contract)
    return (pre + f"labeled `{label}` (interrupt). Handle it per your Step 0 — terminal-state first, then act and clear "
            f"the `{label}` label as your contract directs. " + contract)


@app.get("/")
def health():
    return {"status": "ok", "service": "jarvis-webhook-receiver", "phase": 4,
            "running": sorted(_running), "log_dir": LOG_DIR}


@app.get("/health")
def health_alias():
    return health()


@app.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
    x_github_delivery: str = Header(default=""),
):
    raw_body = await request.body()
    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="server misconfigured")
    if not x_hub_signature_256.startswith("sha256="):
        raise HTTPException(status_code=401, detail="missing signature")
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET, raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="signature mismatch")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="bad json")

    log.info("Received event=%s action=%s delivery=%s repo=%s", x_github_event,
             payload.get("action"), x_github_delivery, payload.get("repository", {}).get("full_name"))
    dispatched = await dispatch(x_github_event, payload, x_github_delivery)
    return {"status": "ok", "event": x_github_event, "action": payload.get("action"),
            "delivery": x_github_delivery, "dispatched": dispatched}


def _is_roadmap(payload: dict) -> bool:
    return (payload.get("repository") or {}).get("full_name") == ROADMAP


async def dispatch(event: str, payload: dict, delivery: str) -> dict:
    if event == "issues" and payload.get("action") == "opened":
        if not _is_roadmap(payload):
            return {"matched": False, "reason": "wrong repo"}
        n = payload["issue"]["number"]
        return await invoke_persona("engineering", build_message("triage", "engineering", n), delivery, n)

    if event == "issues" and payload.get("action") == "labeled":
        label_name = (payload.get("label") or {}).get("name") or ""
        route = LABEL_ROUTES.get(label_name)
        if route:
            if not _is_roadmap(payload):
                return {"matched": False, "reason": "wrong repo"}
            persona, mode = route
            n = payload["issue"]["number"]
            return await invoke_persona(persona, build_message(mode, persona, n, label_name), delivery, n, label=label_name)

    if event == "issue_comment" and payload.get("action") == "created":
        if _is_roadmap(payload):
            body = (payload.get("comment") or {}).get("body", "") or ""
            first_line = body.splitlines()[0].strip() if body.strip() else ""
            route = COMMENT_ROUTES.get(first_line)
            if route:
                persona, mode = route
                n = payload["issue"]["number"]
                return await invoke_persona(persona, build_message(mode, persona, n), delivery, n, sentinel=first_line)

    return {"matched": False, "reason": f"no route for event={event} action={payload.get('action')}"}


async def invoke_persona(persona: str, message: str, delivery: str, issue_n=None, label=None, sentinel=None) -> dict:
    """Spawn `openclaw agent` with the calm guard + visible logging."""
    trig = label or sentinel or "?"
    now = time.monotonic()
    # CALM: never two concurrent runs of one persona; debounce repeat spawns.
    if persona in _running:
        log.info("SKIP persona=%s (already running) trigger=%s issue=%s", persona, trig, issue_n)
        return {"matched": True, "persona": persona, "issue": issue_n, "spawned": False, "reason": "already-running"}
    last = _last_spawn.get(persona, 0.0)
    if now - last < DEBOUNCE_SEC:
        log.info("SKIP persona=%s (debounced %.0fs<%ds) trigger=%s issue=%s", persona, now - last, DEBOUNCE_SEC, trig, issue_n)
        return {"matched": True, "persona": persona, "issue": issue_n, "spawned": False, "reason": "debounced"}

    _last_spawn[persona] = now
    _running.add(persona)
    session_id = f"wh-{int(time.time())}-{delivery[:8]}"
    logpath = os.path.join(LOG_DIR, f"{persona}-{issue_n or 'x'}-{time.strftime('%Y%m%d-%H%M%S')}.log")
    cmd = [OPENCLAW_BIN, "agent", "--agent", persona, "--session-id", session_id,
           "--message", message, "--timeout", "900"]
    log.info("SPAWN persona=%s issue=%s trigger=%s session=%s log=%s", persona, issue_n, trig, session_id, logpath)
    try:
        lf = open(logpath, "w")
        lf.write(f"# webhook spawn persona={persona} issue={issue_n} trigger={trig} session={session_id}\n")
        lf.flush()
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=lf, stderr=asyncio.subprocess.STDOUT)
        asyncio.create_task(_reap(persona, proc, lf, logpath))
        return {"matched": True, "persona": persona, "issue": issue_n, "spawned": True, "log": logpath, "session": session_id}
    except Exception as e:
        _running.discard(persona)
        log.exception("Spawn failed persona=%s: %s", persona, e)
        return {"matched": True, "persona": persona, "issue": issue_n, "spawned": False, "reason": f"spawn-error: {e}"}


async def _reap(persona: str, proc, lf, logpath: str) -> None:
    rc = None
    try:
        rc = await proc.wait()
    except Exception:
        rc = None
    finally:
        try:
            lf.close()
        except Exception:
            pass
        _running.discard(persona)
        log.info("DONE persona=%s rc=%s log=%s", persona, rc, logpath)
