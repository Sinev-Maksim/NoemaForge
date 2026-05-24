# === NoemaForge File Header ===
# File: noemaforge/tools/windows/verify_seed.ps1
# Zone: release/package
# Version: 0.31.13.alpha-patched1
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
File: tools/windows/verify_seed.ps1
Purpose: Provide the script 'verify_seed'.
Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.
Inputs: Parameters and environment variables declared in the script.
Outputs: Console output, spawned processes, and filesystem changes as implemented below.
AutoDoc: refreshed 2026-04-09 (heuristic)
#>

param(
  # Optional explicit brain root. Accepts either:
  #   - <root>\seed\noemaforge
  #   - <root>\noemaforge
  [string]$Root = ""
)

$ErrorActionPreference = "Stop"

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

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Brain = ""
if ($Root -and ($Root.Trim().Length -gt 0)) {
  $Brain = FindBrainRoot $Root
} else {
  $Brain = FindBrainRoot $ScriptDir
}

if (!$Brain -or ($Brain.Trim().Length -eq 0)) {
  throw "Could not locate Brain root from '$ScriptDir'. Pass -Root <path to noemaforge root>, e.g. -Root C:\\noemaforge-seed\\seed\\noemaforge"
}

$SumFile = Join-Path $Brain "checksums\SHA256SUMS"

if (!(Test-Path $SumFile)) {
  throw "SHA256SUMS not found: $SumFile"
}

Write-Host "Verifying hashes under: $Brain"

$lines = Get-Content $SumFile
$ok = 0
$fail = 0

foreach ($line in $lines) {
  if ($line.Trim().Length -eq 0) { continue }
  $parts = $line -split "\s+", 2
  if ($parts.Count -lt 2) { continue }
  $expected = $parts[0].ToLower()
  $rel = $parts[1].Trim()
  if ($rel.StartsWith("./")) { $rel = $rel.Substring(2) }
  $path = Join-Path $Brain $rel

  if (!(Test-Path $path)) {
    Write-Host "MISSING: $rel"
    $fail += 1
    continue
  }

  $actual = (Get-FileHash -Algorithm SHA256 $path).Hash.ToLower()
  if ($actual -eq $expected) {
    $ok += 1
  } else {
    Write-Host "FAIL: $rel"
    Write-Host "  expected: $expected"
    Write-Host "  actual:   $actual"
    $fail += 1
  }
}


# Forbidden artifact checks (these should never ship in the seed kit)
$forbidden = @()
$forbidden += Get-ChildItem -Path $Brain -Recurse -Force -File -Filter "*.pyc" -ErrorAction SilentlyContinue
$forbidden += Get-ChildItem -Path $Brain -Recurse -Force -File -Filter ".DS_Store" -ErrorAction SilentlyContinue
$forbidden += Get-ChildItem -Path $Brain -Recurse -Force -File -Filter "Thumbs.db" -ErrorAction SilentlyContinue
$forbiddenDirs = Get-ChildItem -Path $Brain -Recurse -Force -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq "__pycache__" }
$forbidden += $forbiddenDirs
$bin1 = Join-Path $Brain "src\noemaforge-llm-gateway"
if (Test-Path $bin1) { $forbidden += Get-Item $bin1 }
$bin2 = Join-Path $Brain "src\noemaforge-llm-gateway.exe"
if (Test-Path $bin2) { $forbidden += Get-Item $bin2 }
if ($forbidden.Count -gt 0) {
  Write-Host "FORBIDDEN ARTIFACTS FOUND:"
  foreach ($x in $forbidden) { Write-Host ("  " + $x.FullName) }
  exit 1
}

Write-Host "OK: $ok  FAIL: $fail"
if ($fail -gt 0) { exit 1 }
