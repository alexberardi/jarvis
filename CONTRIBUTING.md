# Contributing to Jarvis

Thanks for your interest in Jarvis — an open-source, self-hosted voice assistant
split across ~60 repositories. This is the umbrella repo (docs, the `jarvis` dev
CLI, and cross-cutting notes); most code lives in the individual service and
package repos listed in the [README](README.md#services).

## Ways to contribute

- **Build a command or device package** — the easiest entry point. Use the
  [Developer Toolkit](https://github.com/alexberardi/jarvis-developer-toolkit)
  (`jdt`) to scaffold, test, and deploy a package, then publish it to the Pantry.
  These packages are Apache-2.0, so you keep full control of your code.
- **Fix a bug or add a feature** in a service — open a PR against that service's
  own repository.
- **Improve the docs** — they live in
  [jarvis-docs](https://github.com/alexberardi/jarvis-docs).

## Getting it running

To *run* Jarvis, use the one-line installer (see the
[README](README.md#quick-start)) — don't try to assemble the full stack by hand.

To *develop* a single service from source:

```bash
git clone https://github.com/alexberardi/<service>.git
cd <service>
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/python -m pytest
```

## Standards

- **Tests** — add or update tests for your change; CI runs the suite on every PR.
  Most services target 80%+ coverage.
- **Logging** — services log through `jarvis-log-client`, not `print()`.
- **Style** — match the surrounding code. Python services use type hints and group
  imports stdlib → third-party → local.
- **Commits** — clear, conventional messages (`feat:`, `fix:`, `chore:` …).

## Licensing

By contributing, you agree that your contributions are licensed under the same
license as the repository you contribute to: **AGPL-3.0** for the server-side
services, **Apache-2.0** for the apps, SDK, client libraries, and command/device
packages. See each repo's `LICENSE` file.
