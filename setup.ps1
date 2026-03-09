# Generacy Development Cluster Setup
#
# Run this script after cloning/forking to configure the cluster
# for your project. Idempotent — safe to re-run at any time.
#
# If .generacy/config.yaml already exists (from the onboarding UI,
# manual creation, or a previous run), the script reads project info
# from it and skips those prompts.
#
# Usage:
#   .\setup.ps1
#   .\setup.ps1 -RepoUrl https://github.com/your-org/your-repo.git

param(
    [string]$RepoUrl = ""
)

$ErrorActionPreference = "Stop"
$DevcontainerDir = Join-Path $PSScriptRoot ".devcontainer"
$GeneracyDir = Join-Path $PSScriptRoot ".generacy"
$ConfigFile = Join-Path $GeneracyDir "config.yaml"

# -- Helpers ------------------------------------------------------------------

function Write-Info  { Write-Host "==> $args" -ForegroundColor Blue }
function Write-Ok    { Write-Host "  + $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "  ! $args" -ForegroundColor Yellow }
function Write-Err   { Write-Host "  x $args" -ForegroundColor Red }

function Parse-Repo {
    param([string]$RepoInput)
    $RepoInput = $RepoInput -replace '^https?://github\.com/', '' -replace '^github\.com/', '' -replace '\.git$', '' -replace '/$', ''
    return $RepoInput
}

# -- Step 1: Load or create .generacy/config.yaml ----------------------------

Write-Info "Checking for existing config..."

if (Test-Path $ConfigFile) {
    Write-Info "Found existing .generacy/config.yaml"

    $configContent = Get-Content -Path $ConfigFile -Raw
    $primaryMatch = [regex]::Match($configContent, 'primary:\s*[''"]?([^\s''"]+)[''"]?')
    if ($primaryMatch.Success) {
        $primaryRepoRaw = $primaryMatch.Groups[1].Value
    } else {
        Write-Err "Could not parse primary repo from config.yaml"
        exit 1
    }

    $ownerRepo = Parse-Repo $primaryRepoRaw
    $parts = $ownerRepo -split '/'
    $Owner = $parts[0]
    $RepoName = $parts[1]
    $RepoUrl = "https://github.com/$ownerRepo.git"
    $ProjectName = ($RepoName.ToLower() -replace '[^a-z0-9-]', '-')

    Write-Ok "Primary repo: $ownerRepo"
    Write-Ok "Project name: $ProjectName"

    $configExists = $true
} else {
    $configExists = $false
    Write-Info "No config.yaml found - will create one"

    if (-not $RepoUrl) {
        try { $RepoUrl = git remote get-url origin 2>$null } catch {}
    }
    if (-not $RepoUrl) {
        $RepoUrl = Read-Host "  ? Repository URL (e.g., https://github.com/your-org/your-repo.git)"
    }
    if (-not $RepoUrl) {
        Write-Err "Repository URL is required"
        exit 1
    }

    $ownerRepo = Parse-Repo $RepoUrl
    $parts = $ownerRepo -split '/'
    $Owner = $parts[0]
    $RepoName = $parts[1]
    $ProjectName = ($RepoName.ToLower() -replace '[^a-z0-9-]', '-')

    Write-Ok "Repository: $RepoUrl"
    Write-Ok "Owner: $Owner"
    Write-Ok "Project name: $ProjectName"
    Write-Ok "Repo name: $RepoName"
}

# -- Step 2: Branch -----------------------------------------------------------

if ($configExists) {
    $branchMatch = [regex]::Match($configContent, 'baseBranch:\s*[''"]?([^\s''"]+)[''"]?')
    if ($branchMatch.Success) {
        $RepoBranch = $branchMatch.Groups[1].Value
    } else {
        $RepoBranch = "main"
    }
    Write-Ok "Branch (from config): $RepoBranch"
} else {
    $RepoBranch = try { git symbolic-ref --short HEAD 2>$null } catch { "main" }
    if (-not $RepoBranch) { $RepoBranch = "main" }
    $input = Read-Host "  ? Default branch [$RepoBranch]"
    if ($input) { $RepoBranch = $input }
    Write-Ok "Branch: $RepoBranch"
}

# -- Step 3: Worker count ----------------------------------------------------

$WorkerCount = "3"
$input = Read-Host "  ? Number of workers [$WorkerCount]"
if ($input) { $WorkerCount = $input }
Write-Ok "Workers: $WorkerCount"

# -- Step 4: Create smee.io channel ------------------------------------------

Write-Info "Setting up webhook forwarding..."

$SmeeChannelUrl = ""
$EnvFile = Join-Path $DevcontainerDir ".env"

# Check existing .env for smee URL
if (Test-Path $EnvFile) {
    $existingSmee = (Get-Content $EnvFile | Where-Object { $_ -match '^SMEE_CHANNEL_URL=' }) -replace '^SMEE_CHANNEL_URL=', ''
    if ($existingSmee) { $SmeeChannelUrl = $existingSmee }
}

if ($SmeeChannelUrl) {
    Write-Ok "Smee channel (from existing .env): $SmeeChannelUrl"
} else {
    $createSmee = Read-Host "  ? Create a new smee.io channel? [Y/n]"
    if ($createSmee -ne "n" -and $createSmee -ne "N") {
        try {
            $response = Invoke-WebRequest -Uri "https://smee.io/new" -MaximumRedirection 0 -ErrorAction SilentlyContinue
        } catch {
            if ($_.Exception.Response.Headers.Location) {
                $SmeeChannelUrl = $_.Exception.Response.Headers.Location.ToString()
            }
        }
        if ($SmeeChannelUrl) {
            Write-Ok "Smee channel: $SmeeChannelUrl"
        } else {
            Write-Warn "Could not create smee.io channel automatically"
        }
    }

    if (-not $SmeeChannelUrl) {
        $SmeeChannelUrl = Read-Host "  ? Smee.io channel URL (create one at https://smee.io/new, or press Enter to skip)"
        if ($SmeeChannelUrl) {
            Write-Ok "Smee channel: $SmeeChannelUrl"
        } else {
            Write-Warn "Skipping smee.io - you can add SMEE_CHANNEL_URL to .env later"
        }
    }
}

# -- Step 5: Generate .generacy/config.yaml (if not present) -----------------

if (-not $configExists) {
    Write-Info "Creating .generacy/config.yaml..."
    if (-not (Test-Path $GeneracyDir)) { New-Item -ItemType Directory -Path $GeneracyDir -Force | Out-Null }
    $configYaml = @"
# Generacy project configuration
# Docs: https://github.com/generacy-ai/cluster-base

project:
  name: "$ProjectName"

repos:
  primary: "$Owner/$RepoName"
  dev:
    # Add repos for active development (owner/repo format):
    # - $Owner/another-repo
  clone:
    # Add repos to clone as read-only reference:
    # - $Owner/docs

defaults:
  baseBranch: $RepoBranch
"@
    Set-Content -Path $ConfigFile -Value $configYaml
    Write-Ok "Created $ConfigFile"
}

# -- Step 6: Generate .env (Docker Compose variables) -------------------------

Write-Info "Generating .devcontainer/.env..."

$writeEnv = $true
if (Test-Path $EnvFile) {
    $overwrite = Read-Host "  ? .env already exists. Overwrite? [y/N]"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-Warn "Keeping existing .env"
        $writeEnv = $false
    }
}

