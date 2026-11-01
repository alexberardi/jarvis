<p align="center">
  <img src="logo.png" alt="Jarvis Automation" width="600" />
</p>

<h3 align="center">Your own Jarvis. It runs in your house, not in someone else's cloud.</h3>

<p align="center">
  A voice assistant that hears you in every room, knows who's talking, remembers what you tell it,<br>
  runs your smart home and works your computer for you, all on hardware you own.
</p>

<p align="center">
  <a href="https://installer.jarvisautomation.io"><strong>Download</strong></a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://docs.jarvisautomation.dev"><strong>Docs</strong></a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://discord.gg/9SuQFVexxJ"><strong>Discord</strong></a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/alexberardi/jarvis-server">jarvis-server</a>
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/license-AGPL--3.0%20%2B%20Apache--2.0-blue" alt="License"></a>
  <a href="https://docs.jarvisautomation.dev"><img src="https://img.shields.io/badge/docs-jarvisautomation.dev-6366f1" alt="Docs"></a>
  <a href="https://github.com/alexberardi/jarvis-server/releases"><img src="https://img.shields.io/github/v/release/alexberardi/jarvis-server?include_prereleases&label=release" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/runs%20on-macOS%20·%20Windows%20·%20Linux-informational" alt="Runs on macOS, Windows and Linux">
</p>

---

## Just say it

```text
"Hey Jarvis, turn off the basement lights."            → your smart home, through Home Assistant
"Good morning."                                         → your routine: lights, weather, today's calendar
"Remind me to check the oven in 20 minutes."            → a reminder, with snooze and repeats
"Remember that I take my coffee black."                 → a memory that's yours, not your partner's
"Open Steam."  ·  "Switch to Firefox."                  → on your computer
"Close the YouTube tab."  ·  "Pause the video."         → in your own browser
"What does this error say?"                             → Jarvis reads your screen
"Tell Claude to run the tests."                         → dictation, typed into the app in front of you
```

All of it runs on one computer in your home: hearing you, understanding you and talking back.

## Why it's different

**🔒 It's actually private.** Speech recognition, the language model, the voice and speaker recognition all run on your own machine. Nothing that needs the internet is on by default. No account with us, no subscription, nobody listening in.

**🗣️ It knows who's talking.** Jarvis recognizes each person's voice, so what you tell it to remember is *yours*, not everyone's in the house.

**🖥️ It works your computer, not just your lights.** The desktop agent lets Jarvis open apps and links, switch and close windows, set the volume, read your screen, type what you dictate and drive your own browser: find a tab, fill in a form, click a button, pause a video. On macOS and Linux, with Windows support newer and less tested.

**🏠 It's everywhere you are.** A small speaker in each room, the iOS and Android app, a web chat in any browser and "Hey Jarvis" on your computer, all on one server with the same commands, memories, devices and routines.

**⚡ It's fast on ordinary hardware.** On a 16 GB Mac mini, the recommended model picked the right action for **98.8 %** of an 80-command voice benchmark, in about **1.2 seconds** a turn once warmed up. No data-center GPU needed.

**📦 It's one program.** `jarvisd` is a single executable with real installers for macOS, Windows and Debian/Ubuntu, and a setup wizard that checks your network and picks a model that fits your machine. No Docker, no database to run, no YAML.

**👨‍👩‍👧 Share it with the people you care about.** One server can host several households. Friends and family add your server's address in the app, make an account and get their own assistant, fully separate from yours.

**🧩 It's yours to extend.** A new command is a Python class. Install community packages (weather, news, music, calendar, smart-home devices and more) from the [Pantry](https://pantry.jarvisautomation.io), or describe what you want and let the Pantry's Forge write it.

### Compared with the big three

| | **Jarvis Automation** | Alexa · Google · Siri |
|---|---|---|
| Where your voice is processed | Your own computer | Their cloud |
| Works when the internet is down | Yes, for everything that doesn't need the internet (timers, devices on your network, your computer) | Mostly no |
| Knows who's speaking | Yes, on your hardware | Yes, on their servers |
| Controls your computer and browser | Yes | No |
| Add your own commands | A Python class, no review process | Their skill store, their rules |
| Subscription | None | For some features |
| Source code | Open (AGPL-3.0 and Apache-2.0) | Closed |

## Get started in three steps

