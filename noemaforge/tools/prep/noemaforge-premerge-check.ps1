# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-premerge-check.ps1
# Zone: release/package
# Version: 0.32.2
# Created: 2026-05-28
# Modified: 2026-05-28
# Purpose: Windows-native premerge audit for release/0.32.2-hardening. Checks version
#   centralization, VERSION files, JSON/YAML parse, py_compile, git-tracked __pycache__,
#   and docs/release.json active fields. Exits non-zero if any check fails.
# Inputs: Working tree rooted at NOEMAFORGE_ROOT (default: repo root relative to this file).
# Outputs: Pass/FAIL per check; summary line; exit code 0 = all pass, 1 = failures.
# Side effects: None (read-only checks; no writes).
# Tests: Run directly: pwsh noemaforge/tools/prep/noemaforge-premerge-check.ps1
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===

[CmdletBinding()]
param(
    [string]$Root = "",
    [string]$ExpectedVersion = "0.32.2",
    [switch]$Strict
)

$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

if (-not $Root) {
    # Three levels up from noemaforge/tools/prep/
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
}

$pass_count = 0
$fail_count = 0

function Pass-Check {
    param([string]$Name, [string]$Detail = "")
    $script:pass_count++
    $line = "[PASS] $Name"
    if ($Detail) { $line += " — $Detail" }
    Write-Host $line
}

function Fail-Check {
    param([string]$Name, [string]$Detail = "")
    $script:fail_count++
    $line = "[FAIL] $Name"
    if ($Detail) { $line += " — $Detail" }
    Write-Host $line -ForegroundColor Red
}

function Ok-Check {
    param([string]$Name, [bool]$Ok, [string]$Detail = "")
    if ($Ok) { Pass-Check $Name $Detail } else { Fail-Check $Name $Detail }
}

Write-Host "=== NoemaForge premerge check $ExpectedVersion ==="
Write-Host "Root: $Root"
Write-Host ""

# ---------------------------------------------------------------------------
# 1. VERSION files
# ---------------------------------------------------------------------------

Write-Host "--- Check 1: VERSION files ---"
foreach ($relPath in @("VERSION", "noemaforge/VERSION", "docs/VERSION")) {
    $fp = Join-Path $Root $relPath
    if (Test-Path $fp) {
        $val = (Get-Content $fp -Raw -Encoding UTF8).Trim()
        Ok-Check "VERSION($relPath)=$ExpectedVersion" ($val -eq $ExpectedVersion) "got: $val"
    } else {
        Fail-Check "VERSION($relPath) exists" "file not found"
    }
}

# ---------------------------------------------------------------------------
# 2. docs/release.json active fields
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- Check 2: docs/release.json ---"
$releaseJsonPath = Join-Path $Root "docs/release.json"
if (Test-Path $releaseJsonPath) {
    try {
        $rj = Get-Content $releaseJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Ok-Check "docs/release.json.version=$ExpectedVersion" ($rj.version -eq $ExpectedVersion) "got: $($rj.version)"
        Ok-Check "docs/release.json.release=$ExpectedVersion" ($rj.release -eq $ExpectedVersion) "got: $($rj.release)"
        Ok-Check "docs/release.json.release_name" ($rj.release_name -like "*$ExpectedVersion*") "got: $($rj.release_name)"
        Ok-Check "docs/release.json.package contains $ExpectedVersion" ($rj.package -like "*$ExpectedVersion*") "got: $($rj.package)"
        $staleStatus = ($rj.status -eq "pre-alpha") -or ($rj.channel -eq "pre-alpha")
        Ok-Check "docs/release.json no stale pre-alpha status/channel" (-not $staleStatus) "status=$($rj.status) channel=$($rj.channel)"
    } catch {
        Fail-Check "docs/release.json parse" $_.Exception.Message
    }
} else {
    Fail-Check "docs/release.json exists" "file not found"
}

# ---------------------------------------------------------------------------
# 3. No hardcoded RUNTIME_VERSION assignment outside noemaforge_version.py
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- Check 3: RUNTIME_VERSION centralization ---"
$srcDir = Join-Path $Root "noemaforge/src"
$versionModule = Join-Path $srcDir "noemaforge_version.py"

if (Test-Path $srcDir) {
    $pyFiles = Get-ChildItem -Path $srcDir -Filter "*.py" -File
    $violations = @()
    foreach ($f in $pyFiles) {
        if ($f.FullName -eq $versionModule) { continue }
        $lines = Get-Content $f.FullName -Encoding UTF8
        $lineNum = 0
        foreach ($line in $lines) {
            $lineNum++
            # Match RUNTIME_VERSION = (assignment), skip import lines
            if ($line -match 'RUNTIME_VERSION\s*=' -and $line -notmatch 'import\s+RUNTIME_VERSION') {
                $violations += "$($f.Name):$lineNum $($line.Trim())"
            }
        }
    }
    Ok-Check "No RUNTIME_VERSION= outside noemaforge_version.py" ($violations.Count -eq 0) "$(if($violations.Count -gt 0){($violations | Select-Object -First 3) -join '; '}else{''})"
} else {
    Fail-Check "noemaforge/src exists" "directory not found"
}

