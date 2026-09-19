<#
    Builds TranscriberSetup-<version>.exe.

    The version is read from transcriber\version.py and passed to the compiler, so the
    setup file name, the exe's version resource, the registry entry the next update
    reads and the app's own update check all come from that one line.

    Usage:
        powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1
        powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1 -Release

    -Release also creates the GitHub release and uploads the setup exe with `gh`.
#>

[CmdletBinding()]
param(
    [switch]$Release,
    [switch]$Draft
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$InstallerDir = Join-Path $RepoRoot 'installer'
$StageDir = Join-Path $InstallerDir 'stage'
$BuildDir = Join-Path $InstallerDir 'build'

function Find-ISCC {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    throw "Inno Setup 6 was not found. Install it with: winget install JRSoftware.InnoSetup"
}

function Get-AppVersion {
    # Parsed rather than imported so the build does not need the app's dependencies.
    $versionFile = Join-Path $RepoRoot 'transcriber\version.py'
    $line = Select-String -Path $versionFile -Pattern '^__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
    if (-not $line) { throw "Could not read __version__ from $versionFile" }
    return $line.Matches[0].Groups[1].Value
}

# Everything the installed app needs at runtime. Kept explicit: a stray folder here
# ends up in every user's install, and a missing one breaks the app after setup.
$AppPayload = @(
    'main.py',
    'global_vars.py',
    'icon.ico',
    'requirements.txt',
    'ctk_ui',
    'transcriber'
)

$version = Get-AppVersion
Write-Host "Building Transcriber $version" -ForegroundColor Cyan

# ---------------------------------------------------------------- stage app files
if (Test-Path $StageDir) { Remove-Item $StageDir -Recurse -Force }
$appStage = Join-Path $StageDir 'app'
New-Item -ItemType Directory -Force -Path $appStage | Out-Null

foreach ($item in $AppPayload) {
    $source = Join-Path $RepoRoot $item
    if (-not (Test-Path $source)) { throw "Payload item is missing: $source" }
    Copy-Item $source -Destination $appStage -Recurse -Force
}

# Compiled caches and any stray weights must never ship inside the wizard.
Get-ChildItem $appStage -Recurse -Directory -Include '__pycache__', 'models' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$staged = (Get-ChildItem $appStage -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("Staged app payload: {0:N1} MB" -f ($staged / 1MB))

# ------------------------------------------------------------------------ compile
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
$iscc = Find-ISCC
Write-Host "Compiling with $iscc"

& $iscc "/DAppVersion=$version" (Join-Path $InstallerDir 'Transcriber.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed with exit code $LASTEXITCODE" }

$setupExe = Join-Path $BuildDir "TranscriberSetup-$version.exe"
if (-not (Test-Path $setupExe)) { throw "Compiler reported success but $setupExe is missing" }

$sizeMb = (Get-Item $setupExe).Length / 1MB
Write-Host ("Built {0} ({1:N1} MB)" -f $setupExe, $sizeMb) -ForegroundColor Green

# ------------------------------------------------------------------------ release
if ($Release) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "The GitHub CLI (gh) is required for -Release. Install it with: winget install GitHub.cli"
    }

    $tag = "v$version"
    # The app's update check compares this tag with its own __version__, so the tag
    # must match exactly or every user is offered an update forever.
    Write-Host "Creating release $tag"

    $args = @('release', 'create', $tag, $setupExe,
              '--title', "Transcriber $version",
              '--generate-notes')
    if ($Draft) { $args += '--draft' }

    & gh @args
    if ($LASTEXITCODE -ne 0) { throw "gh release create failed with exit code $LASTEXITCODE" }
    Write-Host "Released $tag" -ForegroundColor Green
}
