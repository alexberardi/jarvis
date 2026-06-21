"""Phase 2 — CC behavior routing through the REAL stack against a cloud model.

Routes a voice-command corpus through command-center's real ChatGPTOpenAI native
tool-calling path → llm-proxy (REST backend) → gpt-4.1-nano, asserting each
utterance picks the correct tool with sensible arguments. This is the "does the
feature actually work" signal — the wrong-tool / answers-the-literal-question
class of regression — running against the INSTALLER-GENERATED stack.

Pipeline (no real node device needed — the chosen tool comes back synchronously
in the /voice/command response body):
    POST /api/v0/conversation/start (client_tools = tools.cc.yaml)
    POST /api/v0/voice/command      (the utterance)
      → ChatGPTOpenAI (supports_native_tools) → llm-proxy model="live"
      → REST backend → OpenAI gpt-4.1-nano → structured tool_calls

Gated: skipped unless OPENAI_API_KEY is set (real model) AND the seed exported
node creds (CC_NODE_ID/KEY). Corpus + matcher are vendored from
jarvis-integration-tests/tests/behavior (the canonical T6b lane); keep in sync.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import requests
import yaml

CC_URL = os.environ.get("CC_URL", "http://localhost:7703").rstrip("/")
CC_NODE_ID = os.environ.get("CC_NODE_ID", "")
CC_NODE_KEY = os.environ.get("CC_NODE_KEY", "")
HAS_KEY = bool(os.environ.get("OPENAI_API_KEY"))

SKIP_NO_KEY = "OPENAI_API_KEY unset — behavior lane needs a real cloud model"
SKIP_NO_NODE = "CC_NODE_ID/CC_NODE_KEY unset — run seed.py first"

_BEHAVIOR_DIR = Path(__file__).parent / "behavior"


def _load_yaml(name: str) -> list:
    with (_BEHAVIOR_DIR / name).open() as fh:
        return yaml.safe_load(fh) or []


TOOLS = _load_yaml("tools.cc.yaml")
CORPUS = _load_yaml("corpus.cc.yaml")

pytestmark = [
    pytest.mark.skipif(not HAS_KEY, reason=SKIP_NO_KEY),
    pytest.mark.skipif(not (CC_NODE_ID and CC_NODE_KEY), reason=SKIP_NO_NODE),
]


# Matcher engine — ported verbatim from the canonical behavior lanes so all three
# (llm-proxy, jarvis-integration-tests, install-e2e) share identical semantics.
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


def _node_headers() -> dict:
    return {"X-API-Key": f"{CC_NODE_ID}:{CC_NODE_KEY}"}


def _parse_arguments(raw: object) -> dict:
    if isinstance(raw, str):
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _route_through_cc(conv_id: str, utterance: str) -> tuple[str | None, dict, dict]:
    start = requests.post(
        f"{CC_URL}/api/v0/conversation/start",
        headers=_node_headers(),
        json={
            "conversation_id": conv_id,
            "client_tools": TOOLS,
            "available_commands": [],
            "skip_warmup_inference": True,
        },
        timeout=60,
    )
    assert start.status_code == 200, (
        f"/conversation/start failed: {start.status_code} {start.text[:300]}"
    )
    resp = requests.post(
        f"{CC_URL}/api/v0/voice/command",
        headers=_node_headers(),
        json={"voice_command": utterance, "conversation_id": conv_id},
        timeout=60,
    )
    assert resp.status_code in (200, 202), (
        f"/voice/command failed: {resp.status_code} {resp.text[:400]}"
    )
    body = resp.json()
    tool_calls = body.get("tool_calls") or []
    if not tool_calls:
        return None, {}, body
    fn = tool_calls[0].get("function", {})
    return fn.get("name"), _parse_arguments(fn.get("arguments")), body


def test_corpus_and_tools_loaded() -> None:
    assert TOOLS, "tools.cc.yaml failed to load"
    assert CORPUS, "corpus.cc.yaml failed to load"
    tool_names = {t["function"]["name"] for t in TOOLS}
    for entry in CORPUS:
        expected = entry.get("tool")
        assert expected is None or expected in tool_names, (
            f"corpus references unknown tool {expected!r} (have {sorted(tool_names)})"
        )


@pytest.mark.parametrize(
    "idx, entry", list(enumerate(CORPUS)), ids=[e["utterance"] for e in CORPUS]
)
def test_utterance_routes_through_cc(idx: int, entry: dict) -> None:
    utterance = entry["utterance"]
    expected_tool = entry.get("tool")
    chosen, args, body = _route_through_cc(f"ci-behavior-{idx:03d}", utterance)
    stop_reason = body.get("stop_reason")

    if expected_tool is None:
        assert chosen is None, (
            f"{utterance!r}: expected NO tool, CC routed to {chosen!r} "
            f"args={args!r} (stop_reason={stop_reason!r})"
        )
        assert stop_reason != "tool_calls", (
            f"{utterance!r}: expected non-tool stop_reason, got {stop_reason!r}"
        )
        return

    assert chosen is not None, (
        f"{utterance!r}: no tool call (stop_reason={stop_reason!r}, "
        f"msg={body.get('assistant_message')!r})"
    )
    assert chosen == expected_tool, f"{utterance!r} → {chosen!r}, expected {expected_tool!r}"
    for arg_name, matcher in (entry.get("args") or {}).items():
        err = _check_arg(arg_name, matcher, args)
        assert err is None, f"{utterance!r} → {chosen}: {err}"
