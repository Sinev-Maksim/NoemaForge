# === NoemaForge File Header ===
# File: noemaforge/tools/windows/lib_python.ps1
# Zone: release/package
# Version: 0.32.1
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
File: tools/windows/lib_python.ps1
Purpose: Provide the script 'lib_python'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

# NoemaForge Windows helper: resolve a usable Python 3.10+ even if it's NOT on PATH.
#
# Usage:
#   . (Join-Path $PSScriptRoot "lib_python.ps1")
#   $py = ResolveNoemaForgePython -BrainRoot $RepoRoot -PythonExeParam $PythonExe -MinVersion "3.10"
#   if ($py.kind -eq "none") { ... }
#   & $py.exe @($py.args) script.py ...

# === NoemaForge Autodoc Function Header ===
# Function: _IsWindowsStoreStub
# Purpose: Provide the PowerShell routine '_IsWindowsStoreStub'.
# Inputs:
#   - $path
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _IsWindowsStoreStub([string]$path) {
  if (-not $path) { return $false }
  return ($path -match "\\WindowsApps\\") -or ($path -match "AppData\\Local\\Microsoft\\WindowsApps")
}

# === NoemaForge Autodoc Function Header ===
# Function: _ParseVersionTuple
# Purpose: Provide the PowerShell routine '_ParseVersionTuple'.
# Inputs:
#   - $v
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _ParseVersionTuple([string]$v) {
  # Returns int[3] or $null
  if (-not $v) { return $null }
  $t = $v.Trim()
  if ($t -match "^([0-9]+)\\.([0-9]+)\\.([0-9]+)") {
    return @([int]$matches[1], [int]$matches[2], [int]$matches[3])
  }
  if ($t -match "^([0-9]+)\\.([0-9]+)") {
    return @([int]$matches[1], [int]$matches[2], 0)
  }
  return $null
}

# === NoemaForge Autodoc Function Header ===
# Function: _VersionAtLeast
# Purpose: Provide the PowerShell routine '_VersionAtLeast'.
# Inputs:
#   - $have
#   - $need
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _VersionAtLeast([int[]]$have, [int[]]$need) {
  if (-not $have -or -not $need) { return $false }
  for ($i = 0; $i -lt 3; $i++) {
    if ($have[$i] -gt $need[$i]) { return $true }
    if ($have[$i] -lt $need[$i]) { return $false }
  }
  return $true
}

# === NoemaForge Autodoc Function Header ===
# Function: _ProbePythonVersion
# Purpose: Provide the PowerShell routine '_ProbePythonVersion'.
# Inputs:
#   - $exe
#   - $pyArgs
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _ProbePythonVersion([string]$exe, [string[]]$pyArgs) {
  # Returns "X.Y.Z" or "".
  # We intentionally capture stderr too, because some builds print version output there.
  try {
    $out = & $exe @pyArgs -c "import sys; print(sys.version.split()[0])" 2>&1
    if ($LASTEXITCODE -eq 0 -and $out) {
      # $out can be a string or an array of strings; normalize to text first.
      $text = (@($out) -join "`n")
      foreach ($line in ($text -split "\r?\n")) {
        $m = $line.Trim()
        if ($m -match "^[0-9]+\\.[0-9]+(\\.[0-9]+)?$") { return $m }
      }
    }
  } catch {}

  try {
    $out2 = & $exe @pyArgs -V 2>&1
    if ($out2) {
      $t = ((@($out2) -join "`n")).Trim()
      if ($t -match "Python\\s+([0-9]+\\.[0-9]+(\\.[0-9]+)?)") { return $matches[1] }
    }
  } catch {}

  try {
    $out3 = & $exe @pyArgs --version 2>&1
    if ($out3) {
      $t = ((@($out3) -join "`n")).Trim()
      if ($t -match "Python\\s+([0-9]+\\.[0-9]+(\\.[0-9]+)?)") { return $matches[1] }
    }
  } catch {}

  return ""
}

# === NoemaForge Autodoc Function Header ===
# Function: _AddRegPythonCandidates
# Purpose: Provide the PowerShell routine '_AddRegPythonCandidates'.
# Inputs:
#   - $regRoot
#   - $list
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _AddRegPythonCandidates([string]$regRoot, [ref]$list) {
  try {
    if (-not (Test-Path $regRoot)) { return }
    $vers = Get-ChildItem $regRoot -ErrorAction SilentlyContinue
    foreach ($vk in $vers) {
      $ip = Join-Path $vk.PSPath "InstallPath"
      if (-not (Test-Path $ip)) { continue }
      try {
        $rk = Get-Item $ip -ErrorAction SilentlyContinue
        if ($rk) {
          $exe = $rk.GetValue("ExecutablePath")
          if ($exe) { $list.Value += [string]$exe }
          $base = $rk.GetValue("")
          if ($base) { $list.Value += (Join-Path ([string]$base) "python.exe") }
        }
      } catch {}
    }
  } catch {}
}

