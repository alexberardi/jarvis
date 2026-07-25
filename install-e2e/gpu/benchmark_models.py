#!/usr/bin/env python3
"""Voice-command tool-routing benchmark across a set of local GGUF models.

Sweeps every (weights x prompt-provider) pair in ``bench_models.BENCH_MODELS``
through command-center's REAL ``/voice/command`` path against a canned corpus of
voice utterances, scoring two axes per model:

  * ACCURACY  — did the model route each utterance to the correct built-in tool
    with sensible arguments (reusing the behavior-corpus matcher), and did it
    correctly NOT fire a tool on small talk (false-positive rate on negatives).
  * SPEED     — end-to-end ``/voice/command`` wall-clock latency (p50/p95/mean),
    i.e. the latency the product actually delivers, plus per-model load time.

Why the CC path (not raw llm-proxy native tool-calling): local GGUFs do not
reliably emit structured tool_calls under a plain chat template, which is exactly
why command-center embeds the tools into the system prompt and parses the
model's ``<tool_call>`` output back out. Benchmarking that path measures the real
product behavior; each model is paired with its family-appropriate provider.

Topology (dev): this runs on the laptop. CC (:7703) is discovered to route
``model="live"`` inference at the GPU box's llm-proxy (http://10.0.0.122:7704),
so the whole real path exercises the GPU box. Per model the harness:
  1. writes ``model.live.{name,backend,chat_format,stop_tokens,context_window}``
     on llm-proxy (background is blanked once so it follows live -> single load),
  2. restarts the ``llm-proxy-model`` container to reload the new weights,
  3. flips CC ``llm.interface`` to the model's prompt provider,
  4. warms up, then times the corpus through ``/voice/command``.

Originals are captured up-front and restored at the end (best-effort, also on
Ctrl-C) so the box is left as found.

Usage (dev):
    python benchmark_models.py                     # all present models, full corpus
    python benchmark_models.py --models qwen3-8b,llama31-8b
    python benchmark_models.py --limit 6           # quick smoke (first 6 utterances)
    python benchmark_models.py --out results/bench.json

Env (all have sensible dev defaults):
    LLM_PROXY_URL      http://10.0.0.122:7704
    LLM_PROXY_SSH      alex@10.0.0.122
    MODEL_CONTAINER    llm-proxy-model
    API_CONTAINER      llm-proxy-api
    CC_URL             http://localhost:7703
    AUTH_URL           http://localhost:7701
    ADMIN_API_KEY      (read from the CC container if unset)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

from bench_models import BENCH_MODELS, BenchModel

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
LLM_PROXY_URL = os.environ.get("LLM_PROXY_URL", "http://10.0.0.122:7704").rstrip("/")
LLM_PROXY_SSH = os.environ.get("LLM_PROXY_SSH", "alex@10.0.0.122")
MODEL_CONTAINER = os.environ.get("MODEL_CONTAINER", "llm-proxy-model")
API_CONTAINER = os.environ.get("API_CONTAINER", "llm-proxy-api")
CC_URL = os.environ.get("CC_URL", "http://localhost:7703").rstrip("/")
AUTH_URL = os.environ.get("AUTH_URL", "http://localhost:7701").rstrip("/")
# Container names differ between dev (laptop) and the CI export stack (VM):
#   dev: jarvis-command-center-jarvis-voice-api-1 / jarvis-auth-api (local docker)
#   CI:  jarvis-command-center / jarvis-auth       (reached via DOCKER_HOST=ssh://gpu-vm)
CC_CONTAINER = os.environ.get("CC_CONTAINER", "jarvis-command-center-jarvis-voice-api-1")
AUTH_CONTAINER = os.environ.get("AUTH_CONTAINER", "jarvis-auth-api")
SEED_EMAIL = os.environ.get("BENCH_EMAIL", "bench@example.com")
SEED_PASSWORD = os.environ.get("BENCH_PASSWORD", "bench-Password-123")

_GPU_DIR = Path(__file__).resolve().parent
_BEHAVIOR_DIR = _GPU_DIR.parent / "behavior"  # shared tool schemas live here
_DEFAULT_CORPUS = _GPU_DIR / "bench_corpus.cc.yaml"  # expanded benchmark corpus

HEALTH_TIMEOUT_S = float(os.environ.get("HEALTH_TIMEOUT_S", "420"))
REQUEST_TIMEOUT_S = float(os.environ.get("REQUEST_TIMEOUT_S", "90"))

# The benchmark measures the model's tool-routing latency (the /voice/command
# round-trip). A full spoken turn a user actually feels also pays STT + TTS +
# wake/network, which is ~model-independent. VOICE_OVERHEAD_MS estimates that
# constant so we can report an "estimated perceived latency" = routing p50 +
# overhead. Default 1600ms is calibrated to the known ~2.4s fully-local turn
# (routing is ~0.6-0.8s of it). Override per-environment.
VOICE_OVERHEAD_MS = float(os.environ.get("VOICE_OVERHEAD_MS", "1600"))

# model.live.* keys we drive per model; captured + restored.
_LIVE_KEYS = ("name", "backend", "chat_format", "stop_tokens", "context_window")


def log(msg: str) -> None:
    print(f"[bench] {msg}", flush=True)


def die(msg: str) -> None:
    print(f"::error::[bench] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


# --------------------------------------------------------------------------- #
# On-box helpers (ssh)
# --------------------------------------------------------------------------- #
def _ssh(cmd: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", LLM_PROXY_SSH, cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def get_app_creds() -> tuple[str, str]:
    """Read llm-proxy app-to-app creds from the container env (never inlined)."""
    # Single-quote the payload so the container's shell (not the remote login
    # shell, where these vars are empty) expands $JARVIS_APP_ID / $JARVIS_APP_KEY.
    r = _ssh("docker exec %s sh -c 'echo $JARVIS_APP_ID:$JARVIS_APP_KEY'" % API_CONTAINER)
    out = (r.stdout or "").strip()
    if r.returncode != 0 or ":" not in out:
        die(f"could not read app creds from {API_CONTAINER}: {r.stderr.strip()[:200]}")
    app_id, app_key = out.split(":", 1)
    if not app_id or not app_key:
        die("app creds empty")
    return app_id, app_key


def get_gpu_info() -> str:
    """Human-readable GPU description for disclosure (e.g. 'NVIDIA RTX 3080 Ti,
    12288 MiB, driver 580.173.02'). Best-effort — never fatal."""
    r = _ssh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader")
    line = (r.stdout or "").strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
    if not line:
        return "unknown GPU"
    name, mem, driver = [p.strip() for p in line.split(",")]
    return f"{name}, {mem}, driver {driver}"


def restart_model_service() -> None:
    r = _ssh(f"docker restart {MODEL_CONTAINER}", timeout=90)
    if r.returncode != 0:
        die(f"failed to restart {MODEL_CONTAINER}: {r.stderr.strip()[:200]}")


# Containers that also hold VRAM on the dev box — stopped during a run with
# --free-vram so the largest models (9B at 8192 ctx) fit the 12GB card.
VRAM_HOG_CONTAINERS = os.environ.get(
    "VRAM_HOG_CONTAINERS", "jarvis-whisper-api-jarvis-whisper-1,jarvis-tts-jarvis-tts-1"
).split(",")


def _set_containers(action: str) -> None:
    for c in VRAM_HOG_CONTAINERS:
        c = c.strip()
        if c:
            _ssh(f"docker {action} {c}", timeout=60)
    log(f"  {action}ed VRAM-holding containers: {', '.join(VRAM_HOG_CONTAINERS)}")


def model_present(m: BenchModel) -> bool:
    """The gguf_path is relative to .models; resolve against the mounted dir."""
    # .models on the host lives under the llm-proxy repo; check via the container
    # mount (/app/.models) so we don't hard-code the host path.
    rel = m.gguf_path.split(".models/", 1)[-1]
    r = _ssh(f'docker exec {API_CONTAINER} test -f /app/.models/{rel} && echo yes || echo no')
    return (r.stdout or "").strip() == "yes"


# --------------------------------------------------------------------------- #
# llm-proxy settings (direct HTTP from laptop with app creds)
# --------------------------------------------------------------------------- #
class LLMProxy:
    def __init__(self, base: str, app_id: str, app_key: str) -> None:
        self.base = base
        self.h = {"X-Jarvis-App-Id": app_id, "X-Jarvis-App-Key": app_key}

    def get_category(self, category: str) -> dict[str, object]:
        r = requests.get(
            f"{self.base}/settings/", params={"category": category}, headers=self.h, timeout=30
        )
        r.raise_for_status()
        return {s["key"]: s.get("value") for s in r.json().get("settings", [])}

    def put(self, key: str, value: object) -> None:
        r = requests.put(
            f"{self.base}/settings/{key}", headers=self.h, json={"value": value}, timeout=30
        )
        if r.status_code not in (200, 204):
            die(f"PUT {key}={value!r} failed: {r.status_code} {r.text[:200]}")

    def health_status(self) -> str:
        try:
            r = requests.get(f"{self.base}/health", timeout=10)
            return str(r.json().get("status", "")) if r.status_code == 200 else f"http{r.status_code}"
        except requests.RequestException as e:
            return f"err:{type(e).__name__}"


# --------------------------------------------------------------------------- #
# command-center auth + routing (mirrors install-e2e/seed.py + test_behavior.py)
# --------------------------------------------------------------------------- #
def _container_env(container: str, var: str) -> str:
    r = subprocess.run(
        ["docker", "exec", container, "printenv", var], capture_output=True, text=True, timeout=20
    )
    return (r.stdout or "").strip()


def cc_admin_key() -> str:
    return os.environ.get("ADMIN_API_KEY") or _container_env(
        CC_CONTAINER, "ADMIN_API_KEY"
    ) or die("ADMIN_API_KEY not set and not readable from the CC container") or ""


def _auth_admin_token() -> str:
    return os.environ.get("AUTH_ADMIN_TOKEN") or _container_env(
        AUTH_CONTAINER, "JARVIS_AUTH_ADMIN_TOKEN"
    )


def _login() -> tuple[str, str]:
    """Login the bench user, returning (household_id, jwt). Assumes it exists."""
    r = requests.post(
        f"{AUTH_URL}/auth/login", json={"email": SEED_EMAIL, "password": SEED_PASSWORD}, timeout=30
    )
    if r.status_code != 200:
        die(f"login failed: {r.status_code} {r.text[:200]}")
    body = r.json()
    hid = body.get("household_id")
    if not hid:
        hh = requests.get(f"{AUTH_URL}/households", headers={"Authorization": f"Bearer {body['access_token']}"}, timeout=30)
        rows = hh.json() if hh.status_code == 200 else []
        hid = (rows[0]["id"] if isinstance(rows, list) else rows.get("id")) if rows else ""
    return hid or "", body["access_token"]


def get_superuser() -> tuple[str, str]:
    """Return (household_id, superuser_jwt).

    CI / fresh stack: /auth/setup mints the first superuser directly. Existing
    stack (local dev, where a real superuser already owns setup): register a
    dedicated bench user, promote it via the auth admin token, then log in for a
    JWT that carries is_superuser=true.
    """
    setup = requests.post(
        f"{AUTH_URL}/auth/setup", json={"email": SEED_EMAIL, "password": SEED_PASSWORD}, timeout=30
    )
    if setup.status_code in (200, 201):
        body = setup.json()
        return body["household_id"], body["access_token"]

    # Existing stack — bootstrap a bench superuser.
    admin_tok = _auth_admin_token()
    if not admin_tok:
        die("AUTH_ADMIN_TOKEN not set and not readable from jarvis-auth container")
    reg = requests.post(
        f"{AUTH_URL}/auth/register", json={"email": SEED_EMAIL, "password": SEED_PASSWORD}, timeout=30
    )
    if reg.status_code in (200, 201):
        user_id = reg.json()["user"]["id"]
    else:  # already registered — look it up
        lookup = requests.get(
            f"{AUTH_URL}/admin/users/by-email/{SEED_EMAIL}",
            headers={"X-Jarvis-Admin-Token": admin_tok},
            timeout=30,
        )
        if lookup.status_code != 200:
            die(f"could not resolve bench user: {lookup.status_code} {lookup.text[:200]}")
        user_id = lookup.json()["id"]

    promote = requests.put(
        f"{AUTH_URL}/admin/users/{user_id}/superuser",
        headers={"X-Jarvis-Admin-Token": admin_tok},
        json={"is_superuser": True},
        timeout=30,
    )
    if promote.status_code != 200:
        die(f"superuser promotion failed: {promote.status_code} {promote.text[:200]}")
    # Fresh login so the JWT carries is_superuser=true.
    return _login()


def seed_creds() -> tuple[str, str, str]:
    """Return (household_id, superuser_jwt, node_creds="node_id:node_key").
    Registers a fresh node each run so registration always returns a usable key."""
    household_id, jwt = get_superuser()
    node_id = f"bench-node-{os.urandom(4).hex()}"
    reg = requests.post(
        f"{CC_URL}/api/v0/admin/nodes",
        headers={"X-API-Key": cc_admin_key()},
        json={"node_id": node_id, "household_id": household_id, "room": "bench", "name": "Bench Node"},
        timeout=30,
    )
    if reg.status_code not in (200, 201):
        die(f"node registration failed: {reg.status_code} {reg.text[:200]}")
    return household_id, jwt, f"{node_id}:{reg.json()['node_key']}"


def get_cc_interface(jwt: str) -> str:
    r = requests.get(
        f"{CC_URL}/settings/llm.interface", headers={"Authorization": f"Bearer {jwt}"}, timeout=30
    )
    if r.status_code == 200:
        body = r.json()
        return str(body.get("value", body)) if isinstance(body, dict) else str(body)
    return ""


def set_cc_interface(jwt: str, provider: str) -> None:
    h = {"Authorization": f"Bearer {jwt}"}
    r = requests.put(f"{CC_URL}/settings/llm.interface", headers=h, json={"value": provider}, timeout=30)
    if r.status_code not in (200, 204):
        die(f"set llm.interface={provider} failed: {r.status_code} {r.text[:200]}")
    requests.post(f"{CC_URL}/settings/invalidate-cache", headers=h, timeout=30)


# --------------------------------------------------------------------------- #
# Corpus + matcher (verbatim from the canonical behavior lanes)
# --------------------------------------------------------------------------- #
def _load_yaml(name: str) -> list:
    with (_BEHAVIOR_DIR / name).open() as fh:
        return yaml.safe_load(fh) or []


def _load_corpus(path: Path) -> list:
    with path.open() as fh:
        return yaml.safe_load(fh) or []


def _as_number(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _check_arg(name: str, matcher: dict, args: dict) -> str | None:
    if name not in args:
        return f"arg {name!r} missing (got {sorted(args)})"
    value = args[name]
    sval = str(value).strip().lower()
    if "equals" in matcher:
        expected = matcher["equals"]
        num_v, num_e = _as_number(value), _as_number(expected)
        if num_v is not None and num_e is not None:
            if num_v != num_e:
                return f"{name}={value!r} != equals {expected!r}"
        elif sval != str(expected).strip().lower():
            return f"{name}={value!r} != equals {expected!r}"
    if "contains" in matcher and str(matcher["contains"]).strip().lower() not in sval:
        return f"{name}={value!r} does not contain {matcher['contains']!r}"
    if "in" in matcher:
        opts = [str(o).strip().lower() for o in matcher["in"]]
        if sval not in opts:
            return f"{name}={value!r} not in {matcher['in']!r}"
    if "any_of" in matcher:
        opts = [str(o).strip().lower() for o in matcher["any_of"]]
        if not any(o in sval for o in opts):
            return f"{name}={value!r} contains none of {matcher['any_of']!r}"
    return None


def _args_ok(entry: dict, args: dict) -> bool:
    for arg_name, matcher in (entry.get("args") or {}).items():
        if _check_arg(arg_name, matcher, args) is not None:
            return False
    return True


def route(node_creds: str, tools: list, conv_id: str, utterance: str) -> tuple[str | None, dict, float, str | None]:
    """Open a conversation with CC's real tools, send one utterance, return
    (chosen_tool | None, parsed_args, latency_s, stop_reason)."""
    headers = {"X-API-Key": node_creds}
    start = requests.post(
        f"{CC_URL}/api/v0/conversation/start",
        headers=headers,
        json={"conversation_id": conv_id, "client_tools": tools, "available_commands": [], "skip_warmup_inference": True},
        timeout=REQUEST_TIMEOUT_S,
    )
    if start.status_code != 200:
        raise RuntimeError(f"/conversation/start {start.status_code}: {start.text[:200]}")

    t0 = time.perf_counter()
    resp = requests.post(
        f"{CC_URL}/api/v0/voice/command",
        headers=headers,
        json={"voice_command": utterance, "conversation_id": conv_id},
        timeout=REQUEST_TIMEOUT_S,
    )
    latency_s = time.perf_counter() - t0
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"/voice/command {resp.status_code}: {resp.text[:200]}")
    body = resp.json()
    stop_reason = body.get("stop_reason")
    tool_calls = body.get("tool_calls") or []
    if not tool_calls:
        return None, {}, latency_s, stop_reason
    fn = tool_calls[0].get("function", {})
    raw = fn.get("arguments")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            parsed = {}
    else:
        parsed = raw if isinstance(raw, dict) else {}
    return fn.get("name"), parsed, latency_s, stop_reason


# --------------------------------------------------------------------------- #
# Model swap
# --------------------------------------------------------------------------- #
def swap_model(proxy: LLMProxy, m: BenchModel) -> float:
    """Point llm-proxy's live slot at model m, reload, and wait until healthy.
    Returns load time in seconds, or -1.0 if the model never became healthy
    within the timeout (e.g. VRAM OOM) — the caller skips it rather than aborting
    the whole sweep. Background is assumed already blanked so it follows live
    (single shared load on the 12GB card)."""
    proxy.put("model.live.name", m.gguf_path)
    proxy.put("model.live.backend", m.backend)
    proxy.put("model.live.chat_format", m.chat_format)
    proxy.put("model.live.stop_tokens", m.stop_tokens)
    proxy.put("model.live.context_window", m.context_window)

    log(f"  reloading model service for {m.key} ...")
    t0 = time.perf_counter()
    restart_model_service()

    # Poll the API health body until the live slot reports healthy (200 +
    # status=="healthy"); "initializing" means the GGUF is still loading.
    deadline = t0 + HEALTH_TIMEOUT_S
    last = ""
    while time.perf_counter() < deadline:
        st = proxy.health_status()
        if st != last:
            log(f"    health: {st}")
            last = st
        if st == "healthy":
            return time.perf_counter() - t0
        time.sleep(3)
    log(f"  !! {m.key} never became healthy within {HEALTH_TIMEOUT_S:.0f}s (last={last}) — SKIPPING")
    return -1.0


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score(m: BenchModel, load_time_s: float, corpus: list, results: list[dict]) -> dict:
    positives = [(e, r) for e, r in zip(corpus, results) if e.get("tool") is not None]
    negatives = [(e, r) for e, r in zip(corpus, results) if e.get("tool") is None]

    tool_correct = sum(1 for e, r in positives if r["chosen"] == e["tool"])
    exact = sum(1 for e, r in positives if r["chosen"] == e["tool"] and r["args_ok"])
    # arg accuracy conditioned on correct tool selection
    correct_tool = [(e, r) for e, r in positives if r["chosen"] == e["tool"]]
    arg_correct = sum(1 for e, r in correct_tool if r["args_ok"])
    fired_on_negative = sum(1 for _, r in negatives if r["chosen"] is not None)

    lats = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]
    lat_stats = {}
    if lats:
        s = sorted(lats)
        lat_stats = {
            "p50": round(statistics.median(s), 1),
            "p95": round(s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))], 1),
            "mean": round(statistics.fmean(s), 1),
            "min": round(s[0], 1),
            "max": round(s[-1], 1),
        }

    # per-category (keyed on expected tool)
    per_cat: dict[str, dict] = {}
    for e, r in positives:
        cat = e["tool"]
        c = per_cat.setdefault(cat, {"n": 0, "tool_ok": 0, "args_ok": 0})
        c["n"] += 1
        if r["chosen"] == cat:
            c["tool_ok"] += 1
            if r["args_ok"]:
                c["args_ok"] += 1
    for c in per_cat.values():
        c["tool_acc"] = round(c["tool_ok"] / c["n"], 3) if c["n"] else 0.0
        c["arg_acc"] = round(c["args_ok"] / c["tool_ok"], 3) if c["tool_ok"] else 0.0

    # Estimated perceived latency: routing p50 + the ~constant STT+TTS+wake
    # overhead a full spoken turn pays. This is what a user actually feels.
    perceived_ms = round(lat_stats["p50"] + VOICE_OVERHEAD_MS, 0) if lat_stats else None

    n_pos, n_neg = len(positives), len(negatives)
    overall = (exact + (n_neg - fired_on_negative)) / (n_pos + n_neg) if (n_pos + n_neg) else 0.0
    return {
        "key": m.key,
        "display": m.display,
        "family": m.family,
        "cc_provider": m.cc_provider,
        "gguf_path": m.gguf_path,
        "load_time_s": round(load_time_s, 1),
        "n_total": n_pos + n_neg,
        "n_positive": n_pos,
        "n_negative": n_neg,
        "tool_accuracy": round(tool_correct / n_pos, 3) if n_pos else 0.0,
        "arg_accuracy": round(arg_correct / len(correct_tool), 3) if correct_tool else 0.0,
        "exact_match": round(exact / n_pos, 3) if n_pos else 0.0,
        "false_positive_rate": round(fired_on_negative / n_neg, 3) if n_neg else 0.0,
        "negative_accuracy": round((n_neg - fired_on_negative) / n_neg, 3) if n_neg else 0.0,
        "overall_accuracy": round(overall, 3),
        "latency_ms": lat_stats,
        "perceived_latency_ms": perceived_ms,
        "per_category": per_cat,
        "per_utterance": results,
    }


