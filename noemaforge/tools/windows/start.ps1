<#
=== NoemaForge File Header ===
File: noemaforge/tools/windows/start.ps1
Zone: tools/windows
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: One-button start for Windows. Resolves a Python interpreter and runs `noema start`
  (readiness check -> ensure data dirs -> launch the localhost Admin GUI -> open the browser).
  Display-safe: starts only the localhost control plane; no GPU/model/privileged actions.
Inputs: optional pass-through flags for `noema start` (e.g. -Port via "--port 8799", --no-browser,
  --check-only, --no-doctor, --background, --force). An explicit -PythonExe override is honored.
Outputs: launches the Admin GUI; prints the dashboard URL.
Side effects: creates user-writable data dirs; spawns the Admin GUI server process.
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
#>
[CmdletBinding()]
param(
    [string]$PythonExe = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$StartArgs = @()
)

$ErrorActionPreference = "Stop"

# Repo + package roots, derived from this script's location (noemaforge/tools/windows/).
$pkgRoot  = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path        # noemaforge/
$cli      = Join-Path $pkgRoot "src\noema_cli.py"
if (-not (Test-Path $cli)) {
    Write-Host "FAIL: cannot find $cli — run this script from a NoemaForge checkout." -ForegroundColor Red
    exit 1
}

# Resolve Python: explicit override (must exist) -> Windows 'py' launcher -> python on PATH.
$pyExe = $null
if ($PythonExe) {
    if (-not (Test-Path $PythonExe)) {
        Write-Host "FAIL: -PythonExe '$PythonExe' does not exist." -ForegroundColor Red
        exit 1
    }
    $pyExe = $PythonExe
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pyExe = "py"
    $pyPrefix = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pyExe = "python"
} else {
    Write-Host "FAIL: no Python found. Install Python 3.10+ and re-run." -ForegroundColor Red
    exit 1
}

$invokeArgs = @()
if ($pyPrefix) { $invokeArgs += $pyPrefix }
$invokeArgs += @($cli, "start")
if ($StartArgs) { $invokeArgs += $StartArgs }

Write-Host "NoemaForge: starting via $pyExe $($invokeArgs -join ' ')" -ForegroundColor Cyan
& $pyExe @invokeArgs
exit $LASTEXITCODE
