<p align="center">
  <img src="logo.png" alt="Jarvis Automation" width="600" />
</p>

<p align="center">
  <strong>A private voice assistant that runs on your own computer, not someone else's cloud.</strong><br>
  One program, <code>jarvisd</code>, on a Mac, a Windows PC or a Linux machine runs all of Jarvis: speech recognition, the language model, text-to-speech and speaker recognition, on your network.
</p>

<p align="center">
  <a href="https://installer.jarvisautomation.io"><strong>Download</strong></a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="https://docs.jarvisautomation.dev"><strong>Docs</strong></a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="https://github.com/alexberardi/jarvis-server">jarvis-server</a>&nbsp;&nbsp;|&nbsp;&nbsp;<a href="https://discord.gg/9SuQFVexxJ"><strong>Discord</strong></a>
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/license-AGPL--3.0%20%2B%20Apache--2.0-blue" alt="License"></a>
  <a href="https://docs.jarvisautomation.dev"><img src="https://img.shields.io/badge/docs-jarvisautomation.dev-6366f1" alt="Docs"></a>
  <a href="https://github.com/alexberardi/jarvis-server/releases"><img src="https://img.shields.io/github/v/release/alexberardi/jarvis-server?include_prereleases&label=release" alt="Latest release"></a>
</p>