# ---------------------------------------------------------------------------
# 4. py_compile all noemaforge/src/*.py
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- Check 4: py_compile noemaforge/src/*.py ---"
if (Test-Path $srcDir) {
    $pyFiles = Get-ChildItem -Path $srcDir -Filter "*.py" -File
    $compileErrors = @()
    foreach ($f in $pyFiles) {
        $result = python -c "import py_compile; py_compile.compile(r'$($f.FullName)', doraise=True)" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $compileErrors += "$($f.Name): $result"
        }
    }
    Ok-Check "py_compile $($pyFiles.Count) src/*.py files" ($compileErrors.Count -eq 0) "$(if($compileErrors.Count -gt 0){($compileErrors | Select-Object -First 3) -join '; '}else{"$($pyFiles.Count) files OK"})"
} else {
    Fail-Check "py_compile skipped" "noemaforge/src not found"
}

# ---------------------------------------------------------------------------
# 5. JSON parse — noemaforge/configs/*.json
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- Check 5: JSON parse noemaforge/configs/*.json ---"
$configsDir = Join-Path $Root "noemaforge/configs"
if (Test-Path $configsDir) {
    $jsonFiles = Get-ChildItem -Path $configsDir -Filter "*.json" -File
    $jsonErrors = @()
    foreach ($f in $jsonFiles) {
        try {
            $null = Get-Content $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            $jsonErrors += "$($f.Name): $($_.Exception.Message)"
        }
    }
    Ok-Check "JSON parse $($jsonFiles.Count) configs/*.json files" ($jsonErrors.Count -eq 0) "$(if($jsonErrors.Count -gt 0){($jsonErrors | Select-Object -First 3) -join '; '}else{"$($jsonFiles.Count) files OK"})"
} else {
    Fail-Check "JSON parse skipped" "noemaforge/configs not found"
}

# ---------------------------------------------------------------------------
# 6. YAML parse — noemaforge/configs/*.yaml (requires PyYAML)
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- Check 6: YAML parse noemaforge/configs/*.yaml ---"
if (Test-Path $configsDir) {
    $yamlFiles = Get-ChildItem -Path $configsDir -Filter "*.yaml" -File
    $hasPyYaml = ((python -c "import yaml; print('ok')" 2>&1) -eq "ok")
    if ($hasPyYaml) {
        $yamlErrors = @()
        foreach ($f in $yamlFiles) {
            $result = python -c "import yaml; yaml.safe_load(open(r'$($f.FullName)', encoding='utf-8'))" 2>&1
            if ($LASTEXITCODE -ne 0) {
                $yamlErrors += "$($f.Name): $result"
            }
        }
        Ok-Check "YAML parse $($yamlFiles.Count) configs/*.yaml files" ($yamlErrors.Count -eq 0) "$(if($yamlErrors.Count -gt 0){($yamlErrors | Select-Object -First 3) -join '; '}else{"$($yamlFiles.Count) files OK"})"
    } else {
        Write-Host "[SKIP] YAML parse — PyYAML not available (pip install pyyaml)"
    }
}

# ---------------------------------------------------------------------------
# 7. No tracked __pycache__ or *.pyc in git
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "--- Check 7: No tracked __pycache__ or *.py[co] in git ---"
$gitOutput = git -C $Root ls-files --cached 2>&1
if ($LASTEXITCODE -eq 0) {
    $trackedCached = @($gitOutput) | Where-Object { $_ -match '__pycache__' -or $_ -match '\.pyc$' -or $_ -match '\.pyo$' }
    Ok-Check "No tracked __pycache__ or *.py[co]" ($trackedCached.Count -eq 0) "$(if($trackedCached.Count -gt 0){($trackedCached | Select-Object -First 5) -join '; '}else{''})"
} else {
    Write-Host "[SKIP] git ls-files failed — not a git repo or git not found"
}

# ---------------------------------------------------------------------------
# 8. Strict: no hardcoded version string "0.32.1" in active Python source
# ---------------------------------------------------------------------------

if ($Strict -and (Test-Path $srcDir)) {
    Write-Host ""
    Write-Host "--- Check 8 (--Strict): no hardcoded '0.32.1' in src/*.py ---"
    $stalePattern = '"0\.32\.1"'
    $staleFiles = @()
    $pyFiles = Get-ChildItem -Path $srcDir -Filter "*.py" -File
    foreach ($f in $pyFiles) {
        $content = Get-Content $f.FullName -Raw -Encoding UTF8
        if ($content -match $stalePattern) {
            $staleFiles += $f.Name
        }
    }
    Ok-Check "No hardcoded '0.32.1' strings in src/*.py" ($staleFiles.Count -eq 0) "$(if($staleFiles.Count -gt 0){($staleFiles | Select-Object -First 5) -join ', '}else{''})"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "=== Summary: $pass_count passed, $fail_count failed ==="

if ($fail_count -gt 0) {
    Write-Host "PREMERGE CHECK FAILED — fix the above before merging." -ForegroundColor Red
    exit 1
} else {
    Write-Host "PREMERGE CHECK PASSED" -ForegroundColor Green
    exit 0
}