if ($writeEnv) {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $envContent = @"
# Docker Compose configuration
# Generated by setup.ps1 -- $timestamp
#
# These variables are used by docker-compose.yml for container setup.
# Project config (repos, monitoring, webhooks) lives in .generacy/config.yaml.

PROJECT_NAME=$ProjectName
REPO_URL=https://github.com/$Owner/$RepoName.git
REPO_NAME=$RepoName
REPO_BRANCH=$RepoBranch
WORKER_COUNT=$WorkerCount
ORCHESTRATOR_PORT=3100
SMEE_CHANNEL_URL=$SmeeChannelUrl
LABEL_MONITOR_ENABLED=true
WEBHOOK_SETUP_ENABLED=true
"@
    Set-Content -Path $EnvFile -Value $envContent -NoNewline
    Write-Ok "Created $EnvFile"
}

# -- Step 7: Generate .env.local (secrets) ------------------------------------

Write-Info "Setting up credentials..."

$EnvLocalFile = Join-Path $DevcontainerDir ".env.local"
$writeLocal = $true

if (Test-Path $EnvLocalFile) {
    $overwrite = Read-Host "  ? .env.local already exists. Overwrite? [y/N]"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-Warn "Keeping existing .env.local"
        $writeLocal = $false
    }
}

if ($writeLocal) {
    Write-Host ""
    Write-Info "GitHub fine-grained access token"
    Write-Host "  Create one at: https://github.com/settings/tokens?type=beta"
    Write-Host "  Required permissions: Contents (rw), Issues (rw), Pull requests (rw)"
    Write-Host ""

    $ghTokenSecure = Read-Host "  ? GitHub token" -AsSecureString
    $ghToken = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ghTokenSecure))

    $ghUsername = Read-Host "  ? GitHub username"
    $ghEmail = Read-Host "  ? GitHub email"

    Write-Host ""
    Write-Info "Claude API key"
    Write-Host "  Get one at: https://console.anthropic.com/settings/keys"
    Write-Host ""

    $claudeKeySecure = Read-Host "  ? Claude API key" -AsSecureString
    $claudeKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($claudeKeySecure))

    $envLocalContent = @"