1. **Install the server** on a computer that stays on. Get it from **[installer.jarvisautomation.io](https://installer.jarvisautomation.io)**, or from the newest [release](https://github.com/alexberardi/jarvis-server/releases):

   | | Server | Desktop agent |
   |---|---|---|
   | macOS (Apple silicon) | `Jarvis-Automation-Server-<v>.dmg` | `Jarvis-Automation-Agent-<v>.dmg` |
   | Windows | `Jarvis-Automation-Server-Setup-<v>.exe` | `Jarvis-Automation-Agent-Setup-<v>.exe` |
   | Debian, Ubuntu | `jarvis-automation-server_<v>_<arch>.deb` | `jarvis-automation-agent_<v>_<arch>.deb` |
   | From a terminal | `install.sh` (Linux, macOS), `install.ps1` (Windows) | `install-agent.sh` (any Linux) |

   Running a NAS? See [Server in Docker](https://docs.jarvisautomation.dev/install/docker/) and [Unraid](https://docs.jarvisautomation.dev/install/unraid/).

2. **Follow the setup wizard.** It opens in your browser, creates your account, checks that your other devices can reach the server and downloads a model that fits your hardware.

3. **Add the rest.** The [desktop agent](https://docs.jarvisautomation.dev/agent/) on each computer, a [voice node](https://docs.jarvisautomation.dev/install/voice-node/) in each room and the [mobile app](https://docs.jarvisautomation.dev/install/mobile-app/) ([App Store](https://apps.apple.com/app/id6760924901); Google Play coming soon).

The [install guide](https://docs.jarvisautomation.dev/install/) covers every step, upgrades and uninstalling.

> **Pre-release.** Jarvis Automation is at release candidate `v0.1.0-rc18.12`, on its way to `v0.1.0`. It's in daily use, but expect rough edges and changes between release candidates. Come say hi in the [Discord](https://discord.gg/9SuQFVexxJ).

**Coming from the old Docker install?** `jarvisd import-legacy` brings over your users, households, nodes (Pi nodes reconnect without re-provisioning), rooms, devices, settings, memories, routines, contacts and inbox. See [Migrating from the old Docker install](https://docs.jarvisautomation.dev/install/migrating-from-docker/).

## What you need

| | |
|---|---|
| **Server** | A Mac with Apple silicon and 16 GB or more, or a Windows or Linux PC with a GPU. A machine without a GPU works too, with a small model, but answers more slowly. |
| **Voice node** (optional, per room) | A Raspberry Pi with a ReSpeaker 2-mic HAT (about $50), or a USB microphone and speaker. |
| **Model** | The setup wizard suggests one. On a 16 GB Mac, Qwen 3 4B. With 24 GB or more, Qwen 3.5 9B (it can see images too). On a GPU, the largest model the wizard marks **Fits**. |

[Models and hardware](https://docs.jarvisautomation.dev/models/) and [Benchmarks](https://docs.jarvisautomation.dev/reference/benchmarks/) have the details.

## Build on it

Commands are Python classes that implement `IJarvisCommand` from [jarvis-command-sdk](https://github.com/alexberardi/jarvis-command-sdk). They run on a voice node or a computer's desktop agent, and the model picks them like any built-in tool. Share yours in the [Pantry](https://pantry.jarvisautomation.io). Start with [Building commands](https://docs.jarvisautomation.dev/commands/).

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

## About this repository

This repository was the home of the old Docker/microservice install: config-service, auth, logs, command-center, llm-proxy, whisper, tts, notifications, admin, recipes and OCR, on Postgres, Redis, MinIO and Mosquitto. `jarvisd` replaces all of them with one program and embedded storage.

That install is **retired for new users** as of `v0.1.0-rc18`. It no longer installs out of the box (MinIO's images are gone), and its documentation is frozen under [Legacy](https://docs.jarvisautomation.dev/legacy/). If you run it today, [move to jarvisd](https://docs.jarvisautomation.dev/install/migrating-from-docker/); the jarvisd installer's `--stop-legacy` stops the old containers without deleting anything.

What's left here is that stack's development tooling (the `./jarvis` CLI, `scripts/`, `deploy/`) and the `install-e2e/` harness, including the voice-command benchmark corpus that jarvis-server's `scripts/toolbench` reads (`install-e2e/gpu/bench_corpus.cc.yaml`). None of it is needed to run Jarvis Automation.

## Community

Questions, bug reports, or a package you built: **[join the Discord](https://discord.gg/9SuQFVexxJ)**. Bugs and feature requests are also welcome as [jarvis-server issues](https://github.com/alexberardi/jarvis-server/issues).

## License

Jarvis Automation is open source under a split license:

- **The server, the desktop agent, the node software and the rest of the self-hosted stack** are licensed under the **GNU AGPL-3.0**. You can self-host, modify and redistribute freely; if you run a modified version as a network service, you must publish your changes.
- **The mobile app, `jarvis-command-sdk`, the client libraries and the `jarvis-cmd-*` / `jarvis-device-*` packages** are licensed under **Apache-2.0**, so you can build and ship your own commands and integrations without copyleft obligations.

Each repository's `LICENSE` file is authoritative.
