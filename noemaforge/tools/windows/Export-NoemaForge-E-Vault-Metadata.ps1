# === NoemaForge Autodoc File Header ===
# File: tools/windows/Export-NoemaForge-E-Vault-Metadata.ps1
# Purpose: Helper / validation script 'Export-NoemaForge-E-Vault-Metadata.ps1'.
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
# File: tools/windows/Export-NoemaForge-E-Vault-Metadata.ps1
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
    [string]$VaultRoot = 'E:\Vault',
    [string]$OutDir = 'E:\Vault\manifests\noemaforge-metadata-export',
    [string]$RepoRoot = '',
    [string]$PythonExe = 'py',
    [switch]$RunScanVault,
    [switch]$FullHash
)

$ErrorActionPreference = 'Stop'

function Get-Sha256 {
    param([string]$Path)
    try {
        return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    }
    catch {
        return ''
    }
}

function Convert-ToPosixPath {
    param([string]$Path)
    return ($Path -replace '\\','/')
}

function Get-RelativePosixPath {
    param([string]$Root, [string]$Path)
    $rootUri = [System.Uri]((Resolve-Path $Root).Path + [IO.Path]::DirectorySeparatorChar)
    $pathUri = [System.Uri](Resolve-Path $Path).Path
    return $rootUri.MakeRelativeUri($pathUri).ToString().Replace('%20',' ')
}

function Get-BucketRoots {
    param([string]$Root)
    $top = Get-ChildItem -LiteralPath $Root -Directory -Force | Select-Object -ExpandProperty FullName
    $models = @($top | Where-Object { (Split-Path $_ -Leaf).ToLower().StartsWith('models') } | Sort-Object)
    $adapters = @($top | Where-Object { (Split-Path $_ -Leaf).ToLower().StartsWith('adapters') } | Sort-Object)
    $bundles = @($top | Where-Object { (Split-Path $_ -Leaf).ToLower().StartsWith('bundles') } | Sort-Object)
    $datasets = @($top | Where-Object { (Split-Path $_ -Leaf).ToLower().StartsWith('datasets') } | Sort-Object)
    $mirror = Join-Path $Root 'download-mirror'
    $mirrorModels = @()
    if (Test-Path -LiteralPath $mirror) {
        $mirrorModels = @(Get-ChildItem -LiteralPath $mirror -Directory -Force | Where-Object { $_.Name.ToLower().StartsWith('models') } | Select-Object -ExpandProperty FullName | Sort-Object)
    }
    [ordered]@{
        models = $models
        adapters = $adapters
        bundles = $bundles
        datasets = $datasets
        mirror_models = $mirrorModels
    }
}

function Resolve-InboxDestination {
    param([string]$VaultRoot, [string]$RelIn)

    $p = ($RelIn -replace '\\','/')
    $top = ''
    if ($p.Contains('/')) {
        $top = $p.Split('/')[0].ToLowerInvariant()
    } else {
        $top = $p.ToLowerInvariant()
    }

    if ($top.StartsWith('models') -or $top.StartsWith('adapters') -or $top.StartsWith('bundles') -or @('datasets','manifests').Contains($top)) {
        return $p
    }

    $ext = [IO.Path]::GetExtension($p).ToLowerInvariant()
    $base = [IO.Path]::GetFileName($p).ToLowerInvariant()

    if ($ext -eq '.gguf') {
        if (Test-Path -LiteralPath (Join-Path $VaultRoot 'models-gguf')) {
            return "models-gguf/inbox/$p"
        }
        return "models/inbox/$p"
    }
    if (@('.safetensors','.bin','.pt','.pth','.onnx') -contains $ext) {
        return "models/inbox/$p"
    }
    if (@('.zip','.tar','.tgz','.gz') -contains $ext) {
        return "bundles/inbox/$p"
    }
    if ((@('.json','.yml','.yaml') -contains $ext) -and $base.Contains('manifest')) {
        return "manifests/inbox/$p"
    }
    return "misc/inbox/$p"
}

function Get-FileInventory {
    param([string]$Root, [switch]$IncludeHashes)

    if (-not (Test-Path -LiteralPath $Root)) {
        return @()
    }

    $items = New-Object System.Collections.Generic.List[object]
    Get-ChildItem -LiteralPath $Root -File -Recurse -Force | ForEach-Object {
        $item = [ordered]@{
            rel = Get-RelativePosixPath -Root $Root -Path $_.FullName
            name = $_.Name
            size = [int64]$_.Length
            ext = $_.Extension.ToLowerInvariant()
            mtime_utc = $_.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
        }
        if ($IncludeHashes) {
            $item.sha256 = Get-Sha256 -Path $_.FullName
        }
        $items.Add([pscustomobject]$item)
    }
    return $items
}