# Generated by setup.ps1 -- DO NOT COMMIT
GH_TOKEN=$ghToken
GH_USERNAME=$ghUsername
GH_EMAIL=$ghEmail
CLAUDE_API_KEY=$claudeKey
"@
    Set-Content -Path $EnvLocalFile -Value $envLocalContent -NoNewline
    Write-Ok "Created $EnvLocalFile"
}

# -- Step 8: Update devcontainer.json ----------------------------------------

Write-Info "Updating devcontainer.json..."

$DevcontainerJson = Join-Path $DevcontainerDir "devcontainer.json"

if (Test-Path $DevcontainerJson) {
    $content = Get-Content -Path $DevcontainerJson -Raw
    $content = $content -replace '"name": "generacy-cluster"', "`"name`": `"$ProjectName`""
    $content = $content -replace '"workspaceFolder": "/workspaces/project"', "`"workspaceFolder`": `"/workspaces/$RepoName`""
    Set-Content -Path $DevcontainerJson -Value $content -NoNewline
    Write-Ok "Updated devcontainer.json (name: $ProjectName, workspaceFolder: /workspaces/$RepoName)"
} else {
    Write-Warn "devcontainer.json not found at $DevcontainerJson"
}

# -- Step 9: Ensure ~/.claude.json exists ------------------------------------

Write-Info "Checking Claude config..."

$ClaudeJson = Join-Path $env:USERPROFILE ".claude.json"

if (-not (Test-Path $ClaudeJson)) {
    Set-Content -Path $ClaudeJson -Value "{}"
    Write-Ok "Created $ClaudeJson (required for Docker volume mount)"
} else {
    Write-Ok "$ClaudeJson already exists"
}

# -- Done ---------------------------------------------------------------------

Write-Host ""
Write-Info "Setup complete!"
Write-Host ""
Write-Host "  Generated files:"
Write-Host "    .generacy/config.yaml       - project configuration (commit this)"
Write-Host "    .devcontainer/.env          - Docker Compose settings (commit this)"
Write-Host "    .devcontainer/.env.local    - secrets (gitignored, never commit)"
Write-Host "    .devcontainer/devcontainer.json - updated with project values"
Write-Host ""
Write-Host "  Next steps:"
Write-Host "    1. Open this project in VS Code"
Write-Host "    2. VS Code will prompt: 'Reopen in Container' -- click it"
Write-Host "    3. Or run manually: cd .devcontainer; docker compose up -d"
Write-Host ""
if ($SmeeChannelUrl) {
    Write-Host "  Webhook forwarding:"
    Write-Host "    Add this URL as a webhook in your GitHub repo settings:"
    Write-Host "    $SmeeChannelUrl"
    Write-Host ""
}
