<#
.SYNOPSIS
  ChatBot5400 Phase 12 - isolated Windows Local test stack helper
  (docs/ocr/PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md).

.DESCRIPTION
  Drives deploy/phase12-test (compose project "chatbot5400-phase12-test", web
  127.0.0.1:8504, API 127.0.0.1:5057, its own database and folders).

  Safety: checks the environment first, never runs `docker compose down -v`,
  never deletes a folder, never touches another compose project, never uploads
  anything. Secrets in .env are generated locally and never printed.

.EXAMPLE
  .\scripts\windows\phase12-test.ps1 check
  .\scripts\windows\phase12-test.ps1 init-env
  .\scripts\windows\phase12-test.ps1 up
  .\scripts\windows\phase12-test.ps1 import-agri -Model C:\models\vie_agri.traineddata -Version v2
  .\scripts\windows\phase12-test.ps1 compare -Pdf qd-mau.pdf -Engine tesseract_agri
  .\scripts\windows\phase12-test.ps1 fixtures
  .\scripts\windows\phase12-test.ps1 legal-gate -State off
  .\scripts\windows\phase12-test.ps1 stop
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('check', 'init-env', 'build', 'up', 'status', 'logs', 'import-agri', 'activate-agri',
                 'agri-status', 'fixtures', 'compare', 'diagnose', 'legal-gate', 'restart-app', 'stop')]
    [string]$Action,
    [string]$Model,
    [string]$Version = 'v1',
    [string]$Pdf,
    [ValidateSet('rapidocr', 'tesseract_fast', 'tesseract_best', 'easyocr', 'tesseract_agri')]
    [string]$Engine = 'tesseract_agri',
    [ValidateSet('on', 'off')]
    [string]$State = 'on',
    [switch]$FullPage
)

$ErrorActionPreference = 'Stop'
$Project = 'chatbot5400-phase12-test'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StackDir = Join-Path $RepoRoot 'deploy\phase12-test'
$EnvFile = Join-Path $StackDir '.env'
$ImportDir = Join-Path $StackDir 'import'
$OutDir = Join-Path $StackDir 'diagnostics'

function Write-Step($msg) { Write-Host "[phase12] $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "[phase12] ERROR: $msg" -ForegroundColor Red; exit 1 }

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$ComposeArgs)
    Push-Location $StackDir
    try {
        & docker compose -p $Project -f docker-compose.yml @ComposeArgs
        if ($LASTEXITCODE -ne 0) { Fail "docker compose $($ComposeArgs -join ' ') failed ($LASTEXITCODE)" }
    } finally { Pop-Location }
}

function Test-PortFree([int]$Port) {
    $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return -not $busy
}

function Get-EnvValue([string]$Name, [string]$Default) {
    if (Test-Path $EnvFile) {
        $line = Get-Content $EnvFile | Where-Object { $_ -match "^\s*$Name\s*=" } | Select-Object -Last 1
        if ($line) { return ($line -split '=', 2)[1].Trim() }
    }
    return $Default
}

function Invoke-Check {
    Write-Step "Repository: $RepoRoot"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'Docker Desktop is not installed or not on PATH.' }
    $os = (& docker info --format '{{.OSType}}' 2>$null)
    if ($LASTEXITCODE -ne 0) { Fail 'Docker is not running (start Docker Desktop).' }
    if ($os -ne 'linux') { Fail "Docker must use Linux containers (current: $os)." }
    & docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail 'docker compose v2 is required.' }
    $branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD)
    $commit = (& git -C $RepoRoot rev-parse --short HEAD)
    Write-Step "Git: $branch @ $commit"
    if (-not (Test-Path $EnvFile)) { Write-Step 'No .env yet: run "init-env".' }
    $web = [int](Get-EnvValue 'PHASE12_WEB_PORT' '8504')
    $api = [int](Get-EnvValue 'PHASE12_API_PORT' '5057')
    $running = (& docker compose -p $Project ps -q 2>$null)
    foreach ($p in @($web, $api)) {
        if (-not (Test-PortFree $p) -and -not $running) { Fail "Port $p is already in use by another program." }
    }
    $free = (Get-PSDrive -Name ((Get-Item $RepoRoot).PSDrive.Name)).Free / 1GB
    Write-Step ("Free disk on the repository drive: {0:N1} GB (the image needs about 15 GB)" -f $free)
    if ($free -lt 20) { Write-Host '[phase12] WARNING: less than 20 GB free.' -ForegroundColor Yellow }
    Write-Step 'Other compose projects are never touched; this stack uses only:'
    Write-Host "   project=$Project web=127.0.0.1:$web api=127.0.0.1:$api data=$StackDir"
}

