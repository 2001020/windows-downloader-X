# Build WinISO Downloader for Windows.
#
# Output: windows\dist\WinISO-Downloader.exe  (single file, double-click to run)
#
# Requirements: 64-bit Python 3.9+ from python.org (includes Tk).
# Usage:        powershell -ExecutionPolicy Bypass -File windows\build.ps1
#               (or double-click build.bat)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Aria2Version = "1.37.0"
$Aria2Url = "https://github.com/aria2/aria2/releases/download/release-$Aria2Version/aria2-$Aria2Version-win-64bit-build1.zip"
$Aria2Sha256 = "67D015301EEF0B612191212D564C5BB0A14B5B9C4796B76454276A4D28D9B288"

$Here = $PSScriptRoot
$Root = Split-Path -Parent $Here
$Build = Join-Path $Here "build"
$Dist = Join-Path $Here "dist"
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE" }
}

New-Item -ItemType Directory -Force -Path $Build | Out-Null

# Official aria2 Windows build (static, uses the Windows certificate store).
$Aria2Dir = Join-Path $Build "aria2"
$Aria2Exe = Join-Path $Aria2Dir "aria2c.exe"
if (-not (Test-Path $Aria2Exe)) {
    $zip = Join-Path $Build "aria2.zip"
    Write-Host "Downloading aria2 $Aria2Version"
    Invoke-WebRequest -Uri $Aria2Url -OutFile $zip -UseBasicParsing
    $hash = (Get-FileHash -Path $zip -Algorithm SHA256).Hash
    if ($hash -ne $Aria2Sha256) { throw "aria2 download checksum mismatch: $hash" }
    $extract = Join-Path $Build "aria2-extract"
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    Expand-Archive -Path $zip -DestinationPath $extract
    New-Item -ItemType Directory -Force -Path $Aria2Dir | Out-Null
    $src = Get-ChildItem -Path $extract -Directory | Select-Object -First 1
    Copy-Item (Join-Path $src.FullName "aria2c.exe") $Aria2Dir
    Copy-Item (Join-Path $src.FullName "COPYING") $Aria2Dir
}

if (-not $env:SKIP_PIP) {
    Invoke-Checked $Python @("-m", "pip", "install", "-r", (Join-Path $Root "common\requirements-build.txt"))
}

$version = (& $Python -c "import sys; sys.path.insert(0, r'$Root\common'); import winiso; print(winiso.__version__)").Trim()
$parts = ($version.Split(".") + @("0", "0", "0"))[0..3] -join ", "
$versionFile = Join-Path $Build "version_info.txt"
$template = Get-Content (Join-Path $Here "version_info.txt") -Raw -Encoding UTF8
# WriteAllText writes UTF-8 without a BOM, which PyInstaller requires.
[System.IO.File]::WriteAllText($versionFile, $template.Replace("@VERSION@", $version).Replace("@VERSION_TUPLE@", $parts))

Invoke-Checked $Python @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "WinISO-Downloader",
    "--icon", (Join-Path $Here "icon.ico"),
    "--version-file", $versionFile,
    "--paths", (Join-Path $Root "common"),
    "--add-binary", "$Aria2Exe;aria2",
    "--add-data", "$(Join-Path $Root 'common\winiso\assets');assets",
    "--distpath", $Dist,
    "--workpath", (Join-Path $Build "work"),
    "--specpath", $Build,
    (Join-Path $Here "main.py")
)

Write-Host ""
Write-Host "Built: $(Join-Path $Dist 'WinISO-Downloader.exe')"
Get-Item (Join-Path $Dist "WinISO-Downloader.exe") | Format-Table Name, Length
