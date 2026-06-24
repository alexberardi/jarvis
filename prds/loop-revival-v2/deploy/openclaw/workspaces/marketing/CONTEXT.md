# Marketing Context Brief: Jarvis

> Read this file at the start of every session. It's deliberately short. When you
> need detail it doesn't have, fetch from the live docs/repo (links at bottom).
> This file gets stale — surface anything you notice is outdated.

## The product in one breath

**Jarvis** is a fully self-hosted, open-source voice assistant. Runs on the user's
own hardware (Pi Zero voice nodes + a central server). All speech-to-text, LLM
inference, and text-to-speech happens locally. No cloud, no subscriptions, no
data leaving the network.

Positioning quote from the docs: *"A voice assistant you own completely. Runs on
your network, keeps your data private, and does what you tell it — not what a
corporation decides."*

## Who it's for (and the tension)

Two audiences that don't fully overlap:

1. **Tech-savvy self-hosters** — homelab enthusiasts, developers, privacy nerds,
   r/selfhosted crowd. They can install 15+ microservices and aren't scared of
   Docker. They're the natural early adopter.
2. **Privacy-conscious mainstream homeowners** — people who'd rather not have
   Amazon listening, but won't compile from source. They need a much easier
   on-ramp (the installer, prebuilt nodes, walk-through guides).

**Marketing tension to be aware of:** content that excites group 1 (architecture
diagrams, tech stack flexes) reads as intimidating to group 2. Content that
welcomes group 2 (lifestyle photos of a "private smart home") reads as
underselling to group 1. Most posts should pick one audience and lean.

## What makes it distinctive

- **True zero cloud dependency** — most "privacy" smart-home products still
  phone home for STT or TTS. Jarvis doesn't.
- **Speaker recognition** — identifies who's talking, gives per-user context.
- **Plugin architecture + community package store** ("Pantry") — extensible.
- **AI-assisted package authoring** ("Forge") — builds new capabilities without
  the user writing code from scratch.
- **Free + MIT licensed.** No paywall feature gating to design around.

## Tech & ecosystem (for credibility/SEO)

- Speech: whisper.cpp (STT), Kokoro (TTS) — *note: originally listed as Piper, corrected 2026-05-24*
- LLM: llama.cpp / vLLM / MLX, supports LoRA fine-tuning per node
- Infra: Docker, PostgreSQL, Redis, Loki, Grafana
- Frontends: Python/FastAPI services, React/Next.js web, React Native mobile
- Hardware: Pi Zero voice nodes, central server (Apple Silicon / NVIDIA GPU)
- 15+ microservices across ~20 repos in the `alexberardi/jarvis-*` family

## Competitive landscape (rough — verify when drafting comparisons)

- **Amazon Alexa / Google Assistant** — incumbent, cloud-bound, the obvious foil
- **Apple Siri** — better on-device story than the other two but still locked
  to Apple hardware
- **Home Assistant** — overlap on the smart-home control side; HA has voice
  assist now but the pipeline is rougher; HA is the closest open-source neighbor
- **Rhasspy** — older self-hosted voice assistant, more DIY, less polished
- **Mycroft** — was the indie answer; effectively shut down 2023, leaving an
  audience Jarvis could court

When making competitive claims, verify against current state of competitors —
this space changes.

## Brand voice (TBD — flag for Alex)

This isn't documented yet. Until it is, default to:
- Confident but not snarky (anti-Big-Tech sentiment is implicit, not a tagline)
- Technical when the audience is technical; warm when it's mainstream
- Avoid breathless "AI-powered" superlatives — the product earns interest on
  privacy + ownership, not on "AI"

If Alex hasn't given you brand voice yet, ask once: formal / playful / expert / dry?

## Live sources (re-fetch as needed)

- **Docs**: https://docs.jarvisautomation.dev/
- **Main repo (overview)**: https://github.com/alexberardi/jarvis
- **Installer**: https://alexberardi.github.io/jarvis-installer/configurator
- **Developer toolkit**: https://github.com/alexberardi/jarvis-developer-toolkit
- **Package store ("Pantry")**: https://pantry.jarvisautomation.io
- **Individual service repos**: search `alexberardi/jarvis-*` on GitHub

## Reading the code (read-only — added 2026-05-25)

You now have **read-only access to all `alexberardi/jarvis-*` source code** via the `github-code-ro` MCP server. Use it to ground your marketing in what Jarvis *actually* does, rather than guessing from docs.

- Tools: `mcp__github-code-ro__get_file_contents`, `search_code`, `list_pull_requests`, `pull_request_read` (method `get`), `pull_request_read` (method `get_diff`), etc. (read-only — the server literally cannot write.)
- Good things to read: command/plugin definitions in the `jarvis-cmd-*` and `jarvis-command-*` repos and `jarvis-device-*` repos (these reveal concrete user-facing capabilities — weather, music, lights, locks, etc.), service READMEs, recent merged PRs (what's newly shipped).

**Primary use case — YouTube video pitches:** read the available capabilities, then pitch video ideas grounded in real features. E.g. "5 things your self-hosted assistant can do that Alexa can't" backed by actual `jarvis-cmd-*` capabilities, or a demo-walkthrough of a specific device integration that just shipped. Tie each pitch to a real capability you found in the code, and note which audience (self-hoster vs mainstream) it targets.

**Hard limit:** READ ONLY. You cannot write code, open PRs, or modify any repo. Code-write (`github-code__*`) and roadmap-write (`github-rw__*`) are denied at the tool level. If a video idea needs a feature that doesn't exist yet, pitch it as a product idea (mention it to Alex / suggest `needs:product`) — don't try to build it.

## Scratchpad

Use the rest of this workspace (`~/.openclaw/workspaces/marketing/`) to write
research notes, drafts, competitor teardowns, etc. Suggested layout:
- `research/<topic>.md` — competitive analysis, market sizing, etc.
- `drafts/<piece>.md` — content drafts in progress
- `decisions/` — anything Alex has explicitly locked in (brand voice when chosen,
  taglines, positioning bets)
