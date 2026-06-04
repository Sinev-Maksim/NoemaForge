# === NoemaForge File Header ===
# File: noemaforge/tools/windows/run_admin_gui.ps1
# Zone: release/package
# Version: 0.32.2
# Created: 2026-06-04
# Modified: 2026-06-04
# Purpose: One-command launcher for the NoemaForge Admin GUI dashboard on Windows.
# Inputs: Optional -Port, -PackageRoot, -DataRoot, -PythonExe, -NoBrowser.
# Outputs: Runs the localhost Admin GUI HTTP server and opens the dashboard in the browser.
# Side effects: Creates a writable state directory under -DataRoot; binds a localhost TCP port.
# Tests: PowerShell AST syntax validation plus a localhost /api/health smoke check.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
<#
.SYNOPSIS
  Start the NoemaForge Admin GUI dashboard with a single command.

.DESCRIPTION
  Resolves a suitable Python, serves noemaforge/src/admin_gui_server.py against the
  packaged UI templates, and opens http://127.0.0.1:<port>/ in the default browser.
  Runtime state is written under -DataRoot (default %LOCALAPPDATA%\NoemaForge\admin-gui)
  so the source tree stays clean. Press Ctrl+C to stop the server.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File noemaforge\tools\windows\run_admin_gui.ps1

.EXAMPLE
  pwsh noemaforge/tools/windows/run_admin_gui.ps1 -Port 9000 -NoBrowser
#>
param(
  [int]$Port = 8765,
  [string]$PackageRoot = "",
  [string]$DataRoot = "",
  [string]$PythonExe = "",
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

# Package root holds templates/, configs/, src/, bin/ — i.e. the 'noemaforge' folder
# (this script lives in noemaforge/tools/windows/, so ..\.. is the package root).
if (-not $PackageRoot -or $PackageRoot.Trim() -eq "") {
  $PackageRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

# Writable state lives outside the package so the source tree stays clean.
if (-not $DataRoot -or $DataRoot.Trim() -eq "") {
  $DataRoot = Join-Path $env:LOCALAPPDATA "NoemaForge\admin-gui"
}
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null

# Resolve Python: prefer an explicit override, then the Windows 'py' launcher (canonical
# and on PATH by default), then the shared resolver used by the other Windows tools.
$pyExe = ""
$pyArgs = @()
if ($PythonExe -and (Test-Path $PythonExe)) {
  $pyExe = $PythonExe
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  $pyExe = "py"
  $pyArgs = @("-3")
} else {
  . (Join-Path $PSScriptRoot "lib_python.ps1")
  $pyInfo = ResolveNoemaForgePython -BrainRoot $PackageRoot -PythonExeParam $PythonExe -MinVersion "3.10"
  if ($pyInfo.kind -ne "none") {
    $pyExe = $pyInfo.exe
    $pyArgs = @($pyInfo.args)
  }
}
if (-not $pyExe) {
  Write-Host "FAIL: Python 3.10+ not found. Install Python or set env:NOEMAFORGE_PYTHON / pass -PythonExe." -ForegroundColor Red
  exit 2
}

$url = "http://127.0.0.1:$Port/"
Write-Host "NoemaForge Admin GUI" -ForegroundColor Cyan
Write-Host "  package:    $PackageRoot"
Write-Host "  data_root:  $DataRoot"
Write-Host "  url:        $url"
Write-Host ("  python:     " + $pyExe + " " + ($pyArgs -join " "))
Write-Host "  (press Ctrl+C to stop)"
Write-Host ""

# Open the dashboard in the default browser once the server has had time to bind.
# A detached helper process waits briefly so the first page load succeeds.
if (-not $NoBrowser) {
  Start-Process -WindowStyle Hidden powershell -ArgumentList @(
    "-NoProfile", "-Command", "Start-Sleep -Seconds 2; Start-Process '$url'"
  ) | Out-Null
}

$env:PYTHONDONTWRITEBYTECODE = "1"
& $pyExe @($pyArgs) (Join-Path $PackageRoot "src\admin_gui_server.py") `
  --root $PackageRoot `
  --state (Join-Path $DataRoot "state") `
  --persona-state (Join-Path $DataRoot "persona") `
  --evolution-state (Join-Path $DataRoot "evolution") `
  --model-selection-state (Join-Path $DataRoot "model-selection") `
  --dev-state (Join-Path $DataRoot "dev-team") `
  --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
