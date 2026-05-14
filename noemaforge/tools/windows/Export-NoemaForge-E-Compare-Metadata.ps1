# === NoemaForge Autodoc File Header ===
# File: tools/windows/Export-NoemaForge-E-Compare-Metadata.ps1
# Purpose: Helper / validation script 'Export-NoemaForge-E-Compare-Metadata.ps1'.
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
# File: tools/windows/Export-NoemaForge-E-Compare-Metadata.ps1
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
    [string]$RealVaultRoot = 'E:\Vault',
    [string]$LabVaultRoot = 'E:\noemaforge-lab\data\Vault',
    [string]$OutDir = 'E:\Vault\manifests\noemaforge-metadata-export',
    [string]$RepoRoot = '',
    [string]$PythonExe = 'py',
    [switch]$RunScanVault
)

$ErrorActionPreference = 'Stop'

function To-Posix([string]$Path) {
    return ($Path -replace '\\','/')
}

function Get-Roots([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root)) { return @() }
    return @(Get-ChildItem -LiteralPath $Root -Directory -Force | Select-Object -ExpandProperty FullName)
}

function Count-Files([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    return @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force).Count
}

function Preview-Inbox([string]$VaultRoot) {
    $inbox = Join-Path $VaultRoot 'inbox'
    if (-not (Test-Path -LiteralPath $inbox)) { return @() }
    return @(Get-ChildItem -LiteralPath $inbox -File -Recurse -Force |
        Select-Object -First 50 |
        ForEach-Object {
            [pscustomobject]@{
                rel = $_.FullName.Substring($inbox.Length).TrimStart('\\','/') -replace '\\','/'
                ext = $_.Extension.ToLowerInvariant()
                size = [int64]$_.Length
            }
        })
}

function Build-Record([string]$Label, [string]$VaultRoot) {
    $exists = Test-Path -LiteralPath $VaultRoot
    $bucketRoots = @{}
    $counts = @{}
    if ($exists) {
        $top = Get-Roots $VaultRoot
        $bucketRoots.models = @($top | Where-Object { (Split-Path $_ -Leaf).ToLower().StartsWith('models') } | Sort-Object)
        $bucketRoots.adapters = @($top | Where-Object { (Split-Path $_ -Leaf).ToLower().StartsWith('adapters') } | Sort-Object)
        $bucketRoots.bundles = @($top | Where-Object { (Split-Path $_ -Leaf).ToLower().StartsWith('bundles') } | Sort-Object)
        $bucketRoots.datasets = @($top | Where-Object { (Split-Path $_ -Leaf).ToLower().StartsWith('datasets') } | Sort-Object)
        $mirror = Join-Path $VaultRoot 'download-mirror'
        if (Test-Path -LiteralPath $mirror) {
            $bucketRoots.mirror_models = @(Get-ChildItem -LiteralPath $mirror -Directory -Force |
                Where-Object { $_.Name.ToLower().StartsWith('models') } |
                Select-Object -ExpandProperty FullName | Sort-Object)
        } else {
            $bucketRoots.mirror_models = @()
        }
        foreach ($kind in @('models','adapters','bundles','datasets','mirror_models')) {
            foreach ($root in @($bucketRoots[$kind])) {
                $counts["$kind:$([IO.Path]::GetFileName($root))"] = Count-Files $root
            }
        }
    } else {
        $bucketRoots.models = @(); $bucketRoots.adapters = @(); $bucketRoots.bundles = @(); $bucketRoots.datasets = @(); $bucketRoots.mirror_models = @()
    }

    return [pscustomobject]@{
        label = $Label
        exists = $exists
        vault_root = To-Posix $VaultRoot
        bucket_roots = [ordered]@{
            models = @($bucketRoots.models | ForEach-Object { To-Posix $_ })
            adapters = @($bucketRoots.adapters | ForEach-Object { To-Posix $_ })
            bundles = @($bucketRoots.bundles | ForEach-Object { To-Posix $_ })
            datasets = @($bucketRoots.datasets | ForEach-Object { To-Posix $_ })
            mirror_models = @($bucketRoots.mirror_models | ForEach-Object { To-Posix $_ })
        }
        counts = $counts
        has_models_gguf = Test-Path -LiteralPath (Join-Path $VaultRoot 'models-gguf')
        has_download_mirror = Test-Path -LiteralPath (Join-Path $VaultRoot 'download-mirror')
        inbox_preview = @(Preview-Inbox $VaultRoot)
    }
}

