#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/bootstrap/build-backends-wsl.sh
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
# File: bootstrap/build-backends-wsl.sh
# Purpose: Provide the script 'build-backends-wsl'.
# Invoked by: shell operators or wrapper scripts.
# Inputs: Positional arguments, environment variables, and files read below.
# Outputs: Console output and filesystem side effects.
# AutoDoc: refreshed 2026-04-09 (heuristic)
# === End NoemaForge Autodoc File Header ===




set -euo pipefail

# build-backends-wsl.sh
#
# Builds optional backend binaries into <seed/noemaforge>/bin.
# Designed to run on a Windows dev box via WSL.
#
# What it can build:
# - noemaforge-llm-gateway (Go) — lightweight local HTTP gateway for CPU backends
# - llama-server (llama.cpp) — open-source, CPU-first model server
#
# Usage:
#   build-backends-wsl.sh /mnt/c/noemaforge/seed/noemaforge
#
# Optional llama.cpp fetch (supply-chain conscious):
#   build-backends-wsl.sh /mnt/c/noemaforge/seed/noemaforge --fetch-llama --llama-ref <commit_or_tag>
#
# Notes:
# - This script is best-effort: distro packages differ.
# - For reproducibility, always pin --llama-ref when fetching sources.

ROOT="${1:-}"
if [[ -z "$ROOT" ]]; then
  echo "usage: $0 <seed/noemaforge root> [--fetch-llama --llama-ref <ref>] [--llama-src <path>]" >&2
  exit 2
fi
shift || true

FETCH_LLAMA="0"
LLAMA_REF=""
LLAMA_SRC=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fetch-llama) FETCH_LLAMA="1"; shift;;
    --llama-ref) LLAMA_REF="$2"; shift 2;;
    --llama-src) LLAMA_SRC="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

mkdir -p "$ROOT/bin" "$ROOT/third_party"

echo "[1/3] Build noemaforge-llm-gateway (requires go)" >&2
if command -v go >/dev/null 2>&1; then
  (cd "$ROOT/src" && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o "$ROOT/bin/noemaforge-llm-gateway" noemaforge-llm-gateway.go)
  chmod +x "$ROOT/bin/noemaforge-llm-gateway"
else
  echo "Go not installed. Install: sudo apt install -y golang-go" >&2
fi

echo "[2/3] Build llama-server (llama.cpp)" >&2

if [[ -z "$LLAMA_SRC" ]]; then
  LLAMA_SRC="$ROOT/third_party/llama.cpp"
fi

LLAMA_REPO_URL="${LLAMA_REPO_URL:-https://github.com/ggml-org/llama.cpp.git}"

if [[ "$FETCH_LLAMA" == "1" ]]; then
  if [[ -z "$LLAMA_REF" ]]; then
    echo "Refusing to fetch llama.cpp without a pinned ref. Provide: --llama-ref <commit_or_tag>" >&2
    exit 2
  fi
  rm -rf "$LLAMA_SRC"
  git clone --filter=blob:none --no-checkout "$LLAMA_REPO_URL" "$LLAMA_SRC"
  (cd "$LLAMA_SRC" && git checkout "$LLAMA_REF")
fi

if [[ -d "$LLAMA_SRC" ]]; then
  sudo apt-get update -y >/dev/null || true
  sudo apt-get install -y git build-essential cmake >/dev/null || true

  (cd "$LLAMA_SRC" && \
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_SERVER=ON >/dev/null && \
    cmake --build build -j --target llama-server >/dev/null)

  # Attempt to locate resulting binary
  if [[ -f "$LLAMA_SRC/build/bin/llama-server" ]]; then
    cp -f "$LLAMA_SRC/build/bin/llama-server" "$ROOT/bin/llama-server"
    chmod +x "$ROOT/bin/llama-server"
    echo "llama-server -> $ROOT/bin/llama-server" >&2
  elif [[ -f "$LLAMA_SRC/build/llama-server" ]]; then
    cp -f "$LLAMA_SRC/build/llama-server" "$ROOT/bin/llama-server"
    chmod +x "$ROOT/bin/llama-server"
    echo "llama-server -> $ROOT/bin/llama-server" >&2
  else
    echo "WARN: llama-server binary not found in expected locations. Check llama.cpp build output." >&2
  fi
else
  echo "llama.cpp sources not found: $LLAMA_SRC" >&2
  echo "- Option A: provide --llama-src <path>" >&2
  echo "- Option B: use --fetch-llama --llama-ref <commit_or_tag>" >&2
fi

echo "[3/3] Done" >&2