> **Pre-release.** Jarvis Automation is at release candidate `v0.1.0-rc18`; there is no `v0.1.0` yet. Expect rough edges and changes between release candidates.
>
> **This repository is not where Jarvis Automation lives any more.** The server and its desktop agent are [jarvis-server](https://github.com/alexberardi/jarvis-server). This repository was the home of the old Docker/microservice install, which is retired for new users (see [Legacy](#legacy-the-old-docker-install)).

---

## What it is

| Piece | What it does | Where |
|---|---|---|
| **Server** (`jarvisd`) | One program on a computer that stays on. Runs the whole assistant for your household and serves the setup wizard and the web app on port 7710. | [jarvis-server](https://github.com/alexberardi/jarvis-server) |
| **Desktop agent** | Lets Jarvis listen ("Hey Jarvis") on a computer, open apps and links, control windows and work with your browser. Each person installs their own. | [jarvis-server](https://github.com/alexberardi/jarvis-server) |
| **Voice node** | A small microphone and speaker for a room, usually a Raspberry Pi with a ReSpeaker HAT. | [jarvis-node-setup](https://github.com/alexberardi/jarvis-node-setup) |
| **Mobile app** | Talk to Jarvis, manage devices and routines, set up voice nodes. iOS and Android. | [App Store](https://apps.apple.com/app/id6760924901) · [Google Play](https://play.google.com/store/apps/details?id=com.jarvis.nodemobile) |

Everything runs on your hardware. Nothing that needs the internet is on by default, and the server downloads a language model only when you pick one in the setup wizard.

## Install

1. **Install the server.** Get the installer for your computer from **[installer.jarvisautomation.io](https://installer.jarvisautomation.io)**, or from the newest [release](https://github.com/alexberardi/jarvis-server/releases):

   | | Server | Desktop agent |
   |---|---|---|
   | macOS (Apple silicon) | `Jarvis-Automation-Server-<v>.dmg` | `Jarvis-Automation-Agent-<v>.dmg` |
   | Windows | `Jarvis-Automation-Server-Setup-<v>.exe` | `Jarvis-Automation-Agent-Setup-<v>.exe` |
   | Debian, Ubuntu | `jarvis-automation-server_<v>_<arch>.deb` | `jarvis-automation-agent_<v>_<arch>.deb` |
   | From a terminal | `install.sh` (Linux, macOS), `install.ps1` (Windows) | `install-agent.sh` (any Linux) |

   Docker and Unraid: see [Server in Docker](https://docs.jarvisautomation.dev/install/docker/) and [Unraid](https://docs.jarvisautomation.dev/install/unraid/).

2. **Finish the setup wizard.** The installer opens `http://<server>:7710/setup` in your browser. It creates your account, checks that other devices can reach the server, and helps you pick a model for your hardware.

3. **Add the rest.** The [desktop agent](https://docs.jarvisautomation.dev/clients/desktop-agent/) on each computer, a [voice node](https://docs.jarvisautomation.dev/install/voice-node/) per room, and the [mobile app](https://docs.jarvisautomation.dev/install/mobile-app/) pointed at `http://<server>:7700`.

The [install guide](https://docs.jarvisautomation.dev/install/) covers each step, upgrades and uninstalling.

**Coming from the old Docker install?** `jarvisd import-legacy` carries over your users, households, nodes (Pi nodes reconnect without re-provisioning), rooms, devices, settings, memories, routines, contacts and inbox. See [Migrating from the old Docker install](https://docs.jarvisautomation.dev/install/migrating-from-docker/).

## Choosing a model

The model you run sets how quick and how accurate Jarvis feels. Pick it by your machine's memory:

- **Mac with 16 GB:** Qwen 3 4B (Q4_K_M)
- **Mac with 24 GB or more:** Qwen 3.5 9B (Q4_K_M, vision)
- **PC or Linux machine with a GPU:** the largest model the setup wizard marks **Fits**
- **No usable GPU:** Qwen 3 4B (Q4_K_M)

On a 16 GB Mac mini M4, Qwen 3 4B picked the right action for **98.8 %** of an 80-utterance voice benchmark, in about **1.2 s** per turn once the prompt is cached (about 15 s for the first turn after a restart). [Models and hardware](https://docs.jarvisautomation.dev/models/) and [Benchmarks](https://docs.jarvisautomation.dev/reference/benchmarks/) have the rest.

## Extending Jarvis

Commands are Python classes that implement `IJarvisCommand` from [jarvis-command-sdk](https://github.com/alexberardi/jarvis-command-sdk). They run on a voice node or a computer's desktop agent, not on the server. Community packages (weather, music, calendar, smart-home devices and more) install from the [Pantry](https://pantry.jarvisautomation.io). Start with [Building commands](https://docs.jarvisautomation.dev/commands/).

## Repositories

| Repository | What |
|---|---|
| [jarvis-server](https://github.com/alexberardi/jarvis-server) | The server (`jarvisd`) and the desktop agent (`jarvis-agent`) |
| [jarvis-node-setup](https://github.com/alexberardi/jarvis-node-setup) | The Raspberry Pi voice node (Python) |
| [jarvis-node-mobile](https://github.com/alexberardi/jarvis-node-mobile) | The mobile app (React Native) |
| [jarvis-command-sdk](https://github.com/alexberardi/jarvis-command-sdk) | The interfaces commands and packages implement |
| [jarvis-pantry](https://github.com/alexberardi/jarvis-pantry), [jarvis-pantry-web](https://github.com/alexberardi/jarvis-pantry-web) | The Pantry package store and its web app |
| [jarvis-notifications-relay](https://github.com/alexberardi/jarvis-notifications-relay) | Push delivery to the mobile app |
| [jarvis-docs](https://github.com/alexberardi/jarvis-docs) | [docs.jarvisautomation.dev](https://docs.jarvisautomation.dev) |
| [jarvis-installer](https://github.com/alexberardi/jarvis-installer) | [installer.jarvisautomation.io](https://installer.jarvisautomation.io) |

Command and device packages live in their own `jarvis-cmd-*` and `jarvis-device-*` repositories, listed in the [Pantry](https://pantry.jarvisautomation.io).

## Legacy: the old Docker install

Before `jarvisd`, Jarvis was a set of Python microservices run with Docker Compose: config-service, auth, logs, command-center, llm-proxy, whisper, tts, notifications, admin, recipes and OCR, on Postgres, Redis, MinIO and Mosquitto. `jarvisd` replaces all of them with one program and embedded storage.

That install is **retired for new users** as of `v0.1.0-rc18`. It no longer installs out of the box (MinIO's images are gone), and its documentation is frozen under [Legacy](https://docs.jarvisautomation.dev/legacy/) on the docs site. If you run it today, [move to jarvisd](https://docs.jarvisautomation.dev/install/migrating-from-docker/); the jarvisd installer's `--stop-legacy` stops the old containers without deleting anything.

This repository still holds that stack's development tooling (the `./jarvis` CLI, `scripts/`, `deploy/`) and the `install-e2e/` harness, including the voice-command benchmark corpus that jarvis-server's `scripts/toolbench` reads (`install-e2e/gpu/bench_corpus.cc.yaml`). None of it is needed to run Jarvis Automation.

## Community

Questions, bug reports, or a package you built: **[join the Discord](https://discord.gg/9SuQFVexxJ)**. Bugs and feature requests are also welcome as [jarvis-server issues](https://github.com/alexberardi/jarvis-server/issues).

## License

Jarvis Automation is open source under a split license:

- **The server, the desktop agent, the node software and the rest of the self-hosted stack** are licensed under the **GNU AGPL-3.0**. You can self-host, modify and redistribute freely; if you run a modified version as a network service, you must publish your changes.
- **The mobile app, `jarvis-command-sdk`, the client libraries and the `jarvis-cmd-*` / `jarvis-device-*` packages** are licensed under **Apache-2.0**, so you can build and ship your own commands and integrations without copyleft obligations.

Each repository's `LICENSE` file is authoritative.