function Maybe-RunScanVault([string]$VaultRoot) {
    if (-not $RunScanVault) { return }
    if (-not $RepoRoot) { throw 'RepoRoot is required with -RunScanVault.' }
    if (-not (Test-Path -LiteralPath $VaultRoot)) { return }
    $scanScript = Join-Path $RepoRoot 'tools\prep\scan_vault.py'
    if (-not (Test-Path -LiteralPath $scanScript)) { throw "scan_vault.py not found: $scanScript" }
    & $PythonExe $scanScript --vault-root $VaultRoot --auto-manifest
    if ($LASTEXITCODE -ne 0) { throw "scan_vault.py failed for $VaultRoot" }
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Maybe-RunScanVault -VaultRoot $RealVaultRoot
Maybe-RunScanVault -VaultRoot $LabVaultRoot

$real = Build-Record -Label 'real' -VaultRoot $RealVaultRoot
$lab  = Build-Record -Label 'lab'  -VaultRoot $LabVaultRoot

$doc = [ordered]@{
    apiVersion = 'noemaforge.disk_e_compare/v1'
    generated_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    compared = @($real, $lab)
    recommendation = if ($real.exists) { 'Prefer real Vault on E:/Vault for Trixie first-boot staging and selection.' } else { 'Real Vault was not found; fallback to lab Vault.' }
}

$doc | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutDir 'vault.disk_e.compare.json') -Encoding UTF8

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("Generated: $($doc.generated_at)")
$lines.Add('')
foreach ($r in @($real,$lab)) {
    $lines.Add("[$($r.label)] VaultRoot : $($r.vault_root)")
    $lines.Add("  exists              : $($r.exists)")
    $lines.Add("  has models-gguf     : $($r.has_models_gguf)")
    $lines.Add("  has download-mirror : $($r.has_download_mirror)")
    $lines.Add('  bucket roots:')
    foreach ($kind in @('models','adapters','bundles','datasets','mirror_models')) {
        foreach ($root in @($r.bucket_roots[$kind])) {
            $key = "$kind:$([IO.Path]::GetFileName($root))"
            $count = if ($r.counts.ContainsKey($key)) { $r.counts[$key] } else { 0 }
            $lines.Add("    [$kind] $root (files=$count)")
        }
    }
    if (@($r.inbox_preview).Count -gt 0) {
        $lines.Add('  inbox preview:')
        foreach ($item in @($r.inbox_preview | Select-Object -First 20)) {
            $lines.Add("    $($item.rel) [$($item.ext)] size=$($item.size)")
        }
    }
    $lines.Add('')
}
$lines.Add("Recommendation: $($doc.recommendation)")
Set-Content -LiteralPath (Join-Path $OutDir 'vault.disk_e.compare.txt') -Value $lines -Encoding UTF8

$rows = foreach ($r in @($real,$lab)) {
    foreach ($kind in @('models','adapters','bundles','datasets','mirror_models')) {
        foreach ($root in @($r.bucket_roots[$kind])) {
            $key = "$kind:$([IO.Path]::GetFileName($root))"
            [pscustomobject]@{
                label = $r.label
                kind = $kind
                root = $root
                file_count = if ($r.counts.ContainsKey($key)) { $r.counts[$key] } else { 0 }
            }
        }
    }
}
$rows | Export-Csv -LiteralPath (Join-Path $OutDir 'vault.disk_e.compare.csv') -NoTypeInformation -Encoding UTF8

Write-Host "Wrote: $(Join-Path $OutDir 'vault.disk_e.compare.json')"
Write-Host "Wrote: $(Join-Path $OutDir 'vault.disk_e.compare.txt')"
Write-Host "Wrote: $(Join-Path $OutDir 'vault.disk_e.compare.csv')"
