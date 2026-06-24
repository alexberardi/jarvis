#!/usr/bin/env python3
"""Idempotently apply loop-v2 agent changes to ~/.openclaw/openclaw.json.

- Upserts agents: engineering (update), qa (add), coding-agent (add), qa-executor (update).
- Sets each one's tools profile (VERIFIED-FACTS) + systemPromptOverride (read from a sysprompt dir).
- Upserts slack bindings for qa + coding-agent.
- Leaves main/product/marketing/doc-expert/install-expert/qa-author untouched.
- Backs up to openclaw.json.bak-pre-loopv2-<ts> first; validates JSON round-trips.

Usage: python3 apply_openclaw_config.py <sysprompt_dir> <iso_ts>
  sysprompt_dir: dir holding engineering.txt qa.txt coding-agent.txt qa-executor.txt
  iso_ts: a timestamp string for the backup filename (the Pi has no Date.now in this harness; pass one)
"""
import json, os, sys, shutil

CFG = "/home/pi/.openclaw/openclaw.json"
MODEL = "anthropic/claude-opus-4-7"

CHANNELS = {"qa": "C0B3WKBPSJ3", "coding-agent": "C0B4C0W5WHY",
            "engineering": "C0B4C4XJ9L1", "qa-executor": "C0B4DQL8SF4"}

TOOLS = {
    "engineering": {"profile": "full", "deny": [
        "group:runtime", "write", "edit", "apply_patch",
        "github-ro__*", "github-code__*", "github-code-ro__*"]},
    "qa": {"profile": "full", "deny": [
        "group:runtime", "write", "edit", "apply_patch",
        "github-ro__*", "github-code__*", "github-code-ro__*",
        "github-rw__create_issue", "github-rw__issue_write",
        "github-rw__add_labels_to_issue", "github-rw__remove_label_from_issue",
        "github-rw__remove_label"]},
    "coding-agent": {"profile": "full", "deny": [
        "github-ro__*", "github-code-ro__*",
        "github-rw__create_issue", "github-rw__issue_write",
        "github-rw__add_labels_to_issue", "github-rw__remove_label_from_issue",
        "github-rw__remove_label",
        "github-code__merge_pull_request", "github-code__update_pull_request",
        "github-code__push_files", "github-code__create_or_update_file",
        "github-code__delete_file"]},
    "qa-executor": {"profile": "full", "deny": [
        "group:runtime", "write", "edit", "apply_patch", "github-ro__*",
        "github-rw__create_issue", "github-rw__issue_write",
        "github-rw__add_labels_to_issue", "github-rw__remove_label_from_issue",
        "github-rw__remove_label"]},
}

# (id, mode): mode "add" inserts if missing, "update" requires it to already exist.
PLAN = [("engineering", "update"), ("qa", "add"),
        ("coding-agent", "add"), ("qa-executor", "update")]


def load_sysprompt(d, agent_id):
    p = os.path.join(d, f"{agent_id}.txt")
    with open(p) as f:
        return f.read().rstrip("\n") + "\n" if False else f.read()


def upsert_agent(cfg, agent_id, mode, sysprompt_dir):
    lst = cfg["agents"]["list"]
    idx = next((i for i, a in enumerate(lst) if isinstance(a, dict) and a.get("id") == agent_id), None)
    obj = {
        "id": agent_id,
        "name": agent_id,
        "workspace": f"/home/pi/.openclaw/workspaces/{agent_id}",
        "agentDir": f"/home/pi/.openclaw/agents/{agent_id}/agent",
        "model": MODEL,
        "systemPromptOverride": load_sysprompt(sysprompt_dir, agent_id),
        "tools": TOOLS[agent_id],
    }
    if idx is None:
        if mode == "update":
            raise SystemExit(f"ERROR: expected existing agent '{agent_id}' to update, not found")
        lst.append(obj)
        return "added"
    else:
        # preserve any extra keys the live object had, but force our managed fields
        merged = dict(lst[idx])
        merged.update(obj)
        lst[idx] = merged
        return "updated"


def upsert_binding(cfg, agent_id):
    ch = CHANNELS[agent_id]
    bindings = cfg.setdefault("bindings", [])
    for b in bindings:
        if b.get("agentId") == agent_id:
            b["match"] = {"channel": "slack", "accountId": "default",
                          "peer": {"kind": "channel", "id": ch}}
            return "binding-updated"
    bindings.append({
        "type": "route", "agentId": agent_id,
        "match": {"channel": "slack", "accountId": "default",
                  "peer": {"kind": "channel", "id": ch}},
        "comment": f"{agent_id} persona — DM in #{agent_id}-bot routes here",
    })
    return "binding-added"


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: apply_openclaw_config.py <sysprompt_dir> <iso_ts>")
    sysprompt_dir, ts = sys.argv[1], sys.argv[2]
    with open(CFG) as f:
        raw = f.read()
    cfg = json.loads(raw)

    bak = f"{CFG}.bak-pre-loopv2-{ts}"
    shutil.copy2(CFG, bak)
    print(f"backup -> {bak}")

    for agent_id, mode in PLAN:
        action = upsert_agent(cfg, agent_id, mode, sysprompt_dir)
        print(f"agent {agent_id}: {action}")
    for agent_id in ("qa", "coding-agent"):
        print(f"binding {agent_id}: {upsert_binding(cfg, agent_id)}")

    out = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    # round-trip validate
    json.loads(out)
    with open(CFG, "w") as f:
        f.write(out)

    names = [a.get("id") for a in cfg["agents"]["list"] if isinstance(a, dict)]
    print("agents.list now:", names)
    binds = [(b.get("agentId"), b.get("match", {}).get("peer", {}).get("id")) for b in cfg.get("bindings", [])]
    print("bindings now:", binds)
    print("OK")


if __name__ == "__main__":
    main()
