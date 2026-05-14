# === NoemaForge File Header ===
# File: noemaforge/tools/windows/noemaforge_check.ps1
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
File: tools/windows/noemaforge_check.ps1
Purpose: Provide the script 'noemaforge_check'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  [string]$Root = "",
  [string]$OutDir = "",
  [string]$PythonExe = "",
  [switch]$Deep,
  [switch]$NoWSL
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
# Function: _Json
# Purpose: Provide the PowerShell routine '_Json'.
# Inputs:
#   - $obj
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _Json($obj) {
  return ($obj | ConvertTo-Json -Depth 12)
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
  $enc = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($path, $text, $enc)
}

# === NoemaForge Autodoc Function Header ===
# Function: _TryStep
# Purpose: Provide the PowerShell routine '_TryStep'.
# Inputs:
#   - $id
#   - $title
#   - $block
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _TryStep($id, $title, [ScriptBlock]$block) {
  $res = [ordered]@{
    id = $id
    title = $title
    status = "PASS"
    message = ""
    data = @{}
  }
  try {
    $out = & $block
    if ($out -is [hashtable] -or $out -is [System.Collections.Specialized.OrderedDictionary]) {
      foreach ($k in $out.Keys) { $res[$k] = $out[$k] }
    }
  } catch {
    $res.status = "FAIL"
    $res.message = "Exception: $($_.Exception.Message)"
    $res.data = @{ stack = $_.ScriptStackTrace }
  }
  return $res
}

# === NoemaForge Autodoc Function Header ===
# Function: _JoinMaybe
# Purpose: Provide the PowerShell routine '_JoinMaybe'.
# Inputs:
#   - $a
#   - $b
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _JoinMaybe($a, $b) {
  if ($a.EndsWith("\\")) { return $a + $b }
  return (Join-Path $a $b)
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

  for ($i = 0; $i -lt 8; $i++) {
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
# Function: _IsWindowsStoreStub
# Purpose: Provide the PowerShell routine '_IsWindowsStoreStub'.
# Inputs:
#   - $path
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function _IsWindowsStoreStub([string]$path) {
  if (!$path) { return $false }
  # Common Windows Store python shim lives under WindowsApps.
  return ($path -match "\\WindowsApps\\") -or ($path -match "AppData\\Local\\Microsoft\\WindowsApps")
}

# === NoemaForge Autodoc Function Header ===
# Function: ResolvePython
# Purpose: Provide the PowerShell routine 'ResolvePython'.
# Inputs:
#   - $BrainRoot
#   - $PythonExeParam
# Called by:
#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.
# Outputs: Console output and side effects implemented in the body below.
# === End NoemaForge Autodoc Function Header ===
function ResolvePython([string]$BrainRoot, [string]$PythonExeParam) {
  # Returns: @{ kind = "exe"|"launcher"|"none"; path = "<path>" }
  $cands = @()

  if ($PythonExeParam -and $PythonExeParam.Trim().Length -gt 0) { $cands += $PythonExeParam }
  if ($env:NOEMAFORGE_PYTHON -and $env:NOEMAFORGE_PYTHON.Trim().Length -gt 0) { $cands += $env:NOEMAFORGE_PYTHON }

  # Common virtualenv locations (repo-local).
  $cands += (Join-Path $BrainRoot ".venv\Scripts\python.exe")
  $cands += (Join-Path $BrainRoot "venv\Scripts\python.exe")
  $cands += (Join-Path $BrainRoot "env\Scripts\python.exe")

  # Common Conda installs (system + user).
  $cands += "C:\ProgramData\anaconda3\python.exe"
  if ($env:USERPROFILE) {
    $cands += (Join-Path $env:USERPROFILE "anaconda3\python.exe")
    $cands += (Join-Path $env:USERPROFILE "miniconda3\python.exe")
    $cands += (Join-Path $env:USERPROFILE "AppData\Local\Programs\Python\Python311\python.exe")
    $cands += (Join-Path $env:USERPROFILE "AppData\Local\Programs\Python\Python312\python.exe")
  }

  foreach ($c in $cands) {
    try {
      if ($c -and (Test-Path $c)) {
        $rp = (Resolve-Path $c).Path
        if (-not (_IsWindowsStoreStub $rp)) {
          return @{ kind = "exe"; path = $rp }
        }
      }
    } catch { }
  }

  # Python launcher (py.exe) is common and usually reliable.
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py -and $py.Source -and -not (_IsWindowsStoreStub $py.Source)) {
    return @{ kind = "launcher"; path = $py.Source }
  }

  # PATH resolution, but ignore Windows Store shims.
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source -and -not (_IsWindowsStoreStub $cmd.Source)) {
    return @{ kind = "exe"; path = $cmd.Source }
  }
  $cmd = Get-Command python3 -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source -and -not (_IsWindowsStoreStub $cmd.Source)) {
    return @{ kind = "exe"; path = $cmd.Source }
  }

  return @{ kind = "none"; path = "" }
}
# -----------------
# Locate Brain root
# -----------------

