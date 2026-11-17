<#
.SYNOPSIS
  Build the ChatBot5400 offline update package on Windows (Docker Desktop, Linux
  containers, Internet). docs/deployment/OFFLINE_UPDATE_WINDOWS_BUILD.md

.EXAMPLE
  .\scripts\offline\build-package.ps1 -Version 1.3.0-rc.1
  .\scripts\offline\build-package.ps1 -Version 1.3.0-rc.1 -SignKey $HOME\.ssh\cb5400_release -Platform linux/amd64
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Platform = 'linux/amd64',
    [string]$BaseRef = 'v1.2.0',
    [string]$SignKey,
    [string]$Out,
    [string]$ReleaseNotes,
    [switch]$NoBuild
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Out) { $Out = Join-Path $Root 'dist\offline' }
function Fail($m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 2 }

if ($Version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.\-]+)?$') { Fail 'Version must look like 1.3.0-rc.1' }
foreach ($tool in @('docker', 'git')) { if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail "$tool not found" } }
$python = if (Get-Command uv -ErrorAction SilentlyContinue) { @('uv', 'run', '--no-project', 'python') }
          elseif (Get-Command python -ErrorAction SilentlyContinue) { @('python') }
          else { Fail 'Python (or uv) is required' }
if ((& docker info --format '{{.OSType}}') -ne 'linux') { Fail 'Docker Desktop must use Linux containers' }
Push-Location $Root
try {
    if (& git status --porcelain --untracked-files=no) { Fail 'commit or stash your changes first' }
    $commit = (& git rev-parse HEAD).Trim()
    $tag = "chatbot5400:$Version"
    if (-not $NoBuild) {
        & docker image inspect $tag 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Fail "image $tag already exists: remove it deliberately or use -NoBuild" }
        & docker buildx build --platform $Platform --load `
            --build-arg OCR_INSTALL_TESSERACT=true `
            --build-arg OCR_PREINSTALL_RUNTIMES=true `
            --label "org.opencontainers.image.version=$Version" `
            --label "org.opencontainers.image.revision=$commit" `
            --label "org.opencontainers.image.title=ChatBot5400" `
            --target runtime -t $tag .
        if ($LASTEXITCODE -ne 0) { Fail 'docker build failed' }
    }
    New-Item -ItemType Directory -Force -Path $Out | Out-Null
    $pkgArgs = @('scripts/offline/offline_package.py', 'build', '--version', $Version, '--image', $tag,
              '--platform', $Platform, '--git-ref', $commit, '--base-ref', $BaseRef, '--out', $Out)
    if ($SignKey) { $pkgArgs += @('--sign-key', $SignKey) }
    if ($ReleaseNotes) { $pkgArgs += @('--release-notes', $ReleaseNotes) }
    & git rev-parse -q --verify "refs/tags/v$Version" | Out-Null
    if ($LASTEXITCODE -eq 0) { $pkgArgs += @('--bundle-refs', "v$Version") }
    $exe = $python[0]; $pre = @($python | Select-Object -Skip 1)
    & $exe @pre @pkgArgs
    if ($LASTEXITCODE -ne 0) { Fail 'packaging failed' }
} finally { Pop-Location }
