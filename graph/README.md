# Knowledge graph of the live repos

A [graphify](https://github.com/Graphify-Labs/graphify) graph of the nine repos that are still live:
jarvis-server, jarvis-node-mobile, jarvis-loop, jarvis-pantry, jarvis-pantry-web, jarvis-pantry-runner,
jarvis-notifications, jarvis-docs and jarvis-installer. The commits it was built from are in
`repos.txt`. The legacy Python services (`-server`, `-api`, `-service`) and `jarvis-host-agent*` are
deliberately left out.

Built 2026-10-24 from code (structural, free) and all 781 docs (LLM extraction, about 5.4M tokens).
Images and audio are not in it. 41,035 nodes, 168,100 edges, 1,233 communities; community names are
generated from each one's package path and its most-connected node.

| File | What |
|---|---|
| `GRAPH_REPORT.md` | the audit report: god nodes, surprising connections, communities |
| `graph.html` | interactive view, aggregated by community (open in a browser) |
| `graph.json.gz` | the graph itself |
| `cache/semantic/` | the doc extraction cache: the expensive part, so an update only re-reads changed docs |
| `labels.json`, `manifest.json`, `cost.json` | community names, per-file hashes for `--update`, token cost |

## Restore and query

```bash
uv tool install graphifyy
mkdir -p ~/jarvis-graph && cd ~/jarvis-graph
while read -r r sha; do
  git clone -q https://github.com/alexberardi/$r.git "$r" && git -C "$r" checkout -q "$sha"
done < ~/jarvis/graph/repos.txt
mkdir -p graphify-out/cache
cp -r ~/jarvis/graph/cache/semantic graphify-out/cache/
cp ~/jarvis/graph/{GRAPH_REPORT.md,graph.html,manifest.json,cost.json} graphify-out/
cp ~/jarvis/graph/labels.json graphify-out/.graphify_labels.json
gunzip -c ~/jarvis/graph/graph.json.gz > graphify-out/graph.json
ln -sfn ~/jarvis-graph/graphify-out ~/jarvis/graphify-out
graphify query "how does the desktop agent register its tools"
```

## Refresh

Pull each clone (or check out new commits), then from `~/jarvis-graph` run `/graphify . --update` in
Claude Code. Code is re-parsed for free and only changed docs are sent to the model. Copy the outputs
back here, update `repos.txt`, and commit.