if ($Root -eq "") {
  # Try to auto-detect brain root from script location.
  $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
  $Brain = FindBrainRoot $ScriptDir
} else {
  $Brain = FindBrainRoot $Root
}

if (!$Brain -or ($Brain.Trim().Length -eq 0)) {
  throw "Could not locate Brain root. Provide -Root <path to noemaforge root>, e.g. -Root C:\\noemaforge-seed\\seed\\noemaforge"
}

$stamp = _NowStamp
if ($OutDir -eq "") {
  $OutDir = Join-Path $Brain "reports\checker\$stamp"
}

$report = [ordered]@{
  apiVersion = "noemaforge.checker/v1"
  kind = "SeedCheckReport"
  created_at = $stamp
  brain_root = $Brain
  steps = @()
  summary = @{}
}

$failCount = 0
$warnCount = 0

Write-Host "NoemaForge checker running..."
Write-Host "  Brain root: $Brain"
Write-Host "  OutDir:     $OutDir"


# -----------------
# Steps
# -----------------

$report.steps += _TryStep "00" "Basic structure" {
  $req = @(
    "manifest.yaml",
    "checksums\SHA256SUMS",
    "configs",
    "src",
    "contracts"
  )
  $missing = @()
  foreach ($r in $req) {
    $p = Join-Path $Brain $r
    if (!(Test-Path $p)) { $missing += $r }
  }
  if ($missing.Count -gt 0) {
    return @{ status = "FAIL"; message = "Missing required paths"; data = @{ missing = $missing } }
  }
  return @{ status = "PASS"; message = "OK" }
}

$report.steps += _TryStep "10" "SHA256SUMS integrity" {
  $sumFile = Join-Path $Brain "checksums\SHA256SUMS"
  if (!(Test-Path $sumFile)) {
    return @{ status = "FAIL"; message = "SHA256SUMS not found" }
  }
  $lines = Get-Content $sumFile
  $ok = 0
  $fail = 0
  $missing = @()
  $mismatch = @()
  foreach ($line in $lines) {
    $t = $line.Trim()
    if ($t.Length -eq 0) { continue }
    $parts = $t -split "\s+", 2
    if ($parts.Count -lt 2) { continue }
    $expected = $parts[0].ToLower()
    $rel = $parts[1].Trim()
    if ($rel.StartsWith("./")) { $rel = $rel.Substring(2) }
    $path = Join-Path $Brain $rel
    if (!(Test-Path $path)) {
      $missing += $rel
      $fail += 1
      continue
    }
    $actual = (Get-FileHash -Algorithm SHA256 $path).Hash.ToLower()
    if ($actual -eq $expected) {
      $ok += 1
    } else {
      $mismatch += @{ file = $rel; expected = $expected; actual = $actual }
      $fail += 1
    }
  }
  $status = "PASS"
  if ($fail -gt 0) { $status = "FAIL" }
  return @{ status = $status; message = "OK=$ok FAIL=$fail"; data = @{ ok = $ok; fail = $fail; missing = $missing; mismatch = $mismatch } }
}

$report.steps += _TryStep "11" "Forbidden artifacts" {
  $forbidden = @()
  $forbidden += Get-ChildItem -Path $Brain -Recurse -Force -File -Filter "*.pyc" -ErrorAction SilentlyContinue
  $forbidden += Get-ChildItem -Path $Brain -Recurse -Force -File -Filter ".DS_Store" -ErrorAction SilentlyContinue
  $forbidden += Get-ChildItem -Path $Brain -Recurse -Force -File -Filter "Thumbs.db" -ErrorAction SilentlyContinue
  $forbiddenDirs = Get-ChildItem -Path $Brain -Recurse -Force -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq "__pycache__" }
  $forbidden += $forbiddenDirs

  # Exclude runtime artifacts from seed checks (reports/, data/, lab outputs).
  $forbidden = $forbidden | Where-Object {
    $_.FullName -notmatch "\\reports\\" -and $_.FullName -notmatch "\\cd\\" -and $_.FullName -notmatch "\\noemaforge-lab\\" -and $_.FullName -notmatch "\\data\\"
  }
  $bin1 = Join-Path $Brain "src\noemaforge-llm-gateway"
  if (Test-Path $bin1) { $forbidden += Get-Item $bin1 }
  $bin2 = Join-Path $Brain "src\noemaforge-llm-gateway.exe"
  if (Test-Path $bin2) { $forbidden += Get-Item $bin2 }

  if ($forbidden.Count -gt 0) {
    return @{ status = "FAIL"; message = "Forbidden artifacts present"; data = @{ paths = ($forbidden | ForEach-Object { $_.FullName }) } }
  }
  return @{ status = "PASS"; message = "Clean" }
}

