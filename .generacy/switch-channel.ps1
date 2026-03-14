# Switch Generacy release channel (preview / stable)
#
# Updates the cluster-base remote to track the appropriate branch,
# pulls the latest changes, and updates local configuration files.
#
# Usage:
#   .generacy\switch-channel.ps1 preview
#   .generacy\switch-channel.ps1 stable

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("preview", "stable")]
    [string]$Channel
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path $PSScriptRoot -Parent
$ClusterYaml = Join-Path $PSScriptRoot "cluster.yaml"
$EnvTemplate = Join-Path $ProjectDir ".devcontainer" "generacy" ".env.template"
$EnvFile = Join-Path $ProjectDir ".devcontainer" "generacy" ".env"

# -- Helpers ------------------------------------------------------------------

function Write-Info { Write-Host "==> $args" -ForegroundColor Blue }
function Write-Ok   { Write-Host "  + $args" -ForegroundColor Green }
function Write-Warn { Write-Host "  ! $args" -ForegroundColor Yellow }
function Write-Err  { Write-Host "  x $args" -ForegroundColor Red }

# -- Map channel to branch ----------------------------------------------------

if ($Channel -eq "preview") {
    $Branch = "develop"
} else {
    $Branch = "main"
}

Write-Info "Switching to '$Channel' channel (branch: $Branch)"

# -- Step 1: Update cluster-base remote ---------------------------------------

$Remote = "cluster-base"

$remoteUrl = git remote get-url $Remote 2>$null
if ($LASTEXITCODE -eq 0 -and $remoteUrl) {
    Write-Ok "Remote '$Remote' exists"
} else {
    Write-Info "Adding remote '$Remote'..."
    git remote add $Remote "https://github.com/generacy-ai/cluster-base.git"
    Write-Ok "Added remote '$Remote'"
}

# -- Step 2: Fetch from the target branch --------------------------------------

Write-Info "Fetching $Remote/$Branch..."
git fetch $Remote $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to fetch $Remote/$Branch"
    exit 1
}
Write-Ok "Fetched $Remote/$Branch"

# -- Step 3: Merge changes ----------------------------------------------------

Write-Info "Merging $Remote/$Branch..."

git merge "$Remote/$Branch" --allow-unrelated-histories -m "chore: switch to $Channel channel (merge $Remote/$Branch)" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Merge had conflicts - resolve them manually, then re-run this script"
    Write-Warn "Or run: git merge --abort  to undo"
    exit 1
}
Write-Ok "Merged $Remote/$Branch"

# -- Step 4: Update cluster.yaml ----------------------------------------------

if (Test-Path $ClusterYaml) {
    Write-Info "Updating cluster.yaml..."
    $content = Get-Content -Path $ClusterYaml -Raw
    $content = $content -replace '(?m)^channel:.*$', "channel: $Channel"
    Set-Content -Path $ClusterYaml -Value $content -NoNewline
    Write-Ok "cluster.yaml channel set to '$Channel'"
} else {
    Write-Warn "cluster.yaml not found at $ClusterYaml - skipping"
}

# -- Step 5: Update .env.template ---------------------------------------------

if (Test-Path $EnvTemplate) {
    Write-Info "Updating .env.template..."
    $content = Get-Content -Path $EnvTemplate -Raw
    $content = $content -replace '(?m)^GENERACY_CHANNEL=.*$', "GENERACY_CHANNEL=$Channel"
    Set-Content -Path $EnvTemplate -Value $content -NoNewline
    Write-Ok ".env.template GENERACY_CHANNEL set to '$Channel'"
} else {
    Write-Warn ".env.template not found at $EnvTemplate - skipping"
}

# -- Step 6: Update .env (if it exists) ----------------------------------------

if (Test-Path $EnvFile) {
    Write-Info "Updating .env..."
    $content = Get-Content -Path $EnvFile -Raw
    if ($content -match '(?m)^GENERACY_CHANNEL=') {
        $content = $content -replace '(?m)^GENERACY_CHANNEL=.*$', "GENERACY_CHANNEL=$Channel"
        Set-Content -Path $EnvFile -Value $content -NoNewline
        Write-Ok ".env GENERACY_CHANNEL set to '$Channel'"
    } else {
        Add-Content -Path $EnvFile -Value "GENERACY_CHANNEL=$Channel"
        Write-Ok "Added GENERACY_CHANNEL=$Channel to .env"
    }
}

# -- Summary -------------------------------------------------------------------

Write-Host ""
Write-Info "Channel switch complete!"
Write-Host ""
Write-Host "  Channel:  $Channel"
Write-Host "  Branch:   $Remote/$Branch"
Write-Host "  Changed:"
if (Test-Path $ClusterYaml) { Write-Host "    .generacy/cluster.yaml             -> channel: $Channel" }
if (Test-Path $EnvTemplate) { Write-Host "    .devcontainer/generacy/.env.template -> GENERACY_CHANNEL=$Channel" }
if (Test-Path $EnvFile)     { Write-Host "    .devcontainer/generacy/.env          -> GENERACY_CHANNEL=$Channel" }
Write-Host ""
Write-Host "  Next steps:"
Write-Host "    1. Rebuild containers to apply the new channel:"
Write-Host "       cd .devcontainer/generacy; docker compose up -d --build"
Write-Host "    2. Commit the updated configuration files"
Write-Host ""
