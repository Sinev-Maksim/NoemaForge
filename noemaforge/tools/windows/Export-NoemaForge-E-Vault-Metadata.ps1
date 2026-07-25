# === NoemaForge File Header ===
# File: tools/windows/Export-NoemaForge-E-Vault-Metadata.ps1
# Zone: prep
# Version: 0.32.1
# Created: 2026-05-20
# Modified: 2026-05-20
# Purpose: Thin Windows wrapper over cross-platform Python Vault metadata export.
# Inputs: VaultRoot, OutDir, RepoRoot, PythonExe, RunScanVault and FullHash.
# Outputs: vault.disk_e.metadata.json, vault.disk_e.summary.txt and vault.disk_e.roots.csv.
# Side effects: Limited to requested metadata output directory and optional Vault scan artifacts.
# Tests: noemaforge/tests/test_cross_platform_prep_core_runtime.py
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===

param(
    [string]$VaultRoot = 'E:\noemaforge-lab\data\Vault',
    [string]$OutDir = 'E:\noemaforge-lab\data\Vault\manifests\noemaforge-metadata-export',
    [string]$RepoRoot = '',
    [string]$PythonExe = '',
    [switch]$RunScanVault,
    [switch]$FullHash
)

$ErrorActionPreference = 'Stop'

if (-not $RepoRoot -or $RepoRoot.Trim() -eq '') {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
if (-not $PythonExe -or $PythonExe.Trim() -eq '') {
    if ($env:NOEMAFORGE_PYTHON) { $PythonExe = $env:NOEMAFORGE_PYTHON } else { $PythonExe = 'py' }
}

$Core = Join-Path $RepoRoot 'tools\prep\noemaforge_prep_core.py'
$Args = @($Core, 'export-vault-metadata', '--repo-root', $RepoRoot, '--vault-root', $VaultRoot, '--out-dir', $OutDir)
if ($RunScanVault) { $Args += '--run-scan-vault' }
if ($FullHash) { $Args += '--full-hash' }

& $PythonExe @Args
exit $LASTEXITCODE