$report.steps += _TryStep "12" "JSON parse" {
  $jsonFiles = Get-ChildItem -Path $Brain -Recurse -Force -File -Filter "*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\reports\\" -and $_.FullName -notmatch "\\cd\\" -and $_.FullName -notmatch "\\noemaforge-lab\\" -and $_.FullName -notmatch "\\data\\" }
  $bad = @()
  foreach ($f in $jsonFiles) {
    try {
      $null = Get-Content $f.FullName -Raw | ConvertFrom-Json
    } catch {
      $bad += @{ file = $f.FullName; error = $_.Exception.Message }
    }
  }
  if ($bad.Count -gt 0) {
    return @{ status = "FAIL"; message = "JSON parse errors"; data = @{ bad = $bad; total = $jsonFiles.Count } }
  }
  return @{ status = "PASS"; message = "OK ($($jsonFiles.Count) files)" }
}

$report.steps += _TryStep "13" "Filename charset scan" {
  $all = Get-ChildItem -Path $Brain -Recurse -Force -File -ErrorAction SilentlyContinue
  # Exclude runtime outputs (reports/data/lab) from seed scans.
  $all = $all | Where-Object { $_.FullName -notmatch "\\reports\\" -and $_.FullName -notmatch "\\cd\\" -and $_.FullName -notmatch "\\noemaforge-lab\\" -and $_.FullName -notmatch "\\data\\" }
  $nonAscii = @()
  foreach ($f in $all) {
    $name = $f.FullName
    if ($name -match "[^\x00-\x7F]") {
      $nonAscii += $name
    }
  }
  if ($nonAscii.Count -gt 0) {
    return @{ status = "WARN"; message = "Non-ASCII characters found in paths"; data = @{ paths = $nonAscii } }
  }
  return @{ status = "PASS"; message = "All paths ASCII" }
}

$report.steps += _TryStep "14" "Hidden/odd characters scan" {
  $textExt = @(".py", ".ps1", ".sh", ".yaml", ".yml", ".md", ".json")
  $all = Get-ChildItem -Path $Brain -Recurse -Force -File -ErrorAction SilentlyContinue | Where-Object { ($textExt -contains $_.Extension.ToLower()) -and ($_.FullName -notmatch "\\reports\\") -and ($_.FullName -notmatch "\\cd\\") }
  $hits = @()
  foreach ($f in $all) {
    try {
      $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
      # NUL
      if ($bytes -contains 0) { $hits += @{ file = $f.FullName; kind = "NUL" } }
      # UTF-8 BOM
      if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $hits += @{ file = $f.FullName; kind = "UTF8_BOM" }
      }
      # Zero-width spaces in decoded text
      $txt = [System.Text.Encoding]::UTF8.GetString($bytes)
      if ($txt -match "\u200B|\u200C|\u200D|\uFEFF") {
        $hits += @{ file = $f.FullName; kind = "ZERO_WIDTH" }
      }
    } catch {
      $hits += @{ file = $f.FullName; kind = "READ_ERROR"; error = $_.Exception.Message }
    }
  }
  if ($hits.Count -gt 0) {
    return @{ status = "WARN"; message = "Odd chars found (warn-only)"; data = @{ hits = $hits; total = $all.Count } }
  }
  return @{ status = "PASS"; message = "No odd chars" }
}