def run_corpus(node_creds: str, tools: list, corpus: list, warmup: bool) -> list[dict]:
    if warmup:
        try:
            route(node_creds, tools, "bench-warmup", corpus[0]["utterance"])
            log("    warmup ok")
        except Exception as e:  # noqa: BLE001 - warmup is best-effort
            log(f"    warmup failed (continuing): {e}")

    out: list[dict] = []
    for i, entry in enumerate(corpus):
        utterance = entry["utterance"]
        try:
            chosen, args, latency_s, stop_reason = route(node_creds, tools, f"bench-{i:03d}", utterance)
            expected = entry.get("tool")
            correct_tool = (chosen == expected) if expected is not None else (chosen is None)
            args_ok = _args_ok(entry, args) if (expected is not None and chosen == expected) else False
            out.append({
                "utterance": utterance,
                "expected": expected,
                "chosen": chosen,
                "args": args,
                "correct_tool": correct_tool,
                "args_ok": args_ok,
                "latency_ms": round(latency_s * 1000, 1),
                "stop_reason": stop_reason,
            })
            mark = "ok " if correct_tool and (expected is None or args_ok) else ("~  " if correct_tool else "MISS")
            log(f"    [{i + 1:2d}/{len(corpus)}] {mark} {latency_s * 1000:6.0f}ms  {utterance[:44]!r} -> {chosen}")
        except Exception as e:  # noqa: BLE001 - record the failure, keep going
            out.append({
                "utterance": utterance,
                "expected": entry.get("tool"),
                "chosen": None,
                "args": {},
                "correct_tool": False,
                "args_ok": False,
                "latency_ms": None,
                "stop_reason": None,
                "error": str(e)[:200],
            })
            log(f"    [{i + 1:2d}/{len(corpus)}] ERR  {utterance[:44]!r}: {e}")
    return out


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def markdown_table(summaries: list[dict]) -> str:
    rows = [
        "| Model | Provider | Tool acc | Arg acc | Exact | FP rate | Routing p50 | p95 | Est. perceived | Load |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for s in summaries:
        lat = s.get("latency_ms") or {}
        perceived = s.get("perceived_latency_ms")
        perceived_str = f"~{perceived / 1000:.1f}s" if perceived else "-"
        rows.append(
            f"| {s['display']} | {s['cc_provider']} | {s['tool_accuracy']:.0%} | "
            f"{s['arg_accuracy']:.0%} | {s['exact_match']:.0%} | {s['false_positive_rate']:.0%} | "
            f"{lat.get('p50', '-')}ms | {lat.get('p95', '-')}ms | {perceived_str} | {s['load_time_s']}s |"
        )
    return "\n".join(rows)


def emit(summaries: list[dict], out_path: Path, corpus_size: int, gpu: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).isoformat()
    doc = {
        "generated_at": generated,
        "corpus_size": corpus_size,
        "gpu": gpu,
        "voice_overhead_ms": VOICE_OVERHEAD_MS,
        "llm_proxy_url": LLM_PROXY_URL,
        "models": summaries,
    }
    out_path.write_text(json.dumps(doc, indent=2))
    log(f"wrote {out_path}")

    table = markdown_table(summaries)
    caption = (
        f"_Voice-command tool-routing across {len(summaries)} local models, "
        f"{corpus_size} canned utterances, through command-center's real "
        f"`/voice/command` path. GPU: **{gpu}**. "
        f"“Est. perceived” = routing p50 + ~{VOICE_OVERHEAD_MS / 1000:.1f}s STT+TTS. "
        f"Generated {generated[:10]}._"
    )
    print("\n" + table + "\n\n" + caption + "\n")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as f:
            f.write(f"\n### Voice-command model benchmark\n\n{table}\n\n{caption}\n")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", default="", help="comma-separated model keys (default: all present)")
    ap.add_argument("--limit", type=int, default=0, help="limit corpus to first N utterances (smoke)")
    ap.add_argument("--out", default="results/bench.json", help="output JSON path")
    ap.add_argument("--corpus", default="", help=f"corpus YAML path (default: {_DEFAULT_CORPUS.name})")
    ap.add_argument("--no-warmup", action="store_true", help="skip the per-model warmup request")
    ap.add_argument("--no-restore", action="store_true", help="leave the box on the last benchmarked model")
    ap.add_argument("--free-vram", action="store_true", help="stop whisper/tts during the run so 9B models fit the 12GB dev box")
    args = ap.parse_args()

    tools = _load_yaml("tools.cc.yaml")
    corpus_path = Path(args.corpus) if args.corpus else _DEFAULT_CORPUS
    if not corpus_path.exists():
        corpus_path = _BEHAVIOR_DIR / "corpus.cc.yaml"  # fall back to the 29-entry gate
    corpus = _load_corpus(corpus_path)
    if not tools or not corpus:
        die("failed to load corpus/tools")
    log(f"using corpus: {corpus_path}")
    if args.limit:
        corpus = corpus[: args.limit]
    log(f"corpus: {len(corpus)} utterances, {len(tools)} tools")

    wanted = [k.strip() for k in args.models.split(",") if k.strip()]
    models = [m for m in BENCH_MODELS if not wanted or m.key in wanted]
    if not models:
        die(f"no models matched {wanted!r}")

    app_id, app_key = get_app_creds()
    proxy = LLMProxy(LLM_PROXY_URL, app_id, app_key)
    gpu = get_gpu_info()
    log(f"GPU: {gpu}")

    # Capture originals for restore.
    orig_live = proxy.get_category("model.live")
    orig_bg = proxy.get_category("model.background")
    _, jwt, node_creds = seed_creds()
    orig_iface = get_cc_interface(jwt)
    log(f"captured originals: live.name={orig_live.get('model.live.name')!r} iface={orig_iface!r}")

    # Blank background once so it follows live (single shared load on 12GB).
    proxy.put("model.background.name", "")

    # Filter to models actually present on the box (no silent skips).
    present, absent = [], []
    for m in models:
        (present if model_present(m) else absent).append(m)
    if absent:
        log(f"SKIP (not on box yet): {', '.join(m.key for m in absent)}")
    if not present:
        die("none of the requested models are present on the box")

    if args.free_vram:
        _set_containers("stop")

    summaries: list[dict] = []
    try:
        for m in present:
            log(f"=== {m.key} ({m.display}) provider={m.cc_provider} ===")
            load_time = swap_model(proxy, m)
            if load_time < 0:
                continue  # never became healthy (likely OOM); skip, keep sweeping
            log(f"  loaded in {load_time:.1f}s; setting CC provider {m.cc_provider}")
            set_cc_interface(jwt, m.cc_provider)
            results = run_corpus(node_creds, tools, corpus, warmup=not args.no_warmup)
            s = score(m, load_time, corpus, results)
            summaries.append(s)
            log(
                f"  => tool={s['tool_accuracy']:.0%} arg={s['arg_accuracy']:.0%} "
                f"exact={s['exact_match']:.0%} fp={s['false_positive_rate']:.0%} "
                f"p50={ (s['latency_ms'] or {}).get('p50','-')}ms"
            )
    finally:
        if args.free_vram:
            _set_containers("start")
        if not args.no_restore:
            log("restoring original model + provider settings ...")
            try:
                for k in _LIVE_KEYS:
                    if f"model.live.{k}" in orig_live:
                        proxy.put(f"model.live.{k}", orig_live[f"model.live.{k}"])
                if "model.background.name" in orig_bg:
                    proxy.put("model.background.name", orig_bg["model.background.name"])
                if orig_iface:
                    set_cc_interface(jwt, orig_iface)
                restart_model_service()
                log("restore: reload issued")
            except Exception as e:  # noqa: BLE001
                log(f"restore failed (manual check needed): {e}")

    emit(summaries, Path(args.out), len(corpus), gpu)


if __name__ == "__main__":
    main()