function New-Secret([int]$Bytes = 32) {
    $b = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return ([Convert]::ToBase64String($b)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Invoke-InitEnv {
    if (Test-Path $EnvFile) { Write-Step '.env already exists: left unchanged.'; return }
    $content = Get-Content (Join-Path $StackDir '.env.example')
    $content = $content -replace '^SURREAL_PASSWORD=$', "SURREAL_PASSWORD=$(New-Secret 24)"
    $content = $content -replace '^OPEN_NOTEBOOK_ENCRYPTION_KEY=$', "OPEN_NOTEBOOK_ENCRYPTION_KEY=$(New-Secret)"
    $content = $content -replace '^OPEN_NOTEBOOK_JWT_SECRET=$', "OPEN_NOTEBOOK_JWT_SECRET=$(New-Secret)"
    $content = $content -replace '^PHASE12_FONT_DIR=.*$', 'PHASE12_FONT_DIR=C:/Windows/Fonts'
    Set-Content -Path $EnvFile -Value $content -Encoding ascii
    foreach ($d in @($ImportDir, $OutDir)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
    Write-Step ".env created with new random secrets (not displayed). Folders: import\, diagnostics\"
}

function Invoke-Exec {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Cmd)
    Invoke-Compose exec -T open_notebook @Cmd
}

switch ($Action) {
    'check' { Invoke-Check }
    'init-env' { Invoke-InitEnv }
    'build' { Invoke-Check; Invoke-Compose build open_notebook }
    'up' {
        Invoke-Check
        if (-not (Test-Path $EnvFile)) { Fail 'Run "init-env" first.' }
        Invoke-Compose up -d
        Write-Step "Web: http://127.0.0.1:$(Get-EnvValue 'PHASE12_WEB_PORT' '8504')  API: http://127.0.0.1:$(Get-EnvValue 'PHASE12_API_PORT' '5057')/docs"
    }
    'status' { Invoke-Compose ps; Invoke-Exec /app/.venv/bin/python -m open_notebook.ocr.cli status }
    'logs' { Invoke-Compose logs --tail 200 open_notebook }
    'import-agri' {
        if (-not $Model -or -not (Test-Path $Model)) { Fail 'Give -Model <path to vie_agri.traineddata>.' }
        $hash = (Get-FileHash -Algorithm SHA256 $Model).Hash.ToLower()
        Write-Step "SHA-256 of the model on this machine: $hash"
        New-Item -ItemType Directory -Force -Path $ImportDir | Out-Null
        Copy-Item -Path $Model -Destination (Join-Path $ImportDir 'vie_agri.traineddata') -Force
        Invoke-Exec /app/.venv/bin/python -m open_notebook.ocr.cli custom import --file /import/vie_agri.traineddata --version $Version --notes 'Phase 12 Windows Local'
        Write-Step "Compare the 'stored ... sha256' line above with $hash, then run: activate-agri -Version $Version"
    }
    'activate-agri' { Invoke-Exec /app/.venv/bin/python -m open_notebook.ocr.cli custom activate --version $Version; Invoke-Exec /app/.venv/bin/python -m open_notebook.ocr.cli custom status }
    'agri-status' { Invoke-Exec /app/.venv/bin/python -m open_notebook.ocr.cli custom status }
    'fixtures' {
        Invoke-Exec /app/.venv/bin/python scripts/ocr/generate_phase12_fixtures.py --out /phase12-out/fixtures --font-dir /fonts
        Write-Step "Synthetic PDFs: $OutDir\fixtures (copy the ones you want into import\ to compare them)"
    }
    { $_ -in @('compare', 'diagnose') } {
        if (-not $Pdf) { Fail 'Give -Pdf <file or folder name inside deploy\phase12-test\import>.' }
        if ($Pdf -match '\.\.' -or [System.IO.Path]::IsPathRooted($Pdf)) { Fail '-Pdf must be a name inside the import folder.' }
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $script = if ($Action -eq 'compare') { 'scripts/ocr/phase12_compare.py' } else { 'scripts/ocr/phase12_diagnose.py' }
        $extra = @()
        if ($FullPage) { $extra += '--full-page' }
        Invoke-Exec /app/.venv/bin/python $script "/import/$Pdf" --engine $Engine --out "/phase12-out/$Action-$stamp" @extra
        Write-Step "Results (document text, keep local): $OutDir\$Action-$stamp"
    }
    'legal-gate' {
        if (-not (Test-Path $EnvFile)) { Fail 'Run "init-env" first.' }
        $value = if ($State -eq 'on') { 'true' } else { 'false' }
        $lines = Get-Content $EnvFile | Where-Object { $_ -notmatch '^\s*OCR_LEGAL_NORMALIZATION_ENABLED\s*=' }
        $lines += "OCR_LEGAL_NORMALIZATION_ENABLED=$value"
        Set-Content -Path $EnvFile -Value $lines -Encoding ascii
        Write-Step "Gate set to $value; recreating ONLY the application container (database untouched)."
        Invoke-Compose up -d --no-deps --no-build --force-recreate open_notebook
    }
    'restart-app' { Invoke-Compose up -d --no-deps --no-build --force-recreate open_notebook }
    'stop' { Invoke-Compose stop; Write-Step 'Stopped. Data kept (no volume or folder deleted).' }
}