$report.steps += _TryStep "20" "Python-based deep checks" {
  $pyInfo = ResolvePython $Brain $PythonExe
  if ($pyInfo.kind -eq "none" -or !$pyInfo.path) {
    return @{
      status = "WARN"
      message = "Python not found; skipping deep checks (set -PythonExe or env:NOEMAFORGE_PYTHON to a real python.exe)"
      data = @{ python = $pyInfo }
    }
  }

  $checker = Join-Path $Brain "tools\checker\noemaforge_check.py"
  if (!(Test-Path $checker)) {
    return @{ status = "FAIL"; message = "Python checker missing"; data = @{ expected = $checker; python = $pyInfo } }
  }

  $outJson = Join-Path $OutDir "python_checker.json"
  $stdout = Join-Path $OutDir "python_checker.stdout.txt"
  $stderr = Join-Path $OutDir "python_checker.stderr.txt"

  $args = @()
  if ($pyInfo.kind -eq "launcher") { $args += "-3" }
  $args += @($checker, "--root", $Brain, "--out", $outJson)
  if ($Deep) { $args += "--deep" }

  $oldNoBytecode = $env:PYTHONDONTWRITEBYTECODE
  $env:PYTHONDONTWRITEBYTECODE = "1"

  $p = Start-Process -FilePath $pyInfo.path -ArgumentList $args -NoNewWindow -PassThru -Wait `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr

  if ($oldNoBytecode) { $env:PYTHONDONTWRITEBYTECODE = $oldNoBytecode } else { Remove-Item Env:\PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue }

  $code = $p.ExitCode

  $data = @{}
  if (Test-Path $outJson) {
    try { $data = Get-Content $outJson -Raw | ConvertFrom-Json } catch { $data = @{ parse_error = $_.Exception.Message } }
  }

  $stderrPreview = ""
  if (Test-Path $stderr) {
    try {
      $stderrPreview = Get-Content $stderr -Raw
      if ($stderrPreview.Length -gt 4000) { $stderrPreview = $stderrPreview.Substring(0, 4000) }
    } catch { $stderrPreview = "Could not read stderr: $($_.Exception.Message)" }
  }

  $status = "PASS"
  if ($code -eq 0) { $status = "PASS" }
  elseif ($code -eq 1) { $status = "WARN" }     # WARN-only from python checker
  elseif ($code -eq 2) { $status = "FAIL" }     # FAIL present in python checker
  else { $status = "WARN" }                     # Unknown / environment / launcher errors

  $msg = "python checker exit=$code"
  if ($code -eq 9009) {
    $msg = "Python launch failed (exit=9009). Likely Windows Store shim or missing PATH. Set -PythonExe to real python.exe (e.g., C:\\ProgramData\\anaconda3\\python.exe)."
  }

  return @{
    status = $status
    message = $msg
    data = @{
      python = $pyInfo
      report = $data
      stderr_preview = $stderrPreview
      stdout_path = $stdout
      stderr_path = $stderr
    }
  }
}

$report.steps += _TryStep "30" "WSL/Linux tool availability (optional)" {
  if ($NoWSL) {
    return @{ status = "SKIP"; message = "NoWSL set" }
  }
  $wsl = Get-Command wsl -ErrorAction SilentlyContinue
  if (-not $wsl) {
    return @{ status = "WARN"; message = "wsl.exe not found" }
  }
  $info = ""
  try {
    $info = (& wsl -l -v) -join "\n"
  } catch {
    return @{ status = "WARN"; message = "WSL present but failed to query distros"; data = @{ error = $_.Exception.Message } }
  }
  return @{ status = "PASS"; message = "WSL detected"; data = @{ distros = $info } }
}


# -----------------
# Finalize report
# -----------------

foreach ($s in $report.steps) {
  if ($s.status -eq "FAIL") { $failCount += 1 }
  if ($s.status -eq "WARN") { $warnCount += 1 }
}

$report.summary = @{ fails = $failCount; warns = $warnCount; step_count = $report.steps.Count }

$jsonPath = Join-Path $OutDir "noemaforge_check_report.json"
_WriteFileUtf8 $jsonPath (_Json $report)

# Markdown summary
$md = "# NoemaForge Seed Check Report\n\n" +
      "- Created: $($report.created_at)\n" +
      "- Brain root: $($report.brain_root)\n" +
      "- Steps: $($report.summary.step_count)\n" +
      "- FAIL: $($report.summary.fails)\n" +
      "- WARN: $($report.summary.warns)\n\n" +
      "## Steps\n\n"

foreach ($s in $report.steps) {
  $md += "- **[$($s.id)] $($s.title)**: $($s.status)" + "\n"
  if ($s.message) { $md += "  - $($s.message)\n" }
}

$mdPath = Join-Path $OutDir "noemaforge_check_report.md"
_WriteFileUtf8 $mdPath $md

Write-Host ""; Write-Host "Report written:"
Write-Host "  $jsonPath"
Write-Host "  $mdPath"

if ($failCount -gt 0) {
  Write-Host ""; Write-Host "Seed check finished with FAILURES ($failCount)." -ForegroundColor Red
  exit 2
}

if ($warnCount -gt 0) {
  Write-Host ""; Write-Host "Seed check finished with WARNINGS ($warnCount)." -ForegroundColor Yellow
  exit 1
}

Write-Host ""; Write-Host "Seed check finished OK." -ForegroundColor Green
exit 0