if (-not (Test-Path -LiteralPath $VaultRoot)) {
    throw "Vault root not found: $VaultRoot"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$bucketRoots = Get-BucketRoots -Root $VaultRoot
$inboxRoot = Join-Path $VaultRoot 'inbox'
$inboxPreview = @()
if (Test-Path -LiteralPath $inboxRoot) {
    Get-ChildItem -LiteralPath $inboxRoot -File -Recurse -Force | ForEach-Object {
        $rel = Get-RelativePosixPath -Root $inboxRoot -Path $_.FullName
        $inboxPreview += [pscustomobject]@{
            rel = $rel
            proposed_dest = Resolve-InboxDestination -VaultRoot $VaultRoot -RelIn $rel
            size = [int64]$_.Length
            mtime_utc = $_.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
        }
    }
}

$summary = [ordered]@{
    apiVersion = 'noemaforge.disk_e_metadata/v1'
    generated_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    vault_root = (Convert-ToPosixPath -Path (Resolve-Path $VaultRoot).Path)
    bucket_roots = [ordered]@{
        models = @($bucketRoots.models | ForEach-Object { Convert-ToPosixPath -Path $_ })
        adapters = @($bucketRoots.adapters | ForEach-Object { Convert-ToPosixPath -Path $_ })
        bundles = @($bucketRoots.bundles | ForEach-Object { Convert-ToPosixPath -Path $_ })
        datasets = @($bucketRoots.datasets | ForEach-Object { Convert-ToPosixPath -Path $_ })
        mirror_models = @($bucketRoots.mirror_models | ForEach-Object { Convert-ToPosixPath -Path $_ })
    }
    special_paths = [ordered]@{
        queue = (Convert-ToPosixPath -Path (Join-Path $VaultRoot '_queue'))
        inbox = (Convert-ToPosixPath -Path $inboxRoot)
        manifests = (Convert-ToPosixPath -Path (Join-Path $VaultRoot 'manifests'))
        download_mirror = (Convert-ToPosixPath -Path (Join-Path $VaultRoot 'download-mirror'))
        hf_home = (Convert-ToPosixPath -Path (Join-Path $VaultRoot 'hf-home'))
    }
    counts = [ordered]@{}
    inbox_preview = $inboxPreview
}

$inventory = [ordered]@{}
foreach ($kind in @('models','adapters','bundles','datasets','mirror_models')) {
    $inventory[$kind] = @()
    foreach ($root in $bucketRoots[$kind]) {
        $files = Get-FileInventory -Root $root -IncludeHashes:$FullHash
        $inventory[$kind] += [pscustomobject]@{
            root = (Convert-ToPosixPath -Path $root)
            file_count = @($files).Count
            files = $files
        }
        $summary.counts[$kind + ':' + (Split-Path $root -Leaf)] = @($files).Count
    }
}

$summary.inventory = $inventory

$metaPath = Join-Path $OutDir 'vault.disk_e.metadata.json'
$txtPath = Join-Path $OutDir 'vault.disk_e.summary.txt'
$csvPath = Join-Path $OutDir 'vault.disk_e.roots.csv'

$summary | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $metaPath -Encoding UTF8

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("Generated: $($summary.generated_at)")
$lines.Add("VaultRoot : $($summary.vault_root)")
$lines.Add('')
$lines.Add('Bucket roots:')
foreach ($kind in $summary.bucket_roots.Keys) {
    foreach ($root in $summary.bucket_roots[$kind]) {
        $lines.Add("  [$kind] $root")
    }
}
$lines.Add('')
$lines.Add('Counts:')
foreach ($k in $summary.counts.Keys) {
    $lines.Add("  $k = $($summary.counts[$k])")
}
$lines.Add('')
$lines.Add('Inbox preview:')
foreach ($row in $inboxPreview | Select-Object -First 200) {
    $lines.Add("  $($row.rel) -> $($row.proposed_dest)")
}
Set-Content -LiteralPath $txtPath -Value $lines -Encoding UTF8

$rootRows = foreach ($kind in $summary.bucket_roots.Keys) {
    foreach ($root in $summary.bucket_roots[$kind]) {
        [pscustomobject]@{
            kind = $kind
            root = $root
            file_count = $summary.counts[($kind + ':' + (Split-Path $root -Leaf))]
        }
    }
}
$rootRows | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8

if ($RunScanVault) {
    if (-not $RepoRoot) {
        throw 'RepoRoot is required when -RunScanVault is used.'
    }
    $scanScript = Join-Path $RepoRoot 'tools\prep\scan_vault.py'
    if (-not (Test-Path -LiteralPath $scanScript)) {
        throw "scan_vault.py not found: $scanScript"
    }
    $args = @($scanScript, '--vault-root', $VaultRoot, '--auto-manifest')
    if ($FullHash) { $args += '--full-hash' }
    & $PythonExe @args
}

Write-Host "Metadata written to: $metaPath"
Write-Host "Summary written to : $txtPath"
Write-Host "CSV written to     : $csvPath"
