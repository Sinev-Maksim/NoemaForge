# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-update-checksums.ps1
# Zone: release/package
# Version: 0.32.2
# Created: 2026-05-29
# Modified: 2026-05-29
# Purpose: Update the NoemaForge SHA256SUMS checksum chain after content changes.
#   Propagates new hashes for given files into SHA256SUMS, SHA256SUMS_0.32.1,
#   noemaforge/checksums/SHA256SUMS, and recomputes SHA256SUMS.sha256.
# Inputs: List of changed files (relative to project root, or pass --git-diff to
#   auto-detect from 'git diff --name-only HEAD~1').
# Outputs: Updated SHA256SUMS, SHA256SUMS_0.32.1, noemaforge/checksums/SHA256SUMS,
#   SHA256SUMS.sha256. Prints a summary of updated entries.
# Side effects: Writes 4 checksum files.
# Tests: Run with --dry-run to preview changes without writing.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===

[CmdletBinding()]
param(
    [string[]]$Files = @(),
    [string]$Root = "",
    [switch]$GitDiff,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

if (-not $Root) {
    # Three levels up from noemaforge/tools/prep/
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
}

$ProjectChecksums = Join-Path $Root "SHA256SUMS"
$ProjectChecksumsOld = Join-Path $Root "SHA256SUMS_0.32.1"
$ProjectChecksumsSidecar = Join-Path $Root "SHA256SUMS.sha256"
$PackageChecksums = Join-Path $Root "noemaforge/checksums/SHA256SUMS"

if (-not (Test-Path $ProjectChecksums)) {
    Write-Error "SHA256SUMS not found at $ProjectChecksums"
    exit 1
}

# ---------------------------------------------------------------------------
# Collect files to update
# ---------------------------------------------------------------------------

$filesToUpdate = [System.Collections.Generic.List[string]]::new()

if ($GitDiff) {
    $diffOutput = git -C $Root diff --name-only HEAD~1 2>$null
    if ($LASTEXITCODE -ne 0) {
        $diffOutput = git -C $Root diff --name-only HEAD 2>$null
    }
    foreach ($line in ($diffOutput -split "`n")) {
        $line = $line.Trim()
        if ($line) { $filesToUpdate.Add($line) }
    }
    Write-Host "Auto-detected $($filesToUpdate.Count) changed files from git diff"
}

foreach ($f in $Files) {
    $filesToUpdate.Add($f.Trim())
}

if ($filesToUpdate.Count -eq 0) {
    Write-Host "No files specified. Use -Files or -GitDiff."
    exit 0
}

# ---------------------------------------------------------------------------
# Helper: compute SHA256 hash in lowercase
# ---------------------------------------------------------------------------

function Get-SHA256 {
    param([string]$Path)
    return (Get-FileHash $Path -Algorithm SHA256).Hash.ToLower()
}

# ---------------------------------------------------------------------------
# Helper: replace a hash entry in a checksum file
# ---------------------------------------------------------------------------

function Update-ChecksumEntry {
    param(
        [string]$ChecksumFile,
        [string]$EntryPath,
        [string]$NewHash,
        [bool]$IsDryRun
    )
    if (-not (Test-Path $ChecksumFile)) { return $false }
    # Read raw bytes to preserve original line endings (LF, not CRLF)
    $content = [System.IO.File]::ReadAllText($ChecksumFile, [System.Text.Encoding]::UTF8)
    # Match "old_hash  entry_path" with optional carriage return before line end
    $pattern = "(?m)^([0-9a-f]{64})  ($([regex]::Escape($EntryPath)))\r?$"
    if ($content -match $pattern) {
        $oldHash = $Matches[1]
        if ($IsDryRun) {
            Write-Host "  [dry-run] $ChecksumFile : $EntryPath"
            Write-Host "    old: $oldHash"
            Write-Host "    new: $NewHash"
        } else {
            $newContent = [regex]::Replace($content, $pattern, "$NewHash  $EntryPath")
            [System.IO.File]::WriteAllText($ChecksumFile, $newContent, [System.Text.UTF8Encoding]::new($false))
        }
        return $true
    }
    return $false
}

# ---------------------------------------------------------------------------
# Main update loop
# ---------------------------------------------------------------------------

$updated = @()
$notFound = @()

foreach ($relPath in $filesToUpdate) {
    $relPath = $relPath -replace "\\", "/"
    $absPath = Join-Path $Root ($relPath -replace "/", [System.IO.Path]::DirectorySeparatorChar)

    if (-not (Test-Path $absPath)) {
        Write-Warning "File not found, skipping: $relPath"
        $notFound += $relPath
        continue
    }

    $newHash = Get-SHA256 $absPath
    Write-Host "Hashing $relPath -> $newHash"

    # Update project-level SHA256SUMS
    $foundProject = Update-ChecksumEntry -ChecksumFile $ProjectChecksums -EntryPath $relPath -NewHash $newHash -IsDryRun $DryRun.IsPresent
    # Update mirror SHA256SUMS_0.32.1
    $foundMirror = Update-ChecksumEntry -ChecksumFile $ProjectChecksumsOld -EntryPath $relPath -NewHash $newHash -IsDryRun $DryRun.IsPresent

    # If the path starts with "noemaforge/", also update package-level checksums
    # (stripping the "noemaforge/" prefix)
    $foundPackage = $false
    if ($relPath -match "^noemaforge/(.+)$") {
        $pkgPath = $Matches[1]
        $foundPackage = Update-ChecksumEntry -ChecksumFile $PackageChecksums -EntryPath $pkgPath -NewHash $newHash -IsDryRun $DryRun.IsPresent
    }

    if ($foundProject -or $foundMirror -or $foundPackage) {
        $updated += $relPath
    } else {
        Write-Warning "  No matching entry found in any checksum file for: $relPath"
        $notFound += $relPath
    }
}

# ---------------------------------------------------------------------------
# Update noemaforge/checksums/SHA256SUMS hash in project-level checksums
# ---------------------------------------------------------------------------

if ($updated.Count -gt 0 -and -not $DryRun) {
    Write-Host ""
    Write-Host "Updating noemaforge/checksums/SHA256SUMS entry in project checksums..."
    $pkgHash = Get-SHA256 $PackageChecksums
    $r1 = Update-ChecksumEntry -ChecksumFile $ProjectChecksums -EntryPath "noemaforge/checksums/SHA256SUMS" -NewHash $pkgHash -IsDryRun $false
    $r2 = Update-ChecksumEntry -ChecksumFile $ProjectChecksumsOld -EntryPath "noemaforge/checksums/SHA256SUMS" -NewHash $pkgHash -IsDryRun $false
    if ($r1) { Write-Host "  Updated SHA256SUMS: noemaforge/checksums/SHA256SUMS -> $pkgHash" }
    if ($r2) { Write-Host "  Updated SHA256SUMS_0.32.1: noemaforge/checksums/SHA256SUMS -> $pkgHash" }
}

# ---------------------------------------------------------------------------
# Recompute SHA256SUMS.sha256 sidecar
# ---------------------------------------------------------------------------

if ($updated.Count -gt 0 -and -not $DryRun) {
    Write-Host ""
    Write-Host "Recomputing SHA256SUMS.sha256..."
    $mainHash = Get-SHA256 $ProjectChecksums
    [System.IO.File]::WriteAllText($ProjectChecksumsSidecar, "$mainHash`n", [System.Text.UTF8Encoding]::new($false))
    Write-Host "  SHA256SUMS.sha256 -> $mainHash"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "=== SHA256SUMS update summary ==="
Write-Host "Updated entries : $($updated.Count)"
Write-Host "Not found       : $($notFound.Count)"
if ($DryRun) { Write-Host "(dry-run: no files were written)" }

if ($notFound.Count -gt 0) {
    Write-Host ""
    Write-Host "Files with no matching checksum entry:"
    foreach ($f in $notFound) { Write-Host "  $f" }
}
