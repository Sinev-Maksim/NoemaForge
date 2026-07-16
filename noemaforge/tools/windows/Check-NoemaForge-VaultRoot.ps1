# === NoemaForge Autodoc File Header ===
# File: tools/windows/Check-NoemaForge-VaultRoot.ps1
# Purpose: Helper / validation script 'Check-NoemaForge-VaultRoot.ps1'.
# Invoked by / imported from:
#   - direct operator invocation or test discovery
# Public API / entry functions:
#   - module-level helpers / CLI entrypoint
# Inputs:
#   - local filesystem paths, command-line arguments, and NoemaForge runtime/install state
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-13 (manual)
# === End NoemaForge Autodoc File Header ===

# === NoemaForge File Header ===
# File: tools/windows/Check-NoemaForge-VaultRoot.ps1
# Zone: prep
# Purpose: Pre-install / first-boot helper for NoemaForge.
# Callers: bootstrap docs, operator manual, direct user invocation.
# Inputs: command-line arguments, local filesystem paths, NoemaForge seed/install tree.
# Outputs: reports, staged files, status text, or process exit status.
# Side effects: may read/write local files and invoke other NoemaForge helpers.
# Security notes:
#   - Must not bypass ToolProxy for runtime tool execution.
#   - Limited to install-time, prep-time, or host-side validation work.
# === End NoemaForge File Header ===

param(
    [string]$VaultRoot = 'E:\noemaforge-lab\data\Vault',
    [string]$OutDir = 'E:\noemaforge-lab\data\Vault\manifests\noemaforge-metadata-export\diagnose'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $VaultRoot)) {
    throw "Vault root not found: $VaultRoot"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$rootItem = Get-Item -LiteralPath $VaultRoot -Force
$topDirs = Get-ChildItem -LiteralPath $VaultRoot -Directory -Force | Sort-Object Name

$rows = foreach ($d in $topDirs) {
    $fileCount = 0
    try {
        $fileCount = @(Get-ChildItem -LiteralPath $d.FullName -File -Recurse -Force -ErrorAction SilentlyContinue).Count
    } catch {
        $fileCount = -1
    }
    [pscustomobject]@{
        name = $d.Name
        full_name = $d.FullName
        attributes = [string]$d.Attributes
        link_type = $d.LinkType
        target = if ($d.Target) { ($d.Target -join '; ') } else { '' }
        file_count_recursive = $fileCount
        last_write_utc = $d.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
    }
}

$txt = @()
$txt += "VaultRoot        : $VaultRoot"
$txt += "ResolvedFullName : $($rootItem.FullName)"
$txt += "Attributes       : $([string]$rootItem.Attributes)"
$txt += ''
$txt += 'Top-level directories:'
foreach ($r in $rows) {
    $txt += ("  {0} | attrs={1} | link={2} | files={3}" -f $r.name, $r.attributes, ($r.link_type ?? ''), $r.file_count_recursive)
    if ($r.target) {
        $txt += ("    target={0}" -f $r.target)
    }
}

$csvPath = Join-Path $OutDir 'vault.root.diagnose.csv'
$txtPath = Join-Path $OutDir 'vault.root.diagnose.txt'
$rows | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8
Set-Content -LiteralPath $txtPath -Value $txt -Encoding UTF8

Write-Host "Diagnosis written to: $txtPath"
Write-Host "CSV written to      : $csvPath"
