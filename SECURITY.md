# Security Policy

Jarvis handles authentication tokens, app-to-app keys, node API keys, and OAuth
credentials for your home, so we take security seriously and welcome responsible
disclosure.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security problems.**

Email **admin@jarvisautomation.io** with:

- A description of the issue and the affected component / repository
- Steps to reproduce (a proof-of-concept if possible)
- The potential impact

You can expect an acknowledgement within 72 hours and a status update within
7 days. Once a fix is available we'll coordinate a disclosure timeline with you,
and credit you if you'd like.

## Scope

Jarvis spans ~60 repositories — services, client libraries, command/device
packages, and the mobile apps. Vulnerabilities in any of them are in scope,
especially:

- `jarvis-auth` — JWT, password handling, app/node credential issuance
- `jarvis-relay` and other cloud-facing services
- `jarvis-config-service` — service discovery
- The installer and node provisioning flows

## Supported Versions

During the beta, security fixes are applied to the latest release on `main`.
There is no long-term-support branch yet.
