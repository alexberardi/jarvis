# Generacy Development Cluster
# Multi-stage build for efficient layer caching
#
# Customize this Dockerfile for your project's needs.
# The stages are structured so that infrequently-changing layers
# (system packages, CLIs) are cached separately from the tooling layer.

# -- Stage 1: System dependencies (rarely changes, caches well) ---------------
FROM mcr.microsoft.com/devcontainers/typescript-node:22-bookworm AS base

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg netcat-openbsd redis-tools \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# -- Stage 2: Generacy tooling (changes with npm versions) --------------------
FROM base AS tooling

# Install Claude Code
USER node
RUN curl -fsSL https://claude.ai/install.sh | bash
USER root

# Add Claude to system-wide PATH
ENV PATH="/home/node/.local/bin:${PATH}"

# -- Stage 3: Final image -----------------------------------------------------
FROM tooling AS final

# Copy entrypoint scripts
COPY --chmod=755 scripts/ /usr/local/bin/

# Create workspaces directory with node ownership
RUN mkdir -p /workspaces && chown -R node:node /workspaces

# Pre-create shared-packages mount point with node ownership
# (Docker named volumes default to root, causing EACCES for node user)
RUN mkdir -p /shared-packages && chown node:node /shared-packages

# +============================================================================+
# |  Customize below: add your project's system dependencies                    |
# |                                                                             |
# |  Examples:                                                                  |
# |    RUN apt-get update && apt-get install -y python3 python3-pip             |
# |    RUN apt-get update && apt-get install -y postgresql-client               |
# |    RUN npm install -g pnpm@9                                                |
# +============================================================================+

USER node
WORKDIR /workspaces
