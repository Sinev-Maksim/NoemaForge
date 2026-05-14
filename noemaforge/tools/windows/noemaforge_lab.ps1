# === NoemaForge File Header ===
# File: noemaforge/tools/windows/noemaforge_lab.ps1
# Zone: release/package
# Version: 0.31.13.alpha
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
<#
=== NoemaForge Autodoc File Header ===
File: tools/windows/noemaforge_lab.ps1
Purpose: Provide the script 'noemaforge_lab'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  [string]$LabRoot = "C:\noemaforge-lab",
  # Path to Brain root. Accepts either:
  #   - <root>\noemaforge          (flattened)
  #   - <root>\seed\noemaforge     (as shipped in seed-kit zip)
  [Alias("Root","BrainRoot")]
  [string]$SeedRoot = "",
  [switch]$AutoManifest,
  [switch]$FullHash,
  [switch]$AllowRelativeLabRoot,
  [string]$PythonExe = "",
  [string]$ReportPath = ""
)

$ErrorActionPreference = "Continue"

# === NoemaForge Autodoc Function Header ===
# Function: _NowStamp
# Purpose: Provide the PowerShell routine '_NowStamp'.
# Inputs:
#   - See the param() block or in-body variable handling below.
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _NowStamp {
  return (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
}

# === NoemaForge Autodoc Function Header ===
# Function: FindBrainRoot
# Purpose: Provide the PowerShell routine 'FindBrainRoot'.
# Inputs:
#   - $StartDir
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function FindBrainRoot([string]$StartDir) {
  $d = Resolve-Path $StartDir -ErrorAction SilentlyContinue
  if (!$d) { return "" }

  for ($i = 0; $i -lt 10; $i++) {
    $cand = $d.Path

    $m1 = Join-Path $cand "manifest.yaml"
    $s1 = Join-Path $cand "checksums\SHA256SUMS"
    if ((Test-Path $m1) -and (Test-Path $s1)) {
      return $cand
    }

    $sb = Join-Path $cand "seed\noemaforge"
    $m2 = Join-Path $sb "manifest.yaml"
    $s2 = Join-Path $sb "checksums\SHA256SUMS"
    if ((Test-Path $m2) -and (Test-Path $s2)) {
      return (Resolve-Path $sb).Path
    }

    $parent = Split-Path -Parent $cand
    if (!$parent -or ($parent -eq $cand)) { break }
    $d = Resolve-Path $parent -ErrorAction SilentlyContinue
    if (!$d) { break }
  }

  return ""
}

# === NoemaForge Autodoc Function Header ===
# Function: _IsAbsolutePath
# Purpose: Provide the PowerShell routine '_IsAbsolutePath'.
# Inputs:
#   - $p
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _IsAbsolutePath([string]$p) {
  if (!$p) { return $false }
  return ($p -match '^[a-zA-Z]:\\') -or ($p -match '^\\\\')
}

# === NoemaForge Autodoc Function Header ===
# Function: _FailFast
# Purpose: Provide the PowerShell routine '_FailFast'.
# Inputs:
#   - $msg
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _FailFast([string]$msg) {
  Write-Host ("FAIL: " + $msg) -ForegroundColor Red
  exit 2
}

# === NoemaForge Autodoc Function Header ===
# Function: _Warn
# Purpose: Provide the PowerShell routine '_Warn'.
# Inputs:
#   - $msg
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _Warn([string]$msg) {
  Write-Host ("WARN: " + $msg) -ForegroundColor Yellow
}

# === NoemaForge Autodoc Function Header ===
# Function: _NormalizeAndCreateDir
# Purpose: Provide the PowerShell routine '_NormalizeAndCreateDir'.
# Inputs:
#   - $p
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _NormalizeAndCreateDir([string]$p) {
  if (!(Test-Path $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null }
  return (Resolve-Path $p).Path
}

# === NoemaForge Autodoc Function Header ===
# Function: _ValidateLabRoot
# Purpose: Provide the PowerShell routine '_ValidateLabRoot'.
# Inputs:
#   - $BrainRoot
#   - $LabRootRaw
#   - $AllowRelative
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _ValidateLabRoot([string]$BrainRoot, [string]$LabRootRaw, [bool]$AllowRelative) {
  $orig = $LabRootRaw
  if (!$LabRootRaw -or ($LabRootRaw.Trim().Length -eq 0)) {
    _FailFast "LabRoot is empty."
  }

  $trim = $LabRootRaw.Trim()
  if ($trim.ToLower() -eq "cd") {
    _FailFast "LabRoot was 'cd'. This usually happens when a multi-line PowerShell command (with backticks) was pasted into CMD. Use the one-line command or tools\\windows\\run_lab.cmd."
  }

  # Require absolute paths by default (to avoid accidental relative paths like 'cd' or similar)
  if (-not (_IsAbsolutePath $trim)) {
    if (-not $AllowRelative) {
      _FailFast ("LabRoot must be an absolute path (e.g. C:\\Users\\...\\noemaforge-lab). Got: '" + $orig + "'.")
    }
    $trim = Join-Path $BrainRoot $trim
  }

  $resolved = _NormalizeAndCreateDir $trim

  try {
    $br = (Resolve-Path $BrainRoot).Path
    # Only warn if LabRoot is a *descendant* of BrainRoot (not just a string-prefix sibling like 'noemaforge' vs 'noemaforge-lab')
    $brN = $br.TrimEnd('\') + '\'
    $lrN = $resolved.TrimEnd('\') + '\'
    if ($lrN.StartsWith($brN, [System.StringComparison]::OrdinalIgnoreCase)) {
      _Warn "LabRoot is inside BrainRoot. That's allowed, but it can clutter the repo. Recommended: put LabRoot as a sibling folder (e.g. C:\Users\...\noemaforge-lab)."
    }
  } catch {}

  return $resolved
}

# === NoemaForge Autodoc Function Header ===
# Function: _DetectCommonFootguns
# Purpose: Provide the PowerShell routine '_DetectCommonFootguns'.
# Inputs:
#   - $BrainRoot
#   - $LabRootRaw
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _DetectCommonFootguns([string]$BrainRoot, [string]$LabRootRaw) {
  # If someone previously ran with LabRoot='cd', a 'cd\data' directory might exist inside brain root.
  $cdData = Join-Path $BrainRoot "cd\data"
  if (Test-Path $cdData) {
    _Warn ("Found stray '" + $cdData + "'. This likely came from a broken multi-line command in CMD. You can delete the '" + (Join-Path $BrainRoot "cd") + "' folder if it's not needed.")
  }
}

# === NoemaForge Autodoc Function Header ===
# Function: _WriteFileUtf8
# Purpose: Provide the PowerShell routine '_WriteFileUtf8'.
# Inputs:
#   - $path
#   - $text
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _WriteFileUtf8($path, $text) {
  $dir = Split-Path -Parent $path
  if ($dir -and !(Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  [System.IO.File]::WriteAllText($path, $text, [System.Text.Encoding]::UTF8)
}


$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

. (Join-Path $ScriptDir "lib_python.ps1")

# Auto-detect brain root if not passed explicitly
if ($SeedRoot -eq "") {
  $SeedRoot = FindBrainRoot $ScriptDir
} else {
  # Normalize passed root; also allows passing the parent that contains seed\noemaforge
  $SeedRoot = FindBrainRoot $SeedRoot
}

if (!$SeedRoot -or ($SeedRoot.Trim().Length -eq 0)) {
  Write-Host "FAIL: Could not locate Brain root from '$ScriptDir'." -ForegroundColor Red
  Write-Host "  Hint: pass -SeedRoot <path to noemaforge root>, e.g. -SeedRoot C:\Users\<you>\Projects\noemaforge" -ForegroundColor Yellow
  exit 2
}

$pyInfo = ResolveNoemaForgePython -BrainRoot $SeedRoot -PythonExeParam $PythonExe -MinVersion "3.10"
if ($pyInfo.kind -eq "none") {
  Write-Host "FAIL: Python 3.10+ not found. Install Python or pass -PythonExe <path to python.exe> or set env:NOEMAFORGE_PYTHON." -ForegroundColor Red
  exit 2
}
$pyExe = $pyInfo.exe
$pyArgs = $pyInfo.args
Write-Host ("  Python: " + $pyExe + " " + (($pyArgs -join " ")) + " (v" + $pyInfo.version + ")")


# Prevent creation of __pycache__/*.pyc inside the repo during lab prep.
# (The seed kit must remain "sterile" to pass verify_seed/noemaforge_check.)
$env:PYTHONDONTWRITEBYTECODE = "1"

# -----------------
# Validate / normalize LabRoot
# -----------------
$LabRoot = _ValidateLabRoot $SeedRoot $LabRoot $AllowRelativeLabRoot
_DetectCommonFootguns $SeedRoot $LabRoot

$lib = Join-Path $LabRoot "data\Library"
$vault = Join-Path $LabRoot "data\Vault"
$ws = Join-Path $LabRoot "data\Workspace"
$outDir = Join-Path $LabRoot "data\Workspace\outbox\headgw"

if ($ReportPath -eq "") {
  $ReportPath = Join-Path $LabRoot ("data\Reports\lab_run_" + (_NowStamp) + ".json")
}

Write-Host "NoemaForge Lab runner"
Write-Host "  ScriptDir: $ScriptDir"
Write-Host "  BrainRoot: $SeedRoot"
Write-Host "  LabRoot:   $LabRoot"
Write-Host "  Hint: use tools\\windows\\run_lab.cmd to avoid CMD line-continuation issues"
Write-Host "  Report:    $ReportPath"

$results = @()
$failCount = 0

# === NoemaForge Autodoc Function Header ===
# Function: RunStep
# Purpose: Provide the PowerShell routine 'RunStep'.
# Inputs:
#   - $id
#   - $title
#   - $block
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function RunStep($id, $title, [ScriptBlock]$block) {
  $res = [ordered]@{
    id = $id
    title = $title
    status = "PASS"
    message = ""
    data = @{}
  }

  try {
    & $block
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
      $res.status = "FAIL"
      $res.message = "ExitCode=$LASTEXITCODE"
    }
  } catch {
    $res.status = "FAIL"
    $res.message = $_.Exception.Message
  }

  $script:results += $res
  if ($res.status -ne "PASS") { $script:failCount += 1 }
}

# 1) Prepare workspace
RunStep "10" "Prepare workspace layout" {
  $prep = Join-Path $SeedRoot "tools\windows\prepare_workspace.ps1"
  if (!(Test-Path $prep)) { throw "prepare_workspace.ps1 not found: $prep" }
  & powershell -ExecutionPolicy Bypass -File $prep -LabRoot $LabRoot
}



# 1.5) Process inbox (optional; pre-start convenience)
RunStep "15" "Process inbox (Library/Vault)" {
  $proc = Join-Path $SeedRoot "tools\prep\process_inbox.py"
  if (Test-Path $proc) {
    $out = Join-Path $LabRoot ("data\Reports\inbox_process_" + (_NowStamp) + ".json")
    $args = @("--library-root", $lib, "--vault-root", $vault, "--workspace-root", $ws, "--out", $out)
    Write-Host "Running: process_inbox.py" -ForegroundColor Cyan
    & $pyExe @pyArgs $proc @args
  } else {
    Write-Host "SKIP: process_inbox.py not found" -ForegroundColor Yellow
  }
}

# 1.6) Ingest Telegram exports (offline)
RunStep "16" "Scan Telegram exports (incremental)" {
  $scanTg = Join-Path $SeedRoot "tools\prep\scan_tg.py"
  if (Test-Path $scanTg) {
    Write-Host "Running: scan_tg.py" -ForegroundColor Cyan
    & $pyExe @pyArgs $scanTg @("--lab-root", $LabRoot)
  } else {
    Write-Host "SKIP: scan_tg.py not found" -ForegroundColor Yellow
  }
}

# 1.7) Ingest Tabs/Reading list exports (offline)
RunStep "17" "Scan Tabs exports (incremental)" {
  $scanTabs = Join-Path $SeedRoot "tools\prep\scan_tabs.py"
  if (Test-Path $scanTabs) {
    Write-Host "Running: scan_tabs.py" -ForegroundColor Cyan
    & $pyExe @pyArgs $scanTabs @("--lab-root", $LabRoot)
  } else {
    Write-Host "SKIP: scan_tabs.py not found" -ForegroundColor Yellow
  }
}

# 2) Scan library (incremental)
RunStep "20" "Scan Library (incremental)" {
  $scanLib = Join-Path $SeedRoot "tools\prep\scan_library.py"
  if (!(Test-Path $scanLib)) { throw "scan_library.py not found: $scanLib" }
  $libArgs = @("--library-root", $lib)
  if ($AutoManifest) { $libArgs += "--auto-manifest" }
  if ($FullHash) { $libArgs += "--full-hash" }
  Write-Host "Running: scan_library.py" -ForegroundColor Cyan
  & $pyExe @pyArgs $scanLib @libArgs
}

# 3) Scan vault (incremental)
RunStep "30" "Scan Vault (incremental)" {
  $scanVault = Join-Path $SeedRoot "tools\prep\scan_vault.py"
  if (!(Test-Path $scanVault)) { throw "scan_vault.py not found: $scanVault" }
  $vaultArgs = @("--vault-root", $vault)
  if ($AutoManifest) { $vaultArgs += "--auto-manifest" }
  if ($FullHash) { $vaultArgs += "--full-hash" }
  Write-Host "Running: scan_vault.py" -ForegroundColor Cyan
  & $pyExe @pyArgs $scanVault @vaultArgs
}

# 4) Generate head-gateway derived assets
RunStep "40" "Generate intent-router + ui-registry (from head-gateway)" {
  $gen = Join-Path $SeedRoot "tools\prep\generate_head_gateway_assets.py"
  $head = Join-Path $SeedRoot "configs\head-gateway.json"
  if (!(Test-Path $gen)) { throw "generate_head_gateway_assets.py not found: $gen" }
  if (!(Test-Path $head)) { throw "head-gateway.json not found: $head" }
  Write-Host "Generating: intent-router + ui-registry" -ForegroundColor Cyan
  & $pyExe @pyArgs $gen --head $head --out-dir $outDir --write-to-configs
}

# Write report
$report = [ordered]@{
  apiVersion = "noemaforge.lab/v1"
  kind = "LabPrepReport"
  created_at = _NowStamp
  brain_root = $SeedRoot
  lab_root = $LabRoot
  script_dir = $ScriptDir
  results = $results
  summary = [ordered]@{
    fails = $failCount
    step_count = $results.Count
  }
}

_WriteFileUtf8 $ReportPath (($report | ConvertTo-Json -Depth 12))

if ($failCount -gt 0) {
  Write-Host ("DONE with FAILURES: " + $failCount) -ForegroundColor Yellow
  Write-Host ("See report: " + $ReportPath) -ForegroundColor Yellow
  exit 1
}

Write-Host "OK: Lab preparation + scans complete" -ForegroundColor Green
exit 0
