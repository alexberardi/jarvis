# Generacy Cluster Base

Development cluster setup for AI-powered workflow development with [Generacy](https://github.com/generacy-ai/generacy). Provides an orchestrator, scalable Claude Code workers, Redis, and isolated networking.

## Getting Started

### Option A: New Project (Fork)

1. **Fork this repo** on GitHub — click "Fork" in the top right
2. **Clone your fork**:

   ```bash
   git clone https://github.com/YOUR-USERNAME/cluster-base.git my-project
   cd my-project
   ```

3. **Run setup**:

   ```bash
   # macOS / Linux / WSL
   .generacy/setup.sh

   # Windows PowerShell
   .generacy\setup.ps1
   ```

4. **Start the cluster** — open in VS Code and select the "generacy" dev container, or:

   ```bash
   cd .devcontainer/generacy
   docker compose up -d
   ```

### Option B: Existing Project (Remote Merge)

1. **Add the base repo as a remote** from your project directory:

   ```bash
   git remote add cluster-base https://github.com/generacy-ai/cluster-base.git
   git fetch cluster-base
   git merge cluster-base/main --allow-unrelated-histories
   ```

2. **Run setup** and **start the cluster** — same as steps 3 and 4 above.

### What the Setup Script Does

The setup script walks you through configuring the cluster interactively:

- Detects your project from the git remote (or prompts for the repo URL)
- Asks for default branch and worker count
- Creates a [smee.io](https://smee.io) webhook channel for GitHub event forwarding
- Generates `.devcontainer/generacy/.env` with project settings
- Prompts for your GitHub token, username, email, and Claude API key
- Generates `.devcontainer/generacy/.env.local` with your credentials (gitignored, never committed)
- Updates `devcontainer.json` with your project name and workspace path
- Ensures `~/.claude.json` exists on your host (required for the Docker volume mount)

## What's Included

- **Orchestrator** — manages worker lifecycle, dispatches label-driven workflows
- **Scalable workers** — headless Claude Code agents (controlled by `WORKER_COUNT`)
- **Redis** — inter-service communication and state
- **Isolated network** — cluster runs on its own bridge network
- **Clone-mode volumes** — repos cloned into Docker volumes, not bind-mounted from host
- **Shared Claude config** — API keys and settings shared across all containers
- **Speckit workflows** — standard feature and bugfix workflow definitions

## Updating

When this base repo is updated with improvements, pull the latest changes:

```bash
git fetch cluster-base
git merge cluster-base/main
```

If you forked, sync from the upstream repo:

```bash
git remote add upstream https://github.com/generacy-ai/cluster-base.git  # first time only
git fetch upstream
git merge upstream/main
```

Git merge handles conflicts naturally if you've customized any base files.

## Variants

| Variant | Repo | Adds |
|---------|------|------|
| **Standard** (this repo) | [cluster-base](https://github.com/generacy-ai/cluster-base) | Core cluster setup |
| **Microservices** | [cluster-microservices](https://github.com/generacy-ai/cluster-microservices) | Docker-in-Docker for running container stacks |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine
- [VS Code](https://code.visualstudio.com/) with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension
- A [GitHub fine-grained token](https://github.com/settings/tokens?type=beta) with Contents, Issues, and Pull requests permissions
- A [Claude API key](https://console.anthropic.com/settings/keys)

## File Structure

```
.devcontainer/
  generacy/
    Dockerfile            # Multi-stage build with Node, GitHub CLI, Claude Code
    docker-compose.yml    # Orchestrator + workers + Redis
    devcontainer.json     # VS Code Dev Containers config
    .env.template         # Reference for project settings
    .env.local.template   # Reference for user secrets
    scripts/              # Entrypoint and setup scripts
.generacy/
  setup.sh                # Setup script (bash)
  setup.ps1               # Setup script (PowerShell)
  README.md               # This file
  speckit-feature.yaml    # Feature development workflow
  speckit-bugfix.yaml     # Bugfix workflow
.agency/
  config.json             # Agency MCP server config
```