# === NoemaForge Autodoc Function Header ===
# Function: ResolveNoemaForgePython
# Purpose: Provide the PowerShell routine 'ResolveNoemaForgePython'.
# Inputs:
#   - $BrainRoot
#   - $PythonExeParam
#   - $MinVersion
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function ResolveNoemaForgePython {
  param(
    [string]$BrainRoot = "",
    [string]$PythonExeParam = "",
    [string]$MinVersion = "3.10"
  )

  $need = _ParseVersionTuple $MinVersion
  if (-not $need) { $need = @(3,10,0) }

  $explicit = @()
  $cands = @()

  # 1) Explicit parameter and environment override
  if ($PythonExeParam -and $PythonExeParam.Trim().Length -gt 0) {
    $explicit += $PythonExeParam
    $cands += $PythonExeParam
  }
  if ($env:NOEMAFORGE_PYTHON -and $env:NOEMAFORGE_PYTHON.Trim().Length -gt 0) {
    $explicit += $env:NOEMAFORGE_PYTHON
    $cands += $env:NOEMAFORGE_PYTHON
  }

  # 2) Conda env (works even if python isn't on PATH)
  if ($env:CONDA_PREFIX -and $env:CONDA_PREFIX.Trim().Length -gt 0) {
    $cands += (Join-Path $env:CONDA_PREFIX "python.exe")
  }

  # 3) Common repo-local virtualenv locations
  if ($BrainRoot -and $BrainRoot.Trim().Length -gt 0) {
    $cands += (Join-Path $BrainRoot ".venv\\Scripts\\python.exe")
    $cands += (Join-Path $BrainRoot "venv\\Scripts\\python.exe")
    $cands += (Join-Path $BrainRoot "env\\Scripts\\python.exe")
  }

  # 4) Common installs
  $cands += "C:\\ProgramData\\anaconda3\\python.exe"
  $cands += "C:\\ProgramData\\miniconda3\\python.exe"
  $cands += "C:\\Python311\\python.exe"
  $cands += "C:\\Python312\\python.exe"
  $cands += "C:\\Program Files\\Python311\\python.exe"
  $cands += "C:\\Program Files\\Python312\\python.exe"
  $cands += "C:\\Program Files (x86)\\Python311\\python.exe"
  $cands += "C:\\Program Files (x86)\\Python312\\python.exe"

  if ($env:USERPROFILE) {
    $cands += (Join-Path $env:USERPROFILE "anaconda3\\python.exe")
    $cands += (Join-Path $env:USERPROFILE "miniconda3\\python.exe")
    $cands += (Join-Path $env:USERPROFILE "AppData\\Local\\Programs\\Python\\Python311\\python.exe")
    $cands += (Join-Path $env:USERPROFILE "AppData\\Local\\Programs\\Python\\Python312\\python.exe")
  }

  # 5) Registry-based discovery (handles most official python installs)
  $regList = @()
  _AddRegPythonCandidates "HKLM:\\SOFTWARE\\Python\\PythonCore" ([ref]$regList)
  _AddRegPythonCandidates "HKCU:\\SOFTWARE\\Python\\PythonCore" ([ref]$regList)
  _AddRegPythonCandidates "HKLM:\\SOFTWARE\\WOW6432Node\\Python\\PythonCore" ([ref]$regList)
  foreach ($r in $regList) { if ($r) { $cands += $r } }

  # 6) Try candidates that are actual exe paths
  foreach ($c in $cands) {
    try {
      if (-not $c) { continue }
      $p = $c.Trim('"')
      if (-not (Test-Path $p)) { continue }
      $rp = (Resolve-Path $p).Path
      if (_IsWindowsStoreStub $rp) { continue }

      $ver = _ProbePythonVersion $rp @()
      if (-not $ver) { continue }
      $have = _ParseVersionTuple $ver
      if (_VersionAtLeast $have $need) {
        return @{ kind = "exe"; exe = $rp; args = @(); version = $ver; source = "path" }
      }
    } catch {}
  }

  # 6b) Fallback: if an explicit python path was provided but version probing failed,
  # accept it if it can run a trivial command.
  foreach ($e in $explicit) {
    try {
      if (-not $e) { continue }
      $p = $e.Trim('"')
      if (-not (Test-Path $p)) { continue }
      $rp = (Resolve-Path $p).Path
      if (_IsWindowsStoreStub $rp) { continue }

      $ok = & $rp -c "print('ok')" 2>&1
      if ($LASTEXITCODE -eq 0) {
        return @{ kind = "exe"; exe = $rp; args = @(); version = "unknown"; source = "explicit_unverified" }
      }
    } catch {}
  }

  # 7) Try python on PATH (if present, but ignore Windows Store stubs)
  foreach ($name in @("python", "python3")) {
    try {
      $cmd = Get-Command $name -ErrorAction SilentlyContinue
      if ($cmd -and $cmd.Source -and -not (_IsWindowsStoreStub $cmd.Source)) {
        $ver = _ProbePythonVersion $cmd.Source @()
        if ($ver) {
          $have = _ParseVersionTuple $ver
          if (_VersionAtLeast $have $need) {
            return @{ kind = "exe"; exe = $cmd.Source; args = @(); version = $ver; source = "PATH:$name" }
          }
        }
      }
    } catch {}
  }

  # 8) Python launcher (py.exe) — try to force 3.10+
  $pyExe = ""
  try {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd -and $pyCmd.Source) { $pyExe = $pyCmd.Source }
  } catch {}
  if (-not $pyExe) {
    foreach ($p in @("C:\\Windows\\py.exe", "C:\\Windows\\System32\\py.exe")) {
      if (Test-Path $p) { $pyExe = $p; break }
    }
  }
  if ($pyExe -and (Test-Path $pyExe) -and -not (_IsWindowsStoreStub $pyExe)) {
    $ver = _ProbePythonVersion $pyExe @("-3.10")
    if ($ver) {
      $have = _ParseVersionTuple $ver
      if (_VersionAtLeast $have $need) {
        return @{ kind = "launcher"; exe = $pyExe; args = @("-3.10"); version = $ver; source = "py" }
      }
    }
  }

  return @{ kind = "none"; exe = ""; args = @(); version = ""; source = "" }
}
