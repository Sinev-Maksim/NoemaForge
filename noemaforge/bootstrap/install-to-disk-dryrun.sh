#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/bootstrap/install-to-disk-dryrun.sh
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
# === NoemaForge Autodoc File Header ===
# File: bootstrap/install-to-disk-dryrun.sh
# Purpose: Provide the script 'install-to-disk-dryrun'.
# Invoked by: shell operators or wrapper scripts.
# Inputs: Positional arguments, environment variables, and files read below.
# Outputs: Console output and filesystem side effects.
# AutoDoc: refreshed 2026-04-09 (heuristic)
# === End NoemaForge Autodoc File Header ===




set -euo pipefail

# NoemaForge install-to-disk (dry-run)
#
# This script does NOT write to disks.
# It prints a *reviewable* plan that you can run manually.

TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 /dev/nvme0n1" >&2
  echo "\nDetected disks:" >&2
  lsblk -d -o NAME,SIZE,MODEL,TYPE || true
  exit 2
fi

if [[ ! -b "$TARGET" ]]; then
  echo "ERROR: $TARGET is not a block device" >&2
  exit 2
fi

echo "# NoemaForge install plan (DRY RUN)"
echo "# Target: $TARGET"
echo "# Review carefully before running anything."
echo

echo "## Suggested partitioning (UEFI)"
echo "# WARNING: This will destroy data on $TARGET"
echo "sudo sgdisk --zap-all $TARGET"
echo "sudo sgdisk -n 1:0:+1G -t 1:ef00 -c 1:EFI $TARGET"
echo "sudo sgdisk -n 2:0:0   -t 2:8300 -c 2:NoemaForge $TARGET"
echo

echo "## Format"
echo "sudo mkfs.vfat -F32 ${TARGET}p1"
echo "sudo mkfs.ext4 -F ${TARGET}p2"
echo

echo "## Mount"
echo "sudo mkdir -p /mnt/noemaforge"
echo "sudo mount ${TARGET}p2 /mnt/noemaforge"
echo "sudo mkdir -p /mnt/noemaforge/boot"
echo "sudo mount ${TARGET}p1 /mnt/noemaforge/boot"
echo

echo "## Copy seed"
echo "# Assuming seed kit is available at /opt/noemaforge-seed"
echo "sudo rsync -aHAX --delete /opt/noemaforge-seed/ /mnt/noemaforge/opt/noemaforge/"
echo

echo "## Bootloader"
echo "# Install your preferred bootloader (systemd-boot or GRUB) here."
echo "# This seed kit ships BootDoctor + an installer plan, but does not auto-install the OS."

echo

echo "Done. (dry-run only)"
